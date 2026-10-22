from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import requests,concurrent.futures,hashlib,json,re
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010');targets=[];catalog=[]
for region,code in [('tver','69'),('vologda','35'),('pskov','60')]:
 soup=BeautifulSoup((RAW/(region+'_catalog_archived.html')).read_text(),'html.parser')
 for a in soup.find_all('a',href=True):
  href=a['href'];context=a.parent.parent.get_text(' ',strip=True)
  if not re.search(r'\.(?:xls|xlsx|rar|zip|pdf|doc)(?:$|\?)',href,re.I):continue
  url=urljoin(f'https://{code}.rosstat.gov.ru/',href);catalog.append({'region':region,'url':url,'catalogue_literal':context})
  take=(region=='tver' and 'Том8' in context)or(region=='vologda'and ('Населенные пункты.rar' in href))
  if take:targets.append((region+'_allNP_archive','https://web.archive.org/web/20240101id_/'+url,url,context))
(ROOT/'regional_catalogue_download_links.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
def get(item):
 k,url,original,context=item
 try:
  r=requests.get(url,timeout=45);b=r.content;ext='.rar'if b.startswith(b'Rar!')else'.zip'if b.startswith(b'PK')else'.html';p=RAW/(k+ext);p.write_bytes(b);return {'id':k,'original_official_url':original,'retrieval_url':url,'final_url':r.url,'catalogue_literal':context,'status':r.status_code,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'path':str(p),'signature':b[:15].decode(errors='replace')}
 except Exception as e:return {'id':k,'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as e:rows=list(e.map(get,targets))
(ROOT/'regional_archives_acquisition.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rows,ensure_ascii=False,indent=2))
