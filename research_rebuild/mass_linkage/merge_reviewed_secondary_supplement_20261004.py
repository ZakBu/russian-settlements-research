"""Append source-scoped secondary observations after current-QID binding review."""
from pathlib import Path
import hashlib
import json
import pandas as pd

BASE = Path('/workspace/settlements-work/continuation_20261004')
OLD = BASE / 'root/R4/history_application/reviewed_secondary_history_observations.parquet'
PRODUCER = BASE / 'R4/native_physical_corridor_scope_audit/current_qid_false_gate_review/current_qid_false_gate_history_supplement'
REVIEW = BASE / 'R4/current_qid_false_gate_independent_review'
OUT = BASE / 'root/R4/history_application_with_reviewed_supplement'
PINS = {
    OLD: '8b6fca2e3bb9fb293ab0104772f4753bb33ab7d42a5ee217eeb4a4d3f69d9fe2',
    PRODUCER / 'staged_candidate_secondary_history.parquet': '2dc2a4f93f9450f995b00152884c6ff968d6efe39fd73b66cc2b52dc9ecf032c',
    PRODUCER / 'receipt.json': 'd32caba69516f7b655c1d4f41c761761d9cafe80008e00570f28c6e4fe0a4daf',
    REVIEW / 'current_source_qid_review_keys.csv': '16af62359f92acc0449eec2b4d2a644f79869d7bb3d22c06cc90979e7b85e3ba',
    REVIEW / 'receipt.json': '9f918e90a1ed934b0d0cc54f2746f650c3f986c1160cbfa18c06ede9951e0432',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def merge_frames(original, supplement, keys):
    eligible = set(zip(keys.source_record_id.astype(str), keys.qid.astype(str)))
    if len(eligible) != len(keys):
        raise ValueError('duplicate reviewed current binding keys')
    proposed = set(zip(supplement.current_source_record_id.astype(str), supplement.current_wikidata_qid.astype(str)))
    if not proposed <= eligible:
        raise ValueError('secondary observations have unreviewed current subjects')
    for frame in (original, supplement):
        if frame.latitude.notna().any() or frame.longitude.notna().any():
            raise ValueError('secondary historical coordinates must remain unknown')
        if frame.historical_identity_admitted.ne(False).any() or frame.historical_coordinate_asserted.ne(False).any():
            raise ValueError('secondary statements cannot admit historical place identity')
    if set(original.observation_id) & set(supplement.observation_id):
        raise ValueError('new secondary observation ID overlaps the preserved series')
    if set(original.wikidata_statement_id.dropna()) & set(supplement.wikidata_statement_id.dropna()):
        raise ValueError('statement GUID already represented in the preserved series')
    supplement = supplement.copy()
    supplement['current_binding_supplement_review_sha256'] = PINS[REVIEW / 'receipt.json']
    supplement['current_binding_application_status'] = 'reviewed_current_source_subject_association_only'
    combined = pd.concat([original, supplement], ignore_index=True, sort=False)
    # Keep every original observation and source value; new context adds no census evidence.
    pd.testing.assert_frame_equal(combined.iloc[:len(original)][original.columns].reset_index(drop=True),
                                  original.reset_index(drop=True), check_dtype=False)
    return combined


def main():
    for path, expected in PINS.items():
        if sha(path) != expected:
            raise ValueError(f'input checksum mismatch: {path}')
    original = pd.read_parquet(OLD)
    supplement = pd.read_parquet(PRODUCER / 'staged_candidate_secondary_history.parquet')
    keys = pd.read_csv(REVIEW / 'current_source_qid_review_keys.csv', engine='python', dtype=str)
    if len(original) != 362606 or len(supplement) != 1117 or len(keys) != 59:
        raise ValueError('reviewed input counts changed')
    combined = merge_frames(original, supplement, keys)
    OUT.mkdir(parents=True, exist_ok=False)
    result = OUT / 'reviewed_secondary_history_observations.parquet'
    combined.to_parquet(result, index=False)
    receipt = {
        'status': 'separate_secondary_series_with_reviewed_current_subject_supplement',
        'inputs': {str(path): expected for path, expected in PINS.items()},
        'observations': {'observations': len(combined), 'preserved_original': len(original),
                         'new_source_observations': len(supplement), 'new_current_subjects': len(keys)},
        'historical_identity_or_coordinate_admissions': 0,
        'census_population_or_identity_changes': 0,
        'year_or_national_population_sums_emitted': False,
        'original_observations_preserved_exactly': True,
        'municipal_wrapper_historical_grain_risks_preserved': True,
        'outputs': {result.name: {'sha256': sha(result), 'bytes': result.stat().st_size}},
        'script_sha256': sha(__file__),
    }
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(receipt['observations']))


if __name__ == '__main__':
    main()
