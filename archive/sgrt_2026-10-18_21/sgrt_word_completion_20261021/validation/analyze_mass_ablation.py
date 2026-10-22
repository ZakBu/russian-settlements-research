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
 manifest=json.loads((model/'output_manifest.json').read_text())
 receipt=json.loads((model/'run_receipt.json').read_text())
 assert receipt.get('status','').startswith('COMPUTED') and manifest['run_receipt_sha256']==sha(model/'run_receipt.json'),'Completed model snapshot required'
 for p in inputs:assert manifest['files'][p.name]['sha256']==before[str(p)],'Mass input differs from completed snapshot'
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
 # Separate observation-availability scenario: positive registration witnesses only.
 # Re-standardize on the full original axis, not selectively on candidate centers.
 raw=mass.registered_organization_economy_raw
 transformed=np.log1p(raw.where(raw.gt(0)))
 z=(transformed-transformed.mean())/transformed.std(ddof=0)
 available=mass[blocks].copy();available['block_economy_z']=z
 alternate=np.exp(available.mean(axis=1).clip(-20,20));mask=mass.id.isin(centers.id)
 a=mass.loc[mask,'own_positive_mass'];b=alternate[mask];valid=a.notna()&b.notna()
 zero_sensitivity={'scenario':'registration_zero_is_unknown_positive_only_standardization','full_axis_numeric_records':int(raw.notna().sum()),'full_axis_positive_witnesses':int(raw.gt(0).sum()),'full_axis_zero_accepted_witnesses':int(raw.eq(0).sum()),'candidate_centers':int(mask.sum()),'candidate_zero_accepted_witnesses':int(raw[mask].eq(0).sum()),'comparable_centers':int(valid.sum()),'spearman_mass_order':float(spearmanr(a[valid],b[valid]).statistic),'median_mass_ratio':float((b[valid]/a[valid]).median()),'catchments_recomputed':False,'description':'Primary count is observed RFSD registration/reporting witness intensity. This alternative treats no accepted witness as missing economic evidence; neither measures jobs or the complete local economy.'}
 (out/'registration_zero_availability_sensitivity.json').write_text(json.dumps(zero_sensitivity,indent=2)+'\n')
 pd.DataFrame({'id':mass.loc[mask,'id'],'original_mass':a,'registration_positive_only_mass':b,'registration_positive_witness':raw[mask].gt(0)}).to_parquet(out/'registration_zero_availability_mass_by_center.parquet',index=False)
 assert before=={p:sha(Path(p)) for p in before},'Model changed during ablation'
 receipt={'status':'COMPUTED_DESCRIPTIVE_MASS_ABLATION','input_sha256':before,'blocks':blocks,'candidate_count':len(m),'original_mass_formula_independently_reproduced':True,'catchments_recomputed':False,'independent_attraction_validated':False,'scope':'Leave-one-block-out positive mass; fixed candidates and original source standardization. No observed-flow accuracy or refitted hierarchy claimed. Missing blocks remain missing; remaining available blocks averaged.'}
 (out/'mass_block_ablation_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);a=p.parse_args();run(a.model)
