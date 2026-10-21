#!/usr/bin/env python3
from pathlib import Path
from collections import Counter
import json,hashlib,time
import osmium,numpy as np,pyarrow as pa,pyarrow.parquet as pq
from road_profile import SPEED,effective_access,exclusions,oneway,speed
H=Path(__file__).resolve().parent;T=Path('/tmp/sgrt_network2021')
SCHEMA=pa.schema([('way_id',pa.int64()),('refs',pa.list_(pa.int64())),('lat',pa.list_(pa.float64())),('lon',pa.list_(pa.float64())),('highway',pa.string()),('speed_kmh',pa.float64()),('oneway',pa.int8()),('tags',pa.string()),('osm_version',pa.int32()),('source_timestamp',pa.string()),('all_source_tags_sha256',pa.string())])
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def main():
 start=time.monotonic();sr=json.loads((H/'source_filter_receipt.json').read_text());source=T/'roads2021_reference_complete.osm.pbf';assert sha(source)==sr['reference_complete_filtered_pbf_sha256'];assert not (T/'road_ways.parquet').exists()
 writer=pq.ParquetWriter(T/'road_ways.parquet',SCHEMA,compression='zstd');rows=[];ledger=[];parts=[];stats=Counter();reasons=Counter();ledgerdir=H/'profile_ledger';ledgerdir.mkdir(exist_ok=True)
 def flush_ledger():
  if not ledger:return
  schema=pa.schema([('osm_type',pa.string()),('way_id',pa.int64()),('osm_version',pa.int32()),('source_timestamp',pa.string()),('all_source_tags_sha256',pa.string()),('highway',pa.string()),('effective_car_access',pa.string()),('accepted',pa.bool_()),('exclusion_reasons_json',pa.string()),('oneway_raw',pa.string()),('oneway_motor_vehicle_raw',pa.string()),('oneway_motorcar_raw',pa.string()),('junction_raw',pa.string()),('static_direction',pa.int8()),('maxspeed_conditional_present',pa.bool_()),('opening_hours_present',pa.bool_())]);table=pa.Table.from_pylist(ledger,schema=schema);p=ledgerdir/f'part_{len(parts):03d}.parquet';pq.write_table(table,p,compression='zstd');parts.append({'path':str(p.relative_to(H)),'rows':len(ledger),'sha256':sha(p)});ledger.clear()
 proc=osmium.FileProcessor(source).with_locations(f'sparse_file_array,{T}/node_locations.idx').with_filter(osmium.filter.KeyFilter('highway'))
 for o in proc:
  if not o.is_way():continue
  t=dict(o.tags)
  if t.get('highway') not in SPEED:continue
  stats['road_source_ways']+=1;rs=exclusions(t);geometry=None
  if not rs:
   refs=[n.ref for n in o.nodes]
   if len(refs)<2:rs=['fewer_than_two_source_vertices']
   elif not all(n.location.valid() for n in o.nodes):rs=['missing_original_source_node_geometry']
   else:
    la=[n.lat for n in o.nodes];lo=[n.lon for n in o.nodes]
    if not np.isfinite(np.array([la,lo])).all():rs=['nonfinite_source_geometry']
    else:geometry=(refs,la,lo)
  digest=hashlib.sha256(json.dumps(t,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  ledger.append({'osm_type':'way','way_id':int(o.id),'osm_version':int(o.version),'source_timestamp':str(o.timestamp),'all_source_tags_sha256':digest,'highway':t['highway'],'effective_car_access':effective_access(t),'accepted':not bool(rs),'exclusion_reasons_json':json.dumps(rs),'oneway_raw':t.get('oneway'),'oneway_motor_vehicle_raw':t.get('oneway:motor_vehicle'),'oneway_motorcar_raw':t.get('oneway:motorcar'),'junction_raw':t.get('junction'),'static_direction':None if rs else oneway(t),'maxspeed_conditional_present':bool(t.get('maxspeed:conditional')),'opening_hours_present':bool(t.get('opening_hours'))})
  if rs:reasons.update(rs);stats['excluded']+=1
  else:
   refs,la,lo=geometry;ow=oneway(t);rows.append({'way_id':int(o.id),'refs':refs,'lat':la,'lon':lo,'highway':t['highway'],'speed_kmh':speed(t),'oneway':ow,'tags':json.dumps(t,sort_keys=True,ensure_ascii=False),'osm_version':int(o.version),'source_timestamp':str(o.timestamp),'all_source_tags_sha256':digest});stats['accepted']+=1;stats[f'direction_{ow}']+=1
   if effective_access(t)=='destination':stats['destination_roads_retained']+=1
   if t.get('junction')=='roundabout' and ow==0:stats['explicit_bidirectional_roundabouts']+=1
  if len(rows)>=20000:writer.write_table(pa.Table.from_pylist(rows,schema=SCHEMA));rows=[];print('accepted',stats['accepted'],'source',stats['road_source_ways'],flush=True)
  if len(ledger)>=100000:flush_ledger()
 if rows:writer.write_table(pa.Table.from_pylist(rows,schema=SCHEMA))
 writer.close();flush_ledger();assert stats['road_source_ways']==sr['selected_road_ways']
 out={'status':'HISTORICAL_ROAD_PROFILE_APPLIED','source_filter_receipt_sha256':sha(H/'source_filter_receipt.json'),'profile_code_sha256':sha(H/'road_profile.py'),'extract_code_sha256':sha(Path(__file__)),'counts':dict(stats),'exclusion_reason_counts':dict(reasons),'profile_ledger_parts':parts,'working_geometry_parquet':str(T/'road_ways.parquet'),'working_geometry_sha256':sha(T/'road_ways.parquet'),'working_geometry_bytes':(T/'road_ways.parquet').stat().st_size,'seconds':time.monotonic()-start,'limits':['scenario speeds, not observed trips','turn relations inventoried but not enforced','ferries inventoried but not routed','destination through-traffic not enforced','conditional speed/opening hours not evaluated; flagged in ledger']}
 (H/'road_extraction_receipt.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out),flush=True)
if __name__=='__main__':main()
