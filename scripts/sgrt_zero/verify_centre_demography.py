"""Independently check fixed-catchment demographic sums and descriptive classes.

No primary readout helper is imported. Memberships, reference values/credits,
all component sums and directions are checked; scalar examples stay inspectable.
The accepted-values panel is never labelled observed. These descriptive checks
establish neither historic service boundaries nor causal Word types.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(registry, reference, readout, output):
    initial_code_hash = file_sha(Path(__file__))
    registry, reference, readout = map(Path, [registry, reference, readout])
    input_paths = [registry/'level0_centres.parquet', registry/'level0_memberships.parquet', reference,
                   readout/'fixed_membership_population_evidence.parquet',
                   readout/'centre_demographic_components.parquet',
                   readout/'centre_demographic_classes.parquet', readout/'summary.json']
    initial_hashes = {str(path): file_sha(path) for path in input_paths}
    b = Path(readout)
    registry = Path(registry)
    refpath = Path(reference)
    if not b.is_dir():
        raise RuntimeError('Await regenerated output')
    f = pd.read_parquet(b / 'fixed_membership_population_evidence.parquet')
    c = pd.read_parquet(b / 'centre_demographic_components.parquet')
    t = pd.read_parquet(b / 'centre_demographic_classes.parquet')
    s = json.loads((b / 'summary.json').read_text())
    ref = pd.read_parquet(refpath)
    ref = ref[ref.source_record_id.notna()].set_index('source_record_id')
    original = pd.read_parquet(registry / 'level0_memberships.parquet')
    centres = pd.read_parquet(registry / 'level0_centres.parquet')
    ids = pd.Index(centres.star_id)
    n_centres = len(centres)
    require(centres.star_id.is_unique and ref.index.is_unique, 'Independent verification failed: centres.star_id.is_unique and ref.index.is_unique')
    require(len(c) == n_centres * 12 and len(t) == n_centres * 2, 'Independent verification failed: len(c) == n_centres * 12 and len(t) == n_centres * 2')
    require(not c.duplicated(['star_id', 'scope', 'start_year', 'evidence_mode']).any(), "Independent verification failed: not c.duplicated(['star_id', 'scope', 'start_year', 'evidence_mode']).any()")
    require(not t.duplicated(['star_id', 'evidence_mode']).any(), "Independent verification failed: not t.duplicated(['star_id', 'evidence_mode']).any()")
    require(not any(('_observed_known_' in col for col in c.columns)), 'Accepted-mode columns must not be labelled observed')
    key = ['star_id', 'centre_settlement_id', 'origin_id', 'member_role']
    pd.testing.assert_frame_equal(f[key].sort_values(key).reset_index(drop=True), original[key].sort_values(key).reset_index(drop=True), check_dtype=False)
    require(len(f) == len(original) and (not f.duplicated(['star_id', 'origin_id']).any()), "Independent verification failed: len(f) == len(original) and (not f.duplicated(['star_id', 'origin_id']).any())")
    require(f.source_record_id.eq(f.origin_id).all(), 'Independent verification failed: f.source_record_id.eq(f.origin_id).all()')
    fields = [col for col in f if col in ref.columns]
    pd.testing.assert_frame_equal(f[fields].reset_index(drop=True), ref.reindex(f.origin_id)[fields].reset_index(drop=True), check_dtype=False)
    require(set(f.star_id) == set(ids), 'Independent verification failed: set(f.star_id) == set(ids)')
    require(f.member_role.eq('centre').equals(f.origin_id.eq(f.centre_settlement_id)), "Independent verification failed: f.member_role.eq('centre').equals(f.origin_id.eq(f.centre_settlement_id))")
    require(f[f.member_role.eq('centre')].groupby('star_id').size().eq(1).all(), "Independent verification failed: f[f.member_role.eq('centre')].groupby('star_id').size().eq(1).all()")
    PRIMARY = {'direct_published_census_value', 'direct_official_city_value', 'reviewed_primary_source_value_or_null', 'reviewed_primary_reported_value', 'fresh_primary_r5_source'}
    URBAN = {'город', 'пгт', 'посёлок городского типа'}
    centre = f.origin_id.eq(f.centre_settlement_id)
    external = ~centre
    rural = external & f.settlement_type_2021.notna() & ~f.settlement_type_2021.isin(URBAN)
    unknown_types = f[external & f.settlement_type_2021.isna()].groupby('star_id').size().reindex(ids, fill_value=0)

    def counts(mask):
        return f.loc[mask].groupby('star_id').size().reindex(ids, fill_value=0)

    def sums(mask, year):
        return f.loc[mask].groupby('star_id')[f'population_{year}'].sum().reindex(ids)

    def equal(actual, expected, label):
        a = pd.to_numeric(actual, errors='coerce').to_numpy(float)
        e = pd.to_numeric(expected, errors='coerce').to_numpy(float)
        require(np.isclose(a, e, rtol=0, atol=1e-08, equal_nan=True).all(), label)
    numeric = {}
    accepted = {}
    valid = {}
    for y in [2002, 2010, 2021]:
        p = pd.to_numeric(f[f'population_{y}'], errors='coerce')
        require(not (p.notna() & ~np.isfinite(p)).any(), 'Independent verification failed: not (p.notna() & ~np.isfinite(p)).any()')
        numeric[y] = p.notna() & p.ge(0)
        accepted[y] = numeric[y] & f[f'credit_{y}'].eq(True) & f.budget_population_credit.eq(True)
        require(not f[f'source_record_id_{y}'].eq('').any(), "Independent verification failed: not f[f'source_record_id_{y}'].eq('').any()")
    for mode in ['strict_direct_observed', 'accepted_values']:
        cl = t[t.evidence_mode.eq(mode)].set_index('star_id').reindex(ids)
        require(len(cl) == n_centres and cl.index.is_unique and (set(t[t.evidence_mode.eq(mode)].star_id) == set(ids)), 'Independent verification failed: len(cl) == n_centres and cl.index.is_unique and (set(t[t.evidence_mode.eq(mode)].star_id) == set(ids))')
        require(cl.word_causal_type_established.eq(False).all() and cl.historical_boundary_equivalence_established.eq(False).all(), 'Independent verification failed: cl.word_causal_type_established.eq(False).all() and cl.historical_boundary_equivalence_established.eq(False).all()')
        for y in [2002, 2010, 2021]:
            valid[y] = accepted[y] & f[f'source_record_id_{y}'].notna() & (f[f'population_value_quality_{y}'].isin(PRIMARY) if mode == 'strict_direct_observed' else True)
        for start in [2002, 2010]:
            for scope, mask in [('centre', centre), ('external', external), ('rural_external', rural)]:
                actual = c[c.evidence_mode.eq(mode) & c.start_year.eq(start) & c.scope.eq(scope)].set_index('star_id').reindex(ids)
                require(len(actual) == n_centres and actual.index.is_unique, 'Independent verification failed: len(actual) == n_centres and actual.index.is_unique')
                n = counts(mask)
                pair = mask & valid[start] & valid[2021]
                paired = counts(pair)
                complete = n.gt(0) & paired.eq(n) & (unknown_types.eq(0) if scope == 'rural_external' else True)
                equal(actual.records, n, 'component rows')
                equal(actual.comparable_records, paired, 'paired cohort size')
                require(actual.complete.equals(complete.rename('complete')), (mode, start, scope, 'complete'))
                for label, year in [('start', start), ('end', 2021)]:
                    prefix = label + '_mode_eligible_known'
                    equal(actual[prefix + '_records'], counts(mask & valid[year]), 'known count')
                    equal(actual[prefix + '_sum'], sums(mask & valid[year], year), 'known sum')
                    equal(actual[label + '_accepted_credited_numeric_sum'], sums(mask & accepted[year], year), 'accepted credited sum')
                    equal(actual[label + '_paired_cohort_sum'], sums(pair, year), 'paired sum')
                a = sums(pair, start)
                z = sums(pair, 2021)
                direction = pd.Series(np.where(complete, np.where(z > a, 'growth', np.where(z < a, 'decline', 'unchanged')), 'unknown'), index=ids)
                require(actual.direction.tolist() == direction.tolist(), (mode, start, scope, 'direction'))
                require(cl[f'{scope}_direction_{start}_2021'].tolist() == direction.tolist(), "Independent verification failed: cl[f'{scope}_direction_{start}_2021'].tolist() == direction.tolist()")
            for scope in ['external', 'rural_external']:
                aa = cl[f'centre_direction_{start}_2021']
                bb = cl[f'{scope}_direction_{start}_2021']
                expected = np.where(aa.ne('unknown') & bb.ne('unknown'), aa + '__' + bb, 'unknown')
                require(cl[f'joint_centre_{scope}_{start}_2021'].tolist() == expected.tolist(), "Independent verification failed: cl[f'joint_centre_{scope}_{start}_2021'].tolist() == expected.tolist()")
    require(not c.unknown_reasons_json.str.contains('imput', case=False).any(), "Independent verification failed: not c.unknown_reasons_json.str.contains('imput', case=False).any()")
    require(s['sums_across_catchments_are_invalid_due_to_overlap'] is True and s['historical_boundary_equivalence_established'] is False and (s['word_causal_types_assigned'] is False), "Independent verification failed: s['sums_across_catchments_are_invalid_due_to_overlap'] is True and s['historical_boundary_equivalence_established'] is False and (s['word_causal_types_assigned'] is False)")
    unique = f.drop_duplicates('origin_id')
    overlays = {}
    uncredited = f.budget_population_credit.ne(True)
    for y in [2002, 2010, 2021]:
        a = unique[unique[f'population_overlay_applied_{y}'].eq(True)]
        require(not a[f'population_value_quality_{y}'].isin(PRIMARY).any(), "Independent verification failed: not a[f'population_value_quality_{y}'].isin(PRIMARY).any()")
        overlays[str(y)] = {'unique_overlay_records': len(a), 'qualities': a[f'population_value_quality_{y}'].value_counts(dropna=False).to_dict()}
    manual = []
    for name, region in [('Новоузенск', 'саратовская'), ('Питерка', 'саратовская'), ('Симферополь', 'крым'), ('Снегуровка', 'приморский'), ('Москва', 'москва')]:
        selected = f[centre & f.name.eq(name) & f.region.eq(region)]
        for star in selected.star_id:
            own = f[f.star_id.eq(star)]
            parts = []
            for scope, items in [('centre', own[own.origin_id.eq(own.centre_settlement_id)]), ('external', own[own.origin_id.ne(own.centre_settlement_id)]), ('rural_external', own[own.origin_id.ne(own.centre_settlement_id) & own.settlement_type_2021.notna() & ~own.settlement_type_2021.isin(URBAN)])]:
                numbers = []
                for start in [2002, 2010]:
                    pair = []
                    for r in items.to_dict('records'):
                        if all((pd.notna(r[f'population_{y}']) and r[f'population_{y}'] >= 0 and (r[f'credit_{y}'] is True) and pd.notna(r[f'source_record_id_{y}']) for y in [start, 2021])) and r['budget_population_credit'] is True:
                            pair.append(r)
                    a = sum((r[f'population_{start}'] for r in pair)) if pair else None
                    z = sum((r['population_2021'] for r in pair)) if pair else None
                    row = c[c.star_id.eq(star) & c.evidence_mode.eq('accepted_values') & c.start_year.eq(start) & c.scope.eq(scope)].iloc[0]
                    require(pd.isna(row.start_paired_cohort_sum) and a is None or row.start_paired_cohort_sum == a, 'Independent verification failed: pd.isna(row.start_paired_cohort_sum) and a is None or row.start_paired_cohort_sum == a')
                    require(pd.isna(row.end_paired_cohort_sum) and z is None or row.end_paired_cohort_sum == z, 'Independent verification failed: pd.isna(row.end_paired_cohort_sum) and z is None or row.end_paired_cohort_sum == z')
                    numbers.append({'start_year': start, 'comparable_records': len(pair), 'start_sum': a, 'end_sum': z, 'direction': row.direction})
                parts.append({'scope': scope, 'records': len(items), 'raw_member_names': items.name.tolist() if len(items) <= 11 else 'longer than11; retained in fixed evidence', 'accepted_scalar_sums': numbers})
            manual.append({'centre': name, 'star_id': star, 'components': parts})
    proof = {'all_fixed_pairs_and_raw_reference_fields_unchanged': True, 'all_centres_have_complete_class_rows_in_both_modes': True, 'all_component_rows_independently_recomputed': True, 'every_partial_known_accepted_and_paired_sum_equal': True, 'all_directions_and_joint_labels_equal': True, 'uncredited_member_rows_preserved': int(uncredited.sum()), 'uncredited_unique_NPs_preserved': unique.loc[unique.budget_population_credit.ne(True), 'origin_id'].nunique(), 'uncredited_records_excluded_from_credited_sums': True, 'year2010_scope_unverified_not_labelled_imputed': True, 'primary_quality_and_applied_overlay_conflicts': 0, 'overlays': overlays, 'historical_boundaries_and_word_causality_not_claimed': True, 'manual_scalar_examples': manual, 'output_files_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in b.glob('*.parquet')}}
    proof['counts'] = {'centres': n_centres, 'fixed_member_pairs': len(f), 'component_rows': len(c), 'class_rows': len(t)}
    proof['schema'] = 'sgrt.centre_demography_independent_verification.v1'
    proof['verification_code_sha256'] = initial_code_hash
    proof['accepted_mode_known_columns_are_neutral'] = True
    proof['independent_of_primary_readout_code'] = True
    proof['input_sha256'] = initial_hashes
    require(initial_hashes == {str(p): file_sha(p) for p in input_paths}, 'An input changed during independent verification')
    require(file_sha(Path(__file__)) == initial_code_hash, 'Verifier code changed during its own run')
    output = Path(output)
    require(output.resolve() not in {p.resolve() for p in input_paths}, 'Output must not overwrite an input')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2, default=str) + '\n')
    return proof

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['registry', 'reference', 'readout', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    proof = verify(args.registry, args.reference, args.readout, args.output)
    print(json.dumps({key: value for key, value in proof.items()
                     if key not in ['manual_scalar_examples', 'input_sha256', 'output_files_sha256']},
                    ensure_ascii=False, indent=2))
