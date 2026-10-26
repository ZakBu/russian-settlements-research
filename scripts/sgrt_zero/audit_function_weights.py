#!/usr/bin/env python3
"""Sensitivity of direct service-profile leaders to declared function weights.

This independent diagnostic uses a three-column provider pivot, rather than the
primary-allocation implementation. Weights describe scenarios, not visit counts
or empirically estimated preferences. Registered centres remain self-anchors;
reported changes therefore concern noncentres. Unknown functions are not zeros
of provision: they supply no identifiable destination to the comparison.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from lower_profile_quality import part_inventory, sha256

FAMILIES = ['medical_basic', 'school', 'grocery']
SCENARIOS = {'equal': [1., 1., 1.], 'grocery_half': [1., 1., .5],
             'school_half': [1., .5, 1.], 'medicine_half': [.5, 1., 1.]}


def profile_winners(providers, weights):
    """Choose a distinct provider only when its function-weight sum is unique."""
    scores = np.zeros(providers.shape)
    for j in range(3):
        for k in range(3):
            scores[:, j] += (providers[:, j] == providers[:, k]) * weights[k]
        scores[:, j] *= providers[:, j] != ''
    maximum = scores.max(axis=1)
    pick = np.argmax(scores, axis=1)
    first = providers[np.arange(len(providers)), pick]
    # Repeated occurrences of the same provider are not competing leaders.
    tied = ((scores == maximum[:, None]) & (providers != first[:, None])
            & (providers != '')).any(axis=1)
    winner = np.where((maximum > 0) & ~tied, first, '')
    return winner, tied, maximum


def analyse(edges, reference, centres):
    core = edges[edges.service_family.isin(FAMILIES)]
    if core.empty or core.duplicated(['origin_id', 'service_family']).any():
        raise ValueError('Require one outcome per origin and basic function')
    if not core.groupby('origin_id').service_family.nunique().eq(3).all():
        raise ValueError('All three outcomes, including rejected/unknown ones, are required')
    if core.l0_admitted.isna().any() or not core.l0_admitted.isin([True, False]).all():
        raise ValueError('Explicit boolean admission is required')
    ref, _ = part_inventory(reference)
    ref = ref.dropna(subset=['source_record_id']).set_index('source_record_id')
    if not ref.index.is_unique or not centres.centre_settlement_id.is_unique:
        raise ValueError('Unique reference and centre identities are required')
    origins = pd.Index(sorted(core.origin_id.unique()), name='origin_id')
    if not set(origins) <= set(ref.index):
        raise ValueError('Unmatched origin identity')
    admitted = core[core.l0_admitted & core.provider_settlement_id.notna()]
    if not set(admitted.provider_settlement_id) <= set(ref.index):
        raise ValueError('Unmatched provider identity')
    providers = admitted.pivot(index='origin_id', columns='service_family',
        values='provider_settlement_id').reindex(index=origins, columns=FAMILIES).fillna('').to_numpy()
    anchor = origins.isin(centres.centre_settlement_id)
    metadata = ref.reindex(origins)
    positive = (metadata.population_role.eq('ordinary_settlement_record')
        & metadata.analysis_origin.fillna(False) & metadata.population_2021.gt(0)
        & metadata.part_status.eq('unmarked_whole_place_record')).to_numpy()
    eligible = positive & ~anchor
    baseline, baseline_tie, baseline_max = profile_winners(providers, SCENARIOS['equal'])
    known = (providers != '').sum(axis=1)
    rows = pd.DataFrame({'origin_id': origins, 'positive_ordinary_whole_noncentre': eligible,
                         'known_function_count': known})
    summary = {'schema': 'sgrt.function_weight_sensitivity.v1',
        'function_order': FAMILIES,
        'routed_noncentre_records': int((~anchor).sum()),
        'positive_ordinary_whole_noncentre_records': int(eligible.sum()),
        'weights_empirically_calibrated': False,
        'function_support_is_not_trip_frequency': True,
        'registered_centres_remain_self_anchors': True,
        'scenarios': []}
    for name, weights in SCENARIOS.items():
        winner, tied, maximum = profile_winners(providers, weights)
        rows[name + '_winner'] = winner
        rows[name + '_tied'] = tied
        summary['scenarios'].append({'name': name, 'weights': weights,
            'unique_winner_records': int((eligible & (winner != '')).sum()),
            'tied_records': int((eligible & tied).sum()),
            'no_identified_destination_records': int((eligible & (maximum == 0)).sum()),
            'changed_existing_unique_winner_records': int((eligible & (baseline != '')
                & (winner != '') & (baseline != winner)).sum()),
            'unique_winner_became_tied_records': int((eligible & (baseline != '') & tied).sum()),
            'tie_became_unique_winner_records': int((eligible & baseline_tie & (winner != '')).sum()),
            'tie_became_registered_centre_winner_records': int((eligible & baseline_tie
                & (winner != '') & pd.Index(winner).isin(centres.centre_settlement_id)).sum())})
    rows['equal_support_class'] = np.where(known == 0, 'no_identified_destination',
        np.where(baseline_tie, 'equal_support_split',
        np.where(known == 3, np.where(baseline_max == 3, 'three_functions_unanimous',
                                     'two_of_three_functions'),
        np.where(baseline_max == 2, 'two_known_functions_partial', 'one_known_function_provisional'))))
    summary['equal_weight_support_classes'] = {
        str(k): int(v) for k, v in rows.loc[eligible, 'equal_support_class'].value_counts().items()}
    return rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['edges', 'reference', 'centres', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--write-members', action='store_true')
    args = parser.parse_args()
    columns = ['origin_id', 'provider_settlement_id', 'service_family', 'l0_admitted']
    centres = pd.read_csv(args.centres) if args.centres.suffix == '.csv' else pd.read_parquet(args.centres)
    rows, summary = analyse(pd.read_parquet(args.edges, columns=columns),
                           pd.read_parquet(args.reference), centres)
    summary['inputs'] = {key: {'name': path.name, 'sha256': sha256(path)} for key, path in
        [('edges', args.edges), ('reference', args.reference), ('centres', args.centres)]}
    summary['code_sha256'] = sha256(Path(__file__))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    if args.write_members:
        rows.to_parquet(args.output / 'function_weight_sensitivity.parquet', index=False)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
