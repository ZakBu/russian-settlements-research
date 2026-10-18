"""Independent replication. Main geography/compare implementations not read."""
import csv,gzip,hashlib,json,math,pathlib
from collections import defaultdict
import numpy as np
import pandas as pd
from pyproj import Geod
O=pathlib.Path('stage2_work/replication'); P=pathlib.Path('repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz')
sha=hashlib.sha256(P.read_bytes()).hexdigest()
with gzip.open(P,'rt') as f: rows=list(csv.DictReader(f))
for r in rows:
 for y in ('2002','2010','2021'):r['p'+y]=float(r['population_'+y])
assert len(rows)==142570 and len(set(r['entity_uid'] for r in rows))==len(rows)
assert sha=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c'
def write(name,rs):
 with open(O/name,'w') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
# Group definitions derive directly from protocol, no audit code imported.
for col in ['population_value_quality_2010','source_file_2010','effective_region_norm_2010']:
 groups=defaultdict(list)
 for r in rows:groups[r[col] or '<MISSING>'].append(r)
 out=[]
 for k,rs in sorted(groups.items()):
  z=sum(r['p2010']==0 for r in rs);ret=sum(r['p2010']==0 and r['p2021']>0 for r in rs);pos=sum(r['p2010']>0 for r in rs);pz=sum(r['p2010']>0 and r['p2021']==0 for r in rs)
  out.append(dict(group=k,n=len(rs),zero2010_n=z,return2021_n=ret,positive2010_n=pos,zero2021_frompositive_n=pz,return_among_zero2010=ret/z if z else None,zero2021_among_positive2010=pz/pos if pos else None))
 write('independent_denominators_'+col+'.csv',out)
groups=defaultdict(list)
for r in rows:groups[r['effective_region_norm_2002']].append(r)
out=[]
for k,rs in sorted(groups.items()):
 rs=sorted(rs,key=lambda r:(-r['p2002'],r['entity_uid']))
 rec={'unit':k,'n_rows':len(rs),'n_positive2002':sum(r['p2002']>0 for r in rs)}
 for y in ['2002','2010','2021']:rec['population'+y]=math.fsum(r['p'+y] for r in rs)
 for share in [10,1]:
  n=math.ceil(len(rs)*share/100);rec[f'top{share}_count']=n
  for y in ['2002','2010','2021']:rec[f'top{share}_share{y}']=math.fsum(r['p'+y] for r in rs[:n])/rec['population'+y] if rec['population'+y] else None
 rec['survived2002_2021']=sum(r['p2002']>0 and r['p2021']>0 for r in rs)
 rec['reentries2002_2021']=sum(r['p2002']==0 and r['p2021']>0 for r in rs)
 out.append(rec)
write('independent_regional_metrics.csv',out)
# Deterministic hash-sampling before looking at reference distance values.
origins=sorted([r for r in rows if r['p2002']>0],key=lambda r:hashlib.sha256(('stage2-independent-60:'+r['entity_uid']).encode()).hexdigest())[:60]
g=Geod(ellps='WGS84');checks=[]
for y in ['2002','2021']:
 candidates=sorted([r for r in rows if r['p'+y]>0],key=lambda r:r['entity_uid'])
 lon=np.array([float(r['longitude_2002']) for r in candidates]);lat=np.array([float(r['latitude_2002']) for r in candidates]);uids=np.array([r['entity_uid'] for r in candidates])
 for r in origins:
  dist=g.inv(np.full(len(lon),float(r['longitude_2002'])),np.full(len(lat),float(r['latitude_2002'])),lon,lat)[2]/1000
  dist[uids==r['entity_uid']]=np.inf;j=int(np.argmin(dist))
  checks.append(dict(entity_uid=r['entity_uid'],year=y,distance_km=float(dist[j]),neighbor_uid=str(uids[j])))
write('independent_nn60.csv',checks)
# Invariance checks intentionally include ties, coincident UIDs, and zero denominators.
p=np.array([10.,10.,0.,2.]);uids=['b','a','c','d'];order=sorted(range(4),key=lambda i:(-p[i],uids[i]));assert order[:2]==[1,0]
assert abs(p[order[0]]/p.sum()-(p*7)[order[0]]/(p*7).sum())<1e-15
assert math.ceil(.1*4)==1
assert sum(p>0)==3
# Distinct identities colocated remain valid; same UID excluded.
xx=np.array([0.,0.,1.]); dd=g.inv(np.zeros(3),np.zeros(3),xx,np.zeros(3))[2];dd[0]=np.inf;assert np.argmin(dd)==1 and dd[1]==0
assert (None if dd[1]==0 else 1/dd[1]) is None
json.dump(dict(status='passed',checks=['proportional_scaling','UID_tie_order','ceil_top_count','zero_not_positive','exclude_self_UID','coincident_distinct_UID','zero_ratio_undefined']),open(O/'synthetic_receipt.json','w'),indent=2)
# Only now read primary output tables for comparison.
errors=[];counts={}
ref=pd.read_csv('stage2_work/geo/outputs/territory_metrics.csv');ref=ref[ref.kind=='region'].set_index('unit')
for rec in out:
 for col,v in rec.items():
  if col=='unit':continue
  w=ref.loc[rec['unit'],col]
  if v is not None and not np.isclose(float(v),float(w),rtol=1e-12,atol=1e-10):errors.append({'check':'regional','unit':rec['unit'],'field':col,'independent':v,'primary':float(w)})
counts['regional_values']=len(out)*(len(out[0])-1)
refnn=pd.read_csv('stage2_work/geo/outputs/point_distances.csv.gz').set_index('entity_uid');maxdiff=0
for rec in checks:
 w=refnn.loc[rec['entity_uid'],'nn'+rec['year']+'_km'];dif=abs(rec['distance_km']-w);maxdiff=max(maxdiff,dif)
 # Ties can differ at floating precision. Distance must agree.
 if dif>1e-8:errors.append({'check':'NN','uid':rec['entity_uid'],'year':rec['year'],'difference_km':dif})
counts['nn_geodesic_full_search']=len(checks)
for col in ['population_value_quality_2010','source_file_2010','effective_region_norm_2010']:
 a=pd.read_csv(O/('independent_denominators_'+col+'.csv')).set_index('group');b=pd.read_csv('stage2_work/audit/denominators_by_'+col+'.csv').set_index('group')
 for k in a.index:
  for field in a.columns:
   v=a.loc[k,field];w=b.loc[k,field]
   if pd.isna(v) and pd.isna(w):continue
   if not np.isclose(v,w,rtol=1e-12,atol=1e-12):errors.append({'check':'denominator','group':k,'field':field,'independent':float(v),'primary':float(w)})
 counts[col]=a.size
json.dump(dict(input_sha256=sha,n=len(rows),unique_uid=len(set(r['entity_uid'] for r in rows)),counts=counts,nn_max_difference_km=maxdiff,errors=errors,status='passed' if not errors else 'failed',independent_implementation=True,main_geography_compare_not_read=True),open(O/'replication_receipt.json','w'),indent=2,ensure_ascii=False)
print(json.load(open(O/'replication_receipt.json')))
