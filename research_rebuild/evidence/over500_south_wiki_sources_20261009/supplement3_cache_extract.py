from pathlib import Path
import json,gzip,re,hashlib,pandas as pd
O=Path(__file__).parent
r=pd.read_csv('/dev/shm/over500-20261009/south_remaining.csv',dtype=str,keep_default_na=False)
idx=pd.read_csv('/dev/shm/over500-20261009/wiki_cached_title_index.csv.gz',dtype=str,keep_default_na=False)
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
alias={'Центральная усадьба совхоза "Надеждинский"':['Центральная усадьба совхоза «Надеждинский»','Надеждино','Надеждинский'],'Головинская Варежка':['Головинщино'],'Саловка':['Саловка'],'Подъем Первое Отделение':['Подъём','Первое отделение','Первое отделение совхоза «Подъём»'],'Центральное Отделение Совхоза Сулакский':['Сулакский'],'Центральное отделение совхоза им. Мичурина':['Мичурина','Имени Мичурина','Центральный','Мичуринский','Совхоз имени Мичурина'],'1 Отделение совхоза Бондарский':['Бондарский','Первое отделение совхоза «Бондарский»','Пахотный Угол'],'совхоза Пальна-Михайловский':['Пальна-Михайловский'],'1-го отделения совхоза "Михайловский"':['Михайловский'],'1-го отделения племзавода "Тойда"':['Тойда','Первое отделение племзавода «Тойда»'],'совхоза "Опыт"':['Опыт'],'совхоза "Маяк"':['Маяк'],'Ярославка Первая':['Первая Ярославка'],'Ярославка Вторая':['Вторая Ярославка'],'им. Н.Островского':['Имени Н. Островского'],'железнодорожной станции Питерка':['Питерка'],'Центральной усадьбы совхоза "Выдвиженец"':['Выдвиженец'],'совхоза "Серп и Молот"':['Серп и Молот'],'Верхний Чегем':['Эльтюбю'],'Юбилейный':['Юбилейное'],'Школьный':['Школьное'],'Бильгады':['Бильгади'],'Гоцатль Малое':['Гоцатль Малый'],'Мущули':['Мушули'],'Гиреевский':['Гирей'],'Гимова':['Гимово'],'Охотничья':['Охотничья'],'Горная Поляна':['Горная Поляна']}
targets={}
for x in r.to_dict('records'):
 for nm in [x['settlement_name']]+alias.get(x['settlement_name'],[]):targets.setdefault(norm(nm),[]).append(x)
idx['stem']=idx.article_title.map(lambda x:norm(x.split('(')[0]));d=idx[idx.stem.isin(targets)];d.to_csv(O/'supplement3_expanded_cache_index.csv.gz',index=False,compression={'method':'gzip','mtime':0})
rows=[];pins={}
for f,g in d.groupby('cache_file'):
 b=Path(f).read_bytes();sha=hashlib.sha256(b).hexdigest();pins[f]=dict(sha256=sha,bytes=len(b));j=json.loads(gzip.decompress(b));q=j.get('payload',j).get('query',{});pr=q.get('pages',[]);pages={p['title']:p for p in (pr.values() if isinstance(pr,dict) else pr)}
 norms={p['from']:p['to']for p in q.get('normalized',[])};redirect={p['from']:p['to']for p in q.get('redirects',[])}
 for ix in g.to_dict('records'):
  title=norms.get(ix['article_title'],ix['article_title']);title=redirect.get(title,title);p=pages.get(title)
  if not p or 'missing'in p:continue
  rv=p.get('revisions',[{}])[0];slot=rv.get('slots',{}).get('main',{});text=slot.get('content',slot.get('*',''))
  def field(key):
   m=re.search(r'\|\s*'+key+r'\s*=\s*([0-9.]+)',text);return float(m.group(1))if m else None
  def coord(axis):
   deg=field(axis+'_deg');return deg+(field(axis+'_min')or 0)/60+(field(axis+'_sec')or 0)/3600 if deg is not None else ''
  lat,lon=coord('lat'),coord('lon');coords=p.get('coordinates',[])
  if coords:lat,lon=coords[0].get('lat',''),coords[0].get('lon','')
  for x in targets[ix['stem']]:
   region=x['region_norm'];region_root={'карелия':'Карел','нижегородская':'Нижегород','архангельская':'Архангель','тверская':'Твер','тульская':'Туль','костромская':'Костром','калининградская':'Калининград','дагестан':'Дагест','адыгея':'Адыг','северная осетия алания':'Осети','кабардино балкарская':'Кабардин','ингушетия':'Ингуш'}.get(region,region[:7])
   if region_root.lower() not in text.lower() and region_root.lower() not in title.lower():continue
   rows.append(dict(source_record_id=x['source_record_id'],settlement_name=x['settlement_name'],region_norm=region,district_raw=x['district_raw'],requested_article_title=ix['article_title'],article_title=p['title'],cached_settlement_id=ix['settlement_id'],cached_qid=ix['wikidata_id_effective'],pageid=p.get('pageid'),revid=rv.get('revid'),latitude=lat,longitude=lon,capture=f,capture_sha256=sha,source_locator=f"pageid={p.get('pageid')};revid={rv.get('revid')};infobox lat_deg/lon_deg",county_literal_present=bool(x['district_raw']and x['district_raw'] in text),disambiguation='disambiguation'in p.get('pageprops',{})or '{{неоднозначность' in text.lower(),own_source_type_witness=' || '.join(v for v in text.splitlines()if re.search('статус\\s*=|район\\s*=|цифровой идентификатор|^\'\'\'',v))[:3500],history_alias_witness=' || '.join(v for v in text.splitlines()if re.search('переимен|прежн|2002|2010|преобразован|отделен|поселок|посёлок|деревн',v,re.I))[:9000],candidate_only=True,coordinate_admitted=False,identity_admitted=False))
pd.DataFrame(rows).to_csv(O/'supplement3_cached_own_article_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0});(O/'supplement3_cached_source_pins.json').write_text(json.dumps(pins,ensure_ascii=False,indent=2));print('files',len(pins),'rows',len(rows),'pointrows',sum(x['latitude']!=''for x in rows),'targets',len(set(x['source_record_id']for x in rows)))
