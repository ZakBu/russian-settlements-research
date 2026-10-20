"""Explicit second-stage Word eligibility; frozen physical network remains unchanged.

Original measured-pattern hypotheses are retained. Qualitative Word terms use
published scenario parameters, not thresholds chosen from the desired labels.
"""
from pathlib import Path
import argparse,json,hashlib,copy
import pandas as pd
import numpy as np
import run_word_model as m

def encode(value):return json.dumps(value,ensure_ascii=False,allow_nan=False)
def run(inputs,model_output,output):
 output.mkdir(parents=True,exist_ok=True);config=json.loads(inputs.read_text());manifest=json.loads((model_output/'output_manifest.json').read_text());watched={Path(m.__file__).resolve():m.sha(Path(m.__file__)),m.travel_source(config).resolve():m.sha(m.travel_source(config)),inputs.resolve():m.sha(inputs),Path(__file__).resolve():m.sha(Path(__file__)),(model_output/'output_manifest.json').resolve():m.sha(model_output/'output_manifest.json')}
 if m.sha(inputs)!=manifest['configuration_sha256']:raise ValueError('Configuration differs from frozen physical model')
 marker=output/'receipt.json.tmp';marker.write_text(encode({'status':'RUNNING_CANONICAL_TYPOLOGY'})+'\n');marker.replace(output/'receipt.json')
 for filename in ['nodes.parquet','candidate_centers.parquet','own_mass_components.parquet','word_type_hypotheses.parquet','systems.parquet']:
  p=model_output/filename
  if m.sha(p)!=manifest['files'][filename]['sha256']:raise ValueError('Unfrozen model derivative '+str(p))
  watched[p.resolve()]=m.sha(p)
 nodes=pd.read_parquet(model_output/'nodes.parquet');centers=pd.read_parquet(model_output/'candidate_centers.parquet');mass=pd.read_parquet(model_output/'own_mass_components.parquet');types=pd.read_parquet(model_output/'word_type_hypotheses.parquet');systems=pd.read_parquet(model_output/'systems.parquet');types=types.merge(systems[['level','center_id','descriptive_centrality_posthoc_0_1']].rename(columns={'descriptive_centrality_posthoc_0_1':'diagnostic_original_final_zone_posthoc_centrality'}),on=['level','center_id'],validate='many_to_one');index=nodes.set_index('id');ci=centers.set_index('id')[config.get('hierarchy_strength_column','own_positive_mass')]
 # Only potentially admissible recreation patterns need additional OD queries.
 probe=types[types.word_type.eq(5)&types.operational_hypothesis].center_id.unique().tolist();nearest={};route_sources={};accepted_origins=set()
 large=set(nodes.loc[(nodes.type.eq('город')&nodes.population_2021.ge(100000))|nodes.axis_kind.eq('external_service_provider'),'id'])&set(centers.id)
 if probe:
  route_manifest=json.loads(m.travel_source(config).read_text());om=m.travel_source(config).parent/route_manifest['origin_mapping']['path'];accepted_origins=set(pd.read_parquet(om).id.replace(config.get('route_id_aliases',{})))
  cfg=copy.deepcopy(config);cfg['origin_id_filter']=probe;travel,_=m.load_travel(cfg,nodes,centers,mass[['id']]);route_sources=travel.attrs.pop('additional_source_sha256',{});watched.update(route_sources)
  q=travel[travel.destination_id.isin(large)&travel.origin_id.ne(travel.destination_id)].sort_values(['origin_id','travel_minutes','destination_id']).drop_duplicates('origin_id');nearest=q.set_index('origin_id').travel_minutes.to_dict()
 output_rows=[];type5_threshold_counts={t:0 for t in [60,90,120,180]}
 for row in types.to_dict('records'):
  uid=row['center_id'];typ=int(row['word_type']);source=index.loc[uid];full=json.loads(row['required_criteria_truth_json']);core=json.loads(row['operational_core_truth_json']);raw_core=copy.deepcopy(core);added={}
  urban_type=source.get('type');pop=source.get('population_2021',np.nan);small=None if pd.isna(pop) else bool(pop<=50000)
  city=None if pd.isna(urban_type) else urban_type=='город';urban=None if pd.isna(urban_type) else urban_type in ['город','пгт','посёлок городского типа','рабочий посёлок']
  if typ in [2,3,5,7,8,9]:added['small_urban_center']=m.tri_all(urban,small)
  if typ==5:
   minutes=nearest.get(uid,np.nan);added['near_large_center_within90_modeled_minutes']=bool(minutes<=90.) if np.isfinite(minutes) else (False if uid in probe and uid in accepted_origins else None)
   row['nearest_large_center_network_minutes']=float(minutes) if np.isfinite(minutes) else None
  if typ==7:
   # No subject-name inference or climate substitution for the Word geographic zone.
   added['nonchernozem_geographic_zone']=m.tri(source.get('nonchernozem_geographic_evidence',None))
  if typ in [4,7,8]:
   value=ci.get(uid,np.nan);low=None if pd.isna(value) else bool(value<=.5)
   if 'low_ci_le0_5' in core:core['low_ci_le0_5']=low
   if typ==8:full['low_centrality']=low
   elif typ in [4,7]:full['low_mass_and_centrality' if typ==7 else 'low_or_moderate_mass_centrality']=m.tri_all(core.get('low_mass_expmeanZ_le1'),low)
  full.update(added);core.update(added)
  if typ==5:
   for threshold in type5_threshold_counts:
    variation=core.copy();variation['near_large_center_within90_modeled_minutes']=bool(nearest.get(uid,np.inf)<=threshold);type5_threshold_counts[threshold]+=int(m.tri_all(*variation.values()) is True and row['population_pair_complete'])
  state=m.tri_all(*full.values());eligible=m.tri_all(*core.values())
  row['broad_measured_pattern_operational_hypothesis']=row['operational_hypothesis'];row['broad_measured_pattern_core_truth_json']=encode(raw_core);row['literal_eligibility_added_truth_json']=encode(added)
  row['descriptive_partial_candidate_not_proven_type']=bool(sum(v is True for v in full.values())>=2 and not any(v is False for v in full.values()) and row['population_pair_complete']);row['required_criteria_truth_json']=encode(full);row['operational_core_truth_json']=encode(core);row['unknown_required_criteria_json']=encode([k for k,v in full.items() if v is None]);row['contradicted_required_criteria_json']=encode([k for k,v in full.items() if v is False]);row['n_required_criteria']=len(full);row['n_observed_supporting_criteria']=sum(v is True for v in full.values())
  row['operational_hypothesis']=bool(eligible is True and row['population_pair_complete']);row['operational_status']='HYPOTHESIS_WITH_LITERAL_ELIGIBILITY' if row['operational_hypothesis'] else 'NOT_ESTABLISHED_LITERAL_ELIGIBILITY';row['rule_status']='satisfied_observed_indicators' if state is True and row['population_pair_complete'] and row['population_pair_exact_primary_supported'] else ('not_satisfied_observed_indicators' if state is False else 'unknown_missing_required_indicators');row['classification_centrality_column']=config.get('hierarchy_strength_column','own_positive_mass');row['full_causal_validation_claim']=False;output_rows.append(row)
 result=pd.DataFrame(output_rows);broad=types[types.operational_hypothesis].copy();broad['prototype_status']='BROAD_MEASURED_PATTERN_NOT_LITERAL_WORD_TYPE';broad.to_parquet(output/'broad_prototypes.parquet',index=False);result.to_parquet(output/'word_type_hypotheses.parquet',index=False);result[result.operational_hypothesis].to_parquet(output/'operational_type_candidates.parquet',index=False)
 pd.DataFrame([{'center_id':u,'nearest_large_center_network_minutes':nearest.get(u),'within60minutes':nearest.get(u,np.inf)<=60,'within90minutes':nearest.get(u,np.inf)<=90,'within120minutes':nearest.get(u,np.inf)<=120,'within180minutes':nearest.get(u,np.inf)<=180} for u in probe]).to_parquet(output/'recreation_location_sensitivity.parquet',index=False)
 changed=[str(p) for p,h in watched.items() if m.sha(p)!=h]
 receipt={'status':'COMPUTED_LITERAL_TYPOLOGY_ADAPTER' if not changed else 'REJECT_SOURCE_CHANGED','input_sha256':{str(p.resolve().relative_to(m.REPO)):h for p,h in watched.items()},'model_output_manifest_sha256':m.sha(model_output/'output_manifest.json'),'parameters':{'small_center_max_population2021':50000,'large_city_min_population2021':100000,'near_large_center_max_minutes':90,'near_threshold_is_scenario_not_literal_word_number':True,'low_centrality_max':.5},'centrality_metric':config.get('hierarchy_strength_column','own_positive_mass'),'unknown_nonchernozem_geography_not_replaced_with_climate':True,'broad_patterns_count':int(types.operational_hypothesis.sum()),'literal_candidate_count':int(result.operational_hypothesis.sum()),'literal_candidates_by_word_type':{str(k):int(v) for k,v in result[result.operational_hypothesis].word_type.value_counts().items()},'strict_proven_count':int(result.rule_status.eq('satisfied_observed_indicators').sum()),'near_large_threshold_sensitivity_counts':{str(t):int(sum(nearest.get(u,np.inf)<=t for u in probe)) for t in [60,90,120,180]},'literal_type5_candidate_counts_by_near_threshold':{str(k):v for k,v in type5_threshold_counts.items()},'near_large_threshold_sensitivity_population':'unique original broad-pattern center IDs; literal_type5 counts include hierarchy-level systems','physical_network_changed':False,'input_bytes_changed':changed,'files':{q.name:{'sha256':m.sha(q),'rows':len(pd.read_parquet(q))} for q in output.glob('*.parquet')}}
 receipt_temp=output/'receipt.json.tmp';receipt_temp.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');receipt_temp.replace(output/'receipt.json');manifest_temp=output/'manifest.json.tmp';manifest_temp.write_text(json.dumps({'status':receipt['status'],'model_output_manifest_sha256':receipt['model_output_manifest_sha256'],'receipt_sha256':m.sha(output/'receipt.json'),'files':receipt['files'],'adapter_code_sha256':m.sha(Path(__file__)),'selected_classification':'literal eligibility canonical; broad prototypes separate'},ensure_ascii=False,indent=2)+'\n');manifest_temp.replace(output/'manifest.json');print({k:v for k,v in receipt.items() if k not in ['input_sha256','files']})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--model-output',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.inputs,a.model_output,a.output)
