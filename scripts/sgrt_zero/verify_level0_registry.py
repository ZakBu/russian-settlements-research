"""Independently reconcile a direct L0 registry with screened service choices.

No centre builder, registry builder, grouping helper or diameter helper is
imported. Physical actors are screened from the reference, not from population
budget credit. The check validates the model's records, not observed trips.
"""
from __future__ import annotations

import argparse
import hashlib
import gzip
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.spatial.distance import cdist

CORE = frozenset(['school', 'medical_basic', 'grocery'])
ORDINARY = 'ordinary_settlement_record'
CONTEXT = 'external_context_nonadditive'
EARTH_RADIUS_KM = 6371.0088
TYPES = {3: 'recorded_three_basic_functions', 2: 'recorded_two_basic_functions',
         1: 'recorded_one_basic_function', 0: 'own_offer_unknown'}
REFERENCE_COLUMNS = ['source_record_id', 'name', 'region', 'district', 'lat', 'lon',
                     'population_2021', 'population_role', 'analysis_origin',
                     'budget_population_credit', 'settlement_type_2021',
                     'is_settlement_part', 'settlement_is_part', 'population_unit_is_part']
EDGE_COLUMNS = ['origin_id', 'provider_settlement_id', 'service_family',
                'provider_site_id', 'cost_minutes', 'admission_limit_minutes',
                'l0_admitted', 'local_service_present', 'scenario_id',
                'provider_identity_evidence_tier', 'provider_np_identity_basis',
                'provider_np_identity_is_cartographic', 'school_stage_unknown',
                'origin_road_endpoint_accepted', 'source_id', 'source_year']


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def truth(series):
    # Unlike astype(bool), the string "False" is false.
    return series.astype('string').str.strip().str.lower().isin(['true', '1', 'yes'])


def key_set(frame, columns):
    return set(map(tuple, frame[columns].astype(str).itertuples(index=False, name=None)))


def compare_keys(expected, actual, label):
    require(expected == actual,
            f'{label}: missing={len(expected-actual)}, unexpected={len(actual-expected)}; '
            f'missing_examples={sorted(expected-actual)[:3]}, '
            f'unexpected_examples={sorted(actual-expected)[:3]}')


def compare_values(actual, expected, label, *, numeric=False):
    require(len(actual) == len(expected), label + ': row count differs')
    if numeric:
        a = pd.to_numeric(actual, errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        b = pd.to_numeric(expected, errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        same = np.isclose(a, b, rtol=0, atol=1e-8, equal_nan=True)
    else:
        a = actual.astype('string').fillna('__NULL__').to_numpy()
        b = expected.astype('string').fillna('__NULL__').to_numpy()
        same = a == b
    require(np.all(same), label + ': values differ at rows ' + str(np.flatnonzero(~same)[:5].tolist()))


def compare_json_sets(actual, expected, label):
    for row, (a, b) in enumerate(zip(actual, expected)):
        values = json.loads(a)
        require(isinstance(values, list) and len(values) == len(set(values)) and set(values) == set(b),
                f'{label}: set mismatch at row {row}')


def sphere_diameter(latitude, longitude):
    """Maximum spherical distance from Euclidean chords of unit vectors.

    This differs from the builder's haversine loop and does not use an ellipsoid.
    A chunked cross-distance array keeps large catchments bounded in memory.
    """
    coordinates = np.column_stack([np.asarray(latitude, dtype=float),
                                   np.asarray(longitude, dtype=float)])
    coordinates = np.unique(coordinates[np.isfinite(coordinates).all(axis=1)], axis=0)
    if not len(coordinates):
        return float('nan')
    if len(coordinates) == 1:
        return 0.
    lat, lon = np.deg2rad(coordinates.T)
    unit = np.column_stack([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
    chord = 0.
    for start in range(0, len(unit), 128):
        chord = max(chord, float(cdist(unit[start:start+128], unit, metric='euclidean').max()))
    return float(2*EARTH_RADIUS_KM*np.arcsin(min(1., chord/2)))


def validate_hold_records(reference, records):
    """Check raw census identity and coordinates without a builder import."""
    ref = reference[reference.source_record_id.notna()].set_index('source_record_id')
    require(ref.index.is_unique, 'Coordinate hold reference IDs are duplicated')
    held = set()
    for record in records:
        uid = record['source_record_id']
        require(uid not in held, 'Duplicate coordinate hold ID')
        require(uid in ref.index, 'Coordinate hold ID absent from reference: ' + uid)
        expected = record['reference_fields']
        for field in ['name', 'settlement_type_2021', 'region', 'district', 'lat', 'lon']:
            require(field in expected, 'Coordinate hold missing reference field: ' + field)
            observed = ref.at[uid, field]
            if field in ['lat', 'lon']:
                same = np.isfinite(float(observed)) and float(observed) == float(expected[field])
            else:
                same = str(observed) == str(expected[field])
            require(same, 'Coordinate hold reference mismatch: ' + uid + ' ' + field)
        held.add(uid)
    return held


def verify_frames(edges, centres, members, links, reference, *, diameter_cases=50, hold_records=()):
    """Verify every ID/pair/function/quality field, then the largest diameters."""
    ref = reference[reference.source_record_id.notna()].copy().set_index('source_record_id')
    require(ref.index.is_unique, 'Reference has duplicate non-null census IDs')
    held_ids = validate_hold_records(reference, hold_records)
    held_edges = edges.origin_id.isin(held_ids) | edges.provider_settlement_id.isin(held_ids)
    require(not (truth(edges.l0_admitted) & held_edges).any(),
            'An admitted outcome uses a coordinate-held origin or provider NP')
    population = pd.to_numeric(ref.population_2021, errors='coerce')
    whole = ~ref['name'].fillna('').astype(str).str.contains(r'\bчаст(?:ь|и)\b|\(\s*част(?:ь|и)\s*(?:\d+|[ivx]+)?\s*\)', case=False, regex=True)
    for field in ['is_settlement_part', 'settlement_is_part', 'population_unit_is_part']:
        if field in ref:
            whole &= ~truth(ref[field])
    active = truth(ref.analysis_origin)
    credited = truth(ref.budget_population_credit)
    actor = active & whole & population.gt(0) & ref.population_role.eq(ORDINARY)
    centre_ok = active & whole & population.gt(0) & ref.population_role.isin([ORDINARY, CONTEXT])
    core = edges[edges.service_family.isin(CORE)].copy()
    require(not core.duplicated(['origin_id', 'service_family']).any(), 'Duplicate basic origin/function choices')
    require(set(core.origin_id) == set(ref.index[active]), 'Basic edge origins differ from reference analysis origins')
    require(core.groupby('origin_id').service_family.nunique().eq(3).all(), 'An origin lost a basic-function outcome')
    require(set(core.provider_settlement_id.dropna()) <= set(ref.index), 'Unknown provider census identity')
    require(core.scenario_id.nunique() == 1, 'Select one explicit scenario')
    cost = pd.to_numeric(core.cost_minutes, errors='coerce')
    caps = pd.to_numeric(core.admission_limit_minutes, errors='coerce')
    local = truth(core.local_service_present)
    provider_known = core.provider_site_id.notna()
    require((caps.notna() & np.isfinite(caps) & caps.gt(0)).all(), 'Basic edge time cap is invalid')
    require(core.assign(_cap=caps).groupby('service_family')._cap.nunique().eq(1).all(), 'Inconsistent scenario time caps')
    require(not cost.lt(0).any(), 'Invalid negative travel time')
    expected_admission = provider_known & (local | (cost.notna() & cost.le(caps)))
    expected_admission &= ~(core.origin_id.isin(held_ids) | core.provider_settlement_id.isin(held_ids))
    require(truth(core.l0_admitted).equals(expected_admission), 'Declared admission differs from provider/local/time evidence')
    require(not (local & provider_known & (core.provider_settlement_id.isna() | core.provider_settlement_id.ne(core.origin_id).fillna(True))).any(),
            'Known local presence uses a different NP identity')
    require(not (local & provider_known & ~np.isclose(cost.fillna(np.inf), 0., rtol=0, atol=1e-8)).any(),
            'NP-local presence does not preserve its explicit zero-time assumption')
    admitted = core[expected_admission & core.provider_settlement_id.notna()].copy()
    external = admitted[admitted.origin_id.isin(ref.index[actor])
                        & admitted.provider_settlement_id.isin(ref.index[centre_ok])
                        & admitted.origin_id.ne(admitted.provider_settlement_id)]
    expected_external = key_set(external, ['provider_settlement_id', 'origin_id'])
    expected_centres = {c for c, _ in expected_external}
    require(centres.centre_settlement_id.is_unique, 'Duplicate registered centre census IDs')
    require(centres.star_id.is_unique, 'Duplicate registry star IDs')
    compare_keys(expected_centres, set(centres.centre_settlement_id), 'All centre identities')
    require(not members.duplicated(['centre_settlement_id', 'origin_id']).any(), 'Duplicate centre-member pair or anchor')
    expected_pairs = expected_external | {(c, c) for c in expected_centres}
    actual_pairs = key_set(members, ['centre_settlement_id', 'origin_id'])
    compare_keys(expected_pairs, actual_pairs, 'All direct member pairs plus one anchor')
    star_map = centres.set_index('centre_settlement_id').star_id
    compare_values(members.star_id, members.centre_settlement_id.map(star_map), 'Member/centre star identity')
    expected_role = np.where(members.origin_id.eq(members.centre_settlement_id), 'centre', 'direct_surroundings')
    compare_values(members.member_role, pd.Series(expected_role, index=members.index), 'Member role')
    key = ['origin_id', 'service_family', 'provider_settlement_id']
    expected_links = admitted[admitted.provider_settlement_id.isin(expected_centres)]
    require(not links.duplicated(key).any(), 'Duplicate registered basic links')
    compare_keys(key_set(expected_links, key), key_set(links, key), 'Every retained basic link')
    old = expected_links.set_index(key).sort_index()
    new = links.set_index(key).sort_index()
    for column in ['provider_site_id', 'cost_minutes', 'admission_limit_minutes', 'provider_identity_evidence_tier',
                   'provider_np_identity_basis', 'source_id', 'source_year', 'school_stage_unknown']:
        if column in old:
            require(column in new, 'Basic links lost metadata: ' + column)
            compare_values(new[column], old[column], 'Basic link ' + column,
                           numeric=column in ['cost_minutes', 'admission_limit_minutes'])
    local_rows = admitted[admitted.origin_id.eq(admitted.provider_settlement_id)]
    own_sets = local_rows.groupby('origin_id').service_family.agg(set).to_dict()
    centre_ids = centres.centre_settlement_id
    expected_own = centre_ids.map(lambda value: own_sets.get(value, set()))
    expected_own_count = expected_own.map(len)
    compare_values(centres.own_known_basic_function_count, expected_own_count, 'Own function count', numeric=True)
    compare_values(centres.type_code, expected_own_count.map(TYPES), 'Own-function completeness type')
    require(centres.type_label.notna().all() and centres.type_label.astype(str).str.strip().ne('').all(),
            'An L0 centre has no explanatory type label')
    compare_json_sets(centres.own_known_basic_functions_json, expected_own, 'Own function sets')
    if 'centre_own_selected_core_family_count' in centres:
        compare_values(centres.centre_own_selected_core_family_count, expected_own_count,
                       'Inherited own function count', numeric=True)
    external_counts = external.groupby('provider_settlement_id').origin_id.nunique()
    compare_values(centres.external_participant_count, centre_ids.map(external_counts), 'External participant counts', numeric=True)
    external_support = external.groupby(['provider_settlement_id', 'origin_id']).service_family.nunique()
    max_three = external_support.eq(3).groupby(level=0).sum()
    compare_values(centres.full_service_centre_without_same_three_external_participant,
                   expected_own_count.eq(3) & centre_ids.map(max_three).fillna(0).eq(0),
                   'Full local centre versus external three-way coincidence')
    if 'all_three_core_external_positive_whole' in centres:
        compare_values(centres.all_three_core_external_positive_whole, centre_ids.map(max_three).fillna(0),
                       'Inherited three-way external support', numeric=True)
    group_pair_index = pd.MultiIndex.from_frame(members[['centre_settlement_id', 'origin_id']])
    # Group direct choices independently from the builder's per-centre loop.
    all_admitted = edges[truth(edges.l0_admitted) & edges.provider_settlement_id.notna()]
    pair_groups = all_admitted.groupby(['provider_settlement_id', 'origin_id'])
    all_sets = pair_groups.service_family.agg(set).reindex(group_pair_index)
    all_sets = all_sets.map(lambda value: value if isinstance(value, set) else set())
    core_sets = all_sets.map(lambda value: value & CORE)
    compare_values(members.core_family_count, core_sets.map(len).reset_index(drop=True), 'Member basic function count', numeric=True)
    compare_json_sets(members.core_families_json, core_sets, 'Member basic function sets')
    if 'all_families_json' in members:
        compare_json_sets(members.all_families_json, all_sets, 'Member all-function sets')
    if 'maximum_directed_minutes' in members:
        maximum = pair_groups.cost_minutes.max().reindex(group_pair_index)
        compare_values(members.maximum_directed_minutes, maximum.reset_index(drop=True),
                       'Member maximum direct time across retained functions', numeric=True)
    member_ref = ref.reindex(members.origin_id)
    for column in ['name', 'region', 'district', 'lat', 'lon', 'population_2021', 'population_role',
                   'budget_population_credit', 'analysis_origin']:
        require(column in members, 'Registry membership lost reference metadata: ' + column)
        compare_values(members[column], member_ref[column].reset_index(drop=True), 'Member reference ' + column,
                       numeric=column in ['lat', 'lon', 'population_2021'])
    centre_ref = ref.reindex(centre_ids)
    for column, original in [('centre_name', 'name'), ('centre_region', 'region'),
                             ('centre_population_2021_source_value', 'population_2021'),
                             ('centre_population_budget_credit', 'budget_population_credit')]:
        compare_values(centres[column], centre_ref[original].reset_index(drop=True), 'Centre reference ' + original,
                       numeric=original == 'population_2021')
    context = centre_ids.map(ref.population_role).eq(CONTEXT)
    for column, expected in [('centre_in_analysis_origin', centre_ids.map(active)),
                             ('centre_unmarked_whole_record', centre_ids.map(whole)),
                             ('centre_positive_population_known', centre_ids.map(population).gt(0)),
                             ('centre_population_is_nonadditive_context', context),
                             ('centre_ordinary_spatial_or_nonadditive_context',
                              centre_ids.map(ref.population_role).isin([ORDINARY, CONTEXT]))]:
        compare_values(centres[column], expected, 'Centre reference quality ' + column)
    if 'positive_whole_spatial' in members:
        compare_values(members.positive_whole_spatial, members.origin_id.map(actor), 'Member physical actor eligibility')
    if 'part_status' in members:
        require(members.part_status.eq('unmarked_whole_place_record').all(), 'Registered whole actors contain source parts')
    coordinates = ref.dropna(subset=['lat', 'lon']).groupby(['lat', 'lon']).size()
    member_coordinates = pd.MultiIndex.from_frame(member_ref[['lat', 'lon']])
    coincident = coordinates.reindex(member_coordinates).fillna(0).to_numpy() > 1
    if 'coincident_coordinate_requires_review' in members:
        compare_values(members.coincident_coordinate_requires_review, pd.Series(coincident), 'Coincident reference-point quality')
    member_credit = members.origin_id.map(credited).fillna(False)
    member_ordinary = members.origin_id.map(ref.population_role).eq(ORDINARY)
    expected_budget = members.origin_id.map(population).where(member_credit & member_ordinary & members.origin_id.map(active))
    compare_values(members.budget_population_within_star, expected_budget, 'Member credited budget, not total population', numeric=True)
    uncredited = member_ordinary & members.origin_id.map(population).gt(0) & ~member_credit
    uncredited_counts = uncredited.groupby(members.centre_settlement_id).sum()
    expected_uncredited = centre_ids.map(uncredited_counts).fillna(0)
    compare_values(centres.positive_uncredited_member_records, expected_uncredited, 'Positive uncredited actors retained', numeric=True)
    compare_values(centres.population_budget_partial, expected_uncredited.gt(0) | context, 'Partial/nonadditive population budget flag')
    budget_sum = expected_budget.groupby(members.centre_settlement_id).sum(min_count=1)
    compare_values(centres.population_2021_credited_budget_sum_not_total_population,
                   centre_ids.map(budget_sum), 'Centre credited budget sum, not total population', numeric=True)
    for column in ['population_is_additive_across_stars']:
        if column in members:
            require(not truth(members[column]).any(), 'Membership claims additive population across overlapping stars')
    require(not truth(centres.exclusive_partition).any(), 'Direct catchments were labelled an exclusive partition')
    require(not truth(centres.observed_trips_verified).any(), 'Registry incorrectly claims observed-trip verification')
    require(pd.to_numeric(centres.level).eq(0).all(), 'Registry contains a nonzero level')
    require(truth(centres.unestablished_functions_are_not_confirmed_absent).all(), 'Missing offers were not kept unknown')
    tier = expected_links.get('provider_identity_evidence_tier', pd.Series(None, index=expected_links.index))
    proxy_counts = tier.eq('dated_cartographic_locality_containment').groupby(expected_links.provider_settlement_id).sum()
    link_counts = expected_links.groupby('provider_settlement_id').size()
    proxy_count = centre_ids.map(proxy_counts).fillna(0)
    compare_values(centres.selected_links_with_cartographic_ownership, proxy_count, 'Cartographic link-quality counts', numeric=True)
    compare_values(centres.selected_basic_links, centre_ids.map(link_counts).fillna(0), 'Basic link counts', numeric=True)
    compare_values(centres.ownership_evidence_class,
                   pd.Series(np.where(proxy_count.gt(0), 'includes_dated_cartographic_proxy',
                                      'retained_literal_or_registry_evidence'), index=centres.index),
                   'Ownership evidence class')
    if 'ownership_uses_cartographic_proxy' in links:
        actual_tier = links.get('provider_identity_evidence_tier', pd.Series(None, index=links.index))
        compare_values(links.ownership_uses_cartographic_proxy,
                       actual_tier.eq('dated_cartographic_locality_containment'), 'Basic link cartographic ownership flag')
    checks = []
    ranked = centres.sort_values(['core_diameter_km', 'centre_settlement_id'], ascending=[False, True]).head(diameter_cases)
    member_groups = {c: g for c, g in members.groupby('centre_settlement_id')}
    car_max = external.groupby('provider_settlement_id').cost_minutes.max()
    for row in ranked.itertuples():
        group = member_groups[row.centre_settlement_id]
        fresh = sphere_diameter(group.lat, group.lon)
        require(np.isclose(fresh, row.core_diameter_km, rtol=0, atol=1e-7, equal_nan=True),
                f'Spherical diameter mismatch: {row.centre_settlement_id}: {fresh} != {row.core_diameter_km}')
        checks.append({'centre_settlement_id': row.centre_settlement_id, 'name': row.centre_name,
                       'member_records': len(group), 'reported_diameter_km': float(row.core_diameter_km),
                       'independent_spherical_diameter_km': fresh,
                       'maximum_selected_external_basic_car_minutes': float(car_max.loc[row.centre_settlement_id])})
    pair_sha = hashlib.sha256(json.dumps(sorted(expected_pairs), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return {'independent_of_centre_and_registry_builders': True,
            'coordinate_hold_ids_independently_checked': sorted(held_ids),
            'all_admitted_outcomes_exclude_coordinate_held_NPs': True,
            'registered_centres': len(expected_centres), 'centre_member_pairs': len(expected_pairs),
            'external_pairs': len(expected_external), 'all_centre_ids_equal': True,
            'all_direct_pairs_and_single_anchors_equal': True, 'all_own_function_sets_and_types_equal': True,
            'all_member_reference_metadata_equal': True, 'all_population_budgets_and_partial_flags_equal': True,
            'all_ownership_evidence_classes_equal': True, 'all_retained_basic_links_equal': True,
            'positive_uncredited_member_rows': int(uncredited.sum()),
            'by_own_known_basic_function_count': {str(k): int(v) for k, v in expected_own_count.value_counts().sort_index().items()},
            'pair_semantic_sha256': pair_sha,
            'admission_recomputed_for_all_basic_edges': len(core),
            'all_external_basic_car_times_within_source_caps': True,
            'basic_time_caps_minutes': {str(k): float(v) for k, v in core.groupby('service_family').admission_limit_minutes.first().items()},
            'external_time_is_to_selected_physical_offer_not_centre_point_or_household': True,
            'diameter_method': 'maximum pairwise unit-sphere chord, converted to arc',
            'earth_radius_km': EARTH_RADIUS_KM, 'ellipsoid_used': False,
            'largest_reported_diameters_independently_checked': len(checks), 'diameter_cases': checks,
            'car_time_not_converted_to_fixed_km_radius': True,
            'actual_trips_or_all_institution_suitability_verified': False,
            'road_component_details_not_recomputed_by_this_check': True}


def read_columns(path, desired):
    available = set(pq.ParquetFile(path).schema.names)
    return pd.read_parquet(path, columns=[c for c in desired if c in available])


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


DEFAULT_COORDINATE_HOLDS = Path(__file__).resolve().parents[2] / 'references/provenance/coordinate_holds_20261026.json'


def load_hold_manifest(path, repo_root=None):
    """Verify frozen evidence bytes directly, without the overlay helper."""
    repo_root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    require(path.is_file(), 'Required coordinate hold manifest is missing: ' + str(path))
    manifest = json.loads(path.read_text())
    records = manifest['records']
    require(isinstance(records, list), 'Coordinate hold records must be a list')
    evidence_hashes = {str(path): sha(path)}
    for record in records:
        require(record.get('evidence'), 'Coordinate hold has no frozen source proof')
        for evidence in record['evidence']:
            require(evidence.get('http_status') == 200, 'Coordinate hold evidence was not retrieved successfully')
            raw = repo_root / evidence['raw_path']
            require(raw.is_file(), 'Coordinate hold source proof missing: ' + str(raw))
            require(sha(raw) == evidence['sha256'], 'Coordinate hold source proof SHA mismatch: ' + str(raw))
            payload = raw.read_bytes()
            if 'bytes' in evidence:
                require(len(payload) == evidence['bytes'], 'Coordinate hold source proof size mismatch')
            if evidence.get('compression') == 'gzip':
                payload = gzip.decompress(payload)
                require(hashlib.sha256(payload).hexdigest() == evidence['uncompressed_sha256'],
                        'Coordinate hold decompressed source SHA mismatch')
            if evidence.get('required_text'):
                decoded = payload.decode(evidence.get('encoding', 'utf-8'))
                require(all(value in decoded for value in evidence['required_text']),
                        'Coordinate hold source lacks declared literal evidence')
            if evidence.get('object_fields'):
                objects = json.loads(payload)
                candidates = [item for item in objects if all(item.get(key) == value
                              for key, value in evidence['object_fields'].items())]
                require(len(candidates) == 1, 'Coordinate hold named source object is not unique')
                require(all(candidates[0].get('address', {}).get(key) == value
                            for key, value in evidence.get('address_fields', {}).items()),
                        'Coordinate hold named source address mismatch')
            evidence_hashes[str(raw)] = evidence['sha256']
            metadata = repo_root / evidence['metadata_path']
            require(metadata.is_file(), 'Coordinate hold HTTP metadata missing: ' + str(metadata))
            json.loads(metadata.read_text())
            evidence_hashes[str(metadata)] = sha(metadata)
    return records, evidence_hashes


def verify(scenario, registry, reference, output, coordinate_holds=DEFAULT_COORDINATE_HOLDS):
    inputs = [scenario/'daily_edges.parquet', registry/'level0_centres.parquet',
              registry/'level0_memberships.parquet', registry/'level0_basic_links.parquet', reference]
    hold_records, proof_hashes = load_hold_manifest(coordinate_holds)
    hashes = {str(p): sha(p) for p in inputs}
    hashes.update(proof_hashes)
    edges = read_columns(inputs[0], EDGE_COLUMNS)
    centres = pd.read_parquet(inputs[1])
    members = pd.read_parquet(inputs[2])
    links = read_columns(inputs[3], EDGE_COLUMNS + ['ownership_uses_cartographic_proxy'])
    result = verify_frames(edges, centres, members, links, read_columns(reference, REFERENCE_COLUMNS), hold_records=hold_records)
    require(hashes == {p: sha(Path(p)) for p in hashes}, 'An audit input changed during verification')
    result['inputs_sha256'] = hashes
    result['verification_code_sha256'] = sha(Path(__file__))
    result['inputs_unchanged'] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'diameter_cases'}, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['scenario', 'registry', 'reference', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--coordinate-holds', type=Path, default=DEFAULT_COORDINATE_HOLDS)
    args = parser.parse_args()
    verify(args.scenario, args.registry, args.reference, args.output, args.coordinate_holds)
