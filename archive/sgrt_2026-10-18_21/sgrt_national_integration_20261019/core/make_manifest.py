#!/usr/bin/env python3
"""Freeze current core deliverables, excluding historical prototype outputs."""
from pathlib import Path
import json,hashlib

H=Path(__file__).resolve().parent
rows=[]
for p in sorted(H.iterdir()):
    if not p.is_file() or p.name in ['MANIFEST.json','FREEZE.json'] or p.name.startswith('.'):continue
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    rows.append({'path':p.name,'bytes':p.stat().st_size,'sha256':h.hexdigest()})
master=json.loads((H/'MASTER_AUDIT.json').read_text());replay=json.loads((H/'REPRODUCTION.json').read_text());inv=json.loads((H/'INVARIANTS.json').read_text())
assert replay['status']=='PASS' and replay['rows']==master['rows'] and replay['columns']==master['columns']
assert replay['expected_parquet_sha256']==master['outputs']['feature_master.parquet']['sha256']
assert inv['status']=='PASS' and inv['rows']==master['rows'] and inv['columns']==master['columns']
manifest={'role':'national_reference_settlement_feature_master_not_demonstrated_SGRT','files':rows,'inputs':master['inputs'],'rows':master['rows'],'columns':master['columns'],'all_original64_fields_preserved':True,'reproduction':'exact_typed_Arrow_all_cells','invariants_passed':inv['checks_passed']}
(H/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
freeze={'master_sha256':master['outputs']['feature_master.parquet']['sha256'],'rows':master['rows'],'columns':master['columns'],'producer_sha256':master['producer_sha256'],'manifest_sha256':hashlib.sha256((H/'MANIFEST.json').read_bytes()).hexdigest(),'parquet_reproduction_pass':True,'invariants_passed':inv['checks_passed']}
(H/'FREEZE.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2));print(json.dumps(freeze,ensure_ascii=False,indent=2))
