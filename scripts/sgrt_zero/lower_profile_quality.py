#!/usr/bin/env python3
"""Describe source grain and centre membership without changing L0 assignments.

The lower grouping is a partition of provider-choice profiles. This diagnostic
keeps raw census identities and population intact; it never merges homonyms.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import pandas as pd

PART_PAREN = re.compile(r'\(\s*част(?:ь|и)\s*(?:\d+|[ivx]+)?\s*\)', re.I)
PART_WORD = re.compile(r'\bчаст(?:ь|и)\b', re.I)
EXPLICIT_PART_FLAGS = ('is_settlement_part', 'settlement_is_part', 'population_unit_is_part')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def part_inventory(reference):
    """A name-based source-grain warning, not a legal settlement merger."""
    out = reference.copy()
    name = out['name'].fillna('').astype(str)
    explicit_name = name.str.contains(PART_PAREN)
    source_flag = pd.Series(False, index=out.index)
    used_flags = []
    for flag in EXPLICIT_PART_FLAGS:
        if flag in out:
            used_flags.append(flag)
            # Only explicit true values, never Python truthiness of "False".
            source_flag |= out[flag].astype('string').str.lower().isin(['true', '1', 'yes'])
    explicit_text = name.str.match(r'^сельский насел[её]нный пункт\s+часть\s+', case=False)
    out['part_status'] = 'unmarked_whole_place_record'
    out.loc[name.str.contains(PART_WORD), 'part_status'] = 'part_word_in_name_identity_requires_review'
    out.loc[explicit_name | explicit_text | source_flag, 'part_status'] = 'explicit_source_part'
    out['part_source_flag'] = source_flag
    out['part_parenthetical_name_marker'] = explicit_name
    out['part_parent_name_candidate'] = name.str.replace(PART_PAREN, '', regex=True).str.strip()
    out['part_parent_name_is_not_verified_legal_identity'] = out.part_status.eq('explicit_source_part')
    return out, used_flags


def analyse(reference, memberships, units, edges):
    if memberships.origin_id.duplicated().any():
        raise ValueError('Demand-point membership must be unique')
    ref, flags = part_inventory(reference)
    indexed = ref.dropna(subset=['source_record_id']).set_index('source_record_id')
    if not indexed.index.is_unique:
        raise ValueError('Non-null reference identities must be unique')
    rows = memberships[['unit_id', 'origin_id']].merge(
        indexed[['name', 'region', 'district', 'settlement_type_2021', 'lat', 'lon',
                 'population_2021', 'budget_population_credit', 'part_status',
                 'part_parent_name_candidate']], left_on='origin_id', right_index=True,
        validate='one_to_one')
    rows['positive_credited'] = rows.budget_population_credit.fillna(False) & rows.population_2021.gt(0)
    rows['unmarked_positive_whole_record'] = rows.positive_credited & rows.part_status.eq('unmarked_whole_place_record')
    rows['explicit_part'] = rows.part_status.eq('explicit_source_part')
    rows['ambiguous_part_word'] = rows.part_status.eq('part_word_in_name_identity_requires_review')
    # ONLY explicitly labelled parts with the same parent label/context share
    # a diagnostic entity key. Ordinary equal names retain distinct census IDs.
    rows['diagnostic_entity_key'] = 'record:' + rows.origin_id.astype(str)
    parts = rows.explicit_part & rows.name.str.contains(PART_PAREN, na=False)
    context = rows[['region', 'district', 'settlement_type_2021', 'part_parent_name_candidate']].fillna('').astype(str).agg('|'.join, axis=1)
    rows.loc[parts, 'diagnostic_entity_key'] = 'explicit-labelled-parent:' + context[parts]
    positive = rows[rows.positive_credited]
    q = units.set_index('unit_id').copy()
    q['positive_source_records'] = positive.groupby('unit_id').size().reindex(q.index, fill_value=0)
    q['unmarked_positive_whole_records'] = rows.groupby('unit_id').unmarked_positive_whole_record.sum().reindex(q.index, fill_value=0)
    q['diagnostic_positive_entities_after_explicit_part_labels'] = positive.groupby('unit_id').diagnostic_entity_key.nunique().reindex(q.index, fill_value=0)
    q['explicit_part_records'] = rows.groupby('unit_id').explicit_part.sum().reindex(q.index, fill_value=0)
    q['ambiguous_part_word_records'] = rows.groupby('unit_id').ambiguous_part_word.sum().reindex(q.index, fill_value=0)
    lookup = memberships.set_index('origin_id').unit_id
    a = edges[edges.l0_admitted].copy()
    a['unit_id'] = a.origin_id.map(lookup)
    a['provider_own_unit_id'] = a.provider_settlement_id.map(lookup)
    a['provider_is_member'] = a.unit_id.eq(a.provider_own_unit_id)
    a['internal_distinct_np_link'] = a.provider_is_member & a.origin_id.ne(a.provider_settlement_id)
    q['known_np_supplier_edges'] = a.groupby('unit_id').provider_settlement_id.count().reindex(q.index, fill_value=0)
    q['any_known_np_supplier_is_member'] = a.groupby('unit_id').provider_is_member.any().reindex(q.index, fill_value=False)
    q['any_internal_distinct_np_service_link'] = a.groupby('unit_id').internal_distinct_np_link.any().reindex(q.index, fill_value=False)
    q['all_known_np_suppliers_outside'] = q.known_np_supplier_edges.gt(0) & ~q.any_known_np_supplier_is_member
    multi = q[q.inhabited_multi_np_service_area]
    zero = multi[multi.member_geodesic_diameter_km.eq(0)]
    coords = rows.dropna(subset=['lat', 'lon']).groupby(['lat', 'lon']).size()
    coordinate_duplicates = rows.merge(coords[coords.gt(1)].rename('coordinate_record_count').reset_index(), on=['lat', 'lon'])
    marked = ref[ref.part_status.ne('unmarked_whole_place_record')]
    source_part_rows = ref[ref.part_status.eq('explicit_source_part')]
    source_origins = ref.analysis_origin.fillna(False) if 'analysis_origin' in ref else ref.source_record_id.isin(memberships.origin_id)
    review_multi = multi[multi.explicit_part_records.gt(0) | multi.ambiguous_part_word_records.gt(0)]
    evidence = rows[rows.unit_id.isin(review_multi.index)].copy()
    part_groups = []
    for uid, g in evidence.groupby('unit_id', sort=False):
        part_groups.append({'unit_id': uid, 'positive_source_records': int(q.loc[uid, 'positive_source_records']),
            'unmarked_positive_whole_records': int(q.loc[uid, 'unmarked_positive_whole_records']),
            'entities_after_explicit_part_labels': int(q.loc[uid, 'diagnostic_positive_entities_after_explicit_part_labels']),
            'names': g.name.tolist(), 'origin_ids': g.origin_id.tolist()})
    result = {
        'method': 'Read-only source-grain, coordinate and centre-membership diagnostic; no reassignment or population change',
        'source_reference_rows': len(ref), 'analysis_origin_records': len(rows),
        'part_source_flags_available': flags,
        'explicit_parts_in_all_reference_rows': len(source_part_rows),
        'explicit_parts_in_analysis_origins': int((ref.part_status.eq('explicit_source_part') & source_origins).sum()),
        'ambiguous_part_word_in_all_reference_rows': int(ref.part_status.eq('part_word_in_name_identity_requires_review').sum()),
        'ambiguous_part_word_in_analysis_origins': int((ref.part_status.eq('part_word_in_name_identity_requires_review') & source_origins).sum()),
        'raw_multi_positive_source_record_profiles': len(multi),
        'profiles_with_at_least_two_unmarked_positive_whole_place_records': int(multi.unmarked_positive_whole_records.ge(2).sum()),
        'profiles_with_at_least_two_diagnostic_entities_after_explicit_part_labels': int(multi.diagnostic_positive_entities_after_explicit_part_labels.ge(2).sum()),
        'raw_multi_profiles_reduced_below_two_entities_by_explicit_parts': int(multi.diagnostic_positive_entities_after_explicit_part_labels.lt(2).sum()),
        'raw_multi_profiles_with_explicit_parts': int(multi.explicit_part_records.gt(0).sum()),
        'raw_multi_profiles_with_ambiguous_part_word': int(multi.ambiguous_part_word_records.gt(0).sum()),
        'certification_scope': 'Unmarked whole-place source-record grain only. This is not an independent certification of legal identities, geocodes or observed SGRT. Homonymous records are never merged.',
        'zero_diameter_multi_profiles': len(zero), 'records_in_zero_diameter_multi_profiles': int(zero.member_records.sum()),
        'coordinate_duplicate_groups': int(coords.gt(1).sum()), 'records_sharing_coordinates': len(coordinate_duplicates),
        'multi_profiles_without_any_known_np_supplier_in_membership': int((~multi.any_known_np_supplier_is_member).sum()),
        'multi_profiles_all_known_np_suppliers_outside': int(multi.all_known_np_suppliers_outside.sum()),
        'records_in_multi_profiles_all_known_np_suppliers_outside': int(multi.loc[multi.all_known_np_suppliers_outside, 'member_records'].sum()),
        'multi_profiles_without_internal_distinct_np_candidate_link': int((~multi.any_internal_distinct_np_service_link).sum()),
        'limits': ['Unknown provider NP identities do not prove absence of a centre.',
                   'Coincident input points do not establish zero real separation.',
                   'No recorded internal supply edge does not prove absent roads or social interaction.',
                   'Equal provider profiles are intersections of service choices, not certified centre-and-periphery systems.'],
        'part_group_examples': part_groups,
    }
    return result, q.reset_index(), marked, evidence, coordinate_duplicates, rows[rows.unit_id.isin(zero.index)]


def run(directory, reference_path, output):
    files = {name: directory / (name + '.parquet') for name in ('level0_memberships', 'level0_units', 'daily_edge_evidence')}
    result, quality, parts, part_groups, coordinates, zero = analyse(pd.read_parquet(reference_path),
        pd.read_parquet(files['level0_memberships']), pd.read_parquet(files['level0_units']), pd.read_parquet(files['daily_edge_evidence']))
    result['input_sha256'] = {'reference': sha256(reference_path), **{key: sha256(path) for key, path in files.items()}}
    state_path = directory.parents[1] / 'source_code_state.json'
    if state_path.exists():
        result['source_dataset_declared_commit'] = json.loads(state_path.read_text()).get('declared_source_commit')
    result['code_sha256'] = sha256(Path(__file__))
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in [('profile_quality', quality), ('part_name_inventory', parts), ('part_group_members', part_groups),
                        ('coincident_origin_records', coordinates), ('zero_diameter_group_members', zero)]:
        frame.to_parquet(output / (name + '.parquet'), index=False)
    (output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = run(a.directory, a.reference, a.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'part_group_examples'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
