from pathlib import Path
import pandas as pd,zipfile,json,gzip,hashlib,re,unicodedata,urllib.request,urllib.parse,time,datetime
O=Path(__file__).parent;R=Path('/workspace/russian-settlements-research');N=R/'research_rebuild/evidence/over500_north_20261009';d=pd.read_csv(N/'per_record_dispositions_final.csv',keep_default_na=False);r=d[~d.has_ownpoint & ~d.point_newly_admitted & d.point_disposition.eq('held_no_admitted_ownpoint')].copy();assert len(r)==49
ctx=pd.read_csv(N/'native_county_context.csv',keep_default_na=False).set_index('source_record_id');s=p=R/'research_rebuild/evidence/over500_north_supplemental_native_20261009/recovered_direct_native_witnesses.csv';sup=pd.read_csv(s,keep_default_na=False).set_index('source_record_id');r['query_county']=r.district_raw
for i,x in r.iterrows():
 sid=x.source_record_id
 if sid in sup.index:r.loc[i,'query_county']=sup.loc[sid,'actual_printed_county']
 elif not x.district_raw and sid in ctx.index:r.loc[i,'query_county']=ctx.loc[sid,'county']+' район'
r.to_csv(O/'exact49_targets.csv.gz',index=False,compression={'method':'gzip','mtime':0})
admin={'владимирская':'83','смоленская':'69','тульская':'76','карелия':'28','архангельская':'06','вологодская':'85','калининградская':'23','ленинградская':'42','новгородская':'52','псковская':'60','кировская':'33','нижегородская':'51','рязанская':'62','ярославская':'88','калужская':'25','брянская':'10','тверская':'77'}
tr=dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya']))
def norm(v):
 v=''.join(tr.get(c,c)for c in str(v).lower());v=''.join(c for c in unicodedata.normalize('NFKD',v)if not unicodedata.combining(c));return re.sub('[^a-z0-9]','',v.replace('shch','sch').replace('iy','i').replace('yy','y').replace('j','y'))
alias={'Ефремов 3':['Ефремов-3','Ефремов 3-й'],'Лесной Посёлок Ивакша':['Ивакша'],'населенный пункт лесной поселок лепша новый':['Лепша Новый','Новая Лепша','Лепша'],'Пограничное':['Пограничный'],'ст. Скуратово':['Скуратово'],'Старомочалей':['Старый Мочалей'],'совхоза Чкаловский':['Чкаловский'],'Истьинское Отделение':['Истьинское отделение','Истьино'],'Кулицкая':['Кулицкая','Кулицкая станция']}
target={}
for x in r.to_dict('records'):
 for n in [x['settlement_name']]+alias.get(x['settlement_name'],[]):target.setdefault((admin[x['region_norm']],norm(n)),[]).append((x,n))
zp=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip');zh=hashlib.sha256(zp.read_bytes()).hexdigest();geo=[]
with zipfile.ZipFile(zp).open('RU.txt')as f:
 for ln,b in enumerate(f,1):
  t=b.decode().rstrip('\n').split('\t')
  if t[6]!='P':continue
  hits={}
  for n in [t[1],t[2]]+t[3].split(','):
   for x,q in target.get((t[10],norm(n)),[]):hits[x['source_record_id']]=(x,q,n)
  for sid,(x,q,n)in hits.items():geo.append(dict(source_record_id=sid,settlement_name=x['settlement_name'],region_norm=x['region_norm'],query_county=x['query_county'],requested_alias=q,matched_name=n,geonameid=t[0],feature_name=t[1],ascii_name=t[2],alternate_names=t[3],latitude=t[4],longitude=t[5],feature_class=t[6],feature_code=t[7],admin1_code=t[10],admin2_code=t[11],admin3_code=t[12],admin4_code=t[13],provider_population_raw=t[14],modification_date=t[18],source_file=str(zp),source_sha256=zh,source_locator=f'RU.txt:line={ln};geonameid={t[0]}',candidate_only=True,coordinate_admitted=False,identity_admitted=False))
pd.DataFrame(geo).to_csv(O/'geonames_cached_own_place_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});print('GeoNames',len(geo),'targetUIDs',len(set(v['source_record_id']for v in geo)),flush=True)
# Physical settlement/residential candidates only; all service results remain in raw bundle.
queries=[]
for x in r.to_dict('records'):
 if 'сельсовет' in x['settlement_name']:
  queries.append(dict(x,skip_reason='confirmed administrative aggregate, no whole-NP ownpoint target'));continue
 base=[x['settlement_name']]+alias.get(x['settlement_name'],[])
 for qn in dict.fromkeys(base):queries.append(dict(x,query_alias=qn))
receipts=[];candidates=[];bundle=[];last=0
for i,x in enumerate(queries,1):
 if 'skip_reason'in x:receipts.append({'source_record_id':x['source_record_id'],'skip_reason':x['skip_reason']});continue
 region='Республика Карелия' if x['region_norm']=='карелия' else x['region_norm'].capitalize()+' область';q=', '.join(v for v in [x['query_alias'],x['query_county'],region,'Россия']if v);url='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=q,format='jsonv2',addressdetails=1,extratags=1,namedetails=1,limit=8))
 delay=1.1-(time.monotonic()-last)
 if delay>0:time.sleep(delay)
 last=time.monotonic();entry={'source_record_id':x['source_record_id'],'query':q,'request_url':url,'normal_TLS':True,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'RussianSettlementResearch/1.0 (bounded native locality source audit)'}),timeout=12)as resp:raw=resp.read();entry['status']=resp.status
  j=json.loads(raw);entry['results']=len(j);entry['response_sha256']=hashlib.sha256(raw).hexdigest();bundle.append(dict(entry,response=j));receipts.append(entry)
  for v in j:
   candidates.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=x['region_norm'],query_county=x['query_county'],query_alias=x['query_alias'],provider='OSM_Nominatim',feature_id=str(v.get('osm_type'))+'/'+str(v.get('osm_id')),latitude=v.get('lat'),longitude=v.get('lon'),own_name=v.get('name'),display_name=v.get('display_name'),feature_class=v.get('class'),feature_category=v.get('category'),feature_type=v.get('type'),address_type=v.get('addresstype'),address_json=json.dumps(v.get('address',{}),ensure_ascii=False),extratags_json=json.dumps(v.get('extratags',{}),ensure_ascii=False),namedetails_json=json.dumps(v.get('namedetails',{}),ensure_ascii=False),boundingbox_json=json.dumps(v.get('boundingbox',[])),source_file=str(O/'nominatim_capture_bundle.json.gz'),source_response_sha256=entry['response_sha256'],source_locator=f'bundle request[{len(bundle)-1}];osm_type={v.get("osm_type")};osm_id={v.get("osm_id")}',candidate_only=True,coordinate_admitted=False,identity_admitted=False,automatic_place_selection=False))
  print(i,q,len(j),flush=True)
 except Exception as e:
  entry['error']=str(e);receipts.append(entry);print(i,type(e).__name__,str(e),flush=True)
  if getattr(e,'code',None)==429:break
 (O/'nominatim_capture_receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2));(O/'nominatim_capture_bundle.json.gz').write_bytes(gzip.compress(json.dumps(bundle,ensure_ascii=False).encode(),mtime=0));pd.DataFrame(candidates).to_csv(O/'nominatim_own_feature_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0})
(O/'source_pins.json').write_text(json.dumps({str(zp):zh,str(N/'per_record_dispositions_final.csv'):hashlib.sha256((N/'per_record_dispositions_final.csv').read_bytes()).hexdigest(),str(s):hashlib.sha256(s.read_bytes()).hexdigest()},indent=2));(O/'receipt.json').write_text(json.dumps({'target_records':49,'geonames_candidates':len(geo),'geonames_target_UIDs':len(set(v['source_record_id']for v in geo)),'nominatim_queries_attempted':len(receipts),'nominatim_candidates':len(candidates),'nominatim_target_UIDs':len(set(v['source_record_id']for v in candidates)),'normal_TLS':True,'candidate_only':True,'point_or_edge_admissions':0},indent=2));print('COMPLETE',len(receipts),len(candidates),flush=True)
