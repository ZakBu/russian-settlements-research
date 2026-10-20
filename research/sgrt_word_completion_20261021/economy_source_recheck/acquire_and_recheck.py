#!/usr/bin/env python3
"""Independently refetch the pinned RFSD2021 source and check accepted own-code legal counts."""
from pathlib import Path
import json,hashlib,time,requests
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent
PIN='bde9b8b129a8be582b66de4e30ed79c9187a8515'
URL=f'https://huggingface.co/datasets/irlspbru/RFSD/resolve/{PIN}/RFSD/year=2021/part-0.parquet?download=true'
EXPECTED='9c19741d3c85428e79d5f9eedd08aa0422fedfef6bdc0a1c02b70e4d735e6f7f'
CACHE=Path('/workspace/scratch/sgrt_economy_recheck');CACHE.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 raw=CACHE/'RFSD_2021_full.parquet';receipt={'url':URL,'pinned_revision':PIN,'expected_full_sha256':EXPECTED,'target':'legal registered entity code witnesses, not jobs or physical establishments'}
 if not raw.exists() or sha(raw)!=EXPECTED:
  temp=raw.with_suffix('.downloading')
  try:
   t=time.monotonic()
   offset=temp.stat().st_size if temp.exists() else 0
   headers={'Range':f'bytes={offset}-'} if offset else {}
   with requests.get(URL,headers=headers,stream=True,timeout=(15,30)) as response:
    response.raise_for_status();receipt['http_status']=response.status_code
    append=offset>0 and response.status_code==206
    if append:assert response.headers.get('Content-Range','').startswith(f'bytes {offset}-')
    with temp.open('ab' if append else 'wb') as f:
     for chunk in response.iter_content(1024*1024):
      f.write(chunk)
      if time.monotonic()-t>600:raise TimeoutError('Resumable whole-file acquisition exceeded600seconds')
   receipt['received_bytes']=temp.stat().st_size;receipt['received_sha256']=sha(temp)
   assert receipt['received_bytes']==547323604 and receipt['received_sha256']==EXPECTED,'Incomplete or changed pinned source'
   temp.replace(raw)
  except Exception as e:
   receipt.update(status='ACQUISITION_FAILED_NOT_REVERIFIED',error=str(e));(OUT/'source_recheck_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2));return
 receipt['verified_full_source_sha256']=sha(raw)
 # Syntax-valid INN10 matches the inherited row-universe definition; no checksum invention.
 counts={};valid=0;invalid=0;total=0
 for batch in pq.ParquetFile(raw).iter_batches(columns=['inn','oktmo'],batch_size=200000):
  d=batch.to_pandas();total+=len(d);inn=d.inn.astype('string').str.strip();keep=inn.str.fullmatch(r'\d{10}',na=False);valid+=int(keep.sum());invalid+=int((~keep).sum())
  c=d.loc[keep,'oktmo'].astype('string').str.strip();c=c.where(c.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
  for code,n in c.value_counts().items():counts[code]=counts.get(code,0)+int(n)
 axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet',columns=['id','oktmo_2021'])
 master_path=ROOT.parents[0]/'sgrt_national_integration_20261019/core/feature_master.parquet'
 master=pd.read_parquet(master_path,columns=['id','econ_native_2021_legal_entities'])
 a=axis.merge(master,on='id',validate='one_to_one',how='inner');codes=a.oktmo_2021.astype('string').str.strip();codes=codes.where(codes.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
 assert codes.notna().all() and codes.is_unique
 a['recomputed_legal_entities2021']=codes.map(counts).fillna(0).astype('int64');a['agrees']=a.recomputed_legal_entities2021.eq(a.econ_native_2021_legal_entities)
 a.to_parquet(OUT/'own_code_legal_entities2021_recheck.parquet',index=False)
 receipt.update(status='COMPUTED_INDEPENDENT_PINNED_SOURCE_RECHECK',source_rows=total,valid_INN_syntax_rows=valid,invalid_INN_syntax_rows=invalid,axis_comparisons=len(a),all_values_agree=bool(a.agrees.all()),disagreements=int((~a.agrees).sum()),reference_code_year=2021,historical_code_continuity_proven=False,physical_function_or_jobs_observed=False,master_sha256=sha(master_path))
 (OUT/'source_recheck_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2));assert a.agrees.all()
if __name__=='__main__':main()
