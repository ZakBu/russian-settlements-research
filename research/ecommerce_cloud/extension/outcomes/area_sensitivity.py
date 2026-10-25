"""Measurement sensitivity: no invented decimal corrections to reported area."""
from pathlib import Path
import json
import pandas as pd
OUT=Path(__file__).resolve().parent
a=pd.read_csv(OUT/'area_stock_matched.csv');a=a.loc[a.medium_primary2002].copy()
a['any_area_step_factor_outside_half_double']=False
for col in ['centre_area_m2','district_area_m2']:
 for y0,y1 in [(2022,2023),(2023,2024),(2022,2024)]:
  ratio=a[col+'_'+str(y1)]/a[col+'_'+str(y0)].where(a[col+'_'+str(y0)].gt(0))
  a['any_area_step_factor_outside_half_double']|=(ratio.lt(.5)|ratio.gt(2)|ratio.isna())
a.loc[a.any_area_step_factor_outside_half_double].to_csv(OUT/'area_large_breaks.csv',index=False)
summary=[]
for name,subset in [('all_reported',a),('exclude_oryol_all',a.loc[~a.region_2021.eq('орловская')]),('exclude_factor2_breaks',a.loc[~a.any_area_step_factor_outside_half_double]),('exclude_oryol_and_factor2',a.loc[~a.region_2021.eq('орловская')&~a.any_area_step_factor_outside_half_double])]:
 for category,g in subset.groupby('category'):
  summary.append({'sensitivity':name,'category':category,'medium_centres_n':len(g),'area_decline_n':int(g.area_change_m2.lt(0).sum()),'area_growth_n':int(g.area_change_m2.gt(0).sum()),'area_stable_n':int(g.area_change_m2.eq(0).sum()),'area_share_loss_1pp_n':int(g.area_share_change_pp.le(-1).sum()),'area_share_gain_1pp_n':int(g.area_share_change_pp.ge(1).sum()),'median_area_share_change_pp':g.area_share_change_pp.median(),'stock_decline_area_nondecline_n':int((g.centre_stock_change2022_2024.lt(0)&g.area_change_m2.ge(0)).sum()),'stock_decline_area_decline_n':int((g.centre_stock_change2022_2024.lt(0)&g.area_change_m2.lt(0)).sum()),'max_share_change_pp':g.area_share_change_pp.max()})
pd.DataFrame(summary).to_csv(OUT/'area_sensitivity.csv',index=False)
print(pd.DataFrame(summary).to_string(index=False))
