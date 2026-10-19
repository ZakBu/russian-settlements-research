"""Check that the targeted tie correction preserves protected source values."""
import hashlib,json
from pathlib import Path
import pandas as pd
root=Path(__file__).resolve().parent
before=json.loads((root/'tie_patch_before.json').read_text());checks=[]
for name,meta in before.items():
    frame=pd.read_parquet(root/name)
    assert len(frame)==meta['rows']
    for column,wanted in meta['protected_column_value_sha256'].items():
        got=hashlib.sha256(pd.util.hash_pandas_object(frame[column],index=False).values.tobytes()).hexdigest()
        checks.append({'file':name,'column':column,'same':got==wanted})
audit={'status':'PASS' if all(c['same'] for c in checks) else 'FAIL','checks_passed':sum(c['same'] for c in checks),'checks_total':len(checks),'checks':checks,'allowed_changes':'unique_dominant_labels,tie_flags,latest_valid_profile_year;no_original_area_or2021_class_changes'}
(root/'tie_patch_preservation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
assert audit['status']=='PASS';print(audit['status'],audit['checks_passed'],'/',audit['checks_total'])
