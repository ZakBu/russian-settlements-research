#!/usr/bin/env python3
"""National compatibility of complete L0 footprints with external eFUA2015.

External envelopes are inputs, not independent validation or inferred SGRT
levels. Exact current coordinates, boundary coverage and all overlaps survive.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer
import shapely
from shapely import STRtree


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def point_envelopes(reference, polygons):
    if not reference.source_record_id.is_unique or not polygons.eFUA_ID.is_unique:
        raise ValueError('Reference and external envelope identities must be unique')
    valid=(reference.lat.between(-90,90) & reference.lon.between(-180,180)
           & np.isfinite(reference.lat) & np.isfinite(reference.lon))
    points=reference.loc[valid,['source_record_id','lat','lon']].reset_index(drop=True)
    pairs=[]
    for crs,group in polygons.groupby('geometry_crs',sort=True):
        geometries=shapely.from_wkb(group.geometry_wkb.to_numpy())
        if shapely.is_empty(geometries).any():
            raise ValueError('Empty external polygon')
        # Preserve original predicates. The national runner separately compares
        # every pair to MakeValid and refuses scientific output if they differ.
        transformer=Transformer.from_crs('EPSG:4326',crs,always_xy=True)
        x,y=transformer.transform(points.lon.to_numpy(),points.lat.to_numpy())
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError('Coordinate projection failed')
        # covered_by includes boundary points. Every matching polygon is retained.
        indices=STRtree(geometries).query(shapely.points(x,y),predicate='covered_by')
        pairs.append(pd.DataFrame({'origin_id':points.source_record_id.to_numpy()[indices[0]],
            'external_efua_id':group.eFUA_ID.to_numpy()[indices[1]]}))
    result=pd.concat(pairs,ignore_index=True) if pairs else pd.DataFrame(columns=['origin_id','external_efua_id'])
    return result.drop_duplicates().sort_values(['origin_id','external_efua_id']).reset_index(drop=True),set(points.source_record_id)


def footprint_union(units,members,stars):
    if not units.unit_id.is_unique or not units.core_origin_id.is_unique or not members.origin_id.is_unique:
        raise ValueError('Unit/core/member identities must be unique')
    primary=members.loc[members.unit_id.notna(),['unit_id','origin_id']]
    functional=stars[['centre_settlement_id','origin_id']].copy()
    functional['unit_id']=functional.centre_settlement_id.map(units.set_index('core_origin_id').unit_id)
    core=units[['unit_id','core_origin_id']].rename(columns={'core_origin_id':'origin_id'})
    # A context core may belong to another primary unit; still check its own
    # location explicitly rather than silently omitting this mandatory point.
    primary=primary.assign(from_primary=True)
    functional=functional[['unit_id','origin_id']].assign(from_original_functional=True)
    core=core.assign(mandatory_core=True)
    raw=pd.concat([primary,functional,core],ignore_index=True).dropna(subset=['unit_id','origin_id'])
    flags=['from_primary','from_original_functional','mandatory_core']
    raw[flags]=raw[flags].eq(True)
    raw=raw.groupby(['unit_id','origin_id'],as_index=False,sort=False)[flags].max()
    positive=set(members.loc[members.positive_whole_origin.eq(True),'origin_id'])
    return raw,raw[raw.origin_id.isin(positive)].copy()


def audit_units(units,raw,positive,pairs,known_points,reference):
    envelopes={key:set(group.external_efua_id) for key,group in pairs.groupby('origin_id',sort=False)}
    all_members=raw.groupby('unit_id').origin_id.agg(list).to_dict()
    required=positive.groupby('unit_id').origin_id.agg(list).to_dict()
    population=reference.set_index('source_record_id').population_2021
    summaries=[];candidates=[]
    for unit in units.itertuples(index=False):
        ids=required.get(unit.unit_id,[])
        unknown_pop=sum(origin not in population.index or pd.isna(population.loc[origin])
                        for origin in all_members.get(unit.unit_id,[]))
        unknown_geometry=sum(origin not in known_points for origin in ids)
        core_known=unit.core_origin_id in known_points
        core_envelopes=envelopes.get(unit.core_origin_id,set())
        whole=set(core_envelopes)
        for origin in ids:whole.intersection_update(envelopes.get(origin,set()))
        uncertainty=bool(unknown_pop or unknown_geometry or not core_known)
        if uncertainty:status='unknown_positive_demand_or_coordinates'
        elif not ids:status='no_positive_whole_demand'
        elif not core_envelopes:status='no_external_envelope'
        elif whole:status='whole_footprint_inside_one_or_more_envelopes'
        else:status='core_inside_but_child_outside_every_core_envelope'
        summaries.append({'unit_id':unit.unit_id,'core_origin_id':unit.core_origin_id,'name':unit.name,
            'unit_role':unit.unit_role,'is_registered_external_serving_centre':bool(unit.is_registered_external_serving_centre),
            'positive_whole_required_records_including_core_if_positive':len(ids),
            'raw_primary_functional_core_records':len(all_members.get(unit.unit_id,[])),
            'unknown_population_records_not_assumed_positive':unknown_pop,
            'positive_member_coordinates_unknown':unknown_geometry,'core_coordinates_known':core_known,
            'core_external_envelope_count':len(core_envelopes),'whole_known_positive_envelope_count':len(whole),
            'compatible_complete_input_envelope_count':len(whole) if not uncertainty and ids else 0,
            'core_external_envelope_ids_json':json.dumps(sorted(core_envelopes)),
            'whole_known_positive_envelope_ids_json':json.dumps(sorted(whole)),
            'compatibility_status':status,'external_envelope_is_independent_validation':False,
            'empirical_sgrt_level_assigned':False})
        for efua in sorted(core_envelopes):
            covered=sum(efua in envelopes.get(origin,set()) for origin in ids)
            candidates.append({'unit_id':unit.unit_id,'core_origin_id':unit.core_origin_id,'external_efua_id':efua,
                'unit_role':unit.unit_role,'required_positive_whole_records':len(ids),
                'required_positive_whole_inside':covered,'required_positive_whole_outside_or_unknown':len(ids)-covered,
                'unknown_population_records_not_assumed_positive':unknown_pop,
                'positive_member_coordinates_unknown':unknown_geometry,
                'whole_known_positive_footprint_inside':efua in whole,
                'complete_input_compatibility':bool(efua in whole and not uncertainty and ids)})
    return pd.DataFrame(summaries),pd.DataFrame(candidates)


def run(args):
    sources={k:digest(getattr(args,k)) for k in ['reference','units','memberships','service_memberships','polygons']}
    full_reference=pd.read_parquet(args.reference)
    reference=full_reference.dropna(subset=['source_record_id']).copy()
    units=pd.read_parquet(args.units);members=pd.read_parquet(args.memberships)
    stars=pd.read_parquet(args.service_memberships,columns=['centre_settlement_id','origin_id'])
    polygons=pd.read_parquet(args.polygons)
    raw,positive=footprint_union(units,members,stars)
    geometries=shapely.from_wkb(polygons.geometry_wkb.to_numpy())
    invalid=~shapely.is_valid(geometries)
    geometry_audit={'invalid_original_polygon_count':int(invalid.sum()),
        'invalid_external_efua_ids':polygons.loc[invalid,'eFUA_ID'].astype(str).tolist(),
        'invalid_reasons':shapely.is_valid_reason(geometries[invalid]).tolist(),
        'original_predicates_used':True,'silent_geometry_repair_applied':False}
    pairs,known=point_envelopes(reference,polygons)
    if invalid.any():
        repaired=polygons.copy()
        repaired['geometry_wkb']=shapely.to_wkb(shapely.make_valid(geometries))
        repaired_pairs,_=point_envelopes(reference,repaired)
        changes=pairs.merge(repaired_pairs,on=['origin_id','external_efua_id'],how='outer',indicator=True)
        geometry_audit['current_point_pair_changes_after_makevalid']=int(changes._merge.ne('both').sum())
        geometry_audit['original_invalid_polygon_area_m2']=shapely.area(geometries[invalid]).tolist()
        geometry_audit['makevalid_invalid_polygon_area_m2']=shapely.area(shapely.make_valid(geometries[invalid])).tolist()
        if geometry_audit['current_point_pair_changes_after_makevalid']:
            raise ValueError('Invalid source geometry changes coverage after MakeValid; explicit policy required')
    else:geometry_audit['current_point_pair_changes_after_makevalid']=0
    audit,candidates=audit_units(units,raw,positive,pairs,known,reference)
    args.output.mkdir(parents=True,exist_ok=True)
    for name,frame in [('point_external_envelope_pairs',pairs),('unit_external_envelope_candidates',candidates),('units_envelope_audit',audit),('checked_positive_whole_footprints',positive)]:
        frame.to_parquet(args.output/(name+'.parquet'),index=False)
    point_counts=pairs.groupby('external_efua_id').origin_id.nunique().rename('identified_reference_points')
    core_counts=candidates.groupby('external_efua_id').unit_id.nunique().rename('unit_cores_inside')
    pass_counts=candidates.loc[candidates.complete_input_compatibility].groupby('external_efua_id').unit_id.nunique().rename('complete_compatible_units')
    envelope_counts=polygons[['eFUA_ID']].rename(columns={'eFUA_ID':'external_efua_id'}).set_index('external_efua_id')
    envelope_counts=envelope_counts.join(point_counts).join(core_counts).join(pass_counts).fillna(0).astype('int64').reset_index()
    envelope_counts.to_parquet(args.output/'envelope_counts.parquet',index=False)
    counts=audit.groupby(['unit_role','compatibility_status']).size().rename('units').reset_index()
    counts.to_csv(args.output/'role_status_counts.csv',index=False)
    summary={'scope':'External eFUA2015 INPUT compatibility, not independent validation, observed flows, or SGRT tier 1',
        'analysis_origin_records':len(members),'positive_whole_analysis_origin_records':int(members.positive_whole_origin.eq(True).sum()),
        'original_primary_functional_positive_pairs':int((positive.from_primary | positive.from_original_functional).sum()),
        'mandatory_positive_core_pairs_added_to_original_footprint':int((~positive.from_primary & ~positive.from_original_functional & positive.mandatory_core).sum()),
        'reference_total_historical_chains':len(full_reference),'reference_identified_current_records':len(reference),
        'historical_chains_without_current_id_not_spatially_assigned':int(full_reference.source_record_id.isna().sum()),
        'geometry_audit':geometry_audit,
        'units':len(units),'registered_external_anchors':int(units.is_registered_external_serving_centre.sum()),
        'all_external_envelopes':len(polygons),'external_envelopes_covering_any_current_reference_point':int(pairs.external_efua_id.nunique()),
        'external_envelopes_covering_unit_core':int(candidates.external_efua_id.nunique()) if len(candidates) else 0,
        'external_envelopes_with_complete_compatible_footprint':int(candidates.loc[candidates.complete_input_compatibility,'external_efua_id'].nunique()) if len(candidates) else 0,
        'point_envelope_pairs':len(pairs),'current_points_in_any_envelope':int(pairs.origin_id.nunique()),
        'identified_current_records_with_valid_coordinate_points':len(known),
        'identified_current_records_without_valid_coordinates':len(reference)-len(known),
        'points_covered_by_multiple_envelopes':int(pairs.groupby('origin_id').size().gt(1).sum()),
        'unit_envelope_candidates':len(candidates),'raw_primary_functional_core_pairs':len(raw),
        'positive_whole_required_pairs':len(positive),'status_counts':{status:int(audit.compatibility_status.eq(status).sum()) for status in [
            'no_external_envelope','core_inside_but_child_outside_every_core_envelope',
            'whole_footprint_inside_one_or_more_envelopes','unknown_positive_demand_or_coordinates','no_positive_whole_demand']},
        'role_status_counts':counts.to_dict('records'),'boundary_rule':'covered_by; all overlapping envelopes retained',
        'unit_core_always_checked':True,'unknown_population_assumed_positive':False,
        'input_sha256':sources,'implementation_sha256':digest(Path(__file__))}
    if sources!={k:digest(getattr(args,k)) for k in sources}:raise ValueError('An input changed during audit')
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['reference','units','memberships','service-memberships','polygons','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    run(parser.parse_args())
