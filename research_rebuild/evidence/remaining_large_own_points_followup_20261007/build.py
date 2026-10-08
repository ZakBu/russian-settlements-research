from pathlib import Path
import sys,json,gzip,re,hashlib,time,urllib.request,urllib.parse,collections
import pandas as pd,duckdb
T=time.monotonic();R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
s=load(20); targets=pd.read_csv(O/'targets.csv').fillna('');maps={67678:'Q16023150',70723:'Q4243179',81604:'Q20924591',68242:'Q18790401',160648:'Q15253843',70121:'Q4507878',98451:'Q28526968',152489:'Q23976550',19954:'Q13667316',96167:'Q28528064',159976:'Q19643969',97849:'Q4337314',75823:'Q4374553',161028:'Q19973474',33099:'Q112983091',71273:'Q4458188',152605:'Q4078611',97024:'Q109075842',152483:'Q23976566',98952:'Q4229245',65263:'Q37959115',41174:'Q953712'}
# Current Sibirsky already point-admitted; only actual historic population evidence added.
targets=pd.concat([targets,s.by_id.loc[['2021:data_allsettlements_anon_156_v20251217.parquet:parquet:41174']]],ignore_index=True)
entities={};pages={};orig={};pins={str(p):sha(p) for p in s.inputs}
for fn in ['entities.json.gz','additional_entities.json.gz']:
 p=O/fn;a=json.loads(gzip.open(p,'rt').read());entities.update(a['entities']);pins[str(p)]=sha(p)
 for q in a['entities']:orig[q]=str(p)
for fn in ['own_pages.json.gz','additional_pages.json.gz']:
 p=O/fn; pins[str(p)]=sha(p)
 for a in json.loads(gzip.open(p,'rt').read())['query']['pages'].values():
  if a.get('pageprops',{}).get('wikibase_item'):pages[a['pageprops']['wikibase_item']]=(a,str(p))
val=lambda sn:sn.get('datavalue',{}).get('value');refs=json.loads(gzip.open(R/'research_rebuild/work/current_unpointed_own_wiki_mass_batch_20261007/reference_entities.json.gz','rt').read());need=set()
for e in entities.values():
 for st in e.get('claims',{}).get('P1082',[]):
  for ref in st.get('references',[]):
   for sn in ref.get('snaks',{}).get('P248',[]):
    v=val(sn)
    if isinstance(v,dict) and v.get('id') not in refs:need.add(v['id'])
if need:
 u='https://www.wikidata.org/w/api.php?'+urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(sorted(need)),'props':'labels','languages':'ru|en','format':'json'})
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0'}),timeout=20).read(700000);(O/'references.json.gz').write_bytes(gzip.compress(b))
  for q,e in json.loads(b).get('entities',{}).items():refs[q]=e.get('labels',{}).get('ru',e.get('labels',{}).get('en',{})).get('value','')
 except Exception as ex:print('referencefetch hold',ex)
points=[];series=[];invent=[];checks=[];holds=[];claims=[];c=duckdb.connect();rawp=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');pins[str(rawp)]=sha(rawp)
for t in targets.to_dict('records'):
 sid=t['source_record_id'];row=int(sid.rsplit(':',1)[-1]);q=maps.get(row)
 if q not in entities or q not in pages:continue
 e=entities[q];cs=e.get('claims',{});page,wp=pages[q];text=page.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('*','');fields={normalize(k):v.strip() for k,v in re.findall(r'\|\s*([^=|\n]+)=([^|\n]*)',text)}
 raw=c.execute('SELECT object_level,settlement,mun_upper,population,oktmo,okato_dadata,latitude_dadata,longitude_dadata FROM read_parquet(?) LIMIT1 OFFSET '+str(row-1),[str(rawp)]).fetchdf().iloc[0].to_dict() if False else c.execute('SELECT object_level,settlement,mun_upper,population,oktmo,okato_dadata,latitude_dadata,longitude_dadata FROM read_parquet(?) LIMIT 1 OFFSET '+str(row-1),[str(rawp)]).fetchdf().iloc[0].to_dict()
 desc=e.get('descriptions',{}).get('ru',{}).get('value','');kind=fields.get('статус','');county=fields.get('район','');typephysical=any(z in normalize(kind) for z in ['поселок','деревня','село','хутор','населенный пункт','станц']) or '{{НП+Россия' in text
 def dms(prefix):
  try:return float(fields[prefix+'_deg'])+float(fields.get(prefix+'_min',0))/60+float(fields.get(prefix+'_sec',0))/3600
  except (ValueError,KeyError):return None
 lat,lon=dms('lat'),dms('lon');pointorigin='own_Wikipedia_infobox_DMS_representative_physical_locality';pointpath=wp;locator='pageid='+str(page.get('pageid'))+';revision='+str(page.get('revisions',[{}])[0].get('revid'))+';lat_deg/min/sec,lon_deg/min/sec'
 if lat is None or lon is None:
  cc=[(val(st.get('mainsnak',{})),st.get('rank')) for st in cs.get('P625',[]) if st.get('rank')!='deprecated'];cc=[a for a in cc if isinstance(a[0],dict) and 'latitude'in a[0]];pref=[a for a in cc if a[1]=='preferred'];cc=pref or cc
  if len(cc)==1:lat,lon=cc[0][0]['latitude'],cc[0][0]['longitude'];pointorigin='own_Wikidata_P625_unique';pointpath=orig[q];locator='entities.'+q+'.claims.P625'
 # Named administrative source context is explicit; provider location need not agree when known county-centre failure.
 geogtokens={'Q16023150':'красногор','Q4243179':'чехов','Q20924591':'новосибир','Q18790401':'любер','Q15253843':'кунашак','Q4507878':'солнечногор','Q28526968':'нытв','Q23976550':'тула','Q13667316':'вичуг','Q28528064':'карагай','Q19643969':'аргаяш','Q4337314':'березник','Q4374553':'семенов','Q19973474':'соснов','Q112983091':'новокузнец','Q4458188':'кировск','Q4078611':'тула','Q109075842':'кунгур','Q23976566':'тула','Q4229245':'чусов','Q37959115':'ленин','Q953712':'сибирск'};token=geogtokens[q];geogok=token in normalize(county+' '+text[:2800]) and token in normalize(raw['mun_upper']);physical=typephysical and not any(z in normalize(desc) for z in ['сельсовет','муниципальное образование','страница значений','железнодорожная станция в'])
 # Мыза has two same-name whole NPs in Tula: classify only if native own code/article census evidence uniquely chooses one.
 codes=[str(val(st.get('mainsnak',{}))) for prop in ['P764','P635'] for st in cs.get(prop,[])];codeexact=str(raw['oktmo']).zfill(11) in codes or str(t['okato']).zfill(11) in codes
 if q=='Q28528064' and not codeexact:holds.append({'sid':sid,'qid':q,'reason':'two_current_Savino_same_county_type; no_native_FIAS_or_classifier_bridge; count_equality_not_identity_proof'});continue
 if q=='Q23976550' and not codeexact:holds.append({'sid':sid,'qid':q,'reason':'Мыза_multiple_same_name_Tula_NPs_article_binding_needs_explicit_native_code'});continue
 if lat is None or not geogok or not physical:
  holds.append({'sid':sid,'qid':q,'reason':'point_or_named_geography_physical_scope_unresolved','article_county':county,'native_county':raw['mun_upper'],'description':desc});continue
 assert raw['object_level']=='Населенный пункт' and raw['population']==t['population']
 point={'target_source_record_id':sid,'latitude':lat,'longitude':lon,'coordinate_admission_status':'candidate_only_requires_independent_review','coordinate_source_record_id':q,'point_origin_file':pointpath,'point_origin_sha256':sha(Path(pointpath)),'point_origin_locator':locator,'point_origin_kind':pointorigin,'coordinate_binding_rule':'own_exact_named_NP_and_explicit_article_historical_admin_context_to_current_named_county; type_variant_explicit; no_generic_code_truncation','source_name':t['settlement_name'],'source_type':t['settlement_type'],'source_county':raw['mun_upper'],'article_type':kind,'article_county':county,'native_own_code':raw['oktmo'],'entity_codes_json':json.dumps(codes),'code_comparison_status':'exact_own_code' if codeexact else 'different_code_versions_not_equated; own_named_admin_history_only','target_year':2021,'population':t['population'],'bounds':'UNKNOWN','error_rate':'uncalibrated','population_boundary_comparability_asserted':False}
 if sid not in s.point_rows:points.append(point)
 by=collections.defaultdict(list)
 for st in cs.get('P1082',[]):
  amount=val(st.get('mainsnak',{}));
  if not isinstance(amount,dict) or 'amount' not in amount:continue
  for dt in st.get('qualifiers',{}).get('P585',[]):
   d=val(dt)
   if not isinstance(d,dict):continue
   y=int(d.get('time','+0000')[1:5]);
   if y not in [2002,2010,2021]:continue
   rid=[];titles=[]
   for ref in st.get('references',[]):
    for sn in ref.get('snaks',{}).get('P248',[]):
     v=val(sn)
     if isinstance(v,dict):rid.append(v.get('id'))
    for sn in ref.get('snaks',{}).get('P1476',[]):
     v=val(sn)
     if isinstance(v,dict):titles.append(v.get('text',''))
   labels=[refs.get(z,'') for z in rid];reftexts=labels+titles;census=any(('перепис' in z.lower() or 'census'in z.lower() or 'впн-'in z.lower()) and (str(y)in z or y==2021 and '2020'in z) for z in reftexts);dategood=d.get('precision')==9 or d.get('time','')[1:11] in ['2002-10-09','2010-10-14','2021-10-01'];qualified=census and dategood and st.get('rank')!='deprecated';r={'sid':sid,'qid':q,'year':y,'population':float(amount['amount']),'declared_date':d.get('time'),'precision':d.get('precision'),'statement_id':st.get('id'),'reference_ids':';'.join(rid),'reference_labels_json':json.dumps(labels,ensure_ascii=False),'reference_titles_json':json.dumps(titles,ensure_ascii=False),'qualified_explicit_census':qualified,'source_file':orig[q],'source_sha256':sha(Path(orig[q])),'source_locator':'entities.'+q+'.claims.P1082['+st.get('id')+']'};claims.append(r)
   if qualified:by[y].append(r)
 native={2021:s.by_id.loc[sid].to_dict()}
 for y in [2002,2010]:
  old=s.obs[(s.obs.root==s.uf.find(sid))&(s.obs.census_year==y)]
  if len(old)==1:native[y]=old.iloc[0].to_dict()
 # Sibirsky2002 ordinary official urban row is distinct from rural Sibirsky1804; typed ownarticle continuity ties urban12046.
 if q=='Q953712':native[2002]=s.by_id.loc['2002:1_TOM_01_04.xls:0:8457'].to_dict()
 full=all(y in native or by[y] and len({r['population'] for r in by[y]})==1 for y in [2002,2010,2021])
 if full:
  for y in [2002,2010,2021]:
   n=native.get(y)
   r={'trajectory_id':'remaining_large_own:'+q,'year':y,'population_source_value':n['population'] if n else by[y][0]['population'],'source_record_id':n['source_record_id'] if n else '', 'current2021_source_record_id':sid,'settlement_name':t['settlement_name'],'region_norm':t['region_norm'],'county_context':n['district_raw'] if n else county,'latitude':lat,'longitude':lon,'population_quality':n['population_value_quality'] if n else 'secondary_explicit_census_reference','grain':'existing selected settlement observation' if n else 'own physical locality census-reference secondary observation','nonadditive_observation':not bool(n),'source_path':str(Path('/workspace/settlements-raw')/n['source_file']) if n else orig[q],'source_sha256':n['source_sha256'] if n else sha(Path(orig[q])),'source_locator':n['source_record_id'] if n else by[y][0]['source_locator'],'decision_status':'candidate_only_requires_independent_review','ordinary_NP3_asserted':False,'boundary_comparability_asserted':False,'point_binding_json':json.dumps(point,ensure_ascii=False),'point_origin_file':pointpath,'point_origin_sha256':point['point_origin_sha256'],'point_origin_locator':locator,'retrospective_point_use_is_continuity_inference':y!=2021,'scope':'qualified_own_physical_locality_actual_census_history','boundary_comparability':'UNKNOWN','census_reference_witness_json':json.dumps(by[y],ensure_ascii=False)};series.append(r)
 checks.append({'sid':sid,'qid':q,'native_population':raw['population'],'raw_native_name':raw['settlement'],'raw_native_county':raw['mun_upper'],'native_source_sha256':pins[str(rawp)],'native_source_locator':'parquet_row_1based='+str(row),'own_article_title':page['title'],'own_article_revision':page['revisions'][0]['revid'],'article_type':kind,'own_article_county':county,'explicit_geography_token':token,'own_named_geography_matches':geogok,'own_code_exact':codeexact,'own_DMS_or_P625_point':[lat,lon],'own_article_history_excerpt':'\n'.join(l for l in text.splitlines() if re.search('2002|2010|2017|сельск|городск|1994',l))[:1700]})
 invent.append({'sid':sid,'qid':q,'name':t['settlement_name'],'population2021':t['population'],'actual_full3':full,'native_years':';'.join(map(str,native)),'current_point_already_admitted':sid in s.point_rows})
for fn,data in [('candidate_point_uses',points),('candidate_qualified_physical_observations',series),('native_and_own_article_binding_checks',checks),('target_census_claims',claims),('inventory',invent),('holds',holds)]:pd.DataFrame(data).to_csv(O/(fn+'.csv'),index=False)
pins.update({str(p):sha(p) for p in O.glob('*.gz')});(O/'source_manifest.json').write_text(json.dumps(pins,indent=2,ensure_ascii=False));receipt={'stage':20,'current_large_unpointed22_population':50507,'new_point_candidates':len(points),'new_point_candidate_population':sum(p['population'] for p in points),'actual_full3_candidates':sum(t['actual_full3'] for t in invent),'full3_current_population_candidate':sum(t['population2021'] for t in invent if t['actual_full3']),'already_pointed_sibirsky_added_actual_history':any(t['qid']=='Q953712' and t['actual_full3'] for t in invent),'new_admitted_gain':0,'wall_seconds':time.monotonic()-T,'status':'candidate_only_root_review_pending'};(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt));print('holds',holds)
