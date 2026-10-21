#!/usr/bin/env python3
"""One new all-candidate Huff pass with fixed own Mi; dated statistical-rural Ci.

Uses cycle05 model only. No historic memberships/ranks, no fitting Mi to its zones.
Nullable statistical category and missing population are carried into bound/completeness
columns. Operational Ci uses the preregistered lower/upper scenario, not a false exact total.
"""
from pathlib import Path
import argparse,copy,json,hashlib,time,sys
import pandas as pd,numpy as np
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=ROOT.parents[1]
sys.path.insert(0,str(ROOT/'model'))
import run_word_model_cycle05 as m

def normalized(v):
 v=pd.to_numeric(v,errors='coerce');span=v.max()-v.min()
 return (v-v.min())/span if pd.notna(span) and span>0 else v.where(v.isna(),0.)
def summarize_provisional_rural(nodes,members,centers,config):
 if not members.id.equals(nodes.id):raise ValueError('Huff membership IDs/order differ from input nodes')
 spec=config['settlement_role_policy'];selected_mask,rural=m.rural_membership(nodes,config);dated=nodes[spec['dated_column']].astype('boolean').fillna(False);policy=m.rural_volume_policy(config)
 if policy not in {'known_rural_lowerbound','unknown_as_rural_upperbound'}:raise ValueError('Unregistered rural bound')
 x=nodes[['id','_population_axis_row','population_2021']].copy();x['center_id']=members.assigned_center_id.to_numpy();x['rural_role']=rural;x['dated2021']=dated
 external=x[x._population_axis_row&x.dated2021&x.center_id.notna()&x.id.ne(x.center_id)].copy()
 known=external[external.rural_role.fillna(False)];unknown=external[external.rural_role.isna()]
 out=centers[['id','own_positive_mass']].copy()
 def counts(df):return out.id.map(df.groupby('center_id').size()).fillna(0).astype('int64')
 def sums(df):return out.id.map(df.groupby('center_id').population_2021.sum(min_count=1)).fillna(0.)
 out['provisional_observed2021_rural_units']=counts(known);out['provisional_observed2021_rural_missing_values']=counts(known[known.population_2021.isna()]);out['provisional_observed2021_rural_population_known_sum']=sums(known)
 out['provisional_observed2021_unknown_role_units']=counts(unknown);out['provisional_observed2021_unknown_role_population_known_sum']=sums(unknown);out['provisional_observed2021_unknown_role_missing_population_units']=counts(unknown[unknown.population_2021.isna()])
 lower=out.provisional_observed2021_rural_population_known_sum;upper=lower+out.provisional_observed2021_unknown_role_population_known_sum
 no_missing=out.provisional_observed2021_rural_missing_values.eq(0)&out.provisional_observed2021_unknown_role_missing_population_units.eq(0)
 out['provisional_observed2021_statistical_rural_lower_bound']=lower;out['provisional_observed2021_statistical_rural_upper_bound']=upper.where(no_missing)
 complete=no_missing&out.provisional_observed2021_unknown_role_units.eq(0);out['provisional_observed2021_rural_population_complete']=complete;out['provisional_observed2021_rural_population_exact_component']=lower.where(complete)
 out['provisional_selected_rural_volume_policy']=policy;selected=lower if policy=='known_rural_lowerbound' else upper.where(no_missing);out['provisional_selected_rural_population_component2021']=selected
 historical=nodes._population_axis_row&~dated&members.assigned_center_id.notna()&nodes.id.ne(members.assigned_center_id)
 hc=pd.DataFrame({'center_id':members.loc[historical,'assigned_center_id']});out['provisional_historical_entities_outside2021frame']=counts(hc)
 out['normalized_log_own_mass']=normalized(np.log(out.own_positive_mass));out['normalized_log1p_observed2021_rural_population']=normalized(np.log1p(selected));out['word_centrality_observed2021_frame_0_1']=.5*out.normalized_log_own_mass+.5*out.normalized_log1p_observed2021_rural_population
 out['word_centrality_0_1']=out.word_centrality_observed2021_frame_0_1;out['historical_missing_values_imputed_zero']=False;out['own_mass_refitted_on_catchment']=False;out['provisional_iterations']=1;out['provisional_exactness_is_not_implied_by_numeric_operational_bound']=True
 return out,external

def run(inputs,output):
 start=time.monotonic();inputs=inputs.resolve();output=output.resolve()
 if any((output/n).exists() for n in ['word_ci_center_features.parquet','provisional_all_center_memberships.parquet','receipt.json']):raise FileExistsError('Refusing to overwrite an existing provisional run: '+str(output))
 output.mkdir(parents=True,exist_ok=True);config=json.loads(inputs.read_text())
 if config.get('reuse_function_memberships_from'):raise ValueError('Cycle05 forbids reusing previous memberships')
 if config.get('rank_index',{}).get('uses_modeled_catchment'):raise ValueError('Provisional run must rank own fixed Mi, not previously computed Ci')
 reg=inputs.parent/'cycle05_preregistration.json'
 if not reg.exists():raise FileNotFoundError('Preregistration must precede new model outputs')
 nodes,watched=m.load_nodes(config);mass,components=m.build_mass(nodes,config);centers,ranks=m.empirical_ranks(mass,config)
 watched[inputs]=m.sha(inputs);watched[Path(m.__file__).resolve()]=m.sha(Path(m.__file__).resolve());watched[Path(__file__).resolve()]=m.sha(Path(__file__).resolve());watched[reg]=m.sha(reg)
 preliminary=copy.deepcopy(config);preliminary['model']['hierarchy_max_travel_minutes']=preliminary['model']['max_travel_minutes'];rw,rr,scope=m.verify_routing_scope(preliminary,nodes,centers,mass[['id']]);watched.update(rw)
 source=m.travel_source(config);watched[source]=m.sha(source)
 if watched[source]!=rr['output_manifest_sha256']:raise ValueError('Routing manifest differs from actual route receipt')
 travel,source=m.load_travel(preliminary,nodes,centers,mass[['id']]);watched.update(travel.attrs.pop('additional_source_sha256',{}));members,edges=m.huff_assign(nodes,centers,travel,preliminary,preserve_cores=True);n_edges=len(edges);del edges,travel
 features,external=summarize_provisional_rural(nodes,members,centers,config)
 changed=[str(p) for p,digest in watched.items() if m.sha(p)!=digest]
 if changed:raise RuntimeError('Inputs changed during new Ci pass: '+repr(changed))
 members.to_parquet(output/'provisional_all_center_memberships.parquet',index=False);features.to_parquet(output/'word_ci_center_features.parquet',index=False);mass.to_parquet(output/'fixed_own_mass_components.parquet',index=False)
 (output/'mass_component_bindings.json').write_text(json.dumps(components,ensure_ascii=False,indent=2)+'\n')
 ordinary=nodes._population_axis_row;dated=nodes[config['settlement_role_policy']['dated_column']].astype('boolean').fillna(False);unassigned=ordinary&members.assigned_center_id.isna();unknown=features.provisional_observed2021_unknown_role_units
 receipt=dict(status='CYCLE05_WORD_CI_COMPUTED_PENDING_INDEPENDENT_REVIEW',variant=config['cycle05_variant'],eligible_centers=len(features),operational_rank_frame='actual observed additive2021 NP records; statistical-rural category role nullable; declared bound selected',native2021_axis_units=int((ordinary&dated).sum()),native2021_actual_observed_zero_rows=int((ordinary&dated&nodes.population_2021.eq(0)).sum()),native2021_records_with_missing_population=int((ordinary&dated&nodes.population_2021.isna()).sum()),observed2021_frame_complete_centers=int(features.provisional_observed2021_rural_population_complete.sum()),centers_with_unknown_member_role=int(unknown.gt(0).sum()),unknown_role_member_units=int(unknown.sum()),unknown_role_member_known_population2021=float(features.provisional_observed2021_unknown_role_population_known_sum.sum()),centers_missing_selected_bound=int(features.word_centrality_observed2021_frame_0_1.isna().sum()),unassigned_ordinary_origin_units=int(unassigned.sum()),unassigned_known_population2021=float(nodes.loc[unassigned,'population_2021'].sum()),provisional_choice_pairs_computed=n_edges,provisional_all_candidate_competition=True,provisional_core_protection=True,provisional_outside_mass=config['model']['outside_mass'],provisional_minimum_choice_probability=config['model']['minimum_choice_probability'],fixed_formula='0.5*minmax(log(fixedOwnMi))+0.5*minmax(log1p(provisional_selected_statistical_rural_bound2021))',selected_rural_volume_policy=config['settlement_role_policy']['rural_volume'],unknown_role_population_reported_separately_not_imputed_zero=True,own_mass_refit=False,provisional_iterations=1,own_mass_domains=config['mass_domains'],missing_domain_policy=config['mass_missing_domain_policy'],n_observed_mass_blocks=mass.n_observed_mass_blocks.value_counts().sort_index().to_dict(),input_sha256={str(p):v for p,v in watched.items()},own_mass_values_sha256=hashlib.sha256(pd.util.hash_pandas_object(mass[['id','own_positive_mass']],index=False).to_numpy().tobytes()).hexdigest(),input_bytes_changed=changed,seconds=time.monotonic()-start)
 (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_sha256']},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.inputs,a.output)
