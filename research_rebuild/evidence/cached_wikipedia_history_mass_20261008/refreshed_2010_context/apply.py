from pathlib import Path
import sys,json,math,collections,shutil
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load,PARTITION_MEMBERS
from current_chain_state_20261007 import normalize,distance_km,sha
O=Path(__file__).parent;A=O/'application';A.mkdir(exist_ok=True);W=Path('/workspace/settlements-work/cached_wikipedia_history_mass_20261008/refreshed_2010_context');E=O.parents[1];s=load(28);before=s.metrics();d=pd.read_csv(W/'candidates.csv',keep_default_na=False);rec=json.loads((O/'receipt.json').read_text());pins={str(p):sha(p) for p in s.inputs}
for path,digest in rec['inputs'].items():assert sha(Path(path))==digest,(path,'input pin changed');pins[path]=digest
for path,digest in rec['raw_source_hashes'].items():assert sha(Path(path))==digest;pins[path]=digest
for path,z in rec['outputs'].items():assert sha(Path(path))==z['sha256'];pins[path]=z['sha256']
current=collections.defaultdict(list);members=collections.defaultdict(list)
for x in s.obs.to_dict('records'):
 members[s.uf.find(x['source_record_id'])].append(x['source_record_id'])
 if x['census_year']==2021 and x['is_additive_settlement_record'] and x['source_record_id'] in s.point_rows:current[(normalize(x['name_norm']),normalize(x['region_norm']))].append(x)
finite_before=set()
for root,ids in members.items():
 if s.years[root]=={2002,2010,2021} and all(i in s.point_rows and pd.notna(s.by_id.loc[i,'population']) and math.isfinite(float(s.by_id.loc[i,'population'])) for i in ids):finite_before.update(ids)
credited=set(finite_before)
for p in [PARTITION_MEMBERS,E/'additional_complete_partition_application_20261007/accepted_exclusive_member_projection.csv',E/'working_full_chain_20261007/qualified_scope_source_id_credit_union.csv',E/'working_full_chain_20261007/named_merger_lineage_constituents.csv',E/'working_full_chain_20261007/complete_territorial_scope_constituents.csv']:
 if p.exists():
  pins[str(p)]=sha(p);f=pd.read_csv(p,dtype=str,keep_default_na=False)
  for c in f:
   if c=='source_record_id' or c.endswith('source_record_id'):credited.update(f[c])
occupied=collections.defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
edges=[];points=[];holds=[];applied=[];newids=set();proof=[]
for z in d.to_dict('records'):
 sid,bid=z['target_2010_source_record_id'],z['2021_endpoint_source_record_id'];a,b=s.by_id.loc[sid],s.by_id.loc[bid];cp=s.point_rows[bid];near=[]
 for x in current[(normalize(a.name_norm),normalize(a.region_norm))]:
  q=s.point_rows[x['source_record_id']]
  if distance_km((cp['latitude'],cp['longitude']),(q['latitude'],q['longitude']))<=5:near.append(x['source_record_id'])
 reason=''
 if near!=[bid]:reason='Current own-point same-name/region competitor within5km including existing full3 alternatives'
 if not reason and 'объект' in normalize(z['type_2021']):reason='Railway object grain requires explicit own populated-locality corroboration'
 ra,rb=s.uf.find(sid),s.uf.find(bid)
 if not reason and (ra==rb or s.years[ra]&s.years[rb] or s.years[ra]|s.years[rb]!={2002,2010,2021}):reason='Changed or repeated-year component'
 ids=members[ra]+members[rb]
 if not reason and any(pd.isna(s.by_id.loc[x,'population']) or not math.isfinite(float(s.by_id.loc[x,'population'])) for x in ids):reason='Unknown native population cannot be converted to finite history'
 if not reason and any(x in s.conflicting_point_targets or (x in s.point_rows and distance_km((cp['latitude'],cp['longitude']),(s.point_rows[x]['latitude'],s.point_rows[x]['longitude']))>5) for x in ids):reason='Accepted component point conflict'
 if not reason and any(x not in s.point_rows and occupied[(int(s.by_id.loc[x,'census_year']),cp['latitude'],cp['longitude'])] for x in ids):reason='New same-year point collision'
 if reason:holds.append(dict(z,hold_reason=reason,current_5km_competitors=json.dumps(near)));continue
 edge=dict(z,from_source_record_id=sid,to_source_record_id=bid,from_year=2010,to_year=2021,relation='same_place',decision_status='checked_rule_accepted',admission_rule='refreshed_two_distinct_accepted_flanking_source_anchors_with_exact_native_cells_and_unique_local_current_ownpoint_v1',current_5km_competitor_ids=json.dumps(near),source_context_interpretation='Source county inferred from existing accepted anchors; not asserted as literal printed whole-county proof',population_quality_2010=a.population_value_quality,all_current_same_name_region_competitors_checked_before_graph_filter=True,historical_current_type_change_already_on_accepted_2002_2021_identity=True,boundary_comparability_asserted=False)
 edges.append(edge);s.union(sid,bid);members[s.uf.find(sid)]=ids;applied.append(z);newids.update(ids)
 for x in ids:
  if x in s.point_rows:continue
  p=dict(cp);p.update(target_source_record_id=x,target_year=int(s.by_id.loc[x,'census_year']),coordinate_source_record_id=bid,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_origin_ledger=cp['point_ledger_path'],coordinate_origin_ledger_sha256=sha(Path(cp['point_ledger_path'])),coordinate_origin_ledger_locator='target_source_record_id='+bid,admission_rule='retrospective_own_representative_point_reuse_over_raw_source_flanking_context_native_identity',direct_historical_coordinate_measurement=False,boundary_comparability_asserted=False,native_code_binding_asserted=False,source_context_inference='two already accepted distinct-name flanking anchors within20 physical source rows; exact label/native population unchanged');p.pop('point_ledger_path',None);points.append(p);s.point_rows[x]=dict(p,point_ledger_path=str(A/'accepted_point_use_delta.csv'));occupied[(int(s.by_id.loc[x,'census_year']),p['latitude'],p['longitude'])].add(x)
 for x in ids:
  r=s.by_id.loc[x];proof.append({'source_record_id':x,'census_year':int(r.census_year),'population':r.population,'population_value_quality':r.population_value_quality,'source_file':r.source_file,'source_locator':r.source_locator,'already_in_preapplication_final_mixed_source_ID_union':x in credited,'trajectory_current_source_record_id':bid})
pd.DataFrame(edges).to_csv(A/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(A/'accepted_point_use_delta.csv',index=False);pd.DataFrame(holds).to_csv(A/'held_candidates.csv',index=False);pd.DataFrame(proof).drop_duplicates('source_record_id').to_csv(A/'exact_native_source_ID_union.csv',index=False)
for name in ['literal_source_checks.csv.gz','all_selected_competitor_county_context.csv.gz']:shutil.copy2(W/name,A/name)
pd.DataFrame(applied).to_csv(A/'accepted_source_context_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0})
after=s.metrics();net=newids-credited;netrows=[]
for x in sorted(net):
 r=s.by_id.loc[x];netrows.append({'source_record_id':x,'census_year':int(r.census_year),'population':r.population,'population_value_quality':r.population_value_quality})
f=pd.DataFrame(netrows);f.to_csv(A/'net_final_mixed_native_source_ID_union.csv',index=False)
receipt={'status':'applied_refreshed_flanking_source_context_native_2010_identity_rule','baseline_stage':28,'accepted_identity_edges':len(edges),'accepted_point_uses':len(points),'held_candidates':len(holds),'before':before,'after':after,'ordinary_joint_native_population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'final_mixed_native_union_net':{str(y):{'rows':len(g),'population':int(g.population.sum())} for y,g in f.groupby('census_year')},'raw_workbook_count':len(rec['raw_source_hashes']),'target_plus_flanking_anchors_exact_raw_label_and_native_population_checks':True,'same_name_current_ownpoints_including_existing_full3_checked_before_graph_filter':True,'population_and_quality_modified':False,'historical_point_measurement_asserted':False,'existing_points_overwritten_or_rejected':0,'boundary_comparability_asserted':False,'source_county_context_is_inference_not_literal_whole_county_proof':True,'input_hashes':pins,'outputs':{p.name:sha(p)for p in A.iterdir()if p.is_file()}}
(A/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:receipt[k]for k in ['accepted_identity_edges','accepted_point_uses','held_candidates','ordinary_joint_native_population_gain','final_mixed_native_union_net']},ensure_ascii=False))
