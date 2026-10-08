from pathlib import Path
AL=Path('/workspace/russian-settlements-research/research_rebuild/evidence/temporal_source_alias_reserve_20261008');OUT=Path(__file__).parent
s=(AL/'admit.py').read_text().split("cand=pd.read_csv(O/'source_explicit")[0].replace('O=Path(__file__).parent;B=', 'O=AL;B=');exec(compile(s,str(AL/'admit.py'),'exec'))
event.add('2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:3968')
folders=[AL,O.parent/'temporal_current44_corrected_parish_remap65_20261008']
for folder in folders:
 for q in [folder/'accepted_identity_edge_delta.csv.gz',folder/'accepted_point_use_delta.csv.gz',folder/'admission_receipt.json']:pins[str(q)]=sha(q)
 for z in pd.read_csv(folder/'accepted_identity_edge_delta.csv.gz',keep_default_na=False).to_dict('records'):uf.union(z['from_source_record_id'],z['to_source_record_id'])
 for z in pd.read_csv(folder/'accepted_point_use_delta.csv.gz',keep_default_na=False).to_dict('records'):p[z['target_source_record_id']]=z
for q in [O.parent/'current_cached_ownarticle_residual_expansion_20261008/accepted_point_use_delta.csv.gz',O.parent/'temporal_current_carrier_addon65_20261008/accepted_point_use_delta.csv.gz',O.parent/'main_axis_residual_application65_20261008/reviewed_RCSI44_current_ownpoint_delta.csv.gz']:
 pins[str(q)]=sha(q)
 for z in pd.read_csv(q,keep_default_na=False).to_dict('records'):p[z['target_source_record_id']]=z
mg=collections.defaultdict(list)
for i in cs:mg[uf.find(i)].append(i)
def full3(ids):return len(ids)==3 and {int(rd[i]['census_year']) for i in ids}=={2002,2010,2021} and all(i in p and pd.notna(rd[i]['population']) for i in ids)
before={i for ids in mg.values() if full3(ids) for i in ids}
N=O.parent/'current_geographic_residual_grounding_20261008/accepted_point_use_delta.csv.gz';pins[str(N)]=sha(N);pins[str(N.parent/'final_packet_receipt.json')]=sha(N.parent/'final_packet_receipt.json');newcur=set()
for z in pd.read_csv(N,keep_default_na=False).to_dict('records'):assert z['target_source_record_id'] not in p;p[z['target_source_record_id']]=z;newcur.add(z['target_source_record_id'])
occupied=collections.defaultdict(set)
for i in p:occupied[(int(rd[i]['census_year']),round(coord(i)[0],7),round(coord(i)[1],7))].add(i)
points=[];proof=[];held=[]
for cur in sorted(newcur):
 ids=mg[uf.find(cur)]
 if not any(i not in p for i in ids):continue
 cg=coord(cur);cp=p[cur];reason=[]
 if len({int(rd[i]['census_year']) for i in ids})!=len(ids):reason.append('actual same-year repetition')
 if any(i in event for i in ids):reason.append('published nonordinary lifecycle or territorial scope')
 if any(pd.isna(rd[i]['population']) for i in ids):reason.append('protected unknown native population')
 if any(i in p and distance_km(coord(i),cg)>5 for i in ids):reason.append('actual accepted ownpoint contradiction')
 for i in ids:
  if occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))]-set(ids):reason.append('same-year accepted ownpoint collision')
 if not reason:
  for i in ids:
   if not check(i)['literal_label_population_passed']:reason.append('literal original ownleaf/count check failed')
 if reason:held.append({'current_source_record_id':cur,'component_source_ids_json':json.dumps(ids),'held_reason':'; '.join(sorted(set(reason)))});continue
 proof.append({'current_source_record_id':cur,'component_source_ids_json':json.dumps(ids),'admission_method':'already_accepted_native_identity_component_new30_carrier'})
 for i in ids:
  if i not in p:
   pp={k:v for k,v in cp.items() if k not in ['source_record_id','root']};pp.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='explicit_modern_ownpoint_continuity_through_already_accepted_identity_new30',historical_census_coordinate_asserted=False,modern_point_retrospective_inference=True,population_boundary_comparability_asserted=False);points.append(pp);p[i]=pp;occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))].add(i)
gains=[]
for ids in mg.values():
 if full3(ids):
  for i in ids:
   z=rd[i]
   if i not in before and i in remaining and z['is_additive_settlement_record'] and z['region_norm'] not in ['москва','санкт петербург','севастополь'] and not(int(z['census_year'])==2021 and z['region_norm']=='крым'):gains.append({'source_record_id':i,'census_year':int(z['census_year']),'population':z['population']})
for n,x,cols in [('accepted_identity_edge_delta.csv.gz',[],['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('admission_holds.csv.gz',held,['held_reason']),('accepted_native_source_witnesses.csv.gz',proof,['current_source_record_id']),('actual_native_raw_source_checks.csv.gz',[z for i,z in checks.items() if any(i in json.loads(w['component_source_ids_json']) for w in proof)],['source_record_id']),('projected_additional_main_native_gain_UIDs.csv.gz',gains,['source_record_id','census_year','population'])]:pd.DataFrame(x,columns=None if x else cols).to_csv(OUT/n,index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':64,'prepared65_prior_alias32_current13_retro5_corrected44_remap88':True,'current_source_carriers':30,'accepted_edges':0,'accepted_points':len(points),'accepted_identity_components_propagated':len(proof),'held_components':len(held),'no_State_load':True,'canonical_application_pending':True,'main_native_population_increment_beyond_prepared65prior':{str(y):sum(float(z['population']) for z in gains if z['census_year']==y) for y in [2002,2010,2021]},'input_pins':pins,'output_pins':{q.name:sha(q) for q in OUT.glob('*.csv.gz')}};(OUT/'admission_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
