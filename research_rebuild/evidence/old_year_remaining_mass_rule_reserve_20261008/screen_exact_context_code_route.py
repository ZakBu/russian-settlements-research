import sys,json,re
from pathlib import Path
from collections import defaultdict,Counter
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(24);before=s.metrics();c=duckdb.connect();cl=c.execute('select historical_okato,name,status,is_settlement_raw from read_parquet(?)',['/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet']).fetchdf();h=c.execute('select * from read_parquet(?)',['/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet']).fetchdf();counties={r.historical_okato[:5]:county_key(r.name) for r in cl.itertuples() if r.is_settlement_raw=='f' and len(r.historical_okato)==8 and r.historical_okato.endswith('000') and 'район' in normalize(r.name) and r.historical_okato[2]=='2'};regions={k:normalize(g.historical_point_modern_region.mode().iloc[0]) for k,g in h.dropna(subset=['historical_point_modern_region']).groupby(h.historical_okato_2009_raw.str[:2])};types={'деревня':'деревня','село':'село','поселок сельского типа':'поселок','хутор':'хутор','поселок городского типа':'пгт','город':'город','станица':'станица','станция':'станция','разъезд':'разъезд','слобода':'слобода'};classidx=defaultdict(list)
for g in cl[cl.is_settlement_raw.eq('t')].to_dict('records'):
 code=g['historical_okato'];key=(normalize(g['name']),types.get(g['status'],normalize(g['status'])),regions.get(code[:2],''),counties.get(code[:5],''));classidx[key].append(g)
o=s.obs[s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь','крым'])].copy();o=o[~o.settlement_name.str.contains(r'\(часть|железнодорож|ж/д',case=False,regex=True,na=False)];o['n']=o.name_norm.map(normalize);o['t']=o.type_norm.map(normalize);o['r']=o.region_norm.map(normalize);o['d']=o.district_raw.map(county_key)
def code(v):
 if v is None or pd.isna(v):return ''
 x=str(v).strip();return x[:-2] if x.endswith('.0') else x
o['code']=o.okato.map(code);current=defaultdict(list);currentnames=defaultdict(list)
for a in o[o.census_year.eq(2021)].to_dict('records'):
 current[a['code']].append(a);currentnames[(a['n'],a['r'],a['d'])].append(a)
hidx={str(z['historical_okato_2009_raw']):z for z in h.to_dict('records')};members=defaultdict(list)
for sid in s.by_id.index:members[s.uf.find(sid)].append(sid)
counts=Counter();candidates=[];holds=[];old=o[o.census_year.eq(2002)&~o.source_record_id.isin(s.point_rows)];old=old[old.source_record_id.map(lambda sid:s.years[s.uf.find(sid)]!={2002,2010,2021})];uniq=o.groupby(['census_year','n','t','r','d']).source_record_id.size().to_dict()
for a in old.to_dict('records'):
 sid=a['source_record_id'];key=(a['n'],a['t'],a['r'],a['d']);gs=classidx.get(key,[])
 if len(gs)!=1:counts['No unique historical name/type/region/county classifier object']+=1;continue
 if uniq.get((2002,*key),0)!=1:counts['Competing same-year exact historical type/name/county']+=1;continue
 g=gs[0];gc=g['historical_okato'];gh=hidx.get(gc);targets=[z for z in current.get(gc,[]) if z['n']==a['n'] and z['r']==a['r'] and z['d']==a['d']]
 if len(targets)!=1:counts['No unique current exact own-code/name/region/county']+=1;continue
 b=targets[0];bid=b['source_record_id'];ra,rb=s.uf.find(sid),s.uf.find(bid)
 if ra==rb:counts['Already joined']+=1;continue
 reasons=[]
 if s.years[ra]&s.years[rb]:reasons.append('Repeated year component')
 if bid not in s.point_rows:reasons.append('Current own point not admitted')
 if not gh or not bool(gh['historical_name_exact']) or not bool(gh['historical_type_exact']):reasons.append('Raw GeoKLADR name/type does not bind classifier object')
 if a['code'] and a['code']!=gc:reasons.append('Actual old native code conflict')
 component=members[ra]+members[rb];p=s.point_rows.get(bid)
 if p:
  for x in component:
   if x in s.conflicting_point_targets:reasons.append('Active coordinate claim conflict')
   other=s.point_rows.get(x)
   if other and distance_km((p['latitude'],p['longitude']),(other['latitude'],other['longitude']))>5:reasons.append('Active own component points disagree')
   r=s.by_id.loc[x]
   if r.region_norm!=a['r']:reasons.append('Component region conflict')
   dd=county_key(r.district_raw)
   if dd and dd!=a['d']:reasons.append('Component geographic county conflict')
 if reasons:
  if len(holds)<150:holds.append({'source_record_id':sid,'current_source_record_id':bid,'name':a['settlement_name'],'population_2002':a['population'],'code':gc,'hold_reasons':'; '.join(sorted(set(reasons)))})
  counts.update(set(reasons));continue
 rawdist=distance_km((gh['latitude_from_lat'],gh['longitude_from_long']),(p['latitude'],p['longitude'])) if pd.notna(gh['latitude_from_lat']) and pd.notna(gh['longitude_from_long']) else None
 candidates.append({'from_source_record_id':sid,'to_source_record_id':bid,'name':a['settlement_name'],'type_2002':a['settlement_type'],'type_2021':b['settlement_type'],'region':a['r'],'county':a['d'],'population_2002':a['population'],'population_2021':b['population'],'historical_exact_own_code':gc,'raw_name_2009':gh['name_raw_2009'],'raw_name_2011':gh['name_raw_2011'],'raw_type_2011':gh['settlement_type_raw'],'raw_record_1based':gh['record_number_1based'],'raw_classifier_line_1based':gh['source_line_1based'],'old_source_file':a['source_file'],'old_source_locator':a['source_locator'] or sid,'current_source_file':b['source_file'],'current_source_locator':b['source_locator'],'old_component_years':json.dumps(sorted(s.years[ra])),'current_component_years':json.dumps(sorted(s.years[rb])),'same_name_county_current_alternatives':len(currentnames[(a['n'],a['r'],a['d'])]),'old_raw_point_to_current_km':rawdist,'own_point_donor_json':json.dumps(p,ensure_ascii=False),'component_source_ids_json':json.dumps(component,ensure_ascii=False),'decision_status':'Candidate only; source/context checks required'})
pd.DataFrame(candidates).to_csv(O/'exact_context_code_candidates.csv',index=False);pd.DataFrame(holds).to_csv(O/'exact_context_code_holds.csv',index=False);r={'baseline_stage':24,'old_residual_source_rows':len(old),'candidate_edges':len(candidates),'unique_candidate_2002_population':int(sum(z['population_2002'] for z in candidates)),'outcomes':dict(counts),'new_identity_years_prospective_full3':sum(set(json.loads(z['old_component_years']))|set(json.loads(z['current_component_years']))=={2002,2010,2021} for z in candidates),'status':'Candidate only; no mutations'};(O/'exact_context_code_screen_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
