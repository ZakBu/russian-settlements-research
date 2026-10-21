#!/usr/bin/env python3
"""Preregister and bind cycle05 source contracts without changing frozen inputs.
Run before provisional or final model output. Final configs refer to future cycle05 Ci;
there is no reuse of previous memberships, ranks, fitted mass or farmland sidecars.
"""
from pathlib import Path
import argparse,copy,json,hashlib,datetime
import pandas as pd,pyarrow.parquet as pq
H=Path(__file__).resolve().parent;ROOT=H.parent;REPO=ROOT.parents[1]
VARIANTS={'baseline':{},'narrow_general_health':{'healthcare':'general_only'},'broad_retail_plus_ATM':{'commerce':'broad_retail_ATM'},'unknown_role_upper':{'rural_volume':'unknown_as_rural_upperbound'},'P0_probability':{'minimum_choice_probability':0.0},'inclusive_candidates':{'center_eligibility':'broad_catalogue_sensitivity'}}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.resolve().relative_to(REPO))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def layer(p,prefix='',retain=None):
 x=dict(path=rel(p),key='id',prefix=prefix,optional=False)
 if retain is not None:x['retain_prefixes']=retain
 return x

def run(args):
 basepath=ROOT/'model/model_inputs_word_ci_2021.json';old=json.loads(basepath.read_text());out=args.output_directory.resolve();out.mkdir(parents=True,exist_ok=True)
 if any((out/('provisional_'+v)/'word_ci_center_features.parquet').exists() for v in VARIANTS):raise FileExistsError('Cannot rewrite preregistered configs after cycle05 provisional outputs exist')
 axis=ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet';role=ROOT/'data/source_controls_cycle05/statistical_role_primary/source_settlement_statistical_role_primary2021_v3.parquet';ctx=ROOT/'data/source_controls_cycle05/parent_repaired_strict2021_settlement_context.parquet';route=ROOT/'transport/cycle05_axis_extension';relinked=H/'relinked_v3';admin=ROOT/'administration2021_cycle05/administration2021_settlement_features.parquet';climate=ROOT/'context/cycle05_federal335';thematic=args.thematic_layer.resolve()
 # Independently recreate the source-region threshold; never write frozen word_ci_regional_land_features.
 land_source=ROOT/'land2021_recovery/settlement_regional_farmland2021_context.parquet';land=pd.read_parquet(land_source);ax=pd.read_parquet(axis,columns=['id','region']);cols=[c for c in land if c.startswith('region_farmland2021_')];lf=ax[['id']].merge(land[['id']+cols],on='id',how='left',validate='one_to_one');valid=lf.region_farmland2021_source_subject_code.notna()&lf.region_farmland2021_sown_share.notna();g=lf.loc[valid].groupby('region_farmland2021_source_subject_code').region_farmland2021_sown_share
 if g.nunique().gt(1).any():raise ValueError('Multiple source ratios for same region')
 threshold=float(g.first().quantile(.75,interpolation='linear'));lf['regional_high_sown_share2021_evidence']=pd.Series(pd.NA,index=lf.index,dtype='boolean');lf.loc[valid,'regional_high_sown_share2021_evidence']=lf.loc[valid,'region_farmland2021_sown_share'].ge(threshold);land_path=out/'regional_land_features_cycle05.parquet';lf.to_parquet(land_path,index=False)
 config=copy.deepcopy(old);config['axis']=rel(axis);config['layers']=[layer(REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet','legacy_'),layer(relinked/'education/settlement_features_full_axis.parquet','school_',['education_']),layer(relinked/'medical/settlement_features_full_axis.parquet','medical_',['medical_']),layer(relinked/'commerce/settlement_features_full_axis.parquet','services_',['services_']),layer(ctx,'',['context_']),layer(climate/'climate_settlement_features.parquet','',['climate_']),layer(climate/'soil_settlement_features.parquet','',['soil_']),layer(role,'',['source2021_','primary202101_']),layer(admin,'',['admin2021_']),layer(route/'settlement_road_snap.parquet','road_')]
 config['layers'][-1]['normalize_route_aliases']=True
 # Retain the independently reviewed primary2010 values and industrial case documents.
 for l in old['layers']:
  if l.get('prefix') in {'recovered2010_','industrialcase_'}:config['layers'].append(copy.deepcopy(l))
 config['layers'].append(layer(ROOT/'geographic_context_cycle05/expanded_primary_parent2021_agricultural_context.parquet','agri2021_',['sown_share_of_census_farmland2021_usable','actually_used_share_of_census_farmland2021_usable','context_agri_sameyear_primary_parent_matched','source_municipality_oktmo8','observation_year','farmland_reference_date','crop_period','producer_universe','do_not_sum_repeated_','context_is_not_']))
 config['layers'].append(layer(land_path,'land2021_',['region_farmland2021_','regional_high_']))
 config.pop('independent_district_seats',None);config.pop('reuse_function_memberships_from',None);config.pop('rank_provisional_receipt',None);config.pop('hierarchy_strength_column',None)
 anchor_receipt=ROOT/'reviews/cycle05/external_metropolitan_accessibility_anchor_preregistration.json'
 config['external_large_city_anchors']=[{**w,'source_receipt':rel(anchor_receipt),'source_receipt_sha256':sha(anchor_receipt)} for w in json.loads(anchor_receipt.read_text())['witnesses']]
 config['provenance_sidecars']=[rel(anchor_receipt)];config['travel_manifest']=rel(route/'candidate_travel_times_manifest.json');config['travel_edges']=rel(route/'candidate_travel_times_manifest.json');config['target_run_id']='sgrt_word_completion_20261021_cycle05';config['grid_basis']='new_full_axis2021_two_pass_word_Ci_no_reused_memberships';config['rank_index']={'column':'own_positive_mass','transform':'log','uses_modeled_catchment':False};config['rank_feature_columns']=[]
 config['settlement_role_policy']={'rural_column':'source2021_rural_role','dated_column':'source2021_role_has_dated_source','subtype_column':'source2021_effective_settlement_type','rural_volume':'known_rural_lowerbound','unknown_role_population_is_not_zero':True,'statistical_category_separate_from_named_subtype':True}
 config['center_eligibility_2021_admin_columns']=['admin2021_upper_municipal_center_evidence','admin2021_district_center_evidence']
 config['physical_features']={'education':['school_education_osm2021_school_baseline_count'],'healthcare':['medical_medical_osm_baseline_general_and_dental_clinical_sites_count'],'hospital':['medical_medical_osm_baseline_explicit_hospital_sites_count'],'trade':['services_services_osm2021_large_retail_baseline_count'],'finance':['services_services_osm2021_bank_baseline_count'],'administration':['services_services_osm2021_administration_baseline_count'],'higher_education':['school_education_osm2021_college_baseline_count','school_education_osm2021_university_baseline_count'],'preschool':['school_education_osm2021_preschool_baseline_count']}
 config['derived_features']=[]
 config['components']=[c for c in config['components'] if c['name'] not in {'physical_trade','physical_finance','physical_education','physical_healthcare'}]
 services=[dict(name='physical_'+n,block='service',physical=n,transform='log1p',year=2021,unit='dated2021_positive_source_sites_not_capacity; absent_catalog_records_unknown') for n in ['education','healthcare','trade','finance','administration']]
 config['components']+=services
 for c in config['components']:
  if c['name']=='housing_construction':c['columns']=['context_housing_completed_residential_m2_per_capita_parent_strict2021']
  elif c['name']=='baseline_natural_increase':c['columns']=['context_natural_increase_per1000_parent_strict2021']
  elif c['name']=='baseline_net_migration':c['columns']=['context_migration_increase_per1000_parent_strict2021']
 config['required_input_columns']=[v for v in old['required_input_columns'] if not v.startswith('wordci_')]+['source2021_rural_role','source2021_role_has_dated_source','source2021_settlement_subtype']
 config['mass_domains']={'demographic':.2,'service':.2,'economy':.2,'housing':.2,'demographic_context_2021':.2};config['mass_missing_domain_policy']='available_domain_mean_with_observed_domain_count; never_impute_missing_zero; all_five_domains_equal_when_all_observed';config['mass_own_catchment_calibration']=False
 config['rural_context_numeric_columns']=['land2021_region_farmland2021_sown_share','agri2021_sown_share_of_census_farmland2021_usable','agri2021_actually_used_share_of_census_farmland2021_usable'];config['rural_context_boolean_columns']=['land2021_regional_high_sown_share2021_evidence'];config['regional_sown_share_high_threshold']=threshold
 configs=[]
 for name,changes in VARIANTS.items():
  c=copy.deepcopy(config);c['target_run_id']+='__'+name;c['cycle05_variant']=name
  if changes.get('healthcare')=='general_only':c['physical_features']['healthcare']=['medical_medical_osm_baseline_healthcare_sites_count']
  if changes.get('commerce'):
   c['derived_features']=[dict(name='cycle05_broad_trade',columns=['services_services_osm2021_large_retail_baseline_count','services_services_osm2021_other_retail_baseline_count','services_services_osm2021_market_baseline_count'],operation='sum_disjoint'),dict(name='cycle05_bank_plus_ATM',columns=['services_services_osm2021_bank_baseline_count','services_services_osm2021_atm_baseline_count'],operation='sum_disjoint')];c['physical_features']['trade']=['cycle05_broad_trade'];c['physical_features']['finance']=['cycle05_bank_plus_ATM']
  if 'rural_volume' in changes:c['settlement_role_policy']['rural_volume']=changes['rural_volume']
  if 'minimum_choice_probability' in changes:c['model']['minimum_choice_probability']=changes['minimum_choice_probability']
  if 'center_eligibility' in changes:c['center_eligibility']=changes['center_eligibility']
  c['center_eligibility_2021_features']=copy.deepcopy(c['physical_features']);provisional=out/('config_'+name+'_provisional.json');dump(provisional,c)
  final=copy.deepcopy(c);ci_dir=out/('provisional_'+name);ci_path=ci_dir/'word_ci_center_features.parquet';final['layers'].append(layer(ci_path,'wordci_',['word_','provisional_','normalized_','own_mass_','historical_','rural_unit_','true_person_','person_']));final['layers'].append(layer(thematic,'',['recreation_','dacha_','osm_accommodation_','osm_allotment_','ethnic_','share_declared_','commuting_','industrial_','resource_','mapped_resource_','historical_monotown_','thematic_','osm_context_']));final['layers'][-1]['retain_evidence_suffix']=True
  col='wordci_word_centrality_observed2021_frame_0_1';final['rank_feature_columns']=[col];final['hierarchy_strength_column']=col;final['rank_index']={'column':col,'transform':'identity','uses_modeled_catchment':True,'missing_policy':'stop_if_unknown_current2021_component','formula':'0.5*minmax(log(fixedOwnMi))+0.5*minmax(log1p(provisional_statistical_rural2021_selected_bound))','mass_weight':.5,'zone_weight':.5,'provisional_passes':1,'own_mass_refit':False,'selected_rural_bound':c['settlement_role_policy']['rural_volume'],'role_unknown_population_reported_separately':True,'historical_unmatched_population_imputed_zero':False};final['required_input_columns']+=['wordci_own_positive_mass'];final['rank_provisional_receipt']=rel(ci_dir/'receipt.json');final['provenance_sidecars']=c['provenance_sidecars']+[rel(ci_dir/'receipt.json'),rel(Path(__file__)),rel(H/'prepare_word_ci_cycle05.py')];fp=out/('config_'+name+'_final.json');dump(fp,final);configs.append(dict(variant=name,changes=changes,provisional=rel(provisional),final=rel(fp),future_ci=rel(ci_path),final_thematic_layer_pending_freeze=rel(thematic)))
 # Bind only files currently present. Future Ci outputs explicitly have no fabricated hashes.
 inputs=[REPO/l['path'] for l in config['layers']]+[axis,ROOT/'axis/external_context_centers.parquet',route/'candidate_travel_times_manifest.json',basepath]
 missing=[str(p) for p in inputs if not p.exists()]
 if missing:raise FileNotFoundError('Required provisional sources missing: '+repr(missing))
 schemas={str(p.relative_to(REPO)):pq.ParquetFile(p).schema_arrow.names for p in inputs if p.suffix=='.parquet'}
 for l in config['layers']:
  p=REPO/l['path'];keys=pd.read_parquet(p,columns=[l['key']])[l['key']]
  if keys.isna().any() or keys.duplicated().any():raise ValueError('Layer nonunique/null key '+str(p))
 registration=dict(status='PREREGISTERED_BEFORE_NEW_MODEL_OUTPUTS',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),variants=configs,reference=dict(axis_rows=len(ax),axis_sha256=sha(axis),role_v3_sha256=sha(role),own_mass_domains=config['mass_domains'],missing_domain_policy=config['mass_missing_domain_policy'],service_components=['school','general_clinical_plus_dental','large_retail_only','bank_without_ATM','physical_administration_OSM2021'],physical_admin_vs_official_seat_role_separate=True,no_old_memberships_or_ranks_reused=True,no_catchment_calibration=True,zero_initial_population_percentage_undefined_unchanged=True,P0_means_minimum_choice_probability_zero=True,inclusive_means_broad_catalogue_candidate_eligibility=True),provisional_input_sha256={rel(p):sha(p) for p in dict.fromkeys(inputs)},source_schema=schemas,final_thematic_snapshot_sha256_at_registration=sha(thematic) if thematic.exists() else None,final_thematic_requires_frozen_receipt_before_execution=True,regional_land_threshold=dict(distinct_regions=len(g),q75=threshold,source_sha256=sha(land_source),output_sha256=sha(land_path),regional_context_not_own_local_agriculture=True),code_sha256=sha(Path(__file__)))
 dump(out/'cycle05_preregistration.json',registration);print(json.dumps(dict(status=registration['status'],variants=len(configs),provisional_ready=True,axis_rows=len(ax),thematic_pending_freeze=True),indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output-directory',type=Path,default=H);p.add_argument('--thematic-layer',type=Path,default=H/'thematic2021/settlement_thematic_features_2021.parquet');run(p.parse_args())
