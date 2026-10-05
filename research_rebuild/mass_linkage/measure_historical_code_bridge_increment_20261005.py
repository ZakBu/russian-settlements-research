#!/usr/bin/env python3
"""Measure the remaining Graph24 increment in the 1,258-row urban code bridge.

The upstream bridge audit is candidate evidence, not an accepted canonical
layer. This script only joins its frozen IDs to the current residual and the
already measured actual-observed-year additions. It does not change graph or
coordinate ledgers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path('/workspace/russian-settlements-research')
PACKET = Path('/workspace/settlements-work/continuation_20261004/independent_review/historical_urban_code_bridge_1258_audit_v1')
COHORT = PACKET / 'cohort.csv'
PACKET_RECEIPT = PACKET / 'receipt.json'
RESIDUAL = Path('/workspace/settlements-work/continuation_20261004/accepted_graph24_anapa_20261005/scoped_joint_residual.parquet')
ADDITIONS = ROOT / 'research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/additions.csv'
OUT = ROOT / 'research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths'
EXPECTED = {
    'cohort': '2f60214f1b52acc4883effbcc4d2f10fb4e1e6e8c614b43c1c4e5469701389f4',
    'residual': '669d2755db4c13504024d8d80cd899013886587bd7dad10d5759954c5d59750f',
    'additions': '314946dd2305b25f997c8ece7740b7a587f904769095f1b56b326ee05ebc40ee',
    'packet_receipt': 'd3524edd85330387b2354c9599b64c84daf57485cc74f4a5832e297006d014b1',
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    pins = {'cohort': COHORT, 'residual': RESIDUAL, 'additions': ADDITIONS,
            'packet_receipt': PACKET / 'README.md'}
    for key, path in pins.items():
        got = sha(path)
        assert got == EXPECTED[key], f'{key} hash mismatch: {got}'
    packet = json.loads(PACKET_RECEIPT.read_text())
    assert packet['findings']['structural_invariants'].startswith('All 1,258 pass')

    cohort = pd.read_csv(COHORT, low_memory=False)
    assert len(cohort) == 1258 and cohort.source_record_id.astype(str).is_unique
    cohort['year'] = pd.to_numeric(cohort.year, errors='raise').astype(int)
    cohort['population'] = pd.to_numeric(cohort.population, errors='raise').astype(int)
    cohort['source_file_resolved'] = cohort.source_file_resolved.fillna(False).astype(bool)
    cohort['shared_point_n'] = pd.to_numeric(cohort.shared_point_n, errors='raise').astype(int)
    cohort['structurally_clear'] = cohort.source_file_resolved & cohort.shared_point_n.eq(1)

    residual = pd.read_parquet(RESIDUAL, columns=[
        'source_record_id', 'census_year', 'population', 'missing_joint_axis',
    ])
    assert residual.source_record_id.astype(str).is_unique
    additions = pd.read_csv(ADDITIONS, usecols=['source_record_id', 'census_year', 'population'])
    assert additions.source_record_id.astype(str).is_unique
    joined = cohort.merge(residual, on='source_record_id', how='left',
                          suffixes=('_cohort', '_residual'), indicator='residual_state')
    joined = joined.merge(additions[['source_record_id']], on='source_record_id', how='left',
                          indicator='actual_year_path_state')
    in_residual = joined.residual_state.eq('both')
    in_additions = joined.actual_year_path_state.eq('both')
    assert (joined.loc[in_residual, 'year'] == joined.loc[in_residual, 'census_year']).all()
    assert (joined.loc[in_residual, 'population_cohort'] == joined.loc[in_residual, 'population_residual']).all()
    results = {}
    for year in (2002, 2010):
        y = joined.year.eq(year)
        y_res = y & in_residual
        y_added = y & in_additions
        y_candidate = y_res & joined.structurally_clear & ~in_additions
        results[str(year)] = {
            'bridge_candidates': int(y.sum()),
            'bridge_candidate_population': int(joined.loc[y, 'population_cohort'].sum()),
            'structurally_clear_no_collision_source_present': int((y & joined.structurally_clear).sum()),
            'structurally_clear_population': int(joined.loc[y & joined.structurally_clear, 'population_cohort'].sum()),
            'already_in_scope_aware_base_absent_from_residual': int((y & ~in_residual).sum()),
            'already_in_scope_aware_base_population': int(joined.loc[y & ~in_residual, 'population_cohort'].sum()),
            'current_scope_aware_residual_rows': int(y_res.sum()),
            'current_scope_aware_residual_population': int(joined.loc[y_res, 'population_cohort'].sum()),
            'already_counted_in_actual_observed_year_path_additions': int(y_added.sum()),
            'already_counted_in_actual_observed_year_path_population': int(joined.loc[y_added, 'population_cohort'].sum()),
            'clear_residual_not_yet_in_actual_year_additions': int(y_candidate.sum()),
            'clear_residual_not_yet_in_actual_year_population': int(joined.loc[y_candidate, 'population_cohort'].sum()),
            'residual_axis_counts': {
                str(axis): {'rows': int(g.source_record_id.size),
                            'population': int(g.population_cohort.sum())}
                for axis, g in joined.loc[y_res].groupby('missing_joint_axis', dropna=False)
            },
        }

    out_rows = joined.loc[in_residual, [
        'source_record_id', 'year', 'settlement_name', 'settlement_type', 'region_norm',
        'population_cohort', 'structurally_clear', 'shared_point_n', 'source_file_resolved',
        'missing_joint_axis', 'residual_state', 'actual_year_path_state',
    ]].copy().rename(columns={'population_cohort': 'population'})
    out_rows['current_disposition'] = out_rows.apply(
        lambda row: 'already_counted_actual_year_path' if row.actual_year_path_state == 'both'
        else ('candidate_for_bounded_followup' if row.structurally_clear else 'retain_hold'), axis=1)
    output_csv = OUT / 'historical_code_bridge_graph24_overlap.csv'
    output_json = OUT / 'historical_code_bridge_graph24_overlap.json'
    out_rows.to_csv(output_csv, index=False)
    result = {
        'status': 'read_only_current_graph24_overlap_measured',
        'canonical_ledgers_changed': False,
        'candidate_cohort_rows': len(cohort),
        'candidate_cohort_sha256': sha(COHORT),
        'current_scope_aware_residual_sha256': sha(RESIDUAL),
        'current_actual_observed_year_additions_sha256': sha(ADDITIONS),
        'results_by_year': results,
        'readback': {
            'residual_candidate_rows': int(in_residual.sum()),
            'residual_candidate_population': int(joined.loc[in_residual, 'population_cohort'].sum()),
            'already_counted_actual_year_rows': int(in_additions.sum()),
            'already_counted_actual_year_population': int(joined.loc[in_additions, 'population_cohort'].sum()),
            'potential_clear_uncovered_rows': int((in_residual & joined.structurally_clear & ~in_additions).sum()),
            'potential_clear_uncovered_population': int(joined.loc[in_residual & joined.structurally_clear & ~in_additions, 'population_cohort'].sum()),
        },
        'outputs': {
            output_csv.name: {'bytes': output_csv.stat().st_size, 'sha256': sha(output_csv)},
            Path(__file__).name: {'bytes': Path(__file__).stat().st_size, 'sha256': sha(Path(__file__))},
        },
        'limitations': [
            'The 1,167 structurally clear bridge rows are candidate-level coordinates, not accepted graph changes.',
            'Absence from the current residual means the exact source row is already included in the Graph24 scope-aware joint base.',
            'The clear residual population is only an upper bound before identity-component and coordinate admission review.',
        ],
    }
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
