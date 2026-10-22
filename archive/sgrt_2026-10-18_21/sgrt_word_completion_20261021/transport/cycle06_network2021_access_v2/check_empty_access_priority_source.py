from pathlib import Path
import osmium,json,collections,time
from road_profile import ACCESS_KEYS,SPEED,access_decision
from graph_io import sha
H=Path(__file__).resolve().parent;P=Path('/tmp/sgrt_network2021/roads2021_reference_complete.osm.pbf');start=time.monotonic();r=json.loads((H/'source_filter_receipt.json').read_text());assert sha(P)==r['reference_complete_filtered_pbf_sha256'];n=0;w=[]
for obj in osmium.FileProcessor(P).with_filter(osmium.filter.KeyFilter(*ACCESS_KEYS)):
 if not obj.is_way():continue
 t=dict(obj.tags)
 if t.get('highway') not in SPEED:continue
 n+=1;present=[k for k in ACCESS_KEYS if k in t]
 if present and not t[present[0]].strip():
  raw,norm,category,reason=access_decision(t);w.append(dict(way_id=int(obj.id),tags=t,effective_key=present[0],category=category,reason=reason))
d=dict(status='PASS' if not w else 'SOURCE_EMPTY_KEYS_REQUIRE_LEDGER_RECONCILIATION',all_source_tagged_access_ways=n,explicit_empty_highest_present_keys=len(w),witnesses=w,source_sha256=r['reference_complete_filtered_pbf_sha256'],seconds=time.monotonic()-start);(H/'all_source_empty_access_priority_readback.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(json.dumps(d))
