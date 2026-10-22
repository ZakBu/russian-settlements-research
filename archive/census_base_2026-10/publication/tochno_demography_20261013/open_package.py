"""Open the portable Tochno enrichment without materializing NP x municipal facts."""
import argparse,csv,hashlib,json,re,sys
from pathlib import Path
import duckdb

def literal(v):return "'"+str(v).replace("'","''")+"'"
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def open_db(root,verify=False):
 manifest=json.loads((root/'package_manifest.json').read_text())
 if verify:
  for rel,meta in manifest['files'].items():
   p=root/rel;assert p.stat().st_size==meta['bytes'] and sha(p)==meta['sha256'],rel
 c=duckdb.connect();c.execute("SET memory_limit='1GB'");c.execute('SET threads=2')
 groups={}
 for r in manifest['municipal_fact_partitions']:
  p=root/r['relative_path'];cols=c.execute(f'DESCRIBE SELECT * FROM read_parquet({literal(p)})').fetchall()
  raw=','.join('CAST("'+x[0]+'" AS VARCHAR) AS "'+x[0]+'"' for x in cols)
  code="regexp_replace(trim(cast(oktmo as varchar)), '\\.0$', '')"
  norm=f"CASE WHEN regexp_full_match({code}, '[0-9]{{7,8}}') THEN lpad({code},8,'0') END"
  query=f"SELECT {raw},try_cast(indicator_value AS DOUBLE) AS value_numeric,try_cast(year AS INTEGER) AS source_year,{norm} AS municipality_code8,'20260928' AS source_version,{literal(r['source_url'])} AS source_url,{literal(r['source_member'])} AS source_member,{literal(r['source_member_sha256'])} AS source_member_sha256,file_row_number AS source_row_0based,TRUE AS context_only FROM read_parquet({literal(p)},file_row_number=true)"
  groups.setdefault(r['indicator_code'],[]).append(query)
 names=[]
 for code,queries in groups.items():
  name='dataset_'+code;assert re.fullmatch('Y[0-9]+',code)
  c.execute('CREATE VIEW '+name+' AS '+' UNION ALL BY NAME '.join(queries));names.append('SELECT * FROM '+name)
 c.execute('CREATE VIEW municipal_demography_raw AS '+' UNION ALL BY NAME '.join(names))
 allowed_signed="('Y48112004','Y48112009','Y48112023')"
 stock="('Y48112014','Y48112015','Y48112016','Y48112025','Y48112027')"
 status=f"CASE WHEN value_numeric IS NULL THEN 'unknown_source_value' WHEN NOT isfinite(value_numeric) THEN 'invalid_nonfinite' WHEN indicator_code NOT IN {allowed_signed} AND value_numeric<0 THEN 'invalid_negative' WHEN indicator_code IN {stock} AND value_numeric>300000000 THEN 'invalid_population_stock' ELSE 'domain_usable_not_uniqueness_certificate' END"
 c.execute(f"CREATE VIEW municipal_demography AS SELECT *,value_numeric AS source_value_numeric,{status} AS value_status,CASE WHEN ({status})='domain_usable_not_uniqueness_certificate' THEN value_numeric END AS usable_value,(oktmo_history IS NOT NULL AND oktmo_history<>'') AS source_admin_history_present,regexp_matches(lower(coalesce(oktmo_history,'')), 'объедин|раздел|границ|включ|упраздн') AS source_boundary_event_mentioned,CASE WHEN try_cast(oktmo_year_from AS INTEGER) IS NOT NULL AND try_cast(oktmo_year_to AS INTEGER) IS NOT NULL THEN source_year BETWEEN try_cast(oktmo_year_from AS INTEGER) AND try_cast(oktmo_year_to AS INTEGER) END AS source_year_within_code_period FROM municipal_demography_raw")
 for table,key in [('np_attributes_frozen','native_np_frozen_all_attributes'),('np_attributes_latest','native_np_latest_all_attributes')]:
  c.execute(f'CREATE VIEW {table} AS SELECT * FROM read_parquet({literal(root/manifest["tables"][key])})')
 for table,key in [('municipality_bridge','native_np_municipality_bridge'),('census_reference_context','all_years_reference2021_context')]:
  c.execute(f"""CREATE VIEW {table} AS SELECT * FROM read_csv({literal(root/manifest["tables"][key])},header=true,delim=',',quote='"',escape='"',all_varchar=true)""")
 if 'federal_territory_axis' in manifest['tables']:
  c.execute(f"""CREATE VIEW federal_territory_axis AS SELECT * FROM read_csv({literal(root/manifest['tables']['federal_territory_axis'])},header=true,delim=',',quote='"',escape='"',all_varchar=true)""")
 return c,manifest

def manifest_has_federal(m):return 'federal_territory_axis' in m['tables']

def main():
 p=argparse.ArgumentParser(description='Муниципальная демография как контекст НП; численность НП не заменяется.')
 p.add_argument('--package-root',type=Path,required=True);p.add_argument('--verify',action='store_true');p.add_argument('--np-id');p.add_argument('--year',type=int);p.add_argument('--indicator');p.add_argument('--limit',type=int,default=1000);p.add_argument('--attributes',action='store_true');p.add_argument('--output',type=Path)
 a=p.parse_args();c,m=open_db(a.package_root,a.verify)
 if not a.np_id:print(json.dumps({'datasets':len(m['municipal_fact_partitions']),'tables':m['tables']},ensure_ascii=False,indent=2));return
 anchor=c.execute('SELECT reference_2021_source_record_id FROM census_reference_context WHERE source_record_id=?',[a.np_id]).fetchone()
 sid=anchor[0] if anchor and anchor[0] else a.np_id
 if (not anchor or not anchor[0]) and manifest_has_federal(m):
  federal=c.execute('SELECT coordinate_source_record_id FROM federal_territory_axis WHERE population_source_record_id=?',[a.np_id]).fetchone()
  if federal:sid=federal[0]
 if a.attributes:
  cur=c.execute('SELECT * FROM np_attributes_latest WHERE source_record_id=?',[sid])
 else:
  # Select each territorial code/level once even if upper and lower roles coincide.
  rows=c.execute("SELECT municipality_oktmo_code8,municipality_role,context_status,municipality_source_row_ambiguous,all_municipality_source_row1_claims,context_resolution_rule FROM municipality_bridge WHERE source_record_id=? AND context_status IN ('exact_unique_source_context','verified_parent_code_multiple_source_claims')",[sid]).fetchall()
  by={}
  provenance={}
  for code,role,status,ambiguous,claims,rule in rows:
   if not code:continue
   by.setdefault(code,set()).add(role)
   meta=provenance.setdefault(code,{'statuses':set(),'rows':set(),'rules':set(),'ambiguous':False})
   meta['statuses'].add(status);meta['rules'].add(rule);meta['ambiguous']|=(str(ambiguous).lower()=='true')
   if claims:meta['rows'].update(int(v) for v in json.loads(claims))
  allowed=[]
  for code,roles in by.items():
   levels=[]
   if 'upper' in roles:levels.append('Муниципальное образование верхнего уровня')
   if 'lower' in roles:levels.append('Муниципальное образование нижнего уровня')
   if roles&{'region','federal_territory_context'}:levels.append('Регион')
   if levels:allowed.append('(municipality_code8='+literal(code)+' AND mun_level IN ('+','.join(literal(v) for v in levels)+'))')
  if not allowed:raise SystemExit('Для этой записи нет принятого муниципального контекста; отсутствующие данные не заменяются нулями.')
  where=' OR '.join(allowed);params=[]
  def context_case(key):
   pieces=[]
   for code,meta in provenance.items():
    value=('TRUE' if meta['ambiguous'] else 'FALSE') if key=='ambiguous' else literal(json.dumps(sorted(meta[key]),ensure_ascii=False))
    pieces.append('WHEN municipality_code8='+literal(code)+' THEN '+value)
   return 'CASE '+' '.join(pieces)+' END'
  context_fields=context_case('ambiguous')+' AS municipality_source_row_ambiguous,'+context_case('rows')+' AS all_municipality_source_row1_claims,'+context_case('statuses')+' AS context_association_statuses,'+context_case('rules')+' AS context_resolution_rules,FALSE AS municipality_census_attribute_row_selected,FALSE AS boundary_comparability_asserted,'
  query='SELECT '+literal(sid)+' AS reference_2021_source_record_id,FALSE AS historical_membership_asserted,TRUE AS administrative_effective_date_unknown,'+context_fields+'* FROM municipal_demography WHERE ('+where+')'
  if a.year is not None:query+=' AND source_year=?';params.append(a.year)
  if a.indicator:query+=' AND indicator_code=?';params.append(a.indicator)
  query+=' ORDER BY indicator_code,source_year,mun_level,municipality_code8'
  if a.limit>0:query+=' LIMIT '+str(a.limit)
  cur=c.execute(query,params)
 out=a.output.open('w',encoding='utf-8',newline='') if a.output else sys.stdout
 try:
  w=csv.writer(out);w.writerow([x[0] for x in cur.description])
  while rows:=cur.fetchmany(1000):w.writerows(rows)
 finally:
  if a.output:out.close()
if __name__=='__main__':main()
