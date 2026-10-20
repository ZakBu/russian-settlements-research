"""Bind the audited dated-frame Ci and contemporary regional farmland observations."""
from pathlib import Path
import argparse,json,hashlib
import pandas as pd
import numpy as np
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(base_config,ci_directory,output_config):
 config=json.loads(base_config.read_text());source=REPO/'research/sgrt_word_completion_20261021/land2021_recovery/settlement_regional_farmland2021_context.parquet';land=pd.read_parquet(source)
 valid=land.region_farmland2021_source_subject_code.notna()&land.region_farmland2021_sown_share.notna()
 grouped=land.loc[valid].groupby('region_farmland2021_source_subject_code').region_farmland2021_sown_share
 if grouped.nunique().gt(1).any():raise ValueError('Ambiguous regional land source ratio')
 values=grouped.first();threshold=float(values.quantile(.75,interpolation='linear'))
 land['regional_high_sown_share2021_evidence']=pd.Series(pd.NA,index=land.index,dtype='boolean');land.loc[valid,'regional_high_sown_share2021_evidence']=land.loc[valid,'region_farmland2021_sown_share'].ge(threshold)
 lp=HERE/'word_ci_regional_land_features.parquet';land.to_parquet(lp,index=False)
 config['layers']+=[{'path':str((ci_directory/'word_ci_center_features.parquet').resolve().relative_to(REPO)),'key':'id','prefix':'wordci_','optional':False,'retain_prefixes':['word_','provisional_','normalized_','own_mass_','historical_','rural_unit_','true_person_','person_']},{'path':str(lp.relative_to(REPO)),'key':'id','prefix':'land2021_','optional':False,'retain_prefixes':['region_farmland2021_','regional_high_']}]
 config['required_input_columns']+=['wordci_own_positive_mass'];config['rank_feature_columns']=['wordci_word_centrality_observed2021_frame_0_1'];config['rank_index']={'column':'wordci_word_centrality_observed2021_frame_0_1','transform':'identity','uses_modeled_catchment':True,'missing_policy':'stop_if_unknown_current2021_component','formula':'0.5 minmax(log fixedMi)+0.5 minmax(log1p provisional ruralpopulation in observednative2021censusframe)','mass_weight':.5,'zone_weight':.5,'provisional_passes':1,'own_mass_refit':False,'provisional_core_protection':True,'historical_unmatched_population_imputed_zero':False,'provisional_receipt_sha256':sha(ci_directory/'receipt.json')}
 config['rural_context_numeric_columns']=['land2021_region_farmland2021_sown_share'];config['rural_context_boolean_columns']=['land2021_regional_high_sown_share2021_evidence'];config['regional_sown_share_high_threshold']=threshold;config['operational_agrarian_requires_sown_share2021']=True
 config['rank_provisional_receipt']=str((ci_directory/'receipt.json').resolve().relative_to(REPO));config['grid_basis']='word_ci_two_pass_observed_native2021_frame';config['reuse_function_memberships_from']='research/sgrt_word_completion_20261021/model/output_2021_restricted_baseline';config['target_run_id']='sgrt_word_completion_20261021_cycle03_word_ci'
 config['hierarchy_strength_column']='wordci_word_centrality_observed2021_frame_0_1'
 config['provenance_sidecars']=[str(q.resolve().relative_to(REPO)) for q in [ci_directory/'receipt.json',HERE/'prepare_word_ci.py',HERE/'prepare_word_ci_config.py',HERE/'word_ci_regional_land_receipt.json']]
 output_config.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
 (HERE/'word_ci_regional_land_receipt.json').write_text(json.dumps({'status':'BOUND_PRIMARY2021_REGIONAL_CONTEXT_NOT_OWN_SETTLEMENT_AGRICULTURE','source_sha256':sha(source),'output_sha256':sha(lp),'distinct_regions_with_ratio':len(values),'high_ratio_threshold_q75_distinct_regions':threshold,'threshold_method':'linear75thpercentile acrossonevalueperregion,notduplicatedNProws','do_not_sum_repeated_hectares':True,'source_reference':'Rosreestr2022-01-01 stock forend2021 / Rosstat harvest2021sownarea','classification':'ruralP2021weightedregionalratio >=fixedQ75,contextonly'},ensure_ascii=False,indent=2)+'\n')
 print('WordCi config bound; distinctregions',len(values),'Q75',threshold)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base-config',type=Path,default=HERE/'model_inputs_2021_restricted.json');p.add_argument('--ci-directory',type=Path,default=HERE/'word_ci_provisional_observed2021');p.add_argument('--output-config',type=Path,default=HERE/'model_inputs_word_ci_2021.json');a=p.parse_args();run(a.base_config,a.ci_directory,a.output_config)
