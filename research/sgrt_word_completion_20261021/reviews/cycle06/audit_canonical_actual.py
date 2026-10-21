from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');M=B/'model/output_cycle06_access_v2_baseline';C=B/'typology/canonical_cycle06/output_cycle06_access_v2_baseline';O=B/'reviews/cycle06';checks=[]
def ck(n,v):checks.append({'check':n,'pass':bool(v)})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tri(v):return None if pd.isna(v) else bool(v)
def all3(values):return False if any(v is False for v in values) else None if any(v is None for v in values) else True
n=pd.read_parquet(M/'nodes.parquet').set_index('id');cent=pd.read_parquet(M/'candidate_centers.parquet').set_index('id');cfg=json.loads((B/'model_inputs_cycle06/final_access_v2/config_baseline_final.json').read_text());strength=cent[cfg['hierarchy_strength_column']];near=pd.read_parquet(M/'network_accessibility.parquet').set_index('id').nearest_large_city_network_minutes;raw=pd.read_parquet(M/'word_type_hypotheses.parquet').set_index(['level','center_id','word_type']);out=pd.read_parquet(C/'word_type_hypotheses.parquet');receipt=json.loads((C/'receipt.json').read_text());manifest=json.loads((C/'manifest.json').read_text());modelmanifest=json.loads((M/'output_manifest.json').read_text())
for filename,info in manifest['files'].items():ck('actual_frozen_'+filename,sha(C/filename)==info['sha256'])
ck('bind_actual_model',manifest['model_output_manifest_sha256']==sha(M/'output_manifest.json'))
ck('all_nine_types_all_systems_exact',len(out)==8504*9 and not out.duplicated(['level','center_id','word_type']).any() and set(zip(out.level,out.center_id,out.word_type))==set(raw.index))
for typ,g in out.groupby('word_type'):
 ok={k:True for k in ['literal_added','raw_core_retained','full_adjustment','core_adjustment','candidate','complete_status','exact_geo','counts','unknown_contradicted','causal_false']}
 for rr in g.to_dict('records'):
  uid=rr['center_id'];source=n.loc[uid];r=raw.loc[(rr['level'],uid,typ)];core=json.loads(r.operational_core_truth_json);full=json.loads(r.required_criteria_truth_json);expected={};sub=source.get('accepted_formal_settlement_subtype2021',source.get('type'));role=source.accepted_statistical_rural_role2021;formal=None if pd.isna(sub) else str(sub).replace('ё','е') in ['город','пгт','поселок городского типа','рабочий поселок','рп','кп','дп','гп','курортный поселок','дачный поселок','городской поселок'];urban=True if (pd.notna(role) and not bool(role)) or formal is True else None if pd.isna(role) and formal is None else False;p=source.population_2021;small=None if pd.isna(p) else bool(p<=50000)
  if typ in [2,3,5,7,8,9]:expected['small_urban_center']=all3([urban,small])
  if typ==5:expected['near_large_center_within90_modeled_minutes']=bool(near.get(uid)<=90) if np.isfinite(near.get(uid,np.nan)) else None
  if typ==7:expected['nonchernozem_geographic_zone']=tri(source.get('nonchernozem_geographic_evidence',None))
  ok['literal_added']&=json.loads(rr['literal_eligibility_added_truth_json'])==expected;ok['raw_core_retained']&=json.loads(rr['broad_measured_pattern_core_truth_json'])==core
  for criterion in ['trade_and_administration_function','basic_administrative_service_function']:
   if criterion in full and pd.notna(source.get(criterion+'_evidence',pd.NA)):full[criterion]=bool(source[criterion+'_evidence'])
  if typ in [4,7,8]:
   low=None if pd.isna(strength.get(uid)) else bool(strength[uid]<=.5)
   if 'low_ci_le0_5' in core:core['low_ci_le0_5']=low
   if typ==8:full['low_centrality']=low
   else:full['low_mass_and_centrality' if typ==7 else 'low_or_moderate_mass_centrality']=all3([core.get('low_mass_expmeanZ_le1'),low])
  full.update(expected);core.update(expected);ok['full_adjustment']&=json.loads(rr['required_criteria_truth_json'])==full;ok['core_adjustment']&=json.loads(rr['operational_core_truth_json'])==core
  operational=all3(core.values()) is True and bool(rr['population_pair_complete']);ok['candidate']&=bool(rr['operational_hypothesis'])==operational
  exact=core.copy()
  if typ==7:exact['nonchernozem_geographic_zone']=tri(source.get('nonchernozem_exact_contemporary_geographic_evidence',None))
  ok['exact_geo']&=bool(rr['operational_hypothesis_exact_contemporary_geography'])==(all3(exact.values()) is True and bool(rr['population_pair_complete']))
  state=all3(full.values());status='satisfied_observed_indicators' if state is True and rr['population_pair_complete'] and rr['population_pair_exact_primary_supported'] else 'not_satisfied_observed_indicators' if state is False else 'unknown_missing_required_indicators';ok['complete_status']&=rr['rule_status']==status;ok['counts']&=rr['n_required_criteria']==len(full) and rr['n_observed_supporting_criteria']==sum(v is True for v in full.values());ok['unknown_contradicted']&=json.loads(rr['unknown_required_criteria_json'])==[k for k,v in full.items() if v is None] and json.loads(rr['contradicted_required_criteria_json'])==[k for k,v in full.items() if v is False];ok['causal_false']&=not rr['full_causal_validation_claim']
 for k,v in ok.items():ck(f'all_type{typ}_8504_{k}',v)
selected=pd.read_parquet(C/'operational_type_candidates.parquet');ck('47_candidates_exact_projection',selected.reset_index(drop=True).equals(out[out.operational_hypothesis].reset_index(drop=True)) and len(selected)==47);ck('no_indicator_complete_types_invented',out.rule_status.eq('satisfied_observed_indicators').sum()==0);ck('broad85_not_literal47',receipt['broad_patterns_count']==85 and receipt['literal_candidate_count']==47);counts=selected.word_type.value_counts().sort_index().to_dict();ck('literal_type_counts_actual',counts=={2:6,5:21,6:17,8:3});ck('type7_geography_paired_unknown_no_false_type',not out[out.word_type.eq(7)].operational_hypothesis.any() and not out[out.word_type.eq(7)].operational_hypothesis_exact_contemporary_geography.any())
selected[['level','center_id','word_type','required_criteria_truth_json','unknown_required_criteria_json','contradicted_required_criteria_json']].to_csv(O/'canonical_actual_candidates_independent_readback.csv',index=False)
r=dict(status='ACCEPTED' if all(x['pass'] for x in checks) else 'REJECTED',all_checks_passed=all(x['pass'] for x in checks),n_checks=len(checks),n_failed=sum(not x['pass'] for x in checks),checks=checks,model_manifest_sha256=sha(M/'output_manifest.json'),canonical_manifest_sha256=sha(C/'manifest.json'),scope='ACTUAL_ALL76536_LITERAL_ADAPTER_RULES_SOURCE_ELIGIBILITY_TRISTATE_REPLAY; BROAD_PROTOTYPE_GENERATION_AND_MECHANISM_CONFIRMATION_NOT_ACCEPTED_BY_THIS_RECEIPT',literal_candidates=counts)
(O/'canonical_actual_independent_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r['status'],r['n_checks'],r['n_failed']);print([x for x in checks if not x['pass']])
