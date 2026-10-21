from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,time
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');M=B/'model/output_cycle06_access_v2_baseline';O=B/'reviews/cycle06/configuration_actual_independent';t=time.time();checks=[]
def ck(name,v):checks.append({'check':name,'pass':bool(v)})
def equal(x,y):
 if pd.api.types.is_numeric_dtype(x) or pd.api.types.is_bool_dtype(x):return np.allclose(np.asarray(x,dtype=float),np.asarray(y,dtype=float),equal_nan=True,atol=1e-11,rtol=1e-11)
 return pd.Series(x).fillna('<NA>').astype(str).reset_index(drop=True).equals(pd.Series(y).fillna('<NA>').astype(str).reset_index(drop=True))
n=pd.read_parquet(M/'nodes.parquet',columns=['id','_population_axis_row','source_record_id_2021','accepted_statistical_rural_role2021','population_2021']);ids=pd.Index(n.id);a=np.load(O/'independent_field_arrays.npz');rank=a['ranks'];pop=a['population'];eligible=a['eligible'];ties=a['snap_ties'];role=n.accepted_statistical_rural_role2021.astype('boolean');axis=n._population_axis_row.fillna(False).to_numpy(bool);native=n.source_record_id_2021.notna().to_numpy();unknown=role.isna().to_numpy();missing=role.fillna(False).to_numpy(bool)&~np.isfinite(pop)
s=pd.read_parquet(M/'system_configurations.parquet');obs=pd.read_parquet(M/'configuration_sensitivity_summary.parquet');mem=pd.read_parquet(M/'memberships.parquet');raw=pd.read_parquet(M/'configuration_peer_shared_origins.parquet');coverage=pd.read_parquet(M/'configuration_field_source_coverage.parquet').set_index('order').field_source_complete.to_dict();assign={lev:ids.get_indexer(mem[f'center_id_l{lev}']) for lev in range(1,5)}
groups={};ownpairs={};nestedpairs={}
for lev,codes in assign.items():
 for key,g in pd.DataFrame({'p':codes,'i':np.arange(len(n))}).query('p>=0').groupby('p',sort=False):groups[(lev,int(key))]=g.i.to_numpy()
for (order,peer),g in pd.concat([raw.assign(peer=raw.c_a),raw.assign(peer=raw.c_b)]).groupby(['order','peer'],sort=False):ownpairs[(int(order),int(peer))]=g
for lev,codes in assign.items():
 rr=raw[(codes[raw.o]>=0)&(codes[raw.o]==codes[raw.c_a])&(codes[raw.o]==codes[raw.c_b])].copy();rr['parent']=codes[rr.o]
 for (parent,order),g in rr.groupby(['parent','order'],sort=False):nestedpairs[(lev,int(parent),int(order))]=g
empty=raw.iloc[:0];out=[]
for lev,parent_id in s[['level','center_id']].itertuples(index=False,name=None):
 parent=ids.get_loc(parent_id);ix=groups.get((lev,parent),np.array([],dtype=int));external=axis[ix]&(ix!=parent);un=int((external&native[ix]&unknown[ix]).sum());hu=int((external&~native[ix]&unknown[ix]).sum());mp=int((external&native[ix]&missing[ix]).sum());hm=int((external&~native[ix]&missing[ix]).sum());children=ix[(rank[ix]>0)&(rank[ix]<rank[parent])&(ix!=parent)];cr=int(rank[children].max()) if len(children) else None
 base=dict(level=lev,center_id=parent_id,focal_intrinsic_order=rank[parent] or np.nan,child_order_evaluated=cr,n_distinct_contained_lower_order_centers=len(children),unknown_statistical_role_members=un,unknown_statistical_role_native2021_members=un,unknown_statistical_role_historical_only_members=hu,known_rural_members_missing_population2021=mp,known_rural_historical_only_members_missing_population2021=hm,historical_axis_role_population_complete=un+hu+mp+hm==0,n_historical_only_external_axis_members=int((external&~native[ix]).sum()),historical_only_external_population_known_sum2021=float(np.nansum(pop[ix][external&~native[ix]])),historical_only_external_population_known_count2021=int((external&~native[ix]&np.isfinite(pop[ix])).sum()))
 for ratio in [.33,.5,.67]:
  result={**base,'mass_ratio_threshold':ratio}
  for scope,order,focal in [('own_order',int(rank[parent]),parent),('nested',cr,None)]:
   if order is None:
    cnt=shared=literal=0;share=lshare=pshare=dominance=np.nan;complete=tie=poly=mono=False;dom=None
   else:
    ii=ix[eligible[ix]&(rank[ix]<order)];cnt=len(ii);pp=ownpairs.get((order,focal),empty) if focal is not None else nestedpairs.get((lev,parent,order),empty)
    if focal is None:pp=pp[pp.c_a.isin(children[rank[children]==order])&pp.c_b.isin(children[rank[children]==order])]
    pp=pp[pp.mass_ratio.ge(ratio-1e-12)&pp.o.isin(ii)];literal=pp.o.nunique();lshare=literal/cnt if cnt else np.nan;pp=pp[pp.joint_strength_supported];shared=pp.o.nunique();share=shared/cnt if cnt else np.nan;pshare=pop[np.unique(pp.o)].sum()/pop[ii].sum() if cnt else np.nan
    win=a[f'{order}_winner'][ii];q=a[f'{order}_q'][ii];strong=np.isfinite(q)&(q>=.8);vote=pd.Series(win[strong&(win>=0)]).value_counts();dom=int(vote.index[0]) if len(vote) else None;dominance=vote.iloc[0]/cnt if cnt and len(vote) else np.nan
    if focal is not None:dom=focal if cnt else None;dominance=((win==focal)&strong).sum()/cnt if cnt else np.nan
    elif dom not in set(children[rank[children]==order]):dom=None;dominance=np.nan
    tie=bool(ties[ii].any() or a[f'{order}_tie'][ii].any() or (focal is not None and ties[focal]) or (dom is not None and ties[dom]));complete=bool(coverage.get(order,False) and cnt and (a[f'{order}_count'][ii]>0).all() and un==0 and mp==0 and not tie);mono=cnt>=3 and complete and np.isfinite(dominance) and dominance>=.9;poly=bool(coverage.get(order,False) and cnt and shared>=1 and share>=.1)
   for suffix,value in [('eligible_positive_rural_origins',cnt),('literal_shared_origins',literal),('literal_shared_origin_fraction',lshare),('shared_origins',shared),('shared_origin_fraction',share),('shared_population_fraction',pshare),('dominance_fraction',dominance),('field_complete',complete),('road_snap_tie',tie)]:result[scope+'_'+suffix]=value
   if scope=='nested':result['nested_dominant_child_id']=None if dom is None else ids[dom];result['nested_child_configuration']='polycentric_child_complex_potential' if poly else 'monocentric_child_field_potential' if mono else 'configuration_unknown';result['nested_substantial_polycentric_field_support']=poly
   else:result['same_order_configuration']='structural_assignment_unit' if lev==1 else 'polycentric_peer_field_potential' if poly else 'monocentric_field_potential' if mono else 'configuration_unknown';result['own_order_substantial_polycentric_field_support']=poly;result['cross_boundary_peer_overlap_member']=shared>0
  out.append(result)
e=pd.DataFrame(out).set_index(['level','center_id','mass_ratio_threshold']);f=obs.set_index(['level','center_id','mass_ratio_threshold']);ck('all25512_sensitivity_keys_exact',set(e.index)==set(f.index) and len(e)==len(f));e=e.reindex(f.index)
for col in e:ck('ALL_system_decisions_'+col,equal(e[col],f[col]))
primary=obs[obs.mass_ratio_threshold.eq(.5)].reset_index(drop=True);ss=s.reset_index(drop=True)
for col in s:ck('primary_actual_projection_'+col,equal(ss[col],primary[col]))
ck('no_actual_observed_flow_or_partition_mutation_claim',not obs.actual_multicenter_service_flows_observed.any() and not obs.hard_partition_changed.any() and obs.configuration_is_empirical_order_potential_only.all())
result=dict(status='ACCEPTED' if all(c['pass'] for c in checks) else 'REJECTED',all_checks_passed=all(c['pass'] for c in checks),n_checks=len(checks),n_failed=sum(not c['pass'] for c in checks),checks=checks,scope='ACTUAL_ALL_8504_SYSTEMS_ALL_THREE_MASS_THRESHOLDS_CONFIGURATION_DECISIONS_USING_INDEPENDENTLY_RECONSTRUCTED_ENTIRE_MATRIX_FIELDS; COMPLEX_MAXIMALITY_AND_CASE_INTERPRETATION_REMAIN_SEPARATE',model_manifest_sha256=hashlib.sha256((M/'output_manifest.json').read_bytes()).hexdigest(),seconds=time.time()-t)
(O/'system_decision_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],result['n_checks'],result['n_failed'],flush=True);print([x for x in checks if not x['pass']],flush=True)
