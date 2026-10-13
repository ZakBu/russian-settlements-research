import pathlib,json,re,csv,html,hashlib,collections,unicodedata,time
E=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_volga_20261013');RAW=pathlib.Path('/workspace/shared/rsfsr1989_rural_volga')
def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s))).strip()
def norm(s):return unicodedata.normalize('NFKC',s).lower().replace('ё','е').strip()
# Exact 1989 urban-settlement exclusion names from census transcription already archived by parent.
p=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_sources_20261013/95d3ad7dd9ab.html');s=p.read_bytes().decode('cp1251');urban=collections.defaultdict(set);region=None
for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',s,re.S):
 cells=[clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)]
 if not cells:continue
 if re.fullmatch(r'.*(?:АССР|область|край)',cells[0]):region=cells[0]
 m=re.match(r'^(?:г\.|пгт|рп|кп|дп)\s*(.*?)\s*(?:\(.*\))?$',cells[0])
 if m and len(cells)>1 and cells[1].isdigit():urban[region].add(norm(m.group(1).split('(')[0]))
(E/'urban_exclusion_names.json').write_text(json.dumps({k:sorted(v) for k,v in urban.items() if k in ['Башкирская АССР','Татарская АССР']},ensure_ascii=False,indent=2))
fields=['census_year','region_norm','district_raw','name_raw','name_norm','type_raw','population','source_record_id','source_url','source_sha256','source_path','grain','count_basis','population_residency_basis','census_provenance_url','census_provenance_page','licensing','source_population_section','source_subtitle','review_status']
summary={};rejects=[]
tatdistrict={}
for x in json.loads((E/'tatarica_category_manifest.json').read_text()):
 for u in x.get('links',[]):
  if '/municipalnye-rajony/' in u:
   key=u.split('/municipalnye-rajony/')[1].split('/')[0];tatdistrict[re.sub(r'-\d+$','',key)]=x['district_name']
for source,region_name,legacy in [('tatarica','Республика Татарстан','Татарская АССР'),('bashenc','Республика Башкортостан','Башкирская АССР')]:
 p=E/(source+'_download_manifest.jsonl')
 if not p.exists():continue
 records={}
 for line in p.read_text().splitlines():
  try:r=json.loads(line)
  except Exception:continue
  if r.get('http_status')==200:records[r['url']]=r
 rows=[]
 allowed_bash={}
 if source=='bashenc':
  for x in json.loads((RAW/'bashenc_rubric.json').read_text())['items']:
   if x.get('parent')=='246' and 'район' in x['text']:
    n=x['text'].split('/')[1].split(' [')[0].strip();stem=norm(n.replace(' район',''));stem=re.sub(r'ский$','',stem);allowed_bash[stem]=n
 for r in records.values():
  if source=='bashenc' and r.get('kind')!='article':continue
  if source=='bashenc':
   body=r.get('body','');title=r.get('title','');rural=re.search(r'(?i)(?:,\s*|\s+)(деревня|село|пос[её]лок|хутор)(?:\b|$)',title)
   if not r.get('rural_type_current') and rural:r['rural_type_current']=rural.group(1).lower()
   if not r.get('district_raw'):
    d=re.search(r'(?i)(?:в\s+|сельсовету\s+)([А-ЯЁа-яё-]+(?:ском|ского)) рай?оне?',body[:350])
    if d:r['district_raw']=d.group(1)
   if r.get('population_1989') is None and not r.get('rounded_population'):
    pop=re.search(r'(В\s*\d{4}\s*(?:г\.)?\s*насчитывалось.{0,900}?человек)',body,re.I)
    if pop:
     pt=pop.group(1);m=re.search(r'1989\s*(?:г\.)?\s*[—–-]\s*([\d\s]+)(?=,|;|\s*чел)',pt)
     if m and not re.search(r'1989\s*(?:г\.)?\s*[—–-]\s*\d+[.,]\d+',pt):r['population_1989']=int(re.sub(r'\s','',m.group(1)));r['popsec']=pt
   if re.search(r'(?i)(?:19[5-9]\d|1960)[^.;]{0,80}учитывалось вместе',body):
    rejects.append({'source':source,'name':r.get('name_raw'),'url':r['url'],'reason':'1989 may combine settlements; held'});continue
  if r.get('population_1989') is None or not r.get('rural_type_current'):continue
  name=r.get('name_raw') if source=='bashenc' else r.get('title');sub=r.get('subtitle','') if source=='tatarica' else r.get('title','');pt=r.get('popsec','')
  if norm(re.sub(r'\([^)]*\)','',name)).strip() in urban[legacy] or re.match(r'(?i)^пос[её]лок\s+городского\s+типа',sub):rejects.append({'source':source,'name':name,'url':r['url'],'reason':'Urban in 1989 census or current pgt; excluded'});continue
  if source=='tatarica':
   district=re.search(r'(?i)(?:в |центр )([А-ЯЁа-яё\-]+(?:ском|ского|ский)) (?:районе|района|район)',sub);district=district.group(1)+' район' if district else r['url'].rstrip('/').split('/')[-2]
   district=tatdistrict.get(re.sub(r'-\d+$','',r['url'].rstrip('/').split('/')[-2]),district)
   if re.search(r'(?i)Сводные данные|здесь и далее.*(?:совместно|вместе)',pt):
    rejects.append({'source':source,'name':name,'url':r['url'],'reason':'Aggregate or combined settlement population section; held'});continue
   basis='Official census population series, per encyclopedia Volume1 Introduction p3; exact 1989 count in Число жителей section';prov='https://tatarica.org/download_file/view/11463';provpage='3';license='© Institute of Tatar Encyclopedia and Regional Studies AN RT. All rights reserved; no open license. Factual number extraction only.'
  else:
   d=r.get('district_raw');stem=re.sub(r'(ском|ского)$','',norm(d or ''))
   if stem not in allowed_bash:
    rejects.append({'source':source,'name':name,'url':r['url'],'reason':'Bashkortostan district not positively identified','district_raw':d});continue
   district=allowed_bash[stem];basis='1989 population in Нас. series of Bashkir Encyclopedia; census attribution inferred, not explicitly established at source-method level';prov='';provpage='';license='© GAUN RB Bashkir Encyclopedia 2026. All rights reserved; no open license. Factual number extraction only.'
  rows.append(dict(zip(fields,[1989,region_name,district,name,norm(re.sub(r'\([^)]*\)','',name)).strip(),r['rural_type_current'],r['population_1989'],source+':'+hashlib.sha256(r['url'].encode()).hexdigest()[:16],r['url'],r['sha256'],r['path'],'individual named rural settlement',basis,'presence/permanent not specified in encyclopedia',prov,provpage,license,clean(pt),sub,'exact number extracted; unlinked; not accepted into integrated population table'])))
 dedup={};blocked=set()
 for row in rows:
  key=(row['district_raw'],row['name_norm'])
  if key in blocked:continue
  if key in dedup:
   prev=dedup[key]
   rejects.append({'source':source,'name':row['name_raw'],'url':row['source_url'],'reason':'Duplicate district and name URL' if row['population']==prev['population'] else 'Conflicting same district and name counts; held','previous_url':prev['source_url']})
   if row['population']!=prev['population']:dedup.pop(key,None);blocked.add(key)
  else:dedup[key]=row
 rows=list(dedup.values())
 out=E/(source+'_rural_1989.csv')
 with out.open('w') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 summary[source]={'downloaded_unique_successful_pages':len(records),'rows':len(rows),'population_sum':sum(x['population'] for x in rows),'csv':str(out),'csv_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
(E/'source_exclusions.json').write_text(json.dumps(rejects,ensure_ascii=False,indent=2));summary['timestamp_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());(E/'extract_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False,indent=2))
