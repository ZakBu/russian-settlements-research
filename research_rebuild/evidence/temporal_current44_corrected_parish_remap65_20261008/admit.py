from pathlib import Path
AL=Path('/workspace/russian-settlements-research/research_rebuild/evidence/temporal_source_alias_reserve_20261008');OUT=Path(__file__).parent
s=(AL/'admit.py').read_text().split("cand=pd.read_csv(O/'source_explicit")[0].replace('O=Path(__file__).parent;B=', 'O=AL;B=');exec(compile(s,str(AL/'admit.py'),'exec'))
for folder,ef,pf in [(AL,'accepted_identity_edge_delta.csv.gz','accepted_point_use_delta.csv.gz')]:
 for q in [folder/ef,folder/pf,folder/'admission_receipt.json']:pins[str(q)]=sha(q)
 for z in pd.read_csv(folder/ef).to_dict('records'):uf.union(z['from_source_record_id'],z['to_source_record_id'])
 for z in pd.read_csv(folder/pf,keep_default_na=False).to_dict('records'):p[z['target_source_record_id']]=z
for q in [O.parent/'current_cached_ownarticle_residual_expansion_20261008/accepted_point_use_delta.csv.gz',O.parent/'temporal_current_carrier_addon65_20261008/accepted_point_use_delta.csv.gz']:
 pins[str(q)]=sha(q)
 for z in pd.read_csv(q,keep_default_na=False).to_dict('records'):p[z['target_source_record_id']]=z
Q=O.parent/'main_axis_residual_application65_20261008/reviewed_RCSI44_current_ownpoint_delta.csv.gz';J=Q.parent/'reviewed_RCSI44_current_point_rejections.csv.gz';pins[str(Q)]=sha(Q);pins[str(J)]=sha(J);pins[str(Q.parent/'RCSI44_reviewed_carrier_receipt.json')]=sha(Q.parent/'RCSI44_reviewed_carrier_receipt.json');replacement=pd.read_csv(Q,keep_default_na=False).to_dict('records');oldkeys=set()
for z in replacement:
 i=z['target_source_record_id'];assert z['coordinate_admission_status']=='reviewed_rule_accepted';oldkeys.add((round(coord(i)[0],7),round(coord(i)[1],7)));p[i]=z
mg=collections.defaultdict(list)
for i in cs:mg[uf.find(i)].append(i)
occupied=collections.defaultdict(set)
for i in p:occupied[(int(rd[i]['census_year']),round(coord(i)[0],7),round(coord(i)[1],7))].add(i)
GG=O.parent/'shared_ownpoint_conflict_route_20261008/collision_groups_diagnostics.csv';pins[str(GG)]=sha(GG);currentgroup=set()
for z in pd.read_csv(GG).to_dict('records'):
 if (round(z['lat'],7),round(z['lon'],7)) in oldkeys:currentgroup.update(json.loads(z['members_json']))
HH=B/'admission_holds.csv.gz';DP=O.parent/'shared_ownpoint_conflict_route_20261008/held_254_pair_diagnostics.csv.gz';pins[str(HH)]=sha(HH);pins[str(DP)]=sha(DP);diag=pd.read_csv(DP);pairs={(x.old_source_record_id,x.current_source_record_id) for x in diag.itertuples() if x.current_source_record_id in currentgroup};h=pd.read_csv(HH,keep_default_na=False);cand=[z for z in h.to_dict('records') if (z['from_source_record_id'],z['to_source_record_id']) in pairs];assert len(cand)==88,(len(cand),len(pairs))
W=B/'parish_all_native_namesake_competitors.csv.gz';pins[str(W)]=sha(W);riv=pd.read_csv(W,keep_default_na=False);raw=[];edges=[];points=[];held=[];proof=[];candidates=[];seen=set()
for z in cand:
 sid,cur=z['from_source_record_id'],z['to_source_record_id'];pair=(sid,cur)
 if pair in seen:continue
 seen.add(pair);ar,br=uf.find(sid),uf.find(cur)
 if ar==br:held.append({**z,'held_reason':'already accepted in prepared65 union'});continue
 ids=mg[ar]+mg[br];cp=p[cur];cg=coord(cur);reason=[]
 if len({int(rd[i]['census_year']) for i in ids})!=len(ids):reason.append('actual same-year component repetition')
 if any(i in event for i in ids):reason.append('published nonordinary lifecycle or territorial scope')
 if any(pd.isna(rd[i]['population']) for i in ids):reason.append('protected unknown population')
 if any(i in p and distance_km(coord(i),cg)>5 for i in ids):reason.append('actual accepted historical ownpoint contradiction')
 for i in ids:
  if occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))]-set(ids):reason.append('same-year admitted ownpoint collision')
  if i in p and occupied[(int(rd[i]['census_year']),round(coord(i)[0],7),round(coord(i)[1],7))]-set(ids):reason.append('accepted ownpoint remains shared by other same-year record')
 # Frozen candidate positive parish binding is actual row header or three rawflanking accepted source anchors, never distant urban heading.
 old=json.loads(z['native_historical_parish_witness_json']);current=json.loads(z['native_current_parish_witness_json']);key=old['parish_key'];county=old['bound_county_key']
 if not key or key!=current['parish_key'] or not county or county not in [current['bound_county_key'],current.get('dated_classifier_county_key','')]:reason.append('frozen positive parish/county proof mismatch')
 rr=riv[riv.target_source_record_id==sid]
 if len(rr)==0:reason.append('full source-year parish rival proof missing')
 for ri in rr.to_dict('records'):
  if ri['rival_source_record_id']==sid:continue
  if ri['rival_parish_key']==key and (not county_key(ri['rival_county']) or county_key(ri['rival_county'])==county) or str(ri['rival_unresolved_samecounty'])=='True':reason.append('same-parish or unplaced county rival unresolved')
 if not reason:
  for i in ids:
   if not check(i)['literal_label_population_passed']:reason.append('literal original ownleaf/count check failed')
 if reason:held.append({**z,'held_reason':'; '.join(sorted(set(reason)))});continue
 for anchor in json.loads(old['positive_context_anchor_source_IDs_json']):
  ai,ci=anchor['source_record_id'],anchor['current_source_record_id']
  if uf.find(ai)!=uf.find(ci) or not check(ai)['literal_label_population_passed'] or not check(ci)['literal_label_population_passed']:reason.append('sourceflanking accepted anchor identity/leaf proof failed')
 if reason:held.append({**z,'held_reason':'; '.join(sorted(set(reason)))});continue
 edges.append({'from_source_record_id':sid,'to_source_record_id':cur,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'Frozen actualprinted-parish/threeflanking rawNP anchor nativebinding with independently admitted correctedcurrentownpoint; fullactualyear rivals, duplicateyears, historicalacceptedpoint conflicts andremainingpointoccupation rechecked; oldunacceptedcandidategeometry nothistoricalmeasurement or solehardblock','admission_method':'corrected44_currentpoint_positive_parish_remap','source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;frozen_full_native_parish_rivals.csv.gz','population_boundary_comparability_asserted':False});proof.append({**z,'component_source_ids_json':json.dumps(ids),'corrected_current_carrier_sourcecoordinateID':cp['coordinate_source_record_id'],'prepared_current_point_origin_file':cp['point_origin_file'],'prepared_current_point_origin_sha256':cp['point_origin_sha256'],'prepared_current_point_origin_locator':cp['point_origin_locator']})
 for i in ids:
  if i not in p:
   pp={k:v for k,v in cp.items() if k not in ['source_record_id','root']};pp.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',point_use_inference='explicit_modern_ownpoint_continuity_for_sourceparish_bound_corrected_current_carrier',historical_census_coordinate_asserted=False,modern_point_retrospective_inference=True,population_boundary_comparability_asserted=False,point_replacement_scope='new_retrospective_oldcensus_representative_use_only_noexisting_historicalclaim_replaced');points.append(pp);p[i]=pp;occupied[(int(rd[i]['census_year']),round(cg[0],7),round(cg[1],7))].add(i)
 uf.union(sid,cur);mg[uf.find(sid)]=ids
final=collections.defaultdict(list)
for i in cs:final[uf.find(i)].append(i)
gains=[]
for ids in final.values():
 if len(ids)==3 and {int(rd[i]['census_year']) for i in ids}=={2002,2010,2021} and all(i in p and pd.notna(rd[i]['population']) for i in ids):
  for i in ids:
   z=rd[i]
   if i in remaining and z['is_additive_settlement_record'] and z['region_norm'] not in ['москва','санкт петербург','севастополь'] and not (int(z['census_year'])==2021 and z['region_norm']=='крым'):gains.append({'source_record_id':i,'census_year':int(z['census_year']),'population':z['population']})
prior=set(pd.read_csv(AL/'projected_main_native_gain_UIDs.csv.gz').source_record_id);increment=[z for z in gains if z['source_record_id'] not in prior]
for n,x,cols in [('candidate_identity_pairs.csv.gz',cand,['from_source_record_id']),('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('admission_holds.csv.gz',held,['held_reason']),('accepted_native_source_witnesses.csv.gz',proof,['from_source_record_id']),('actual_native_raw_source_checks.csv.gz',[z for i,z in checks.items() if any(i in json.loads(w['component_source_ids_json']) for w in proof)],['source_record_id']),('projected_prepared65_main_native_gain_UIDs.csv.gz',gains,['source_record_id','census_year','population']),('projected_addon_incremental_main_native_gain_UIDs.csv.gz',increment,['source_record_id','census_year','population'])]:pd.DataFrame(x,columns=None if x else cols).to_csv(OUT/n,index=False,compression={'method':'gzip','mtime':0})
riv[riv.target_source_record_id.isin([z['from_source_record_id'] for z in cand])].to_csv(OUT/'frozen_full_native_parish_rivals.csv.gz',index=False,compression={'method':'gzip','mtime':0})
r={'baseline_stage':64,'status':'ready_not_canonical_applied','candidate_pairs':len(cand),'accepted_edges':len(edges),'accepted_points':len(points),'held_pairs':len(held),'historical_point_replacements':0,'current44_replacements_required_from_root_packet':str(Q),'prior_alias32_and_current13_carriers_applied_in_prepared_union':True,'combined13plus44_additional_main_population_beyond_alias32':{str(y):sum(float(z['population']) for z in increment if z['census_year']==y) for y in [2002,2010,2021]},'total_prepared65_main_population_gain_vsactual64':{str(y):sum(float(z['population']) for z in gains if z['census_year']==y) for y in [2002,2010,2021]},'held_reason_counts':dict(collections.Counter(z['held_reason'] for z in held)),'no_State_load':True,'input_pins':pins,'output_pins':{q.name:sha(q) for q in OUT.glob('*.csv.gz')}};(OUT/'admission_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
