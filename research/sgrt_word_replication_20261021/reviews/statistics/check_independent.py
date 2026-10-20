#!/usr/bin/env python3
"""Independent verifier: rederive sources, haversine winners, balances and typology.
Does not import author model functions or trust author assert/receipt values.
"""
from pathlib import Path
import hashlib,json,sys,time
import numpy as np,pandas as pd,pyarrow.parquet as pq
BASE=Path(__file__).resolve().parents[2]
REPO=BASE.parents[1]
OLD=REPO/'research/sgrt_national_integration_20261019'
OUT=BASE/'reviews/statistics';OUT.mkdir(parents=True,exist_ok=True)
checks=[];details={};start=time.monotonic()
def ck(name,ok,**info):
 checks.append({'check':name,'pass':bool(ok),**info})
 print(name, bool(ok), info,flush=True)
def hashfile(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def hav(lat,lon,clat,clon):
 a=np.deg2rad(lat);b=np.deg2rad(clat);da=b-a;dl=np.deg2rad(clon-lon)
 return 6371.0088*2*np.arctan2(np.sqrt(np.clip(np.sin(da/2)**2+np.cos(a)*np.cos(b)*np.sin(dl/2)**2,0,1)),np.sqrt(np.clip(1-(np.sin(da/2)**2+np.cos(a)*np.cos(b)*np.sin(dl/2)**2),0,1)))
master=OLD/'core/feature_master.parquet'
ck('master_hash',hashfile(master)=='8c98d5a113eec4c3bf131232b1d7e5c6362dc3a50ee484e964420de58c377f85')
cols=pq.ParquetFile(master).schema.names
use=[c for c in cols if c in ['id','name','type','region','lat','lon','population_1989','municipality_oktmo8_2021'] or c.startswith(('population_2002','population_2010','population_2021','places_baseline_','econ_native_2025_','wb_strict_focus'))]
d=pd.read_parquet(master,columns=use)
m=pd.read_parquet(BASE/'results/memberships.parquet')
fed=pd.read_csv(OLD/'core/external_federal_features.csv');N=len(d)
ck('all_ordinary_uid_retained',len(m)==142570 and m.id.is_unique and m.id.tolist()==d.id.tolist())
for y in [2002,2010,2021]:
 ck(f'raw_population_{y}_unchanged',np.array_equal(m[f'population_{y}'].values,d[f'population_{y}'].values,equal_nan=True))
ck('2010_observed_zeros',int(m.population_2010.eq(0).sum())==21246,n_zeros=int(m.population_2010.eq(0).sum()))
ck('modern_axis_all_population_observed',all(d[f'population_{y}'].notna().all() for y in [2002,2010,2021]))
ck('all_historical_boundary_flags_false',not m.boundary_historical_presence_asserted.any())
allids=np.r_[d.id.values,fed.id.values];lat=np.r_[d.lat.values,fed.lat.values];lon=np.r_[d.lon.values,fed.lon.values]
legal={'trade_access':'retail47','food_service':'food56','education':'education85','healthcare':'health86','social_care':'social8788','repair':'repair95','personal':'personal96'}
physical={'trade_access':['retail_store','market'],'food_service':['food_service'],'education':['school','preschool','other_education'],'healthcare':['hospital','healthcare'],'veterinary':['veterinary'],'pharmacy':['pharmacy'],'banking':['bank','atm'],'postal_service':['post_office','postal_collection_point']}
groups=['trade_access','food_service','education','healthcare','social_care','repair','personal','veterinary','pharmacy','banking','postal_service']
count_components={}
for g in groups:
 a=np.zeros(N+len(fed));b=np.zeros_like(a)
 if g in legal:
  a[:N]=d[f'econ_native_2025_{legal[g]}_legal_entities'].fillna(0)
  f=f'econ_legacy_federal_2021_federal_coded_baseline_{legal[g]}_legal_entities'
  if f in fed:a[N:]=fed[f].fillna(0)
 for p in physical.get(g,[]):b[:N]+=d[f'places_baseline_{p}_count'].fillna(0).values
 if g=='trade_access':b[:N]=np.maximum(b[:N],d.wb_strict_focus_types_locations.fillna(0))
 count_components[g]=np.maximum(a,b)
c=pd.DataFrame(count_components);z=np.log1p(c.values);caps=[]
for j in range(len(groups)):
 v=z[:,j];pos=v[v>0];cap=np.percentile(pos,99) if len(pos) else 0;caps.append(cap);z[:,j]=np.fmin(v,cap)
rederived=z.sum(axis=1)
savedc=pd.read_parquet(BASE/'results/functional_count_components.parquet')
ck('all_source_count_components_exact',np.allclose(c.values,savedc[groups].values,rtol=0,atol=0))
ck('mass_all_sources_independent_rederivation',np.allclose(m.own_functional_mass.values,rederived[:N],rtol=1e-13,atol=1e-13),max_abs=float(np.max(abs(m.own_functional_mass.values-rederived[:N]))))
# Check executable source only restricts the baseline formula. Scenario P2002 is explicitly separate.
source=(BASE/'model/run_model.py').read_text();countsbody=source[source.index('def counts('):source.index('def assign(')]
ck('mass_functions_no_population_or_outcome_or_catchment',not any(x in countsbody for x in ['population','assignment','center_id','system_population']))
anchors=d.places_baseline_school_count.fillna(0).gt(0)|d.places_baseline_hospital_count.fillna(0).gt(0)
candidate=(c.gt(0).sum(axis=1).to_numpy()>=2);candidate[:N]|=anchors.values;candidate[N:]=True
ck('candidate_rule_rederived',np.array_equal(candidate[:N],m.candidate_center.values))
ci=np.flatnonzero(candidate);idindex={u:i for i,u in enumerate(allids)}
# Deterministic nationwide spatially varied sample, every ordinary row eligible before subsampling.
rng=np.random.default_rng(20261021);sample=np.unique(np.r_[np.linspace(0,N-1,200,dtype=int),rng.choice(N,200,replace=False),np.flatnonzero(d.lon.abs().gt(170))[:20]])
rows=[];bad=[]
for i in sample:
 distances=hav(lat[i],lon[i],lat[ci],lon[ci]);eligible=distances<=75+1e-9
 if eligible.any():
  ids=ci[eligible];scores=rederived[ids]*np.exp(-distances[eligible]/15)
  order=np.lexsort((ids,-scores));winner=ids[order[0]];nonforcedwinner=winner
 else:winner=-1;nonforcedwinner=-1
 if candidate[i]:winner=i
 got=int(m.center_index_l1.iloc[i]);ok=got==winner
 rows.append({'index':int(i),'id':allids[i],'expected_center_index':int(winner),'actual_center_index':got,'unforced_winner_index':int(nonforcedwinner),'pinned':bool(candidate[i]),'pass':bool(ok)})
 if not ok:bad.append(rows[-1])
pd.DataFrame(rows).to_csv(OUT/'independent_sample_gravity_winners.csv',index=False)
ck('sample_gravity_all_radius_winners',not bad,n_sample=len(sample),n_mismatch=len(bad))
mask=m.center_index_l1.ge(0)
ck('assigned_distance_max75',m.loc[mask,'distance'].le(75+1e-8).all(),max_km=float(m.distance.max()))
# Recompute actual assigned distances separately, including antimeridian handling.
a=m.center_index_l1.values;valid=a>=0
actual_dist=hav(d.lat.values[valid],d.lon.values[valid],lat[a[valid]],lon[a[valid]])
ck('all_assigned_distances_independent_haversine',np.allclose(actual_dist,m.distance.values[valid],rtol=1e-8,atol=1e-7),max_error_km=float(np.max(np.abs(actual_dist-m.distance.values[valid]))))
ck('all_candidate_cores_retained',np.array_equal(m.loc[candidate[:N],'center_index_l1'].values,np.flatnonzero(candidate[:N])))
edges=pd.read_csv(BASE/'results/hierarchy.csv');sysrows=pd.read_parquet(BASE/'results/systems_all_levels.parquet')
for level in [2,3,4]:
 e=edges[edges.level.eq(level)];previous=m[f'center_index_l{level-1}'].values;current=m[f'center_index_l{level}'].values
 mapping=e.set_index('child_index').parent_index.to_dict()
 expected=np.array([mapping[x] if x>=0 else -1 for x in previous]);ck(f'level{level}_whole_lower_membership_preserved',np.array_equal(expected,current))
 ck(f'level{level}_one_parent_per_child',e.child_index.is_unique)
 non=e[e.child_index.ne(e.parent_index)]
 ck(f'level{level}_strict_parent_mass_increase',non.parent_mass.gt(non.child_mass).all())
 ck(f'level{level}_radius',e.distance_km.le(e.search_radius_km+1e-8).all())
 # Check exact all eligible winners; catches any nearest64 truncation.
 active=np.unique(previous[previous>=0]);threshold=e.mass_threshold.iloc[0];radius=e.search_radius_km.iloc[0];eligible=active[rederived[active]>=threshold]
 mismatches=[]
 for row in e.itertuples():
  u=row.child_index;expected_parent=u
  if rederived[u]<threshold and len(eligible):
   distances=hav(lat[u],lon[u],lat[eligible],lon[eligible]);ok=(distances<=radius+1e-9)&(rederived[eligible]>rederived[u])
   if ok.any():
    ids=eligible[ok];scores=rederived[ids]*np.exp(-distances[ok]/(radius/3));expected_parent=int(ids[np.lexsort((ids,-scores))[0]])
  if expected_parent!=row.parent_index:mismatches.append({'level':level,'child':int(u),'actual':int(row.parent_index),'expected':int(expected_parent)})
 ck(f'level{level}_all_eligible_parent_winners',not mismatches,n_mismatch=len(mismatches))
 if mismatches:details[f'level{level}_parent_mismatches']=mismatches
for level in [1,2,3,4]:
 assignment=m[f'center_index_l{level}'].values;assigned=assignment>=0;s=sysrows[sysrows.level.eq(level)].set_index('center_index')
 ck(f'level{level}_reported_center_set',set(s.index)==set(assignment[assigned]))
 for y in [2002,2010,2021]:
  source=d[f'population_{y}'].values;expected=pd.Series(source[assigned]).groupby(assignment[assigned]).sum()
  ck(f'level{level}_{y}_all_system_sums',np.array_equal(s.loc[expected.index,f'system_population_{y}'].values,expected.values))
  unassigned=float(source[~assigned].sum());ck(f'level{level}_{y}_population_conservation',float(s[f'system_population_{y}'].sum())+unassigned==float(source.sum()),assigned=float(expected.sum()),unassigned=unassigned,total=float(source.sum()))
  center=np.zeros(len(s));ordinary=s.index.values<N;center[ordinary]=source[s.index.values[ordinary]]
  ck(f'level{level}_{y}_center_external_balance',np.array_equal(s[f'center_population_{y}'].values,center) and np.array_equal(s[f'external_population_{y}'].values,s[f'system_population_{y}'].values-center))
# Independent labels, explicitly handle zero endpoints without arbitrary pseudocounts.
labels=[]
for row in sysrows.itertuples():
 if row.center_axis_kind!='ordinary':expected='federal_context_center_not_comparable'
 else:
  if row.system_population_2002>0 and row.system_population_2021>0:
   annual=(row.system_population_2021/row.system_population_2002)**(1/19)-1
   trend='growth' if annual>.0025 else 'decline' if annual<-.0025 else 'stable'
  else:trend='zero_endpoint_or_unknown'
  if row.system_population_2002>0 and row.system_population_2021>0:
   diff=row.center_population_2021/row.system_population_2021-row.center_population_2002/row.system_population_2002
   concentration='concentration' if diff>.02 else 'deconcentration' if diff<-.02 else 'stable_share'
  else:concentration='unknown'
  expected=trend+':'+concentration
 labels.append(expected)
ck('all_typology_labels_independent',labels==sysrows.demographic_type.tolist(),n_rows=len(labels))
# Municipal split denominator includes outside-model records; compare its valid totals.
pairs=pd.read_parquet(BASE/'results/municipal_overlap.parquet');mun=d.groupby('municipality_oktmo8_2021').population_2002.sum()
ck('municipality_denominator_includes_unassigned',np.allclose(pairs.share_of_municipality.values,pairs.overlap_population2002.values/pairs.municipality_oktmo8_2021.map(mun).replace(0,np.nan).values,equal_nan=True))
# Receipt status is the verdict of this checker, not of the scientific empirical construct.
report={'status':'PASS_IMPLEMENTATION_WITH_SCOPE_LIMITS' if all(c['pass'] for c in checks) else 'REVISE','independence':'No import of author calculations; source mass recomputed, sample winners all-radius haversine, parents all-eligible, sums and labels independently recomputed','checks':checks,'details':details,'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'seconds':round(time.monotonic()-start,3),'checker_sha256':hashfile(Path(__file__)),'inputs':{str(p.relative_to(REPO)):hashfile(p) for p in [master,BASE/'results/memberships.parquet',BASE/'results/systems_all_levels.parquet',BASE/'results/hierarchy.csv']},'scientific_limits':['Does not establish real travel/service flows','Source coverage strongly city-biased','Distances are not road travel times','Contemporary functions projected over historic demography are not historical service boundaries','Existing documents are post-development external checks, not blind holdout'],'regression':'Pending separate review when available'}
(OUT/'independent_model_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
(OUT/'VERDICT.md').write_text('# Независимая вычислительная проверка\n\n'+report['status']+'\n\n'+f"Проверено {len(checks)} условий; не пройдено {report['n_failed']}. Победители пересчитаны независимо по всем кандидатам в радиусе для {len(sample)} НП. Все родительские назначения проверены по полному множеству подходящих узлов, типология и балансы — по всей оси.\n\n"+'\n'.join('- '+c['check'] for c in checks if not c['pass'])+'\n\nПроверка реализации не доказывает наблюдаемые районы обслуживания; ограничения источников, расстояний и времени остаются.\n')
print(json.dumps({'status':report['status'],'n_checks':len(checks),'n_failed':report['n_failed']},ensure_ascii=False))
