from pathlib import Path
import pandas as pd,duckdb,ast,json,re,unicodedata,sys,collections,time,resource
START=time.monotonic();O=Path(__file__).parent;PACK=O.parent;E=PACK.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize,distance_km
RULE=E/'current_cached_ownarticle_residual_expansion_20261008/review_articles.py';t=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
B=E/'main_axis_residual_application66_20261008';S=B/'applied_state_observations.parquet';P=B/'applied_point_snapshot.parquet';C=B/'applied_component_snapshot.csv.gz';F=E/'main_axis_residual_registry_20261008/stage66_current_positive_samecounty_NULL2002_metadata_candidates.csv.gz';RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');H=PACK/'county_all_positive_current/raw_scope_positive_historic_observations.csv.gz';REG=PACK/'regional_unique_all_residual_rule/accepted_identity_edge_delta.csv.gz';FIVE=E/'verified_county_counterparts_after66_20261008/accepted_identity_edge_delta.csv.gz';RES=E/'temporal_published_code_alias_mass_20261008/candidate_identity_pairs.csv.gz'
f=pd.read_csv(F,dtype=str,keep_default_na=False);h=pd.read_csv(H,dtype=str,keep_default_na=False);rawold={z['source_record_id']:z for z in h.to_dict('records')};covered=set()
for ef in [REG,FIVE]:
 d=pd.read_csv(ef,dtype=str,keep_default_na=False);covered.update(d.to_source_record_id)
r=pd.read_csv(RES,dtype=str,keep_default_na=False);reserved=set(r.from_source_record_id)|set(r.to_source_record_id);c=duckdb.connect();c.execute("SET memory_limit='192MB'");wanted=set(int(s.rsplit(':',1)[1]) for col in ['current_source_record_id','current_alltype_samecounty_namesake_source_IDs_json'] for s in (f[col] if col=='current_source_record_id' else [y for x in f[col] for y in json.loads(x)]));c.register('wanted_rns',pd.DataFrame({'rn':list(wanted)}));ns=c.execute('select * from (select row_number() over() rn,object_level,object_name,region,mun_upper,mun_lower,oktmo from read_parquet(?)) join wanted_rns using(rn)',[str(RAW)]).fetchdf();native={int(z['rn']):z for z in ns.to_dict('records')}
def pk(s):
 s=bare(s);s=re.sub(r'\b(?:муниципальное образование|сельское поселение|городское поселение|сельский округ|сельская администрация|сельский совет|сельсовет|сумон|сельсовета|сумона|сельского округа|администрации)\b',' ',s);s=' '.join(s.split());return re.sub(r'(?:ская|ское|ский)$','ск',s)
rural={'село','деревня','поселок','хутор','станица','слобода','местечко','аул','арбан','населенный пункт','сельский населенный пункт'};rough=[];sourceholds=[]
for z in f.to_dict('records'):
 sid=z['current_source_record_id'];oid=z['historic_source_record_id'];n=native.get(int(sid.rsplit(':',1)[1]));q=rawold.get(oid);reason=[];rule=''
 if sid in covered or sid in reserved or oid in reserved:continue
 if not n or not q:reason.append('raw_current_or_historic_positive_source_scope_not_available')
 if q and (county(q['historical_raw_county_header_literal'])!=county(z['current_native_county']) or namekey(q['settlement_name'])!=namekey(z['current_name'])):reason.append('raw_printed_county_or_name_not_equal')
 ct=typekey(z['current_type']);ht=typekey(z['historic_type'])
 if ct!=ht and not (ct in rural and ht in rural):reason.append('physical_source_type_family_incompatible')
 if z['component_overlap_guard_passed']!='True':reason.append('actual66_source_components_sameyear_overlap')
 if z['cached_county_uniqueness_guard_passed']=='True':rule='literal raw typed ownNP sourcecounty and alltype unique native NP name within actualcounty in both years'
 elif n and q:
  parish=pk(n['mun_lower']);specific=parish and parish!=pk(n['mun_upper']);rp=pk(q['historical_raw_specific_parish_header_literal'])
  currentids=json.loads(z['current_alltype_samecounty_namesake_source_IDs_json']);oldids=json.loads(z['historic_alltype_samecounty_namesake_source_IDs_json']);cm=[s for s in currentids if pk(native.get(int(s.rsplit(':',1)[1]),{}).get('mun_lower',''))==parish];om=[s for s in oldids if s in rawold and pk(rawold[s]['historical_raw_specific_parish_header_literal'])==parish];unclassified=[s for s in oldids if s not in rawold];unplaced=json.loads(z['current_unplaced_same_region_name_rival_source_IDs_json'])+json.loads(z['historic_unplaced_same_region_name_rival_source_IDs_json'])
  if specific and rp==parish and cm==[sid] and om==[oid] and not unclassified and not unplaced:rule='exact printed proper specific parish within exact actualcounty closes all current and historical name rivals; closed grammatical gender -ская/-ское/-ский and official territorial role removal only, no fuzzy parish matching'
 if not rule:reason.append('actual_named_county_competitors_not_closed_by_unique_county_or_unique_specific_printed_parish')
 if reason:sourceholds.append({**z,'county_source_holds':';'.join(reason)});continue
 rough.append({**z,'current_raw_primary_row_json':json.dumps(n,ensure_ascii=False),'historic_raw_scope_evidence_json':json.dumps(q,ensure_ascii=False),'county_source_binding_rule':rule,'current_historic_raw_type_equal':ct==ht,'rural_legal_type_continuity_status':'literal_types_equal' if ct==ht else 'UNKNOWN_no_statuschange_date_inferred'})
roots={z[x] for z in rough for x in ['current_component_root','historic_component_root']};c.register('wanted_roots',pd.DataFrame({'root':list(roots)}));m=c.execute('select s.source_record_id,s.root,s.census_year,s.population,s.settlement_name,s.settlement_type,s.oktmo,s.okato from read_parquet(?) s join wanted_roots using(root)',[str(S)]).fetchdf();years=collections.defaultdict(set);members=collections.defaultdict(list)
for z in m.to_dict('records'):years[z['root']].add(int(z['census_year']));members[z['root']].append(z)
c.register('wanted_members',m[['source_record_id','root']]);pt=c.execute('select p.source_record_id,p.latitude,p.longitude,p.coordinate_source_record_id,p.coordinate_admission_status,p.point_origin_file,p.point_origin_sha256,p.point_origin_locator,p.point_origin_kind,m.root from read_parquet(?) p join wanted_members m using(source_record_id)',[str(P)]).fetchdf();c.close();pts={z['source_record_id']:z for z in pt.to_dict('records')};rpt=collections.defaultdict(list)
for z in pts.values():rpt[z['root']].append(z)
accepted=[];holds=[];edges=[];pointuses=[]
for z in rough:
 sid=z['current_source_record_id'];oid=z['historic_source_record_id'];a=z['current_component_root'];b=z['historic_component_root'];reason=[];far=[]
 if sid not in pts:reason.append('current_actual66_ownpoint_absent')
 if years[a]&years[b]:reason.append('actual66_component_years_overlap')
 if sid in pts:
  xy=(float(pts[sid]['latitude']),float(pts[sid]['longitude']))
  for p in rpt[a]+rpt[b]:
   d=distance_km(xy,(float(p['latitude']),float(p['longitude'])))
   if d>5:far.append({'source_record_id':p['source_record_id'],'distance_km':d,'coordinate_source_record_id':p['coordinate_source_record_id']})
 if far:reason.append('accepted_component_point_over5km_positive_conflict_no_supersession')
 z.update(actual66_current_component_members_json=json.dumps(members[a],ensure_ascii=False),actual66_historic_component_members_json=json.dumps(members[b],ensure_ascii=False),actual66_accepted_component_point_conflicts_json=json.dumps(far,ensure_ascii=False),county_admission_holds=';'.join(reason),historical_date_coordinate_measurement_asserted=False,external_provider_identifier_transfer_asserted=False,population_boundary_comparability_asserted=False)
 if reason:holds.append(z);continue
 accepted.append(z);edges.append({'from_source_record_id':oid,'to_source_record_id':sid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_method':'raw_printed_county_unique_or_specific_printed_parish_ordinary_NP_continuity','admission_rule':z['county_source_binding_rule']+'; literal physical rawNP name/type and whole locality source grain; actual66UFyear/acceptedpoint guards; no historical owncode or coordinate measurement assertion; NULL population_scope not exclusion','population_boundary_comparability_asserted':False})
 for q in members[a]+members[b]:
  mid=q['source_record_id']
  if mid in pts:continue
  p=pts[sid];pointuses.append({'target_source_record_id':mid,'latitude':float(p['latitude']),'longitude':float(p['longitude']),'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':p['coordinate_source_record_id'],'point_origin_file':p['point_origin_file'],'point_origin_sha256':p['point_origin_sha256'],'point_origin_locator':p['point_origin_locator'],'point_origin_kind':'retrospective_ownNP_representative_geography_through_raw_county_or_specific_parish_continuity','coordinate_binding_rule':'new source-bound rawcounty or specific printed parish ordinaryNP identity plus existing historical acceptedcomponent continuity; modern representative geography only','point_use_inference':'representative ownphysicalNP geography, not historic census-date measurement','historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False,'external_provider_ID_binding_asserted':False,'current_carrier_source_record_id':sid})
u={}
for z in pointuses:
 sid=z['target_source_record_id']
 if sid in u:assert u[sid]==z
 u[sid]=z
pointuses=list(u.values());edges=list({(z['from_source_record_id'],z['to_source_record_id']):z for z in edges}.values())
for fn,zs in [('accepted_identity_edge_delta',edges),('accepted_point_use_delta',pointuses),('accepted_county_or_parish_source_evidence',accepted),('county_positive_admission_holds',holds),('county_source_binding_holds',sourceholds)]:pd.DataFrame(zs).to_csv(O/(fn+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
uni={z['current_source_record_id']:z for z in accepted};r={'baseline':66,'cached_metadata_pairs':len(f),'raw_county_or_parish_source_positive_pairs':len(rough),'accepted_edges':len(edges),'accepted_retrospective_points':len(pointuses),'accepted_current_UIDs':len(uni),'accepted_current_population2021_not_gain':sum(float(z['current_population2021']) for z in uni.values() if z['current_population2021']),'rule_counts':dict(collections.Counter(z['county_source_binding_rule'] for z in accepted)),'positive_component_holds':len(holds),'source_binding_holds':len(sourceholds),'regional58_and_priorfive_current_targets_excluded':len(covered),'canonical_applied':False,'actual_State_loads':0,'source_population_counts_unchanged':True,'seconds':time.monotonic()-START,'peak_RSS_MB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'input_pins':{str(p):sha(p) for p in [S,P,C,F,RAW,H,REG,FIVE,RES,RULE,O/'admit_county.py']}};(O/'county_admission_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k!='input_pins'},ensure_ascii=False))
