import sys,json,re,math
from pathlib import Path
from collections import defaultdict
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(32);d=s.obs;f=pd.read_csv(O/'raw_cached_own_claim_binding_checks.csv.gz',dtype=str,keep_default_na=False);f=f[f.raw_status.eq('candidate_positive_raw_claim_own_code_name')];meta=duckdb.connect().execute("select source_record_id,source_sheet,source_row,entity_grain_status from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf().set_index('source_record_id');d['sr']=d.source_record_id.map(meta.source_row);d['sheet']=d.source_record_id.map(meta.source_sheet);members=defaultdict(list)
for sid in s.by_id.index:members[s.uf.find(sid)].append(sid)
oldmap={};newmap={};currentcounty_by_anchor={};county_map=defaultdict(set)
for _,x in d[d.census_year.eq(2002)].iterrows():oldmap[s.uf.find(x.source_record_id)]=x
for _,x in d[d.census_year.eq(2021)].iterrows():newmap[s.uf.find(x.source_record_id)]=x
for root,n in newmap.items():
 old=oldmap.get(root)
 if old is not None and county_key(old.district_raw):county_map[(old.region_norm,county_key(old.district_raw))].add(county_key(n.district_raw))
 for sid in members[root]:currentcounty_by_anchor[sid]=n
books={};rawbook_context={};anchors=[];rows=[];holds=[]
def source_bracket(target,current,maxgap=80):
 sid=target.source_record_id;rn=int(meta.loc[sid].source_row);sheet=meta.loc[sid].source_sheet;peers=d[d.census_year.eq(target.census_year)&d.source_file.eq(target.source_file)&d['sheet'].eq(sheet)&d.sr.between(rn-maxgap,rn+maxgap)];ls=[];us=[]
 for _,p in peers.iterrows():
  if p.source_record_id==sid:continue
  n=currentcounty_by_anchor.get(p.source_record_id)
  if n is None or county_key(n.district_raw)!=county_key(current.district_raw):continue
  if s.years[s.uf.find(p.source_record_id)]!={2002,2010,2021}:continue
  z={'target_source_record_id':sid,'anchor_source_record_id':p.source_record_id,'anchor_source_row':int(p.sr),'anchor_name':p.settlement_name,'anchor_native2021_source_record_id':n.source_record_id,'anchor_native2021_county':n.district_raw,'anchor_component_years':str(sorted(s.years[s.uf.find(p.source_record_id)]))};(ls if p.sr<rn else us).append(z)
 if not ls or not us:return None
 l=max(ls,key=lambda x:x['anchor_source_row']);u=min(us,key=lambda x:x['anchor_source_row']);return [l,u] if normalize(l['anchor_name'])!=normalize(u['anchor_name']) else None
for z in f.to_dict('records'):
 a=s.by_id.loc[z['old_source_record_id']];n=s.by_id.loc[z['current_source_record_id']];county=county_key(n.district_raw);oldcounty=county_key(a.district_raw);oldbracket=None;oldok=bool(oldcounty and (oldcounty==county or county in county_map[(a.region_norm,oldcounty)]));oldmethod='Native2002 printed county matched directly or through already accepted native county mapping' if oldok else ''
 if not oldok:
  oldbracket=source_bracket(a,n)
  if oldbracket:oldok=True;oldmethod='Native2002 independently bracketed source block, both anchors current printed county'
 # Direct printed primary source parent supports old urban/rural singleton rows as well.
 if not oldok and a.source_file.endswith('.xls'):
  path='/workspace/settlements-raw/'+a.source_file;bk=books.setdefault(path,xlrd.open_workbook(path));mm=meta.loc[a.source_record_id];sh=bk.sheet_by_name(str(mm.source_sheet)) if str(mm.source_sheet) in bk.sheet_names() else bk.sheet_by_index(int(mm.source_sheet));rr=int(mm.source_row);captions=[]
  for i in range(max(0,rr-120),rr):
   rv=sh.row_values(i)[:8]
   for v in rv:
    vv=normalize(v)
    if isinstance(v,str) and re.search(r'район|кожуун|улус|^\s*г\.',vv):captions.append({'row_1based':i+1,'literal':v,'county_key':county_key(v)})
  match=[x for x in captions if x['county_key']==county or county in county_map[(a.region_norm,x['county_key'])]]
  if match and not any(x['row_1based']>match[-1]['row_1based'] and x['county_key'] not in ['',county] and re.search('район|кожуун|улус',normalize(x['literal'])) for x in captions):oldok=True;oldmethod='Actual native2002 printed own parent '+json.dumps(match[-1],ensure_ascii=False)
 if not oldok:holds.append({'old_source_record_id':a.source_record_id,'current_source_record_id':n.source_record_id,'name':a.settlement_name,'reason':'No unambiguous native2002 county/source block recovered in bounded scan'});continue
 if oldbracket:anchors.extend(oldbracket)
 # All same-name native2002 competitors in the chosen source county or source bracket, regardless of population, must leave one compatible own observation.
 comps=d[d.census_year.eq(2002)&d.region_norm.eq(a.region_norm)&d.name_norm.eq(a.name_norm)]
 scoped=comps[comps.district_raw.map(county_key).eq(oldcounty)] if oldcounty else comps[comps.source_file.eq(a.source_file)&comps['sheet'].eq(meta.loc[a.source_record_id].source_sheet)&comps.sr.between(oldbracket[0]['anchor_source_row'] if oldbracket else float(meta.loc[a.source_record_id].source_row)-120,oldbracket[1]['anchor_source_row'] if oldbracket else float(meta.loc[a.source_record_id].source_row)+120)]
 # Native urban type can distinguish an explicitly printed urban NP from nearby rural namesakes.
 typed=scoped[scoped.type_norm.eq(a.type_norm)]
 if len(typed)!=1:holds.append({'old_source_record_id':a.source_record_id,'current_source_record_id':n.source_record_id,'name':a.settlement_name,'reason':'Native2002 same-name/type source-scope competitor; no unique old own observation','competitor_ids':';'.join(typed.source_record_id)});continue
 if z['native2010_in_component']:
  ids=z['native2010_in_component'].split(';');opts=[s.by_id.loc[x] for x in ids];method2010='Already accepted native2010 member in old/current component';br=None
 else:
  opts=[];method2010='Independent native2010 source bracket';br=None
  for _,b in d[d.census_year.eq(2010)&d.region_norm.eq(n.region_norm)&d.name_norm.eq(n.name_norm)&d.is_additive_settlement_record.fillna(False)].iterrows():
   if 2002 in s.years[s.uf.find(b.source_record_id)] or 2021 in s.years[s.uf.find(b.source_record_id)]:continue
   cb=source_bracket(b,n)
   if cb:opts.append(b);br=cb
 if len(opts)!=1:holds.append({'old_source_record_id':a.source_record_id,'current_source_record_id':n.source_record_id,'name':a.settlement_name,'reason':'No unique native2010 own row in independent source county bracket','native2010_option_count':len(opts)});continue
 b=opts[0]
 if br:anchors.extend(br)
 ids=[a.source_record_id,b.source_record_id,n.source_record_id];roots={s.uf.find(x) for x in ids};ys=[y for root in roots for y in s.years[root]]
 if len(ys)!=len(set(ys)) or set(ys)!={2002,2010,2021}:holds.append({'old_source_record_id':a.source_record_id,'name':a.settlement_name,'reason':'Real repeated-year component after native2010 endpoint binding'});continue
 rows.append(dict(z,native2010_source_record_id=b.source_record_id,native2010_population=b.population,native2002_binding_rule=oldmethod,native2010_binding_rule=method2010,native2002_source_scope_competitor_ids=';'.join(scoped.source_record_id),native2002_county_binding=oldcounty,raw02_source_bracket=json.dumps(oldbracket,ensure_ascii=False),raw10_source_bracket=json.dumps(br,ensure_ascii=False)))
pd.DataFrame(rows).to_csv(O/'source_bound_native_full3_candidates.csv.gz',index=False,compression='gzip');pd.DataFrame(anchors).to_csv(O/'independent_source_county_anchors.csv.gz',index=False,compression='gzip');pd.DataFrame(holds).to_csv(O/'source_context_holds.csv.gz',index=False,compression='gzip');r={'source_bound_native_full3_candidates':len(rows),'native_population_potential':{str(y):int(sum(float(z[k]) for z in rows)) for y,k in [(2002,'native2002_population'),(2010,'native2010_population'),(2021,'native2021_population')]},'holds':len(holds),'raw_P764_date_population_name_asserted':True,'baseline_stage':32,'status':'Source-bound candidate batch; source population/code/point conflicts and exact rawcells final admission checks pending'};(O/'source_bound_potential_counts.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False));print(pd.DataFrame(rows)[['old_name','region','native2002_population','native2010_population','native2021_population']].head(25).to_string(index=False))
