import csv,gzip,math,json
from pathlib import Path
root=Path(__file__).resolve().parents[2];R=6371.0088
with gzip.open(root/'repo/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz','rt') as f:
 rows=[(r['entity_uid'],float(r['population_2010']),math.radians(float(r['latitude_2010'])),math.radians(float(r['longitude_2010']))) for r in csv.DictReader(f)]
targetids={r['entity_uid'] for r in csv.DictReader(open(root/'research_staging/replication/blind_initial/geometry_stratified100.csv'))}
with gzip.open(root/'research_staging/geo/features.csv.gz','rt') as f:features={r['entity_uid']:r for r in csv.DictReader(f) if r['entity_uid'] in targetids}
fed=[r for r in csv.DictReader(open(root/'repo/publication/stage71/accepted_common_federal_territory_axis.csv')) if r['census_year']=='2010']
def dist(a,b,c,d):
 q=math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2
 return 2*R*math.asin(math.sqrt(min(1,max(0,q))))
errors=[];maxerr=0;tests=0
for uid,p,la,lo in rows:
 if uid not in targetids:continue
 best={k:[math.inf,[]] for k in ['nearest_ge10000','nearest_ge100000','nearest_larger']}
 for j,pj,laj,loj in rows:
  if j==uid:continue
  eligible=[k for k,yes in [('nearest_ge10000',pj>=10000),('nearest_ge100000',pj>=100000),('nearest_larger',pj>p)] if yes]
  if not eligible:continue
  d=dist(la,lo,laj,loj)
  for k in eligible:
   if d<best[k][0]-1e-9:best[k]=[d,[j]]
   elif abs(d-best[k][0])<=1e-9:best[k][1].append(j)
 for k,(d,uids) in best.items():
  m=features[uid];got=float(m[k+'_km']);tests+=2;err=abs(d-got);maxerr=max(maxerr,err)
  if err>1e-9 or m[k+'_uid'] not in uids:errors.append([uid,k,d,got,uids,m[k+'_uid']])
 for r in fed:
  d=dist(la,lo,math.radians(float(r['latitude'])),math.radians(float(r['longitude'])));got=float(features[uid]['distance_'+r['territory_key']+'_km']);tests+=1;maxerr=max(maxerr,abs(d-got))
  if abs(d-got)>1e-9:errors.append([uid,r['territory_key'],d,got])
out={'status':'reviewed' if not errors else 'needs_revision','checks':tests,'n_origins':len(targetids),'max_abs_distance_error_km':maxerr,'mismatches':errors,'tolerance_km':1e-9,'ties':'UID accepted if within1e-9km of exact minimum','method':'Separate brute force standard-library haversine; eligible masses2010; raw2010 coords; federal exact file anchors2010 rows. Does not validate census-day truth of anchors.'}
(root/'research_staging/replication/nearest_comparison.json').write_text(json.dumps(out,indent=2)+'\n');print(out)
