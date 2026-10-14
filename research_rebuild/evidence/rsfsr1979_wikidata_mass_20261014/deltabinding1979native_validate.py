from pathlib import Path
import csv,json,collections,hashlib
import pyarrow as pa,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;O=Path('/workspace/shared/rsfsr1979_wikidata_mass');rs=pq.read_table(O/'deltabinding1979native_population_long.parquet').to_pylist();receipt=json.loads((H/'deltabinding1979native_receipt.json').read_text());base=H/'secondary_population_1979_long.parquet';assert hashlib.file_digest(base.open('rb'),'sha256').hexdigest()==receipt['inputs'][str(base)]
pneed={r['source_population_row_0based']:r for r in rs};eneed={i for r in rs for i in json.loads(r['source_entity_rows_json'])};entities={}
with open(rs[0]['source_population_file']) as f:
 for i,p in enumerate(csv.DictReader(f,delimiter='\t',quoting=csv.QUOTE_NONE)):
  if i not in pneed:continue
  r=pneed[i];assert p['?date'].startswith('1979-') and p['?statement']==r['statement_uri_raw'] and p['?population']==r['raw_population_literal'];r['source_population_raw_json']=json.dumps(p,ensure_ascii=False)
with open(rs[0]['source_entity_file']) as f:
 for i,e in enumerate(csv.DictReader(f,delimiter='\t',quoting=csv.QUOTE_NONE)):
  if i in eneed:entities[i]=e
oldroots=set(pq.read_table(base,columns=['root']).column('root').to_pylist())
for r in rs:
 er=[{'row0':i,'raw':entities[i]} for i in json.loads(r['source_entity_rows_json'])];assert all(r['wikidata_qid'] in e['raw']['?item'] for e in er)
 assert r['root'] not in oldroots and r['native_object_level']=='Населенный пункт' and r['own_point_distance_km']<=5
 assert r['current_region'] not in ['крым','севастополь'] and r['latitude'] is not None and r['longitude'] is not None
 assert json.loads(r['binding_code_literals_json']) and r['primary_verification']=='primary_unverified'
 r['source_entity_proofs_json']=json.dumps(er,ensure_ascii=False);r['source_GUID']=r['statement_uri_raw'].strip('<>').split('/')[-1].replace('-','$',1)
assert len(rs)==len({r['root'] for r in rs})==len({r['source_GUID'].casefold() for r in rs})
for d in [H,O]:pq.write_table(pa.Table.from_pylist(rs),d/'deltabinding1979native_population_long.parquet',compression='zstd')
receipt['outputs']={str(p):{'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),'bytes':p.stat().st_size} for p in H.glob('deltabinding1979native*.parquet')};v={'status':'PASS_secondary_not_verified_primary','population_source_rows_replayed':len(pneed),'entity_source_rows_replayed':len(eneed),'net_new_roots':len(rs),'net_new_population':sum(r['population_value'] for r in rs),'frozen_base_unchanged':True,'P31_unit_qualifiers_precision':'UNKNOWN_flat_cache','municipal8code_route_disabled':True}
for d in [H,O]:
 (d/'deltabinding1979native_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));(d/'deltabinding1979native_validation.json').write_text(json.dumps(v,ensure_ascii=False,indent=2))
print(v)
