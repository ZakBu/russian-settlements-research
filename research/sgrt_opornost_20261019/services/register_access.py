"""Hash actual saved access responses; failed requests are not data acquisitions."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parent
rows=[]
for filename,url,status,limitation in [
    ("national_medical_registry.web.txt","https://www.roszdravnadzor.gov.ru/services/licenses","schema_read_records_not_downloaded","explicit CAPTCHA Я не робот; no bypass attempted"),
    ("national_education_registry.web.txt","https://islod.obrnadzor.gov.ru/rlic/","timeout","web open returned timeout; no national records acquired"),
    ("national_bus_registry.web.txt","https://bus.gov.ru/","timeout","web open returned timeout; no national records acquired"),
    ("omsk_mobile.web.txt","https://мфц-омск.рф/main/struktura-MFC/regions/znamenskoe/","timeout","search snippet suggests mobile supply trips; excluded from confirmed edges"),
    ("nevyansk_pdf.web.txt","https://soshkonevo.uralschool.ru/file/download?id=5628","direct_url_open_failed_but_reference_pdf_parser_succeeded","raw source bytes unavailable; captured PDF page12/14 text separately; curl HEAD HTTP403")
]:
    p=R/"captures"/filename;b=p.read_bytes()
    rows.append(dict(url=url,retrieved_date="2026-10-19",status=status,limitation=limitation,records_downloaded=0,capture_file=str(p.relative_to(R)),capture_sha256=hashlib.sha256(b).hexdigest(),capture_size=len(b),raw_source_bytes_sha256=None))
(R/"access_audit.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(dict(n_access_records=len(rows),all_captures_hashed=True),ensure_ascii=False))
