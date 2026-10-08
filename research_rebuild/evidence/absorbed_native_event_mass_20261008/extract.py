from pathlib import Path
import sys,json,gzip,re,hashlib
import pandas as pd
from bs4 import BeautifulSoup
R=Path('/workspace/russian-settlements-research'); O=Path(__file__).parent
sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(34)
d=s.obs.copy();d['full3']=d.root.map(lambda x:s.years[x]=={2002,2010,2021});d['ownpoint']=d.source_record_id.isin(s.point_rows)
h=d[d.census_year.isin([2002,2010]) & d.is_additive_settlement_record.fillna(False) & ~d.full3 & d.population.ge(5000)].sort_values('population',ascending=False)
h.head(250).to_csv(O/'ranked_historical_targets.csv',index=False)
paths=set(Path('/tmp/absorbed_cache_paths').read_text().splitlines())|set(Path('/tmp/wiki_inventory_paths').read_text().splitlines())
def docs(v,loc=''):
 if not isinstance(v,dict):return
 if 'parse' in v:
  p=v['parse'];t=p.get('text',p.get('wikitext',''));yield p.get('title',''),t.get('*','')if isinstance(t,dict)else t,loc+'/parse',p.get('revid','')
 for k,p in v.get('query',{}).get('pages',{}).items() if isinstance(v.get('query',{}).get('pages',{}),dict) else enumerate(v.get('query',{}).get('pages',[])):
  for i,r in enumerate(p.get('revisions',[])):yield p.get('title',''),r.get('slots',{}).get('main',{}).get('content',r.get('*','')),loc+f'/query/pages/{k}/revisions/{i}',r.get('revid','')
 if 'html'in v:yield v.get('title',''),v['html'],loc+'/html',''
 for k,x in v.items():
  if isinstance(x,dict) and k not in ['query','parse']:yield from docs(x,loc+'/'+k)
rows=[];article_seen=set();docs_n=0
for path in sorted(paths):
 p=Path(path);p=p if p.is_absolute()else R/p
 if not p.is_file()or p.stat().st_size>25_000_000:continue
 try:
  b=p.read_bytes();raw=(gzip.decompress(b)if p.suffix=='.gz'else b).decode();dd=list(docs(json.loads(raw)))if '.json'in p.name else [('',raw,'html','')]
 except:continue
 for title,txt,loc,rev in dd:
  if not txt:continue
  if '<html'in txt or '<table'in txt:
   soup=BeautifulSoup(txt,'html.parser');title=title or (soup.title.get_text()if soup.title else '');txt=soup.get_text(' ',strip=True)
  if (title,hashlib.sha256(txt.encode()).hexdigest()) in article_seen:continue
  article_seen.add((title,hashlib.sha256(txt.encode()).hexdigest()));docs_n+=1
  matches=list(re.finditer(r'(?:включ[её]н[аы]?|вош[её]л|присоедин[её]н|объедин[её]н|упраздн[её]н|поглощ[её]н).{0,160}',txt,re.I))
  if not matches:continue
  canon=title.split('(')[0].strip().lower().replace('ё','е')
  hits=h[h.name_norm.eq(canon)]
  if hits.empty:continue
  snippets=[txt[max(0,m.start()-100):m.end()+100]for m in matches]
  for _,z in hits.iterrows():
   rows.append({'title':title,'source_record_id':z.source_record_id,'year':z.census_year,'name':z.settlement_name,'region':z.region_norm,'county':z.district_raw,'population':z.population,'ownpoint':z.ownpoint,'sourcepath':str(p),'sha256':hashlib.sha256(b).hexdigest(),'locator':loc,'revision':rev,'snippets':snippets,'intro':txt[:2000]})
(O/'cached_event_candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print('historical >=5k',len(h),'top100 mass',h.head(100).groupby('census_year').population.sum().to_dict(),'cached docs',docs_n,'event hits',len(rows))
for z in rows:print(z['title'],z['year'],z['region'],z['population'],z['ownpoint'],z['snippets'][:2])
