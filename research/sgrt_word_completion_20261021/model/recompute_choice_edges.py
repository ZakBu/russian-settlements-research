#!/usr/bin/env python3
"""Recompute exact declared Huff edges from durable inputs, optionally for chosen origins."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
import run_word_model as m

def run(inputs,model_dir,output,origins=None,function=None):
 config=json.loads(inputs.read_text());receipt=json.loads((model_dir/'run_receipt.json').read_text())
 if receipt['model_code_sha256']!=m.sha(Path(m.__file__)):raise ValueError('Model implementation differs from saved run')
 if receipt['configuration_sha256']!=m.sha(inputs):raise ValueError('Configuration differs from saved model run')
 source=m.travel_source(config)
 if receipt['source_sha256'][str(source.relative_to(m.REPO))]!=m.sha(source):raise ValueError('Routing source differs from saved model run')
 nodes=pd.read_parquet(model_dir/'nodes.parquet');mass=pd.read_parquet(model_dir/'own_mass_components.parquet');centers=pd.read_parquet(model_dir/'candidate_centers.parquet')
 if origins:
  unknown=set(origins)-set(nodes.id)
  if unknown:raise ValueError('Unknown origin IDs: '+repr(sorted(unknown)))
  config['origin_id_filter']=origins
 travel,source=m.load_travel(config,nodes,centers,mass)
 if function:
  count=mass['physical_'+function+'_count_proxy'];providers=mass.loc[count.gt(0),['id']].copy();providers['own_positive_mass']=np.log1p(count[count.gt(0)].to_numpy())
 else:providers=centers[centers.intrinsic_empirical_rank.eq(centers.intrinsic_empirical_rank.min())] if config.get('initial_assignment_center_scope')=='lowest_empirical_order_only' else centers
 _,edges=m.huff_assign(nodes,providers,travel,config,preserve_cores=False)
 output.parent.mkdir(parents=True,exist_ok=True);edges.to_parquet(output,index=False)
 output.with_suffix(output.suffix+'.receipt.json').write_text(json.dumps({'status':'RECOMPUTED_EXACT_DECLARED_HUFF_EDGES','rows':len(edges),'origins_filter':origins,'function':function,'configuration_sha256':m.sha(inputs),'routing_source_sha256':m.sha(source),'output_sha256':m.sha(output)},ensure_ascii=False,indent=2)+'\n')
 print('Recomputed',len(edges),'declared Huff edges to',output)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,default=m.HERE/'model_inputs_2021_restricted.json');p.add_argument('--model-dir',type=Path,default=m.HERE/'output_2021_restricted_baseline');p.add_argument('--output',type=Path,required=True);p.add_argument('--origin-id',action='append');p.add_argument('--function',choices=['education','healthcare','hospital','trade','finance','administration']);a=p.parse_args();run(a.inputs,a.model_dir,a.output,a.origin_id,a.function)
