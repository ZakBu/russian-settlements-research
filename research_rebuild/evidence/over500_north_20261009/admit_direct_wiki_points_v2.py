from pathlib import Path
import pandas as pd,sys,json,gzip,re,hashlib,collections
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;A=R/'research_rebuild/evidence/over500_north_wiki_sources_20261009';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from apply_unique_county_name_bridge_20261007 import county_key
from current_chain_state_20261007 import normalize
sha=lambda q:hashlib.sha256(Path(q).read_bytes()).hexdigest()
f=pd.read_parquet('/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet').fillna('');b=f.set_index('source_record_id');w=pd.read_csv(O/'direct_native_witnesses.csv.gz').fillna('').set_index('source_record_id').to_dict('index');context=pd.read_csv(O/'native_county_context.csv').fillna('').set_index('source_record_id').to_dict('index');cand=pd.concat([pd.read_csv(A/'cached_own_article_coordinate_candidates.csv.gz').fillna(''),pd.read_csv(A/'article_coordinate_candidates.csv.gz').fillna('')]).fillna('');books={};points=[];review=[];pins={str(q):sha(q) for q in [A/'cached_own_article_coordinate_candidates.csv.gz',A/'article_coordinate_candidates.csv.gz',O/'direct_native_witnesses.csv.gz',O/'direct_native_witnesses_manifest.json',O/'native_county_context.csv',Path('/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet')]};extra_native=R/'research_rebuild/evidence/over500_north_supplemental_native_20261009/recovered_direct_native_witnesses.csv';w.update(pd.read_csv(extra_native).fillna('').set_index('source_record_id').to_dict('index'));pins[str(extra_native)]=sha(extra_native);
extra_file=A/'additional_two_estate_candidates_v2.csv.gz';extra=pd.read_csv(extra_file).fillna(''); extra['source_record_id']=extra.article_title.map({'Совхоз «Чаусово»':'2002:006_1916564aaa_02c_Kaluzhskaja.xls:Sheet1:1036','Совхоз имени Ленина (Калужская область)':'2002:006_1916564aaa_02c_Kaluzhskaja.xls:Sheet1:652'});extra['source_locator']=extra.apply(lambda x:f"pageid={x.pageid};revid={x.revid};own infobox lat_deg/lon_deg",axis=1);cand=pd.concat([cand,extra]).fillna('');pins[str(extra_file)]=sha(extra_file);
existing=set(pd.read_csv(O/'accepted_point_use_delta.csv').target_source_record_id)|set(pd.read_csv(O/'supplemental_accepted_point_use_delta.csv').target_source_record_id);admitted=set();ownpages=[]
aliases={'Гравийного карьера':'гравийный карьер','Газопровода':'газопровод','Санатория "Воробьево"':'санаторий воробьево','центрального отделения совхоза "Заря"':'заря','Центральной Усадьбы совхоза им. Ленина':'совхоз имени ленина','Чаусово':'совхоз чаусово','железнодорожнойстанции Скалино':'скалино','населенный пункт лесной поселок ивакша':'ивакша','населенный пункт лесной поселок лепша новый':'лепша новый'}
def clean(x):return re.sub(r'[^а-я0-9 ]','',normalize(x)).strip()
def field(txt,key):
 z=re.search(r'\|\s*'+key+r'\s*=\s*([^\n|]+)',txt,re.I);v=z.group(1).strip() if z else '';return re.sub(r'\[\[([^]|]+)\|[^]]+\]\]',r'\1',v).replace('[[','').replace(']]','').strip()
def county(sid):return county_key(b.loc[sid,'district_raw']) or county_key(w.get(sid,{}).get('actual_printed_county','')) or context.get(sid,{}).get('county','')
def page(z):
 q=Path(z['capture']);pins[str(q)]=pins.get(str(q)) or sha(q)
 if str(q) not in books:books[str(q)]=json.loads(gzip.decompress(q.read_bytes()))
 blob=books[str(q)];pages=blob.get('payload',blob).get('query',{}).get('pages',[])
 if not pages:pages=blob.get('page_response',{}).get('query',{}).get('pages',[])
 if isinstance(pages,dict):pages=list(pages.values())
 pp=next((p for p in pages if str(p.get('pageid'))==str(z['pageid']) or p.get('title')==z['article_title']),None)
 if not pp:return None,''
 rev=pp.get('revisions',[{}])[0];return pp,rev.get('slots',{}).get('main',{}).get('content',rev.get('*',''))
for z in cand.to_dict('records'):
 sid=z['source_record_id']
 if sid in admitted or sid in existing or sid not in w:continue
 nw=w[sid];reason=[];pp,txt=page(z)
 if not txt:continue
 positional=re.search(r'\{\{НП\+Россия\s*\|([^|\n=]+)\|([^|\n=]+)',txt,re.I);ownname=field(txt,'русское название') or (positional.group(1).strip() if positional else str(z['article_title']).split(' (')[0]);owntype=clean(field(txt,'статус') or (positional.group(2).strip() if positional else ''));articlecounty=county_key(re.sub(r'\([^)]*\)','',field(txt,'район')));ck=county(sid);expected=aliases.get(b.loc[sid,'settlement_name'],clean(b.loc[sid,'settlement_name']))
 if isinstance(expected,str):expected=clean(expected)
 if clean(ownname)!=expected and not (sid.startswith('ARK2010:') and 'лесной поселок' in b.loc[sid,'name_norm'] and clean(ownname)==clean(b.loc[sid,'name_norm']).removeprefix('населенный пункт ')):reason.append('own article name does not bind exact native or explicit compound designator')
 if clean(b.loc[sid,'region_norm']) not in clean(field(txt,'регион')):reason.append('own article region field does not bind native region')
 if ck and ck!=articlecounty:reason.append('native own county not independently equal own article county')
 if not ck:
  # Source-positive literal whole-region uniqueness fallback: all native types, both sourceyear and currentyear, no county assumption.
  ownr=f[(f.region_norm==b.loc[sid,'region_norm']) & (f.name_norm==b.loc[sid,'name_norm'])]
  source_r=ownr[ownr.census_year==b.loc[sid,'census_year']]
  current_r=ownr[ownr.census_year==2021]
  if len(source_r)!=1 or len(current_r)!=1:reason.append('missingcounty and literal whole-region ownname not unique in sourceyear/currentyear')
  if len(current_r)==1 and clean(current_r.iloc[0].type_norm)!=clean(b.loc[sid,'type_norm']):reason.append('missingcounty current own printedtype differs')
 if not nw['literal_label_population_passed']:reason.append('original own native label/count not passed')
 native_type=clean(b.loc[sid,'type_norm']);exception=''
 if owntype.startswith(native_type+' ') and native_type in ['поселок','деревня','село','станция']:owntype=native_type
 if native_type!=owntype:
  if sid.startswith('ARK2010:') and clean(nw.get('raw_source_type',''))==owntype:exception='Actual original native source type matches own article; selected imported type discrepancy explicitly retained. Point-only geometry, no type repair or ordinary edge.'
  elif sid.startswith('ARK2010:') and 'лесной поселок' in b.loc[sid,'name_norm'] and ('лесной поселок' in clean(owntype) or 'лесной поселок' in clean(txt[:2000])):exception='Actual original native full label explicitly named forest settlement; article same own forest place distinguished from plain village by subtype. Selected blank type retained, point only.'
  elif b.loc[sid,'settlement_name']=='Козловка' and ck=='рославльский' and native_type=='поселок' and 'Статус деревни с 28 декабря 2004 года (до этого была посёлком)' in txt and 'Остер' in nw.get('primary_native_parent_header',''):exception='Own article explicit dated 28 December 2004 settlement-type change; 2002 own poselok contrasted with separate old samecounty village.'
  elif b.loc[sid,'settlement_name']=='Чаусово' and owntype=='село' and 'официально признана отдельным населенным пунктом' in txt and 'деревня [[Чаусово' in txt:exception='Historical own non-village Chausovo locality distinct from separately printed village; own modern named farm centre explicitly distinguishes neighboring separate village. Printed historical type retained; own representative point only, no ordinary identity edge.'
  elif b.loc[sid,'settlement_name'] in ['Санатория "Воробьево"','Центральной Усадьбы совхоза им. Ленина']:exception='Distinct compound named estate/sanatorium locality; point-only historical own physical reference. Printed type variant retained and no legal type-change date or ordinary identity edge asserted.'
  else:reason.append('article own type differs without explicit typed binding')
 # Competitor screen includes all native types; dated previous-type witness can separate old poselok from old village.
 native_name=b.loc[sid,'name_norm'];pool=f[(f.census_year==b.loc[sid,'census_year'])&(f.region_norm==b.loc[sid,'region_norm'])&(f.name_norm==native_name)];rivals=[]
 for rr in pool.itertuples():
  if rr.source_record_id==sid:continue
  rc=county(rr.source_record_id)
  if ck and rc and rc!=ck:continue
  if (exception.startswith('Own article explicit dated') or exception.startswith('Historical own non-village')) and rr.type_norm!=b.loc[sid,'type_norm']:continue
  rivals.append(rr.source_record_id)
 if rivals:reason.append('unresolved native same-year alltype namesake county rivals')
 # Require source code independently printed in the page for compound labels with type change.
 owncodes=re.findall(r'\b\d{8,11}\b',txt);codes=[x for x in owncodes if len(x)==11];cur=f[(f.census_year==2021)&(f.region_norm==b.loc[sid,'region_norm'])&f.oktmo.astype(str).isin(codes)]
 if b.loc[sid,'settlement_name'] in ['Чаусово','Центральной Усадьбы совхоза им. Ленина']:
  pubname=clean(ownname).replace('имени','им')
  cur=f[(f.census_year==2021)&(f.region_norm==b.loc[sid,'region_norm'])&f.settlement_name.map(lambda x:clean(x).replace('имени','им')).eq(pubname)&f.district_raw.map(county_key).eq(ck)]
  if len(cur)!=1 or clean(cur.iloc[0].type_norm)!=owntype:reason.append('own modern compound locality does not bind unique literal owncoded native2021 leaf')
 if b.loc[sid,'settlement_name']=='Санатория "Воробьево"' and len(cur)!=1:reason.append('distinct compound locality lacks own printed full code bound to unique native2021 locality')
 if b.loc[sid,'settlement_name']=='центрального отделения совхоза "Заря"' and not ('Горностаевский' in nw.get('primary_native_parent_header','') and 'Горностаевское' in txt and 'поселок совхоза «Заря» переименован в посёлок Заря' in txt):reason.append('compound estate alias lacks independent native parish and explicit own article name history')
 review.append({**z,'article_own_name':ownname,'article_own_type':owntype,'article_own_county':articlecounty,'bound_native_county':ck,'native_rivals_json':json.dumps(rivals),'native_own_code2021_bound_ids_json':json.dumps(cur.source_record_id.tolist()),'typed_point_binding_note':exception,'disposition':'hold:'+ ';'.join(reason) if reason else 'accepted_own_point_only'})
 if reason:continue
 # Freeze exact accepted own page as included source evidence, preserving original cache reference/hash separately.
 ownpages.append({'source_record_id':sid,'original_capture':z['capture'],'original_capture_sha256':pins[z['capture']],'page':pp});admitted.add(sid)
 points.append({'target_source_record_id':sid,'latitude':float(z['latitude']),'longitude':float(z['longitude']),'coordinate_admission_status':'reviewed_extension_rule_accepted','decision_status':'checked_rule_accepted','admission_allowed':True,'own_locality_point':True,'recipient_point_assigned_to_child':False,'coordinate_source_record_id':sid,'source_sha256':nw.get('source_sha256',''),'source_locator':f"{nw.get('source_sheet','')}:{nw.get('source_row','')}",'point_origin_file':z['capture'],'point_origin_sha256':pins[z['capture']],'point_origin_locator':z['source_locator'],'point_origin_kind':'independently_bound_own_locality_Wikipedia_coordinate','point_source_qid':z.get('cached_qid') or z.get('qid',''),'point_source_revision':z['revid'],'admission_rule':'Reopened original native own locality leaf label/count; exact own article name or explicit compound grammatical designator; independent own county; alltype native namesakes screened. Own article physical coordinate reused as retrospective representative, not a censusday measurement. '+exception,'point_temporal_interpretation':'Explicit retrospective own physical representative point continuity inference; historical censusday measurement and population boundary equivalence unknown. Point only, no new identity or population claim.','historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False,'new_identity_edges':0,'native_population_quality_preserved':True,'typed_binding_note':exception})
pd.DataFrame(points,columns=None if points else ['target_source_record_id','latitude','longitude','coordinate_admission_status']).to_csv(O/'supplemental_accepted_point_use_delta_v2.csv',index=False);pd.DataFrame(review).to_csv(O/'supplemental_point_review_v2.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'accepted_direct_own_article_inclusions_v2.json.gz').write_bytes(gzip.compress(json.dumps(ownpages,ensure_ascii=False).encode(),mtime=0));manifest={'status':'accepted_point_only_packet_for_root_replay','accepted_ownpoint_UIds':len(points),'source_bindings_reviewed':len(review),'native_counts_quality_unchanged':True,'new_temporal_edges':0,'input_pins':pins,'output_pins':{str(q):sha(q) for q in [O/'supplemental_accepted_point_use_delta_v2.csv',O/'supplemental_point_review_v2.csv.gz',O/'accepted_direct_own_article_inclusions_v2.json.gz']}};(O/'supplemental_point_manifest_v2.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print('accepted',len(points),'reviewed',len(review));print([(b.loc[x['target_source_record_id'],'settlement_name'],b.loc[x['target_source_record_id'],'region_norm']) for x in points])
