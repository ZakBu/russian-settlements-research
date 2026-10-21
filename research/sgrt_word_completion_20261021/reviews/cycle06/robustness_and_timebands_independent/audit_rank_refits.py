#!/usr/bin/env python3
"""Independent sklearn refits for every declared regional draw/leaveout.
Does not import producer model or robustness code. Fixed Ci only.
"""
from pathlib import Path
import json,hashlib,os,concurrent.futures
import numpy as np,pandas as pd
from sklearn.mixture import GaussianMixture
from threadpoolctl import threadpool_limits
H=Path(__file__).resolve().parent;ROOT=H.parents[2];REPO=next(p for p in H.parents if (p/'.git').exists());R=ROOT/'robustness/cycle06_access_v2_baseline';M=ROOT/'model/output_cycle06_access_v2_baseline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def boundaries(g):
 order=np.argsort(g.means_[:,0]);mu=g.means_[order,0];var=g.covariances_[order,0,0];w=g.weights_[order];out=[]
 for j in range(len(mu)-1):
  aa=(1/var[j+1]-1/var[j])/2;bb=mu[j]/var[j]-mu[j+1]/var[j+1];cc=np.log(w[j]/w[j+1])-.5*np.log(var[j]/var[j+1])-.5*mu[j]**2/var[j]+.5*mu[j+1]**2/var[j+1]
  roots=np.polynomial.polynomial.polyroots([cc,bb,aa]) if abs(aa)>1e-12 else ([-cc/bb] if abs(bb)>1e-12 else []);valid=[float(np.real(v)) for v in roots if abs(np.imag(v))<1e-8 and mu[j]<np.real(v)<mu[j+1]];mid=(mu[j]+mu[j+1])/2;out.append(min(valid,key=lambda v:(abs(v-mid),v)) if valid else mid)
 return np.array(out)
def init():
 global C,CFG,REG,LAB,ROWS
 threadpool_limits(1);C=pd.read_parquet(M/'candidate_centers.parquet');C['region']=C.region.fillna('EXTERNAL_ANCHOR_REGION_UNSPECIFIED');REG=np.array(sorted(C.region.unique()));CFG=json.loads((ROOT/'model_inputs_cycle06/final_access_v2/config_baseline_final.json').read_text());LAB=pd.read_parquet(R/'candidate_ranks_by_replicate.parquet');ROWS=pd.read_parquet(R/'rank_replicates.parquet')
def job(task):
 kind,i=task;omitted=None
 if kind=='baseline':sample=C
 elif kind=='block_bootstrap':
  draw=np.random.default_rng(2026102105+i).choice(REG,size=len(REG),replace=True);sample=pd.concat([C[C.region.eq(v)] for v in draw],ignore_index=True)
 else:omitted=REG[i];sample=C[C.region.ne(omitted)]
 spec=CFG['rank_index'];v=sample[spec['column']].to_numpy(float);x=(np.log(v) if spec['transform']=='log' else v)[:,None];train=x if len(x)<=12000 else x[np.sort(np.random.default_rng(CFG['model']['random_seed']).choice(len(x),12000,replace=False))];sels=[];fits={}
 for k in range(1,min(CFG['model']['maximum_rank_components'],len(x)//CFG['model']['minimum_rank_cluster_size'])+1):
  g=GaussianMixture(n_components=k,covariance_type='full',reg_covar=1e-4,random_state=CFG['model']['random_seed'],n_init=3,max_iter=250).fit(train);b=boundaries(g);counts=np.bincount(np.searchsorted(b,x[:,0],side='right'),minlength=k);ok=g.converged_ and counts.min()>=CFG['model']['minimum_rank_cluster_size'];sels.append((k,g.bic(train),ok));fits[k]=(b,g)
 admissible=[a for a in sels if a[2]];k=min(admissible,key=lambda z:z[1])[0];b,g=fits[k];allv=C[spec['column']].to_numpy(float);allv=np.log(allv) if spec['transform']=='log' else allv;labels=np.searchsorted(b,allv,side='right')+1;name='baseline' if kind=='baseline' else f'{kind}_{i:03d}';row=ROWS[(ROWS.kind==kind)&(ROWS.replicate==i)].iloc[0];same=np.array_equal(labels,LAB[name]);assert same,(kind,i,'labels');assert row.chosen_k==k and row.fit_candidate_records==len(x),(kind,i,'K/n')
 for j,t in enumerate(b):assert abs(row[f'boundary_{j+1}_if_present']-t)<1e-7,(kind,i,'boundary')
 # Independently calculate ARI by contingency combinations, not sklearn metric.
 f=pd.DataFrame({'a':C.intrinsic_empirical_rank,'b':labels});comb=lambda z:float((z*(z-1)/2).sum());cells=f.groupby(['a','b']).size().to_numpy(float);a=f.a.value_counts().to_numpy(float);bb=f.b.value_counts().to_numpy(float);pairs=len(f)*(len(f)-1)/2;expect=comb(a)*comb(bb)/pairs;den=(comb(a)+comb(bb))/2-expect;ari=(comb(cells)-expect)/den if den else 1.;assert abs(row.adjusted_rand_full_fixed_centers-ari)<1e-12
 samek=k==int(C.intrinsic_empirical_rank.max());fraction=float(np.mean(labels==C.intrinsic_empirical_rank.to_numpy()));assert (abs(row.same_ordinal_fraction_if_same_k-fraction)<1e-12) if samek else pd.isna(row.same_ordinal_fraction_if_same_k)
 if omitted is not None:
  mask=C.region.eq(omitted).to_numpy();assert row.heldout_candidate_count==mask.sum();expected=float(np.mean(labels[mask]==C.intrinsic_empirical_rank.to_numpy()[mask]));assert abs(row.heldout_same_ordinal_fraction_if_same_k-expected)<1e-12 if samek else pd.isna(row.heldout_same_ordinal_fraction_if_same_k)
 return dict(kind=kind,replicate=i,refit_chosen_k=k,all_fixed_center_labels_equal=same,ARI=ari,fit_records=len(x),n_boundaries=len(b))
def main():
 init();protocol=json.loads((R/'protocol.json').read_text());assert all(sha(REPO/k)==v for k,v in protocol['source_sha256'].items());freeze=json.loads((R/'freeze_manifest.json').read_text());assert all(sha(R/k)==v['sha256'] for k,v in freeze['files'].items());tasks=[('baseline',0)]+[('block_bootstrap',i) for i in range(200)]+[('leave_region_out',i) for i in range(len(REG))];out=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=2,initializer=init) as pool:
  for i,r in enumerate(pool.map(job,tasks)):
   out.append(r)
   if (i+1)%25==0:print('independent_refits',i+1,'/',len(tasks),flush=True)
 pd.DataFrame(out).to_csv(H/'all286_independent_rank_refits.csv',index=False);receipt=dict(status='ALL_REGIONAL_BOOTSTRAP_AND_LEAVEOUT_GMM_REFITS_INDEPENDENTLY_REPRODUCED',all_checks_passed=True,n_refits=len(out),bootstrap=200,leave_region_out=len(REG),baseline=1,frozen_Ci_only_not_catchment_refits=True,no_sampling_or_functional_tier_validation_claim=True,source_freeze_manifest_sha256=sha(R/'freeze_manifest.json'),model_manifest_sha256=sha(M/'output_manifest.json'),code_sha256=sha(Path(__file__)),refit_table_sha256=sha(H/'all286_independent_rank_refits.csv'));(H/'rank_refit_admission.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
