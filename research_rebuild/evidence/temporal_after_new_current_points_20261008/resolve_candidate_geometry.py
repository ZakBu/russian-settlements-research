from pathlib import Path
import sys,json,re,gzip,zipfile,io,collections,math,unicodedata
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;APP=R/'research_rebuild/evidence/primary_residual_mass_application_20261008';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,distance_km,sha
S=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');P=APP/'applied_point_snapshot.parquet';Y=Path('/workspace/settlements-work/coordinate_first_20261008/year_points.parquet');H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet');D=Path('/workspace/settlements-assets/baseline/legacy_database_20260929.duckdb');A=Path('/workspace/settlements-work/continuation_20261003/geonames_named_point_probe_v1/adm1_literal_alias_bindings.csv');RC=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv');GN=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');OSM=Path('/workspace/settlements-work/coordinate_first_20261008/sources/osm_geoapify_ru.zip');con=duckdb.connect();sel=con.execute('select source_record_id,census_year,settlement_name,settlement_type,region_norm from read_parquet(?) where census_year in(2002,2010)',[str(S)]).fetchdf();accepted=set(con.execute('select source_record_id from read_parquet(?)',[str(P)]).fetchnumpy()['source_record_id']);yp=con.execute('select * from read_parquet(?) where census_year in(2002,2010) and latitude is not null',[str(Y)]).fetchdf();yp=yp[~yp.source_record_id.isin(accepted)];rd=sel.set_index('source_record_id').to_dict('index');ef=con.execute("select source_record_id,effective_region_norm from read_parquet(?)",[str(R/'research_rebuild/evidence/main_axis_residual_registry_20261008/competitors/all_selected_native_competitors.parquet')]).fetchdf().set_index('source_record_id').effective_region_norm.to_dict()
for sid in rd:rd[sid]['region_norm']=ef[sid]
def n(v):
 x=normalize(v);x=re.sub(r'[^\w\s]+',' ',x);return ' '.join(x.split())
def nm(v):
 x=n(v);x=re.sub(r'^(?:п|поселок|оселок|с|село|д|деревня|г|город|рп|рабочий поселок|пгт|ст|станица|х|хутор)\s+','',x);x=re.sub(r'\s+п$','',x);x=re.sub(r'\bим\s+','имени ',x);x=re.sub(r'^(?:свх|совхоз)\s+','совхоза ',x);return x
def region(v):
 x=n(v);x=re.sub(r'\b(?:республика|республики|область|области|край|края|автономный|автономная|автономного|округ|округа|ао|авт|г|город)\b',' ',x);x=' '.join(x.split());return {'саха якутия':'саха','саха якутская':'саха','удмуртия':'удмуртская','чувашия':'чувашская','ханты мансийский югра':'ханты мансийский','кемеровская кузбасс':'кемеровская','чувашская чувашия':'чувашская'}.get(x,x)
def typ(v):
 x=n(v);return {'п':'поселок','с':'село','д':'деревня','х':'хутор','ст ца':'станица','г':'город','рп':'пгт','поселок городского типа':'пгт','рабочий поселок':'пгт','village':'село','hamlet':'деревня','town':'пгт','city':'город','isolated_dwelling':'деревня'}.get(x,x)
physical={'пгт','село','деревня','поселок','хутор','станица','аул','слобода'}
def compatible(a,b):return a==b or(a in physical and b in physical)
refs={provider:set(g.coordinate_ref) for provider,g in yp.groupby('provider')};source={};pins={str(q):sha(q) for q in [S,P,Y,H]};outcomes=collections.Counter()
# Independent raw source objects are reopened by their literal gazetteer row/claim locators.
if refs.get('RCSI'):
 pins[str(RC)]=sha(RC);rc=pd.read_csv(RC,sep=';',dtype=str,keep_default_na=False).set_index('id').to_dict('index')
 for ref in refs['RCSI']:
  k=ref.split('#row=')[-1];z=rc.get(k)
  if z:
   try:la,lo=float(z['latitude_dd']),float(z['longitude_dd'])
   except ValueError:continue
   source[ref]={'source_file':str(RC),'source_locator':'id='+k,'source_kind':'RCSI_literal_physical_settlement_row','source_name':z['settlement'],'source_names_json':json.dumps([z['settlement']],ensure_ascii=False),'source_type':typ(z['type']),'source_region':region(z['region']),'source_county':z['municipality'],'source_own_code':z['oktmo'],'source_latitude':la,'source_longitude':lo,'physical_NP_positive':typ(z['type']) in physical|{'город','станция','разъезд','починок','местечко','заимка','аал','арбан','кордон','участок','железнодорожный объект'}}
if refs.get('GeoNames'):
 pins[str(GN)]=sha(GN);pins[str(A)]=sha(A);amap=pd.read_csv(A,dtype=str).set_index('admin1').region_norm.map(region).to_dict();amap.update({'04':'алтайский','63':'саха','32':'ханты мансийский'});wanted={re.search(r'geonames.org/(\d+)',r).group(1) for r in refs['GeoNames']}
 with zipfile.ZipFile(GN) as z:
  with z.open('RU.txt') as f:
   for lineno,line in enumerate(io.TextIOWrapper(f,encoding='utf-8'),1):
    v=line.rstrip('\n').split('\t')
    if len(v)<19 or v[0] not in wanted:continue
    ref='https://www.geonames.org/'+v[0]+'/';names=[v[1],*v[3].split(',')];source[ref]={'source_file':str(GN),'source_locator':f'RU.txt;line1based={lineno};geonameid={v[0]}','source_kind':'GeoNames_literal_named_PPL_raw_row','source_name':v[1],'source_names_json':json.dumps(names,ensure_ascii=False),'source_type':'populated_locality' if v[6]=='P' else v[7],'source_region':amap.get(v[10],''),'source_county':v[11],'source_own_code':v[0],'source_latitude':float(v[4]),'source_longitude':float(v[5]),'physical_NP_positive':v[6]=='P' and v[7] in ['PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLA5','PPLC','PPLL','PPLQ','PPLS']}
if refs.get('OSM/Geoapify'):
 pins[str(OSM)]=sha(OSM);wanted=refs['OSM/Geoapify']
 with zipfile.ZipFile(OSM) as zz:
  for filename in zz.namelist():
   if not filename.endswith('.ndjson'):continue
   with zz.open(filename) as f:
    for lineno,line in enumerate(f,1):
     z=json.loads(line);ref=f"https://www.openstreetmap.org/{z['osm_type']}/{z['osm_id']}"
     if ref not in wanted:continue
     addr=z.get('address',{});tags=z.get('other_names',{});names=[z.get('name','')]
     for field in ['name:ru','alt_name','old_name','official_name','short_name']:names.extend(tags.get(field,'').split(';'))
     st=z.get('type',z.get('place',z.get('category','')));loc=z.get('location',[])
     if len(loc)!=2:continue
     source[ref]={'source_file':str(OSM),'source_locator':f'{filename};line1based={lineno};osm={z["osm_type"]}/{z["osm_id"]}','source_kind':'OSM_Geoapify_literal_named_locality_raw_object','source_name':z.get('name',''),'source_names_json':json.dumps(names,ensure_ascii=False),'source_type':typ(st),'source_region':region(addr.get('state','')),'source_county':addr.get('county',''),'source_own_code':str(z['osm_id']),'source_latitude':loc[1],'source_longitude':loc[0],'physical_NP_positive':str(st).lower() in ['city','town','village','hamlet','isolated_dwelling'],'raw_object_class_json':json.dumps({k:z.get(k) for k in ['type','place','category','address']},ensure_ascii=False)}
if refs.get('Wikipedia_cached'):
 pins[str(D)]=sha(D);db=duckdb.connect(str(D),read_only=True);wanted=pd.DataFrame({'url':sorted(refs['Wikipedia_cached'])});db.register('wanted_urls',wanted);wf=db.execute('select * from wikipedia_template_fields where permanent_url in(select url from wanted_urls)').fetchdf();db.close();groups=collections.defaultdict(list)
 for z in wf.to_dict('records'):groups[z['permanent_url']].append(z)
 def clean(x):return re.sub(r'\[\[([^]|]+)\|([^]]+)\]\]',r'\2',str(x)).replace('[[','').replace(']]','')
 for ref,rows in groups.items():
  fields={str(x['field_name_raw']).lower().strip():x['field_value_wikitext'] for x in rows};title=rows[0]['canonical_title'];names=[title.split('(')[0],clean(fields.get('русское название',''))]
  try:la=float(fields['lat_deg'].replace(',','.'))+float(fields.get('lat_min','0'))/60+float(fields.get('lat_sec','0'))/3600;lo=float(fields['lon_deg'].replace(',','.'))+float(fields.get('lon_min','0'))/60+float(fields.get('lon_sec','0'))/3600
  except(KeyError,ValueError):continue
  st=typ(clean(fields.get('статус',fields.get('тип',''))));source[ref]={'source_file':str(D),'source_locator':f'wikipedia_template_fields;permanent_url={ref};article_pageid={rows[0]["article_pageid"]}','source_kind':'cached_Wikipedia_literal_own_NP_infobox_claims','source_name':title,'source_names_json':json.dumps(names,ensure_ascii=False),'source_type':st,'source_region':region(clean(fields.get('регион',''))),'source_county':clean(fields.get('район','')),'source_own_code':re.sub(r'\D','',str(fields.get('код октмо',''))),'source_latitude':la,'source_longitude':lo,'physical_NP_positive':st in physical|{'город','станция','разъезд','починок','местечко','заимка','аал','арбан','кордон','участок','железнодорожная станция'} and not re.search('сельское поселение|район|сельсовет',title,re.I),'raw_claim_fields_json':json.dumps({k:v for k,v in fields.items() if k in ['русское название','статус','тип','регион','район','код октмо','lat_deg','lat_min','lat_sec','lon_deg','lon_min','lon_sec']},ensure_ascii=False)}
if refs.get('GeoKLADR2011'):
 CP=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet');GP=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet');pins[str(CP)]=sha(CP);pins[str(GP)]=sha(GP);c=duckdb.connect();cl=c.execute('select historical_okato,name,status,is_settlement_raw,source_line_1based,source_sha256 from read_parquet(?)',[str(CP)]).fetchdf().drop_duplicates(['historical_okato','name','status']);cl=cl[~cl.historical_okato.duplicated(keep=False)].set_index('historical_okato').to_dict('index');geo=c.execute('select * from read_parquet(?)',[str(GP)]).fetchdf();c.close();geo=geo[~geo.is_deleted.fillna(True)];geo=geo.drop_duplicates('historical_okato').set_index('historical_okato').to_dict('index');province={k[:2]:region(g.region_norm.mode().iloc[0]) for k,g in sel.groupby(sel.source_record_id.str[:0])} if False else {}
 # Historical provider province binding is independently derived from accepted own-name/type raw-object native bindings, not external ID equality.
 hh=con.execute('select historical_okato,historical_point_modern_region from read_parquet(?) where historical_name_exact and historical_type_exact and historical_code_structure_compatible',[str(H)]).fetchdf() if False else duckdb.connect().execute('select historical_okato,historical_point_modern_region from read_parquet(?) where historical_name_exact and historical_type_exact and historical_code_structure_compatible',[str(H)]).fetchdf()
 province={k:region(g.historical_point_modern_region.dropna().mode().iloc[0]) for k,g in hh[hh.historical_point_modern_region.notna()].groupby(hh.historical_okato.str[:2])}
 for ref in refs['GeoKLADR2011']:
  code=ref.split('OKATO=')[-1];z=geo.get(code);cc=cl.get(code)
  if not z or not cc:continue
  la,lo=z.get('latitude_from_lat'),z.get('longitude_from_long')
  if pd.isna(la) or pd.isna(lo):continue
  source[ref]={'source_file':str(GP),'source_locator':f'record1based={z["record_number_1based"]};OKATO={code};classifier_line1based={cc["source_line_1based"]}','source_kind':'raw_2009_named_typed_leaf_plus_2011_owncode_GeoKLADR_point_candidate','source_name':z['name_raw'],'source_names_json':json.dumps([z['name_raw'],cc['name']],ensure_ascii=False),'source_type':typ(z['settlement_type_raw']),'source_region':province.get(code[:2],''),'source_county':'','source_own_code':code,'source_latitude':la,'source_longitude':lo,'physical_NP_positive':str(cc['is_settlement_raw'])=='t' and typ(z['settlement_type_raw']) in physical|{'город','станция','разъезд','починок','местечко','заимка','аал','арбан','кордон','участок','железнодорожный объект'},'raw_classifier_name':cc['name'],'raw_classifier_type':cc['status'],'raw_classifier_sha256':cc['source_sha256'],'raw_geokladr_sha256':z['source_sha256']}
valid=[];held=[]
for z in yp.to_dict('records'):
 sid=z['source_record_id'];native=rd[sid];q=source.get(z['coordinate_ref']);reason=[]
 if q is None:reason.append('no independent named physical source object resolved for proposal locator')
 else:
  names=json.loads(q['source_names_json']);name_ok=nm(native['settlement_name']) in {nm(x) for x in names};region_ok=region(native['region_norm'])==q['source_region'];type_ok=q['source_type']=='populated_locality' or compatible(typ(native['settlement_type']),q['source_type']);distance=distance_km((float(z['latitude']),float(z['longitude'])),(float(q['source_latitude']),float(q['source_longitude'])))
  if not name_ok:reason.append('actual proposal source label or literal alias contradicts native NP name')
  if not region_ok:reason.append('actual proposal source province contradicts native source province')
  if not type_ok:reason.append('actual proposal source populated-locality class contradicts native NP type')
  if not q['physical_NP_positive']:reason.append('actual proposal source is not independently a physical populated locality')
  if distance>0.05:reason.append('actual source point differs from experimental proposed geometry')
 if reason:held.append({'source_record_id':sid,'provider':z['provider'],'coordinate_ref':z['coordinate_ref'],'native_name':native['settlement_name'],'held_reason':'; '.join(reason)});outcomes.update(reason);continue
 valid.append({'source_record_id':sid,'census_year':native['census_year'],'native_name':native['settlement_name'],'latitude':float(q['source_latitude']),'longitude':float(q['source_longitude']),'provider':z['provider'],'coordinate_ref':z['coordinate_ref'],'coordinate_rule_proposal':z['coordinate_rule'],'geometry_status':'candidate_only_independent_actual_named_NP_source_reopened_no_historic_measurement_or_ID_binding_claim',**q});outcomes[z['provider']+': independent literal own-NP source object positive']+=1
pd.DataFrame(valid).to_parquet(O/'resolved_candidate_geometry.parquet',index=False,compression='zstd');pd.DataFrame(held).to_csv(O/'candidate_geometry_resolver_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0});receipt={'status':'experimental_geometry_proposals_resolved_against_actual_named_NP_source_objects_candidate_only','no_State_load':True,'candidate_rows_considered':len(yp),'independent_named_NP_positive_candidates':len(valid),'held_rows':len(held),'outcomes':dict(outcomes),'provider_locator_does_not_admit_identity_or_coordinates':True,'coordinate_first_status_is_experimental_not_accepted':True,'use_conditions':{'GeoNames':'CC BY4.0; GeoNames','OSM/Geoapify':'ODbL; ©OpenStreetMap contributors; respect share-alike for derived databases','Wikipedia':'CC BY-SA attribution to exact permanent revisions preserved','RCSI':'CC BY-NC-SA catalog terms preserved; candidate geometry only, final retrospective coordinates reused from independently accepted ownpoints','GeoKLADR':'Preserve source version/hash/raw DBF and classifier locators; candidate coordinates not admitted historic measurement'},'input_pins':pins,'output_pins':{q.name:sha(q) for q in [O/'resolved_candidate_geometry.parquet',O/'candidate_geometry_resolver_holds.csv.gz']}};(O/'candidate_geometry_resolver_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins','use_conditions']},ensure_ascii=False))
