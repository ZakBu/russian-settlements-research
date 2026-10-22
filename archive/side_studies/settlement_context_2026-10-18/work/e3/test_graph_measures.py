"""Small correctness checks; no empirical outcomes."""
import json
import numpy as np
from pathlib import Path
from explore_morphology import graph_stats
n=6;i=np.array([0,1,2]);j=np.array([1,2,3]);p=np.ones(n)
a=graph_stats(n,i,j,np.ones(n,bool),p);keep=np.array([1,1,1,0,0,0],bool);b=graph_stats(n,i,j,keep,p)
assert a['lcc_n']==4 and b['lcc_n']==3
assert b['lcc_fixed']<a['lcc_fixed'] and b['lcc_active']>a['lcc_active']
rng=np.random.default_rng(20261018)
for k in range(100):
 ii,jj=np.triu_indices(20,1);sel=rng.uniform(size=len(ii))<.15;ii,jj=ii[sel],jj[sel]
 a=graph_stats(20,ii,jj,np.ones(20,bool),np.ones(20));b=graph_stats(20,ii,jj,rng.uniform(size=20)<.6,np.ones(20));assert b['lcc_n']<=a['lcc_n']
Path('research_staging/e3/synthetic_graph_checks.json').write_text(json.dumps(dict(seed=20261018,random_graph_checks=100,passed=True,denominator_counterexample={'before_lcc_fixed':4/6,'after_lcc_fixed':3/6,'before_lcc_active':4/6,'after_lcc_active':1},calibrated_conditional_null=False),indent=2))
