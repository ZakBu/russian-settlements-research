#!/usr/bin/env python3
"""Independent Poppler extraction of the original medical tariff PDFs."""
from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[1];O=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for y,stem in [(2025,'sv_tariff_2025_full'),(2026,'sv_tariff_2026')]:
 pdf=R/f'medical/captures/{stem}.pdf';text=O/f'medical_tariff_{y}_independent.txt'
 subprocess.run(['pdftotext','-layout',str(pdf),str(text)],check=True)
 previous=R/f'medical/captures/{stem}.txt'
 rows.append({'year':y,'original_pdf_sha256':sha(pdf),'new_text_sha256':sha(text),'author_text_sha256':sha(previous),'identical_text':text.read_bytes()==previous.read_bytes()})
(O/'MEDICAL_PDF_EXTRACTION_AUDIT.json').write_text(json.dumps({'status':'PASS' if all(r['identical_text'] for r in rows) else 'FAIL','checks':rows,'command':'pdftotext -layout SOURCE.pdf statistics/medical_tariff_YEAR_independent.txt'},indent=2)+'\n')
assert all(r['identical_text'] for r in rows)
print('PASS: both original PDFs re-extracted independently')
