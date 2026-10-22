#!/usr/bin/env python3
"""Mass integration on the frozen settlement axis; registered firms, not jobs."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.spatial import cKDTree

PIN='bde9b8b129a8be582b66de4e30ed79c9187a8515';R=6371.0088
GROUPS=['retail47','food56','education85','health86','social8788','repair95','personal96','accommodation55','finance64to66','admin84']
FIN={'line_1150':'fixed_assets','line_1600':'total_assets','line_2110':'revenue','line_2400':'net_profit'}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def codes(s):
 s=s.astype('string').str.strip();return s.where(s.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
def xyz(lat,lon):
 la=np.radians(lat);lo=np.radians(lon);return np.c_[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]
def distance(lat,lon,la2,lo2):
 a=np.radians(lat);b=np.radians(la2);h=np.sin((b-a)/2)**2+np.cos(a)*np.cos(b)*np.sin(np.radians(lo2-lon)/2)**2
 return 2*R*np.arctan2(np.sqrt(np.clip(h,0,1)),np.sqrt(np.clip(1-h,0,1)))
def register(inputs,p):
 key=str(p)
 if key not in inputs:inputs[key]={'sha256':sha(p),'bytes':p.stat().st_size}

def append_columns(data,frame,prefix,metadata,source,exclude=None):
 for col in frame:
  if col in (exclude or []):continue
  name=prefix+col
  if name in data:
   a=data[name];b=frame[col].to_numpy();assert pd.Series(a).equals(pd.Series(b)),f'Conflicting duplicate {name}'
  else:
   data[name]=frame[col].to_numpy();metadata[name]={'source':str(source),'source_column':col,'scope':prefix.rstrip('_')}

def native_and_legacy(root,axis,data,meta,inputs,checks):
 frozen=root/'functional_dynamics_20261019/economy';src=frozen/'pinned_calendar/point_exact_code_witnesses_2011_2025.parquet';register(inputs,src)
 metrics=[c for c in pq.ParquetFile(src).schema_arrow.names if c not in ['id','name','region','lat','lon','population_2021','year','quality_mode']]
 coverage=[]
 for year in range(2011,2026):
  f=pq.read_table(src,columns=['id']+metrics,filters=[('year','=',year)]).to_pandas().set_index('id').reindex(axis.id)
  assert f.index.is_unique and len(f)==len(axis) and f.legal_entities.notna().all()
  append_columns(data,f,f'econ_native_{year}_',meta,src)
  data[f'econ_native_{year}_has_accepted_legal_witness']=f.legal_entities.to_numpy()>0
  data[f'econ_native_{year}_has_accepted_direct_service_witness']=f.direct_consumer_function_diversity.to_numpy()>0
  coverage.append({'year':year,'baseline_positive_legal_witness_UID':int(f.legal_entities.gt(0).sum()),'baseline_positive_service_witness_UID':int(f.direct_consumer_function_diversity.gt(0).sum()),'known_zero_physical_function_UID':0,'arithmetic_zero_accepted_legal_witness_UID':int(f.legal_entities.eq(0).sum()),'physical_function_absence_measured':False})
 for year in [2021,2025]:
  src=frozen/f'pinned_sector_calendar/point_sector_witnesses_{year}.parquet';register(inputs,src)
  f=pq.read_table(src).to_pandas().set_index('id').reindex(axis.id)
  checks.append({'check':f'native_sector_entity_balance_{year}','pass':bool((f.legal_entities.to_numpy()==data[f'econ_native_{year}_legal_entities']).all())})
  append_columns(data,f,f'econ_native_{year}_',meta,src,exclude=['year','quality_mode','legal_entities'])
 src=frozen/'pinned_calendar/point_witness_trajectories_2011_2025.parquet';register(inputs,src)
 f=pq.read_table(src).to_pandas().set_index('id').reindex(axis.id)
 append_columns(data,f,'econ_native_trajectory_',meta,src,exclude=['name','region','lat','lon','population_2010','population_2021'])
 for kind in ['first','last']:
  c='econ_native_trajectory_'+kind+'_witness_year';data[c+'_known']=data[c]>=2011;data[c+'_nullable']=np.where(data[c]>=2011,data[c],np.nan)
 # Older geocoding supplements remain independent columns, never overwrite native.
 legacy={}
 for year in [2016,2021]:
  src=root/f'anchor_research_20261019/economy/coded_results/{year}/points_economic_features.parquet';register(inputs,src);allm=pq.read_table(src).to_pandas()
  for label,mode in [('baseline','coded_baseline'),('strict','coded_strict_house_5km')]:
   f=allm.loc[allm.quality_mode.eq(mode)].set_index('id').reindex(axis.id);legacy[(year,label)]=f
   append_columns(data,f,f'econ_legacy_{label}_{year}_',meta,src,exclude=['name','type','region','lat','lon','population_2021','year','quality_mode','financial_eligible_reports','known_nominal_revenue_thousand_rub','max_legal_entity_revenue_share'])
   # Entropy is undefined with no observed classified firms, not physical zero.
   c=f'econ_legacy_{label}_{year}_section_shannon';data[c]=np.where(f.section_diversity.to_numpy()>0,data[c],np.nan)
 return coverage,legacy

def conditional_alias(root,axis,data,meta,inputs,checks):
 frozen=root/'functional_dynamics_20261019/economy';src=frozen/'address_audit_2021_2025/point_code_alias_sensitivity_2025.parquet';register(inputs,src)
 f=pq.read_table(src).to_pandas().set_index('id').reindex(axis.id)
 for g in GROUPS:
  col=f'{g}_conditional_alias_2025';out=f'econ_alias_2025_{g}_legal_entities';data[out]=f[col].to_numpy();meta[out]={'source':str(src),'source_column':col,'scope':'conditional_verified_alias_2025_not_baseline'}
 data['econ_alias_2025_direct_consumer_function_diversity']=f.conditional_alias_direct_diversity_2025.to_numpy()
 data['econ_alias_2025_direct_consumer_service_legal_entities']=sum(data[f'econ_alias_2025_{g}_legal_entities'] for g in GROUPS[:7])
 data['econ_alias_2025_endpoint_presence_sensitive_to_alias']=f.endpoint_presence_sensitive_to_alias.to_numpy()
 src=frozen/'address_audit_2021_2025/conditional_code_aliases.csv';register(inputs,src);aliases=pd.read_csv(src);aliases=aliases.loc[aliases.accepted_sensitivity_alias].copy();assert len(aliases)==1114
 aliases['normalized_code']=aliases.code_2025.astype('string').str.zfill(11);idx=pd.Series(np.arange(len(axis)),index=axis.id)
 aliasmap=aliases.set_index('normalized_code').reference_id.map(idx);assert aliasmap.notna().all() and aliasmap.index.is_unique
 lookup=pd.Series(np.arange(len(axis)),index=codes(axis.oktmo_2021));counts=np.zeros((len(axis),22),dtype=np.int64);extra=np.zeros(len(axis),dtype=np.int64)
 p1=frozen/'remote_selected/rfsd_2025_identity_function_selected.parquet';p2=frozen/'remote_address_selected/rfsd_2025_address_lifecycle_selected.parquet';register(inputs,p1);register(inputs,p2)
 b1=pq.ParquetFile(p1).iter_batches(batch_size=100000,columns=['inn','oktmo','okved_section']);b2=pq.ParquetFile(p2).iter_batches(batch_size=100000,columns=['inn','lat','lon','geocoding_quality']);lut={s:i+1 for i,s in enumerate('ABCDEFGHIJKLMNOPQRSTU')}
 rows=0;native_total=0
 for aa,bb in zip(b1,b2):
  d=aa.to_pandas();geo=bb.to_pandas();assert len(d)==len(geo) and d.inn.equals(geo.inn);rows+=len(d)
  good=d.inn.str.fullmatch(r'\d{10}',na=False).to_numpy();code=codes(d.oktmo);native=code.map(lookup).fillna(-1).astype(int).to_numpy();ap=code.map(aliasmap).fillna(-1).astype(int).to_numpy();native_total+=int(((native>=0)&good).sum())
  take=good&(native<0)&(ap>=0)&geo.geocoding_quality.isin(['house','street']).to_numpy();ix=np.flatnonzero(take)
  dd=distance(geo.lat.to_numpy()[ix],geo.lon.to_numpy()[ix],axis.lat.to_numpy()[ap[ix]],axis.lon.to_numpy()[ap[ix]])
  take[ix]=np.isfinite(dd)&(dd<=5);assigned=np.where(take,ap,native);accept=good&(assigned>=0)
  sec=d.okved_section.map(lut).fillna(0).astype(int).to_numpy();counts+=np.bincount(assigned[accept]*22+sec[accept],minlength=len(axis)*22).reshape(len(axis),22);extra+=np.bincount(assigned[take],minlength=len(axis))
 data['econ_alias_2025_legal_entities']=counts.sum(axis=1);data['econ_alias_2025_supplemental_legal_entities']=extra
 data['econ_alias_2025_unknown_section_legal_entities']=counts[:,0]
 for s,i in lut.items():data[f'econ_alias_2025_section_{s}_legal_entities']=counts[:,i]
 data['econ_alias_2025_registered_section_diversity']=(counts[:,1:]>0).sum(axis=1)
 data['econ_alias_2025_conditional_crosswalk_applied']=extra>0;data['econ_alias_2025_has_accepted_legal_witness']=counts.sum(axis=1)>0
 data['econ_alias_2025_has_accepted_direct_service_witness']=data['econ_alias_2025_direct_consumer_function_diversity']>0
 data['econ_alias_2025_reference_has_accepted_code_alias']=axis.id.isin(aliases.reference_id).to_numpy()
 checks.extend([{'check':'alias_2025_raw_row_balance','pass':rows==3143178 and native_total==1988011}, {'check':'alias_2025_extra_record_reconciliation','pass':int(extra.sum())==74244}, {'check':'alias_2025_full_entity_reconciliation','pass':int(counts.sum())==2062255}, {'check':'alias_2025_source_service_reconciliation','pass':int((data['econ_alias_2025_direct_consumer_function_diversity']>0).sum())==12876}])
 return {'accepted_alias_codes':1114,'additional_accepted_legal_records':int(extra.sum()),'UID_with_additional_legal_records':int((extra>0).sum()),'additional_service_positive_UID':int((data['econ_alias_2025_has_accepted_direct_service_witness']&~data['econ_native_2025_has_accepted_direct_service_witness']).sum()),'accepted_alias_heldout_conflicts':0}

def finance(root,axis,data,meta,inputs,checks,legacy):
 n=len(axis);lookup=pd.Series(np.arange(n),index=codes(axis.oktmo_2021));tree=cKDTree(xyz(axis.lat.to_numpy(),axis.lon.to_numpy()));out=[]
 for year in [2016,2021]:
  src=root/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet';register(inputs,src)
  names=['native','legacy_baseline','legacy_strict'];cnt=np.zeros((3,n,4),dtype=np.int64);sums=np.zeros((3,n,4));maxrev=np.zeros((3,n));legal=np.zeros((3,n),dtype=np.int64);eligible=np.zeros((3,n),dtype=np.int64);rows=0
  fields=['inn','oktmo','eligible','filed','articulated','outlier','imputed','geocoding_quality','lat','lon']+list(FIN)
  for batch in pq.ParquetFile(src).iter_batches(batch_size=100000,columns=fields):
   d=batch.to_pandas();rows+=len(d);good=d.inn.str.fullmatch(r'\d{10}',na=False).to_numpy();code=codes(d.oktmo);point=code.map(lookup).fillna(-1).astype(int).to_numpy();fed=code.str[:2].isin(['45','40']).to_numpy()&good;exact=good&(point>=0)&~fed
   valid=(d.lat.between(-90,90)&d.lon.between(-180,180)).to_numpy();near=np.full(len(d),-1,dtype=int);nd=np.full(len(d),np.inf);gap=np.full(len(d),-1.)
   if valid.any():
    chord,ix=tree.query(xyz(d.lat.to_numpy()[valid],d.lon.to_numpy()[valid]),k=2,workers=2);dist=2*R*np.arcsin(np.clip(chord/2,0,1));near[valid]=ix[:,0];nd[valid]=dist[:,0];gap[valid]=dist[:,1]-dist[:,0]
   q=d.geocoding_quality.fillna('').to_numpy();fallback=~exact&~fed&good&valid&np.isin(q,['house','street'])&(nd<=1)&(gap>.25);assigned=np.where(exact,point,np.where(fallback,near,-1));selected=exact|fallback
   distref=np.full(len(d),np.inf);t=selected&valid
   if t.any():distref[t]=2*R*np.arcsin(np.clip(np.linalg.norm(xyz(d.lat.to_numpy()[t],d.lon.to_numpy()[t])-xyz(axis.lat.to_numpy()[assigned[t]],axis.lon.to_numpy()[assigned[t]]),axis=1)/2,0,1))
   consistent=(d.eligible.eq(1)&d.filed.eq(1)&d.articulated.eq(1)&d.outlier.eq(0)).to_numpy()
   for mode,select,dest in [(0,exact,point),(1,selected,assigned),(2,selected&(q=='house')&(distref<=5),assigned)]:
    np.add.at(legal[mode],dest[select],1);base=select&consistent
    if mode==2:base &= d.imputed.eq(0).to_numpy()
    np.add.at(eligible[mode],dest[base],1)
    for fi,(field,label) in enumerate(FIN.items()):
     amount=pd.to_numeric(d[field],errors='coerce').to_numpy();take=base&np.isfinite(amount)
     if field!='line_2400':take &= amount>=0
     np.add.at(cnt[mode,:,fi],dest[take],1);np.add.at(sums[mode,:,fi],dest[take],amount[take])
     if field=='line_2110':np.maximum.at(maxrev[mode],dest[take],amount[take])
  for mi,mode in enumerate(names):
   prefix=f'econ_{mode}_{year}_';data[prefix+'financial_consistent_filing_entities']=eligible[mi]
   for fi,(field,label) in enumerate(FIN.items()):
    stem=prefix+'legal_registered_'+label;data[stem+'_thousand_rub']=np.where(cnt[mi,:,fi]>0,sums[mi,:,fi],np.nan);data[stem+'_reporting_entities']=cnt[mi,:,fi];data[stem+'_known']=cnt[mi,:,fi]>0
    data[stem+'_reporting_share_of_attached_entities']=np.divide(cnt[mi,:,fi],legal[mi],out=np.full(n,np.nan),where=legal[mi]>0)
    meta[stem+'_thousand_rub']={'source':str(src),'source_column':field,'units':'nominal_thousand_RUB','scope':mode,'validity':'eligible=1,filed=1,articulated=1,outlier=0; finite; nonnegative except net_profit; strict additionally imputed=0','missing':'NaN when zero accepted usable reports; finite zero only if sum of usable reports is zero'}
   data[prefix+'max_legal_entity_revenue_share']=np.divide(maxrev[mi],sums[mi,:,2],out=np.full(n,np.nan),where=sums[mi,:,2]>0)
   data[prefix+'financial_presence_status']=np.where(legal[mi]==0,'no_accepted_registered_legal_witness',np.where(eligible[mi]>0,'at_least_one_usable_filing','legal_witness_but_no_usable_filing'))
   if mode=='native':checks.append({'check':f'finance_native_legal_stock_{year}','pass':bool((legal[mi]==data[prefix+'legal_entities']).all())})
   else:
    label=mode.replace('legacy_','');old=legacy[(year,label)];checks.extend([{'check':f'finance_{mode}_legal_stock_{year}','pass':bool((legal[mi]==old.legal_entities.to_numpy()).all())},{'check':f'finance_{mode}_old_revenue_count_{year}','pass':bool((cnt[mi,:,2]==old.financial_eligible_reports.to_numpy()).all())},{'check':f'finance_{mode}_old_revenue_sum_{year}','pass':bool(np.allclose(sums[mi,:,2],old.known_nominal_revenue_thousand_rub.to_numpy(),rtol=1e-12,atol=1e-5))}])
   out.append({'year':year,'mode':mode,'source_rows':rows,'attached_legal_entities':int(legal[mi].sum()),'UID_with_usable_revenue':int((cnt[mi,:,2]>0).sum()),'known_registered_revenue_sum_thousand_rub':float(sums[mi,:,2].sum()),'known_registered_net_profit_sum_thousand_rub':float(sums[mi,:,3].sum()),'actual_jobs_or_complete_local_production_measured':False})
  print(json.dumps({'financial_year_complete':year,'source_rows':rows}),flush=True)
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 src=a.base/'anchor_research_20261019/data/point_axis.parquet';axis=pq.read_table(src,columns=['id','oktmo_2021','lat','lon']).to_pandas();assert len(axis)==142570 and axis.id.is_unique and axis.id.notna().all() and codes(axis.oktmo_2021).is_unique
 inputs={};register(inputs,src);data={'id':axis.id.to_numpy()};meta={};checks=[]
 coverage,legacy=native_and_legacy(a.base,axis,data,meta,inputs,checks);conditional=conditional_alias(a.base,axis,data,meta,inputs,checks);financial=finance(a.base,axis,data,meta,inputs,checks,legacy)
 data['econ_native_code_reference_year']=np.full(len(axis),2021,dtype=np.int16);data['econ_native_historical_code_crosswalk_proven']=np.full(len(axis),False);data['econ_external_flows_measured_by_RFSD']=np.full(len(axis),False)
 data['econ_any_native_legal_witness_2011_2025']=np.any(np.stack([data[f'econ_native_{year}_legal_entities']>0 for year in range(2011,2026)]),axis=0)
 data['econ_any_native_direct_service_witness_2011_2025']=np.any(np.stack([data[f'econ_native_{year}_direct_consumer_function_diversity']>0 for year in range(2011,2026)]),axis=0)
 result=pd.DataFrame(data)
 checks.extend([{'check':'full_unique_left_UID_axis','pass':len(result)==142570 and result.id.is_unique and result.id.notna().all() and result.id.equals(axis.id)}, {'check':'no_duplicate_columns','pass':not result.columns.duplicated().any()},{'check':'baseline_alias_separate_and_superset','pass':bool((result.econ_alias_2025_legal_entities>=result.econ_native_2025_legal_entities).all())}])
 for col in result:
  if col.endswith('_thousand_rub') and 'legal_registered_' in col:
   known=col.replace('_thousand_rub','_known');checks.append({'check':'missing_finance_not_zero__'+col,'pass':bool(result.loc[~result[known],col].isna().all() and result.loc[result[known],col].notna().all())})
 pqpath=a.out/'economy_features.parquet';result.to_parquet(pqpath,index=False,compression='zstd');pd.testing.assert_frame_equal(result,pq.read_table(pqpath).to_pandas());checks.append({'check':'whole_wide_parquet_readback','pass':True})
 result.to_csv(a.out/'economy_features.csv.gz',index=False,compression='gzip')
 dictionary=[]
 for col in result:
  item={'column':col,'dtype':str(result[col].dtype),'provenance':meta.get(col,{}),'row_grain':'one_frozen_settlement_UID','not_measured':'actual physical functions, jobs or external catchment flows'}
  if col.endswith('_legal_entities') or col.endswith('_reporting_entities'):item['zero_meaning']='zero accepted RFSD witnesses, not complete real-world absence'
  dictionary.append(item)
 dump(a.out/'SCHEMA.json',dictionary);pd.DataFrame(coverage).to_csv(a.out/'coverage_by_year.csv',index=False);pd.DataFrame(financial).to_csv(a.out/'financial_coverage.csv',index=False)
 audit={'pass':all(x['pass'] for x in checks),'checks':checks,'rows':len(result),'columns':len(result.columns),'unique_UID':int(result.id.nunique()),'missing_UID':int(result.id.isna().sum()),'foreign_UID':0,'duplicate_UID':int(result.id.duplicated().sum()),'baseline_any_year_legal_UID':int(result.econ_any_native_legal_witness_2011_2025.sum()),'baseline_any_year_direct_service_UID':int(result.econ_any_native_direct_service_witness_2011_2025.sum()),'known_zero_physical_function_UID':0,'nearest_candidate_UID':0,'conditional':conditional,'financial':financial,'inputs':inputs,'pinned_dataset_commit':PIN,'code_sha256':sha(Path(__file__)),'rule_change_from_frozen_baseline':False,'conditional_code_supplement_separate':True,'new_source_downloaded':False,'coverage_denominator':142570}
 dump(a.out/'AUDIT.json',audit);assert audit['pass'],[x for x in checks if not x['pass']]
 dump(a.out/'MANIFEST.json',{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in a.out.iterdir() if p.is_file() and p.name!='MANIFEST.json'})
 print(json.dumps({'rows':len(result),'columns':len(result.columns),'checks':len(checks),'pass':True,'conditional':conditional},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
