"""Nationwide geographic proximity to linked WB catalogue objects.
Spherical straight-line distances only. No inferred travel, service use or opening dates.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial import cKDTree
P=Path(__file__).resolve().parent
S=P.parents[2]
base=P.parent/'pilot/inputs/data/population/settlements_census_long.parquet'
columns=['source_record_id','census_year','settlement_name','region_norm','effective_population',
 'population_scope','is_additive_settlement_record','working_credit_present','accepted_point_present',
 'accepted_latitude','accepted_longitude']
d=pq.read_table(base,columns=columns).to_pandas()
target=d.loc[(d.census_year==2021)&(d.population_scope=='settlement')&
 d.is_additive_settlement_record.fillna(False)&d.working_credit_present.fillna(False)].copy()
assert target.source_record_id.is_unique
valid=target.accepted_point_present.fillna(False)&target.accepted_latitude.between(-90,90)&target.accepted_longitude.between(-180,180)
missing=target.loc[~valid].copy();x=target.loc[valid].copy()
w=pq.read_table(S/'wb20261021_objects.parquet').to_pandas()
w=w.loc[w.focus_types_8_34.fillna(False)&(w.baseline_uid.notna()|w.federal_territory_uid.notna())&
 w.latitude.between(-90,90)&w.longitude.between(-180,180)].copy()
assert w.object_id.is_unique
assert w.snapshot_date.nunique()==1

def xyz(lat,lon):
 a=np.radians(np.asarray(lat,dtype=float));b=np.radians(np.asarray(lon,dtype=float))
 return np.column_stack((np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)))
points=xyz(w.latitude,w.longitude);targets=xyz(x.accepted_latitude,x.accepted_longitude)
chord,index=cKDTree(points).query(targets,k=1)
x['nearest_linked_wb_straight_km']=6371.0088*2*np.arcsin(np.clip(chord/2,0,1))
x['nearest_wb_object_id']=w.object_id.to_numpy()[index]
x['nearest_wb_link_kind']=w.link_status.to_numpy()[index]
# Verify exact nearest chord on a deterministic sample without the spatial index.
rng=np.random.default_rng(20261024);sample=rng.choice(len(x),size=min(50,len(x)),replace=False)
for i in sample:
 brute=np.sqrt(((points-targets[i])**2).sum(axis=1)).min()
 assert abs(brute-chord[i])<1e-12
x['size_2021']=pd.cut(x.effective_population,[-1,0,99,999,2999,9999,np.inf],
 labels=['0','1–99','100–999','1 000–2 999','3 000–9 999','10 000+'])

def aggregate(g):
 pop=g.effective_population.fillna(0).clip(lower=0)
 inhabited=g.effective_population>0
 r={'settlements_with_coordinates':len(g),'inhabited_settlements':int(inhabited.sum()),
    'population_2021_in_scope':float(pop.sum()),
    'median_straight_km_all_settlements':float(g.nearest_linked_wb_straight_km.median()),
    'median_straight_km_inhabited':float(g.loc[inhabited,'nearest_linked_wb_straight_km'].median())}
 for km in [5,10,20]:
  near=g.nearest_linked_wb_straight_km<=km
  r[f'inhabited_within_{km}km']=int((near&inhabited).sum())
  r[f'population_within_{km}km']=float(pop.loc[near].sum())
  r[f'population_share_within_{km}km_pct']=float(100*pop.loc[near].sum()/pop.sum()) if pop.sum()>0 else None
 return r
regional=pd.DataFrame([{'region':k,**aggregate(g)} for k,g in x.groupby('region_norm')])
size=pd.DataFrame([{'size_2021':str(k),**aggregate(g)} for k,g in x.groupby('size_2021',observed=True)])
regional.to_csv(P/'nearest_wb_by_region.csv',index=False)
size.to_csv(P/'nearest_wb_by_size.csv',index=False)
pq.write_table(__import__('pyarrow').Table.from_pandas(x,preserve_index=False),P/'nearest_wb_settlements.parquet')
missing.to_csv(P/'nearest_wb_no_accepted_coordinates.csv',index=False)
meta={'target':'Credited ordinary additive census2021 source records; federal territories separate',
 'target_rows_before_coordinate_filter':len(target),'no_accepted_coordinates':len(missing),
 'no_accepted_coordinates_population_2021':float(missing.effective_population.sum()),
 'linked_focus_wb_objects':len(w),'ordinary_linked_objects':int(w.baseline_uid.notna().sum()),
 'federal_context_objects':int(w.federal_territory_uid.notna().sum()),'region_count':len(regional),
 'sphere_radius_km':6371.0088,'brute_force_checked_points':len(sample),
 'all':aggregate(x),
 'limits':['Straight-line proximity is not road travel, actual accessibility, trips or use.',
 'Catalogue objects are linked focus types8/34 on2026-10-21, not a complete independent inventory.',
 'Ozon and other operators are not included.',
 'Population weights are from census2021, not current population2026.',
 'Federal-city population is excluded from ordinary totals; federal WB coordinates are included as candidate destinations.',
 'Selection follows the frozen accepted population axis; it does not independently establish territorial boundaries.']}
assert regional.settlements_with_coordinates.sum()==len(x)
assert size.settlements_with_coordinates.sum()==len(x)
(P/'nearest_wb_summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
print(json.dumps(meta,ensure_ascii=False,indent=2));print(size.to_string(index=False))
