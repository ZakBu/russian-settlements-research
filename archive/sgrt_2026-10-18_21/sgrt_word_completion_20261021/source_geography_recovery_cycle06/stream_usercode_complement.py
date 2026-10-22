from pathlib import Path
import subprocess,sys,json,hashlib,time,requests,pandas as pd
H=Path(__file__).resolve().parent;URL='https://download.geofabrik.de/russia-210101.osm.pbf';SIZE=2969339717;SHA='1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe'
CONSUMER=r'''
from pathlib import Path
import osmium,pyarrow as pa,pyarrow.parquet as pq,json,hashlib,collections,sys
h=Path(sys.argv[1]);wanted=set(json.loads((h/'usercode_complement_request.json').read_text())['B_candidate_node_ids']);buf=[];count=collections.Counter();rawcodes=collections.Counter();n=0
for o in osmium.FileProcessor(osmium.io.File('-','pbf')).with_filter(osmium.filter.KeyFilter('place','boundary','ref:oktmo','oktmo','ref:okato','okato','ref:gar','ref:fias','fias','oktmo:user','okato:user')):
 t=dict(o.tags);typ='node' if o.is_node() else 'way' if o.is_way() else 'relation';original=('place' in t or t.get('boundary')=='administrative' or any(k in t for k in ['ref:oktmo','oktmo','ref:okato','okato','ref:gar','ref:fias','fias']));complement=not original and any(k in t for k in ['oktmo:user','okato:user']);Bnode=o.is_node() and int(o.id) in wanted
 for k in ['ref:oktmo','oktmo','oktmo:user']:
  if k in t:rawcodes[k]+=1
 if not complement and not Bnode:continue
 tags=json.dumps(t,sort_keys=True,ensure_ascii=False,separators=(',',':'));refs=None if o.is_node() else json.dumps([n.ref for n in o.nodes]) if o.is_way() else json.dumps([dict(type=m.type,ref=m.ref,role=m.role) for m in o.members],ensure_ascii=False)
 buf.append(dict(osm_type=typ,osm_id=int(o.id),osm_version=int(o.version),object_timestamp=str(o.timestamp),lat=float(o.location.lat) if o.is_node() and o.location.valid() else None,lon=float(o.location.lon) if o.is_node() and o.location.valid() else None,tags_json=tags,all_source_tags_sha256=hashlib.sha256(tags.encode()).hexdigest(),refs_or_members_json=refs,visible=bool(o.visible),deleted=bool(o.deleted),original_inventory_predicate=original,user_code_only_complement=complement,B_source_node_validation=Bnode));count[typ]+=1
pq.write_table(pa.Table.from_pylist(buf),h/'all_usercode_only_complement_and_B_source_nodes.parquet',compression='zstd');(h/'usercode_complement_extraction_receipt.json').write_text(json.dumps({'rows':len(buf),'counts':dict(count),'all_source_code_field_object_counts':dict(rawcodes),'B_candidate_node_ids_found':sorted(int(x['osm_id']) for x in buf if x['B_source_node_validation'])},indent=2)+'\n');print(json.dumps({'rows':len(buf),'counts':dict(count)}),flush=True)
'''
def main():
 b=pd.read_parquet(H/'B_v2_dated_exact_parent_source_assertions.parquet');ids=sorted(set(map(int,b.loc[b.candidate_status.eq('B_dated_exact_parent_candidate'),'source_osm_node_id'])));request={'scope':'ALL sourceobjects with usercode-only omitted by original predicate + actual21 B candidate nodes; all-source exactnative-code uniqueness check','B_candidate_node_ids':ids};(H/'usercode_complement_request.json').write_text(json.dumps(request,indent=2)+'\n');p=subprocess.Popen([sys.executable,'-c',CONSUMER,str(H)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);d=hashlib.sha256();n=0;start=time.monotonic()
 with requests.get(URL,stream=True,timeout=(30,90)) as r:
  r.raise_for_status()
  for block in r.iter_content(4*1024*1024):p.stdin.write(block);d.update(block);n+=len(block)
 p.stdin.close();out=p.stdout.read().decode();err=p.stderr.read().decode();rc=p.wait();receipt={'status':'COMPLETE_EXACT_SOURCE_COMPLEMENT_STREAM' if rc==0 and n==SIZE and d.hexdigest()==SHA else 'FAILED','actual_bytes':n,'actual_sha256':d.hexdigest(),'expected_bytes':SIZE,'expected_sha256':SHA,'returncode':rc,'stdout':out,'stderr':err,'seconds':time.monotonic()-start,'full_PBF_written_to_disk':False,'full_PBF_loaded_to_RAM':False};(H/'usercode_complement_stream_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True);assert receipt['status'].startswith('COMPLETE')
if __name__=='__main__':main()
