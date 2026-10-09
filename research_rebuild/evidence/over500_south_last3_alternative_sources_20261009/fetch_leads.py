from pathlib import Path
import urllib.request,urllib.parse,gzip,json,hashlib
from bs4 import BeautifulSoup
O=Path(__file__).parent;results=json.load(open(O/'search_candidate_sources.json'));out=[]
for i,x in enumerate(results[:2]):
 href=x['href'];url=urllib.parse.parse_qs(urllib.parse.urlsplit('https:'+href).query)['uddg'][0];e={'url':url,'normal_TLS':True,'candidate_source_only':True}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=15)as r:raw=r.read();e.update(status=r.status,final_url=r.url)
  f=O/f'gireevsky_lead_{i}.html.gz';f.write_bytes(gzip.compress(raw,mtime=0));e.update(capture=str(f),sha256=hashlib.sha256(f.read_bytes()).hexdigest());s=BeautifulSoup(raw,'html.parser');text=' '.join(s.stripped_strings);(O/f'gireevsky_lead_{i}.txt').write_text(text);print(i,text[:450],flush=True)
  if i==1:
   links=[{'text':a.get_text(' ',strip=True),'url':urllib.parse.urljoin(url,a.get('href',''))}for a in s.find_all('a')if'Гиреевский'in a.get_text()];(O/'Gireevsky_postal_child_links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2));print(links,flush=True)
 except Exception as ex:e['error']=str(ex);print(str(ex),flush=True)
 out.append(e)
(O/'lead_capture_receipts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
