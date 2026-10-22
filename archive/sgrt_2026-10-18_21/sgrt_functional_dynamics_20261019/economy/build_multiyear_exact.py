#!/usr/bin/env python3
"""Pinned 2011–2025 calendar of exact-code legal-registration witnesses only."""
import argparse,json,time
from pathlib import Path
import numpy as np,pandas as pd
import pyarrow.parquet as pq
from build_dynamics import GROUPS,DIRECT,raw_year,save,sha,dump,statust,codes,spatial
PIN='bde9b8b129a8be582b66de4e30ed79c9187a8515'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));ap.add_argument('--out',type=Path,required=True);ap.add_argument('--wait-for-inputs',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 root=a.base/'functional_dynamics_20261019/economy';pfile=a.base/'restored/extracted/research/sgrt_recovered_20261019/data/panel.parquet'
 p=pq.read_table(pfile,columns=['id','name','region','lat','lon','population_2010','population_2021','oktmo_2021']).to_pandas();n=len(p)
 checks=[{'check':'unique_fixed_id_axis','pass':len(p)==142570 and p.id.is_unique},
 {'check':'unique_fixed_normalized_settlement_codes','pass':bool(codes(p.oktmo_2021).notna().all() and codes(p.oktmo_2021).is_unique)}];coverage=[];frames=[];sources={};tables={};years=list(range(2011,2026));cohort_previous=None;cohort_rows=[];cohort_function_rows=[]
 for year in years:
  source=root/f'remote_selected/rfsd_{year}_identity_function_selected.parquet'
  auditfile=root/f'remote_selected/{year}_acquisition.json';deadline=time.monotonic()+600
  while True:
   acquisition=json.loads(auditfile.read_text()) if auditfile.exists() else {}
   if source.exists() and acquisition.get('pinned_dataset_commit')==PIN:break
   if not a.wait_for_inputs or time.monotonic()>deadline:raise RuntimeError(f'Pinned input {year} not yet verified; no zero replacement allowed')
   time.sleep(2)
  assert acquisition['pinned_dataset_commit']==PIN and acquisition['whole_selected_table_readback'] and acquisition['schema_inspected_before_column_download']
  assert sha(source)==acquisition['selected_file_sha256']
  d=raw_year(source,p,year,checks);selected=d['point']>=0;loc=d['point'][selected];mask=d['mask'][selected]
  f=p[['id','name','region','lat','lon','population_2021']].copy();f['year']=year;f['quality_mode']='exact_settlement_code_only'
  f['legal_entities']=np.bincount(loc,minlength=n)
  for gi,g in enumerate(GROUPS):f[g+'_legal_entities']=np.bincount(loc[(mask&(1<<gi))>0],minlength=n)
  f['direct_consumer_function_diversity']=sum(f[g+'_legal_entities'].gt(0).astype(int) for g in DIRECT)
  f['direct_consumer_service_legal_entities']=sum(f[g+'_legal_entities'] for g in DIRECT)
  f['witness_status']=np.where(f.legal_entities>0,'legal_address_witness','no_accepted_witness_not_absence')
  coverage.append({'year':year,'source_rows':len(d['inn'])+d['invalid_inn_rows'],'valid_inn_rows':len(d['inn']),'INN_validity_definition':'ten_digits_syntax_only_not_EGRUL_legal_validation','checksum_invalid_INN_retained':d['checksum_invalid_rows_retained'],'exact_settlement_code_entities':int(selected.sum()),'points_with_legal_witness':int(f.legal_entities.gt(0).sum()),'points_with_direct_service_witness':int(f.direct_consumer_function_diversity.gt(0).sum()),'points_with_ge2_direct_groups':int(f.direct_consumer_function_diversity.ge(2).sum()),'points_with_ge3_direct_groups':int(f.direct_consumer_function_diversity.ge(3).sum()),'reference_code_year':2021,'historical_code_crosswalk_proven':False})
  checks.append({'check':f'entity_balance_{year}','pass':int(f.legal_entities.sum())==int(selected.sum())})
  tables[year]=f;frames.append(f);sources[str(year)]={'path':str(source),'sha256':sha(source),'schema_columns_read':['inn','oktmo','okved','okved_section','filed'],'pinned_dataset_commit':PIN,'acquisition_audit':str(root/f'remote_selected/{year}_acquisition.json')}
  # Genuine paired identities of adjacent annual panels; no physical birth/death labels.
  if cohort_previous is not None:
   common,ia,ib=np.intersect1d(cohort_previous['inn'],d['inn'],assume_unique=True,return_indices=True)
   x=cohort_previous['point'][ia];y=d['point'][ib];both=(x>=0)&(y>=0);same=both&(x==y)
   cohort_rows.append({'from_year':year-1,'to_year':year,'valid_INN_from':len(cohort_previous['inn']),'valid_INN_to':len(d['inn']),'common_INN':len(common),'only_from_INN_not_proven_death':len(cohort_previous['inn'])-len(common),'only_to_INN_not_proven_birth':len(d['inn'])-len(common),'same_exact_point':int(same.sum()),'different_exact_points':int((both&~same).sum()),'exact_from_only':int(((x>=0)&(y<0)).sum()),'exact_to_only':int(((x<0)&(y>=0)).sum()),'neither_exact':int(((x<0)&(y<0)).sum())})
   lc=x[same];ma=cohort_previous['mask'][ia][same];mb=d['mask'][ib][same]
   ca=np.stack([np.bincount(lc[(ma&(1<<gi))>0],minlength=n) for gi in range(7)],axis=1)
   cb=np.stack([np.bincount(lc[(mb&(1<<gi))>0],minlength=n) for gi in range(7)],axis=1)
   for gi,g in enumerate(DIRECT):
    va=ca[:,gi]>0;vb=cb[:,gi]>0
    cohort_function_rows.append({'from_year':year-1,'to_year':year,'cohort':'same_INN_same_exact_point','feature':g,'points_from':int(va.sum()),'points_to':int(vb.sum()),'witness_lost':int((va&~vb).sum()),'witness_gained':int((~va&vb).sum()),'witness_retained':int((va&vb).sum()),'unobserved_both':int((~va&~vb).sum())})
   for k in [1,2,3]:
    va=(ca>0).sum(axis=1)>=k;vb=(cb>0).sum(axis=1)>=k
    cohort_function_rows.append({'from_year':year-1,'to_year':year,'cohort':'same_INN_same_exact_point','feature':f'direct_diversity_ge{k}','points_from':int(va.sum()),'points_to':int(vb.sum()),'witness_lost':int((va&~vb).sum()),'witness_gained':int((~va&vb).sum()),'witness_retained':int((va&vb).sum()),'unobserved_both':int((~va&~vb).sum())})
   checks.append({'check':f'identity_partition_{year-1}_{year}','pass':int(same.sum()+(both&~same).sum()+((x>=0)&(y<0)).sum()+((x<0)&(y>=0)).sum()+((x<0)&(y<0)).sum())==len(common)})
  cohort_previous={'inn':d['inn'],'point':d['point'],'mask':d['mask']}
  print(json.dumps(coverage[-1]),flush=True)
  del d
 long=pd.concat(frames,ignore_index=True);save(long,a.out/'point_exact_code_witnesses_2011_2025');pd.DataFrame(coverage).to_csv(a.out/'coverage_2011_2025.csv',index=False);pd.DataFrame(cohort_rows).to_csv(a.out/'adjacent_year_INN_cohorts.csv',index=False);pd.DataFrame(cohort_function_rows).to_csv(a.out/'adjacent_same_INN_same_point_function_transitions.csv',index=False)
 pairrows=[]
 for y0,y1 in [(yr,yr+1) for yr in years[:-1]]+[(2011,2016),(2016,2021),(2021,2025),(2011,2025)]:
  aa=tables[y0];bb=tables[y1]
  for col in ['legal_entities']+[g+'_legal_entities' for g in GROUPS]+['direct_consumer_function_diversity']:
   va=aa[col].gt(0);vb=bb[col].gt(0);t=statust(va,vb)
   r={'from_year':y0,'to_year':y1,'feature':col,'n':n,'observed_from':int(va.sum()),'observed_to':int(vb.sum())}
   for st in ['unobserved_both','witness_lost','witness_gained','witness_retained']:r[st]=int(t.eq(st).sum())
   r['net_change']=r['witness_gained']-r['witness_lost'];pairrows.append(r)
  checks.append({'check':f'axis_order_equal_{y0}_{y1}','pass':bool(aa.id.equals(bb.id))})
 pd.DataFrame(pairrows).to_csv(a.out/'annual_and_benchmark_transitions.csv',index=False)
 pairframes=[]
 for y0,y1 in [(2011,2025),(2016,2021),(2021,2025)]:
  q=p[['id','lat','lon']].copy();q['quality_mode']=f'pinned_exact_{y0}_{y1}'
  for k,label in [(1,'any_direct_service'),(2,'diversification_ge2'),(3,'diversification_ge3')]:q[label+'_transition']=statust(tables[y0].direct_consumer_function_diversity>=k,tables[y1].direct_consumer_function_diversity>=k)
  pairframes.append(q)
 blockdir=a.out/'spatial_robustness';blockdir.mkdir(exist_ok=True);blockchecks=[];spatial(pd.concat(pairframes,ignore_index=True),blockdir,blockchecks);checks.extend(blockchecks)
 trajectory=p[['id','name','region','population_2010','population_2021','lat','lon']].copy()
 masks=np.stack([sum((tables[yr][g+'_legal_entities'].to_numpy()>0).astype(np.uint16)<<gi for gi,g in enumerate(DIRECT)) for yr in years],axis=1)
 pres=masks>0;changes=(pres[:,1:]!=pres[:,:-1]).sum(axis=1);anyw=pres.any(axis=1);allw=pres.all(axis=1);profile_changes=(masks[:,1:]!=masks[:,:-1]).sum(axis=1)
 first=np.where(anyw,np.argmax(pres,axis=1)+2011,-1);last=np.where(anyw,2025-np.argmax(pres[:,::-1],axis=1),-1)
 trajectory['n_years_direct_service_witness']=pres.sum(axis=1);trajectory['n_witness_presence_changes']=changes;trajectory['n_annual_profile_changes']=profile_changes
 trajectory['first_witness_year']=first;trajectory['last_witness_year']=last
 trajectory['direct_diversity_2011']=tables[2011].direct_consumer_function_diversity.to_numpy();trajectory['direct_diversity_2025']=tables[2025].direct_consumer_function_diversity.to_numpy()
 trajectory['witness_trajectory']=np.select([~anyw,allw&(profile_changes==0),allw&(profile_changes>0),(first>2011)&(last==2025)&(changes==1),(first==2011)&(last<2025)&(changes==1),(first>2011)&(last<2025)&(changes==2)],['no_accepted_service_witness_any_year','witness_all_years_unchanged_profile','witness_all_years_changed_profile','first_appearance_without_later_dropout','last_disappearance_without_return','one_internal_witness_episode'],default='intermittent_witness_evidence')
 trajectory['diversity_net_change']=trajectory.direct_diversity_2025-trajectory.direct_diversity_2011
 trajectory['population_bin_2021']=pd.cut(trajectory.population_2021,[-1,0,99,499,999,4999,19999,99999,np.inf],labels=['0','1–99','100–499','500–999','1000–4999','5000–19999','20000–99999','100000+']).astype('string').fillna('unknown')
 save(trajectory,a.out/'point_witness_trajectories_2011_2025')
 trajectory.groupby('witness_trajectory').size().rename('n_settlements').reset_index().to_csv(a.out/'trajectory_summary.csv',index=False)
 trajectory.groupby(['population_bin_2021','witness_trajectory'],observed=True).size().rename('n_settlements').reset_index().to_csv(a.out/'trajectory_by_population_size.csv',index=False)
 checks.append({'check':'full_fifteen_year_axis','pass':len(long)==15*142570 and not long.duplicated(['id','year']).any()})
 checks.append({'check':'trajectory_full_axis','pass':len(trajectory)==142570 and trajectory.id.is_unique})
 checks.append({'check':'all_acquisitions_same_pin','pass':all(s['pinned_dataset_commit']==PIN for s in sources.values())})
 dump(a.out/'AUDIT.json',{'checks':checks,'pass':all(x['pass'] for x in checks),'sources':sources,'panel_sha256':sha(pfile),'code_sha256':sha(Path(__file__)),'industry_harmonization_author_documented':True,'author_industry_harmonization_reexecuted':False,'actual_object_change_asserted':False,'fixed_code_reference_year':2021,'historical_code_crosswalk_proven':False})
 assert all(x['pass'] for x in checks)
 dump(a.out/'MANIFEST.json',{x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(a.out.iterdir()) if x.is_file() and x.name!='MANIFEST.json'})
 print(json.dumps({'checks':len(checks),'pass':True}))
if __name__=='__main__':main()
