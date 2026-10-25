"""Retail floor area independently of outlet stock, fixed exact Q4 categories.

No summing municipality levels, no imputing missing observations. Lower municipality
is a settlement candidate, not geolocated inventory; 2023/24 rosters unverified.
"""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024'
source=ROOT/'work/ecommerce_extension_outcomes/raw/data_section2_112_v20260928.parquet'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='333886ae0fc7f0ab3a2e157c86f5852c84ee9cd06f5d99b0fd318a0dd0c01cae'
full=pd.read_parquet(source)
candidates=pd.read_csv(BASE/'bdmo/singleton/internal_singleton_centre_district_candidates.csv',dtype={'oktmo':str,'parent_oktmo':str})
system=pd.read_csv(BASE/'system/centre_system_demography.csv');KEY='source_record_id_2021'
upper='Муниципальное образование верхнего уровня';lower='Муниципальное образование нижнего уровня'
records=[];audits=[];invalids=[]
for category in ['Магазины','Специализированные непродовольственные магазины']:
 raw=full.loc[full.indicator_code.eq('Y48002002')&full.obroz.eq(category)&full.indicator_period.eq('IV квартал')&full.year.isin([2022,2023,2024])].copy()
 keys=['oktmo','mun_level','year'];k=raw.groupby(keys).indicator_value.agg(size='size',nunique=lambda x:x.nunique(dropna=False)).reset_index()
 bad=k.loc[k['nunique'].ne(1),keys]
 raw=raw.merge(bad.assign(bad=True),on=keys,how='left',validate='many_to_one');raw=raw.loc[~raw.bad.eq(True)].drop_duplicates(keys)
 raw=raw.loc[raw.indicator_value.notna()&raw.indicator_value.ge(0)]
 children=raw.loc[raw.mun_level.eq(lower),['oktmo','year','indicator_value','mun_type','indicator_unit']].rename(columns={'indicator_value':'centre_area_m2','mun_type':'centre_mun_type'})
 parents=raw.loc[raw.mun_level.eq(upper),['oktmo','year','indicator_value','mun_type']].rename(columns={'oktmo':'parent_oktmo','indicator_value':'district_area_m2','mun_type':'parent_mun_type'})
 x=candidates[['oktmo','parent_oktmo',KEY]].merge(children,on='oktmo',validate='one_to_many').merge(parents,on=['parent_oktmo','year'],validate='many_to_one')
 x['category']=category
 valid=x.centre_mun_type.isin(['Городское поселение','Сельское поселение'])&x.parent_mun_type.eq('Муниципальный район')&x.district_area_m2.gt(0)&x.district_area_m2.ge(x.centre_area_m2)&x.indicator_unit.eq('Квадратный метр')
 invalids.append(x.loc[~valid].copy());x=x.loc[valid]
 x['centre_share_pct']=100*x.centre_area_m2/x.district_area_m2
 counts=x.groupby(KEY).year.nunique();x=x.loc[x[KEY].isin(counts.index[counts.eq(3)])]
 x=x.merge(system[[KEY,'name_2021','region_2021','medium_primary2002']],on=KEY,validate='many_to_one')
 assert not x.duplicated([KEY,'year']).any()
 for centre,g in x.groupby(KEY):
  g=g.set_index('year');a=g.loc[2022];z=g.loc[2024]
  row={KEY:centre,'name_2021':a.name_2021,'region_2021':a.region_2021,'category':category,'medium_primary2002':bool(a.medium_primary2002),'centre_oktmo':a.oktmo,'district_oktmo':a.parent_oktmo,'area_change_m2':z.centre_area_m2-a.centre_area_m2,'area_share_change_pp':z.centre_share_pct-a.centre_share_pct}
  for year in [2022,2023,2024]:
   for col in ['centre_area_m2','district_area_m2','centre_share_pct']:row[col+'_'+str(year)]=g.loc[year,col]
  records.append(row)
 audits.append({'category':category,'raw_q4_rows':int(len(full.loc[full.indicator_code.eq('Y48002002')&full.obroz.eq(category)&full.indicator_period.eq('IV квартал')&full.year.isin([2022,2023,2024])])),'conflicting_keys_excluded':len(bad),'invalid_joined_observations':len(invalids[-1]),'complete_panels':int(x[KEY].nunique())})
area=pd.DataFrame(records);area.to_csv(OUT/'area_panels.csv',index=False)
pd.concat(invalids).to_csv(OUT/'area_invalid_observations.csv',index=False)
stock=pd.read_csv(BASE/'bdmo/singleton/internal_centre_district_common_panels2022_2024.csv')
matched=area.merge(stock[[KEY,'category','centre_stock_change2022_2024','centre_share_change2022_2024_pp','centre_shops_2022','centre_shops_2024']],on=[KEY,'category'],validate='one_to_one')
matched['avg_area_per_shop_2022']=matched.centre_area_m2_2022/matched.centre_shops_2022.where(matched.centre_shops_2022.gt(0))
matched['avg_area_per_shop_2024']=matched.centre_area_m2_2024/matched.centre_shops_2024.where(matched.centre_shops_2024.gt(0))
matched.to_csv(OUT/'area_stock_matched.csv',index=False)
summary=[]
for category,g in area.loc[area.medium_primary2002].groupby('category'):
 m=matched.loc[matched.medium_primary2002&matched.category.eq(category)]
 summary.append({'category':category,'medium_area_panel_n':len(g),'regions_n':g.region_2021.nunique(),'area_decline_n':int(g.area_change_m2.lt(0).sum()),'area_growth_n':int(g.area_change_m2.gt(0).sum()),'area_stable_n':int(g.area_change_m2.eq(0).sum()),'area_share_loss_1pp_n':int(g.area_share_change_pp.le(-1).sum()),'area_share_gain_1pp_n':int(g.area_share_change_pp.ge(1).sum()),'median_area_share_change_pp':g.area_share_change_pp.median(),'stock_area_common_n':len(m),'count_decline_area_stable_or_up_n':int((m.centre_stock_change2022_2024.lt(0)&m.area_change_m2.ge(0)).sum()),'count_decline_area_decline_n':int((m.centre_stock_change2022_2024.lt(0)&m.area_change_m2.lt(0)).sum()),'count_growth_area_decline_n':int((m.centre_stock_change2022_2024.gt(0)&m.area_change_m2.lt(0)).sum()),'count_share_loss_area_share_nonloss_n':int((m.centre_share_change2022_2024_pp.lt(0)&m.area_share_change_pp.ge(0)).sum()),'median_avg_shop_area_change_pct':(100*(m.avg_area_per_shop_2024/m.avg_area_per_shop_2022-1)).median()})
report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'indicator':'Y48002002','unit':'square_metres','grain':'lower municipal centre territory / whole district, exact category, Q4 2022–2024','year_specific_rosters2023_2024_verified':False,'causal_effect_identified':False,'selection_audits':audits,'results':summary}
(OUT/'area_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False,indent=2))
