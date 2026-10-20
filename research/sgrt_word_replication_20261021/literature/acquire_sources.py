from pathlib import Path
import urllib.request,concurrent.futures,hashlib,json,time
ROOT=Path(__file__).resolve().parent
URLS={
'horev1980':'https://www.demoscope.ru/weekly/2022/0949/nauka03.php',
'rodoman2021':'https://sciencejournals.ru/view-article/?a=IzvGeo2103012Rodoman&j=izvgeo&n=3&v=85&y=2021',
'lappo2005':'https://geo.1sept.ru/article.php?ID=200500603',
'pokshishevskiy1978':'https://www.demoscope.ru/weekly/knigi/IDEM_library/pdf/book044.pdf',
'lappo1997_card':'https://www.demoscope.ru/weekly/knigi/IDEM_library/book072.php',
'horev1975_card':'https://www.demoscope.ru/weekly/knigi/IDEM_library/book065.php',
'maergoyz1986_card':'https://search.rsl.ru/ru/record/01001291112',
'rodoman1999_card':'https://cat.gpntb.ru/?id=EC%2FShowFull&irbDb=KATBW&mfn=241248',
}
def get(kv):
 k,u=kv;t=time.time();r={'id':k,'url':u,'retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
 try:
  with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=35) as x:b=x.read();r.update(http_status=x.status,final_url=x.url,content_type=x.headers.get('Content-Type'))
  p=ROOT/'raw'/(k+('.pdf' if b[:4]==b'%PDF' else '.html'));p.write_bytes(b)
  r.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),local_path=str(p.relative_to(ROOT)),status='downloaded')
 except Exception as e:r.update(status='failed',error=repr(e))
 r['seconds']=round(time.time()-t,2);return r
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:r=list(ex.map(get,URLS.items()))
(ROOT/'acquisition_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
for x in r:print(x['id'],x['status'],x.get('bytes'),x.get('error',''))
