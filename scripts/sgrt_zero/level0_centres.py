"""Register direct level-zero centres, separating own offers from external use.

Every retained centre has a positive whole-NP identity and at least one external
positive whole participant by a basic function. No transitive union, population
rank or required intersection of all three functions is used.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from lower_profile_quality import sha256

CORE = ['school', 'medical_basic', 'grocery']
LABELS = {3: 'Записаны три базовые функции', 2: 'Записаны две базовые функции',
          1: 'Записана одна базовая функция', 0: 'Собственное предложение не установлено'}


def build(scenario, output):
    output.mkdir(parents=True, exist_ok=True)
    stars = pd.read_parquet(scenario / 'centre_stars.parquet')
    members = pd.read_parquet(scenario / 'centre_memberships.parquet')
    edges = pd.read_parquet(scenario / 'daily_edges.parquet')
    core = edges[edges.service_family.isin(CORE)].copy()
    role = stars.get('centre_ordinary_spatial_or_nonadditive_context', stars.centre_ordinary_credited_or_nonadditive_context)
    centres = stars[stars.centre_unmarked_whole_record & stars.centre_positive_population_known
                    & role
                    & stars.centre_in_analysis_origin
                    & stars.one_or_more_core_external_positive_whole.gt(0)].copy()
    centres['level'] = 0
    centres['own_known_basic_function_count'] = centres.centre_own_selected_core_family_count
    centres['type_code'] = centres.own_known_basic_function_count.map({
        3: 'recorded_three_basic_functions', 2: 'recorded_two_basic_functions',
        1: 'recorded_one_basic_function', 0: 'own_offer_unknown'})
    centres['type_label'] = centres.own_known_basic_function_count.map(LABELS)
    local = core[core.l0_admitted & core.origin_id.eq(core.provider_settlement_id)]
    own = local.groupby('origin_id').service_family.agg(lambda x: json.dumps(sorted(set(x))))
    centres['own_known_basic_functions_json'] = centres.centre_settlement_id.map(own).fillna('[]')
    own_documented=local.loc[local.get('provider_identity_evidence_tier',pd.Series(None,index=local.index)).eq(
        'documented_official_address_dated_school_presence'),'origin_id']
    centres['own_offer_includes_documented_dated_school_presence']=centres.centre_settlement_id.isin(own_documented)
    historical=local.get('provider_historical_source_only',pd.Series(False,index=local.index)).fillna(False)
    historical=historical.astype(str).str.lower().isin(['true','1','1.0'])
    centres['own_offer_includes_historical_only_source']=centres.centre_settlement_id.isin(local.loc[historical,'origin_id'])
    centres['unestablished_functions_are_not_confirmed_absent'] = True
    centres['external_participant_count'] = centres.one_or_more_core_external_positive_whole
    centres['core_diameter_km'] = centres['1_core_subset_geodesic_diameter_km']
    centres['full_service_centre_without_same_three_external_participant'] = (
        centres.own_known_basic_function_count.eq(3) & centres.all_three_core_external_positive_whole.eq(0))
    centres['rank_is_not_population_class'] = True
    centres['exclusive_partition'] = False
    centres['observed_trips_verified'] = False
    selected = members[members.star_id.isin(centres.star_id)
                       & members.in_1_core_positive_whole_subset].copy()
    if selected.duplicated(['star_id', 'origin_id']).any():
        raise ValueError('A centre-member pair was repeated')
    uncredited = (selected.population_role.eq('ordinary_settlement_record')
                  & selected.population_2021.gt(0) & ~selected.budget_population_credit.fillna(False))
    uncredited_counts = selected[uncredited].groupby('star_id').size()
    centres['positive_uncredited_member_records'] = centres.star_id.map(uncredited_counts).fillna(0).astype(int)
    centres['population_budget_partial'] = (centres.positive_uncredited_member_records.gt(0)
                                           | centres.centre_population_is_nonadditive_context)
    centres['population_2021_credited_budget_sum_not_total_population'] = centres.star_id.map(
        selected.groupby('star_id').budget_population_within_star.sum(min_count=1))
    anchors = selected[selected.member_role.eq('centre')].set_index('star_id')
    centres['centre_population_2021_source_value'] = centres.star_id.map(anchors.population_2021)
    centres['centre_population_budget_credit'] = centres.star_id.map(anchors.budget_population_credit)
    centres['lat'] = centres.star_id.map(anchors.lat)
    centres['lon'] = centres.star_id.map(anchors.lon)
    retained_links = core[core.l0_admitted & core.provider_settlement_id.isin(centres.centre_settlement_id)].copy()
    tier = retained_links.get('provider_identity_evidence_tier', pd.Series(None, index=retained_links.index))
    retained_links['ownership_uses_cartographic_proxy'] = tier.eq('dated_cartographic_locality_containment')
    quality = retained_links.groupby('provider_settlement_id').ownership_uses_cartographic_proxy.agg(['sum', 'size'])
    centres['selected_links_with_cartographic_ownership'] = centres.centre_settlement_id.map(quality['sum']).fillna(0).astype(int)
    centres['selected_basic_links'] = centres.centre_settlement_id.map(quality['size']).fillna(0).astype(int)
    centres['ownership_evidence_class'] = centres.selected_links_with_cartographic_ownership.map(
        lambda n: 'includes_dated_cartographic_proxy' if n else 'retained_literal_or_registry_evidence')
    # Own function count and external support are independent dimensions.
    counts = selected[selected.member_role.eq('direct_surroundings')].groupby('star_id').size()
    expected = centres.set_index('star_id').external_participant_count.sort_index()
    actual = counts.reindex(expected.index, fill_value=0).sort_index()
    if not expected.astype(int).equals(actual.astype(int)):
        raise ValueError('Registered external participants differ from direct basic memberships')
    if centres.type_code.isna().any():
        raise ValueError('Every level-zero centre needs an explicit offer-completeness type')
    centres.to_parquet(output / 'level0_centres.parquet', index=False, compression='zstd')
    selected.to_parquet(output / 'level0_memberships.parquet', index=False, compression='zstd')
    retained_links.to_parquet(output / 'level0_basic_links.parquet', index=False, compression='zstd')
    centre_columns = ['centre_settlement_id', 'centre_name', 'centre_region', 'type_code', 'type_label',
                      'lat', 'lon', 'own_known_basic_function_count',
                      'own_known_basic_functions_json', 'external_participant_count', 'core_diameter_km',
                      'ownership_evidence_class', 'selected_links_with_cartographic_ownership',
                      'population_budget_partial', 'centre_population_2021_source_value',
                      'own_offer_includes_documented_dated_school_presence','own_offer_includes_historical_only_source']
    centres[centre_columns].to_csv(output / 'level0_centres.csv', index=False)
    full = centres.own_known_basic_function_count.eq(3)
    summary = {'registered_level0_centres': len(centres),
               'by_recorded_own_basic_function_count': centres.own_known_basic_function_count.value_counts().sort_index().to_dict(),
               'full_three_function_centres_with_external_participants': int(full.sum()),
               'full_centres_without_same_three_external_participant': int(centres.full_service_centre_without_same_three_external_participant.sum()),
               'strict_same_three_external_diagnostic_subset': int((full & centres.all_three_core_external_positive_whole.gt(0)).sum()),
               'centres_using_cartographic_ownership': int(centres.selected_links_with_cartographic_ownership.gt(0).sum()),
               'centres_with_partial_population_budget': int(centres.population_budget_partial.sum()),
               'centres_with_own_documented_dated_school_presence':int(centres.own_offer_includes_documented_dated_school_presence.sum()),
               'centres_with_own_historical_only_evidence':int(centres.own_offer_includes_historical_only_source.sum()),
               'centre_member_pairs': len(selected), 'unique_participant_records': int(selected.origin_id.nunique()),
               'diameter_km': {name: float(centres.core_diameter_km.quantile(q)) for name, q in [('median', .5), ('p95', .95), ('maximum', 1.)]},
               'full_centres_diameter_km': {name: float(centres.loc[full, 'core_diameter_km'].quantile(q)) for name, q in [('median', .5), ('p95', .95), ('maximum', 1.)]},
               'own_function_count_is_not_external_support_count': True,
               'unknown_function_is_not_confirmed_absent': True,
               'overlapping_direct_catchments_not_exclusive_country_partition': True,
               'actual_trips_observed': False,
               'inputs_sha256': {p.name: sha256(p) for p in [scenario / 'centre_stars.parquet', scenario / 'centre_memberships.parquet', scenario / 'daily_edges.parquet']}}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build(a.scenario, a.output)
