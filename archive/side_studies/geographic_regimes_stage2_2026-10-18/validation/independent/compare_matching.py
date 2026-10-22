import pandas as pd,numpy as np,hashlib,json
from pathlib import Path
p=Path('stage2_work/replication')
a=pd.read_csv(p/'independent_all_matching.csv.gz').rename(columns={'unit_a':'a','unit_b':'b','max_abs_std_diff':'max_abs_difference','rms_std_diff':'rms_difference'})
b=pd.read_csv('stage2_work/comparison/comparison_registry.csv.gz')
for d in [a,b]:d['pair_lo']=d[['a','b']].min(axis=1);d['pair_hi']=d[['a','b']].max(axis=1)
keys=['kind','pair_lo','pair_hi'];a=a.set_index(keys);b=b.set_index(keys)
missing_primary=a.index.difference(b.index);missing_independent=b.index.difference(a.index)
errors=[];maxdiff=0
# Entire registry membership,all region numeric values +10 deterministic local pairs.
indices=list(a.index[a.index.get_level_values(0)=='region'])
local=list(a.index[a.index.get_level_values(0)!='region']);local.sort(key=lambda v:hashlib.sha256((':'.join(v)).encode()).hexdigest());indices+=local[:10]
for key in indices:
 if key not in b.index:continue
 for col in ['rms_difference','max_abs_difference']+[c for c in a.columns if c.startswith('std_diff_')]:
  diff=abs(abs(float(a.loc[key,col]))-abs(float(b.loc[key,col])));maxdiff=max(maxdiff,diff)
  if diff>1e-10:errors.append(dict(key=key,field=col,absolute_difference=diff))
b.loc[indices].to_csv(p/'matching_primary_checked_subset.csv',index=True)
receipt=dict(status='passed' if not len(missing_primary) and not len(missing_independent) and not errors else 'failed',independent_n=len(a),primary_n=len(b),missing_from_primary=len(missing_primary),missing_from_independent=len(missing_independent),complete_region_numeric_pairs=sum(k[0]=='region' for k in indices),deterministic_local_numeric_pairs=sum(k[0]!='region' for k in indices),max_abs_difference=maxdiff,errors=errors,independent_sha256=hashlib.sha256((p/'independent_all_matching.csv.gz').read_bytes()).hexdigest(),primary_sha256=hashlib.sha256(Path('stage2_work/comparison/comparison_registry.csv.gz').read_bytes()).hexdigest(),notes='Signed main differences compared in absolute magnitude; all pair membership checked; main compare implementation never read.')
json.dump(receipt,open(p/'matching_receipt.json','w'),indent=2);print(receipt)
