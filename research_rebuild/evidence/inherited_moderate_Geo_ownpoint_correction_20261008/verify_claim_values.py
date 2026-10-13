import json,gzip,collections,hashlib
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;a=pd.read_csv(O/'own_current_point_source_witnesses.csv.gz',keep_default_na=False);need=collections.defaultdict(dict)
for z in a[a.route.eq('raw_own_Wikidata_P764_P31_P625')].drop_duplicates('current_native_source_record_id').to_dict('records'):
 q=json.loads(z['own_current_wiki_claims_json'])
 for prop,key in [('P625','coord'),('P31','p31'),('P764','codes')]:
  for v in q[key]:need[v['source_file']][int(v['line_number'])]=(z['own_current_entity'],prop,str(v['value_raw']))
count=0;pins={}
for fn,lines in need.items():
 p=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/fn;pins[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();seen=set()
 with gzip.open(p,'rt') as f:
  for ln,line in enumerate(f,1):
   if ln in lines:
    qid,prop,value=lines[ln];z=json.loads(line);assert z['item'].rsplit('/',1)[-1]==qid and z['property'].rsplit('/',1)[-1]==prop and str(z['value'])==value,(fn,ln);seen.add(ln);count+=1
   if ln>=max(lines):break
 assert seen==set(lines)
r={'status':'All admitted exact raw own P764 P31 P625 values independently reopened and literal value checked','claims_checked':count,'source_files':len(pins),'input_pins':pins,'witness_pin':hashlib.sha256((O/'own_current_point_source_witnesses.csv.gz').read_bytes()).hexdigest()};(O/'exact_raw_property_value_verification.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print({'claims_checked':count,'source_files':len(pins),'passed':True})
