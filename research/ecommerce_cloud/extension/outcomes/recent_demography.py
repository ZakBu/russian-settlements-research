"""Postcensus centre and remainder population, paired municipal territories.

Exact same 1-Jan dates and population category; no 2022/23 census-basis break.
Unverified 2023/24 composition means conditional municipality—not proven catchment.
"""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024'
p=ROOT/'work/ecommerce_extension_outcomes/raw/data_Y48112027_112_v20260928.parquet'
d=pd.read_parquet(p);assert set(d.indicator_code)=={'Y48112027'}
KEY='source_record_id_2021';upper='Муниципальное образование верхнего уровня';lower='Муниципальное образование нижнего уровня'
candidates=pd.read_csv(BASE/'bdmo/singleton/internal_singleton_centre_district_candidates.csv',dtype={'oktmo':str,'parent_oktmo':str})
system=pd.read_csv(BASE/'system/centre_system_demography.csv')
raw=d.loc[d.year.isin([2023,2024,2025])&d.mest.eq('Все население')&d.indicator_period.eq('На 1 января')&d.indicator_unit.eq('Человек')].copy()
keys=['oktmo','mun_level','year'];counts=raw.groupby(keys).indicator_value.nunique(dropna=False);bad=counts.loc[counts.ne(1)].reset_index()[keys]
raw=raw.merge(bad.assign(conflict=True),on=keys,how='left',validate='many_to_one');raw=raw.loc[~raw.conflict.eq(True)].drop_duplicates(keys)
raw=raw.loc[raw.indicator_value.notna()&raw.indicator_value.ge(0)]
cols=['oktmo','year','indicator_value','mun_type','municipality','oktmo_stable','oktmo_history','oktmo_year_from','oktmo_year_to']
c=raw.loc[raw.mun_level.eq(lower),cols].rename(columns={col:'centre_'+col for col in cols if col not in ['oktmo','year']})
s=raw.loc[raw.mun_level.eq(upper),cols].rename(columns={col:('parent_oktmo' if col=='oktmo' else 'district_'+col) for col in cols if col!='year'})
x=candidates[['oktmo','parent_oktmo',KEY]].merge(c,on='oktmo',validate='one_to_many').merge(s,on=['parent_oktmo','year'],validate='many_to_one')
x['valid_observation']=x.centre_mun_type.isin(['Городское поселение','Сельское поселение'])&x.district_mun_type.eq('Муниципальный район')&x.district_indicator_value.gt(0)&x.district_indicator_value.ge(x.centre_indicator_value)
x.loc[~x.valid_observation].to_csv(OUT/'recent_population_invalid_observations.csv',index=False)
x=x.loc[x.valid_observation].copy();n=x.groupby(KEY).year.nunique();x=x.loc[x[KEY].isin(n.index[n.eq(3)])]
x=x.merge(system[[KEY,'name_2021','region_2021','medium_primary2002','type_2021','population_2002','population_2021','population_2023','population_2025']],on=KEY,validate='many_to_one')
x['other_population']=x.district_indicator_value-x.centre_indicator_value
x['centre_population_share_pct']=100*x.centre_indicator_value/x.district_indicator_value
x.to_csv(OUT/'recent_population_observations.csv',index=False)
rows=[]
for centre,g in x.groupby(KEY):
 g=g.set_index('year');a=g.loc[2023];z=g.loc[2025]
 r={KEY:centre,'name_2021':a.name_2021,'region_2021':a.region_2021,'type_2021':a.type_2021,'medium_primary2002':bool(a.medium_primary2002),'centre_oktmo':a.oktmo,'district_oktmo':a.parent_oktmo,'own_growth_pct':100*(z.centre_indicator_value/a.centre_indicator_value-1) if a.centre_indicator_value>0 else None,'other_growth_pct':100*(z.other_population/a.other_population-1) if a.other_population>0 else None,'share_change_pp':z.centre_population_share_pct-a.centre_population_share_pct,'year_specific_composition_verified':False,'travel_catchment_observed':False,'causal_effect_identified':False}
 for year in [2023,2024,2025]:
  r['centre_population_'+str(year)]=g.loc[year,'centre_indicator_value'];r['district_population_'+str(year)]=g.loc[year,'district_indicator_value'];r['other_population_'+str(year)]=g.loc[year,'other_population']
 r['district_no_publisher_transformation_flags']=all(str(g.loc[y,'district_oktmo_history'])=='Без изменений' for y in [2023,2024,2025])
 r['lower_municipal_history_unknown']=all(str(g.loc[y,'centre_oktmo_history'])=='CD' for y in [2023,2024,2025])
 # Identical own-urban counts are a valuable independent source cross-check, not boundary proof.
 r['urban_own_population2023']=a.population_2023;r['urban_own_population2025']=a.population_2025
 r['urban_source_crosscheck_available']=pd.notna(a.population_2023) and pd.notna(a.population_2025)
 r['urban_own_exact_match']=r['urban_source_crosscheck_available'] and a.population_2023==a.centre_indicator_value and a.population_2025==z.centre_indicator_value
 rows.append(r)
panel=pd.DataFrame(rows);panel.to_csv(OUT/'recent_population_panels.csv',index=False)
summary=[]
for scope,g in [('all_candidates',panel),('medium2002',panel.loc[panel.medium_primary2002]),('medium2002_district_no_publisher_transformation_flags',panel.loc[panel.medium_primary2002&panel.district_no_publisher_transformation_flags])]:
 summary.append({'scope':scope,'centres_n':len(g),'regions_n':g.region_2021.nunique(),'own_decline_n':int(g.own_growth_pct.lt(0).sum()),'other_decline_n':int(g.other_growth_pct.lt(0).sum()),'own_and_other_decline_n':int((g.own_growth_pct.lt(0)&g.other_growth_pct.lt(0)).sum()),'share_increase_n':int(g.share_change_pp.gt(0).sum()),'share_decrease_n':int(g.share_change_pp.lt(0).sum()),'share_increase_atleast_halfpp_n':int(g.share_change_pp.ge(.5).sum()),'share_decrease_atleast_halfpp_n':int(g.share_change_pp.le(-.5).sum()),'median_own_growth_pct':g.own_growth_pct.median(),'median_other_growth_pct':g.other_growth_pct.median(),'median_share_change_pp':g.share_change_pp.median(),'urban_crosscheck_n':int(g.urban_source_crosscheck_available.sum()),'urban_exact_match_n':int(g.urban_own_exact_match.sum())})
report={'indicator':'Y48112027','definition':d.indicator_name.iloc[0],'raw_rows':len(d),'source_parquet_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'conflicting_keys_excluded_n':len(bad),'candidate_centres_n':len(candidates),'timing':'1January2023,2024,2025 only','interpretation':'centre lower municipal territory and district minus centre territory; singleton candidacy based2020/21/22/26, rosters2023/24 not verified; not observed settlement catchments','results':summary}
(OUT/'recent_population_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
