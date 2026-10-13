#!/usr/bin/env python3
"""Exact cell lookup preserves published zero and suppression; absence is not zero."""
import argparse,json,math,hashlib
import duckdb
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--version',choices=['frozen','latest'],default='frozen');p.add_argument('--source-record-id',required=True);p.add_argument('--field',required=True);p.add_argument('--wide-root',default='/workspace/scratch/tochno-np-attach-20261013');a=p.parse_args();path=Path(a.wide_root)/('native_np_'+a.version+'_all_attributes.parquet');prefix='tochno_'+a.version+'__';c=duckdb.connect();cols=[x[0] for x in c.execute('describe select * from read_parquet(?)',[str(path)]).fetchall()];field=a.field if a.field.startswith(prefix) else prefix+a.field
inventory=json.load(open(Path(__file__).resolve().parent/'schema_inventory.json'))
if field not in inventory[a.version]['structure_fields']:raise ValueError('Field is not a published NP structure count')
if field not in cols:raise ValueError('No such published source field')
ident=lambda s:'"'+s.replace('"','""')+'"'
rows=c.execute('select source_record_id,root,'+ident(prefix+'object_level')+','+ident(field)+' from read_parquet(?) where source_record_id=?',[str(path),a.source_record_id]).fetchall()
out=[]
for uid,root,level,value in rows:
 status='aggregate_scope_blocked' if level!='Населенный пункт' else 'unknown' if value is None else 'nonfinite' if not math.isfinite(value) else 'suppressed_minus9' if value==-9 else 'invalid_negative' if value<0 else 'invalid_noninteger_count' if value!=int(value) else 'published_count'
 out.append(dict(source_record_id=uid,root=root,observation_year=2021,source_field=a.field,source_value_numeric=value,value_status=status,usable_value=value if status=='published_count' else None,canonical=a.version=='frozen',municipality_allocation=False))
print(json.dumps(out,ensure_ascii=False))
