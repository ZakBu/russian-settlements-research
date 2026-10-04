#!/usr/bin/env python3
"""Measure exact identity_sets coverage deltas for the frozen 2k candidate packet."""
from pathlib import Path
import json,math
import numpy as np
import pandas as pd
from research_rebuild.mass_linkage.stage_residual_population_qid_signature_mass_20261004 import OUT,SEL,G,P,COV,sha,truth,utc
from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF
from research_rebuild.mass_linkage.coverage import identity_sets,metric

ROOT=OUT/'expanded_fetch';PK=ROOT/'final_candidate_packet';SUP=ROOT/'conditional_coverage_supplement'

def hav_km(lat1,lon1,lat2,lon2):
 r=6371.0088
 a1,a2=np.radians(lat1),np.radians(lat2); dlat=np.radians(lat2-lat1); dlon=np.radians(lon2-lon1)
 h=np.sin(dlat/2)**2+np.cos(a1)*np.cos(a2)*np.sin(dlon/2)**2
 return 2*r*np.arcsin(np.sqrt(np.minimum(1,h)))
def point_propagation(components,points,affected_targets=None):
 direct=set(points.target_source_record_id.astype(str));prop=set(direct);rows=[]
 pmap={}
 for r in points.to_dict('records'):pmap.setdefault(str(r['target_source_record_id']),[]).append(r)
 for ix,members in enumerate(components):
  if affected_targets is not None and not any(str(sid) in affected_targets for sid in members):continue
  seeds=[r for sid in members for r in pmap.get(str(sid),[])]
  if not seeds:continue
  seeds.sort(key=lambda r:(int(float(r.get('target_year') or 0))!=2021,-int(float(r.get('target_year') or 0)),str(r.get('review_id') or ''),str(r['target_source_record_id'])))
  carrier=seeds[0]; d=max(float(hav_km(float(carrier['latitude']),float(carrier['longitude']),float(x['latitude']),float(x['longitude']))) for x in seeds)
  ok=d<=5.0
  rows.append({'component_index':ix,'member_count':len(members),'accepted_seed_count':len(seeds),'carrier_source_record_id':str(carrier['target_source_record_id']),'carrier_year':int(float(carrier.get('target_year') or 0)),'max_distance_to_carrier_km':d,'spread_le_5km':ok,'candidate_propagated_targets':len(members-direct) if ok else 0,'candidate_only':True})
  if ok:prop.update(map(str,members))
 return direct,prop,rows

def measure_axes(selected,linked,full,direct,prop,controls):
 out={}
 for y,g in selected.groupby('census_year',sort=True):
  y=int(y); control=controls[y]
  out[y]={'selected_known_population':int(g.population.sum()),'official_control':control,
          'identity_link_to_other_census':metric(g,linked,control),
          'full_census_chain':metric(g,full,control),
          'joint_point_and_at_least_one_other_census_direct_only':metric(g,direct&linked,control),
          'joint_point_and_all_three_censuses_direct_only':metric(g,direct&full,control),
          'joint_point_and_at_least_one_other_census_with_component_propagation':metric(g,prop&linked,control),
          'joint_point_and_all_three_censuses_with_component_propagation':metric(g,prop&full,control),
          'full_chain_rows_direct_point_quality':g.loc[g.source_record_id.isin(full&direct)].groupby('population_value_quality',dropna=False).agg(rows=('source_record_id','size'),population=('population','sum')).reset_index().to_dict('records'),
          'full_chain_rows_propagated_point_quality':g.loc[g.source_record_id.isin(full&prop)].groupby('population_value_quality',dropna=False).agg(rows=('source_record_id','size'),population=('population','sum')).reset_index().to_dict('records')}
 return out

def main():
 SUP.mkdir(exist_ok=True)
 selected=pd.read_parquet(SEL,columns=['source_record_id','census_year','population','population_scope','population_value_quality','settlement_id'])
 selected.source_record_id=selected.source_record_id.astype(str);selected.census_year=selected.census_year.astype(int)
 points=pd.read_parquet(P,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','review_id'])
 points=points[points.coordinate_admission_status.isin({'reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted'})].copy();points.target_source_record_id=points.target_source_record_id.astype(str)
 base=pd.read_parquet(G,columns=['from_source_record_id','to_source_record_id'])
 base=base.rename(columns={'from_source_record_id':'from_source_record_id','to_source_record_id':'to_source_record_id'})
 b_link,b_full,b_comp=identity_sets(selected[['source_record_id','census_year']],base)
 controls={int(x['year']):int(x['official_control']) for x in json.loads(COV.read_text())['census_metrics']}
 b_direct=set(points.target_source_record_id.astype(str));b_prop=set(b_direct)
 bm=measure_axes(selected,b_link,b_full,b_direct,b_prop,controls)
 cand=pd.read_csv(PK/'unique_signature_current_binding_source_evidence_candidates.csv',low_memory=False)
 cand['source_population_quality_reviewable']=cand.source_population_quality_reviewable.map(truth)
 e=pd.read_csv(PK/'conditional_year_uf_candidate_edges.csv',dtype={'from_source_record_id':str,'to_source_record_id':str},low_memory=False)
 out=[]
 for label,cd in [('all_923_identity_candidates',cand),('914_source_quality_reviewable',cand[cand.source_population_quality_reviewable])]:
  uf=YearUF(selected.source_record_id.tolist(),selected.census_year.tolist())
  for a,b in base[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
   if uf.union_ids(str(a),str(b))=='year_constrained_collision':raise ValueError('baseline collision')
  fresh=[]
  qset=set(cd.wikidata_qid.astype(str))
  for r in e[e.wikidata_qid.astype(str).isin(qset)].sort_values(['wikidata_qid','historical_year']).to_dict('records'):
   status=uf.union_ids(str(r['from_source_record_id']),str(r['to_source_record_id']))
   if status=='year_constrained_collision':raise ValueError('candidate causes same-year collision in combined graph')
   if status=='merged':fresh.append(r)
  add=pd.DataFrame(fresh)[['from_source_record_id','to_source_record_id']] if fresh else pd.DataFrame(columns=['from_source_record_id','to_source_record_id'])
  union=pd.concat([base,add],ignore_index=True)
  linked,full,comps=identity_sets(selected[['source_record_id','census_year']],union)
  affected={str(x[k]) for x in fresh for k in ('from_source_record_id','to_source_record_id')}
  dr,prop,pr=point_propagation(comps,points,affected_targets=affected)
  metrics=measure_axes(selected,linked,full,dr,prop,controls)
  out.append({'scenario':label,'candidate_qids':int(cd.wikidata_qid.nunique()),'new_uf_edges':len(fresh),'baseline_linked_vertices':len(b_link),'after_linked_vertices':len(linked),'baseline_full_chain_vertices':len(b_full),'after_full_chain_vertices':len(full),'point_propagation_components':len(pr),'components_with_5km_pass':sum(bool(x['spread_le_5km']) for x in pr),'components_over_5km_held':sum(not bool(x['spread_le_5km']) for x in pr),'baseline_point_targets':len(b_direct),'after_candidate_component_propagated_point_targets':len(prop),'baseline_metrics':bm,'candidate_metrics':metrics,'edge_receipt':'candidate-only; does not update accepted graph or point ledger'})
  if label=='all_923_identity_candidates': pd.DataFrame(pr).to_csv(SUP/'all_923_candidate_component_point_spread.csv',index=False)
 result={'status':'candidate_only_coverage_supplement_no_status_changes','created_utc':utc(),'baseline_graph_sha256':sha(G),'baseline_point_uses_sha256':sha(P),'candidate_packet_receipt_sha256':sha(PK/'receipt.json'),'official_baseline_reproduced':{str(y):{'joint_point_all_three':bm[y]['joint_point_and_all_three_censuses_direct_only'],'joint_point_any_other':bm[y]['joint_point_and_at_least_one_other_census_direct_only']} for y in sorted(bm)},'scenarios':out,'limitations':['All candidate links remain unreviewed.','Conditional point propagation uses the deterministic 2021 accepted point carrier and holds components whose other accepted seed points are >5 km from it.','P1082 is secondary evidence; publisher populations remain unchanged and 2010 protected/scope-unverified values retain that status.','Candidate edge gains are not added to official published metrics until independent review and canonical application.']}
 (SUP/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 (SUP/'receipt.json').write_text(json.dumps({'status':result['status'],'script_sha256':sha(__file__),'baseline_graph_sha256':sha(G),'baseline_point_uses_sha256':sha(P),'candidate_packet_receipt_sha256':sha(PK/'receipt.json'),'output_summary_sha256':sha(SUP/'summary.json')},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result['official_baseline_reproduced'],ensure_ascii=False,indent=2))
 for s in out:
  print(s['scenario'],s['new_uf_edges'],s['components_with_5km_pass'],s['components_over_5km_held'])
  for y,m in s['candidate_metrics'].items(): print(y,m['joint_point_and_all_three_censuses_with_component_propagation'],m['joint_point_and_at_least_one_other_census_with_component_propagation'])
if __name__=='__main__':main()
