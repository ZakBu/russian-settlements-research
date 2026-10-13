import json,gzip,re,hashlib
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;P=O.parent.parent
w=pd.read_csv(P/'owncoded_coordinate_consistency_witnesses.csv.gz',keep_default_na=False);held=w[~w.point_recovered].copy();bycode={str(int(str(z['native2021_own_code']))):z for z in held.to_dict('records')};tsv=Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv');hits=[];wanted={};pins={str(tsv):hashlib.sha256(tsv.read_bytes()).hexdigest(),str(P/'owncoded_coordinate_consistency_witnesses.csv.gz'):hashlib.sha256((P/'owncoded_coordinate_consistency_witnesses.csv.gz').read_bytes()).hexdigest()}
for n,line in enumerate(tsv.open(),1):
 a=line.rstrip('\n').split('\t')
 if len(a)<8:continue
 code=a[1].strip('"')
 if not code.isdigit() or str(int(code)) not in bycode:continue
 q=a[0].rsplit('/',1)[1].rstrip('>');z=bycode[str(int(code))];wanted[q]=z;hits.append({'current_source_record_id':z['current_source_record_id'],'name':z['name'],'own_current_code_raw':z['native2021_own_code'],'QID':q,'TSV_line1based':n,'TSV_raw_line':line.rstrip('\n'),'TSV_coordinate_literal':a[3]})
entities={};files={}
for root in ['/workspace/settlements-raw/data/raw/wikidata_entities_full','/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007','/workspace/settlements-work/additional_uncached_census_histories_20261008','/workspace/settlements-work/continuation_20261004/R4/residual_alias_fetch/raw_entity_batches']:
 for p in Path(root).glob('*.json*'):
  try:d=json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith('.gz') else p.read_bytes());es=d.get('entities',d.get('payload',{}).get('entities',{}))
  except:continue
  for q in wanted:
   e=es.get(q)
   if isinstance(e,dict) and (q not in entities or len(e.get('claims',{}))>len(entities[q].get('claims',{}))):entities[q]=e;files[q]=p
for z in hits:
 q=z['QID'];e=entities.get(q,{});ps=e.get('claims',{}).get('P625',[]);ps=[a for a in ps if a.get('rank')!='deprecated' and 'datavalue' in a.get('mainsnak',{})];z['cached_P625_claims_json']=json.dumps(ps,ensure_ascii=False);z['cached_entity_file']=str(files.get(q,''));z['cached_entity_raw_json']=json.dumps(e,ensure_ascii=False);z['coordinate_available']=bool(z['TSV_coordinate_literal'].strip()) or bool(ps);z['decision']='candidate_coordinate_requires_own_binding_check' if z['coordinate_available'] else 'hold_no_actual_coordinate_in_owncoded_cached_sources'
 if q in files:pins[str(files[q])]=hashlib.sha256(files[q].read_bytes()).hexdigest()
pd.DataFrame(hits).to_csv(O/'current_owncode_cached_coordinate_inventory.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'scope':len(held),'own_current_code_TSV_hits':len(hits),'coordinate_available_candidates':sum(z['coordinate_available'] for z in hits),'Q23976086_reason':'actual TSV line135434 has blank coordinate; cached physical owncoded entity has no P625; no contradictory type or owncode, simply no actual point','input_pins':pins};(O/'inventory_receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'}))
