from pathlib import Path
import urllib.request,urllib.parse,gzip,re,html,json,concurrent.futures
OUT=Path(__file__).parent
queries=['"469702421"','"О реорганизации территориальных единиц" "Воронеж" "2010"','"Воронеж" "24" "Гидроузел" "24 декабря 2010"']
urls=[('google'+str(i),'https://www.google.com/search?q='+urllib.parse.quote(q)) for i,q in enumerate(queries)]
urls += [('cntd_mirror','https://docs.cntd.ru/document/469702421?marker=64U0IK'),('lawru','https://www.lawmix.ru/zakonodatelstvo/265119')]
def fetch(item):
 name,url=item
 try:
  r=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20);b=r.read();gzip.open(OUT/(name+'.html.gz'),'wb').write(b);t=re.sub(r'<script.*?</script>|<style.*?</style>',' ',b.decode('utf-8','replace'),flags=re.S);text=html.unescape(re.sub('<[^>]+>',' ',t));(OUT/(name+'.txt')).write_text(text);return {'name':name,'url':url,'status':r.status,'bytes':len(b),'text_excerpt':text[:300]}
 except Exception as e:return {'name':name,'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(fetch,urls))
(OUT/'retrieval_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False,indent=2))
