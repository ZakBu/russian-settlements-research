#!/usr/bin/env python3
"""Retain dated source geometry/metadata before applying a public-car routing profile."""
from pathlib import Path
import json,hashlib,time,shutil
import osmium
import pandas as pd
from road_profile import SPEED
H=Path(__file__).resolve().parent;TEMP=Path('/tmp/sgrt_network2021');RAW=TEMP/'russia-210101.osm.pbf';FILTERED=TEMP/'roads2021_reference_complete.osm.pbf'
SOURCE_SHA='1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as s:
  for b in iter(lambda:s.read(4194304),b''):h.update(b)
 return h.hexdigest()
def main():
 start=time.monotonic();assert sha(RAW)==SOURCE_SHA;assert not FILTERED.exists();rows=[];selection_parts=[];counts=[0,0,0,0];selection_dir=H/'source_selection';selection_dir.mkdir(exist_ok=True)
 def flush():
  if not rows:return
  df=pd.DataFrame(rows,columns=['osm_type','osm_id','osm_version','source_timestamp','road_class_predicate','ferry_predicate','restriction_relation_predicate','all_source_tags_sha256']);part=selection_dir/f'part_{len(selection_parts):03d}.parquet';df.to_parquet(part,index=False,compression='zstd');selection_parts.append({'path':str(part.relative_to(H)),'rows':len(df),'sha256':sha(part)});rows.clear()
 assert shutil.disk_usage(TEMP).free>2_000_000_000
 with osmium.BackReferenceWriter(FILTERED,RAW,remove_tags=False,relation_depth=16) as writer:
  for o in osmium.FileProcessor(RAW,entities=osmium.osm.WAY|osmium.osm.RELATION).with_filter(osmium.filter.KeyFilter('highway','route','type','restriction')):
   t=dict(o.tags);kind='way' if o.is_way() else 'relation';road=o.is_way() and t.get('highway') in SPEED;ferry=t.get('route')=='ferry';restriction=o.is_relation() and (t.get('type')=='restriction' or 'restriction' in t)
   if road or ferry or restriction:
    writer.add(o);rows.append((kind,int(o.id),int(o.version),str(o.timestamp),road,ferry,restriction,hashlib.sha256(json.dumps(t,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()))
    counts[0]+=1;counts[1]+=int(road);counts[2]+=int(ferry);counts[3]+=int(restriction)
    if len(rows)>=100000:flush();print('selected',counts[0],flush=True)
 flush()
 # Durable source parts are byte fragments of one reference-complete original PBF.
 target=H/'sources';target.mkdir(exist_ok=True);parts=[]
 with FILTERED.open('rb') as f:
  while True:
   b=f.read(90_000_000)
   if not b:break
   p=target/f'roads2021_reference_complete.osm.pbf.part{len(parts):03d}';assert not p.exists();p.write_bytes(b);parts.append({'path':str(p.relative_to(H)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
 assert sha(RAW)==SOURCE_SHA
 receipt={'status':'ACTUAL_HISTORICAL_REFERENCE_COMPLETE_SOURCE_RETAINED','original_url':'https://download.geofabrik.de/russia-210101.osm.pbf','original_sha256':SOURCE_SHA,'original_bytes':RAW.stat().st_size,'source_snapshot_date':'2021-01-01','snapshot_is_date_not_midnight':True,'selection_rows':counts[0],'selected_road_ways':counts[1],'selected_ferry_objects':counts[2],'selected_restriction_relations':counts[3],'reference_complete_filtered_pbf_sha256':sha(FILTERED),'reference_complete_filtered_pbf_bytes':FILTERED.stat().st_size,'durable_parts':parts,'all_source_tags_and_metadata_preserved':True,'backreference_relation_depth':16,'ferry_and_turn_inventory_not_applied_to_routing':True,'raw_selection_parts':selection_parts,'filter_code_sha256':sha(Path(__file__)),'seconds':time.monotonic()-start}
 (H/'source_filter_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
