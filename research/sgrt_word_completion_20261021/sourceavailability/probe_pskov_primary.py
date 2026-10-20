from pathlib import Path
import requests,concurrent.futures,json,hashlib,subprocess
R=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_demography2010/pskov_source_check');RAW.mkdir(exist_ok=True)
files=['приложения.rar','t1_Итоги-ВПН2010.pdf','t1_pub-01-01_Терр=58000000.pdf']
def get(n):
 u='https://60.rosstat.gov.ru/storage/mediabank/'+n
 try:
  r=requests.get('https://web.archive.org/web/20240101id_/'+u,timeout=40);p=RAW/n;p.write_bytes(r.content)
  if r.content.startswith(b'%PDF'):subprocess.run(['pdftotext','-layout',str(p),str(p.with_suffix('.txt'))],check=True)
  return dict(original=u,final=r.url,status=r.status_code,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),path=str(p))
 except Exception as e:return dict(original=u,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as ex:r=list(ex.map(get,files))
(R/'pskov_primary_probe_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False,indent=2))
