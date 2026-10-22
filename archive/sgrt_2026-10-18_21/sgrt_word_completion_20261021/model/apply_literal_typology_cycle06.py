"""Cycle05 literal Word eligibility using dated subtype and independent large-city anchors.

Original measured-pattern hypotheses are retained. Qualitative Word terms use
published scenario parameters, not thresholds chosen from the desired labels.
"""
from pathlib import Path
import argparse,json,hashlib,copy
import pandas as pd
import numpy as np
import run_word_model_cycle06 as m

def encode(value):return json.dumps(value,ensure_ascii=False,allow_nan=False)
def require_source_review(reviewfile, layer):
 review=json.loads(reviewfile.read_text())
 allowed={'ACCEPTED','OWN_FUNCTION_POSITIVE_CO_PRESENCE_V1_INDEPENDENTLY_ACCEPTED','LITERAL_AGROPROCESSING_SOURCE_PROXY_V1_INDEPENDENTLY_ACCEPTED'}
 failed=review.get('n_failed',review.get('n_failed_checks'))
 if review.get('status') not in allowed or failed!=0 or m.sha(layer) not in reviewfile.read_text():raise ValueError('Unaccepted or unpinned source review')

def run(inputs,model_output,output,own_function_layer=None,own_function_review=None,geographic_layer=None,geographic_review=None,processing_layer=None,processing_review=None):
 if (output/'manifest.json').exists():raise FileExistsError('Use a new canonical output directory')
 output.mkdir(parents=True,exist_ok=True);config=json.loads(inputs.read_text());manifest=json.loads((model_output/'output_manifest.json').read_text());watched={Path(m.__file__).resolve():m.sha(Path(m.__file__)),m.travel_source(config).resolve():m.sha(m.travel_source(config)),inputs.resolve():m.sha(inputs),Path(__file__).resolve():m.sha(Path(__file__)),(model_output/'output_manifest.json').resolve():m.sha(model_output/'output_manifest.json')}
 if m.sha(inputs)!=manifest['configuration_sha256']:raise ValueError('Configuration differs from frozen physical model')
 if m.sha(Path(m.__file__))!=manifest['model_code_sha256']:raise ValueError('Implementation differs from frozen model; use its pinned source snapshot')
 for filename,item in manifest['execution_source_snapshots'].items():
  current=Path(m.__file__).parent/filename
  if m.sha(current)!=item['sha256']:raise ValueError('Execution helper differs from pinned model: '+filename)
  watched[current.resolve()]=item['sha256']
 marker=output/'receipt.json.tmp';marker.write_text(encode({'status':'RUNNING_CANONICAL_TYPOLOGY'})+'\n');marker.replace(output/'receipt.json')
 for filename in ['nodes.parquet','candidate_centers.parquet','own_mass_components.parquet','word_type_hypotheses.parquet','systems.parquet']:
  p=model_output/filename
  if m.sha(p)!=manifest['files'][filename]['sha256']:raise ValueError('Unfrozen model derivative '+str(p))
  watched[p.resolve()]=m.sha(p)
 nodes=pd.read_parquet(model_output/'nodes.parquet');centers=pd.read_parquet(model_output/'candidate_centers.parquet');mass=pd.read_parquet(model_output/'own_mass_components.parquet');types=pd.read_parquet(model_output/'word_type_hypotheses.parquet');systems=pd.read_parquet(model_output/'systems.parquet');types=types.merge(systems[['level','center_id','descriptive_centrality_posthoc_0_1']].rename(columns={'descriptive_centrality_posthoc_0_1':'diagnostic_original_final_zone_posthoc_centrality'}),on=['level','center_id'],validate='many_to_one');index=nodes.set_index('id');ci=centers.set_index('id')[config.get('hierarchy_strength_column','own_positive_mass')]
 if own_function_layer is not None:
  if own_function_review is None:raise ValueError('Independent own-function layer review is required')
  reviewtext=own_function_review.read_text();review=json.loads(reviewtext)
  require_source_review(own_function_review,own_function_layer)
  own=pd.read_parquet(own_function_layer)
  if not own.id.is_unique or not set(own.id)<=set(nodes.id):raise ValueError('Own-function source identity conflict')
  columns=['trade_and_administration_function_evidence','basic_administrative_service_function_evidence']
  if (set(columns)&set(nodes)):raise ValueError('Own-function fields already present; require explicit conflict review')
  nodes=nodes.merge(own[['id']+columns],on='id',how='left',validate='one_to_one');index=nodes.set_index('id')
  watched[own_function_layer.resolve()]=m.sha(own_function_layer);watched[own_function_review.resolve()]=m.sha(own_function_review)
 # Independent population-defined large-city accessibility was computed by the
 # model from all eligible city anchors; do not reintroduce a Ci/rank filter.
 probe=types[types.word_type.eq(5)&types.operational_hypothesis].center_id.unique().tolist()
 accessibility_source=model_output/'network_accessibility.parquet'
 if m.sha(accessibility_source)!=manifest['files'][accessibility_source.name]['sha256']:raise ValueError('Unfrozen accessibility derivative')
 watched[accessibility_source.resolve()]=m.sha(accessibility_source)
 nearest=pd.read_parquet(accessibility_source).set_index('id').nearest_large_city_network_minutes.dropna().to_dict()
 for layer,reviewfile,kind in [(geographic_layer,geographic_review,'geographic'),(processing_layer,processing_review,'processing')]:
  if layer is None:continue
  if reviewfile is None:raise ValueError('Independent enrichment source admission required')
  reviewtext=reviewfile.read_text();review=json.loads(reviewtext);status=str(review.get('status',''))
  require_source_review(reviewfile,layer)
  enrichment=pd.read_parquet(layer)
  if not enrichment.id.is_unique or not set(enrichment.id)<=set(nodes.id):raise ValueError('Enrichment IDs differ from the frozen model')
  columns=[c for c in enrichment if c!='id' and (c.startswith(('agro_','context_grain_','context_sown_')) if kind=='geographic' else c=='agro_processing_function_evidence')]
  if set(columns)&set(nodes):raise ValueError('Enrichment shadows an existing model observation')
  nodes=nodes.merge(enrichment[['id']+columns],on='id',how='left',validate='one_to_one')
  watched[layer.resolve()]=m.sha(layer);watched[reviewfile.resolve()]=m.sha(reviewfile)
 if geographic_layer is not None or processing_layer is not None:
  # Restore observed geographic context without changing one assignment, mass,
  # rank, demographic observation or population aggregation of the frozen model.
  members_source=model_output/'memberships.parquet'
  if m.sha(members_source)!=manifest['files'][members_source.name]['sha256']:raise ValueError('Unfrozen memberships')
  watched[members_source.resolve()]=m.sha(members_source);members=pd.read_parquet(members_source)
  if not members.id.equals(nodes.id):raise ValueError('Frozen membership and node order differ')
  nodes=nodes.merge(pd.read_parquet(accessibility_source),on='id',how='left',validate='one_to_one')
  levels={int(c.removeprefix('center_id_l')):members[c] for c in members if c.startswith('center_id_l')}
  enriched,balances=m.aggregate(nodes,members,levels,config)
  enriched=m.descriptive_centrality(enriched,centers,int(config['mass_reference_year']))
  population_columns=[c for c in systems if 'population' in c and c in enriched and not c.startswith('rural_agro_') and '_population_coverage' not in c]
  left=systems.sort_values(['level','center_id']).reset_index(drop=True);right=enriched.sort_values(['level','center_id']).reset_index(drop=True)
  if not left[['level','center_id']+population_columns].equals(right[['level','center_id']+population_columns]):raise ValueError('Nonmass enrichment changed a demographic aggregation')
  if not balances.known_population_conserved.all():raise ValueError('Enriched population balances differ')
  enriched.to_parquet(output/'geographic_enriched_systems.parquet',index=False)
  types=m.classify_word_types(enriched,nodes,config)
  types.to_parquet(output/'geographic_enriched_broad_word_hypotheses.parquet',index=False)
  types=types.merge(enriched[['level','center_id','descriptive_centrality_posthoc_0_1']].rename(columns={'descriptive_centrality_posthoc_0_1':'diagnostic_original_final_zone_posthoc_centrality'}),on=['level','center_id'],validate='many_to_one')
  index=nodes.set_index('id')
 watched[Path(m.__file__).parent/'large_city_accessibility_cycle05.py']=m.sha(Path(m.__file__).parent/'large_city_accessibility_cycle05.py')
 output_rows=[];type5_threshold_counts={t:0 for t in [60,90,120,180]}
 for row in types.to_dict('records'):
  uid=row['center_id'];typ=int(row['word_type']);source=index.loc[uid];full=json.loads(row['required_criteria_truth_json']);core=json.loads(row['operational_core_truth_json']);raw_core=copy.deepcopy(core);added={}
  urban_type=source.get('accepted_formal_settlement_subtype2021',source.get('type'));pop=source.get('population_2021',np.nan);small=None if pd.isna(pop) else bool(pop<=50000)
  city=None if pd.isna(urban_type) else urban_type=='город'
  stat_rural=source.get('accepted_statistical_rural_role2021',pd.NA)
  formal_urban=None if pd.isna(urban_type) else str(urban_type).replace('ё','е') in ['город','пгт','поселок городского типа','рабочий поселок','рп','кп','дп','гп','курортный поселок','дачный поселок','городской поселок']
  urban=True if (pd.notna(stat_rural) and not bool(stat_rural)) or formal_urban is True else (None if pd.isna(stat_rural) and formal_urban is None else False)
  if typ in [2,3,5,7,8,9]:added['small_urban_center']=m.tri_all(urban,small)
  if typ==5:
   minutes=nearest.get(uid,np.nan);added['near_large_center_within90_modeled_minutes']=bool(minutes<=90.) if np.isfinite(minutes) else None
   row['nearest_large_center_network_minutes']=float(minutes) if np.isfinite(minutes) else None
  if typ==7:
   # No subject-name inference or climate substitution for the Word geographic zone.
   added['nonchernozem_geographic_zone']=m.tri(source.get('nonchernozem_geographic_evidence',None))
  if any(c in nodes for c in ['trade_and_administration_function_evidence','basic_administrative_service_function_evidence']):
   for criterion in ['trade_and_administration_function','basic_administrative_service_function']:
    if criterion in full:
     observed=m.tri(source.get(criterion+'_evidence',None))
     if full[criterion] is not None and observed is not None and full[criterion]!=observed:raise ValueError('Conflicting own-function evidence')
     full[criterion]=observed if observed is not None else full[criterion]
  if typ in [4,7,8]:
   value=ci.get(uid,np.nan);low=None if pd.isna(value) else bool(value<=.5)
   if 'low_ci_le0_5' in core:core['low_ci_le0_5']=low
   if typ==8:full['low_centrality']=low
   elif typ in [4,7]:full['low_mass_and_centrality' if typ==7 else 'low_or_moderate_mass_centrality']=m.tri_all(core.get('low_mass_expmeanZ_le1'),low)
  full.update(added);core.update(added)
  if typ==5:
   for threshold in type5_threshold_counts:
    variation=core.copy();variation['near_large_center_within90_modeled_minutes']=bool(nearest[uid]<=threshold) if uid in nearest else None;type5_threshold_counts[threshold]+=int(m.tri_all(*variation.values()) is True and row['population_pair_complete'])
  state=m.tri_all(*full.values());eligible=m.tri_all(*core.values())
  strict_geo_core=core.copy();strict_geo_full=full.copy()
  if typ==7:
   exact=m.tri(source.get('nonchernozem_exact_contemporary_geographic_evidence',None))
   strict_geo_core['nonchernozem_geographic_zone']=exact;strict_geo_full['nonchernozem_geographic_zone']=exact
  row['operational_hypothesis_exact_contemporary_geography']=bool(m.tri_all(*strict_geo_core.values()) is True and row['population_pair_complete'])
  row['required_criteria_truth_exact_contemporary_geography_json']=encode(strict_geo_full)
  row['nonchernozem_context_interpretation']='historical_CSU1974_regional_hypothesis_only; exact_contemporary_condition_separate_unknown' if typ==7 else 'not_required'
  row['broad_measured_pattern_operational_hypothesis']=row['operational_hypothesis'];row['broad_measured_pattern_core_truth_json']=encode(raw_core);row['literal_eligibility_added_truth_json']=encode(added)
  row['descriptive_partial_candidate_not_proven_type']=bool(sum(v is True for v in full.values())>=2 and not any(v is False for v in full.values()) and row['population_pair_complete']);row['required_criteria_truth_json']=encode(full);row['operational_core_truth_json']=encode(core);row['unknown_required_criteria_json']=encode([k for k,v in full.items() if v is None]);row['contradicted_required_criteria_json']=encode([k for k,v in full.items() if v is False]);row['n_required_criteria']=len(full);row['n_observed_supporting_criteria']=sum(v is True for v in full.values())
  row['operational_hypothesis']=bool(eligible is True and row['population_pair_complete']);row['operational_status']='HYPOTHESIS_WITH_LITERAL_ELIGIBILITY' if row['operational_hypothesis'] else 'NOT_ESTABLISHED_LITERAL_ELIGIBILITY';row['rule_status']='satisfied_observed_indicators' if state is True and row['population_pair_complete'] and row['population_pair_exact_primary_supported'] else ('not_satisfied_observed_indicators' if state is False else 'unknown_missing_required_indicators');row['classification_centrality_column']=config.get('hierarchy_strength_column','own_positive_mass');row['full_causal_validation_claim']=False;output_rows.append(row)
 result=pd.DataFrame(output_rows);broad=types[types.operational_hypothesis].copy();broad['prototype_status']='BROAD_MEASURED_PATTERN_NOT_LITERAL_WORD_TYPE';broad.to_parquet(output/'broad_prototypes.parquet',index=False);result.to_parquet(output/'word_type_hypotheses.parquet',index=False);result[result.operational_hypothesis].to_parquet(output/'operational_type_candidates.parquet',index=False)
 pd.DataFrame([{'center_id':u,'nearest_large_center_network_minutes':nearest.get(u),'within60minutes':nearest.get(u,np.inf)<=60,'within90minutes':nearest.get(u,np.inf)<=90,'within120minutes':nearest.get(u,np.inf)<=120,'within180minutes':nearest.get(u,np.inf)<=180} for u in probe]).to_parquet(output/'recreation_location_sensitivity.parquet',index=False)
 changed=[str(p) for p,h in watched.items() if m.sha(p)!=h]
 receipt={'status':'COMPUTED_LITERAL_TYPOLOGY_ADAPTER' if not changed else 'REJECT_SOURCE_CHANGED','input_sha256':{str(p.resolve().relative_to(m.REPO)):h for p,h in watched.items()},'model_output_manifest_sha256':m.sha(model_output/'output_manifest.json'),'parameters':{'small_center_max_population2021':50000,'large_city_min_population2021':100000,'near_large_center_max_minutes':90,'near_threshold_is_scenario_not_literal_word_number':True,'low_centrality_max':.5},'centrality_metric':config.get('hierarchy_strength_column','own_positive_mass'),'unknown_nonchernozem_geography_not_replaced_with_climate':True,'historical_nonchernozem_context_hypothesis_only':True,'type7_paired_exact_contemporary_geography_retained':True,'broad_patterns_count':int(types.operational_hypothesis.sum()),'literal_candidate_count':int(result.operational_hypothesis.sum()),'literal_candidates_by_word_type':{str(k):int(v) for k,v in result[result.operational_hypothesis].word_type.value_counts().items()},'indicator_complete_count_no_causal_proof':int(result.rule_status.eq('satisfied_observed_indicators').sum()),'near_large_threshold_sensitivity_counts':{str(t):int(sum(nearest.get(u,np.inf)<=t for u in probe)) for t in [60,90,120,180]},'literal_type5_candidate_counts_by_near_threshold':{str(k):v for k,v in type5_threshold_counts.items()},'near_large_threshold_sensitivity_population':'unique original broad-pattern center IDs; literal_type5 counts include hierarchy-level systems','physical_network_changed':False,'input_bytes_changed':changed,'files':{q.name:{'sha256':m.sha(q),'rows':len(pd.read_parquet(q))} for q in output.glob('*.parquet')}}
 receipt_temp=output/'receipt.json.tmp';receipt_temp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');receipt_temp.replace(output/'receipt.json');manifest_temp=output/'manifest.json.tmp';manifest_temp.write_text(json.dumps({'status':receipt['status'],'model_output_manifest_sha256':receipt['model_output_manifest_sha256'],'receipt_sha256':m.sha(output/'receipt.json'),'files':receipt['files'],'adapter_code_sha256':m.sha(Path(__file__)),'selected_classification':'literal eligibility canonical; broad prototypes separate'},ensure_ascii=False,indent=2)+'\n');manifest_temp.replace(output/'manifest.json');print({k:v for k,v in receipt.items() if k not in ['input_sha256','files']})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--model-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 for name in ['own-function-layer','own-function-review','geographic-layer','geographic-review','processing-layer','processing-review']:p.add_argument('--'+name,type=Path)
 a=p.parse_args();run(a.inputs,a.model_output,a.output,a.own_function_layer,a.own_function_review,a.geographic_layer,a.geographic_review,a.processing_layer,a.processing_review)
