#!/usr/bin/env python3
"""Independent checks for normalized/historical context, stratified 100 targets."""
import csv,gzip,math,hashlib,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; R=6371.0088; radii=(10,30,60,100)
p=ROOT/'repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
rows=[];strata={k:[] for k in ['zero2010','positive_under100','positive_100to999','positive_1000plus']}
with gzip.open(p,'rt',newline='') as f:
 for d in csv.DictReader(f):
  p0=float(d['population_2002']);p1=float(d['population_2010'])
  r=(d['entity_uid'],math.radians(float(d['latitude_2010'])),math.radians(float(d['longitude_2010'])),p0,p1)
  rows.append(r);k='zero2010' if p1==0 else 'positive_under100' if p1<100 else 'positive_100to999' if p1<1000 else 'positive_1000plus';strata[k].append(r)
targets=[(k,r) for k,rr in strata.items() for r in sorted(rr,key=lambda r:hashlib.sha256(('independent-stratified-v1|'+r[0]).encode()).hexdigest())[:25]]
out=[];start=time.time()
for stratum,(uid,lat,lon,pop0,pop1) in targets:
 accum=[[0,0,0.,0.,0.,0.,0,0] for _ in radii]; ds=[]
 for j,la,lo,po0,po1 in rows:
  if j==uid:continue
  a=math.sin((la-lat)/2)**2+math.cos(lat)*math.cos(la)*math.sin((lo-lon)/2)**2
  d=2*R*math.asin(math.sqrt(min(1,max(0,a))));ds.append(d)
  for k,r in enumerate(radii):
   if d<=r:
    v=accum[k];v[0]+=1;v[1]+=po1>0;v[2]+=po0;v[3]+=po1;v[4]+=po1*po1;v[5]=max(v[5],po1);v[6]+=po0>0;v[7]+=(po0>0 and po1==0)
 z={'entity_uid':uid,'stratum':stratum};ds.sort();z['nn1']=ds[0];z['nn5_mean']=sum(ds[:5])/5
 for r,v in zip(radii,accum):
  n,np,s0,s1,ss,m,nold,nzero=v;prefix='r'+str(r)+'_'
  z.update({prefix+'mass2010':s1,prefix+'count_all':n,prefix+'count_positive':np,prefix+'maxshare':m/s1 if s1 else None,prefix+'effective_n':s1*s1/ss if ss else None,prefix+'density2010':s1/(math.pi*r*r),prefix+'history_symmetric_change':2*(s1-s0)/(s1+s0) if s1+s0 else None,prefix+'history_zero_fraction':nzero/nold if nold else None,prefix+'empty':int(n==0)})
 out.append(z)
f=Path(__file__).with_name('geometry_stratified100.csv')
with f.open('w',newline='') as o:
 w=csv.DictWriter(o,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
Path(__file__).with_name('geometry_stratified_receipt.json').write_text(json.dumps({'status':'computed','targets':100,'target_selection':'25 per population2010 stratum, smallest SHA256(independent-stratified-v1|UID)','strata_sizes':{k:len(v) for k,v in strata.items()},'independent_method':'stdlib math brute force haversine; complete candidate set; UID self exclusion; sorted all distances for nearest neighbors','elapsed_seconds':time.time()-start,'sha256_output':hashlib.sha256(f.read_bytes()).hexdigest(),'comparison_not_yet_performed':True},indent=2)+'\n')
print('Completed',len(out),'stratified queries in',time.time()-start,'seconds')
