"""Source-pinned executor for prospective bounded bottom-up provider forest.
--prepare-only writes inspectable premetric source/code binding.
--resume REQUIRES independent admission binding exact protocol/code/providerpool.
"""
import argparse,hashlib,json,sys,gc,ctypes
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.metrics import adjusted_rand_score
from matrix_query import sha
from route_field import RouteField,build_route_field
from forest import Forest
from select_cuts import accept_stable_cut
HERE=Path(__file__).resolve().parent;BASE=next(x for x in HERE.parents if (x/"transport").is_dir() and (x/"model").is_dir())
SOURCES=['run.py','route_field.py','forest.py','aggregate_modularity.py','select_cuts.py','matrix_query.py','build_provider_pool.py']

def binding(scenario="primary",cache_dir=None):
 settings={"primary":(60,1,"reciprocal",False),"tau30":(30,1,"reciprocal",False),"tau90":(90,1,"reciprocal",False),"gamma0.5":(60,.5,"reciprocal",False),"gamma2":(60,2,"reciprocal",False),"directed_max":(60,1,"directed_max",False),"extended180":(60,1,"reciprocal",True)}
 if scenario not in settings:raise ValueError("unknown preregistered scenario")
 tau,gamma,symmetry,extended=settings[scenario]
 protocol=HERE/'PROTOCOL_v1.json';p=json.loads(protocol.read_text())
 source_admission=json.loads((BASE/'reviews/cycle07_mass_pool477_v2_independent/combined_admission.json').read_text());matrix_admission=json.loads((BASE/'reviews/cycle07_matrix477_independent/combined_admission.json').read_text())
 if source_admission.get('all_checks_passed') is not True or matrix_admission.get('all_checks_passed') is not True:raise ValueError('actual source/transport not admitted')
 if source_admission.get('accepted_nodes_sha256')!=sha(BASE/p['source_nodes']) or source_admission.get('accepted_own_mass_sha256')!=sha(BASE/p['source_own_mass']) or matrix_admission.get('accepted_matrix_manifest_sha256')!=sha(BASE/p['matrix_manifest']):raise ValueError('independent source/transport exact bytes mismatch')
 paths=[BASE/'reviews/cycle07_mass_pool477_v2_independent/combined_admission.json',BASE/'reviews/cycle07_matrix477_independent/combined_admission.json',BASE/'model_inputs_cycle07/cycle07_source_mass_pool_admitted_handoff.json',BASE/p['source_nodes'],BASE/p['source_own_mass'],BASE/p['matrix_manifest'],HERE/'source_provider_pool/active_provider_pool.parquet',HERE/'source_provider_pool/provider_pool_receipt.json']
 cache_paths=[Path(cache_dir)/x for x in ['cache_receipt.json','routes_180.npz','origin_mapping.parquet','provider_mapping.parquet']] if cache_dir is not None else []
 if any(not x.exists() for x in cache_paths):raise ValueError('source-only numeric cache must be prepared before execution binding')
 return dict(numeric_cache_source_hashes={x.name:sha(x) for x in cache_paths},scenario=scenario,scenario_parameters=dict(tau=tau,gamma=gamma,symmetry=symmetry,extended180=extended),protocol_sha256=sha(protocol),protocol=p,inputs={str(x.relative_to(BASE)):sha(x) for x in paths},execution_sources={x:sha(HERE/x) for x in SOURCES},new_national_outcomes_read=False)

def get_field(cache):
 r=cache/'cache_receipt.json'
 if not r.exists():return build_route_field(BASE,cache)
 meta=json.loads(r.read_text())
 if meta['code_sha256']!=sha(HERE/'route_field.py'):raise ValueError('source-cache helper version mismatch')
 if meta['matrix_manifest_sha256']!=sha(BASE/json.loads((HERE/'PROTOCOL_v1.json').read_text())['matrix_manifest']):raise ValueError('source-cache matrix mismatch')
 if meta['provider_pool_sha256']!=sha(HERE/'source_provider_pool/active_provider_pool.parquet'):raise ValueError('cache pool mismatch')
 if meta['route_cache_sha256']!=sha(cache/'routes_180.npz'):raise ValueError('cache byte mismatch')
 routes=sparse.load_npz(cache/'routes_180.npz');o=pd.read_parquet(cache/'origin_mapping.parquet');p=pd.read_parquet(cache/'provider_mapping.parquet')
 mp=BASE/json.loads((HERE/'PROTOCOL_v1.json').read_text())['matrix_manifest'];manifest=json.loads(mp.read_text());op=mp.parent/manifest['origin_mapping']['path']
 if sha(op)!=manifest['origin_mapping']['sha256']:raise ValueError('source origin mapping SHA mismatch')
 expected_origins=pd.read_parquet(op)
 if not o.equals(expected_origins):raise ValueError('cached origin mapping does not exactly match source mapping')
 expected_providers=pd.read_parquet(HERE/'source_provider_pool/active_provider_pool.parquet').sort_values('id').reset_index(drop=True)
 if not p.equals(expected_providers):raise ValueError('cached provider mapping/mass differs from admitted active source pool')
 if routes.shape!=(len(o),len(p)):raise ValueError('numeric route shape differs from exact source maps')
 return RouteField(routes,o,p,p.own_positive_mass.to_numpy(float)),meta

def native_source_ids(nodes):
 mask=nodes._population_axis_row.fillna(False)&nodes.source_record_id_2021.notna()&nodes.population_2021.notna()
 return set(nodes.loc[mask,'id'].astype(str))

def run_path(field,native,proto_hash,caps,tau=60,gamma=1,weights=None,symmetry='reciprocal'):
 f=Forest(field,native,proto_hash,tau,gamma,weights,symmetry);stages=[]
 for cap in caps:
  s=f.one_cap(cap);stages.append(s)
 return f,stages

def stage_export(out,f,stages,nodes,replicate_id=None):
 node_lookup=nodes.set_index("id");all_atomic=set(nodes.loc[nodes._population_axis_row.fillna(False),"id"])
 status=[]
 for s in stages:
  cap=s['cap'];knee=s['knee'];stem=f'cap_{cap:03}'
  if replicate_id is not None:
   status.append(dict(replicate_id=replicate_id,candidate_cap=cap,status=knee['status'],selected_merge=knee.get('selected_merge'),n_merges=len(s['events']),n_residuals=s['n_residuals']))
   continue
  events=[]
  for e in s['events']:
   row={k:v for k,v in e.items() if k!='source_envelope_witness'};row.update(e['source_envelope_witness']);row['candidate_cap']=cap;events.append(row)
  pd.DataFrame(events).to_parquet(out/f'{stem}_accepted_merge_events.parquet',index=False)
  pd.DataFrame({'merge_index':np.arange(len(s['objective_curve'])),'Q':s['objective_curve'],'candidate_cap':cap}).to_parquet(out/f'{stem}_objective_curve.parquet',index=False)
  np.save(out/f'{stem}_provider_knee_labels.npy',s['labels'],allow_pickle=False)
  # Actual source provider seeds are separate from single focal central object.
  rows=[];members=[];forest_rows=[]
  for kind,units in [('candidate_knee_or_fallback',s['units']),('supported_end_forest',s['forest_units'])]:
   for u in units:
    focal=f.selected_core(u.nuclei,f.mask(u,cap))
    if focal is None:raise AssertionError('exported unit has no complete direct-envelope focal core')
    times=f.known_envelope_times(u.members,focal)
    record_id=f'{stem}:{kind}:{u.key}'
    cn=node_lookup.loc[str(f.nucleus_ids[focal])]
    row=dict(unit_id=record_id,semantic_unit_id=u.key,candidate_cap=cap,resolution_index=None,kind='functional_union' if len(u.members)>1 else 'provider_core_seed',unit_role='territorial_unit' if len(u.members)>1 else 'protected_carry',core_id=str(f.nucleus_ids[focal]),central_object_ids=json.dumps([str(f.nucleus_ids[focal])]),central_object_definition='one_focal_core',original_provider_seed_ids=json.dumps([str(f.nucleus_ids[i]) for i in sorted(u.nuclei)]),n_provider_seeds=len(u.nuclei),n_members=len(u.members),max_member_direct_minutes=float(np.max(times)) if len(times) else 0.,extent_complete=True,extent_frame='observed_native2021_plus_actual_source_core_self',partition_role=kind,n_children=len(u.children),children_semantic_ids=json.dumps(u.children),ancestry_depth=u.ancestry_depth,ancestry_depth_is_functional_rank=False,name=cn['name'],region=cn['region'],lat=cn['lat'],lon=cn['lon'],core_fixed_own_mass=float(f.f.mass[focal]),n_member_direct_known=len(times),n_member_direct_unknown=0,core_population_2021_known=pd.notna(cn['population_2021']),core_population_2021=cn['population_2021'])
    row['center_scope']='external_metropolitan_context_anchor' if str(f.nucleus_ids[focal]) in {'ctx:RU-FED-MOW','ctx:RU-FED-SPB'} else 'ordinary_source_settlement'
    row['dominant_source_core_rule']=True
    rows.append(row)
    for x in sorted(u.members):members.append(dict(unit_id=record_id,id=x,candidate_cap=cap,partition_role=kind,is_overlay_membership=False))
   covered=set().union(*(u.members for u in units)) if units else set()
   for x in sorted(all_atomic-covered):
    record_id=f'{stem}:{kind}:atom:{x}';cn=node_lookup.loc[x]
    rows.append(dict(unit_id=record_id,semantic_unit_id='atom:'+x,candidate_cap=cap,resolution_index=None,kind='atomic_residual',unit_role='protected_carry',core_id=x,central_object_ids=json.dumps([x]),central_object_definition='own_atomic',original_provider_seed_ids='[]',n_provider_seeds=0,n_members=1,max_member_direct_minutes=None,extent_complete=False,extent_frame='not_in_defined_functional_unit',partition_role=kind,n_children=0,children_semantic_ids='[]',ancestry_depth=0,ancestry_depth_is_functional_rank=False,name=cn['name'],region=cn['region'],lat=cn['lat'],lon=cn['lon'],core_fixed_own_mass=None,n_member_direct_known=0,n_member_direct_unknown=1,core_population_2021_known=pd.notna(cn['population_2021']),core_population_2021=cn['population_2021']))
    members.append(dict(unit_id=record_id,id=x,candidate_cap=cap,partition_role=kind,is_overlay_membership=False))
  for row in rows:
   row.setdefault('center_scope','external_metropolitan_context_anchor' if row['core_id'] in {'ctx:RU-FED-MOW','ctx:RU-FED-SPB'} else 'ordinary_source_settlement')
   row.setdefault('dominant_source_core_rule',row['kind']!='atomic_residual')
  pd.DataFrame(rows).to_parquet(out/f'{stem}_raw_units.parquet',index=False)
  pd.DataFrame(members).to_parquet(out/f'{stem}_raw_memberships.parquet',index=False)
  status.append(dict(candidate_cap=cap,**knee,n_units=len(s['units']),n_supported_forest_units=len(s['forest_units']),n_residuals=s['n_residuals'],n_zero_provider_denominators=s['n_zero_provider_denominators']))
 return status

def trim():
 try:ctypes.CDLL(None).malloc_trim(0)
 except (AttributeError,OSError):pass

def release(field,forest):
 forest.member_masks.clear();forest.attachment_events.clear();field.graph_cache.clear()
 if hasattr(field,'origin_mask_cache'):field.origin_mask_cache.clear()
 gc.collect();trim()

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True,type=Path);ap.add_argument('--cache',required=True,type=Path);ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--resume',action='store_true');ap.add_argument('--admission',type=Path);ap.add_argument('--scenario',default='primary',choices=['primary','tau30','tau90','gamma0.5','gamma2','directed_max','extended180']);ap.add_argument('--baseline-only',action='store_true',help='save actual baseline path; bootstrap is a later resumable stage, never claim full robustness')
 a=ap.parse_args();out=a.output
 if a.prepare_only:
  if out.exists() and any(out.iterdir()):raise ValueError('new output directory required')
  out.mkdir(parents=True,exist_ok=True);(out/'pre_execution_binding.json').write_text(json.dumps(binding(a.scenario,a.cache),indent=2));print('PREPARED no hierarchy outcomes computed');return
 if not a.resume or not a.admission:raise ValueError('resume requires independent exact source/code admission')
 if (out/'run_receipt.json').exists():raise ValueError('completed outputs immutable; use a new output directory')
 old=json.loads((out/'pre_execution_binding.json').read_text());now=binding(a.scenario,a.cache)
 if old!=now:raise ValueError('premetric execution binding changed')
 admit=json.loads(a.admission.read_text())
 if admit.get('accepted_pre_execution_binding_sha256')!=sha(out/'pre_execution_binding.json'):raise ValueError('independent admission does not bind exact pre-execution source/cache inputs')
 if admit.get('all_checks_passed') is not True or admit.get('accepted_protocol_sha256')!=now['protocol_sha256'] or admit.get('accepted_execution_sources')!=now['execution_sources'] or admit.get('accepted_provider_pool_sha256')!=sha(HERE/'source_provider_pool/active_provider_pool.parquet'):raise ValueError('independent admission does not bind exact protocol/code/providerpool')
 field,cache_receipt=get_field(a.cache);nodes=pd.read_parquet(BASE/now['protocol']['source_nodes'],columns=['id','name','region','lat','lon','population_2021','source_record_id_2021','_population_axis_row']);native=native_source_ids(nodes)
 caps=now['protocol']['extent']['candidate_caps_minutes'];ph=now['protocol_sha256']
 params=now['scenario_parameters']
 if params['extended180']:caps=caps+[180]
 f=Forest(field,native,ph,params['tau'],params['gamma'],None,params['symmetry'])
 statuses=[];baselabels={};baseline_status={};attachment_parts=[]
 for cap in caps:
  stage=f.one_cap(cap)
  statuses.extend(stage_export(out,f,[stage],nodes))
  baselabels[cap]=stage['labels'].copy();baseline_status[cap]=stage['knee']['status']
  attachment_path=out/f'cap_{cap:03}_directed_local_attachment_events.parquet'
  pd.DataFrame(f.attachment_events).to_parquet(attachment_path,index=False);attachment_parts.append(attachment_path)
  pd.DataFrame(statuses).to_csv(out/'candidate_knee_summary.csv',index=False)
  del stage;release(field,f)
  print(f'BASELINE_CAP_{cap:03}_EXPORTED',flush=True)
 atomic=nodes.loc[nodes._population_axis_row.fillna(False)&~nodes.id.isin(set.union(*[set(u.members) for u in f.units])),['id','name','population_2021','source_record_id_2021']].copy()
 atomic['unit_role']='protected_carry';atomic['kind']='atomic_residual';atomic.to_parquet(out/'final_atomic_residuals.parquet',index=False)
 del atomic,nodes,f;gc.collect();trim()
 pd.concat([pd.read_parquet(x) for x in attachment_parts],ignore_index=True).to_parquet(out/'directed_local_attachment_events.parquet',index=False)
 if a.baseline_only or a.scenario!='primary':
  if binding(a.scenario,a.cache)!=old:raise ValueError('execution inputs/code/numeric-cache changed during baseline run')
  (out/'baseline_stage_receipt.json').write_text(json.dumps(dict(status='BASELINE_ONLY_BOOTSTRAP_NOT_COMPLETE',pre_execution_binding_sha256=sha(out/'pre_execution_binding.json'),admission_sha256=sha(a.admission),cache=cache_receipt),indent=2));print('Baseline path written,50replicate stability NOTcomplete');return
 print('BASELINE_ALL_CAP_EXPORTS_READY, starting 50 conditional geographic replicates',flush=True)
 p=field.providers;ordinary=~p.documented_external_context_anchor.fillna(False);regions=sorted(set(p.loc[ordinary,'region'].dropna().astype(str)))
 regindex={x:i for i,x in enumerate(regions)};rng=np.random.default_rng(now['protocol']['seed']);boot=[]
 mapped=p.region.astype(str).map(regindex);known=ordinary&mapped.notna()
 for rep in range(50):
  draw=rng.multinomial(len(regions),np.full(len(regions),1/len(regions)));weights=np.ones(len(p));weights[known]=draw[mapped[known].astype(int)]
  bf=Forest(field,native,ph,params['tau'],params['gamma'],weights,params['symmetry'])
  for cap in caps:
   stage=bf.one_cap(cap);base=baselabels[cap];compare=weights>0;coverage=int(compare.sum())
   assess=stage['knee']['status']=='candidate_knee' and baseline_status[cap]=='candidate_knee' and coverage>=20 and len(np.unique(base[compare]))>=2 and len(np.unique(stage['labels'][compare]))>=2
   ari=float(adjusted_rand_score(base[compare],stage['labels'][compare])) if assess else None
   boot.append(dict(replicate_id=rep,candidate_cap=cap,status=stage['knee']['status'],assessable=assess,ari=ari,n_compared_provider_seeds=coverage,compared_provider_fraction=coverage/len(p),n_positive_weight_regions=int((draw>0).sum()),selected_merge=stage['knee'].get('selected_merge'),n_merges=len(stage['events']),knee_fraction=stage['knee']['selected_merge']/len(stage['events']) if assess and stage['events'] else None,region_weight_draw_json=json.dumps(draw.tolist())))
   np.savez_compressed(out/f'rep_{rep:02}_cap_{cap:03}_numeric_witnesses.npz',provider_labels=stage['labels'],objective_curve=np.asarray(stage['objective_curve'],float),positive_weight_provider_mask=compare,region_weights=draw)
   pd.DataFrame(boot).to_csv(out/'all_50_bootstrap_ledger_checkpoint.csv',index=False)
   del stage;release(field,bf)
  del bf;gc.collect();trim();print(f'Finished geographic perturbation {rep+1}/50',flush=True)
 b=pd.DataFrame(boot);b.to_parquet(out/'all_50_bootstrap_ledger.parquet',index=False);ret=[]
 for cap,g in b.groupby('candidate_cap'):
  test=accept_stable_cut(pd.to_numeric(g.ari,errors='coerce'),pd.to_numeric(g.knee_fraction,errors='coerce'));ret.append(dict(candidate_cap=int(cap),**test))
 pd.DataFrame(ret).to_csv(out/'retained_resolution_stability.csv',index=False)
 # Source-faithful exports preserve all scenarios; promotion to empirical levels
 # is a distinct registry built from admitted stable nested cuts.
 if binding(a.scenario,a.cache)!=old:raise ValueError('execution inputs/code/numeric-cache changed during complete run')
 receipt=dict(status='COMPUTED_PRIMARY_PATH_AND_50_CONDITIONAL_STABILITY_REPLICATES',pre_execution_binding_sha256=sha(out/'pre_execution_binding.json'),independent_design_admission_sha256=sha(a.admission),new_result_independent_review_pending=True,sourceMi_not_refitted=True,candidate_caps_are_not_empirical_levels=True,files=[dict(path=x.name,sha256=sha(x)) for x in sorted(out.iterdir()) if x.is_file()])
 (out/'run_receipt.json').write_text(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
