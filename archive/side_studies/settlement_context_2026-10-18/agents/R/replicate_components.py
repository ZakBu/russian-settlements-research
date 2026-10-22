import csv,gzip,math,hashlib,json
from pathlib import Path
from collections import defaultdict,Counter
from pyproj import Transformer
root=Path(__file__).resolve().parents[2];R=6371.0088;trans=Transformer.from_crs(4326,6933,always_xy=True);regions=defaultdict(list)
with gzip.open(root/'repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz','rt') as f:
 for r in csv.DictReader(f):
  p=float(r['population_2010']);la=float(r['latitude_2010']);lo=float(r['longitude_2010'])
  if p<=0:continue
  x,y=trans.transform(lo,la);block=f'{math.floor(x/200000)}:{math.floor(y/200000)}'
  if int(hashlib.sha256(('settlement-context-v1|'+block).encode()).hexdigest(),16)%5==0:continue
  z=float(r['population_2021'])==0
  regions[r['effective_region_norm_2010']].append((math.radians(la),math.radians(lo),p,z))
chosen=sorted((len(v),k) for k,v in regions.items() if len(v)>50)[:3]
checks=[];errors=[]
curves={(r['region'],float(r['radius_km'])):r for r in csv.DictReader(open(root/'research_staging/e3/regional_curves.csv')) if r['grid']=='absolute_km'}
for n,k in chosen:
 v=regions[k];edges=[]
 for i in range(n):
  for j in range(i):
   la,lo,_,_=v[i];lb,lp,_,_=v[j];a=math.sin((la-lb)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lo-lp)/2)**2;d=2*R*math.asin(math.sqrt(min(1,max(0,a))))
   if d<=30:edges.append((d,i,j))
 for radius in [2,10,30]:
  c=curves[(k,radius)];result={}
  for label,active in [('initial',set(range(n))),('surviving',{i for i,x in enumerate(v) if not x[3]})]:
   parent={i:i for i in active};deg=Counter();en=0
   def find(i):
    while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
    return i
   for d,i,j in edges:
    if d<=radius and i in active and j in active:
     a,b=find(i),find(j);parent[a]=b;deg[i]+=1;deg[j]+=1;en+=1
   comps=Counter(find(i) for i in active);lcc=max(comps.values());isolated=sum(deg[i]==0 for i in active)
   result.update({label+'_active_n':len(active),label+'_lcc_n':lcc,label+'_isolated_n':isolated,label+'_components':len(comps),'edges_'+label:en})
  for key,value in result.items():
   got=float(c[key]);checks.append([k,radius,key,value,got])
   if value!=got:errors.append(checks[-1])
report={'status':'reviewed' if not errors else 'needs_revision','method':'Independent standard-library brute edges and disjoint-set components; pyproj6933 + direct SHA masks;2021 converted only after dev membership','regions':chosen,'radii':[2,10,30],'checks':len(checks),'mismatch_count':len(errors),'mismatches':errors}
(root/'research_staging/replication/components_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report)
