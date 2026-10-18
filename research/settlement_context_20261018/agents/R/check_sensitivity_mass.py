import csv,gzip,math,json
from pathlib import Path
root=Path(__file__).resolve().parents[2];radii=[10,30,60,100];R=6371.0088
roster=root/'repo/research_staging/data_audit/evidence/point_drift_over5km.csv'
excluded={r['entity_uid'] for r in csv.DictReader(open(roster))}
ids=[r['entity_uid'] for r in csv.DictReader(open(root/'research_staging/replication/blind_initial/geometry_stratified100.csv'))][:10]+sorted(excluded)[:4];wanted=set(ids)
rows=[]
with gzip.open(root/'repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz','rt') as f:
 for r in csv.DictReader(f):
  selected=float(r['population_2010']);o=r['original_population_2010'];orig=float(o) if o and math.isfinite(float(o)) else selected
  rows.append((r['entity_uid'],math.radians(float(r['latitude_2010'])),math.radians(float(r['longitude_2010'])),selected,orig))
outputs={}
for name,path in [('original','geo/original2010/features.csv.gz'),('drift','geo/exclude_drift_recovery/features.csv.gz')]:
 with gzip.open(root/'research_staging'/path,'rt') as f:outputs[name]={r['entity_uid']:r for r in csv.DictReader(f) if r['entity_uid'] in wanted}
errors=[];checks=0
for uid,la,lo,p,o in rows:
 if uid not in wanted:continue
 sums={'original':[0]*4,'drift':[0]*4};counts={'original':[0]*4,'drift':[0]*4}
 for j,lb,lp,pj,oj in rows:
  if j==uid:continue
  a=math.sin((la-lb)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lo-lp)/2)**2;d=2*R*math.asin(math.sqrt(min(1,max(0,a))))
  for k,r in enumerate(radii):
   if d<=r:
    sums['original'][k]+=oj;counts['original'][k]+=1
    if j not in excluded:sums['drift'][k]+=pj;counts['drift'][k]+=1
 for variant in sums:
  for k,r in enumerate(radii):
   for key,val in [('mass2010',sums[variant][k]),('count_all',counts[variant][k])]:
    got=float(outputs[variant][uid]['r'+str(r)+'_'+key]);checks+=1
    if got!=val:errors.append([variant,uid,r,key,val,got])
report={'status':'reviewed' if not errors else 'needs_revision','targets':len(wanted),'checks':checks,'mismatches':errors,'method':'Independent brute-force spherical2010coords;10hashsampletargets+4flaggedtargets; originalfinitefallbackselected;drift48neighborsremoved,focaloriginsretained','excluded_count':len(excluded),'scope':'Mass/count only,not allvariantfeatures'}
(root/'research_staging/replication/sensitivity_mass_comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
