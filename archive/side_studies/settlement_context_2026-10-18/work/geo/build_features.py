"""Immutable stage71 geometric context, no 2021 fields read. Sphere R=6371.0088 km."""
import argparse,hashlib,json,time,resource,platform
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree
R=6371.0088
RADII=(10,30,60,100)
COLS=['entity_uid','population_2002','population_2010','latitude_2010','longitude_2010','population_value_quality_2010','historical_measurement_asserted_2010','point_reuse_or_continuity_inference_status_2010','effective_region_norm_2010','settlement_type_2010']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--input',default='repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz');ap.add_argument('--federal',default='repo/publication/stage71/accepted_common_federal_territory_axis.csv');ap.add_argument('--output',default='research_staging/geo');ap.add_argument('--population-axis',choices=['selected','original_fallback'],default='selected');ap.add_argument('--exclude-neighbor-uids');a=ap.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);t=time.time()
 d=pd.read_csv(a.input,usecols=COLS+(['original_population_2010'] if a.population_axis=='original_fallback' else []));assert d.entity_uid.is_unique
 if a.population_axis=='original_fallback':
  original=pd.to_numeric(d.original_population_2010,errors='coerce');d['population_2010']=original.where(np.isfinite(original),d.population_2010)
 excluded=set(pd.read_csv(a.exclude_neighbor_uids,usecols=['entity_uid']).entity_uid) if a.exclude_neighbor_uids else set()
 universe=np.flatnonzero(~d.entity_uid.isin(excluded).to_numpy())
 p=d.population_2010.to_numpy(float);p0=d.population_2002.to_numpy(float);xy=np.deg2rad(d[['latitude_2010','longitude_2010']].to_numpy(float));assert np.isfinite(xy).all() and np.isfinite(p).all() and (p>=0).all()
 tree=BallTree(xy[universe],metric='haversine');n=len(d);f=d.copy()
 for radius in RADII:
  names=['mass2010','count_all','count_positive','maxshare','effective_n','density2010','history_symmetric_change','history_zero_fraction','empty','history_pair_count','history_positive2002_count','history_mass2002','history_mass2010']
  vals={k:np.full(n,np.nan) for k in names}
  for st in range(0,n,1000):
   inds=tree.query_radius(xy[st:st+1000],r=radius/R)
   for ii,js in enumerate(inds):
    i=st+ii;js=universe[js];js=js[js!=i];pp=p[js];pp0=p0[js];m=pp.sum();old=pp0.sum();sq=(pp*pp).sum();den=m+old
    row=[m,len(js),int((pp>0).sum()),pp.max()/m if m>0 else np.nan,m*m/sq if sq>0 else np.nan,m/(2*np.pi*R*R*(1-np.cos(radius/R))),2*(m-old)/den if den>0 else np.nan,float(((pp0>0)&(pp==0)).sum()/(pp0>0).sum()) if (pp0>0).any() else np.nan,int(len(js)==0),int((np.isfinite(pp)&np.isfinite(pp0)).sum()),int((pp0>0).sum()),old,m]
    for k,v in zip(names,row):vals[k][i]=v
  for k,v in vals.items():f[f'r{radius}_{k}']=v
  print('radius complete',radius,'seconds',round(time.time()-t,1),flush=True)
 # Annuli use additive differences only; HHI/maxshare cannot be differenced.
 for lo,hi in zip((0,10,30,60),RADII):
  for k in ['mass2010','count_all','count_positive']:
   f[f'annulus_{lo}_{hi}_{k}']=f[f'r{hi}_{k}']-(f[f'r{lo}_{k}'] if lo else 0)
 # Preserve colocated distinct UIDs; self only is excluded.
 dist,ind=tree.query(xy,k=7);nn=np.empty((n,5))
 for i in range(n):nn[i]=dist[i][universe[ind[i]]!=i][:5]*R
 f['nn1_km']=nn[:,0];f['nn5_mean_km']=nn.mean(axis=1)
 # Dimensionless NN shape: mean first-five distance / radius needed for five points under locally uniform 30-km count density.
 expected=30*np.sqrt(5/np.maximum(f.r30_count_all.to_numpy(),1));f['nn5_normalized']=nn.mean(axis=1)/expected;f['nn5_norm_reference_empty']=f.r30_count_all.eq(0)
 for threshold in [10000,100000]:
  eligible=universe[p[universe]>=threshold];ct=BallTree(xy[eligible],metric='haversine');dd,jj=ct.query(xy,k=min(2,len(eligible)))
  picked=np.where(eligible[jj[:,0]]==np.arange(n),1,0);idx=eligible[jj[np.arange(n),picked]]
  prefix=f'nearest_ge{threshold}';f[prefix+'_km']=dd[np.arange(n),picked]*R;f[prefix+'_uid']=d.entity_uid.to_numpy()[idx];f[prefix+'_population2010']=p[idx];f[prefix+'_size_ratio']=np.divide(p[idx],p,out=np.full(n,np.nan),where=p>0)
 # Adaptive query expansion: no dense NxN matrix; only unresolved origins expand.
 larger_idx=np.full(n,-1,int);larger_dist=np.full(n,np.nan);remaining=np.arange(n);k=16
 while len(remaining):
  k=min(k,len(universe));still=[]
  for st in range(0,len(remaining),max(1,2000000//k)):
   ids=remaining[st:st+max(1,2000000//k)];dd,jj=tree.query(xy[ids],k=k);jj=universe[jj]
   ok=p[jj]>p[ids,None];has=ok.any(axis=1);first=ok.argmax(axis=1);resolved=ids[has];larger_idx[resolved]=jj[np.arange(len(ids))[has],first[has]];larger_dist[resolved]=dd[np.arange(len(ids))[has],first[has]]*R
   still.extend(ids[~has & (p[ids]<p[universe].max())].tolist())
  remaining=np.array(still,dtype=int)
  if k==len(universe):break
  k*=2
 f['nearest_larger_km']=larger_dist;f['nearest_larger_uid']=[d.entity_uid.iloc[j] if j>=0 else '' for j in larger_idx];lp=np.where(larger_idx>=0,p[np.maximum(larger_idx,0)],np.nan);f['nearest_larger_population2010']=lp;f['nearest_larger_size_ratio']=np.divide(lp,p,out=np.full(n,np.nan),where=p>0)
 # External anchors affect distances/sensitivity only; federal territorial masses never enter BallTree/mass.
 fed=pd.read_csv(a.federal);fed=fed[(fed.census_year==2010)&fed.territory_key.isin(['RU-FED-MOW','RU-FED-SPB'])]
 cd=[]
 for row in fed.itertuples():
  anchor=np.deg2rad([[row.latitude,row.longitude]]);ds=BallTree(anchor,metric='haversine').query(xy,k=1)[0][:,0]*R;f['distance_'+row.territory_key+'_km']=ds;cd.append(ds)
 f['capital_distance_min_km']=np.min(cd,axis=0);f['capital_within100km']=f.capital_distance_min_km.le(100)
 f.to_csv(out/'features.csv.gz',index=False,compression={'method':'gzip','mtime':0})
 meta={'population_axis':a.population_axis,'excluded_neighbor_uid_file':a.exclude_neighbor_uids,'excluded_neighbor_uid_sha256':sha(a.exclude_neighbor_uids) if a.exclude_neighbor_uids else None,'neighbor_universe_rows':len(universe),'input_sha256':sha(a.input),'federal_sha256':sha(a.federal),'script_sha256':sha(__file__),'rows':n,'columns':list(f.columns),'radii_km':RADII,'sphere_radius_km':R,'seconds':time.time()-t,'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'python':platform.python_version(),'population_2010_sum':float(p.sum()),'population_2002_sum':float(p0.sum()),'historical_measurement_asserted2010_counts':d.historical_measurement_asserted_2010.value_counts(dropna=False).astype(int).to_dict(),'coordinate_duplicate_rows':int(d.duplicated(['latitude_2010','longitude_2010'],keep=False).sum()),'feature_sha256':sha(out/'features.csv.gz'),'limitations':['Full3-selected ordinary neighborhood universe, not all census records; absent lifecycle/available-year observations not allocated.','2010 coordinates are retrospective representative point uses; not demonstrated census-day measurements.','Federal territorial aggregates excluded from point masses; capital distances use 2021-derived anchor retained in 2010 territory layer.','NN5 normalization is dimensionless shape relative to local30km count density, not a transport or functional link.','History symmetric change uses same2010 geographic neighbor set and2002/2010 populations. All finite2010 counts retained irrespective of quality; quality column preserved.','A zero population2010 makes size ratio undefined rather than infinity.']}
 (out/'spatial_contract.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False))
 print(json.dumps({k:v for k,v in meta.items() if k not in ['columns','limitations']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
