import pandas as pd,duckdb,json,re,unicodedata
from pathlib import Path
R=Path('/workspace/russian-settlements-research');E=R/'research_rebuild/evidence';O=Path(__file__).parent
paths=[p for p in E.glob('*/accepted_qualified_physical_observations.csv') if 'event' not in p.parent.name]
frames=[]
for p in paths:
 d=pd.read_csv(p,dtype=str,keep_default_na=False);d['qualified_packet']=str(p);frames.append(d)
f=pd.concat(frames,ignore_index=True);f['year_n']=pd.to_numeric(f.year);f['pop_n']=pd.to_numeric(f.population_source_value,errors='coerce');old=f[f.year_n.eq(2002)&f.pop_n.gt(0)&~f.region_norm.isin(['чеченская','тульская','свердловская','ульяновская'])].copy();current=f[f.year_n.eq(2021)].copy();by={}
for _,x in current.iterrows():
 for k in ['source_record_id','current2021_source_record_id','native_current_source_record_id']:
  if k in x and str(x[k]).startswith('2021:'):by[x.trajectory_id]=x[k];break
c=duckdb.connect();native=c.execute("select * from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet') where census_year in (2002,2021)").fetchdf();n02=native[native.census_year.eq(2002)];n21=native[native.census_year.eq(2021)].set_index('source_record_id');groups={(reg,float(pop)):a for (reg,pop),a in n02.groupby(['region_norm','population'])}
def key(x):
 x=' '.join(unicodedata.normalize('NFKC',str(x)).lower().replace('ё','е').split());x=re.sub(r'^(?:пгт|пос[её]лок|пос\.|п\.|село|с\.|деревня|д\.|хутор|х\.)\s+','',x);x=re.sub(r'\s+(?:пгт|рп|п\.|пос\.)$','',x);return x
def pick(*vals):
 return next((v for v in vals if pd.notna(v) and str(v).strip()),'')
rows=[];allcompetitors=[];seen=set()
for _,q in old.iterrows():
 sid=by.get(q.trajectory_id) or q.get('native_current_source_record_id') or q.get('current2021_source_record_id');
 if sid not in n21.index:continue
 z=n21.loc[sid];pool=groups.get((q.region_norm,float(q.pop_n)))
 if pool is None:continue
 canon={key(q.settlement_name),key(z.settlement_name)};matched=[]
 for _,a in pool.iterrows():
  ak=key(a.settlement_name);rule='exact_printed_name' if ak in canon else 'bounded_hyphen_or_period_variant' if any(ak.replace('-','').replace('.','')==k.replace('-','').replace('.','') for k in canon) else ''
  allcompetitors.append({'current_source_record_id':sid,'qid':pick(q.get('wikidata_id'),q.trajectory_id.split(':')[-1]),'old_source_record_id':a.source_record_id,'old_name':a.settlement_name,'old_type':a.settlement_type,'old_county':a.district_raw,'population2002':a.population,'name_rule':rule,'population_colliding_pool_size':len(pool)})
  if not rule:continue
  pair=(a.source_record_id,sid)
  if pair in seen:continue
  seen.add(pair);matched.append(a)
  rows.append({'old_source_record_id':a.source_record_id,'current_source_record_id':sid,'old_name':a.settlement_name,'old_type':a.settlement_type,'old_county':a.district_raw,'current_name':z.settlement_name,'current_type':z.settlement_type,'current_county':z.district_raw,'current_okato':z.okato,'current_oktmo':z.oktmo,'region':q.region_norm,'native2002_population':a.population,'native2021_population':z.population,'qid':pick(q.get('wikidata_id'),q.trajectory_id.split(':')[-1]),'qualified_claim_trajectory':q.trajectory_id,'claim_source_file':pick(q.get('secondary_source_path'),q.source_path),'claim_source_sha256':pick(q.get('secondary_source_sha256'),q.source_sha256),'claim_locator':pick(q.get('secondary_source_locator'),q.source_locator),'qualified_packet':q.qualified_packet,'name_rule':rule,'all_count_competitors_in_region':len(pool),'declared_date':pick(q.get('declared_date'),q.get('observation_declared_date'),'source claim/date needs raw verification')})
pd.DataFrame(rows).to_csv(O/'dated_count_native02_potential.csv.gz',index=False);pd.DataFrame(allcompetitors).to_csv(O/'all_count_collision_competitors.csv.gz',index=False)
d=pd.DataFrame(rows);r={'qualified2002rows_screened':len(old),'unique_bound_native02_current_pairs':len(d),'distinct_current':d.current_source_record_id.nunique() if len(d) else 0,'old2002_population_potential':int(d.drop_duplicates('old_source_record_id').native2002_population.sum()) if len(d) else 0,'current2021_population_potential':int(d.drop_duplicates('current_source_record_id').native2021_population.sum()) if len(d) else 0,'status':'Potential only; actual30 component, raw claim/current own code and native source county/points checks pending'};(O/'first_potential_counts.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False));print(d.sort_values('native2002_population',ascending=False)[['old_name','current_name','region','old_county','current_county','native2002_population','native2021_population','name_rule']].head(35).to_string(index=False))
