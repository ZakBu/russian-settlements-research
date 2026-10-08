import json,gzip,re
from pathlib import Path
import pandas as pd
O=Path(__file__).parent;out=[]
for p in sorted(O.glob('own_wikipedia_articles_batch_*.json.gz')):
 z=json.load(gzip.open(p,'rt'))
 for pg in z.get('query',{}).get('pages',{}).values():
  text=pg.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('*','');fields={}
  for k,v in re.findall(r'^\s*\|\s*([^=\n]{1,60}?)\s*=\s*([^\n]*)',text,re.M):
   if any(s in k.lower() for s in ['название','статус','регион','район','поселени','идентифик','oktmo','октмо','окато','lat_','lon_','прежн','численность','население']):fields[k.strip()]=v.strip()
  out.append({'title':pg.get('title'),'pageid':pg.get('pageid'),'missing':'missing' in pg,'revisionid':pg.get('revisions',[{}])[0].get('revid'),'source_archive':str(p),'fields_json':json.dumps(fields,ensure_ascii=False),'census2002_context_snippets':json.dumps([text[max(0,m.start()-130):min(len(text),m.end()+250)] for m in re.finditer('2002',text)],ensure_ascii=False),'intro_text':text[:4500],'article_text':text})
f=pd.DataFrame(out);f.to_csv(O/'own_article_source_discovery.csv.gz',index=False,compression='gzip');print('returned',len(f),'missing',int(f.missing.sum()));print(f[['title','missing','fields_json','census2002_context_snippets']].head(32).to_string(index=False)[:24000])
