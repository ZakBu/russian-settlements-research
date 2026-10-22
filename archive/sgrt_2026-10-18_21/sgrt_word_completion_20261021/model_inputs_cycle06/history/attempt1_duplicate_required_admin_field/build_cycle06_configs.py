#!/usr/bin/env python3
"""Same six preregistered scientific models on actual January2021 roads.
Adds independently reviewed nonmass Word evidence; never refits ownMi to regions.
"""
from pathlib import Path
import argparse,json,copy,hashlib,shutil,datetime,sys
import pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=ROOT.parents[1];OLD=ROOT/'model_inputs_cycle05';VARIANTS=['baseline','narrow_general_health','broad_retail_plus_ATM','unknown_role_upper','P0_probability','inclusive_candidates']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return str(p.resolve().relative_to(REPO))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def layer(path,retain):return dict(path=rel(path),key='id',prefix='',optional=False,retain_prefixes=retain)
def run(a):
 out=a.output_directory.resolve();out.mkdir(parents=True,exist_ok=True)
 if any((out/('config_'+v+'_provisional.json')).exists() for v in VARIANTS):raise FileExistsError('Do not overwrite any existing cycle06 source config')
 base=a.base_config_directory.resolve();net=ROOT/'transport/cycle06_network2021';matrix=net/'candidate_travel_times_manifest.json';snap=net/'settlement_road_snap.parquet';road=json.loads((net/'routing_receipt.json').read_text());assert road['output_manifest_sha256']==sha(matrix) and road['source_snapshot_utc'].startswith('2021-01-01')
 agro=ROOT/'data/geographic_agro_v3/municipal_agro_evidence_full_axis.parquet';own=ROOT/'typology2021_cycle05/own_function_rules/settlement_own_function_evidence_2021.parquet';processing=ROOT/'typology2021_cycle05/own_function_rules/agro_processing_v1/settlement_literal_agro_processing_evidence_2021.parquet'
 independent=[ROOT/'reviews/cycle05/own_function_rules_v1_independent_audit.json',ROOT/'reviews/cycle05/literal_agroprocessing_v1_independent_audit.json',ROOT/'reviews/cycle05/network2021_independent/full_raw_source_selection_independent_audit.json'];agroreview=ROOT/'reviews/cycle05/geographic_agro_v3_independent_audit.json';pending=[]
 if agroreview.exists():independent.append(agroreview)
 else:pending.append(rel(agroreview))
 if a.transport_review:independent.append(a.transport_review.resolve())
 else:pending.append('independent actual2021 graph/matrix admission receipt to be bound before execution')
 for p in independent:
  j=json.loads(p.read_text());assert j.get('n_failed',j.get('n_failed_checks',0))==0,str(p)
 provenance=independent+[net/'artifact_manifest.json',net/'routing_receipt.json',net/'matrix_protocol.json',ROOT/'data/geographic_agro_v3/freeze_manifest.json',ROOT/'data/geographic_agro_v3/source_archive_provenance.json']
 shutil.copyfile(OLD/'cycle05_preregistration.json',out/'cycle05_preregistration.json');protocol=out/'cycle06_source_epoch_and_nonmass_evidence_protocol.json'
 sources=[matrix,snap,agro,own,processing]+provenance
 supplement=dict(status='PREREGISTERED_SOURCE_EPOCH_REPAIR_AND_AVAILABLE_NONMASS_WORD_EVIDENCE_BEFORE_CYCLE06_METRICS',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),old_scientific_design_sha256=sha(OLD/'cycle05_preregistration.json'),six_variants=VARIANTS,network_source_snapshot_utc=road['source_snapshot_utc'],network_reference_year=2021,network_source='actual historical Russia OSM, directed graph and declared speed/connector scenario, not observed traffic',new_matrix_sha256=sha(matrix),unchanged=['five_equal_available_domains_ownMi','all_source_mass_values_and_standardization','statistical_role_V3','legal_subtype_eligibility','six_candidate_and_P0_policies','Huff_decay_and_probability_rules','Ci_formula_and_onepass','no_fit_on_catchment_or_external_labels'],nonmass_added=['municipalgrain/sownareaWordevidence','datedownpositivefunctioncopresence','datedliteralagroprocessingproxy'],new_evidence_is_not_in_Mi_or_center_eligibility=True,no_previous_memberships_or_Ci_or_ranks_reused=True,source_sha256={rel(p):sha(p) for p in sources},independent_admission_receipts=[rel(p) for p in independent],pending_admissions_before_actual_execution=pending,provisional_algorithm='unchanged model_inputs_cycle05/prepare_word_ci_cycle05.py imports cycle05 model; only dated sources change',full_algorithm='new model/run_word_model_cycle06.py supplied by root after source/shape audit',code_sha256=sha(Path(__file__)));dump(protocol,supplement)
 entries=[]
 for variant in VARIANTS:
  src=base/('config_'+variant+'_provisional.json');c=json.loads(src.read_text());old=copy.deepcopy(c);roadlayers=[l for l in c['layers'] if l.get('prefix')=='road_'];assert len(roadlayers)==1;roadlayers[0]['path']=rel(snap);c['travel_manifest']=rel(matrix);c['travel_edges']=rel(matrix);c['transport_reference_year']=2021;c['network_source_snapshot_utc']=road['source_snapshot_utc'];c['target_run_id']='sgrt_word_completion_20261021_cycle06_actual_network2021__'+variant
  c['layers'] += [layer(agro,['agro_','context_grain_yield_','context_sown_area_','context_sown2010_']),layer(own,['own2021_','trade_and_administration_','basic_administrative_','developed_agro_infrastructure_','own_function_','official_seat2021Jan_']),layer(processing,['own2021_','agro_processing_','literal_processing_'])]
  c['provenance_sidecars']=list(dict.fromkeys(c.get('provenance_sidecars',[])+[rel(p) for p in provenance]+[rel(protocol)]));c['rural_context_numeric_columns']=list(dict.fromkeys(c.get('rural_context_numeric_columns',[])+['context_grain_yield_centner_per_ha_2021','context_sown_area2021_over2010_usable_ratio']))
  assert c['components']==old['components'] and c['physical_features']==old['physical_features'] and c['center_eligibility_2021_features']==old['center_eligibility_2021_features'] and c['model']==old['model'] and c['settlement_role_policy']==old['settlement_role_policy']
  q=out/('config_'+variant+'_provisional.json');dump(q,c);entries.append(dict(variant=variant,base_config=rel(src),base_config_sha256=sha(src),new_config=rel(q),new_config_sha256=sha(q)))
 dump(out/'cycle06_config_binding_receipt.json',dict(status='ALL_SIX_CYCLE06_CONFIGS_PREPARED_SOURCE_ADMISSION_PENDING' if pending else 'ALL_SIX_CYCLE06_CONFIGS_SOURCE_BOUND',entries=entries,protocol_sha256=sha(protocol),pending_admissions=pending,old_source_bound_v4_configs_unmodified=True))
 # Actual source-level Mi check, with pending review pins omitted only from this
 # in-memory comparison. It does not authorize model execution before admission.
 sys.path.insert(0,str(ROOT/'model'));import run_word_model_cycle05 as model
 variant='baseline';newcfg=json.loads((out/'config_baseline_provisional.json').read_text());newcfg['provenance_sidecars']=[p for p in newcfg['provenance_sidecars'] if (REPO/p).exists()];oldcfg=json.loads((base/'config_baseline_provisional.json').read_text());n0,w0=model.load_nodes(oldcfg);m0,co0=model.build_mass(n0,oldcfg);n1,w1=model.load_nodes(newcfg);m1,co1=model.build_mass(n1,newcfg);compare=[x for x in m0 if x=='id' or x=='own_positive_mass' or x.endswith(('_raw','_z')) or x=='n_observed_mass_blocks'];assert m0[compare].equals(m1[compare]),'Actual cycle06 source change affected ownMi components';assert m0.candidate_center.equals(m1.candidate_center),'Nonmass source changed candidate eligibility'
 fingerprint=hashlib.sha256(pd.util.hash_pandas_object(m1[['id','own_positive_mass']],index=False).to_numpy().tobytes()).hexdigest();evidence={k:int(n1[k].notna().sum()) for k in ['agro_high_productivity_evidence','agro_decline_evidence','trade_and_administration_function_evidence','basic_administrative_service_function_evidence','developed_agro_infrastructure_evidence','agro_processing_function_evidence']};dump(out/'baseline_actual_Mi_invariance_preflight.json',dict(status='PASS_ACTUAL_FIXED_MI_AND_CANDIDATES_IDENTICAL_WITH_ADDED_WORD_EVIDENCE',new_nodes=len(n1),candidate_centers=int(m1.candidate_center.sum()),all_numeric_Mi_components_compared=compare,fixed_Mi_values_sha256=fingerprint,nonnull_new_evidence=evidence,no_metrics_or_new_memberships_read=True,model_code_sha256=sha(Path(model.__file__)),admission_pending=pending))
 print(json.dumps(dict(status='CYCLE06_BASELINE_AND_ALL6_CONFIGS_READY',baseline_config=rel(out/'config_baseline_provisional.json'),fixed_Mi_values_sha256=fingerprint,candidate_centers=int(m1.candidate_center.sum()),evidence_nonnull=evidence,admissions_pending=pending),ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base-config-directory',type=Path,default=OLD/'source_bound_v4');p.add_argument('--output-directory',type=Path,default=H);p.add_argument('--transport-review',type=Path);run(p.parse_args())
