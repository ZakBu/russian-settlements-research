#!/usr/bin/env python3
"""Read-only stage71 risk audit. Run: python audit_stage2.py --input PATH --out DIR."""
from pathlib import Path
import argparse,hashlib,json,platform,datetime,re,subprocess
import pandas as pd,numpy as np
ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
P=Path(args.input).resolve();OUT=Path(args.out).resolve();OUT.mkdir(parents=True,exist_ok=True);REPO=P.parents[2]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(P)=='d40273e13a8ecf8f31bf367ddc414e21bd026eea325192629fb2f81f6dfa374c'
x=pd.read_csv(P,dtype=str,keep_default_na=False);assert x.shape==(142570,135) and x.entity_uid.is_unique
for y in [2002,2010,2021]:x[f'population_{y}']=pd.to_numeric(x[f'population_{y}'],errors='raise');assert x[f'population_{y}'].ge(0).all()
a,b,c=[x[f'population_{y}'] for y in [2002,2010,2021]]
x['path']=(a.gt(0).astype(int).astype(str)+b.gt(0).astype(int).astype(str)+c.gt(0).astype(int).astype(str))
x['size2002']=pd.cut(a,[-1,0,10,100,1000,10000,100000,np.inf],labels=['0','1-10','11-100','101-1000','1001-10000','10001-100000','>100000']).astype(str)
x['size2010']=pd.cut(b,[-1,0,10,100,1000,10000,100000,np.inf],labels=['0','1-10','11-100','101-1000','1001-10000','10001-100000','>100000']).astype(str)
x['zero2010']=b.eq(0);x['return2021']=b.eq(0)&c.gt(0);x['positive2010']=b.gt(0);x['zero2021_frompositive']=b.gt(0)&c.eq(0)
x['positive2002']=a.gt(0);x['zero2010_frompositive']=a.gt(0)&b.eq(0)
x['delta2002_2010']=b-a;x['delta2010_2021']=c-b;x['delta2002_2021']=c-a
for k in ['population_value_quality_2010','source_file_2010','effective_region_norm_2010','size2002','size2010']:
 rows=[]
 for val,g in x.groupby(k,dropna=False,sort=True):
  r={'group':val or '<MISSING>','n':len(g),'zero2010_n':int(g.zero2010.sum()),'return2021_n':int(g.return2021.sum()),'positive2010_n':int(g.positive2010.sum()),'zero2021_frompositive_n':int(g.zero2021_frompositive.sum()),'positive2002_n':int(g.positive2002.sum()),'zero2010_frompositive_n':int(g.zero2010_frompositive.sum())}
  for num,den,out in [('return2021_n','zero2010_n','return_among_zero2010'),('zero2021_frompositive_n','positive2010_n','zero2021_among_positive2010'),('zero2010_frompositive_n','positive2002_n','zero2010_among_positive2002')]:r[out]=r[num]/r[den] if r[den] else np.nan
  for y in [2002,2010,2021]:r[f'population{y}']=int(g[f'population_{y}'].sum())
  for p in ['000','001','010','011','100','101','110','111']:r['path'+p+'_n']=int(g.path.eq(p).sum())
  rows.append(r)
 pd.DataFrame(rows).to_csv(OUT/f'denominators_by_{k}.csv',index=False)
paths=[]
for pat,g in x.groupby('path',sort=True):
 r={'path':pat,'n':len(g)}
 for y in [2002,2010,2021]:
  v=g[f'population_{y}'];r.update({f'pop{y}_sum':int(v.sum()),f'pop{y}_median':float(v.median()),f'pop{y}_max':int(v.max())})
 for interval in ['2002_2010','2010_2021','2002_2021']:
  v=g['delta'+interval].abs();r.update({f'absdelta{interval}_sum':int(v.sum()),f'absdelta{interval}_median':float(v.median()),f'absdelta{interval}_p90':float(v.quantile(.9)),f'absdelta{interval}_max':int(v.max()),f'absdelta{interval}_le2':int(v.le(2).sum()),f'absdelta{interval}_gt100':int(v.gt(100).sum())})
 paths.append(r)
pd.DataFrame(paths).to_csv(OUT/'eight_paths_and_absolute_jumps.csv',index=False)
# Disjoint strata: all 8 trajectories × quality protection indicator × 2002 size (0,1–10,11–100,>100).
x['quality_bin']=np.where(x.population_value_quality_2010.str.contains('confidentiality'),'protected','other')
x['sampling_size']=pd.cut(a,[-1,0,10,100,np.inf],labels=['0','1-10','11-100','>100']).astype(str)
x['stratum']=x.path+'|'+x.quality_bin+'|'+x.sampling_size
sizes=x.groupby('stratum').size().sort_index();alloc={k:1 for k in sizes.index}
# Equal round-robin allocation across nonempty strata; no outcome-based search beyond predeclared trajectory strata.
while sum(alloc.values())<120:
 progressed=False
 for k in sizes.index:
  if alloc[k]<sizes[k] and sum(alloc.values())<120:alloc[k]+=1;progressed=True
 if not progressed:break
rng=np.random.default_rng(20261018);sample=[];strata=[]
for k,N in sizes.items():
 g=x[x.stratum.eq(k)].sort_values('entity_uid');n=alloc[k];chosen=rng.choice(len(g),n,replace=False);s=g.iloc[chosen].copy();s['stratum_N']=N;s['stratum_n']=n;s['inclusion_probability']=n/N;s['diagnostic_role']=np.where(s.path.isin(['000','111']),'stable_control','zero_transition');sample.append(s);strata.append({'stratum':k,'N':N,'n':n,'pi':n/N})
s=pd.concat(sample).sort_values(['stratum','entity_uid']);s.to_csv(OUT/'diagnostic_sample120.csv',index=False);pd.DataFrame(strata).to_csv(OUT/'sample_strata_probabilities.csv',index=False)
# Addressed local locator checks, no inference from old cache-resolution assertions.
records=[];cache={}
for _,r in s.iterrows():
 for y in [2002,2010,2021]:
  raw=r[f'source_actual_path_{y}'];rel=r[f'source_file_{y}'];cand=[Path(raw)] if raw else []
  for pref in ['','data/']:
   if rel:cand.append(REPO/rel)
  if '/research_rebuild/' in raw:cand.append(REPO/'research_rebuild'/raw.split('/research_rebuild/',1)[1])
  found=next((p for p in cand if p.is_file()),None);expected=r[f'source_actual_sha256_{y}'];actual=''
  if found:
   if str(found) not in cache:cache[str(found)]=sha(found)
   actual=cache[str(found)]
  records.append({'entity_uid':r.entity_uid,'year':y,'path':r.path,'source_file':rel,'locator':r[f'source_locator_{y}'],'locator_nonempty':bool(r[f'source_locator_{y}']),'local_found':bool(found),'local_path':str(found or ''),'expected_sha256':expected,'actual_sha256':actual,'bytes_match':bool(actual and expected and actual==expected),'population_rechecked':False,'status':'local_bytes_only_row_not_verified' if found else 'primary_bytes_unavailable_in_cloud'})
pd.DataFrame(records).to_csv(OUT/'sample_locator_checks.csv',index=False)
f=REPO/'publication/stage71/accepted_common_federal_territory_axis.csv';fed=pd.read_csv(f)
scope={'ordinary_n':len(x),'regions_n':int(x.effective_region_norm_2002.nunique()),'region_names':sorted(x.effective_region_norm_2002.unique()),'ordinary_federal_rows':int(x.effective_region_norm_2002.isin(['москва','санкт петербург']).sum()),'federal_rows':len(fed),'federal_sha256':sha(f),'boundaries_comparable':'UNKNOWN; no universal verified flag','coverage_record_share':'UNKNOWN: no same-scope census universe row roster reconciled in this audit','coverage_population_share':'UNKNOWN: national total with different scopes is not a reconciled denominator','national_99_5_percent':'Not applicable to ordinary full3 panel; stage68 receipt refers broader available-calendar layer','ordinary_population_sums':{str(y):int(x[f'population_{y}'].sum()) for y in [2002,2010,2021]},'federal_population_sums':{str(y):int(g.territory_population.sum()) for y,g in fed.groupby('census_year')}}
(OUT/'territorial_scope.json').write_text(json.dumps(scope,ensure_ascii=False,indent=2))
x.groupby('effective_region_norm_2002').agg(n=('entity_uid','size'),pop2002=('population_2002','sum'),pop2010=('population_2010','sum'),pop2021=('population_2021','sum')).to_csv(OUT/'regional_panel_sums.csv')
rec={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'input':str(P),'input_sha256':sha(P),'script_sha256':sha(__file__),'seed':20261018,'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'n':len(x),'sample_n':len(s),'strata_n':len(sizes),'locator_checks_n':len(records),'local_sources_found_n':sum(r['local_found'] for r in records),'outputs':{p.name:sha(p) for p in OUT.glob('*') if p.is_file() and p.suffix in ['.csv','.json']}}
(OUT/'audit_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in rec.items() if k!='outputs'},ensure_ascii=False,indent=2))
