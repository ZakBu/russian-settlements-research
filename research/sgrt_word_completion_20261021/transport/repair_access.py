#!/usr/bin/env python3
"""Repair OSM motorcar override priority in accepted and previously excluded ways."""
from build_transport import *
DENY={'no','private','agricultural','forestry','delivery','customers','permit','official','psv','bus','taxi','emergency'}
def access(t):return t.get('motorcar',t.get('motor_vehicle',t.get('vehicle',t.get('access',''))))
def oldaccess(t):return t.get('motor_vehicle',t.get('motorcar',t.get('vehicle',t.get('access',''))))
start=time.time();missing=[];needed=set();n=0
# Restrict at C++ reader/filter level; do not call Python once for every building/node.
for w in osmium.FileProcessor(str(PBF),entities=osmium.osm.WAY).with_filter(osmium.filter.KeyFilter('motorcar')):
 t={x.k:x.v for x in w.tags}
 if t.get('highway') in SPEED and oldaccess(t) in {'no','private','agricultural','forestry'} and access(t) not in DENY:
  refs=[x.ref for x in w.nodes]
  if len(refs)>1:missing.append((w.id,t,refs));needed.update(refs)
print('missingways',len(missing),'neededrefs',len(needed),flush=True)
coords={}
if needed:
 for o in osmium.FileProcessor(str(PBF),entities=osmium.osm.NODE).with_filter(osmium.filter.IdFilter(needed)):
  coords[o.id]=(o.location.lat,o.location.lon)
pf=pq.ParquetFile(RAW/'road_ways.parquet');tmp=RAW/'road_ways_access_repaired.parquet';writer=pq.ParquetWriter(tmp,pf.schema_arrow,compression='zstd');removed=[];destination=0;present_restored=set();restore_ids={x[0] for x in missing}
for b in pf.iter_batches(batch_size=20000):
 rows=[]
 for r in b.to_pylist():
  if r['way_id'] in restore_ids:present_restored.add(r['way_id'])
  effective=access(json.loads(r['tags']))
  if effective in DENY:removed.append(r['way_id']);continue
  if effective=='destination':destination+=1
  rows.append(r)
 if rows:writer.write_table(pa.Table.from_pylist(rows,schema=pf.schema_arrow));n+=len(rows)
rows=[]
for wid,t,refs in missing:
 if wid in present_restored:continue
 if not all(x in coords for x in refs):raise RuntimeError('Missing node coordinates')
 ow=t.get('oneway','');direction=-1 if ow=='-1' else 1 if ow in {'yes','true','1'} or t.get('junction')=='roundabout' or t['highway'] in {'motorway','motorway_link'} and ow not in {'no','0','false'} else 0
 rows.append({'way_id':wid,'refs':refs,'lat':[coords[x][0] for x in refs],'lon':[coords[x][1] for x in refs],'highway':t['highway'],'speed_kmh':spd(t,t['highway']),'oneway':direction,'tags':json.dumps(t,ensure_ascii=False)})
if rows:writer.write_table(pa.Table.from_pylist(rows,schema=pf.schema_arrow));n+=len(rows)
writer.close();tmp.replace(RAW/'road_ways.parquet')
dump(ROOT/'access_repair_receipt.json',{'status':'REPAIRED','priority':'motorcar > motor_vehicle > vehicle > access','excluded_effective_values':sorted(DENY),'removed_accepted_ways':len(removed),'restored_previously_excluded_ways':len(rows),'accepted_way_count':n,'destination_ways_retained':destination,'destination_policy':'Retained for destination access; through traffic restriction not represented. Report sensitivity limitation.','removed_way_ids':removed,'restored_way_ids':[x['way_id'] for x in rows],'seconds':time.time()-start})
print('REPAIRED',n,'removed',len(removed),'restored',len(missing),flush=True)
