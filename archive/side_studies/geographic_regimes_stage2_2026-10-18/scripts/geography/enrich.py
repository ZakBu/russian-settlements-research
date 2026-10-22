"""Protocol-fixed additional baseline matching context; no outcome-based selection."""
from pathlib import Path
import numpy as np,pandas as pd,pyproj,json,hashlib
B=Path(__file__).parent;O=B/'outputs';R=Path('/workspace/scratch/c21afd18c709/repo/publication/stage71');p=O/'point_distances.csv.gz';d=pd.read_csv(R/'ordinary_full3_with_primary_population_sources.csv.gz',usecols=['entity_uid','population_2002','population_2021','latitude_2002','longitude_2002','latitude_2010','longitude_2010','latitude_2021','longitude_2021','effective_region_norm_2002']).sort_values('entity_uid').reset_index(drop=True);pt=pd.read_csv(p);assert np.array_equal(d.entity_uid,pt.entity_uid)
g=pyproj.Geod(ellps='WGS84');xy=d[['longitude_2002','latitude_2002']].to_numpy();orig=np.flatnonzero(d.population_2002.to_numpy()>0);cent=np.flatnonzero(d.population_2002.to_numpy()>=100000);dst=np.full(len(d),np.nan);which=np.full(len(d),-1,int)
for st in range(0,len(orig),1000):
 ids=orig[st:st+1000];xx=np.repeat(xy[ids],len(cent),axis=0);cc=np.tile(xy[cent],(len(ids),1));dd=g.inv(xx[:,0],xx[:,1],cc[:,0],cc[:,1])[2].reshape(len(ids),len(cent))/1000;dd[ids[:,None]==cent[None,:]]=np.inf;idx=np.argmin(dd,axis=1);dst[ids]=dd[np.arange(len(ids)),idx];which[ids]=cent[idx]
pt['nearest100k2002_km']=dst;pt['nearest100k2002_uid']=[d.entity_uid.iloc[i] if i>=0 else '' for i in which]
f=pd.read_csv(R/'accepted_common_federal_territory_axis.csv');f=f[(f.census_year==2002)&f.territory_key.isin(['RU-FED-MOW','RU-FED-SPB'])];assert len(f)==2
fd=[]
for r in f.itertuples():fd.append(g.inv(xy[:,0],xy[:,1],np.full(len(d),r.longitude),np.full(len(d),r.latitude))[2]/1000)
pt['nearest_federal_anchor_km']=np.min(fd,axis=0);pt['nearest100k2002_plus_federal_anchor_km']=np.fmin(dst,pt.nearest_federal_anchor_km)
m=pd.read_csv(O/'territory_metrics.csv');extra=[]
for kind,parts in pt.groupby('region'):
 pass
for kind in m.kind.unique():
 for key,ix in pt.groupby(kind).groups.items():
  ids=np.array(ix);reg=d.effective_region_norm_2002.iloc[ids].fillna('UNKNOWN');vc=reg.value_counts();b=d.population_2002.iloc[ids].to_numpy()>0;zs={'kind':kind,'unit':key,'dominant_region2002':vc.index[0],'dominant_region_row_fraction2002':vc.iloc[0]/len(ids),'region_mixing_fraction':1-vc.iloc[0]/len(ids)}
  for field in ['nearest100k2002_km','nearest100k2002_plus_federal_anchor_km','nearest_federal_anchor_km']:zs[field+'_median']=pt[field].iloc[ids][b].median()
  extra.append(zs)
m=m.merge(pd.DataFrame(extra),on=['kind','unit'],validate='one_to_one');m.to_csv(O/'territory_metrics.csv',index=False);pt.to_csv(p,index=False,compression={'method':'gzip','mtime':0})
move=g.inv(d.longitude_2002.to_numpy(),d.latitude_2002.to_numpy(),d.longitude_2021.to_numpy(),d.latitude_2021.to_numpy())[2]/1000
check={'all_rows':len(d),'latitude2002_min':d.latitude_2002.min(),'latitude2002_max':d.latitude_2002.max(),'latitude_outside_EPSG6933_area_abs_gt86':int((d.latitude_2002.abs()>86).sum()),'coordinate_distinct2002':len(d[['longitude_2002','latitude_2002']].drop_duplicates()),'duplicate_coordinate_rows2002':int(d.duplicated(['longitude_2002','latitude_2002'],False).sum()),'movement2002to2021_gt1km':int((move>1).sum()),'movement2002to2021_gt10km':int((move>10).sum()),'nearest100k_ordinary_center_count2002':len(cent),'federal_anchor_count':len(f),'federal_anchor_note':'Moscow/StPetersburg territorial representative2021-derived anchors retained as context, no federal territorial population allocated to cell. Base nearest100k excludes federal aggregate population; separate plus-anchor sensitivity uses those2 contextual anchors.'}
(O/'geometry_diagnostics.json').write_text(json.dumps(check,indent=2,ensure_ascii=False));(O/'enrichment_receipt.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'federal_sha256':hashlib.sha256((R/'accepted_common_federal_territory_axis.csv').read_bytes()).hexdigest(),'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in O.iterdir() if f.is_file()}},indent=2));print(json.dumps(check),flush=True)
