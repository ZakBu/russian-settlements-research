"""Fresh registered-address RFSD projection. No employment/production/flow inference.
50k batch streaming; independent nearest observed NP -> frozen primary center; 1/5/10km.
"""
import argparse,pathlib,json,hashlib,os,collections,time
import numpy as np,pandas as pd,pyarrow.parquet as pq
from scipy.spatial import cKDTree
P=pathlib.Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--cache',type=pathlib.Path,required=True);ap.add_argument('--membership',type=pathlib.Path,required=True);ap.add_argument('--out',type=pathlib.Path,default=P/'primary2010');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
R=6371.0088

def xyz(lat,lon):
 la,lo=np.radians(lat),np.radians(lon);return np.column_stack([np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(d,name):
 for ext in ['csv','parquet']:
  dest=a.out/(name+'.'+ext);tmp=a.out/(name+'.'+ext+'.tmp')
  if ext=='csv':d.to_csv(tmp,index=False);back=pd.read_csv(tmp)
  else:d.to_parquet(tmp,index=False);back=pd.read_parquet(tmp)
  assert back.shape==d.shape and list(back.columns)==list(d.columns),(name,ext,'shape')
  for col in d.select_dtypes(include=[np.number]).columns:assert np.allclose(d[col],back[col],equal_nan=True),('roundtrip',name,col)
  os.replace(tmp,dest)
mem=pd.read_parquet(a.membership);assert {'id','lat','lon','center_id'}<=set(mem.columns);mem=mem[mem.center_id.notna()&mem.lat.between(-90,90)&mem.lon.between(-180,180)].reset_index(drop=True);assert mem.id.is_unique
cids=sorted(mem.center_id.unique());cindex=dict(zip(cids,range(len(cids))));mi=mem.center_id.map(cindex).to_numpy();tree=cKDTree(xyz(mem.lat,mem.lon));selfpoint=mem.id.eq(mem.center_id).to_numpy();N=len(cids)
COLS=['inn','eligible','filed','articulated','outlier','imputed','geocoding_quality','lat','lon','okved_section','line_2110','line_1600','line_2400'];MODES=[(1,'baseline'),(5,'baseline'),(10,'baseline'),(1,'strict'),(5,'strict'),(10,'strict')];financial=[];sectors=[];witnesses=[];receipts=[]
for year in [2016,2021]:
 t=time.time();source=a.cache/f'rfsd_{year}_selected.parquet';pf=pq.ParquetFile(source);assert set(COLS)<=set(pf.schema_arrow.names);rec=dict(year=year,source_file=source.name,selected_sha256=sha(source),rows_expected=pf.metadata.num_rows,schema=str(pf.schema_arrow),selected_columns=COLS);receipts.append(rec)
 sums=np.zeros((6,N,6));maximum=np.zeros((6,N));sec=collections.defaultdict(lambda:np.zeros(2));wsec=collections.defaultdict(lambda:np.zeros(2));seen=set();quality=collections.Counter();aud=collections.Counter()
 for batch in pf.iter_batches(batch_size=50000,columns=COLS):
  d=batch.to_pandas().reset_index(drop=True);aud['rows']+=len(d);quality.update(d.geocoding_quality.fillna('missing'))
  for inn in d.inn:
   if inn is None or pd.isna(inn):aud['inn_missing']+=1;continue
   if inn in seen:aud['inn_duplicates']+=1
   seen.add(inn)
  valid=d.lat.between(-90,90).to_numpy()&d.lon.between(-180,180).to_numpy();aud['valid_source_coordinates']+=int(valid.sum());rv=d.line_2110.to_numpy();av=d.line_1600.to_numpy();pv=d.line_2400.to_numpy();base=d.inn.notna().to_numpy()&d.eligible.eq(1).to_numpy()&d.filed.eq(1).to_numpy()&d.articulated.eq(1).to_numpy()&d.outlier.eq(0).to_numpy()&d.line_2110.ge(0).to_numpy();strict=base&d.geocoding_quality.eq('house').to_numpy()&d.imputed.eq(0).to_numpy();aud['baseline_before_location']+=int(base.sum());aud['strict_before_location']+=int(strict.sum());aud['missing_revenue']+=int(d.line_2110.isna().sum());aud['negative_revenue']+=int(d.line_2110.lt(0).sum())
  for flag in ['eligible','filed','outlier','imputed']:aud[flag]+=int(d[flag].eq(1).sum())
  loc=np.full(len(d),-1,int);dist=np.full(len(d),np.inf);w=np.zeros(len(d),bool);ii=np.flatnonzero(valid&base)
  if len(ii):
   ch,ix=tree.query(xyz(d.lat.to_numpy()[ii],d.lon.to_numpy()[ii]),workers=2);dist[ii]=2*R*np.arcsin(np.clip(ch/2,0,1));loc[ii]=mi[ix];w[ii]=selfpoint[ix]
  ss=d.okved_section.fillna('UNKNOWN').astype(str).to_numpy()
  for k,(threshold,q) in enumerate(MODES):
   mask=(base if q=='baseline' else strict)&(loc>=0)&(dist<=threshold);ci=loc[mask]
   for col,val in enumerate([np.ones(len(d)),rv,np.nan_to_num(av),np.nan_to_num(pv),np.isfinite(av),np.isfinite(pv)]):np.add.at(sums[k,:,col],ci,val[mask])
   np.maximum.at(maximum[k],ci,rv[mask]);z=pd.DataFrame(dict(ci=ci,sector=ss[mask],revenue=rv[mask]));groups=z.groupby(['ci','sector'],dropna=False).agg(n=('revenue','size'),rev=('revenue','sum'));assert groups.n.sum()==mask.sum()
   for (j,s),row in groups.iterrows():sec[k,int(j),s]+=row.to_numpy()
   if threshold==5:
    mask=mask&w;z=pd.DataFrame(dict(ci=loc[mask],sector=ss[mask],revenue=rv[mask]));groups=z.groupby(['ci','sector'],dropna=False).agg(n=('revenue','size'),rev=('revenue','sum'));assert groups.n.sum()==mask.sum()
    for (j,s),row in groups.iterrows():wsec[q,int(j),s]+=row.to_numpy()
 assert aud['rows']==pf.metadata.num_rows and aud['inn_duplicates']==0,dict(aud)
 for k,(threshold,q) in enumerate(MODES):
  assert int(sum(v[0] for (kk,j,s),v in sec.items() if kk==k))==int(sums[k,:,0].sum());assert np.isclose(sum(v[1] for (kk,j,s),v in sec.items() if kk==k),sums[k,:,1].sum())
  for j in np.flatnonzero(sums[k,:,0]):financial.append(dict(center_id=cids[j],year=year,max_distance_km=threshold,quality=q,n_organizations=int(sums[k,j,0]),revenue_thousand_rub_nominal=sums[k,j,1],assets_thousand_rub_nominal=sums[k,j,2] if sums[k,j,4]>0 else np.nan,profit_thousand_rub_nominal=sums[k,j,3] if sums[k,j,5]>0 else np.nan,top_firm_revenue_share=maximum[k,j]/sums[k,j,1] if sums[k,j,1]>0 else np.nan))
  aud[f'{q}_{threshold}km_n']=int(sums[k,:,0].sum());aud[f'{q}_{threshold}km_revenue']=float(sums[k,:,1].sum())
 sectors.extend(dict(center_id=cids[j],year=year,max_distance_km=MODES[k][0],quality=MODES[k][1],okved_section=s,n_organizations=int(v[0]),revenue_thousand_rub_nominal=v[1]) for (k,j,s),v in sec.items());witnesses.extend(dict(center_id=cids[j],year=year,max_distance_km=5,quality=q,okved_section=s,n_organizations=int(v[0]),revenue_thousand_rub_nominal=v[1]) for (q,j,s),v in wsec.items());rec.update(coverage=dict(aud),quality=dict(quality),elapsed_seconds=time.time()-t);print('DONE',year,dict(aud),flush=True)
save(pd.DataFrame(financial),'financial_observations');save(pd.DataFrame(sectors),'sector_sensitivity');save(pd.DataFrame(witnesses),'center_economic_witness');tmp=a.out/'coverage.json.tmp';tmp.write_text(json.dumps(receipts,indent=2));os.replace(tmp,a.out/'coverage.json')
manifest=dict(model_input_name=a.membership.name,model_sha256=sha(a.membership),interpretation='Registered legal entity addresses projected through nearest observed NP; not jobs, production locations, commuting or service flows',units='thousand nominal rubles, no deflation',outputs=[dict(name=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(a.out.glob('*')) if p.suffix in ['.csv','.parquet','.json'] and p.name!='FINISHED.json']);tmp=a.out/'FINISHED.json.tmp';tmp.write_text(json.dumps(manifest,indent=2));os.replace(tmp,a.out/'FINISHED.json');print('FINISHED',a.out,flush=True)
