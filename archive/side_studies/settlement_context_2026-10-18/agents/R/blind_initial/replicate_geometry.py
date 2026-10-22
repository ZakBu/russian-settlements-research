#!/usr/bin/env python3
"""100 brute force all-pairs queries, no spatial index, excludes UID equality."""
import csv,gzip,math,hashlib,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; R=6371.0088
p=ROOT/'repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz'
rows=[]
with gzip.open(p,'rt',newline='') as f:
 for d in csv.DictReader(f):rows.append((d['entity_uid'],math.radians(float(d['latitude_2010'])),math.radians(float(d['longitude_2010'])),float(d['population_2010'])))
targets=sorted(rows,key=lambda r:hashlib.sha256(('independent-query-v1|'+r[0]).encode()).hexdigest())[:100]
out=[];start=time.time()
for uid,lat,lon,pop in targets:
 counts=[0]*4;masses=[0.]*4
 for j,la,lo,po in rows:
  if j==uid:continue
  a=math.sin((la-lat)/2)**2+math.cos(lat)*math.cos(la)*math.sin((lo-lon)/2)**2
  d=2*R*math.asin(math.sqrt(min(1,max(0,a))))
  for k,r in enumerate((10,30,60,100)):
   if d<=r:counts[k]+=1;masses[k]+=po
 for r,c,m in zip((10,30,60,100),counts,masses):out.append({'entity_uid':uid,'radius_km':r,'count':c,'population_2010_sum':int(m)})
f=Path(__file__).with_name('geometry_100.csv')
with f.open('w',newline='') as o:
 w=csv.DictWriter(o,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
Path(__file__).with_name('geometry_receipt.json').write_text(json.dumps({'status':'computed','method':'stdlib math brute-force haversine','R_km':R,'coordinate_year':2010,'mass_year':2010,'self_exclusion':'UID equality','threshold':'distance <= radius','target_selection':'100 smallest SHA256(independent-query-v1|UID)','query_count':100,'source_rows':len(rows),'elapsed_seconds':time.time()-start,'sha256_output':hashlib.sha256(f.read_bytes()).hexdigest(),'comparison_not_yet_performed':True},indent=2)+'\n')
print('Completed',len(out),'query-radius results in',time.time()-start,'seconds')
