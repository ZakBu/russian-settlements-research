#!/usr/bin/env python3
"""Prove a metadata-only axis revision preserves inputs actually used in thematic joins."""
from pathlib import Path
import hashlib,io,json,subprocess
import pandas as pd
H=Path(__file__).resolve().parent;R=H.parent;REPO=R.parents[1]
relative=(R/'axis/full_settlement_axis.parquet').relative_to(REPO)
old_revision='52e5a94';payload=subprocess.check_output(['git','show',f'{old_revision}:{relative}'],cwd=REPO)
old=pd.read_parquet(io.BytesIO(payload));current=pd.read_parquet(REPO/relative)
columns=['id','name','type','region','lat','lon','population_2021','is_additive_source_unit','municipality_oktmo8_2021','municipality_upper_2021']
master=pd.read_parquet(REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',columns=['id','oktmo_2021']).set_index('id').oktmo_2021
def code(v):
 if pd.isna(v):return None
 s=str(v).strip().removesuffix('.0')
 return s.zfill(11) if s.isdigit() and len(s) in [10,11] else None
before=old.id.map(master).fillna(old.oktmo_2021).map(code);after=current.id.map(master).fillna(current.oktmo_2021).map(code)
same=old[columns].equals(current[columns]);codes_same=before.equals(after)
r={'old_git_revision':old_revision,'old_axis_sha256':hashlib.sha256(payload).hexdigest(),'current_axis_sha256':hashlib.sha256((REPO/relative).read_bytes()).hexdigest(),'relevant_thematic_input_columns':columns,'thematic_input_values_equal':same,'ethnicity_effective_native_code_after_old_master_fallback_equal':codes_same,'new_axis_byte_change_does_not_invalidate_same_thematic_inputs':same and codes_same,'changed_axis_fields_are_metadata_quality_scope_and_restored_native_codes':[c for c in old if not old[c].equals(current[c])]}
assert same and codes_same,'Axis changed thematic input values; recompute features instead of claiming compatibility'
(H/'axis_version_semantic_check.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
