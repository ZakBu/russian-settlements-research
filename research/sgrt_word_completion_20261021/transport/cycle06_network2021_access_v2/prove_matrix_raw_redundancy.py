"""Read-only byte witness for optional release of duplicate routing shard payloads."""
from pathlib import Path
import json,hashlib
import numpy as np,pyarrow.parquet as pq
from graph_io import sha
H=Path(__file__).resolve().parent;T=Path('/tmp/sgrt_network2021_access_v2');DT=np.dtype([('origin','<u4'),('center','<u4'),('network_minutes','<f4')])
def main():
 m=json.loads((H/'candidate_travel_times_manifest.json').read_text());parts=iter(m['parts']);offset=0;receipts=[]
 for folder in sorted(T.glob('matrix_shard_*')):
  rawpath=folder/'matrix_pairs.bin';raw=np.memmap(rawpath,dtype=DT,mode='r');h=hashlib.sha256();checks=[]
  for start in range(0,len(raw),1000000):
   block=raw[start:start+1000000];part=next(parts);p=H/part['path'];assert sha(p)==part['sha256'];d=pq.read_table(p);assert len(d)==len(block)==part['rows'];rebuilt=np.empty(len(d),dtype=DT);rebuilt['origin']=d['origin_index'].to_numpy();rebuilt['center']=d['destination_index'].to_numpy()-offset;rebuilt['network_minutes']=d['network_minutes'].to_numpy();a=hashlib.sha256(block.tobytes()).hexdigest();b=hashlib.sha256(rebuilt.tobytes()).hexdigest();assert a==b;h.update(block.tobytes());checks.append(dict(part=part['path'],rows=len(d),raw_chunk_sha256=a,reconstructed_from_accepted_part_sha256=b))
  receipts.append(dict(raw_path=str(rawpath),bytes=rawpath.stat().st_size,rows=len(raw),raw_sha256=h.hexdigest(),destination_offset=offset,chunk_checks=checks));offset+=(folder/'source_nodes.bin').stat().st_size//4
 assert next(parts,None) is None;assert sum(r['rows'] for r in receipts)==m['rows']
 r=dict(status='PROVEN_BYTE_EXACT_DUPLICATE_ROUTE_SHARDS',accepted_matrix_manifest_sha256=sha(H/'candidate_travel_times_manifest.json'),all_rows=sum(x['rows'] for x in receipts),duplicate_bytes=sum(x['bytes'] for x in receipts),raw_shards=receipts,deleted=False,source_geometries_graphs_reverse_bins_and_compact_parts_not_disposable_by_this_proof=True)
 (H/'duplicate_matrix_raw_redundancy_proof.json').write_text(json.dumps(r,indent=2)+'\n');print(r['status'],r['duplicate_bytes'])
if __name__=='__main__':main()
