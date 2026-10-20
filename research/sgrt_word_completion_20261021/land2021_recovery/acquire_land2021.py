from pathlib import Path
import requests,json,hashlib,concurrent.futures,subprocess
O=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_land2021');official='https://rosreestr.gov.ru/upload/Doc/16-upr/Государственный (национальный) доклад о состоянии и использовании земель в РФ в 2021 году.pdf';urls=[official,'https://web.archive.org/web/20240101id_/'+official,'https://t-j.ru/media/gosudarstvennyi-doklad-o-sostoyanii-i-ispolzovanii-zemel-v-2021-godu.e8vfqjoy4o9p..pdf']
def get(it):
 i,u=it
 try:
  r=requests.get(u,timeout=45);h=hashlib.sha256(r.content).hexdigest();p=RAW/f'rosreestr2021_candidate_{i}_{h[:8]}.pdf';p.write_bytes(r.content);ispdf=r.content.startswith(b'%PDF')
  if ispdf:subprocess.run(['pdftotext','-layout',str(p),str(p.with_suffix('.txt'))],check=True)
  return dict(url=u,final_url=r.url,status=r.status_code,bytes=len(r.content),sha256=h,path=str(p),is_pdf=ispdf)
 except Exception as e:return dict(url=u,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:rows=list(ex.map(get,enumerate(urls)))
(O/'acquisition_receipt.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');print(json.dumps(rows,ensure_ascii=False,indent=2))
