"""Sparse optional metadata hydration; preserve every populated source field."""
import pyarrow.parquet as pq
CORE={'target_source_record_id','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','point_ledger_path'}
def hydrate_active_point_rows(path,accepted_statuses,batch_size=8192):
 rows={};omitted=0;populated=0
 for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
  for original in batch.to_pylist():
   sid=original['source_record_id'];assert sid and sid not in rows
   assert original['coordinate_admission_status'] in accepted_statuses
   kept={k:v for k,v in original.items() if k!='source_record_id' and (k in CORE or v not in ['',None])}
   for k,v in original.items():
    if k=='source_record_id':continue
    assert kept.get(k,'')==(v if v is not None else ''),'source metadata equality failed'
    if k not in kept:omitted+=1
    elif v not in ['',None]:populated+=1
   kept['latitude'],kept['longitude']=float(kept['latitude']),float(kept['longitude']);rows[sid]=kept
 return rows,{'source_rows':len(rows),'batch_size':batch_size,'populated_metadata_fields_retained':populated,'only_empty_optional_fields_omitted':omitted,'all_source_fields_equal_under_empty_optional_absence_semantics':True}
