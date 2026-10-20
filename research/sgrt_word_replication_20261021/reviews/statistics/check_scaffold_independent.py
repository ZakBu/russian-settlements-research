#!/usr/bin/env python3
"""Independent demographic scaffold audit, not functional validation."""
from pathlib import Path
import numpy as np,pandas as pd,json,hashlib,time
from sklearn.neighbors import BallTree
BASE=Path(__file__).resolve().parents[2];OLD=BASE.parent/'sgrt_national_integration_20261019';OUT=BASE/'reviews/statistics';S=BASE/'results/demographic_scaffold';checks=[];t=time.monotonic()
def ck(name,ok,**info):checks.append({'check':name,'pass':bool(ok),**info})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def hav(a,b):
 # radians [lat,lon] to vector; independent scalar origin broadcast.
 da=b[:,0]-a[0];dl=b[:,1]-a[1];h=np.sin(da/2)**2+np.cos(a[0])*np.cos(b[:,0])*np.sin(dl/2)**2
 return 2*6371.0088*np.arcsin(np.sqrt(np.clip(h,0,1)))
d=pd.read_parquet(OLD/'core/feature_master.parquet');fed=pd.read_csv(OLD/'core/external_federal_features.csv');N=len(d)
m=pd.read_parquet(S/'memberships.parquet');sysrows=pd.read_parquet(S/'systems_all_levels.parquet');edges=pd.read_csv(S/'hierarchy.csv')
ck('scaffold_all142570_UID_order',len(m)==142570 and m.id.equals(d.id) and m.id.is_unique)
# Counts were independently rederived in base check; cap again on ordinary axis only, as scaffold specifies.
c=pd.read_parquet(BASE/'results/functional_count_components.parquet');groups=[x for x in c if x!='id'];arr=np.log1p(c.loc[:N-1,groups].to_numpy())
for j in range(arr.shape[1]):
 pos=arr[:,j][arr[:,j]>0]
 if len(pos):arr[:,j]=np.fmin(arr[:,j],np.percentile(pos,99))
fm=arr.sum(axis=1);expected_mass=fm+np.log1p(d.population_2002.fillna(0).values)
ck('scaffold_mass_only_own_functions_plusP2002',np.allclose(expected_mass,m.own_mass.values,atol=1e-13,rtol=1e-13))
base=(c.loc[:N-1,groups].gt(0).sum(axis=1).values>=2)|d.places_baseline_school_count.gt(0).values|d.places_baseline_hospital_count.gt(0).values
urban=d.settlement_type_2002.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок']).values
# Separate stable tie-break, no source idx imported.
ranked=d[['id','municipality_oktmo8_2021','population_2002']].copy().reset_index(names='row')
maxima=ranked.sort_values(['municipality_oktmo8_2021','population_2002','id'],ascending=[True,False,True]).groupby('municipality_oktmo8_2021',sort=False).head(1).row.values
provisional=np.zeros(N,bool);provisional[maxima]=True;candidate=base|urban|provisional
ck('municipal_maxima_provisional_flags',np.array_equal(provisional,m.provisional_municipal_maximum.values),n_provisional=int(provisional.sum()))
ck('scaffold_candidate_union_rederived',np.array_equal(candidate,m.candidate_center.values),n_candidates=int(candidate.sum()))
ck('support_flags_nofalsefunctionalclaim',np.array_equal(base|urban,m.candidate_supported_by_function_or_urban_status.values),unsupported_maxima=int((provisional&~base&~urban).sum()))
allids=np.r_[d.id.values,fed.id.values];mass=np.r_[expected_mass,np.log1p(fed.population_2002.values)];coords=np.deg2rad(np.vstack([d[['lat','lon']].values,fed[['lat','lon']].values]));ci=np.flatnonzero(np.r_[candidate,np.ones(len(fed),bool)])
# All ordinary winners by independent BallTree angular distance.
tree=BallTree(coords[ci],metric='haversine');chosen=np.full(N,-1,int)
for start in range(0,N,4096):
 inds,dists=tree.query_radius(coords[start:min(start+4096,N)],r=75/6371.0088,return_distance=True)
 for off,(ix,dist) in enumerate(zip(inds,dists)):
  i=start+off
  if candidate[i]:chosen[i]=i;continue
  if len(ix):
   ids=ci[ix];weights=mass[ids]*np.exp(-dist*6371.0088/15);chosen[i]=ids[np.lexsort((ids,-weights))[0]]
ck('allordinary_scaffold_winners_BallTree',np.array_equal(chosen,m.center_index_l1.values))
for level in [2,3,4]:
 e=edges[edges.level.eq(level)];previous=m[f'center_index_l{level-1}'].values;current=m[f'center_index_l{level}'].values
 mapping=e.set_index('child_index').parent_index.to_dict();expected=np.array([mapping[x] if x>=0 else -1 for x in previous])
 ck(f'level{level}_whole_children_preserved',np.array_equal(expected,current));ck(f'level{level}_unique_parent',e.child_index.is_unique)
 non=e[e.child_index.ne(e.parent_index)];ck(f'level{level}_strict_mass_increase',non.parent_mass.gt(non.child_mass).all())
 ck(f'level{level}_search_radius',e.distance_km.le(e.search_radius_km+1e-8).all())
 active=e.child_index.values;threshold=e.mass_threshold.iloc[0];radius=e.search_radius_km.iloc[0];eligible=active[mass[active]>=threshold]
 bad=[]
 for row in e.itertuples():
  expected=row.child_index
  if mass[row.child_index]<threshold and len(eligible):
   distances=hav(coords[row.child_index],coords[eligible]);ok=(distances<=radius+1e-8)&(mass[eligible]>mass[row.child_index])
   if ok.any():
    ii=eligible[ok];weights=mass[ii]*np.exp(-distances[ok]/(radius/3));expected=ii[np.lexsort((ii,-weights))[0]]
  if expected!=row.parent_index:bad.append(int(row.child_index))
 ck(f'level{level}_allparent_exactwinner',not bad,n_bad=len(bad))
for level in [1,2,3,4]:
 assignment=m[f'center_index_l{level}'].values;valid=assignment>=0;s=sysrows[sysrows.level.eq(level)].set_index('center_index')
 ck(f'level{level}_center_set',set(s.index)==set(assignment[valid]))
 for year in [2002,2010,2021]:
  population=d[f'population_{year}'].values;expected=pd.Series(population[valid]).groupby(assignment[valid]).sum()
  ck(f'level{level}_{year}_all_system_sums',np.array_equal(s.loc[expected.index,f'system_population_{year}'].values,expected.values))
  ck(f'level{level}_{year}_allpopulationbalance',float(s[f'system_population_{year}'].sum()+population[~valid].sum())==float(population.sum()))
 # Explicit zero for federal context own population; ordinary own populations exact.
 for year in [2002,2010,2021]:
  population=d[f'population_{year}'].values;own=np.zeros(len(s));ordinary=s.index.values<N;own[ordinary]=population[s.index.values[ordinary]]
  ck(f'level{level}_{year}_own_and_external',np.array_equal(own,s[f'center_population_{year}'].values) and np.array_equal(s[f'external_population_{year}'].values,s[f'system_population_{year}'].values-own))
receipt=json.load(open(S/'receipt.json'))
ck('scaffold_truthful_scope_label','not actual functional catchments' in receipt['scope'] and 'modern municipality' in receipt['scope'])
ck('no_catchment_outcome_mass_training',receipt['mass_fitted_to_catchments'] is False)
report={'status':'PASS_PROVISIONAL_DEMOGRAPHIC_SCAFFOLD_ONLY' if all(x['pass'] for x in checks) else 'REVISE','checks':checks,'n_checks':len(checks),'n_failed':sum(not x['pass'] for x in checks),'independent_method':'Independently reconstruct source-defined candidates and currentmunicipalityP2002maxima; all142570winners by BallTreehaversine; every higher parent across full eligible pool; complete nested sums/own-external balances. No author function import.','limits':['Largest modernmunicipality settlement is provisional scenario, not evidenced administrative/service center','No selection of this model on disclosed local documentmatchscore','OwnP2002mass avoids direct futurepopulationinput but contemporary functionalcomponents and modernmunicipalitysupport prevent historical causal interpretation','Scaffold is a Wordaligned morphology/population alternative and does not replace functionalmodel or validate actualfunctionalcatchments'],'seconds':round(time.monotonic()-t,3),'input_sha256':{str(p.relative_to(BASE)):sha(p) for p in [S/'memberships.parquet',S/'hierarchy.csv',S/'systems_all_levels.parquet']},'script_sha256':sha(Path(__file__))}
(OUT/'independent_scaffold_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps({'status':report['status'],'n_checks':len(checks),'n_failed':report['n_failed'],'seconds':report['seconds']},ensure_ascii=False))
