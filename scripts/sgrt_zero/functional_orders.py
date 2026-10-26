#!/usr/bin/env python3
"""Direct whole-subsystem associations for successively considered functions.

These explicit service scenarios are not an empirically identified ranking of
Russian agglomerations. A provider must be inside an existing subsystem; every
member must reach its selected provider within the declared time. The anchoring
subsystem must serve itself. Thus A -> B -> C cannot silently become one parent.
Unresolved lower memberships and split/unknown destinations remain unresolved.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

try:
    from .hierarchy import coordinate_diameter
except ImportError:
    from hierarchy import coordinate_diameter


STAGES = [
    {'name': 'physician_primary', 'families': ['medical_physician_primary'], 'minutes': 30.},
    {'name': 'hospital_and_college', 'families': ['medical_inpatient', 'vocational_education'], 'minutes': 60.},
    {'name': 'specialized_university_shopping',
     'families': ['medical_specialized', 'higher_education', 'shopping_centre'], 'minutes': 90.},
    {'name': 'hightech_reported_profile', 'families': ['medical_hightech_licensed'], 'minutes': 120.,
     'territorial_merge': False},
]
ROUTE_COLUMNS = ['origin_id', 'provider_settlement_id', 'provider_site_id',
                 'cost_minutes', 'known_local_supply', 'road_endpoint_accepted', 'road_endpoint_status',
                 'provider_named_child_only_contingent',
                 'provider_restriction_scope_unknown', 'provider_historical_source_only',
                 'provider_actual_operational_status_verified', 'route_status', 'source_id', 'source_year']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def stable_parent(stage, children):
    signature = stage + '|' + '|'.join(sorted(str(x) for x in children))
    return 'functional-parent:' + hashlib.sha256(signature.encode()).hexdigest()[:24]


def read_route(path):
    fields = set(pq.read_schema(path).names)
    required = {'origin_id', 'provider_settlement_id', 'cost_minutes'}
    if not required <= fields:
        raise ValueError('Missing route columns: ' + ', '.join(sorted(required - fields)))
    out = pd.read_parquet(path, columns=[x for x in ROUTE_COLUMNS if x in fields])
    if not out.origin_id.is_unique:
        raise ValueError('A route family must have one outcome per origin')
    return out


def direct_promotion(members, routes, families, minutes, *, stage, depth=None, guard_members=None,
                     eligible_parent_units=None, eligible_child_units=None, demand_origin_ids=None):
    """Return parent members, child crosswalk, candidates and accepted links.

    Families are a declared bundle for one scenario, not weighted votes. All
    outcomes for every child member must point into the same existing parent.
    A missing route or unknown provider identity never passes the test.
    """
    if members.origin_id.duplicated().any():
        raise ValueError('Lower memberships must be exclusive, including unresolved rows')
    if not families or len(families) != len(set(families)):
        raise ValueError('Require a nonempty bundle of distinct new functions')
    if not np.isfinite(minutes) or minutes <= 0:
        raise ValueError('Time must be a positive finite scenario value')
    primary_lower = members.loc[members.unit_id.notna(), ['origin_id', 'unit_id']].copy()
    owner = primary_lower.set_index('origin_id').unit_id
    lower = primary_lower if guard_members is None else guard_members[['origin_id', 'unit_id']].drop_duplicates()
    if not set(lower.unit_id) <= set(primary_lower.unit_id):
        raise ValueError('A constraint child is outside the primary unit axis')
    active_primary = primary_lower if demand_origin_ids is None else primary_lower[primary_lower.origin_id.isin(demand_origin_ids)]
    if demand_origin_ids is not None:
        lower = lower[lower.origin_id.isin(demand_origin_ids)]
    baseline = set(active_primary.itertuples(index=False, name=None))
    if not baseline <= set(lower.itertuples(index=False, name=None)):
        raise ValueError('Functional guard omits a primary child member')
    sizes = lower.groupby('unit_id').size()
    primary_sizes = primary_lower.groupby('unit_id').size()
    active_sizes = active_primary.groupby('unit_id').size()
    frames = []
    per_family = []
    for family in families:
        source = routes[family]
        if not source.origin_id.is_unique:
            raise ValueError('Duplicate route outcome in ' + family)
        x = lower.merge(source, on='origin_id', how='left', validate='many_to_one')
        x['family'] = family
        x['provider_unit_id'] = x.provider_settlement_id.map(owner)
        cost = pd.to_numeric(x.cost_minutes, errors='coerce')
        explicit_child_only = x.get('provider_named_child_only_contingent', pd.Series(False, index=x.index)).fillna(False).eq(True)
        endpoint = x.get('road_endpoint_accepted', pd.Series(False, index=x.index)).fillna(False).eq(True)
        local = x.get('known_local_supply', pd.Series(False, index=x.index)).fillna(False).eq(True)
        x['route_admitted'] = (x.provider_settlement_id.notna() & np.isfinite(cost)
                               & cost.ge(0) & cost.le(minutes + 1e-8) & ~explicit_child_only
                               & (endpoint | local))
        x['provider_in_resolved_lower_system'] = x.provider_unit_id.notna()
        x['provider_np_identity_unknown'] = x.provider_settlement_id.isna()
        x['provider_known_outside_resolved_lower_system'] = x.provider_settlement_id.notna() & x.provider_unit_id.isna()
        x['explicit_child_only_provider'] = explicit_child_only
        x['far_known_route'] = np.isfinite(cost) & cost.gt(minutes + 1e-8)
        x['unknown_route_cost'] = ~np.isfinite(cost)
        x['reported_access_scope_unknown'] = x.get('provider_restriction_scope_unknown', pd.Series(True, index=x.index)).fillna(True).eq(True)
        x['reported_historical_only'] = x.get('provider_historical_source_only', pd.Series(False, index=x.index)).fillna(False).eq(True)
        x['reported_operation_verified'] = x.get('provider_actual_operational_status_verified', pd.Series(False, index=x.index)).fillna(False).eq(True)
        x['usable_destination'] = x.route_admitted & x.provider_in_resolved_lower_system
        x['selected_cost_minutes'] = cost.where(x.usable_destination)
        x['selected_destination'] = x.provider_unit_id.where(x.usable_destination)
        grouped = x.groupby('unit_id', sort=False)
        a = grouped.agg(member_outcomes=('origin_id', 'size'),
                        usable_member_outcomes=('usable_destination', 'sum'),
                        admitted_member_outcomes=('route_admitted', 'sum'),
                        unknown_provider_np_outcomes=('provider_np_identity_unknown', 'sum'),
                        provider_known_outside_resolved_lower_outcomes=('provider_known_outside_resolved_lower_system', 'sum'),
                        explicit_child_only_provider_outcomes=('explicit_child_only_provider', 'sum'),
                        far_known_route_outcomes=('far_known_route', 'sum'),
                        unknown_route_cost_outcomes=('unknown_route_cost', 'sum'),
                        unknown_access_scope_outcomes=('reported_access_scope_unknown', 'sum'),
                        historical_only_provider_outcomes=('reported_historical_only', 'sum'),
                        operation_verified_provider_outcomes=('reported_operation_verified', 'sum'),
                        destinations=('selected_destination', 'nunique'),
                        maximum_directed_minutes=('selected_cost_minutes', 'max'))
        a['family'] = family
        per_family.append(a.reset_index())
        frames.append(x)
    links = pd.concat(frames, ignore_index=True)
    rows = []
    grouped_links = {uid: group for uid, group in links.groupby('unit_id', sort=True)}
    for uid in sorted(primary_sizes.index):
        group = grouped_links.get(uid, links.iloc[:0])
        targets = sorted(set(group.loc[group.usable_destination, 'provider_unit_id']))
        n = int(sizes.get(uid, 0))
        complete = bool(n > 0 and group.usable_destination.sum() == n * len(families))
        single = bool(complete and len(targets) == 1)
        status = ('no_confirmed_positive_whole_demand' if not n else
                  'no_usable_destination' if not targets else
                  'partial_member_or_function_coverage' if not complete else
                  'split_destination_systems' if len(targets) > 1 else 'single_complete_destination')
        eligible_child = eligible_child_units is None or uid in eligible_child_units
        if not eligible_child:
            status = 'lower_unit_not_eligible_as_child'
        rows.append({'child_unit_id': uid, 'member_records': n,
                     'primary_member_records': int(primary_sizes[uid]),
                     'active_primary_demand_records': int(active_sizes.get(uid, 0)),
                     'additional_functional_constraint_records': n - int(active_sizes.get(uid, 0)),
                     'eligible_as_child': eligible_child,
                     'functional_overlap_guard_applied': guard_members is not None,
                     'required_family_count': len(families),
                     'usable_member_function_outcomes': int(group.usable_destination.sum()),
                     'admitted_member_function_outcomes': int(group.route_admitted.sum()),
                     'destination_system_count': len(targets),
                     'destination_unit_id': targets[0] if single and eligible_child else None,
                     'complete_single_destination': single and eligible_child,
                     'maximum_directed_minutes': float(group.selected_cost_minutes.max()) if group.usable_destination.any() else None,
                     'candidate_status': status})
    candidates = pd.DataFrame(rows)
    if not len(candidates):
        candidates = pd.DataFrame(columns=['child_unit_id', 'destination_unit_id', 'complete_single_destination',
                                          'maximum_directed_minutes', 'candidate_status'])
    destination = candidates.set_index('child_unit_id').destination_unit_id.to_dict()
    anchors = {uid for uid, target in destination.items() if uid == target}
    if eligible_parent_units is not None:
        anchors &= set(eligible_parent_units)
    proposed = {uid: target if target in anchors else uid for uid, target in destination.items()}
    group_children = {}
    for uid, anchor in proposed.items():
        group_children.setdefault(anchor, []).append(uid)
    parent_map = {}
    depth = depth or {}
    depths = {}
    new_mergers = {}
    anchor_for_parent = {}
    for anchor, children in group_children.items():
        changed = len(children) > 1
        parent = stable_parent(stage, children) if changed else children[0]
        for uid in children:
            parent_map[uid] = parent
        depths[parent] = max(int(depth.get(uid, 0)) for uid in children) + int(changed)
        new_mergers[parent] = changed
        anchor_for_parent[parent] = anchor
    crosswalk = candidates.copy()
    crosswalk['parent_unit_id'] = crosswalk.child_unit_id.map(parent_map)
    crosswalk['target_is_self_servicing_anchor'] = crosswalk.destination_unit_id.isin(anchors)
    crosswalk['merged_to_direct_anchor'] = crosswalk.child_unit_id.ne(crosswalk.parent_unit_id)
    crosswalk['stage_name'] = stage
    crosswalk['time_limit_minutes'] = float(minutes)
    result = members.copy()
    result['child_unit_id'] = result.unit_id
    result['unit_id'] = result.unit_id.map(parent_map).astype('string')
    result['effective_merge_depth'] = result.unit_id.map(depths).astype('Int64')
    result['stage_name'] = stage
    result['higher_stage_membership_status'] = np.where(result.unit_id.isna(), 'unresolved_lower_membership',
        np.where(result.child_unit_id.ne(result.unit_id).fillna(False), 'joined_by_new_function', 'lower_subsystem_retained'))
    if not result.origin_id.equals(members.origin_id):
        raise AssertionError('Origins or ordering changed')
    if not result.unit_id.notna().equals(members.unit_id.notna()):
        raise AssertionError('An unresolved origin was assigned or a resolved origin lost')
    # One child maps to one parent. No whole child can be silently split.
    assert crosswalk.child_unit_id.is_unique
    links['parent_unit_id'] = links.unit_id.map(parent_map)
    links['admitted_parent_association'] = (links.usable_destination
        & links.unit_id.map(proposed).eq(links.provider_unit_id)
        & links.provider_unit_id.isin(anchors))
    metadata = {'depths': depths, 'new_mergers': new_mergers,
                'anchor_for_parent': anchor_for_parent,
                'family_coverage': pd.concat(per_family, ignore_index=True)}
    return result, crosswalk, candidates, links, metadata


def summarize_units(members, crosswalk, links, meta, reference, stage_index, stage, anchor_representatives=None):
    reference = reference.dropna(subset=['source_record_id']).set_index('source_record_id')
    if not reference.index.is_unique:
        raise ValueError('Reference identities must be unique')
    known = members[members.unit_id.notna()]
    joined = known[['origin_id', 'unit_id']].merge(
        reference[['name', 'region', 'lat', 'lon', 'population_2021', 'budget_population_credit']],
        left_on='origin_id', right_index=True, how='left', validate='one_to_one')
    accepted_links = links[links.admitted_parent_association]
    by_links = {uid: group for uid, group in accepted_links.groupby('parent_unit_id', sort=False)}
    parent_children = crosswalk.groupby('parent_unit_id').child_unit_id.apply(list).to_dict()
    child_representatives = known.groupby('child_unit_id').origin_id.first().to_dict()
    if anchor_representatives:
        child_representatives.update(anchor_representatives)
    guard_origins = links[['parent_unit_id', 'origin_id']].drop_duplicates().groupby('parent_unit_id').origin_id.apply(list).to_dict()
    evaluated_ids = set(members.loc[members.get('upper_demand_evaluated', pd.Series(True, index=members.index)).fillna(False), 'origin_id'])
    confirmed_ids = set(members.loc[members.get('confirmed_positive_whole_demand', pd.Series(True, index=members.index)).fillna(False), 'origin_id'])
    # Build the national membership masks once. Calling isin(100k IDs) for
    # each tiny unit repeatedly reconstructs the same national hash table.
    joined['_confirmed_demand'] = joined.origin_id.isin(confirmed_ids)
    joined['_evaluated_demand'] = joined.origin_id.isin(evaluated_ids)
    rows = []
    for uid, group in joined.groupby('unit_id', sort=True):
        association = by_links.get(uid)
        provider_ids = sorted(set(association.provider_settlement_id.dropna())) if association is not None else []
        # Exact representative point, not an invented geographic centroid.
        if provider_ids:
            representative = provider_ids[0]
        else:
            anchor = meta['anchor_for_parent'][uid]
            representative = str(child_representatives[anchor])
        ref = reference.loc[representative]
        if representative not in set(group.origin_id):
            raise AssertionError('A representative centre is not a primary parent member')
        credit = group.budget_population_credit.fillna(False).eq(True)
        pop = pd.to_numeric(group.population_2021, errors='coerce')
        children = parent_children[uid]
        guard_ids = guard_origins.get(uid, group.origin_id.tolist())
        guard_points = reference.reindex(guard_ids)
        row = {'unit_id': uid, 'stage_index': stage_index, 'stage_name': stage['name'],
               'effective_merge_depth': meta['depths'][uid],
               'new_territorial_merger': meta['new_mergers'][uid],
               'direct_child_count': len(children), 'member_records': len(group),
               'confirmed_positive_whole_demand_records': int(group._confirmed_demand.sum()),
               'evaluated_demand_source_records': int(group._evaluated_demand.sum()),
               'source_context_records_retained_not_demand': int((~group._evaluated_demand).sum()),
               'unknown_population_source_records': int(group.population_2021.isna().sum()),
               'unknown_population_demand_status': 'not_evaluated_for_unknown_demand' if group.population_2021.isna().any() else 'no_unknown_population_record_in_primary_composition',
               'checked_functional_member_records': len(guard_ids),
               'anchor_child_unit_id': meta['anchor_for_parent'][uid],
               'representative_id': representative, 'name': str(ref['name']), 'region': str(ref['region']),
               'lat': float(ref['lat']), 'lon': float(ref['lon']),
               'current_function_provider_np_ids_json': json.dumps(provider_ids, ensure_ascii=False),
               'current_function_provider_np_count': len(provider_ids),
               'geodesic_point_diameter_km': coordinate_diameter(group.lat, group.lon),
               'checked_functional_point_diameter_km': coordinate_diameter(guard_points.lat, guard_points.lon),
               'maximum_selected_function_minutes': float(association.cost_minutes.max()) if association is not None else None,
               'credited_population_partial_sum_2021': float(pop[credit].sum(min_count=1)),
               'population_budget_partial': bool((~credit | pop.isna()).any()),
               'time_limit_minutes': float(stage['minutes']),
               'observed_flows_verified': False, 'agglomeration_order_identified': False,
               'upper_medical_need_conditional': any(family.startswith('medical_') for family in stage['families']),
               'universal_patient_suitability_established': False,
               'current_upper_unknown_access_scope_outcomes': (int(association.reported_access_scope_unknown.sum())
                                                               if association is not None else None),
               'current_upper_historical_only_outcomes': (int(association.reported_historical_only.sum())
                                                          if association is not None else None),
               'current_upper_operation_verified_outcomes': (int(association.reported_operation_verified.sum())
                                                             if association is not None else None),
               'model_service_association_not_observed_sgrt': True,
               'value': int(meta['depths'][uid])}
        rows.append(row)
    return pd.DataFrame(rows)


def functional_guard_members(members, service_memberships):
    """Union all original functional footprints of centres in each current unit.

    A record shared by two original footprints may constrain both children. It
    is never copied into the exclusive primary membership as a side effect.
    """
    primary = members.loc[members.unit_id.notna(), ['origin_id', 'unit_id']]
    centre_owner = primary.rename(columns={'origin_id': 'centre_settlement_id'})
    extra = service_memberships[['centre_settlement_id', 'origin_id']].merge(
        centre_owner, on='centre_settlement_id', how='inner', validate='many_to_one')
    return pd.concat([primary, extra[['origin_id', 'unit_id']]], ignore_index=True).drop_duplicates()


def run(membership_path, reference_path, route_directory, medical_route_directory, output, *, time_scale=1.,
        service_membership_path=None, unit_path=None, demand_scope='positive-whole'):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    members = pd.read_parquet(membership_path)
    if not {'origin_id', 'unit_id'} <= set(members):
        raise ValueError('Common level-zero memberships require origin_id and nullable unit_id')
    if 'is_core' in members:
        members = members.rename(columns={'is_core': 'level0_is_core'})
    members['level0_unit_id'] = members.unit_id
    reference = pd.read_parquet(reference_path)
    service_memberships = pd.read_parquet(service_membership_path) if service_membership_path else None
    unit_metadata = pd.read_parquet(unit_path) if unit_path else None
    pop = pd.to_numeric(members.population_2021, errors='coerce')
    part_ok = members.part_status.eq('unmarked_whole_place_record')
    role_ok = members.population_role.isin(['ordinary_settlement_record', 'external_context_nonadditive'])
    confirmed_demand = pop.gt(0) & part_ok & role_ok
    if demand_scope not in {'positive-whole', 'all-source-records'}:
        raise ValueError('Unknown demand scope')
    demand_ids = set(members.loc[confirmed_demand, 'origin_id']) if demand_scope == 'positive-whole' else None
    members['upper_demand_evaluated'] = confirmed_demand if demand_ids is not None else True
    members['confirmed_positive_whole_demand'] = confirmed_demand
    families = sorted({family for stage in STAGES for family in stage['families']})
    paths = {family: Path(medical_route_directory if family.startswith('medical_') else route_directory)
             / (family + '.parquet') for family in families}
    guarded_paths = [Path(membership_path), Path(reference_path), *paths.values(),
                     Path(__file__), Path(__file__).with_name('hierarchy.py')]
    if service_membership_path:
        guarded_paths.append(Path(service_membership_path))
    if unit_path:
        guarded_paths.append(Path(unit_path))
    source_inputs = {str(path): digest(path) for path in guarded_paths}
    routes = {family: read_route(path) for family, path in paths.items()}
    provider_sets = {family: set(frame.provider_settlement_id.dropna()) for family, frame in routes.items()}
    family_inventory = [{'family': family, 'selected_known_provider_nps': len(provider_sets[family]),
                         'origins_with_finite_route': int(np.isfinite(pd.to_numeric(frame.cost_minutes, errors='coerce')).sum())}
                        for family, frame in routes.items()]
    # A counterexample to assigning Moscow a unique top order from binary
    # presence alone. Select the real city among namesakes using its reference
    # population only for this descriptive audit, never for associations.
    city_examples = []
    for name in ['Москва', 'Санкт-Петербург', 'Казань', 'Новосибирск', 'Екатеринбург', 'Саратов']:
        candidates = reference[reference.name.eq(name) & reference.source_record_id.notna()]
        if len(candidates):
            row = candidates.loc[pd.to_numeric(candidates.population_2021, errors='coerce').idxmax()]
            city_examples.append({'name': name, 'source_record_id': row.source_record_id,
                                  'recorded_function_presence': {family: row.source_record_id in ids
                                                                 for family, ids in provider_sets.items()}})
    known_primary_origins = set(members.loc[members.unit_id.notna(), 'origin_id'])
    context_ids = set(unit_metadata.core_origin_id) if unit_metadata is not None else set()
    unresolved_provider_rows = []
    provider_coverage = []
    for family, ids in provider_sets.items():
        unresolved = sorted(ids - known_primary_origins)
        provider_coverage.append({'family': family, 'selected_known_provider_np': len(ids),
                                  'with_resolved_primary_membership': len(ids & known_primary_origins),
                                  'additional_local_context_metadata': len((ids - known_primary_origins) & context_ids),
                                  'still_without_any_context': len(ids - known_primary_origins - context_ids)})
        for provider in unresolved:
            unresolved_provider_rows.append({'family': family, 'provider_settlement_id': provider,
                                             'has_known_local_context_unit': provider in context_ids,
                                             'provider_is_not_absent': True,
                                             'strict_nested_parent_requires_primary_membership_resolution': True})
    pd.DataFrame(unresolved_provider_rows, columns=['family', 'provider_settlement_id', 'has_known_local_context_unit',
                                                   'provider_is_not_absent', 'strict_nested_parent_requires_primary_membership_resolution']).to_parquet(
                                                       output / 'unresolved_higher_provider_contexts.parquet', index=False)
    summary = {'scope': 'explicit_new_function_direct_whole_child_scenarios_not_agglomeration_ranking',
               'time_scale': float(time_scale), 'initial_resolved_units': int(members.unit_id.nunique()),
               'all_origin_records': len(members), 'initial_unresolved_origin_records': int(members.unit_id.isna().sum()),
               'population_used_as_attraction_weight': False, 'moscow_only_top_forced': False,
               'input_sha256': source_inputs, 'route_family_inventory': family_inventory,
               'major_city_function_signature_examples': city_examples,
               'higher_provider_primary_context_coverage': provider_coverage,
               'medical_source_provenance_warning': 'Separate supplied medical route version, not certified as rerouted by the 20261026 education/commerce physical-identity repair. Clinical suitability remains conditional.',
               'unrecorded_function_is_not_confirmed_absent': True, 'stages': []}
    summary['demand_scope'] = demand_scope
    summary['confirmed_positive_whole_origin_records'] = int(confirmed_demand.sum())
    summary['excluded_known_zero_population_records'] = int(pop.eq(0).sum()) if demand_ids is not None else 0
    summary['excluded_unknown_population_records'] = int(pop.isna().sum()) if demand_ids is not None else 0
    summary['excluded_positive_source_part_or_nonsettlement_records'] = int((pop.gt(0) & ~(part_ok & role_ok)).sum()) if demand_ids is not None else 0
    summary['unknown_demand_is_not_evaluated_not_assumed_zero'] = True
    depth = {}; previous_families = set()
    eligible_parents = (set(unit_metadata.loc[unit_metadata.eligible_as_higher_parent.fillna(False), 'unit_id'])
                        if unit_metadata is not None else None)
    eligible_children = (set(unit_metadata.loc[unit_metadata.eligible_as_higher_child.fillna(False), 'unit_id'])
                         if unit_metadata is not None else None)
    anchor_representatives = (dict(unit_metadata.loc[unit_metadata.core_membership_consistent.fillna(False),
                                                   ['unit_id', 'core_origin_id']].itertuples(index=False, name=None))
                              if unit_metadata is not None else {})
    for index, declaration in enumerate(STAGES, 1):
        stage = {**declaration, 'minutes': declaration['minutes'] * time_scale}
        if previous_families & set(stage['families']):
            raise ValueError('Repeated functions would manufacture additional levels')
        previous_families.update(stage['families'])
        folder = output / f'{index:02d}_{stage["name"]}'; folder.mkdir(exist_ok=True)
        guard = functional_guard_members(members, service_memberships) if service_memberships is not None else None
        next_members, crosswalk, candidates, links, meta = direct_promotion(
            members, routes, stage['families'], stage['minutes'], stage=stage['name'], depth=depth,
            guard_members=guard, eligible_parent_units=eligible_parents,
            eligible_child_units=eligible_children, demand_origin_ids=demand_ids)
        units = summarize_units(next_members, crosswalk, links, meta, reference, index, stage, anchor_representatives)
        territorial = stage.get('territorial_merge', True)
        units['territorial_membership_applied'] = territorial
        units.to_parquet(folder / ('units.parquet' if territorial else 'referral_units.parquet'), index=False)
        units[['unit_id', 'name', 'region', 'lat', 'lon', 'value', 'member_records',
               'new_territorial_merger', 'geodesic_point_diameter_km']].to_csv(
                   folder / ('centres.csv' if territorial else 'referral_centres.csv'), index=False)
        crosswalk.to_parquet(folder / 'child_parent_crosswalk.parquet', index=False)
        meta['family_coverage'].to_parquet(folder / 'family_coverage.parquet', index=False)
        # Keep each stage's complete composition, including unresolved origins.
        next_members.to_parquet(folder / ('memberships.parquet' if territorial else 'referral_memberships.parquet'), index=False)
        record = {'stage_index': index, **stage,
                  'parent_units': len(units) if territorial else int(members.unit_id.nunique()),
                  'new_merger_groups': int(units.new_territorial_merger.sum()) if territorial else 0,
                  'projected_referral_groups': 0 if territorial else int(units.new_territorial_merger.sum()),
                  'projected_referral_units': None if territorial else len(units),
                  'territorial_membership_applied': territorial,
                  'functional_overlap_guard_applied': guard is not None,
                  'checked_origin_child_pairs': int(crosswalk.member_records.sum()),
                  'retained_primary_source_records': int(crosswalk.primary_member_records.sum()),
                  'child_units_consumed_in_mergers': (int(units.loc[units.new_territorial_merger, 'direct_child_count'].sum())
                                                       if territorial else 0),
                  'projected_referral_child_units': (0 if territorial else
                      int(units.loc[units.new_territorial_merger, 'direct_child_count'].sum())),
                  'candidate_status_counts': candidates.candidate_status.value_counts().to_dict(),
                  'maximum_effective_merge_depth': ((int(units.effective_merge_depth.max()) if len(units) else 0)
                                                     if territorial else max(depth.values(), default=0)),
                  'maximum_point_diameter_km': ((float(units.geodesic_point_diameter_km.max()) if len(units) else None)
                                                 if territorial else summary['stages'][-1]['maximum_point_diameter_km']),
                  'maximum_projected_referral_point_diameter_km': (None if territorial else
                      float(units.geodesic_point_diameter_km.max()) if len(units) else None),
                  'all_origins_retained': next_members.origin_id.equals(members.origin_id),
                  'unresolved_origin_records': int(next_members.unit_id.isna().sum()),
                  'agglomeration_order_identified': False}
        (folder / 'summary.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        summary['stages'].append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if territorial:
            depth = meta['depths']; members = next_members
            # New parents inherit eligibility of their direct anchor. Retained
            # lower systems preserve their explicit initial quality flag.
            if eligible_parents is not None:
                eligible_parents = {uid for uid, anchor in meta['anchor_for_parent'].items()
                                    if anchor in eligible_parents}
            if eligible_children is not None:
                child_flags = crosswalk.child_unit_id.isin(eligible_children)
                eligible_children = set(crosswalk.assign(_eligible_child=child_flags).groupby('parent_unit_id')._eligible_child.all().loc[lambda s:s].index)
            anchor_representatives = dict(units[['unit_id', 'representative_id']].itertuples(index=False, name=None))
    summary['maximum_effective_merge_depth'] = max([r['maximum_effective_merge_depth'] for r in summary['stages']
                                                   if r['territorial_membership_applied']] or [0])
    summary['highest_referral_projection_is_not_additional_territorial_level'] = True
    summary['all_available_declared_functions_attempted'] = True
    summary['further_universal_hierarchy_identifiable'] = False
    summary['stopping_reason'] = 'no_additional_independent_function_or_observed_intercentre_flow_in_this_input'
    if source_inputs != {str(path): digest(path) for path in guarded_paths}:
        raise RuntimeError('Input changed during calculation')
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ['memberships', 'reference', 'route-directory', 'medical-route-directory', 'output']:
        parser.add_argument('--' + argument, type=Path, required=True)
    parser.add_argument('--time-scale', type=float, default=1.)
    parser.add_argument('--service-memberships', type=Path,
                        help='Original overlapping functional footprints; checked in addition to every primary member')
    parser.add_argument('--units', type=Path,
                        help='Level-zero unit/context metadata; unresolved provider contexts are retained diagnostically')
    parser.add_argument('--demand-scope', choices=['positive-whole', 'all-source-records'], default='positive-whole')
    args = parser.parse_args()
    run(args.memberships, args.reference, args.route_directory, args.medical_route_directory,
        args.output, time_scale=args.time_scale, service_membership_path=args.service_memberships, unit_path=args.units,
        demand_scope=args.demand_scope)
