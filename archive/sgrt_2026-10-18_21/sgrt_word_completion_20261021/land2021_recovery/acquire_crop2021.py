"""Reproduce the exact archived primary Rosstat XLS, without touching other layers."""
from pathlib import Path
import requests,hashlib,json
O=Path(__file__).resolve().parent;P=Path('/workspace/scratch/sgrt_land2021/posev_2021.xls');expected='9648c0144304d884085dfdfcad68648844cc6bfe631621d35ae4ac30c68b3c38';url='https://web.archive.org/web/20230325215450id_/https://rosstat.gov.ru/storage/mediabank/posev_2021.xls'
if P.exists()and hashlib.sha256(P.read_bytes()).hexdigest()==expected:print('Exact primary XLS already present:',P)
else:
 r=requests.get(url,timeout=45);assert r.status_code==200 and len(r.content)==2316288;assert hashlib.sha256(r.content).hexdigest()==expected;P.parent.mkdir(parents=True,exist_ok=True);P.write_bytes(r.content);print('Restored exact primary XLS:',P)
