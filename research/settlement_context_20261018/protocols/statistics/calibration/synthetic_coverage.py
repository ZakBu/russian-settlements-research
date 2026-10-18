"""Focused bootstrap-coverage diagnostic on real coordinates; never reads outcomes."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import sys,json,hashlib,platform,argparse
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from statistical_utils import split_blocks
SEED=20261018
N_SIM=300
N_BOOT=499
LENGTHS_KM=[0,100,300]

def wilson(k,n,z=1.959963984540054):
 p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d
 h=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return [float(c-h),float(c+h)]

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--features',required=True);ap.add_argument('--output',required=True);args=ap.parse_args()
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 # Explicit usecols: no real outcome is loaded, selected population2010 only fixes actual risk weights.
 f=pd.read_csv(args.features,usecols=['entity_uid','longitude_2010','latitude_2010','population_2010'])
 block,hold,fold=split_blocks(f.longitude_2010,f.latitude_2010)
 mask=hold&(f.population_2010.to_numpy()>0)
 q=f.loc[mask,['longitude_2010','latitude_2010']].copy();q['block_id']=block[mask]
 # Unit-vector centroid handles longitude wrap, chord distances guarantee PSD Gaussian kernel.
 lat=np.deg2rad(q.latitude_2010.to_numpy());lon=np.deg2rad(q.longitude_2010.to_numpy())
 q['vx']=np.cos(lat)*np.cos(lon);q['vy']=np.cos(lat)*np.sin(lon);q['vz']=np.sin(lat)
 g=q.groupby('block_id').agg(n=('vx','size'),vx=('vx','mean'),vy=('vy','mean'),vz=('vz','mean')).reset_index()
 v=g[['vx','vy','vz']].to_numpy();v/=np.linalg.norm(v,axis=1)[:,None]
 g['centroid_lon']=np.rad2deg(np.arctan2(v[:,1],v[:,0]));g['centroid_lat']=np.rad2deg(np.arcsin(v[:,2]))
 g.to_csv(out/'holdout_block_geometry.csv',index=False)
 n=g.n.to_numpy(float);w=n/n.sum();B=len(g)
 d2=np.maximum(0,2-2*np.clip(v@v.T,-1,1))*6371.0088**2
 results=[]; rng=np.random.default_rng(SEED)
 for length in LENGTHS_KM:
  cov=np.eye(B) if length==0 else np.exp(-d2/(2*length**2))
  # Fixed tiny jitter ensures numerical stability; recorded in covariance.
  cov=cov+np.eye(B)*1e-10
  chol=np.linalg.cholesky(cov)
  fields=rng.standard_normal((N_SIM,B))@chol.T
  means=fields@w;covered=[];positive=[];widths=[];ses=[]
  for field in fields:
   draw=rng.integers(0,B,size=(N_BOOT,B))
   boot=(field[draw]*n[draw]).sum(axis=1)/n[draw].sum(axis=1)
   lo,hi=np.quantile(boot,[.025,.975])
   covered.append(lo<=0<=hi);positive.append(lo>0);widths.append(hi-lo);ses.append(np.std(boot,ddof=1))
  k=int(np.sum(covered));kp=int(np.sum(positive));truth_se=float(np.sqrt(w@cov@w))
  results.append({'lengthscale_km':length,'covariance':'I + 1e-10 I' if length==0 else 'exp(-spherical_chord_distance_km^2/(2*lengthscale_km^2)) + 1e-10 I',
    'coverage_n':k,'simulations':N_SIM,'coverage':k/N_SIM,'coverage_mc_wilson95':wilson(k,N_SIM),
    'lower_ci_above_zero_n':kp,'lower_ci_above_zero_fraction':kp/N_SIM,'positive_mc_wilson95':wilson(kp,N_SIM),
    'mean_interval_width':float(np.mean(widths)),'mean_bootstrap_se':float(np.mean(ses)),
    'true_ensemble_mean_se':truth_se,'empirical_mean_sd':float(np.std(means,ddof=1)),
    'bootstrap_se_to_true_se':float(np.mean(ses)/truth_se),'empirical_mean':float(np.mean(means))})
  pd.DataFrame({'simulation':np.arange(N_SIM),'ensemble_mean':means,'covered_null0':covered,'lower_ci_above0':positive,'interval_width':widths,'bootstrap_se':ses}).to_csv(out/f'simulations_length{length}.csv',index=False)
 report={'status':'computed_focused_known_null_bootstrap_coverage_diagnostic','seed':SEED,'n_simulations':N_SIM,'bootstrap_replicates':N_BOOT,
 'holdout_blocks':B,'risk_rows':int(mask.sum()),'feature_sha256':hashlib.sha256(Path(args.features).read_bytes()).hexdigest(),
 'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'feature_columns_loaded':list(f.columns),
 'estimator':'row-weighted mean of zero-mean block-constant Gaussian synthetic loss differences, n2010-positive rows per actual holdout block',
 'resampling':'uniform resampling of whole actual holdout blocks, keeping block n weights; percentile 95% CI',
 'true_estimand':'unconditional Gaussian ensemble expectation zero, conditional on fixed real geometry and weights',
 'limitations':['No real 2021 outcomes or predictions loaded. Not a model-selection, learner, predictive-gain or p-value calibration.',
 'Synthetic differences constant within each block; all dependence specified by idealized isotropic centroid field.',
 'Gaussian field defined using spherical chord distance to ensure positive-semidefinite covariance; not measured real residual correlation.',
 '300 Monte Carlo replicates and 499 bootstrap resamples give bounded diagnostic precision; intervals shown are Monte Carlo binomial Wilson, not research-effect uncertainty.',
 'Coverage failures at an assumed lengthscale do not estimate actual research CI coverage; passing IID case does not validate spatial independence.'],
 'results':results,'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__}
 (out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
