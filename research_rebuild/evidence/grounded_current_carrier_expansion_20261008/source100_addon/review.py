from pathlib import Path
import ast,json,collections,re
B=Path(__file__).resolve().parent.parent;OUT=Path(__file__).resolve().parent
# Hydrate pinned compact snapshots/raw source contexts once; stop before prior discovery loop.
s=(B/'discover_parish_bindings.py').read_text().split('# Blank 2010 subunit requires')[0]
s=s.replace("O=Path(__file__).parent;A=", "O=B;A=")
s=s.replace('select target_source_record_id as source_record_id,latitude,longitude,point_origin_file,point_origin_sha256,point_origin_locator from read_parquet(?)','select target_source_record_id as source_record_id,latitude,longitude,coordinate_source_record_id,source_sha256,source_locator,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind from read_parquet(?)')
exec(compile(s,str(B/'discover_parish_bindings.py'),'exec'))
paths=[(O.parent/'original_2002_population_control_residual_20261008/finalized_stage64_source100/accepted_source_observations_100_20col.csv',O.parent/'original_2002_population_control_residual_20261008/finalized_stage64_source100/accepted_source_observation_metadata_100.csv'),(O.parent/'residual_source_followup_20261008/finalized_Tver28_source_addon/accepted_Tver28_source_observations_20col.csv',O.parent/'residual_source_followup_20261008/finalized_Tver28_source_addon/accepted_Tver28_source_metadata.csv')]
new=pd.concat([pd.read_csv(q,keep_default_na=False) for q,m in paths],ignore_index=True);meta=pd.concat([pd.read_csv(m,keep_default_na=False) for q,m in paths],ignore_index=True).set_index('source_record_id').to_dict('index')
for q,m in paths:pins[str(q)]=sha(q);pins[str(m)]=sha(m)
assert len(new)==128 and not set(new.source_record_id)&set(rd)
for z in new.to_dict('records'):
 z.update(source_sheet=meta[z['source_record_id']]['source_sheet'],source_row=meta[z['source_record_id']]['source_row']);rd[z['source_record_id']]=z
uf=UnionFind(rd)
for ids in members.values():
 for i in ids[1:]:uf.union(ids[0],i)
for z in pd.read_csv(B/'accepted_identity_edge_delta.csv.gz',keep_default_na=False).to_dict('records'):uf.union(z['from_source_record_id'],z['to_source_record_id'])
for z in pd.read_csv(B/'accepted_point_use_delta.csv.gz',keep_default_na=False).to_dict('records'):p[z['target_source_record_id']]=z
for q in [B/'accepted_identity_edge_delta.csv.gz',B/'accepted_point_use_delta.csv.gz',B/'admission_receipt.json']:pins[str(q)]=sha(q)
mg=collections.defaultdict(list)
for i in rd:mg[uf.find(i)].append(i)
native=collections.defaultdict(list);cur=collections.defaultdict(list);occupied=collections.defaultdict(set)
for i,z in rd.items():
 if z['is_additive_settlement_record']:
  native[(int(z['census_year']),z['region_norm'],nm(z['settlement_name']))].append(i)
  if int(z['census_year'])==2021:cur[(z['region_norm'],nm(z['settlement_name']))].append(i)
 if i in p:occupied[(int(z['census_year']),round(float(p[i]['latitude']),7),round(float(p[i]['longitude']),7))].add(i)
def eligible(ids):
 return len(ids)==3 and {int(rd[i]['census_year']) for i in ids}=={2002,2010,2021} and all(i in p and str(rd[i]['population']) not in ['', 'nan'] for i in ids)
base={i for ids in mg.values() if eligible(ids) for i in ids}
accepted=[];held=[];candidates=[];points=[];rivals=[];witness=[];rawchecks=[]
event=set()
for q in [A/'lifecycle_round2_accepted_source_UID_credit_union.csv',O.parent/'remaining_large_lifecycle_residual_20261008/accepted_direct_event_native_credit_union.csv']:
 if q.exists():event.update(pd.read_csv(q).source_record_id);pins[str(q)]=sha(q)
for n in ['direct_inclusion_transformation_path_native_credit_union.csv','formation_path_native_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv']:
 q=O.parent/'working_full_chain_20261007'/n
 if q.exists():event.update(pd.read_csv(q).source_record_id);pins[str(q)]=sha(q)
for sid in new.sort_values('population',ascending=False).source_record_id:
 z=rd[sid];m=meta[sid];label=normalize(m['source_name_raw']);q=file(z);sh=books.setdefault(str(q),xlrd.open_workbook(str(q),on_demand=True)).sheet_by_name(str(z['source_sheet']));rn=int(z['source_row'])-1;vals=sh.row_values(rn);matched=[j for j,v in enumerate(vals) if isinstance(v,str) and normalize(v)==label];nums=[v for v in vals[min(matched)+1:] if isinstance(v,(int,float)) or isinstance(v,str) and re.fullmatch(r'\d+',v.strip())] if matched else [];passed=bool(nums and float(nums[0])==float(z['population']));rawchecks.append({'source_record_id':sid,'source_file':str(q),'source_sha256':sha(q),'source_locator':z['source_locator'],'raw_cells_json':json.dumps(vals,ensure_ascii=False),'literal_label_first_count_passed':passed});pins[str(q)]=sha(q)
 oc=oldcontext(sid);name=nm(z['settlement_name']);reason=[]
 if not name:reason.append('no literal own settlement name')
 if 'часть' in label:reason.append('explicit partial-place census source scope; whole receiver identity excluded')
 if not passed:reason.append('literal original first population count mismatch')
 matches=[i for i in cur[(z['region_norm'],name)] if i in p and oc['parish_key'] and currentcontext[i]['parish_key']==oc['parish_key'] and oc['bound_county_key'] in [currentcontext[i]['bound_county_key'],currentcontext[i]['dated_classifier_county_key']]]
 if len(matches)!=1:reason.append('no unique literal parish/county grounded current counterpart')
 record={'from_source_record_id':sid,'name':z['settlement_name'],'population':z['population'],'region':z['region_norm'],'county':z['district_raw'],'parish_key':oc['parish_key'],'matched_current_source_IDs_json':json.dumps(matches),'source_grade':m.get('source_grade','secondary_compilation_of_2002_census')}
 if reason:held.append({**record,'held_reason':'; '.join(reason)});continue
 bid=matches[0];ids=mg[uf.find(sid)]+mg[uf.find(bid)];cp=p[bid];record['to_source_record_id']=bid;candidates.append(record)
 if len({int(rd[i]['census_year']) for i in ids})!=len(ids):reason.append('existing component already contains actual 2002 source observation')
 for ri in native[(2002,z['region_norm'],name)]:
  rc=oldcontext(ri);unresolved=ri!=sid and (rc['parish_key']==oc['parish_key'] and (not rc['bound_county_key'] or rc['bound_county_key']==oc['bound_county_key']) or not rc['parish_key'] and (not county_key(rd[ri]['district_raw']) or county_key(rd[ri]['district_raw'])==oc['bound_county_key']))
  rivals.append({'target_source_record_id':sid,'rival_source_record_id':ri,'rival_name':rd[ri]['settlement_name'],'rival_type':rd[ri]['settlement_type'],'rival_parish_key':rc['parish_key'],'rival_county_key':rc['bound_county_key'],'unresolved':unresolved})
  if unresolved:reason.append('actual same-year parish or unplaced samecounty namesake unresolved')
 if any(i in event for i in ids):reason.append('published nonordinary lifecycle scope')
 for i in ids:
  if i in p and distance_km((float(p[i]['latitude']),float(p[i]['longitude'])),(float(cp['latitude']),float(cp['longitude'])))>5:reason.append('accepted ownpoint contradiction')
  if occupied[(int(rd[i]['census_year']),round(float(cp['latitude']),7),round(float(cp['longitude']),7))]-set(ids):reason.append('same-year accepted ownpoint collision')
 if reason:held.append({**record,'held_reason':'; '.join(sorted(set(reason)))});continue
 for i in ids:
  if i not in p:
   pp={**cp,'target_source_record_id':i,'coordinate_admission_status':'reviewed_extension_rule_accepted','point_use_inference':'explicit_modern_ownpoint_continuity_for_source128_parish_bound_ordinaryNP','historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False};points.append(pp);p[i]=pp;occupied[(int(rd[i]['census_year']),round(float(cp['latitude']),7),round(float(cp['longitude']),7))].add(i)
 accepted.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Literal secondary census-compilation whole NP source leaf/first count; printed parish and county match source-positive current proper NP subunit; all actual same-year native competitors including128 additions screened; accepted point/duplicate year/lifecycle contradictions excluded','admission_method':'source128_literal_printed_parish_county','source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;all_native_namesake_competitors.csv.gz','population_boundary_comparability_asserted':False});witness.append({**record,'old_context_json':json.dumps(oc,ensure_ascii=False),'current_context_json':json.dumps(currentcontext[bid],ensure_ascii=False),'component_source_ids_json':json.dumps(ids)})
 uf.union(sid,bid);mg[uf.find(sid)]=ids
final=collections.defaultdict(list)
for i in rd:final[uf.find(i)].append(i)
oldremaining=set(pd.read_csv(A/'applied_remaining_primary.csv.gz').source_record_id);gains=[]
for ids in final.values():
 if eligible(ids):
  for i in ids:
   if i not in base and (i in oldremaining or i in set(new.source_record_id)) and rd[i]['region_norm'] not in ['москва','санкт петербург','севастополь'] and not(int(rd[i]['census_year'])==2021 and rd[i]['region_norm']=='крым'):gains.append({'source_record_id':i,'census_year':rd[i]['census_year'],'population':rd[i]['population']})
for n,rows,cols in [('candidate_identity_pairs.csv.gz',candidates,['from_source_record_id']),('accepted_identity_edge_delta.csv.gz',accepted,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('held_identity_bindings.csv.gz',held,['from_source_record_id','held_reason']),('all_native_namesake_competitors.csv.gz',rivals,['target_source_record_id','rival_source_record_id']),('accepted_native_source_witnesses.csv.gz',witness,['from_source_record_id']),('actual_native_raw_source_checks.csv.gz',rawchecks,['source_record_id']),('projected_main_native_gain_UIDs.csv.gz',gains,['source_record_id','census_year','population'])]:pd.DataFrame(rows,columns=None if rows else cols).to_csv(OUT/n,index=False,compression={'method':'gzip','mtime':0})
receipt={'baseline_stage':63,'application_status':'ready_not_canonical_applied','source_observations_reviewed':len(new),'secondary_compilation_source_population':int(new.population.sum()),'accepted_edges':len(accepted),'accepted_point_uses':len(points),'held_source_bindings':len(held),'main_gain_population_by_year':{str(y):sum(float(z['population']) for z in gains if int(z['census_year'])==y) for y in [2002,2010,2021]},'held_reason_counts':dict(collections.Counter(z['held_reason'] for z in held)),'no_State_load':True,'source_alone_credit':False,'frozen1398_branch_modified':False,'input_pins':pins,'output_pins':{q.name:sha(q) for q in OUT.glob('*.csv.gz')}};(OUT/'admission_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
