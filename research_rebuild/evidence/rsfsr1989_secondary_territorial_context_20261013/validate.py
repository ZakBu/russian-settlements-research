from pathlib import Path
import json,collections,duckdb,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;receipt=json.loads((H/'receipt.json').read_text());O=Path('/workspace/scratch/rsfsr1989_secondary_territorial_context_20261013')
a=pq.read_table(O/'secondary_population_1989_long.parquet').to_pylist();b=pq.read_table(O/'current_own_NP_bindings.parquet').to_pylist()
assert len(a)==receipt['secondary1989_rows_GUID_deduplicated']
assert len({(r['wikidata_qid'],r['statement_uri_raw'].casefold()) for r in a})==len(a)
assert len({r['anchor_source_record_id'] for r in b})==len(b)
assert all(r['observed_year']==1989 and r['source_date_raw'].startswith('1989-') and r['population_value']>=0 and r['boundary_comparability']=='UNKNOWN' and r['primary_verification']=='primary_unverified' for r in a)
c=duckdb.connect();c.register('observations',pq.read_table(O/'secondary_population_1989_long.parquet'))
result=c.execute("select count(*) from observations o join (select row_number() over()-1 row0,* from read_csv(?,delim='\t',quote='',header=true,all_varchar=true)) p on o.source_population_row_0based=p.row0 where o.statement_uri_raw=p.\"?statement\" and o.raw_population_literal=p.\"?population\" and o.source_date_raw=p.\"?date\"",[a[0]['source_population_file']]).fetchone()[0]
assert result==len(a)
out={'status':'PASS','replayed_literal_raw_source_rows':result,'GUID_duplicates':0,'binding_UID_duplicates':0,'identity_routes':dict(collections.Counter(r['identity_rule'] for r in b)),'not_primary_verified':True}
(H/'validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
