#!/usr/bin/env python3
"""Independent matrix-free snapshot maths and fixed-label direct source readback."""
from pathlib import Path
import json,hashlib,math
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parents[2];REPO=next(p for p in H.parents if (p/'.git').exists());checks=[];pins={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):pins[str(p)]=sha(p);return pd.read_parquet(p) if p.suffix=='.parquet' else pd.read_csv(p)
def js(p):pins[str(p)]=sha(p);return json.loads(p.read_text())
def check(name,ok,detail=None):checks.append(dict(check=name,pass_=bool(ok),detail=detail));assert ok,name+' '+str(detail)
def ari(a,b):
 counts=pd.DataFrame({'a':a,'b':b}).groupby(['a','b'],observed=True).size().to_numpy(dtype='float64');ca=pd.Series(a).value_counts().to_numpy(dtype='float64');cb=pd.Series(b).value_counts().to_numpy(dtype='float64');pair=lambda x:float((x*(x-1)/2).sum());n=len(a);total=n*(n-1)/2
 if n<2:return None
 same=pair(counts);left=pair(ca);right=pair(cb);expected=left*right/total;den=(left+right)/2-expected
 return (same-expected)/den if den else 1.
def run():
 old=ROOT/'model/output_cycle05_v4_baseline';new=ROOT/'model/output_cycle06_access_v2_baseline';comp=ROOT/'robustness/cycle06_access_v2_vs_cycle05_v4';sup=ROOT/'robustness/cycle06_access_v2_full_source_axis_supplement';ext=ROOT/'validation/cycle06_access_v2_external52';support=ROOT/'validation/cycle06_access_v2_external52_provider_support'
 # SHA binding is checked from frozen premetric source pins, not author PASS flags.
 binding=js(comp/'source_binding_before_metrics.json')
 for p,d in binding['source_sha256'].items():check('premetric_bound_source:'+Path(p).name,sha(Path(p))==d)
 protocol=js(ROOT/'robustness/cycle06_comparison_tools/comparison_protocol.json');check('comparison_registered_without_new_metrics',protocol['new_metrics_read'] is False)
 A={};B={}
 for target,folder in [(A,old),(B,new)]:
  for kind in ['nodes','memberships','candidate_centers','own_mass_components']:target[kind]=read(folder/(kind+'.parquet')).set_index('id').sort_index()
 check('all_modelentity_IDsets_same',A['nodes'].index.equals(B['nodes'].index))
 for col in protocol['protected_node_fields']:check('protected_node:'+col,A['nodes'][col].equals(B['nodes'][col]))
 for col in protocol['protected_mass_fields']:check('protected_mass:'+col,A['own_mass_components'][col].equals(B['own_mass_components'][col]))
 check('candidate_IDs_fixed',A['candidate_centers'].index.equals(B['candidate_centers'].index));changed=int(A['candidate_centers'].intrinsic_empirical_rank.ne(B['candidate_centers'].intrinsic_empirical_rank).sum());check('actual_rankchanged93',changed==93)
 aritab=read(comp/'ARI_with_explicit_denominators.csv');availability=read(comp/'assignment_availability_by_level_and_scope.csv');nodes=B['nodes'];sourceaxis=read(ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet');sourceids=set(sourceaxis.id)
 masks={'all_model_entities':pd.Series(True,index=nodes.index),'primary_population_axis_rows':nodes._population_axis_row.fillna(False),'explicit_statistical_rural_axis_rows':nodes._population_axis_row.fillna(False)&nodes.accepted_statistical_rural_role2021.eq(True).fillna(False)}
 reconstruct=[]
 for row in aritab.itertuples(index=False):
  scope=masks[row.scope];a=A['memberships'].loc[scope,f'center_id_l{row.level}'];b=B['memberships'].loc[scope,f'center_id_l{row.level}'];both=a.notna()&b.notna();n=int(scope.sum());r=ari(a[both].to_numpy(),b[both].to_numpy());check(f'ARI:{row.level}:{row.scope}',abs(r-row.ARI_common_assigned_only)<1e-12)
  counts={'total_entities':n,'old_assigned':int(a.notna().sum()),'new_assigned':int(b.notna().sum()),'both_assigned':int(both.sum()),'old_only_assigned':int((a.notna()&b.isna()).sum()),'new_only_assigned':int((a.isna()&b.notna()).sum()),'neither_assigned':int((a.isna()&b.isna()).sum()),'exact_center_retained':int((both&a.eq(b)).sum()),'different_center_both_assigned':int((both&a.ne(b)).sum())}
  saved=availability[(availability.level==row.level)&availability.scope.eq(row.scope)].iloc[0];check(f'all_denominators:{row.level}:{row.scope}',all(int(saved[k])==v for k,v in counts.items()));check(f'ARI_exclusion:{row.level}:{row.scope}',row.common_assigned_n==both.sum() and row.total_scope_n==n and row.missing_or_unavailable_excluded_from_ARI==n-both.sum());reconstruct.append(dict(level=row.level,scope=row.scope,ARI=r,**counts))
 check('allsource173862_vs_population173856',len(sourceids)==173862 and int(nodes._population_axis_row.sum())==173856 and len(nodes)==173864)
 sr=js(sup/'receipt.json')
 for p,d in sr['source_sha256'].items():check('supplement_bound:'+Path(p).name,sha(Path(p))==d)
 # Fixed labels read from their original freeze, not from evaluated output.
 labels=read(ROOT/'validation/cycle05_external_tools/labels52_frozen.parquet').set_index('label_id');diag=read(ext/'all52_label_diagnostics.parquet').set_index('label_id');check('fixed52label_IDs',set(labels.index)==set(diag.index) and len(labels)==52)
 for col in ['stratum','function_group','origin_id','provider_id','source_sha256','provider_witness_sha256']:check('fixed_label_field:'+col,labels[col].sort_index().equals(diag[col].sort_index()))
 er=js(ext/'external_diagnostic_receipt.json');cfg=ROOT/'model_inputs_cycle06/final_access_v2/config_baseline_final.json';run=js(new/'run_receipt.json');check('external_exact_completed_config',run['configuration_sha256']==sha(cfg) and er['input_sha256'][str(cfg.resolve())]==sha(cfg))
 for p,d in er['input_sha256'].items():check('external_bound_source:'+Path(p).name,sha(Path(p))==d)
 fun=read(new/'function_specific_memberships.parquet').set_index(['id','function_group']);mem=B['memberships'];mass=B['own_mass_components'];candidates=set(B['candidate_centers'].index)
 for q in diag.itertuples():
  row=labels.loc[q.Index];oid=row.origin_id;pid=row.provider_id;fn=row.function_group;key=(oid,fn);pred=fun.at[key,'assigned_center_id'] if key in fun.index else None;integral=mem.at[oid,'assigned_center_id'] if oid in mem.index else None
  eq=lambda a,b:(pd.isna(a) and pd.isna(b)) or a==b
  check('function_prediction:'+str(q.Index),eq(pred,q.function_predicted_provider_id));check('integral_prediction:'+str(q.Index),eq(integral,q.integral_predicted_provider_id));check('exact_flags:'+str(q.Index),bool(q.function_exact_provider_reproduced)==bool(pd.notna(pred) and pred==pid) and bool(q.integral_exact_provider_reproduced)==bool(pd.notna(integral) and integral==pid))
  check('labelprovider_positivewitness:'+str(q.Index),bool(q.label_provider_has_corresponding_OSM_witness)==bool(pid in mass.index and mass.at[pid,'physical_'+fn+'_count_proxy']>0))
  for level in [1,2,3,4]:
   oc=mem.at[oid,f'center_id_l{level}'] if oid in mem.index else None;pc=mem.at[pid,f'center_id_l{level}'] if pid in mem.index else None;both=pd.notna(oc) and pd.notna(pc);match=both and oc==pc;check(f'coassignment:{q.Index}:L{level}',bool(getattr(q,f'both_assigned_center_id_l{level}'))==both and bool(getattr(q,f'coassigned_center_id_l{level}'))==match)
 for metric in er['metrics']:
  z=diag[diag.stratum.eq(metric['stratum'])];method=metric['method'];matchcol,availcol=({'function_exact':('function_exact_provider_reproduced','function_prediction_available'),'integral_exact':('integral_exact_provider_reproduced','integral_prediction_available'),'nearest_observed_provider':('nearest_exact_provider_reproduced','nearest_prediction_available')}.get(method,('coassigned_'+method,'both_assigned_'+method)));k=int(z[matchcol].sum());v=int(z[availcol].sum());check('metric_denominator:'+method+':'+metric['stratum'],len(z)==metric['n_documented_positive_labels'] and k==metric['n_labels_reproduced'] and v==metric['n_prediction_available'] and abs(k/len(z)-metric['share_documented_labels_reproduced'])<1e-15)
 supportreceipt=js(support/'receipt.json')
 for p,d in supportreceipt['source_sha256'].items():check('coverage_bound:'+Path(p).name,sha(Path(p))==d)
 for pid,z in diag.groupby('provider_id'):
  fn=z.function_group.iloc[0];check('all_three_labelprovider_NA_source:'+pid,len(diag.provider_id.unique())==3 and pd.isna(mass.at[pid,'physical_'+fn+'_count_proxy']) and not z.label_provider_has_corresponding_OSM_witness.any())
 pd.DataFrame(reconstruct).to_csv(H/'independent_ARI_and_missing_denominators.csv',index=False)
 # Route/nearest and finite raw3km readback are a second phase; do not admit them
 # based on this source-only exact-provider and coassignment reconstruction.
 out=dict(status='INDEPENDENT_SNAPSHOT_AND_EXACT52_MATH_PASS_ROUTE_AND_3KM_PHASE_PENDING',all_checks_passed=True,n_checks=len(checks),n_failed=0,checks=checks,source_sha256=pins,rank_changed=changed,ARI_all_entities={str(r['level']):r['ARI'] for r in reconstruct if r['scope']=='all_model_entities'},three_labelprovider_NP_positive_OSM_witness_absent=True,provider_absence_is_source_unknown_not_real_absence=True,not_pure_roadyear_causal_effect=True,not_national_trip_accuracy=True,nearest_route_and_3km_source_counts_not_yet_admitted=True,code_sha256=sha(Path(__file__)))
 (H/'phase1_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(len(checks))
if __name__=='__main__':run()
