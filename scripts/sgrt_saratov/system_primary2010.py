"""Evaluate the already published primary-2010 variant on document memberships.

This companion leaves the original census base and baseline profiles unchanged.
Primary numerical observations do not prove intercensus boundary/scope equality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.sgrt_saratov.system_economy import read_frame, build_demographic_context


def compare_profiles(baseline, auxiliary):
    """Separate changed comparable trajectories from newly available evidence."""
    if baseline.system_id.duplicated().any() or auxiliary.system_id.duplicated().any():
        raise ValueError('Repeated profile identity')
    old, new = baseline.set_index('system_id'), auxiliary.set_index('system_id')
    if set(old.index) != set(new.index):
        raise ValueError('Sensitivity must compare the same compositions')
    old = old.loc[new.index]
    for column in ['family', 'centre_id', 'regional_external_origins', 'documented_membership_complete']:
        if not (old[column].eq(new[column]) | (old[column].isna() & new[column].isna())).all():
            raise ValueError('Composition changed between census scenarios: ' + column)
    for mode in ['accepted', 'strict']:
        for scope in ['centre', 'external', 'rural_external']:
            column = f'{scope}_direction_2002_2021_{mode}'
            if not (old[column].eq(new[column]) | (old[column].isna() & new[column].isna())).all():
                raise ValueError('A 2010-only variant changed the 2002-2021 result')
    trajectories = ['centre_trajectory_2002_2010_2021_accepted',
                    'rural_external_trajectory_2002_2010_2021_accepted']
    observed = [c.replace('_accepted', '_strict') for c in trajectories]
    result = new[['family', 'centre_id', 'documented_membership_complete']].copy()
    for column in trajectories:
        result['baseline_' + column] = old[column]
        result['primary2010_' + column] = new[column]
    result['accepted_trajectory_comparable_in_both'] = old[trajectories].ne('unknown').all(axis=1) & new[trajectories].ne('unknown').all(axis=1)
    result['accepted_trajectory_changed_among_comparable'] = result.accepted_trajectory_comparable_in_both & old[trajectories].ne(new[trajectories]).any(axis=1)
    result['baseline_three_primary_numeric_parts_known'] = old[observed].ne('unknown').all(axis=1)
    result['auxiliary_three_primary_numeric_parts_known'] = new[observed].ne('unknown').all(axis=1)
    result['baseline_full_document_primary_numeric_three_census'] = old.classifiable_full_documented_three_census_system_strict
    result['auxiliary_full_document_primary_numeric_three_census'] = new.classifiable_full_documented_three_census_system_strict
    result['primary_numbers_do_not_prove_scope_or_historical_boundaries'] = True
    summary = {}
    for family, group in result.groupby('family', sort=True):
        full = group.documented_membership_complete.eq(True)
        summary[family] = {
            'documented_compositions': len(group),
            'primary_numeric_three_census_full_document_baseline': int(group.baseline_full_document_primary_numeric_three_census.sum()),
            'primary_numeric_three_census_full_document_auxiliary': int(group.auxiliary_full_document_primary_numeric_three_census.sum()),
            'primary_numeric_three_census_accepted_subset_auxiliary': int(group.auxiliary_three_primary_numeric_parts_known.sum()),
            'accepted_trajectory_comparable_geocoded_subsets': int(group.accepted_trajectory_comparable_in_both.sum()),
            'accepted_trajectory_changed_geocoded_subsets': int(group.accepted_trajectory_changed_among_comparable.sum()),
            'accepted_trajectory_comparable_full_documents': int((full & group.accepted_trajectory_comparable_in_both).sum()),
            'accepted_trajectory_changed_full_documents': int((full & group.accepted_trajectory_changed_among_comparable).sum())}
    return result.reset_index(), summary


def run(membership, baseline_profiles, primary_context, output):
    members = read_frame(membership)
    members = members[members.membership_basis.astype(str).str.startswith('documented_')].copy()
    if members.empty:
        raise ValueError('No documented compositions supplied')
    context = read_frame(primary_context)
    baseline = read_frame(baseline_profiles)
    baseline = baseline[baseline.system_id.isin(members.system_id)].copy()
    components, profiles = build_demographic_context(members, context)
    comparison, counts = compare_profiles(baseline, profiles)
    scope_columns = [c for c in context if c.startswith('primary2010_') or c.startswith('foundation_population_2010')]
    evidence_columns = ['source_record_id', 'name', 'population_2002', 'population_2010', 'population_2021',
                        'source_record_id_2010', 'population_value_quality_2010', 'credit_2010', 'budget_population_credit'] + scope_columns
    evidence = context[context.source_record_id.isin(members.source_record_id)][evidence_columns].copy()
    if evidence.source_record_id.duplicated().any():
        raise ValueError('Repeated source evidence')
    if 'primary2010_frozen_population_foundation_modified' not in evidence:
        raise ValueError('The primary-2010 provenance flags are required')
    if evidence.primary2010_frozen_population_foundation_modified.any():
        raise ValueError('Auxiliary context claims to have modified the foundation')
    summary = {'schema': 'sgrt.saratov.document_primary2010_sensitivity.v1',
               'documented_compositions': int(members.system_id.nunique()),
               'membership_rows': len(members),
               'distinct_member_settlements': int(members.source_record_id.nunique()),
               'scope': 'Separate primary-number 2010 scenario for unchanged current documented memberships; original v1 and population foundation retained.',
               'by_membership_basis': counts,
               'member_primary2010_overlay_applied': int(evidence.primary2010_derived_evidence_applied.eq(True).sum()),
               'members_with_2010_population_scope_comparability_unverified': int(evidence.primary2010_population_scope_comparability_unverified.eq(True).sum()),
               'population_foundation_modified': False,
               'historical_membership_or_boundary_equivalence_established': False,
               'limitations': ['Primary numerical observations are not proof of identical population scope, boundaries or correct intercensus identity chains.',
                              'The geographic compositions come from current documents, not reconstructed 2002 or 2010 service areas.',
                              'Document geography coverage remains independent of completeness of the admitted census subset.',
                              'Baseline zero primary-numeric three-census rows refers only to its selected 2010 evidence, not absence of available primary data.']}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in [('primary2010_demographic_components', components),
                        ('primary2010_demographic_profiles', profiles),
                        ('primary2010_profile_comparison', comparison),
                        ('primary2010_member_evidence', evidence)]:
        frame.to_parquet(output / (name + '.parquet'), index=False, compression='zstd')
        frame.to_csv(output / (name + '.csv'), index=False)
    (output / 'primary2010_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--membership', type=Path, required=True)
    parser.add_argument('--baseline-profiles', type=Path, required=True)
    parser.add_argument('--primary-context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.membership, args.baseline_profiles, args.primary_context, args.output), ensure_ascii=False, indent=2))
