#!/usr/bin/env python3
"""Bounded provider-core sensitivities, not inferred commuting agglomerations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
try:
 from .hierarchy import canonical_edges,higher_candidates,promote_layer,demographic_summaries,save
 from .upward import STAGES,read_route,one_area_keys,inherited_provider_metadata,digest,mark_medical_need_scope
except ImportError:
 from hierarchy import canonical_edges,higher_candidates,promote_layer,demographic_summaries,save
 from upward import STAGES,read_route,one_area_keys,inherited_provider_metadata,digest,mark_medical_need_scope

DOMAINS={'medical_inpatient':'health','medical_specialized':'health','medical_hightech_licensed':'health',
 'vocational_education':'education','higher_education':'education','shopping_centre':'commerce'}


def provider_core_edges(routes,stage,provider_status):
 areas=one_area_keys(provider_status,'point_key')
 counts=provider_status.set_index('point_key').external_boundary_match_count
 parts=[]
 for family in stage['families']:
  d=mark_medical_need_scope(routes[family].copy(),family);d['service_family']=family;d['scenario_id']='extended_provider_core_scenario'
  d['provider_point_key']=d.provider_site_id
  d['parent_target_key']=d.provider_site_id.map(areas)
  ambiguous=d.provider_site_id.map(counts).gt(1).fillna(False)
  fallback=np.where(d.provider_settlement_id.notna(),'np:'+d.provider_settlement_id.astype(str),'site:'+d.provider_site_id.astype(str))
  d['parent_target_key']=d.parent_target_key.fillna(pd.Series(fallback,index=d.index)).mask(ambiguous)
  missing=d.provider_settlement_id.isna()&d.provider_site_id.isna()
  d.loc[missing,'parent_target_key']=pd.NA
  d['parent_target_kind']=np.where(d.parent_target_key.astype('string').str.startswith('efua:',na=False),'external_functional_area','provider')
  cost=pd.to_numeric(d.cost_minutes,errors='coerce')
  d['higher_admitted']=~missing&np.isfinite(cost)&cost.ge(0)&cost.le(stage['limit_minutes']+1e-8)
  d['territorial_merge_admitted']=d.higher_admitted&d.parent_target_key.notna()
  d['admission_limit_minutes']=stage['limit_minutes']
  d['admission_basis']='author_direct_car_cost_sensitivity_not_observed_trip_limit'
  d['territorial_guard_basis']='selected_provider_representative_point_core_and_all_member_direct_cost_no_origin_polygon_requirement'
  d['provider_core_geometry_is_building_verified']=False
  d['provider_core_membership_ambiguous']=ambiguous
  d['external_reference_epoch']=2015;d['external_reference_is_observed_commuting']=False
  d['origin_outside_external_polygon_permitted']=True
  d['functional_stage_name']=stage['name']
  if 'evidence_kind' not in d:d['evidence_kind']='reported_service_not_observed_use'
  d['quality']=d.get('evidence_quality',pd.Series(pd.NA,index=d.index))
  parts.append(d)
 return canonical_edges(pd.concat(parts,ignore_index=True),admission='higher_admitted')


def decide(candidates,mode,minimum_domains=2):
 """Whole-child positives only; one complete rival channel blocks selection."""
 if mode not in {'all_declared','partial_positive_two_domains'}:raise ValueError(mode)
 families=set(candidates.service_family.unique());decisions=[];synthetic=[]
 for (child,scenario),g in candidates.groupby(['child_unit_id','scenario_id'],sort=False):
  valid=g[g.territorial_merge_admitted_for_all_child_members]
  eligible=[]
  for target,v in valid.groupby('parent_target_key',sort=False):
   domains={DOMAINS[f] for f in v.service_family}
   if len(domains)>=minimum_domains and (mode!='all_declared' or set(v.service_family)==families):eligible.append(target)
  selected=None
  if not eligible:status='retained_insufficient_complete_independent_domains'
  elif len(eligible)>1:status='retained_ambiguous_multiple_eligible_cores'
  elif valid.parent_target_key.ne(eligible[0]).any():status='retained_complete_competing_core'
  else:selected=eligible[0];status='positive_whole_child_core_selected'
  decisions.append({'child_unit_id':child,'scenario_id':scenario,'parent_target_key':selected,'decision_status':status,
   'eligible_cores_json':json.dumps(eligible),'complete_positive_functions':len(valid),
   'partial_or_split_channel_present':bool(g.coverage_type.isin(['partial_higher_coverage','split_higher_candidates']).any()),
   'channels_without_admitted_evidence':int(g[g.coverage_type.eq('no_known_higher_candidate')].service_family.nunique()),
   'minimum_independent_domains_author_assumption':minimum_domains})
  v=valid[valid.parent_target_key.eq(selected)] if selected is not None else valid.iloc[:0]
  keys=sorted({k for literal in v.real_provider_keys_json for k in json.loads(literal)})
  synthetic.append({'child_unit_id':child,'scenario_id':scenario,'service_family':'explicit_'+mode,
   'parent_target_key':selected,'provider_key':None,'real_provider_keys_json':json.dumps(keys),
   'territorial_merge_admitted_for_all_child_members':selected is not None,
   'external_reference_parent_target':bool(selected is not None and selected.startswith('efua:'))})
 return pd.DataFrame(decisions),pd.DataFrame(synthetic)


def run(root,strict_directory,reference_path,output):
 root=Path(root);strict_directory=Path(strict_directory);output=Path(output)
 reference=pd.read_parquet(reference_path)
 lookup=strict_directory/'reference_lookup'
 provider_status=pd.read_parquet(lookup/'provider_external_fua_status.parquet')
 paths={f:root/'routes/nearest'/f'{f}.parquet' for f in DOMAINS}
 inputs=[*paths.values(),Path(reference_path),lookup/'provider_external_fua_status.parquet',lookup/'provider_points.parquet',
  Path(__file__),Path(__file__).with_name('hierarchy.py'),Path(__file__).with_name('higher_candidates_fast.py'),Path(__file__).with_name('upward.py'),
  strict_directory/'01_physician_direct_30/units.parquet',strict_directory/'01_physician_direct_30/memberships.parquet']
 hashes={str(p):digest(p) for p in inputs}
 routes={f:read_route(p) for f,p in paths.items()}
 lookup_points=pd.read_parquet(lookup/'provider_points.parquet').set_index('point_key')
 for family,d in routes.items():
  points=d[['provider_site_id','provider_lat','provider_lon']].dropna(subset=['provider_site_id']).drop_duplicates()
  if not points.provider_site_id.isin(provider_status.point_key).all():
   raise ValueError('Stale provider-core lookup misses selected source points: '+family)
  joined=points.join(lookup_points[['lat','lon']],on='provider_site_id',validate='many_to_one')
  for actual,expected in [('provider_lat','lat'),('provider_lon','lon')]:
   if not np.isclose(joined[actual],joined[expected],equal_nan=True,atol=1e-10,rtol=0).all():
    raise ValueError('Provider-core lookup coordinates differ from actual selected source: '+family)
 results={}
 for mode in ['all_declared','partial_positive_two_domains']:
  child=pd.read_parquet(inputs[-2]);members=pd.read_parquet(inputs[-1]);summaries=[]
  for index,stage in enumerate(STAGES[1:],2):
   folder=output/mode/f'{index:02d}_{stage["name"]}';folder.mkdir(parents=True,exist_ok=True)
   edges=provider_core_edges(routes,stage,provider_status)
   candidates=higher_candidates(members,edges,reference)
   decisions,selected=decide(candidates,mode)
   parents,parent_members,crosswalk,stop=promote_layer(child,members,selected,index)
   parents=inherited_provider_metadata(parents,crosswalk,child,selected)
   parents=parents.merge(demographic_summaries(parent_members,reference),on='unit_id',validate='one_to_one')
   parents['functional_stage_name']=stage['name'];parents['extended_core_mode']=mode
   parents['not_observed_agglomeration_or_commuting_region']=True
   for name,frame in [('higher_edge_evidence',edges),('parent_candidates',candidates),('parent_decisions',decisions),
    ('selected_core_candidates',selected),('units',parents),('memberships',parent_members),('subsystem_crosswalk',crosswalk)]:save(frame,folder/name)
   summary={'stage':index,'name':stage['name'],'mode':mode,'families':stage['families'],'function_domains':DOMAINS,
    'minimum_domains':2,'minimum_domains_is_author_sensitivity_assumption':True,'child_units':len(child),
    'parent_units':len(parents),'new_merger_groups':int(parents.new_territorial_merger.sum()),
    'origins_retained':parent_members.origin_id.nunique(),'maximum_effective_merge_depth':int(parents.effective_merge_depth.max()),
    'decision_statuses':decisions.decision_status.value_counts().to_dict(),'origin_polygon_is_not_a_hard_boundary':True,
    'provider_point_may_be_settlement_representative_not_building':True,'observed_hierarchy_established':False}
   (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
   print(json.dumps(summary,ensure_ascii=False),flush=True)
   summaries.append(summary);child=parents;members=parent_members
  results[mode]=summaries
 if hashes!={str(p):digest(p) for p in inputs}:raise RuntimeError('Input mutated during extended calculation')
 result={'scenarios':results,'function_domains':DOMAINS,'input_sha256':hashes,'code_sha256':digest(__file__),
  'hierarchy_code_sha256':digest(Path(__file__).with_name('hierarchy.py')),
  'candidate_engine':'higher_candidates_fast_with_original_reference_reducer_retained',
  'candidate_engine_sha256':digest(Path(__file__).with_name('higher_candidates_fast.py')),
  'population_used_for_assignment':False,'Moscow_only_top_forced':False,'observed_hierarchy_established':False}
 output.mkdir(parents=True,exist_ok=True);(output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
 p.add_argument('--strict-directory',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 run(a.root,a.strict_directory,a.reference,a.output)
