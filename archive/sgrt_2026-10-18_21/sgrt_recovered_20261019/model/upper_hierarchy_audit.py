"""Separate hierarchy sensitivity. Does not modify primary basins or their centers."""
from pathlib import Path
import numpy as np,pandas as pd,json,hashlib
from scipy.spatial import cKDTree
from run_model import xyz,chord,km,export
O=Path(__file__).resolve().parent;c=pd.read_parquet(O/'centers.parquet');s=pd.read_parquet(O/'nearest_membership.parquet');z=pd.read_parquet(O/'zone_trajectories.parquet');coords=xyz(c.lat,c.lon);mass=c.population_2010.to_numpy();tree=cKDTree(coords);best=np.full(len(c),-1,int);ratio=np.zeros(len(c))
for i,nb in enumerate(tree.query_ball_point(coords,chord(100),workers=2)):
 nb=np.array([j for j in nb if mass[j]>mass[i]],int)
 if len(nb):
  dd=km(np.linalg.norm(coords[nb]-coords[i],axis=1));a=mass[nb]/(dd+5)**2;j=np.argmax(a);best[i]=nb[j];ratio[i]=a[j]/(mass[i]/25)
summary=[];audits=[];sc=xyz(s.lat,s.lon);lookup=dict(zip(c.id,range(len(c))));membercenter=s.center_id.map(lookup);valid=membercenter.notna().to_numpy();mci=membercenter[valid].to_numpy(int)
for threshold in [.1,.5,1]:
 parent=np.where(ratio>threshold,best,-1);roots=[];depths=[]
 for i in range(len(c)):
  chain=[i]
  while parent[chain[-1]]>=0:chain.append(parent[chain[-1]]);assert len(chain)<=len(c)
  roots.append(chain[-1]);depths.append(len(chain)-1)
 rootdist=km(np.linalg.norm(sc[valid]-coords[np.array(roots)[mci]],axis=1));assert all(j<0 or mass[j]>mass[i] for i,j in enumerate(parent));summary.append(dict(threshold=threshold,n_parent_edges=int((parent>=0).sum()),max_depth=max(depths),n_roots=int((parent<0).sum()),member_to_root_median_km=float(np.median(rootdist)),member_to_root_p95_km=float(np.quantile(rootdist,.95)),member_to_root_max_km=float(rootdist.max())))
 a=c[['id','name','region','lat','lon','population_2010']].copy();a['threshold']=threshold;a['parent_id']=[c.id.iloc[j] if j>=0 else None for j in parent];a['root_id']=[c.id.iloc[j] for j in roots];a['depth_to_root']=depths;a['external_to_self_field_ratio']=ratio;audits.append(a)
export(pd.concat(audits,ignore_index=True),O/'upper_hierarchy_sensitivity.parquet');pd.DataFrame(summary).to_csv(O/'upper_hierarchy_sensitivity_summary.csv',index=False)
empty=c[~c.id.isin(set(s.center_id))].copy();empty['cohort_members']=0;empty['population_outcome_added']=0;export(empty,O/'empty_center_ledger.parquet')
case=z[z.center_name.str.contains('Коморгуз|Буланов',case=False,na=False)].copy();export(case,O/'illustrative_case_recomputed.parquet')
config=dict(primary_baseline=2010,coordinates='frozen2021',source2010_values='all retained including zeros; no metadata-based exclusions',candidates='all2010urban with positive2010 mass plus positive rural local maxima10km and2externalterritoryanchors',urban_statuses=['город','пгт','посёлок городского типа','рабочий посёлок'],rural_origin='not verified administrative center',nearest_primary_radius_km=100,huff=dict(mass='population2010',alpha=1,beta=2,d0_km=5,radius_km=100,score_is_not_nearest_assignment_probability=True),upper_parent_rule='strongest greater2010mass center within100km with external/self field ratio>1',sensitivity_parent_ratio_thresholds=[.1,.5,1],dynamic2021='candidate list reselected using raw population2021/status2021, same coordinates and cohort; nearest2010geometry fixed comparison retained',outcomes='external mass not added to cohort; empty external anchors tracked separately; UNASSIGNED residual included',interpretation='geometric potential and calculated membership; not measured service or labor flows')
(O/'config.json').write_text(json.dumps(config,indent=2,ensure_ascii=False));print(json.dumps(dict(sensitivity=summary,n_empty_centers=len(empty),illustrative_case_rows=len(case)),ensure_ascii=False))
