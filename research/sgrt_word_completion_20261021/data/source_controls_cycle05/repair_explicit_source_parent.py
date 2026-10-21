#!/usr/bin/env python3
"""Repair source-parent grain using explicit typed census hierarchy, not string truncation.

Scope: 2021 census-source context. No axis overwrite, no historical territorial
identity claim, no conversion of missing municipal observations into zeros.
"""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];ROOT=REPO/'research/sgrt_word_completion_20261021'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=ROOT/'typology/sources/allsettlements_20260925/data_allsettlements_anon_156_v20260925.parquet'
axispath=ROOT/'axis/full_settlement_axis.parquet'
paths=[source,axispath,HERE/'latest2021_np_roster_complete_accounting.parquet',HERE/'housing_native_year_rate_audit.parquet',HERE/'demographic2021_native_year_rate_audit.parquet',ROOT/'context/municipal_source2021_to_stable_crosswalk.parquet',ROOT/'context/municipal_settlement_features.parquet']
before={str(p.relative_to(REPO)):sha(p) for p in paths}
checks=[]
def check(name,v):checks.append(dict(check=name,passed=bool(v)))
t=pd.read_parquet(source,columns=['object_level','object_name','oktmo','region','mun_upper','population']);t['upper_source_row_1based']=np.arange(len(t))+1
u=t[t.object_level.eq('Муниципалитет верхнего уровня')][['region','object_name','oktmo','population','upper_source_row_1based']].rename(columns={'object_name':'mun_upper','oktmo':'native_source_parent_oktmo8','population':'published_parent_census_population'})
u['native_source_parent_oktmo8']=u.native_source_parent_oktmo8.astype('string').str.zfill(8)
r=pd.read_parquet(HERE/'latest2021_np_roster_complete_accounting.parquet');r=r[r.id.notna()].copy()
c=r.merge(u,on=['region','mun_upper'],how='left',validate='many_to_many')
counts=c.groupby('id').native_source_parent_oktmo8.count()
multi=set(counts[counts.gt(1)].index)
c['parent_relation_rule']='explicit_source_NP_mun_upper_and_region_exact_unique_typed_upper'
c=c[(~c.id.isin(multi))|c.native_source_parent_oktmo8.eq(c.native_np_oktmo11.str[:8])].copy()
c.loc[c.id.isin(multi),'parent_relation_rule']='explicit_parent_name_region_rivals_resolved_only_by_exact_native_prefix8'
missing=c.native_source_parent_oktmo8.isna()
assert missing.sum()==1
fallback=c[missing][['id','region','native_np_oktmo11']].copy();fallback['native_source_parent_oktmo8']=fallback.native_np_oktmo11.str[:8]
fallback=fallback.merge(u.drop(columns=['mun_upper']),on=['region','native_source_parent_oktmo8'],how='left',validate='one_to_one').set_index('id')
for col in ['native_source_parent_oktmo8','published_parent_census_population','upper_source_row_1based']:
 c.loc[missing,col]=c.loc[missing,'id'].map(fallback[col]).values
c.loc[missing,'parent_relation_rule']='Irkutsk_source_city_vs_urban_okrug_parent_label_alias_exact_native_prefix8_and_region'
check('every155411_accepted2021_np_has_one_explicit_source_parent',len(c)==155411 and c.id.is_unique and c.native_source_parent_oktmo8.notna().all())
check('all_parent_entities_are_explicit_typed_upper_municipalities',c.native_source_parent_oktmo8.isin(u.native_source_parent_oktmo8).all())
control=c.groupby('native_source_parent_oktmo8').agg(np_count=('id','size'),np_population_sum=('population','sum'),published_parent_census_population=('published_parent_census_population','first')).reset_index()
control=control.merge(u[['native_source_parent_oktmo8','region','mun_upper']],on='native_source_parent_oktmo8',how='outer',validate='one_to_one');control['population_difference']=control.np_population_sum-control.published_parent_census_population
control.to_csv(HERE/'repaired_source_parent_municipal_mass_controls.csv',index=False)
check('all2336_upper_municipal_source_mass_controls_exact',len(control)==2336 and control.population_difference.eq(0).all())
a=pd.read_parquet(axispath,columns=['id','municipality_oktmo8_2021','population_2021','source_record_id_2021'])
bridge=c[['id','native_np_oktmo11','source_row_1based','upper_source_row_1based','region','object_name','mun_upper','native_source_parent_oktmo8','published_parent_census_population','parent_relation_rule']].merge(a[['id','municipality_oktmo8_2021']],on='id',validate='one_to_one')
bridge['original_axis_code_is_different_grain']=bridge.native_source_parent_oktmo8.ne(bridge.municipality_oktmo8_2021)
bridge['historical_boundary_equivalence_proven']=False
bridge.to_parquet(HERE/'explicit2021_source_parent_bridge.parquet',index=False)
oldbridge=pd.read_parquet(ROOT/'context/municipal_source2021_to_stable_crosswalk.parquet').rename(columns={'municipality_oktmo8_2021':'native_source_parent_oktmo8'})
side=a[['id','municipality_oktmo8_2021']].merge(bridge.drop(columns=['municipality_oktmo8_2021']),on='id',how='left',validate='one_to_one')
side=side.merge(oldbridge,on='native_source_parent_oktmo8',how='left',validate='many_to_one')
side['parent_context_mapping_scope']='explicit_source_upper2021_to_raw_BDMO2021_code_only_no_unproved_stable_code_fallback'
h=pd.read_parquet(HERE/'housing_native_year_rate_audit.parquet');h=h[h.year.eq(2021)].set_index('stable_code')
d=pd.read_parquet(HERE/'demographic2021_native_year_rate_audit.parquet').set_index('stable_code')
side['context_housing_completed_residential_m2_per_capita_parent_strict2021']=side.municipality_code.map(h.strict_native_year_rate)
side['housing2021_native_year_rate_status']=side.municipality_code.map(h.eligibility_status).fillna('no_source2021_parent_or_BDMO_native_bridge_or_rate')
for metric,name in [('natural','natural_increase'),('migration','migration_increase')]:
 side[f'context_{name}_per1000_parent_strict2021']=side.municipality_code.map(d[f'{metric}_strict_rate_per1000'])
 side[f'{name}2021_native_year_rate_status']=side.municipality_code.map(d[f'{metric}_source_rate_guard_status']).fillna('no_source2021_parent_or_BDMO_native_bridge_or_rate')
side['context_unit']='municipality_context_repeated_not_own_settlement'
side['context_historical_boundary_equivalence_proven']=False
check('repaired_parent_context_preserves_all_axis_ids_order',side.id.equals(a.id))
side.to_parquet(HERE/'parent_repaired_strict2021_settlement_context.parquet',index=False)
old=pd.read_parquet(ROOT/'context/municipal_settlement_features.parquet').set_index('id');stats={}
original_strict_h=pd.read_parquet(HERE/'strict_housing2021_settlement_context.parquet').set_index('id')
original_strict_d=pd.read_parquet(HERE/'strict_demographic2021_settlement_context.parquet').set_index('id')
candidates=set(pd.read_parquet(ROOT/'model/output_word_ci_2021_baseline/candidate_centers.parquet',columns=['id']).id)
changes=side[['id','municipality_oktmo8_2021','native_source_parent_oktmo8','municipality_code','original_axis_code_is_different_grain']].copy()
for name,oldcol,newcol,strictcol,stricttab in [
 ('housing','context_housing_completed_residential_m2_per_capita_2021','context_housing_completed_residential_m2_per_capita_parent_strict2021','context_housing_completed_residential_m2_per_capita_strict2021',original_strict_h),
 ('natural','context_natural_increase_per1000_2021','context_natural_increase_per1000_parent_strict2021','context_natural_increase_per1000_strict2021',original_strict_d),
 ('migration','context_migration_increase_per1000_2021','context_migration_increase_per1000_parent_strict2021','context_migration_increase_per1000_strict2021',original_strict_d)]:
 prior=side.id.map(old[oldcol]);strictprior=side.id.map(stricttab[strictcol]);current=side[newcol]
 new=prior.isna()&current.notna();held=prior.notna()&current.isna();changed=prior.notna()&current.notna()&~np.isclose(prior,current,rtol=1e-12,atol=1e-12,equal_nan=True)
 changes[name+'_old']=prior;changes[name+'_new']=current;changes[name+'_newly_recovered']=new;changes[name+'_previous_value_now_held']=held;changes[name+'_both_known_value_changed']=changed
 stats[name]=dict(frozen_original_axis_nonnull=int(prior.notna().sum()),original_bridge_strict_nonnull=int(strictprior.notna().sum()),repaired_bridge_strict_nonnull=int(current.notna().sum()),newly_recovered_vs_frozen=int(new.sum()),newly_recovered_candidate_centers=int((new&side.id.isin(candidates)).sum()),previous_values_now_held=int(held.sum()),held_candidate_centers=int((held&side.id.isin(candidates)).sum()),both_known_value_changed=int(changed.sum()),changed_candidate_centers=int((changed&side.id.isin(candidates)).sum()),net_coverage_change=int(current.notna().sum()-prior.notna().sum()))
changes.to_parquet(HERE/'parent_context_repair_before_after.parquet',index=False)
check('frozen_source_inputs_unchanged',before=={str(p.relative_to(REPO)):sha(p) for p in paths})
outputs=['repair_explicit_source_parent.py','repaired_source_parent_municipal_mass_controls.csv','explicit2021_source_parent_bridge.parquet','parent_repaired_strict2021_settlement_context.parquet','parent_context_repair_before_after.parquet']
receipt=dict(status='EXPLICIT_TYPED_SOURCE_PARENT_REPAIRED_AND_RATE_GUARDED',n_checks=len(checks),n_failed=sum(not x['passed'] for x in checks),checks=checks,source_np_parent_rows=len(bridge),parent_mass_controls=len(control),axis_lower_or_other_parent_grain_repaired=int(bridge.original_axis_code_is_different_grain.sum()),statistics=stats,model_old_modified=False,historical_boundary_equivalence_proven=False,inputs_sha256=before,outputs={name:dict(sha256=sha(HERE/name),bytes=(HERE/name).stat().st_size) for name in outputs})
(HERE/'parent_context_repair_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))
