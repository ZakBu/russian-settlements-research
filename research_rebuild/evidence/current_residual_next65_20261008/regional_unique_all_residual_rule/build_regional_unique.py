from pathlib import Path
import pandas as pd,duckdb,ast,json,re,unicodedata,sys,collections,time,resource,xlrd
START=time.monotonic();O=Path(__file__).parent;PACK=O.parent;E=PACK.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,normalize,distance_km
RULE=E/'current_cached_ownarticle_residual_expansion_20261008/review_articles.py';t=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
B=E/'main_axis_residual_application66_20261008';S=B/'applied_state_observations.parquet';P=B/'applied_point_snapshot.parquet';C=B/'applied_component_snapshot.csv.gz';F=B/'applied_remaining_primary.csv.gz';RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');RES=E/'temporal_published_code_alias_mass_20261008/candidate_identity_pairs.csv.gz';reserved=pd.read_csv(RES,dtype=str,keep_default_na=False);reserved=set(reserved.from_source_record_id)|set(reserved.to_source_record_id)
f=pd.read_csv(F,dtype=str,keep_default_na=False);f=f[f.census_year.eq('2021') & ~f.component_years.eq('2002,2010,2021') & f.has_own_point.eq('True') & ~f.source_record_id.isin(reserved)].sort_values('population',key=lambda x:pd.to_numeric(x,errors='coerce'),ascending=False);EXCLUDED=E/'verified_county_counterparts_after66_20261008/accepted_identity_edge_delta.csv.gz';ex=pd.read_csv(EXCLUDED,dtype=str,keep_default_na=False);excurrent=set(ex.to_source_record_id);f=f[~f.source_record_id.isin(excurrent)]
targetkeys={(namekey(z['settlement_name']),regionkey(z['region_norm'])) for z in f.to_dict('records')};c=duckdb.connect();c.execute("SET memory_limit='192MB'")
cur=c.execute("select row_number() over() rn,object_level,object_name,region,mun_upper,mun_lower,oktmo from read_parquet(?)",[str(RAW)]);cols=[x[0] for x in cur.description];modern=collections.defaultdict(list);codes=collections.Counter();nativemap={}
while True:
 bs=cur.fetchmany(5000)
 if not bs:break
 for tup in bs:
  z=dict(zip(cols,tup))
  if z['object_level']!='Населенный пункт':continue
  codes[fullcode(z['oktmo'])]+=1;n,ty=splitname(z['object_name']);key=(namekey(n),regionkey(z['region']))
  if key in targetkeys:modern[key].append(z);nativemap[z['rn']]=z
physicaltypes={'село','деревня','поселок','город','хутор','станица','слобода','местечко','аул','арбан','населенный пункт','железнодорожный объект','пгт','рп','рабочий поселок','разъезд','станция'};hist=collections.defaultdict(list);cur=c.execute("select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_raw,population,root,source_file,source_path,source_locator,population_value_quality,population_scope,oktmo,okato from read_parquet(?) where census_year in (2002,2010)",[str(S)]);cols=[x[0] for x in cur.description]
while True:
 bs=cur.fetchmany(5000)
 if not bs:break
 for tup in bs:
  q=dict(zip(cols,tup))
  if not q['settlement_name']:continue
  if q['population_scope'] and any(a in str(q['population_scope']).lower() for a in ['municipality_parent','federal_city_region','region_total','district_total']):continue
  if q['settlement_type'] and typekey(q['settlement_type']) not in physicaltypes:continue
  key=(namekey(q['settlement_name']),regionkey(q['region_norm']))
  if key in targetkeys:hist[(int(q['census_year']),key)].append(q)
LIFEFILES=[E/'largest_available_year_lifecycle_round2_20261008/accepted_lifecycle_events.csv',E/'largest_lifecycle_residual_20261008/accepted_lifecycle_events.csv',B/'g17_accepted_lifecycle_event.csv'];knownlife=set();knownlifenames=set()
for lf in LIFEFILES:
 if lf.is_file():
  ld=pd.read_csv(lf,dtype=str,keep_default_na=False)
  for field in ['place','recipient_place']:
   if field in ld:knownlifenames.update(namekey(x) for x in ld[field] if x)
  for col in ld.columns:
   if 'source_record_id' in col or 'source_uid' in col.lower():knownlife.update(x for x in ld[col] if x)
rough=[];competing=[]
for z in f.to_dict('records'):
 key=(namekey(z['settlement_name']),regionkey(z['region_norm']));native=nativemap.get(int(z['source_record_id'].rsplit(':',1)[1]));nr=modern.get(key,[])
 if not native:continue
 code=fullcode(native['oktmo'])
 for yr in [2002,2010]:
  old=hist.get((yr,key),[])
  if len(nr)!=1 or len(old)!=1:
   if old:competing.append({'current_source_record_id':z['source_record_id'],'current_name':z['settlement_name'],'population2021':z['population'],'historic_year':yr,'current_same_region_alltype_competitors_json':json.dumps(nr,ensure_ascii=False),'historic_same_region_alltype_competitors_json':json.dumps(old,ensure_ascii=False,default=str),'hold':'actual_regional_namesakes_requires_county_or_specific_parish_positive_binding'})
   continue
  q=old[0]
  if z['source_record_id'] in knownlife or q['source_record_id'] in knownlife or namekey(z['settlement_name']) in knownlifenames:continue
  if q['source_record_id'] in reserved:continue
  ct=typekey(z['settlement_type']);ht=typekey(q['settlement_type']);rural={'село','деревня','поселок','хутор','станица','слобода','местечко','аул','арбан','населенный пункт','сельский населенный пункт'}
  if ct!=ht and not (ct in rural and ht in rural):continue
  if not code.isdigit() or len(code)!=11 or codes[code]!=1:continue
  if q['root']==z['root']:continue
  rough.append((z,q,native,key))
# Source-literal physical NP readbacks grouped, one workbook at a time; county is not required for exact regional uniqueness.
groups=collections.defaultdict(list);rawproof={};rawpins={};sourceholds=[]
for z,q,n,key in rough:
 p=Path('/workspace/settlements-raw')/str(q['source_file'] or '');parts=q['source_record_id'].split(':')
 if p.is_file() and p.suffix.lower()=='.xls' and parts[-1].isdigit():groups[p].append(q)
 else:sourceholds.append({'current_source_record_id':z['source_record_id'],'historic_source_record_id':q['source_record_id'],'hold':'raw_historic_literal_source_not_available_in_cached_XLS'})
PREFIX={'с':'село','д':'деревня','п':'поселок','х':'хутор','ст-ца':'станица','нп':'населенный пункт','пгт':'пгт','рп':'рабочий поселок'}
def physical(s):
 ma=re.match(r'^\s*(с|д|п|х|ст-ца|н\.?п|пгт|рп)\.\s*(.+)$',str(s),re.I)
 if ma:return ma.group(2),PREFIX[ma.group(1).lower().replace('.','')]
 s=str(s).strip()
 for tp in ['железнодорожная станция','железнодорожный разъезд','поселок при станции','посёлок при станции','населенный пункт','населённый пункт','рабочий поселок','рабочий посёлок','поселок','посёлок','деревня','село','город','хутор','станица','слобода','местечко','аул','арбан','пгт','станция','разъезд']:
  if s.lower().startswith(tp+' '):return s[len(tp):].strip(),tp
 return '', ''
for p,qs in groups.items():
 rawpins[str(p)]=sha(p);b=xlrd.open_workbook(str(p),on_demand=True)
 for q in {q['source_record_id']:q for q in qs}.values():
  parts=q['source_record_id'].split(':');sn=parts[-2];rn=int(parts[-1]);
  try:s=b.sheet_by_name(sn)
  except xlrd.biffh.XLRDError:
   if sn.isdigit() and int(sn)<b.nsheets:s=b.sheet_by_index(int(sn))
   else:continue
  if not 1<=rn<=s.nrows:continue
  raw=s.row_values(rn-1)[:8];matches=[]
  for k,val in enumerate(raw[:-1]):
   name,tp=physical(val)
   if name and namekey(name)==namekey(q['settlement_name']) and typekey(tp)==typekey(q['settlement_type']):
    try:ok=q['population'] is None or float(raw[k+1])==float(q['population'])
    except (ValueError,TypeError):ok=False
    if ok:matches.append((k,name,tp))
  if len(matches)==1:
   k,name,tp=matches[0];rawproof[q['source_record_id']]={'source_file':str(p),'source_sha256':rawpins[str(p)],'source_locator':f'{s.name}:row:{rn}:physicalNPcol{k+1}:populationcol{k+2}','literal_raw_fields_first8_json':json.dumps(raw,ensure_ascii=False),'raw_literal_name':name,'raw_literal_type':tp,'positive_physical_NP_class':True,'native_name_type_population_reopened_equal':True,'historical_county_missing_or_unbounded_not_used_as_positive_binding':True}
 b.release_resources();del b
print('regional unique rough',len(rough),'raw literal positive',len(rawproof),'books',len(groups),flush=True)
rough=[r for r in rough if r[1]['source_record_id'] in rawproof];neededroots={z['root'] for a,q,n,k in rough for z in [a,q]};c.register('needed_roots',pd.DataFrame({'root':list(neededroots)}));members=c.execute('select s.source_record_id,s.root,s.census_year,s.oktmo,s.okato,s.settlement_name,s.settlement_type,s.region_norm,s.district_raw from read_parquet(?) s join needed_roots using(root)',[str(S)]).fetchdf();years=collections.defaultdict(set);mem=collections.defaultdict(list)
for z in members.to_dict('records'):years[z['root']].add(int(z['census_year']));mem[z['root']].append(z)
c.register('needed_members',members[['source_record_id','root']]);pts=c.execute('select p.source_record_id,p.latitude,p.longitude,p.coordinate_source_record_id,p.coordinate_admission_status,p.point_origin_file,p.point_origin_sha256,p.point_origin_locator,p.point_origin_kind,m.root from read_parquet(?) p join needed_members m using(source_record_id)',[str(P)]).fetchdf();c.close();pt={z['source_record_id']:z for z in pts.to_dict('records')};rootpt=collections.defaultdict(list)
for z in pt.values():rootpt[z['root']].append(z)
accepted=[];holds=[];edges=[];points=[]
for z,q,n,key in rough:
 sid=z['source_record_id'];oid=q['source_record_id'];a=z['root'];b=q['root'];reason=[];far=[]
 if sid not in pt:reason.append('current_accepted_ownphysical_point_not_present')
 if years[a]&years[b]:reason.append('sameyear_component_overlap')
 if sid in pt:
  xy=(float(pt[sid]['latitude']),float(pt[sid]['longitude']))
  for p in rootpt[b]+rootpt[a]:
   d=distance_km(xy,(float(p['latitude']),float(p['longitude'])))
   if d>5:far.append({'source_record_id':p['source_record_id'],'distance_km':d,'coordinate_source_record_id':p['coordinate_source_record_id']})
 if far:reason.append('accepted_historic_component_physical_point_over5km')
 if fullcode(q.get('oktmo') or '') and q.get('census_year')==2021:raise AssertionError()
 witness={'current_source_record_id':sid,'historic_source_record_id':oid,'current_population2021':z['population'],'historic_population':q['population'],'current_name':z['settlement_name'],'current_type':z['settlement_type'],'current_historic_raw_type_equal':typekey(z['settlement_type'])==typekey(q['settlement_type']),'rural_legal_type_continuity_status':'UNKNOWN_no_statuschange_date_inferred' if typekey(z['settlement_type'])!=typekey(q['settlement_type']) else 'literal_types_equal','region':z['region_norm'],'current_native_county':z['district_raw'],'current_native_specific_parish':n['mun_lower'],'current_native_owncode':fullcode(n['oktmo']),'current_owncode_unique_across_full_raw_NP_roster':True,'current_alltype_region_name_count':1,'historic_alltype_region_name_count':1,'historic_year':q['census_year'],'current_raw_primary_row_json':json.dumps(n,ensure_ascii=False),'historic_native_observation_json':json.dumps(q,ensure_ascii=False,default=str),'historic_raw_source_evidence_json':json.dumps(rawproof[oid],ensure_ascii=False),'current_accepted_physical_point_json':json.dumps(pt.get(sid),ensure_ascii=False,default=str),'current_component_members_actual66_json':json.dumps(mem[a],ensure_ascii=False,default=str),'historic_component_members_actual66_json':json.dumps(mem[b],ensure_ascii=False,default=str),'component_point_conflicts_json':json.dumps(far,ensure_ascii=False),'admission_holds':';'.join(reason),'identity_inference':'explicit ordinary settlement continuity from uniquely named same typed physical NP across all properNP types in same source region/year, source-bound raw physical NP row, unique current native owncode and independently accepted ownphysicalpoint; regional scope is administrative support; finite population is not identity evidence; historical NULL legacy scope/county absence alone is not a rejection','external_provider_identifier_transfer_asserted':False,'historical_date_coordinate_measurement_asserted':False,'population_boundary_comparability_asserted':False}
 if reason:holds.append(witness);continue
 accepted.append(witness);edges.append({'from_source_record_id':oid,'to_source_record_id':sid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_method':'exact_regional_unique_alltype_named_physical_NP_ordinary_continuity_sourcebound','admission_rule':'all-native alltype regional unique literal name; positive rawphysical NP source row and compatible rural/identical type; currentnativeowncode and independent accepted ownphysicalpoint; actual66UFyear/acceptedpoint/lifecycle/fullnative competitors guarded; explicit ordinary continuity, historic county/NULLlegacyScope absence not identity rejection','population_boundary_comparability_asserted':False,'evidence_file':str(O/'accepted_regional_unique_source_evidence.csv.gz'),'evidence_locator':f'historic_source_record_id={oid};current_source_record_id={sid}'})
 for member in mem[b]+mem[a]:
  mid=member['source_record_id']
  if mid in pt:continue
  carrier=pt[sid];points.append({'target_source_record_id':mid,'latitude':float(carrier['latitude']),'longitude':float(carrier['longitude']),'coordinate_admission_status':'reviewed_extension_rule_accepted','coordinate_source_record_id':carrier['coordinate_source_record_id'],'point_origin_file':carrier['point_origin_file'],'point_origin_sha256':carrier['point_origin_sha256'],'point_origin_locator':carrier['point_origin_locator'],'point_origin_kind':'retrospective_representative_point_through_explicit_regional_unique_ordinary_continuity','coordinate_binding_rule':'current source-bound ownphysical point through newly reviewed exact regional-unique named/type ordinary settlement continuity and existing historical native component identity; modern representative geography, historical census measurement unasserted','point_use_inference':'explicit retrospective own NP representative geography only','historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False,'external_provider_ID_binding_asserted':False,'current_carrier_source_record_id':sid})
# Historic root duplicated across proposed years reuses an edge once; point target may repeat only if literally identical carrier.
u={}
for p in points:
 sid=p['target_source_record_id']
 if sid in u:assert u[sid]==p
 u[sid]=p
points=list(u.values());edges=list({(z['from_source_record_id'],z['to_source_record_id']):z for z in edges}.values())
for fn,zs in [('accepted_identity_edge_delta',edges),('accepted_point_use_delta',points),('accepted_regional_unique_source_evidence',accepted),('regional_unique_admission_holds',holds),('regional_competing_name_regression_holds',competing),('regional_source_literal_holds',sourceholds)]:pd.DataFrame(zs).to_csv(O/(fn+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0})
unique={z['current_source_record_id']:z for z in accepted};r={'actual_baseline':66,'current_residual_singleton_or_partial2_carriers':len(f),'regional_unique_source_literal_pairs':len(rough),'accepted_identity_edges':len(edges),'accepted_retrospective_point_uses':len(points),'accepted_current_UIDs':len(unique),'accepted_current_known_population2021_not_main_gain':sum(float(z['current_population2021']) for z in unique.values() if z['current_population2021']),'admission_holds':len(holds),'historical_NULL_scope_positive_accepted_pairs':sum(json.loads(z['historic_native_observation_json'])['population_scope'] is None for z in accepted),'raw_workbooks_one_at_a_time':len(groups),'actual_State_loads':0,'population_or_sourcecounts_changed':False,'canonical_applied':False,'known_sourcebound_lifecycle_endpoints_excluded':len(knownlife),'known_sourcebound_lifecycle_place_names_guarded':len(knownlifenames),'unknown_native_type_negative_regional_rivals_retained':True,'conditional_main_gain':'must compose new edges+representative point uses against actual66 and evaluate full3 native positive finite population, not currentpoint populations','seconds':time.monotonic()-START,'peak_RSS_MB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'input_pins':{str(p):sha(p) for p in [S,P,C,F,RAW,RES,EXCLUDED,RULE,O/'build_regional_unique.py']+LIFEFILES},'raw_workbook_pins':rawpins};(O/'regional_unique_admission_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','raw_workbook_pins']},ensure_ascii=False))
