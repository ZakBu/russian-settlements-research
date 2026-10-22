"""Post-computation independent conservation/inclusion/hash checks on frozen projection."""
import argparse,pathlib,json,hashlib,pandas as pd,numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--projection',type=pathlib.Path,required=True);a=ap.parse_args();P=a.projection;m=json.loads((P/'FINISHED.json').read_text());checks=[]
def ck(n,v):assert v,n;checks.append(dict(check=n,passed=True))
for x in m['outputs']:ck('hash '+x['name'],hashlib.sha256((P/x['name']).read_bytes()).hexdigest()==x['sha256'])
f=pd.read_parquet(P/'financial_observations.parquet');s=pd.read_parquet(P/'sector_sensitivity.parquet');w=pd.read_parquet(P/'center_economic_witness.parquet');KEY=['center_id','year','max_distance_km','quality'];ck('unique financial keys',not f.duplicated(KEY).any());ck('unique sector keys',not s.duplicated(KEY+['okved_section']).any());ck('unassigned never financial zone',f.center_id.ne('UNASSIGNED').all());ck('witness unique keys',not w.duplicated(KEY+['okved_section']).any())
z=s.groupby(KEY).agg(n=('n_organizations','sum'),revenue=('revenue_thousand_rub_nominal','sum')).reset_index();j=f.merge(z,on=KEY,validate='one_to_one',how='outer',indicator=True);ck('all fiscal groups have sectors including unknown',j['_merge'].eq('both').all());ck('every zone sector counts equal financial',j.n_organizations.eq(j.n).all());ck('every zone sector money equals financial',np.allclose(j.revenue_thousand_rub_nominal,j.revenue,rtol=1e-11,atol=1e-4))
for year,g in f.groupby('year'):
 for q in ['baseline','strict']:
  p=g[g.quality==q].pivot(index='center_id',columns='max_distance_km',values='n_organizations').fillna(0);ck(f'{year} {q} all-zone radius nesting',((p[1]<=p[5])&(p[5]<=p[10])).all())
 for dist,h in g.groupby('max_distance_km'):
  p=h.pivot(index='center_id',columns='quality',values='n_organizations').fillna(0);ck(f'{year} {dist}km all-zone strict subset',p.strict.le(p.baseline).all())
 for q in ['baseline','strict']:
  z=w[(w.year==year)&(w.quality==q)];h=s[(s.year==year)&(s.quality==q)&(s.max_distance_km==5)];j=z.merge(h,on=KEY+['okved_section'],suffixes=('_witness','_zone'),validate='one_to_one',how='left');ck(f'{year} {q} centre-witness count subset',j.n_organizations_witness.le(j.n_organizations_zone).all());ck(f'{year} {q} centre-witness revenue subset',j.revenue_thousand_rub_nominal_witness.le(j.revenue_thousand_rub_nominal_zone+1e-4).all())
for rec in json.loads((P/'coverage.json').read_text()):
 ck(str(rec['year'])+' full rowcount',rec['rows_expected']==rec['coverage']['rows']);ck(str(rec['year'])+' INN uniqueness',rec['coverage'].get('inn_duplicates',0)==0)
(P/'verification.json').write_text(json.dumps(dict(passed=True,n_checks=len(checks),checks=checks),indent=2));print('PASS',len(checks),'fresh primary financial checks',flush=True)
