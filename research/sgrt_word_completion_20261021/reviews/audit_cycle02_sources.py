#!/usr/bin/env python3
"""Independent second-cycle source audit. Does not import source builders or model functions."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
RAW=Path('/workspace/scratch/sgrt_context_completion')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def run():
 files=['axis/full_settlement_axis.parquet','education/education_objects.parquet','education/education_objects_2021.parquet','education/settlement_features_full_axis.parquet','education/settlement_features_2021_full_axis.parquet','medical/current_20261019/osm_medical_inventory.parquet','medical/current_20261019/settlement_features.parquet','medical/history_20210101/osm_medical_inventory.parquet','medical/history_20210101/settlement_features.parquet','medical/udmurt_official_2025/physical_fap_inventory.parquet','medical/udmurt_official_2025/settlement_features.parquet','context/municipal_selected_source_observations.parquet','context/municipal_annual_context.parquet','context/municipal_annual_wide.parquet','context/municipal_settlement_features.parquet','context/climate_settlement_features.parquet','typology/settlement_features.parquet']
 files += ['calibration/services_2021_objects.parquet','calibration/services_2021_settlement_features.parquet']
 before={f:sha(ROOT/f) for f in files if (ROOT/f).exists()};checks=[];blockers=[];metrics={}
 def check(name,condition,scope='implementation'):
  checks.append({'check':name,'pass':bool(condition),'scope':scope})
 axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet');ids=axis.id;idset=set(ids);located=axis.lat.notna()&axis.lon.notna()
 check('axis_unique_nonnull_ids',ids.is_unique and ids.notna().all());check('located_coordinates_valid',axis.loc[located,'lat'].between(-90,90).all()&axis.loc[located,'lon'].between(-180,180).all())
 old=pd.read_parquet(ROOT.parent/'sgrt_national_integration_20261019/core/feature_master.parquet');oldaxis=axis.set_index('id').reindex(old.id)
 for year in [2002,2010,2021]:check(f'legacy_population_{year}_preserved',np.allclose(old[f'population_{year}'],oldaxis[f'population_{year}'],equal_nan=True))
 metadata=['population_value_quality_2002','population_value_quality_2010','population_value_quality_2021','district_raw_2002','district_raw_2010','district_raw_2021','oktmo_2002','oktmo_2010','oktmo_2021','okato_2002','okato_2010','okato_2021']
 for col in metadata:check('legacy_metadata_'+col+'_preserved',np.array_equal(old[col].astype('string').fillna('<NULL>').to_numpy(),oldaxis[col].astype('string').fillna('<NULL>').to_numpy()),'data')
 metrics['axis']={'rows':len(axis),'located':int(located.sum()),'unlocated':int((~located).sum()),'complete_three_census':int(axis[['population_2002','population_2010','population_2021']].notna().all(axis=1).sum())}
 allfeature=['education/settlement_features_full_axis.parquet','education/settlement_features_2021_full_axis.parquet','medical/current_20261019/settlement_features.parquet','medical/history_20210101/settlement_features.parquet','medical/udmurt_official_2025/settlement_features.parquet','context/municipal_settlement_features.parquet','context/climate_settlement_features.parquet','typology/settlement_features.parquet']
 for file in allfeature:
  if not (ROOT/file).exists():checks.append({'check':file+'_exists','pass':False,'scope':'data'});continue
  a=pd.read_parquet(ROOT/file,columns=['id']);check(file+'_axis_equal',a.id.equals(ids));check(file+'_id_unique',a.id.is_unique)
 school={}
 for label,objfile,featurefile in [('current','education/education_objects.parquet','education/settlement_features_full_axis.parquet'),('2021','education/education_objects_2021.parquet','education/settlement_features_2021_full_axis.parquet')]:
  obj=pd.read_parquet(ROOT/objfile);features=pd.read_parquet(ROOT/featurefile).set_index('id');check(label+'_school_object_ids_unique',~obj.duplicated(['osm_type','osm_id']).any())
  for key in ['baseline_uid','candidate_uid']:check(label+'_school_'+key+'_valid',set(obj[key].dropna())<=idset)
  check(label+'_school_baseline_candidate_disjoint',not (obj.baseline_uid.notna()&obj.candidate_uid.notna()).any())
  for group in sorted(obj.education_group.unique()):
   for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
    sample=obj[obj.education_group.eq(group)&obj[key].notna()].drop_duplicates([key,'canonical_site_id']);count=sample.groupby(key).size().reindex(ids,fill_value=0)
    namespace='education_osm2021' if label=='2021' else 'education_osm'
    col=f'{namespace}_{group}_{mode}_count'
    if col in features:check(label+'_'+col+'_all_recomputed',np.array_equal(count.to_numpy(),features.reindex(ids)[col].to_numpy()))
  actual=obj[obj.education_group.eq('school')];strict=actual.baseline_uid.dropna();candidate=actual.candidate_uid.dropna()
  school[label]={'source_school_rows':len(actual),'strict_settlements':strict.nunique(),'candidate_settlements':candidate.nunique(),'union_settlements':pd.concat([strict,candidate]).nunique(),'source_numeric_capacity_rows':int(pd.to_numeric(actual.get('source_capacity',pd.Series(index=actual.index,dtype=float)),errors='coerce').notna().sum()),'snapshot':sorted(obj.source_snapshot.dropna().astype(str).unique())}
  for col in [x for x in features if x.endswith('_observed_presence')]:check(label+'_'+col+'_unknown_not_false',not features[col].eq(False).fillna(False).any())
 metrics['school']=school
 health={}
 for label in ['current_20261019','history_20210101']:
  obj=pd.read_parquet(ROOT/f'medical/{label}/osm_medical_inventory.parquet');features=pd.read_parquet(ROOT/f'medical/{label}/settlement_features.parquet').set_index('id');check(label+'_medical_object_ids_unique',obj.object_id.is_unique)
  check(label+'_medical_baseline_conditional_disjoint',not (obj.baseline_uid.notna()&obj.conditional_uid.notna()).any())
  for key in ['baseline_uid','conditional_uid','coordinate_candidate_uid']:check(label+'_medical_'+key+'_valid',set(obj[key].dropna())<=idset)
  for prefix,key in [('baseline','baseline_uid'),('conditional_additional','conditional_uid'),('coordinate_candidate','coordinate_candidate_uid')]:
   selected=obj[~obj.inactive_source_assertion&obj[key].notna()]
   for kind in ['all','healthcare']:
    a=selected if kind=='all' else selected[selected.broad_function.eq('healthcare')];count=a.groupby(key).size().reindex(ids,fill_value=0);col=f'medical_osm_{prefix}_{kind}_sites_count';check(label+'_'+col+'_all_recomputed',np.array_equal(count.to_numpy(),features.reindex(ids)[col].to_numpy()))
  health[label]={'all_source_assertions':len(obj),'healthcare_source_assertions':int(obj.broad_function.eq('healthcare').sum()),'pharmacy_assertions':int(obj.broad_function.eq('pharmacy').sum()),'capacity_source_rows':int(obj.capacity_known.sum()),'inactive_source_rows':int(obj.inactive_source_assertion.sum()),'baseline_healthcare_settlements':int(features.medical_osm_baseline_healthcare_sites_count.gt(0).sum()),'candidate_healthcare_settlements':int(features.medical_osm_coordinate_candidate_healthcare_sites_count.gt(0).sum())}
 metrics['medical']=health
 # Official selected catalogue corroborates a presence assertion, not operation/capacity or synchronized object identity.
 official=pd.read_parquet(ROOT/'medical/udmurt_official_2025/physical_fap_inventory.parquet');official_ids=set(official.baseline_uid.dropna());med=pd.read_parquet(ROOT/'medical/current_20261019/settlement_features.parquet').set_index('id').reindex(sorted(official_ids))
 metrics['official_udmurt_overlap']={'official_rows':len(official),'linked_source_settlements':len(official_ids),'unresolved_rows':int(official.baseline_uid.isna().sum()),'strict_named_fap_overlap':int(med.medical_osm_baseline_fap_name_assertion_count.gt(0).sum()),'coordinate_named_fap_overlap':int(med.medical_osm_coordinate_candidate_fap_name_assertion_count.gt(0).sum()),'coordinate_any_healthcare_overlap':int(med.medical_osm_coordinate_candidate_healthcare_sites_count.gt(0).sum()),'not_national_recall_or_same_date_census':True}
 check('official_fap_link_ids_valid',official_ids<=idset)
 blockers.append({'gate':'W06','issue':'OSM physical assertions are neither national functioning service census nor verified capacity; selected officialFAP inventory sharply disagrees even with permissive coordinate evidence','repair':'Use official sourcecontrols and independently review rural linkage; retain address-confirmed vs coordinate sensitivity; validate source recall separately from gravity assignments'})
 raw=pd.read_parquet(ROOT/'context/municipal_selected_source_observations.parquet');agg=pd.read_parquet(ROOT/'context/municipal_annual_context.parquet');wide=pd.read_parquet(ROOT/'context/municipal_annual_wide.parquet');feat=pd.read_parquet(ROOT/'context/municipal_settlement_features.parquet')
 check('municipal_conflicting_values_not_selected',agg.loc[agg.conflicting_values,'value'].isna().all())
 g=raw.groupby(['municipality_code','year','metric'],dropna=False).agg(nraw=('oktmo','nunique'),nvalue=('usable_value','nunique'),nunit=('indicator_unit','nunique'),nperiod=('indicator_period','nunique')).reset_index();a=agg.merge(g,on=['municipality_code','year','metric'],validate='one_to_one')
 accepted_multi=a[(a.nraw>1)&a.value.notna()];check('municipal_multiple_raw_geographies_not_selected_without_equivalence',len(accepted_multi)==0,'data')
 if len(accepted_multi):blockers.append({'gate':'W04/W08/W11','issue':f'{len(accepted_multi)} groups collapse different raw municipal codes to one usable equal value','repair':'Hold ambiguous_rawcode groups irrespective of equal numbers until dated territorial equivalence is proved; preserve raw observations'})
 check('municipal_no_mixed_unit_or_period_accepted',not ((a.nunit.gt(1)|a.nperiod.gt(1))&a.value.notna()).any())
 year0=wide[wide.year.eq(2010)];reported_col='natural_increase_reported' if 'natural_increase_reported' in year0 else 'natural_increase'
 published=year0[year0.births.notna()&year0.deaths.notna()&year0[reported_col].notna()];mismatch=published[(published.births-published.deaths-published[reported_col]).abs()>1e-6]
 if 'natural_increase_derived_from_births_minus_deaths' in wide:
  derived=wide[wide.natural_increase_derived_from_births_minus_deaths.fillna(False)];check('derived_natural_equals_births_minus_deaths',np.allclose(derived.natural_increase,derived.births-derived.deaths,equal_nan=True));check('conflicting_reported_natural_retained_in_separate_column',len(mismatch)==0 or mismatch.natural_increase_source_balance_mismatch.fillna(False).all())
  denom_ok=wide.municipal_population_denominator_raw_code_comparable.fillna(False);check('municipal_denominator_absent_when_raw_code_different',wide.loc[~denom_ok,'municipal_population_annual_mean_endpoints'].isna().all())
 if len(mismatch):blockers.append({'gate':'W04/W11','issue':f'{len(mismatch)} published2010natural/birth/death balances disagree','repair':'Keep raw reported value; flag source discrepancy; independently compute derivedbalanced variant only on same raw geography/year/unit, with sensitivity'})
 migration2010=feat.context_migration_increase_per1000_2010.notna().sum();metrics['municipal']={'source_rows':len(raw),'aggregate_rows':len(agg),'numeric_conflicting_groups':int(agg.conflicting_values.sum()),'multiple_raw_codes_with_usable_value':len(accepted_multi),'migration2010_nonnull':int(migration2010),'migration2011_nonnull':int(feat.context_migration_increase_per1000_2011.notna().sum()),'housing2010_nonnull':int(feat.context_housing_completed_residential_m2_per_capita_2010.notna().sum()),'natural2010_nonnull':int(feat.context_natural_increase_per1000_2010.notna().sum()),'farmland_share2010_nonnull':int(feat.context_sown_share_of_farmland_2010.notna().sum()),'farmland_share2021_nonnull':int(feat.context_sown_share_of_farmland_2021.notna().sum()),'published2010_natural_balance_mismatches':mismatch[['municipality_code','births','deaths',reported_col]].to_dict('records')}
 if migration2010==0:blockers.append({'gate':'W04/W12','issue':'No actual baseline2010migration observation in current layer','repair':'Do not substitute2011silently; use2010missing or an explicit contemporaneous2021 fixed-frame design; no future leakage in predictive test'})
 climate=pd.read_parquet(ROOT/'context/climate_settlement_features.parquet');check('climate_unlocated_coordinates_remain_unknown',climate.loc[~located,'climate_gaez_sat_above10_cday_1981_2010'].isna().all())
 for m in range(1,13):check(f'climate_prec_month{m}_nonnull_nonnegative',climate[f'climate_prec_normal_month{m:02d}_mm'].dropna().ge(0).all())
 check('climate_annual_prec_sum12',np.allclose(climate.filter(regex='^climate_prec_normal_month').sum(axis=1,min_count=12).to_numpy(),climate.climate_annual_precipitation_mm.to_numpy(),equal_nan=True))
 check('climate_soil_bonitet_not_fabricated',not climate.climate_bonitet_observed.any())
 metrics['climate']={'gaez_sat1981_2010_nonnull':int(climate.climate_gaez_sat_above10_cday_1981_2010.notna().sum()),'gaez_summer_moisture1981_2010_nonnull':int(climate.climate_gaez_summer_precipitation_over_pet_1981_2010.notna().sum()),'bonitet_observed':bool(climate.climate_bonitet_observed.any()),'annual_ai_is_other_normal_period':True}
 if not climate.climate_bonitet_observed.any():blockers.append({'gate':'W09','issue':'No actual soilbonitet layer; agrarianland denominator2010/2021 still missing','repair':'Obtain a valid soil/productivity measure and clearly distinguish proxy; never label crop share or grain yield as farmland fraction/soil bonitet'})
 themes=pd.read_parquet(ROOT/'typology/settlement_features.parquet');check('thematic_no_false_absence_claim',not themes.negative_record_means_actual_absence.any());check('ethnic_composition_not_causal_mechanism',themes.ethnic_composition_explains_demographic_change.isna().all())
 check('ethnic_suppression_not_zero',themes.loc[themes.ethnicity_suppressed2021,'share_declared_not_russian_response2021'].isna().all())
 metrics['typology']={'recreation_dacha_positive':int(themes.recreation_dacha_evidence.fillna(False).sum()),'resource_context_positive':int(themes.mapped_resource_site_context_evidence.fillna(False).sum()),'historical_mono_positive':int(themes.historical_monotown_evidence.fillna(False).sum()),'ethnic_context_attachments':int(themes.ethnicity_context_attachment_verified.sum()),'ethnic_declared_ratio_usable':int(themes.share_declared_not_russian_response2021.notna().sum()),'industrial_decline_known':int(themes.industrial_decline_evidence.notna().sum()),'resource_shift_known':int(themes.resource_shift_evidence.notna().sum()),'commuting_known':int(themes.commuting_observed.notna().sum()),'ethnocultural_mechanism_known':int(themes.ethnocultural_demographic_evidence.notna().sum())}
 blockers.append({'gate':'W25','issue':'Theme/context witnesses now exist, but historical mono designation/resource geometry/one ethnic composition snapshot do not establish industrial decline/rotational shift/ethnocultural growth mechanism','repair':'Classify evidence-backed types with nullable required criteria, not headline nine labels from demographics alone; independently corroborate missing mechanisms'})
 if (ROOT/'calibration/services_2021_objects.parquet').exists():
  objs=pd.read_parquet(ROOT/'calibration/services_2021_objects.parquet');features=pd.read_parquet(ROOT/'calibration/services_2021_settlement_features.parquet').set_index('id');check('services2021_complete_axis',features.index.equals(pd.Index(ids)))
  check('services2021_objects_unique',~objs.duplicated(['osm_type','osm_id']).any());check('services2021_baseline_candidate_disjoint',not(objs.baseline_uid.notna()&objs.candidate_uid.notna()).any())
  for group in sorted(objs.service_group.unique()):
   for mode,key in [('baseline','baseline_uid'),('candidate_additional','candidate_uid')]:
    a=objs[objs.service_group.eq(group)&objs[key].notna()].drop_duplicates([key,'canonical_site_id']);count=a.groupby(key).size().reindex(ids,fill_value=0);col=f'services_osm2021_{group}_{mode}_count';check(col+'_recomputed',np.array_equal(count.to_numpy(),features.reindex(ids)[col].to_numpy()))
  check('services2021_absence_unknown',features.service_absence_means_unknown.all());metrics['services2021']={'source_assertions':len(objs),'snapshot':sorted(objs.snapshot.astype(str).unique()),'source_groups':{str(k):int(v) for k,v in objs.service_group.value_counts().items()},'strict_settlements':objs.baseline_uid.nunique(),'candidate_settlements':objs.candidate_uid.nunique()}
 after={f:sha(ROOT/f) for f in before};check('reviewed_input_bytes_stable',before==after)
 receipt={'status':'SOURCE_IMPROVEMENT_VERIFIED_REPAIRS_REMAIN' if all(c['pass'] for c in checks) else 'RETURN_TO_REPAIR_LOOP','checks':checks,'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'metrics':metrics,'scientific_blockers':blockers,'source_bytes_unchanged_during_review':before==after,'reviewed_sha256':before,'scientific_final_allowed':False}
 (HERE/'cycle02_source_audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({k:receipt[k] for k in ['status','n_checks','n_failed','metrics','scientific_blockers']},ensure_ascii=False,indent=2))
if __name__=='__main__':run()
