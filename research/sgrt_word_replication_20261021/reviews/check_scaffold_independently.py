#!/usr/bin/env python3
"""Read-only independent verification of the provisional Word-demographic alternative."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;RUN=HERE.parent;REPO=HERE.parents[2]
def close(a,b):return bool(np.allclose(a,b,rtol=1e-10,atol=1e-7,equal_nan=True))
def main():
 out=RUN/'results/demographic_scaffold';m=pd.read_parquet(out/'memberships.parquet');s=pd.read_parquet(out/'systems_all_levels.parquet');h=pd.read_csv(out/'hierarchy.csv');master=pd.read_parquet(REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',columns=['id','type','settlement_type_2002','municipality_oktmo8_2021','population_2002','population_2010','population_2021'])
 checks={};checks['axis_ids_equal']=m.id.equals(master.id);checks['axis_rows_unique']=len(m)==142570 and m.id.is_unique
 cp=pd.read_parquet(RUN/'results/functional_count_components.parquet').iloc[:142570].drop(columns='id');z=np.log1p(cp.to_numpy(float))
 for j in range(z.shape[1]):
  pos=z[:,j][z[:,j]>0];z[:,j]=np.minimum(z[:,j],np.quantile(pos,.99) if len(pos) else 0)
 expected=z.sum(axis=1)+np.log1p(master.population_2002.to_numpy(float));checks['mass_recomputed_independently']=close(expected,m.own_mass)
 modern=pd.read_parquet(RUN/'results/memberships.parquet',columns=['id','candidate_center'])
 urban=master.settlement_type_2002.isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 maxima=master.assign(idx=np.arange(len(master))).sort_values(['municipality_oktmo8_2021','population_2002','id'],ascending=[True,False,True]).drop_duplicates('municipality_oktmo8_2021').idx.to_numpy();provisional=np.zeros(len(m),bool);provisional[maxima]=True
 candidate=modern.candidate_center.to_numpy()|urban.to_numpy()|provisional
 checks['candidate_rule_recomputed']=bool(np.array_equal(candidate,m.candidate_center));checks['provisional_maximum_rule_recomputed']=bool(np.array_equal(provisional,m.provisional_municipal_maximum))
 checks['candidates_self_pinned']=m.loc[m.candidate_center,'id'].equals(m.loc[m.candidate_center,'center_id_l1'])
 for lev in [1,2,3,4]:
  key=f'center_id_l{lev}';assigned=m[key].notna();t=s[s.level.eq(lev)].set_index('center_id');checks[f'l{lev}_centers_unique']=t.index.is_unique
  checks[f'l{lev}_counts_recomputed']=close(m.loc[assigned].groupby(key).size().reindex(t.index),t.n_ordinary_settlements)
  for y in [2002,2010,2021]:
   expected=master.loc[assigned,f'population_{y}'].groupby(m.loc[assigned,key]).sum().reindex(t.index)
   checks[f'l{lev}_{y}_population_recomputed']=close(expected,t[f'system_population_{y}'])
   checks[f'l{lev}_{y}_national_balance']=close(expected.sum()+master.loc[~assigned,f'population_{y}'].sum(),master[f'population_{y}'].sum())
  if lev>1:
   edge=h[h.level.eq(lev)];mapping=dict(zip(edge.child_id,edge.parent_id));prediction=m[f'center_id_l{lev-1}'].map(mapping)
   checks[f'l{lev}_whole_lower_memberships']=prediction.fillna('UNASSIGNED').equals(m[key].fillna('UNASSIGNED'))
   checks[f'l{lev}_parent_unique']=not edge.child_id.duplicated().any()
   nonself=edge.child_id.ne(edge.parent_id);checks[f'l{lev}_strict_mass_ascent']=bool(edge.loc[nonself,'parent_mass'].gt(edge.loc[nonself,'child_mass']).all())
   checks[f'l{lev}_radius']=bool(edge.distance_km.le(edge.search_radius_km+1e-7).all())
 low=s[s.level.eq(1)&s.has_rural_periphery&s.center_axis_kind.eq('ordinary')]
 checks={k:bool(v) for k,v in checks.items()}
 result={'checks':checks,'n_checks':len(checks),'n_passed':sum(checks.values()),'all_pass':all(checks.values()),'ordinary_assigned':int(m.center_id_l1.notna().sum()),'ordinary_unassigned':int(m.center_id_l1.isna().sum()),'candidate_centers':int(m.candidate_center.sum()),'provisional_unsupported_by_function_or_urban':int((m.provisional_municipal_maximum&~m.candidate_supported_by_function_or_urban_status).sum()),'levels':{str(l):int(s.level.eq(l).sum()) for l in [1,2,3,4]},'rural_systems_l1':len(low),'rural_decline_concentration':int(low.demographic_type.eq('decline:concentration').sum()),'membership_sha256':hashlib.sha256((out/'memberships.parquet').read_bytes()).hexdigest(),'scope':'A separate provisional demographic/urban scaffold, not empirical confirmation of functional centrality'}
 (HERE/'independent_scaffold_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
