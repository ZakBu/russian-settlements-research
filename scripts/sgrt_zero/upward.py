#!/usr/bin/env python3
"""Try every declared higher functional set while retaining lower subsystems.

Direct medical grouping is separate from the external-modelled-urban-area
scenario. A rare provider never creates an unbounded territorial catchment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from hierarchy import canonical_edges,demographic_summaries,higher_candidates,promote_layer,save


STAGES=[
 {'name':'physician_direct_30','families':['medical_physician_primary'],'limit_minutes':30.,
  'guard':'direct_bounded_functional_medical_scenario','source_role':'author_car_network_scenario_with_dated_rural_SP42_comparator_not_observed_trips'},
 {'name':'urban_hospital_college','families':['medical_inpatient','vocational_education'],'limit_minutes':90.,
  'guard':'same_external_estimated_efua2015','source_role':'author_numerical_sensitivity_not_literature_estimated_trip_limit'},
 {'name':'urban_specialized_university_shopping','families':['medical_specialized','higher_education','shopping_centre'],'limit_minutes':90.,
  'guard':'same_external_estimated_efua2015','source_role':'author_numerical_sensitivity_not_literature_estimated_trip_limit'},
 {'name':'urban_hightech','families':['medical_hightech_licensed'],'limit_minutes':120.,
  'guard':'same_external_estimated_efua2015','source_role':'author_numerical_sensitivity_not_literature_estimated_trip_limit'},
]
ROUTE_COLUMNS=['origin_id','provider_settlement_id','provider_site_id','provider_lat','provider_lon','cost_minutes',
 'network_minutes','connector_minutes','point_separation_km','known_local_supply','zero_cost_np_assumption','route_status',
 'source_id','source_year','source_snapshot','evidence_quality','evidence_kind','location_precision','road_snapshot_utc',
 'provider_source_service_code','provider_source_pool','provider_source_object_id','provider_np_identity_basis',
 'provider_actual_operational_status_checked','provider_source_status_semantics_verified','provider_input_kind',
 'provider_grades_known','provider_school_program_evidence_json','specific_institution_choice_established','observed_flow',
 'assignment_established','origin_is_additional_context','budget_population_credit','provider_provider_name']


def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for chunk in iter(lambda:stream.read(4<<20),b''):h.update(chunk)
 return h.hexdigest()


def read_route(path):
 names=set(pq.read_schema(path).names)
 required={'origin_id','provider_settlement_id','provider_site_id','provider_lat','provider_lon','cost_minutes'}
 if not required.issubset(names):raise ValueError('Route source missing fields: '+str(sorted(required-names)))
 d=pd.read_parquet(path,columns=[c for c in ROUTE_COLUMNS if c in names])
 if not d.origin_id.is_unique:raise ValueError('More than one selected nearest provider per origin: '+str(path))
 d['provider_name']=d.get('provider_provider_name',pd.Series(pd.NA,index=d.index))
 return d


def one_area_keys(status,key):
 if status[key].duplicated().any():raise ValueError('Boundary status key not unique')
 out={}
 for row in status[[key,'external_boundary_match_count','external_efua_ids_json']].itertuples(index=False,name=None):
  identifier,count,literal=row
  if count==1:
   ids=json.loads(literal)
   if len(ids)!=1:raise ValueError('Boundary count disagrees with IDs')
   out[identifier]='efua:'+str(int(ids[0]))
 return out


def prepare_stage_edges(routes,stage,origin_status,provider_status):
 """Admit direct source costs; external areas are targets, never provider IDs."""
 origin_area=one_area_keys(origin_status,'source_record_id');provider_area=one_area_keys(provider_status,'point_key')
 parts=[]
 for family in stage['families']:
  d=routes[family].copy();d['service_family']=family;d['scenario_id']='explicit_higher_function_scenario'
  cost=pd.to_numeric(d.cost_minutes,errors='coerce')
  provider_known=d.provider_settlement_id.notna()|d.provider_site_id.notna()
  d['higher_admitted']=provider_known&np.isfinite(cost)&cost.ge(0)&cost.le(stage['limit_minutes']+1e-8)
  d['admission_limit_minutes']=float(stage['limit_minutes'])
  d['admission_basis']=stage['source_role']
  d['functional_stage_name']=stage['name'];d['functional_stage_is_explicit_scenario']=True
  d['higher_role_is_not_automatic_city_rank']=True
  d['age_eligibility_and_free_capacity_not_established']=True
  d['ordinary_public_access_scope_not_universally_verified']=True
  d['source_role_and_time_bound_are_not_observed_demand']=True
  if stage['guard']=='direct_bounded_functional_medical_scenario':
   d['territorial_merge_admitted']=d.higher_admitted
   d['territorial_guard_basis']='direct_physician_cost30_dated_rural_comparator_author_city_car_scenario_not_agglomeration'
   d['parent_target_kind']='provider'
   d['origin_external_area_key']=d.origin_id.map(origin_area)
   d['provider_external_area_key']=d.provider_site_id.map(provider_area)
  else:
   d['origin_external_area_key']=d.origin_id.map(origin_area)
   d['provider_external_area_key']=d.provider_site_id.map(provider_area)
   common=d.origin_external_area_key.notna()&d.origin_external_area_key.eq(d.provider_external_area_key)
   d['territorial_merge_admitted']=d.higher_admitted&common
   d['territorial_guard_basis']='origin_and_selected_provider_inside_same_single_estimated_efua2015'
   d['parent_target_key']=d.origin_external_area_key.where(common)
   d['parent_target_kind']=np.where(common,'external_functional_area','provider')
  d['external_reference_epoch']=2015
  d['external_reference_is_observed_commuting']=False
  d['outside_external_area_is_not_evidence_of_isolation']=True
  if 'evidence_kind' not in d:d['evidence_kind']='reported_service_not_observed_use'
  else:d['evidence_kind']=d.evidence_kind.fillna('reported_service_not_observed_use')
  d['quality']=d.get('evidence_quality',pd.Series(pd.NA,index=d.index))
  parts.append(d)
 return canonical_edges(pd.concat(parts,ignore_index=True),admission='higher_admitted')


def prepare_provider_lookup(routes,polygons,output):
 from logic_checks import locate_external_fua_points
 points=[]
 for d in routes.values():
  x=d[['provider_site_id','provider_lat','provider_lon']].dropna(subset=['provider_site_id']).drop_duplicates()
  points.append(x.rename(columns={'provider_site_id':'point_key','provider_lat':'lat','provider_lon':'lon'}))
 frame=pd.concat(points,ignore_index=True).drop_duplicates().reset_index(drop=True)
 if frame.duplicated('point_key').any():raise ValueError('Same provider ID has conflicting coordinates across source functions')
 output.mkdir(parents=True,exist_ok=True);save(frame,output/'provider_points')
 links,status=locate_external_fua_points(frame,polygons)
 save(links,output/'provider_external_fua_links');save(status,output/'provider_external_fua_status')
 return status


def inherited_provider_metadata(parent_units,crosswalk,child_units,candidates):
 field='all_provider_keys_json' if 'all_provider_keys_json' in child_units else 'provider_keys_json' if 'provider_keys_json' in child_units else 'real_provider_keys_json'
 child_provider=child_units.set_index('unit_id')[field].to_dict()
 child_reference=child_units.set_index('unit_id').reference_area_keys_json.to_dict() if 'reference_area_keys_json' in child_units else {}
 provider_sets={};reference_sets={}
 for r in crosswalk.itertuples():
  provider_sets.setdefault(r.unit_id,set()).update(json.loads(child_provider.get(r.child_unit_id,'[]')))
  reference_sets.setdefault(r.unit_id,set()).update(json.loads(child_reference.get(r.child_unit_id,'[]')))
 joined=candidates.merge(crosswalk[['child_unit_id','scenario_id','unit_id']],on=['child_unit_id','scenario_id'],validate='many_to_one')
 for uid,g in joined[joined.territorial_merge_admitted_for_all_child_members].groupby('unit_id',sort=False):
  reference_sets.setdefault(uid,set()).update(str(k) for k in g.parent_target_key.dropna() if str(k).startswith('efua:'))
 for r in parent_units.itertuples():provider_sets.setdefault(r.unit_id,set()).update(json.loads(r.real_provider_keys_json))
 parent_units['all_provider_keys_json']=parent_units.unit_id.map(lambda k:json.dumps(sorted(provider_sets.get(k,set())),ensure_ascii=False))
 parent_units['reference_area_keys_json']=parent_units.unit_id.map(lambda k:json.dumps(sorted(reference_sets.get(k,set())),ensure_ascii=False))
 parent_units['provider_population_is_nonadditive_context']=True
 return parent_units


def run(root,l0_directory,reference_path,fua_directory,physician_route,output,medical_routes=None):
 root=Path(root);l0_directory=Path(l0_directory);fua_directory=Path(fua_directory);output=Path(output)
 output.mkdir(parents=True,exist_ok=True)
 reference=pd.read_parquet(reference_path);child_units=pd.read_parquet(l0_directory/'level0_units.parquet')
 members=pd.read_parquet(l0_directory/'level0_memberships.parquet')
 if members.scenario_id.nunique()!=1:raise ValueError('Run upward for one explicit L0 scenario at a time')
 required=sorted({family for stage in STAGES for family in stage['families']})
 paths={}
 for family in required:
  if family=='medical_physician_primary':paths[family]=Path(physician_route)
  elif medical_routes is not None and family in {'medical_inpatient','medical_specialized'}:
   paths[family]=Path(medical_routes)/f'{family}.parquet'
  else:paths[family]=root/'routes/nearest'/f'{family}.parquet'
 for family,path in paths.items():
  if not path.is_file():raise ValueError('Higher function route missing: '+family+' '+str(path))
 source_paths=[reference_path,l0_directory/'level0_units.parquet',l0_directory/'level0_memberships.parquet',fua_directory/'analysis_frame_efua_2015.parquet',fua_directory/'settlement_external_fua_status.parquet',*paths.values()]
 snapshots={str(p):digest(p) for p in source_paths}
 routes={family:read_route(path) for family,path in paths.items()}
 polygons=pd.read_parquet(fua_directory/'analysis_frame_efua_2015.parquet');origin_status=pd.read_parquet(fua_directory/'settlement_external_fua_status.parquet')
 lookup_output=output/'reference_lookup';lookup_manifest=lookup_output/'lookup_cache.json'
 lookup_inputs={str(path):snapshots[str(path)] for path in [fua_directory/'analysis_frame_efua_2015.parquet',*paths.values()]}
 from logic_checks import locate_external_fua_points
 import inspect
 lookup_function_hash=hashlib.sha256(inspect.getsource(locate_external_fua_points).encode()).hexdigest()
 cached=json.loads(lookup_manifest.read_text()) if lookup_manifest.exists() else {}
 valid_cache=cached.get('input_sha256')==lookup_inputs and cached.get('lookup_function_sha256')==lookup_function_hash
 if valid_cache:
  valid_cache=all((lookup_output/name).is_file() and digest(lookup_output/name)==sha for name,sha in cached.get('output_sha256',{}).items())
  valid_cache=valid_cache and set(cached.get('output_sha256',{}))=={'provider_points.parquet','provider_external_fua_links.parquet','provider_external_fua_status.parquet'}
 if valid_cache:provider_status=pd.read_parquet(lookup_output/'provider_external_fua_status.parquet')
 else:
  provider_status=prepare_provider_lookup(routes,polygons,lookup_output)
  record={'input_sha256':lookup_inputs,'lookup_function_sha256':lookup_function_hash,
   'output_sha256':{name:digest(lookup_output/name) for name in ['provider_points.parquet','provider_external_fua_links.parquet','provider_external_fua_status.parquet']}}
  lookup_manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
 previous=['medical_basic','school','grocery','parcel_pickup'];summaries=[]
 for index,stage in enumerate(STAGES,1):
  folder=output/f'{index:02d}_{stage["name"]}';folder.mkdir(parents=True,exist_ok=True)
  edges=prepare_stage_edges(routes,stage,origin_status,provider_status)
  candidates=higher_candidates(members,edges,reference)
  parents,parent_members,crosswalk,stop=promote_layer(child_units,members,candidates,index,previous)
  parents=inherited_provider_metadata(parents,crosswalk,child_units,candidates)
  parents=parents.merge(demographic_summaries(parent_members,reference),on='unit_id',validate='one_to_one')
  parents['functional_stage_name']=stage['name'];parents['source_stage_guard']=stage['guard']
  for name,frame in [('higher_edge_evidence',edges),('parent_candidates',candidates),('units',parents),('memberships',parent_members),('subsystem_crosswalk',crosswalk)]:save(frame,folder/name)
  summary={'stage':index,'name':stage['name'],'families':stage['families'],'limit_minutes':stage['limit_minutes'],'guard':stage['guard'],
   'child_units':len(child_units),'parent_units':len(parents),'origins_retained':parent_members.origin_id.nunique(),
   'new_merger_groups':int(parents.new_territorial_merger.sum()),'maximum_effective_merge_depth':int(parents.effective_merge_depth.max()),
   'mergers_using_or_inheriting_external_reference':int((parents.new_territorial_merger&parents.boundary_depends_on_external_reference).sum()),
   'candidate_types':candidates.coverage_type.value_counts().to_dict(),'new_function_attempt':stop,
   'a_no_merger_stage_does_not_skip_remaining_new_functions':True,'source_quality_and_geometry_not_observed_flows':True}
  (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(summary,ensure_ascii=False),flush=True)
  summaries.append(summary);previous+=stage['families'];child_units=parents;members=parent_members
 if snapshots!={str(p):digest(p) for p in source_paths}:raise RuntimeError('An input changed during upward calculation')
 result={'stages_attempted':len(STAGES),'declared_scenarios':STAGES,'stages':summaries,
  'maximum_supported_merge_depth':int(child_units.effective_merge_depth.max()),'origins_retained':members.origin_id.nunique(),
  'observed_agglomeration_hierarchy_established':False,'source_of_external_reference':'GHS_FUA2015_R2019A_independent_estimated_boundary_epoch2015',
  'Moscow_only_top_forced':False,'population_used_for_assignment':False,'input_sha256':snapshots,
  'code_sha256':digest(Path(__file__)),'hierarchy_code_sha256':digest(Path(__file__).with_name('hierarchy.py')),
  'halt_reason':'all_available_declared_new_function_sets_attempted_no_additional_evidence_for_further_order',
  'further_order_needs_new_inter_system_or_functional_evidence_not_larger_unbounded_catchments':True}
 (output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--l0-directory',type=Path,required=True)
 p.add_argument('--reference',type=Path,required=True);p.add_argument('--fua-directory',type=Path,required=True);p.add_argument('--physician-route',type=Path,required=True);p.add_argument('--medical-routes',type=Path);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();print(json.dumps(run(a.root,a.l0_directory,a.reference,a.fua_directory,a.physician_route,a.output,a.medical_routes),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
