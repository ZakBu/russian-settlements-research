import urllib.request,urllib.parse,json,gzip,pathlib,hashlib,time
D=pathlib.Path('/dev/shm/over500-20261009/final_history');D.mkdir(exist_ok=True);titles=['Пальна-Михайловка','Пальна-Михайловский (посёлок)','Ярославка (Никифоровский район)','Кантышево','Гиреевский','Гиреевский (Ингушетия)','Горная Поляна (Волгоград)'];receipts=[]
for title in titles:
 params={'action':'query','format':'json','prop':'revisions|coordinates','rvprop':'ids|content','rvslots':'main','coprimary':'primary','titles':title,'redirects':1};url='https://ru.wikipedia.org/w/api.php?'+urllib.parse.urlencode(params);dest=D/(hashlib.sha256(title.encode()).hexdigest()[:16]+'.json.gz')
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'SettlementSourceResearch/1.0'});raw=urllib.request.urlopen(req,timeout=25).read();body=json.loads(raw)
  with gzip.GzipFile(filename=str(dest),mode='wb',mtime=0) as f:f.write(json.dumps({'url':url,'requested_title':title,'body':body},ensure_ascii=False).encode())
  pages=list(body.get('query',{}).get('pages',{}).values());print(title,[(p.get('title'),p.get('pageid'),p.get('missing')) for p in pages]);receipts.append(dict(title=title,capture=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
 except Exception as e:print(title,str(e));receipts.append(dict(title=title,error=str(e)))
 time.sleep(.2)
(D/'receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
