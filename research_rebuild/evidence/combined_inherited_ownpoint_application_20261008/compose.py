"""Compose frozen point-only corrections without changing census identities or values."""
from pathlib import Path
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
E = ROOT / 'research_rebuild/evidence'
OUT = Path(__file__).resolve().parent


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    names = [
        'inherited_extreme_Geo_ownpoint_correction_20261008',
        'inherited_moderate_Geo_ownpoint_correction_20261008',
        'inherited_moderate_Geo_ownpoint_correction_20261008/broader_cached_modern_point_followup',
    ]
    optional = E / 'inherited_extreme_Geo_ownpoint_correction_20261008/held16_followup'
    if (optional / 'application_receipt.json').exists():
        names.append(str(optional.relative_to(E)))
    supplement = E / 'corrected_ownpoint_cached_history_followup_20261008/standalone/current_code_only_wiki_point_supplement'
    names.append(str(supplement.relative_to(E)))
    rejections, replacements, sources, pins = [], [], [], {}
    for name in names:
        folder = E / name
        receipt_path = folder / ('acceptance_receipt.json' if folder == supplement else 'application_receipt.json')
        receipt = json.loads(receipt_path.read_text())
        # Freeze actual evidence and application files, not Python caches.
        for path in sorted(folder.glob('*')):
            if path.is_file():
                pins[str(path)] = sha(path)
        for filename, expected in receipt.get('input_pins', {}).items():
            path = Path(filename)
            # Source applications preserve the exact earlier calculation code.
            # Only immutable, source-data inputs are live inputs to this overlay.
            if path.suffix == '.py' or path.parent == E / 'working_full_chain_20261007':
                continue
            if sha(path) != expected:
                raise ValueError(f'Immutable source input changed: {path}')
            pins[str(path)] = expected
        rpath, ppath = folder / 'point_use_rejections.csv.gz', folder / 'accepted_point_use_delta.csv.gz'
        if rpath.exists():
            frame = pd.read_csv(rpath, dtype=str, keep_default_na=False)
            frame['source_application_file'] = str(receipt_path)
            frame['source_application_sha256'] = sha(receipt_path)
            rejections.append(frame)
        quarantine_path = folder / 'unresolved_shared_rural_Geo_point_quarantine.csv.gz'
        if quarantine_path.exists():
            frame = pd.read_csv(quarantine_path, dtype=str, keep_default_na=False)
            frame['source_application_file'] = str(receipt_path)
            frame['source_application_sha256'] = sha(receipt_path)
            rejections.append(frame)
        frame = pd.read_csv(ppath, dtype=str, keep_default_na=False)
        frame['source_application_file'] = str(receipt_path)
        frame['source_application_sha256'] = sha(receipt_path)
        frame['point_use_time_interpretation'] = 'explicit_representative_retrospective_continuity_not_censusday_measurement'
        witness = folder / 'own_current_point_source_witnesses.csv.gz'
        if witness.exists():
            frame['coordinate_evidence_file'] = str(witness)
            frame['coordinate_evidence_sha256'] = sha(witness)
            frame['coordinate_evidence_locator'] = frame.target_source_record_id.map(lambda sid: f'exact target_source_record_id={sid}')
        replacements.append(frame)
        sources.append({'folder': str(folder), 'application_receipt': str(receipt_path), 'sha256': sha(receipt_path),
                        'positive_rejections': len(pd.read_csv(rpath)) if rpath.exists() else 0,
                        'explicit_shared_rural_quarantine': len(pd.read_csv(quarantine_path)) if quarantine_path.exists() else 0,
                        'replacements': len(frame)})
    rejected = pd.concat(rejections, ignore_index=True).fillna('')
    points = pd.concat(replacements, ignore_index=True).fillna('')
    # A separately recovered held point may supersede the original hold, but
    # two applications must agree on the exact active claim being removed.
    for sid, rows in rejected.groupby('target_source_record_id'):
        if len(rows) > 1:
            for field in ['old_latitude', 'old_longitude', 'origin_ledger', 'origin_ledger_sha256']:
                if rows[field].nunique() != 1:
                    raise ValueError(f'Conflicting original claim for {sid}: {field}')
    rejected = rejected.drop_duplicates('target_source_record_id', keep='last')
    if points.target_source_record_id.duplicated().any():
        raise ValueError('Competing representative replacements; no first-row tie breaking')
    recovered = set(points.target_source_record_id)
    replaced = rejected.target_source_record_id.isin(recovered)
    rejected.loc[replaced, 'rejection_status'] = 'reviewed_superseded_representative_point_only'
    rpath, ppath = OUT / 'point_use_rejections.csv.gz', OUT / 'accepted_point_use_delta.csv.gz'
    rejected.to_csv(rpath, index=False, compression={'method': 'gzip', 'mtime': 0})
    points.to_csv(ppath, index=False, compression={'method': 'gzip', 'mtime': 0})
    before = {'histories': 141065, 'populations_by_year': {'2002': 126912057, '2010': 124052342, '2021': 124675353}}
    check = E / 'geonames_anchor_rule_independent_check_20261008/receipt.json'
    if not check.exists():
        raise ValueError('Independent bounded physical-GeoNames rule check is missing')
    independent_check = json.loads(check.read_text())
    pins[str(check)] = sha(check)
    receipt = {'status': 'root_composed_independent_ownpoint_representatives_and_explicit_holds',
               'baseline_stage': 59, 'intended_stage': 60,
               'identity_edges_unchanged': True, 'raw_census_population_quality_unchanged': True,
               'before_finite': before, 'point_claims_superseded_or_held': len(rejected),
               'accepted_point_uses': len(points),
               'held_point_uses': int((~replaced).sum()),
               'source_applications': sources, 'input_pins': pins,
               'independent_GeoNames_rule_check': {'path': str(check), 'sha256': sha(check),
                    'receipt': independent_check, 'accuracy_confidence_interval_asserted': False},
               'output_pins': {rpath.name: sha(rpath), ppath.name: sha(ppath)},
               'historical_point_alternatives_preserved_in_immutable_source_ledgers': True,
               'current_point_is_not_historical_censusday_measurement': True,
               'historical_boundary_comparability': 'UNKNOWN unless separately proved',
               'statistical_accuracy_probability_calibrated': False,
               'after_finite_requires_actual_root_replay': True}
    (OUT / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ['point_claims_superseded_or_held', 'accepted_point_uses', 'held_point_uses']}))


if __name__ == '__main__':
    main()
