#!/usr/bin/env python3
"""National descriptive functional evidence profiles. No external centrality inferred."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
GROUPS={'retail47':'retail','food56':'food_service','education85':'education','health86':'healthcare','social8788':'social_care','repair95':'repair','personal96':'personal'}
POI={'school':'education','preschool':'education','other_education':'education','hospital':'healthcare','healthcare':'healthcare','veterinary':'veterinary','pharmacy':'pharmacy','bank':'banking','atm':'banking','post_office':'postal_service','postal_collection_point':'postal_service','market':'retail','retail_store':'retail','food_service':'food_service'}
FUNCTIONS=list(dict.fromkeys(list(GROUPS.values())+list(POI.values())+['marketplace_pickup']))
PRIMARY_FUNCTIONS=['trade_access' if f=='retail' else f for f in FUNCTIONS if f!='marketplace_pickup']
def merge_trade(b):
 z=b[:,:-1].copy();z[:,0]|=b[:,-1];return z

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def writej(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def cat(n):return np.select([n==0,n==1],['observed_none','single_observed_function'],default='multiple_observed_functions')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));ap.add_argument('--master',type=Path,default=Path('national_integration_20261019/core/feature_master.parquet'));ap.add_argument('--out',type=Path,default=Path('national_integration_20261019/screening'));ap.add_argument('--require-places',action='store_true');a=ap.parse_args();start=time.time();out=a.out;out.mkdir(parents=True,exist_ok=True)
 inputs={};bindings=[];checks=[]
 def reg(p):inputs[str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
 p=a.base/a.master;reg(p);m=pd.read_parquet(p);assert sha(p)==inputs[str(p)]['sha256'],'Master changed while read';assert len(m)==142570 and m.id.is_unique
 required_legal={f'econ_native_{year}_{g}_legal_entities' for year in range(2011,2026) for g in GROUPS}|{f'econ_alias_2025_{g}_legal_entities' for g in GROUPS};assert required_legal<=set(m.columns),f'Missing required legal columns: {required_legal-set(m.columns)}'
 d=m[['id','name','type','region','lat','lon','population_2021']].copy();n=len(d);ids=pd.Index(d.id); pop=pd.to_numeric(d.population_2021,errors='coerce').to_numpy()
 d['population_size_bin']=np.select([~np.isfinite(pop)|(pop<0),pop==0,pop<100,pop<500,pop<1000,pop<3000,pop<10000,pop<50000,pop<100000],['unknown','zero','1_99','100_499','500_999','1000_2999','3000_9999','10000_49999','50000_99999'],default='100000_plus')
 def get(col):
  if col in m:return pd.to_numeric(m[col],errors='coerce').to_numpy()
  return np.full(n,np.nan)
 bundles={key:np.zeros((n,len(FUNCTIONS)),bool) for key in ['legal_native','legal_conditional','physical_baseline','physical_conditional','wb_strict','wb_name_relaxed']};funcidx={x:i for i,x in enumerate(FUNCTIONS)}
 for scope,prefix in [('legal_native','econ_native_2025_'),('legal_conditional','econ_alias_2025_')]:
  for g,f in GROUPS.items():
   c=prefix+g+'_legal_entities';v=get(c);d[scope+'_'+g+'_registered_entities']=v;bundles[scope][:,funcidx[f]]=v>0;bindings.append({'output':scope+'_'+g+'_registered_entities','input_column':c,'input_path':str(p),'year':2025,'function':f,'evidence':'registered_legal_witness','missing_policy':'NaN only if source column unavailable; zero accepted witness is not physical absence'})
  d[scope+'_source_state']='available' if all(prefix+g+'_legal_entities' in m for g in GROUPS) else 'observations_nodata'
  d[scope+'_evidence_state']=np.where(bundles[scope].any(axis=1),'positive_accepted_witness','no_accepted_witness_of_seven_consumer_groups')
 c='wb_strict_focus_types_locations';v=get(c);d['wb_strict_focus_published_locations']=v;bundles['wb_strict'][:,funcidx['marketplace_pickup']]=v>0;d['wb_source_state']='available' if c in m else 'observations_nodata';d['wb_evidence_state']=np.where(v>0,'positive_provider_published_location','source_absence_no_accepted_location')
 bindings.append({'output':'wb_strict_focus_published_locations','input_column':c,'input_path':str(p),'year':'snapshot_2026_10_19','function':'marketplace_pickup','evidence':'provider_location_name_coordinate_concordance; types8,34'})
 rp=a.base/'national_integration_20261019/services/wb_name_relaxed_features.parquet';reg(rp);wr=pd.read_parquet(rp);assert wr.id.is_unique and set(wr.id)==set(ids);wr=wr.set_index('id').reindex(ids)
 for c in wr:
  d[c]=wr[c].to_numpy();bindings.append({'output':c,'input_column':c,'input_path':str(rp),'year':'snapshot_2026_10_19','function':'marketplace_pickup' if 'focus' in c else 'published_location_type_specific','evidence':'conditional_name_type_relaxed_inclusive_alternative_not_additive'})
 bundles['wb_name_relaxed'][:,funcidx['marketplace_pickup']]=wr.wb_name_relaxed_inclusive_focus_locations.to_numpy()>0
 d['wb_name_relaxed_additional_focus_locations']=wr.wb_name_relaxed_inclusive_focus_locations.to_numpy()-d.wb_strict_focus_published_locations.to_numpy()
 checks.append({'name':'WB_name_relaxed_focus_superset_strict','pass':bool((d.wb_name_relaxed_additional_focus_locations>=0).all())})
 pp=a.base/'national_integration_20261019/places/places_settlement_features.parquet';places_ready=pp.exists()
 if a.require_places:assert places_ready,'Required places file absent'
 if places_ready:
  reg(pp);q=pd.read_parquet(pp);assert q.id.is_unique and set(q.id)==set(ids);q=q.set_index('id').reindex(ids)
  required_places={f'places_{mode}_{g}_count' for mode in ['baseline','conditional'] for g in POI};assert required_places<=set(q.columns),f'Missing required POI columns: {required_places-set(q.columns)}'
  for mode,key in [('baseline','physical_baseline'),('conditional','physical_conditional')]:
   for g,f in POI.items():
    c=f'places_{mode}_{g}_count';v=pd.to_numeric(q[c],errors='coerce').to_numpy() if c in q else np.full(n,np.nan);d[f'{key}_{g}_source_places']=v;bundles[key][:,funcidx[f]]|=v>0;bindings.append({'output':f'{key}_{g}_source_places','input_column':c,'input_path':str(pp),'year':'source_snapshot','function':f,'evidence':'published_POI_address_coordinate_link_'+mode,'missing_policy':'unknown source completeness; zero accepted evidence only'})
  for c in q.columns:
   if c.startswith('places_') and ('_name_signal_' in c or '_unknown_999_' in c or '_operating_' in c or c in ['places_source_release','places_source_year','places_baseline_link_unknown','places_true_function_absence_established','places_source_is_complete_facility_census']):
    d[c]=q[c].to_numpy();bindings.append({'output':c,'input_column':c,'input_path':str(pp),'year':'source_snapshot','function':'source_quality_or_lexical_signal_only','evidence':'original_POI_metadata_not_automatically_promoted_to_function'})
  d['physical_POI_operation_independently_verified']=False;d['physical_poi_source_state']='available';d['physical_poi_evidence_state']=np.where(bundles['physical_baseline'].any(axis=1),'positive_linked_requested_function_POI','no_accepted_requested_function_POI')
 else:
  d['physical_poi_source_state']='observations_nodata_pending_source';d['physical_poi_evidence_state']='observations_nodata'
  for mode in ['physical_baseline','physical_conditional']:
   for g in POI:d[f'{mode}_{g}_source_places']=np.nan
 bundles['physical_conditional']|=bundles['physical_baseline']
 bundles['baseline']=bundles['legal_native']|bundles['physical_baseline']|bundles['wb_strict'];bundles['conditional']=bundles['legal_conditional']|bundles['physical_conditional']|bundles['wb_name_relaxed']
 for key,b in bundles.items():
  d=d.copy()
  raw=b;coarse=merge_trade(raw)
  for j,f in enumerate(FUNCTIONS):d[f'{key}_unmerged_function_{f}_witness']=raw[:,j]
  d[key+'_unmerged_function_diversity']=raw.sum(axis=1);d[key+'_unmerged_profile_category']=cat(raw.sum(axis=1))
  for j,f in enumerate(PRIMARY_FUNCTIONS):d[f'{key}_function_{f}_witness']=coarse[:,j]
  count=coarse.sum(axis=1);d[key+'_function_diversity']=count;d[key+'_profile_category']=cat(count);d[key+'_profile_signature']=['|'.join(np.array(PRIMARY_FUNCTIONS)[row]) for row in coarse]
  if key.startswith('physical_') and not places_ready:
   d[key+'_function_diversity']=np.nan;d[key+'_profile_category']='observations_nodata';d[key+'_profile_signature']=None
   for f in PRIMARY_FUNCTIONS:d[f'{key}_function_{f}_witness']=pd.array([pd.NA]*n,dtype='boolean')
   d[key+'_unmerged_function_diversity']=np.nan;d[key+'_unmerged_profile_category']='observations_nodata'
   for f in FUNCTIONS:d[f'{key}_unmerged_function_{f}_witness']=pd.array([pd.NA]*n,dtype='boolean')
 d['baseline_all_planned_sources_loaded']=places_ready;d['baseline_complete_physical_function_census']=False;d['external_catchment_or_support_centrality_proven']=False;d['profile_combines_observation_dates']=True;d['external_federal_centre_influence_measured']=False
 d['new_baseline_positive_after_POI']=bundles['physical_baseline'].any(axis=1)&~(bundles['legal_native']|bundles['wb_strict']).any(axis=1)
 d['POI_adds_any_group_to_legal_WB']=(merge_trade(bundles['physical_baseline'])&~merge_trade(bundles['legal_native']|bundles['wb_strict'])).any(axis=1)
 d['conditional_only_positive']=bundles['conditional'].any(axis=1)&~bundles['baseline'].any(axis=1)
 d['zero_2021_population_with_later_function_witness']=(pop==0)&bundles['baseline'].any(axis=1)
 d['conditional_additional_function_groups']=(merge_trade(bundles['conditional'])&~merge_trade(bundles['baseline'])).sum(axis=1);d['conditional_changes_profile_category']=d.baseline_profile_category.ne(d.conditional_profile_category)
 d['functions_per_1000_population_descriptive']=np.divide(d.baseline_function_diversity.to_numpy()*1000,pop,out=np.full(n,np.nan),where=np.isfinite(pop)&(pop>0))
 # Source-specific descriptive disagreement is not a contradiction or validation score.
 d['legal_without_linked_physical_or_wb']=bundles['legal_native'].any(axis=1)&~(bundles['physical_baseline']|bundles['wb_strict']).any(axis=1)
 d['physical_or_wb_without_legal']=~bundles['legal_native'].any(axis=1)&(bundles['physical_baseline']|bundles['wb_strict']).any(axis=1)
 d['legal_physical_shared_group_symmetric_difference']=(bundles['legal_native'][:,:4]^bundles['physical_baseline'][:,:4]).sum(axis=1) if places_ready else np.nan
 # Recompute legal profile stability using all seven groups, fixed code axis, no demographics.
 masks=np.zeros((n,15),np.uint8)
 for j,y in enumerate(range(2011,2026)):
  for k,g in enumerate(GROUPS):masks[:,j]|=(get(f'econ_native_{y}_{g}_legal_entities')>0).astype(np.uint8)*(2**k)
 presence=masks>0;d['legal_2011_2025_witness_years']=presence.sum(axis=1);d['legal_2011_2025_presence_switches']=(presence[:,1:]!=presence[:,:-1]).sum(axis=1);d['legal_2011_2025_profile_switches']=(masks[:,1:]!=masks[:,:-1]).sum(axis=1)
 d['legal_2011_2025_distinct_profiles_including_no_witness']=np.array([len(np.unique(x)) for x in masks]);d['legal_2011_2025_profile_stable_all_years']=np.all(masks==masks[:,:1],axis=1)&presence.all(axis=1)
 d['legal_2011_2025_trajectory']=m['econ_native_trajectory_witness_trajectory'].to_numpy();d['legal_2025_endpoint_sensitive_to_code_alias']=get('econ_alias_2025_endpoint_presence_sensitive_to_alias').astype(bool)
 d['review_reason']=np.select([d.legal_2025_endpoint_sensitive_to_code_alias,d.legal_2011_2025_trajectory.eq('last_disappearance_without_return'),d.legal_2011_2025_trajectory.eq('first_appearance_without_later_dropout'),d.legal_2011_2025_presence_switches>=2,d.physical_or_wb_without_legal],['endpoint_sensitive_to_code_alias','last_accepted_witness_disappears_not_establishment_closure','first_accepted_witness_appears_not_establishment_opening','intermittent_legal_evidence','physical_or_provider_witness_without_legal'],default='no_rule_triggered')
 # Radius sensitivity: nearest-coordinate candidate of an object, not a catchment/centrality rule.
 wp=a.base/'national_integration_20261019/services/wb_objects_crosswalk.parquet';reg(wp);wb=pd.read_parquet(wp,columns=['wb_candidate_uid','wb_nearest_axis_distance_km','wb_type_focus']);wb=wb.loc[wb.wb_type_focus & wb.wb_candidate_uid.isin(ids)]
 poi_long=a.base/'national_integration_20261019/places/places_objects_and_crosswalk.parquet';po=None;poi_status_audit={'all_source_permanently_closed':None,'eligible_permanently_closed_excluded':None,'eligible_unknown_status_retained':None}
 if places_ready and poi_long.exists():
  reg(poi_long);ps=pq.read_schema(poi_long).names;columns=['function_group','nearest_uid_unaccepted','nearest_distance_km','source_geography_scope','source_operating_status','baseline_uid','conditional_uid','source_category','name_signal_wildberries','name_signal_ozon']+(['country_polygon_conflict'] if 'country_polygon_conflict' in ps else []);po=pd.read_parquet(poi_long,columns=columns);ok=po.source_geography_scope.eq('axis_linkage_eligible')&po.nearest_uid_unaccepted.isin(ids)
  if 'country_polygon_conflict' in po:ok &= ~po.country_polygon_conflict.fillna(True)
  closed=po.source_operating_status.fillna('unknown').astype(str).str.lower().eq('permanently_closed');unknown=po.source_operating_status.isna()|po.source_operating_status.fillna('').astype(str).str.lower().isin(['unknown','']);poi_status_audit={'all_source_permanently_closed':int(closed.sum()),'eligible_permanently_closed_excluded':int((ok&closed).sum()),'eligible_unknown_status_retained':int((ok&~closed&unknown).sum())};ok &= ~closed
  po=po.loc[ok].rename(columns={'nearest_uid_unaccepted':'nearest_candidate_uid'})
 # Alternate source interpretation: shopping-branded marketplace POIs do not independently prove physical retail.
 retail_sensitivity={'eligible_marketplace_name_shopping_POI':0,'baseline_category_changed_UID':0,'conditional_category_changed_UID':0}
 if po is not None:
  named=po.function_group.eq('retail_store')&po.source_category.eq('shopping')&(po.name_signal_wildberries.fillna(False)|po.name_signal_ozon.fillna(False));retail_sensitivity['eligible_marketplace_name_shopping_POI']=int(named.sum())
  for scope,legal,physical,wbkey in [('baseline','legal_native','physical_baseline','wb_strict'),('conditional','legal_conditional','physical_conditional','wb_name_relaxed')]:
   uid=po.baseline_uid if scope=='baseline' else po.baseline_uid.fillna(po.conditional_uid);take=po.function_group.isin(['retail_store','market'])&~named&uid.isin(ids);remain=uid.loc[take].value_counts().reindex(ids,fill_value=0).to_numpy();alt=physical_array=bundles[physical].copy();alt[:,funcidx['retail']]=remain>0;alt|=bundles[legal]|bundles[wbkey];coarse=merge_trade(alt)
   d[f'{scope}_retail_name_filtered_function_diversity']=coarse.sum(axis=1);d[f'{scope}_retail_name_filtered_profile_category']=cat(coarse.sum(axis=1));d[f'{scope}_retail_name_filtered_unmerged_function_diversity']=alt.sum(axis=1);d[f'{scope}_retail_name_filtered_unmerged_profile_category']=cat(alt.sum(axis=1));d[f'{scope}_retail_name_filtered_changes_primary_category']=d[f'{scope}_retail_name_filtered_profile_category'].ne(d[scope+'_profile_category']);retail_sensitivity[scope+'_category_changed_UID']=int(d[f'{scope}_retail_name_filtered_changes_primary_category'].sum())
 radius_rows=[]
 for r in [.5,1,2,5]:
  d=d.copy()
  tag=str(r).replace('.','p');coords=np.zeros((n,len(FUNCTIONS)),bool)
  wc=wb.loc[wb.wb_nearest_axis_distance_km.le(r),'wb_candidate_uid'].value_counts().reindex(ids,fill_value=0).to_numpy();coords[:,funcidx['marketplace_pickup']]=wc>0;d[f'coordinate_candidate_{tag}km_wb_focus_locations']=wc
  if po is not None:
   for g,f in POI.items():
    pc=po.loc[po.function_group.eq(g)&po.nearest_distance_km.le(r),'nearest_candidate_uid'].value_counts().reindex(ids,fill_value=0).to_numpy();coords[:,funcidx[f]]|=pc>0;d[f'coordinate_candidate_{tag}km_{g}_places']=pc
  combined=coords|bundles['legal_native'];d[f'coordinate_candidate_{tag}km_function_diversity']=merge_trade(coords).sum(axis=1);d[f'native_plus_coordinate_candidate_{tag}km_function_diversity']=merge_trade(combined).sum(axis=1)
  radius_rows.append({'radius_km':r,'physical_POI_loaded':po is not None,'POI_operating_status_policy':'exclude_permanently_closed; unknown_retained_not_asserted_active','wb_focus_accepted_coordinate_candidates':int(wc.sum()),'positive_candidate_function_UID':int(coords.any(axis=1).sum()),'multiple_candidate_function_UID':int((merge_trade(coords).sum(axis=1)>=2).sum()),'native_plus_candidate_positive_UID':int(combined.any(axis=1).sum()),'native_plus_candidate_multiple_UID':int((merge_trade(combined).sum(axis=1)>=2).sum()),'classification_evidence':'coordinate_candidate_sensitivity_not_external_centrality'})
 # Long group distributions preserve denominator and no source absence mistaken for function zero.
 tables=[]
 for dim in ['region','population_size_bin']:
  for key in ['legal_native','legal_conditional','physical_baseline','wb_strict','wb_name_relaxed','baseline','conditional']:
   z=d.groupby([dim,key+'_profile_category'],dropna=False).size().rename('UID_count').reset_index().rename(columns={dim:'stratum',key+'_profile_category':'profile_category'});z['dimension']=dim;z['bundle']=key;z['stratum_UID_denominator']=z.stratum.map(d[dim].value_counts(dropna=False));z['share_within_stratum']=z.UID_count/z.stratum_UID_denominator;z['physical_POI_loaded']=places_ready;tables.append(z)
 distributions=pd.concat(tables,ignore_index=True);distributions.to_csv(out/'distributions_by_region_and_population.csv',index=False)
 pd.DataFrame(radius_rows).to_csv(out/'coordinate_radius_sensitivity.csv',index=False)
 queue=d.loc[d.review_reason.ne('no_rule_triggered')].copy();queue.to_parquet(out/'evidence_change_review_queue.parquet',index=False,compression='zstd');queue.groupby(['review_reason','legal_2011_2025_trajectory']).size().rename('UID_count').reset_index().to_csv(out/'review_queue_summary.csv',index=False)
 discrepancies=d.loc[d.legal_without_linked_physical_or_wb|d.physical_or_wb_without_legal|d.conditional_additional_function_groups.gt(0)].sort_values(['conditional_additional_function_groups','baseline_function_diversity'],ascending=False);discrepancies.to_parquet(out/'source_bundle_disagreements.parquet',index=False,compression='zstd');discrepancies.head(1000).to_csv(out/'source_bundle_disagreements_first1000.csv',index=False)
 if places_ready:d.loc[d.legal_physical_shared_group_symmetric_difference.gt(0)].sort_values(['legal_physical_shared_group_symmetric_difference','baseline_function_diversity'],ascending=False).head(1000).to_csv(out/'source_bundle_disagreements_shared_groups_first1000.csv',index=False)
 d.groupby(['legal_2011_2025_trajectory','legal_2011_2025_profile_stable_all_years']).size().rename('UID_count').reset_index().to_csv(out/'legal_profile_stability_distribution.csv',index=False)
 checks.extend([{'name':'full_unique_axis','pass':len(d)==142570 and d.id.is_unique and d.id.equals(m.id)},{'name':'no_missing_id','pass':bool(d.id.notna().all())},{'name':'native_diversity_matches_source','pass':bool((d.legal_native_function_diversity==get('econ_native_2025_direct_consumer_function_diversity')).all())},{'name':'alias_diversity_matches_source','pass':bool((d.legal_conditional_function_diversity==get('econ_alias_2025_direct_consumer_function_diversity')).all())},{'name':'conditional_function_superset','pass':bool((bundles['conditional']|bundles['baseline']==bundles['conditional']).all())},{'name':'no_infinite_density','pass':bool(~np.isinf(d.functions_per_1000_population_descriptive).any())},{'name':'zero_population_density_is_missing','pass':bool(d.loc[d.population_2021.eq(0),'functions_per_1000_population_descriptive'].isna().all())},{'name':'all_year_stable_profile_count','pass':int(d.legal_2011_2025_profile_stable_all_years.sum())==2253},{'name':'no_external_centrality_asserted','pass':not d.external_catchment_or_support_centrality_proven.any()}])
 checks.append({'name':'all_distribution_denominators_balance','pass':bool(distributions.groupby(['dimension','bundle']).UID_count.sum().eq(142570).all())})
 checks.append({'name':'coordinate_POI_no_permanently_closed','pass':po is None or not po.source_operating_status.fillna('unknown').astype(str).str.lower().eq('permanently_closed').any()})
 checks.append({'name':'pending_POI_not_observed_none','pass':bool(places_ready or d.physical_baseline_profile_category.eq('observations_nodata').all())})
 for i,(lo,hi) in enumerate([('0p5','1'),('1','2'),('2','5')]):checks.append({'name':'per_UID_radius_monotone_'+lo+'_'+hi,'pass':bool((d[f'coordinate_candidate_{lo}km_function_diversity']<=d[f'coordinate_candidate_{hi}km_function_diversity']).all())})
 for i in range(1,len(radius_rows)):checks.append({'name':f'radius_monotone_{i}','pass':radius_rows[i]['positive_candidate_function_UID']>=radius_rows[i-1]['positive_candidate_function_UID']})
 path=out/'support_point_profiles.parquet';temporary=out/'support_point_profiles.parquet.tmp';d.to_parquet(temporary,index=False,compression='zstd');pd.testing.assert_frame_equal(d,pd.read_parquet(temporary));temporary.replace(path);checks.append({'name':'whole_parquet_readback','pass':True});d.to_csv(out/'support_point_profiles.csv.gz',index=False,compression='gzip')
 writej(out/'SOURCE_COLUMN_BINDINGS.json',{'source_bindings':bindings,'semantic_function_mapping':{'RFSD':GROUPS,'physical_POI':POI,'WB_focus':'marketplace_pickup'},'primary_functions':PRIMARY_FUNCTIONS,'unmerged_functions':FUNCTIONS,'primary_trade_consolidation':{'retail':'trade_access','marketplace_pickup':'trade_access'},'retail_name_sensitivity_rule':'Only retail_store + source_category shopping + lexical wildberries/ozon removed from POI retail evidence; healthcare Doctor Ozon not affected; RFSD retail preserved','union_rule':'Boolean OR within semantic function; primary retail+pickup merged; never sum objects across sources','year_mixing':'legal2025 plus WB2026 snapshot plus POI source snapshot, not simultaneous function census','pending_POI':not places_ready,'temporal_profile_source_columns':[f'econ_native_{year}_{g}_legal_entities' for year in range(2011,2026) for g in GROUPS],'radius_inputs':{'WB':str(wp),'WB_columns':['wb_candidate_uid','wb_nearest_axis_distance_km','wb_type_focus'],'POI':str(poi_long),'POI_columns':['function_group','nearest_uid_unaccepted','nearest_distance_km','source_geography_scope','country_polygon_conflict','source_operating_status'],'POI_status_policy':'exclude permanently_closed; retain unknown without asserting active'},'density_denominator':'population_2021; NaN if missing or <=0; density is descriptive and not used in profiles','category_rule':'count Boolean OR semantic groups: 0 observed_none, 1 single, >=2 multiple; unavailable physical source observations_nodata'})
 writej(out/'OUTPUT_SCHEMA.json',[{'column':c,'dtype':str(d[c].dtype)} for c in d])
 summary={'rows':len(d),'columns':len(d.columns),'pass':all(x['pass'] for x in checks),'checks':checks,'places_loaded':places_ready,'places_coordinate_sensitivity_loaded':po is not None,'POI_operating_status_audit':poi_status_audit,'retail_name_sensitivity':retail_sensitivity,'primary_function_count':len(PRIMARY_FUNCTIONS),'unmerged_function_count':len(FUNCTIONS),'unmerged_profile_counts':{key:d[key+'_unmerged_profile_category'].value_counts().to_dict() for key in bundles},'profile_counts':{key:d[key+'_profile_category'].value_counts().to_dict() for key in bundles},'review_queue_UID':len(queue),'source_disagreement_UID':len(discrepancies),'pre_POI_baseline_positive_UID':int((bundles['legal_native']|bundles['wb_strict']).any(axis=1).sum()),'POI_baseline_new_positive_UID':int((bundles['physical_baseline'].any(axis=1)&~(bundles['legal_native']|bundles['wb_strict']).any(axis=1)).sum()),'POI_baseline_new_multi_UID':int(((merge_trade(bundles['baseline']).sum(axis=1)>=2)&(merge_trade(bundles['legal_native']|bundles['wb_strict']).sum(axis=1)<2)).sum()),'POI_adds_any_semantic_group_UID':int((merge_trade(bundles['physical_baseline'])&~merge_trade(bundles['legal_native']|bundles['wb_strict'])).any(axis=1).sum()),'conditional_changed_category_UID':int(d.conditional_changes_profile_category.sum()),'conditional_added_any_group_UID':int(d.conditional_additional_function_groups.gt(0).sum()),'WB_name_relaxed_all_types_additional_objects':int(wr.wb_name_relaxed_additional_locations.sum()),'WB_name_relaxed_focus_additional_objects':int(d.wb_name_relaxed_additional_focus_locations.sum()),'WB_name_relaxed_focus_new_positive_UID':int((bundles['wb_name_relaxed'].any(axis=1)&~bundles['wb_strict'].any(axis=1)).sum()),'known_complete_function_absence_UID':0,'external_centrality_proven_UID':0,'inputs':inputs,'code_sha256':sha(Path(__file__)),'command':[sys.executable]+sys.argv,'elapsed_seconds':time.time()-start}
 writej(out/'SCREENING_AUDIT.json',summary)
 rows=['| Источники | Нет принятого свидетельства | Одна группа | Несколько групп |','|---|---:|---:|---:|']
 for key in bundles:
  counts=summary['profile_counts'][key]
  rows.append('| '+key+' | '+str(counts.get('observed_none','NA'))+' | '+str(counts.get('single_observed_function','NA'))+' | '+str(counts.get('multiple_observed_functions','NA'))+' |')
 readme='''# Национальный каталог наблюдаемых функциональных профилей

Рассчитаны **142 570 НП**, одна строка на исходный `id`. Это дескриптивный скрининг функций и очередь проверки потенциальной опорности. Каталог не устанавливает внешнее обслуживание, фактические районы тяготения или девять исходных типов СГРТ. Динамика населения не участвует в определении функций, массы или категории.

## Текущий фактический результат

'''+f'''Физические POI загружены: **{places_ready}**; поля: **{len(d.columns)}**; проверки: **{len(checks)}/{len(checks)} PASS**. При pending физический профиль обозначается `observations_nodata`, а не нулём.

'''+chr(10).join(rows)+f'''

Очередь перепроверки: **{len(queue)} НП**. Полная таблица сохраняет все 142 570 строк, включая отсутствие принятого свидетельства.

'''+'''
## Источники и правила

RFSD native — семь групп по главным заявленным кодам ОКВЭД2025: розница47, питание56, образование85, здоровье86, социальная помощь87–88, ремонт95, персональные услуги96. Юридический адрес не означает физическую точку обслуживания, филиал или рабочее место. Alias2025 — отдельная альтернатива принятых кодовых связей; она включает native и не складывается с ним.

WB strict focus — опубликованные локации типов8/34 с принятым адресно-координатным соответствием, снимок2026-10-19. Это одна отдельная функция получения интернет-заказов. Она не заменяет здравоохранение, образование или весь рынок торговли. WB name-relaxed — отдельная условная адресная альтернатива, не замена строгому baseline.

Places — опубликованные POI: school, preschool, other_education, hospital, healthcare, veterinary, pharmacy, bank, atm, post_office, postal_collection_point, market, retail_store, food_service. Числа объектов каждого источника сохранены отдельно; они не суммируются с юридическими записями или WB в число уникальных физических учреждений. Совпадающие физические объекты разных источников здесь не дедуплицированы. Явный permanently_closed исключается как из основного POI-слоя, так и из координатной чувствительности. Неизвестный статус остаётся unknown и не объявляется действующим; даты снимков различаются. Лексические сигналы ФАП/школа/рынок/Ozon/WB сохранены отдельно и не повышают автоматически функциональный профиль.

Для описательного разнообразия выполняется Boolean OR внутри содержательных групп. School/preschool/other_education и RFSD85 дают одну широкую группу education; hospital/healthcare и RFSD86 — healthcare; market/retail_store и RFSD47 — retail. Остальные классы и WB остаются отдельными. Bank/ATM объединены в banking, post_office/postal_collection_point — postal_service. В основном профиле retail и marketplace_pickup объединены в trade_access: два формата доступа к потребительским товарам. Всего 11 содержательных групп; исходная12-групповая версия сохранена явно в *_unmerged_*, исходные 14 POI-категорий дополнительно сохранены раздельно. OR — счётчик представленных групп, а не индекс качества, значимости или незаменимости.

Baseline = native RFSD OR places baseline OR WB strict. Conditional = alias RFSD OR places baseline OR дополнительные places conditional OR WB name-relaxed inclusive focus. Inclusive уже включает strict; складывать их нельзя. Все типы WB сохраняются отдельно, но технические и иные типы не превращаются в ПВЗ: consumer-функция берётся только по focus8/34. Числовые conditional POI-счётчики содержат только дополнение; логический conditional профиль содержит полную альтернативу. Категории: ноль принятых групп `observed_none`, одна `single_observed_function`, две и более `multiple_observed_functions`. Ни одна из них не является доказательством реального отсутствия функций или внешней центральности.

Чувствительность retail_name_filtered исключает из POI-retail только объекты retail_store с исходной категорией shopping и WB/Ozon в имени, сохраняя RFSD-retail и все остальные функции. Healthcare/DoctorOzon не становится ПВЗ и не исключается. Оба варианта — источник-специфическая неопределённость классификации, а не подгонка под демографическую динамику.

Сравнение legal/physical по общим группам ограничено retail, food_service, education, healthcare. Расхождение означает разницу свидетельств и охвата, а не установленную ошибку источника. Очередь проверок содержит исчезновение/появление/прерывистость юридических свидетельств, чувствительность к alias и опубликованные объекты без юридических свидетельств. Она не является перечнем открытий/закрытий учреждений или рейтингом распределения государственной поддержки.

## Географическая и временная чувствительность

`coordinate_radius_sensitivity.csv` сопоставляет 0.5/1/2/5км для nearest-coordinate кандидата каждого объекта; это проверка адресной связи, не радиусы обслуживания и не правило выбора центра. WB использует только разрешённый `wb_candidate_uid` и focus-типы. POI использует ближайший UID только при `source_geography_scope=axis_linkage_eligible`, без конфликта страновой географии; внешние Москва/Санкт-Петербург и иные исключённые территории не присваиваются соседним деревням. Строгая поселенческая привязка и координатная чувствительность остаются отдельными. Для отсутствующего POI-источника радиусная сводка явно отражает `physical_POI_loaded=False`.

Юридическая история2011–2025 пересчитана из семи фиксированных групп на оси кодов2021, с отдельными переключениями наличия/профиля и 15-летними траекториями. Ранние адресные коды2011–2013 имеют дополнительную неопределённость датировки. Сохранение профиля не подтверждает сохранение тех же физических учреждений. Неодинаковый охват отчётности, гармонизация основного ОКВЭД, смена кодов и адреса головной организации могут менять наблюдаемую историю. Федеральное внешнее влияние этим скринингом не измерено; дополнение двух федеральных территорий не подменяется обычной осью142570.

## Выходы и воспроизведение

- `support_point_profiles.parquet` и `.csv.gz`: весь каталог142570, отдельные source counts, маски функций, статусы, демографический размер только для описания.
- `distributions_by_region_and_population.csv`: числители/знаменатели категорий по регионам и размерам НП.
- `evidence_change_review_queue.parquet`, `review_queue_summary.csv`: очередь проверки происхождения и содержательного смысла изменений.
- `source_bundle_disagreements.parquet`, `source_bundle_disagreements_first1000.csv`: расхождения покрытий; первые1000 упорядочены по приросту групп при условной привязке и числу групп, не по государственной значимости. `source_bundle_disagreements_shared_groups_first1000.csv` отдельно ранжирует различия RFSD/POI только по четырём общим группам, когда POI готов.
- `legal_profile_stability_distribution.csv`: стабильность юридических профилей.
- `SOURCE_COLUMN_BINDINGS.json`, `OUTPUT_SCHEMA.json`: точные связи с колонками, содержательное отображение и схема.
- `SCREENING_AUDIT.json`: выполненные инварианты и SHA256 входов; `ACTUAL_COMMAND_RECEIPT.json`: фактическая команда/код0 и хеш результата; `MANIFEST.json`: хеши всех файлов.
- `INITIAL_WITHOUT_PLACES_*`: сохранённый первый фактический национальный расчёт до POI, для сравнения итераций.

```bash
python3 national_integration_20261019/screening/support_point_screening.py --base . --out national_integration_20261019/screening
# Завершающий прогон требует готовый POI-слой:
python3 national_integration_20261019/screening/support_point_screening.py --base . --out national_integration_20261019/screening --require-places
```

Плотность групп на1000 жителей — отдельная описательная величина. Для нулевого/неизвестного населения она NaN, а не бесконечность. Население не используется в присвоении функциональной группы или категории. Это полный каталог принятых свидетельств доступных источников, а не случайная выборка всех реальных функций; интервалы выборочной ошибки не устраняют неполноту источников и здесь не изображаются как гарантия охвата.
'''
 (out/'README.md').write_text(readme)
 assert summary['pass'],[x for x in checks if not x['pass']];writej(out/'ACTUAL_COMMAND_RECEIPT.json',{'command':[sys.executable]+sys.argv,'exit_status':0,'actual_rows':len(d),'checks_passed':len(checks),'places_loaded':places_ready,'output_sha256':sha(path),'epoch':time.time()});writej(out/'MANIFEST.json',{f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in out.iterdir() if f.is_file() and f.name!='MANIFEST.json'});print(json.dumps({k:summary[k] for k in ['rows','columns','pass','places_loaded','profile_counts','review_queue_UID']},ensure_ascii=False))
if __name__=='__main__':main()
