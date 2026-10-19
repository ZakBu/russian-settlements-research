#!/usr/bin/env python3
"""Reuse the auditor's own checked block algorithm with new pinned stocks.

No author modules are imported, and the first-wave freeze is not overwritten.
"""
from pathlib import Path
import importlib.util,hashlib,json
import pandas as pd
HERE=Path(__file__).resolve().parent;R=HERE.parent;B=R.parent;OUT=HERE/'wave2'
def main():
 spec=importlib.util.spec_from_file_location('independent_first_wave',HERE/'independent_audit.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.OUT=OUT;mod.CHECKS=[]
 p=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet',columns=['id','lat','lon']);features={}
 for a,b in [(2011,2025),(2016,2021),(2021,2025)]:
  x=pd.read_parquet(OUT/f'calendar_{a}.parquet').set_index('id').reindex(p.id);y=pd.read_parquet(OUT/f'calendar_{b}.parquet').set_index('id').reindex(p.id);features[f'pinned_exact_{a}_{b}']=(x.diversity.to_numpy(),y.diversity.to_numpy())
 mod.spatial(p,features)
 audit={'status':'PASS' if all(x['pass'] for x in mod.CHECKS) else 'FAIL','n_checks':len(mod.CHECKS),'checks':mod.CHECKS,'algorithm_sha256':hashlib.sha256((HERE/'independent_audit.py').read_bytes()).hexdigest(),'output_sha256':hashlib.sha256((OUT/'equal_area_block_sensitivity.csv').read_bytes()).hexdigest(),'interpretation':'Geographic composition envelopes conditional on observed legal witness measurement; not confidence intervals for physical functions. No national p-values or causal inference.'};(OUT/'CALENDAR_SPATIAL_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(audit['status'],len(mod.CHECKS));assert all(x['pass'] for x in mod.CHECKS)
if __name__=='__main__':main()
