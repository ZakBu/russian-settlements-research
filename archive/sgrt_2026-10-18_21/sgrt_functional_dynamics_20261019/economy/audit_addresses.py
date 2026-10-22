#!/usr/bin/env python3
"""Dated reported-address compatibility and conservative crosswalk sensitivity.

No coordinates are imputed or transferred. No physical function transfer is
asserted. A single INN never supplies a code alias for other organizations.
"""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd,pyarrow.parquet as pq
from build_dynamics import codes,raw_year,GROUPS,DIRECT,sha,dump,save
PIN='bde9b8b129a8be582b66de4e30ed79c9187a8515'
R=6371.0088
def distance(lat1,lon1,lat2,lon2):
 a=np.radians(lat1);b=np.radians(lat2);dl=np.radians(lon2-lon1);da=b-a
 h=np.sin(da/2)**2+np.cos(a)*np.cos(b)*np.sin(dl/2)**2
 return 2*R*np.arctan2(np.sqrt(np.clip(h,0,1)),np.sqrt(np.clip(1-h,0,1)))
def read(src):
 arrays={c:[] for c in ['inn','code','lat','lon','q','creation','dissolution']};invalid=0
 for b in pq.ParquetFile(src).iter_batches(batch_size=200000):
  d=b.to_pandas();good=d.inn.str.fullmatch(r'\d{10}',na=False);invalid+=int((~good).sum());d=d.loc[good]
  arrays['inn'].append(d.inn.astype(np.uint64).to_numpy());arrays['code'].append(pd.to_numeric(codes(d.oktmo),errors='coerce').fillna(0).astype(np.uint64).to_numpy())
  arrays['lat'].append(d.lat.to_numpy());arrays['lon'].append(d.lon.to_numpy());arrays['q'].append(d.geocoding_quality.map({'house':1,'street':2,'city':3}).fillna(0).astype(np.uint8).to_numpy())
  for field,label in [('creation_date','creation'),('dissolution_date','dissolution')]:
   v=np.asarray(d[field],dtype='datetime64[D]');arrays[label].append(np.where(np.isnat(v),np.iinfo(np.int32).min,v.astype('int64')).astype(np.int32))
 for c in arrays:arrays[c]=np.concatenate(arrays[c])
 arrays['invalid_inn_rows']=invalid;return arrays
def count_functions(point,mask,n):
 accepted=point>=0
 return np.stack([np.bincount(point[accepted&((mask&(1<<gi))>0)],minlength=n) for gi in range(len(GROUPS))],axis=1)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True);root=a.base/'functional_dynamics_20261019/economy'
 pp=a.base/'restored/extracted/research/sgrt_recovered_20261019/data/panel.parquet';p=pq.read_table(pp,columns=['id','name','region','lat','lon','population_2021','oktmo_2021']).to_pandas();n=len(p);pc=pd.to_numeric(codes(p.oktmo_2021)).astype(np.uint64);lookup=pd.Series(np.arange(n,dtype=np.int32),index=pc)
 raw={};sources={};checks=[]
 for yr in [2021,2025]:
  src=root/f'remote_address_selected/rfsd_{yr}_address_lifecycle_selected.parquet';au=json.loads((root/f'remote_address_selected/{yr}_acquisition.json').read_text());assert au['pinned_dataset_commit']==PIN and sha(src)==au['selected_file_sha256']
  raw[yr]=read(src);raw[yr]['point']=pd.Series(raw[yr]['code']).map(lookup).fillna(-1).astype(np.int32).to_numpy()
  checks.append({'check':f'unique_address_INN_{yr}','pass':len(np.unique(raw[yr]['inn']))==len(raw[yr]['inn'])})
  source5=root/f'remote_selected/rfsd_{yr}_identity_function_selected.parquet';inn5=pq.read_table(source5,columns=['inn']).to_pandas().inn;inn5=inn5[inn5.str.fullmatch(r'\d{10}',na=False)].astype(np.uint64).to_numpy()
  checks.append({'check':f'address_function_INN_order_{yr}','pass':bool(np.array_equal(inn5,raw[yr]['inn']))})
  sources[str(yr)]={'path':str(src),'sha256':sha(src),'rows':pq.ParquetFile(src).metadata.num_rows,'pinned_dataset_commit':PIN}
 x=raw[2021];y=raw[2025];common,ia,ib=np.intersect1d(x['inn'],y['inn'],assume_unique=True,return_indices=True)
 old=x['point'][ia];new=y['point'][ib];c0=x['code'][ia];c1=y['code'][ib]
 valid=(np.isfinite(x['lat'][ia])&np.isfinite(y['lat'][ib])&np.isfinite(x['lon'][ia])&np.isfinite(y['lon'][ib])&(np.abs(x['lat'][ia])<=90)&(np.abs(y['lat'][ib])<=90)&(np.abs(x['lon'][ia])<=180)&(np.abs(y['lon'][ib])<=180))
 dd=np.full(len(common),np.nan);dd[valid]=distance(x['lat'][ia][valid],x['lon'][ia][valid],y['lat'][ib][valid],y['lon'][ib][valid])
 quality=((x['q'][ia]>0)&(x['q'][ia]<=2)&(y['q'][ib]>0)&(y['q'][ib]<=2))
 exact_coordinates=valid&(x['lat'][ia]==y['lat'][ib])&(x['lon'][ia]==y['lon'][ib]);stable=valid&(dd<=.1)&quality
 code_change=(c0>0)&(c1>0)&(c0!=c1);lost=(old>=0)&(new<0);both=(old>=0)&(new>=0);same=both&(old==new)
 summary={'common_INN':len(common),'common_same_native_exact_point':int(same.sum()),'common_different_native_exact_points':int((both&~same).sum()),'native_exact2021_only':int(lost.sum()),'native_exact2025_only':int(((old<0)&(new>=0)).sum()),'neither_native_exact':int(((old<0)&(new<0)).sum()),'common_reported_code_changed_valid_both':int(code_change.sum()),'valid_reported_coordinates_both':int(valid.sum()),'house_street_both':int(quality.sum()),'exactly_equal_reported_coordinates':int(exact_coordinates.sum()),'house_street_distance_le100m':int(stable.sum()),'changed_code_stable_reported_coordinates':int((code_change&stable).sum()),'lost_native_link_stable_reported_coordinates':int((lost&stable).sum()),'declared_coordinates_not_guaranteed_physical_activity':True}
 tab=[]
 for cname,cmask in [('all_common',np.ones(len(common),dtype=bool)),('changed_valid_code',code_change),('lost_native_exact_link',lost),('different_native_exact_points',both&~same)]:
  for qname,qmask in [('any_quality',np.ones(len(common),dtype=bool)),('house_street_both',quality)]:
   sub=cmask&qmask
   for label,m in [('exact_equal',exact_coordinates),('changed_le100m',valid&~exact_coordinates&(dd<=.1)),('100m_to1km',valid&(dd>.1)&(dd<=1)),('1_to5km',valid&(dd>1)&(dd<=5)),('gt5km',valid&(dd>5)),('coordinate_missing_invalid',~valid)]:tab.append({'cohort':cname,'quality':qname,'coordinate_relation':label,'INN_count':int((sub&m).sum())})
 pd.DataFrame(tab).to_csv(a.out/'code_address_compatibility.csv',index=False)
 checks.append({'check':'coordinate_relations_partition','pass':sum(row['INN_count'] for row in tab if row['cohort']=='all_common' and row['quality']=='any_quality')==len(common)})
 checks.append({'check':'native_identity_partition','pass':summary['common_INN']==sum(summary[k] for k in ['common_same_native_exact_point','common_different_native_exact_points','native_exact2021_only','native_exact2025_only','neither_native_exact'])})
 # Dates are legal lifecycle evidence only, never physical openings/closures.
 end21=int(np.datetime64('2021-12-31','D').astype(int));end25=int(np.datetime64('2025-12-31','D').astype(int));missing=np.iinfo(np.int32).min
 is_old_only=~np.isin(x['inn'],common,assume_unique=True);is_new_only=~np.isin(y['inn'],common,assume_unique=True)
 start21=int(np.datetime64('2021-01-01','D').astype(int))
 lifecycle={'only_INN_2021':int(is_old_only.sum()),'only_INN_2025':int(is_new_only.sum()),'only2021_dissolution_known_le2025':int((is_old_only&(x['dissolution']!=missing)&(x['dissolution']<=end25)).sum()),'only2021_dissolution_known_after2021_le2025':int((is_old_only&(x['dissolution']>end21)&(x['dissolution']<=end25)).sum()),'only2021_dissolution_during2021':int((is_old_only&(x['dissolution']>=start21)&(x['dissolution']<=end21)).sum()),'only2021_dissolution_before2021':int((is_old_only&(x['dissolution']!=missing)&(x['dissolution']<start21)).sum()),'only2021_dissolution_unknown':int((is_old_only&(x['dissolution']==missing)).sum()),'only2025_creation_after2021_le2025':int((is_new_only&(y['creation']>end21)&(y['creation']<=end25)).sum()),'only2025_creation_le2021':int((is_new_only&(y['creation']!=missing)&(y['creation']<=end21)).sum()),'dates_mean_legal_registration_not_physical_service':True}
 # Dated reports compare coordinates; no coordinate is transferred between years.
 within_old=np.zeros(len(common),dtype=bool);known=old>=0
 distance_old=np.full(len(common),np.nan);distance_old[known]=distance(x['lat'][ia][known],x['lon'][ia][known],p.lat.to_numpy()[old[known]],p.lon.to_numpy()[old[known]])
 within_old[known]=np.isfinite(distance_old[known])&(distance_old[known]<=5)
 # codes() has already rejected 8-digit municipality codes; a leading zero
 # must not exclude valid settlement codes in regions01–09.
 candidates=lost&stable&(c1>0)&((c1%1000)!=0)
 # Split identities BEFORE constructing aliases: even INN training, odd INN test.
 train=candidates&(common%2==0);test=candidates&(common%2==1)
 t=pd.DataFrame({'code_2025':c1[train],'old_point':old[train],'within5km':within_old[train]})
 trainagg=t.groupby('code_2025').agg(training_INN=('old_point','size'),distinct_old_points=('old_point','nunique'),old_point=('old_point','first'),training_within5km=('within5km','sum')).reset_index()
 trainagg['training_eligible']=(trainagg.training_INN>=3)&(trainagg.distinct_old_points==1)&(trainagg.training_within5km>=3)
 learned=trainagg.loc[trainagg.training_eligible].set_index('code_2025').old_point
 testframe=pd.DataFrame({'code_2025':c1[test],'old_point':old[test]});testframe['expected_point']=testframe.code_2025.map(learned);testframe=testframe.loc[testframe.expected_point.notna()];testframe['matches']=testframe.old_point==testframe.expected_point
 testagg=testframe.groupby('code_2025').agg(heldout_INN=('matches','size'),heldout_matches=('matches','sum')).reset_index()
 aliases=trainagg.merge(testagg,on='code_2025',how='left').fillna({'heldout_INN':0,'heldout_matches':0});aliases['accepted_sensitivity_alias']=aliases.training_eligible&(aliases.heldout_INN>=1)&(aliases.heldout_INN==aliases.heldout_matches)
 aliases['reference_id']=aliases.old_point.map(pd.Series(p.id.to_numpy()));aliases.to_csv(a.out/'conditional_code_aliases.csv',index=False)
 accepted=aliases.loc[aliases.accepted_sensitivity_alias].set_index('code_2025').old_point
 summary.update({'training_candidate_codes':len(trainagg),'training_eligible_codes':int(trainagg.training_eligible.sum()),'heldout_tested_INN':len(testframe),'heldout_mismatching_INN':int((~testframe.matches).sum()),'accepted_multi_INN_conditional_aliases':len(accepted),'alias_min_train_INN':3,'alias_min_heldout_INN':1,'alias_train_test_split':'INN_even_train_odd_test','alias_distance_threshold_km':.1,'alias_reference_compatibility_km':5.,'alias_is_not_official_historical_crosswalk':True})
 # Apply only accepted multi-INN aliases, to contemporary address-compatible rows.
 point=raw_year(root/'remote_selected/rfsd_2025_identity_function_selected.parquet',p,2025,checks)
 assert np.array_equal(point['inn'],y['inn'])
 aliaspoint=pd.Series(y['code']).map(accepted).fillna(-1).astype(np.int32).to_numpy();take=(point['point']<0)&(aliaspoint>=0)&np.isin(y['q'],[1,2]);idx=np.flatnonzero(take)
 da=distance(y['lat'][idx],y['lon'][idx],p.lat.to_numpy()[aliaspoint[idx]],p.lon.to_numpy()[aliaspoint[idx]])
 take[idx]=np.isfinite(da)&(da<=5);with_alias=np.where(take,aliaspoint,point['point'])
 native=count_functions(point['point'],point['mask'],n);extra=count_functions(with_alias,point['mask'],n);df=p[['id','name','region','population_2021']].copy()
 for gi,g in enumerate(GROUPS):df[g+'_native_2025']=native[:,gi];df[g+'_conditional_alias_2025']=extra[:,gi]
 df['native_direct_diversity_2025']=(native[:,:7]>0).sum(axis=1);df['conditional_alias_direct_diversity_2025']=(extra[:,:7]>0).sum(axis=1)
 df['native_service_witness_2025']=df.native_direct_diversity_2025>0;df['conditional_alias_service_witness_2025']=df.conditional_alias_direct_diversity_2025>0
 df['endpoint_presence_sensitive_to_alias']=df.native_service_witness_2025!=df.conditional_alias_service_witness_2025
 trajectory=pq.read_table(root/'pinned_calendar/point_witness_trajectories_2011_2025.parquet',columns=['id','witness_trajectory']).to_pandas()
 df=df.merge(trajectory,on='id',validate='one_to_one')
 df.groupby(['witness_trajectory','endpoint_presence_sensitive_to_alias']).size().rename('n_settlements').reset_index().to_csv(a.out/'native_trajectory_endpoint_sensitivity.csv',index=False)
 save(df,a.out/'point_code_alias_sensitivity_2025')
 summary.update({'additional_legal_records_from_conditional_aliases':int(take.sum()),'native_points_with_service_2025':int((native[:,:7]>0).any(axis=1).sum()),'conditional_alias_points_with_service_2025':int((extra[:,:7]>0).any(axis=1).sum()),'conditional_aliases_change_no_primary_axis_or_source':True})
 summary['native_last_disappearance_label_endpoint_sensitive']=int((df.endpoint_presence_sensitive_to_alias&df.witness_trajectory.eq('last_disappearance_without_return')).sum())
 # The annual RFSD panel can include firms dissolved within the labelled year.
 # This separate filter checks compatibility with year-end legal survival,
 # without converting it to a physical-service or complete-EGRUL census.
 point21=raw_year(root/'remote_selected/rfsd_2021_identity_function_selected.parquet',p,2021,checks);assert np.array_equal(point21['inn'],x['inn'])
 yearend21=((x['creation']==missing)|(x['creation']<=end21))&((x['dissolution']==missing)|(x['dissolution']>end21))
 yearend25=((y['creation']==missing)|(y['creation']<=end25))&((y['dissolution']==missing)|(y['dissolution']>end25))
 stock_rows=[];stock_point=p[['id','name','region','population_2021']].copy()
 for label,year,where,mask,legalkeep in [('native_annual_2021',2021,point21['point'],point21['mask'],np.ones(len(x['inn']),dtype=bool)),('native_yearend_compatible_2021',2021,point21['point'],point21['mask'],yearend21),('native_annual_2025',2025,point['point'],point['mask'],np.ones(len(y['inn']),dtype=bool)),('native_yearend_compatible_2025',2025,point['point'],point['mask'],yearend25),('conditional_alias_annual_2025',2025,with_alias,point['mask'],np.ones(len(y['inn']),dtype=bool)),('conditional_alias_yearend_compatible_2025',2025,with_alias,point['mask'],yearend25)]:
  loc=np.where(legalkeep,where,-1);mat=count_functions(loc,mask,n);div=(mat[:,:7]>0).sum(axis=1)
  stock_point[label+'_direct_diversity']=div
  stock_rows.append({'mode':label,'year':year,'source_legal_records_passing_date_filter':int(legalkeep.sum()),'exact_or_conditional_linked_legal_records':int((loc>=0).sum()),'points_direct_service_witness':int((div>0).sum()),'points_ge2_direct_groups':int((div>=2).sum()),'points_ge3_direct_groups':int((div>=3).sum()),'missing_creation_date_included':int((legalkeep&((x if year==2021 else y)['creation']==missing)).sum()),'missing_dissolution_date_interpreted_not_known_to_be_closed':True})
 pd.DataFrame(stock_rows).to_csv(a.out/'annual_vs_yearend_date_sensitivity.csv',index=False);save(stock_point,a.out/'point_yearend_date_sensitivity')
 summary['date_sensitivity_is_not_full_yearend_EGRUL_census']=True
 checks.append({'check':'conditional_alias_is_superset','pass':bool((extra>=native).all())})
 checks.append({'check':'native_service_stock_reconciles_pinned_calendar','pass':summary['native_points_with_service_2025']==12097})
 checks.append({'check':'no_alias_from_single_training_INN','pass':bool((aliases.loc[aliases.accepted_sensitivity_alias].training_INN>=3).all())})
 checks.append({'check':'accepted_aliases_no_heldout_contradiction','pass':bool((aliases.loc[aliases.accepted_sensitivity_alias].heldout_matches==aliases.loc[aliases.accepted_sensitivity_alias].heldout_INN).all())})
 checks.append({'check':'yearend_native21_source_reconciliation','pass':stock_rows[0]['points_direct_service_witness']==15321})
 checks.append({'check':'yearend_date_filters_never_add_legal_records','pass':bool((stock_point.native_yearend_compatible_2021_direct_diversity<=stock_point.native_annual_2021_direct_diversity).all() and (stock_point.native_yearend_compatible_2025_direct_diversity<=stock_point.native_annual_2025_direct_diversity).all())})
 dump(a.out/'LIFECYCLE.json',lifecycle);dump(a.out/'ADDRESS_AUDIT.json',{'summary':summary,'checks':checks,'pass':all(c['pass'] for c in checks),'sources':sources,'code_sha256':sha(Path(__file__)),'helper_sha256':sha(Path(__file__).with_name('build_dynamics.py')),'pinned_dataset_commit':PIN})
 assert all(c['pass'] for c in checks)
 dump(a.out/'MANIFEST.json',{f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in a.out.iterdir() if f.is_file() and f.name!='MANIFEST.json'})
 print(json.dumps({'summary':summary,'lifecycle':lifecycle,'checks':len(checks),'pass':True},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
