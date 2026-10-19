"""Coordinator's independent check of2002 masses, nearest and potential, no GIS import."""
from pathlib import Path
import json
import numpy as np,pandas as pd
R=Path(__file__).resolve().parent;m=pd.read_parquet(R/'model2002/nearest_membership.parquet');c=pd.read_parquet(R/'model2002/centers.parquet');z=pd.read_parquet(R/'model2002/nested_aggregates.parquet');p=pd.read_parquet(R/'data/panel.parquet');checks=[]
def check(name,ok):
    assert ok,name;checks.append({'test':name,'passed':True})
check('all panel rows',len(m)==142570 and set(m.id)==set(p.id))
check('2002 ordinary masses exact',c.loc[~c.external_anchor].set_index('id').population_2002.eq(p.set_index('id').population_2002.reindex(c.loc[~c.external_anchor,'id'])).all())
for year in [2002,2010,2021]:
    check('nested conserved '+str(year),all(g[f'population_{year}'].sum()==p[f'population_{year}'].sum() for _,g in z.groupby('aggregation_step')))
sample=m.sample(600,random_state=20022026);la=np.radians(c.lat.to_numpy());lo=np.radians(c.lon.to_numpy());mass=c.population_2002.to_numpy();bad_nearest=bad_field=bad_probability=0
for row in sample.itertuples():
    a,b=np.radians(row.lat),np.radians(row.lon);v=np.sin((la-a)/2)**2+np.cos(la)*np.cos(a)*np.sin((lo-b)/2)**2;dist=2*6371.0088*np.arcsin(np.sqrt(np.clip(v,0,1)))
    actual=c.id.eq(row.center_id).to_numpy();mine=dist[actual].min() if actual.any() else np.inf
    if row.id not in set(c.id):bad_nearest+=int((dist.min()<=100 and abs(mine-dist.min())>1e-7) or (dist.min()>100 and row.center_id!='UNASSIGNED'))
    w=np.where(dist<=100,mass/(dist+5)**2,0);largest=w.max();winners=c.id.to_numpy()[np.isclose(w,largest,rtol=1e-12,atol=0)] if largest>0 else ['UNASSIGNED'];bad_field+=int(row.raw_huff_winner not in winners)
    expected=largest/w.sum() if w.sum()>0 else 0;bad_probability+=int(abs(expected-row.raw_huff_pmax)>1e-8)
check('600 all centres independent nearest',bad_nearest==0);check('600 all centres independent2002 potential winner',bad_field==0);check('600 independent2002 probability',bad_probability==0)
out={'passed':len(checks),'failed':0,'sample_n':600,'checks':checks,'interpretation':'2002-specific demography, no use of2010/2021 as center mass'};(R/'model2002/independent_coordinator_audit.json').write_text(json.dumps(out,indent=2));print(json.dumps(out))
