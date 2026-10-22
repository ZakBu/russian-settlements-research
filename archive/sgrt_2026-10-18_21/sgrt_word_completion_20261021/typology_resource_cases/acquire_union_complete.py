#!/usr/bin/env python3
"""Use the complete2022 archive: the2021 CommonCrawl capture truncates this PDF at1MiB."""
from pathlib import Path
import requests,hashlib,json,fitz,time
ROOT=Path(__file__).resolve().parent;RAW=Path('/workspace/scratch/sgrt_resource_cases');RAW.mkdir(exist_ok=True,parents=True)
url='https://web.archive.org/web/20221019223646id_/https://www.rogwu.ru/upload/iblock/35b/kuy9ftsewe48ruzkwzr2w8h2psdy81ms.pdf';r=requests.get(url,timeout=40);r.raise_for_status();assert r.content.startswith(b'%PDF');p=RAW/'yamburg_union2021_archive_complete.pdf';p.write_bytes(r.content);d=fitz.open(p);assert len(d)==64;p.with_suffix('.txt').write_text('\n\f\n'.join(x.get_text() for x in d));row={'name':'yamburg_union2021_archive_complete','archive_url':url,'http_status':r.status_code,'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'capture_timestamp':'20221019223646','retrieved_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'warning_header':r.headers.get('warning'),'local_path':str(p),'pages':len(d),'payload_validation':'VALID_COMPLETE_PDF'};(ROOT/'union_complete_archive_receipt.json').write_text(json.dumps(row,indent=2));print(row)
