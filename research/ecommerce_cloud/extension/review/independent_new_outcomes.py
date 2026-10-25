"""Recalculate new outcomes and verify all medium observations against raw sources."""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
P=ROOT/'research/ecommerce_cloud/extension/outcomes';RAW=ROOT/'work/ecommerce_extension_outcomes/raw'
res={'scope':'raw values for every medium panel and independent derived arithmetic; does not verify unpublished composition or source statistical accuracy','failures':[]}
r=pd.read_csv(P/'recent_population_panels.csv',dtype={'centre_oktmo':str,'district_oktmo':str});r=r[r.medium_primary2002]
pop=pd.read_parquet(RAW/'data_Y48112027_112_v20260928.parquet')
pop=pop[pop.year.isin([2023,2024,2025])&(pop.mest=='Все население')&(pop.indicator_period=='На 1 января')&(pop.indicator_unit=='Человек')]
lookup=pop.groupby(['oktmo','mun_level','year']).indicator_value.agg(lambda x:set(x))
for _,x in r.iterrows():
 for y in [2023,2024,2025]:
  c=float(x[f'centre_population_{y}']);s=float(x[f'district_population_{y}'])
  for code,level,value in [(x.centre_oktmo,'Муниципальное образование нижнего уровня',c),(x.district_oktmo,'Муниципальное образование верхнего уровня',s)]:
   if lookup.loc[(code,level,y)]!={value}:res['failures'].append(['pop_raw',x.source_record_id_2021,y,code])
  if abs((s-c)-x[f'other_population_{y}'])>1e-8:res['failures'].append(['pop_remainder',x.source_record_id_2021,y])
calc=100*(r.centre_population_2025/r.district_population_2025-r.centre_population_2023/r.district_population_2023)
assert (abs(calc-r.share_change_pp)<1e-8).all()
res['recent_population']={'n':len(r),'regions':r.region_2021.nunique(),'share_increase':int((calc>0).sum()),'share_decrease':int((calc<0).sum()),'median_share_change_pp':calc.median(),'raw_values_checked':len(r)*3*2}
a=pd.read_csv(P/'area_stock_matched.csv',dtype={'centre_oktmo':str,'district_oktmo':str});a=a[a.medium_primary2002]
f=pd.read_parquet(RAW/'data_section2_112_v20260928.parquet',columns=['indicator_code','obroz','indicator_period','year','oktmo','mun_level','indicator_value','indicator_unit'])
f=f[(f.indicator_code=='Y48002002')&(f.indicator_period=='IV квартал')&f.year.isin([2022,2023,2024])]
units=f.indicator_unit.unique().tolist();look=f.groupby(['obroz','oktmo','mun_level','year']).indicator_value.agg(lambda x:set(x))
for _,x in a.iterrows():
 for y in [2022,2023,2024]:
  for code,level,col in [(x.centre_oktmo,'Муниципальное образование нижнего уровня','centre_area_m2'),(x.district_oktmo,'Муниципальное образование верхнего уровня','district_area_m2')]:
   value=float(x[f'{col}_{y}'])
   if look.loc[(x.category,code,level,y)]!={value}:res['failures'].append(['area_raw',x.source_record_id_2021,x.category,y,code])
 assert abs(100*(x.centre_area_m2_2024/x.district_area_m2_2024-x.centre_area_m2_2022/x.district_area_m2_2022)-x.area_share_change_pp)<1e-8
res['area']={'n':len(a),'raw_values_checked':len(a)*3*2,'source_units':units}
# Independently reconstruct sensitivity labels and calculate summaries.
a['large_break']=False
for field in ['centre_area_m2','district_area_m2']:
 for u,v in [(2022,2023),(2023,2024),(2022,2024)]:
  ratio=a[f'{field}_{v}']/a[f'{field}_{u}'].where(a[f'{field}_{u}']>0)
  a['large_break']|=~ratio.between(.5,2,inclusive='both')
checks=[]
saved=pd.read_csv(P/'area_sensitivity.csv')
for _,s in saved.iterrows():
 g=a[a.category==s.category]
 if 'oryol' in s.sensitivity:g=g[g.region_2021!='орловская']
 if 'factor2' in s.sensitivity:g=g[~g.large_break]
 assert len(g)==s.medium_centres_n
 assert abs(g.area_share_change_pp.median()-s.median_area_share_change_pp)<1e-8
 assert int(((g.centre_stock_change2022_2024<0)&(g.area_change_m2>=0)).sum())==s.stock_decline_area_nondecline_n
 checks.append({'sensitivity':s.sensitivity,'category':s.category,'n':len(g),'verified':True})
res['sensitivity_checks']=checks
assert not res['failures']
(OUT/'independent_new_outcomes_results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(res,ensure_ascii=False,indent=2))
