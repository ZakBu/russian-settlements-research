from pathlib import Path
AL=Path('/workspace/russian-settlements-research/research_rebuild/evidence/temporal_source_alias_reserve_20261008');OUT=Path(__file__).parent
s=(AL/'admit.py').read_text().split("cand=pd.read_csv(O/'source_explicit")[0].replace('O=Path(__file__).parent;B=', 'O=AL;B=');exec(compile(s,str(AL/'admit.py'),'exec'))
for q in [AL/'accepted_identity_edge_delta.csv.gz',AL/'accepted_point_use_delta.csv.gz',AL/'admission_receipt.json']:pins[str(q)]=sha(q)
for z in pd.read_csv(AL/'accepted_identity_edge_delta.csv.gz').to_dict('records'):uf.union(z['from_source_record_id'],z['to_source_record_id'])
for z in pd.read_csv(AL/'accepted_point_use_delta.csv.gz',keep_default_na=False).to_dict('records'):p[z['target_source_record_id']]=z
N=O.parent/'current_cached_ownarticle_residual_expansion_20261008/accepted_point_use_delta.csv.gz';pins[str(N)]=sha(N);ncur=set()
for z in pd.read_csv(N,keep_default_na=False).to_dict('records'):assert z['target_source_record_id'] not in p;p[z['target_source_record_id']]=z;ncur.add(z['target_source_record_id'])
mg=collections.defaultdict(list)
for i in cs:mg[uf.find(i)].append(i)
occupied=collections.defaultdict(set)
for i in p:occupied[(int(rd[i]['census_year']),round(coord(i)[0],7),round(coord(i)[1],7))].add(i)
candidate=[];held=[];edges=[];points=[];proof=[];rivals=[]
def screen(ids,cur):
 cp=p[cur];cg=coord(cur);reason=[]
 if len({int(rd[i]['census_year']) for i in ids})!=len(ids):reason.append('same-year component repetition')
 if any(i in event for i in ids):reason.append('published nonordinary lifecycle or territorial scope')
 if any(pd.isna(rd[i]['population']) for i in ids):reason.append('protected unknown population')
 if any(i in p and distance_km(coord(i),cg)>5 for i in ids):reason.append('actual accepted oldpoint contradiction')
 for i in ids:
  if occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))]-set(ids):reason.append('same-year accepted ownpoint collision')
 if not reason:
  for i in ids:
   if not check(i)['literal_label_population_passed']:reason.append('literal original ownleaf/count check failed')
 return sorted(set(reason))
def admitpoints(ids,cur):
 cp=p[cur];cg=coord(cur)
 for i in ids:
  if i not in p:
   pp={k:v for k,v in cp.items() if k not in ['source_record_id','root']};pp.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='explicit_modern_ownpoint_continuity_for_independently_new13_source_carrier',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False);points.append(pp);p[i]=pp;occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))].add(i)
# Bounded printed-parish supplement for the thirteen independently admitted carriers.
import bisect
context={};headers={}
for i,z in rd.items():
 z['source_sheet']=b.loc[i,'source_sheet'];z['source_row']=b.loc[i,'source_row']
ptree=ast.parse((B/'discover_parish_bindings.py').read_text());exec(compile(ast.Module(body=[n for n in ptree.body if isinstance(n,ast.FunctionDef) and n.name in ['parishkey','file','oldcontext']],type_ignores=[]),'literal_parish_context','exec'))
parishpat=re.compile(r'\b(?:сельсовет(?:а|ы)?|волост(?:ь|и)|сельск(?:ий|ого) округ(?:а)?|сельская администрация|сельское поселение|поселковый совет|сс)\b')
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');pins[str(RAW)]=sha(RAW);cc=duckdb.connect();rawcur=cc.execute('select row_number()over() rn,mun_lower,mun_upper from read_parquet(?)',[str(RAW)]).fetchdf().fillna('').set_index('rn');cc.close()
parishc={i:parishkey(rawcur.loc[int(i.rsplit(':',1)[1]),'mun_lower']) for i in rd if int(rd[i]['census_year'])==2021}
for cur in sorted(ncur):
 key=parishc[cur];county=county_key(rd[cur]['district_raw'])
 if not key or not county:continue
 for sid in native[(2002,rd[cur]['region_norm'],nm(rd[cur]['settlement_name']))]:
  if sid not in remaining or uf.find(sid)==uf.find(cur):continue
  oc=oldcontext(sid)
  if oc['parish_key']!=key or oc['bound_county_key']!=county:continue
  ids=mg[uf.find(sid)]+mg[uf.find(cur)];reason=screen(ids,cur)
  for ri in native[(2002,rd[cur]['region_norm'],nm(rd[cur]['settlement_name']))]:
   rc=oldcontext(ri)
   if ri!=sid and (rc['parish_key']==key and (not rc['bound_county_key'] or rc['bound_county_key']==county) or not rc['parish_key'] and (not county_key(rd[ri]['district_raw']) or county_key(rd[ri]['district_raw'])==county)):reason.append('actual same-year parish/unplaced county namesake unresolved')
  currentrivals=[ri for ri in native[(2021,rd[cur]['region_norm'],nm(rd[cur]['settlement_name']))] if parishc[ri]==key and (not county_key(rd[ri]['district_raw']) or county_key(rd[ri]['district_raw'])==county)]
  if currentrivals!=[cur]:reason.append('current parish native namesake unresolved')
  for ri in native[(2021,rd[cur]['region_norm'],nm(rd[cur]['settlement_name']))]:
   if ri!=cur and not parishc[ri] and (not county_key(rd[ri]['district_raw']) or county_key(rd[ri]['district_raw'])==county) and (ri not in p or distance_km(coord(ri),coord(cur))<=5):reason.append('unplaced current samecounty blankparish namesake unresolved')
  rec={'from_source_record_id':sid,'to_source_record_id':cur,'component_source_ids_json':json.dumps(ids),'native_historical_parish_witness_json':json.dumps(oc,ensure_ascii=False),'current_raw_parish':rawcur.loc[int(cur.rsplit(':',1)[1]),'mun_lower'],'current_raw_county':rawcur.loc[int(cur.rsplit(':',1)[1]),'mun_upper'],'current_raw_locator':cur};candidate.append(rec)
  if reason:held.append({**rec,'held_reason':'; '.join(sorted(set(reason)))});continue
  edges.append({'from_source_record_id':sid,'to_source_record_id':cur,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Literal printed2002 wholeNP name/count/parish/county +literal current native publisher parish/county and independent properNP ownarticle point; allsameyear parish/name rivals and actualpoint/UF/event contradictions excluded','admission_method':'independently_new13_printed_parish_carrier','source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz','population_boundary_comparability_asserted':False});admitpoints(ids,cur);proof.append({**rec,'admission_method':'independently_new13_printed_parish_carrier'});uf.union(sid,cur);mg[uf.find(cur)]=ids

for cur in sorted(ncur):
 ids=mg[uf.find(cur)]
 if any(i not in p for i in ids):
  reason=screen(ids,cur)
  if reason:held.append({'current_source_record_id':cur,'component_source_ids_json':json.dumps(ids),'held_reason':'; '.join(reason)})
  else:admitpoints(ids,cur);proof.append({'current_source_record_id':cur,'component_source_ids_json':json.dumps(ids),'admission_method':'already_accepted_native_identity_component'})
 for sid in native[(2002,rd[cur]['region_norm'],nm(rd[cur]['settlement_name']))]+native[(2010,rd[cur]['region_norm'],nm(rd[cur]['settlement_name']))]:
  if sid not in remaining or uf.find(sid)==uf.find(cur):continue
  g=geom(sid);cg=coord(cur)
  if g is None or distance_km(g,cg)>5:continue
  ids=mg[uf.find(sid)]+mg[uf.find(cur)];reason=screen(ids,cur)
  for i in ids:
   if int(rd[i]['census_year'])==2021:continue
   row=rd[i]
   for ri in native[(int(row['census_year']),row['region_norm'],nm(row['settlement_name']))]:
    rg=geom(ri);unresolved=ri!=i and (rg is not None and distance_km(rg,cg)<=5 or rg is None and (not county_key(row['district_raw']) or not county_key(rd[ri]['district_raw']) or county_key(row['district_raw'])==county_key(rd[ri]['district_raw'])))
    rivals.append({'target_source_record_id':i,'rival_source_record_id':ri,'rival_name':rd[ri]['settlement_name'],'rival_type':rd[ri]['settlement_type'],'unresolved':unresolved,'geometry_is_accepted':ri in p})
    if unresolved:reason.append('actual same-year physical or unplaced county namesake unresolved')
   ca=str(row['okato']).removesuffix('.0');cb=str(rd[cur]['okato']).removesuffix('.0')
   if ca not in ['','None','nan'] and cb not in ['','None','nan'] and ca!=cb and ca+'000'!=cb and cb+'000'!=ca:reason.append('native owncode contradiction without dated recoding proof')
  # Full rawcurrent competitors are checked before UF exclusion, including unplaced rows.
  for ri in native[(2021,rd[cur]['region_norm'],nm(rd[cur]['settlement_name']))]:
   if ri==cur:continue
   if ri in p and distance_km(coord(ri),cg)<=5 or ri not in p and (not county_key(rd[ri]['district_raw']) or county_key(rd[ri]['district_raw'])==county_key(rd[cur]['district_raw'])):reason.append('current ownname competitor unresolved')
  record={'from_source_record_id':sid,'to_source_record_id':cur,'old_imported_candidate_distance_km':distance_km(g,cg),'component_source_ids_json':json.dumps(ids)};candidate.append(record)
  if reason:held.append({**record,'held_reason':'; '.join(sorted(set(reason)))});continue
  edges.append({'from_source_record_id':sid,'to_source_record_id':cur,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Literal native wholeNP name/region +independently admitted newcurrent ownarticle physicalNP point +independent oldnamedNP candidatewithin5km; full rawyear physical/unplacednamesakes, codes, acceptedpoints, UFyears, publishedscope screened; native ownleaf/count reopened, modern representative explicit','admission_method':'independently_new13_named_carrier','source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;all_native_namesake_competitors.csv.gz','population_boundary_comparability_asserted':False});admitpoints(ids,cur);proof.append({**record,'old_geometry_witness_json':json.dumps(gc.get(sid,{}),ensure_ascii=False),'admission_method':'independently_new13_named_carrier'});uf.union(sid,cur);mg[uf.find(cur)]=ids
for n,x,cols in [('candidate_identity_pairs.csv.gz',candidate,['from_source_record_id']),('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('admission_holds.csv.gz',held,['held_reason']),('accepted_native_source_witnesses.csv.gz',proof,['current_source_record_id']),('all_native_namesake_competitors.csv.gz',rivals,['target_source_record_id']),('actual_native_raw_source_checks.csv.gz',[z for i,z in checks.items() if any(i in json.loads(w['component_source_ids_json']) for w in proof)],['source_record_id'])]:pd.DataFrame(x,columns=None if x else cols).to_csv(OUT/n,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':64,'new_current_source_carriers':13,'accepted_edges':len(edges),'accepted_points':len(points),'held_pairs':len(held),'status':'preparation_not_frozen_pending44_corrections','source128_added_again':False,'input_pins':pins,'output_pins':{q.name:sha(q) for q in OUT.glob('*.csv.gz')}};(OUT/'preparation_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
