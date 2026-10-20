#!/usr/bin/env python3
"""One provisional all-center Huff pass, fixed Mi, then Word's mass+perimeter Ci.

This never fits Mi to modeled perimeters and never iterates to a fixed point.
Any unknown member P2021 makes that center's zone component and Ci unknown.
"""
from pathlib import Path
import argparse,copy,json,hashlib,time
import numpy as np
import pandas as pd
import run_word_model as m

def normalized(values):
 span=values.max()-values.min()
 return (values-values.min())/span if span>0 else values.where(values.isna(),0.)

def run(inputs,output):
 output.mkdir(parents=True,exist_ok=True);start=time.monotonic();config=json.loads(inputs.read_text());nodes,watched=m.load_nodes(config);mass,components=m.build_mass(nodes,config);centers,ranks=m.empirical_ranks(mass,config)
 watched[inputs.resolve()]=m.sha(inputs);watched[Path(m.__file__)]=m.sha(Path(m.__file__));watched[Path(__file__).resolve()]=m.sha(Path(__file__))
 preliminary=copy.deepcopy(config);preliminary['model']['hierarchy_max_travel_minutes']=preliminary['model']['max_travel_minutes']
 route_watched,route_receipt,scope=m.verify_routing_scope(preliminary,nodes,centers,mass[['id']]);watched.update(route_watched)
 source=m.travel_source(config);watched[source]=m.sha(source)
 if watched[source]!=route_receipt['output_manifest_sha256']:raise ValueError('Routing manifest receipt mismatch')
 travel,source=m.load_travel(preliminary,nodes,centers,mass[['id']]);watched.update(travel.attrs.pop('additional_source_sha256',{}))
 members,edges=m.huff_assign(nodes,centers,travel,preliminary,preserve_cores=True);n_edges=len(edges);del edges,travel
 members.to_parquet(output/'provisional_all_center_memberships.parquet',index=False)
 x=nodes[['id','type','_population_axis_row','population_2021','source_record_id_2021']].copy();x['center_id']=members.assigned_center_id.to_numpy();rural=~x.type.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 external=x[x._population_axis_row&rural&x.center_id.notna()&x.id.ne(x.center_id)]
 groups=external.groupby('center_id',observed=True);total=groups.size();known=groups.population_2021.count();lower=groups.population_2021.sum(min_count=1)
 result=centers[['id','own_positive_mass']].copy();result['provisional_rural_units']=result.id.map(total).fillna(0).astype(int);result['provisional_rural_known_population_units']=result.id.map(known).fillna(0).astype(int);result['provisional_rural_missing_population_units']=result.provisional_rural_units-result.provisional_rural_known_population_units
 result['provisional_rural_population_known_lower_bound2021']=result.id.map(lower).fillna(0.)
 result.loc[result.provisional_rural_units.eq(0),'provisional_rural_population_known_lower_bound2021']=0.
 complete=result.provisional_rural_missing_population_units.eq(0);result['provisional_rural_population_complete2021']=complete
 result['provisional_rural_population_exact_component2021']=result.provisional_rural_population_known_lower_bound2021.where(complete)
 result['rural_unit_count_coverage']=np.divide(result.provisional_rural_known_population_units,result.provisional_rural_units,out=np.ones(len(result)),where=result.provisional_rural_units.to_numpy()>0)
 result['true_person_population_coverage']=np.where(complete,1.,np.nan)
 result['person_population_coverage_unknown_if_any_missing_unit']=~complete
 result['normalized_log_own_mass']=normalized(np.log(result.own_positive_mass));result['normalized_log1p_complete_provisional_rural_population']=normalized(np.log1p(result.provisional_rural_population_exact_component2021))
 result['word_centrality_0_1']=.5*result.normalized_log_own_mass+.5*result.normalized_log1p_complete_provisional_rural_population
 # A separately declared 2021 estimand uses actual dated census source records.
 # Historical entities outside that frame retain NA, not imputed zero population.
 native_external=external[external.source_record_id_2021.notna()];native_groups=native_external.groupby('center_id',observed=True)
 native_total=native_groups.size();native_known=native_groups.population_2021.count();native_volume=native_groups.population_2021.sum(min_count=1)
 result['provisional_observed2021_rural_units']=result.id.map(native_total).fillna(0).astype(int)
 result['provisional_observed2021_rural_missing_values']=result.provisional_observed2021_rural_units-result.id.map(native_known).fillna(0).astype(int)
 result['provisional_historical_rural_entities_outside2021frame']=result.provisional_rural_units-result.provisional_observed2021_rural_units
 result['provisional_observed2021_rural_population_known_sum']=result.id.map(native_volume).fillna(0.)
 observed_complete=result.provisional_observed2021_rural_missing_values.eq(0);result['provisional_observed2021_rural_population_complete']=observed_complete
 observed_value=result.provisional_observed2021_rural_population_known_sum.where(observed_complete)
 result['normalized_log1p_observed2021_rural_population']=normalized(np.log1p(observed_value))
 result['word_centrality_observed2021_frame_0_1']=.5*result.normalized_log_own_mass+.5*result.normalized_log1p_observed2021_rural_population
 result['historical_missing_values_imputed_zero']=False
 result['own_mass_refitted_on_catchment']=False;result['provisional_iterations']=1;result.to_parquet(output/'word_ci_center_features.parquet',index=False)
 ordinary=nodes._population_axis_row;missing_origin=members.assigned_center_id.isna()&ordinary
 changed=[str(p) for p,h in watched.items() if m.sha(p)!=h]
 receipt={'status':'PREPARED_WORD_CI_REQUIRES_RANK_SCOPE_AUDIT' if not changed else 'REJECT_INPUT_CHANGED_DURING_RUN','eligible_centers':len(result),'operational_rank_frame':'observed_native_census2021_records; unmatched historical entities excluded from this dated estimand, not imputed zero','native2021_axis_units':int((ordinary&nodes.source_record_id_2021.notna()).sum()),'native2021_actual_observed_zero_rows':int((ordinary&nodes.source_record_id_2021.notna()&nodes.population_2021.eq(0)).sum()),'native2021_records_with_missing_population':int((ordinary&nodes.source_record_id_2021.notna()&nodes.population_2021.isna()).sum()),'observed2021_frame_complete_centers':int(observed_complete.sum()),'centers_with_complete_zone':int(complete.sum()),'centers_missing_zone_population':int((~complete).sum()),'missing_population_units_in_assigned_provisional_zones':int(result.provisional_rural_missing_population_units.sum()),'unassigned_ordinary_origin_units':int(missing_origin.sum()),'unassigned_known_population2021':float(nodes.loc[missing_origin,'population_2021'].sum()),'provisional_choice_pairs_computed':n_edges,'provisional_all_candidate_competition':True,'provisional_core_protection':True,'provisional_outside_mass':config['model']['outside_mass'],'provisional_minimum_choice_probability':config['model']['minimum_choice_probability'],'fixed_formula':'0.5*minmax(log(Mi))+0.5*minmax(log1p(complete provisional rural P2021))','zone_missing_policy':'any missing member P2021 => zone component NULL and Ci NULL; no own-Mi-only fallback','own_mass_refit':False,'provisional_iterations':1,'input_sha256':{str(p):h for p,h in watched.items()},'own_mass_values_sha256':hashlib.sha256(pd.util.hash_pandas_object(mass[['id','own_positive_mass']],index=False).to_numpy().tobytes()).hexdigest(),'input_bytes_changed':changed,'seconds':time.monotonic()-start}
 (output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='input_sha256'},ensure_ascii=False,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.inputs,a.output)
