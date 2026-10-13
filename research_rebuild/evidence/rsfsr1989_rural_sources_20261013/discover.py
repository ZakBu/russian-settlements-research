import urllib.request,urllib.parse,concurrent.futures,re,json,hashlib
from pathlib import Path
E=Path(__file__).resolve().parent
urls=['https://www.demoscope.ru/weekly/ssp/rus89_reg1.php','https://www.demoscope.ru/weekly/ssp/rus89_reg2.php','https://www.demoscope.ru/weekly/ssp/rus89_reg3.php','https://www.demoscope.ru/weekly/ssp/census.php','https://lingvarium.org/russia/BD/02c.shtml','https://www.lingvarium.org/russia/BD/1989.shtml','https://lingvarium.org/russia/BD/1989.shtml','https://www.google.com/search?q='+urllib.parse.quote('перепись 1989 сельские населенные пункты численность xls')]
def fetch(u):
 try:
  r=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=25);b=r.read();enc='cp1251' if b'1251' in b[:2000] else 'utf-8';s=b.decode(enc,errors='replace');name=hashlib.sha256(u.encode()).hexdigest()[:12]+'.html';(E/name).write_bytes(b);t=re.sub('<[^>]+>',' ',s);t=re.sub(r'\s+',' ',t);return dict(url=u,status=r.status,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),path=str(E/name),text=t[:10000],links=re.findall(r'(?:href|HREF)\s*=\s*[\"\']([^\"\']+)',s))
 except Exception as e:return dict(url=u,error=str(e))
results=list(concurrent.futures.ThreadPoolExecutor(max_workers=5).map(fetch,urls));json.dump(results,open(E/'initial_discovery.json','w'),ensure_ascii=False,indent=2)
for r in results:print(r['url'],r.get('status',r.get('error')),r.get('text','')[:1800],r.get('links',[])[:25])
