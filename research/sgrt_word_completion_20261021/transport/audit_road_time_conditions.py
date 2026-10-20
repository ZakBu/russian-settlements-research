#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import json
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_transport');counts=Counter();values=Counter();examples=[]
for b in pq.ParquetFile(RAW/'road_ways.parquet').iter_batches(batch_size=50000,columns=['way_id','tags']):
 for row in b.to_pylist():
  t=json.loads(row['tags']);flags=[]
  for k in ('seasonal','winter_road','ice_road','access:conditional','motorcar:conditional','motor_vehicle:conditional','opening_hours','maxspeed:conditional','oneway:conditional'):
   if k in t:counts[k]+=1;values[k+'='+t[k]]+=1;flags.append(k)
  if flags and len(examples)<100:examples.append({'way_id':row['way_id'],'tags':t})
result={'status':'AUDITED','way_counts_with_time_condition_tags':dict(counts),'common_values':dict(values.most_common(100)),'examples':examples,'policy':'Primary graph is static topology; conditional/seasonal access and speed are not evaluated. Do not interpret its routes as year-round or date-specific operational availability.'};(ROOT/'road_temporal_conditions_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(dict(counts)))
