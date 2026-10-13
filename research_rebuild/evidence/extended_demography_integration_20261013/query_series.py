"""Query census and extended claims separately; never replace census observations."""
import argparse,json,math
from pathlib import Path
import duckdb
p=argparse.ArgumentParser();p.add_argument('--census',type=Path,required=True);p.add_argument('--history',type=Path);p.add_argument('--primary',type=Path,action='append',default=[]);p.add_argument('--source-record-id',required=True);a=p.parse_args()
c=duckdb.connect();c.execute("SET memory_limit='1GB'")
root=c.execute('select root from read_parquet(?) where source_record_id=?',[str(a.census),a.source_record_id]).fetchone()
if not root:raise SystemExit('Не найден исходный UID; название не используется как глобальный идентификатор.')
census=c.execute('select * from read_parquet(?) where root=? order by census_year',[str(a.census),root[0]]).fetchdf().to_dict('records')
result={'root':root[0],'census_records':census,'extended_claims':[],'census_values_replaced':False,'historical_boundary_comparability':'UNKNOWN'}
for kind,path in [('secondary_history',a.history)]+[('primary_named_city_history',v) for v in a.primary]:
 if path:
  names=[r[0] for r in c.execute('describe select * from read_parquet(?)',[str(path)]).fetchall()]
  if 'root' not in names:raise SystemExit('Расширение должно явно содержать root; нельзя соединять только по названию.')
  anchors=[r['source_record_id'] for r in census]
  placeholders=','.join('?' for _ in anchors)
  values=c.execute('select * from read_parquet(?) where anchor_source_record_id IN ('+placeholders+')',[str(path)]+anchors).fetchdf().to_dict('records')
  result['extended_claims'].extend({'claim_kind':kind,**r} for r in values)
def clean(x):
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 if isinstance(x,float) and not math.isfinite(x):return None
 return x
print(json.dumps(clean(result),ensure_ascii=False,default=str,allow_nan=False,indent=2))
