"""Cloud worker: schema-first, pinned & SHA checked annual RFSD, streaming aggregates only.
python research/sgrt_results_20261018/rfsd/cloud_missing_years.py --out cloud_rfsd
No raw/source writes; temporary files auto-removed; only grouped outputs are exported.
"""
import pathlib,json,time,collections,hashlib,urllib.request,struct,io,tempfile,argparse,gc
import pandas as pd,numpy as np,pyarrow.parquet as pq
from scipy.spatial import cKDTree
SCRIPT=pathlib.Path(__file__).resolve().parent;R=6371.0088
P=argparse.ArgumentParser();P.add_argument('--out',default='cloud_rfsd');P.add_argument('--years',default='2011,2012,2013,2014,2015,2016,2021');args=P.parse_args();OUT=pathlib.Path(args.out);OUT.mkdir(parents=True,exist_ok=True)
meta=json.loads((SCRIPT/'hf_metadata.txt').read_text());REV=meta['sha'];items={int(x['path'].split('year=')[1].split('/')[0]):x for x in json.loads((SCRIPT/'hf_tree.txt').read_text()) if x['path'].endswith('.parquet')}

def xyz(lat,lon):
 la,lo=np.radians(lat),np.radians(lon);return np.column_stack((np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)))
cent=pd.read_csv(SCRIPT/'cloud_centers.csv');N=len(cent);cc=xyz(cent.lat,cent.lon);tree=cKDTree(cc);mass=cent.population_2002.to_numpy();mem=pd.read_parquet(SCRIPT/'cloud_localfirst_points.parquet');mem=mem[mem.center_id.notna()].reset_index(drop=True);lcids=sorted(mem.center_id.unique());lmap=dict(zip(lcids,range(len(lcids))));mci=mem.center_id.map(lmap).to_numpy();stree=cKDTree(xyz(mem.lat,mem.lon));cache={};parts=[];localparts=[];sectorparts=[];local_sectors=[];receipts=[]
COLS=['inn','eligible','filed','articulated','outlier','imputed','geocoding_quality','lon','lat','line_2110','line_1600','line_2400','okved_section'];labels=['baseline','strict_house_nonimputed','house_or_street','all_outliers_included']
def write():
 (OUT/'coverage_provenance.json').write_text(json.dumps(receipts,indent=2))
 for frames,name in [(parts,'zone_financial'),(localparts,'localfirst_financial'),(sectorparts,'zone_sectors'),(local_sectors,'localfirst_sectors')]:
  if frames:
   df=pd.concat(frames,ignore_index=True);df.to_csv(OUT/(name+'.csv'),index=False);df.to_parquet(OUT/(name+'.parquet'),index=False)
for y in map(int,args.years.split(',')):
 t=time.time();x=items[y];n=x['size'];url=f"https://huggingface.co/datasets/irlspbru/RFSD/resolve/{REV}/{x['path']}";rec=dict(year=y,url=url,revision=REV,source_expected_bytes=n,source_expected_sha256=x['lfs']['oid'],status='started');receipts.append(rec);write()
 try:
  # Range metadata inspection PRECEDES downloading row data.
  def rng(start,end,tag):
   req=urllib.request.Request(url+'?range='+tag,headers={'Range':f'bytes={start}-{end}'})
   with urllib.request.urlopen(req,timeout=90) as r:
    b=r.read();assert r.status==206 and len(b)==end-start+1,(r.status,len(b));return b
  tail=rng(n-8,n-1,'trailer');assert tail[-4:]==b'PAR1';m=struct.unpack('<I',tail[:4])[0];footer=rng(n-m-8,n-1,'schema');schema_pf=pq.ParquetFile(io.BytesIO(b'PAR1'+footer));rec.update(schema_rows=schema_pf.metadata.num_rows,schema_columns=schema_pf.schema_arrow.names,footer_bytes=m,metadata_bytes_transferred=m+16,selected_columns=COLS);assert set(COLS)<=set(schema_pf.schema_arrow.names);del schema_pf,footer;gc.collect()
  with tempfile.TemporaryDirectory() as td:
   raw=pathlib.Path(td)/'source.parquet';h=hashlib.sha256();nb=0
   with urllib.request.urlopen(url,timeout=180) as r,raw.open('wb') as f:
    while True:
     b=r.read(2**20)
     if not b:break
     f.write(b);h.update(b);nb+=len(b)
   rec.update(bytes_transferred=nb,source_sha256=h.hexdigest());assert nb==n and h.hexdigest()==x['lfs']['oid'],'SOURCE_LENGTH_OR_SHA_MISMATCH'
   pf=pq.ParquetFile(raw);assert pf.metadata.num_rows==rec['schema_rows'];seen=set();quality=collections.Counter();audit=collections.Counter();agg=np.zeros((4,N,5));l_agg=np.zeros((6,len(lcids),5));top=np.zeros((4,N));ltop=np.zeros((6,len(lcids)));sec=collections.defaultdict(lambda:np.zeros(2));lsec=collections.defaultdict(lambda:np.zeros(2));missing=np.zeros((4,N,2));lmissing=np.zeros((6,len(lcids),2))
   for b in pf.iter_batches(batch_size=50000,columns=COLS):
    d=b.to_pandas();audit['rows']+=len(d);quality.update(d.geocoding_quality.fillna('missing'))
    for inn in d.inn:
     if inn is None:audit['inn_missing']+=1;continue
     if inn in seen:audit['inn_duplicates']+=1
     seen.add(inn)
    valid=d.lat.between(-90,90)&d.lon.between(-180,180);audit['valid_coordinates']+=int(valid.sum());keys=list(zip(d.lat,d.lon));unknown=list(dict.fromkeys(k for k,v in zip(keys,valid) if v and k not in cache))
    if unknown:
     pp=np.array(unknown);xx=xyz(pp[:,0],pp[:,1]);ch,near=stree.query(xx,workers=2);near_dist=2*R*np.arcsin(np.clip(ch/2,0,1));nbs=tree.query_ball_point(xx,2*np.sin(100/(2*R)),workers=2)
     for key,coord,nb,j,distn in zip(unknown,xx,nbs,near,near_dist):
      win=-1
      if nb:
       nb=np.array(nb);ds=2*R*np.arcsin(np.clip(np.linalg.norm(cc[nb]-coord,axis=1)/2,0,1));win=int(nb[np.argmax(mass[nb]/(ds+5)**2)])
      cache[key]=(win,int(mci[j]),float(distn))
    mapped=np.array([cache.get(k,(-1,-1,np.inf)) if v else (-1,-1,np.inf) for k,v in zip(keys,valid)]);ci=mapped[:,0].astype(int);li=mapped[:,1].astype(int);ldist=mapped[:,2];audit['assigned']+=int((ci>=0).sum())
    for name in ['eligible','filed','outlier','imputed']:audit[name]+=int(d[name].eq(1).sum())
    audit['missing_revenue']+=int(d.line_2110.isna().sum());audit['negative_revenue']+=int(d.line_2110.lt(0).sum());pre=d.inn.notna().to_numpy()&d.eligible.eq(1).to_numpy()&d.filed.eq(1).to_numpy()&d.articulated.eq(1).to_numpy()&d.line_2110.ge(0).to_numpy();base=pre&d.outlier.eq(0).to_numpy();strict=base&d.geocoding_quality.eq('house').to_numpy()&d.imputed.eq(0).to_numpy();street=base&d.geocoding_quality.isin(['house','street']).to_numpy();rv=d.line_2110.to_numpy();av=d.line_1600.to_numpy();pv=d.line_2400.to_numpy();audit['baseline_before_location']+=int(base.sum())
    for k,mask in enumerate([base,strict,street,pre]):
     mask=mask&(ci>=0);ii=ci[mask]
     for col,vals in enumerate([np.ones(len(d)),rv,np.nan_to_num(av),np.nan_to_num(pv),np.isfinite(av)]):np.add.at(agg[k,:,col],ii,vals[mask])
     np.add.at(missing[k,:,0],ii,np.isfinite(av[mask]));np.add.at(missing[k,:,1],ii,np.isfinite(pv[mask]));np.maximum.at(top[k],ii,rv[mask])
     if k==0:
      zz=pd.DataFrame(dict(idx=ii,section=d.okved_section[mask].fillna('missing'),revenue=rv[mask]))
      for (i,s),v in zz.groupby(['idx','section']).agg(n=('revenue','size'),rev=('revenue','sum')).iterrows():sec[(i,s)]+=v.to_numpy()
    for k,(dist,qual) in enumerate([(1,base),(5,base),(10,base),(1,strict),(5,strict),(10,strict)]):
     mask=qual&(li>=0)&(ldist<=dist);ii=li[mask]
     for col,vals in enumerate([np.ones(len(d)),rv,np.nan_to_num(av),np.nan_to_num(pv),np.isfinite(av)]):np.add.at(l_agg[k,:,col],ii,vals[mask])
     np.add.at(lmissing[k,:,0],ii,np.isfinite(av[mask]));np.add.at(lmissing[k,:,1],ii,np.isfinite(pv[mask]));np.maximum.at(ltop[k],ii,rv[mask])
     if k==1:
      zz=pd.DataFrame(dict(idx=ii,section=d.okved_section[mask].fillna('missing'),revenue=rv[mask]))
      for (i,s),v in zz.groupby(['idx','section']).agg(n=('revenue','size'),rev=('revenue','sum')).iterrows():lsec[(i,s)]+=v.to_numpy()
   assert audit['rows']==rec['schema_rows'] and audit['inn_duplicates']==0
   def frame(vals,mx,miss,names,k):
    ii=np.flatnonzero(vals[k,:,0]);return pd.DataFrame(dict(center_id=np.array(names)[ii],year=y,n_organizations=vals[k,ii,0].astype(int),revenue_thousand_rub_nominal=vals[k,ii,1],assets_thousand_rub_nominal=np.where(miss[k,ii,0]>0,vals[k,ii,2],np.nan),profit_thousand_rub_nominal=np.where(miss[k,ii,1]>0,vals[k,ii,3],np.nan),top_firm_revenue_share=mx[k,ii]/np.where(vals[k,ii,1]>0,vals[k,ii,1],np.nan)))
   for k,label in enumerate(labels):
    z=frame(agg,top,missing,cent.id,k);z['selection']=label;parts.append(z);audit[label+'_n']=int(agg[k,:,0].sum());audit[label+'_revenue']=float(agg[k,:,1].sum())
   for k,(dist,q) in enumerate([(1,'baseline'),(5,'baseline'),(10,'baseline'),(1,'strict'),(5,'strict'),(10,'strict')]):
    z=frame(l_agg,ltop,lmissing,lcids,k);z['max_distance_km']=dist;z['quality']=q;localparts.append(z);audit[f'localfirst_{q}_{dist}km_n']=int(l_agg[k,:,0].sum());audit[f'localfirst_{q}_{dist}km_revenue']=float(l_agg[k,:,1].sum())
   for records,names,dest in [(sec,cent.id,sectorparts),(lsec,lcids,local_sectors)]:dest.append(pd.DataFrame([dict(center_id=names[i],year=y,okved_section=s,n_organizations=int(v[0]),revenue_thousand_rub_nominal=v[1]) for (i,s),v in records.items()]))
   rec.update(status='ok',coverage=dict(audit),quality=dict(quality));del pf,seen
 except Exception as e:rec.update(status='error',error=repr(e))
 rec['elapsed_seconds']=time.time()-t;write();print('DONE',y,rec['status'],rec.get('error'),rec.get('coverage'),flush=True);gc.collect()
# A failing year is explicitly visible and makes workflow unsuccessful; completed years remain in artifact.
assert all(r['status']=='ok' for r in receipts),[(r['year'],r.get('error')) for r in receipts if r['status']!='ok']
