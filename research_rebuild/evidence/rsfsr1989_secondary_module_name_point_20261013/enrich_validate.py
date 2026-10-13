from pathlib import Path
import json,gzip,hashlib,shutil,pyarrow.parquet as pq,pyarrow as pa,duckdb
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/rsfsr1989_secondary_module_name_point_20261013');B=Path('/workspace/scratch/rsfsr1989_secondary_name_point_20261013');added=pq.read_table(O/'additional_module_population_1989_long.parquet').to_pylist();base=pq.read_table(B/'secondary_population_1989_long.parquet').to_pylist();qs={r['wikidata_qid'] for r in added};sources={};full={};cache=O/'api_cache';cache.mkdir(exist_ok=True)
for p in list(H.glob('module_entity_batch_*.json'))+list(cache.glob('module_entity_batch_*.json')):
 b=p.read_bytes();digest=hashlib.sha256(b).hexdigest()
 for q,e in json.loads(b).get('entities',{}).items():sources[q]=(str(cache/p.name),digest);full[q]=e
entityrows={}
with gzip.open(added[0]['source_entity_file'],'rt') as f:
 for i,l in enumerate(f):
  e=json.loads(l);q=e['item'].split('/')[-1]
  if q in qs and e.get('coord'):entityrows.setdefault(q,[]).append({'row0':i,'raw_entity_row':e})
with gzip.open(added[0]['source_population_file'],'rt') as f:rawlines={i:json.loads(l) for i,l in enumerate(f) if i in {r['source_population_row_0based'] for r in added}}
for r in added:
 raw=rawlines[r['source_population_row_0based']];assert raw['date']==r['source_date_raw'] and raw['population']==r['population_value'] and '<'+raw['statement']+'>'==r['statement_uri_raw'];r.update({'full_API_response_file':sources[r['wikidata_qid']][0],'full_API_response_sha256':sources[r['wikidata_qid']][1],'source_entity_rows_json':json.dumps(entityrows[r['wikidata_qid']],ensure_ascii=False)})
combined=base+added;keys=set().union(*(r.keys() for r in combined))
for r in combined:
 for k in keys:r.setdefault(k,None)
pq.write_table(pa.Table.from_pylist(combined),O/'secondary_population_1989_long.parquet',compression='zstd');pq.write_table(pa.Table.from_pylist(added),O/'additional_module_population_1989_long.parquet',compression='zstd');assert len({r['statement_uri_raw'].casefold() for r in combined})==len(combined);assert len({r['anchor_source_record_id'] for r in pq.read_table(O/'current_own_NP_bindings.parquet').to_pylist()})==10135
c=duckdb.connect();c.register('observations',pa.Table.from_pylist(base));count=c.execute('select count(*) from observations o join (select row_number() over()-1 row0,* from read_csv(?,delim=\'\\t\',quote=\'\',header=true,all_varchar=true)) p on o.source_population_row_0based=p.row0 where o.statement_uri_raw=p."?statement" and o.raw_population_literal=p."?population" and o.source_date_raw=p."?date"',[base[0]['source_population_file']]).fetchone()[0];assert count==len(base)
manifest=[]
for p in H.glob('module_entity_batch_*.json'):
 target=cache/p.name;shutil.move(str(p),str(target));manifest.append({'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size})
(H/'API_response_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');r=json.loads((H/'receipt.json').read_text());r['validation']={'status':'PASS','all_population_source_rows_replayed':count+len(added),'module_entity_rows_provenance':len(added),'new_full_GUIDs_checked':len(added),'GUID_duplicates':0,'anchor_binding_duplicates':0};r['outputs']={p.name:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in O.glob('*.parquet')};(H/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');(H/'validation.json').write_text(json.dumps(r['validation'],ensure_ascii=False,indent=2)+'\n')
for p in O.glob('*.parquet'):shutil.copy2(p,H/p.name)
print(json.dumps({'validation':r['validation'],'outputs':r['outputs']},ensure_ascii=False))
