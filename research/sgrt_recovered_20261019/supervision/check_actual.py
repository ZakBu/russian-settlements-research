"""Independent supervisor checks: never imports GIS/data implementation."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np,pandas as pd
O=Path(__file__).resolve().parent;R=O.parent;repo=R.parent.parent
ap=argparse.ArgumentParser();ap.add_argument('--data-only',action='store_true');args=ap.parse_args();checks=[]
def ck(name,condition,**evidence):
 checks.append(dict(test=name,passed=bool(condition),**evidence))
 if not condition:raise AssertionError(checks[-1])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def haversine(lat,lon,lats,lons):
 a,b,aa,bb=np.radians(lat),np.radians(lon),np.radians(lats),np.radians(lons)
 q=np.sin((aa-a)/2)**2+np.cos(a)*np.cos(aa)*np.sin((bb-b)/2)**2
 return 2*6371.0088*np.arcsin(np.sqrt(np.clip(q,0,1)))
sp=repo/'publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz';ck('stage71_sha',sha(sp)=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c')
s=pd.read_csv(sp,usecols=['entity_uid','latitude_2021','longitude_2021','population_2002','population_2010','population_2021']).set_index('entity_uid').sort_index();d=pd.read_parquet(R/'data/panel.parquet').set_index('id').sort_index();ck('all_142570_ids_exact',len(s)==142570 and d.index.equals(s.index))
for y in [2002,2010,2021]:ck(f'all_source_population_values_{y}_exact',np.array_equal(s[f'population_{y}'],d[f'population_{y}']),zeros=int(d[f'population_{y}'].eq(0).sum()),population_sum=float(d[f'population_{y}'].sum()))
ck('all_2010_observed_zeros_retained',np.array_equal(d.population_2010.eq(0),s.population_2010.eq(0)),zeros=int(d.population_2010.eq(0).sum()))
ck('coordinates_exact',np.array_equal(d.lat,s.latitude_2021) and np.array_equal(d.lon,s.longitude_2021))
if not args.data_only:
 finished=json.loads((R/'model/FINISHED.json').read_text());m=pd.read_parquet(R/'model/nearest_membership.parquet').set_index('id').sort_index();c=pd.read_parquet(R/'model/centers.parquet');ag=pd.read_parquet(R/'model/zone_trajectories.parquet');ci=c.set_index('id');ck('model_row_ids_match_all_source',m.index.equals(d.index))
 for y in [2002,2010,2021]:ck(f'model_preserves_source_population_{y}',np.array_equal(m[f'population_{y}'],d[f'population_{y}']))
 ordinary=c[~c.external_anchor].id;ck('all_ordinary_anchors_self_assigned',m.loc[ordinary,'center_id'].eq(ordinary.to_numpy()).all(),ordinary_centers=len(ordinary),all_centers=len(c))
 ck('no_duplicate_center_ids',not c.id.duplicated().any());assigned=m[~m.center_id.eq('UNASSIGNED')];ck('assigned_center_known',assigned.center_id.isin(c.id).all());ck('assigned_max_distance100',assigned.distance_km.le(100+1e-8).all(),maximum=float(assigned.distance_km.max()))
 # All centers, independently recomputed, for a fixed random sample of 600 points.
 sample=assigned.sample(n=min(600,len(assigned)),random_state=20261019);maxerror=0;hufferrors=0;probmaxerror=0
 for sid,row in sample.iterrows():
  ds=haversine(row.lat,row.lon,c.lat.to_numpy(),c.lon.to_numpy());actual_idx=ci.index.get_loc(row.center_id);maxerror=max(maxerror,float(abs(ds[actual_idx]-ds.min())),float(abs(ds[actual_idx]-row.distance_km)))
  ok=ds<=100+1e-9;weights=c.population_2010.to_numpy()[ok]/(ds[ok]+5)**2;ids=c.id.to_numpy()[ok]
  if len(ids):
   w=weights.max();actual=ci.index.get_loc(row.raw_huff_winner);actualweight=float(ci.loc[row.raw_huff_winner,'population_2010'])/(ds[actual]+5)**2
   hufferrors+=not np.isclose(actualweight,w,rtol=1e-10,atol=1e-10);probmaxerror=max(probmaxerror,abs(w/weights.sum()-row.raw_huff_pmax))
 ck('600_all_center_haversine_nearest',maxerror<1e-6,max_absolute_distance_error_km=maxerror,sampled=len(sample));ck('600_all_center_potential_maxima',hufferrors==0,errors=hufferrors);ck('600_all_center_huff_normalization',probmaxerror<1e-8,max_error=probmaxerror)
 parent=c.dropna(subset=['parent_id']);ck('parent_mass_strictly_increases',np.all(parent.parent_id.map(ci.population_2010).to_numpy()>parent.population_2010.to_numpy()))
 for _,row in c.iterrows():
  seen={row.id};p=row.parent_id
  while pd.notna(p):
   if p in seen:raise AssertionError(('hierarchy_cycle',row.id,p))
   seen.add(p);p=ci.loc[p,'parent_id']
 ck('all_parent_chains_acyclic',True)
 g=m.groupby('center_id')[[f'population_{y}' for y in [2002,2010,2021]]].sum();aa=ag.set_index('center_id');ck('zone_membership_set_matches_aggregates',set(g.index)==set(aa.index))
 for y in [2002,2010,2021]:ck(f'exact_zone_population_sums_{y}',np.array_equal(g[f'population_{y}'].sort_index(),aa[f'population_{y}'].sort_index()))
 nested=pd.read_parquet(R/'model/nested_aggregates.parquet')
 for y in [2002,2010,2021]:ck(f'all_nested_levels_conserve_{y}',nested.groupby('aggregation_step')[f'population_{y}'].sum().eq(m[f'population_{y}'].sum()).all())
 dec=pd.read_parquet(R/'model/fixed_dynamic_decomposition.parquet');err=np.abs(dec.observed_dynamic_change-dec.symmetric_demographic_effect-dec.symmetric_reallocation_effect);ck('symmetric_decomposition_identity_all_zones',err.max()<1e-6,max_error=float(err.max()));ck('reallocation_zero_national_balance',dec.groupby('baseline_year').symmetric_reallocation_effect.sum().abs().le(1e-6).all())
 # Operational case review, not predetermined expected numbers from the previous session.
 cases=[];members=m.reset_index();a=ag[ag.center_name.str.contains('Коморгуз|Буланов',case=False,na=False)]
 for _,row in a.iterrows():
  zz=members[members.center_id.eq(row.center_id)].sort_values('population_2010',ascending=False);city=ci.loc[row.center_id];cases.append(dict(center_id=row.center_id,center_name=row.center_name,center_population_2010=row.center_population_2010,n_settlements=int(row.n_settlements),population_2021=row.population_2021,max_distance_km=float(zz.distance_km.max()),largest_member_2010=zz.iloc[0]['name'],largest_member_population2010=zz.iloc[0].population_2010,center_origin=city.center_origin))
 pd.DataFrame(cases).to_csv(O/'sharp_case_audit.csv',index=False)
 empty=c[~c.id.isin(m.center_id)];empty.to_csv(O/'empty_center_audit.csv',index=False);ck('empty_centers_only_external_anchors',empty.external_anchor.all(),empty_centers=len(empty))
for name,path in [('panel',R/'data/panel.parquet')]+([] if args.data_only else [('membership',R/'model/nearest_membership.parquet'),('centers',R/'model/centers.parquet')]):checks.append(dict(test='pin_'+name,passed=True,path=str(path.relative_to(repo)),sha256=sha(path)))
result=dict(status='PASS',checks=checks,passed=len(checks),failed=0,checked_mode='data_only' if args.data_only else 'data_and_model');tmp=O/'actual_checks.json.tmp';tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2));json.loads(tmp.read_text());tmp.replace(O/('data_only_checks.json' if args.data_only else 'actual_checks.json'));print(json.dumps(result,ensure_ascii=False,indent=2))
