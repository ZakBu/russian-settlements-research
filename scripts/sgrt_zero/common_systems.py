#!/usr/bin/env python3
"""Common low-order service cores and conditional direct-dependency basins.

Our diagnostic construction, not observed travel or a completed SGRT typology.
All terminal SCCs are retained; missing routes are never treated as no demand.
Known branches to different terminal cores stay unassigned. Graph-chain costs
are proxies across contracted SCCs, not measured vehicle journeys: physical
provider sites and settlement points need not share an internal transfer.
"""
from __future__ import annotations
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from lower_profile_quality import part_inventory, sha256

CORE = ('medical_basic', 'school', 'grocery')

def stable_id(values):
    return 'l0:' + hashlib.sha256('|'.join(sorted(values)).encode()).hexdigest()[:24]

def geodesic_diameter(lat, lon):
    """Exact WGS84 extreme-pair diameter; no inferred area or road distance."""
    from pyproj import Geod
    g = Geod(ellps='WGS84')
    points = np.column_stack((lat, lon)).astype(float)
    points = points[np.isfinite(points).all(axis=1)]
    points = np.unique(points, axis=0)
    maximum = 0.
    for i in range(len(points) - 1):
        n = len(points) - i - 1
        _, _, d = g.inv(np.full(n, points[i, 1]), np.full(n, points[i, 0]),
                        points[i + 1:, 1], points[i + 1:, 0])
        maximum = max(maximum, float(np.max(d)))
    return maximum / 1000

def cooperation_diagnostics(edges, reference, chain_review_minutes=30.):
    if not np.isfinite(chain_review_minutes) or chain_review_minutes <= 0:
        raise ValueError('A positive finite diagnostic chain-review threshold is required')
    edges = edges[edges.service_family.isin(CORE)].copy()
    if edges.empty or edges.duplicated(['origin_id', 'service_family']).any():
        raise ValueError('One complete outcome per origin and basic function is required')
    if not edges.groupby('origin_id').service_family.nunique().eq(3).all():
        raise ValueError('Rejected and unknown outcomes must remain in the input')
    if edges.l0_admitted.isna().any() or not edges.l0_admitted.isin([True, False]).all():
        raise ValueError('Admission must be explicit boolean data')
    if edges[edges.l0_admitted].cost_minutes.isna().any() or edges[edges.l0_admitted].cost_minutes.lt(0).any():
        raise ValueError('Admitted link costs must be known and nonnegative')
    ref, _ = part_inventory(reference)
    ref = ref.dropna(subset=['source_record_id']).set_index('source_record_id')
    if not ref.index.is_unique or not set(edges.origin_id) <= set(ref.index):
        raise ValueError('Unique reference identities are required for every origin')
    if not set(edges.provider_settlement_id.dropna()) <= set(ref.index):
        raise ValueError('Unknown declared provider identity')
    # All routed origins survive. Source parts/nonadditive cities are flagged,
    # not silently merged with a guessed parent settlement or removed.
    ids = pd.Index(sorted(edges.origin_id.unique()), name='origin_id')
    metadata = ref.reindex(ids)
    number = pd.Series(np.arange(len(ids)), index=ids)
    selected = edges[edges.l0_admitted & edges.provider_settlement_id.isin(ids)].copy()
    a = selected.origin_id.map(number).to_numpy(dtype='int64')
    b = selected.provider_settlement_id.map(number).to_numpy(dtype='int64')
    ncomp, component = connected_components(
        csr_matrix((np.ones(len(a), dtype='int8'), (a, b)), shape=(len(ids), len(ids))),
        directed=True, connection='strong')
    sizes = np.bincount(component, minlength=ncomp)
    known_functions = selected.groupby('origin_id').service_family.nunique().reindex(ids, fill_value=0).to_numpy()
    admitted_functions = edges[edges.l0_admitted].groupby('origin_id').size().reindex(ids, fill_value=0).to_numpy()
    local = selected[selected.origin_id.eq(selected.provider_settlement_id)]
    local_functions = local.groupby('origin_id').service_family.nunique().reindex(ids, fill_value=0).to_numpy()
    direct_max = selected.groupby('origin_id').cost_minutes.max().reindex(ids).to_numpy()
    component_complete = np.bincount(component, weights=known_functions == 3, minlength=ncomp) == sizes
    component_local = np.bincount(component, weights=local_functions > 0, minlength=ncomp)
    crossed = component[a] != component[b]
    condensed = pd.DataFrame({'a':component[a[crossed]], 'b':component[b[crossed]],
                              'cost':selected.cost_minutes.to_numpy()[crossed]})
    condensed = condensed.groupby(['a', 'b'], as_index=False).cost.max()
    outgoing = [[] for _ in range(ncomp)]
    parents = [[] for _ in range(ncomp)]
    for u, v, cost in condensed.itertuples(index=False, name=None):
        outgoing[u].append((v, cost)); parents[v].append(u)
    terminal = np.array([not values for values in outgoing])
    remaining = np.array([len(values) for values in outgoing])
    queue = deque(np.flatnonzero(terminal).tolist())
    reachable = [set() for _ in range(ncomp)]
    incomplete = ~component_complete.copy()
    chain_proxy = np.zeros(ncomp, dtype=float)
    maximum_hops = np.zeros(ncomp, dtype='int64')
    for j in queue: reachable[j] = {j}
    visited = 0
    while queue:
        child = queue.popleft(); visited += 1
        for parent in parents[child]:
            reachable[parent].update(reachable[child])
            incomplete[parent] |= incomplete[child]
            # A diagnostic sum along component-to-component service edges.
            # Intra-component transfer times are not available and not invented.
            cost = next(cost for dest, cost in outgoing[parent] if dest == child)
            chain_proxy[parent] = max(chain_proxy[parent], cost + chain_proxy[child])
            maximum_hops[parent] = max(maximum_hops[parent], 1 + maximum_hops[child])
            remaining[parent] -= 1
            if remaining[parent] == 0: queue.append(parent)
    if visited != ncomp: raise AssertionError('SCC condensation must be acyclic')
    groups = [[] for _ in range(ncomp)]
    for i, j in enumerate(component): groups[j].append(i)
    core_ids = {j:stable_id(ids[groups[j]].tolist()) for j in np.flatnonzero(terminal)}
    sole = np.array([next(iter(v)) if len(v) == 1 else -1 for v in reachable], dtype='int64')
    out = metadata[['name','region','district','lat','lon','population_2021','population_role',
                    'budget_population_credit','part_status']].copy()
    out['component_id'] = component
    out['core_node_count'] = sizes[component]
    out['is_core'] = terminal[component]
    out['local_known_function_count'] = local_functions
    out['admitted_function_count'] = admitted_functions
    out['identified_admitted_function_count'] = known_functions
    out['reachable_terminal_count'] = [len(reachable[j]) for j in component]
    out['unit_id'] = pd.Series([core_ids.get(sole[j], pd.NA) for j in component], index=ids, dtype='string')
    out['reachable_unit_ids_json'] = [json.dumps(sorted(core_ids[k] for k in reachable[j])) for j in component]
    out['any_unresolved_downstream_function'] = incomplete[component]
    out['graph_chain_proxy_minutes'] = chain_proxy[component]
    out['component_hops_to_terminals_maximum'] = maximum_hops[component]
    out['maximum_selected_direct_service_minutes'] = direct_max
    out['source_grain_requires_review'] = out.part_status.ne('unmarked_whole_place_record')
    out['positive_whole_origin'] = (out.population_2021.gt(0) & ~out.source_grain_requires_review
        & out.population_role.isin(['ordinary_settlement_record','external_context_nonadditive']))
    out['positive_ordinary_whole_origin'] = out.positive_whole_origin & out.population_role.eq('ordinary_settlement_record')
    out['chain_proxy_requires_review'] = out.graph_chain_proxy_minutes.gt(chain_review_minutes)
    out['membership_status'] = 'split_known_terminal_directions'
    unique = out.unit_id.notna()
    out.loc[unique & out.any_unresolved_downstream_function, 'membership_status'] = 'one_known_core_incomplete_functions'
    out.loc[unique & ~out.any_unresolved_downstream_function, 'membership_status'] = 'closed_three_function_basin'
    out.loc[out.is_core & out.any_unresolved_downstream_function, 'membership_status'] = 'terminal_incomplete_functions'
    out.loc[out.is_core & ~out.any_unresolved_downstream_function, 'membership_status'] = 'terminal_complete_three_functions'
    out['observed_membership_verified'] = False
    out['graph_chain_proxy_is_actual_vehicle_time'] = False
    out['population_additive_credit'] = out.budget_population_credit.fillna(False)
    cores = []
    for j in np.flatnonzero(terminal):
        positions = groups[j]; rows = metadata.iloc[positions]
        # Stable label only; no population ranking or invented dominant centre.
        names = rows.name.fillna('').astype(str).tolist()
        core_has_local = bool(component_local[j] > 0)
        core_kind = ('monocentric_complete' if sizes[j] == 1 else 'complementary_complete') if component_complete[j] else (
            'recorded_partial_service_core' if core_has_local or sizes[j] > 1 else 'unestablished_service_core')
        cores.append({'unit_id':core_ids[j], 'name':' / '.join(sorted(set(names))),
            'core_node_ids_json':json.dumps(ids[positions].tolist()), 'core_size':int(sizes[j]),
            'core_kind':core_kind, 'complete_three_functions':bool(component_complete[j]),
            'known_service_core':bool(core_has_local or sizes[j] > 1),
            'core_local_service_node_count':int(component_local[j]),
            'lat':float(rows.lat.mean()), 'lon':float(rows.lon.mean()),
            'coordinate_semantics':'mean_of_core_census_points_not_inferred_dominant_centre',
            'core_regions_json':json.dumps(sorted(rows.region.dropna().unique().tolist()), ensure_ascii=False),
            'core_source_grain_requires_review':bool(out.iloc[positions].source_grain_requires_review.any()),
            'core_positive_whole_nodes':int(out.iloc[positions].positive_whole_origin.sum()),
            'core_geodesic_diameter_km':geodesic_diameter(rows.lat, rows.lon)})
    cores = pd.DataFrame(cores)
    units = []
    for unit, rows in out[unique].groupby('unit_id', sort=True):
        demand = rows[rows.positive_whole_origin]
        external = demand[~demand.is_core]
        credited = rows[rows.population_additive_credit]
        units.append({'unit_id':unit, 'member_records':len(rows), 'positive_whole_member_records':len(demand),
            'external_positive_whole_records':len(external),
            'all_members_have_complete_known_dependency':bool(~rows.any_unresolved_downstream_function.any()),
            'graph_chain_proxy_minutes_maximum':float(rows.graph_chain_proxy_minutes.max()),
            'component_hops_maximum':int(rows.component_hops_to_terminals_maximum.max()),
            'any_chain_proxy_requires_review':bool(rows.chain_proxy_requires_review.any()),
            'any_source_grain_requires_review':bool(rows.source_grain_requires_review.any()),
            'member_geodesic_diameter_km':geodesic_diameter(rows.lat, rows.lon),
            'credited_population_2021_partial_sum':float(credited.population_2021.sum(min_count=1)),
            'population_total_complete':bool(rows.population_additive_credit.all() & rows.population_2021.notna().all())})
    units = pd.DataFrame(units).merge(cores, on='unit_id', validate='one_to_one')
    units['known_service_terminal_basin'] = (units.known_service_core & units.positive_whole_member_records.gt(1)
        & units.external_positive_whole_records.gt(0) & ~units.core_source_grain_requires_review)
    units['full_function_closure_basin'] = units.known_service_terminal_basin & units.complete_three_functions & units.all_members_have_complete_known_dependency
    units['value'] = 5
    units.loc[units.known_service_core, 'value'] = 3
    units.loc[units.complete_three_functions & units.core_size.eq(1), 'value'] = 1
    units.loc[units.complete_three_functions & units.core_size.gt(1), 'value'] = 2
    units.loc[units.known_service_core & units.external_positive_whole_records.eq(0), 'value'] = 4
    summary = {'schema':'sgrt.service_cooperation_closure_diagnostics.v1', 'routed_origin_records':len(out),
        'strong_components':int(ncomp), 'terminal_components_retained':len(cores),
        'complete_terminal_cores':int(cores.complete_three_functions.sum()),
        'known_service_terminal_cores':int(cores.known_service_core.sum()),
        'unestablished_terminal_cores':int((~cores.known_service_core).sum()),
        'nontrivial_complete_terminal_cores':int((cores.complete_three_functions & cores.core_size.gt(1)).sum()),
        'known_service_terminal_basins_with_external_members':int(units.known_service_terminal_basin.sum()),
        'complete_dependency_terminal_basins':int(units.full_function_closure_basin.sum()),
        'membership_status_counts':out.membership_status.value_counts().to_dict(),
        'positive_whole_membership_status_counts':out[out.positive_whole_origin].membership_status.value_counts().to_dict(),
        'positive_whole_origin_records':int(out.positive_whole_origin.sum()),
        'split_positive_whole_records':int((out.positive_whole_origin & ~unique).sum()),
        'graph_chain_review_threshold_minutes':float(chain_review_minutes),
        'graph_chain_threshold_is_empirically_calibrated':False,
        'graph_chain_proxy_is_actual_vehicle_time':False,
        'observed_membership_verified':False,
        'all_terminal_cores_are_established_centres':False,
        'unknown_service_is_not_absent':True,
        'demand_population_used_as_attraction_weight':False}
    return {'memberships':out.reset_index(), 'cores':cores, 'units':units}, summary

def anchored_systems(edges, reference, centres, service_memberships):
    """Preserve all registered centres and their original direct surroundings.

    A primary affiliation is a supplementary, partial, operational allocation.
    It never consumes an existing centre or discards its functional surroundings.
    Equal votes and unknown provider identities do not elect an invented winner.
    """
    ref, _ = part_inventory(reference)
    ref = ref.dropna(subset=['source_record_id']).set_index('source_record_id')
    centres = centres.copy()
    if 'star_id' not in centres:
        if 'star_id' not in service_memberships:
            raise ValueError('Stable original star identities are required in centres or service memberships')
        mapping = service_memberships[['centre_settlement_id','star_id']].drop_duplicates()
        if not mapping.centre_settlement_id.is_unique:
            raise ValueError('Original centre has conflicting star identities')
        centres['star_id'] = centres.centre_settlement_id.map(mapping.set_index('centre_settlement_id').star_id)
    if centres.star_id.isna().any():
        raise ValueError('No stable original star identity for a registered centre')
    if not centres.centre_settlement_id.is_unique or not centres.star_id.is_unique:
        raise ValueError('Every registered centre must have one stable identity')
    if not set(centres.centre_settlement_id) <= set(ref.index):
        raise ValueError('Registered centre identity absent from reference')
    if service_memberships.duplicated(['centre_settlement_id', 'origin_id']).any():
        raise ValueError('Original direct surroundings contain repeated centre/member pairs')
    if set(service_memberships.centre_settlement_id) != set(centres.centre_settlement_id):
        raise ValueError('Every centre and its original surroundings must be preserved')
    core = edges[edges.service_family.isin(CORE)].copy()
    if core.empty or core.duplicated(['origin_id', 'service_family']).any():
        raise ValueError('One outcome per origin and basic function is required')
    if not core.groupby('origin_id').service_family.nunique().eq(3).all():
        raise ValueError('All three outcomes, including unknowns, must remain')
    if core.l0_admitted.isna().any() or not core.l0_admitted.isin([True,False]).all():
        raise ValueError('Admission must be explicit boolean data')
    ids = pd.Index(sorted(core.origin_id.unique()), name='origin_id')
    if not set(ids) <= set(ref.index) or not set(centres.centre_settlement_id) <= set(ids):
        raise ValueError('Every origin and centre must occur in the complete scenario')
    if not set(core.provider_settlement_id.dropna()) <= set(ref.index):
        raise ValueError('Unknown declared provider identity')
    chosen = core[core.l0_admitted & core.provider_settlement_id.notna()].copy()
    votes = chosen.groupby(['origin_id','provider_settlement_id']).service_family.nunique().rename('votes').reset_index()
    votes['maximum'] = votes.groupby('origin_id').votes.transform('max')
    leaders = votes[votes.votes.eq(votes.maximum)]
    leader_count = leaders.groupby('origin_id').size()
    unique_leader = leaders[leaders.origin_id.map(leader_count).eq(1)].set_index('origin_id')
    membership = ref.reindex(ids)[['name','region','district','lat','lon','population_2021',
        'population_role','budget_population_credit','part_status']].copy()
    membership['is_registered_centre'] = membership.index.isin(centres.centre_settlement_id)
    membership['known_function_count'] = chosen.groupby('origin_id').service_family.nunique().reindex(ids,fill_value=0)
    membership['admitted_function_count'] = core[core.l0_admitted].groupby('origin_id').size().reindex(ids,fill_value=0)
    membership['leading_target_id'] = unique_leader.provider_settlement_id.reindex(ids)
    membership['maximum_support_count'] = leaders.groupby('origin_id').votes.max().reindex(ids,fill_value=0)
    membership['equally_supported_targets'] = leader_count.reindex(ids,fill_value=0)
    membership['known_provider_ids_json'] = chosen.groupby('origin_id').provider_settlement_id.agg(
        lambda x:json.dumps(sorted(set(x)))).reindex(ids,fill_value='[]')
    unit_lookup = centres.set_index('centre_settlement_id').star_id
    membership['unit_id'] = membership.leading_target_id.map(unit_lookup).astype('string')
    membership['primary_centre_id'] = membership.leading_target_id.where(membership.unit_id.notna()).astype('string')
    membership['membership_status'] = 'no_known_direction_not_no_dependency'
    known = membership.known_function_count.gt(0)
    tied = membership.equally_supported_targets.gt(1)
    membership.loc[known & tied,'membership_status'] = 'distributed_equal_known_support'
    single = known & ~tied
    self_leader = membership.leading_target_id.eq(membership.index.to_series())
    outside = single & ~self_leader & membership.unit_id.isna()
    membership.loc[outside,'membership_status'] = 'leading_provider_not_registered_centre_requires_review'
    membership.loc[single & self_leader,'membership_status'] = 'local_leading_profile_without_registered_external_role'
    assigned = membership.unit_id.notna()
    membership.loc[assigned & membership.maximum_support_count.eq(1),'membership_status'] = 'one_known_function_primary_provisional'
    membership.loc[assigned & membership.maximum_support_count.eq(2),'membership_status'] = 'two_function_primary_partial'
    membership.loc[assigned & membership.maximum_support_count.eq(2) & membership.known_function_count.eq(3),
        'membership_status'] = 'two_of_three_function_primary'
    membership.loc[assigned & membership.maximum_support_count.eq(3),'membership_status'] = 'three_function_primary'
    anchor = membership.is_registered_centre
    # The anchor invariant is independent of its outbound medical/school/shop
    # needs. A village with a school remains a centre even if its shop is elsewhere.
    membership.loc[anchor,'unit_id'] = membership.index.to_series().loc[anchor].map(unit_lookup)
    membership.loc[anchor,'primary_centre_id'] = membership.index[anchor]
    membership.loc[anchor,'membership_status'] = 'registered_centre_preserved_as_self_anchor'
    local_self_not_anchor = single & self_leader & ~anchor
    local_selected = chosen[chosen.origin_id.eq(chosen.provider_settlement_id)]
    local_profile_ids = set(local_selected.origin_id) - set(centres.centre_settlement_id)
    context_ids = local_profile_ids | set(membership.loc[outside,'leading_target_id'].dropna())
    context_lookup = {i:'local:'+hashlib.sha256(str(i).encode()).hexdigest()[:24] for i in sorted(context_ids)}
    membership.loc[local_self_not_anchor,'unit_id'] = membership.index.to_series().loc[local_self_not_anchor].map(context_lookup)
    membership.loc[local_self_not_anchor,'primary_centre_id'] = membership.index[local_self_not_anchor]
    membership.loc[local_self_not_anchor,'membership_status'] = 'local_single_site_profile_not_external_centre'
    membership.loc[outside,'unit_id'] = membership.loc[outside,'leading_target_id'].map(context_lookup)
    membership.loc[outside,'primary_centre_id'] = membership.loc[outside,'leading_target_id']
    membership.loc[outside,'membership_status'] = 'provider_context_primary_requires_review'
    membership['is_core'] = anchor | local_self_not_anchor
    membership['primary_rule_is_our_operational_proposal'] = True
    membership['observed_membership_verified'] = False
    membership['source_grain_requires_review'] = membership.part_status.ne('unmarked_whole_place_record')
    membership['positive_whole_origin'] = (membership.population_2021.gt(0) & ~membership.source_grain_requires_review
        & membership.population_role.isin(['ordinary_settlement_record','external_context_nonadditive']))
    vote_lookup = votes.set_index(['origin_id','provider_settlement_id']).votes
    actual_keys = pd.MultiIndex.from_arrays([membership.index,membership.primary_centre_id])
    actual_support = vote_lookup.reindex(actual_keys).fillna(0).to_numpy(dtype='int64')
    membership['primary_centre_function_support_count'] = pd.Series(actual_support,index=ids,dtype='Int64').where(membership.unit_id.notna())
    membership['primary_support_fraction_of_all_three_functions'] = membership.primary_centre_function_support_count / 3.
    membership['leading_target_support_fraction_of_all_three_functions'] = (membership.maximum_support_count / 3.).where(known)
    membership['all_three_function_identities_known'] = membership.known_function_count.eq(3)
    original_centre_count = len(centres)
    centres['is_registered_external_serving_centre'] = True
    centres['unit_role'] = 'external_serving_anchor'
    centres['core_origin_id'] = centres.centre_settlement_id
    centres['core_node_ids_json'] = centres.centre_settlement_id.map(lambda v:json.dumps([v]))
    local_count = chosen[chosen.origin_id.eq(chosen.provider_settlement_id)].groupby('origin_id').service_family.nunique()
    provider_count = chosen.groupby('provider_settlement_id').service_family.nunique()
    additional=[]
    for i,uid in context_lookup.items():
        row=ref.loc[i]
        is_local = i in local_profile_ids
        own = int(local_count.get(i,0))
        extra = {key:pd.NA for key in centres.columns}
        extra.update(centre_settlement_id=i,star_id=uid,centre_name=row['name'],centre_region=row['region'],
            own_known_basic_function_count=own,lat=row['lat'],lon=row['lon'],
            is_registered_external_serving_centre=False,
            unit_role='local_singleton_known_profile' if is_local else 'provider_context_requires_review',
            core_origin_id=i,core_node_ids_json=json.dumps([i]),
            provider_selected_function_presence_count=int(provider_count.get(i,0)),
            type_code='local_profile_known_'+str(own) if is_local else 'provider_context_requires_review',
            type_label='Локальный профиль: известно функций '+str(own) if is_local else 'Контекст поставщика: требуется проверка',
            population_budget_partial=not bool(row['budget_population_credit']),
            centre_population_2021_source_value=row['population_2021'])
        additional.append(extra)
    if additional:centres=pd.concat([centres,pd.DataFrame(additional)],ignore_index=True)
    centres['unit_id'] = centres.star_id
    centres['name'] = centres.centre_name
    primary = membership[membership.unit_id.notna()]
    centres['primary_member_records'] = centres.unit_id.map(primary.groupby('unit_id').size()).fillna(0).astype('int64')
    externals = primary[primary.origin_id.ne(primary.primary_centre_id) & primary.positive_whole_origin] if 'origin_id' in primary else primary[primary.index.to_series().ne(primary.primary_centre_id) & primary.positive_whole_origin]
    centres['primary_external_positive_whole_records'] = centres.unit_id.map(externals.groupby('unit_id').size()).fillna(0).astype('int64')
    strong = externals[externals.membership_status.isin(['two_of_three_function_primary','three_function_primary'])]
    centres['primary_supported_by_two_or_three_known_functions'] = centres.unit_id.map(strong.groupby('unit_id').size()).fillna(0).astype('int64')
    partial = externals[externals.membership_status.isin(['one_known_function_primary_provisional','two_function_primary_partial'])]
    centres['primary_provisional_external_records'] = centres.unit_id.map(partial.groupby('unit_id').size()).fillna(0).astype('int64')
    centres['centre_never_absorbed_by_other_zero_centre'] = centres.is_registered_external_serving_centre
    centres['original_direct_surroundings_preserved'] = centres.is_registered_external_serving_centre
    centres['core_membership_consistent'] = centres.core_origin_id.map(membership.unit_id).eq(centres.unit_id).fillna(False)
    core_metadata = ref.reindex(centres.core_origin_id)
    centres['core_population_role'] = core_metadata.population_role.to_numpy()
    centres['core_source_grain_requires_review'] = core_metadata.part_status.ne('unmarked_whole_place_record').to_numpy()
    centres['core_positive_population_known'] = core_metadata.population_2021.gt(0).to_numpy()
    centres['core_analysis_origin'] = core_metadata.analysis_origin.fillna(False).to_numpy()
    centres['eligible_as_higher_parent'] = (centres.core_positive_population_known & ~centres.core_source_grain_requires_review
        & centres.core_analysis_origin & centres.own_known_basic_function_count.gt(0)
        & centres.core_population_role.isin(['ordinary_settlement_record','external_context_nonadditive']))
    centres['eligible_as_higher_child'] = centres.core_membership_consistent & centres.eligible_as_higher_parent
    centres['context_unit_is_not_additional_external_service_centre'] = ~centres.is_registered_external_serving_centre
    centres['context_unit_is_not_extra_population_budget'] = ~centres.is_registered_external_serving_centre
    # Exact original functional types remain; contexts have separate map codes.
    centres['value'] = centres.own_known_basic_function_count.map({3:1,2:2,1:3}).fillna(5).astype('int64')
    centres.loc[~centres.is_registered_external_serving_centre,'value'] = 4
    centres.loc[centres.unit_role.eq('provider_context_requires_review'),'value'] = 5
    centres['primary_radius_is_not_a_new_service_area'] = True
    membership = membership.reset_index()
    service = service_memberships.copy()
    service['unit_id'] = service.centre_settlement_id.map(unit_lookup)
    summary = {'schema':'sgrt.anchored_zero_systems.v1', 'registered_centres_preserved':original_centre_count,
        'original_service_membership_pairs_preserved':len(service),
        'primary_membership_records':len(membership),
        'primary_status_counts':membership.membership_status.value_counts().to_dict(),
        'positive_whole_status_counts':membership[membership.positive_whole_origin].membership_status.value_counts().to_dict(),
        'centres_with_primary_positive_whole_external_members':int((centres.is_registered_external_serving_centre & centres.primary_external_positive_whole_records.gt(0)).sum()),
        'centres_with_two_or_three_function_primary_external_members':int((centres.is_registered_external_serving_centre & centres.primary_supported_by_two_or_three_known_functions.gt(0)).sum()),
        'centres_by_own_known_function_count':{str(k):int(v) for k,v in centres[centres.is_registered_external_serving_centre].own_known_basic_function_count.value_counts().items()},
        'additional_context_units':len(additional),'unit_role_counts':centres.unit_role.value_counts().to_dict(),
        'context_parent_candidates':int((~centres.is_registered_external_serving_centre & centres.eligible_as_higher_parent).sum()),
        'existing_centres_absorbed':0, 'full_country_exclusive_sgrt_partition_claimed':False,
        'observed_membership_verified':False,'unknown_function_is_not_absent':True,
        'primary_rule_is_our_operational_proposal':True,
        'primary_support_counts_distinct_function_families_not_object_numbers':True}
    assert membership.loc[membership.is_registered_centre,'primary_centre_id'].eq(
        membership.loc[membership.is_registered_centre,'origin_id']).all()
    return {'units':centres,'memberships':membership,'service_memberships':service}, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--edges',type=Path,required=True);p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--centres',type=Path,required=True);p.add_argument('--memberships',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--chain-review-minutes',type=float,default=30.)
    p.add_argument('--regions',nargs='+',help='Pilot roots and their complete downstream provider closure')
    p.add_argument('--skip-cooperation',action='store_true')
    args=p.parse_args()
    cols=['origin_id','provider_settlement_id','service_family','l0_admitted','cost_minutes']
    edges=pd.read_parquet(args.edges,columns=cols);reference=pd.read_parquet(args.reference)
    centres=pd.read_csv(args.centres) if args.centres.suffix=='.csv' else pd.read_parquet(args.centres)
    service=pd.read_parquet(args.memberships)
    if args.regions:
        ids=set(reference.loc[reference.region.isin(args.regions),'source_record_id'].dropna())
        while True:
            extra=set(edges.loc[edges.origin_id.isin(ids),'provider_settlement_id'].dropna())
            added=extra-ids
            if not added:break
            ids.update(added)
        edges=edges[edges.origin_id.isin(ids)]
        centres=centres[centres.centre_settlement_id.isin(ids)]
        service=service[service.centre_settlement_id.isin(centres.centre_settlement_id)]
    tables,summary=anchored_systems(edges,reference,centres,service)
    if not args.skip_cooperation:
        coops,cooperation_summary=cooperation_diagnostics(edges,reference,args.chain_review_minutes)
        tables.update({'cooperation_'+key:frame for key,frame in coops.items()})
        summary['cooperation_diagnostics']=cooperation_summary
    args.output.mkdir(parents=True,exist_ok=True)
    for name,frame in tables.items():frame.to_parquet(args.output/(name+'.parquet'),index=False)
    tables['units'][tables['units'].is_registered_external_serving_centre].to_csv(args.output/'common_local_centres.csv',index=False)
    tables['units'].to_csv(args.output/'zero_units.csv',index=False)
    summary['inputs']={name:sha256(path) for name,path in [('edges',args.edges),('reference',args.reference),
        ('centres',args.centres),('memberships',args.memberships)]}
    summary['code_sha256']=sha256(Path(__file__))
    summary['pilot_regions']=args.regions
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
