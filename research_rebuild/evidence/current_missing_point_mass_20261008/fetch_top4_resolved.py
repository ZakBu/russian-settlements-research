from pathlib import Path
import urllib.request,urllib.parse,json,gzip,concurrent.futures,hashlib
O=Path(__file__).parent
names=['Барановка (Хостинский район)','Михайловка (Михайловский сельсовет, Бугурусланский район)','Мыза (Привокзальный территориальный округ)','Мыза (Пролетарский территориальный округ)','Савино (Нердвинское сельское поселение)']
def get(title):
 u='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','titles':title,'prop':'revisions','rvprop':'ids|timestamp|content','rvslots':'main','redirects':1,'format':'json','formatversion':2})
 try:
  b=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'SettlementResearch/1.0 (+local research; bounded ownpoint verification)'}),timeout=25).read(500000);a=json.loads(b);p=O/('top4_resolved_'+str(names.index(title)+1)+'_article_revision_source.json.gz');p.write_bytes(gzip.compress(b,mtime=0));return {'title':title,'url':u,'bytes':len(b),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'file':str(p),'response':a}
 except Exception as ex:return {'title':title,'url':u,'failure':type(ex).__name__+': '+str(ex)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as t:r=list(t.map(get,names))
(O/'top4_resolved_article_fetch_receipt.json').write_text(json.dumps([{k:v for k,v in z.items() if k!='response'} for z in r],ensure_ascii=False,indent=2)+'\n')
for z in r:
 print(z['title'],z.get('failure','OK'))
 for page in z.get('response',{}).get('query',{}).get('pages',[]):
  print(page.get('title'),page.get('missing'),page.get('revisions',[{}])[0].get('revid'));content=page.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','');print(content[:7000])
