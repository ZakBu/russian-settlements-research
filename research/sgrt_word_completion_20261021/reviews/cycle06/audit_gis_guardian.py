from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,sqlite3,struct
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');M=B/'model/output_cycle06_access_v2_baseline';C=B/'typology/canonical_cycle06/output_cycle06_access_v2_baseline';G=B/'delivery/gis_cycle06_access_v2_baseline';F=Path('/tmp/sgrt_cycle06_guardian_gis/SGRT_output_cycle06_access_v2_baseline.gpkg');checks=[]
def ck(k,v):checks.append({'check':k,'pass':bool(v)})
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def eq(a,b):
 a=pd.Series(a).reset_index(drop=True);b=pd.Series(b).reset_index(drop=True)
 if pd.api.types.is_numeric_dtype(a) or pd.api.types.is_bool_dtype(a):return np.array_equal(pd.to_numeric(a).astype(float).to_numpy(),pd.to_numeric(b).astype(float).to_numpy(),equal_nan=True)
 return a.astype('string').fillna('<NA>').equals(b.astype('string').fillna('<NA>'))
r=json.loads((G/'SGRT_output_cycle06_access_v2_baseline.receipt.json').read_text());ck('archive_payload_exact_declared_SHA',sha(G/r['archive'])==r['archive_sha256'] and sha(F)==r['sha256']);con=sqlite3.connect(f'file:{F}?mode=ro',uri=True);ck('full_SQLite_integrity',con.execute('pragma integrity_check').fetchone()[0]=='ok' and not con.execute('pragma foreign_key_check').fetchall());n=pd.read_parquet(M/'nodes.parquet');mem=pd.read_parquet(M/'memberships.parquet');conf=pd.read_parquet(M/'system_configurations.parquet');s=pd.read_parquet(M/'systems.parquet');t=pd.read_parquet(C/'word_type_hypotheses.parquet')
fields=['id','lat','lon','population_2002','population_2010','population_2021','_population_axis_row','accepted_statistical_rural_role2021','accepted_formal_settlement_subtype2021','population_value_quality_2010','population_value_quality_2021'];actual=pd.concat([pd.read_sql_query('select '+','.join('"'+f+'"' for f in fields)+' from '+table,con) for table in ['settlements','unlocated_source_entities']]).set_index('id').reindex(n.id)
ck('all173864_located_unlocated_source_IDs_exact',actual.index.is_unique and actual.shape[0]==len(n) and sum(con.execute('select count(*) from '+table).fetchone()[0] for table in ['settlements','unlocated_source_entities'])==len(n))
for c in fields[1:]:ck('ALL_axis_GIS_source_'+c,eq(n[c],actual[c]))
for lev in range(1,5):
 source=s[s.level.eq(lev)].merge(conf,on=['level','center_id']).set_index('center_id');table=pd.read_sql_query(f'select * from systems_level{lev}',con).set_index('center_id').reindex(source.index);ck(f'L{lev}_GIS_keys_exact',len(table)==len(source) and table.index.is_unique)
 columns=['center_population_2010','center_population_2021','system_population_known_sum_2010','system_population_known_sum_2021','system_population_complete_2010','system_population_complete_2021','rural_external_population_known_sum_2010','rural_external_population_known_sum_2021','rural_role_complete','population_secondary_protected_scope_unverified_known_population_share_2010']+[c for c in conf if c not in ['level','center_id']]
 for c in columns:ck(f'L{lev}_ALL_GIS_'+c,eq(source[c],table[c]))
 for typ in range(1,10):
  expected=t[t.level.eq(lev)&t.word_type.eq(typ)].set_index('center_id').reindex(source.index);ck(f'L{lev}_type{typ}_candidate_scope',eq(expected.operational_hypothesis,table[f'word_type{typ}_operational_hypothesis']) and eq(expected.rule_status,table[f'word_type{typ}_evidence_status']) and eq(expected.operational_hypothesis_exact_contemporary_geography,table[f'word_type{typ}_exact_contemporary_geography_candidate']))
for table,col,kind,srid,z,m in con.execute('select * from gpkg_geometry_columns'):
 ok=kind=='POINT' and srid==4326 and z==m==0;count=0
 for blob,lon,lat in con.execute(f'select "{col}",lon,lat from "{table}"'):
  ok &= len(blob)==29 and blob[:4]==bytes([71,80,0,1]) and struct.unpack('<i',blob[4:8])[0]==4326 and struct.unpack('<BIdd',blob[8:])==(1,1,lon,lat) and -180<=lon<=180 and -90<=lat<=90;count+=1
 ck('ALL_actual_GIS_WKB_geometry_'+table,ok)
ctx=actual.loc[actual.index.astype(str).str.startswith('ctx:')];ck('external_context_ownpopulation_NULL_nonadditive',len(ctx)==2 and ctx.population_2010.isna().all() and ctx.population_2021.isna().all() and ctx._population_axis_row.eq(0).all());con.close();result={'status':'ACCEPTED' if all(c['pass'] for c in checks) else 'REJECTED','all_checks_passed':all(c['pass'] for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'checks':checks,'GIS_receipt_sha256':sha(G/'SGRT_output_cycle06_access_v2_baseline.receipt.json'),'model_output_manifest_sha256':sha(M/'output_manifest.json'),'scope':'Fresh independent SQLite integrity/readback of allaxis sourcepopulation/quality/nullable roles; allsystem population andconfiguration cells/allnine type candidate/status cells; everyactual pointWKB coordinate. Exact sourcepointartifact, not precise catchment territorial polygons or trueflows.'};(B/'reviews/cycle06/GIS_guardian_independent_admission.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],result['n_checks'],result['n_failed']);print([c for c in checks if not c['pass']])
