#!/usr/bin/env python3
from compute_matrix import *
def run():
 export_graph();destpath=REPO/'research/sgrt_word_completion_20261021/model/routing_destinations_budgets_frozen.parquet';cc=pd.read_parquet(destpath);snap=pd.read_parquet(ROOT/'settlement_road_snap.parquet');target=snap[snap.snap_km<=10].reset_index(drop=True);source=cc[['id','routing_budget_minutes']].merge(target,on='id',validate='one_to_one');sample=source.iloc[np.linspace(0,len(source)-1,100,dtype=int)].copy();subprocess.run(['g++','-O3','-std=c++17',str(ROOT/'route_matrix.cpp'),'-o',str(RAW/'route_matrix_benchmark')],check=True);shards=[]
 for k,indices in enumerate(np.array_split(np.arange(100),4)):
  d=RAW/f'benchmark100_{k}';d.mkdir(exist_ok=True)
  for name in ['rev_indptr.bin','rev_indices.bin','rev_weights.bin']:
   if not (d/name).exists():(d/name).symlink_to(RAW/name)
  target.road_node_index.to_numpy('uint32').tofile(d/'target_nodes.bin');target.snap_km.mul(4).to_numpy('float32').tofile(d/'target_connectors.bin');s=sample.iloc[indices];s.road_node_index.to_numpy('uint32').tofile(d/'source_nodes.bin');s.snap_km.mul(4).to_numpy('float32').tofile(d/'source_connectors.bin');s.routing_budget_minutes.to_numpy('float32').tofile(d/'source_budgets.bin');(d/'route_checkpoint.txt').unlink(missing_ok=True);shards.append(d)
 start=time.time()
 def execute(d):
  with open(d/'progress.log','w') as f:subprocess.run([str(RAW/'route_matrix_benchmark'),str(d)],check=True,stderr=f)
  return {'shard':str(d),'pairs':(d/'matrix_pairs.bin').stat().st_size//12,'log':(d/'progress.log').read_text()}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(execute,shards))
 seconds=time.time()-start;receipt={'status':'COMPUTED_BENCHMARK100','graph_sha256':sha(ROOT/'routing_graph.npz'),'frozen_budgets_sha256':sha(destpath),'deterministic_sample':'100 equally spaced rows across full accepted frozen union','accepted_destinations_total':len(source),'sample_budget_counts':sample.routing_budget_minutes.value_counts().to_dict(),'full_budget_counts':source.routing_budget_minutes.value_counts().to_dict(),'wall_seconds':seconds,'linear_full_projection_minutes':seconds/100*len(source)/60,'warning':'Projection depends on sample geography, concurrent load, worker straggling and conversion; not a completion promise.','workers':4,'shards':results};(ROOT/'routing_benchmark100_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
if __name__=='__main__':run()
