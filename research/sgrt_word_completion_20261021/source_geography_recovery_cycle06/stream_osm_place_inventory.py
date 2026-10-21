"""Stream exact dated national PBF through libosmium stdin; retain relevant source assertions only."""
from pathlib import Path
import subprocess,sys,json,hashlib,time,datetime,requests
H=Path(__file__).resolve().parent;URL='https://download.geofabrik.de/russia-210101.osm.pbf';SIZE=2969339717;SHA='1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe'
CONSUMER=r'''
from pathlib import Path
import osmium,pyarrow as pa,pyarrow.parquet as pq,json,hashlib,collections,sys
h=Path(sys.argv[1]);folder=h/'osm2021_inventory';folder.mkdir(exist_ok=False);buf=[];parts=[];counts=collections.Counter()
schema=pa.schema([('osm_type',pa.string()),('osm_id',pa.int64()),('osm_version',pa.int32()),('object_timestamp',pa.string()),('lat',pa.float64()),('lon',pa.float64()),('tags_json',pa.string()),('all_source_tags_sha256',pa.string()),('refs_or_members_json',pa.string())])
def flush():
 if not buf:return
 p=folder/f'part_{len(parts):03d}.parquet';pq.write_table(pa.Table.from_pylist(buf,schema=schema),p,compression='zstd');parts.append(dict(path=str(p.relative_to(h)),rows=len(buf),sha256=hashlib.sha256(p.read_bytes()).hexdigest()));buf.clear()
for o in osmium.FileProcessor(osmium.io.File('-','pbf')).with_filter(osmium.filter.KeyFilter('place','boundary','ref:oktmo','oktmo','ref:okato','okato','ref:gar','ref:fias','fias')):
 t=dict(o.tags)
 if 'place' not in t and t.get('boundary')!='administrative' and not any(k in t for k in ['ref:oktmo','oktmo','ref:okato','okato','ref:gar','ref:fias','fias']):continue
 typ='node' if o.is_node() else 'way' if o.is_way() else 'relation';counts[typ]+=1
 la=float(o.location.lat) if o.is_node() and o.location.valid() else None;lo=float(o.location.lon) if o.is_node() and o.location.valid() else None
 tags=json.dumps(t,sort_keys=True,ensure_ascii=False,separators=(',',':'));refs=None if o.is_node() else json.dumps([n.ref for n in o.nodes]) if o.is_way() else json.dumps([dict(type=m.type,ref=m.ref,role=m.role) for m in o.members],ensure_ascii=False)
 buf.append(dict(osm_type=typ,osm_id=int(o.id),osm_version=int(o.version),object_timestamp=str(o.timestamp),lat=la,lon=lo,tags_json=tags,all_source_tags_sha256=hashlib.sha256(tags.encode()).hexdigest(),refs_or_members_json=refs))
 if len(buf)>=50000:flush()
flush();(h/'osm2021_extraction_receipt.json').write_text(json.dumps(dict(status='EXTRACTED_FROM_COMPLETE_STDIN_PBF_PENDING_PARENT_STREAM_SHA',counts=dict(counts),parts=parts,nonnode_geometry_not_assembled=True,geometry_source='Original source node coordinates only; no centroids'),indent=2)+'\n')
print(json.dumps(dict(counts)),flush=True)
'''
def main():
 assert not (H/'osm2021_inventory').exists();start=time.monotonic();p=subprocess.Popen([sys.executable,'-c',CONSUMER,str(H)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);digest=hashlib.sha256();n=0
 with requests.get(URL,stream=True,timeout=(30,90)) as response:
  response.raise_for_status();assert response.status_code==200
  for block in response.iter_content(4*1024*1024):
   p.stdin.write(block);digest.update(block);n+=len(block)
   if n//268435456!=(n-len(block))//268435456:print('streamed',n,SIZE,flush=True)
 p.stdin.close();out=p.stdout.read().decode();err=p.stderr.read().decode();code=p.wait();receipt=dict(status='COMPLETE_EXACT_DATED_SOURCE_STREAM_EXTRACTED' if code==0 and n==SIZE and digest.hexdigest()==SHA else 'FAILED_SOURCE_VERIFICATION',url=URL,created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),actual_bytes=n,expected_bytes=SIZE,actual_sha256=digest.hexdigest(),expected_sha256=SHA,consumer_returncode=code,consumer_stdout=out,consumer_stderr=err,seconds=time.monotonic()-start,full_raw_pbf_written_to_disk=False,full_raw_pbf_loaded_into_RAM=False,source_snapshot='2021-01-01 date-level, header2021-01-01T21:42:03Z; modification timestamps are not coordinate measurement dates')
 (H/'national_osm2021_stream_acquisition_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');assert receipt['status']=='COMPLETE_EXACT_DATED_SOURCE_STREAM_EXTRACTED';print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
