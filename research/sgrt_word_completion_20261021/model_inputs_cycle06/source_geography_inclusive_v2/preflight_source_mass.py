#!/usr/bin/env python3
"""Actual seventh-source Mi/candidate/provider preflight after prereg admission.
Reads frozen source data and code only; never reads predictions or runs Huff.
"""
from pathlib import Path
import argparse,json,copy,hashlib,sys,datetime
import pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parents[1];REPO=next(p for p in H.parents if (p/'.git').exists())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.resolve().relative_to(REPO))
def dump(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
def fingerprint(m):return hashlib.sha256(pd.util.hash_pandas_object(m[['id','own_positive_mass']],index=False).to_numpy().tobytes()).hexdigest()
def run(a):
 output=a.output.resolve();assert not output.exists();review=a.admission.resolve();j=json.loads(review.read_text());reg=H/'preregistration.json';assert j.get('all_checks_passed') is True and (sha(reg) in review.read_text() or sha(H/'freeze_manifest.json') in review.read_text()),'Seventh V2 prereg must be independently admitted first'
 base=ROOT/'model_inputs_cycle06/config_baseline_provisional.json';baseline=json.loads(base.read_text());cfg=copy.deepcopy(baseline);patch=json.loads((H/'future_config_patch_NOT_BOUND.json').read_text());cfg['physical_features']=patch['physical_features'];cfg['center_eligibility_2021_features']=patch['center_eligibility_2021_features'];cfg['derived_features']=cfg.get('derived_features',[])+patch['derived_features_additions'];cfg['cycle05_variant']='source_geography_inclusive';cfg['target_run_id']='SOURCE_ONLY_PREFLIGHT_NOT_ROUTING_BOUND_OR_MODEL_RUN';cfg['provenance_sidecars']+= [rel(reg),rel(review)]
 sys.path.insert(0,str(ROOT/'model'));import run_word_model_cycle05 as m
 nodes0,w0=m.load_nodes(baseline);mass0,c0=m.build_mass(nodes0,baseline);nodes,watched=m.load_nodes(cfg);mass,components=m.build_mass(nodes,cfg);assert nodes.id.equals(nodes0.id)
 # Check every union before Mi: actual summation, never max across channels.
 for d in patch['derived_features_additions']:
  expected=nodes[d['columns']].apply(pd.to_numeric,errors='coerce').sum(axis=1,min_count=1);assert expected.equals(nodes[d['name']]),d['name']
 # Non-service raw source components remain identical, while their standardization
 # is also unchanged. OwnMi can change only through the specified service unions.
 unchanged=[x['name'] for x in baseline['components'] if x['block']!='service'];cols=['id']+[n+s for n in unchanged for s in ['_raw','_z']];assert mass0[cols].equals(mass[cols])
 providercols=[k for k in mass if k.startswith('physical_') and k.endswith('_positive_witness')];provider=mass[providercols].any(axis=1);candidate=mass.candidate_center;anchors=set(m.large_city_anchor_ids(nodes,cfg));select=provider|candidate|nodes.id.isin(anchors)
 fields=[c for c in ['id','name','type','region','lat','lon','population_2021','axis_kind','accepted_statistical_rural_role2021','accepted_formal_settlement_subtype2021'] if c in nodes];dest=nodes.loc[select,fields].copy();dest['eligible_in_source_geography_scenario']=candidate[select].to_numpy();dest['large_city_context_anchor']=dest.id.isin(anchors);dest['provider_functions_json']=[json.dumps([c.removeprefix('physical_').removesuffix('_positive_witness') for c in providercols if bool(mass.at[i,c])]) for i in mass.index[select]];dest['routing_budget_minutes']=(dest.eligible_in_source_geography_scenario|dest.large_city_context_anchor).map({True:360,False:180});dest['source_only_potential_not_accepted_snap']=True
 previous=a.existing_destinations.resolve();old=pd.read_parquet(previous);dest['new_vs_original_six_destinations']=~dest.id.isin(old.id);dest['existing_budget_minutes']=dest.id.map(old.set_index('id').routing_budget_minutes);dest['existing_budget_upgrade_needed']=dest.existing_budget_minutes.notna()&dest.existing_budget_minutes.lt(dest.routing_budget_minutes)
 output.mkdir(parents=True);dest.to_parquet(output/'seventh_source_only_potential_destinations.parquet',index=False);mass.to_parquet(output/'source_only_own_mass_components.parquet',index=False);dump(output/'mass_component_bindings.json',components);dump(output/'source_only_configuration_NOT_ROUTING_BOUND.json',cfg)
 watched.update(w0);watched.update({base:sha(base),reg:sha(reg),review:sha(review),previous:sha(previous),Path(m.__file__):sha(Path(m.__file__)),Path(__file__):sha(Path(__file__))});assert all(sha(p)==v for p,v in watched.items()),'Source changed while preflighting'
 dump(output/'receipt.json',dict(status='ACTUAL_SOURCE_ONLY_MASS_AND_POTENTIAL_DESTINATIONS_COMPUTED_NOT_ROUTING_BOUND_NO_HUFF',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline_ownMi_sha256=fingerprint(mass0),seventh_ownMi_sha256=fingerprint(mass),baseline_candidates=int(mass0.candidate_center.sum()),seventh_candidates=int(candidate.sum()),new_candidate_ids=int((candidate&~mass0.candidate_center).sum()),lost_candidate_ids=int((~candidate&mass0.candidate_center).sum()),potential_provider_or_candidate_or_largecity_destinations=len(dest),new_vs_existing_six_destinations=int(dest.new_vs_original_six_destinations.sum()),existing_destinations_needing_budget_upgrade=int(dest.existing_budget_upgrade_needed.sum()),nonservice_Mi_components_identical=True,all_disjoint_union_fields_recomputed=True,source_geography_only_no_format_or_eligibility_policy_broadening=True,transport_access_v2_binding_pending=True,all_potential_points_require_future_accepted_snap_and_matrix=True,no_predictions_or_memberships_or_old_Ci_read=True,no_model_or_Huff_run=True,input_sha256={rel(p):v for p,v in watched.items()}));files=list(output.iterdir());dump(output/'freeze_manifest.json',dict(files={p.name:sha(p) for p in files if p.is_file()}));print((output/'receipt.json').read_text())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--admission',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--existing-destinations',type=Path,default=ROOT/'transport/cycle06_network2021_access_v2/all_six_required_potential_destinations.parquet');run(p.parse_args())
