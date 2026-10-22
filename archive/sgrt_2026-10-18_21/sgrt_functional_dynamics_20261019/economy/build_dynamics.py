#!/usr/bin/env python3
"""Paired legal-registration witnesses. No object closure, service flow or SGRT inference."""
from pathlib import Path
import argparse, hashlib, json, time
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

GROUPS={'retail47':({'47'},'G'),'food56':({'56'},'I'),'education85':({'85'},'P'),
 'health86':({'86'},'Q'),'social8788':({'87','88'},'Q'),'repair95':({'95'},'S'),
 'personal96':({'96'},'S'),'accommodation55':({'55'},'I'),
 'finance64to66':({'64','65','66'},'K'),'admin84':({'84'},'O')}
DIRECT=list(GROUPS)[:7]
TRANS={0:'unobserved_both',1:'witness_lost',2:'witness_gained',3:'witness_retained'}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def codes(s):
 s=s.astype('string').str.strip()
 return s.where(s.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
def save(df,path):
 df.to_parquet(path.with_suffix('.parquet'),index=False)
 df.to_csv(path.with_suffix('.csv.gz'),index=False,compression='gzip')
 pd.testing.assert_frame_equal(df,pq.read_table(path.with_suffix('.parquet')).to_pandas())
def statust(a,b):return pd.Series(np.take(list(TRANS.values()),a.astype(int)+2*b.astype(int)),index=a.index)

def paired(agg,panel,out,checks):
 frames=[]; summaries=[]
 covars=panel[['id','population_2010','population_2021']].copy()
 for mode in ['coded_baseline','coded_strict_house_5km']:
  a=agg[2016].query('quality_mode==@mode').set_index('id');b=agg[2021].query('quality_mode==@mode').set_index('id').reindex(a.index)
  assert len(a)==len(b)==len(panel) and a.index.is_unique and b.index.is_unique
  p=a[['name','type','region','lat','lon']].reset_index().merge(covars,on='id',validate='one_to_one')
  p['quality_mode']=mode
  p['population_bin']=pd.cut(p.population_2021,[-1,0,99,499,999,4999,19999,99999,np.inf],labels=['0','1–99','100–499','500–999','1000–4999','5000–19999','20000–99999','100000+']).astype('string').fillna('unknown')
  # No arbitrary threshold in growth: numerical relative band +/-5% explicitly descriptive.
  p0=p.population_2010.to_numpy();p1=p.population_2021.to_numpy();d=np.divide(p1-p0,p0,out=np.full(len(p),np.nan),where=p0>0)
  p['demographic_2010_2021']=np.select([~np.isfinite(p0)|~np.isfinite(p1),(p0==0)&(p1==0),(p0==0)&(p1>0),d<-.05,d>.05],['unknown','zero_both','from_zero','decrease_gt5pct','increase_gt5pct'],default='within_5pct')
  for g in ['legal_entities']+[g+'_legal_entities' for g in GROUPS]+['direct_consumer_function_diversity']:
   p[g+'_2016']=a[g].to_numpy();p[g+'_2021']=b[g].to_numpy();p[g+'_delta']=p[g+'_2021']-p[g+'_2016']
  for g in ['legal_entities']+list(GROUPS):
   c=g if g=='legal_entities' else g+'_legal_entities'
   p[g+'_transition']=statust(p[c+'_2016']>0,p[c+'_2021']>0)
  p['any_direct_service_transition']=statust(p.direct_consumer_function_diversity_2016>0,p.direct_consumer_function_diversity_2021>0)
  for k in [2,3]:p[f'diversification_ge{k}_transition']=statust(p.direct_consumer_function_diversity_2016>=k,p.direct_consumer_function_diversity_2021>=k)
  p['diversity_change']=np.select([p.direct_consumer_function_diversity_delta<0,p.direct_consumer_function_diversity_delta>0],['decreased','increased'],default='unchanged')
  for strat in [None,'population_bin','demographic_2010_2021']:
   groups=[('all',p)] if strat is None else p.groupby(strat,observed=True,dropna=False,sort=True)
   for level,z in groups:
    for g in ['any_direct_service','diversification_ge2','diversification_ge3','legal_entities']+list(GROUPS):
     v=z[g+'_transition'].value_counts()
     row={'quality_mode':mode,'stratifier':strat or 'all','stratum':level,'feature':g,'n_settlements':len(z)}
     row.update({k:int(v.get(k,0)) for k in TRANS.values()})
     row['observed_2016']=row['witness_lost']+row['witness_retained'];row['observed_2021']=row['witness_gained']+row['witness_retained']
     row['net_change']=row['witness_gained']-row['witness_lost'];summaries.append(row)
  frames.append(p)
  checks.append({'check':'one_axis_'+mode,'pass':len(p)==142570 and not p.id.duplicated().any()})
 paired_df=pd.concat(frames,ignore_index=True);summary=pd.DataFrame(summaries)
 checks.append({'check':'four_states_partition_each_stratum','pass':bool((summary[list(TRANS.values())].sum(axis=1)==summary.n_settlements).all())})
 checks.append({'check':'stock_flow_balance','pass':bool((summary.observed_2021-summary.observed_2016==summary.net_change).all())})
 save(paired_df,out/'point_function_dynamics');summary.to_csv(out/'transition_summary.csv',index=False)
 return paired_df,summary

def spatial(p,out,checks,seed=20261019):
 """Paired geographic block resampling: composition robustness, not sampling CI."""
 rows=[];block_rows=[]
 for mode,z in p.groupby('quality_mode',sort=True):
  for latw,lonw in [(2.5,5.),(5.,10.)]:
   # Dateline-aware bins, point-count weighted national estimand. No interpolation.
   block=np.floor((z.lat+90)/latw).astype(int).astype(str)+'_'+np.floor((z.lon+180)/lonw).astype(int).astype(str)
   for feature in ['any_direct_service','diversification_ge2','diversification_ge3']:
    v=z[feature+'_transition'];w=pd.DataFrame({'block':block,'n':1,'delta':v.eq('witness_gained').astype(int)-v.eq('witness_lost').astype(int),'lost':v.eq('witness_lost').astype(int),'gained':v.eq('witness_gained').astype(int)}).groupby('block').sum()
    n=w.n.to_numpy();delta=w.delta.to_numpy();rng=np.random.default_rng(seed);B=2000
    ix=rng.integers(0,len(w),size=(B,len(w)));rep=delta[ix].sum(axis=1)/n[ix].sum(axis=1)
    lo,hi=np.quantile(rep,[.025,.975]);point=float(delta.sum()/n.sum())
    rows.append({'quality_mode':mode,'feature':feature,'latitude_width_deg':latw,'longitude_width_deg':lonw,'n_blocks':len(w),'n_settlements':int(n.sum()),'net_presence_change_proportion':point,'block_resampling_p025':float(lo),'block_resampling_p975':float(hi),'replications':B,'seed':seed,'interpretation':'geographical_composition_envelope_not_sampling_CI_or_causal_effect'})
    ww=w.reset_index();ww['quality_mode']=mode;ww['feature']=feature;ww['latitude_width_deg']=latw;ww['longitude_width_deg']=lonw;block_rows.append(ww)
    checks.append({'check':f'block_balance_{mode}_{feature}_{latw}','pass':int(n.sum())==142570 and int(delta.sum())==int((v=='witness_gained').sum()-(v=='witness_lost').sum())})
 pd.DataFrame(rows).to_csv(out/'spatial_block_robustness.csv',index=False)
 pd.concat(block_rows,ignore_index=True).to_csv(out/'spatial_block_counts.csv',index=False)

def raw_year(source,panel,year,checks):
 """Re-read only identity, codes, function and filing flags; exact codes only for cohort."""
 pc=codes(panel.oktmo_2021);lookup=pd.Series(np.arange(len(panel),dtype=np.int32),index=pc)
 arrays={x:[] for x in ['inn','point','mask','filed','section','prefix']};invalid=0;checksum_invalid=0
 pf=pq.ParquetFile(source)
 for batch in pf.iter_batches(batch_size=200000,columns=['inn','oktmo','okved','okved_section','filed']):
  d=batch.to_pandas();valid=d.inn.str.fullmatch(r'\d{10}',na=False);invalid+=int((~valid).sum());d=d.loc[valid]
  inn=d.inn.astype(np.uint64).to_numpy();point=codes(d.oktmo).map(lookup).fillna(-1).astype(np.int32).to_numpy()
  control=np.zeros(len(inn),dtype=np.uint64)
  for pos,weight in enumerate([2,4,10,3,5,9,4,6,8]):control+=((inn//(10**(9-pos)))%10)*weight
  checksum_invalid+=int(((control%11)%10 != inn%10).sum())
  pref=d.okved.fillna('').str.extract(r'^(\d{2})',expand=False).fillna('');sec=d.okved_section.fillna('')
  mask=np.zeros(len(d),dtype=np.uint16)
  for gi,(_, (ps,s)) in enumerate(GROUPS.items()):mask|=((pref.isin(ps)&sec.eq(s)).to_numpy().astype(np.uint16)<<gi)
  arrays['inn'].append(inn);arrays['point'].append(point);arrays['mask'].append(mask);arrays['filed'].append(d.filed.eq(1).to_numpy())
  arrays['section'].append(sec.map({s:i+1 for i,s in enumerate('ABCDEFGHIJKLMNOPQRSTU')}).fillna(0).astype(np.uint8).to_numpy())
  arrays['prefix'].append(pd.to_numeric(pref,errors='coerce').fillna(255).astype(np.uint8).to_numpy())
 for k in arrays:arrays[k]=np.concatenate(arrays[k])
 checks.append({'check':f'raw_unique_valid_INN_{year}','pass':len(np.unique(arrays['inn']))==len(arrays['inn'])})
 checks.append({'check':f'raw_total_{year}','pass':len(arrays['inn'])+invalid==pf.metadata.num_rows})
 arrays['invalid_inn_rows']=invalid
 arrays['checksum_invalid_rows_retained']=checksum_invalid
 return arrays

def cohort(raw,panel,out,checks):
 a,b=raw[2016],raw[2021]
 common,ia,ib=np.intersect1d(a['inn'],b['inn'],assume_unique=True,return_indices=True)
 x=a['point'][ia];y=b['point'][ib];same=(x==y)&(x>=0);both=(x>=0)&(y>=0);stablecode=(a['prefix'][ia]==b['prefix'][ib])&(a['section'][ia]==b['section'][ib])
 samefiled=same&a['filed'][ia]&b['filed'][ib]
 sameclass=same&stablecode
 summary={'valid_INN_2016':len(a['inn']),'valid_INN_2021':len(b['inn']),'invalid_or_missing_INN_2016':a['invalid_inn_rows'],'invalid_or_missing_INN_2021':b['invalid_inn_rows'],'common_INN':len(common),'only_2016_INN':len(a['inn'])-len(common),'only_2021_INN':len(b['inn'])-len(common),'common_exact_point_both':int(both.sum()),'common_same_exact_point':int(same.sum()),'common_different_exact_points':int((both&~same).sum()),'common_exact2016_only':int(((x>=0)&(y<0)).sum()),'common_exact2021_only':int(((x<0)&(y>=0)).sum()),'common_neither_exact':int(((x<0)&(y<0)).sum()),'common_same_point_filed_both':int(samefiled.sum()),'common_same_point_unchanged_2digit_section':int(sameclass.sum()),'common_same_point_class_changed':int((same&~stablecode).sum()),'interpretation':'INN persistence and modern exact-code projection; unmatched year is not legal birth/death; changed point is code/address evidence, not proved physical relocation'}
 n=len(panel);rows=[];point_frames=[]
 # Separate full exact-code witnesses from fixed common-INN cohorts.
 masks=[('all_exact_code',None),('common_INN_any_address',np.ones(len(common),dtype=bool)),('common_INN_same_exact_point',same),('common_INN_same_point_filed_both',samefiled),('common_INN_same_point_same_primary_code',sameclass)]
 for name,keep in masks:
  counts={}
  for year,d,index in [(2016,a,ia),(2021,b,ib)]:
   loc=d['point'] if keep is None else d['point'][index][keep]
   fm=d['mask'] if keep is None else d['mask'][index][keep]
   accepted=loc>=0;loc=loc[accepted];fm=fm[accepted]
   cnt=np.stack([np.bincount(loc[(fm&(1<<gi))>0],minlength=n) for gi in range(len(GROUPS))],axis=1)
   counts[year]=cnt
  div={yr:(cnt[:,:7]>0).sum(axis=1) for yr,cnt in counts.items()}
  f=panel[['id','name','region']].copy();f['cohort']=name
  for yr in [2016,2021]:
   for gi,g in enumerate(GROUPS):f[f'{g}_{yr}']=counts[yr][:,gi]
   f[f'direct_diversity_{yr}']=div[yr]
  point_frames.append(f)
  for gi,g in enumerate(GROUPS):
   aa=counts[2016][:,gi]>0;bb=counts[2021][:,gi]>0
   rows.append({'cohort':name,'feature':g,'entities_2016':int(counts[2016][:,gi].sum()),'entities_2021':int(counts[2021][:,gi].sum()),'points_2016':int(aa.sum()),'points_2021':int(bb.sum()),'witness_lost':int((aa&~bb).sum()),'witness_gained':int((~aa&bb).sum()),'witness_retained':int((aa&bb).sum()),'unobserved_both':int((~aa&~bb).sum())})
  for k in [1,2,3]:
   aa=div[2016]>=k;bb=div[2021]>=k
   rows.append({'cohort':name,'feature':f'direct_diversity_ge{k}','entities_2016':None,'entities_2021':None,'points_2016':int(aa.sum()),'points_2021':int(bb.sum()),'witness_lost':int((aa&~bb).sum()),'witness_gained':int((~aa&bb).sum()),'witness_retained':int((aa&bb).sum()),'unobserved_both':int((~aa&~bb).sum())})
  if name=='common_INN_same_point_same_primary_code':checks.append({'check':'stable_primary_code_implies_no_function_changes','pass':bool(np.array_equal(counts[2016],counts[2021]))})
  if name=='all_exact_code':
   for yr in [2016,2021]:
    summary[f'exact_code_service_entities_{yr}']=int(counts[yr][:,:7].sum())
 s=pd.DataFrame(rows);s.to_csv(out/'cohort_transition_summary.csv',index=False);save(pd.concat(point_frames,ignore_index=True),out/'point_cohort_sensitivity')
 checks.append({'check':'common_identity_partition','pass':summary['common_INN']==sum(summary[k] for k in ['common_same_exact_point','common_different_exact_points','common_exact2016_only','common_exact2021_only','common_neither_exact'])})
 checks.append({'check':'cohort_states_cover_axis','pass':bool((s[['witness_lost','witness_gained','witness_retained','unobserved_both']].sum(axis=1)==n).all())})
 # Net point-code transitions only aggregate cells: no new micro-INN disclosure/output.
 z=pd.DataFrame({'origin_id':panel.id.to_numpy()[x[both&~same]],'destination_id':panel.id.to_numpy()[y[both&~same]]}).value_counts().rename('common_INN_count').reset_index()
 save(z,out/'registered_point_code_transitions')
 dump(out/'cohort_audit.json',summary)
 return summary

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 panelpath=a.base/'restored/extracted/research/sgrt_recovered_20261019/data/panel.parquet'
 panel=pq.read_table(panelpath,columns=['id','name','region','lat','lon','population_2010','population_2021','oktmo_2021']).to_pandas()
 agg={yr:pq.read_table(a.base/f'anchor_research_20261019/economy/coded_results/{yr}/points_economic_features.parquet').to_pandas() for yr in [2016,2021]}
 checks=[];p,s=paired(agg,panel,a.out,checks);spatial(p,a.out,checks)
 print('Paired point dynamics and spatial robustness complete',flush=True)
 raw={};sources={}
 for yr in [2016,2021]:
  src=a.base/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{yr}_selected.parquet';sources[str(yr)]={'path':str(src),'sha256':sha(src),'rows':pq.ParquetFile(src).metadata.num_rows,'columns_read':['inn','oktmo','okved','okved_section','filed']}
  raw[yr]=raw_year(src,panel,yr,checks);print(f'Raw identity/function read {yr}',flush=True)
 summary=cohort(raw,panel,a.out,checks)
 # Verify full exact-code entity-count stock against author aggregates (not used in cohort).
 for yr in [2016,2021]:
  checks.append({'check':f'exact_code_raw_reconciles_aggregate_{yr}','pass':int((raw[yr]['point']>=0).sum())==int(agg[yr].query('quality_mode=="coded_baseline"').exact_code_entities.sum())})
 dump(a.out/'AUDIT.json',{'checks':checks,'pass':all(c['pass'] for c in checks),'source':sources,'panel_sha256':sha(panelpath),'aggregate_sha256':{str(yr):sha(a.base/f'anchor_research_20261019/economy/coded_results/{yr}/points_economic_features.parquet') for yr in [2016,2021]},'code_sha256':sha(Path(__file__)),'years':[2016,2021],'units':'legal entities or settlements; no direct jobs or physical services','axis_year':2021,'historical_code_crosswalk_verified':False})
 assert all(c['pass'] for c in checks),checks
 outputs={str(f.relative_to(a.out)):{'sha256':sha(f),'bytes':f.stat().st_size} for f in sorted(a.out.iterdir()) if f.is_file() and f.name!='MANIFEST.json'};dump(a.out/'MANIFEST.json',outputs)
 print(json.dumps({'checks':len(checks),'pass':True,'cohort':summary},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
