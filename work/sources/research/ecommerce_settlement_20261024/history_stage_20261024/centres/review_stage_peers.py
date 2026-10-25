"""Read-only independent checks on new network and retail acquisition outputs."""
from pathlib import Path
import csv
import hashlib
import json
import openpyxl

OUT=Path(__file__).resolve().parent
STAGE=OUT.parent
checks=[]
manifest=json.loads((STAGE/'network/acquisition_manifest.json').read_text())
for snapshot in manifest['historical_snapshots']:
    path=STAGE/'network'/snapshot['decoded_json']
    data=path.read_bytes()
    raw=json.loads(data)
    ru=next(r['items'] for r in raw if r['country']=='ru')
    checks.append({'name':'network_'+snapshot['observation_date'],
                   'passed':hashlib.sha256(data).hexdigest()==snapshot['decoded_sha256']
                   and len(ru)==snapshot['ru_unique_ids']
                   and len(set(r['id'] for r in ru))==len(ru),
                   'objects':len(ru)})
for filename in ['rosstat_physical_retail_annual_2020_2025_long.csv',
                 'rosstat_physical_retail_quarterly_2022_2024_long.csv']:
    rows=list(csv.DictReader((STAGE/'retail'/filename).open()))
    workbooks={}
    errors=[]
    for row in rows:
        name=row['source_file']
        if name not in workbooks:
            workbooks[name]=openpyxl.load_workbook(STAGE/'retail/raw'/name,data_only=True)
        raw=workbooks[name][row['source_sheet']][row['source_cell']].value
        numeric=float(raw) if isinstance(raw,(float,int)) else None
        exported=float(row['value']) if row['value'] else None
        if numeric!=exported:
            errors.append({'cell':row['source_cell'],'raw':raw,'exported':exported})
    checks.append({'name':'retail_cell_trace_'+filename,'passed':not errors,
                   'checked_cells':len(rows),'errors':errors[:10]})
report={'date':'2026-10-24','checks':checks,
        'result':'PASS' if all(c['passed'] for c in checks) else 'FAIL',
        'limits':[
            'Network: verified local decoded source hashes, ru record counts and within-snapshot IDs; acquisition script additionally verifies Wayback compressed CDX digests. Capture is not opening date.',
            'Historical pickupType/isWb/dtype flags have changing, unverified semantics; historical records cannot automatically be equated to current focus types8/34.',
            'Retail cell values reproduce primary workbook cells. Series is regional/nested regional, not settlement-level. Category and reporting-form breaks remain.',
            'No retail cells were allocated to settlements, and no historical network point was automatically treated as a dated opening.',
        ]}
(OUT/'stage_peer_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
assert report['result']=='PASS'
