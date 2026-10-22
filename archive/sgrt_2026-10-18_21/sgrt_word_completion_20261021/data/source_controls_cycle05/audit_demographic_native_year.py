#!/usr/bin/env python3
"""Independent 2021 birth/death/natural/migration raw-cell readback and strict guards."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];ROOT=REPO/'research/sgrt_word_completion_20261021';RAW=Path('/workspace/scratch/sgrt_context_completion')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
UPPER='Муниципальное образование верхнего уровня'
cols=['region_name','mun_level','municipality','oktmo','oktmo_stable','oktmo_history','oktmo_year_from','oktmo_year_to','year','indicator_code','indicator_name','indicator_value','indicator_unit','indicator_period']
inputs=[];blocks=[]
for code,metric in [('Y48112001','deaths'),('Y48112003','births'),('Y48112004','natural_reported')]:
 p=RAW/f'data_{code}_112_v20260928.csv';inputs.append(p)
 parts=[]
 for c in pd.read_csv(p,sep=';',dtype='string',usecols=cols,chunksize=100000):
  c=c[c.mun_level.eq(UPPER)&c.year.eq('2021')].copy()
  if len(c):parts.append(c)
 d=pd.concat(parts,ignore_index=True);d['metric']=metric;d['source_file']=p.name;blocks.append(d)
p=RAW/'data_Y48112023_year2021_112_v20260928.parquet';inputs.append(p)
d=pd.read_parquet(p,filters=[('mun_level','=',UPPER),('migr','=','Миграция — всего'),('grup_2','=','Всего'),('vozr','=','Всего')]);d=d[cols].astype('string');d['metric']='migration';d['source_file']=p.name;blocks.append(d)
raw=pd.concat(blocks,ignore_index=True)
raw['year']=pd.to_numeric(raw.year,errors='raise');raw['value']=pd.to_numeric(raw.indicator_value,errors='coerce')
raw['stable_code']=raw.oktmo_stable.fillna(raw.oktmo)
raw['valid_numeric']=np.isfinite(raw.value)&(raw.value.ge(0)|raw.metric.isin(['natural_reported','migration']))
raw['native_year_valid']=pd.to_numeric(raw.oktmo_year_from,errors='coerce').fillna(-9999).le(raw.year)&pd.to_numeric(raw.oktmo_year_to,errors='coerce').fillna(9999).ge(raw.year)
raw['valid_unit_period']=raw.indicator_unit.eq('Человек')&raw.indicator_period.eq('Значение показателя за год')
raw.to_parquet(HERE/'demographic2021_selected_raw_cells.parquet',index=False)
rows=[]
for (stable,metric),g in raw.groupby(['stable_code','metric'],dropna=False,sort=False):
 vals=g.loc[g.valid_numeric,'value'].unique();codes=g.oktmo.dropna().unique()
 rows.append(dict(stable_code=stable,metric=metric,value=float(vals[0]) if len(vals)==1 and len(codes)==1 else np.nan,native_code=codes[0] if len(codes)==1 else None,native_year_valid=bool(g.native_year_valid.all()),valid_unit_period=bool(g.valid_unit_period.all()),distinct_values=len(vals),distinct_raw_codes=len(codes),source_rows=len(g)))
groups=pd.DataFrame(rows);groups.to_parquet(HERE/'demographic2021_raw_group_readback.parquet',index=False)
wide=groups.pivot(index='stable_code',columns='metric')
wide.columns=['_'.join([metric,attr]) for attr,metric in wide.columns];wide=wide.reset_index()
# Production preserves reported counts; births minus deaths is an explicit analytical
# variant only when same native raw code and person units/year intervals agree.
known=wide.births_value.notna()&wide.deaths_value.notna()&wide.births_native_code.eq(wide.deaths_native_code)&wide.births_native_year_valid.eq(True)&wide.deaths_native_year_valid.eq(True)&wide.births_valid_unit_period.eq(True)&wide.deaths_valid_unit_period.eq(True)
derived=wide.births_value-wide.deaths_value
reported=wide.natural_reported_value
replace=known&(reported.isna()|reported.ne(derived))
wide['natural_value']=reported.mask(replace,derived)
wide['natural_native_code']=wide.natural_reported_native_code.mask(replace,wide.births_native_code)
wide['natural_native_year_valid']=wide.natural_reported_native_year_valid.mask(replace,wide.births_native_year_valid&wide.deaths_native_year_valid)
wide['natural_valid_unit_period']=wide.natural_reported_valid_unit_period.mask(replace,wide.births_valid_unit_period&wide.deaths_valid_unit_period)
wide['natural_raw_derivation_used']=replace
pop=pd.read_parquet(HERE/'population_denominator_raw_readback.parquet')
for year,label in [(2021,'start'),(2022,'next')]:
 p=pop[pop.year.eq(year)].drop(columns=['year']).rename(columns={c:'population_'+label+'_'+c for c in pop if c not in ['stable_code','year']})
 wide=wide.merge(p,on='stable_code',how='left',validate='one_to_one')
wide['annual_population_mean']=(wide.population_start_value+wide.population_next_value)/2
w=pd.read_parquet(ROOT/'context/municipal_annual_wide.parquet');w=w[w.year.eq(2021)][['municipality_code','natural_increase','natural_increase_per1000','migration_increase','migration_increase_per1000','natural_increase_derived_from_births_minus_deaths']]
wide=wide.merge(w,left_on='stable_code',right_on='municipality_code',how='outer',validate='one_to_one');wide['stable_code']=wide.stable_code.fillna(wide.municipality_code)
checks=[]
def check(name,v):checks.append(dict(check=name,passed=bool(v)))
summary={}
for metric,production in [('natural','natural_increase'),('migration','migration_increase')]:
 value=wide[f'{metric}_value'];native=wide[f'{metric}_native_code']
 same=native.eq(wide.population_start_native_code)&native.eq(wide.population_next_native_code)
 rate=(1000*value/wide.annual_population_mean.where(wide.annual_population_mean.gt(0))).where(same)
 wide[f'{metric}_independent_rate_per1000']=rate
 observed=wide[production+'_per1000'].notna()
 check(metric+'_all_published_rates_equal_raw_numeric_readback',np.isclose(rate[observed],wide.loc[observed,production+'_per1000'],rtol=1e-12,atol=1e-12,equal_nan=True).all())
 yearguard=wide[f'{metric}_native_year_valid'].eq(True)&wide.population_start_native_year_valid.eq(True)&wide.population_next_native_year_valid.eq(True)
 periodguard=wide[f'{metric}_valid_unit_period'].eq(True)&wide.population_start_valid_period.eq(True)&wide.population_next_valid_period.eq(True)&wide.population_start_valid_unit.eq(True)&wide.population_next_valid_unit.eq(True)
 strict=rate.where(yearguard&periodguard)
 wide[f'{metric}_strict_rate_per1000']=strict
 wide[f'{metric}_source_rate_guard_status']=np.select([rate.isna(),~yearguard,~periodguard],['unknown_or_ambiguous_or_different_native_codes','source_year_outside_native_code_interval','unit_or_period_conflict'],default='accepted_context_rate_not_own_NP')
 wide[f'{metric}_prior_rate_held']=observed&strict.isna()
 summary[metric]=dict(prior_municipal_nonnull=int(observed.sum()),strict_municipal_nonnull=int(strict.notna().sum()),prior_values_held=int((observed&strict.isna()).sum()),hold_reasons=wide.loc[observed&strict.isna(),f'{metric}_source_rate_guard_status'].value_counts().to_dict())
wide.to_parquet(HERE/'demographic2021_native_year_rate_audit.parquet',index=False)
axis=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet',columns=['id','municipality_oktmo8_2021']);bridge=pd.read_parquet(ROOT/'context/municipal_source2021_to_stable_crosswalk.parquet')
side=axis.merge(bridge,on='municipality_oktmo8_2021',how='left',validate='many_to_one');lookup=wide.set_index('stable_code')
frozen=pd.read_parquet(ROOT/'context/municipal_settlement_features.parquet',columns=['id','context_natural_increase_per1000_2021','context_migration_increase_per1000_2021']).set_index('id')
candidates=set(pd.read_parquet(ROOT/'model/output_word_ci_2021_baseline/candidate_centers.parquet',columns=['id']).id)
for metric,name in [('natural','natural_increase'),('migration','migration_increase')]:
 col=f'context_{name}_per1000_strict2021'
 side[col]=side.municipality_code.map(lookup[f'{metric}_strict_rate_per1000'])
 side[f'{name}2021_native_year_rate_status']=side.municipality_code.map(lookup[f'{metric}_source_rate_guard_status']).fillna('no_source_municipality_or_rate')
 prior=side.id.map(frozen[f'context_{name}_per1000_2021'])
 held=prior.notna()&side[col].isna()
 summary[metric].update(affected_axis_ids=int(held.sum()),affected_candidate_centers=int((held&side.id.isin(candidates)).sum()),prior_axis_nonnull=int(prior.notna().sum()),strict_axis_nonnull=int(side[col].notna().sum()))
side['demography2021_grain']='municipality_context_repeated_not_own_NP'
side['demography2021_historical_boundary_equivalence_proven']=False
side.to_parquet(HERE/'strict_demographic2021_settlement_context.parquet',index=False)
check('all_axis_rows_exact_order_preserved',side.id.equals(axis.id))
receipt=dict(status='RAW2021_DEMOGRAPHIC_RATES_READ_BACK_WITH_NATIVE_YEAR_SIDE_SCENARIO',n_checks=len(checks),n_failed=sum(not c['passed'] for c in checks),checks=checks,summary=summary,source_grain='municipality;not ownsettlement; fixed2021bridge; noexacthistoricalboundaryclaim',source_cells_rows=len(raw),inputs_sha256={str(p):sha(p) for p in inputs},outputs={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in HERE.glob('*') if p.name in ['audit_demographic_native_year.py','demographic2021_selected_raw_cells.parquet','demographic2021_raw_group_readback.parquet','demographic2021_native_year_rate_audit.parquet','strict_demographic2021_settlement_context.parquet']})
(HERE/'demographic_context_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt['summary'],ensure_ascii=False,indent=2));print('checks',checks)
