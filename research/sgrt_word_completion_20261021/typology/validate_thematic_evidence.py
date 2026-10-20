#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
import pandas as pd
H=Path(__file__).resolve().parent
f=pd.read_parquet(H/'settlement_features.parquet');a=pd.read_parquet(H.parent/'axis/full_settlement_axis.parquet')
assert len(f)==len(a)==173527 and f.id.is_unique and set(f.id)==set(a.id)
axis_sha=hashlib.sha256((H.parent/'axis/full_settlement_axis.parquet').read_bytes()).hexdigest()
thematic_receipt=json.loads((H/'thematic_receipt.json').read_text());original_axis_sha=next(v for k,v in thematic_receipt['inputs'].items() if k.endswith('axis/full_settlement_axis.parquet'))
if axis_sha!=original_axis_sha:
 compatibility=json.loads((H/'axis_version_semantic_check.json').read_text())
 assert compatibility['old_axis_sha256']==original_axis_sha and compatibility['current_axis_sha256']==axis_sha
 assert compatibility['thematic_input_values_equal'] and compatibility['ethnicity_effective_native_code_after_old_master_fallback_equal']
for c in ['industrial_decline_evidence','resource_shift_evidence','ethnocultural_demographic_evidence','commuting_observed','ethnic_composition_explains_demographic_change']:assert f[c].isna().all(),c
assert f.loc[f.ethnicity_suppressed2021.fillna(False),'share_declared_not_russian_response2021'].isna().all()
assert f.share_declared_not_russian_response2021.dropna().between(0,1).all()
assert (f.ethnicity_declared_persons2021.dropna()>=0).all()
assert f.loc[f.current_monotown_category2026.notna(),'current_monotown_category2026'].isin([1,2,3]).all()
for c in ['recreation_dacha_evidence','historical_monotown_evidence','mapped_resource_site_context_evidence']:assert not f[c].eq(False).fillna(False).any(),c
p=pd.read_parquet(H/'official_resort_points.parquet');assert p.lat.between(35,85).all() and p.lon.between(15,180).all()
m=pd.read_csv(H/'current_monotowns2026.csv');assert m.registry_row.tolist()==list(range(1,265));assert not m.loc[m.linked_id.notna(),'linked_id'].duplicated().any()
h=pd.read_csv(H/'historical_monotowns2012.csv');assert len(h)==333
counts={c:int(f[c].fillna(False).sum()) for c in f if str(f[c].dtype)=='boolean'}
r={'status':'PASS','rows':len(f),'columns':len(f.columns),'unique_ids':f.id.nunique(),'positive_boolean_counts':counts,'usable_ethnic_rates':int(f.share_declared_not_russian_response2021.notna().sum()),'suppressed_ethnic_records':int(f.ethnicity_suppressed2021.fillna(False).sum()),'features_sha256':hashlib.sha256((H/'settlement_features.parquet').read_bytes()).hexdigest(),'validated_scope':'provenance, identity-grain, suppression, coordinates, legal-list completeness and unknown causal mechanism preservation; not complete Word type validation'}
(H/'validation_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
# Content-addressed manifest includes all actually retained source payloads; HTTP503 kept as failed retrievals.
out=[]
for p in sorted((H/'sources').rglob('*')):
 if p.is_file() and '__MACOSX' not in str(p):out.append({'path':str(p.relative_to(H)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'note':'Raw retained payload; acquisition receipts supply URLs and HTTP status. A saved error payload is not evidence.'})
(H/'source_manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
