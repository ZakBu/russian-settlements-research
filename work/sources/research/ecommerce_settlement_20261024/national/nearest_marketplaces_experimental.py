"""Experimental combined geographic proximity; asynchronous, unequal network sources."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree
P=Path(__file__).resolve().parent
x=pq.read_table(P/'nearest_wb_settlements.parquet').to_pandas()
o=pq.read_table(P/'ozon_objectlinks_experimental.parquet').to_pandas()
# Only inferred pickup points; parcel lockers are excluded from the primary variant.
use=(pd.to_numeric(o.raw_p,errors='coerce')==0)&(o.link_status_5km.eq('accepted_unique_exact_name_within_radius')|
 o.federal_territory_context_source2021.notna())
o=o.loc[use].copy()
assert len(o)>0
assert o.objectid.is_unique

def xyz(lat,lon):
 a=np.radians(np.asarray(lat,float));b=np.radians(np.asarray(lon,float))
 return np.column_stack([np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)])
y=xyz(x.accepted_latitude,x.accepted_longitude);z=xyz(o.latitude,o.longitude)
chord,idx=cKDTree(z).query(y,k=1)
x['nearest_experimental_ozon_straight_km']=6371.0088*2*np.arcsin(np.clip(chord/2,0,1))
x['nearest_experimental_ozon_objectid']=o.objectid.to_numpy()[idx]
x['nearest_either_straight_km_experimental']=np.minimum(
 x.nearest_linked_wb_straight_km,x.nearest_experimental_ozon_straight_km)
assert (x.nearest_either_straight_km_experimental<=x.nearest_linked_wb_straight_km+1e-12).all()
for i in np.random.default_rng(20261024).choice(len(x),size=30,replace=False):
 assert abs(np.sqrt(((z-y[i])**2).sum(axis=1)).min()-chord[i])<1e-12

def group(g):
 live=g.effective_population>0;pop=g.effective_population.clip(lower=0)
 r={'settlements':len(g),'inhabited_settlements':int(live.sum()),'population2021':float(pop.sum())}
 for label,col in [('wb','nearest_linked_wb_straight_km'),
                   ('ozon_candidate','nearest_experimental_ozon_straight_km'),
                   ('either_experimental','nearest_either_straight_km_experimental')]:
  r[label+'_median_straight_km_inhabited']=float(g.loc[live,col].median())
  for km in [5,10,20]:
   r[label+f'_inhabited_within_{km}km']=int((live&(g[col]<=km)).sum())
   r[label+f'_population_share_within_{km}km_pct']=float(100*pop.loc[g[col]<=km].sum()/pop.sum()) if pop.sum()>0 else None
 return r
out=pd.DataFrame([{'size2021':str(k),**group(g)} for k,g in x.groupby('size_2021',observed=True)])
out.to_csv(P/'nearest_marketplaces_by_size_experimental.csv',index=False)
pq.write_table(__import__('pyarrow').Table.from_pandas(x,preserve_index=False),P/'nearest_marketplaces_experimental.parquet')
meta={'target_rows':len(x),'ozon_pickup_points_used':len(o),'WB_snapshot':'2026-10-21',
 'Ozon_third_party_declared_snapshot':'2026-08-06','national_ordinary_target':group(x),
 'limits':['Experimental Ozon third-party source; completeness and current operation are unverified.',
 'Ozon uses exact-name unique5km links and federal label context; WB uses its own prior accepted linkage.',
 'Different dates and linkage profiles forbid market-share or growth comparisons.',
 'Straight-line proximity is not road travel, actual access or customer flows.',
 'Population weights are census2021; federal-city population excluded from ordinary denominator.']}
(P/'nearest_marketplaces_summary_experimental.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
print(json.dumps(meta,ensure_ascii=False,indent=2))
