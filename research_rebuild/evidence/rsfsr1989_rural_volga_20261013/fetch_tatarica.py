import concurrent.futures,urllib.request,urllib.parse,pathlib,hashlib,json,time,re,html
from html.parser import HTMLParser
RAW=pathlib.Path('/workspace/shared/rsfsr1989_rural_volga');E=pathlib.Path('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_rural_volga_20261013');RAW.mkdir(exist_ok=True)
class Plain(HTMLParser):
 def __init__(self): super().__init__(); self.parts=[];self.hidden=0
 def handle_starttag(self,t,a):
  if t in ['script','style']: self.hidden+=1
  if t in ['p','br','h1','h2','h3','div','li','tr']: self.parts.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style']:self.hidden=max(0,self.hidden-1)
  if t in ['p','h1','h2','h3','div','li','tr']:self.parts.append('\n')
 def handle_data(self,d):
  if not self.hidden:self.parts.append(d)
def strip(s):
 p=Plain();p.feed(s);return re.sub(r'[ \t\r\xa0]+',' ',''.join(p.parts))
def fetch(u):
 h=hashlib.sha256(u.encode()).hexdigest()[:16];path=RAW/(h+'.html')
 try:
  b=path.read_bytes() if path.exists() else urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Settlement historical population research (academic source archive)'}),timeout=25).read()
  path.write_bytes(b);s=b.decode('utf-8');t=strip(s);(RAW/(h+'.txt')).write_text(t)
  links=set(urllib.parse.urljoin(u,html.unescape(x)) for x in re.findall(r'href=[\"\']([^\"\']+)',s))
  links=[x for x in links if x.startswith('https://tatarica.org/ru/razdely/municipalnye-obrazovaniya/municipalnye-rajony/') and '#' not in x and '?' not in x]
  h1=re.search(r'<h1[^>]*>(.*?)</h1>',s,re.S);sub=re.search(r'<div class="inner-page-top__subtitle">(.*?)</div>',s,re.S)
  title=strip(h1.group(1)).strip() if h1 else '';subtitle=strip(sub.group(1)).strip() if sub else ''
  popsec=re.search(r'<h2[^>]*>\s*(?:Число жителей|Численность населения|Население)\s*</h2>(.*?)(?=<h2|<div class="(?:actions|copyright)|</main>|$)',s,re.S|re.I)
  pt=strip(popsec.group(1)) if popsec else ''
  m=re.search(r'1989\s*г?\.?\s*[–—−-]\s*([\d\s]+)([,;.]|\n|чел)',pt)
  rural=re.match(r'(?i)^(село|деревня|пос[её]лок|хутор)\b',subtitle)
  rec={'url':u,'path':str(path),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'title':title,'subtitle':subtitle,'popsec':pt[:4000],'population_1989':int(re.sub(r'\s','',m.group(1))) if m else None,'rural_type_current':rural.group(1).lower() if rural else None,'links':links,'http_status':200,'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
  return rec
 except Exception as e:return {'url':u,'error':str(e)}
urls=json.loads((RAW/'tatarica_urls.json').read_text());done=set();out=E/'tatarica_download_manifest.jsonl'
if out.exists():
 for l in out.read_text().splitlines():
  r=json.loads(l)
  if r.get('http_status')==200:done.add(r['url'])
urls=[u for u in urls if u not in done]
for rnd in range(3):
 new=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex, out.open('a') as f:
  for n,r in enumerate(ex.map(fetch,urls),1):
   f.write(json.dumps(r,ensure_ascii=False)+'\n');f.flush();done.add(r['url']);new+=r.get('links',[])
   if n%100==0:print('round',rnd,'done',len(done),'this',n,'of',len(urls),flush=True)
 urls=sorted(set(new)-done)
 print('round complete',rnd,'newurls',len(urls),flush=True)
 if not urls:break
 if len(done)+len(urls)>4500:urls=urls[:max(0,4500-len(done))]
print('COMPLETE',len(done),flush=True)
