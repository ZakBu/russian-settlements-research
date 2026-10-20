#!/usr/bin/env python3
"""Conservative year-round static car profile; retain unfiltered accepted ways for replay."""
from pathlib import Path
from collections import Counter
import json,time
import pyarrow as pa,pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_transport');start=time.time();source=RAW/'road_ways_all_static.parquet'
if not source.exists():(RAW/'road_ways.parquet').rename(source)
pf=pq.ParquetFile(source);temp=RAW/'road_ways_yearround.tmp.parquet';writer=pq.ParquetWriter(temp,pf.schema_arrow,compression='zstd');removed=[];counts=Counter();n=0
for b in pf.iter_batches(batch_size=20000):
 rows=[]
 for r in b.to_pylist():
  t=json.loads(r['tags']);reasons=[]
  for k in ['winter_road','ice_road']:
   if t.get(k,'').lower() in {'yes','1','true'}:reasons.append(k)
  if t.get('seasonal','').strip().lower() not in {'','no','0','false'}:reasons.append('seasonal')
  for k in ['access:conditional','motor_vehicle:conditional','motorcar:conditional']:
   if t.get(k,'').strip():reasons.append(k)
  if reasons:removed.append({'way_id':r['way_id'],'reasons':';'.join(reasons),'tags':r['tags']});counts.update(reasons)
  else:rows.append(r)
 if rows:writer.write_table(pa.Table.from_pylist(rows,schema=pf.schema_arrow));n+=len(rows)
writer.close();temp.replace(RAW/'road_ways.parquet');pq.write_table(pa.Table.from_pylist(removed),ROOT/'excluded_seasonal_conditional_ways.parquet',compression='zstd');receipt={'status':'FILTERED_YEARROUND_CONSERVATIVE','accepted_ways':n,'excluded_unique_ways':len(removed),'exclusion_reason_counts':dict(counts),'policy':'Exclude explicit winter/ice roads, all non-no seasonal values, and any motorcar/motor_vehicle/general access conditional tag. Keep raw accepted static ways separately. Seasonal absence is not proof of year-round operation.','unfiltered_access_repaired_raw':str(source),'seconds':time.time()-start};(ROOT/'yearround_profile_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2),flush=True)
