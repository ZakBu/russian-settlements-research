#!/usr/bin/env python3
"""Independent read-only verification of the restored source axis."""
from pathlib import Path
import hashlib,json
import pandas as pd
import pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MASTER=ROOT/'research/sgrt_national_integration_20261019/core/feature_master.parquet'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def main():
 before=sha(MASTER)
 cols=['id','name','type','region','lat','lon']+[f'population_{y}' for y in [2002,2010,2021,1989]]
 df=pd.read_parquet(MASTER,columns=cols)
 n=len(df);checks={
 'master_expected_sha':before=='8c98d5a113eec4c3bf131232b1d7e5c6362dc3a50ee484e964420de58c377f85',
 'rows_142570':n==142570,
 'columns_914':len(pq.ParquetFile(MASTER).schema_arrow.names)==914,
 'id_unique':bool(df.id.is_unique),
 'id_nonnull':bool(df.id.notna().all()),
 'coordinates_nonnull':bool(df[['lat','lon']].notna().all().all()),
 'lat_range':bool(df.lat.between(-90,90).all()),
 'lon_range':bool(df.lon.between(-180,180).all()),
 'census2010_zeros_retained':int(df.population_2010.eq(0).sum())==21246,
 }
 population={str(y):{'sum':int(df[f'population_{y}'].sum()),'nonmissing':int(df[f'population_{y}'].notna().sum()),'zeros':int(df[f'population_{y}'].eq(0).sum()),'negative':int(df[f'population_{y}'].lt(0).sum())} for y in [2002,2010,2021,1989]}
 checks['no_negative_population']=all(x['negative']==0 for x in population.values())
 after=sha(MASTER);checks['input_unchanged_during_independent_read']=before==after
 result={'role':'independent Word-concept guardian','source':str(MASTER.relative_to(ROOT)),'sha256_before':before,'sha256_after':after,'rows':n,'columns':914,'population':population,'checks':checks,'all_pass':all(checks.values()),'scope':'Source-axis integrity only; does not establish comparability of boundaries or actual functional catchments'}
 (HERE/'independent_input_axis_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
