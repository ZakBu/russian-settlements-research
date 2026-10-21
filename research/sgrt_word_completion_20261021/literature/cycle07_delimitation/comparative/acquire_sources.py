from pathlib import Path
import requests,hashlib,json,datetime,fitz
H=Path(__file__).resolve().parent;S=H/'sources';S.mkdir(exist_ok=True)
items=[('raysikh2020','https://demreview.hse.ru/en/article/download/11139/12301/23173'),('oecd_ec2019','https://www.oecd.org/content/dam/oecd/en/publications/reports/2019/12/the-eu-oecd-definition-of-a-functional-urban-area_cef4a128/d58cb34d-en.pdf'),('degree_urbanisation2021','https://ec.europa.eu/eurostat/documents/3859598/15348338/KS-02-20-499-EN-N.pdf')]
receipts=[]
for k,u in items:
 p=S/k;p.mkdir(exist_ok=True);r=requests.get(u,timeout=60);r.raise_for_status();assert r.content.startswith(b'%PDF');f=p/'source.pdf';f.write_bytes(r.content);d=fitz.open(f);pages=[{'pdf_page':i+1,'text':x.get_text()} for i,x in enumerate(d)];(p/'pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2));(p/'text.txt').write_text('\n'.join(f'\n===PDF PAGE {x["pdf_page"]}===\n'+x['text'] for x in pages));rec={'key':k,'requested_url':u,'final_url':r.url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(r.content).hexdigest(),'bytes':len(r.content),'pages':len(d),'status':r.status_code};(p/'acquisition.json').write_text(json.dumps(rec,indent=2));receipts.append(rec);print(json.dumps(rec),flush=True)
(H/'source_inventory.json').write_text(json.dumps(receipts,indent=2))
