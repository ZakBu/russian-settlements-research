#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,copy,datetime,shutil
H=Path(__file__).resolve().parent;ROOT=H.parents[1];REPO=next(p for p in H.parents if (p/'.git').exists())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rel(p):return str(p.relative_to(REPO))
def run():
 assert not (H/'preregistration.json').exists();old=H.parent/'source_geography_inclusive_v1';j=json.loads((old/'preregistration.json').read_text());base=json.loads((ROOT/'model_inputs_cycle06/config_baseline_provisional.json').read_text());defs=[];mapping={};physical={}
 for function,originals in base['physical_features'].items():
  physical[function]=[]
  for col in originals:
   if col.startswith('medical_'):channels=[col,col.replace('_baseline_','_conditional_additional_'),col.replace('_baseline_','_coordinate_candidate_')]
   else:channels=[col,col.replace('_baseline_','_candidate_additional_')]
   name='source_geography_union2021_'+col.replace('_baseline_','_');defs.append(dict(name=name,operation='sum_disjoint',columns=channels));physical[function].append(name);mapping[col]=name
 eligibility={k:physical[k] for k in base['center_eligibility_2021_features']}
 j.update(status='PREREGISTERED_INTERFACE_REPAIR_SAME_SEVENTH_SOURCE_UNION_BEFORE_MASS_OR_OUTCOMES',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),supersedes_nonrunnable_v1_patch_only=True,repair_reason='choose_physical uses max(options), not sum; disjoint counts must first be materialized through existing declared sum_disjoint derived feature operation',old_v1_preregistration_sha256=sha(old/'preregistration.json'),scientific_source_union_design_unchanged=True,no_source_or_outcome_reclassification=True,physical_features=physical,center_eligibility_2021_features=eligibility,derived_features_additions=defs,highereducation_preserves_primary_college_vs_university_MAX_proxy_not_crossformat_SUM=True,code_sha256=sha(Path(__file__)))
 dump(H/'preregistration.json',j);dump(H/'future_config_patch_NOT_BOUND.json',dict(cycle05_variant='source_geography_inclusive',derived_features_additions=defs,physical_features=physical,center_eligibility_2021_features=eligibility,nonservice_scientific_parameters_inherit_baseline_exactly=True,transport_binding_pending_access_v2=True,not_a_runnable_config=True));shutil.copyfile(old/'source_channel_counts_before_model.csv',H/'source_channel_counts_before_model.csv');files=list(H.iterdir());dump(H/'freeze_manifest.json',dict(status='FROZEN_BEFORE_SEVENTH_ACTUAL_MASS_OR_OUTCOMES',files={p.name:sha(p) for p in files if p.is_file()}));print(H)
if __name__=='__main__':run()
