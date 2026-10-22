#!/usr/bin/env python3
"""Re-run the real nationwide assembly in a fresh directory; compare every cell."""
from pathlib import Path
import tempfile,subprocess,sys,json,hashlib,time
import pyarrow.parquet as pq

H=Path(__file__).resolve().parent
start=time.monotonic()
with tempfile.TemporaryDirectory(dir=H,prefix='.national_replay_') as tmp:
    cmd=[sys.executable,str(H/'build_feature_master.py'),'--out-dir',tmp,'--no-csv']
    r=subprocess.run(cmd,capture_output=True,text=True)
    (H/'REPRODUCTION_COMMAND.log').write_text(r.stdout+'\n'+r.stderr)
    assert r.returncode==0,{'returncode':r.returncode,'stderr':r.stderr}
    expected=H/'feature_master.parquet';got=Path(tmp)/'feature_master.parquet'
    schema_a=pq.read_schema(expected).remove_metadata();schema_b=pq.read_schema(got).remove_metadata()
    assert schema_a.equals(schema_b),'Fresh assembly differs in Arrow schema'
    n=pq.ParquetFile(expected).metadata.num_rows
    assert pq.ParquetFile(got).metadata.num_rows==n
    for i in range(0,len(schema_a.names),16):
        cols=schema_a.names[i:i+16]
        a=pq.read_table(expected,columns=cols).replace_schema_metadata(None);b=pq.read_table(got,columns=cols).replace_schema_metadata(None)
        assert a.equals(b),('Fresh assembly differs in at least one typed cell',cols)
        del a,b
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    receipt={'status':'PASS','actual_command':cmd,'fresh_directory_recomputation':True,'all_arrow_columns_types_nulls_and_values_exact':True,'comparison_mode':'16_column_blocks_all_rows_all_columns','rows':n,'columns':len(schema_a.names),'expected_parquet_sha256':sha(expected),'reproduced_parquet_sha256':sha(got),'parquet_bytes_identical':sha(expected)==sha(got),'elapsed_seconds':time.monotonic()-start,'csv_replay_omitted':'Authoritative Parquet all-cell reproduction; primary CSV.gz separately checked for complete UID/order.'}
    (H/'REPRODUCTION.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
