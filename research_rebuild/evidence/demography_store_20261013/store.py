#!/usr/bin/env python3
"""Bounded-memory source-preserving demographic store; no NP allocation."""
import argparse,csv,hashlib,json,re,zipfile,shutil,time
from pathlib import Path
import duckdb,openpyxl,pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent
P=argparse.ArgumentParser();P.add_argument('--scratch',default='/workspace/scratch/demography-store-20261013');P.add_argument('--catalog',default=str(E.parent/'tochno_catalog_20261013'));P.add_argument('--bridge');P.add_argument('--source-root');P.add_argument('--np-id');P.add_argument('--build',action='store_true');P.add_argument('--validate',action='store_true');P.add_argument('--validate-indicator');P.add_argument('--resume-validation',action='store_true');P.add_argument('--arithmetic',action='store_true');P.add_argument('--numeric-audit',action='store_true');a=P.parse_args()
S=Path(a.scratch);S.mkdir(parents=True,exist_ok=True)
def q(x):return "'"+str(x).replace("'","''")+"'"
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
c=duckdb.connect(str(S/'demography.duckdb'));c.execute("SET memory_limit='2GB'");c.execute('SET threads=4');c.execute('SET temp_directory='+q(S/'tmp'))
if a.build:
 start=time.time();receipts=[];groups={};schemas={}
 catalog=Path(a.catalog)
 packaged=[]
 if a.source_root and (E/'store_receipts.json').exists():
  previous=json.load(open(E/'store_receipts.json'))
  if all((Path(a.source_root)/Path(r['store_path']).name).exists() for r in previous):
   for r in previous:
    r['packaged_store']=True;r['original_source_local_path']=r['local_path'];r['local_path']=str(Path(a.source_root)/Path(r['store_path']).name);packaged.append(r)
 if packaged:inputs=packaged
 else:
  inputs=json.load(open(catalog/'range_receipts.json'))
  if a.source_root:
   for r in inputs:r['original_local_path']=r['local_path'];r['local_path']=str(Path(a.source_root)/Path(r['local_path']).name)
  for r in json.load(open(catalog/'archive_receipts.json')):
   if not r.get('local_path'):continue
   if a.source_root:r['local_path']=str(Path(a.source_root)/Path(r['local_path']).name)
   assert sha(r['local_path'])==r['sha256'],f"Archive byte hash mismatch: {r['local_path']}"
   z=zipfile.ZipFile(r['local_path']);top=[n for n in z.namelist() if '/' not in n];member=next((n for n in top if n.endswith('.parquet')),None) or next(n for n in top if n.endswith('.csv'))
   dst=S/member
   if not dst.exists():
    with z.open(member) as src,open(dst,'wb') as out:shutil.copyfileobj(src,out)
   inputs.append(dict(local_path=str(dst),source_url=r['url'],member=member,archive_path=r['local_path'],archive_sha256=r['sha256'],member_sha256=sha(dst)))
 for r in inputs:
  p=Path(r['local_path']);assert (sha(p)==r['store_sha256'] if r.get('packaged_store') else (not r.get('source_sha256_verified') or r.get('member_sha256') or sha(p)==r['member_sha256'])),f'Byte hash mismatch: {p}';code=re.search('Y\\d+',p.name).group();out=p
  physical=empty=None
  if p.suffix=='.csv':
   out=S/(p.stem+'.parquet')
   if not out.exists():c.execute(f"COPY (SELECT * FROM read_csv({q(p)},delim=';',header=true,all_varchar=true)) TO {q(out)} (FORMAT PARQUET,COMPRESSION ZSTD)")
  elif p.suffix=='.xlsx':
   out=S/(p.stem+'.parquet')
   if out.exists():
    w=openpyxl.load_workbook(p,read_only=True,data_only=True);physical=w.worksheets[0].max_row-1;w.close();empty=physical-c.sql(f'select count(*) from read_parquet({q(out)})').fetchone()[0]
   else:
    w=openpyxl.load_workbook(p,read_only=True,data_only=True);s=w.worksheets[0];it=s.iter_rows(values_only=True);heads=[str(v) for v in next(it)];schema=pa.schema([(h,pa.string()) for h in heads]);writer=pq.ParquetWriter(out,schema,compression='zstd');batch=[];physical=empty=0
    for row in it:
     physical+=1
     if all(v is None for v in row):empty+=1;continue
     batch.append({h:None if v is None else str(v) for h,v in zip(heads,row)})
     if len(batch)>=10000:writer.write_table(pa.Table.from_pylist(batch,schema=schema));batch=[]
    if batch:writer.write_table(pa.Table.from_pylist(batch,schema=schema))
    writer.close();w.close()
  cols=c.sql(f'describe select * from read_parquet({q(out)})').fetchall();schemas[code]=[x[0] for x in cols]
  expr=','.join('CAST("'+x[0]+'" AS VARCHAR) AS "'+x[0]+'"' for x in cols)
  # Locator is the immutable member plus the Parquet physical row index.
  select=f"SELECT {expr}, CASE WHEN isfinite(try_cast(indicator_value AS DOUBLE)) THEN try_cast(indicator_value AS DOUBLE) ELSE NULL END AS value_numeric,try_cast(year AS INTEGER) AS source_year,CASE WHEN regexp_full_match(cast(oktmo as varchar),'[0-9]{{7,8}}') THEN lpad(cast(oktmo as varchar),8,'0') ELSE NULL END AS municipality_code8,'20260928' AS source_version,{q(r.get('original_source_local_path',str(p))+'::'+r.get('member',p.name))} AS source_member,{q(out)} AS store_path,{q(r.get('source_url',''))} AS source_url,{q(r.get('source_sha256_verified') or r.get('member_sha256') or sha(p))} AS source_byte_sha256,file_row_number AS source_row_0based,source_member || '#store_row0=' || cast(file_row_number AS VARCHAR) AS source_locator FROM read_parquet({q(out)},file_row_number=true)"
  groups.setdefault(code,[]).append(select)
  actual=c.sql(f'select count(*),count(*) filter(where isfinite(try_cast(indicator_value as double))),min(try_cast(year as integer)),max(try_cast(year as integer)) from read_parquet({q(out)})').fetchone()
  receipts.append({**r,'actual_rows':actual[0],'actual_nonnull_values':actual[1],'year_min':actual[2],'year_max':actual[3],'store_path':str(out),'store_sha256':sha(out),'source_sha256_verified':r.get('source_sha256_verified') or sha(p),'xlsx_physical_data_rows':physical if physical is not None else r.get('xlsx_physical_data_rows'),'xlsx_skipped_empty_rows':empty if empty is not None else r.get('xlsx_skipped_empty_rows'),'columns':[x[0] for x in cols]})
  print(code,p.name,actual,flush=True)
 views=[]
 for code,selects in sorted(groups.items()):
  name='dataset_'+code;c.execute('CREATE OR REPLACE VIEW '+name+' AS '+' UNION ALL BY NAME '.join(selects));views.append('select * from '+name)
 c.execute('CREATE OR REPLACE VIEW demographic_context AS '+' UNION ALL BY NAME '.join(views))

 c.execute(f"COPY (select indicator_code,indicator_name,source_year,mun_level,count(*) AS row_count,count(value_numeric) nonnull_values,count(*)-count(value_numeric) unknown_values,count(*) filter(where value_numeric=0) zero_values from demographic_context group by all order by indicator_code,source_year,mun_level) TO {q(E/'data_profile.csv')} (HEADER,DELIMITER ',')")
 c.execute(f"COPY (select indicator_code,indicator_name,sum(row_count) AS row_count,sum(nonnull_values) nonnull_values,min(source_year) year_min,max(source_year) year_max from read_csv({q(E/'data_profile.csv')},header=true) group by all order by indicator_code) TO {q(E/'indicator_inventory.csv')} (HEADER,DELIMITER ',')")
 json.dump(receipts,open(E/'store_receipts.json','w'),ensure_ascii=False,indent=2);json.dump(schemas,open(E/'schemas.json','w'),ensure_ascii=False,indent=2)
 json.dump({'datasets':len(groups),'rows':sum(r['actual_rows'] for r in receipts),'nonnull_values':sum(r['actual_nonnull_values'] for r in receipts),'seconds':time.time()-start,'database':str(S/'demography.duckdb')},open(E/'run_receipt.json','w'),indent=2)
for name,definition in c.sql("select view_name,sql from duckdb_views() where view_name like 'dataset_Y%'").fetchall():
 if '[0-9](7, 8)' in definition:
  c.execute(definition.replace('CREATE VIEW','CREATE OR REPLACE VIEW',1).replace('[0-9](7, 8)','[0-9]{7,8}'))
if 'source_locator' not in [r[0] for r in c.sql('describe demographic_context').fetchall()]:
 old=c.sql("select sql from duckdb_views() where view_name='demographic_context'").fetchone()[0].split(' AS ',1)[1].rstrip(';')
 c.execute("CREATE OR REPLACE VIEW demographic_context AS SELECT *,source_member || '#store_row0=' || cast(source_row_0based AS VARCHAR) AS source_locator FROM ("+old+")")
raw_value="try_cast(indicator_value AS DOUBLE)"
locator_sql="" if 'source_locator' in [r[0] for r in c.sql('describe demographic_context').fetchall()] else "source_member || '#store_row0=' || CAST(source_row_0based AS VARCHAR) AS source_locator,"
status=f"CASE WHEN {raw_value} IS NULL THEN 'unknown_or_non_numeric' WHEN NOT isfinite({raw_value}) THEN 'nonfinite' WHEN {raw_value}<0 AND indicator_code NOT IN ('Y48112004','Y48112009','Y48112023') THEN 'invalid_negative' WHEN indicator_code IN ('Y48112014','Y48112015','Y48112016','Y48112025','Y48112027') AND {raw_value}>300000000 THEN 'invalid_stock_upper_bound' ELSE 'numeric_source_observation' END"
c.execute(f"CREATE OR REPLACE VIEW municipal_context AS SELECT *, {raw_value} AS source_value_numeric, {locator_sql} {status} AS value_status, CASE WHEN ({status})='numeric_source_observation' THEN {raw_value} ELSE NULL END AS usable_value, TRUE AS context_only, (oktmo_history IS NOT NULL AND oktmo_history<>'') AS source_admin_history_present,regexp_matches(coalesce(oktmo_history,''),'Объедин|Раздел|объедин|раздел') AS explicit_boundary_change_requires_review,(source_year BETWEEN try_cast(oktmo_year_from AS INTEGER) AND try_cast(oktmo_year_to AS INTEGER)) AS source_year_within_code_period, ({status}) IN ('nonfinite','invalid_negative','invalid_stock_upper_bound') AS source_numeric_sanity_flag FROM demographic_context")
if a.numeric_audit:
 numeric=[]
 for code in sorted(json.load(open(E/'schemas.json'))):
  r=c.sql(f"select count(*),count(raw_value),count(*) filter(where NOT isfinite(raw_value)),count(*) filter(where raw_value<0),min(raw_value),max(raw_value),count(*) filter(where value_status IN ('invalid_negative','invalid_stock_upper_bound')),count(*) filter(where value_status='numeric_source_observation') from (select {raw_value} AS raw_value,{status} AS value_status from dataset_{code})").fetchone()
  numeric.append(dict(indicator_code=code,rows=r[0],numeric_nonnull_values=r[1],nonfinite_values=r[2],negative_values=r[3],min_value=r[4],max_value=r[5],source_domain_invalid_values=r[6],usable_numeric_rows=r[7]))
 c.execute(f"COPY (SELECT * FROM municipal_context WHERE source_numeric_sanity_flag) TO {q(E/'numeric_anomalies.csv')} (HEADER,DELIMITER ',')")
 with open(E/'numeric_validity.csv','w') as f:
  wr=csv.DictWriter(f,fieldnames=list(numeric[0]));wr.writeheader();wr.writerows(numeric)
 c.execute(f"COPY (SELECT indicator_code,indicator_name,source_year,mun_level,count(*) row_count,count(source_value_numeric) nonnull_values,count(*)-count(source_value_numeric) unknown_values,count(*) filter(where source_value_numeric=0) zero_values,count(*) filter(where value_status IN ('invalid_negative','invalid_stock_upper_bound')) source_domain_invalid_values,count(usable_value) usable_values FROM municipal_context GROUP BY ALL ORDER BY indicator_code,source_year,mun_level) TO {q(E/'usable_data_profile.csv')} (HEADER,DELIMITER ',')")
if a.validate:
 stats=[];completed=[]
 if a.resume_validation:
  completed=json.load(open(E/'duplicate_scan_status.json'))['completed_indicators'];stats=list(csv.DictReader(open(E/'candidate_key_duplicates.csv')))

 if a.validate_indicator and (E/'candidate_key_duplicates.csv').exists():
  stats=[r for r in csv.DictReader(open(E/'candidate_key_duplicates.csv')) if r['indicator_code']!=a.validate_indicator]
 for code in sorted(json.load(open(E/'schemas.json'))):
  if code in completed or (a.validate_indicator and code!=a.validate_indicator):continue
  view='dataset_'+code
  columns=[r[0] for r in c.sql('describe '+view).fetchall()]
  dims=[x for x in ['grup_2','vozr','migr','nazsostv','mest'] if x in columns]
  keys=['oktmo','source_year','mun_level','indicator_unit','indicator_period']+dims
  key=','.join('"'+x+'"' for x in keys)
  sources=[r for r in json.load(open(E/'store_receipts.json')) if code in Path(r['store_path']).name]
  separated_years=len(sources)>1 and all(r['year_min']==r['year_max'] for r in sources) and len({r['year_min'] for r in sources})==len(sources)
  selections=[]
  if separated_years:
   category_cols=[x for x in keys if x not in ['oktmo','source_year']]
   literal_rows=c.sql('select distinct '+','.join('"'+x+'"' for x in category_cols)+' from '+view).fetchall()
   dictionaries={x:sorted({row[n] for row in literal_rows if row[n] is not None}) for n,x in enumerate(category_cols)}
   # Exact bijective ENUM encoding avoids millions of copied long label strings.
   projection=['cast(oktmo as varchar) AS oktmo','try_cast(year as integer) AS source_year','try_cast(indicator_value as double) AS value_numeric']
   for x,values in dictionaries.items():projection.append(('CAST("'+x+'" AS ENUM('+','.join(q(v) for v in values)+'))' if values else 'cast("'+x+'" as varchar)')+' AS "'+x+'"')

   for src in sources:
    # Each immutable year member is read once; candidate year keys cannot cross parts.
    selections.append(f"(SELECT {','.join(projection)} FROM read_parquet({q(src['store_path'])}))")
  else:selections=[view]
  results=[]
  for selection in selections:
   results+=c.sql(f"select source_year,count(*),coalesce(sum(n-1),0),count(*) filter(where value_conflict) from (select {key},count(*) n,(coalesce(min(value_numeric)<>max(value_numeric),false) OR (count(value_numeric)>0 AND count(value_numeric)<count(*))) AS value_conflict from {selection} group by {key} having count(*)>1) group by source_year order by source_year").fetchall()
  for year,ng,extra,conf in results:stats.append(dict(indicator_code=code,year=year,duplicate_key_groups=ng,extra_rows=extra,conflicting_value_groups=conf,candidate_key=key))
  completed.append(code)
  with open(E/'candidate_key_duplicates.csv','w') as f:
   wr=csv.DictWriter(f,fieldnames=['indicator_code','year','duplicate_key_groups','extra_rows','conflicting_value_groups','candidate_key']);wr.writeheader();wr.writerows(stats)
  json.dump(dict(completed_indicators=completed,complete=len(completed)==16),open(E/'duplicate_scan_status.json','w'),indent=2)
  print('validated',code,results,flush=True)
 with open(E/'candidate_key_duplicates.csv','w') as f:
  wr=csv.DictWriter(f,fieldnames=['indicator_code','year','duplicate_key_groups','extra_rows','conflicting_value_groups','candidate_key']);wr.writeheader();wr.writerows(stats)
if a.arithmetic or (a.validate and not a.validate_indicator):
 checks=[]
 for left,right,net in ([] if a.validate_indicator else [('Y48112003','Y48112001','Y48112004'),('Y48112021','Y48112022','Y48112023')]):
  cols=[r[0] for r in c.sql('describe dataset_'+left).fetchall()]
  dims=[x for x in ['grup_2','vozr','migr','nazsostv','mest'] if x in cols]
  keys=['oktmo','source_year','mun_level','indicator_unit','indicator_period','oktmo_stable','oktmo_year_from','oktmo_year_to']+dims
  key=','.join('"'+x+'"' for x in keys)
  # Only keys occurring once in each complete source qualify; null value stays unknown.
  for code in [left,right,net]:
   c.execute(f"create or replace temp view check_{code} as select {key},max(value_numeric) v from dataset_{code} group by {key} having count(*)=1 and count(value_numeric)=1 and isfinite(max(value_numeric))"+(' and max(value_numeric)>=0' if code in [left,right] else ''))
  join=' AND '.join(f'a."{k}" IS NOT DISTINCT FROM b."{k}"' for k in keys)
  join2=' AND '.join(f'a."{k}" IS NOT DISTINCT FROM d."{k}"' for k in keys)
  profile=list(csv.DictReader(open(E/'data_profile.csv')))
  years=sorted({int(r['source_year']) for r in profile if r['indicator_code']==left})
  per_year=[]
  for year in years:
   r=c.sql(f'select count(*),count(*) filter(where abs(a.v-b.v-d.v)>0.000001),max(abs(a.v-b.v-d.v)) from check_{left} a join check_{right} b on {join} join check_{net} d on {join2} where a.source_year={year} AND b.source_year={year} AND d.source_year={year}').fetchone()
   per_year.append(dict(year=year,unique_matching_nonnull_keys=r[0],mismatches=r[1],max_abs_error=r[2]));print('arithmetic',left,year,r,flush=True)
  checks.append(dict(left=left,right=right,net=net,unique_matching_nonnull_keys=sum(r['unique_matching_nonnull_keys'] for r in per_year),mismatches=sum(r['mismatches'] for r in per_year),max_abs_error=max((r['max_abs_error'] for r in per_year if r['max_abs_error'] is not None),default=None),key=keys,per_year=per_year))
 if checks:json.dump(checks,open(E/'arithmetic_checks.json','w'),ensure_ascii=False,indent=2)
if a.bridge:
 c.execute('CREATE OR REPLACE VIEW np_municipality_bridge AS SELECT * FROM read_csv('+q(a.bridge)+',header=true,all_varchar=true,delim='+q(',')+',quote='+q(chr(34))+',escape='+q(chr(34))+')')
if a.np_id:
 # Filter bridge first; no materialized Cartesian settlement/fact table.
 sql="WITH selected AS (SELECT * FROM np_municipality_bridge WHERE source_record_id=? AND context_status='exact_unique_source_context'),raw_codes AS (SELECT municipality_oktmo_code8 code FROM selected UNION SELECT substr(municipality_oktmo_code8,2) FROM selected WHERE substr(municipality_oktmo_code8,1,1)='0') SELECT b.*,m.* FROM selected b JOIN municipal_context m ON m.municipality_code8=b.municipality_oktmo_code8 AND ((b.municipality_role='upper' AND m.mun_level='Муниципальное образование верхнего уровня') OR (b.municipality_role='lower' AND m.mun_level='Муниципальное образование нижнего уровня')) WHERE m.oktmo IN (SELECT code FROM raw_codes)"
 rows=c.execute(sql,[a.np_id]).fetch_record_batch(10000)
 summary={}
 with open(S/'np_context.jsonl','w') as f:
  for batch in rows:
   for row in batch.to_pylist():
    assert row['context_only'] is True
    f.write(json.dumps(row,ensure_ascii=False)+'\n')
    code=row['indicator_code'];d=summary.setdefault(code,dict(rows=0,nonnull_values=0,source_years=set(),municipality_codes=set()));d['rows']+=1;d['nonnull_values']+=int(row['value_numeric'] is not None);d['source_years'].add(row['source_year']);d['municipality_codes'].add(row['municipality_code8'])
 for d in summary.values():d['source_years']=sorted(d['source_years']);d['municipality_codes']=sorted(d['municipality_codes'])
 json.dump(dict(source_record_id=a.np_id,bridge=a.bridge,context_only=True,historical_np_membership_asserted=False,output=str(S/'np_context.jsonl'),output_sha256=sha(S/'np_context.jsonl'),indicators=summary),open(E/'np_query_smoke.json','w'),ensure_ascii=False,indent=2)
 print(S/'np_context.jsonl')
with open(E/'views.sql','w') as f:
 for (sql,) in c.sql("select sql from duckdb_views() where not internal and not temporary order by view_name").fetchall():f.write(sql+'\n')
c.close()
