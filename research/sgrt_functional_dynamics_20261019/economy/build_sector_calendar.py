#!/usr/bin/env python3
"""Broad industry-registration witnesses, complementary to narrow services."""
import argparse,json,time
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq
from build_dynamics import codes,sha,dump
PIN='bde9b8b129a8be582b66de4e30ed79c9187a8515'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path('.'));ap.add_argument('--out',type=Path,required=True);ap.add_argument('--wait-for-inputs',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 root=a.base/'functional_dynamics_20261019/economy';pp=a.base/'restored/extracted/research/sgrt_recovered_20261019/data/panel.parquet'
 p=pq.read_table(pp,columns=['id','oktmo_2021']).to_pandas();pc=codes(p.oktmo_2021);assert pc.is_unique and pc.notna().all();lookup=pd.Series(np.arange(len(p),dtype=np.int32),index=pc)
 lut={s:i+1 for i,s in enumerate('ABCDEFGHIJKLMNOPQRSTU')};checks=[];rows=[];sources={}
 for year in range(2011,2026):
  src=root/f'remote_selected/rfsd_{year}_identity_function_selected.parquet';au=root/f'remote_selected/{year}_acquisition.json';deadline=time.monotonic()+600
  while True:
   ac=json.loads(au.read_text()) if au.exists() else {}
   if src.exists() and ac.get('pinned_dataset_commit')==PIN:break
   if not a.wait_for_inputs or time.monotonic()>deadline:raise RuntimeError(f'No verified pinned input {year}')
   time.sleep(2)
  assert sha(src)==ac['selected_file_sha256'];counts=np.zeros((len(p),22),dtype=np.int64);accepted=0;total=0
  for b in pq.ParquetFile(src).iter_batches(batch_size=200000,columns=['inn','oktmo','okved_section']):
   d=b.to_pandas();total+=len(d);where=codes(d.oktmo).map(lookup).fillna(-1).astype(int).to_numpy();good=d.inn.str.fullmatch(r'\d{10}',na=False).to_numpy()&(where>=0);sec=d.okved_section.map(lut).fillna(0).astype(int).to_numpy()
   counts+=np.bincount(where[good]*22+sec[good],minlength=len(p)*22).reshape(len(p),22);accepted+=int(good.sum())
  f=p[['id']].copy();f['year']=year;f['quality_mode']='exact_settlement_code_only';f['legal_entities']=counts.sum(axis=1);f['unknown_section_legal_entities']=counts[:,0]
  for section,idx in lut.items():f[f'section_{section}_legal_entities']=counts[:,idx]
  f['registered_section_diversity']=(counts[:,1:]>0).sum(axis=1)
  dest=a.out/f'point_sector_witnesses_{year}.parquet';f.to_parquet(dest,index=False);pd.testing.assert_frame_equal(f,pq.read_table(dest).to_pandas())
  f.to_csv(a.out/f'point_sector_witnesses_{year}.csv.gz',index=False,compression='gzip')
  checks.append({'check':f'raw_sector_balance_{year}','pass':int(counts.sum())==accepted and len(f)==142570 and f.id.is_unique})
  for section,idx in [('UNKNOWN',0)]+list(lut.items()):rows.append({'year':year,'section':section,'legal_entities':int(counts[:,idx].sum()),'points_with_witness':int((counts[:,idx]>0).sum())})
  sources[str(year)]={'path':str(src),'sha256':ac['selected_file_sha256'],'rows':total,'columns_read':['inn','oktmo','okved_section']};print(f'Broad sectors complete: {year}; exact legal entities {accepted}',flush=True)
 pd.DataFrame(rows).to_csv(a.out/'national_sector_witnesses_2011_2025.csv',index=False)
 dump(a.out/'AUDIT.json',{'checks':checks,'pass':all(x['pass'] for x in checks),'pinned_dataset_commit':PIN,'sources':sources,'panel_sha256':sha(pp),'code_sha256':sha(Path(__file__)),'physical_activity_jobs_asserted':False,'classification':'RFSD harmonized primary industry section; UNKNOWN separate','reference_code_year':2021,'historical_crosswalk_proven':False});assert all(x['pass'] for x in checks)
 dump(a.out/'MANIFEST.json',{x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in a.out.iterdir() if x.is_file() and x.name!='MANIFEST.json'})
 print(json.dumps({'checks':len(checks),'pass':True}))
if __name__=='__main__':main()
