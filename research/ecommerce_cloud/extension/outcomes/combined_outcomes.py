"""Different roles in same selected centres; adjacent windows, descriptive only."""
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024'
d=pd.read_csv(OUT/'recent_population_panels.csv');d=d.loc[d.medium_primary2002]
s=pd.read_csv(BASE/'bdmo/singleton/internal_centre_district_common_panels2022_2024.csv');s=s.loc[s.medium_primary2002]
x=d.merge(s[['source_record_id_2021','category','centre_stock_change2022_2024','centre_share_change2022_2024_pp']],on='source_record_id_2021',validate='one_to_many')
def typ(v,t):return 'increase' if v>=t else 'decrease' if v<=-t else 'within_threshold'
x['population_share_type_halfpp']=x.share_change_pp.map(lambda v:typ(v,.5))
x['shop_share_type_onepp']=x.centre_share_change2022_2024_pp.map(lambda v:typ(v,1))
x.to_csv(OUT/'combined_population_trade.csv',index=False)
x.groupby(['category','population_share_type_halfpp','shop_share_type_onepp']).size().rename('centres_n').reset_index().to_csv(OUT/'combined_population_trade_types.csv',index=False)
print(x.groupby('category').size().to_string());print(x.groupby(['category','population_share_type_halfpp','shop_share_type_onepp']).size().to_string())
