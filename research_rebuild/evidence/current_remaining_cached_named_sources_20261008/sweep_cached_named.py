from pathlib import Path
import ast,sys,re,json,unicodedata,zipfile,collections,hashlib,math,gzip
import pandas as pd,duckdb
O=Path(__file__).parent;E=O.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
RULE=E/'current_positive_residual_point_sources_20261008/review_articles.py'
tree=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
F=E/'current_positive_residual_point_sources_20261008/prioritized_unresolved_after_round2.csv.gz';RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');RC=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv');OS=Path('/workspace/settlements-work/coordinate_first_20261008/sources/osm_geoapify_ru.zip');GN=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');AD=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_admin1CodesASCII_20260907.txt')
pins={str(p):sha(p) for p in [RULE,F,RAW,RC,OS,GN,AD,O/'sweep_cached_named.py']};f=pd.read_csv(F,dtype=str,keep_default_na=False);c=duckdb.connect();raw=c.execute('select row_number() over() rn,object_level,object_name,oktmo,region,mun_upper,mun_lower from read_parquet(?)',[str(RAW)]).fetchdf();c.close();ri=collections.defaultdict(list);rco=collections.defaultdict(list)
for z in raw[raw.object_level.eq('Населенный пункт')].to_dict('records'):
 n,t=splitname(z['object_name']);ri[(namekey(n),regionkey(z['region']),county(z['mun_upper']))].append(z);rco[fullcode(z['oktmo'])].append(z)
rawby=raw.set_index('rn');targets=collections.defaultdict(list)
for z in f.to_dict('records'):targets[(namekey(z['settlement_name']),regionkey(z['region_norm']),county(z['district_raw']))].append(z)
rc=pd.read_csv(RC,sep=';',dtype=str,keep_default_na=False);rc['rawline']=range(2,len(rc)+2);rcodes=collections.defaultdict(list);rcnames=collections.defaultdict(list)
for z in rc.to_dict('records'):
 rcodes[fullcode(z['oktmo'])].append(z);rcnames[(namekey(z['settlement']),regionkey(z['region']),county(z['municipality']))].append(z)
osm=collections.defaultdict(list);source_rows=[]
with zipfile.ZipFile(OS) as zf:
 for member in zf.namelist():
  if not member.endswith('.ndjson'):continue
  with zf.open(member) as stream:
   for ln,line in enumerate(stream,1):
    z=json.loads(line);ad=z.get('address',{});reg=regionkey(ad.get('state',''));co=county(ad.get('county',''));names=[z.get('name',''),z.get('other_names',{}).get('name:ru','')];keys={(namekey(n),reg,co) for n in names if n}
    for key in keys&targets.keys():osm[key].append({'member':member,'line':ln,'raw':z,'raw_line':line.decode().rstrip(),'key':key})
# GeoNames supplies a secondary independent physical locality witness; ADM1 and exact Russian primary/alternate names only.
admin={};
for line in AD.read_text().splitlines():
 p=line.split('\t')
 if p[0].startswith('RU.'):admin[p[0].split('.')[1]]=regionkey(p[1])
# Reopen literal GeoNames ADM1 aliases to establish regional labels without transliteration guesses.
with zipfile.ZipFile(GN) as zf:
 with zf.open('RU.txt') as stream:
  for line in stream:
   p=line.decode().rstrip('\n').split('\t')
   if len(p)<19 or p[7]!='ADM1':continue
   rs={regionkey(n) for n in [p[1]]+p[3].split(',') if re.search('[а-я]',normalize(n))}
   targetregs={k[1] for k in targets};matches=rs&targetregs
   if len(matches)==1:admin[p[10]]=next(iter(matches))
geos=collections.defaultdict(list)
with zipfile.ZipFile(GN) as zf:
 with zf.open('RU.txt') as stream:
  for ln,line in enumerate(stream,1):
   p=line.decode().rstrip('\n').split('\t')
   if len(p)<19 or p[6]!='P' or p[7] not in ['PPL','PPLA','PPLA2','PPLA3','PPLA4']:continue
   for n in [p[1]]+p[3].split(','):
    nk=namekey(n)
    if not re.search('[а-я]',normalize(n)):continue
    geos[(nk,admin.get(p[10],''))].append({'raw_line':line.decode().rstrip(),'line':ln,'geonameid':p[0],'name':p[1],'feature_class':p[6],'feature_code':p[7],'latitude':float(p[4]),'longitude':float(p[5]),'admin1':p[10],'admin2':p[11]})
typemap={'д':'деревня','с':'село','п':'поселок','х':'хутор','ст-ца':'станица','ст':'станция','нп':'населенный пункт','рзд':'разъезд','г':'город','пгт':'пгт','рп':'рабочий поселок','сл':'слобода'}
rows=[];accepted=[];holds=[]
for z in f.to_dict('records'):
 sid=z['source_record_id'];rn=int(sid.rsplit(':',1)[1]);native=rawby.loc[rn].to_dict();key=(namekey(z['settlement_name']),regionkey(z['region_norm']),county(z['district_raw']));rivals=[q for q in ri[key] if int(q['rn'])!=rn];rcode=fullcode(native['oktmo']);rcl=rcodes.get(rcode,[]);rcgood=[]
 for q in rcl:
  try:xy=(float(q['latitude_dd']),float(q['longitude_dd']));valid=41<=xy[0]<=82 and (-180<=xy[1]<=180)
  except ValueError:valid=False
  if len(rco[rcode])==1 and valid and namekey(q['settlement'])==key[0] and regionkey(q['region'])==key[1] and county(q['municipality'])==key[2] and typekey(typemap.get(q['type'],q['type']))==typekey(z['settlement_type']):rcgood.append(q)
 osml=osm[key];og=[]
 for q in osml:
  p=q['raw'];xy=p.get('location',[])
  if p.get('type') in ['hamlet','village'] and p.get('osm_type') in ['node','way','relation'] and len(xy)==2 and 41<=xy[1]<=82 and (-180<=xy[0]<=180):og.append(q)
 # Duplicate representations are never arbitrarily first-picked.
 unique={ (q['raw'].get('osm_type'),q['raw'].get('osm_id')):q for q in og};og=list(unique.values());proof=[];chosen=None;why=[]
 if len(og)==1 and not rivals:chosen=og[0];proof.append('unique exact current own-name/region/county physical OSM place object with no native samecounty namesake')
 elif len(rcgood)==1 and og:
  r=rcgood[0];near=[q for q in og if distance_km((float(r['latitude_dd']),float(r['longitude_dd'])),(q['raw']['location'][1],q['raw']['location'][0]))<=1]
  if len(near)==1 and all(distance_km((near[0]['raw']['location'][1],near[0]['raw']['location'][0]),(q['raw']['location'][1],q['raw']['location'][0]))>5 for q in og if q is not near[0]):chosen=near[0];proof.append('unique literal owncode/name/type/region/county RCSI row independently agrees <=1km with one exact physical OSM place object; other name rivals >5km')
 gnchosen=None
 if not chosen and len(rcgood)==1:
  r=rcgood[0];gs=list({q['geonameid']:q for q in geos.get((key[0],key[1]),[])}.values());near=[q for q in gs if distance_km((float(r['latitude_dd']),float(r['longitude_dd'])),(q['latitude'],q['longitude']))<=1]
  if len(near)==1 and all(distance_km((near[0]['latitude'],near[0]['longitude']),(q['latitude'],q['longitude']))>5 for q in gs if q is not near[0]):gnchosen=near[0];proof.append('unique literal owncode/name/type/region/county RCSI row independently agrees <=1km with one exact named physical GeoNames P-class locality in literal ADM1 region; other same-region named PPLs >5km')
 if chosen:
  p=chosen['raw'];lat,lon=p['location'][1],p['location'][0]
  # Agreement is recorded, but no incompatible raw provider coordinate is reused.
  chosenpoint={'latitude':lat,'longitude':lon,'point_origin_file':str(OS),'point_origin_sha256':pins[str(OS)],'point_origin_locator':f"{chosen['member']}:line:{chosen['line']}:osm_{p['osm_type']}:{p['osm_id']}",'point_origin_kind':'cached_named_physical_OSM_place_object_representative_point','coordinate_source_record_id':f"OSM:{p['osm_type']}:{p['osm_id']}"}
 elif gnchosen:
  p=gnchosen;chosenpoint={'latitude':p['latitude'],'longitude':p['longitude'],'point_origin_file':str(GN),'point_origin_sha256':pins[str(GN)],'point_origin_locator':f"RU.txt:line:{p['line']}:geonameid:{p['geonameid']}",'point_origin_kind':'cached_named_owncode_corroborated_physical_GeoNames_PPL_point','coordinate_source_record_id':f"GeoNames:{p['geonameid']}"}
 else:
  if rivals:why.append('native_samecounty_name_rivals_without_unique_owncoded_physical_point_agreement')
  if not og:why.append('no_exact_named_region_county_physical_OSM_object')
  if len(og)>1:why.append('multiple_distinct_local_named_OSM_objects')
  if rcgood and not og:why.append('literal_owncoded_RCSI_point_without_independent_named_physical_node')
  if len(rcgood)>1:why.append('multiple_literal_owncoded_RCSI_rows')
  chosenpoint={}
 evidence={**z,**chosenpoint,'native_primary_row_json':json.dumps(native,ensure_ascii=False,default=str),'samecounty_native_name_rivals_json':json.dumps(rivals,ensure_ascii=False,default=str),'literal_owncoded_RCSI_rows_json':json.dumps(rcgood,ensure_ascii=False),'RCSI_code_lookup_all_rows_json':json.dumps(rcl,ensure_ascii=False),'cached_named_OSM_matches_json':json.dumps(osml,ensure_ascii=False),'cached_GeoNames_same_region_name_witnesses_json':json.dumps(geos.get((key[0],key[1]),[]),ensure_ascii=False),'source_binding_proof':';'.join(proof),'source_binding_holds':';'.join(why),'external_provider_ID_binding_asserted':False,'native_current_fullcode':rcode}
 rows.append(evidence)
 if chosen or gnchosen:accepted.append(evidence)
 else:holds.append(evidence)
for n,d in [('all_cached_named_source_review',rows),('source_positive_cached_named_point_candidates',accepted),('cached_named_source_holds',holds)]:pd.DataFrame(d).to_csv(O/(n+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
r={'remaining_current_targets':len(f),'remaining_known_population':pd.to_numeric(f.population,errors='coerce').sum(),'source_positive_point_candidates':len(accepted),'source_positive_population':sum(float(z['population']) for z in accepted if z['population']),'positive100_candidates':sum(float(z['population'] or 0)>=100 for z in accepted),'input_pins':pins,'candidate_not_admission':True,'no_State_load_no_graph_population_quality_changes':True};(O/'cached_named_source_sweep_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'},ensure_ascii=False))
