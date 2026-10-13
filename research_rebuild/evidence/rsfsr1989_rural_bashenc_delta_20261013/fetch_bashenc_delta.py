import concurrent.futures,urllib.request,urllib.parse,pathlib,hashlib,json,time,re,html
RAW=pathlib.Path('/workspace/shared/rsfsr1989_rural_bashenc_delta');E=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_bashenc_delta_20261013')
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

OLD=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_volga_20261013')
urls=json.loads((OLD/'bashenc_pending_article_urls.json').read_text());assert len(urls)==2531
(E/'requested_urls.json').write_text(json.dumps(urls,ensure_ascii=False,indent=2))
out=E/'bashenc_download_manifest.jsonl';done=set()
if out.exists():
 for line in out.read_text().splitlines():
  try:r=json.loads(line)
  except Exception:continue
  if r.get('http_status')==200:done.add(r['url'])
urls=[u for u in urls if u not in done]
print('bounded URLs',len(urls),'already completed',len(done),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex,out.open('a') as f:
 fut={ex.submit(fetch,u,'article'):u for u in urls}
 for n,future in enumerate(concurrent.futures.as_completed(fut),1):
  r=future.result();f.write(json.dumps(r,ensure_ascii=False)+'\n');f.flush()
  if n%100==0:print('completed',n,'of',len(urls),'at',time.strftime('%H:%M:%S',time.gmtime()),flush=True)
print('COMPLETE',flush=True)
