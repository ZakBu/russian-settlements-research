"""Post-audit sensitivity, masks use cross-year coordinate metadata; never primary X."""
import json,hashlib
from pathlib import Path
import pandas as pd,numpy as np
from sklearn.neighbors import BallTree
R=6371.0088
p=Path('research_staging/geo')
roster=Path('repo/research_staging/data_audit/evidence/point_drift_over5km.csv')
uids=set(pd.read_csv(roster,usecols=['entity_uid']).entity_uid)
f=pd.read_csv(p/'features.csv.gz');mask=f.entity_uid.isin(uids).to_numpy();xy=np.deg2rad(f[['latitude_2010','longitude_2010']].to_numpy());badidx=np.flatnonzero(mask);tree=BallTree(xy[mask],metric='haversine');pop=f.population_2010.to_numpy();old=f.population_2002.to_numpy();out=pd.DataFrame({'entity_uid':f.entity_uid,'focal_coordinate_drift_over5km':mask});summary={}
for r in (10,30,60,100):
 inds=tree.query_radius(xy,r=r/R);mass=np.zeros(len(f));hmass=np.zeros(len(f));ct=np.zeros(len(f),int)
 for i,js in enumerate(inds):
  ids=badidx[js];ids=ids[ids!=i];ct[i]=len(ids);mass[i]=pop[ids].sum();hmass[i]=old[ids].sum()
 orig=f[f'r{r}_mass2010'].to_numpy();origold=f[f'r{r}_history_mass2002'].to_numpy();m=orig-mass;o=origold-hmass
 frac=np.divide(mass,orig,out=np.zeros(len(f)),where=orig>0)
 out[f'r{r}_mass2010_excluding_drift']=m;out[f'r{r}_history_symmetric_change_excluding_drift']=np.divide(2*(m-o),m+o,out=np.full(len(f),np.nan),where=(m+o)>0);out[f'r{r}_flagged_neighbor_count']=ct
 summary[str(r)]={'origins_with_flagged_neighbor':int((ct>0).sum()),'unflagged_origins_with_flagged_neighbor':int(((ct>0)&~mask).sum()),'origins_mass_fraction_over_1pct':int((frac>.01).sum()),'origins_mass_fraction_over_10pct':int((frac>.1).sum()),'max_mass_fraction':float(frac.max())}
out.to_csv(p/'coordinate_sensitivity.csv.gz',index=False,compression={'method':'gzip','mtime':0})
meta={'mask_roster_sha256':hashlib.sha256(roster.read_bytes()).hexdigest(),'flagged_rows':len(uids),'summary':summary,'semantics':'Post-audit sensitivity only; maskcrossyear coordinates includes2021coordinate metadata. Removes flagged neighbors,never redistributes mass or changes rawcoordinates; not sufficient for nearest hierarchy sensitivity.','output_sha256':hashlib.sha256((p/'coordinate_sensitivity.csv.gz').read_bytes()).hexdigest()};(p/'coordinate_sensitivity_summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));print(json.dumps(meta,ensure_ascii=False))
