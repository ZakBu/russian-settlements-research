from pathlib import Path
import requests,hashlib,json,concurrent.futures
OUT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/frozen_primary_recovery');expected='42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3';urls=['https://static.statmuseum.ru/results/2010/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf','https://rosstat.gov.ru/free_doc/new_site/perepis2010/croc/Documents/Vol1/pub-01-05.pdf','https://web.archive.org/web/20240101id_/https://static.statmuseum.ru/results/2010/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf']
def get(pair):
 i,u=pair
 try:
  r=requests.get(u,timeout=55);h=hashlib.sha256(r.content).hexdigest();p=RAW/f'national2010_candidate_{i}_{h[:10]}.pdf';p.write_bytes(r.content);return dict(url=u,final_url=r.url,status=r.status_code,bytes=len(r.content),sha256=h,exact_hash=h==expected,exact_bytes=len(r.content)==15230814,path=str(p),pdf_signature=r.content[:5]==b'%PDF-')
 except Exception as e:return dict(url=u,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:rr=list(ex.map(get,enumerate(urls)))
(OUT/'national2010_exact_restore_receipt.json').write_text(json.dumps(rr,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rr,ensure_ascii=False,indent=2))
