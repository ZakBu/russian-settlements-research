"""Fresh independent audit of recovered aggregates; not a new computation of raw firm rows."""
import pathlib,json,hashlib,zipfile,pandas as pd,numpy as np
P=pathlib.Path(__file__).resolve().parent;A=P.parents[3]/'recovery/SGRT_RFSD_RECOVERED.zip';OUT=P/'reference2002_recovered';OUT.mkdir(exist_ok=True);checks=[]
def ck(n,v):assert v,n;checks.append(dict(check=n,passed=True))
ck('archive SHA256',hashlib.sha256(A.read_bytes()).hexdigest()=='a1f4cf310b3fac8d0fd5cf2375e203ed7c589fbef7cabe05a52e7ab2fb33a6ef')
with zipfile.ZipFile(A) as z:
 ck('ZIP CRC',z.testzip() is None)
 z.extractall(OUT)
r=json.loads((OUT/'coverage_provenance.json').read_text());tree={int(x['path'].split('year=')[1].split('/')[0]):x for x in json.loads((P/'hf_tree.txt').read_text()) if x['path'].endswith('.parquet')}
f=pd.read_parquet(OUT/'zone_financial.parquet');s=pd.read_parquet(OUT/'zone_sectors.parquet');lf=pd.read_parquet(OUT/'localfirst_financial.parquet');ls=pd.read_parquet(OUT/'localfirst_sectors.parquet')
for name in ['zone_financial','zone_sectors','localfirst_financial','localfirst_sectors']:
 a=pd.read_csv(OUT/(name+'.csv'));b=pd.read_parquet(OUT/(name+'.parquet'));ck(name+' CSV/Parquet shape',a.shape==b.shape)
 for c in a.columns:
  if pd.api.types.is_numeric_dtype(b[c]):ck(name+' CSV/Parquet '+c,np.allclose(a[c],b[c],equal_nan=True))
ck('unique zone fiscal',not f.duplicated(['center_id','year','selection']).any());ck('unique zone sectors',not s.duplicated(['center_id','year','okved_section']).any());ck('unique local fiscal',not lf.duplicated(['center_id','year','max_distance_km','quality']).any())
for rr in r:
 y=rr['year'];v=rr['coverage'];ck(str(y)+' archived successful raw receipt',rr['status']=='ok');ck(str(y)+' pinned source SHA',rr['source_sha256']==tree[y]['lfs']['oid']);ck(str(y)+' pinned source bytes',rr['bytes_transferred']==tree[y]['size']);ck(str(y)+' row counts',rr['schema_rows']==v['rows']);ck(str(y)+' schema-first',rr['footer_bytes']>0 and len(rr['schema_columns'])==223)
 for q in ['baseline','strict_house_nonimputed','house_or_street','all_outliers_included']:
  z=f[(f.year==y)&(f.selection==q)];ck(str(y)+q+' count',z.n_organizations.sum()==v[q+'_n']);ck(str(y)+q+' revenue',np.isclose(z.revenue_thousand_rub_nominal.sum(),v[q+'_revenue']))
 z=s[s.year==y];b=f[(f.year==y)&(f.selection=='baseline')];ck(str(y)+' sector baseline counts',z.n_organizations.sum()==b.n_organizations.sum());ck(str(y)+' sector baseline revenue',np.isclose(z.revenue_thousand_rub_nominal.sum(),b.revenue_thousand_rub_nominal.sum()))
 b=lf[(lf.year==y)&(lf.quality=='baseline')&(lf.max_distance_km==5)];z=ls[ls.year==y];ck(str(y)+' LF5 sector counts',z.n_organizations.sum()==b.n_organizations.sum());ck(str(y)+' LF5 sector revenue',np.isclose(z.revenue_thousand_rub_nominal.sum(),b.revenue_thousand_rub_nominal.sum()))
 totals=lf[lf.year==y].groupby(['quality','max_distance_km']).n_organizations.sum();ck(str(y)+' thresholds nested',all(totals[q,1]<=totals[q,5]<=totals[q,10] for q in ['baseline','strict']));ck(str(y)+' strict subset',all(totals['strict',d]<=totals['baseline',d] for d in [1,5,10]))
(P/'reference_archive_verification.json').write_text(json.dumps(dict(passed=True,n_checks=len(checks),scope='Recovered 2002-reference grouped artifacts; no new raw-data calculation claimed',checks=checks),indent=2));print('PASS',len(checks),'fresh recovered archive checks')
