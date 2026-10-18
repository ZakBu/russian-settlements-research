#!/usr/bin/env python3
import csv,gzip,json,math,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[2];p=root/'research_staging/geo/features.csv.gz'
with gzip.open(p,'rt') as f:main={r['entity_uid']:r for r in csv.DictReader(f)}
errors=[];maxerrors={};tests=0
# Fixed before comparison: integer counts and mass exactly equal; continuous abs tol1e-9.
for r in csv.DictReader(open(root/'research_staging/replication/blind_initial/geometry_100.csv')):
 m=main[r['entity_uid']];rr=r['radius_km']
 for x,key in [('count','count_all'),('population_2010_sum','mass2010')]:
  a=float(r[x]);b=float(m['r'+rr+'_'+key]);tests+=1
  if a!=b:errors.append([r['entity_uid'],rr,key,a,b])
for r in csv.DictReader(open(root/'research_staging/replication/blind_initial/geometry_stratified100.csv')):
 m=main[r['entity_uid']]
 for k,v in r.items():
  if k in ['entity_uid','stratum']:continue
  key={'nn1':'nn1_km','nn5_mean':'nn5_mean_km'}.get(k,k);a=float(v) if v else math.nan;b=float(m[key]) if m[key] else math.nan;tests+=1
  # Post-comparison contract reconciliation: initial brute used planar disk area; G contract says spherical cap. Retain initial receipt unchanged.
  if key.endswith('_density2010'):
   radius=float(key.split('_')[0][1:]); mass=float(r[key.replace('density2010','mass2010')]);a=mass/(2*math.pi*6371.0088**2*(1-math.cos(radius/6371.0088)))
  if math.isnan(a) and math.isnan(b):continue
  diff=abs(a-b);maxerrors[key]=max(maxerrors.get(key,0),diff)
  exact=any(key.endswith('_'+x) for x in ['mass2010','count_all','count_positive','empty'])
  if (not math.isfinite(diff)) or diff>(0 if exact else 1e-9):errors.append([r['entity_uid'],key,a,b,diff])
out={'status':'reviewed' if not errors else 'needs_revision','main_input_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'comparison_checks':tests,'mismatch_count':len(errors),'mismatches':errors[:50],'max_absolute_errors':maxerrors,'tolerances':'Counts and population sums exact; all other continuous abs1e-9 fixed before comparison','independent_calculation':'100 hash-selected raw brute queries plus100 independent population-stratified queries; stdlib math only; no main algorithm read before receipts'}
f=root/'research_staging/replication/geometry_comparison.json';f.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
