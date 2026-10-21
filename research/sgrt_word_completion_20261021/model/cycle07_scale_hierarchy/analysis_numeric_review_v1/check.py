"""Independent numeric countercheck on generated data only; no real outcomes."""
from pathlib import Path
import sys,json,hashlib
import numpy as np,pandas as pd
from scipy.stats import t
BASE=next(p for p in Path(__file__).resolve().parents if (p/'analysis').is_dir() and (p/'model').is_dir())
sys.path.insert(0,str(BASE/'analysis/cycle07_tools'))
import run_analysis as tested
rng=np.random.default_rng(711);n=120;x1=rng.normal(size=n);x2=rng.normal(size=n);y=2*x1-3*x2+rng.normal(size=n)
d=pd.DataFrame(dict(unit_id=[f'u{i:03}' for i in range(n)],candidate_cap=60,region=[f'r{i%12:02}' for i in range(n)],center_id=[f'c{i}' for i in range(n)],name='generated',lat=rng.uniform(40,60,n),lon=rng.uniform(30,60,n),x1=x1,x2=x2,constant=1.,duplicate=2*x1,outcome=y))
d.loc[0,'x2']=np.nan;d.loc[1,'x1']=np.inf;d.loc[2,'region']=None
p=json.loads((BASE/'analysis/cycle07_tools/PROTOCOL_v1.json').read_text());p['moran_neighbors']=3
terms={'M1':['x1'],'M2':['x1','x2','constant','duplicate']}
r=tested.estimate(d,'INDEPENDENT_SYNTHETIC','outcome',terms,p)
checks={};sample=d.iloc[3:].sort_values('unit_id');groups=sample.region.to_numpy();ys=sample.outcome.to_numpy();G=len(np.unique(groups));N=len(sample)
checks['same117commonrows']=len(r['metrics'])==2 and all(x['n']==117 for x in r['metrics'])
checks['same5folds_bothmodels']=pd.DataFrame(r['predictions']).groupby('unit_id').cv_fold.nunique().eq(1).all()
checks['drop_constant_and_duplicate']=next(x for x in r['metrics'] if x['model']=='M2')['dropped_constant_terms']=='constant' and next(x for x in r['metrics'] if x['model']=='M2')['dropped_collinear_terms']=='duplicate'
seed=p['seed']+int(hashlib.sha256(b'INDEPENDENT_SYNTHETIC|outcome|60').hexdigest()[:8],16);unique=sorted(set(groups));codes=pd.Categorical(groups,categories=unique).codes;draws=np.random.default_rng(seed).multinomial(G,np.full(G,1/G),size=499)
for model,cols in [('M1',['x1']),('M2',['x1','x2'])]:
 raw=sample[cols].to_numpy();mu=raw.mean(0);sd=raw.std(0);Z=np.c_[np.ones(N),(raw-mu)/sd];P=Z.shape[1];bread=np.linalg.inv(Z.T@Z);beta=np.linalg.solve(Z.T@Z,Z.T@ys);res=ys-Z@beta;meat=np.zeros((P,P))
 for g in unique:
  score=(Z[groups==g]*res[groups==g,None]).sum(0);meat+=score[:,None]*score[None,:]
 cov=(G/(G-1))*((N-1)/(N-P))*bread@meat@bread;se=np.sqrt(np.diag(cov));critical=t.ppf(.975,G-1)
 coeff=[x for x in r['coefficients'] if x['model']==model]
 checks[model+'_beta_OLS']=np.allclose([x['beta'] for x in coeff],beta,rtol=1e-10,atol=1e-10)
 checks[model+'_CR1_se']=np.allclose([x['se_cluster_region'] for x in coeff],se,rtol=1e-10,atol=1e-10)
 checks[model+'_cluster_t_intervals']=np.allclose([x['ci95_lower'] for x in coeff],beta-critical*se,rtol=1e-10,atol=1e-10) and all(x['ci_dof']==G-1 for x in coeff)
 pred=pd.DataFrame([x for x in r['predictions'] if x['model']==model]).set_index('unit_id').loc[sample.unit_id]
 expected=np.empty(N)
 for fold in range(5):
  test=pred.cv_fold.to_numpy()==fold;train=~test
  assert set(groups[test]).isdisjoint(groups[train]);center=raw[train].mean(0);scale=raw[train].std(0);trainZ=np.c_[np.ones(train.sum()),(raw[train]-center)/scale];testZ=np.c_[np.ones(test.sum()),(raw[test]-center)/scale];b=np.linalg.solve(trainZ.T@trainZ,trainZ.T@ys[train]);expected[test]=testZ@b
 checks[model+'_CV_train_only_scaling']=np.allclose(pred.group_oof_prediction,expected,rtol=1e-10,atol=1e-10)
 values=[]
 for draw in draws:
  W=draw[codes];A=Z.T@(Z*W[:,None]);B=Z.T@(ys*W)
  if np.linalg.matrix_rank(A)==P:values.append(np.linalg.solve(A,B))
 bounds=np.quantile(values,[.025,.975],axis=0);bs=[x for x in r['bootstrap'] if x['model']==model]
 checks[model+'_499same_region_draws']=all(x['requested_replicates']==499 and x['paired_region_draw_seed']==seed and x['full_rank_replicates']==len(values) for x in bs)
 checks[model+'_weighted_cluster_percentiles']=np.allclose([x['ci95_lower'] for x in bs],bounds[0],rtol=1e-9,atol=1e-9) and np.allclose([x['ci95_upper'] for x in bs],bounds[1],rtol=1e-9,atol=1e-9)
 # Independent dense spherical kNN union and row normalization, with no ties.
 lat=np.radians(sample.lat.to_numpy());lon=np.radians(sample.lon.to_numpy());xyz=np.c_[np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)];dist=np.sqrt(((xyz[:,None,:]-xyz[None,:,:])**2).sum(2));np.fill_diagonal(dist,np.inf);idx=np.argsort(dist,axis=1)[:,:3];A=np.zeros((N,N));A[np.arange(N)[:,None],idx]=1;A=np.maximum(A,A.T);W=A/A.sum(1)[:,None];z=res-res.mean();den=z@z;I=z@W@z/den;E=-1/(N-1);sim=[];rr=np.random.default_rng(p['seed'])
 for _ in range(499):
  zz=rr.permutation(z);sim.append(zz@W@zz/den)
 tail=(1+np.count_nonzero(np.abs(np.asarray(sim)-E)>=abs(I-E)))/500
 actual=next(x for x in r['spatial'] if x['model']==model)
 checks[model+'_dense_knn_Moran_I']=abs(actual['moran_i']-I)<1e-12
 checks[model+'_499_Moran_inclusive_tail']=abs(actual['two_sided_permutation_p']-tail)<1e-12
checks['minimum_common_sample_gate']=not tested.estimate(d.iloc[:50],'SMALL','outcome',terms,p)['metrics']
assert all(checks.values()),checks
out=Path(__file__).resolve().parent/'numeric_generated_data_receipt.json';out.write_text(json.dumps({'status':'PASS_GENERATED_DATA_NUMERIC_PRIMITIVES_NO_REAL_FITS','all_checks_passed':True,'n_checks':len(checks),'checks':{k:bool(v) for k,v in checks.items()},'runner_sha256':hashlib.sha256(Path(tested.__file__).read_bytes()).hexdigest(),'real_demographic_outcomes_read':False,'source_admission_not_covered':True},indent=2));print(out,len(checks),'PASS')
