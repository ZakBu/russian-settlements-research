#!/usr/bin/env python3
"""Demography of fixed, overlapping centre catchments; no new regionalisation.

Only explicitly primary reported values enter the strict comparable cohort.
Accepted protected/secondary values remain inspectable, never renamed observed.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import pandas as pd

OBSERVED_QUALITIES = frozenset({
    'direct_published_census_value', 'direct_official_city_value',
    'reviewed_primary_source_value_or_null', 'reviewed_primary_reported_value',
    'fresh_primary_r5_source',
})
URBAN_TYPES = frozenset({'город', 'пгт', 'посёлок городского типа'})


def true(value):
    return pd.notna(value) and (value is True or value == 1)


def numeric(record, year):
    value = record.get(f'population_{year}')
    return pd.notna(value) and isinstance(value, (int, float)) and value >= 0


def reasons(record, year, evidence_mode="strict_direct_observed"):
    result = []
    if not numeric(record, year):
        result.append(f'missing_or_invalid_population_{year}')
    if pd.isna(record.get(f'source_record_id_{year}')):
        result.append(f'missing_census_record_{year}')
    if not true(record.get(f'credit_{year}')):
        result.append(f'population_not_credited_{year}')
    if not true(record.get('budget_population_credit')):
        result.append('current_population_budget_not_credited')
    quality = record.get(f'population_value_quality_{year}')
    if evidence_mode == 'strict_direct_observed' and quality not in OBSERVED_QUALITIES:
        if quality == 'secondary_confidentiality_protected_value_exact_scope_unverified':
            result.append(f'secondary_confidentiality_value_scope_unverified_{year}')
        else:
            result.append(f'population_quality_not_primary_observed_{year}')
    return result


def analyse_component(records, start, end=2021, unknown_type_count=0, evidence_mode="strict_direct_observed"):
    """Return partial sums plus an explicit complete-cohort decision."""
    record_reasons = [set(reasons(r, start, evidence_mode) + reasons(r, end, evidence_mode)) for r in records]
    counts = Counter(reason for rr in record_reasons for reason in rr)
    if not records:
        counts['empty_component'] = 1
    if unknown_type_count:
        counts['external_settlement_type_unknown'] = unknown_type_count
    cohort = [r for r, rr in zip(records, record_reasons) if not rr]
    result = {'records': len(records), 'comparable_records': len(cohort),
              'complete': bool(records) and not counts,
              'unknown_reasons_json': json.dumps(dict(sorted(counts.items())), sort_keys=True)}
    for label, year in [('start', start), ('end', end)]:
        known = [r[f'population_{year}'] for r in records if not reasons(r, year, evidence_mode)]
        accepted = [r[f'population_{year}'] for r in records if numeric(r, year)
                    and true(r.get(f'credit_{year}')) and true(r.get('budget_population_credit'))]
        result[f'{label}_observed_known_records'] = len(known)
        result[f'{label}_observed_known_sum'] = sum(known) if known else None
        result[f'{label}_accepted_credited_numeric_sum'] = sum(accepted) if accepted else None
        result[f'{label}_paired_cohort_sum'] = sum(r[f'population_{year}'] for r in cohort) if cohort else None
    direction = 'unknown'
    if result['complete']:
        a, b = result['start_paired_cohort_sum'], result['end_paired_cohort_sum']
        direction = 'growth' if b > a else 'decline' if b < a else 'unchanged'
    result['direction'] = direction
    return result


def build_readout(centres, memberships, reference, evidence_mode="strict_direct_observed"):
    reference = reference[reference.source_record_id.notna()].copy()
    if not centres.star_id.is_unique or not reference.source_record_id.is_unique:
        raise ValueError('Centre/reference identities must be unique')
    if memberships.duplicated(['star_id', 'origin_id']).any():
        raise ValueError('Duplicate member inside a catchment')
    if set(memberships.star_id) != set(centres.star_id):
        raise ValueError('Centre and membership sets differ')
    ref = reference.set_index('source_record_id').to_dict('index')
    grouped = memberships.groupby('star_id', sort=False).origin_id.agg(list).to_dict()
    rows, classes = [], []
    for centre in centres.itertuples(index=False):
        cid = centre.centre_settlement_id
        ids = grouped[centre.star_id]
        if ids.count(cid) != 1 or any(sid not in ref for sid in ids):
            raise ValueError('Centre must appear once; all members must exist in reference')
        external = [ref[sid] for sid in ids if sid != cid]
        unknown_types = sum(pd.isna(r.get('settlement_type_2021')) for r in external)
        rural = [r for r in external if pd.notna(r.get('settlement_type_2021'))
                 and r['settlement_type_2021'] not in URBAN_TYPES]
        classification = {'star_id': centre.star_id, 'centre_settlement_id': cid,
                          'centre_name': ref[cid]['name'], 'word_causal_type_established': False,
                          'historical_boundary_equivalence_established': False}
        for start in [2002, 2010]:
            results = {}
            for scope, records in [('centre', [ref[cid]]), ('external', external), ('rural_external', rural)]:
                result = analyse_component(records, start, unknown_type_count=unknown_types if scope == 'rural_external' else 0, evidence_mode=evidence_mode)
                rows.append({'star_id': centre.star_id, 'centre_settlement_id': cid,
                             'scope': scope, 'start_year': start, 'end_year': 2021, **result})
                results[scope] = result
                classification[f'{scope}_direction_{start}_2021'] = result['direction']
            for scope in ['external', 'rural_external']:
                a, b = results['centre'], results[scope]
                classification[f'joint_centre_{scope}_{start}_2021'] = (
                    a['direction'] + '__' + b['direction'] if a['complete'] and b['complete'] else 'unknown')
                classification[f'joint_centre_{scope}_unknown_reasons_{start}_2021_json'] = json.dumps({
                    k: json.loads(v['unknown_reasons_json']) for k, v in [('centre', a), (scope, b)]
                    if not v['complete']}, sort_keys=True)
        classes.append(classification)
    return pd.DataFrame(rows).assign(evidence_mode=evidence_mode), pd.DataFrame(classes).assign(evidence_mode=evidence_mode)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(registry, reference_path, output):
    registry, reference_path, output = Path(registry), Path(reference_path), Path(output)
    if output.resolve() in [registry.resolve(), reference_path.parent.resolve()] or registry.resolve() in output.resolve().parents:
        raise ValueError('Use a separate output directory, never the input registry')
    paths = [registry/'level0_centres.parquet', registry/'level0_memberships.parquet', reference_path]
    fingerprints = {str(p): sha(p) for p in paths}
    centres, memberships, reference = (pd.read_parquet(p) for p in paths)
    outputs = [build_readout(centres, memberships, reference, mode) for mode in ['strict_direct_observed', 'accepted_values']]
    components = pd.concat([x[0] for x in outputs], ignore_index=True)
    classes = pd.concat([x[1] for x in outputs], ignore_index=True)
    output.mkdir(parents=True, exist_ok=False)
    components.to_parquet(output/'centre_demographic_components.parquet', index=False)
    classes.to_parquet(output/'centre_demographic_classes.parquet', index=False)
    classes.to_csv(output/'centre_demographic_classes.csv', index=False)
    counts = {mode: {str(start): {scope: group.direction.value_counts().to_dict()
              for scope, group in components[components.start_year.eq(start) & components.evidence_mode.eq(mode)].groupby('scope')}
              for start in [2002, 2010]} for mode in ['strict_direct_observed', 'accepted_values']}
    joints = {mode: {c: part[c].value_counts().to_dict() for c in part if c.startswith('joint_') and '_json' not in c}
              for mode, part in classes.groupby('evidence_mode')}
    retained = ['source_record_id', 'name', 'region', 'district', 'population_role', 'settlement_type_2021',
                'budget_population_credit'] + [f'{field}_{year}' for year in [2002, 2010, 2021]
                for field in ['population', 'credit', 'source_record_id', 'population_value_quality', 'population_overlay_applied']]
    memberships[['star_id', 'centre_settlement_id', 'origin_id', 'member_role']].merge(
        reference.loc[reference.source_record_id.notna(), retained], left_on='origin_id', right_on='source_record_id', validate='many_to_one').to_parquet(
        output/'fixed_membership_population_evidence.parquet', index=False)
    summary = {'centres': len(centres), 'centre_member_pairs': len(memberships),
               'fixed_membership_reference_year': 2021, 'component_direction_counts': counts,
               'joint_direction_counts': joints, 'strict_primary_quality_allowlist': sorted(OBSERVED_QUALITIES),
               'population_fields_available': [c for c in reference if 'population' in c or c.startswith('credit_')],
               'raw_effective_population_pair_available': False,
               'accepted_population_with_quality_and_overlay_flags_only': True,
               'protected_secondary_2010_is_not_primary_observed': True,
               'secondary_confidentiality_value_not_automatically_imputed': True,
               'accepted_values_mode_is_not_claimed_observed': True,
               'partial_known_sums_are_not_component_totals': True,
               'sums_across_catchments_are_invalid_due_to_overlap': True,
               'historical_boundary_equivalence_established': False,
               'word_causal_types_assigned': False, 'input_sha256': fingerprints}
    if any(sha(Path(p)) != digest for p, digest in fingerprints.items()):
        raise ValueError('An immutable input changed')
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    (output/'README.md').write_text(
        '# Демография фиксированных окружений 2021 года\n\n'
        'Для каждого центра отдельно описаны сам центр, внешнее окружение без центра и его сельская часть. '
        'Составы закреплены по модели 2021 года; это не исторические границы обслуживания. '
        'Направление определяется только при полном сопоставимом составе: у каждого участника есть первичное '
        'наблюдённое число, переписная запись и право учёта населения в обоих годах. '
        'Защищённые вторичные значения 2010 года, интерпретации прочерков и производные разбиения не считаются '
        'первичными наблюдениями. Защищённое вторичное значение не объявляется автоматически импутированным. '
        'Второй вариант accepted_values использует все принятые кредитованные числа и не называется наблюдённым. '
        'Принятая база содержит population/quality/overlay, но не отдельную пару raw/effective.\n\n'
        'Частичные известные суммы и суммы доступных принятых чисел сохранены отдельно от направления. '
        'Unknown имеет явные причины; пустая сельская часть не считается неизменной. '
        'Сельский состав определён типом НП2021 года. Окружения пересекаются: их население нельзя складывать. '
        'Описательные направления роста/убыли не устанавливают девять причинных типов Word.\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.registry, args.reference, args.output)
