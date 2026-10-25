"""Download only archive links published on the official dislocation index.
No authentication, purchases, torrent download or challenge-solving is used.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,re,hashlib,zipfile
import requests,urllib3
from bs4 import BeautifulSoup
urllib3.disable_warnings()
P=Path(__file__).resolve().parent/'raw'
URL='https://www.xn----8sbwdbcc3abhth9e.xn--p1ai/index.php/eko2/potrebitelskij-rynok/3363-torgovyj-reestr-dislokatsiya-predpriyatij-torgovli-obshchestvennogo-pitaniya-khlebopecheniya-aptek-azs-vsekh-form-sobstvennosti-munitsipalnogo-obrazovaniya-chojskij-rajon'
session=requests.Session()
r=session.get(URL,timeout=30,verify=False);r.raise_for_status()
(P/'choya_register_index.html').write_bytes(r.content)
soup=BeautifulSoup(r.content,'html.parser')
links=[]
for a in soup.find_all('a',href=True):
 label=a.get_text(' ',strip=True)
 if 'реестр' in label.lower() and 'состоянию' in label.lower():
  year=re.search(r'01\.01\.(20\d\d)',label)
  if year and 2019<=int(year.group(1))<=2026:
   links.append({'label':label,'url':requests.compat.urljoin(URL,a['href'])})
assert len(links)==8
(P/'choya_discovered_links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2))
receipts=[]
for x in links:
 year=re.search(r'01\.01\.(20\d\d)',x['label']).group(1)
 r=session.get(x['url'],timeout=30,verify=False);r.raise_for_status()
 archive=P/f'choya_{year}.zip';archive.write_bytes(r.content)
 contents=[]
 with zipfile.ZipFile(archive) as z:
  for i,n in enumerate(z.namelist()):
   body=z.read(n);ext=Path(n).suffix.lower()
   assert ext in ['.xls','.docx']
   f=P/f'choya_{year}_{i}{ext}';f.write_bytes(body)
   contents.append({'name_raw':n,'local_file':f.name,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
 receipts.append({'observation_date_label':year+'-01-01','index_label':x['label'],'url':r.url,
  'status':r.status_code,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),
  'local_archive':archive.name,'contents':contents,'tls_verification':False,
  'retrieved_at_utc':datetime.now(timezone.utc).isoformat()})
(P/'choya_download_manifest.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
print('Downloaded and checked8ZIPs; chronology will be checked inside each file by analyzer.')
