#!/usr/bin/env python3
"""Describe existing low-order units using source-grain-safe economic context.

Municipal agricultural values remain one row per unit and municipality. Neither
those repeated municipal values nor partial workforce observations are summed
into a supposed settlement output, complete job count or employment rate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

AGRI = ('agri_sown_area_ha_2021_municipal_context',
        'agri_cattle_heads_2021_municipal_context',
        'agri_grain_yield_centner_per_harvested_ha_2021_municipal_context')
WORKFORCE = 'partial_organisation_workforce_2025'
CONTEXT_COLUMNS = ['source_record_id', 'agri_municipality_code',
                   'agri_parent_match_status', *AGRI, WORKFORCE,
                   'partial_workforce_status', 'partial_workforce_observation_year',
                   'partial_workforce_source_id']


def describe(memberships, units, context):
    if memberships.origin_id.isna().any() or memberships.origin_id.duplicated().any():
        raise ValueError('Every primary origin must be retained exactly once')
    if units.unit_id.isna().any() or units.unit_id.duplicated().any():
        raise ValueError('Unit identities must be nonmissing and unique')
    if not set(memberships.unit_id.dropna()) <= set(units.unit_id):
        raise ValueError('Primary membership refers to an unknown unit')
    known = context.dropna(subset=['source_record_id']).copy()
    if known.source_record_id.duplicated().any():
        raise ValueError('Economic source identities must be unique; no join multiplication')
    for col in CONTEXT_COLUMNS:
        if col not in known:
            raise ValueError('Missing economic field: ' + col)
    observed = known.partial_workforce_status.eq('observed_partial_organisation_workforce')
    if known.loc[observed, WORKFORCE].isna().any() or not known.loc[
            observed, 'partial_workforce_observation_year'].eq(2025).all():
        raise ValueError('Observed partial workforce must have a number and actual year 2025')
    if (known.loc[observed, WORKFORCE] < 0).any():
        raise ValueError('Negative observed workforce')
    selected = ['origin_id', 'unit_id'] + [c for c in [
        'name', 'region', 'membership_status', 'positive_whole_origin',
        'source_grain_requires_review', 'is_registered_centre'] if c in memberships]
    if 'positive_whole_origin' not in selected:
        raise ValueError('Explicit positive-whole eligibility is required')
    rows = memberships[selected].merge(known[CONTEXT_COLUMNS], how='left',
        left_on='origin_id', right_on='source_record_id', validate='one_to_one', indicator=True)
    rows['economic_source_record_matched'] = rows.pop('_merge').eq('both')
    rows['partial_workforce_observed'] = rows.partial_workforce_status.eq(
        'observed_partial_organisation_workforce') & rows[WORKFORCE].notna()
    rows['agriculture_is_municipal_context_not_own_output'] = True
    rows['partial_workforce_is_not_total_jobs_or_resident_employment'] = True
    rows['workforce_values_are_not_summed_across_members'] = True
    # These columns count source availability; numeric zero is an observation.
    for metric in AGRI:
        rows[metric + '_observed'] = rows[metric].notna()
    assigned = rows[rows.unit_id.notna()].copy()
    profile_rows = assigned[assigned.agri_municipality_code.notna()].copy()
    key = ['unit_id', 'agri_municipality_code']
    profiles = []
    for pair, group in profile_rows.groupby(key, sort=True):
        record = dict(zip(key, pair))
        record['member_records_sharing_context'] = len(group)
        record['positive_whole_member_records_sharing_context'] = int(group.positive_whole_origin.fillna(False).sum())
        for field in AGRI:
            values = group[field].dropna().unique()
            if len(values) > 1:
                raise ValueError('Conflicting values for one municipality/year/metric: ' + str(pair) + ' ' + field)
            record[field] = values[0] if len(values) else None
        record['agriculture_observation_year'] = 2021
        record['full_municipality_values_not_allocated_to_unit'] = True
        profiles.append(record)
    profile_columns = [*key, 'member_records_sharing_context',
                       'positive_whole_member_records_sharing_context', *AGRI,
                       'agriculture_observation_year', 'full_municipality_values_not_allocated_to_unit']
    municipal = pd.DataFrame(profiles, columns=profile_columns)
    descriptor_fields = ['unit_id'] + [c for c in ['name', 'centre_name', 'centre_region',
        'centre_settlement_id', 'is_registered_external_serving_centre'] if c in units]
    result = units[descriptor_fields].copy().set_index('unit_id')
    count_fields = {
        'primary_member_records': assigned.groupby('unit_id').size(),
        'positive_whole_member_records': assigned.groupby('unit_id').positive_whole_origin.sum(),
        'members_with_matched_economic_source_record': assigned.groupby('unit_id').economic_source_record_matched.sum(),
        'members_with_identified_municipal_context': assigned.groupby('unit_id').agri_municipality_code.count(),
        'distinct_municipal_contexts': assigned.groupby('unit_id').agri_municipality_code.nunique(),
        'members_with_sown_2021_context': assigned.groupby('unit_id')[AGRI[0] + '_observed'].sum(),
        'members_with_cattle_2021_context': assigned.groupby('unit_id')[AGRI[1] + '_observed'].sum(),
        'members_with_grain_yield_2021_context': assigned.groupby('unit_id')[AGRI[2] + '_observed'].sum(),
        'members_with_partial_workforce_2025_observation': assigned.groupby('unit_id').partial_workforce_observed.sum(),
        'members_with_suppressed_workforce_2025': assigned.assign(
            _suppressed=assigned.partial_workforce_status.eq('source_suppressed')).groupby('unit_id')._suppressed.sum(),
    }
    positive_assigned = assigned[assigned.positive_whole_origin.fillna(False)]
    count_fields.update({
        'positive_whole_members_with_sown_2021_context': positive_assigned.groupby('unit_id')[AGRI[0] + '_observed'].sum(),
        'positive_whole_members_with_cattle_2021_context': positive_assigned.groupby('unit_id')[AGRI[1] + '_observed'].sum(),
        'positive_whole_members_with_partial_workforce_2025_observation': positive_assigned.groupby('unit_id').partial_workforce_observed.sum(),
    })
    for field, values in count_fields.items():
        result[field] = values.reindex(result.index, fill_value=0).astype('int64')
    result['agriculture_observation_year'] = 2021
    result['partial_workforce_observation_year'] = 2025
    result['total_unit_jobs_established'] = False
    result['municipal_agriculture_is_not_unit_output'] = True
    result['uses_economy_to_change_unit_membership'] = False
    result = result.reset_index()
    positive = rows[rows.positive_whole_origin.fillna(False)]
    summary = {
        'schema': 'sgrt.common_economic_context.v1',
        'units': len(result), 'all_primary_origin_records': len(rows),
        'assigned_origin_records': len(assigned), 'unassigned_origin_records': int(rows.unit_id.isna().sum()),
        'positive_whole_origin_records': len(positive),
        'assigned_positive_whole_origin_records': int((rows.unit_id.notna() & rows.positive_whole_origin.fillna(False)).sum()),
        'unit_municipal_context_pairs': len(municipal),
        'units_with_sown_2021_context': int(result.members_with_sown_2021_context.gt(0).sum()),
        'units_with_cattle_2021_context': int(result.members_with_cattle_2021_context.gt(0).sum()),
        'units_with_partial_workforce_2025_observations': int(result.members_with_partial_workforce_2025_observation.gt(0).sum()),
        'units_with_partial_workforce_2025_observations_in_positive_whole_members': int(
            result.positive_whole_members_with_partial_workforce_2025_observation.gt(0).sum()),
        'positive_whole_origins_with_sown_2021_context': int(positive[AGRI[0]].notna().sum()),
        'positive_whole_origins_with_cattle_2021_context': int(positive[AGRI[1]].notna().sum()),
        'positive_whole_origins_with_partial_workforce_2025_observation': int(positive.partial_workforce_observed.sum()),
        'agriculture_source': 'BDMO_SECTION7_20250918, year 2021 municipal observations',
        'workforce_source': 'ROSSTAT_NP2025_PRIMARY_BOOKS, January–December 2025; partial workforce',
        'agriculture_is_not_settlement_or_unit_output': True,
        'partial_workforce_is_not_total_jobs_or_resident_employment': True,
        'municipal_values_or_workforce_values_summed': False,
        'membership_changed': False,
    }
    if 'is_registered_external_serving_centre' in result:
        summary['by_unit_role'] = {}
        for label, mask in [
            ('registered_external_serving_centres', result.is_registered_external_serving_centre.eq(True)),
            ('additional_local_or_provider_context_units', result.is_registered_external_serving_centre.ne(True)),
        ]:
            group = result[mask]
            summary['by_unit_role'][label] = {
                'units': len(group),
                'units_with_sown_2021_context': int(group.members_with_sown_2021_context.gt(0).sum()),
                'units_with_cattle_2021_context': int(group.members_with_cattle_2021_context.gt(0).sum()),
                'units_with_partial_workforce_2025_observations': int(
                    group.members_with_partial_workforce_2025_observation.gt(0).sum()),
            }
    return {'economic_memberships': rows, 'unit_economic_context': result,
            'unit_municipal_context': municipal}, summary


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['memberships', 'units', 'context', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    source_paths = {name: getattr(args, name) for name in ['memberships', 'units', 'context']}
    source_sha = {name: sha(path) for name, path in source_paths.items()}
    tables, summary = describe(*[pd.read_parquet(source_paths[name]) for name in ['memberships', 'units', 'context']])
    if source_sha != {name: sha(path) for name, path in source_paths.items()}:
        raise RuntimeError('Input changed during economic description')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_parquet(args.output / (name + '.parquet'), index=False)
    summary['inputs_sha256'] = source_sha
    summary['code_sha256'] = sha(Path(__file__))
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))
