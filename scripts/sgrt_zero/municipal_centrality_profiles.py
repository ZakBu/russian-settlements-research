#!/usr/bin/env python3
"""Territorial scale comparisons on actual municipal workforce observations.

Never distribute municipal employment among settlements. The joined population
and care-address counts describe the *known 2021 parent-matched portion*, not a
certified reconstruction of a 2025 municipal boundary. Federal-city subject
totals are retained once and their wards excluded. Dominance intervals refer
to recorded components, not statistical confidence or inferred SGRT ranks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
try:
    from .municipal_workforce_source import classify_territory
except ImportError:
    from municipal_workforce_source import classify_territory

TOTAL = 'Всего по обследуемым видам экономической деятельности'
UPPER = 'Муниципальное образование верхнего уровня'
SUBJECT = 'Субъект РФ'
WARD = 'Внутригородская территория города федерального значения'
FEDERAL_CITIES = {'45000000': 'Москва', '40000000': 'Санкт-Петербург'}
COMPONENTS = ['partial_organisation_workers_2025_territorial',
              'medical_care_address_ids_in_known_2021_parent',
              'credited_population_2021_in_known_parent']


def federal_medical_stock(evidence, addresses):
    """Count actual care-address IDs by explicit federal-city address region.

    An address with unknown NP identity remains usable at the wider *reported*
    region scope. Subdivision/profile repetitions never multiply its count.
    """
    keys = ['UIDSPMO', 'IDADDRESS']
    loc = addresses[[*keys, 'address_region_normalized', 'source_record_id']].drop_duplicates()
    if loc.duplicated(keys).any():
        raise ValueError('Conflicting care-address regional identity')
    positive = evidence[keys].drop_duplicates().merge(loc, on=keys, how='inner', validate='one_to_one')
    regions = {'45000000': 'москва', '40000000': 'санкт петербург'}
    rows = []
    for code, region in regions.items():
        part = positive.loc[positive.address_region_normalized.eq(region)]
        known = set(part.loc[part.source_record_id.notna(), 'IDADDRESS'])
        all_ids = set(part.IDADDRESS.dropna())
        rows.append({'oktmo': code, 'federal_medical_address_ids_known': len(all_ids) if all_ids else np.nan,
                     'federal_medical_address_ids_without_np_identity': len(all_ids - known)})
    return pd.DataFrame(rows).set_index('oktmo')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def select_workforce(frame):
    selected = frame.loc[frame.year.eq(2025) & frame.indicator_period.eq('Январь-декабрь')
                         & frame.okved2.eq(TOTAL)].copy()
    if selected.duplicated('oktmo').any():
        raise ValueError('Conflicting annual total workforce observations per territory')
    selected['source_territory_class'] = selected.apply(classify_territory, axis=1)
    eligible = (selected.mun_level.eq(UPPER) & ~selected.mun_type.eq(WARD)) | (
        selected.mun_level.eq(SUBJECT) & selected.oktmo.isin(FEDERAL_CITIES))
    eligible &= selected.source_territory_class.isin([
        'municipal_territory_record', 'reported_federal_city_subject_total'])
    federal_scope = selected.oktmo.astype(str).str[:2].isin(['40', '45'])
    eligible &= ~federal_scope | (selected.mun_level.eq(SUBJECT) & selected.oktmo.isin(FEDERAL_CITIES))
    result = selected.loc[eligible].copy()
    if not result.indicator_code.eq('Y48423005').all() or not result.indicator_unit.eq('Человек').all():
        raise ValueError('Unexpected workforce indicator or unit')
    if result.indicator_value.notna().any() and result.indicator_value.dropna().lt(0).any():
        raise ValueError('Negative observed headcount')
    result = result.rename(columns={'indicator_value': COMPONENTS[0]})
    keep = ['oktmo', 'municipality', 'region_name', 'mun_level', 'mun_type', 'year',
            'indicator_period', 'indicator_name', 'indicator_unit', 'source_territory_class', COMPONENTS[0]]
    source_ward_type = selected.mun_type.eq(WARD)
    excluded_wards = source_ward_type & ~eligible
    excluded_groups = selected.source_territory_class.eq('group_of_municipalities_aggregate') & ~eligible & ~excluded_wards
    excluded_other = ~eligible & ~excluded_wards & ~excluded_groups
    if len(result) + int(excluded_wards.sum()) + int(excluded_groups.sum()) + int(excluded_other.sum()) != len(selected):
        raise AssertionError('Workforce source exclusions must partition the annual rows')
    return result[keep].reset_index(drop=True), {'annual_total_source_rows': len(selected),
        'selected_nonoverlapping_upper_scope_rows': len(result),
        'excluded_federal_ward_rows': int(excluded_wards.sum()),
        'excluded_group_aggregate_rows': int(excluded_groups.sum()),
        'excluded_other_scope_rows': int(excluded_other.sum()),
        'source_rows_with_federal_ward_type': int(source_ward_type.sum()),
        'retained_subject_rows_with_federal_ward_type': int((eligible & source_ward_type).sum()),
        'federal_city_subject_totals_kept_once': int(result.mun_level.eq(SUBJECT).sum())}


def build_profiles(workforce, reference, parent_context, medical_profiles, federal_medical=None):
    jobs, audit = select_workforce(workforce)
    ref = reference.loc[reference.source_record_id.notna()].copy()
    if not ref.source_record_id.is_unique:
        raise ValueError('Reference source identities must be unique')
    parents = parent_context.loc[parent_context.source_record_id.notna(),
        ['source_record_id', 'agri_municipality_code', 'parent_relation_rule']].copy()
    if not parents.source_record_id.is_unique or not medical_profiles.source_record_id.is_unique:
        raise ValueError('Parent/profile settlement keys must be unique')
    pairs = ref.merge(parents, on='source_record_id', how='left', validate='one_to_one')
    pairs = pairs.merge(medical_profiles[['source_record_id', 'medical_care_address_ids_known']],
                        on='source_record_id', how='left', validate='one_to_one')
    pairs = pairs.rename(columns={'agri_municipality_code': 'matched_2021_parent_code'})
    pairs['parent_scope_basis'] = pairs.parent_relation_rule.fillna('no_verified_parent')
    # Actual subject totals are not downscaled into an NP. A dedicated federal
    # context stands for that same subject comparison row, with an explicit flag.
    federal_rows = {}
    for code, name in FEDERAL_CITIES.items():
        candidate = pairs.loc[pairs.name.eq(name) & pairs.population_role.eq('external_context_nonadditive')]
        if len(candidate) > 1:
            raise ValueError('Ambiguous federal-city context')
        if len(candidate) == 1:
            idx = candidate.index[0]
            pairs.loc[idx, 'matched_2021_parent_code'] = code
            pairs.loc[idx, 'parent_scope_basis'] = 'explicit_federal_city_subject_context_not_np_distribution'
            federal_rows[code] = idx
    valid = pairs[pairs.matched_2021_parent_code.notna()].copy()
    valid['credited_population'] = pd.to_numeric(valid.population_2021, errors='coerce').where(valid.credit_2021.eq(True))
    rows = valid.groupby('matched_2021_parent_code', sort=True).agg(
        reference_settlement_records=('source_record_id', 'size'),
        credited_population_2021_in_known_parent=('credited_population', lambda x: x.sum(min_count=1)),
        credited_population_source_records=('credited_population', 'count'),
        medical_care_address_ids_in_known_2021_parent=('medical_care_address_ids_known', lambda x: x.sum(min_count=1)),
        settlements_with_positive_medical_evidence=('medical_care_address_ids_known', 'count'))
    out = jobs.merge(rows, left_on='oktmo', right_index=True, how='left', validate='one_to_one')
    out['population_basis'] = 'sum_of_credited_reference_NP_2021_in_matching_parent_not_2025_total'
    for code, index in federal_rows.items():
        target = out.oktmo.eq(code)
        out.loc[target, 'credited_population_2021_in_known_parent'] = pairs.loc[index, 'population_2021']
        out.loc[target, 'population_basis'] = 'explicit_federal_city_total_context_not_additive_to_NP_budget'
    out['medical_scope_basis'] = 'known_NP_address_ids_in_matching_2021_parent_subset_not_complete_inventory'
    out['federal_medical_address_ids_without_np_identity'] = pd.Series(pd.NA, index=out.index, dtype='Int64')
    if federal_medical is not None:
        for code in FEDERAL_CITIES:
            if code in federal_medical.index:
                target = out.oktmo.eq(code)
                out.loc[target, COMPONENTS[1]] = federal_medical.loc[code, 'federal_medical_address_ids_known']
                out.loc[target, 'federal_medical_address_ids_without_np_identity'] = int(
                    federal_medical.loc[code, 'federal_medical_address_ids_without_np_identity'])
                out.loc[target, 'medical_scope_basis'] = 'deduplicated_actual_care_address_region_including_unknown_NP_identity'
    out['workers_assigned_to_settlements'] = False
    out['workforce_measures_resident_employment'] = False
    out['care_address_count_is_capacity'] = False
    out['territorial_boundary_2021_2025_equality_verified'] = False
    out['profile_scope'] = 'municipal_or_federal_city_territory_never_a_disaggregated_settlement'
    out['temporal_scope'] = 'workforce_2025_medical_2026_population_and_parent_matching_2021'
    out['rank_scope'] = 'conditional_comparison_of_recorded_components_not_true_SGRT_order'
    audit.update(known_parent_np_records=len(valid), parentless_np_records=int(pairs.matched_2021_parent_code.isna().sum()),
                 same_code_is_not_proof_of_boundary_stability=True,
                 municipality_totals_distributed_to_NP=False)
    return out, pairs, audit


def dominance_rank_bounds(values):
    """Outer rank bounds under any strictly componentwise increasing index.

    Identical vectors do not dominate one another. These bounds need not be
    attainable by every positive linear weighting, and are not confidence CIs.
    """
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ValueError('A complete finite component matrix is required')
    lower = np.ones(len(values), dtype='int64')
    upper = np.full(len(values), len(values), dtype='int64')
    for start in range(0, len(values), 64):
        part = values[start:start+64]
        # First axis indexes the territory whose rank is being bounded.
        dominated_by_other = (values[None, :, :] >= part[:, None, :]).all(axis=2) & (
            values[None, :, :] > part[:, None, :]).any(axis=2)
        dominates_other = (part[:, None, :] >= values[None, :, :]).all(axis=2) & (
            part[:, None, :] > values[None, :, :]).any(axis=2)
        lower[start:start+len(part)] += dominated_by_other.sum(axis=1)
        upper[start:start+len(part)] -= dominates_other.sum(axis=1)
    return lower, upper


def compare(out):
    out = out.copy()
    eligibility = out[COMPONENTS].notna().all(axis=1) & out[COMPONENTS].gt(0).all(axis=1)
    out['recorded_component_comparison_eligible'] = eligibility
    for column in ['dominance_rank_lower', 'dominance_rank_upper', 'scenario_rank_min', 'scenario_rank_max']:
        out[column] = pd.Series(pd.NA, index=out.index, dtype='Int64')
    matrix = out.loc[eligibility, COMPONENTS].to_numpy(dtype=float)
    low, high = dominance_rank_bounds(matrix)
    out.loc[eligibility, 'dominance_rank_lower'] = low
    out.loc[eligibility, 'dominance_rank_upper'] = high
    transformed = np.log1p(matrix)
    standard = (transformed - transformed.mean(0)) / transformed.std(0)
    ranks = []
    weight_cases = []
    for a in range(1, 9):
        for b in range(1, 10-a):
            c = 10-a-b
            if c < 1: continue
            weights = np.array([a, b, c], dtype=float) / 10
            score = standard @ weights
            # Tied observations remain tied, not arbitrarily sorted by ID.
            ranks.append(pd.Series(score).rank(ascending=False, method='min').to_numpy(dtype='int64'))
            weight_cases.append(weights.tolist())
    ranks = np.stack(ranks)
    out.loc[eligibility, 'scenario_rank_min'] = ranks.min(0)
    out.loc[eligibility, 'scenario_rank_max'] = ranks.max(0)
    out['dominance_interval_is_statistical_confidence_interval'] = False
    out['rank_bounds_apply_only_to_recorded_components_not_unobserved_capacity'] = True
    summary = {'comparison_eligible_territories': int(eligibility.sum()), 'all_workforce_territories': len(out),
        'components': COMPONENTS, 'weight_scenarios': weight_cases,
        'index_is_strictly_componentwise_monotone_on_recorded_positive_components': True,
        'bounds_are_outer_dominance_bounds_not_exact_attainable_weighted_rank_intervals': True,
        'bounds_are_not_statistical_confidence_intervals': True,
        'same_year_boundaries_verified': False, 'workforce_is_full_workplaces_or_resident_workers': False,
        'municipal_workers_disaggregated_to_NP': False, 'spatial_SGRT_hierarchy_inferred': False}
    return out, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['workforce', 'reference', 'parent-context', 'medical-profiles', 'output']:
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--medical-evidence', type=Path)
    p.add_argument('--medical-addresses', type=Path)
    args = p.parse_args()
    if bool(args.medical_evidence) != bool(args.medical_addresses):
        p.error('Federal regional stock requires both medical evidence and actual care addresses')
    inputs = {k:v for k,v in vars(args).items() if k != 'output' and isinstance(v, Path)}
    before = {k:sha(v) for k,v in inputs.items()}
    raw = pd.read_parquet(args.workforce)
    federal = None
    if args.medical_evidence:
        federal = federal_medical_stock(pd.read_parquet(args.medical_evidence, columns=['UIDSPMO','IDADDRESS']),
            pd.read_parquet(args.medical_addresses,
                columns=['UIDSPMO','IDADDRESS','source_record_id','address_region_normalized']))
    profiles, crosswalk, audit = build_profiles(raw, pd.read_parquet(args.reference),
        pd.read_parquet(args.parent_context, columns=['source_record_id', 'agri_municipality_code', 'parent_relation_rule']),
        pd.read_parquet(args.medical_profiles, columns=['source_record_id', 'medical_care_address_ids_known']), federal)
    profiles, summary = compare(profiles)
    args.output.mkdir(parents=True, exist_ok=True)
    profiles.to_parquet(args.output/'municipal_scale_comparisons.parquet', index=False)
    crosswalk[['source_record_id', 'matched_2021_parent_code', 'parent_scope_basis']].to_parquet(
        args.output/'reference_parent_crosswalk.parquet', index=False)
    example_codes = ['45000000', '40000000', '63701000', '65701000', '75701000', '92701000']
    profiles[profiles.oktmo.isin(example_codes)].to_csv(args.output/'six_urban_territories.csv', index=False)
    summary.update(source_audit=audit, input_sha256=before, code_sha256=sha(Path(__file__)))
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    if before != {k:sha(v) for k,v in inputs.items()}: raise RuntimeError('Input changed during calculation')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__': main()
