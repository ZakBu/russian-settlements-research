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
import re

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


def check_external_provider_core_edges(edges, point_fua_links):
    """An external reference groups providers; origins need not be inside it.

    This checks a declared scenario, not an observed agglomeration boundary.
    Direct finite bounded cost remains mandatory for each supplied relation.
    """
    possible=set(zip(point_fua_links.point_key.astype(str),point_fua_links.eFUA_ID.map(lambda x:f'efua:{int(x)}')))
    rows=[]
    for r in edges.itertuples():
        base=dict(unit_id=getattr(r,'child_unit_id',None),origin_id=r.origin_id)
        cost=pd.to_numeric(r.cost_minutes,errors='coerce');bound=pd.to_numeric(r.admission_limit_minutes,errors='coerce')
        if not np.isfinite(cost) or not np.isfinite(bound) or cost<0 or bound<0 or cost>bound+1e-8:
            rows.append(dict(check='provider_core_link_without_direct_bounded_cost',detail=str(cost),**base))
        target=str(r.parent_target_key)
        if target.startswith('efua:') and (str(r.provider_point_key),target) not in possible:
            rows.append(dict(check='provider_outside_claimed_external_core',detail=target,**base))
    return issues_frame(rows)


def check_relaxed_positive_assignments(child_memberships, assignments, edges, function_domains, minimum_domains=2):
    """Independently test an explicitly declared partial-positive scenario.

    A supportive function must cover every member of a whole child with a
    direct bounded relation to the same core. Unknown functions are not filled.
    Multiple clinical codes are one health domain, not independent support.
    Complete positive evidence to another core is retained as competition.
    """
    if minimum_domains<1:raise ValueError('Minimum domains must be explicit and positive')
    joined=child_memberships[['child_unit_id','origin_id']].merge(edges,on='origin_id',how='inner',validate='one_to_many')
    finite=np.isfinite(pd.to_numeric(joined.cost_minutes,errors='coerce'))
    bounded=finite&joined.cost_minutes.ge(0)&joined.cost_minutes.le(joined.admission_limit_minutes+1e-8)
    eligible=joined[bounded&joined.higher_admitted.eq(True)&joined.parent_target_key.notna()]
    sizes=child_memberships.groupby('child_unit_id').origin_id.nunique()
    positive={}
    for (child,function,target),g in eligible.groupby(['child_unit_id','service_family','parent_target_key']):
        if g.origin_id.nunique()==sizes[child]:
            if function not in function_domains:raise ValueError('Undeclared functional domain: '+str(function))
            positive.setdefault((child,target),set()).add(function_domains[function])
    by_child={}
    for (child,target),domains in positive.items():by_child.setdefault(child,{})[target]=domains
    rows=[]
    for a in assignments.itertuples():
        base=dict(unit_id=a.child_unit_id,origin_id=None)
        if a.child_unit_id not in sizes:
            rows.append(dict(check='unknown_child_assigned_to_core',detail=str(a.parent_target_key),**base));continue
        domains=positive.get((a.child_unit_id,a.parent_target_key),set())
        if len(domains)<minimum_domains:
            rows.append(dict(check='insufficient_whole_child_positive_domains',detail=json.dumps(sorted(domains)),**base))
        rivals=[target for target,d in by_child.get(a.child_unit_id,{}).items() if target!=a.parent_target_key and d]
        if rivals:
            rows.append(dict(check='competing_complete_positive_core_ignored',detail=json.dumps(sorted(rivals)),**base))
    return issues_frame(rows)


def _named_cases(reference):
    return reference[reference.name.isin(['Москва','Санкт-Петербург','Саратов','Энгельс','Новоузенск','Питерка','Челябинск','Магнитогорск'])&reference.region.fillna('').str.contains('саратов|москв|петербург|челябин',case=False)]


def _route_extrema(edges, origin_ids, selected_core_by_origin=None):
    g=edges[edges.origin_id.isin(origin_ids)]
    def maximum(values):
        values=pd.to_numeric(values,errors='coerce');values=values[np.isfinite(values)]
        return float(values.max()) if len(values) else None
    admitted=g[g.higher_admitted.eq(True)]
    guarded=g[g.territorial_merge_admitted.eq(True)]
    selected=None
    if selected_core_by_origin is not None:
        selected=guarded[guarded.parent_target_key.eq(guarded.origin_id.map(selected_core_by_origin))]
    return {'current_step_max_raw_nearest_minutes':maximum(g.cost_minutes),
        'current_step_max_admitted_direct_minutes':maximum(admitted.cost_minutes),
        'current_step_max_guard_admitted_direct_minutes':maximum(guarded.cost_minutes),
        'current_step_origin_count_with_any_admitted_function':int(admitted.origin_id.nunique()),
        'current_step_max_selected_core_direct_minutes':maximum(selected.cost_minutes) if selected is not None else None,
        'current_step_selected_core_origin_coverage':int(selected.origin_id.nunique()) if selected is not None else None,
        'time_fields_refer_to_current_function_step_not_assumed_inherited_or_observed_trip':True}


def _ellipsoidal_extent(points, anchor_lat=None, anchor_lon=None):
    """Independent WGS84 distances; no conversion of minutes into kilometres."""
    from pyproj import Geod
    geod=Geod(ellps='WGS84')
    q=points[['lat','lon']].dropna().drop_duplicates()
    if q.empty:return {'wgs84_member_diameter_km':None,'anchor_max_distance_km':None}
    lat=q.lat.to_numpy(dtype=float);lon=q.lon.to_numpy(dtype=float);maximum=0.
    for i in range(len(q)):
        _,_,distance=geod.inv(np.full(len(q)-i,lon[i]),np.full(len(q)-i,lat[i]),lon[i:],lat[i:])
        maximum=max(maximum,float(np.max(distance)))
    radius=None
    if anchor_lat is not None and anchor_lon is not None:
        _,_,distance=geod.inv(np.full(len(q),anchor_lon),np.full(len(q),anchor_lat),lon,lat)
        radius=float(np.max(distance))/1000.
    return {'wgs84_member_diameter_km':maximum/1000.,'anchor_max_distance_km':radius}


def check_upper_need_scope_labels(edges):
    """A shared rare-care offer never establishes patient suitability or flows."""
    required=['service_family','upper_medical_link_need_conditional',
              'universal_patient_suitability_established','rare_service_is_agglomeration_proof']
    if not set(required).issubset(edges.columns):
        return {'upper_need_scope_labels_missing':len(edges)}
    medical=edges.service_family.astype(str).str.startswith('medical_')
    return {'medical_link_not_labelled_need_conditional':int((medical&~edges.upper_medical_link_need_conditional.eq(True)).sum()),
            'unsupported_universal_patient_suitability_claim':int(edges.universal_patient_suitability_established.eq(True).sum()),
            'unsupported_rare_service_agglomeration_proof_claim':int(edges.rare_service_is_agglomeration_proof.eq(True).sum())}


def audit_extended_results(directory, strict_directory, reference_path, origin_links_path, minimum_domains=2):
    """Validate actual provider-core scenarios and measure named/outlier extents."""
    directory=Path(directory);strict_directory=Path(strict_directory)
    reference=pd.read_parquet(reference_path)
    reference=reference[reference.analysis_origin.eq(True)].copy()
    pl=pd.read_parquet(strict_directory/'reference_lookup/provider_external_fua_links.parquet')
    status=pd.read_parquet(strict_directory/'reference_lookup/provider_external_fua_status.parquet')
    points=pd.read_parquet(strict_directory/'reference_lookup/provider_points.parquet').set_index('point_key')
    ambiguous_providers=set(pl.loc[pl.point_key.duplicated(keep=False),'point_key'])
    unique_links=pl[~pl.point_key.duplicated(keep=False)]
    actualcore=unique_links.set_index('point_key').eFUA_ID.map(lambda x:f'efua:{int(x)}')
    ol=pd.read_parquet(origin_links_path)
    origin_core_pairs=set(zip(ol.source_record_id.astype(str),ol.eFUA_ID.map(lambda x:f'efua:{int(x)}')))
    cases=_named_cases(reference)
    domains={'medical_inpatient':'health','medical_specialized':'health','medical_hightech_licensed':'health',
             'vocational_education':'education','higher_education':'education','shopping_centre':'commerce'}
    reports=[]
    for mode in ['all_declared','partial_positive_two_domains']:
        previous_m=pd.read_parquet(strict_directory/'01_physician_direct_30/memberships.parquet')
        previous_u=pd.read_parquet(strict_directory/'01_physician_direct_30/units.parquet')
        for stage in sorted((directory/mode).glob('[0-9][0-9]_*')):
            if not (stage/'summary.json').exists():continue
            m=pd.read_parquet(stage/'memberships.parquet');u=pd.read_parquet(stage/'units.parquet')
            cw=pd.read_parquet(stage/'subsystem_crosswalk.parquet')
            edge_columns=['origin_id','service_family','provider_point_key','provider_settlement_id','provider_site_id','provider_lat','provider_lon','parent_target_key','cost_minutes','admission_limit_minutes','higher_admitted','territorial_merge_admitted','upper_medical_link_need_conditional','universal_patient_suitability_established','rare_service_is_agglomeration_proof']
            e=pd.read_parquet(stage/'higher_edge_evidence.parquet',columns=edge_columns)
            dec=pd.read_parquet(stage/'parent_decisions.parquet')
            assignments=dec[dec.parent_target_key.notna()][['child_unit_id','parent_target_key']]
            child_members=previous_m[['origin_id','unit_id']].rename(columns={'unit_id':'child_unit_id'})
            positive_issues=check_relaxed_positive_assignments(child_members,assignments,e,domains,minimum_domains)
            accepted=e[e.territorial_merge_admitted.eq(True)]
            admitted=e[e.higher_admitted.eq(True)]
            choice_by_origin=child_members.merge(assignments,on='child_unit_id',validate='many_to_one').set_index('origin_id').parent_target_key
            external_choices=choice_by_origin[choice_by_origin.astype('string').str.startswith('efua:',na=False)]
            outside_origins=sum((str(origin),str(core)) not in origin_core_pairs for origin,core in external_choices.items())
            geometry_issues=check_external_provider_core_edges(accepted,pl)
            failures={'positive_assignment_issues':len(positive_issues),'direct_or_provider_core_issues':len(geometry_issues),
                'duplicate_origin_memberships':int(m.origin_id.duplicated().sum()),
                'origin_set_changed':len(set(previous_m.origin_id)^set(m.origin_id)),
                'missing_or_duplicate_child_crosswalk':len(set(previous_u.unit_id)^set(cw.child_unit_id))+int(cw.child_unit_id.duplicated().sum()),
                'provider_points_missing_from_lookup':int(e.provider_point_key.notna().mul(~e.provider_point_key.isin(status.point_key)).sum())}
            failures.update(check_upper_need_scope_labels(e))
            desired=child_members.merge(cw[['child_unit_id','unit_id']],on='child_unit_id',validate='many_to_one')
            compare=desired[['origin_id','unit_id']].merge(m[['origin_id','unit_id']],on='origin_id',suffixes=('_expected','_actual'),how='outer',validate='one_to_one')
            failures['parent_not_exact_whole_child_union']=int(compare.unit_id_expected.ne(compare.unit_id_actual).sum())
            childcount=cw.groupby('unit_id').child_unit_id.nunique();indexed=u.set_index('unit_id')
            failures['new_merger_flag_mismatch']=int(indexed.new_territorial_merger.ne(childcount.gt(1)).sum())
            expecteddepth=cw.groupby('unit_id').child_effective_merge_depth.max()+childcount.gt(1).astype(int)
            failures['effective_merge_depth_mismatch']=int(indexed.effective_merge_depth.ne(expecteddepth).sum())
            inherited=previous_u.set_index('unit_id').get('boundary_depends_on_external_reference',pd.Series(False,index=previous_u.unit_id))
            inherited=(cw.child_unit_id.map(inherited).fillna(False)|cw.external_reference_in_parent.eq(True)).groupby(cw.unit_id).any()
            failures['external_reference_provenance_lost']=int((inherited&~indexed.boundary_depends_on_external_reference).sum())
            failures['higher_admitted_invalid_or_over_bound']=int((~np.isfinite(admitted.cost_minutes)|admitted.cost_minutes.lt(0)|admitted.cost_minutes.gt(admitted.admission_limit_minutes+1e-8)).sum())
            unique_core=e.provider_point_key.map(actualcore)
            failures['provider_reference_core_not_preserved']=int((unique_core.notna()&e.parent_target_key.ne(unique_core)).sum())
            failures['ambiguous_provider_core_admitted']=int((e.provider_point_key.isin(ambiguous_providers)&e.territorial_merge_admitted.eq(True)).sum())
            fallback=('site:'+e.provider_point_key.astype(str)).where(e.provider_settlement_id.isna(),'np:'+e.provider_settlement_id.astype(str))
            failures['nonreference_core_differs_from_known_provider_identity']=int((unique_core.isna()&e.territorial_merge_admitted.eq(True)&e.parent_target_key.ne(fallback)).sum())
            known_points=e.provider_point_key.isin(points.index)
            failures['provider_coords_differ_from_lookup']=int((known_points&(~np.isclose(e.provider_lat,e.provider_point_key.map(points.lat),atol=1e-9,rtol=0)|~np.isclose(e.provider_lon,e.provider_point_key.map(points.lon),atol=1e-9,rtol=0))).sum())
            if mode=='all_declared':
                selected=child_members.merge(assignments,on='child_unit_id',validate='many_to_one').merge(e,on='origin_id',suffixes=('_chosen',''),validate='one_to_many')
                selected=selected[selected.higher_admitted.eq(True)&selected.parent_target_key.eq(selected.parent_target_key_chosen)]
                n=selected.groupby(['child_unit_id','service_family']).origin_id.nunique().reset_index(name='covered')
                sizes=child_members.groupby('child_unit_id').origin_id.nunique()
                n=n[n.covered.eq(n.child_unit_id.map(sizes))]
                complete=n.groupby('child_unit_id').service_family.nunique()
                failures['all_declared_missing_complete_channels']=int(assignments.child_unit_id.map(complete).fillna(0).ne(e.service_family.nunique()).sum())
            case_unit_ids=set(m.loc[m.origin_id.isin(cases.source_record_id),'unit_id'])
            wanted_units=case_unit_ids|set(u.nlargest(10,'member_geodesic_diameter_km').unit_id)
            geo=m[m.unit_id.isin(wanted_units)].merge(reference[['source_record_id','lat','lon','population_2021']],left_on='origin_id',right_on='source_record_id',validate='many_to_one')
            grouped={key:frame for key,frame in geo.groupby('unit_id',sort=False)}
            named=[]
            for r in cases.itertuples():
                unit=m.loc[m.origin_id.eq(r.source_record_id),'unit_id'].iloc[0];g=grouped[unit]
                metadata=indexed.loc[unit]
                extent=_ellipsoidal_extent(g,float(r.lat),float(r.lon))
                inhabited=_ellipsoidal_extent(g[g.population_2021.gt(0)],float(r.lat),float(r.lon))
                named.append(dict(name=r.name,source_record_id=r.source_record_id,unit_id=unit,member_records=len(g),
                    source_population_2021=float(r.population_2021),source_population_role=str(r.population_role),
                    source_population_is_nonadditive_context=not bool(r.ordinary_spatial_2021),source_population_is_not_total_unit_population=True,
                    ordinary_member_population_2021_credited_sum=float(metadata.member_population_2021_credited_sum),effective_merge_depth=int(metadata.effective_merge_depth),
                    anchor_is_reference_point_not_physical_catchment_boundary=True,**extent,
                    positive_population_point_diameter_km=inhabited['wgs84_member_diameter_km'],
                    positive_population_anchor_max_distance_km=inhabited['anchor_max_distance_km'],**_route_extrema(e,g.origin_id,choice_by_origin)))
            outliers=[]
            for r in u.nlargest(10,'member_geodesic_diameter_km').itertuples():
                g=grouped[r.unit_id];ext=_ellipsoidal_extent(g);inh=_ellipsoidal_extent(g[g.population_2021.gt(0)])
                outliers.append(dict(unit_id=r.unit_id,member_records=len(g),declared_spherical_diameter_km=float(r.member_geodesic_diameter_km),
                    **ext,positive_population_point_diameter_km=inh['wgs84_member_diameter_km'],
                    minimum_latitude=float(g.lat.min()),maximum_latitude=float(g.lat.max()),minimum_longitude=float(g.lon.min()),maximum_longitude=float(g.lon.max()),**_route_extrema(e,g.origin_id,choice_by_origin)))
            reports.append({'mode':mode,'stage':stage.name,'units':len(u),'origins':len(m),'selected_children':len(assignments),
                'new_merger_groups':int(u.new_territorial_merger.sum()),'selected_external_core_origins':len(external_choices),'selected_external_core_origins_outside_2015_polygon':outside_origins,'maximum_effective_merge_depth':int(u.effective_merge_depth.max()),
                'failures':failures,'issue_examples':pd.concat([positive_issues,geometry_issues]).head(20).to_dict('records'),
                'named_cases':named,'largest_diameter_units':outliers,
                'origin_reference_links_sha256':sha(origin_links_path),'input_sha256':{f:sha(stage/(f+'.parquet')) for f in ['memberships','units','subsystem_crosswalk','higher_edge_evidence','parent_decisions']}})
            previous_m,previous_u=m,u
    return reports


def compare_medical_route_versions(before_directory, after_directory, reference_path):
    """Count changes in recorded accessibility, not changes in actual facilities."""
    reference=pd.read_parquet(reference_path)
    in_saratov=set(reference.loc[reference.region.fillna('').str.contains('саратов',case=False),'source_record_id'])
    rows=[]
    for family,bound in [('medical_basic_primary',30.),('medical_physician_primary',30.),('medical_inpatient',90.),('medical_specialized',90.),('medical_hightech_licensed',120.)]:
        a_path=Path(before_directory)/(family+'.parquet');b_path=Path(after_directory)/(family+'.parquet')
        cols=['origin_id','cost_minutes','provider_site_id','source_year','location_precision']
        a=pd.read_parquet(a_path,columns=cols);b=pd.read_parquet(b_path,columns=cols)
        d=a.merge(b,on='origin_id',how='outer',suffixes=('_before','_after'),validate='one_to_one',indicator=True)
        old=pd.to_numeric(d.cost_minutes_before,errors='coerce');new=pd.to_numeric(d.cost_minutes_after,errors='coerce')
        both=np.isfinite(old)&np.isfinite(new);improved=both&new.lt(old-1e-8);worsened=both&new.gt(old+1e-8)
        old_inside=np.isfinite(old)&old.ge(0)&old.le(bound);new_inside=np.isfinite(new)&new.ge(0)&new.le(bound)
        rows.append({'service_family':family,'comparison_bound_minutes':bound,'origin_records':len(d),
            'origin_set_mismatch':int(d['_merge'].ne('both').sum()),'decreased_model_minutes':int(improved.sum()),
            'decreased_model_minutes_in_saratov':int((improved&d.origin_id.isin(in_saratov)).sum()),
            'decreased_model_minutes_outside_saratov':int((improved&~d.origin_id.isin(in_saratov)).sum()),
            'increased_model_minutes':int(worsened.sum()),'newly_finite_model_cost':int((~np.isfinite(old)&np.isfinite(new)).sum()),
            'within_bound_before':int(old_inside.sum()),'within_bound_after':int(new_inside.sum()),
            'entered_bound':int((new_inside&~old_inside).sum()),'left_bound':int((old_inside&~new_inside).sum()),
            'different_provider_site_id':int(d.provider_site_id_before.fillna('__NONE__').ne(d.provider_site_id_after.fillna('__NONE__')).sum()),
            'provider_representative_settlement_points_before':int(d.location_precision_before.eq('settlement_point').sum()),
            'provider_representative_settlement_points_after':int(d.location_precision_after.eq('settlement_point').sum()),
            'before_sha256':sha(a_path),'after_sha256':sha(b_path),
            'new_source_year_values':sorted(str(x) for x in d.source_year_after.dropna().unique()),
            'not_an_observed_change_in_facilities_or_trips':True})
    return rows


def audit_historical_primary_scope(directory):
    """Reconcile accepted universal primary evidence with literal age/scope."""
    directory=Path(directory)
    raw=pd.read_parquet(directory/'source_rows.parquet')
    evidence=pd.read_parquet(directory/'service_evidence.parquet')
    selected=evidence[evidence.service_code.isin(['medical_basic_primary','medical_physician_primary'])]
    rawcols=['object_id','care_type_literal','care_conditions_literal','care_profile_literal',
        'pediatric_only_signal','explicit_restricted_scope','other_registry_exclusion',
        'address_inheritance_parent_oid_conflict','narrow_unit_name_ambiguity_signal']
    checked=selected.merge(raw[rawcols],on='object_id',validate='many_to_one')
    child=checked.subdivision_name.str.contains(r'детск|педиатр',case=False,na=False)
    explicitly_mixed=checked.subdivision_name.str.contains(r'взросл',case=False,na=False)
    suspicious=checked[child&~explicitly_mixed]
    physician=checked[checked.service_code.eq('medical_physician_primary')]
    general=physician.care_profile_literal.fillna('').str.contains(r'\bтерапии\b|общей врачебной практике',case=False,regex=True)
    findings={
        'accepted_primary_rows':len(checked),'accepted_physician_rows':len(physician),
        'accepted_explicit_child_named_primary_rows':len(suspicious),
        'accepted_explicit_child_named_primary_objects':int(suspicious.object_id.nunique()),
        'physician_without_adult_general_profile':int((~general).sum()),
        'physician_without_explicit_physician_care':int((~physician.care_type_literal.fillna('').str.contains('первичная врачебная',case=False)).sum()),
        'physician_without_ambulatory_care':int((~physician.care_conditions_literal.fillna('').str.contains('амбулаторно',case=False)).sum()),
        'current_operation_claims':int(raw.current_operation_verified.eq(True).sum()),
        'observed_flow_claims':int(evidence.observed_flow.eq(True).sum())}
    for col in rawcols[4:]:findings['accepted_'+col]=int(checked[col].eq(True).sum())
    return {'input_directory':str(directory),'input_sha256':{f:sha(directory/(f+'.parquet')) for f in ['source_rows','service_evidence']},
        'source_year_values':sorted(str(x) for x in raw.source_year.dropna().unique()),
        'counts':findings,'child_scope_examples':suspicious[['object_id','subdivision_name','activity_address','source_record_id','service_code','care_profile_literal']].to_dict('records'),
        'interpretation':'Explicit child-only unit names are suspicious for a universal adult-access primary channel even when an aggregated license lists general practice. No claim of current operation follows from historical programme membership.'}


def audit_medical_primary_scope(legacy_evidence, federal_care, np_supply, physical_sites):
    """Reconcile actual accepted primary rows with literal care codes and scope.

    Literal-name review remains a separate source interpretation: agreement of
    generated flags is internal consistency, not proof of inventory completeness.
    """
    primary=['medical_basic_primary','medical_physician_primary']
    legacy=pd.read_parquet(legacy_evidence)
    accepted_legacy=legacy[legacy.service_code.isin(primary)&legacy.current_source_eligible.eq(True)]
    care=pd.read_parquet(federal_care)
    basic=care.service_codes.fillna('').str.split('|').map(lambda codes:primary[0] in codes)
    physician=care.service_codes.fillna('').str.split('|').map(lambda codes:primary[1] in codes)
    accepted=care[basic|physician]
    failures={
        'accepted_legacy_unit_scope_explicitly_held':int(accepted_legacy.new_unit_primary_scope_held.eq(True).sum()),
        'accepted_legacy_named_child_only':int(accepted_legacy.named_child_only_contingent.eq(True).sum()),
        'accepted_legacy_explicit_restricted_scope':int(accepted_legacy.explicit_restricted_scope.eq(True).sum())}
    for col in ['named_child_only_contingent','pediatric_only_signal','restricted_access_signal',
                'narrow_unit_name_ambiguity_signal','organization_oms_participation_ended_asof','telemedicine_only']:
        failures['accepted_federal_'+col]=int(accepted[col].eq(True).sum())
    failures['accepted_federal_without_positive_general_primary_unit_literal']=int((~accepted.positive_general_primary_unit_literal.eq(True)).sum())
    # These predicates use original NSI codes, independently of service labels.
    p=care.loc[physician]
    failures['physician_without_original_12_3_adult_general_profile']=int((~p.MPVID.astype(str).eq('12')|~p.MPUSL.astype(str).eq('3')|~p.MPROF.astype(str).isin(['57','58','97'])).sum())
    failures['basic_without_original_ambulatory_condition']=int((~care.loc[basic,'MPUSL'].astype(str).eq('3')).sum())
    npdata=pd.read_parquet(np_supply);physical=pd.read_parquet(physical_sites)
    n=npdata[npdata.service_code.isin(primary)]
    failures['duplicate_final_np_primary_keys']=int(n.duplicated(['source_record_id','service_code']).sum())
    failures['final_np_primary_named_child_only']=int(n.named_child_only_contingent.eq(True).sum()) if 'named_child_only_contingent' in n else 0
    active_physical=physical[physical.service_code.isin(primary)&physical.supply_status.isin(['proxy','observed'])]
    if 'named_child_only_contingent' in active_physical:
        failures['accepted_physical_named_child_only']=int(active_physical.named_child_only_contingent.eq(True).sum())
    paths={'legacy_evidence':legacy_evidence,'federal_care':federal_care,'np_supply':np_supply,'physical_sites':physical_sites}
    return {'input_sha256':{k:sha(p) for k,p in paths.items()},'failures':failures,
        'legacy_raw_service_evidence_rows':len(legacy),'accepted_legacy_primary_evidence_rows':len(accepted_legacy),
        'federal_raw_care_rows_retained':len(care),'accepted_federal_primary_care_rows':len(accepted),
        'accepted_federal_basic_care_rows':int(basic.sum()),'accepted_federal_physician_care_rows':int(physician.sum()),
        'final_np_primary_keys':len(n),'final_np_primary_unique_np':int(n.source_record_id.nunique()),
        'accepted_physical_primary_rows':len(active_physical),
        'interpretation':'Codes and exclusion flags are reconciled from actual selected inputs. These are source confirmations, not patient flows, staffing, capacity or complete current medical inventories. Age- and need-specific rare care is retained separately; universal hospital suitability is not inferred.'}


def audit_upward(directory, level_zero, origin_links_path, reference_path=None):
    """Check complete-child nesting, source-area guards and inherited depth."""
    directory=Path(directory);level_zero=Path(level_zero)
    previous_m=pd.read_parquet(level_zero/'level0_memberships.parquet')
    previous_u=pd.read_parquet(level_zero/'level0_units.parquet')
    reference=pd.read_parquet(reference_path) if reference_path is not None else None
    if reference is not None:reference=reference[reference.analysis_origin.eq(True)]
    ol=pd.read_parquet(origin_links_path)
    pl=pd.read_parquet(directory/'reference_lookup/provider_external_fua_links.parquet')
    points=pd.read_parquet(directory/'reference_lookup/provider_points.parquet').set_index('point_key')
    if ol.source_record_id.duplicated().any() or pl.point_key.duplicated().any():
        raise ValueError('Ambiguous reference matches need explicit treatment, not a first-match collapse')
    om=ol.set_index('source_record_id').eFUA_ID.map(lambda x:f'efua:{int(x)}')
    pm=pl.set_index('point_key').eFUA_ID.map(lambda x:f'efua:{int(x)}')
    output=[]
    for stage in sorted(directory.glob('[0-9][0-9]_*')):
        if not (stage/'summary.json').exists():continue
        m=pd.read_parquet(stage/'memberships.parquet');u=pd.read_parquet(stage/'units.parquet')
        cw=pd.read_parquet(stage/'subsystem_crosswalk.parquet')
        import pyarrow.parquet as pq
        edge_path=stage/'higher_edge_evidence.parquet'
        available=set(pq.read_schema(edge_path).names)
        needed=['origin_id','service_family','provider_site_id','provider_lat','provider_lon','cost_minutes','admission_limit_minutes','higher_admitted','territorial_merge_admitted','parent_target_key','external_reference_is_observed_commuting','upper_medical_link_need_conditional','universal_patient_suitability_established','rare_service_is_agglomeration_proof']
        e=pd.read_parquet(edge_path,columns=[c for c in needed if c in available])
        failures={}
        failures.update(check_upper_need_scope_labels(e))
        failures['duplicate_origin_memberships']=int(m.origin_id.duplicated().sum())
        failures['origin_set_changed']=len(set(m.origin_id)^set(previous_m.origin_id))
        failures['child_missing_or_duplicated_crosswalk']=len(set(previous_u.unit_id)^set(cw.child_unit_id))+int(cw.child_unit_id.duplicated().sum())
        expected=previous_m[['origin_id','unit_id']].rename(columns={'unit_id':'child_unit_id'}).merge(cw[['child_unit_id','unit_id']],on='child_unit_id',validate='many_to_one')
        compare=expected[['origin_id','unit_id']].merge(m[['origin_id','unit_id']],on='origin_id',suffixes=('_expected','_actual'),how='outer',validate='one_to_one')
        failures['parent_not_exact_whole_child_union']=int(compare.unit_id_expected.ne(compare.unit_id_actual).sum())
        childcount=cw.groupby('unit_id').child_unit_id.nunique()
        declared=u.set_index('unit_id')
        failures['new_merger_flag_mismatch']=int(declared.new_territorial_merger.ne(childcount.gt(1)).sum())
        expecteddepth=cw.groupby('unit_id').child_effective_merge_depth.max()+childcount.gt(1).astype(int)
        failures['effective_merge_depth_mismatch']=int(declared.effective_merge_depth.ne(expecteddepth).sum())
        previous_flags=previous_u.set_index('unit_id').get('boundary_depends_on_external_reference',pd.Series(False,index=previous_u.unit_id))
        inherited=cw.child_unit_id.map(previous_flags).fillna(False)|cw.external_reference_in_parent.eq(True)
        expectedflag=inherited.groupby(cw.unit_id).any()
        failures['external_reference_provenance_lost']=int((expectedflag&~declared.boundary_depends_on_external_reference).sum())
        admitted=e[e.higher_admitted.eq(True)]
        failures['higher_admitted_invalid_or_over_bound']=int((~np.isfinite(admitted.cost_minutes)|admitted.cost_minutes.lt(0)|admitted.cost_minutes.gt(admitted.admission_limit_minutes+1e-8)).sum())
        guard=e[e.territorial_merge_admitted.eq(True)]
        external=guard[guard.get('parent_target_key',pd.Series(pd.NA,index=guard.index,dtype='string')).astype('string').str.startswith('efua:',na=False)]
        actualorigin=external.origin_id.map(om);actualprovider=external.provider_site_id.map(pm)
        target=external.get('parent_target_key',pd.Series(pd.NA,index=external.index,dtype='string'))
        failures['external_guard_origin_outside_source_polygon']=int(actualorigin.ne(target).sum())
        failures['external_guard_provider_outside_source_polygon']=int(actualprovider.ne(target).sum())
        cached_lat=external.provider_site_id.map(points.lat);cached_lon=external.provider_site_id.map(points.lon)
        failures['external_provider_coords_differ_from_lookup']=int((~np.isclose(cached_lat,external.provider_lat,atol=1e-9,rtol=0)|~np.isclose(cached_lon,external.provider_lon,atol=1e-9,rtol=0)).sum())
        failures['external_estimate_claimed_observed_flow']=int(e.get('external_reference_is_observed_commuting',pd.Series(False,index=e.index)).eq(True).sum())
        named=[]
        if reference is not None:
            cases=_named_cases(reference);indexed=u.set_index('unit_id')
            wanted=set(m.loc[m.origin_id.isin(cases.source_record_id),'unit_id'])
            geo=m[m.unit_id.isin(wanted)].merge(reference[['source_record_id','lat','lon','population_2021']],left_on='origin_id',right_on='source_record_id',validate='many_to_one')
            groups={key:frame for key,frame in geo.groupby('unit_id',sort=False)}
            for r in cases.itertuples():
                unit=m.loc[m.origin_id.eq(r.source_record_id),'unit_id'].iloc[0];g=groups[unit];metadata=indexed.loc[unit]
                named.append(dict(name=r.name,source_record_id=r.source_record_id,unit_id=unit,member_records=len(g),
                    source_population_2021=float(r.population_2021),source_population_role=str(r.population_role),
                    source_population_is_nonadditive_context=not bool(r.ordinary_spatial_2021),source_population_is_not_total_unit_population=True,
                    ordinary_member_population_2021_credited_sum=float(metadata.member_population_2021_credited_sum),
                    effective_merge_depth=int(metadata.effective_merge_depth),**_ellipsoidal_extent(g,float(r.lat),float(r.lon)),**_route_extrema(e,g.origin_id)))
        output.append({'stage':stage.name,'origins':len(m),'units':len(u),'named_cases':named,'new_mergers':int(u.new_territorial_merger.sum()),
            'max_effective_merge_depth':int(u.effective_merge_depth.max()),'external_guarded_edges':len(external),
            'failures':failures,'input_sha256':{f:sha(stage/(f+'.parquet')) for f in ['memberships','units','subsystem_crosswalk','higher_edge_evidence']}})
        previous_m,previous_u=m,u
    return output


def audit_level_zero(directory, reference_path):
    """Recalculate invariants from actual full-country rows, independently of summaries."""
    directory=Path(directory)
    m=pd.read_parquet(directory/'level0_memberships.parquet')
    u=pd.read_parquet(directory/'level0_units.parquet')
    edge_columns=['origin_id','origin_name','service_family','l0_admitted','provider_key','cost_minutes','admission_limit_minutes','origin_is_additional_context','origin_budget_population_credit','observed_flow','assignment_established','origin_independence_established','population_or_object_count_used_as_attraction_weight','limit_is_fitted_to_observed_trips','limit_is_current_legal_compliance_test','service_status','source_year','admission_source_id','provider_settlement_id','provider_site_id','provider_name','point_separation_km','source_id','location_precision']
    e=pd.read_parquet(directory/'daily_edge_evidence.parquet',columns=edge_columns)
    ref=pd.read_parquet(reference_path)
    expected=ref[ref.analysis_origin.eq(True)]
    failures={}
    failures['duplicate_origin_memberships']=int(m.origin_id.duplicated().sum())
    failures['missing_reference_origins']=len(set(expected.source_record_id)-set(m.origin_id))
    failures['extra_reference_origins']=len(set(m.origin_id)-set(expected.source_record_id))
    failures['duplicate_origin_function_rows']=int(e.duplicated(['origin_id','service_family']).sum())
    families=sorted(e.service_family.unique())
    counts=e.groupby('origin_id').service_family.nunique()
    failures['incomplete_origin_function_vectors']=int(counts.ne(len(families)).sum())
    admitted=e[e.l0_admitted.eq(True)]
    failures['admitted_missing_provider_key']=int(admitted.provider_key.isna().sum())
    cost=pd.to_numeric(admitted.cost_minutes,errors='coerce')
    bound=pd.to_numeric(admitted.admission_limit_minutes,errors='coerce')
    failures['admitted_invalid_or_over_bound']=int((~np.isfinite(cost)|~np.isfinite(bound)|cost.lt(0)|cost.gt(bound+1e-8)).sum())
    signature=e[['origin_id','service_family']].copy()
    signature['independent_provider']=e.provider_key.where(e.l0_admitted).fillna('__UNKNOWN__')
    signature=signature.merge(m[['origin_id','unit_id']],on='origin_id',validate='many_to_one')
    diversity=signature.groupby(['unit_id','service_family']).independent_provider.nunique()
    failures['unit_function_mixes_different_providers']=int(diversity.gt(1).sum())
    actual_vectors=signature.groupby(['unit_id','service_family']).independent_provider.first().unstack().reindex(columns=families)
    signature_mismatches=0
    for unit in u.itertuples():
        declared=dict(json.loads(unit.profile_signature).get('providers',[]))
        actual=actual_vectors.loc[unit.unit_id]
        signature_mismatches+=any(declared.get(f)!= (None if actual[f]=='__UNKNOWN__' else actual[f]) for f in families)
    failures['stored_profile_disagrees_with_raw_edges']=signature_mismatches
    known=signature.independent_provider.ne('__UNKNOWN__').groupby(signature.origin_id).sum()
    allunknown=set(known[known.eq(0)].index)
    membercount=m.groupby('unit_id').origin_id.size()
    unknown_members=m[m.origin_id.isin(allunknown)]
    failures['all_unknown_origin_assigned_to_nonsingleton']=int(unknown_members.unit_id.map(membercount).gt(1).sum())
    uindex=u.set_index('unit_id')
    failures['unit_record_count_mismatch']=int(membercount.ne(uindex.member_records).sum())
    merged=e.merge(expected[['source_record_id','ordinary_spatial_2021','budget_population_credit']],left_on='origin_id',right_on='source_record_id',validate='many_to_one')
    failures['context_receives_population_credit']=int((merged.origin_is_additional_context.eq(True)&merged.origin_budget_population_credit.eq(True)).sum())
    failures['budget_flag_differs_from_reference']=int(merged.origin_budget_population_credit.ne(merged.budget_population_credit).sum())
    for col in ['observed_flow','assignment_established','origin_independence_established','population_or_object_count_used_as_attraction_weight','limit_is_fitted_to_observed_trips','limit_is_current_legal_compliance_test']:
        failures[col+'_unsupported_claims']=int(e[col].eq(True).sum())
    ordinary=expected.ordinary_spatial_2021.eq(True)&expected.credit_2021.eq(True)
    expectedpop=expected.loc[ordinary,'population_2021'].sum()
    actualpop=u.member_population_2021_credited_sum.sum()
    failures['population_sum_absolute_difference']=float(abs(expectedpop-actualpop))
    cases=_named_cases(expected)
    casecols=['origin_id','origin_name','service_family','provider_settlement_id','provider_site_id','provider_name','cost_minutes','point_separation_km','l0_admitted','service_status','admission_limit_minutes','source_id','source_year','location_precision']
    cases=cases[['source_record_id','name','population_2021','lat','lon']].merge(m,left_on='source_record_id',right_on='origin_id').merge(u[['unit_id','member_records','positive_credited_member_records','member_geodesic_diameter_km','type_code']],on='unit_id')
    measured=[]
    for case in cases.itertuples():
        ids=m.loc[m.unit_id.eq(case.unit_id),'origin_id']
        points=expected[expected.source_record_id.isin(ids)]
        measured.append(_ellipsoidal_extent(points,float(case.lat),float(case.lon)))
    cases=pd.concat([cases.reset_index(drop=True),pd.DataFrame(measured)],axis=1)
    result={'dataset_directory':str(directory),'reference_sha256':sha(reference_path),
        'input_sha256':{f:sha(directory/(f+'.parquet')) for f in ['level0_units','level0_memberships','daily_edge_evidence']},
        'origin_records':len(m),'unit_records':len(u),'daily_families':families,'all_unknown_singleton_origins':len(allunknown),
        'ordinary_budget_population_sum':float(expectedpop),'unit_member_population_sum':float(actualpop),
        'failures':failures,'service_states':e.groupby(['service_family','service_status']).size().rename('records').reset_index().to_dict('records'),
        'source_year_values':sorted(str(x) for x in e.source_year.dropna().unique()),
        'admission_source_values':sorted(str(x) for x in e.admission_source_id.dropna().unique()),
        'case_units':cases.to_dict('records'),'case_function_links':e.loc[e.origin_id.isin(cases.origin_id),casecols].to_dict('records')}
    # JSON round-trip normalizes pandas missing values while retaining literal unknowns.
    return json.loads(pd.Series(result).to_json(force_ascii=False))


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
    p=sub.add_parser('check-level-zero');p.add_argument('--directory',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('check-upward');p.add_argument('--directory',type=Path,required=True);p.add_argument('--level-zero',type=Path,required=True);p.add_argument('--origin-links',type=Path,required=True);p.add_argument('--reference',type=Path);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('check-historical-primary-scope');p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('check-medical-primary-scope')
    for flag in ['legacy-evidence','federal-care','np-supply','physical-sites','output']:p.add_argument('--'+flag,type=Path,required=True)
    p=sub.add_parser('check-extended');p.add_argument('--directory',type=Path,required=True);p.add_argument('--strict-directory',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--origin-links',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('compare-medical-routes');p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='extract-external-fua':
        result=extract_russia_efua(args.gpkg,args.reference,args.output)
    elif args.command=='check-extended':
        result=audit_extended_results(args.directory,args.strict_directory,args.reference,args.origin_links)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    elif args.command=='compare-medical-routes':
        result=compare_medical_route_versions(args.before,args.after,args.reference)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    elif args.command=='check-historical-primary-scope':
        result=audit_historical_primary_scope(args.directory)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    elif args.command=='check-medical-primary-scope':
        result=audit_medical_primary_scope(args.legacy_evidence,args.federal_care,args.np_supply,args.physical_sites)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    elif args.command=='check-upward':
        result=audit_upward(args.directory,args.level_zero,args.origin_links,args.reference)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    elif args.command=='check-level-zero':
        result=audit_level_zero(args.directory,args.reference)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    else:
        result=numeric_route_layer_checks(args.nearest)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
