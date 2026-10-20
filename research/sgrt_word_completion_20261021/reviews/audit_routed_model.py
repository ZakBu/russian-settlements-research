#!/usr/bin/env python3
"""Independent audit of completed model tables; never reads a non-atomic route matrix.
No functions are imported from model builders. All outputs stay in reviews/.
"""
from pathlib import Path
import argparse,hashlib,json
import numpy as np,pandas as pd
from require_model_snapshot import require_snapshot
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=H.parents[2]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--model',default='output_2021_restricted_baseline');ap.add_argument('--inputs');ap.add_argument('--code');a=ap.parse_args();M=ROOT/'model'/a.model
 route_receipt=ROOT/'transport/routing_receipt.json'
 if not route_receipt.exists() or json.loads(route_receipt.read_text()).get('status')!='COMPUTED':raise SystemExit('WAIT_ATOMIC_ROUTING_RECEIPT_COMPUTED; route matrix not read')
 run=json.loads((M/'run_receipt.json').read_text())
 if not run.get('status','').startswith('COMPUTED'):raise SystemExit('WAIT_ACTUAL_COMPLETED_MODEL; model outputs not read')
 files=['run_receipt.json','nodes.parquet','own_mass_components.parquet','candidate_centers.parquet','memberships.parquet','hierarchy.parquet','systems.parquet','word_type_hypotheses.parquet','operational_type_candidates.parquet','population_balances.csv']
 config_guard=Path(a.inputs) if a.inputs else ROOT/'model'/('model_inputs_2021_restricted_inclusive.json' if 'inclusive' in a.model else 'model_inputs_2021_restricted.json')
 require_snapshot(M,config_guard,Path(a.code) if a.code else ROOT/'model/run_word_model.py',[f for f in files if f!='run_receipt.json'])
 guard_paths=[config_guard,Path(a.code) if a.code else ROOT/'model/run_word_model.py'];guard_hashes={str(p):sha(p) for p in guard_paths};before={f:sha(M/f) for f in files};checks=[]
 def check(name,condition,scope='implementation'):checks.append(dict(check=name,pass_=bool(condition),scope=scope))
 nodes=pd.read_parquet(M/'nodes.parquet');mass=pd.read_parquet(M/'own_mass_components.parquet');centers=pd.read_parquet(M/'candidate_centers.parquet');members=pd.read_parquet(M/'memberships.parquet');systems=pd.read_parquet(M/'systems.parquet');hier=pd.read_parquet(M/'hierarchy.parquet');types=pd.read_parquet(M/'word_type_hypotheses.parquet');oper=pd.read_parquet(M/'operational_type_candidates.parquet')
 check('model_ids_unique',nodes.id.is_unique and mass.id.is_unique and members.id.is_unique)
 check('member_axis_exactly_nodes',members.id.equals(nodes.id));check('mass_axis_exactly_nodes',mass.id.equals(nodes.id))
 check('positive_mass_matches_exp_own_index',np.allclose(mass.own_positive_mass,np.exp(mass.own_mean_standardized_index.clip(-20,20)),equal_nan=True));check('mass_never_uses_modeled_catchment',not mass.mass_uses_modeled_catchment.any())
 blocks=mass.filter(regex='^block_.*_z$');check('own_index_is_mean_of_available_blocks',np.allclose(blocks.mean(axis=1),mass.own_mean_standardized_index,equal_nan=True));check('mass_block_counts_match',np.array_equal(blocks.notna().sum(axis=1),mass.n_observed_mass_blocks))
 n=nodes.set_index('id');rural=~n.type.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок']);additive=n._population_axis_row.fillna(False);m=members.set_index('id').reindex(n.index);rows=[];revision=[]
 levels=sorted(int(c.removeprefix('center_id_l')) for c in members if c.startswith('center_id_l'))
 check('system_level_axis_matches_members',set(systems.level)==set(levels));check('system_ids_unique',not systems.duplicated(['level','center_id']).any())
 for lev in levels:
  col=f'center_id_l{lev}';assignment=m[col];s=systems[systems.level.eq(lev)].set_index('center_id');knownassignment=assignment.notna();active=set(assignment[knownassignment]);check(f'level{lev}_systems_exact_membership_centers',set(s.index)==set(assignment[additive&knownassignment]))
  for year in [2002,2010,2021]:
   p=n[f'population_{year}'];actual=p[additive&knownassignment].groupby(assignment[additive&knownassignment],observed=True).sum(min_count=1).reindex(s.index);check(f'l{lev}_P{year}_all_system_sums_recomputed',np.allclose(actual,s[f'system_population_known_sum_{year}'],equal_nan=True))
   missing=p[additive&knownassignment].isna().groupby(assignment[additive&knownassignment],observed=True).sum().reindex(s.index);check(f'l{lev}_P{year}_missing_counts_recomputed',np.array_equal(missing,s[f'n_missing_population_{year}']));check(f'l{lev}_P{year}_completeness_not_nonnull_sum',np.array_equal(missing.eq(0),s[f'system_population_complete_{year}']))
   outside=additive&knownassignment&rural&pd.Series(n.index,index=n.index).ne(assignment);rs=p[outside].groupby(assignment[outside],observed=True).sum(min_count=1).reindex(s.index);has=outside.groupby(assignment,observed=True).sum().reindex(s.index).fillna(0);rs.loc[has.eq(0)]=0.;check(f'l{lev}_P{year}_rural_external_recomputed',np.allclose(rs,s[f'rural_external_population_known_sum_{year}'],equal_nan=True))
   national_known=float(p[additive].sum());assigned_known=float(actual.sum());unassigned_known=float(p[additive&~knownassignment].sum());check(f'l{lev}_P{year}_assigned_plus_unassigned_conserved',np.isclose(national_known,assigned_known+unassigned_known))
  if lev>min(levels):
   lower=m[f'center_id_l{levels[levels.index(lev)-1]}'];mapping=pd.DataFrame({'lower':lower,'higher':assignment});check(f'l{lev}_whole_children_not_split',mapping.dropna(subset=['lower']).groupby('lower',observed=True).higher.nunique(dropna=False).le(1).all())
  if 'original_population_2010' in n:
   old=n.original_population_2010;new=n.population_2010;mask=additive&knownassignment;original=old[mask].groupby(assignment[mask],observed=True).sum(min_count=1).reindex(s.index);original_missing=old[mask].isna().groupby(assignment[mask],observed=True).sum().reindex(s.index);changed=(old.ne(new)&old.notna()&new.notna())[mask].groupby(assignment[mask],observed=True).sum().reindex(s.index)
   impact=pd.DataFrame({'level':lev,'center_id':s.index,'original_P2010_known_sum':original.to_numpy(),'accepted_P2010_known_sum':s.system_population_known_sum_2010.to_numpy(),'original_P2010_missing_n':original_missing.to_numpy(),'changed_observed_P2010_members':changed.to_numpy(),'P2021_known_sum':s.system_population_known_sum_2021.to_numpy(),'accepted_pair_numerically_complete':(s.system_population_complete_2010&s.system_population_complete_2021).to_numpy()})
   impact['accepted_minus_original_P2010']=impact.accepted_P2010_known_sum-impact.original_P2010_known_sum;oldvalid=impact.original_P2010_missing_n.eq(0)&impact.accepted_pair_numerically_complete&impact.original_P2010_known_sum.gt(0);newvalid=impact.accepted_pair_numerically_complete&impact.accepted_P2010_known_sum.gt(0)
   impact['original_change2010_2021_pct']=((impact.P2021_known_sum/impact.original_P2010_known_sum-1)*100).where(oldvalid);impact['accepted_change2010_2021_pct']=((impact.P2021_known_sum/impact.accepted_P2010_known_sum-1)*100).where(newvalid);impact['change_delta_percentage_points']=impact.accepted_change2010_2021_pct-impact.original_change2010_2021_pct;revision.append(impact)
  rows.append(dict(level=lev,systems=len(s),assigned_additive=int((additive&knownassignment).sum()),unassigned_additive=int((additive&~knownassignment).sum())))
 check('hierarchy_parent_strictly_higher_or_self',((hier.self_retained&hier.child_id.eq(hier.parent_id))|(~hier.self_retained&hier.parent_rank.gt(hier.child_rank))).all())
 check('hierarchy_one_parent_per_step',not hier.duplicated(['level','child_id']).any())
 cfg_for_strength=json.loads(config_guard.read_text());nonself=hier[~hier.self_retained&~hier.pending_dependent_singleton_attachment]
 strength_column=cfg_for_strength.get('hierarchy_strength_column','own_positive_mass');rank_input=cfg_for_strength.get('rank_index',{}).get('column','own_positive_mass')
 ci=centers.set_index('id');nd=nodes.set_index('id')
 strength=ci[strength_column] if strength_column in ci else nd[strength_column]
 check('hierarchy_nonself_parent_strictly_greater_configured_strength',nonself.parent_id.map(strength).gt(nonself.child_id.map(strength)).all())
 rankcol='intrinsic_empirical_rank'
 if rankcol in centers:
  rankvalues=ci[rank_input] if rank_input in ci else nd[rank_input].reindex(ci.index)
  ordered=ci.assign(_review_rankvalue=rankvalues).sort_values('_review_rankvalue')
  check('empirical_ranks_monotonic_by_declared_input',ordered[rankcol].diff().dropna().ge(0).all())
  check('empirical_rank_input_finite_all_centers',np.isfinite(rankvalues.to_numpy(float)).all())
  if cfg_for_strength.get('rank_index',{}).get('uses_modeled_catchment'):
   check('WordCi_never_refits_own_mass',cfg_for_strength['rank_index'].get('own_mass_refit') is False)
   check('WordCi_frame_excludes_historical_without_zero_imputation',cfg_for_strength['rank_index'].get('historical_unmatched_population_imputed_zero') is False)

 check('exactly_nine_type_records_per_system',types.groupby(['level','center_id']).word_type.nunique().eq(9).all() and len(types)==9*len(systems))
 check('type_system_keys_exact',set(map(tuple,types[['level','center_id']].drop_duplicates().to_numpy()))==set(map(tuple,systems[['level','center_id']].to_numpy())));check('type_record_keys_unique',not types.duplicated(['level','center_id','word_type']).any())
 configpath=config_guard;config=json.loads(configpath.read_text());initial=config['dynamic_initial_year'];final=config['dynamic_final_year'];years=final-initial
 pairs=types[['level','center_id','center_annual_rate','rural_annual_rate']].merge(systems,on=['level','center_id'],how='left',validate='many_to_one')
 for scope,startcol,endcol,outcol in [('center',f'center_population_{initial}',f'center_population_{final}','center_annual_rate'),('rural',f'rural_external_population_known_sum_{initial}',f'rural_external_population_known_sum_{final}','rural_annual_rate')]:
  baseline=pairs[startcol].to_numpy(float);endpoint=pairs[endcol].to_numpy(float);valid=(baseline>0)&(endpoint>=0);expected=np.full(len(pairs),np.nan);expected[valid]=(endpoint[valid]/baseline[valid])**(1/years)-1
  check(scope+'_annual_demographic_rate_recomputed_including_endpoint_zero',np.allclose(expected,pairs[outcol],equal_nan=True))
 full=types.rule_status.eq('satisfied_observed_indicators');condition_true=types.required_criteria_truth_json.map(lambda s:all(v is True for v in json.loads(s).values()));core_true=types.operational_core_truth_json.map(lambda s:all(v is True for v in json.loads(s).values()))
 check('full_types_require_every_literal_true_and_primary_population',(~full|(condition_true&types.population_pair_complete&types.population_pair_exact_primary_supported)).all());check('operational_hypotheses_require_every_core_true_and_population_complete',np.array_equal(types.operational_hypothesis,(core_true&types.population_pair_complete)))
 expect=set(map(tuple,types.loc[types.operational_hypothesis,['level','center_id','word_type']].to_numpy()));actual=set(map(tuple,oper[['level','center_id','word_type']].to_numpy()));check('operational_export_exact_filtered_rows',expect==actual);check('operational_status_always_hypothesis',oper.operational_status.eq('HYPOTHESIS').all())
 after={f:sha(M/f) for f in files};check('all_outputs_stable_during_independent_review',before==after);check('code_config_stable_during_review',guard_hashes=={str(p):sha(p) for p in guard_paths})
 if revision:pd.concat(revision,ignore_index=True).to_csv(H/(a.model+'_population_revision_impact.csv'),index=False)
 result=dict(target_run_id=run.get('target_run_id'),model_directory=a.model,checks=checks,n_checks=len(checks),n_failed=sum(not x['pass_'] for x in checks),model_output_sha256=before,reviewed_code_configuration_sha256=guard_hashes,levels=rows,strict_fully_satisfied_types=int(full.sum()),operational_type_hypotheses=len(oper),status='INDEPENDENT_ARITHMETIC_AND_TYPES_VERIFIED_SCIENTIFIC_REVIEW_REMAINS' if all(x['pass_'] for x in checks) else 'RETURN_TO_REPAIR_LOOP',scientific_final_allowed=False)
 (H/(a.model+'_independent_audit.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['checks','model_output_sha256']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
