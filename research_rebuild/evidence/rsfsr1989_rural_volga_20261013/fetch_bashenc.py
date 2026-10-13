import concurrent.futures,urllib.request,urllib.parse,pathlib,hashlib,json,time,re,html
RAW=pathlib.Path('/workspace/shared/rsfsr1989_rural_volga');E=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_volga_20261013')
def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s))).strip()
def fetch(u,kind):
 h=hashlib.sha256(u.encode()).hexdigest()[:16];p=RAW/('bash_'+h+'.html')
 try:
  b=p.read_bytes() if p.exists() else urllib.request.urlopen(u,timeout=20).read();p.write_bytes(b);s=b.decode();links=set('https://bashenc.online'+x for x in re.findall(r'href="(/ru/articles/\d+/)',s));rec={'url':u,'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'http_status':200,'links':sorted(links),'kind':kind,'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
  if kind=='article':
   h1=re.search(r'<h1[^>]*>(.*?)</h1>',s,re.S);title=clean(h1.group(1)) if h1 else '';content=re.search(r'<div class="news-detail__text">(.*?)</div>',s,re.S);t=clean(content.group(1)) if content else '';rural=re.search(r',\s*(деревня|село|пос[её]лок|хутор)\b',title,re.I);popsec=re.search(r'Нас\.\s*(?:\([^)]*\))?\s*:\s*(.*?)(?=Живут|Есть|Основан|$)',t);pt=popsec.group(0) if popsec else '';m=re.search(r'1989\s*[—–-]\s*([\d\s]+)(?=[;.]|\s*чел)',pt);rounded='тыс.' in pt or (m and re.search(r'1989\s*[—–-]\s*\d+[.,]\d+',pt));district=re.search(r'(?:в\s+|центр\s+)([А-ЯЁа-яё-]+(?:ском|ского)) р[‑-]не?',title)
   rec.update({'title':title,'name_raw':title.split(',')[0].strip(),'district_raw':district.group(1) if district else None,'rural_type_current':rural.group(1).lower() if rural else None,'population_1989':int(re.sub(r'\s','',m.group(1))) if m and not rounded else None,'rounded_population':bool(rounded),'popsec':pt,'body':t[:5000]})
  return rec
 except Exception as e:return {'url':u,'kind':kind,'error':str(e)}
urls=[]
for name,total in [('деревня',86),('село',65)]:
 for page in range(1,total+1):urls.append('https://bashenc.online/ru/articles/?'+urllib.parse.urlencode({'filter_text':'1989','filter_name':name,'nav-articles':'page-'+str(page)}))
out=E/'bashenc_download_manifest.jsonl';articles=set()
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex,out.open('a') as f:
 for n,r in enumerate(ex.map(lambda u:fetch(u,'catalog'),urls),1):
  f.write(json.dumps(r,ensure_ascii=False)+'\n');f.flush();articles.update(r.get('links',[]))
  if n%30==0:print('catalog',n,'article URLs',len(articles),flush=True)
articles.discard('https://bashenc.online/ru/articles/38/');print('articles',len(articles),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex,out.open('a') as f:
 for n,r in enumerate(ex.map(lambda u:fetch(u,'article'),sorted(articles)),1):
  f.write(json.dumps(r,ensure_ascii=False)+'\n');f.flush()
  if n%200==0:print('articles',n,'of',len(articles),flush=True)
print('COMPLETE',flush=True)
