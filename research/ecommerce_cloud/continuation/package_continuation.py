"""Package executed evidence without modifying census or historical inputs."""
from pathlib import Path
import hashlib
import json
import os
import zipfile
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'work/ecommerce_continuation_release'
OUT.mkdir(parents=True,exist_ok=True)
folders=[
 'work/ecommerce_extension_outcomes/nonshop_population_contexts',
 'work/ecommerce_atp_history','work/ecommerce_atp_analysis',
 'work/ecommerce_atp_ozon_audit','work/ecommerce_rosters_verified',
 'work/ecommerce_continuation','work/ecommerce_surveys_probe',
 'work/ecommerce_cloud_extension/figures','work/ecommerce_cloud_extension/national',
 'work/ecommerce_cloud_extension/report',
]
single=[
 'research/ecommerce_cloud/REPORT_RU.md',
 'research/ecommerce_cloud/METHOD_AND_SOURCE_RECHECK_20261025.md',
 'research/ecommerce_cloud/extension/review/FINAL_CRITICAL_REVIEW.md',
 'research/ecommerce_cloud/continuation/atp_pinned_manifest.json',
 'work/ecommerce_extension_outcomes/raw/data_Y48112027_112_v20260928.parquet',
]
files=set()
for folder in folders:
    path=ROOT/folder
    if not path.is_dir():
        raise FileNotFoundError(folder)
    files.update(p for p in path.rglob('*') if p.is_file())
for name in single:
    path=ROOT/name
    if not path.is_file():
        raise FileNotFoundError(name)
    files.add(path)
for name in ['work/ecommerce_extension_outcomes/nonshop_population_contexts/independent_arithmetic_check.json',
             'work/ecommerce_atp_analysis/independent_atp_check.json']:
    check=json.loads((ROOT/name).read_text())
    assert check['status']=='PASS',name
notebook=json.loads((ROOT/'work/ecommerce_continuation/notebook_execution.json').read_text())
assert notebook['all_code_cells_executed'] and notebook['errors']==0
pdf=ROOT/'work/ecommerce_cloud_extension/report/Marketplaces_and_Russian_Centres_20261025.pdf'
reader=PdfReader(pdf)
assert len(reader.pages)>=20
text='\n'.join(page.extract_text() or '' for page in reader.pages)
assert '564' in text and '67' in text and len(text)>25000
records=[]
for path in sorted(files):
    body=path.read_bytes()
    records.append({'path':str(path.relative_to(ROOT)),'bytes':len(body),
                    'sha256':hashlib.sha256(body).hexdigest()})
receipt={'schema':'ecommerce.continuation.release.v2',
         'source_commit':os.environ.get('GITHUB_SHA'),
         'files':records,'pdf_pages':len(reader.pages),
         'notebook_execution':notebook,
         'census_base_modified':False,'causal_effect_identified':False,
         'visual_inspection_status':'Execution and values verified; human-like rendered inspection is recorded separately.'}
manifest=OUT/'manifest.json'
manifest.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
archive=OUT/'ecommerce-continuation-20261025-v2.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in sorted(files):
        z.write(path,str(path.relative_to(ROOT)))
    z.write(manifest,'manifest.json')
sha=hashlib.sha256(archive.read_bytes()).hexdigest()
(OUT/'SHA256SUMS.txt').write_text(sha+'  '+archive.name+'\n')
print('CONTINUATION_RELEASE_RECEIPT_BEGIN')
print(json.dumps({'source_commit':receipt['source_commit'],'files_n':len(records),
                  'zip_bytes':archive.stat().st_size,'zip_sha256':sha,
                  'pdf_pages':len(reader.pages),'notebook':notebook,
                  'causal_effect_identified':False},ensure_ascii=False))
print('CONTINUATION_RELEASE_RECEIPT_END')
