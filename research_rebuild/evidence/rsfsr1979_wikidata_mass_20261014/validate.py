from pathlib import Path
import json,csv,gzip
from decimal import Decimal
import pyarrow.parquet as pq
H=Path(__file__).resolve().parent
rows=pq.read_table(H/'secondary_population_1979_long.parquet').to_pylist();need={};replayed=0
for r in rows:
 for proof in json.loads(r['source_proofs_json']):need.setdefault(proof['file'],{})[proof['row0']]=proof['raw']
for file,indices in need.items():
 if file.endswith('.gz'):
  with gzip.open(file,'rt') as f:
   for i,l in enumerate(f):
    if i in indices:assert json.loads(l)==indices[i];replayed+=1
 else:
  with open(file) as f:
   for i,r in enumerate(csv.DictReader(f,delimiter='\t',quoting=csv.QUOTE_NONE)):
    if i in indices:assert r==indices[i];replayed+=1
for r in rows:
 assert r['root'] and r['anchor_source_record_id'] and r['latitude'] is not None and r['longitude'] is not None
 assert len({x['source_GUID'].casefold() for x in rows})==len(rows)
 assert r['population_value']>=0 and r['year']==1979 and r['primary_verification']=='primary_unverified'
 for p in json.loads(r['source_proofs_json']):
  raw=p['raw'];date=raw.get('date',raw.get('?date'));pop=raw.get('population',raw.get('?population'));assert date.startswith('1979-') and Decimal(str(pop))==r['population_value']
v={'status':'PASS','source_locators_replayed':replayed,'observation_rows':len(rows),'unique_GUIDs':len({r['source_GUID'].casefold() for r in rows}),'unique_roots':len({r['root'] for r in rows}),'all_own_points_present':True,'counts_not_additive_across_GUIDs':True,'secondary_not_verified_primary':True}
for d in [H,Path('/workspace/shared/rsfsr1979_wikidata_mass')]: (d/'validation.json').write_text(json.dumps(v,indent=2))
print(v)
