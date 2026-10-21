from pathlib import Path
import json,hashlib,subprocess,sys,time,requests,datetime
import pandas as pd
H=Path(__file__).resolve().parent;URL='https://download.geofabrik.de/russia-210101.osm.pbf';SHA='1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe';SIZE=2969339717
CONSUMER=r'''
from pathlib import Path
import json,osmium,pyarrow as pa,pyarrow.parquet as pq,sys,collections
h=Path(sys.argv[1]);q=json.loads((h/'boundary_dependency_request.json').read_text());nodes=set(q['node_ids']);ways=set(q['way_ids']);relations=set(q['relation_ids']);ids=nodes|ways|relations;rows=[];counts=collections.Counter()
for o in osmium.FileProcessor(osmium.io.File('-','pbf')).with_filter(osmium.filter.IdFilter(sorted(ids))):
 typ='node' if o.is_node() else 'way' if o.is_way() else 'relation';wanted=nodes if typ=='node' else ways if typ=='way' else relations
 if int(o.id) not in wanted:continue
 t=dict(o.tags);counts[typ]+=1;refs=None if typ=='node' else [n.ref for n in o.nodes] if typ=='way' else [dict(type=m.type,ref=m.ref,role=m.role) for m in o.members];la=float(o.location.lat) if typ=='node' and o.location.valid() else None;lo=float(o.location.lon) if typ=='node' and o.location.valid() else None
 rows.append(dict(osm_type=typ,osm_id=int(o.id),osm_version=int(o.version),object_timestamp=str(o.timestamp),visible=getattr(o,'visible',None),deleted=getattr(o,'deleted',None),lat=la,lon=lo,tags_json=json.dumps(t,ensure_ascii=False,sort_keys=True,separators=(',',':')),refs_or_members_json=json.dumps(refs,ensure_ascii=False) if refs is not None else None))
pq.write_table(pa.Table.from_pylist(rows),h/'actual2021_boundary_dependency_source_objects.parquet',compression='zstd');print(json.dumps(dict(counts)),flush=True)
'''
def main():
 a=pd.read_parquet(H/'all_exact_native11_osm2021_source_assertions.parquet');s=pd.read_parquet(H/'osm2021_inventory');a2=a[a.status.str.startswith('A2')];wayids=set(a2.loc[a2.source_osm_type.eq('way'),'source_osm_id']);relids=set(a2.loc[a2.source_osm_type.eq('relation'),'source_osm_id']);nodeids=set(a.loc[a.source_osm_type.eq('node'),'source_osm_id'])
 for r in s[s.osm_type.eq('relation')&s.osm_id.isin(relids)].itertuples():wayids.update(m['ref'] for m in json.loads(r.refs_or_members_json) if m['type']=='w')
 for r in s[s.osm_type.eq('way')&s.osm_id.isin(wayids)].itertuples():nodeids.update(json.loads(r.refs_or_members_json))
 hist=json.loads((H/'sources/missing_boundary_way_history_acquisition.json').read_text())
 for r in hist:
  if r['selected_snapshot_way']:nodeids.update(r['selected_snapshot_way']['refs'])
 request=dict(status='DEPENDENCY_IDS_FIXED_BEFORE_SECOND_STREAM',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),node_ids=sorted(nodeids),way_ids=sorted(wayids),relation_ids=sorted(relids),source='Original snapshot IDs and boundaryrefs; four missing memberwayrefs from actual primaryOSMhistory selectedat<=snapshot, tobeconfirmedagainstactualstreamwayversionandrefs beforeuse.',geometry='Actual boundary reconstruction/containment only; observed sourcepoint never replacedbycentroid ornearestroad.')
 (H/'boundary_dependency_request.json').write_text(json.dumps(request,indent=2)+'\n');assert not (H/'actual2021_boundary_dependency_source_objects.parquet').exists();p=subprocess.Popen([sys.executable,'-c',CONSUMER,str(H)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);digest=hashlib.sha256();n=0;start=time.monotonic()
 with requests.get(URL,stream=True,timeout=(30,90)) as response:
  response.raise_for_status()
  for b in response.iter_content(4*1024*1024):
   p.stdin.write(b);digest.update(b);n+=len(b)
   if n//536870912!=(n-len(b))//536870912:print('streamed',n,flush=True)
 p.stdin.close();out=p.stdout.read().decode();err=p.stderr.read().decode();code=p.wait();r=dict(status='COMPLETE_EXACT_SOURCE_DEPENDENCY_STREAM' if code==0 and n==SIZE and digest.hexdigest()==SHA else 'FAILED',bytes=n,sha256=digest.hexdigest(),expected_sha256=SHA,consumer_returncode=code,consumer_stdout=out,consumer_stderr=err,seconds=time.monotonic()-start,request_sha256=hashlib.sha256((H/'boundary_dependency_request.json').read_bytes()).hexdigest(),full_raw_disk_copy=False);(H/'boundary_dependency_stream_receipt.json').write_text(json.dumps(r,indent=2)+'\n');assert r['status']=='COMPLETE_EXACT_SOURCE_DEPENDENCY_STREAM';print(json.dumps(r),flush=True)
if __name__=='__main__':main()
