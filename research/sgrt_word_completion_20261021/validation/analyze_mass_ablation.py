#!/usr/bin/env python3
"""Descriptive leave-one-block-out mass sensitivity; not a refit or catchment validation."""
from pathlib import Path
import argparse,hashlib,json
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(model):
 inputs=[model/'own_mass_components.parquet',model/'candidate_centers.parquet']
 before={str(p):sha(p) for p in inputs}
 mass=pd.read_parquet(inputs[0]);centers=pd.read_parquet(inputs[1]);m=mass[mass.id.isin(centers.id)].copy()
 blocks=[c for c in m if c.startswith('block_') and c.endswith('_z')]
 expected=np.exp(m[blocks].mean(axis=1).clip(-20,20))
 assert np.allclose(expected,m.own_positive_mass,rtol=1e-12,equal_nan=True)
 rows=[];details=[]
 for dropped in blocks:
  x=np.exp(m[[c for c in blocks if c!=dropped]].mean(axis=1).clip(-20,20))
  valid=x.notna()&m.own_positive_mass.notna();a=m.loc[valid,'own_positive_mass'];b=x[valid]
  q=max(1,int(np.ceil(len(a)*.1)));topa=set(a.nlargest(q).index);topb=set(b.nlargest(q).index)
  ratios=b/a
  rows.append({'dropped_block':dropped,'candidate_centers':len(m),'comparable_centers':int(valid.sum()),'centers_with_dropped_block_observed':int(m[dropped].notna().sum()),'spearman_mass_order':float(spearmanr(a,b).statistic),'top_decile_jaccard':len(topa&topb)/len(topa|topb),'median_mass_ratio':float(ratios.median()),'mass_ratio_p05':float(ratios.quantile(.05)),'mass_ratio_p95':float(ratios.quantile(.95))})
  details.append(pd.DataFrame({'id':m.id,'dropped_block':dropped,'original_mass':m.own_positive_mass,'ablated_mass':x,'original_observed_blocks':m.n_observed_mass_blocks,'remaining_observed_blocks':m[[c for c in blocks if c!=dropped]].notna().sum(axis=1)}))
 out=ROOT/'validation'/model.name;out.mkdir(exist_ok=True)
 pd.DataFrame(rows).to_csv(out/'mass_block_ablation_summary.csv',index=False)
 pd.concat(details).to_parquet(out/'mass_block_ablation_by_center.parquet',index=False)
 assert before=={p:sha(Path(p)) for p in before},'Model changed during ablation'
 receipt={'status':'COMPUTED_DESCRIPTIVE_MASS_ABLATION','input_sha256':before,'blocks':blocks,'candidate_count':len(m),'original_mass_formula_independently_reproduced':True,'catchments_recomputed':False,'independent_attraction_validated':False,'scope':'Leave-one-block-out positive mass; fixed candidates and original source standardization. No observed-flow accuracy or refitted hierarchy claimed. Missing blocks remain missing; remaining available blocks averaged.'}
 (out/'mass_block_ablation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);a=p.parse_args();run(a.model)
