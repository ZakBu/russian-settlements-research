"""Diagnose coverage and observed heterogeneity without causal comparisons."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024'
sys=pd.read_csv(BASE/'system/centre_system_demography.csv')
pan=pd.read_csv(BASE/'bdmo/singleton/internal_centre_district_common_panels2022_2024.csv')
medium=sys.loc[sys.medium_primary2002].copy()
shops=pan.loc[pan.medium_primary2002&pan.category.eq('Магазины')].copy()
medium['in_shop_panel']=medium.source_record_id_2021.isin(shops.source_record_id_2021)
rows=[]
for selected,g in medium.groupby('in_shop_panel'):
 for col in ['population_2002','population_2021','context_members_n','context_other_inhabited2021_n','centre_change2002_2021_pct','centre_population_share_change_pp','common_roster_population2021_coverage']:
  rows.append({'in_shop_panel':bool(selected),'measure':col,'centres_n':len(g),'observed_n':int(g[col].notna().sum()),'median':g[col].median(),'q25':g[col].quantile(.25),'q75':g[col].quantile(.75)})
pd.DataFrame(rows).to_csv(OUT/'selection_characteristics.csv',index=False)
reg=medium.groupby('region_2021').agg(all_medium_centres=('source_record_id_2021','size'),shop_panel_centres=('in_shop_panel','sum')).reset_index()
reg['coverage_pct']=100*reg.shop_panel_centres/reg.all_medium_centres
reg.to_csv(OUT/'selection_by_region.csv',index=False)
x=shops.merge(medium[['source_record_id_2021','population_2002','population_2021','centre_population_share_change_pp']],on='source_record_id_2021',validate='one_to_one')
x['size2002']=pd.cut(x.population_2002,[4999,9999,19999,49999],labels=['5000–9999','10000–19999','20000–49999'])
x['centre_decline']=x.centre_stock_change2022_2024.lt(0)
x['share_loss_1pp']=x.centre_share_change2022_2024_pp.le(-1)
x['share_gain_1pp']=x.centre_share_change2022_2024_pp.ge(1)
x['periphery_shops_2022']=x.district_shops_2022-x.centre_shops_2022
x['periphery_shops_2024']=x.district_shops_2024-x.centre_shops_2024
x['periphery_change']=x.periphery_shops_2024-x.periphery_shops_2022
x['stock_centre_periphery_type']=x.apply(lambda r:('centre_decline' if r.centre_stock_change2022_2024<0 else 'centre_growth' if r.centre_stock_change2022_2024>0 else 'centre_stable')+'__'+('periphery_decline' if r.periphery_change<0 else 'periphery_growth' if r.periphery_change>0 else 'periphery_stable'),axis=1)
x.groupby('stock_centre_periphery_type').size().rename('centres_n').reset_index().to_csv(OUT/'centre_periphery_stock_types.csv',index=False)
for group in ['size2002','region_2021']:
 x.groupby(group,observed=True).agg(centres_n=('source_record_id_2021','size'),centre_stock_decline_n=('centre_decline','sum'),centre_share_loss_1pp_n=('share_loss_1pp','sum'),centre_share_gain_1pp_n=('share_gain_1pp','sum'),median_share_change_pp=('centre_share_change2022_2024_pp','median'),median_centre_stock_change=('centre_stock_change2022_2024','median'),median_periphery_stock_change=('periphery_change','median')).reset_index().to_csv(OUT/('shops_by_'+group+'.csv'),index=False)
x.to_csv(OUT/'centre_periphery_shops.csv',index=False)
summary={'medium_total':len(medium),'shop_panel':len(shops),'panel_pct':100*len(shops)/len(medium),'regions_total':medium.region_2021.nunique(),'regions_in_panel':shops.region_2021.nunique(),'regions_without_panel':reg.loc[reg.shop_panel_centres.eq(0),'region_2021'].tolist(),'stock_types':x.stock_centre_periphery_type.value_counts().to_dict(),'note':'Selected municipal panel; stock differences are not openings/closures; administration is not observed travel catchment; no causal effect estimated.'}
(OUT/'selection_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
