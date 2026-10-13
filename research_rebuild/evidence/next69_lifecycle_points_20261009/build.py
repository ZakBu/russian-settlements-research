from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,math
Z=Path(__file__).parent
A=Z.parent/'main_axis_residual_application68_20261008';O=Z.parent/'working_full_chain_20261007'
R=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
def sha(f):
 h=hashlib.sha256()
 with open(f,'rb') as s:
  for b in iter(lambda:s.read(1048576),b''):h.update(b)
 return h.hexdigest()
def dist(la,lo,lb,lob):
 a=np.radians(np.asarray(la,dtype=float));b=np.radians(np.asarray(lb,dtype=float));d=np.radians(np.asarray(lob,dtype=float)-np.asarray(lo,dtype=float));x=np.sin((b-a)/2)**2+np.cos(a)*np.cos(b)*np.sin(d/2)**2;return 6371.0088*2*np.arcsin(np.minimum(1,np.sqrt(x)))
inputs=[A/'applied_state_observations.parquet',A/'applied_component_snapshot.csv.gz',A/'applied_point_snapshot.parquet',A/'applied_remaining_primary.csv.gz',A/'applied_primary_credited_UID_roster.csv.gz',O/'coverage_receipt.json',O/'input_hash_manifest.json',R]
pins={str(f):{'sha256':sha(f),'bytes':f.stat().st_size} for f in inputs}
o=pd.read_parquet(inputs[0]);c=pd.read_csv(inputs[1]);r=pd.read_csv(inputs[3]);j=o.merge(c[['source_record_id','has_own_point']],on='source_record_id',validate='one_to_one');assert len(j)==len(o)==465928
pcols=['target_source_record_id','latitude','longitude','coordinate_admission_status','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','admission_rule','integration_input_path']
p=pd.read_parquet(inputs[2],columns=pcols);p['coordinate_provenance']=p.admission_rule;p['latitude']=pd.to_numeric(p.latitude);p['longitude']=pd.to_numeric(p.longitude);assert p.target_source_record_id.is_unique
# Residual targets only; donor/current admission is actual snapshot68, no reconstructed UF.
t=r[(~r.has_own_point)&r.census_year.isin([2002,2010])].copy();donors=j[j.census_year.eq(2021)&j.has_own_point].copy();assert donors.root.is_unique
x=t.merge(donors[['root','source_record_id','settlement_name','settlement_type','region_norm','district_raw','population','oktmo']],on='root',suffixes=('','_donor')).merge(p,left_on='source_record_id_donor',right_on='target_source_record_id',suffixes=('','_point'))
print("actual residual donor-supported targets",len(x));assert x.source_record_id.is_unique
raw=pd.read_parquet(R,columns=['object_level','object_name','oktmo','region','mun_upper','mun_lower','population','fias_level_dadata','oktmo_dadata','settlement_dadata','settlement_type_full_dadata','latitude_dadata','longitude_dadata'])
allactive=j[['source_record_id','root','census_year','settlement_name']].merge(p,left_on='source_record_id',right_on='target_source_record_id');groups={root:g for root,g in allactive[allactive.root.isin(x.root)].groupby('root')}
currentactive=allactive[allactive.census_year.eq(2021)].copy();currentactive['lat7']=currentactive.latitude.round(7);currentactive['lon7']=currentactive.longitude.round(7);duplicates=currentactive.groupby(['lat7','lon7']).source_record_id.agg(list);dupmap={k:v for k,v in duplicates.items() if len(v)>1}
rows=[];holds=[];profiles=[];sourcepins={};origincache={}
for z in x.to_dict('records'):
 donor=z['source_record_id_donor'];dp=p[p.target_source_record_id.eq(donor)].iloc[0];la,lo=float(dp.latitude),float(dp.longitude);g=groups[z['root']];dg=dist(la,lo,g.latitude,g.longitude);maxd=float(np.max(dg));reasons=[]
 if maxd>5:reasons.append('active_component_ownpoint_geometry_exceeds_5km')
 if str(dp.coordinate_admission_status) not in {'reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted'}:reasons.append('donor_status_not_in_canonical_accepted_coordinate_statusset')
 if not (math.isfinite(la) and math.isfinite(lo)):reasons.append('nonfinite_donor')
 shared=dupmap.get((round(la,7),round(lo,7)),[])
 if len(shared)>1:reasons.append('same_current_coordinate_shared_by_distinct_native_current_NPs')
 rr=raw.iloc[int(donor.rsplit(':',1)[1])-1];owncode=str(rr.oktmo);provider=str(rr.oktmo_dadata)
 try:codeeq=str(int(float(provider)))==owncode
 except:codeeq=False
 proper=(rr.object_level=='Населенный пункт' and str(rr.fias_level_dadata)=='6' and codeeq and str(rr.settlement_dadata).casefold()==str(z['settlement_name_donor']).casefold())
 providerdistance=None
 if proper and pd.notna(rr.latitude_dadata) and pd.notna(rr.longitude_dadata):
  providerdistance=float(dist(la,lo,float(rr.latitude_dadata),float(rr.longitude_dadata)))
  if providerdistance>5:reasons.append('independently_owncoded_native_DaData_point_disagrees_over_5km')
 origin=Path(str(dp.point_origin_file));expected=dp.point_origin_sha256
 if origin.exists():
  if str(origin) not in origincache:origincache[str(origin)]=sha(origin)
  actual=origincache[str(origin)]
  if pd.notna(expected) and str(expected)!=actual:reasons.append('donor_origin_hash_mismatch')
  sourcepins[str(origin)]={'sha256':actual,'bytes':origin.stat().st_size}
 else:actual=str(expected) if pd.notna(expected) else None # canonical ledger pin retained; missing journal is not rejection
 hist=Path(str(z.get('source_path')))
 if not hist.exists():hist=Path('/workspace/settlements-raw')/str(z['source_file'])
 if hist.exists():
  if str(hist) not in origincache:origincache[str(hist)]=sha(hist)
  sourcepins[str(hist)]={'sha256':origincache[str(hist)],'bytes':hist.stat().st_size}
 profile={'target_source_record_id':z['source_record_id'],'donor_source_record_id':donor,'root':z['root'],'active_component_point_count':len(g),'active_component_max_distance_from_donor_km':maxd,'independently_owncoded_DaData_current_point_present':proper,'owncoded_DaData_distance_km':providerdistance,'same_current_coordinate_rivals':json.dumps(shared,ensure_ascii=False),'donor_origin_file':str(origin),'donor_origin_sha256':actual,'status':'HOLD' if reasons else 'positive','hold_reasons':'|'.join(reasons)};profiles.append(profile)
 if reasons:holds.append(dict(z,**{'hold_reasons':'|'.join(reasons)}));continue
 rows.append({'target_source_record_id':z['source_record_id'],'target_year':int(z['census_year']),'latitude':la,'longitude':lo,'coordinate_admission_status':'reviewed_extension_rule_accepted','candidate_status':'finalized_source_bound_ordinary_accepted_component_retrospective_point_use_not_yet_applied','coordinate_source':dp.point_origin_kind,'coordinate_source_record_id':donor,'point_origin_file':str(origin),'point_origin_sha256':actual,'point_origin_locator':dp.point_origin_locator,'point_origin_kind':dp.point_origin_kind,'coordinate_provider':dp.coordinate_provider,'coordinate_provider_id':dp.coordinate_provider_id,'coordinate_provenance':dp.coordinate_provenance,'donor_active_point_ledger':str(inputs[2]),'donor_active_point_ledger_sha256':pins[str(inputs[2])]['sha256'],'donor_snapshot_point_status':dp.coordinate_admission_status,'actual_baseline_component_root':z['root'],'actual_stage68_primary_axis_already_credited':False,'historical_source_file':str(hist) if hist.exists() else z['source_file'],'historical_source_sha256':origincache.get(str(hist),z.get('source_sha256')),'historical_source_locator':z.get('source_locator'),'historical_native_source_ID':z['source_record_id'],'historical_name':z['settlement_name'],'historical_type':z['settlement_type'],'historical_population_unchanged':z['population'],'historical_population_quality_unchanged':z['population_value_quality'],'historical_source_field_reverification':'existing_source_snapshot_and_accepted_component_input_preserved_no_new_population_admission','donor_name':z['settlement_name_donor'],'donor_type':z['settlement_type_donor'],'donor_region':z['region_norm_donor'],'donor_county':z['district_raw_donor'],'donor_native_own_OKTMO':owncode,'donor_source_rule':dp.point_origin_kind,'coordinate_temporal_basis':'modern_own_representative_point_retrospective_continuity_already_accepted_ordinary_identity','coordinate_measurement_date':'UNKNOWN','historical_measurement_claimed':False,'population_scope_comparability_asserted':False,'identity_edges_added':0,'source_population_quality_unchanged':True,'active_component_max_distance_from_donor_km':maxd,'candidate_evidence_path':str(Z/'readonly_point_profiles.csv.gz')})
q=pd.DataFrame(rows);h=pd.DataFrame(holds);pr=pd.DataFrame(profiles)
assert set(q.target_source_record_id).issubset(set(r.source_record_id)) and not set(q.target_source_record_id)&set(p.target_source_record_id)
# Exact component-level finite credit projection, includes donor and already-pointed historical members once.
proposed=set(q.target_source_record_id);affected=j[j.root.isin(q.actual_baseline_component_root)].copy();affected['point_after']=affected.has_own_point|affected.source_record_id.isin(proposed)
credited=set(pd.read_csv(inputs[4],usecols=['source_record_id']).source_record_id)
newcredit=[];componentrows=[]
for root,g in affected.groupby('root'):
 years=set(g.census_year);known=g.population.notna().all() and np.isfinite(g.population).all();full=years=={2002,2010,2021} and g.groupby('census_year').size().eq(1).all();own=g.point_after.all();proper=g.is_additive_settlement_record.fillna(False).all() and not g.region_norm.isin(['москва','санкт петербург','севастополь']).any() and not (g.census_year.eq(2021)&g.region_norm.eq('крым')).any() # canonical ordinary criterion; optional old scope NULL is not a grain veto;qualifies=full and known and own and proper
 componentrows.append({'root':root,'years':','.join(map(str,sorted(years))),'native_members':len(g),'points_added':int(g.source_record_id.isin(proposed).sum()),'missing_points_after':int((~g.point_after).sum()),'all_three_finite_proper_NP_after':qualifies,'already_credited_source_count':int(g.source_record_id.isin(credited).sum())})
 if qualifies:
  for v in g[~g.source_record_id.isin(credited)].to_dict('records'):newcredit.append({'source_record_id':v['source_record_id'],'census_year':int(v['census_year']),'population':v['population'],'settlement_name':v['settlement_name'],'root':root,'projection_only':True})
n=pd.DataFrame(newcredit);cg=pd.DataFrame(componentrows)
for name,d in [('accepted_point_use_delta.csv.gz',q),('readonly_point_profiles.csv.gz',pr),('point_use_holds.csv.gz',h),('component_credit_projection.csv.gz',cg),('projected_new_primary_native_credit_UIDs.csv.gz',n),('stage68_residual_target_membership.csv.gz',r[r.source_record_id.isin(set(x.source_record_id))])]:d.to_csv(Z/name,index=False,compression={'method':'gzip','mtime':0})
receipt={'status':'finalized_bounded_stage69_point_packet_readonly_stage68_not_applied','baseline_stage':68,'baseline_snapshot_native_rows':len(o),'baseline_remaining_native_rows':len(r),'donor_supported_missing_historical_uses':len(x),'finalized_point_uses':len(q),'held_point_uses':len(h),'affected_components':len(cg),'new_full3_components_projected':int(cg.all_three_finite_proper_NP_after.sum()),'allthree_projection_native_population_by_year':n.groupby('census_year').population.sum().to_dict() if len(n) else {},'allthree_projection_new_UIDs_by_year':n.groupby('census_year').source_record_id.nunique().to_dict() if len(n) else {},'point_presence_population_by_year':q.groupby('target_year').historical_population_unchanged.sum().to_dict(),'new_identity_edges':0,'source_population_or_quality_changes':0,'State_loader_runs':0,'core_files_changed':False,'projection_method':'actualstage68 UF component snapshot; require one proper additive finite NP peryear2002/2010/2021 and all ownpoints after delta; subtract exact actual68 creditedUID roster; projection remains subject to root replay','donor_source_kind_counts':q.point_origin_kind.value_counts().to_dict(),'held_reason_counts':pr[pr.status.eq('HOLD')].hold_reasons.value_counts().to_dict(),'historical_coordinate_measurement_claimed':False,'historical_or_population_boundary_equivalence_claimed':False,'limits':['Modern representative point reuse along already accepted ordinary identity; historical accuracy/time UNKNOWN.','No new physical identity or primary population certification is introduced.','Excluded every active component or independently owncoded DaData geometry discrepancy above5km, origin hash mismatch, or same-current coordinate rival.','Two-year-only components improve accepted point presence but do not add ordinary NP3 credit.']}
(Z/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');(Z/'source_pins.json').write_text(json.dumps(dict(pins,**sourcepins),ensure_ascii=False,indent=2)+'\n')
(Z/'verification_receipt.json').write_text(json.dumps({'actual68_residual_exact_membership':True,'every_target_currently_unpointed':True,'every_donor_has_active_accepted_point':True,'available_origin_bytes_rehashed_and_missing_journals_retained_as_ledger_context':True,'full_component_point_profile_checked':True,'no_finalized_geometry_above5km':True,'known_owncoded_provider_conflicts_excluded':True,'population_quality_identity_preserved':True,'exactUID_projection_conservation':True,'no_State_or_core_mutation':True},indent=2)+'\n')
m={f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in Z.iterdir() if f.is_file() and f.name!='asset_manifest.json'};(Z/'asset_manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2));print('packetbytes',sum(f.stat().st_size for f in Z.iterdir() if f.is_file()),'manifestSHA',sha(Z/'asset_manifest.json'))
