#!/usr/bin/env python3
"""Independent verification that sector outputs preserve the fixed settlement axis."""
from pathlib import Path
import json,hashlib
import pandas as pd
HERE=Path(__file__).resolve().parent
RUN=HERE.parent
REPO=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 master=REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet'
 axis=pd.read_parquet(master,columns=['id'])
 result={'axis_sha256':sha(master),'sectors':{},'scope':'Key integrity only, no assertion of national school/medical/trade completeness'}
 for sector in ['education','medical','commerce']:
  p=RUN/sector/'settlement_features.parquet'
  if not p.exists():
   result['sectors'][sector]={'status':'NOT_YET_AVAILABLE'};continue
  df=pd.read_parquet(p)
  checks={'row_count':len(df)==len(axis),'id_unique':df.id.is_unique,'id_nonnull':df.id.notna().all(),'ids_equal':set(df.id)==set(axis.id),'id_order_preserved':df.id.equals(axis.id)}
  result['sectors'][sector]={'status':'PASS' if all(checks.values()) else 'FAIL','rows':len(df),'columns':len(df.columns),'sha256':sha(p),'checks':{k:bool(v) for k,v in checks.items()}}
 result['all_available_pass']=all(v['status'] in ['PASS','NOT_YET_AVAILABLE'] for v in result['sectors'].values())
 (HERE/'independent_sector_axis_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
