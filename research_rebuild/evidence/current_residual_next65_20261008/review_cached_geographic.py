from pathlib import Path
import ast,re,json,unicodedata,sys,gzip,collections
import pandas as pd
O=Path(__file__).parent;E=O.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize
RULE=E/'current_cached_ownarticle_residual_expansion_20261008/review_articles.py'
t=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
def parish(s):
 s=bare(s)
 return re.sub(r'\s+',' ',re.sub(r'\b(?:муниципальное образование|сельское поселение|городское поселение|сельсовет|сельский совет)\b',' ',s)).strip()
def nk(s):return namekey(re.sub(r'\bкм\b','километр',s,flags=re.I))
f=pd.read_csv(O/'cached_named_source_diagnostic.csv.gz',dtype=str,keep_default_na=False);live=[];li=collections.defaultdict(list)
for z in live:li[z['source_record_id']].append(z)
OS=Path('/workspace/settlements-work/coordinate_first_20261008/sources/osm_geoapify_ru.zip');ossha=sha(OS);out=[];holds=[]
for z in f.to_dict('records'):
 n=json.loads(z['native_primary_row_json']);rv=json.loads(z['samecounty_native_name_rivals_json']);key=(nk(z['settlement_name']),regionkey(n['region']),county(n['mun_upper']));lp=parish(n['mun_lower']);specific=lp and lp!=parish(n['mun_upper']);choices=[]
 for q in json.loads(z['cached_named_OSM_matches_json']):
  p=q['raw'];a=p.get('address',{});xy=p.get('location',[])
  if p.get('type') not in ['hamlet','village'] or len(xy)!=2:continue
  if (nk(p.get('name','')),regionkey(a.get('state','')),county(a.get('county','')))!=key:continue
  if specific and parish(a.get('municipality',''))==lp and not any(parish(v['mun_lower'])==lp for v in rv):choices.append(q)
 unique={ (q['raw']['osm_type'],q['raw']['osm_id']):q for q in choices};chosen=None
 if len(unique)==1:
  q=next(iter(unique.values()));p=q['raw'];chosen={'latitude':p['location'][1],'longitude':p['location'][0],'point_origin_file':str(OS),'point_origin_sha256':ossha,'point_origin_locator':f"{q['member']}:line:{q['line']}:osm_{p['osm_type']}:{p['osm_id']}",'point_origin_kind':'cached_physical_OSM_place_exact_native_specific_parish','coordinate_source_record_id':f"OSM:{p['osm_type']}:{p['osm_id']}",'source_binding_proof':'literal physical own place name/region/county and independently matching current native specific lower parish; no other native samecounty namesake in own parish; unique physical OSM object in own parish','chosen_raw_source_json':json.dumps(q,ensure_ascii=False)}
 own=[];rail=[]
 for q in li[z['source_record_id']]:
  p=q['raw_ownplace_result'];a=p.get('address',{});tags=p.get('extratags') or {};pn=p.get('name','');st=tags.get('official_status','').removeprefix('ru:')
  if p.get('category')!='place' or p.get('type') not in ['hamlet','village']:continue
  if (nk(pn),regionkey(a.get('state','')),county(a.get('county','')))!=key:continue
  if fullcode(tags.get('oktmo:user',tags.get('ref:oktmo',tags.get('oktmo',''))))==fullcode(n['oktmo']) and typekey(st)==typekey(z['settlement_type']):own.append(q)
  if 'станци' in n['object_name'].lower() and 'станци' in st and not any('станци' in v['object_name'].lower() for v in rv):rail.append(q)
 livechosen=own if own else rail
 lu={(q['raw_ownplace_result']['osm_type'],q['raw_ownplace_result']['osm_id']):q for q in livechosen}
 if len(lu)==1:
  q=next(iter(lu.values()));p=q['raw_ownplace_result'];chosen={'latitude':float(p['lat']),'longitude':float(p['lon']),'point_origin_file':q['source_response_file'],'point_origin_sha256':sha(Path(q['source_response_file'])),'point_origin_locator':q['source_locator']+':lat,lon','point_origin_kind':'live_named_physical_OSM_place_literal_owncode' if own else 'live_named_physical_OSM_station_settlement_explicit_role','coordinate_source_record_id':f"OSM:{p['osm_type']}:{p['osm_id']}",'source_binding_proof':'proper physical place exact ownname/region/county and literal full native owncode/type' if own else 'proper physical named settlement own explicit published station-settlement role matching native own role and excluding every plain samecounty namesake; infrastructure coordinates excluded','chosen_raw_source_json':json.dumps(q,ensure_ascii=False)}
 if chosen:out.append({**z,**chosen,'external_provider_ID_binding_asserted':False})
 else:holds.append({**z,'geographic_source_hold_reason':'no uniquely source-bound physical own point under exact owncode/type or exact specific native parish or explicit own rail-settlement role; conflicting reform codes and ambiguous sameparish objects held','matching_parish_objects':len(unique),'matching_live_owncode_objects':len(own),'matching_live_rail_role_objects':len(rail)})
for fn,v in [('source_positive_geographic_candidates',out),('geographic_source_holds',holds)]:pd.DataFrame(v).to_csv(O/(fn+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
r={'priority_targets':len(f),'source_positive_candidates':len(out),'source_positive_known_population':sum(float(z['population']) for z in out if z['population']),'candidate_not_admission':True,'source_rule_counts':dict(collections.Counter(z['point_origin_kind'] for z in out)),'input_pins':{str(p):sha(p) for p in [O/'cached_named_source_diagnostic.csv.gz',O/'actual65_current_remaining.csv.gz',OS,RULE,Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'),O/'review_cached_geographic.py']}};(O/'source_review_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False))
