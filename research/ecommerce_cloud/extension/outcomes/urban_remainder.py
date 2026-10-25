"""Alternative recent outcome: named urban centre from Rosstat bulletins / BDMO district.
Not municipality-to-settlement allocation; requires already accepted internal-centre bridge.
"""
from pathlib import Path
import pandas as pd,json
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024'
s=pd.read_csv(BASE/'system/centre_system_demography.csv');c=pd.read_csv(BASE/'bdmo/singleton/internal_singleton_centre_district_candidates.csv',dtype={'parent_oktmo':str})
d=pd.read_parquet(ROOT/'work/ecommerce_extension_outcomes/raw/data_Y48112027_112_v20260928.parquet')
d=d.loc[d.year.isin([2023,2025])&d.mest.eq('Все население')&d.indicator_period.eq('На 1 января')&d.indicator_unit.eq('Человек')&d.mun_level.eq('Муниципальное образование верхнего уровня')&d.mun_type.eq('Муниципальный район')]
keys=['oktmo','year'];bad=d.groupby(keys).indicator_value.nunique(dropna=False);bad=bad.loc[bad.ne(1)].reset_index()[keys]
d=d.merge(bad.assign(bad=True),on=keys,how='left');d=d.loc[~d.bad.eq(True)].drop_duplicates(keys)
wide=d.pivot(index='oktmo',columns='year',values='indicator_value').dropna(subset=[2023,2025]).reset_index().rename(columns={'oktmo':'parent_oktmo',2023:'district_population_2023',2025:'district_population_2025'})
x=c[['source_record_id_2021','parent_oktmo']].merge(s,on='source_record_id_2021',validate='one_to_one');x=x.loc[x.medium_primary2002&x.urban_2023_2025_observed]
x=x.merge(wide,on='parent_oktmo',validate='one_to_one')
x=x.loc[x.district_population_2023.ge(x.population_2023)&x.district_population_2025.ge(x.population_2025)&x.district_population_2023.gt(0)&x.population_2023.gt(0)]
for y in [2023,2025]:x['other_population_'+str(y)]=x['district_population_'+str(y)]-x['population_'+str(y)]
x['other_growth_pct']=100*(x.other_population_2025/x.other_population_2023.where(x.other_population_2023.gt(0))-1)
x['share_change_pp']=100*(x.population_2025/x.district_population_2025-x.population_2023/x.district_population_2023)
x.to_csv(OUT/'urban_population_district_remainders.csv',index=False)
summary={'medium_named_urban_centres_n':len(x),'regions_n':x.region_2021.nunique(),'own_decline_n':int(x.centre_change2023_2025_pct.lt(0).sum()),'other_decline_n':int(x.other_growth_pct.lt(0).sum()),'share_increase_n':int(x.share_change_pp.gt(0).sum()),'share_decrease_n':int(x.share_change_pp.lt(0).sum()),'median_own_growth_pct':x.centre_change2023_2025_pct.median(),'median_other_growth_pct':x.other_growth_pct.median(),'median_share_change_pp':x.share_change_pp.median(),'composition2023_2024_verified':False,'difference_from_lower_municipal_panel':'Named own urban population from frozen official bulletin candidates, not lower municipal population; district total from Y48112027, internal singleton candidacy2020/21/22/26.'}
(OUT/'urban_remainders_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
