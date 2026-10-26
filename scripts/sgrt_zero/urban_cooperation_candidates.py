#!/usr/bin/env python3
"""Conditional urban cooperation links, with an external eFUA2015 envelope.

No new territorial partition or empirical rank is assigned. The external
envelope is an input constraint and therefore cannot validate these results.
Every living whole member of both the primary and overlapping functional L0
footprints must satisfy the polygon and current directed-road scenario.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from pyproj import Transformer
import shapely
from hierarchy_gravity_candidates import digest

COMPONENTS = ['partial_organisation_workers_2025_territorial',
              'medical_care_address_ids_in_known_2021_parent',
              'credited_population_2021_in_known_parent']


def whole_footprint_guard(footprints, inside_ids, costs, budget):
    """Missing geometry/route never passes; compare every footprint member."""
    work = footprints.copy()
    work['inside'] = work.origin_id.isin(inside_ids)
    work['cost'] = work.origin_id.map(costs)
    work['known_road'] = np.isfinite(work.cost) & work.cost.ge(0)
    work['within_budget'] = work.known_road & work.cost.le(budget)
    return work.groupby('unit_id').agg(
        checked_living_whole_records=('origin_id', 'nunique'),
        whole_footprint_inside=('inside', 'all'),
        whole_footprint_road_known=('known_road', 'all'),
        whole_footprint_within_time=('within_budget', 'all'),
        maximum_checked_minutes=('cost', 'max'))


def territorial_comparison(child_code, parent_code, profiles):
    # Municipality workers are never assigned to a settlement. Same municipal
    # actor cannot establish dominance of one NP over another NP inside it.
    if pd.isna(child_code) or pd.isna(parent_code):
        return 'unknown_territorial_profile'
    if child_code == parent_code:
        return 'same_municipal_actor_np_rank_unidentified'
    if child_code not in profiles.index or parent_code not in profiles.index:
        return 'unknown_territorial_profile'
    child = pd.to_numeric(profiles.loc[child_code, COMPONENTS], errors='coerce')
    parent = pd.to_numeric(profiles.loc[parent_code, COMPONENTS], errors='coerce')
    if not np.isfinite(child).all() or not np.isfinite(parent).all():
        return 'incomplete_territorial_profile'
    if parent.ge(child).all() and parent.gt(child).any():
        return 'parent_territory_dominates_recorded_components'
    return 'territorial_dominance_not_established'


def run(args):
    input_hashes = {key: digest(getattr(args,key)) for key in [
        'reference','memberships','units','service_memberships','pairs','polygons',
        'efua_status','parent_crosswalk','municipal_profiles']}
    ref = pd.read_parquet(args.reference).dropna(subset=['source_record_id']).set_index('source_record_id')
    if not ref.index.is_unique:
        raise ValueError('Non-null reference identities must be unique')
    members = pd.read_parquet(args.memberships)
    units = pd.read_parquet(args.units)
    stars = pd.read_parquet(args.service_memberships,
                            columns=['centre_settlement_id', 'origin_id'])
    positive = set(members.loc[members.positive_whole_origin.eq(True), 'origin_id'])
    primary = members.loc[members.unit_id.notna(), ['unit_id', 'origin_id']]
    anchor_to_unit = units.set_index('core_origin_id').unit_id
    stars['unit_id'] = stars.centre_settlement_id.map(anchor_to_unit)
    footprints = pd.concat([primary, stars[['unit_id', 'origin_id']]], ignore_index=True)
    footprints = footprints[footprints.unit_id.notna() & footprints.origin_id.isin(positive)].drop_duplicates()
    costs = pd.read_parquet(args.pairs)
    polygons = pd.read_parquet(args.polygons).set_index('eFUA_ID')
    efua_status = pd.read_parquet(args.efua_status).set_index('source_record_id')
    contexts = pd.read_parquet(args.parent_crosswalk).set_index('source_record_id')
    profiles = pd.read_parquet(args.municipal_profiles)
    profiles['oktmo'] = profiles.oktmo.astype(str)
    profiles = profiles.set_index('oktmo')
    eligible = units[units.eligible_as_higher_child.eq(True)].copy()
    eligible['core_name'] = eligible.core_origin_id.map(ref.name)
    eligible['core_lat'] = eligible.core_origin_id.map(ref.lat)
    eligible['core_lon'] = eligible.core_origin_id.map(ref.lon)
    eligible['child_municipality_code'] = eligible.core_origin_id.map(contexts.matched_2021_parent_code)
    # Recompute containment from exact CURRENT reference coordinates, rather
    # than treating historical membership labels as spatial truth.
    reference_points = ref.loc[members.origin_id]
    out = []
    for destination, part in costs.groupby('destination_id'):
        efuas = json.loads(efua_status.loc[destination, 'external_efua_ids_json'])
        if len(efuas) != 1:
            raise ValueError('Pilot parent must match one external eFUA envelope')
        efua = efuas[0]
        polygon = shapely.from_wkb(polygons.loc[efua, 'geometry_wkb'])
        transformer = Transformer.from_crs('EPSG:4326', polygons.loc[efua, 'geometry_crs'], always_xy=True)
        x, y = transformer.transform(reference_points.lon.to_numpy(), reference_points.lat.to_numpy())
        inside = shapely.covers(polygon, shapely.points(x, y))
        inside_ids = set(reference_points.index[inside])
        if destination not in inside_ids:
            raise ValueError('Current exact parent point lies outside its proposed external envelope')
        parent_code = contexts.loc[destination, 'matched_2021_parent_code']
        current_cost = part.set_index('origin_id').cost_minutes
        comparison = {code: territorial_comparison(code, parent_code, profiles)
                      for code in eligible.child_municipality_code.drop_duplicates()}
        for budget in args.time_budgets:
            guard = whole_footprint_guard(footprints, inside_ids, current_cost, budget)
            result = eligible.merge(guard, left_on='unit_id', right_index=True, how='left')
            result['parent_origin_id'] = destination
            result['parent_name'] = ref.loc[destination, 'name']
            result['parent_lat'] = ref.loc[destination, 'lat']
            result['parent_lon'] = ref.loc[destination, 'lon']
            result['external_efua_id'] = efua
            result['time_budget_scenario_minutes'] = budget
            result['parent_municipality_code'] = parent_code
            result['core_inside_external_envelope'] = result.core_origin_id.isin(inside_ids)
            result['core_cost_minutes'] = result.core_origin_id.map(current_cost)
            result['core_only_pass'] = (result.core_inside_external_envelope
                & result.core_cost_minutes.le(budget) & result.core_origin_id.ne(destination))
            result['whole_footprint_pass'] = (result.whole_footprint_inside.eq(True)
                & result.whole_footprint_road_known.eq(True) & result.whole_footprint_within_time.eq(True)
                & result.core_only_pass & result.core_origin_id.ne(destination))
            result['territorial_scale_comparison'] = result.child_municipality_code.map(comparison)
            result['spatial_time_admissible'] = result.whole_footprint_pass
            result['distinct_municipal_actor_with_recorded_dominance'] = (
                result.territorial_scale_comparison.eq('parent_territory_dominates_recorded_components'))
            result['conditional_cooperation_link_with_territorial_scale_evidence'] = (
                result.spatial_time_admissible & result.distinct_municipal_actor_with_recorded_dominance)
            result['candidate_relation_status'] = np.where(
                result.conditional_cooperation_link_with_territorial_scale_evidence,
                'conditional_cooperation_link_not_observed_flow', np.where(result.spatial_time_admissible,
                    'spatial_time_admissible_functional_rank_unidentified', 'held_by_spatial_or_road_guard'))
            # Keep all units with an admitted core so a remote omitted member
            # cannot disappear from the diagnostics of rejected candidates.
            out.append(result[result.core_only_pass].copy())
    links = pd.concat(out, ignore_index=True)
    links['territorial_assignment_established'] = False
    links['external_envelope_independently_validates_result'] = False
    links['jobs_assigned_to_np'] = False
    args.output.mkdir(parents=True, exist_ok=True)
    links.to_parquet(args.output/'urban_cooperation_candidates.parquet', index=False)
    accepted_pairs = links.loc[links.spatial_time_admissible,
                              ['unit_id','parent_origin_id','parent_name']].drop_duplicates()
    compositions = accepted_pairs.merge(footprints, on='unit_id', how='inner')
    compositions['name'] = compositions.origin_id.map(ref.name)
    compositions['lat'] = compositions.origin_id.map(ref.lat)
    compositions['lon'] = compositions.origin_id.map(ref.lon)
    compositions = compositions.merge(costs[['origin_id','destination_id','cost_minutes','pair_status']],
        left_on=['origin_id','parent_origin_id'], right_on=['origin_id','destination_id'], how='left',
        validate='many_to_one').drop(columns=['destination_id'])
    compositions['scope'] = 'living_whole_union_primary_and_original_functional_footprints'
    compositions.to_parquet(args.output/'candidate_footprint_members.parquet', index=False)
    summary = []
    for (name, budget), part in links.groupby(['parent_name', 'time_budget_scenario_minutes']):
        accepted = part[part.whole_footprint_pass]
        summary.append({'parent': name, 'minutes': budget, 'core_only_units': len(part),
            'whole_footprint_candidates': len(accepted),
            'candidate_external_serving_L0_anchors': int(accepted.unit_role.eq('external_serving_anchor').sum()),
            'candidate_local_self_profile_contexts': int(accepted.unit_role.eq('local_singleton_known_profile').sum()),
            'rejected_after_whole_footprint_check': int((~part.whole_footprint_pass).sum()),
            'candidate_scale_comparisons': accepted.territorial_scale_comparison.value_counts().to_dict(),
            'maximum_whole_footprint_minutes': float(accepted.maximum_checked_minutes.max()) if len(accepted) else None})
    named = links[links.core_name.isin(['Энгельс','Подольск','Химки','Копейск','Берёзовский','Зеленодольск'])]
    named[['core_name','parent_name','time_budget_scenario_minutes','whole_footprint_pass',
           'checked_living_whole_records','maximum_checked_minutes','territorial_scale_comparison']].to_csv(
               args.output/'named_cooperation_examples.csv', index=False)
    payload = {'interpretation': 'conditional_urban_cooperation_not_SGRT_hierarchy',
        'external_envelope_epoch': 2015, 'external_envelope_is_observed_russian_commuting': False,
        'envelope_is_input_not_independent_validation': True,
        'whole_child_check_scope': 'union_of_living_whole_primary_and_original_functional_L0_footprints',
        'time_scenarios_are_not_calibrated_commuting_thresholds': True,
        'municipal_workforce_never_disaggregated_to_np': True,
        'living_whole_footprint_pairs': len(footprints),
        'unknown_population_primary_records_not_evaluated_as_confirmed_demand': int(
            (members.unit_id.notna() & members.population_2021.isna()).sum()),
        'input_sha256': input_hashes, 'implementation_sha256': digest(Path(__file__)), 'summary': summary}
    (args.output/'urban_cooperation_summary.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['reference','memberships','units','service-memberships','pairs','polygons',
                 'efua-status','parent-crosswalk','municipal-profiles','output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--time-budgets', nargs='+', type=float, default=[30.,60.,90.])
    run(parser.parse_args())
