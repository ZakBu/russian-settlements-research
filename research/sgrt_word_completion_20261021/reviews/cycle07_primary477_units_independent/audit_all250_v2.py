from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');P=B/'model/cycle07_scale_hierarchy/source477_adminall_v2/output_primary_v1';O=B/'reviews/cycle07_primary477_units_independent';C=Path('/tmp/sgrt_cycle07_source477_adminall_cache_v1')
assert (P/'run_receipt.json').exists(),'Full primary50 run has not closed; no partial admission'
checks=[];watch={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ck(k,v,d=None):checks.append({'check':k,'pass_':bool(v),'detail':d})
def ari(a,b):
 _,a=np.unique(a,return_inverse=True);_,b=np.unique(b,return_inverse=True);na=np.bincount(a);nb=np.bincount(b);_,ns=np.unique(np.column_stack((a,b)),axis=0,return_counts=True);choose=lambda z:np.sum(z.astype(float)*(z-1)/2);n=len(a);A=choose(na);D=choose(nb);I=choose(ns);T=n*(n-1)/2;expected=A*D/T if T else 0.;maximum=(A+D)/2
 return (I-expected)/(maximum-expected)if maximum!=expected else 1.
def knee(y):
 n=len(y);side=max(10,int(np.ceil(.05*(n-1))))
 if n<2*side+1:return 'no_knee_insufficient_merge_path',None
 # Independently vectorized centered OLS SSE on every allowed split.
 x=np.arange(n,dtype=float);z=np.column_stack((x,y,x*x,y*y,x*y));c=np.vstack((np.zeros(5),np.cumsum(z,axis=0)))
 def loss(lo,hi):
  m=hi-lo;v=c[hi]-c[lo];xx=v[...,2]-v[...,0]**2/m;yy=v[...,3]-v[...,1]**2/m;xy=v[...,4]-v[...,0]*v[...,1]/m
  return np.maximum(0,yy-np.divide(xy*xy,xx,out=np.zeros_like(xx),where=xx>1e-15))
 candidates=np.arange(side,n-side);losses=loss(0,candidates+1)+loss(candidates,n);best=int(candidates[np.argmin(losses)]);single=float(loss(0,n));gain=(single-float(losses.min()))/single if single>1e-12 else 0
 return ('candidate_knee',best)if gain>=.25 else ('no_knee',None)
ledger=P/'all_50_bootstrap_ledger.parquet';summary=P/'retained_resolution_stability.csv';d=pd.read_parquet(ledger);s=pd.read_csv(summary).set_index('candidate_cap');ck('exact250_complete_unique_cap_replicate_keys',len(d)==250 and not d.duplicated(['replicate_id','candidate_cap']).any() and set(d.replicate_id)==set(range(50)) and set(d.candidate_cap)=={30,45,60,90,120})
p=pd.read_parquet(C/'provider_mapping.parquet');ordinary=~p.documented_external_context_anchor.fillna(False);regions=sorted(set(p.loc[ordinary,'region'].dropna().astype(str)));regindex={x:i for i,x in enumerate(regions)};mapped=p.region.astype(str).map(regindex);known=ordinary&mapped.notna();rng=np.random.default_rng(20261021);records=[]
for cap in (30,45,60,90,120):
 baseline=P/f'cap_{cap:03}_provider_knee_labels.npy';watch[str(baseline)]=sha(baseline);labels=np.load(baseline);mm=pd.read_parquet(P/f'cap_{cap:03}_raw_memberships.parquet',columns=['id','unit_id','partition_role']);mm=mm[mm.partition_role.eq('candidate_knee_or_fallback')].set_index('id');unit=mm.loc[p.id,'unit_id'].to_numpy();cross=pd.DataFrame({'label':labels,'unit':unit});ck(f'{cap}:baseline_labels_EXACT_actual_candidate_membership_partition',len(labels)==len(p) and cross.groupby('label').unit.nunique().eq(1).all() and cross.groupby('unit').label.nunique().eq(1).all())
for rep in range(50):
 draw=rng.multinomial(len(regions),np.full(len(regions),1/len(regions)));weights=np.ones(len(p));weights[known]=draw[mapped[known].astype(int)];mask=weights>0
 for cap in (30,45,60,90,120):
  row=d[(d.replicate_id==rep)&(d.candidate_cap==cap)].iloc[0];file=P/f'rep_{rep:02}_cap_{cap:03}_numeric_witnesses.npz';watch[str(file)]=sha(file);z=np.load(file);labels=z['provider_labels'];curve=z['objective_curve'];base=np.load(P/f'cap_{cap:03}_provider_knee_labels.npy');status,cut=knee(curve);assess=status=='candidate_knee' and mask.sum()>=20 and len(np.unique(base[mask]))>=2 and len(np.unique(labels[mask]))>=2;value=ari(base[mask],labels[mask])if assess else np.nan;prefix=f'{rep}:{cap}:'
  ck(prefix+'exactRNGdraw_and_full_sourceprovider_mask',np.array_equal(z['region_weights'],draw)and np.array_equal(z['positive_weight_provider_mask'],mask)and json.loads(row.region_weight_draw_json)==draw.tolist())
  ck(prefix+'complete_providerlabels_objective_numeric_path',labels.shape==(len(p),)and curve.ndim==1 and np.isfinite(curve).all()and np.diff(curve).min(initial=0)>=-1e-12 and len(curve)==row.n_merges+1)
  ck(prefix+'independent_knee_allbreakpoints',status==row.status and (cut==int(row.selected_merge)if pd.notna(row.selected_merge)else cut is None))
  ck(prefix+'all_assessability_coverage_and_fraction',assess==row.assessable and int(mask.sum())==row.n_compared_provider_seeds and np.isclose(mask.mean(),row.compared_provider_fraction)and int((draw>0).sum())==row.n_positive_weight_regions)
  ck(prefix+'ARI_exact_contingency_rebuild',np.isclose(value,row.ari,atol=1e-12,rtol=1e-12,equal_nan=True),{'rebuilt':value,'saved':float(row.ari)})
  fraction=cut/row.n_merges if assess and row.n_merges else np.nan;ck(prefix+'knee_fraction',np.isclose(fraction,row.knee_fraction,atol=1e-12,equal_nan=True));records.append({'replicate_id':rep,'candidate_cap':cap,'ari':value,'knee_fraction':fraction,'assessable':assess})
 print('REPLAYED_NUMERIC_WITNESSES',rep,flush=True)
r=pd.DataFrame(records);ret=[]
for cap,g in r.groupby('candidate_cap'):
 good=g.ari.notna()&g.knee_fraction.notna();a=g.loc[good,'ari'];k=g.loc[good,'knee_fraction'];med=a.median();q=a.quantile(.1);iqr=k.quantile(.75)-k.quantile(.25);accepted=good.sum()>=40 and med>=.8 and q>=.6 and iqr<=.15;row=s.loc[cap];ck(f'{cap}:full50_conditional_retention_no_hidden_drop',bool(row.accepted)==accepted and row.n_valid==int(good.sum())and np.allclose([row.median_ari,row.p10_ari,row.knee_fraction_iqr],[med,q,iqr],atol=1e-12,rtol=1e-12));ret.append(dict(candidate_cap=int(cap),accepted=bool(accepted),n_valid=int(good.sum()),median_ari=float(med),p10_ari=float(q),knee_fraction_iqr=float(iqr)))
for f,h in watch.items():ck('immutable_witness_'+f,sha(Path(f))==h)
out={'status':'ACCEPTED'if all(c['pass_']for c in checks)else'REJECTED','all_checks_passed':all(c['pass_']for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass_']for c in checks),'checks':checks,'accepted_all50_ledger_sha256':sha(ledger),'accepted_stability_summary_sha256':sha(summary),'numeric_witnesses_sha256':watch,'scope':'Independent all250 saved provider-label contingency ARI, actual fixed seeded regional draws/sourceprovider masks/coverage, every numeric Q-path engineering knee and retention quantiles. This is conditional perturbation computational stability, not observed commuting probability, causal or generalization CI. Full250 weighted graph reruns were NOT independently repeated; baseline graph/objective has separate source audit. Registry distinct nesting and demographic classification require separate review.'};(O/'all250_stability_admission.json').write_text(json.dumps(out,indent=2)+'\n');pd.DataFrame(ret).to_csv(O/'independent_all250_retention.csv',index=False);print(out['status'],out['n_checks'],out['n_failed'])
