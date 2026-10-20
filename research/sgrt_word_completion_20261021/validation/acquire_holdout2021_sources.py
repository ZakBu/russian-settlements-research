#!/usr/bin/env python3
"""Replay accepted source acquisition only; preregistration and frozen ledger are never overwritten."""
from pathlib import Path
import concurrent.futures,requests,hashlib,json,datetime
H=Path(__file__).resolve().parent;R=Path('/workspace/scratch/sgrt_holdout2021');R.mkdir(exist_ok=True)
SOURCES=[('kaluga2021_official_http_pdf.pdf','http://publication.pravo.gov.ru/file/pdf?eoNumber=4000202108050001','4fd94192431472a9c96db5e47df39f0670aef91234ca2dfba50e6fafeb519637'),('kaluga2021_garant_candidate.html','https://base.garant.ru/401569870/','d92a2b610255a78594e7a188333f5e45e9362d5ce8bd13035643eaadbd7d8e3a'),('rus.traineddata','https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/rus.traineddata','e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225')]
def get(v):
 name,url,expected=v;p=R/name
 if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==expected:return {'name':name,'status':'PINNED_CACHE_REUSED','sha256':expected}
 q=requests.get(url,timeout=60);q.raise_for_status();actual=hashlib.sha256(q.content).hexdigest()
 if actual!=expected:
  (R/(name+'.unaccepted_newbytes')).write_bytes(q.content);return {'name':name,'url':url,'status':'SOURCE_BYTES_CHANGED_NOT_ADMITTED','sha256':actual,'expected':expected}
 p.write_bytes(q.content);return {'name':name,'url':url,'status':'REPLAYED_HTTP200','bytes':len(q.content),'sha256':actual}
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(3) as ex:rows=list(ex.map(get,SOURCES))
 (H/'holdout2021_acquisition_replay_receipt.json').write_text(json.dumps({'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sources':rows},ensure_ascii=False,indent=2)+'\n')
