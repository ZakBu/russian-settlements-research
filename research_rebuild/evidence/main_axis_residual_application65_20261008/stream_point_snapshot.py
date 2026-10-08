"""Bound memory while preserving every active point field and authoritative source key."""
from pathlib import Path
import math
import pyarrow as pa
import pyarrow.parquet as pq
def textcell(v):
 if v is None:return ''
 if isinstance(v,float) and math.isnan(v):return ''
 return str(v)
def write_point_snapshot_from_active_rows(point_rows,path,batch_size=8192):
 columns=[];seen=set()
 for row in point_rows.values():
  for key in row:
   if key!='source_record_id' and key not in seen:columns.append(key);seen.add(key)
 columns.append('source_record_id');schema=pa.schema([(c,pa.string()) for c in columns]);writer=pq.ParquetWriter(str(path),schema,compression='zstd');batch=[];keys=set()
 try:
  for sid,row in point_rows.items():
   assert sid and sid not in keys;keys.add(sid);batch.append({**{c:textcell(row.get(c,'')) for c in columns if c!='source_record_id'},'source_record_id':sid})
   if len(batch)>=batch_size:writer.write_table(pa.Table.from_pylist(batch,schema=schema));batch=[]
  if batch:writer.write_table(pa.Table.from_pylist(batch,schema=schema))
 finally:writer.close()
 return keys
