from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,time
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');M=B/'model/output_cycle06_access_v2_baseline';O=B/'reviews/cycle06/configuration_actual_independent';checks=[];t=time.time()
def ck(k,v):checks.append({'check':k,'pass':bool(v)})
def eq(x,y):return np.allclose(np.asarray(x,float),np.asarray(y,float),equal_nan=True,rtol=1e-11,atol=1e-11)
n=pd.read_parquet(M/'nodes.parquet',columns=['id']);ids=n.id.to_numpy();a=np.load(O/'independent_field_arrays.npz');near=pd.read_parquet(O/'independent_near_gravity_routes.parquet');raw=pd.read_parquet(M/'configuration_peer_shared_origins.parquet');actual=pd.read_parquet(M/'configuration_complex_shared_origins.parquet');expected=[]
for (order,o),g in near.groupby(['order','o'],sort=False):
 if len(g)<2:continue
 cs=g.c.to_numpy();ms=g.mass.to_numpy();pp=g.p.to_numpy()
 for ratio in [.33,.5,.67]:
  candidates=set()
  for top in np.unique(ms):
   choose=frozenset(cs[(ms<=top)&(ms>=ratio*top-1e-12)])
   if len(choose)>=2:candidates.add(choose)
  maximal=[s for s in candidates if not any(s<other for other in candidates)]
  for subset in maximal:
   positions=np.flatnonzero(np.isin(cs,list(subset)));codes=sorted(subset);text=json.dumps([str(ids[k]) for k in codes],ensure_ascii=False,separators=(',',':'));identity=hashlib.sha256((str(order)+'|'+str(ratio)+'|'+text).encode()).hexdigest()[:24];pv=np.sort(pp[positions]);expected.append(dict(complex_id=identity,order=order,mass_ratio_threshold=ratio,origin_code=o,origin_id=ids[o],population_2021=a['population'][o],peer_ids_json=text,n_peer_centers=len(subset),minimum_to_maximum_mass_ratio=ms[positions].min()/ms[positions].max(),all_pair_joint_strength_supported=pv[:2].sum()>=.35-1e-12,joint_probability=pv.sum(),common_origin_source_witness=True,transitive_chain_merge_used=False))
e=pd.DataFrame(expected);keys=['complex_id','order','mass_ratio_threshold','origin_code'];ck('ALL_maximal_common_origin_mass_comparable_sets_exact',not e.duplicated(keys).any() and len(e)==len(actual) and set(map(tuple,e[keys].to_numpy()))==set(map(tuple,actual[keys].to_numpy())));e=e.set_index(keys).sort_index();f=actual.set_index(keys).sort_index()
for c in e:
 if pd.api.types.is_numeric_dtype(e[c]):ck('ALL221966_complex_origin_'+c,eq(e[c],f[c]))
 else:ck('ALL221966_complex_origin_'+c,e[c].equals(f[c]))
summary=pd.read_parquet(M/'configuration_common_origin_complexes.parquet');group=['complex_id','order','mass_ratio_threshold','peer_ids_json','n_peer_centers'];expected_summary=e.reset_index().groupby(group).agg(n_shared_rural_origins=('origin_id','nunique'),shared_population2021=('population_2021','sum'),minimum_to_maximum_mass_ratio=('minimum_to_maximum_mass_ratio','min'),n_joint_strength_supported_origins=('all_pair_joint_strength_supported','sum')).sort_index();ss=summary.set_index(group).sort_index();ck('ALL15200_complex_summary_keys',expected_summary.index.equals(ss.index))
for c in expected_summary:ck('ALL_complex_summary_'+c,eq(expected_summary[c],ss[c]))
ck('no_transitive_chain_merge_claim',not summary.transitive_chain_merge_used.any())
parts=[]
for ratio in [.33,.5,.67]:
 r=raw[raw.joint_strength_supported&raw.mass_ratio.ge(ratio-1e-12)].copy();r['mass_ratio_threshold']=ratio;parts.append(r)
r=pd.concat(parts);r['gravity_ratio_check']=np.minimum(r.g_a,r.g_b)/np.maximum(r.g_a,r.g_b);k=['order','peer_a_id','peer_b_id','mass_ratio_threshold'];expected_pairs=r.groupby(k).agg(n_shared_positive_rural_origins=('origin_id','nunique'),shared_population2021=('population_2021','sum'),minimum_joint_probability=('pair_joint_probability','min'),minimum_gravity_ratio=('gravity_ratio_check','min'),own_mass_ratio=('mass_ratio','first')).sort_index();obs_pairs=pd.read_parquet(M/'configuration_supported_peer_pairs.parquet').set_index(k).sort_index();ck('ALL7499_supported_peer_pair_keys',expected_pairs.index.equals(obs_pairs.index))
for c in expected_pairs:ck('ALL_supported_pair_'+c,eq(expected_pairs[c],obs_pairs[c]))
result=dict(status='ACCEPTED' if all(x['pass'] for x in checks) else 'REJECTED',all_checks_passed=all(x['pass'] for x in checks),n_checks=len(checks),n_failed=sum(not x['pass'] for x in checks),checks=checks,scope='ACTUAL_ALL_MAXIMAL_COMMON_ORIGIN_COMPLEXES_ALL_THRESHOLDS_AND_SUPPORTED_PAIR_AGGREGATES_NO_TRANSITIVE_CHAINS; MODELED_POTENTIAL_NOT_OBSERVED_FLOW',model_manifest_sha256=hashlib.sha256((M/'output_manifest.json').read_bytes()).hexdigest(),seconds=time.time()-t)
(O/'complex_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],result['n_checks'],result['n_failed']);print([x for x in checks if not x['pass']])
