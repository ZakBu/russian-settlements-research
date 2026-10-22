#!/usr/bin/env python3
"""Independent census-accounting and native-year housing-rate readback.

Does not import the production builders; reads raw BDMO Parquet and separately
published census aggregate rows. Frozen inputs are never overwritten.
"""
from pathlib import Path
import hashlib,json,datetime
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
ROOT=REPO/'research/sgrt_word_completion_20261021'
RAW=HERE/'sources'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()
def relative(p):
 try:return str(p.relative_to(REPO))
 except ValueError:return str(p)
def dump(name,x):(HERE/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
checks=[]
def check(name,ok,**details):checks.append(dict(check=name,passed=bool(ok),**details))
paths={
 'axis':ROOT/'axis/full_settlement_axis.parquet',
 'ledger':ROOT/'axis/source_observations_all.parquet',
 'raw_imported_census':REPO/'publication/stage71/applied_state_observations.parquet',
 'independent_table_version':ROOT/'typology/sources/allsettlements_20260925/data_allsettlements_anon_156_v20260925.parquet',
 'housing_raw':RAW/'data_section37_112_v20260928.parquet',
 'population_raw':RAW/'data_Y48112027_112_v20260928.parquet',
 'frozen_wide':ROOT/'context/municipal_annual_wide.parquet',
 'frozen_context':ROOT/'context/municipal_settlement_features.parquet',
 'frozen_crosswalk':ROOT/'context/municipal_source2021_to_stable_crosswalk.parquet',
 'model_inputs':ROOT/'model/model_inputs_word_ci_2021.json',
 'model_candidates':ROOT/'model/output_word_ci_2021_baseline/candidate_centers.parquet',
}
before={relative(p):sha(p) for p in paths.values()}
a=pd.read_parquet(paths['axis']);ledger=pd.read_parquet(paths['ledger']);raw=pd.read_parquet(paths['raw_imported_census'])
check('all_axis_ids_unique',a.id.is_unique)
check('all_axis_ids_exact_union_dated_source_ids',set(a.id)==set(ledger.id))
check('ledger_unique_entity_year',not ledger.duplicated(['id','census_year']).any())
check('ledger_unique_raw_source_record',ledger.source_record_id.is_unique)
check('imported_raw_source_exact_ledger_record_set',set(raw.source_record_id)==set(ledger.source_record_id))
joined=ledger.merge(raw[['source_record_id','census_year','population','region_norm','settlement_type','settlement_name','oktmo','population_scope']],on='source_record_id',how='left',suffixes=('_ledger','_raw'),validate='one_to_one')
check('all_imported_raw_years_match_ledger',joined.census_year_ledger.eq(joined.census_year_raw).all())
check('all_raw_populations_match_ledger', (joined.population_ledger.eq(joined.population_raw)|(joined.population_ledger.isna()&joined.population_raw.isna())).all())
# Accounting dimensions are explicit; no historical-only row is a 2021 zero.
account=a[['id','region','type','axis_kind','lat','lon','population_scope','is_additive_source_unit']].copy()
account['located']=account.lat.notna()&account.lon.notna()
for year in [2002,2010,2021]:
 p=a[f'population_{year}'];source=a[f'source_record_id_{year}'];native=ledger[ledger.census_year.eq(year)].set_index('id')
 account[f'has_source_{year}']=source.notna()
 account[f'known_population_{year}']=p.notna()
 account[f'population_{year}']=p
 account[f'population_status_{year}']=np.select([source.isna(),p.isna(),p.eq(0)],['no_dated_source_observation','source_population_unknown','observed_zero'],default='observed_positive')
 check(f'{year}_axis_source_ids_exact_raw_frame',set(source.dropna())==set(native.source_record_id))
 check(f'{year}_population_integer_nonnegative_or_unknown',p.dropna().ge(0).all() and p.dropna().mod(1).eq(0).all())
account['2021_role']=np.select([~account.has_source_2021,account.population_scope.eq('federal_city_region'),~account.is_additive_source_unit],['historical_only_not2021zero','federal_territory_total_excluded_from_ordinary_sum','nonadditive_source_entity'],default='ordinary_2021_source_unit')
account.to_parquet(HERE/'axis_entity_year_accounting.parquet',index=False)
by=[]
for year in [2002,2010,2021]:
 z=account[['region','type','located','axis_kind',f'population_status_{year}',f'population_{year}']].rename(columns={f'population_status_{year}':'population_status',f'population_{year}':'population'})
 z['year']=year;z['size_class']=pd.cut(z.population,[-1,0,99,499,1999,9999,49999,99999,np.inf],labels=['zero','1–99','100–499','500–1999','2000–9999','10000–49999','50000–99999','100000+']).astype('string').fillna('no_population_observation')
 group=z.groupby(['year','region','type','size_class','population_status','located','axis_kind'],dropna=False,observed=True).agg(entities=('population','size'),known_population=('population','count'),population_sum=('population',lambda x:x.sum(min_count=1))).reset_index();by.append(group)
coverage=pd.concat(by,ignore_index=True);coverage.to_csv(HERE/'coverage_by_year_region_type_size_location.csv.gz',index=False)
check('coverage_accounting_exhausts_all_entities_each_year',coverage.groupby('year').entities.sum().eq(len(a)).all())
# Independent table-level controls: regional and country aggregates, not sum of its NP rows.
t=pd.read_parquet(paths['independent_table_version'],columns=['object_level','object_name','oktmo','region','population'])
t['raw_row_1based']=np.arange(len(t))+1
controls=t[t.object_level.isin(['Регион','Город федерального значения'])].copy()
def region_key(v):
 v=str(v).strip();v=v.zfill(11) if len(v) in (10,11) else v.zfill(8)
 return v[:3] if v.startswith(('118','718','719')) else v[:2]+'0'
controls['source_region_key']=controls.oktmo.map(region_key)
check('independent_region_controls85_unique',len(controls)==85 and controls.source_region_key.is_unique)
native=joined[joined.census_year_raw.eq(2021)].copy();native['source_region_key']=native.oktmo.map(region_key)
aggregated=native.groupby('source_region_key').agg(source_entities=('id','size'),source_population=('population_raw','sum'),source_region=('region_norm','first')).reset_index()
region=controls[['source_region_key','object_name','population','raw_row_1based','oktmo']].rename(columns={'population':'published_regional_population','object_name':'published_region_name','oktmo':'published_region_oktmo'}).merge(aggregated,on='source_region_key',how='outer',validate='one_to_one',indicator=True)
region['difference']=region.source_population-region.published_regional_population
region.to_csv(HERE/'census2021_region_aggregate_controls.csv',index=False)
check('all85_regions_source_frame_aggregate_controls_match',region._merge.eq('both').all() and region.difference.eq(0).all())
country=t[t.object_level.eq('Страна')]
check('country_control_unique',len(country)==1)
country_n=int(country.population.iloc[0]);check('all2021_source_populations_exhaust_country_control',int(native.population_raw.sum())==country_n,population=country_n)
ordinary=account[account['2021_role'].eq('ordinary_2021_source_unit')]
fed=account[account['2021_role'].eq('federal_territory_total_excluded_from_ordinary_sum')]
check('ordinary_plus_federal_no_double_count_country',ordinary.population_2021.sum()+fed.population_2021.sum()==country_n)
# Full physical-universe completeness is not inferred from population control: uninhabited NP need source rosters.
check('known2021_real_zeros_preserved',int(account.population_2021.eq(0).sum())==int(native.population_raw.eq(0).sum()))

# Independent native-code housing rates from raw source. No call to production collapse().
UPPER='Муниципальное образование верхнего уровня'
h=pd.read_parquet(paths['housing_raw'],filters=[('indicator_code','=','Y48010001'),('mun_level','=',UPPER),('year','>=',2010),('year','<=',2021)])
h=h[h.mosh.eq('Жилые здания')&h.indicator_unit.eq('Квадратный метр общей площади')].copy()
p=pd.read_parquet(paths['population_raw'],filters=[('mun_level','=',UPPER),('year','>=',2010),('year','<=',2022)])
p=p[p.mest.eq('Все население')].copy()

def extract(frame,kind):
 frame=frame.copy();frame['stable_code']=frame.oktmo_stable.astype('string').fillna(frame.oktmo.astype('string'))
 frame['native_code']=frame.oktmo.astype('string');frame['numeric_value']=pd.to_numeric(frame.indicator_value,errors='coerce')
 frame['valid_numeric']=np.isfinite(frame.numeric_value)&frame.numeric_value.ge(0)
 frame['native_year_valid']=pd.to_numeric(frame.oktmo_year_from,errors='coerce').fillna(-9999).le(frame.year)&pd.to_numeric(frame.oktmo_year_to,errors='coerce').fillna(9999).ge(frame.year)
 frame['valid_unit']=frame.indicator_unit.eq('Человек' if kind=='population' else 'Квадратный метр общей площади')
 frame['valid_period']=frame.indicator_period.eq('На 1 января' if kind=='population' else 'Значение показателя за год')
 groups=[]
 for (stable,year),g in frame.groupby(['stable_code','year'],dropna=False,sort=False):
  values=g.numeric_value[g.valid_numeric].unique();codes=g.native_code.dropna().unique()
  unambiguous=len(values)==1 and len(codes)==1
  groups.append(dict(stable_code=stable,year=int(year),source_rows=len(g),value=float(values[0]) if unambiguous else np.nan,native_code=codes[0] if len(codes)==1 else None,distinct_nonnegative_values=len(values),distinct_native_codes=len(codes),native_year_valid=bool(g.native_year_valid.all()),valid_unit=bool(g.valid_unit.all()),valid_period=bool(g.valid_period.all()),municipality=g.municipality.iloc[0],region=g.region_name.iloc[0],source_history=' | '.join(sorted(g.oktmo_history.dropna().unique()))))
 return pd.DataFrame(groups),frame
hh,hraw=extract(h,'housing');pp,praw=extract(p,'population')
hh.to_parquet(HERE/'housing_numerator_raw_readback.parquet',index=False);pp.to_parquet(HERE/'population_denominator_raw_readback.parquet',index=False)
raw_columns=['stable_code','year','native_code','numeric_value','native_year_valid','valid_numeric','indicator_name','indicator_period','indicator_unit','oktmo_year_from','oktmo_year_to','region_name','municipality']
hraw[raw_columns].to_parquet(HERE/'housing_selected_raw_cells.parquet',index=False)
praw[raw_columns].to_parquet(HERE/'population_selected_raw_cells.parquet',index=False)
q=hh.rename(columns={c:'housing_'+c for c in hh if c not in ['stable_code','year']})
for offset,label in [(0,'start'),(1,'next')]:
 v=pp.copy();v['year']-=offset;v=v.rename(columns={c:f'population_{label}_'+c for c in v if c not in ['stable_code','year']})
 q=q.merge(v,on=['stable_code','year'],how='left',validate='one_to_one')
q['same_native_code']=q.housing_native_code.eq(q.population_start_native_code)&q.housing_native_code.eq(q.population_next_native_code)
q['annual_mean_population']=(q.population_start_value+q.population_next_value)/2
q['source_rate_numeric_complete']=q.housing_value.notna()&q.population_start_value.notna()&q.population_next_value.notna()&q.annual_mean_population.gt(0)
q['all_native_years_valid']=q[['housing_native_year_valid','population_start_native_year_valid','population_next_native_year_valid']].eq(True).all(axis=1)
q['all_units_periods_valid']=q[['housing_valid_unit','housing_valid_period','population_start_valid_unit','population_start_valid_period','population_next_valid_unit','population_next_valid_period']].eq(True).all(axis=1)
q['numeric_rate_same_native_code']=q.housing_value/q.annual_mean_population.where(q.annual_mean_population.gt(0))
q['numeric_rate_same_native_code']=q.numeric_rate_same_native_code.where(q.same_native_code)
q['strict_native_year_rate']=q.numeric_rate_same_native_code.where(q.all_native_years_valid&q.all_units_periods_valid)
q['eligibility_status']=np.select([~q.source_rate_numeric_complete,~q.same_native_code,~q.all_native_years_valid,~q.all_units_periods_valid],['unknown_or_ambiguous_numerator_or_denominator','different_native_raw_codes','source_year_outside_declared_native_code_interval','unit_or_period_metadata_conflict'],default='accepted_native_code_year_rate_context_not_own_NP')
w=pd.read_parquet(paths['frozen_wide'],columns=['municipality_code','year','housing_completed_residential_m2_per_capita'])
q=q.merge(w,left_on=['stable_code','year'],right_on=['municipality_code','year'],how='outer',validate='one_to_one')
q['stable_code']=q.stable_code.fillna(q.municipality_code)
q['eligibility_status']=q.eligibility_status.fillna('housing_numerator_absent')
known=q.housing_completed_residential_m2_per_capita.notna()
q['production_rate_equals_independent_numeric_readback']=np.isclose(q.housing_completed_residential_m2_per_capita,q.numeric_rate_same_native_code,equal_nan=True,rtol=1e-12,atol=1e-12)
check('all_published_housing_rates_exact_raw_numeric_readback',q.loc[known,'production_rate_equals_independent_numeric_readback'].all())
q['production_rate_missing_native_year_or_period_guard']=known&q.strict_native_year_rate.isna()
q.to_parquet(HERE/'housing_native_year_rate_audit.parquet',index=False)
q[q.production_rate_missing_native_year_or_period_guard].to_csv(HERE/'housing_rates_requiring_native_year_repair.csv',index=False)
# New sidecar, row-grain identical to axis. This is a stricter contextual source input, not own NP housing.
bridge=pd.read_parquet(paths['frozen_crosswalk'])
q21=q[q.year.eq(2021)].set_index('stable_code')
side=a[['id','municipality_oktmo8_2021']].merge(bridge,on='municipality_oktmo8_2021',how='left',validate='many_to_one')
side['context_housing_completed_residential_m2_per_capita_strict2021']=side.municipality_code.map(q21.strict_native_year_rate)
side['housing2021_native_year_rate_status']=side.municipality_code.map(q21.eligibility_status).fillna('no_unambiguous_source_municipality_bridge_or_rate')
side['housing2021_source_grain']='municipality_context_repeated_do_not_sum_not_own_settlement'
side['housing2021_historical_boundary_equivalence_proven']=False
check('strict_housing_sidecar_preserves_all_axis_ids_exact_order',side.id.equals(a.id))
side.to_parquet(HERE/'strict_housing2021_settlement_context.parquet',index=False)
context=pd.read_parquet(paths['frozen_context'],columns=['id','context_housing_completed_residential_m2_per_capita_2021'])
z=context.merge(side[['id','context_housing_completed_residential_m2_per_capita_strict2021','housing2021_native_year_rate_status']],on='id',validate='one_to_one')
z['prior_housing_context_held']=z.context_housing_completed_residential_m2_per_capita_2021.notna()&z.context_housing_completed_residential_m2_per_capita_strict2021.isna()
z[z.prior_housing_context_held].to_parquet(HERE/'housing2021_affected_axis_ids.parquet',index=False)
nodes=pd.read_parquet(paths['model_candidates'],columns=['id'])
affected_candidates=nodes.id.isin(set(z.loc[z.prior_housing_context_held,'id'])).sum()
check('strict_housing_no_missing_to_zero',side.context_housing_completed_residential_m2_per_capita_strict2021.notna().sum()<=z.context_housing_completed_residential_m2_per_capita_2021.notna().sum())
check('frozen_inputs_unchanged',before=={relative(p):sha(p) for p in paths.values()})
summary={
 'schema_version':1,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'SOURCE_ACCOUNTING_AND_RAW_READBACK_COMPLETE_NATIVE_YEAR_HOUSING_SENSITIVITY_AVAILABLE',
 'n_checks':len(checks),'n_failed':sum(not c['passed'] for c in checks),'checks':checks,
 'census':{'axis_entities':len(a),'dated_observations':len(ledger),'national2021_population_control':country_n,'source2021_rows':len(native),'ordinary2021_rows':len(ordinary),'ordinary2021_population':int(ordinary.population_2021.sum()),'federal_2021_rows':len(fed),'federal_2021_population':int(fed.population_2021.sum()),'regional_controls':len(region),'regional_zero_difference':int(region.difference.eq(0).sum()),'located_entities':int(account.located.sum()),'unlocated_entities':int((~account.located).sum()),'historical_only_not2021zero':int(account['2021_role'].eq('historical_only_not2021zero').sum()),'real2021zeros':int(account.population_2021.eq(0).sum()),'zero_population_roster_completeness_not_proven_by_population_sum':True,'controls_scope':'independently read20260925 published aggregate rows, same census/different sourceversion; not independent primary census roster reading'},
 'housing':{'raw_numerator_rows':len(hraw),'raw_population_endpoint_rows':len(praw),'production_rate_rows':int(known.sum()),'all_numeric_rates_match_independent_raw_readback':bool(q.loc[known,'production_rate_equals_independent_numeric_readback'].all()),'rates_requiring_native_year_or_period_repair_all_years':int(q.production_rate_missing_native_year_or_period_guard.sum()),'rates_requiring_repair2021':int(q.loc[q.year.eq(2021),'production_rate_missing_native_year_or_period_guard'].sum()),'affected2021_axis_ids':int(z.prior_housing_context_held.sum()),'affected2021_candidate_centers':int(affected_candidates),'prior2021_axis_nonnull':int(z.context_housing_completed_residential_m2_per_capita_2021.notna().sum()),'strict2021_axis_nonnull':int(side.context_housing_completed_residential_m2_per_capita_strict2021.notna().sum()),'strict_sidecar_available_for_next_model_run':True,'old_physics_modified':False,'own_settlement_housing_claim':False},
 'inputs_sha256':before,'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in HERE.iterdir() if p.is_file() and p.name in ['audit_source_controls.py','axis_entity_year_accounting.parquet','coverage_by_year_region_type_size_location.csv.gz','census2021_region_aggregate_controls.csv','housing_numerator_raw_readback.parquet','population_denominator_raw_readback.parquet','housing_selected_raw_cells.parquet','population_selected_raw_cells.parquet','housing_native_year_rate_audit.parquet','housing_rates_requiring_native_year_repair.csv','strict_housing2021_settlement_context.parquet','housing2021_affected_axis_ids.parquet']},
 'scientific_completion_claim':False,
}
dump('source_control_receipt.json',summary)
print(json.dumps({k:v for k,v in summary.items() if k not in ['checks','inputs_sha256','outputs']},ensure_ascii=False,indent=2))
