from pathlib import Path
import requests,concurrent.futures,hashlib,json
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010');RAW.mkdir(exist_ok=True)
name='Численность+населения+по+населенным+пунктам+Республики+Башкортостан.pdf'
old='http://bashstat.gks.ru/wps/wcm/connect/rosstat_ts/bashstat/resources/2f055a804e303140ba45fe3bf8d20d64/'+name
urls={'bash_official_current':'https://02.rosstat.gov.ru/storage/mediabank/'+requests.utils.quote(name,safe=''), 'bash_archived_original':'https://web.archive.org/web/20131020083342id_/'+old,'tver_catalog_archived':'https://web.archive.org/web/20240101id_/https://69.rosstat.gov.ru/folder/25218','vologda_catalog_archived':'https://web.archive.org/web/20240101id_/https://35.rosstat.gov.ru/folder/31540','pskov_catalog_archived':'https://web.archive.org/web/20240101id_/https://60.rosstat.gov.ru/vpn2010'}
def fetch(kv):
 k,u=kv
 try:
  r=requests.get(u,timeout=35);b=r.content;p=RAW/(k+('.pdf' if b.startswith(b'%PDF') else '.html'));p.write_bytes(b);return {'id':k,'url':u,'final_url':r.url,'status':r.status_code,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'path':str(p),'payload_signature':b[:15].decode(errors='replace')}
 except Exception as e:return {'id':k,'url':u,'status':'FAILED','error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=5)as e:rows=list(e.map(fetch,urls.items()))
(ROOT/'candidate_acquisition.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rows,ensure_ascii=False,indent=2))
