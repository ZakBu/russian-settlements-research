"""Independent recovered model audit. Author built input panel, NOT GIS/agri/RFSD model.
No model implementation imported. All2010 raw values and zeros retained.
"""
from pathlib import Path
import argparse,time,json,hashlib
import numpy as np,pandas as pd
from scipy.spatial import cKDTree
EARTH=6371.0088

def equal_area6933(lon,lat):
 """WGS84 ellipsoidal Lambert cylindrical equal area, standard parallel30deg (EPSG6933)."""
 semimajor=6378137.;ecc2=0.0066943799901413165;ecc=np.sqrt(ecc2);k0=np.cos(np.pi/6)/np.sqrt(1-ecc2*np.sin(np.pi/6)**2);phi=np.radians(lat);s=np.sin(phi);q=(1-ecc2)*(s/(1-ecc2*s*s)-np.log((1-ecc*s)/(1+ecc*s))/(2*ecc));return semimajor*k0*np.radians(lon),semimajor*q/(2*k0)
def haversine(lat,lon,lat0,lon0):
 la,lo=np.radians(lat),np.radians(lon);a,b=np.radians(lat0),np.radians(lon0)
 return 2*EARTH*np.arcsin(np.sqrt(np.clip(np.sin((la-a)/2)**2+np.cos(la)*np.cos(a)*np.sin((lo-b)/2)**2,0,1)))
def spatial_blockfit(f,ycol,features,label,size,rng,reps=399):
 f=f.replace([np.inf,-np.inf],np.nan).dropna(subset=[ycol,*features,'x','y']).copy();y=f[ycol].to_numpy();x=f[features].to_numpy();mu=x.mean(0);sd=x.std(0);sd[sd==0]=1;x=np.c_[np.ones(len(x)),(x-mu)/sd];blocks=pd.MultiIndex.from_arrays([np.floor(f.x/(size*1000)).astype(int),np.floor(f.y/(size*1000)).astype(int)]);codes,ids=pd.factorize(blocks);nb=len(ids);xx=np.zeros((nb,x.shape[1],x.shape[1]));xy=np.zeros((nb,x.shape[1]));n=np.bincount(codes)
 for k in range(nb):z=codes==k;xx[k]=x[z].T@x[z];xy[k]=x[z].T@y[z]
 coef=np.linalg.lstsq(x,y,rcond=None)[0];boot=[]
 for _ in range(reps):i=rng.integers(0,nb,nb);boot.append(np.linalg.pinv(xx[i].sum(0))@xy[i].sum(0))
 lo,hi=np.quantile(np.asarray(boot),[.025,.975],axis=0)
 return dict(label=label,outcome=ycol,block_km=size,n=len(f),n_blocks=nb,repetitions=reps,seed=20261019,features=features,coefficients={s:dict(coefficient=float(coef[i]),CI025=float(lo[i]),CI975=float(hi[i])) for i,s in enumerate(['intercept']+features)},predictor_mean=mu.tolist(),predictor_sd=sd.tolist(),largest_block_share=float(n.max()/len(f)),method='pairs whole spatial-block bootstrap, EPSG6933, conditional observational association, no iid P values')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent);ap.add_argument('--wait-seconds',type=int,default=300);ap.add_argument('--bootstrap-reps',type=int,default=399);args=ap.parse_args();root=args.root.resolve();o=root/'statistics';o.mkdir(exist_ok=True);m=root/'model';deadline=time.time()+args.wait_seconds
 while not ((m/'FINISHED.json').exists() or (m/'SOURCE_READY.json').exists()):
  if time.time()>deadline:raise RuntimeError('GIS final immutable FINISHED marker not available by deadline; validation not claimed')
  time.sleep(2)
 rng=np.random.default_rng(20261019);checks=[]
 def ck(name,ok,details=None):checks.append({'test':name,'passed':bool(ok),'details':details})
 panel=pd.read_parquet(root/'data/panel.parquet');d=pd.read_parquet(m/'nearest_membership.parquet');h=pd.read_parquet(m/'centers.parquet');ag=pd.read_parquet(m/'zone_trajectories.parquet');dyn=pd.read_parquet(m/'dynamic2021_membership.parquet');decomp=pd.read_parquet(m/'fixed_dynamic_decomposition.parquet');nested=pd.read_parquet(m/'nested_aggregates.parquet')
 ck('panel_identity_complete',len(d)==len(panel)==142570 and d.id.is_unique and set(d.id)==set(panel.id));j=d.merge(panel,on='id',suffixes=('_model','_panel'),validate='one_to_one')
 for col in ['lat','lon','population_2002','population_2010','population_2021']:ck('exact_source_'+col,np.array_equal(j[col+'_model'],j[col+'_panel']))
 ck('zeros2010_preserved',d.population_2010.eq(0).sum()==panel.population_2010.eq(0).sum()==21246)
 ck('centers_unique',h.id.is_unique);ck('ordinary_center_values2010',h.loc[~h.external_anchor].set_index('id').population_2010.eq(panel.set_index('id').population_2010.reindex(h.loc[~h.external_anchor,'id'])).all())
 for year in [2002,2010,2021]:
  own=d.groupby('center_id')[f'population_{year}'].sum();pub=ag.set_index('center_id')[f'population_{year}'];ck(f'zone_population_exact_{year}',np.array_equal(own.reindex(pub.index,fill_value=0),pub));ck(f'all_population_exact_{year}',float(pub.sum())==float(panel[f'population_{year}'].sum()),{'zone_sum':float(pub.sum()),'panel_sum':float(panel[f'population_{year}'].sum())})
  cp=ag.set_index('center_id')[f'center_population_{year}'];expected=cp.index.to_series().map(panel.set_index('id')[f'population_{year}']).fillna(0);expected.loc[expected.index.isin(h.loc[h.external_anchor,'id'])]=0;ck(f'center_contribution_external_excluded_{year}',np.array_equal(cp,expected))
 ck('own_centers_retained',d.loc[d.id.isin(h.id)].id.eq(d.loc[d.id.isin(h.id)].center_id).all())
 par=h.set_index('id').parent_id.to_dict();mass=h.set_index('id').population_2010.to_dict();chains={};cycle=False;strict=True
 for key in par:
  ch=[key]
  while isinstance(par.get(ch[-1]),str):
   p=par[ch[-1]]
   if p in ch:cycle=True;break
   strict &= mass[p]>mass[ch[-1]];ch.append(p)
  chains[key]=ch
 ck('acyclic_parent_tree',not cycle);ck('strictly_increasing_2010_mass',strict)
 sample=rng.choice(len(d),600,replace=False);nearest_error=huff_error=runner_error=count_error=0;distance_error=prob_error=potential_error=0;hid=h.id.to_numpy();hm=h.population_2010.to_numpy();hindex=dict(zip(hid,range(len(h))))
 for i in sample:
  row=d.iloc[i];ds=haversine(h.lat.to_numpy(),h.lon.to_numpy(),row.lat,row.lon);mi=ds.min();actual=row.center_id
  if row.id in hindex:nearest_error+=actual!=row.id
  elif mi>100:nearest_error+=actual!='UNASSIGNED'
  else:nearest_error+=(actual not in hindex or abs(ds[hindex[actual]]-mi)>1e-7)
  distance_error=max(distance_error,abs(mi-row.distance_km));ids=np.flatnonzero(ds<=100+1e-8);weights=hm[ids]/(ds[ids]+5)**2;order=np.argsort(-weights,kind='stable');total=weights.sum();winner=hid[ids[order[0]]] if len(ids) else 'UNASSIGNED';runner=hid[ids[order[1]]] if len(ids)>1 else 'UNASSIGNED';huff_error+=winner!=row.raw_huff_winner;runner_error+=runner!=row.raw_huff_runner;count_error+=len(ids)!=row.n_competitors
  if total>0:prob_error=max(prob_error,abs(weights[order[0]]/total-row.raw_huff_pmax));potential_error=max(potential_error,abs(total-row.potential))
 ck('sample600_independent_all_center_nearest',nearest_error==0,{'sample':600,'errors':int(nearest_error),'max_distance_error_km':float(distance_error)});ck('sample600_independent_Huff_winner',huff_error==0,{'errors':int(huff_error)});ck('sample600_independent_Huff_runner',runner_error==0,{'errors':int(runner_error)});ck('sample600_independent_Huff_competitors',count_error==0,{'errors':int(count_error)});ck('sample600_independent_Huff_probability',prob_error<1e-8,{'max_error':float(prob_error),'max_potential_abs_error':float(potential_error)})
 parent_error=0
 for i in rng.choice(len(h),min(600,len(h)),replace=False):
  ds=haversine(h.lat.to_numpy(),h.lon.to_numpy(),h.lat.iloc[i],h.lon.iloc[i]);ids=np.flatnonzero((ds<=100+1e-8)&(hm>hm[i]));expected=None
  if len(ids):weights=hm[ids]/(ds[ids]+5)**2;k=ids[np.argmax(weights)];expected=hid[k] if weights.max()>hm[i]/25 else None
  actual=h.parent_id.iloc[i];parent_error+=(expected is None and pd.notna(actual)) or (expected is not None and expected!=actual)
 ck('sample600_parent_field_rule',parent_error==0,{'errors':int(parent_error)})
 for step,nt in nested.groupby('aggregation_step'):
  mp={key:ch[min(int(step),len(ch)-1)] for key,ch in chains.items()};z=d.assign(unit=d.center_id.map(mp).fillna('UNASSIGNED'));own=z.groupby('unit')[[f'population_{y}' for y in [2002,2010,2021]]].sum();pub=nt.set_index('nested_unit');ck(f'nested_set_step{step}',set(own.index)==set(pub.index))
  for y in [2002,2010,2021]:ck(f'nested_exact_step{step}_{y}',np.array_equal(own[f'population_{y}'].reindex(pub.index),pub[f'population_{y}']) and float(pub[f'population_{y}'].sum())==float(panel[f'population_{y}'].sum()))
 z=d.merge(dyn[['id','center_id']],on='id',suffixes=('_fixed','_dynamic'),validate='one_to_one');decomp_errors=[]
 for base,dc in decomp.groupby('baseline_year'):
  z['delta']=(z.population_2021-z[f'population_{base}'])/2;z['mean']=(z.population_2021+z[f'population_{base}'])/2;old=z.groupby('center_id_fixed')[['delta','mean',f'population_{base}']].sum();new=z.groupby('center_id_dynamic')[['delta','mean','population_2021']].sum();old=old.reindex(dc.center_id,fill_value=0);new=new.reindex(dc.center_id,fill_value=0);demo=old.delta.to_numpy()+new.delta.to_numpy();realloc=new['mean'].to_numpy()-old['mean'].to_numpy();change=new.population_2021.to_numpy()-old[f'population_{base}'].to_numpy();error=max(np.abs(demo-dc.symmetric_demographic_effect).max(),np.abs(realloc-dc.symmetric_reallocation_effect).max(),np.abs(change-dc.observed_dynamic_change).max(),np.abs(demo+realloc-change).max());ck(f'exact_fixed_dynamic_decomposition_{base}',error<1e-6 and abs(realloc.sum())<1e-6 and float(change.sum())==float((panel.population_2021-panel[f'population_{base}']).sum()),{'max_error':float(error),'reallocation_sum':float(realloc.sum()),'zones':len(dc)})
 for part,pre in [('total',''),('environment','environment_')]:
  zero=ag[f'{pre}population_2010'].eq(0);ck(f'zero_base_ratio_undefined_{part}',ag.loc[zero,f'{part}_growth_2010_2021'].isna().all());ck(f'log1p_preserves_zeros_{part}',np.allclose(ag[f'{part}_log1p_change_2010_2021'],np.log1p(ag[f'{pre}population_2021'])-np.log1p(ag[f'{pre}population_2010']),rtol=0,atol=1e-12))
 # Independent baseline25km point density; all raw2010 values, no source metadata filter.
 la=np.radians(d.lat.to_numpy());lo=np.radians(d.lon.to_numpy());xyz=np.c_[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)];tree=cKDTree(xyz);pop=d.population_2010.to_numpy();density=np.array([pop[ix].sum()/(np.pi*25**2) for ix in tree.query_ball_point(xyz,2*np.sin(25/(2*EARTH)),workers=2)]);point=d[['id','center_id','population_2010','population_2021','distance_km','center_anchored','lat','lon']].copy();point['density25_2010']=density;point['noncenter']=~point.center_anchored;point.to_parquet(o/'independent_point_covariates.parquet',index=False)
 g=point.groupby('center_id').agg(mean_density25=('density25_2010','mean'),mean_distance=('distance_km','mean'),noncenter_members=('noncenter','sum'));f=ag.merge(g,on='center_id',validate='one_to_one');f['log_mass2010']=np.log1p(f.center_id.map(mass));f['log_density25']=np.log1p(f.mean_density25);f['log_distance']=np.log1p(f.mean_distance);f['log_population2010']=np.log1p(f.population_2010);f['has_environment']=f.noncenter_members.gt(0).astype(int);f['outcome_total']=np.log1p(f.population_2021)-np.log1p(f.population_2010);f['outcome_environment']=np.log1p(f.environment_population_2021)-np.log1p(f.environment_population_2010);f['x'],f['y']=equal_area6933(f.lon.to_numpy(),f.lat.to_numpy());f.to_parquet(o/'independent_zone_covariates.parquet',index=False);features=['log_mass2010','log_density25','log_distance','log_population2010','has_environment'];results=[]
 for outcome in ['outcome_total','outcome_environment']:
  cohort=f[f.center_id.ne('UNASSIGNED')].copy();cohort=cohort if outcome=='outcome_total' else cohort[cohort.noncenter_members>0]
  for size in [250,400,600]:results.append(spatial_blockfit(cohort,outcome,features,outcome,size,rng,args.bootstrap_reps))
 report={'role_disclosure':'Author created input panel and provenance audit, not GIS model, agriculture profiles or RFSD projections. Formula, aggregations and decomposition checked independently; no model code imported.','checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks)};(o/'independent_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));(o/'spatial_block_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));pins=[root/'data/panel.parquet',m/'centers.parquet',m/'nearest_membership.parquet',m/'zone_trajectories.parquet',m/'nested_aggregates.parquet',m/'fixed_dynamic_decomposition.parquet',m/'dynamic2021_membership.parquet'];(o/'core_provenance.json').write_text(json.dumps([{'path':str(q.relative_to(root)),'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in pins],indent=2));print(json.dumps({'passed':report['passed'],'failed':report['failed'],'spatial_results':results},ensure_ascii=False,indent=2))
 if report['failed']:raise SystemExit(1)
if __name__=='__main__':main()
