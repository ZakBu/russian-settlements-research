from pathlib import Path
import pandas as pd,duckdb,json,collections,sys,re,ast,math,unicodedata
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;E=O.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
RULE=E/'current_positive_residual_point_sources_20261008/review_articles.py';tree=ast.parse(RULE.read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['bare','namekey','typekey','regionkey','county','fullcode','splitname']],type_ignores=[]),str(RULE),'exec'))
F=E/'current_remaining_cached_named_sources_20261008/cached_named_source_holds.csv.gz';RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');RC=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv');OS=Path('/workspace/settlements-work/coordinate_first_20261008/sources/osm_geoapify_ru.zip');GN=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');f=pd.read_csv(F,dtype=str,keep_default_na=False);pins={str(q):sha(q) for q in [F,RAW,RC,OS,GN,RULE]};c=duckdb.connect();raw=c.execute('select row_number() over() rn,object_level,object_name,oktmo,region,mun_upper,mun_lower,settlement_dadata,settlement_type_full_dadata,fias_id_dadata,settlement_fias_id_dadata,fias_level_dadata,oktmo_dadata,latitude_dadata,longitude_dadata from read_parquet(?)',[str(RAW)]).fetchdf().astype(object).fillna('');c.close();raw=raw.set_index('rn');rc=pd.read_csv(RC,sep=';',dtype=str,keep_default_na=False).set_index('id').to_dict('index');typemap={'д':'деревня','с':'село','п':'поселок','х':'хутор','ст-ца':'станица','ст':'станция','нп':'населенный пункт','рзд':'разъезд','г':'город','пгт':'пгт','рп':'рабочий поселок','сл':'слобода'};positive=[];holds=[];counts=collections.Counter()
for z in f.to_dict('records'):
 sid=z['source_record_id'];rr=raw.loc[int(sid.rsplit(':',1)[1])].to_dict();aa=json.loads(z['literal_owncoded_RCSI_rows_json']);objects=collections.defaultdict(list)
 for q in aa:
  actual=rc[q['id']]
  assert all(str(q[k])==str(actual[k]) for k in ['settlement','type','oktmo','region','municipality','latitude_dd','longitude_dd'])
  key=tuple(str(q[k]) for k in ['settlement','type','oktmo','region','municipality','latitude_dd','longitude_dd']);objects[key].append(q)
 if len(objects)!=1:continue
 a=next(iter(objects.values()));r=a[0];xy=float(r['latitude_dd']),float(r['longitude_dd']);osm=json.loads(z['cached_named_OSM_matches_json']);gn=json.loads(z['cached_GeoNames_same_region_name_witnesses_json']);og={};gg={}
 for q in osm:
  p=q['raw'];loc=p.get('location',[])
  if p.get('type') in ['hamlet','village','town','city','isolated_dwelling'] and len(loc)==2:og[(p['osm_type'],p['osm_id'])]=q
 for q in gn:gg[q['geonameid']]=q
 osnear=[q for q in og.values() if distance_km(xy,(q['raw']['location'][1],q['raw']['location'][0]))<=1];gnnear=[q for q in gg.values() if distance_km(xy,(q['latitude'],q['longitude']))<=1];chosen=None;proof='';rawprovider=None
 if len(osnear)==1 and all(distance_km(xy,(q['raw']['location'][1],q['raw']['location'][0]))>5 for q in og.values() if q not in osnear):chosen=osnear[0];proof='deduplicated identical raw owncoded RCSI physical object + independent unique actual named OSM physical object <=1km; other named OSM objects >5km'
 elif len(gnnear)==1 and all(distance_km(xy,(q['latitude'],q['longitude']))>5 for q in gg.values() if q not in gnnear):chosen=gnnear[0];proof='deduplicated identical raw owncoded RCSI physical object + independent unique actual named GeoNames PPL object <=1km; other regional named PPL objects >5km'
 # A raw-provider wrongcode is not an external identifier binding; only a positive named physical coordinate corroboration is considered, and the RCSI point is used.
 if not chosen:
  try:pp=float(rr['latitude_dadata']),float(rr['longitude_dadata'])
  except (ValueError,TypeError):pp=None
  nk,nt=splitname(rr['object_name']);pcode=fullcode(rr['oktmo_dadata']);ncode=fullcode(rr['oktmo'])
  named=rr['object_level']=='Населенный пункт' and str(rr['fias_level_dadata'])=='6' and bool(rr['fias_id_dadata']) and rr['fias_id_dadata']==rr['settlement_fias_id_dadata'] and namekey(rr['settlement_dadata'])==namekey(z['settlement_name']) and typekey(rr['settlement_type_full_dadata'])==typekey(z['settlement_type'])
  if pp and named and 41<=pp[0]<=82 and 19<=pp[1]<=180 and pcode[:2]==ncode[:2] and distance_km(xy,pp)<=1:
   # All actual samecounty current namesakes must have independently source-named provider geometry >5km, or the coded target remains unresolved.
   rivals=json.loads(z['samecounty_native_name_rivals_json']);resolved=True
   for rival in rivals:
    rv=raw.loc[int(rival['rn'])].to_dict()
    try:rp=float(rv['latitude_dadata']),float(rv['longitude_dadata'])
    except (ValueError,TypeError):resolved=False;continue
    rn,rt=splitname(rv['object_name']);valid=fullcode(rv['oktmo'])==fullcode(rv['oktmo_dadata']) and namekey(rv['settlement_dadata'])==namekey(rn) and typekey(rv['settlement_type_full_dadata'])==typekey(rt) and str(rv['fias_level_dadata'])=='6' and rv['fias_id_dadata']==rv['settlement_fias_id_dadata']
    if not valid or distance_km(xy,rp)<=5:resolved=False
   if resolved:rawprovider=rr;proof='unique actual owncoded typed/name/region/county RCSI physical object + literal named level6 raw FIAS NP geometry <=1km; samecounty native rivals independently owncoded/named provider points >5km; wrong provider owncode does not transfer external ID and point used from correctly owncoded independent RCSI'
 if not chosen and rawprovider is None:counts['unique_coded_RCSI_still_lacks_independent_unique_named_physical_agreement']+=1;continue
 if chosen and 'raw' in chosen:
  p=chosen['raw'];la,lo=p['location'][1],p['location'][0];origin=OS;locator=f"{chosen['member']}:line:{chosen['line']}:osm_{p['osm_type']}:{p['osm_id']}";cid=f"OSM:{p['osm_type']}:{p['osm_id']}"
 elif chosen:
  la,lo=chosen['latitude'],chosen['longitude'];origin=GN;locator=f"RU.txt:line:{chosen['line']}:geonameid:{chosen['geonameid']}";cid='GeoNames:'+chosen['geonameid']
 else:la,lo=xy;origin=RC;locator='id='+','.join(q['id'] for q in a)+';literal ownname/type/oktmo/municipality/latitude_dd/longitude_dd';cid='RCSI:'+','.join(q['id'] for q in a)
 positive.append({**z,'target_source_record_id':sid,'latitude':la,'longitude':lo,'coordinate_source_record_id':cid,'point_origin_file':str(origin),'point_origin_sha256':pins[str(origin)],'point_origin_locator':locator,'point_origin_kind':'independent_current_owncoded_named_physical_point_corroborated_under_duplicate_object_rule','coordinate_admission_status':'candidate_only_positive_sourcebinding_pending_actual63','coordinate_binding_rule':proof,'external_provider_ID_binding_asserted':False,'identical_duplicate_RCSI_source_object_ids_json':json.dumps([q['id'] for q in a]),'raw_FIAS_positive_physical_corroboration_json':json.dumps(rawprovider,ensure_ascii=False,default=str),'reopened_RCSI_objects_json':json.dumps(a,ensure_ascii=False),'deduplicated_RCSI_physical_objects':len(objects),'duplicate_RCSI_rows_folded':len(a)-1,'historical_census_coordinate_asserted':False});counts['positive_current_sourcebinding']+=1
pd.DataFrame(positive).to_csv(O/'independent_named_current_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});receipt={'status':'candidate_only_closed_duplicate_object_and_independent_named_physical_point_binding_pending_actual63','positive_current_candidates':len(positive),'known2021_population':sum(float(z['population']) for z in positive if z['population']),'no_State_load':True,'outcomes':dict(counts),'actual_identical_duplicates_folded_only':True,'raw_wrongprovider_code_not_asserted_as_binding':True,'input_pins':pins,'output_pins':{str(O/'independent_named_current_candidates.csv.gz'):sha(O/'independent_named_current_candidates.csv.gz')}};(O/'independent_named_candidate_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k not in ['input_pins','output_pins']},ensure_ascii=False))
