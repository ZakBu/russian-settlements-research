from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
from sklearn.mixture import GaussianMixture
from scipy.optimize import brentq
from scipy.stats import norm
from threadpoolctl import threadpool_limits
H=Path(__file__).resolve().parent;D=H.parent/'model/output_word_ci_2021_baseline';cfg=H.parent/'model/model_inputs_word_ci_2021.json';c=json.loads(cfg.read_text());r=json.loads((D/'empirical_ranks.json').read_text());d=pd.read_parquet(D/'candidate_centers.parquet');x=d[c['rank_index']['column']].to_numpy(float);checks=[]
def ck(k,v):checks.append(dict(check=k,pass_=bool(v)))
models={}
with threadpool_limits(limits=1):
 for s in r['selection']:
  k=s['components'];g=GaussianMixture(n_components=k,covariance_type='full',reg_covar=1e-4,random_state=c['model']['random_seed'],n_init=3,max_iter=250).fit(x[:,None]);models[k]=g;ck(f'k{k}_BIC_refit',np.isclose(g.bic(x[:,None]),s['bic_on_fixed_training_sample'],atol=1e-6));ck(f'k{k}_AIC_refit',np.isclose(g.aic(x[:,None]),s['aic_on_fixed_training_sample'],atol=1e-6))
valid=[s for s in r['selection'] if s['converged'] and s['minimum_ordered_interval_size_pass']];ck('chosen_minimum_BIC_among_admissible',r['chosen_components']==min(valid,key=lambda v:v['bic_on_fixed_training_sample'])['components']);g=models[r['chosen_components']];order=np.argsort(g.means_[:,0]);mu=g.means_[order,0];sd=np.sqrt(g.covariances_[order,0,0]);weights=g.weights_[order];ck('fitted_means_reproduced',np.allclose(mu,r['means_rank_index_ordered']));boundaries=[]
for i,s in enumerate(r['ordinal_boundary_details']):
 fun=lambda z:np.log(weights[i])+norm.logpdf(z,mu[i],sd[i])-np.log(weights[i+1])-norm.logpdf(z,mu[i+1],sd[i+1]);grid=np.linspace(mu[i],mu[i+1],10001);vals=fun(grid);roots=[]
 for j in np.flatnonzero(vals[:-1]*vals[1:]<0):roots.append(brentq(fun,grid[j],grid[j+1]))
 ck(f'boundary{i}_density_roots_numerically_independent',np.allclose(roots,s['weighted_density_roots_between_means'],atol=1e-8) if len(roots)==len(s['weighted_density_roots_between_means']) else False);mid=(mu[i]+mu[i+1])/2;chosen=min(roots,key=lambda z:(abs(z-mid),z)) if roots else mid;ck(f'boundary{i}_intersection_or_declared_midpoint',np.isclose(chosen,s['boundary'],atol=1e-8));boundaries.append(chosen)
expected=np.digitize(x,boundaries)+1;ck('every_ordinal_rank_recomputed',np.array_equal(expected,d.intrinsic_empirical_rank));ck('minimum_interval_cluster_sizes',np.bincount(expected)[1:].min()>=c['model']['minimum_rank_cluster_size']);ck('rank_input_not_population_only',c['rank_index']['uses_modeled_catchment'] and c['rank_index']['column']=='wordci_word_centrality_observed2021_frame_0_1');out=dict(status='EMPIRICAL_CI_RANK_SELECTION_INDEPENDENTLY_VERIFIED' if all(v['pass_'] for v in checks) else 'RETURN_TO_REPAIR_LOOP',n_checks=len(checks),n_failed=sum(not z['pass_'] for z in checks),checks=checks,chosen_orders=r['chosen_components'],ordered_interval_sizes=np.bincount(expected)[1:].tolist(),source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [cfg,D/'candidate_centers.parquet',D/'empirical_ranks.json']},scope='Independent refit all6GMM and numericalbracketing ofweighted-density intersections, explicitmidpointfallback. This verifies empirical reproducibility, not bootstraprankstability or observedfunctionalservicetiers.');(H/'empirical_ci_ranks_independent_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['checks','source_sha256']},ensure_ascii=False,indent=2))
