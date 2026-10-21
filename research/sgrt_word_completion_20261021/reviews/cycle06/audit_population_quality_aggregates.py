from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
B=Path('/workspace/russian-settlements-research/research/sgrt_word_completion_20261021');M=B/'model/output_cycle06_access_v2_baseline';O=B/'reviews/cycle06';checks=[]
def ck(n,v):checks.append({'check':n,'pass':bool(v)})
def eq(x,y):return np.allclose(np.asarray(x,float),np.asarray(y,float),equal_nan=True,rtol=1e-11,atol=1e-10)
supported={'direct_published_census_value','reviewed_primary_reported_value','reviewed_primary_source_value_or_null','direct_official_city_value','fresh_primary_r5_source','reviewed_primary_source_child_partition','reviewed_primary_control_derived_zero'}
cols=['id','_population_axis_row']+[c for y in [2002,2010,2021] for c in [f'population_{y}',f'population_value_quality_{y}']];n=pd.read_parquet(M/'nodes.parquet',columns=cols);mem=pd.read_parquet(M/'memberships.parquet');s=pd.read_parquet(M/'systems.parquet')
for lev in range(1,5):
 x=n[n._population_axis_row].copy();x['center']=mem.loc[n._population_axis_row,f'center_id_l{lev}'].to_numpy();x=x[x.center.notna()];ss=s[s.level.eq(lev)].set_index('center_id')
 for year in [2002,2010,2021]:
  col=f'population_{year}';quality=x[f'population_value_quality_{year}'].fillna('quality_unavailable');primary=quality.isin(supported)&x[col].notna();secondary=quality.eq('secondary_confidentiality_protected_value_exact_scope_unverified');den=x.groupby('center',observed=True)[col].sum(min_count=1).reindex(ss.index)
  expected={f'n_population_exact_primary_supported_{year}':primary.groupby(x.center,observed=True).sum(),f'n_population_secondary_protected_scope_unverified_{year}':secondary.groupby(x.center,observed=True).sum(),f'system_population_exact_primary_supported_{year}':primary.groupby(x.center,observed=True).all(),f'population_exact_primary_supported_known_population_share_{year}':x[col].where(primary).groupby(x.center,observed=True).sum()/den,f'population_secondary_protected_scope_unverified_known_population_share_{year}':x[col].where(secondary).groupby(x.center,observed=True).sum()/den}
  for c,v in expected.items():
   if '_share_' in c:v=v.where(den>0)
   ck(f'L{lev}_ALL_{c}',eq(v.reindex(ss.index),ss[c]))
  counts=x.assign(quality=quality).groupby(['center','quality'],observed=True).size();actual=ss[f'population_quality_counts_json_{year}'].map(json.loads);ck(f'L{lev}_{year}_ALL_quality_category_counts',all(actual.loc[k]==counts.loc[k].to_dict() for k in ss.index))
r={'status':'ACCEPTED' if all(c['pass'] for c in checks) else 'REJECTED','all_checks_passed':all(c['pass'] for c in checks),'n_checks':len(checks),'n_failed':sum(not c['pass'] for c in checks),'checks':checks,'model_output_manifest_sha256':hashlib.sha256((M/'output_manifest.json').read_bytes()).hexdigest(),'scope':'All8504system threecensusyear source-quality counts/shares/complete-primary flags independently rebuilt from acceptednode quality labels. Doesnot establish secondary value exactsource scope or validate primary source labels themselves.'};(O/'population_quality_aggregates_independent_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(r['status'],r['n_checks'],r['n_failed']);print([c for c in checks if not c['pass']])
