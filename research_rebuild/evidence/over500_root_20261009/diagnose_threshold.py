"""Measure actual own-point and graph coverage independently of population credit."""
from pathlib import Path
import argparse, hashlib, json
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--threshold', type=int, default=500)
    parser.add_argument('--snapshot', default='publication/stage71')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source = ROOT / args.snapshot
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    obs = pd.read_parquet(source / 'applied_state_observations.parquet')
    points = pd.read_parquet(source / 'applied_point_snapshot.parquet', columns=['target_source_record_id'])
    components = pd.read_csv(source / 'applied_component_snapshot.csv.gz', dtype=str, keep_default_na=False)
    credit = pd.read_csv(source / 'applied_primary_credited_UID_roster.csv.gz', usecols=['source_record_id'])
    scope = pd.read_csv(source / 'accepted_large_record_scope_classification_overlay.csv', keep_default_na=False)
    overlay = pd.read_csv(source / 'applied_primary_population_source_overlay_2010.csv.gz', low_memory=False).set_index('original_source_record_id')
    obs['effective_population'] = obs.population
    mask = obs.census_year.eq(2010) & obs.source_record_id.isin(overlay.index)
    obs.loc[mask, 'effective_population'] = obs.loc[mask, 'source_record_id'].map(overlay.population)
    rows = obs[obs.is_additive_settlement_record.fillna(False) &
               ((obs.population > args.threshold) | (obs.effective_population > args.threshold)) &
               ~obs.source_record_id.isin(scope.source_record_id)].copy()
    rows['has_ownpoint'] = rows.source_record_id.isin(points.target_source_record_id)
    rows['in_existing_population_credit_roster'] = rows.source_record_id.isin(credit.source_record_id)
    rows['component_years'] = rows.source_record_id.map(components.set_index('source_record_id').component_years)
    rows['has_same_place_other_census'] = rows.component_years.str.contains(',')
    rows['has_full3_identity_component'] = rows.component_years.eq('2002,2010,2021')
    residual = rows[~rows.has_ownpoint | ~rows.in_existing_population_credit_roster]
    residual.to_csv(out / 'residual.csv', index=False)
    rows.to_csv(out / 'all_eligible_records.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    receipt = {
        'threshold_strictly_greater_than': args.threshold,
        'eligible_source_year_records': len(rows),
        'missing_ownpoint': int((~rows.has_ownpoint).sum()),
        'missing_same_place_other_census': int((~rows.has_same_place_other_census).sum()),
        'missing_full3_identity_component': int((~rows.has_full3_identity_component).sum()),
        'absent_existing_population_credit_roster': int((~rows.in_existing_population_credit_roster).sum()),
        'credit_roster_absence_does_not_prove_missing_temporal_route': True,
        'known_scope_exclusions': len(scope),
        'source_pins': {},
        'residual_by_region': residual.groupby('region_norm').size().to_dict(),
    }
    for name in ['applied_state_observations.parquet', 'applied_point_snapshot.parquet',
                 'applied_component_snapshot.csv.gz', 'applied_primary_credited_UID_roster.csv.gz',
                 'accepted_large_record_scope_classification_overlay.csv',
                 'applied_primary_population_source_overlay_2010.csv.gz']:
        path = source / name
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        receipt['source_pins'][name] = {'sha256': digest, 'bytes': path.stat().st_size}
    (out / 'diagnostic_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k not in {'source_pins', 'residual_by_region'}}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
