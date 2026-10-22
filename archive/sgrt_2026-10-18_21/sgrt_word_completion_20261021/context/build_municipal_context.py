#!/usr/bin/env python3
"""Source-backed municipal demographics/housing/agriculture; no allocation to settlements."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parents[2];RAW=Path('/workspace/scratch/sgrt_context_completion')
BASE=['region_id','region_name','mun_level','municipality','oktmo','oktmo_stable','oktmo_history','oktmo_year_from','oktmo_year_to','year','indicator_code','indicator_name','indicator_value','indicator_unit','indicator_period','comment']
UPPER='Муниципальное образование верхнего уровня'
def load_csv(p):
 chunks=[]
 for c in pd.read_csv(p,sep=';',dtype={'oktmo':'string','oktmo_stable':'string','oktmo_year_from':'string','oktmo_year_to':'string'},chunksize=100000,low_memory=False):
  c=c[c.mun_level.eq(UPPER)&pd.to_numeric(c.year,errors='coerce').between(2010,2021)];chunks.append(c)
 return pd.concat(chunks,ignore_index=True)
def source_frame(frame,metric,valid_negative=False):
 x=frame[BASE].copy()
 for col in BASE:
  if col not in ['year','indicator_value']:x[col]=x[col].astype('string')
 x['metric']=metric;x['value']=pd.to_numeric(x.indicator_value,errors='coerce')
 x['source_value_invalid']=~np.isfinite(x.value)|((x.value<0)&(not valid_negative))
 x['usable_value']=x.value.mask(x.source_value_invalid)
 x['municipality_code']=x.oktmo_stable.astype('string').fillna(x.oktmo.astype('string'))
 x['source_declares_unchanged']=x.oktmo_history.fillna('').eq('Без изменений')
 return x

def collapse(x):
 x=x.copy();x['source_year_in_declared_interval']=(pd.to_numeric(x.oktmo_year_from,errors='coerce').fillna(-9999)<=x.year)&(pd.to_numeric(x.oktmo_year_to,errors='coerce').fillna(9999)>=x.year)
 g=x.groupby(['municipality_code','year','metric'],dropna=False,sort=False)
 data=g.agg(value=('usable_value','first'),source_rows=('usable_value','size'),source_distinct_nonnull_values=('usable_value','nunique'),source_declares_unchanged=('source_declares_unchanged','all'),source_year_in_declared_interval=('source_year_in_declared_interval','all'),region_name=('region_name','first'),municipality=('municipality','first'),indicator_code=('indicator_code','first'),indicator_name=('indicator_name','first'),indicator_unit=('indicator_unit','first'),indicator_period=('indicator_period','first'),code_history=('oktmo_history','first'),raw_codes=('oktmo','first'),source_distinct_raw_codes=('oktmo','nunique')).reset_index()
 data['conflicting_values']=data.source_distinct_nonnull_values.gt(1);data['ambiguous_multiple_raw_codes']=data.source_distinct_raw_codes.gt(1);data.loc[data.conflicting_values|data.ambiguous_multiple_raw_codes,'value']=np.nan
 return data

def run():
 blocks=[]
 for code,name,negative in [('Y48112001','deaths',False),('Y48112003','births',False),('Y48112004','natural_increase',True)]:
  d=load_csv(RAW/f'data_{code}_112_v20260928.csv');blocks.append(source_frame(d,name,negative))
 # Migration source dimensions are overlapping; only total direction x total sex x total age.
 for p in sorted(RAW.glob('data_Y48112023_year*.parquet')):
  y=int(p.name.split('year')[1][:4])
  if not 2010<=y<=2021:continue
  d=pd.read_parquet(p,filters=[('mun_level','=',UPPER),('migr','=','Миграция — всего'),('grup_2','=','Всего'),('возр','=','Всего')]) if False else pd.read_parquet(p,filters=[('mun_level','=',UPPER),('migr','=','Миграция — всего'),('grup_2','=','Всего'),('vozr','=','Всего')])
  blocks.append(source_frame(d,'migration_increase',True))
 housing=pd.read_parquet(RAW/'data_section37_112_v20260928.parquet',filters=[('indicator_code','=','Y48010001'),('mun_level','=',UPPER),('year','>=',2010),('year','<=',2021)])
 housing=housing[housing.mosh.eq('Жилые здания')&housing.indicator_unit.eq('Квадратный метр общей площади')]
 blocks.append(source_frame(housing,'housing_completed_residential_m2'))
 land=pd.read_parquet(RAW/'data_section6_112_v20260928.parquet',filters=[('indicator_code','in',['Y48006001','Y48006006']),('mun_level','=',UPPER),('year','>=',2006),('year','<=',2021)])
 for code,name in [('Y48006001','municipal_land_ha'),('Y48006006','farmland_ha')]:
  d=land[land.indicator_code.eq(code)&land.indicator_unit.eq('Гектар')];blocks.append(source_frame(d,name))
 ag=pd.read_parquet(RAW/'data_section7_112_v20260928.parquet',filters=[('indicator_code','in',['Y48007018','Y48007025','Y48007010','Y48007013']),('mun_level','=',UPPER),('year','>=',2008),('year','<=',2021)],columns=BASE+['kategor','kultur'])
 ag=ag[ag.kategor.eq('Хозяйства всех категорий')]
 blocks.append(source_frame(ag[ag.indicator_code.eq('Y48007010')&ag.indicator_unit.eq('Тысяча рублей')],'agricultural_output_current_thousand_rub'))
 blocks.append(source_frame(ag[ag.indicator_code.eq('Y48007013')&ag.indicator_unit.eq('Процент')],'agricultural_production_index_real_previousyear_percent'))
 blocks.append(source_frame(ag[ag.indicator_code.eq('Y48007018')&ag.kultur.eq('Вся посевная площадь')&ag.indicator_unit.eq('Гектар')],'sown_area_ha'))
 blocks.append(source_frame(ag[ag.indicator_code.eq('Y48007025')&ag.kultur.eq('Зерновые и зернобобовые культуры — всего')&ag.indicator_unit.eq('Центнер с гектара убранной площади')],'grain_yield_centner_per_ha'))
 pp=list(RAW.glob('data_Y48112027*.parquet')) or list(RAW.glob('data_Y48112027*.csv'))
 if pp:
  p=pp[0];pop=pd.read_parquet(p,filters=[('mun_level','=',UPPER),('year','>=',2010),('year','<=',2022)]) if p.suffix=='.parquet' else load_csv(p)
  pop=pop[pop.mest.eq('Все население')]
  blocks.append(source_frame(pop,'municipal_population_jan1'))
 raw=pd.concat(blocks,ignore_index=True);raw.to_parquet(ROOT/'municipal_selected_source_observations.parquet',index=False)
 data=collapse(raw);data.to_parquet(ROOT/'municipal_annual_context.parquet',index=False)
 wide=data.pivot(index=['municipality_code','year'],columns='metric',values='value').reset_index()
 codes=data.pivot(index=['municipality_code','year'],columns='metric',values='raw_codes')
 validinterval=data.pivot(index=['municipality_code','year'],columns='metric',values='source_year_in_declared_interval')
 units=data.pivot(index=['municipality_code','year'],columns='metric',values='indicator_unit')
 bi=codes.births.eq(codes.deaths)&validinterval.births.eq(True)&validinterval.deaths.eq(True)&units.births.eq('Человек')&units.deaths.eq('Человек')
 wide=wide.set_index(['municipality_code','year'])
 wide['natural_increase_reported']=wide.natural_increase
 known=wide.births.notna()&wide.deaths.notna()&bi.reindex(wide.index).fillna(False)
 derived=wide.births-wide.deaths
 wide['natural_increase_source_balance_mismatch']=(known&wide.natural_increase.notna()&wide.natural_increase.ne(derived)).astype('boolean').mask(~known)
 wide.loc[wide.natural_increase_source_balance_mismatch.fillna(False),'natural_increase']=np.nan
 fill=wide.natural_increase.isna()&known
 wide['natural_increase_derived_from_births_minus_deaths']=fill
 wide['natural_increase_balance_status']=np.select([wide.natural_increase_source_balance_mismatch.fillna(False).to_numpy(dtype=bool),fill.to_numpy(dtype=bool),wide.natural_increase_reported.notna().to_numpy(dtype=bool)],['derived_with_conflicting_reported_source','derived_reported_missing','reported_source'],default='unknown')
 wide.loc[fill,'natural_increase']=derived[fill]
 wide['municipal_population_jan1_raw_code']=codes.municipal_population_jan1.reindex(wide.index)
 wide=wide.reset_index()

 if 'farmland_ha' not in wide:wide['farmland_ha']=np.nan
 keys=pd.MultiIndex.from_frame(wide[['municipality_code','year']])
 native_codes_equal=codes.sown_area_ha.eq(codes.farmland_ha)
 comparable=native_codes_equal&validinterval.sown_area_ha.eq(True)&validinterval.farmland_ha.eq(True)
 wide['sown_farmland_historical_code_interval_valid']=pd.Series((validinterval.sown_area_ha.eq(True)&validinterval.farmland_ha.eq(True)).reindex(keys).values,index=wide.index).fillna(False)
 wide['sown_share_of_farmland_source_harmonized']=(wide.sown_area_ha/wide.farmland_ha.where(wide.farmland_ha>0)).where(pd.Series(native_codes_equal.reindex(keys).values,index=wide.index).fillna(False))
 wide['sown_share_of_farmland_source_harmonized_usable']=wide.sown_share_of_farmland_source_harmonized.where(wide.sown_share_of_farmland_source_harmonized.between(0,1))
 wide['sown_farmland_native_code_comparable']=pd.Series(comparable.reindex(keys).values,index=wide.index).fillna(False)
 wide['sown_share_of_farmland']=(wide.sown_area_ha/wide.farmland_ha.where(wide.farmland_ha>0)).where(wide.sown_farmland_native_code_comparable)
 wide['sown_share_invalid_gt1_or_negative']=((wide.sown_share_of_farmland>1)|(wide.sown_share_of_farmland<0)).astype('boolean').mask(wide.sown_share_of_farmland.isna())
 wide['sown_share_of_farmland_usable']=wide.sown_share_of_farmland.mask(wide.sown_share_invalid_gt1_or_negative.fillna(False))
 if 'municipal_population_jan1' in wide:
  pnext=wide[['municipality_code','year','municipal_population_jan1','municipal_population_jan1_raw_code']].copy();pnext['year']-=1;pnext=pnext.rename(columns={'municipal_population_jan1':'municipal_population_jan1_nextyear','municipal_population_jan1_raw_code':'municipal_population_jan1_nextyear_raw_code'})
  wide=wide.merge(pnext,on=['municipality_code','year'],how='left',validate='one_to_one')
  wide['municipal_population_denominator_raw_code_comparable']=wide.municipal_population_jan1_raw_code.eq(wide.municipal_population_jan1_nextyear_raw_code)
  wide['municipal_population_annual_mean_endpoints']=((wide.municipal_population_jan1+wide.municipal_population_jan1_nextyear)/2).where(wide.municipal_population_denominator_raw_code_comparable)
  denom=wide.municipal_population_annual_mean_endpoints.where(wide.municipal_population_annual_mean_endpoints>0)
  keys=pd.MultiIndex.from_frame(wide[['municipality_code','year']])
  for metric in ['natural_increase','natural_increase_reported','migration_increase','births','deaths','housing_completed_residential_m2']:
   source_metric='natural_increase' if metric=='natural_increase_reported' else metric
   native=pd.Series(codes[source_metric].reindex(keys).values,index=wide.index)
   if metric=='natural_increase':native=native.mask(wide.natural_increase_derived_from_births_minus_deaths,pd.Series(codes.births.reindex(keys).values,index=wide.index))
   compatible=native.eq(wide.municipal_population_jan1_raw_code).fillna(False)
   output=metric+'_per1000' if metric!='housing_completed_residential_m2' else metric+'_per_capita'
   wide[output]=(wide[metric]*(1 if metric=='housing_completed_residential_m2' else 1000)/denom).where(compatible)

 wide.to_parquet(ROOT/'municipal_annual_wide.parquet',index=False)
 base=pd.read_parquet(REPO/'research/sgrt_word_completion_20261021/axis/full_settlement_axis.parquet',columns=['id','municipality_oktmo8_2021'])
 ids=base.id.copy();base['municipality_oktmo8_2021']=base.municipality_oktmo8_2021.astype('string')
 metrics=[c for c in wide if c not in ['municipality_code','year']]
 ww=wide.pivot(index='municipality_code',columns='year',values=metrics);ww.columns=[f'context_{metric}_{int(year)}' for metric,year in ww.columns];ww=ww.reset_index()
 bridge=raw[raw.year.eq(2021)][['oktmo','municipality_code']].drop_duplicates();counts=bridge.groupby('oktmo').municipality_code.nunique();bridge=bridge[bridge.oktmo.map(counts).eq(1)];bridge=bridge.rename(columns={'oktmo':'municipality_oktmo8_2021'})
 bridge.to_parquet(ROOT/'municipal_source2021_to_stable_crosswalk.parquet',index=False)
 result=base.merge(bridge,on='municipality_oktmo8_2021',how='left',validate='many_to_one').merge(ww,on='municipality_code',how='left',validate='many_to_one');assert result.id.equals(ids)
 result['context_unit']='source_municipality_not_own_settlement_values';result['context_historical_boundary_equivalence_proven']=False
 # Source-declared unchanged histories on exactly the paired observations are required.
 hist=data[data.metric.eq('sown_area_ha')&data.year.isin([2010,2021])].pivot(index='municipality_code',columns='year',values='source_declares_unchanged')
 comparable=hist.get(2010,pd.Series(dtype=bool)).eq(True)&hist.get(2021,pd.Series(dtype=bool)).eq(True)
 has=result.context_sown_area_ha_2010.gt(0)&result.context_sown_area_ha_2021.notna()&result.municipality_code.map(comparable).fillna(False)
 decline=pd.Series(pd.NA,index=result.index,dtype='boolean');decline.loc[has]=(result.loc[has,'context_sown_area_ha_2021']/result.loc[has,'context_sown_area_ha_2010'])<.8
 result['agro_decline_evidence']=decline
 # Transparent high-yield observed context, NOT total factor productivity or soil bonitet.
 yields=wide[wide.year.eq(2021)].grain_yield_centner_per_ha.dropna();threshold=float(yields.quantile(.75)) if len(yields) else None
 high=pd.Series(pd.NA,index=result.index,dtype='boolean');has=result.context_grain_yield_centner_per_ha_2021.notna()
 if threshold is not None:high.loc[has]=result.loc[has,'context_grain_yield_centner_per_ha_2021']>=threshold
 result['agro_high_productivity_evidence']=high
 result.to_parquet(ROOT/'municipal_settlement_features.parquet',index=False)
 receipt={'status':'ACTUALLY_BUILT','axis_rows':len(result),'unique_id':int(result.id.nunique()),'source_rows_selected':len(raw),'municipality_year_metric_rows':len(data),'source_conflict_groups':int(data.conflicting_values.sum()),'ambiguous_multiple_raw_codes_groups':int(data.ambiguous_multiple_raw_codes.sum()),'natural_balance_source_disagreements':int(wide.natural_increase_source_balance_mismatch.sum()),'natural_derived_count':int(wide.natural_increase_derived_from_births_minus_deaths.sum()),'natural_derivation':'births-minus-deaths onlysame year/rawcode/unit Человек and validintervals; source disagreements retained in reported, mismatchflag andstatus; this is an analytical variant, not independent correction of official source','sown_farmland_share_invalid_rows':int(wide.sown_share_invalid_gt1_or_negative.sum()),'high_grain_yield2021_centner_ha_threshold_q75':threshold,'agro_high_productivity_meaning':'Observed municipal grain yield>=national75thquantile2021, not full farm productivity or soil bonitet','agro_decline_meaning':'Municipal all-category sownarea2021/2010<0.8 with source-declared unchanged codehistory; no stronger legal boundaryclaim','migration_dimensions':'Миграция — всего / Всего sex / Всего age; no summing subcategories','housing_dimensions':'Y48010001 / Жилые здания / Квадратный метр общей площади; other scopes kept out','land_denominator':'Y48006006 actual farmland ha exists only 2006-2008; no contemporaneous2010-2021 denominator, no cross-year ratio substituted','allocation_to_settlements':False,'context_repeated_do_not_sum':True,'rate_denominator':'Arithmetic mean of Jan1 population year and nextyear, identical native raw codes both endpoints AND numerator source; absent/incompatible=>NULL','coverage_nonnull':{c:int(result[c].notna().sum()) for c in result if c.startswith('context_')},'temporal_scope':'2010-2021; source2026harmonizedmunicipalcodehistory, frozenaxis2021contextbridge; historical boundaries not independently established'}
 (ROOT/'municipal_context_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print('MUNICIPAL',len(result),len(raw),len(data),receipt['source_conflict_groups']);print({c:result[c].notna().sum() for c in result if c.endswith('_2021') or c in ['agro_decline_evidence','agro_high_productivity_evidence']})
if __name__=='__main__':run()
