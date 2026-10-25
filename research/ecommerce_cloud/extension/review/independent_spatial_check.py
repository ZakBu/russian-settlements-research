"""Independent haversine verification, no KDTree and no imported analysis code."""
from pathlib import Path
import json,math,hashlib
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
long=pd.read_parquet(ROOT/'data/population/settlements_census_long.parquet')
s=long[(long.census_year==2021)&(long.population_scope=='settlement')&(long.is_additive_settlement_record==True)&(long.working_credit_present==True)&long.effective_population.notna()]
w=pd.read_parquet(ROOT/'data/population/settlements_census_wide.parquet')
w=w[w.source_record_id_2021.notna()]
d=s.merge(w[['source_record_id_2021','effective_population_2002','population_value_quality_2002']],left_on='source_record_id',right_on='source_record_id_2021',validate='1:1')
d=d[d.accepted_latitude.notna()&d.accepted_longitude.notna()].set_index('source_record_id')
r=pd.read_parquet(ROOT/'work/ecommerce_cloud_extension/national/circular_neighbourhoods.parquet')
ids=sorted(r.source_record_id_2021.unique())
chosen=[ids[i] for i in np.linspace(0,len(ids)-1,16,dtype=int)]
strict=(d.population_value_quality=='direct_published_census_value')&(d.population_value_quality_2002=='direct_published_census_value')&d.effective_population_2002.notna()
la=np.radians(d.accepted_latitude.to_numpy());lo=np.radians(d.accepted_longitude.to_numpy())
checks=[]
for cid in chosen:
 c=d.loc[cid];a=math.radians(c.accepted_latitude);b=math.radians(c.accepted_longitude)
 distances=2*6371.0088*np.arcsin(np.sqrt(np.clip(np.sin((la-a)/2)**2+np.cos(a)*np.cos(la)*np.sin((lo-b)/2)**2,0,1)))
 for radius in [10,20,40,80]:
  rows=r[(r.source_record_id_2021==cid)&(r.radius_km==radius)]
  if rows.empty:continue
  z=rows.iloc[0];inside=(distances<=radius);g=d[inside];common=d[inside&strict]
  delta=100*(c.effective_population/common.effective_population.sum()-c.effective_population_2002/common.effective_population_2002.sum())
  checks.append({'id':cid,'latitude':c.accepted_latitude,'longitude':c.accepted_longitude,'radius_km':radius,'members_n':len(g),'common_members_n':len(common),'independent_delta_pp':delta,'saved_delta_pp':z.share_change_pp,'pass':len(g)==z.members_n and len(common)==z.common_members_n and abs(delta-z.share_change_pp)<1e-8})
res={'method':'Brute-force haversine distances to all 144149 point records; 16 centres selected evenly across sorted IDs, four radii where supported','n':len(checks),'failures':sum(not c['pass'] for c in checks),'checks':checks}
(OUT/'independent_spatial_results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2,default=lambda x:x.item())+'\n')
assert res['failures']==0
print(json.dumps({k:v for k,v in res.items() if k!='checks'},ensure_ascii=False))
