"""E3 development-only descriptive curves; never summarize held-out2021 outcomes."""
import sys,json,hashlib,time,csv,gzip
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.neighbors import BallTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'statistics'))
from statistical_utils import split_blocks
P=Path('repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz');O=Path('research_staging/e3');R=6371.0088

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def edges(xy,r):
 tree=BallTree(xy,metric='haversine');ii=[];jj=[]
 for s in range(0,len(xy),1000):
  v=tree.query_radius(xy[s:s+1000],r=r/R)
  for k,ne in enumerate(v):
   ne=ne[ne>s+k];ii.extend([s+k]*len(ne));jj.extend(ne.tolist())
 return np.array(ii,int),np.array(jj,int)
def graph_stats(n,i,j,keep,pop):
 active=np.flatnonzero(keep);a=len(active)
 if not a:return dict(active_n=0,lcc_n=0,lcc_fixed=0.,lcc_active=np.nan,isolated_n=0,isolated_fraction_active=np.nan,components=0,lcc_population_share=np.nan)
 e=keep[i]&keep[j];ii=i[e];jj=j[e];mapping=np.full(n,-1,int);mapping[active]=np.arange(a)
 g=coo_matrix((np.ones(len(ii)*2), (np.r_[mapping[ii],mapping[jj]],np.r_[mapping[jj],mapping[ii]])),shape=(a,a)).tocsr()
 c,lab=connected_components(g,directed=False);counts=np.bincount(lab);m=int(counts.argmax());l=int(counts[m]);deg=np.asarray(g.sum(axis=1)).ravel();mass=pop[active].sum()
 return dict(active_n=a,lcc_n=l,lcc_fixed=l/n,lcc_active=l/a,isolated_n=int((deg==0).sum()),isolated_fraction_active=float((deg==0).mean()),components=int(c),lcc_population_share=float(pop[active][lab==m].sum()/mass) if mass>0 else np.nan)
def main():
 start=time.time();cols=['entity_uid','population_2010','latitude_2010','longitude_2010','effective_region_norm_2010']
 d=pd.read_csv(P,usecols=cols);block,hold,fold=split_blocks(d.longitude_2010,d.latitude_2010)
 # Parse only development outcome strings; held-out targets never numerically parsed.
 wanted=set(d.loc[~hold,'entity_uid']);outcomes={}
 with gzip.open(P,'rt',newline='',encoding='utf-8') as src:
  for row in csv.DictReader(src):
   if row['entity_uid'] in wanted:outcomes[row['entity_uid']]=row['population_2021']
 parsed=pd.to_numeric(pd.Series(outcomes),errors='coerce');d['population_2021']=d.entity_uid.map(parsed)
 assert d.loc[hold,'population_2021'].isna().all()
 d['block_id']=block;d['holdout']=hold
 pos=d.population_2010.gt(0).to_numpy();xy=np.radians(d[['latitude_2010','longitude_2010']].to_numpy());tree=BallTree(xy[pos],metric='haversine');dist,_=tree.query(xy[pos],k=6);nn5=np.full(len(d),np.nan);nn5[pos]=dist[:,5]*R
 # Block induced graph2010 only, no future columns.
 bf=[]
 for b,ids0 in d.groupby('block_id').indices.items():
  ids=np.asarray(ids0);pids=ids[pos[ids]];n=len(pids)
  if n:
   i,j=edges(xy[pids],10);s=graph_stats(n,i,j,np.ones(n,bool),d.population_2010.to_numpy()[pids]);bf.append(dict(block_id=b,morph_median_nn5_2010=float(np.nanmedian(nn5[pids])),morph_isolated10_2010=s['isolated_fraction_active'],morph_lcc10_2010=s['lcc_active'],morph_n2010=n,morph_insufficient=int(n<6)))
  else:bf.append(dict(block_id=b,morph_median_nn5_2010=np.nan,morph_isolated10_2010=np.nan,morph_lcc10_2010=np.nan,morph_n2010=0,morph_insufficient=1))
 pd.DataFrame(bf).to_csv(O/'block_morphology2010.csv',index=False)
 rows=[];summary=[]
 risk=d[(~hold)&pos&d.population_2021.notna()&d.population_2021.ge(0)].copy()
 for reg,fr in risk.groupby('effective_region_norm_2010'):
  ids=fr.index.to_numpy();n=len(ids);coords=xy[ids];p=fr.population_2010.to_numpy();keep=fr.population_2021.to_numpy()>0;scale=float(np.nanmedian(nn5[ids]));rr=[]
  for grid,rs in [('absolute_km',[2,5,10,20,30]),('normalized_nn5',[.25,.5,1,2,3])]:
   for v in rs:
    r=v if grid=='absolute_km' else v*scale;i,j=edges(coords,r)
    base=graph_stats(n,i,j,np.ones(n,bool),p);surv=graph_stats(n,i,j,keep,p)
    row=dict(region=reg,grid=grid,radius_value=v,radius_km=r,median_nn5_2010_km=scale,initial_n=n,zero2021_n=int((~keep).sum()),edges_initial=len(i),edges_surviving=int((keep[i]&keep[j]).sum()))
    row.update({'initial_'+k:val for k,val in base.items()});row.update({'surviving_'+k:val for k,val in surv.items()});rows.append(row);rr.append(row)
   curve=rr[-5:];loss=np.array([a['initial_lcc_fixed']-a['surviving_lcc_fixed'] for a in curve]);auc=float(np.trapezoid(loss,x=np.log(rs))/(np.log(rs[-1])-np.log(rs[0])))
   summary.append(dict(region=reg,grid=grid,initial_n=n,zero2021_n=int((~keep).sum()),integrated_fixed_lcc_loss=auc))
  print(reg,n,'elapsed',round(time.time()-start,1),flush=True)
 pd.DataFrame(rows).to_csv(O/'regional_curves.csv',index=False);pd.DataFrame(summary).to_csv(O/'regional_integrals.csv',index=False)
 meta=dict(status='computed_exploratory',input_sha256=sha(P),script_sha256=sha(__file__),n_input=len(d),dev_risk_n=len(risk),heldout_outcomes_used=0,n_regions=risk.effective_region_norm_2010.nunique(),radii_km=[2,5,10,20,30],normalized_radii=[.25,.5,1,2,3],seconds=time.time()-start,limitations=['Development-only induced graphs lose cross-holdout and cross-region edges.','Fixed baselinepositive2010 nodes; zero2021 is census zero, not proven physical loss.','Normalization median globalpositive2010 fifth-neighbor distance of region development points; fixed across dates.','No conditional-risk null simulation or p-value.','LCC population shares weight surviving baseline2010 population, not2021 population.'])
 (O/'curve_metadata.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False));(O/'null_diagnostics.json').write_text(json.dumps(dict(status='not_performed',simulations=0,required=1999,synthetic_calibration=False,confirmatory_graph_claims_permitted=False),indent=2))
 print(json.dumps(meta,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
