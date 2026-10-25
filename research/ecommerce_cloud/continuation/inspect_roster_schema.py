"""Read the official CSV schema through the pinned public CA chain."""
from pathlib import Path
import hashlib
import json
import ssl
import urllib.request
D=Path('work/ecommerce_rosters_verified')
pins={'russian_trusted_root_ca_pem.crt':'936a43fea6e8e525bcc0f81acd9c3d21b4fc4b9b68acea7906d698005afc6504',
      'russian_trusted_sub_ca_2024_pem.crt':'6f9d829c8e6712444fce3624658d8788672849c5d5b7b53fd9cf7e83eac4193e'}
context=ssl.create_default_context()
for name,digest in pins.items():
    path=D/name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    context.load_verify_locations(cafile=str(path))
url='https://rosstat.gov.ru/opendata/7708234640-oktmo/structure-20260210T1102.csv'
record={'url':url,'tls_verification':True,'status_semantics_confirmed':False}
try:
    with urllib.request.urlopen(url,context=context,timeout=30) as r:
        body=r.read(100001)
        if len(body)>100000:
            raise ValueError('Unexpected schema size')
        record.update(http_status=r.status,bytes=len(body),
                      sha256=hashlib.sha256(body).hexdigest())
    (D/'structure-20260210T1102.csv').write_bytes(body)
    try:
        text=body.decode('utf-8-sig')
    except UnicodeDecodeError:
        text=body.decode('cp1251')
    record['schema_text']=text
except Exception as e:
    record.update(error_type=type(e).__name__,error=str(e))
(D/'schema_probe.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print('OFFICIAL_ROSTER_SCHEMA_BEGIN')
print(json.dumps(record,ensure_ascii=False))
print('OFFICIAL_ROSTER_SCHEMA_END')
