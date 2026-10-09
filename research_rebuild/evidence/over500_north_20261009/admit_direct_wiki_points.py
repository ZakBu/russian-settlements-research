from pathlib import Path
import pandas as pd,sys,json,gzip,re,hashlib,collections
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;A=R/'research_rebuild/evidence/over500_north_wiki_sources_20261009';sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from apply_unique_county_name_bridge_20261007 import county_key
from current_chain_state_20261007 import normalize
sha=lambda q:hashlib.sha256(Path(q).read_bytes()).hexdigest()
f=pd.read_parquet('/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet').fillna('');b=f.set_index('source_record_id');w=pd.read_csv(O/'direct_native_witnesses.csv.gz').fillna('').set_index('source_record_id').to_dict('index');context=pd.read_csv(O/'native_county_context.csv').fillna('').set_index('source_record_id').to_dict('index');cand=pd.concat([pd.read_csv(A/'cached_own_article_coordinate_candidates.csv.gz').fillna(''),pd.read_csv(A/'article_coordinate_candidates.csv.gz').fillna('')]).fillna('');books={};points=[];review=[];pins={str(q):sha(q) for q in [A/'cached_own_article_coordinate_candidates.csv.gz',A/'article_coordinate_candidates.csv.gz',O/'direct_native_witnesses.csv.gz',O/'direct_native_witnesses_manifest.json',O/'native_county_context.csv',Path('/dev/shm/settlements-stage71-20261009/applied_state_observations.parquet')]};existing=set(pd.read_csv(O/'accepted_point_use_delta.csv').target_source_record_id);admitted=set();ownpages=[]
aliases={'Гравийного карьера':'гравийный карьер','Газопровода':'газопровод','Санатория "Воробьево"':'санаторий воробьево','центрального отделения совхоза "Заря"':'заря','Центральной Усадьбы совхоза им. Ленина':'совхоз им ленина','железнодорожнойстанции Скалино':'скалино'}
def clean(x):return re.sub(r'[^а-я0-9 ]','',normalize(x)).strip()
def field(txt,key):
 z=re.search(r'\|\s*'+key+r'\s*=\s*([^\n|]+)',txt,re.I);v=z.group(1).strip() if z else '';return re.sub(r'\[\[([^]|]+)\|[^]]+\]\]',r'\1',v).replace('[[','').replace(']]','').strip()
def county(sid):return county_key(b.loc[sid,'district_raw']) or context.get(sid,{}).get('county','')
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
 ownname=field(txt,'русское название') or str(z['article_title']).split(' (')[0];owntype=clean(field(txt,'статус'));articlecounty=county_key(re.sub(r'\([^)]*\)','',field(txt,'район')));ck=county(sid);expected=aliases.get(b.loc[sid,'settlement_name'],clean(b.loc[sid,'settlement_name']))
 if isinstance(expected,str):expected=clean(expected)
 if clean(ownname)!=expected:reason.append('own article name does not bind exact native or explicit compound designator')
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
  if b.loc[sid,'settlement_name']=='Козловка' and ck=='рославльский' and native_type=='поселок' and 'Статус деревни с 28 декабря 2004 года (до этого была посёлком)' in txt and 'Остер' in nw.get('primary_native_parent_header',''):exception='Own article explicit dated 28 December 2004 settlement-type change; 2002 own poselok contrasted with separate old samecounty village.'
  elif b.loc[sid,'settlement_name'] in ['Санатория "Воробьево"','Центральной Усадьбы совхоза им. Ленина']:exception='Distinct compound named estate/sanatorium locality; point-only historical own physical reference. Printed type variant retained and no legal type-change date or ordinary identity edge asserted.'
  else:reason.append('article own type differs without explicit typed binding')
 # Competitor screen includes all native types; dated previous-type witness can separate old poselok from old village.
 native_name=b.loc[sid,'name_norm'];pool=f[(f.census_year==b.loc[sid,'census_year'])&(f.region_norm==b.loc[sid,'region_norm'])&(f.name_norm==native_name)];rivals=[]
 for rr in pool.itertuples():
  if rr.source_record_id==sid:continue
  rc=county(rr.source_record_id)
  if ck and rc and rc!=ck:continue
  if exception.startswith('Own article explicit dated') and rr.type_norm!=b.loc[sid,'type_norm']:continue
  rivals.append(rr.source_record_id)
 if rivals:reason.append('unresolved native same-year alltype namesake county rivals')
 # Require source code independently printed in the page for compound labels with type change.
 owncodes=re.findall(r'\b\d{8,11}\b',txt);codes=[x for x in owncodes if len(x)==11];cur=f[(f.census_year==2021)&(f.region_norm==b.loc[sid,'region_norm'])&f.oktmo.astype(str).isin(codes)]
 if b.loc[sid,'settlement_name'] in ['Санатория "Воробьево"','Центральной Усадьбы совхоза им. Ленина'] and len(cur)!=1:reason.append('distinct compound locality lacks own printed full code bound to unique native2021 locality')
 if b.loc[sid,'settlement_name']=='центрального отделения совхоза "Заря"' and not ('Горностаевский' in nw.get('primary_native_parent_header','') and 'Горностаевское' in txt and 'поселок совхоза «Заря» переименован в посёлок Заря' in txt):reason.append('compound estate alias lacks independent native parish and explicit own article name history')
 review.append({**z,'article_own_name':ownname,'article_own_type':owntype,'article_own_county':articlecounty,'bound_native_county':ck,'native_rivals_json':json.dumps(rivals),'native_own_code2021_bound_ids_json':json.dumps(cur.source_record_id.tolist()),'typed_point_binding_note':exception,'disposition':'hold:'+ ';'.join(reason) if reason else 'accepted_own_point_only'})
 if reason:continue
 # Freeze exact accepted own page as included source evidence, preserving original cache reference/hash separately.
 ownpages.append({'source_record_id':sid,'original_capture':z['capture'],'original_capture_sha256':pins[z['capture']],'page':pp});admitted.add(sid)
 points.append({'target_source_record_id':sid,'latitude':float(z['latitude']),'longitude':float(z['longitude']),'coordinate_admission_status':'reviewed_extension_rule_accepted','decision_status':'checked_rule_accepted','admission_allowed':True,'own_locality_point':True,'recipient_point_assigned_to_child':False,'coordinate_source_record_id':sid,'source_sha256':nw.get('source_sha256',''),'source_locator':f"{nw.get('source_sheet','')}:{nw.get('source_row','')}",'point_origin_file':z['capture'],'point_origin_sha256':pins[z['capture']],'point_origin_locator':z['source_locator'],'point_origin_kind':'independently_bound_own_locality_Wikipedia_coordinate','point_source_qid':z.get('cached_qid') or z.get('qid',''),'point_source_revision':z['revid'],'admission_rule':'Reopened original native own locality leaf label/count; exact own article name or explicit compound grammatical designator; independent own county; alltype native namesakes screened. Own article physical coordinate reused as retrospective representative, not a censusday measurement. '+exception,'point_temporal_interpretation':'Explicit retrospective own physical representative point continuity inference; historical censusday measurement and population boundary equivalence unknown. Point only, no new identity or population claim.','historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False,'new_identity_edges':0,'native_population_quality_preserved':True,'typed_binding_note':exception})
pd.DataFrame(points,columns=None if points else ['target_source_record_id','latitude','longitude','coordinate_admission_status']).to_csv(O/'supplemental_accepted_point_use_delta.csv',index=False);pd.DataFrame(review).to_csv(O/'supplemental_point_review.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'accepted_direct_own_article_inclusions.json.gz').write_bytes(gzip.compress(json.dumps(ownpages,ensure_ascii=False).encode(),mtime=0));manifest={'status':'accepted_point_only_packet_for_root_replay','accepted_ownpoint_UIds':len(points),'source_bindings_reviewed':len(review),'native_counts_quality_unchanged':True,'new_temporal_edges':0,'input_pins':pins,'output_pins':{str(q):sha(q) for q in [O/'supplemental_accepted_point_use_delta.csv',O/'supplemental_point_review.csv.gz',O/'accepted_direct_own_article_inclusions.json.gz']}};(O/'supplemental_point_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print('accepted',len(points),'reviewed',len(review));print([(b.loc[x['target_source_record_id'],'settlement_name'],b.loc[x['target_source_record_id'],'region_norm']) for x in points])
