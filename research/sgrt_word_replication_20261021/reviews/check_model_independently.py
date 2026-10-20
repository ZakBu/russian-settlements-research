#!/usr/bin/env python3
"""Independent numeric review: no author model functions imported."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
RUN=HERE.parent
REPO=HERE.parents[2]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def close(a,b):return bool(np.allclose(np.asarray(a,float),np.asarray(b,float),rtol=1e-10,atol=1e-7,equal_nan=True))
def main():
 out=RUN/'results';master=REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet'
 before={str(p.relative_to(RUN)):sha(p) for p in [out/'memberships.parquet',out/'systems_all_levels.parquet',out/'hierarchy.csv',out/'functional_count_components.parquet']}
 axis=pd.read_parquet(master,columns=['id','type','population_2002','population_2010','population_2021','population_1989'])
 m=pd.read_parquet(out/'memberships.parquet');s=pd.read_parquet(out/'systems_all_levels.parquet');h=pd.read_csv(out/'hierarchy.csv')
 components=pd.read_parquet(out/'functional_count_components.parquet');mass=pd.read_csv(out/'center_mass_components.csv.gz')
 checks={};details={}
 def put(label,value):checks[label]=bool(value)
 put('axis_rows_142570',len(m)==142570);put('axis_ids_unique',m.id.is_unique);put('axis_ids_order_equal',m.id.equals(axis.id))
 for y in [2002,2010,2021]:put(f'population_{y}_unchanged',m[f'population_{y}'].equals(axis[f'population_{y}']))
 put('all_source_2010_zeros_preserved',m.population_2010.eq(0).sum()==21246)
 put('no_duplicate_system_level_center',not s.duplicated(['level','center_id']).any())
 ids=mass.id.astype(str).to_numpy();uid_to_index=dict(zip(ids,range(len(ids))))
 put('functional_components_ids_equal',components.id.astype(str).equals(mass.id.astype(str)))
 z=np.log1p(components.drop(columns='id').to_numpy(float))
 for j in range(z.shape[1]):
  p=z[:,j][z[:,j]>0];cap=np.quantile(p,.99) if len(p) else 0;z[:,j]=np.minimum(z[:,j],cap)
 expected_mass=z.sum(axis=1)
 put('mass_recomputed_from_11_components',close(expected_mass,mass.own_mass))
 put('mass_has_no_population_components',not any('population' in c for c in components.columns))
 put('candidate_core_self_l1',m.loc[m.candidate_center,'center_id_l1'].equals(m.loc[m.candidate_center,'id']))
 put('unassigned_has_null_id',m.loc[m.center_index_l1.eq(-1),'center_id_l1'].isna().all())
 put('baseline_radius75',m.loc[m.center_index_l1.ge(0),'distance'].le(75+1e-7).all())
 put('pinned_distance0',m.loc[m.pinned,'distance'].eq(0).all())
 levels=sorted(s.level.unique());details['levels']={str(l):int(s.level.eq(l).sum()) for l in levels}
 put('four_levels_present',levels==[1,2,3,4])
 rural=~axis.type.isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 for lev in levels:
  key=f'center_id_l{lev}';assigned=m[key].notna();part=s[s.level.eq(lev)].set_index('center_id')
  put(f'l{lev}_systems_equal_membership_centers',set(m.loc[assigned,key])==set(part.index))
  counts=m.loc[assigned].groupby(key).size().reindex(part.index)
  put(f'l{lev}_settlement_counts',close(counts,part.n_ordinary_settlements))
  rural_external=assigned&rural&m.id.ne(m[key])
  nr=m.loc[rural_external].groupby(key).size().reindex(part.index,fill_value=0)
  put(f'l{lev}_rural_external_counts',close(nr,part.n_rural_external_settlements))
  for y in [2002,2010,2021]:
   pop=axis[f'population_{y}'];sums=pop[assigned].groupby(m.loc[assigned,key]).sum().reindex(part.index)
   put(f'l{lev}_{y}_system_population_recomputed',close(sums,part[f'system_population_{y}']))
   put(f'l{lev}_{y}_national_balance',close(part[f'system_population_{y}'].sum()+pop[~assigned].sum(),pop.sum()))
   centerpop=axis.set_index('id')[f'population_{y}'].reindex(part.index).fillna(0)
   put(f'l{lev}_{y}_center_population',close(centerpop,part[f'center_population_{y}']))
   put(f'l{lev}_{y}_center_external_balance',close(part[f'center_population_{y}']+part[f'external_population_{y}'],part[f'system_population_{y}']))
   rp=pop[rural_external].groupby(m.loc[rural_external,key]).sum().reindex(part.index,fill_value=0)
   put(f'l{lev}_{y}_rural_population',close(rp,part[f'rural_external_population_{y}']))
  known=assigned&axis.population_1989.notna()
  for y in [1989,2002]:
   pair=axis.loc[known,f'population_{y}'].groupby(m.loc[known,key]).sum().reindex(part.index,fill_value=0)
   put(f'l{lev}_paired1989_{y}_fixed_subset',close(pair,part[f'paired_known1989_population_{y}']))
  if lev>1:
   edge=h[h.level.eq(lev)]
   put(f'l{lev}_parent_unique',not edge.child_id.duplicated().any())
   mp=dict(zip(edge.child_id,edge.parent_id));expected=m[f'center_id_l{lev-1}'].map(mp)
   put(f'l{lev}_whole_lower_systems_preserved',expected.fillna('UNASSIGNED').equals(m[key].fillna('UNASSIGNED')))
   nonself=edge.child_id.ne(edge.parent_id)
   put(f'l{lev}_strict_mass_increase',edge.loc[nonself,'parent_mass'].gt(edge.loc[nonself,'child_mass']).all())
   put(f'l{lev}_radius_bound',edge.distance_km.le(edge.search_radius_km+1e-7).all())
 # Recompute all demography labels independently, excluding federal context labels.
 p0=s.system_population_2002.to_numpy(float);p1=s.system_population_2021.to_numpy(float)
 c0=s.center_population_2002.to_numpy(float);c1=s.center_population_2021.to_numpy(float)
 rate=np.full(len(s),np.nan);valid=(p0>0)&(p1>0);rate[valid]=(p1[valid]/p0[valid])**(1/19)-1
 share=np.full(len(s),np.nan);share[valid]=c1[valid]/p1[valid]-c0[valid]/p0[valid]
 put('annual_change_recomputed',close(rate,s.annual_change_2002_2021))
 put('share_change_recomputed',close(share,s.center_share_change_2002_2021))
 trend=np.where(~valid,'zero_endpoint_or_unknown',np.where(rate>.0025,'growth',np.where(rate<-.0025,'decline','stable')))
 concentration=np.where(~valid,'unknown',np.where(share>.02,'concentration',np.where(share<-.02,'deconcentration','stable_share')))
 expected=np.char.add(np.char.add(trend,':'),concentration);ordinary=s.center_axis_kind.eq('ordinary').to_numpy()
 put('demographic_types_recomputed',np.array_equal(expected[ordinary],s.demographic_type.to_numpy()[ordinary]))
 low=s[s.level.eq(1)&s.has_rural_periphery&s.center_axis_kind.eq('ordinary')]
 details['low_rural_systems']=len(low);details['low_rural_type_counts']={str(k):int(v) for k,v in low.demographic_type.value_counts().items()}
 details['assigned_ordinary']=int(m.center_id_l1.notna().sum());details['unassigned_ordinary']=int(m.center_id_l1.isna().sum())
 details['self_core_count']=int(m.pinned.sum());details['self_core_without_any_external_ordinary_members_l1']=int(((s.level.eq(1))&s.center_axis_kind.eq('ordinary')&s.n_ordinary_settlements.eq(1)).sum())
 put('unconstrained_confidence_explicit',all(c in m for c in ['unconstrained_winner_id','unconstrained_top_weight','unconstrained_second_center_id']))
 if 'unconstrained_winner_id' in m:
  details['forced_cores_differing_from_unconstrained_winner']=int((m.pinned & m.id.ne(m.unconstrained_winner_id)).sum())
  noncore=~m.pinned&m.center_id_l1.notna()
  put('noncore_assignment_matches_unconstrained',m.loc[noncore,'center_id_l1'].equals(m.loc[noncore,'unconstrained_winner_id']))
  put('unconstrained_second_not_winner',m.loc[m.unconstrained_second_center_id.notna(),'unconstrained_second_center_id'].ne(m.loc[m.unconstrained_second_center_id.notna(),'unconstrained_winner_id']).all())
 after={str((RUN/k).relative_to(RUN)):sha(RUN/k) for k in before}
 put('checked_output_bytes_stable',before==after)
 result={'reviewer_role':'independent Word-concept guardian','model_functions_imported':False,'checks':checks,'n_checks':len(checks),'n_passed':sum(checks.values()),'all_pass':all(checks.values()),'details':details,'files_sha256':before,'scope':'All axis, aggregation, hierarchy and type rows; no claim that model assignments are observed service flows'}
 (HERE/'independent_model_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
