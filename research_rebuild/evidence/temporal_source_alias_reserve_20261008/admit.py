from pathlib import Path
import json,sys,ast,re,collections,math
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;B=O.parent/'grounded_current_carrier_expansion_20261008';A=O.parent/'main_axis_residual_application64_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
from build_long_table import UnionFind
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');P=A/'applied_point_snapshot.parquet';C=A/'applied_component_snapshot.csv.gz';F=A/'applied_remaining_primary.csv.gz';V=O.parent/'main_axis_residual_registry_20261008/competitors/all_selected_native_competitors.parquet';G=O.parent/'temporal_after_new_current_points_20261008/resolved_candidate_geometry.parquet';c=duckdb.connect();orig=c.execute('select * from read_parquet(?)',[str(S)]).fetchdf();f=c.execute('select * from read_parquet(?)',[str(A/'applied_state_observations.parquet')]).fetchdf();p=c.execute('select * from read_parquet(?)',[str(P)]).fetchdf().fillna('').set_index('target_source_record_id').to_dict('index');gc=c.execute('select * from read_parquet(?)',[str(G)]).fetchdf().set_index('source_record_id').to_dict('index');c.close();original=orig.set_index('source_record_id');b=f.set_index('source_record_id');cs=pd.read_csv(C,keep_default_na=False).set_index('source_record_id').to_dict('index');rd=b.to_dict('index');remaining=set(pd.read_csv(F,usecols=['source_record_id']).source_record_id);pins={str(q):sha(q) for q in [S,P,C,F,V,G,A/'application_receipt.json',A/'applied_state_observations.parquet',O/'source_explicit_former_name_candidates.csv.gz',O/'candidate_receipt.json']};checks={};raw=[];books={};rawparquet={}
# Use immutable parsed source locators without replacing any native value or quality.
for col in ['source_name_raw','source_sheet','source_row']:
 b[col]=b.index.map(original[col].to_dict())
for q in [B/'actual_native_raw_source_checks.csv.gz',O.parent/'temporal_after_new_current_points_20261008/actual_native_raw_source_checks.csv.gz',B/'source100_addon/actual_native_raw_source_checks.csv.gz']:
 pins[str(q)]=sha(q)
 for z in pd.read_csv(q,keep_default_na=False).to_dict('records'):
  if 'literal_label_population_passed' in z:z['literal_label_population_passed']=str(z['literal_label_population_passed'])=='True';checks[z['source_record_id']]=z
# Reopen only new native leaf rows; prior accepted source cohorts reuse their pinned checks.
tree=ast.parse((B/'admit_temporal.py').read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['path','check']],type_ignores=[]),'original_native_leaf_source_checker','exec'))
tree=ast.parse((B/'discover_closed_geometry.py').read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['nm','ty']],type_ignores=[]),'closed_names','exec'))
uf=UnionFind(cs);mg=collections.defaultdict(list)
for i,z in cs.items():mg[z['root']].append(i)
for ids in mg.values():
 for i in ids[1:]:uf.union(ids[0],i)
mg=collections.defaultdict(list)
for i in cs:mg[uf.find(i)].append(i)
occupied=collections.defaultdict(set);native=collections.defaultdict(list)
for i,z in rd.items():
 if z['is_additive_settlement_record']:native[(int(z['census_year']),z['region_norm'],nm(z['settlement_name']))].append(i)
 if i in p:occupied[(int(z['census_year']),round(float(p[i]['latitude']),7),round(float(p[i]['longitude']),7))].add(i)
def coord(i):return float(p[i]['latitude']),float(p[i]['longitude'])
def geom(i):
 if i in p:return coord(i)
 if i in gc:return float(gc[i]['latitude']),float(gc[i]['longitude'])
 return None
event=set()
for q in [A/'lifecycle_round2_accepted_source_UID_credit_union.csv',O.parent/'main_axis_residual_application63_20261008/lifecycle_round2_accepted_source_UID_credit_union.csv',O.parent/'remaining_large_lifecycle_residual_20261008/accepted_direct_event_native_credit_union.csv']:
 if q.exists():event.update(pd.read_csv(q).source_record_id);pins[str(q)]=sha(q)
for n in ['direct_inclusion_transformation_path_native_credit_union.csv','formation_path_native_credit_union.csv','named_merger_lineage_constituents.csv','complete_territorial_scope_constituents.csv','complete_publisher_partition_members.csv']:
 q=O.parent/'working_full_chain_20261007'/n
 if q.exists():event.update(pd.read_csv(q).source_record_id);pins[str(q)]=sha(q)
cand=pd.read_csv(O/'source_explicit_former_name_candidates.csv.gz',keep_default_na=False);candidatebyold=cand.groupby('source_record_id').current_source_record_id.agg(lambda x:set(x)).to_dict();edges=[];points=[];held=[];proof=[];rivals=[];seen=set()
for z in cand.sort_values('native_population',ascending=False).to_dict('records'):
 sid,bid=z['source_record_id'],z['current_source_record_id'];pair=(sid,bid)
 if pair in seen:continue
 seen.add(pair);ar,br=uf.find(sid),uf.find(bid)
 if ar==br:held.append({**z,'held_reason':'identity already accepted in actual64 baseline'});continue
 if sid not in remaining:held.append({**z,'held_reason':'old row already credited by actual64 main axis'});continue
 ids=mg[ar]+mg[br];reason=[];cp=p[bid];cg=coord(bid);g=geom(sid)
 if len(set(int(rd[i]['census_year']) for i in ids))!=len(ids):reason.append('actual same-year component repetition')
 if any(i in event for i in ids):reason.append('published nonordinary lifecycle or territorial scope')
 if any(pd.isna(rd[i]['population']) for i in ids):reason.append('protected unknown population')
 if g is None or distance_km(g,cg)>5:reason.append('no independent positive old native-object geometry within5km; direct parish/code alternative pending')
 if any(i in p and distance_km(coord(i),cg)>5 for i in ids):reason.append('actual accepted ownpoint contradiction')
 nearaliases=[cur for cur in candidatebyold[sid] if distance_km(coord(cur),cg)<=5]
 if nearaliases!=[bid]:reason.append('multiple source-positive former-name current carriers unresolved')
 for i in ids:
  if int(rd[i]['census_year'])==2021:continue
  row=rd[i];ig=geom(i)
  for ri in native[(int(row['census_year']),row['region_norm'],nm(row['settlement_name']))]:
   rg=geom(ri);unresolved=ri!=i and (rg is not None and distance_km(rg,cg)<=5 or rg is None and (not county_key(row['district_raw']) or not county_key(rd[ri]['district_raw']) or county_key(row['district_raw'])==county_key(rd[ri]['district_raw'])))
   rivals.append({'target_source_record_id':i,'rival_source_record_id':ri,'rival_name':rd[ri]['settlement_name'],'rival_type':rd[ri]['settlement_type'],'rival_county':rd[ri]['district_raw'],'geometry_is_accepted':ri in p,'distance_to_grounded_current_km':distance_km(rg,cg) if rg else '', 'unresolved':unresolved})
   if unresolved:reason.append('actual same-year physical or unplaced county namesake unresolved')
  ca=str(row['okato']).removesuffix('.0');cb=str(rd[bid]['okato']).removesuffix('.0')
  if ca not in ['','None','nan'] and cb not in ['','None','nan'] and ca!=cb and ca+'000'!=cb and cb+'000'!=ca:reason.append('native own OKATO contradiction without dated recoding proof')
 for i in ids:
  if occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))]-set(ids):reason.append('same-year accepted ownpoint collision')
 # Source-name identity assertions require reopened literal native leaf and population.
 if not reason:
  for i in ids:
   ck=check(i)
   if not ck['literal_label_population_passed']:reason.append('original native label/count check failed')
 if reason:held.append({**z,'held_reason':'; '.join(sorted(set(reason)))});continue
 edges.append({'from_source_record_id':sid,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Literal published proper ownNP former-name field, article ownname/status/region/county +independently admitted physical currentpoint confirmedwithin1km orliteralowncode/pageID; reopened historical native wholeleaf/count; independently named oldobject geometrywithin5km; allnative same-year rivals/UFyears/acceptedpoints/events screened; explicit modern representative geography only','admission_method':'source_explicit_former_name_alias','source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;all_native_namesake_competitors.csv.gz','population_boundary_comparability_asserted':False})
 proof.append({**z,'component_source_ids_json':json.dumps(ids),'old_geometry_witness_json':json.dumps(gc.get(sid,{}),ensure_ascii=False)})
 for i in ids:
  if i not in p:
   pp={k:v for k,v in cp.items() if k not in ['source_record_id','root']};pp.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='explicit_modern_ownpoint_continuity_for_sourcepublished_former_name',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False);points.append(pp);p[i]=pp;occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))].add(i)
 uf.union(sid,bid);mg[uf.find(sid)]=ids
final=collections.defaultdict(list)
for i in cs:final[uf.find(i)].append(i)
gains=[]
for ids in final.values():
 if len(ids)==3 and {int(rd[i]['census_year']) for i in ids}=={2002,2010,2021} and all(i in p and pd.notna(rd[i]['population']) for i in ids):
  for i in ids:
   z=rd[i]
   if i in remaining and z['is_additive_settlement_record'] and z['region_norm'] not in ['москва','санкт петербург','севастополь'] and not (int(z['census_year'])==2021 and z['region_norm']=='крым'):gains.append({'source_record_id':i,'census_year':int(z['census_year']),'population':z['population']})
raw=list(checks.values())+raw
for n,x,cols in [('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('admission_holds.csv.gz',held,['source_record_id','held_reason']),('accepted_native_source_witnesses.csv.gz',proof,['source_record_id']),('actual_native_raw_source_checks.csv.gz',[x for x in raw if x['source_record_id'] in {i for z in proof for i in json.loads(z['component_source_ids_json'])}],['source_record_id']),('all_native_namesake_competitors.csv.gz',rivals,['target_source_record_id','rival_source_record_id']),('projected_main_native_gain_UIDs.csv.gz',gains,['source_record_id','census_year','population'])]:pd.DataFrame(x,columns=None if x else cols).to_csv(O/n,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':64,'status':'ready_not_canonical_applied','accepted_edges':len(edges),'accepted_points':len(points),'held_pairs':len(held),'main_native_population_gain_by_year':{str(y):sum(float(z['population']) for z in gains if z['census_year']==y) for y in [2002,2010,2021]},'main_native_UID_gain_by_year':{str(y):sum(z['census_year']==y for z in gains) for y in [2002,2010,2021]},'held_reason_counts':dict(collections.Counter(z['held_reason'] for z in held)),'candidate_only_geometry_not_historical_measurement':True,'no_State_load':True,'input_pins':pins,'output_pins':{q.name:sha(q) for q in O.glob('*.csv.gz')}};(O/'admission_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
