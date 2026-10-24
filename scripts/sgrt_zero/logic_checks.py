#!/usr/bin/env python3
"""Independent numerical checks for local service profiles and nested unions.

These checks examine supplied evidence. They do not turn institution registers
or estimated accessibility into observed trips, and do not select a desired
number of levels or a predetermined top city.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

ISSUE_COLUMNS = ['check', 'unit_id', 'origin_id', 'detail']


def issues_frame(rows):
    return pd.DataFrame(rows, columns=ISSUE_COLUMNS)


def known(value):
    return pd.notna(value) and str(value).strip() != ''


def provider_anchor(row):
    """A named settlement and an unresolved physical site are different anchors."""
    if known(row.get('provider_anchor_key')):
        return str(row['provider_anchor_key'])
    if known(row.get('provider_settlement_id')):
        return 'np:' + str(row['provider_settlement_id'])
    if known(row.get('provider_site_id')):
        return 'site:' + str(row.get('source_id', 'unknown_source')) + ':' + str(row['provider_site_id'])
    return None


def check_direct_admission(edges, limits, metric_columns=None):
    """Check origin→selected-provider costs in their declared function units.

    ``limits`` and ``metric_columns`` must be supplied by the scenario. A walking
    separation screen can use point_separation_km; car minutes are not compared
    with a walking metre threshold. Non-admitted distant links are retained and
    are not treated as failures or absence of an external need.
    """
    required = {'origin_id', 'service_family', 'l0_admitted'}
    if not required <= set(edges):
        raise ValueError('Missing edge fields: ' + repr(sorted(required-set(edges))))
    metrics = metric_columns or {}
    rows = []
    for _, r in edges[edges.l0_admitted.eq(True)].iterrows():
        base = dict(unit_id=r.get('unit_id'), origin_id=r.origin_id)
        if provider_anchor(r) is None:
            rows.append(dict(check='admitted_without_known_provider', detail=r.service_family, **base))
        if r.service_family not in limits:
            rows.append(dict(check='admitted_function_has_no_declared_bound', detail=r.service_family, **base))
            continue
        col = metrics.get(r.service_family, 'cost_minutes')
        raw_value = r.get(col)
        value = pd.to_numeric(raw_value, errors='coerce')
        if not known(value) or not np.isfinite(float(value)):
            rows.append(dict(check='admitted_without_finite_direct_cost', detail=col, **base))
        elif float(value) < 0:
            rows.append(dict(check='negative_direct_cost', detail=str(value), **base))
        elif float(value) > float(limits[r.service_family]) + 1e-8:
            rows.append(dict(check='direct_cost_exceeds_function_bound', detail=f'{col}={value}; bound={limits[r.service_family]}', **base))
    return issues_frame(rows)


def profile_coverage(edges, origin_ids, daily_families):
    """Describe evidence completeness without declaring all needs satisfied."""
    good = edges[edges.l0_admitted.eq(True)].copy()
    good['anchor'] = good.apply(provider_anchor, axis=1)
    good = good[good.anchor.notna() & good.service_family.isin(daily_families)]
    counts = good.groupby('origin_id').service_family.nunique()
    out = pd.DataFrame({'origin_id':list(origin_ids)})
    out['known_daily_channels'] = out.origin_id.map(counts).fillna(0).astype(int)
    out['declared_daily_channels'] = len(set(daily_families))
    out['evidence_state'] = np.where(out.known_daily_channels.eq(0), 'no_supported_local_service_link',
        np.where(out.known_daily_channels.eq(out.declared_daily_channels), 'all_declared_channels_have_candidates', 'partial_daily_service_evidence'))
    out['all_needs_satisfied'] = pd.Series(pd.NA, index=out.index, dtype='boolean')
    out['absence_of_service_established'] = False
    return out


def check_profile_atoms(memberships, edges, daily_families):
    """Exact profile atoms cannot mix providers or merge all-unknown origins.

    Run separately for source/scenario alternatives. Known NP anchors can group
    several buildings of the same settlement, so this does not prove that every
    member visits the same physical building or polygon contiguity.
    """
    admitted = edges[edges.l0_admitted.eq(True)].copy()
    admitted['anchor'] = admitted.apply(provider_anchor, axis=1)
    admitted = admitted[admitted.service_family.isin(daily_families)]
    duplicate = admitted.duplicated(['origin_id','service_family'], keep=False)
    if duplicate.any():
        raise ValueError('Multiple admitted choices per origin/function; separate scenarios first')
    lookup = {(r.origin_id,r.service_family):r.anchor for r in admitted.itertuples()}
    rows = []
    for unit, frame in memberships.groupby('unit_id',sort=False):
        profiles = {o:tuple(lookup.get((o,f)) for f in daily_families) for o in frame.origin_id}
        if len(set(profiles.values())) > 1:
            rows.append(dict(check='atom_mixes_distinct_service_profiles', unit_id=unit, origin_id=None, detail=str(len(set(profiles.values())))))
        all_unknown = [o for o,p in profiles.items() if all(x is None or pd.isna(x) for x in p)]
        if all_unknown and len(profiles) > 1:
            rows.append(dict(check='all_unknown_origins_merged',unit_id=unit,origin_id=None,detail=str(all_unknown[:10])))
    return issues_frame(rows)


def check_nested_unions(child_memberships, assignments, parent_memberships, *, disjoint_parents=False):
    """Every declared parent must contain the exact union of its complete children."""
    expected = assignments[['child_unit_id','parent_unit_id']].merge(
        child_memberships[['child_unit_id','origin_id']],on='child_unit_id',how='left',validate='many_to_many')
    rows = []
    for parent, frame in expected.groupby('parent_unit_id',sort=False):
        target = set(frame.origin_id.dropna())
        actual = set(parent_memberships.loc[parent_memberships.parent_unit_id.eq(parent),'origin_id'])
        if target != actual:
            rows.append(dict(check='parent_is_not_exact_union_of_children',unit_id=parent,origin_id=None,
                detail=json.dumps({'missing':sorted(target-actual),'extra':sorted(actual-target)})))
    unknown_children = set(assignments.child_unit_id)-set(child_memberships.child_unit_id)
    for child in sorted(unknown_children):
        rows.append(dict(check='unknown_child_unit',unit_id=child,origin_id=None,detail=''))
    extra_parents=set(parent_memberships.parent_unit_id)-set(assignments.parent_unit_id)
    for parent in sorted(extra_parents):
        rows.append(dict(check='parent_without_declared_children',unit_id=parent,origin_id=None,detail=''))
    if disjoint_parents:
        groups=parent_memberships.groupby('origin_id').parent_unit_id.nunique()
        for origin in groups[groups.gt(1)].index:
            rows.append(dict(check='overlap_in_claimed_parent_partition',unit_id=None,origin_id=origin,detail=str(groups[origin])))
    return issues_frame(rows)


def check_direct_core_cover(memberships, cores, direct_costs, max_minutes, *, common_core_required=False):
    """Require supplied directional costs, not chains or reversed routes.

    Each member needs a finite origin→core cost. With multiple cores, union
    coverage alone does not establish compactness of the core set; use a
    separate, explicitly sourced bound or external-reference comparison.
    """
    if direct_costs.duplicated(['origin_id','core_id']).any():
        raise ValueError('Repeated directional origin/core costs')
    rows=[]
    for unit,g in memberships.groupby('unit_id',sort=False):
        origins=set(g.origin_id)
        nuclei=set(cores.loc[cores.unit_id.eq(unit),'core_id'])
        d=direct_costs[direct_costs.origin_id.isin(origins)&direct_costs.core_id.isin(nuclei)].copy()
        finite=np.isfinite(pd.to_numeric(d.cost_minutes,errors='coerce'))
        d=d[finite & d.cost_minutes.ge(0) & d.cost_minutes.le(float(max_minutes)+1e-8)]
        uncovered=origins-set(d.origin_id)
        for origin in sorted(uncovered):
            rows.append(dict(check='member_has_no_direct_core_within_bound',unit_id=unit,origin_id=origin,detail=str(max_minutes)))
        if common_core_required and not uncovered:
            covered=d.groupby('core_id').origin_id.nunique()
            if not covered.eq(len(origins)).any():
                rows.append(dict(check='no_single_common_core_covers_all_members',unit_id=unit,origin_id=None,detail=str(len(origins))))
    return issues_frame(rows)


def check_promotions(promotions):
    """Check explicit new evidence for each claimed higher-order attachment."""
    allowed={'higher_service_order','observed_intercentre_flow','external_estimated_fua_reference'}
    rows=[]
    for _,r in promotions.iterrows():
        base=dict(unit_id=r.get('parent_unit_id'),origin_id=r.get('child_unit_id'))
        if r.get('promotion_basis') not in allowed:
            rows.append(dict(check='promotion_without_new_functional_or_external_evidence',detail=str(r.get('promotion_basis')),**base))
        if not known(r.get('evidence_source_id')):
            rows.append(dict(check='promotion_source_not_identified',detail='',**base))
        observed=r.get('is_observed_flow',False)
        if r.get('promotion_basis')=='external_estimated_fua_reference' and pd.notna(observed) and bool(observed):
            rows.append(dict(check='estimated_fua_mislabelled_as_observed_flow',detail='',**base))
        if r.get('promotion_basis')=='higher_service_order':
            existing=r.get('child_service_orders_json','[]')
            existing=json.loads(existing) if isinstance(existing,str) else existing
            existing=[] if existing is None else existing
            if not known(r.get('new_service_order')) or r.get('new_service_order') in existing:
                rows.append(dict(check='same_function_order_reused_as_higher_level',detail=str(r.get('new_service_order')),**base))
    return issues_frame(rows)


def check_external_reference_parents(memberships, selected_edges, point_fua_links):
    """All members and their selected higher providers need the same eFUA.

    Memberships: parent_unit_id, origin_id, eFUA_ID. Selected evidence edges:
    parent_unit_id, origin_id, provider_point_key. Spatial lookup:
    point_key, eFUA_ID. Point keys must distinguish actual facility geometry
    from a settlement reference point; the latter remains a spatial proxy.
    """
    links={p:set(map(int,g.eFUA_ID)) for p,g in point_fua_links.groupby('point_key')}
    rows=[]
    for _,m in memberships.iterrows():
        base=dict(unit_id=m.parent_unit_id,origin_id=m.origin_id)
        target=int(m.eFUA_ID)
        origin_areas=links.get(m.origin_id,set())
        if len(origin_areas)>1:
            rows.append(dict(check='ambiguous_external_boundary_origin',detail=str(sorted(origin_areas)),**base))
        if target not in origin_areas:
            rows.append(dict(check='parent_member_outside_claimed_external_reference',detail=str(target),**base))
        edges=selected_edges[selected_edges.parent_unit_id.eq(m.parent_unit_id)&selected_edges.origin_id.eq(m.origin_id)]
        if edges.empty:
            rows.append(dict(check='parent_member_without_selected_higher_provider_evidence',detail='',**base))
        for _,edge in edges.iterrows():
            provider_areas=links.get(edge.provider_point_key,set())
            if len(provider_areas)>1:
                rows.append(dict(check='ambiguous_external_boundary_provider',detail=str(sorted(provider_areas)),**base))
            if target not in provider_areas:
                rows.append(dict(check='higher_provider_outside_claimed_external_reference',detail=str(edge.provider_point_key),**base))
    return issues_frame(rows)


def check_nontrivial_spatial_merges(child_memberships, assignments, parent_memberships):
    """A new function can be described without inventing a new spatial merger.

    Call this only for assignments declared to be *new spatial unions*, not
    carry-forward units or a new functional label on unchanged territory.
    """
    child_sets={u:frozenset(g.origin_id) for u,g in child_memberships.groupby('child_unit_id')}
    parent_sets={u:frozenset(g.origin_id) for u,g in parent_memberships.groupby('parent_unit_id')}
    rows=[]
    for parent,group in assignments.groupby('parent_unit_id'):
        p=parent_sets.get(parent,frozenset())
        if any(p==child_sets.get(child) for child in group.child_unit_id):
            rows.append(dict(check='unchanged_membership_relabelled_as_new_spatial_merge',unit_id=parent,origin_id=None,detail=str(len(p))))
    return issues_frame(rows)


def gpkg_wkb(blob):
    """Read the public GeoPackage geometry header, preserving embedded SRS."""
    if blob[:2] != b'GP':
        raise ValueError('Not a GeoPackage geometry')
    envelope=(blob[3]>>1)&7
    sizes={0:0,1:32,2:48,3:48,4:64}
    if envelope not in sizes:
        raise ValueError('Unsupported GeoPackage envelope')
    return blob[8+sizes[envelope]:]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1048576),b''):h.update(b)
    return h.hexdigest()


def locate_external_fua_points(point_frame, polygon_frame):
    """Spatial lookup without inventing ownership or selecting nearest polygons.

    Points: point_key, lat, lon. Polygons: eFUA_ID, geometry_wkb,
    geometry_crs, optionally Cntry_ISO. Returns all point/polygon matches and
    an explicit point status; multiple boundary matches are never collapsed.
    """
    from shapely import from_wkb, points, STRtree
    from pyproj import Transformer
    for key,g in point_frame.groupby('point_key'):
        if len(g[['lat','lon']].drop_duplicates())>1:
            raise ValueError('Point key has conflicting geometries: '+str(key))
    frame=point_frame[['point_key','lat','lon']].drop_duplicates('point_key').reset_index(drop=True)
    if frame.point_key.isna().any():raise ValueError('Point keys must be explicit')
    frame['lat']=pd.to_numeric(frame.lat,errors='coerce');frame['lon']=pd.to_numeric(frame.lon,errors='coerce')
    valid=np.isfinite(frame.lat)&np.isfinite(frame.lon)
    valid&=frame.lat.between(-90,90)&frame.lon.between(-180,180)
    crs=polygon_frame.geometry_crs.unique()
    if len(crs)!=1:raise ValueError('Expected one declared polygon CRS')
    project=Transformer.from_crs('EPSG:4326',crs[0],always_xy=True)
    finite=frame[valid]
    x,y=project.transform(finite.lon.to_numpy(),finite.lat.to_numpy())
    geo=from_wkb(polygon_frame.geometry_wkb.to_numpy())
    pairs=STRtree(geo).query(points(x,y),predicate='intersects')
    links=pd.DataFrame({'point_key':finite.iloc[pairs[0]].point_key.to_numpy(),
        'eFUA_ID':polygon_frame.iloc[pairs[1]].eFUA_ID.to_numpy()})
    if 'Cntry_ISO' in polygon_frame:
        links['source_country_iso']=links.eFUA_ID.map(polygon_frame.set_index('eFUA_ID').Cntry_ISO)
    count=links.groupby('point_key').eFUA_ID.nunique()
    ids=links.groupby('point_key').eFUA_ID.agg(lambda x:json.dumps(sorted(set(map(int,x)))))
    frame['external_boundary_match_count']=frame.point_key.map(count).fillna(0).astype(int)
    frame['external_efua_ids_json']=frame.point_key.map(ids).fillna('[]')
    frame['external_boundary_status']=np.where(~valid,'geometry_unknown_or_invalid_no_boundary_claim',
        np.where(frame.external_boundary_match_count.eq(0),'outside_modelled_reference_not_evidence_of_isolation',
        np.where(frame.external_boundary_match_count.eq(1),'one_modelled_reference_contains_point','ambiguous_multiple_reference_boundaries')))
    return links,frame


def extract_russia_efua(gpkg_path, reference_path, output):
    """Extract an independent estimated 2015 metro reference, not Russian OD.

    Optional dependencies: shapely 2.1.2, pyproj 3.7.2. Raw source coordinates are
    ESRI:54009 (World Mollweide), not EPSG:54009. WKB and CRS are preserved.
    """
    import shapely
    from shapely import from_wkb, points, STRtree
    from shapely.ops import transform
    from pyproj import Transformer

    gpkg_path,reference_path,output=map(Path,[gpkg_path,reference_path,output]);output.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(gpkg_path)
    table=conn.execute('select table_name from gpkg_contents').fetchone()[0]
    raw=pd.read_sql_query(f'SELECT * FROM "{table}" WHERE Cntry_ISO = ?',conn,params=['RUS'])
    conn.close()
    raw['eFUA_ID']=raw.eFUA_ID.astype(int)
    geometries=from_wkb(raw.geom.map(gpkg_wkb).to_numpy())
    raw=raw.drop(columns='geom')
    raw['geometry_wkb']=[bytes(shapely.to_wkb(g)) for g in geometries]
    raw['geometry_crs']='ESRI:54009'
    raw['geometry_area_km2']=shapely.area(geometries)/1e6
    raw['source_area_km2']=raw.FUA_area
    raw['source_epoch']=2015
    raw['is_observed_russian_commuting']=False
    raw['reference_role']='independent_estimated_upper_comparator'
    raw.to_parquet(output/'russia_efua_2015.parquet',index=False,compression='zstd')

    to_wgs=Transformer.from_crs('ESRI:54009','EPSG:4326',always_xy=True).transform
    geojson={'type':'FeatureCollection','features':[{'type':'Feature','geometry':shapely.geometry.mapping(transform(to_wgs,g)),
        'properties':{'eFUA_ID':int(r.eFUA_ID),'name':r.eFUA_name,'source_epoch':2015,'source_area_km2':float(r.FUA_area),'is_observed_russian_commuting':False}}
        for r,g in zip(raw.itertuples(),geometries)]}
    (output/'russia_efua_2015.geojson').write_text(json.dumps(geojson,ensure_ascii=False)+'\n')

    reference=pd.read_parquet(reference_path)
    origin_mask=reference.analysis_origin if 'analysis_origin' in reference else reference.ordinary_spatial_2021
    ordinary=reference[origin_mask & reference.source_record_id.notna()].copy()
    finite=np.isfinite(ordinary.lat)&np.isfinite(ordinary.lon)
    ordinary=ordinary[finite].reset_index(drop=True)
    project=Transformer.from_crs('EPSG:4326','ESRI:54009',always_xy=True)
    x,y=project.transform(ordinary.lon.to_numpy(),ordinary.lat.to_numpy())
    # Keep original country labels, while detecting source-country differences
    # through geometry. The adopted research frame must not disappear merely
    # because the external 2015 source uses a different country code.
    conn=sqlite3.connect(gpkg_path)
    other=pd.read_sql_query(f'SELECT * FROM "{table}" WHERE Cntry_ISO <> ?',conn,params=['RUS'])
    conn.close()
    other_geometry=from_wkb(other.geom.map(gpkg_wkb).to_numpy())
    other_pairs=STRtree(other_geometry).query(points(x,y),predicate='intersects')
    selected=np.unique(other_pairs[1])
    if len(selected):
        extra=other.iloc[selected].drop(columns='geom').copy().reset_index(drop=True)
        extra_geo=other_geometry[selected]
        extra['eFUA_ID']=extra.eFUA_ID.astype(int)
        extra['geometry_wkb']=[bytes(shapely.to_wkb(g)) for g in extra_geo]
        extra['geometry_crs']='ESRI:54009'
        extra['geometry_area_km2']=shapely.area(extra_geo)/1e6
        extra['source_area_km2']=extra.FUA_area
        extra['source_epoch']=2015
        extra['is_observed_russian_commuting']=False
        extra['reference_role']='independent_estimated_upper_comparator'
        raw=pd.concat([raw,extra],ignore_index=True)
        geometries=np.concatenate([geometries,extra_geo])
    pairs=STRtree(geometries).query(points(x,y),predicate='intersects')
    links=pd.DataFrame({'source_record_id':ordinary.iloc[pairs[0]].source_record_id.to_numpy(),
        'eFUA_ID':raw.iloc[pairs[1]].eFUA_ID.to_numpy()})
    links['source_epoch']=2015
    links['source_role']='estimated_2015_boundary_contains_census2021_point_not_observed_trip'
    links['source_country_iso']=links.eFUA_ID.map(raw.set_index('eFUA_ID').Cntry_ISO)
    links['is_nonadditive_city_context']=~links.source_record_id.isin(ordinary.loc[ordinary.ordinary_spatial_2021,'source_record_id'])
    links.to_parquet(output/'settlement_external_fua_links.parquet',index=False,compression='zstd')
    grouped=links.groupby('source_record_id').eFUA_ID.agg(lambda a:json.dumps(sorted(set(map(int,a)))))
    states=ordinary[['source_record_id','name','region','lat','lon','population_role','ordinary_spatial_2021']].copy()
    states['external_efua_ids_json']=states.source_record_id.map(grouped).fillna('[]')
    states['external_boundary_match_count']=states.source_record_id.map(links.groupby('source_record_id').eFUA_ID.nunique()).fillna(0).astype(int)
    states['external_boundary_status']=np.where(states.external_boundary_match_count.eq(0),'outside_modelled_2015_efua_not_evidence_of_isolation',
        np.where(states.external_boundary_match_count.eq(1),'one_estimated_2015_efua_contains_point','multiple_estimated_2015_efua_boundaries_contain_point'))
    states.to_parquet(output/'settlement_external_fua_status.parquet',index=False,compression='zstd')
    ordinary_links=links[~links.is_nonadditive_city_context]
    raw['ordinary_census2021_point_count']=raw.eFUA_ID.map(ordinary_links.groupby('eFUA_ID').source_record_id.nunique()).fillna(0).astype(int)
    raw['analysis_point_count']=raw.eFUA_ID.map(links.groupby('eFUA_ID').source_record_id.nunique()).fillna(0).astype(int)
    raw.to_parquet(output/'analysis_frame_efua_2015.parquet',index=False,compression='zstd')
    raw[raw.Cntry_ISO.eq('RUS')].to_parquet(output/'russia_efua_2015.parquet',index=False,compression='zstd')
    raw.drop(columns='geometry_wkb').to_csv(output/'analysis_frame_efua_2015_attributes.csv',index=False)
    raw[raw.Cntry_ISO.eq('RUS')].drop(columns='geometry_wkb').to_csv(output/'russia_efua_2015_attributes.csv',index=False)
    geojson={'type':'FeatureCollection','features':[{'type':'Feature','geometry':shapely.geometry.mapping(transform(to_wgs,g)),
        'properties':{'eFUA_ID':int(r.eFUA_ID),'name':r.eFUA_name,'source_country_iso':r.Cntry_ISO,'source_epoch':2015,
            'source_area_km2':float(r.FUA_area),'is_observed_russian_commuting':False}} for r,g in zip(raw.itertuples(),geometries)]}
    (output/'analysis_frame_efua_2015.geojson').write_text(json.dumps(geojson,ensure_ascii=False)+'\n')
    aliases={'Moscow':'Москва','Saint Petersburg':'Санкт-Петербург','Saratov':'Саратов','Engels':'Энгельс','Volgograd':'Волгоград','Chelyabinsk':'Челябинск','Magnitogorsk':'Магнитогорск','Sevastopol':'Севастополь'}
    normalized_names=reference.name.astype(str).str.replace(r'[-‐–]',' ',regex=True).str.casefold().str.strip()
    case_rows=[]
    for name,ru in aliases.items():
        f=raw[raw.eFUA_name.eq(name)]
        p=reference[normalized_names.eq(ru.replace('-',' ').casefold())&reference.lat.notna()&reference.lon.notna()].sort_values('population_2021',ascending=False)
        for r in f.itertuples():
            row={'name':name,'name_ru':ru,'eFUA_ID':int(r.eFUA_ID),'area_km2':float(r.FUA_area),
                'source_population_2015':float(r.FUA_p_2015),'urban_centre_count':int(r.UC_num),
                'census2021_ordinary_point_count':int(r.ordinary_census2021_point_count)}
            if len(p):
                centre=p.iloc[0];row.update(anchor_source_record_id=centre.source_record_id,anchor_role=centre.population_role,
                    anchor_lon=float(centre.lon),anchor_lat=float(centre.lat),anchor_is_measurement_reference_not_attraction_weight=True)
                coords=shapely.get_coordinates(transform(to_wgs,geometries[f.index[0]]))
                lo,la=np.deg2rad(coords[:,0]),np.deg2rad(coords[:,1]);clo,cla=np.deg2rad([centre.lon,centre.lat])
                a=np.sin((la-cla)/2)**2+np.cos(la)*np.cos(cla)*np.sin((lo-clo)/2)**2
                row['max_geodesic_distance_to_boundary_vertex_km']=float((6371.0088*2*np.arcsin(np.sqrt(np.clip(a,0,1)))).max())
            case_rows.append(row)
    cases=pd.DataFrame(case_rows)
    cases.to_parquet(output/'external_fua_named_cases.parquet',index=False,compression='zstd');cases.to_csv(output/'external_fua_named_cases.csv',index=False)
    summary={'source_id':'GHS_FUA2015_R2019A','dataset_doi':'10.2905/347F0337-F2DA-4592-87B3-E25975EC2C95',
        'method_doi':'10.1016/j.jue.2020.103242','source_epoch':2015,'is_observed_russian_commuting':False,
        'russian_estimated_fua_polygons':int(raw.Cntry_ISO.eq('RUS').sum()),
        'additional_source_country_polygons_intersecting_analysis_frame':int(raw.Cntry_ISO.ne('RUS').sum()),
        'original_source_country_labels_preserved':True,
        'analysis_points_examined':len(ordinary),
        'ordinary_census2021_points_examined':int(ordinary.ordinary_spatial_2021.sum()),
        'nonadditive_context_points_examined':int((~ordinary.ordinary_spatial_2021).sum()),
        'analysis_points_inside_at_least_one_estimated_fua':int(states.external_boundary_match_count.gt(0).sum()),
        'ordinary_points_inside_at_least_one_estimated_fua':int((states.external_boundary_match_count.gt(0)&states.ordinary_spatial_2021).sum()),
        'points_with_multiple_boundary_matches':int(states.external_boundary_match_count.gt(1).sum()),
        'source_gpkg_sha256':sha(gpkg_path),'reference_sha256':sha(reference_path),
        'read_scope':'JRC2019 product report selected sections printed4-5; OECD2019 printed5-7 and12-13; journal publisher abstract and institutional bibliographic metadata',
        'not_a_hard_true_boundary_or_chosen_target':True,'not_a_national_settlement_hierarchy':True,
        'named_cases':cases.replace({np.nan:None}).to_dict('records')}
    (output/'external_fua_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def numeric_route_layer_checks(nearest_directory):
    """Inspect arithmetic and preserved unknowns; this does not validate speeds."""
    columns = ['origin_id','cost_minutes','network_minutes','connector_minutes',
        'provider_settlement_id','provider_site_id','observed_flow','assignment_established',
        'raw_nearest_has_no_time_cutoff','zero_cost_np_assumption']
    rows=[]
    for path in sorted(Path(nearest_directory).glob('*.parquet')):
        d=pd.read_parquet(path,columns=columns)
        cost=pd.to_numeric(d.cost_minutes,errors='coerce')
        finite=np.isfinite(cost)
        decomposition=finite & d.network_minutes.notna() & d.connector_minutes.notna()
        residual=(cost[decomposition]-d.loc[decomposition,'network_minutes']-
                  d.loc[decomposition,'connector_minutes']).abs()
        rows.append(dict(service=path.stem,source_sha256=sha(path),origins=len(d),
            duplicate_origins=int(d.origin_id.duplicated().sum()),finite_cost=int(finite.sum()),
            negative_cost=int(cost.lt(0).sum()),
            no_provider_but_cost=int((finite & d.provider_site_id.isna() & d.provider_settlement_id.isna()).sum()),
            max_decomposition_error_minutes=float(residual.max()) if len(residual) else None,
            observed_flow_claims=int(d.observed_flow.eq(True).sum()),
            established_attachment_claims=int(d.assignment_established.eq(True).sum()),
            without_time_cutoff=int(d.raw_nearest_has_no_time_cutoff.eq(True).sum()),
            over60min=int(cost.gt(60).sum()),over120min=int(cost.gt(120).sum()),
            zero_np_assumptions=int(d.zero_cost_np_assumption.eq(True).sum())))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('extract-external-fua');p.add_argument('--gpkg',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('check-route-arithmetic');p.add_argument('--nearest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='extract-external-fua':
        result=extract_russia_efua(args.gpkg,args.reference,args.output)
    else:
        result=numeric_route_layer_checks(args.nearest)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
