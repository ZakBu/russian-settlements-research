import json,gzip,hashlib
from pathlib import Path
p=Path(__file__).parent;s=p.parent/'inherited_extreme_Geo_ownpoint_correction_20261008'
with gzip.open(s/'native_ownpoint_recovery_witnesses.json.gz','rt') as f:w=json.load(f)
g=[r for r in w if r['anchor_proof']['anchor_rule'].startswith('independent_raw_GeoNames')]
assert len(g)==55
high=min(g,key=lambda r:(-int(r['anchor_proof']['actual_raw_current_row']['population']),r['carrier_source_record_id']))
rest=sorted([r for r in g if r!=high],key=lambda r:hashlib.sha256(('20261008|'+r['carrier_source_record_id']).encode()).hexdigest())[:3]
selection={'rule':'55 frozen GeoNames anchors; highest native2021 population, ties sourceID lexical; plus first3 SHA256(20261008|sourceID) among remaining54','selected':[high['carrier_source_record_id']]+[r['carrier_source_record_id'] for r in rest]}
(p/'selection_rule.json').write_text(json.dumps(selection,indent=2));(p/'selected_source_witnesses.json').write_text(json.dumps([high]+rest,ensure_ascii=False,indent=2))
for r in [high]+rest:print(r['name'],r['carrier_source_record_id'],r['anchor_proof']['actual_raw_current_row']['population'])
