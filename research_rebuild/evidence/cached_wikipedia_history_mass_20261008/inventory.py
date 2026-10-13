from pathlib import Path
import json,gzip,re,hashlib
from bs4 import BeautifulSoup
O=Path(__file__).parent
paths=set(Path('/tmp/wiki_inventory_paths').read_text().splitlines())
# Broadly include Wikipedia API batches and cached HTML, without fetching.
for root in ['/workspace/settlements-work','/workspace/russian-settlements-research/research_rebuild/evidence']:
 for p in Path(root).rglob('*'):
  if p.is_file() and any(z in str(p).lower() for z in ['wikipedia','ruwiki','article','raw_http']) and p.name.endswith(('.json','.json.gz','.html','.html.gz')): paths.add(str(p))
def docs(d):
 if isinstance(d,dict):
  if 'parse' in d:
   p=d['parse']; v=p.get('text',p.get('wikitext',''));yield p.get('title',''),v.get('*','') if isinstance(v,dict) else v
  pages=d.get('query',{}).get('pages',[])
  if isinstance(pages,dict):pages=pages.values()
  for p in pages:
   for r in p.get('revisions',[]):yield p.get('title',''),r.get('slots',{}).get('main',{}).get('content',r.get('*',''))
  if 'html' in d:yield d.get('title',''),d['html']
  for k,v in d.items():
   if isinstance(v,dict) and k not in ['parse','query']:yield from docs(v)
rows=[]
for path in sorted(paths):
 p=Path(path)
 if p.stat().st_size>25_000_000:continue
 try:
  b=p.read_bytes();text=(gzip.decompress(b)if p.name.endswith('.gz')else b).decode()
  dd=list(docs(json.loads(text))) if '.json' in p.name else [('',text)]
 except Exception:continue
 for title,txt in dd:
  if not txt or not all(str(y)in txt for y in [2002,2010]):continue
  soup=BeautifulSoup(txt,'html.parser') if '<table' in txt else None
  tables=[str(t)for t in soup.find_all('table') if all(str(y)in t.get_text()for y in [2002,2010])] if soup else [m.group(0)for m in re.finditer(r'\{\|.*?\|\}',txt,re.S)if all(str(y)in m.group(0)for y in [2002,2010])]
  if not tables and '{{Численность населения' in txt:tables=[txt[max(0,txt.index('{{Численность населения')-100):txt.index('{{Численность населения')+5000]]
  if not tables:continue
  if not title and soup:title=soup.title.get_text() if soup.title else (soup.h1.get_text()if soup.h1 else '')
  rows.append({'path':path,'sha256':hashlib.sha256(b).hexdigest(),'title':title,'tables':tables,'article_intro':soup.get_text(' ',strip=True)[:1800]if soup else txt[:2500]})
(O/'cached_table_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print('files',len(paths),'table_articles',len(rows));print([(x['title'],x['path'])for x in rows])
