#!/usr/bin/env python3
"""Independently reconstruct common primary memberships and upper associations.

No production allocation/promotion function is imported. The zero-level check
uses a three-column provider pivot; upper checks rebuild raw route eligibility,
positive-demand constraints and whole-child partitions. This verifies an
explicit scenario, not observed trips or clinical suitability.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit_function_weights import profile_winners, FAMILIES
from lower_profile_quality import part_inventory, sha256

STAGES = [('01_physician_primary', ['medical_physician_primary'], 30.),
          ('02_hospital_and_college', ['medical_inpatient', 'vocational_education'], 60.),
          ('03_specialized_university_shopping', ['medical_specialized', 'higher_education', 'shopping_centre'], 90.),
          ('04_hightech_reported_profile', ['medical_hightech_licensed'], 120.)]


def read_frame(path):
    return pd.read_csv(path) if path.suffix == '.csv' else pd.read_parquet(path)


def zero_check(edges, reference, centres, original_service, directory):
    core = edges[edges.service_family.isin(FAMILIES)]
    if core.duplicated(['origin_id', 'service_family']).any() or not core.groupby('origin_id').service_family.nunique().eq(3).all():
        raise ValueError('Expected the complete unique three-function outcome axis')
    ids = pd.Index(sorted(core.origin_id.unique()), name='origin_id')
    selected = core[core.l0_admitted & core.provider_settlement_id.notna()]
    providers = selected.pivot(index='origin_id', columns='service_family', values='provider_settlement_id').reindex(index=ids, columns=FAMILIES).fillna('').to_numpy()
    winner, tied, maximum = profile_winners(providers, [1., 1., 1.])
    known = (providers != '').sum(axis=1)
    mapping = original_service[['centre_settlement_id', 'star_id']].drop_duplicates()
    if not mapping.centre_settlement_id.is_unique:
        raise ValueError('Conflicting original centre identities')
    lookup = mapping.set_index('centre_settlement_id').star_id
    lookup = lookup.reindex(centres.centre_settlement_id).dropna()
    registered = ids.isin(centres.centre_settlement_id)
    ref, _ = part_inventory(reference)
    ref = ref.dropna(subset=['source_record_id']).set_index('source_record_id')
    metadata = ref.reindex(ids)
    expected = pd.DataFrame({'leading_target_id': winner, 'known_function_count': known,
        'maximum_support_count': maximum.astype(int)}, index=ids)
    expected['unit_id'] = expected.leading_target_id.map(lookup)
    expected['primary_centre_id'] = expected.leading_target_id.where(expected.unit_id.notna())
    status = np.full(len(ids), 'no_known_direction_not_no_dependency', dtype=object)
    status[(known > 0) & tied] = 'distributed_equal_known_support'
    self_leader = (winner == ids.to_numpy()) & (winner != '')
    outside = (winner != '') & ~self_leader & expected.unit_id.isna().to_numpy()
    status[(winner != '') & self_leader] = 'local_leading_profile_without_registered_external_role'
    status[outside] = 'leading_provider_not_registered_centre_requires_review'
    assigned = expected.unit_id.notna().to_numpy()
    status[assigned & (maximum == 1)] = 'one_known_function_primary_provisional'
    status[assigned & (maximum == 2)] = 'two_function_primary_partial'
    status[assigned & (maximum == 2) & (known == 3)] = 'two_of_three_function_primary'
    status[assigned & (maximum == 3)] = 'three_function_primary'
    expected.loc[registered, 'unit_id'] = ids.to_series().loc[registered].map(lookup)
    expected.loc[registered, 'primary_centre_id'] = ids[registered]
    status[registered] = 'registered_centre_preserved_as_self_anchor'
    local = self_leader & ~registered
    for mask, targets, label in [
        (local, ids.to_numpy(), 'local_single_site_profile_not_external_centre'),
        (outside, winner, 'provider_context_primary_requires_review')]:
        expected.loc[mask, 'unit_id'] = ['local:' + hashlib.sha256(str(v).encode()).hexdigest()[:24] for v in targets[mask]]
        expected.loc[mask, 'primary_centre_id'] = targets[mask]
        status[mask] = label
    expected['membership_status'] = status
    expected['equally_supported_targets'] = np.where(maximum >= 2, 1, known)
    primary = expected.primary_centre_id.fillna('').to_numpy()
    expected['primary_centre_function_support_count'] = (providers == primary[:, None]).sum(axis=1)
    expected.loc[expected.unit_id.isna(), 'primary_centre_function_support_count'] = np.nan
    actual = pd.read_parquet(directory / 'memberships.parquet').set_index('origin_id')
    if not actual.index.equals(ids):
        raise ValueError('Origin axis/order differs')
    reference_columns = ['name', 'region', 'district', 'lat', 'lon', 'population_2021',
                         'population_role', 'budget_population_credit', 'part_status']
    pd.testing.assert_frame_equal(metadata[reference_columns], actual[reference_columns], check_dtype=False)
    expected['positive_whole_origin'] = (metadata.population_2021.gt(0)
        & metadata.part_status.eq('unmarked_whole_place_record')
        & metadata.population_role.isin(['ordinary_settlement_record', 'external_context_nonadditive']))
    result = {'origin_records': len(ids), 'reference_fields_unchanged_all_rows': True, 'mismatches': {}}
    for column in ['unit_id', 'primary_centre_id', 'membership_status', 'known_function_count',
                   'maximum_support_count', 'equally_supported_targets', 'leading_target_id', 'primary_centre_function_support_count', 'positive_whole_origin']:
        left = expected[column].astype(object).where(expected[column].notna(), '')
        right = actual[column].astype(object).where(actual[column].notna(), '')
        result['mismatches'][column] = int(left.ne(right).sum())
    # The support after self-anchoring must refer to the actual primary target.
    fraction = expected.primary_centre_function_support_count / 3.
    result['mismatches']['primary_support_fraction'] = int((~np.isclose(
        fraction.to_numpy(dtype=float), pd.to_numeric(actual.primary_support_fraction_of_all_three_functions).to_numpy(dtype=float, na_value=np.nan), equal_nan=True)).sum())
    new_service = pd.read_parquet(directory / 'service_memberships.parquet')
    pd.testing.assert_frame_equal(original_service.reset_index(drop=True),
        new_service[original_service.columns].reset_index(drop=True), check_dtype=False)
    units = pd.read_parquet(directory / 'units.parquet')
    registered_units = units[units.is_registered_external_serving_centre].reset_index(drop=True)
    pd.testing.assert_frame_equal(centres.reset_index(drop=True), registered_units[centres.columns], check_dtype=False)
    expected_consistent = units.core_origin_id.map(expected.unit_id).eq(units.unit_id)
    core_metadata = ref.reindex(units.core_origin_id)
    eligible = (core_metadata.population_2021.gt(0).to_numpy()
        & core_metadata.part_status.eq('unmarked_whole_place_record').to_numpy()
        & core_metadata.analysis_origin.fillna(False).to_numpy()
        & units.own_known_basic_function_count.gt(0).to_numpy()
        & core_metadata.population_role.isin(['ordinary_settlement_record', 'external_context_nonadditive']).to_numpy())
    result['mismatches']['unit_core_membership_consistency'] = int(expected_consistent.ne(units.core_membership_consistent).sum())
    result['mismatches']['unit_parent_eligibility'] = int((eligible != units.eligible_as_higher_parent.to_numpy()).sum())
    result['mismatches']['unit_child_eligibility'] = int(((eligible & expected_consistent.to_numpy()) != units.eligible_as_higher_child.to_numpy()).sum())
    old_pairs = pd.MultiIndex.from_frame(original_service[['origin_id', 'centre_settlement_id']])
    positive_assigned = actual[actual.positive_whole_origin & actual.primary_centre_id.isin(centres.centre_settlement_id)]
    assigned_pairs = pd.MultiIndex.from_arrays([positive_assigned.index, positive_assigned.primary_centre_id])
    result['positive_primary_pairs_outside_original_footprints'] = int((~assigned_pairs.isin(old_pairs)).sum())
    result['original_service_pairs_equal'] = len(original_service)
    result['original_centres_equal'] = len(centres)
    result['unresolved_origin_records'] = int(actual.unit_id.isna().sum())
    return result, actual.reset_index(), units


def upper_checks(members, unitmeta, original_service, directory, route_directory, medical_directory):
    eligible_parent = set(unitmeta.loc[unitmeta.eligible_as_higher_parent.fillna(False), 'unit_id'])
    eligible_child = set(unitmeta.loc[unitmeta.eligible_as_higher_child.fillna(False), 'unit_id'])
    demand = set(members.loc[members.positive_whole_origin, 'origin_id'])
    results = []
    for folder, families, declared_minutes in STAGES:
        target = directory / folder
        if not (target / 'summary.json').is_file():
            break
        reported = json.loads((target / 'summary.json').read_text())
        # The checked time is recorded explicitly; no calibration is inferred.
        minutes = float(reported['minutes'])
        crosswalk = pd.read_parquet(target / 'child_parent_crosswalk.parquet')
        territorial = bool(reported.get('territorial_membership_applied', True))
        primary = members.loc[members.unit_id.notna(), ['origin_id', 'unit_id']]
        owners = primary.set_index('origin_id').unit_id
        extra = original_service[['centre_settlement_id', 'origin_id']].merge(
            primary.rename(columns={'origin_id': 'centre_settlement_id'}), on='centre_settlement_id', how='inner')
        guard = pd.concat([primary, extra[['origin_id', 'unit_id']]], ignore_index=True).drop_duplicates()
        guard = guard[guard.origin_id.isin(demand)]
        frames = []
        for family in families:
            route = pd.read_parquet((medical_directory if family.startswith('medical_') else route_directory) / (family + '.parquet'))
            columns = [c for c in ['origin_id', 'provider_settlement_id', 'cost_minutes', 'road_endpoint_accepted',
                                   'known_local_supply', 'provider_named_child_only_contingent'] if c in route]
            outcomes = guard.merge(route[columns], on='origin_id', how='left', validate='many_to_one')
            cost = pd.to_numeric(outcomes.cost_minutes, errors='coerce')
            endpoint = outcomes.get('road_endpoint_accepted', pd.Series(False, index=outcomes.index)).fillna(False).eq(True)
            local = outcomes.get('known_local_supply', pd.Series(False, index=outcomes.index)).fillna(False).eq(True)
            child_only = outcomes.get('provider_named_child_only_contingent', pd.Series(False, index=outcomes.index)).fillna(False).eq(True)
            outcomes['owner'] = outcomes.provider_settlement_id.map(owners)
            outcomes['usable'] = (outcomes.provider_settlement_id.notna() & outcomes.owner.notna()
                & np.isfinite(cost) & cost.ge(0) & cost.le(minutes + 1e-8) & (endpoint | local) & ~child_only)
            frames.append(outcomes[['origin_id', 'unit_id', 'owner', 'usable']])
        outcomes = pd.concat(frames, ignore_index=True)
        good = outcomes.groupby('unit_id').usable.sum()
        sizes = guard.groupby('unit_id').size()
        targets = outcomes.loc[outcomes.usable].groupby('unit_id').owner.agg(set)
        expected = {}
        for uid in set(primary.unit_id):
            choices = targets.get(uid, set())
            complete = (sizes.get(uid, 0) > 0 and good.get(uid, 0) == sizes.get(uid, 0) * len(families)
                        and len(choices) == 1 and uid in eligible_child)
            expected[uid] = next(iter(choices)) if complete else None
        anchors = {uid for uid, dest in expected.items() if uid == dest and uid in eligible_parent}
        leaders = {uid: dest if dest in anchors else uid for uid, dest in expected.items()}
        groups = defaultdict(set)
        for uid, leader in leaders.items():
            groups[leader].add(uid)
        expected_partition = {frozenset(values) for values in groups.values()}
        actual_partition = {frozenset(group.child_unit_id) for _, group in crosswalk.groupby('parent_unit_id')}
        expected_targets = pd.Series(expected).reindex(crosswalk.child_unit_id).fillna('').to_numpy()
        actual_targets = crosswalk.destination_unit_id.fillna('').to_numpy()
        next_members = pd.read_parquet(target / ('memberships.parquet' if territorial else 'referral_memberships.parquet'))
        if crosswalk.child_unit_id.duplicated().any() or set(crosswalk.child_unit_id) != set(primary.unit_id):
            raise ValueError('Child crosswalk duplicates or omits a lower unit')
        expected_member_units = members.unit_id.map(crosswalk.set_index('child_unit_id').parent_unit_id)
        expected_member_units = expected_member_units.astype(object).where(expected_member_units.notna(), '')
        actual_member_units = next_members.unit_id.astype(object).where(next_members.unit_id.notna(), '')
        row = {'stage': folder, 'families': families, 'time_limit_minutes': minutes,
            'lower_units': len(expected), 'positive_functional_constraint_pairs': len(guard),
            'candidate_destination_mismatches': int((expected_targets != actual_targets).sum()),
            'parent_partition_symmetric_difference': len(expected_partition ^ actual_partition),
            'individual_parent_membership_mismatches': int(expected_member_units.ne(actual_member_units).sum()),
            'origin_axis_unchanged': bool(next_members.origin_id.equals(members.origin_id)),
            'unresolved_mask_unchanged': bool(next_members.unit_id.notna().equals(members.unit_id.notna())),
            'territorial_membership_applied': territorial,
            'resulting_partition_units': int(next_members.unit_id.nunique())}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if territorial:
            anchor_by_new = {new: leaders[group.child_unit_id.iloc[0]] for new, group in crosswalk.groupby('parent_unit_id')}
            eligible_parent = {new for new, anchor in anchor_by_new.items() if anchor in eligible_parent}
            eligible_child = {new for new, group in crosswalk.groupby('parent_unit_id') if all(uid in eligible_child for uid in group.child_unit_id)}
            members = next_members
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['edges', 'reference', 'centres', 'original-service-memberships', 'zero-directory',
                'upper-directory', 'route-directory', 'medical-route-directory', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--require-complete', action='store_true')
    args = parser.parse_args()
    original_service = pd.read_parquet(args.original_service_memberships)
    zero, members, unitmeta = zero_check(pd.read_parquet(args.edges, columns=['origin_id', 'provider_settlement_id',
        'service_family', 'l0_admitted']), pd.read_parquet(args.reference), read_frame(args.centres),
        original_service, args.zero_directory)
    upper = upper_checks(members, unitmeta, original_service, args.upper_directory,
                         args.route_directory, args.medical_route_directory)
    paths = {'edges': args.edges, 'reference': args.reference, 'centres': args.centres,
             'original_service_memberships': args.original_service_memberships,
             'audit_code': Path(__file__), 'profile_audit_code': Path(__file__).with_name('audit_function_weights.py'),
             'source_grain_helper': Path(__file__).with_name('lower_profile_quality.py')}
    for name in ['memberships', 'units', 'service_memberships']:
        paths['zero/' + name] = args.zero_directory / (name + '.parquet')
    for index, (folder, families, _) in enumerate(STAGES[:len(upper)]):
        for name in ['summary.json', 'child_parent_crosswalk.parquet']:
            paths[folder + '/' + name] = args.upper_directory / folder / name
        membership_name = 'memberships.parquet' if upper[index]['territorial_membership_applied'] else 'referral_memberships.parquet'
        paths[folder + '/' + membership_name] = args.upper_directory / folder / membership_name
        for family in families:
            paths['route/' + family] = (args.medical_route_directory if family.startswith('medical_') else args.route_directory) / (family + '.parquet')
    summary = {'schema': 'sgrt.independent_common_results_audit.v1',
        'zero': zero, 'upper': upper, 'stages_not_yet_present': [s[0] for s in STAGES[len(upper):]],
        'inputs_sha256': {name: sha256(path) for name, path in paths.items()},
        'scope': 'reconstruction of declared model outcomes; not external validation of actual trips or clinical eligibility'}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    failures = any(zero['mismatches'].values()) or zero['positive_primary_pairs_outside_original_footprints']
    failures |= any(r['candidate_destination_mismatches'] or r['parent_partition_symmetric_difference']
        or r['individual_parent_membership_mismatches']
        or not r['origin_axis_unchanged'] or not r['unresolved_mask_unchanged'] for r in upper)
    failures |= bool(args.require_complete and len(upper) != len(STAGES))
    if failures:
        raise SystemExit('Independent reconstruction differs; inspect the written summary')
    print(json.dumps({'zero_rows': zero['origin_records'], 'stages_checked': len(upper), 'mismatches': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
