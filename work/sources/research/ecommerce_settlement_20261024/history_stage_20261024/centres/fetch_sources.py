"""Fetch official primary classifier files; preserve raw bytes and download metadata.
Existing files are reused. TLS fallback is recorded for this local certificate setup.
"""
from pathlib import Path
import hashlib
import json
import requests
from requests.exceptions import SSLError

OUT=Path(__file__).resolve().parent
RAW=OUT/'raw'
RAW.mkdir(exist_ok=True)
ROOT='https://rosstat.gov.ru/opendata/7708234640-oktmo'
downloads=[
    (ROOT,'rosstat_oktmo_page.html'),
    ('https://rosstat.gov.ru/classification','classification_page.html'),
    ('https://rosstat.gov.ru/storage/mediabank/ОКТМО_Vvedenie_red950.docx','oktmo_introduction_950.docx'),
]
for filename in ['meta.csv','structure-20260210T1102.csv']+[
    f'data-{v}-structure-20260210T1102.csv' for v in [
        '20150128T1701','20200110T1001','20211103T1311','20220927T1309','20261001T1110']]:
    downloads.append((ROOT+'/'+filename,filename))
manifest=[]
for url,filename in downloads:
    path=RAW/filename
    if path.exists():
        status='reused_preserved_download'
        tls='historical_initial_download_disabled_due_local_certificate_failure'
    else:
        tls=True
        try:
            response=requests.get(url,timeout=120)
        except SSLError:
            response=requests.get(url,timeout=120,verify=False)
            tls=False
        response.raise_for_status()
        path.write_bytes(response.content)
        status=response.status_code
    data=path.read_bytes()
    manifest.append({'url':url,'file':'raw/'+filename,'status':status,'bytes':len(data),
                     'sha256':hashlib.sha256(data).hexdigest(),'tls_validation':tls})
(OUT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('Preserved',len(manifest),'official source files')
