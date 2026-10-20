#!/usr/bin/env python3
"""Independent compact-output integrity and deterministic SciPy route spot-check.
Only runs after the final atomic COMPUTED receipt. Three part locations are
fixed before seeing any routes. This is a sampled algorithm check, not all-pair proof.
"""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra
H=Path(__file__).resolve().parent;ROOT=H.parent/'transport'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def run():
 rp=ROOT/'routing_receipt.json'
 if not rp.exists() or json.loads(rp.read_text()).get('status')!='COMPUTED':raise SystemExit('WAIT_ATOMIC_COMPUTED_RECEIPT; no matrix read')
 r=json.loads(rp.read_text());manpath=ROOT/'candidate_travel_times_manifest.json'
 if not manpath.exists():raise SystemExit('REPAIR_UNKNOWN_MANIFEST_FILENAME')
 manifest=json.loads(manpath.read_text());checks=[];before={str(rp):sha(rp),str(manpath):sha(manpath)}
 def check(name,ok):checks.append({'check':name,'pass':bool(ok)})
 check('frozen_manifest_matches_atomic_receipt',before[str(manpath)]==r['output_manifest_sha256']);check('declared_format',manifest['format']=='compact_parquet_parts_v1');check('declared_rowcount_conserved',sum(p['rows'] for p in manifest['parts'])==r['pairs']==manifest['rows'])
 maps=[]
 for key in ['origin_mapping','destination_mapping']:
  item=manifest[key];p=ROOT/item['path'];before[str(p)]=sha(p);check(key+'_bytes_match',before[str(p)]==item['sha256']);d=pd.read_parquet(p);check(key+'_id_unique',d.id.is_unique);check(key+'_indices_exact',np.array_equal(d[item['index_column']],np.arange(len(d))));maps.append(d)
 origins,destinations=maps;graphpath=ROOT/'routing_graph.npz';before[str(graphpath)]=sha(graphpath);check('actual_graph_matches_receipt',before[str(graphpath)]==r['graph_sha256'])
 for i,item in enumerate(manifest['parts']):
  p=ROOT/item['path'];before[str(p)]=sha(p);check(f'part{i}_frozen_sha',before[str(p)]==item['sha256']);check(f'part{i}_rowcount',pq.ParquetFile(p).metadata.num_rows==item['rows'])
 graph=load_npz(graphpath).transpose().tocsr();samples=[]
 for position in sorted(set([0,len(manifest['parts'])//2,len(manifest['parts'])-1])):
  item=manifest['parts'][position];table=pq.ParquetFile(ROOT/item['path']);batch=next(table.iter_batches(batch_size=1000,columns=['origin_index','destination_index','network_minutes'])).to_pandas();di=int(batch.destination_index.iloc[0]);sample=batch[batch.destination_index.eq(di)].head(100);dest=destinations.iloc[di]
  expected=dijkstra(graph,directed=True,indices=int(dest.road_node_index),limit=float(dest.routing_budget_minutes));oi=sample.origin_index.to_numpy(int);truth=expected[origins.iloc[oi].road_node_index.to_numpy(int)];stored=sample.network_minutes.to_numpy(float);error=np.abs(stored-truth)
  check(f'part{position}_sample_network_time_matches_independent_scipy',np.allclose(stored,truth,rtol=1e-5,atol=.05));check(f'part{position}_sample_indices_in_range',sample.origin_index.between(0,len(origins)-1).all() and sample.destination_index.between(0,len(destinations)-1).all());check(f'part{position}_sample_network_minutes_nonnegative',np.isfinite(stored).all() and (stored>=0).all())
  samples.append(dict(part_position=position,destination_id=dest.id,sampled_pairs=len(sample),max_absolute_network_minutes_error=float(error.max()),algorithm='independent SciPy directed Dijkstra on transposed actual CSR',numeric_tolerance_minutes=.05,relative_tolerance=1e-5))
 after={p:sha(Path(p)) for p in before};check('all_reviewed_bytes_stable',before==after)
 result={'status':'INDEPENDENT_COMPACT_INTEGRITY_AND_SAMPLED_ROUTES_VERIFIED' if all(c['pass'] for c in checks) else 'RETURN_TO_REPAIR_LOOP','checks':checks,'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'samples':samples,'source_sha256':before,'pairs':r['pairs'],'scope':'All compactpart hashes/rowcounts; deterministic first/middle/lastpart sampled networktimes. Not all-pair recomputation or observed trip validation. Predeclared .05minabsolute tolerance permits float32 edgeweights/accumulation differences.','scientific_final_allowed':False}
 (H/'compact_routes_independent_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['checks','source_sha256']},ensure_ascii=False,indent=2))
if __name__=='__main__':run()
