"""Reproject a frozen raw-native 2011 point candidate set to the fifth accepted base.

No identity graph or point admissions are made. Relation ``same_place_candidate``
rows are included because their canonical decision status is already accepted;
they are treated as same-place connectivity for this projection.
"""
from __future__ import annotations
import argparse, hashlib, json, math, shutil
from collections import defaultdict
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES, ACCEPTED_COORDINATE_STATUSES

ROOT=Path('/workspace')
SEL=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EVID=ROOT/'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/accepted_identity_edges.parquet'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/accepted_point_uses.parquet'
COVERAGE=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/coverage.json'
BASE_RECEIPT=ROOT/'settlements-work/continuation_20261004/accepted_mass_fifth_with_context/receipt.json'
OLD_DIR=ROOT/'settlements-work/continuation_20261004/R4/named_native_point_full_chain_recovery_20261004/freeze_v1'
OLD_CSV=OLD_DIR/'staged_point_use_candidates.csv'; OLD_RECEIPT=OLD_DIR/'receipt.json'
HIST=ROOT/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
QUARANTINE=ROOT/'settlements-work/continuation_20261004/R4/point_quarantine_scope_recovery_20261004/scoped_quarantine_dispositions.jsonl'
TYPED_DIR=ROOT/'settlements-work/continuation_20261004/R4/official_comparative_transformation_recovery_20261004/freeze_v3'

HIST_COLS=['source_record_id','historical_named_point_candidate','historical_name_exact','historical_type_exact','historical_key_region_name_type_count','possible_unlocated_historical_competitor','historical_code_structure_compatible','historical_point_modern_region','historical_okato_2009_raw','historical_okato_2011_raw','name_raw_2009','name_raw_2011','name_key','geo_name_key','type_key_2009','type_key_2011','settlement_type_raw','latitude_from_lat','longitude_from_long','source_sha256_2009','source_sha256_2011','record_number_1based','record_byte_offset_0based','historical_okato','code_join_basis']

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def distance_km(a,b):
 if not all(pd.notna(v) for v in [a[0],a[1],b[0],b[1]]):return None
 lat1,lon1,lat2,lon2=map(math.radians,[float(a[0]),float(a[1]),float(b[0]),float(b[1])])
 h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
 if a.output.exists():raise FileExistsError('Use a new immutable output directory')
 a.output.mkdir(parents=True)
 # Verify frozen base receipt and its ledger hashes before projection.
 br=json.loads(BASE_RECEIPT.read_text())
 if sha(GRAPH)!=br['outputs']['accepted_identity_edges.parquet'] or sha(POINTS)!=br['outputs']['accepted_point_uses.parquet']:
  raise ValueError('Fifth accepted base differs from its receipt')
 basecov=json.loads(COVERAGE.read_text())
 if basecov.get('identity_graph',{}).get('edges')!=327745 or basecov.get('identity_graph',{}).get('full_census_components')!=112577:
  raise ValueError('Unexpected fifth-base coverage snapshot')
 candidates=pd.read_csv(OLD_CSV,dtype={'raw_historical_OKATO_2009':str,'raw_historical_OKATO_2011':str,'modern_current_OKTMO_literal':str})
 if candidates.target_source_record_id.duplicated().any():raise ValueError('Frozen point candidates have duplicate target IDs')
 cand_ids=set(candidates.target_source_record_id)
 modern_ids=set(candidates.modern_current_source_record_id)
 # Minimal selected ledger; IDs are the canonical endpoints and populations are unchanged source values.
 s=pd.read_parquet(SEL,columns=['source_record_id','census_year','population','latitude','longitude','settlement_name','settlement_type','name_norm','type_norm','region_norm','population_scope','is_additive_settlement_record','entity_grain_status','oktmo','okato','source_native_id','source_file','source_sheet','source_row','source_sha256','source_locator'])
 if s.source_record_id.isna().any() or s.source_record_id.duplicated().any():raise ValueError('Selected source IDs must be unique')
 years=s.set_index('source_record_id').census_year.to_dict(); rowmap=s.set_index('source_record_id',drop=False)
 if not cand_ids.issubset(years) or not modern_ids.issubset(years):raise ValueError('Candidate endpoint absent from current selected source layer')
 # Recount literal source-native OKTMO uniqueness over all selected 2021 observations.
 cur=s[s.census_year.eq(2021)].copy();cur['native_oktmo_count']=cur.groupby('oktmo',dropna=False).source_record_id.transform('size');curmap=cur.set_index('source_record_id',drop=False)
 # Historical parsed-table row replay for these target IDs (raw 2009/2011 labels, code and DBF locator).
 hist=pd.read_parquet(HIST,columns=HIST_COLS);hist=hist[hist.source_record_id.isin(cand_ids)]
 if hist.source_record_id.duplicated().any():raise ValueError('Historical table has duplicate exact selected rows')
 hmap=hist.set_index('source_record_id',drop=False)
 # Current source evidence replay. Optional inherited flags are retained but never used as acceptance gates.
 src_evidence={}
 for b in pq.ParquetFile(EVID).iter_batches(columns=['source_record_id','source_evidence_json'],batch_size=65536):
  for sid,payload in zip(b.column(0).to_pylist(),b.column(1).to_pylist()):
   if sid in modern_ids:src_evidence[sid]=json.loads(payload)
 if set(src_evidence)!=modern_ids:raise ValueError('Current source evidence is not complete for all modern witnesses')
 # Accepted graph projection: canonical statuses only. Do not drop relation=same_place_candidate.
 g=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','decision_status','relation'])
 if not g.decision_status.isin(ACCEPTED_EDGE_STATUSES).all():raise ValueError('Fifth graph has unaccepted canonical decision status')
 parent={x:x for x in years};rank={x:0 for x in years}
 def find(x):
  while parent[x]!=x: parent[x]=parent[parent[x]];x=parent[x]
  return x
 def union(x,y):
  x,y=find(x),find(y)
  if x==y:return
  if rank[x]<rank[y]:x,y=y,x
  parent[y]=x
  if rank[x]==rank[y]:rank[x]+=1
 for x,y in g[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None):
  if x not in parent or y not in parent:raise ValueError('Graph endpoint outside selected source layer')
  if years[x]==years[y]:raise ValueError('Accepted graph has same-year direct edge')
  union(x,y)
 compmembers=defaultdict(list)
 for sid in years:compmembers[find(sid)].append(sid)
 for members in compmembers.values():
  ys=[int(years[x]) for x in members]
  if len(ys)!=len(set(ys)):raise ValueError('Accepted component has a same-year collision')
 full_roots={r for r,m in compmembers.items() if {2002,2010,2021}.issubset({int(years[x]) for x in m})}
 # All accepted point-use records remain governed by the canonical status field.
 pts=pd.read_parquet(POINTS,columns=['target_source_record_id','coordinate_admission_status','latitude','longitude','coordinate_source','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','source_file','source_row','source_sha256'])
 if not pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all():raise ValueError('Fifth point ledger has nonaccepted canonical status')
 if pts.target_source_record_id.duplicated().any():raise ValueError('Fifth point ledger has duplicate target IDs')
 pointmap=pts.set_index('target_source_record_id',drop=False);point_ids=set(pointmap.index)
 baseline_reproduction={}
 cov_by_year={int(x['year']):x for x in basecov['census_metrics']}
 for y,group in s.groupby('census_year',sort=True):
  y=int(y); full_mask=group.source_record_id.map(lambda sid:find(sid) in full_roots)
  joint_mask=full_mask & group.source_record_id.isin(point_ids)
  f={'rows':int(full_mask.sum()),'known_population':int(group.loc[full_mask,'population'].sum())}
  j={'rows':int(joint_mask.sum()),'known_population':int(group.loc[joint_mask,'population'].sum())}
  frozen=cov_by_year[y]['axes']
  if f!= {k:frozen['full_census_chain'][k] for k in ['rows','known_population']} or j!={k:frozen['joint_admitted_coordinate_and_full_chain'][k] for k in ['rows','known_population']}:
   raise ValueError(f'Fifth coverage baseline does not reproduce for {y}: {f} / {j}')
  baseline_reproduction[str(y)]={'full_chain':f,'joint_full_chain':j}
 # Same-place alias status is canonical-accepted. The record count and edge IDs are preserved for reproducibility.
 alias_edges=g[g.relation.eq('same_place_candidate')]
 if len(alias_edges)!=114:raise ValueError(f'Expected 114 accepted same_place_candidate alias edges, got {len(alias_edges)}')
 alias_roots={find(x) for pair in alias_edges[['from_source_record_id','to_source_record_id']].itertuples(index=False,name=None) for x in pair}
 # Load prior provider/point-choice quarantines. Only explicit true physical conflict is a hold here.
 quarantine={}
 for line in QUARANTINE.open():
  q=json.loads(line);sid=q.get('source_record_id')
  if sid:quarantine[sid]=q
 current_from_source=set(modern_ids)
 # Prepare accepted-point coordinates per component, plus optional distance support.
 candidate_roots={find(sid) for sid in cand_ids}
 needed_component_ids={sid for root in candidate_roots for sid in compmembers[root]}
 component_points=defaultdict(list)
 for sid,p in pointmap.iterrows():
  if sid not in needed_component_ids:continue
  root=find(sid);component_points[root].append((sid,(p.latitude,p.longitude),p.coordinate_source,p.source_file,p.source_row))
 proposed=[];already=[];holds=[];proof=[]
 for r in candidates.to_dict('records'):
  sid=r['target_source_record_id'];mid=r['modern_current_source_record_id'];root=find(sid); reasons=[]
  if sid in point_ids:
   p=pointmap.loc[sid]
   already.append({'target_source_record_id':sid,'census_year':int(years[sid]),'population':int(rowmap.loc[sid].population),'name':r['settlement_name'],'accepted_point_coordinate_source':p.coordinate_source,'accepted_point_source_file':p.source_file,'accepted_point_source_row':p.source_row,'disposition':'already_covered_in_fifth_point_ledger'})
   continue
  if root not in full_roots:reasons.append('candidate_not_in_a_full_2002_2010_2021_component_in_fifth_graph')
  hr=hmap.loc[sid] if sid in hmap.index else None
  if hr is None:reasons.append('raw_historical_named_point_source_row_missing')
  else:
   checks={
    'historical_named_point_candidate':bool(hr.historical_named_point_candidate) if pd.notna(hr.historical_named_point_candidate) else False,
    'historical_name_exact':bool(hr.historical_name_exact) if pd.notna(hr.historical_name_exact) else False,
    'historical_type_exact':bool(hr.historical_type_exact) if pd.notna(hr.historical_type_exact) else False,
    'historical_region_name_type_unique':pd.notna(hr.historical_key_region_name_type_count) and int(hr.historical_key_region_name_type_count)==1,
    'no_unlocated_competitor':pd.notna(hr.possible_unlocated_historical_competitor) and not bool(hr.possible_unlocated_historical_competitor),
    'historical_code_structure_compatible':bool(hr.historical_code_structure_compatible) if pd.notna(hr.historical_code_structure_compatible) else False,
    'historical_point_region_equals_target_region':str(hr.historical_point_modern_region)==str(r['region_norm']),
    'raw_2009_name_equals_target_name_key':str(hr.name_key)==str(r['settlement_name']).strip().lower() or str(hr.name_key)==str(rowmap.loc[sid].name_norm),
    'raw_2009_type_equals_target_type':str(hr.type_key_2009)==str(rowmap.loc[sid].type_norm),
    'raw_2011_type_equals_2009_type':str(hr.type_key_2011)==str(hr.type_key_2009),
    'historical_raw_point_matches_frozen_coordinate':abs(float(hr.latitude_from_lat)-float(r['latitude']))<1e-8 and abs(float(hr.longitude_from_long)-float(r['longitude']))<1e-8,
    'raw_2011_OKATO_matches_frozen_code':str(hr.historical_okato_2011_raw)==str(r['raw_historical_OKATO_2011']),
   }
   reasons += [k for k,v in checks.items() if not v]
  mr=curmap.loc[mid]; se=src_evidence[mid]
  current_checks={
   'modern_exact_name':str(mr.settlement_name)==str(r['modern_current_name']),
   'modern_exact_type':str(mr.settlement_type)==str(r['modern_current_type']),
   'modern_exact_region':str(mr.region_norm)==str(r['modern_current_region']),
   'modern_target_same_name_type_region':str(mr.name_norm)==str(rowmap.loc[sid].name_norm) and str(mr.type_norm)==str(rowmap.loc[sid].type_norm) and str(mr.region_norm)==str(rowmap.loc[sid].region_norm),
   'modern_additive_source_flag':bool(se.get('is_additive_settlement_record')) is True and bool(mr.is_additive_settlement_record),
   'modern_nonfederal_source_flag':se.get('is_federal_aggregate') is False,
   'modern_proper_settlement_scope':se.get('population_scope')=='settlement' and mr.population_scope=='settlement',
   'modern_native_oktmo_matches_frozen_literal':str(mr.oktmo)==str(r['modern_current_OKTMO_literal']),
   'modern_native_oktmo_equals_native_id':str(mr.source_native_id)==str(mr.oktmo),
   'modern_native_oktmo_unique_whole_2021':int(mr.native_oktmo_count)==1,
   'modern_selected_code_class_source_publication_pinned':str(mr.source_file)==str(r['modern_source_file']) and int(mr.source_row)==int(r['modern_source_row']),
   'modern_source_evidence_id_matches':se.get('source_record_id')==mid and int(se.get('census_year',0))==2021,
  }
  reasons += [k for k,v in current_checks.items() if not v]
  q=quarantine.get(sid) or quarantine.get(mid)
  qreason=None; qdistance=None
  if q:
   qdist=q.get('current_QID_code_and_class_evidence',{}).get('historic_classifier_point_distance_to_P625_km')
   qdistance=float(qdist) if qdist is not None else None
   qreason=q.get('rule_status')
   if qreason=='hold_true_historic_vs_current_point_conflict':reasons.append('quarantine_true_historic_vs_current_point_conflict')
  # Compare against independently accepted point(s) already attached to this component.
  dists=[]
  for other,xy,coord_source,srcfile,srcrow in component_points.get(root,[]):
   km=distance_km((r['latitude'],r['longitude']),xy)
   if km is not None:dists.append((km,other,coord_source,srcfile,srcrow))
  nearest=min(dists,key=lambda x:x[0]) if dists else None
  spatial_status='no_accepted_point_in_component_to_compare'
  if nearest:
   if nearest[0]<=5: spatial_status='congruent_with_accepted_component_point_le_5km'
   elif nearest[0]>20: spatial_status='conflict_with_accepted_component_point_gt_20km';reasons.append('candidate_point_gt_20km_from_existing_accepted_component_point')
   else: spatial_status='5_to_20km_spatial_review_band'
  # Do not require P625 if current exact source/native OKTMO and already accepted identity component are clear.
  proof.append({'target_source_record_id':sid,'modern_current_source_record_id':mid,'historical_raw_check_results_json':json.dumps(checks if hr is not None else {},ensure_ascii=False,sort_keys=True),'modern_source_check_results_json':json.dumps(current_checks,ensure_ascii=False,sort_keys=True),'existing_component_contains_reviewed_same_place_candidate_edge':root in alias_roots,'existing_accepted_point_in_component_count':len(component_points.get(root,[])),'nearest_accepted_component_point_distance_km':round(nearest[0],3) if nearest else None,'nearest_accepted_component_point_source_record_id':nearest[1] if nearest else None,'nearest_accepted_component_point_origin':nearest[2] if nearest else None,'candidate_vs_current_P625_conflict_km_from_quarantine':qdistance,'quarantine_rule_status':qreason,'spatial_congruence_status':spatial_status,'provider_identifier_binding_asserted':False})
  projected=dict(r)
  projected.update({'fifth_base_component_size':len(compmembers[root]),'fifth_base_full_three_year_component':root in full_roots,'component_has_accepted_same_place_candidate_alias':root in alias_roots,'source_witness_validation':'passed' if not reasons else 'held','hold_reasons':';'.join(reasons),'spatial_congruence_status':spatial_status,'nearest_accepted_component_point_distance_km':round(nearest[0],3) if nearest else None,'quarantine_rule_status':qreason,'candidate_vs_current_P625_conflict_km_from_quarantine':qdistance,'new_point_admission_status':None,'candidate_only':True})
  if reasons:holds.append(projected)
  else:proposed.append(projected)
 # Disjoint populations: every proposal target is an unpointed member of a current full component.
 pframe=pd.DataFrame(proposed);hframe=pd.DataFrame(holds);aframe=pd.DataFrame(already);prframe=pd.DataFrame(proof)
 pframe.to_csv(a.output/'projected_point_candidates.csv',index=False)
 hframe.to_csv(a.output/'disjoint_holds.csv',index=False)
 aframe.to_csv(a.output/'already_covered_targets.csv',index=False)
 prframe.to_csv(a.output/'source_congruence_audit.csv',index=False)
 # Package the independently staged event/status trajectory files separately and byte-preserved.
 hist_out=a.output/'typed_city_history_review';hist_out.mkdir()
 for name in ['typed_transformation_candidates.csv','auxiliary_official_population_observations.csv','held_legacy_event_candidates.csv','receipt.json']:
  shutil.copyfile(TYPED_DIR/name,hist_out/name)
 cov_joint={str(x['year']):x['axes']['joint_admitted_coordinate_and_full_chain'] for x in basecov['census_metrics']}
 gain=[]
 for y in (2002,2010,2021):
  z=pframe[pframe.census_year.eq(y)] if len(pframe) else pframe
  gain.append({'year':y,'eligible_candidate_rows':len(z),'predicted_new_joint_population_gain':int(z.population.fillna(0).sum()),'not_admitted':True})
 hold_summary=hframe.groupby('census_year').agg(rows=('target_source_record_id','size'),population=('population','sum')).reset_index().to_dict('records') if len(hframe) else []
 already_summary=aframe.groupby('census_year').agg(rows=('target_source_record_id','size'),population=('population','sum')).reset_index().to_dict('records') if len(aframe) else []
 inputs=[SEL,EVID,GRAPH,POINTS,COVERAGE,BASE_RECEIPT,OLD_CSV,OLD_RECEIPT,HIST,QUARANTINE,TYPED_DIR/'receipt.json',TYPED_DIR/'typed_transformation_candidates.csv',TYPED_DIR/'auxiliary_official_population_observations.csv',Path(__file__)]
 receipt={'status':'candidate_only_reprojected_to_fifth_accepted_base_no_new_admissions','rule':'frozen raw named typed 2011 point evidence + exact current publisher name/type/region/native unique OKTMO + current accepted full-chain component; new coordinate only',
  'same_place_candidate_relation_treatment':'All 114 relation=same_place_candidate edges in the fifth graph have canonical accepted statuses and were included in connected components as same-place links. No candidate identity edge was proposed.',
  'fifth_base_identity_graph':basecov['identity_graph'],'fifth_base_joint_coverage':cov_joint,'reproduced_fifth_base_coverage':baseline_reproduction,
  'frozen_candidates':len(candidates),'already_covered_targets':len(aframe),'source_witness_and_full_chain_holds':len(hframe),'projected_new_point_candidates':len(pframe),
  'already_covered_by_year':already_summary,'held_by_year':hold_summary,'predicted_new_joint_gain_by_year':gain,
  'dispositions':{'point_conflict_Mezhgorye':'explicit hold preserved from scoped quarantine, 22.571km old named classifier point vs current P625; not silently resolved by name/code',
                  'other_existing_physical_conflicts':'held when current quarantine explicitly marks true historic-vs-current point conflict or an already accepted component point is >20km away',
                  'no_P625_or_accepted_point_requirement':'A missing modern point alone is not a hold if source/native code congruence and accepted full-chain identity are otherwise clear.'},
  'typed_history_review_package':{'path':str(hist_out),'source_receipt_sha256':sha(TYPED_DIR/'receipt.json'),'files':{f.name:sha(f) for f in hist_out.iterdir()}},
  'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in inputs},
  'outputs':{f.relative_to(a.output).as_posix():sha(f) for f in a.output.rglob('*') if f.is_file()},
  'nonclaims':['No point or identity admissions; no population values altered.','Population gains are conditional marginals in the existing accepted full-chain graph only.','No exact measurement-date or population-boundary comparability is asserted.','Dadata/legacy provider OKATO is not treated as native OKTMO or as an automatic identity conflict.']}
 (a.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'output':str(a.output),'frozen':len(candidates),'already':len(aframe),'holds':len(hframe),'eligible':len(pframe),'gains':gain},ensure_ascii=False))
if __name__=='__main__':main()
