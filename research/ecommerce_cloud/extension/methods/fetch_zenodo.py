"""Fetch the sole primary DOCX, verify Zenodo MD5; do not redistribute it."""
import datetime,hashlib,json,signal,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'work/sources/research/ecommerce_settlement_20261024/methods_primary_20261025'
OUT.mkdir(parents=True,exist_ok=True)
def deadline(*args):raise TimeoutError('absolute deadline45seconds')
signal.signal(signal.SIGALRM,deadline);signal.alarm(45)
api=OUT/'RU-L02_api.json'
if not api.exists():
 with urllib.request.urlopen('https://zenodo.org/api/records/22040878',timeout=30) as response:api.write_bytes(response.read())
record=json.loads(api.read_text());file=record['files'][0];url=file['links']['self'];target=OUT/'RU-L02_primary.docx'
if target.exists():raw=target.read_bytes();status='cached'
else:
 with urllib.request.urlopen(url,timeout=30) as response:raw=response.read();status=response.status
 expected=file['checksum'].split(':')[1]
 assert hashlib.md5(raw).hexdigest()==expected
 target.write_bytes(raw)
match=hashlib.md5(raw).hexdigest()==file['checksum'].split(':')[1]
assert match
result={'url':url,'http_status':status,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'md5_matches_repository':match,'checked_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(Path(__file__).parent/'RU-L02_primary_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('DOCX verified',len(raw))
