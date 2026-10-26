"""Explain losses between locally recorded functions and the three-core subset.

This audit changes no providers, identities, routing or group membership.
"""
import argparse
import json
from pathlib import Path
import pandas as pd
from lower_profile_quality import part_inventory, sha256

CORE = ['school', 'medical_basic', 'grocery']


def audit(scenario, reference, output):
    output.mkdir(parents=True, exist_ok=True)
    columns = ['origin_id', 'service_family', 'provider_settlement_id',
               'provider_site_id', 'provider_name', 'local_service_present',
               'l0_admitted', 'cost_minutes']
    edges = pd.read_parquet(scenario / 'daily_edges.parquet', columns=columns)
    edges = edges[edges.service_family.isin(CORE)].copy()
    if edges.duplicated(['origin_id', 'service_family']).any():
        raise ValueError('Duplicate origin/function')
    ref, _ = part_inventory(pd.read_parquet(reference))
    ref = ref[ref.source_record_id.notna()].set_index('source_record_id')
    if not ref.index.is_unique:
        raise ValueError('Reference identities are not unique')
    local = edges.pivot(index='origin_id', columns='service_family',
                        values='local_service_present')
    if local.isna().any().any():
        raise ValueError('An origin lost a function row')
    local = local.astype(bool)
    local['full_three'] = local[CORE].all(axis=1)
    local = local.join(ref[['name', 'region', 'settlement_type_2021',
                           'population_2021', 'part_status', 'population_role',
                           'budget_population_credit', 'analysis_origin']],
                       validate='one_to_one')
    if local.name.isna().any():
        raise ValueError('Origin/reference join lost names')
    valid = (local.part_status.eq('unmarked_whole_place_record')
             & local.population_2021.gt(0)
             & ((local.population_role.eq('ordinary_settlement_record')
                 & local.budget_population_credit.fillna(False))
                | local.population_role.eq('external_context_nonadditive')))
    stars = pd.read_parquet(scenario / 'centre_stars.parquet')
    usable = (stars.centre_unmarked_whole_record
              & stars.centre_positive_population_known
              & stars.centre_ordinary_credited_or_nonadditive_context)
    full = stars.centre_own_all_three_core_confirmed & usable
    any_external = stars.one_or_more_core_external_positive_whole.gt(0)
    same_three = stars.all_three_core_external_positive_whole.gt(0)
    counts = {
        'all_origin_records': len(local),
        'locally_recorded_school_origins': int(local.school.sum()),
        'locally_recorded_medical_origins': int(local.medical_basic.sum()),
        'locally_recorded_grocery_origins': int(local.grocery.sum()),
        'all_three_locally_recorded_before_grain_screen': int(local.full_three.sum()),
        'all_three_valid_positive_whole_centres': int(full.sum()),
        'full_centres_with_any_external_core_participant': int((full & any_external).sum()),
        'full_centres_without_external_core_participant': int((full & ~any_external).sum()),
        'full_centres_with_external_same_three_core_participant': int((full & same_three).sum()),
        'full_centres_with_external_but_no_same_three_participant': int((full & any_external & ~same_three).sum()),
    }
    if int((valid & local.full_three).sum()) != counts['all_three_valid_positive_whole_centres']:
        raise ValueError('Independent local-offer count differs from centre table')
    table = []
    for label, mask in [
        ('city_source_records', local.settlement_type_2021.eq('город')),
        ('pgt_source_records', local.settlement_type_2021.eq('пгт')),
        ('city_and_pgt_source_records', local.settlement_type_2021.isin(['город', 'пгт'])),
        ('valid_positive_whole_city_and_pgt_records', valid & local.settlement_type_2021.isin(['город', 'пгт'])),
        ('valid_positive_whole_urban_under50000', valid & local.settlement_type_2021.isin(['город', 'пгт']) & local.population_2021.lt(50000)),
    ]:
        rows = local[mask]
        table.append({'scope': label, 'origin_records': len(rows),
                      **{c: int(rows[c].sum()) for c in CORE + ['full_three']}})
    coverage = []
    for family, group in edges.groupby('service_family'):
        admitted = group[group.l0_admitted]
        known = admitted.provider_settlement_id.notna()
        coverage.append({'family': family, 'origin_records': len(group),
                         'admitted_links': len(admitted),
                         'known_provider_np_links': int(known.sum()),
                         'unknown_provider_np_links': int((~known).sum()),
                         'known_provider_np_count': int(admitted.provider_settlement_id.nunique())})
    examples = local[(local.region.eq('саратовская'))
                     & local.name.isin(['Саратов', 'Энгельс', 'Новоузенск', 'Питерка'])
                     & local.settlement_type_2021.isin(['город', 'село'])]
    cases = edges[edges.origin_id.isin(examples.index)].merge(
        examples[['name', 'region', 'settlement_type_2021', 'population_2021']],
        left_on='origin_id', right_index=True, validate='many_to_one')
    cases.to_csv(output / 'saratov_examples.csv', index=False)
    pd.DataFrame(table).to_csv(output / 'urban_local_offer_coverage.csv', index=False)
    result = {'scope': 'recorded NP identity and membership criterion; not a true national system count',
              'counts': counts, 'urban_coverage': table, 'admitted_identity_coverage': coverage,
              'false_local_flag_does_not_prove_no_institution': True,
              'expected_2000_3000_not_used_as_target': True,
              'inputs_sha256': {p.name: sha256(p) for p in
                                [scenario / 'daily_edges.parquet', scenario / 'centre_stars.parquet', reference]}}
    (output / 'count_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['scenario', 'reference', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    audit(args.scenario, args.reference, args.output)
