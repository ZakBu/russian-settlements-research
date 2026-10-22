"""Fixed panel geography; WGS84 exhaustive bounded candidates. See protocol_geography.md."""
import json,hashlib,platform,sys,time
from pathlib import Path
import numpy as np,pandas as pd,pyproj
from sklearn.neighbors import BallTree
BASE=Path(__file__).parent; IN=Path('/workspace/scratch/c21afd18c709/repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz');OUT=BASE/'outputs';OUT.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(IN)=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c'
cols=['entity_uid','effective_region_norm_2002']+[f'{c}_{y}' for y in [2002,2010,2021] for c in ['population','latitude','longitude','population_value_quality']]
d=pd.read_csv(IN,usecols=cols).sort_values('entity_uid').reset_index(drop=True);assert len(d)==142570 and d.entity_uid.is_unique
p=d[[f'population_{y}' for y in [2002,2010,2021]]].to_numpy(float);assert np.isfinite(p).all() and (p>=0).all()
xy=d[['latitude_2002','longitude_2002']].to_numpy(float);assert np.isfinite(xy).all()
orig=np.flatnonzero(p[:,0]>0);geod=pyproj.Geod(ellps='WGS84');RMIN=geod.a*(1-geod.es)/1000

def nearest(orig,neighbors,coords=xy):
 tree=BallTree(np.deg2rad(coords[neighbors]),metric='haversine'); qxy=xy[orig]; dd,jj=tree.query(np.deg2rad(qxy),k=min(2,len(neighbors)));cand=neighbors[jj]
 initial=np.where(cand[:,0]==orig,cand[:,1],cand[:,0]);best=geod.inv(qxy[:,1],qxy[:,0],coords[initial,1],coords[initial,0])[2]/1000
 result=np.empty(len(orig));idx=np.empty(len(orig),int);nc=0
 for st in range(0,len(orig),4000):
  sl=slice(st,st+4000);c=tree.query_radius(np.deg2rad(qxy[sl]),r=np.nextafter(best[sl]/RMIN,np.inf));lens=np.array([len(v) for v in c]);ii=np.repeat(np.arange(st,min(st+4000,len(orig))),lens);js=neighbors[np.concatenate(c)];keep=js!=orig[ii];ii=ii[keep];js=js[keep];nc+=len(js)
  dst=geod.inv(xy[orig[ii],1],xy[orig[ii],0],coords[js,1],coords[js,0])[2]/1000
  order=np.lexsort((js,dst,ii));ii=ii[order];js=js[order];dst=dst[order];first=np.r_[True,np.diff(ii)!=0];result[ii[first]]=dst[first];idx[ii[first]]=js[first]
 print('nearest done',len(neighbors),nc,flush=True);return result,idx
nn0,j0=nearest(orig,np.flatnonzero(p[:,0]>0));nn1,j1=nearest(orig,np.flatnonzero(p[:,2]>0));nn_surv,js=nearest(orig,np.flatnonzero((p[:,0]>0)&(p[:,2]>0)))
# Observed2021 coordinate sensitivity changes target locations, fixed origins remain2002.
xy21=d[['latitude_2021','longitude_2021']].to_numpy(float);nn21,j21=nearest(orig,np.flatnonzero(p[:,2]>0),xy21)
pts=d[['entity_uid','effective_region_norm_2002','latitude_2002','longitude_2002']].copy()
for k,val in [('nn2002_km',nn0),('nn2021_km',nn1),('nn2021_survivor_neighbors_km',nn_surv),('nn2021_original_coords_km',nn21),('nn_change_km',nn1-nn0),('nn_ratio',np.divide(nn1,nn0,out=np.full(len(orig),np.nan),where=nn0>0)),('neighbor2021_newpositive2002',p[j1,0]==0)]:
 pts[k]=np.nan;pts.loc[orig,k]=val
pts['nn2002_neighbor_uid']='';pts.loc[orig,'nn2002_neighbor_uid']=d.entity_uid.iloc[j0].to_numpy();pts['nn2021_neighbor_uid']='';pts.loc[orig,'nn2021_neighbor_uid']=d.entity_uid.iloc[j1].to_numpy()
proj=pyproj.Transformer.from_crs(4326,6933,always_xy=True);x,y=proj.transform(xy[:,1],xy[:,0]);pts['x6933_m']=x;pts['y6933_m']=y
spec=[('region',None,0),('grid50',50000,0),('grid25',25000,0),('grid100',100000,0),('grid50shift25',50000,25000)]
rows=[]
for kind,size,shift in spec:
 if size is None: groups=d.effective_region_norm_2002.fillna('UNKNOWN').astype(str).to_numpy()
 else:
  gx=np.floor((x-shift)/size).astype(int);gy=np.floor((y-shift)/size).astype(int);groups=np.array([f'{a}_{b}' for a,b in zip(gx,gy)])
 pts[kind]=groups
 for unit,ix in pd.Series(np.arange(len(d))).groupby(groups,sort=True):
  ids=ix.to_numpy();pp=p[ids];b=pp[:,0]>0;npos=int(b.sum());nzero=int((~b).sum());ss=pp.sum(axis=0);r={'kind':kind,'unit':unit,'n_rows':len(ids),'n_positive2002':npos,'n_zero2002':nzero,'support20':npos>=20,'logpop2002':np.log1p(ss[0]),'logn2002':np.log1p(npos)}
  for yi,year in enumerate([2002,2010,2021]):r['population'+str(year)]=ss[yi];r['n_positive'+str(year)]=int((pp[:,yi]>0).sum())
  for a,z,ya,yz in [(0,1,2002,2010),(1,2,2010,2021),(0,2,2002,2021)]:
   r[f'change_{ya}_{yz}']=ss[z]-ss[a];r[f'relchange_{ya}_{yz}']=ss[z]/ss[a]-1 if ss[a]>0 else np.nan;r[f'annual_rate_{ya}_{yz}']=(ss[z]/ss[a])**(1/(yz-ya))-1 if ss[a]>0 else np.nan
  # all-row membership: numeric zero rows included in denominator as frozen.
  order=np.lexsort((d.entity_uid.iloc[ids].to_numpy(),-pp[:,0]));
  for pct in [10,1]:
   k=int(np.ceil(len(ids)*pct/100));r[f'top{pct}_count']=k
   for yi,yr in enumerate([2002,2010,2021]):r[f'top{pct}_share{yr}']=pp[order[:k],yi].sum()/ss[yi] if ss[yi]>0 else np.nan
   r[f'top{pct}_delta_pp']=100*(r[f'top{pct}_share2021']-r[f'top{pct}_share2002'])
  survived=int((b&(pp[:,2]>0)).sum());reent=int((~b&(pp[:,2]>0)).sum());r.update(survived2002_2021=survived,zero_transition2002_2021=npos-survived,survival_fraction=survived/npos if npos else np.nan,reentries2002_2021=reent,reentry_fraction=reent/nzero if nzero else np.nan)
  positives=pp[b,0];r['size_median2002']=np.median(positives) if npos else np.nan;r['size_p90_2002']=np.quantile(positives,.9) if npos else np.nan
  for lo,hi,key in [(0,10,'lt10'),(10,100,'10_99'),(100,1000,'100_999'),(1000,np.inf,'ge1000')]:r['size_fraction_'+key]=float(((positives>lo if lo==0 else positives>=lo)&(positives<hi)).sum()/npos) if npos else np.nan
  vv=pts.iloc[ids][b]
  for field in ['nn2002_km','nn2021_km','nn_change_km','nn_ratio','nn2021_survivor_neighbors_km','nn2021_original_coords_km']:
   values=vv[field].dropna().to_numpy(float);r[field+'_median']=np.median(values) if len(values) else np.nan;r[field+'_p90']=np.quantile(values,.9) if len(values) else np.nan
  r['nn_baseline_zero_count']=int(vv.nn2002_km.eq(0).sum());r['nn_newneighbor_fraction']=vv.neighbor2021_newpositive2002.mean() if npos else np.nan
  if size:r.update(grid_side_km=size/1000,grid_shift_km=shift/1000,cell_x=(int(unit.split('_')[0])+0.5)*size+shift,cell_y=(int(unit.split('_')[1])+0.5)*size+shift,density_positive2002_per1000km2=npos/(size/1000)**2*1000)
  rows.append(r)
 print(kind,'complete',flush=True)
m=pd.DataFrame(rows);m.to_csv(OUT/'territory_metrics.csv',index=False);pts.to_csv(OUT/'point_distances.csv.gz',index=False,compression={'method':'gzip','mtime':0})
# deterministic brute-force check against all candidates for24 fixed origins, includes first colocation if any.
checks=[];rng=np.random.default_rng(20261018);sample=rng.choice(np.arange(len(orig)),24,replace=False)
for yr,mask,nn in [(2002,p[:,0]>0,nn0),(2021,p[:,2]>0,nn1)]:
 js=np.flatnonzero(mask)
 for z in sample:
  i=orig[z];ne=js[js!=i];brute=geod.inv(np.full(len(ne),xy[i,1]),np.full(len(ne),xy[i,0]),xy[ne,1],xy[ne,0])[2].min()/1000;checks.append({'uid':d.entity_uid.iloc[i],'year':yr,'calculated':nn[z],'brute':brute,'error':abs(brute-nn[z])})
pd.DataFrame(checks).to_csv(OUT/'geodesic_bruteforce_checks.csv',index=False);assert max(c['error'] for c in checks)<1e-9
receipt={'input_sha256':sha(IN),'script_sha256':sha(__file__),'protocol_sha256':sha(BASE/'protocol_geography.md'),'rows':len(d),'positive2002':len(orig),'duplicate_coordinate_rows':int(d.duplicated(['latitude_2002','longitude_2002'],False).sum()),'RMIN_km':RMIN,'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'pyproj':pyproj.__version__,'seed':20261018,'checks_maxerr_km':max(c['error'] for c in checks),'files':{f.name:sha(f) for f in OUT.iterdir() if f.is_file()}}
(OUT/'receipts.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2),flush=True)
