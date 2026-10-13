from pathlib import Path
import pandas as pd, json, hashlib, zipfile, re, unicodedata, math
E=Path(__file__).resolve().parent
M=Path('/workspace/russian-settlements-research/research_rebuild/evidence/main_axis_residual_application65_20261008')
BASE=Path('/workspace/russian-settlements-research/research_rebuild/evidence/main_axis_residual_application64_20261008')
LEDGER=Path('/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet')
NAT=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
GNZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def norm(s): return re.sub(r'[^a-zа-я0-9]+',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).strip()
def dist(a,b):
 la1,lo1,la2,lo2=map(math.radians,[a[0],a[1],b[0],b[1]]);h=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
 return 6371.0088*2*math.asin(math.sqrt(min(1,h)))
claims=pd.read_parquet(M/'RCSI44_actual64_active_component_point_claims.parquet')
assert len(claims)==44 and claims.target_source_record_id.is_unique
native=pd.read_parquet(M/'RCSI44_actual64_native_component_observations.parquet')
prop=pd.read_csv(M/'RCSI44_root_authorized_sourcepositive_proposals_not_applied.csv.gz')
gnproof=pd.read_csv(E/'RCSI_GN_corroboration_v2.csv')
prop=prop.merge(gnproof,on='target_source_record_id',validate='one_to_one')
prop=prop[(prop.eligible_within_1km_count==1)&prop.all_other_P_feature_name_rivals_gt5km].copy()
assert len(prop)==44 and set(prop.target_source_record_id)==set(claims.target_source_record_id)
# Native same-county/type/name competitor roster: all records in the actual native observation set.
allnat=pd.read_parquet(NAT,columns=['source_record_id','census_year','settlement_name','settlement_type','region_norm','district_raw','oktmo','population','latitude','longitude'])
allnat=allnat[allnat.census_year.eq(2021)].copy(); allnat['nm']=allnat.settlement_name.map(norm);allnat['ty']=allnat.settlement_type.map(norm);allnat['reg']=allnat.region_norm.map(norm);allnat['county']=allnat.district_raw.map(norm)
competitors={}
for r in prop.itertuples():
 n=native[native.source_record_id.eq(r.target_source_record_id)].iloc[0]
 rr=allnat[(allnat.nm==norm(n.settlement_name))&(allnat.ty==norm(n.settlement_type))&(allnat.reg==norm(n.region_norm))&(allnat.county==norm(n.district_raw))]
 arr=[]
 for z in rr.itertuples():
  if z.source_record_id==r.target_source_record_id: continue
  arr.append({'source_record_id':z.source_record_id,'name':z.settlement_name,'type':z.settlement_type,'oktmo':str(z.oktmo),'population':z.population,'latitude':z.latitude,'longitude':z.longitude,'distance_to_replacement_km':dist((r.new_latitude,r.new_longitude),(z.latitude,z.longitude)) if pd.notna(z.latitude) and pd.notna(z.longitude) else None})
 competitors[r.target_source_record_id]=arr
# V2 GeoNames witnesses are raw RU.txt fields with corrected indexes; locators were recorded during raw TSV scan.
# Current point claim rejection: exact active64 point ledger row and source claim retained; no historical uses in singleton components.
ledger=pd.read_parquet(LEDGER,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','provider_binding_status'])
ledger=ledger[ledger.target_source_record_id.isin(claims.target_source_record_id)]
assert len(ledger)==44 and ledger.target_source_record_id.is_unique
reject=[]
for c in claims.itertuples():
 old=ledger[ledger.target_source_record_id.eq(c.target_source_record_id)].iloc[0]
 assert abs(float(old.latitude)-float(c.latitude))<1e-10 and abs(float(old.longitude)-float(c.longitude))<1e-10
 p=prop[prop.target_source_record_id.eq(c.target_source_record_id)].iloc[0]
 reject.append({'target_source_record_id':c.target_source_record_id,'rejection_status':'reviewed_superseded_representative_point_only_candidate_not_applied','old_latitude':float(old.latitude),'old_longitude':float(old.longitude),'origin_ledger':str(LEDGER),'origin_ledger_sha256':sha(LEDGER),'old_point_origin_file':str(c.point_origin_file),'old_point_origin_sha256':str(c.point_origin_sha256),'old_point_origin_locator':str(c.point_origin_locator),'old_coordinate_source_record_id':str(old.coordinate_source_record_id),'old_coordinate_admission_status':str(old.coordinate_admission_status),'old_provider':str(old.coordinate_provider),'old_provider_id':str(old.coordinate_provider_id),'provider_identifier_binding_status':'old_DaData_identifier_not_transferred_to_RCSI_coordinate; provider binding remains distinct','active64_status':str(c.coordinate_admission_status),'point_rejection_reason':'Shared exact current-year Dadata point was also assigned to another distinct native own-OKTMO locality; this current representative coordinate is superseded by uniquely code/name/type/region/municipality-bound RCSI point plus independent GeoNames feature-class-P whole-NP exact-literal-name corroboration with full populated-place namesake rivals screened.','historical_point_uses_rejected':0,'candidate_only':True})
# Evidence enriched replacement proposals. Keep target ID as locality carrier; no external provider ID claimed for RCSI coordinate.
replace=[]
for p in prop.itertuples():
 gn=json.loads(p.near_support_json)
 replace.append({'target_source_record_id':p.target_source_record_id,'candidate_status':'source_positive_current_ownpoint_replacement_not_applied','old_latitude':p.old_latitude,'old_longitude':p.old_longitude,'new_latitude':p.new_latitude,'new_longitude':p.new_longitude,'distance_old_to_new_km':p.distance_old_to_new_km,'native_name':p.native_name,'native_type':p.native_type,'native_own_OKTMO':str(p.native_OKTMO),'native_region':p.native_region,'native_county':str(native[native.source_record_id.eq(p.target_source_record_id)].iloc[0].district_raw),'RCSI_file':p.point_origin_file,'RCSI_sha256':p.point_origin_sha256,'RCSI_locator':p.point_origin_locator,'RCSI_name':p.RCSI_name,'RCSI_type':p.RCSI_type,'RCSI_municipality':p.RCSI_municipality,'RCSI_record_id':p.RCSI_record_id,'RCSI_code_bound_exact_native_OKTMO_name_type_region_municipality':True,'GeoNames_file':str(GNZIP),'GeoNames_zip_sha256':sha(GNZIP),'GeoNames_admin1':p.gn_admin1,'GeoNames_feature_class_P':True,'GeoNames_same_region_all_populated_place_candidates_count':int(p.same_region_whole_P_candidate_count),'GeoNames_eligible_whole_NP_support_count':int(p.eligible_whole_NP_support_count),'GeoNames_within_1km_count':int(p.eligible_within_1km_count),'GeoNames_nearest_eligible_distance_km':float(p.nearest_eligible_km),'GeoNames_points_json':json.dumps(gn,ensure_ascii=False),'GeoNames_all_place_rivals_json':p.all_P_feature_name_rivals_json,'same_county_exact_name_type_native_competitors_json':json.dumps(competitors[p.target_source_record_id],ensure_ascii=False),'same_county_exact_name_type_native_competitor_count':len(competitors[p.target_source_record_id]),'replacement_provider_identifier_binding':'not asserted; RCSI coordinate source has no reused DaData provider ID','old_point_preserved_as_source_claim':True,'historical_claims_changed':False,'candidate_only':True})
rej=pd.DataFrame(reject); rep=pd.DataFrame(replace)
rej.to_csv(E/'RCSI44_actual64_current_point_rejection_delta_v2_not_applied.csv.gz',index=False,compression={'method':'gzip','mtime':0})
rep.to_csv(E/'RCSI44_actual64_source_positive_replacement_proposals_v2_not_applied.csv.gz',index=False,compression={'method':'gzip','mtime':0})
# Point ledger lookup receipt and source/outputs pins.
receipt={'status':'frozen_actual64_exact_current_point_rejection_and_source_positive_replacement_packet_candidate_only','baseline_stage':64,'application_allowed':False,'live_core_edits':False,'historical_claims_changed':False,'targets':44,'components':44,'components_singleton_2021':True,'exact_active64_coordinates_verified_against_point_ledger':44,'active64_statuses':claims.coordinate_admission_status.value_counts().to_dict(),'active_point_ledger_path':str(LEDGER),'active_point_ledger_sha256':sha(LEDGER),'rejected_current_representative_points':44,'candidate_replacements':44,'independent_RCSI_GN_supported':44,'GeoNames_feature_class_field':'column 7/index 6','GeoNames_feature_code_field':'column 8/index 7','GeoNames_country_field':'column 9/index 8','GeoNames_admin1_field':'column 11/index 10','GeoNames_positive_codes':['PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLC','PPLF','PPLG','PPLL','PPLR','PPLS'],'GeoNames_rival_codes_additionally_included':['PPLH','PPLQ','PPLW','PPLX'],'GeoNames_source_witness_indices_corrected':True,'native_same_county_exact_name_type_competitor_counts':pd.Series([len(x) for x in competitors.values()]).value_counts().to_dict(),'historical_accepted_point_uses_rejected':0,'preserved_old_native_claims':True,'provider_ID_binding_reused':False,'inputs':{},'outputs':{}}
inputs={'actual64_receipt':BASE/'application_receipt.json','actual64_point_snapshot':BASE/'applied_point_snapshot.parquet','actual64_component_snapshot':BASE/'applied_component_snapshot.csv.gz','actual64_state_observations':BASE/'applied_state_observations.parquet','point_origin_ledger':LEDGER,'actual64_claims':M/'RCSI44_actual64_active_component_point_claims.parquet','native_components':M/'RCSI44_actual64_native_component_observations.parquet','RCSI_candidates_all65':E/'proposed_RCSI_current_point_replacements_not_applied.csv.gz','GN_corroboration_v2':E/'RCSI_GN_corroboration_v2.csv','GeoNames_RU_zip':GNZIP,'native_roster':NAT}
receipt['inputs']={k:{'path':str(v),'sha256':sha(v)} for k,v in inputs.items()}
for f in [E/'RCSI44_actual64_current_point_rejection_delta_v2_not_applied.csv.gz',E/'RCSI44_actual64_source_positive_replacement_proposals_v2_not_applied.csv.gz']:
 receipt['outputs'][f.name]={'sha256':sha(f),'bytes':f.stat().st_size}
(E/'RCSI44_actual64_packet_receipt_v2.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:receipt[k] for k in ['targets','exact_active64_coordinates_verified_against_point_ledger','candidate_replacements','historical_accepted_point_uses_rejected','native_same_county_exact_name_type_competitor_counts','active_point_ledger_sha256']},ensure_ascii=False))
