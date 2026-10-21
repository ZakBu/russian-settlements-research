from pathlib import Path
import requests,hashlib,json,fitz
h=Path(__file__).resolve().parent
urls={'crimeastat_form2021.pdf':'https://82.rosstat.gov.ru/storage/mediabank/BsFGi1h8/Разъяснения+1-приватизация_2021.pdf','crimeastat_demography_methodology.pdf':'https://82.rosstat.gov.ru/storage/mediabank/Методология+демография.pdf','crimea_law18_2014_replica.pdf':'https://www.roscadastre.ru/html/krim/Zakon_18_ZPK_2014.pdf'}
receipts=[]
for n,u in urls.items():
 try:
  r=requests.get(u,timeout=30);(h/n).write_bytes(r.content);item=dict(file=n,url=u,status=r.status_code,sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content),is_pdf=r.content.startswith(b'%PDF'))
  if item['is_pdf']:
   d=fitz.open(stream=r.content,filetype='pdf');txt='\n'.join('PDF PAGE'+str(i+1)+'\n'+p.get_text() for i,p in enumerate(d));(h/(n+'.txt')).write_text(txt);print(n,txt[:12000])
  receipts.append(item)
 except Exception as e:receipts.append(dict(file=n,url=u,error=str(e)))
(h/'acquisition_receipt.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipts,ensure_ascii=False,indent=2))
