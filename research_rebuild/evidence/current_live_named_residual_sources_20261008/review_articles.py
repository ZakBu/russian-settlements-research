from pathlib import Path
import sys,json,gzip,re,unicodedata,collections
import duckdb,pandas as pd
O=Path(__file__).parent;E=O.parent;R=E.parent.parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
RAW=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');W=Path('/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet');S=Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet');f=pd.read_csv(O/'positive100_priority_roster.csv.gz',keep_default_na=False);w=pd.read_csv(O/'cached_Wikidata_positive100_bindings.csv.gz',keep_default_na=False,dtype={'source_oktmo_exact_digits':str,'source_oktmo_raw':str});targets=pd.read_csv(O/'cached_title_source_binding_candidates.csv.gz',keep_default_na=False);sourceindex=json.loads(gzip.open(O/'cached_title_article_sources_index.json.gz','rt').read());bytitle={z['article_title']:z for z in sourceindex}
if (O/'searched_own_article_sources_index.json.gz').exists():
 sourceindex.extend(json.loads(gzip.open(O/'searched_own_article_sources_index.json.gz','rt').read()));bytitle={z['article_title']:z for z in sourceindex};targets=pd.concat([targets,pd.read_csv(O/'searched_own_article_title_candidates_filtered.csv.gz',keep_default_na=False)],ignore_index=True)
c=duckdb.connect();c.register('targets',f[['source_record_id']]);raw=c.execute('select row_number() over() rn,object_level,object_name,oktmo,region,mun_upper,mun_lower,population,fias_id_dadata,settlement_fias_id_dadata,fias_level_dadata,oktmo_dadata,okato_dadata,settlement_dadata,settlement_type_full_dadata,latitude_dadata,longitude_dadata,qc_geo_dadata from read_parquet(?)',[str(RAW)]).fetchdf().set_index('rn');screen=c.execute('select s.* from read_parquet(?) s join targets using(source_record_id)',[str(S)]).fetchdf().set_index('source_record_id');c.close();pins={str(p):sha(p) for p in [RAW,W,S,O/'review_articles.py',O/'positive100_priority_roster.csv.gz',O/'cached_Wikidata_positive100_bindings.csv.gz',O/'cached_title_source_binding_candidates.csv.gz',O/'cached_title_article_sources_index.json.gz']}
def bare(v):
 v=unicodedata.normalize('NFC',''.join(z for z in unicodedata.normalize('NFD',normalize(v)) if z!='\u0301'));return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',v).split())
def namekey(v):
 v=normalize(v).replace('_x000d_','').replace('cлобода','слобода');v=re.sub(r'\bим\.?\s+', 'имени ',v);v=re.sub(r'\bсвх\b','совхоза',v);v=re.sub(r'\b(?:n|№)\s*(\d)',r'номер \1',v);v=re.sub(r'ж\.?\s*[д/]\.?\s*','железнодорожная ',v);v=v.replace('ж/д','железнодорожная');v=re.sub(r'\bжелезнодорожн(?:ая|ой|ого)\b','железнодорожная',v);v=re.sub(r'^\s*(?:поселок\s+)?(?:при\s+)?(?:железнодорожная\s+)?(?:станци[яи]|разъезда?|ст\.)\s+','',v);v=re.sub(r',?\s*железнодорожная\s+станция\s*$','',v);v=re.sub(r'^\s*поселок\s+','',v);return bare(v)
def typekey(v):
 v=bare(v)
 if v in ['сельский поселок','поселок сельского типа','поселок станции','поселок железнодорожного разъезда','поселок при станции','поселок при железнодорожной станции','поселок железнодорожной станции','поселок и при станция и']:v='поселок'
 if v in ['железнодорожная станция','железнодорожный разъезд']:v='железнодорожный объект'
 return v
def regionkey(v):
 v=bare(v);v=re.sub(r'\b(?:республика|область|край|автономная|автономный|округ|россия|республики)\b',' ',v);v=' '.join(v.split());return {'якутия':'саха якутия','северная осетия':'северная осетия алания','чувашия':'чувашская','чувашская чувашия':'чувашская','кемеровская кузбасс':'кемеровская','удмуртия':'удмуртская','калмыкия':'калмыкия','карелия':'карелия'}.get(v,v)
def county(v):
 v=re.sub(r'\([^)]*(?:\)|$)',' ',v);return bare(re.sub(r'\b(?:муниципальное образование|муниципальный|муниципального|городской|городского|город|города|округ|округа|район|района|улус|улуса|административный|город курорт)\b',' ',normalize(v)))
def fullcode(v):
 v=str(v);v=v[:-2] if v.endswith('.0') else v;return v.zfill(11) if v.isdigit() and len(v) in [10,11] else v
def splitname(v):
 v=str(v).strip();types=['железнодорожная площадка','железнодорожный объект','населенный пункт','рабочий поселок','город','посёлок','поселок','деревня','село','хутор','станица','станция','разъезд','слобода','пгт','рп']
 for t in types:
  if normalize(v).startswith(normalize(t)+' '):return v[len(t):].strip(),t
 return v,''
rawid=collections.defaultdict(list);rawcodes=collections.defaultdict(list)
for rn,z in raw[raw.object_level.eq('Населенный пункт')].iterrows():
 n,t=splitname(z.object_name);rawid[(namekey(n),typekey(t),regionkey(z.region),county(z.mun_upper))].append(int(rn));rawcodes[fullcode(z.oktmo)].append(int(rn))
# Reopen cached raw own full P764 properties once for all exact positive bindings.
wiki=collections.defaultdict(list);requests=collections.defaultdict(dict)
for z in w.to_dict('records'):
 if not z['wikidata_truthy_exact_p764_match'] or z['entity_competition_across_tsv_or_truthy'] or z['source_observation_competition_for_exact_oktmo']:continue
 wiki[z['source_record_id']].append(z)
 for p in json.loads(z['wikidata_truthy_exact_p764_claims_json']):requests[p['source_file']][int(p['line_number'])]=(z['wikidata_qid'],z['source_oktmo_exact_digits'])
for fn,req in requests.items():
 p=Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')/fn;pins[str(p)]=sha(p);found=set()
 with gzip.open(p,'rt') as stream:
  for ln,line in enumerate(stream,1):
   if ln in req:
    q,code=req[ln];z=json.loads(line);assert z['item'].rsplit('/',1)[-1]==q and z['property'].endswith('/P764') and str(z['value'])==code;found.add(ln)
   if ln>=max(req):break
 assert found==set(req)
def infobox(t):
 t=re.sub(r'<!--.*?-->','',t,flags=re.S);m=re.search(r'\{\{\s*НП\+Россия\b',t,re.I)
 if not m:return ''
 i=m.start();j=i;depth=0
 while j<len(t)-1:
  token=t[j:j+2]
  if token=='{{':depth+=1;j+=2
  elif token=='}}':depth-=1;j+=2
  else:j+=1
  if depth==0:return t[i:j]
 return ''
def val(box,key):
 m=re.findall(r'\|\s*'+re.escape(key)+r'\s*=\s*([^|\n]*)',box);return m[0].strip() if len(m)==1 else ''
def clean(v):return re.sub(r'\[\[|\]\]|<[^>]+>',' ',v.split('{{!}}',1)[0]).strip()
entities=json.loads(gzip.open(O/'own_article_entities_index.json.gz','rt').read());pins[str(O/'own_article_entities_index.json.gz')]=sha(O/'own_article_entities_index.json.gz')
accepted=[];holds=[];candidates=[]
for sid,ts in targets.groupby('source_record_id',sort=False):
 if sid not in set(f.source_record_id):continue
 z=f[f.source_record_id.eq(sid)].iloc[0].to_dict();rn=int(sid.rsplit(':',1)[1]);own=raw.loc[rn].to_dict();owncode=fullcode(own['oktmo']);positive=[]
 for target in ts.to_dict('records'):
  title=target['article_title'];src=bytitle.get(title);page=src.get('page',{}) if src else {};rev=page.get('revisions',[{}])[0];text=rev.get('slots',{}).get('main',{}).get('content',rev.get('*',''));box=infobox(text);reasons=[]
  if not box:reasons.append('no_own_physical_NP_infobox')
  if not rev.get('revid'):reasons.append('no_pinned_article_revision')
  positional=re.match(r'\{\{НП\+Россия\s*\|([^|=]+)\|([^|=]+)',box,re.I);aname=clean(val(box,'русское название')) or (positional[1].strip() if positional else '');atype=typekey(clean(val(box,'статус')) or (positional[2].strip() if positional else ''));areg=regionkey(clean(val(box,'регион')));adistrict=county(clean(val(box,'район')));ap=clean(val(box,'поселение'));st=typekey(z['settlement_type']);sn=namekey(z['settlement_name']);same_name=sn==namekey(aname);same_type=(st==atype or st=='населенный пункт' and atype in ['поселок','деревня','село','хутор','станция','железнодорожный объект'] or st=='поселок' and atype in ['станция','железнодорожный объект'] and 'станц' in normalize(z['settlement_name']) or st=='станция' and atype=='железнодорожный объект')
  qid=page.get('pageprops',{}).get('wikibase_item','');exactwiki=[q for q in wiki.get(sid,[]) if q['wikidata_qid']==qid and fullcode(q['source_oktmo_exact_digits'])==owncode];articlecodes=[re.sub(r'\D','',val(box,key)) for key in ['цифровой идентификатор','цифровой идентификатор 2']];ownarticlecode=owncode in articlecodes;liveentity=entities.get(qid,{});livecodes=[str(q.get('mainsnak',{}).get('datavalue',{}).get('value','')) for q in liveentity.get('entity',{}).get('claims',{}).get('P764',[]) if q.get('rank')!='deprecated'];liveowncode=owncode in livecodes;directowncode=bool(exactwiki or ownarticlecode or liveowncode);physicaltypes={'деревня','село','поселок','хутор','станица','станция','железнодорожный объект','населенный пункт','разъезд','слобода'};subtype_difference_with_direct_owncode=bool(not same_type and directowncode and st in physicaltypes and atype in physicaltypes and len(rawcodes[owncode])==1);same_type=same_type or subtype_difference_with_direct_owncode
  if not same_name and not directowncode:reasons.append('no_exact_closed_lexical_own_name_or_direct_owncode_binding')
  if not same_type:reasons.append('article_physical_subtype_does_not_match_native_NP')
  article_region_variants={regionkey(clean(val(box,k))) for k in ['регион','регион в таблице']};
  if regionkey(own['region']) not in article_region_variants:reasons.append('article_native_region_not_exact')
  article_county_variants={county(clean(val(box,k))) for k in ['район','район в таблице']};nativecounty=county(own['mun_upper']);membership=re.search(r'(?:муниципальн(?:ое|ого|ом)\s+образован(?:ие|ия|ии)|городск(?:ой|ого|ом)\s+округ(?:а|е)?)\s*(?:город[а]?\s+)?(?:\[\[)?'+re.escape(nativecounty)+r'\b',normalize(text),re.I) if nativecounty else None;
  if nativecounty not in article_county_variants and not membership:reasons.append('article_native_county_not_exact')
  rivals=[x for x in rawid[(sn,st,regionkey(own['region']),county(own['mun_upper']))] if x!=rn]
  ap=re.sub(r'\([^)]*(?:\)|$)',' ',ap).strip();parent=bare(re.sub(r'\b(?:сельское поселение|сельсовет|сельский совет|муниципальное образование)\b',' ',normalize(own['mun_lower'])));aparent=bare(re.sub(r'\b(?:сельское поселение|сельсовет|сельский совет|муниципальное образование)\b',' ',normalize(ap)));ownparish=bool(ap and parent and parent==aparent and parent!=county(own['mun_upper']));rivalcodes={fullcode(raw.loc[x]['oktmo']) for x in rivals};article_rivalcode=[k for k in articlecodes if k in rivalcodes]
  if article_rivalcode:reasons.append('article_literal_code_binds_other_native_samecounty_NP')
  source_rail_role=bool(re.search(r'(?:поселок|посёлок)\s+(?:при\s+)?(?:железнодорожн(?:ой|ого)\s+)?(?:станци[яи]|разъезд[а]?)\b',normalize(own['object_name'])));article_rail_role=bare(clean(val(box,'статус'))) in ['поселок при станции','поселок станции','поселок железнодорожной станции','поселок железнодорожного разъезда'];rival_rail_role=any(re.search(r'(?:поселок|посёлок)\s+(?:при\s+)?(?:железнодорожн(?:ой|ого)\s+)?(?:станци[яи]|разъезд[а]?)\b',normalize(raw.loc[x]['object_name'])) for x in rivals);unique_explicit_rail_NP_role=bool(source_rail_role and article_rail_role and not rival_rail_role)
  if rivals and not directowncode and not ownparish and not unique_explicit_rail_NP_role:reasons.append('samecounty_native_homonym_without_owncode_or_specific_ownparish')
  coords={};literal={}
  for axis in ['lat','lon']:
   parts=[]
   for part in ['deg','min','sec']:
    x=val(box,axis+'_'+part);literal[axis+'_'+part]=x
    try:parts.append(float(x.replace(',','.')) if x else 0)
    except ValueError:parts.append(float('nan'))
   direction=val(box,axis+'_dir');literal[axis+'_dir']=direction;coords[axis]=parts[0]+parts[1]/60+parts[2]/3600
   if direction.upper() in ['W','S','З','Ю']:coords[axis]=-abs(coords[axis])
  lat,lon=coords['lat'],coords['lon'];origin=src.get('origin_file','') if src else '';origin_locator=f"pageid={page.get('pageid')};revisionid={rev.get('revid')};slots.main.content;ownNP_infobox_latlon";pointkind='own_physicalNP_article_revision_infobox';provider_binding=False
  if not (41<=lat<=82 and -180<=lon<=180) and not reasons and liveentity:
   pointclaims=[q for q in liveentity.get('entity',{}).get('claims',{}).get('P625',[]) if q.get('rank')!='deprecated'];values=[]
   for q in pointclaims:
    dv=q.get('mainsnak',{}).get('datavalue',{}).get('value',{})
    if isinstance(dv,dict) and dv.get('globe','').endswith('/Q2') and 41<=float(dv.get('latitude',0))<=82 and -180<=float(dv.get('longitude',999))<=180:values.append((q,dv))
   uniquevalues={(float(v['latitude']),float(v['longitude'])) for q,v in values}
   if len(uniquevalues)==1:
    lat,lon=next(iter(uniquevalues));origin=liveentity['origin_file'];origin_locator=liveentity['origin_locator']+'.claims.P625;single_non_deprecated_Earth_own_article_QID_coordinate';pointkind='proper_physical_ownNP_article_identity_supported_single_ownQID_P625_point';literal={'own_article_QID':qid,'P625_claims':pointclaims}
   elif len(uniquevalues)>1:reasons.append('multiple_ownQID_P625_without_independent_physical_point_selection_witness')
  if not (41<=lat<=82 and -180<=lon<=180) or not val(box,'lat_deg') and pointkind=='own_physicalNP_article_revision_infobox':reasons.append('no_single_valid_own_infobox_latlon')
  row={**z,'candidate_article_title':title,'canonical_article_title':page.get('title',''),'article_pageid':page.get('pageid'),'article_revision_id':rev.get('revid'),'article_revision_timestamp':rev.get('timestamp'),'article_own_name':aname,'article_own_type':atype,'article_own_region':areg,'article_own_county':adistrict,'article_county_variants_json':json.dumps(sorted(article_county_variants),ensure_ascii=False),'article_explicit_current_municipal_membership_excerpt':membership[0] if membership else '','article_own_parish':ap,'exact_reopened_cached_P764_binding':bool(exactwiki),'live_own_article_QID':qid,'live_own_QID_full_native_P764_binding':liveowncode,'live_own_QID_P764_claims_json':json.dumps(liveentity.get('entity',{}).get('claims',{}).get('P764',[]),ensure_ascii=False),'live_own_QID_source_file':liveentity.get('origin_file',''),'live_own_QID_source_sha256':liveentity.get('origin_sha256',''),'live_own_QID_source_locator':liveentity.get('origin_locator',''),'physical_subtype_difference_accepted_only_by_direct_own_fullcode_unique_native_code':subtype_difference_with_direct_owncode,'literal_own_fullcode_in_infobox':ownarticlecode,'specific_own_printed_parish_match':ownparish,'unique_native_and_published_physical_rail_NP_role_disambiguates_plain_samecounty_namesake':unique_explicit_rail_NP_role,'rival_native_row_numbers_json':json.dumps(rivals),'rival_native_full_codes_json':json.dumps(sorted(rivalcodes)),'native_primary_row_json':json.dumps(own,ensure_ascii=False,default=str),'coordinate_literal_json':json.dumps(literal,ensure_ascii=False),'latitude':lat,'longitude':lon,'article_own_infobox_excerpt':box,'article_own_lead_geography_excerpt':text[text.find("'''"):text.find('== История ==') if '== История ==' in text else min(len(text),text.find("'''")+2500)],'point_origin_file':origin,'point_origin_sha256':sha(Path(origin)) if origin else '','point_origin_locator':origin_locator,'point_origin_kind':pointkind,'article_identity_source_file':src.get('origin_file','') if src else '', 'article_identity_source_sha256':sha(Path(src['origin_file'])) if src and src.get('origin_file') else '','hold_reasons':';'.join(reasons),'external_provider_ID_binding_asserted':provider_binding}
  if src and src.get('origin_file'):pins[src['origin_file']]=row['article_identity_source_sha256']
  if liveentity:pins[liveentity['origin_file']]=liveentity['origin_sha256']
  candidates.append(row)
  if reasons:holds.append(row)
  else:positive.append(row)
 # One proper named object must be uniquely bound, not first hit or first coordinate.
 unique={(z['article_pageid'],z['latitude'],z['longitude']):z for z in positive}
 strongest={k:v for k,v in unique.items() if v['exact_reopened_cached_P764_binding'] or v['live_own_QID_full_native_P764_binding'] or v['literal_own_fullcode_in_infobox']}
 if not strongest:strongest={k:v for k,v in unique.items() if v['specific_own_printed_parish_match'] or v['unique_native_and_published_physical_rail_NP_role_disambiguates_plain_samecounty_namesake']}
 if strongest and len(strongest)==1:
  selected=next(iter(strongest.values()));selected['article_alternative_selection_proof']='one physical ownNP article has explicit native fullcode or native specific parish; weaker county-only alternatives retained as holds';accepted.append(selected)
  for k,v in unique.items():
   if k not in strongest:holds.append({**v,'hold_reasons':'weaker_generic_county_article_alternative_explicit_own_native_code_or_parish_binds_another_article'})
 elif len(unique)==1:accepted.append(next(iter(unique.values())))
 elif unique:
  for z in unique.values():holds.append({**z,'hold_reasons':'multiple_positive_own_physical_NP_article_alternatives'})
for n,d in [('source_positive_article_ownpoint_candidates',accepted),('all_article_binding_checks',candidates),('article_binding_holds',holds)]:pd.DataFrame(d).to_csv(O/(n+'.csv.gz'),index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
r={'status':'source-positive candidates pending actualStage63 component and point-occupation screen for future64','positive100_targets':len(f),'reviewed_source_target_article_pairs':len(candidates),'source_positive_current_ownpoint_candidates':len(accepted),'known_population2021_candidates':sum(float(z['population']) for z in accepted),'proper_source_observations_unchanged':True,'provider_identifier_binding_asserted_candidates':sum(bool(z.get('external_provider_ID_binding_asserted',False)) for z in accepted),'independent_article_points_without_provider_ID_binding':sum(not bool(z.get('external_provider_ID_binding_asserted',False)) for z in accepted),'input_pins':pins};(O/'article_source_review_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k!='input_pins'},ensure_ascii=False))
