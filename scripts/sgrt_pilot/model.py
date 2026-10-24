#!/usr/bin/env python3
"""Conditional attraction on dated incomplete supply; not observed trips/SGRT.

Background: DEVRIES2009 (compare decay families), ESRI_HUFF_DOC (conditional
choice). Matched half-lives, screening and numerical values are our research
choices, not coefficients transferred from those sources.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

KNOWN_POSITIVE = frozenset({'observed', 'proxy', 'present', 'presence_proxy'})


def decay(cost_minutes, half_life_minutes, family='exponential'):
    """Both kernels equal one at zero and one half at the named half-life.

    Shifted power avoids a zero-time singularity. It is not asserted to be the
    exact fitted specification in DEVRIES2009.
    """
    if not math.isfinite(half_life_minutes) or half_life_minutes <= 0:
        raise ValueError('half_life_minutes must be positive and finite')
    values = np.asarray(cost_minutes, dtype=float)
    if np.any(np.isfinite(values) & (values < 0)):
        raise ValueError('Negative travel cost')
    if family == 'exponential':
        return np.exp(-np.log(2.0) * values / half_life_minutes)
    if family == 'power':
        scale = half_life_minutes / (np.sqrt(2.0) - 1.0)
        return np.power(1.0 + values / scale, -2.0)
    raise ValueError(f'Unknown decay family: {family}')


def _require(frame, columns, name):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f'{name} missing columns: {sorted(missing)}')


def prepare_inputs(settlements, supply, costs, function, service_order, supply_transform='as_provided'):
    """Unknown supply stays unknown; missing budgeted routes are not unreachable."""
    _require(settlements, ['source_record_id', 'population'], 'settlements')
    _require(supply, ['center_id', 'function', 'service_order', 'supply_value', 'supply_status'], 'supply')
    _require(costs, ['origin_id', 'destination_id', 'cost_minutes', 'route_status'], 'costs')
    origins = settlements.copy()
    origins['source_record_id'] = origins.source_record_id.astype(str)
    origins['population'] = pd.to_numeric(origins.population, errors='coerce')
    if (origins.population.dropna() < 0).any():
        raise ValueError('Negative origin population')
    if origins.source_record_id.duplicated().any():
        raise ValueError('Duplicated origin source_record_id')
    providers = supply.loc[(supply.function.astype(str) == str(function)) & (supply.service_order.astype(str) == str(service_order))].copy()
    providers['center_id'] = providers.center_id.astype(str)
    if providers.center_id.duplicated().any():
        raise ValueError('Duplicate center/function/order; deduplicate physical objects upstream')
    numeric = pd.to_numeric(providers.supply_value, errors='coerce')
    if (numeric.dropna() < 0).any() or np.isinf(numeric).any():
        raise ValueError('Negative or infinite supply')
    known = providers.supply_status.isin(KNOWN_POSITIVE) & numeric.notna() & (numeric > 0)
    candidate_providers = providers.loc[known].copy()
    candidate_providers['supply_value'] = numeric.loc[known].astype(float)
    if supply_transform == 'binary':
        candidate_providers['supply_value'] = 1.0
    elif supply_transform == 'object_count':
        if 'object_count_proxy' not in candidate_providers:
            raise ValueError('object_count_proxy missing')
        counts = pd.to_numeric(candidate_providers.object_count_proxy, errors='coerce')
        if counts.isna().any() or (counts <= 0).any():
            raise ValueError('Object-count proxy requires positive recorded counts')
        candidate_providers['supply_value'] = counts.astype(float)
    elif supply_transform != 'as_provided':
        raise ValueError('supply_transform must be as_provided, object_count or binary')
    if 'population' not in candidate_providers:
        candidate_providers = candidate_providers.merge(origins[['source_record_id', 'population']], left_on='center_id', right_on='source_record_id', how='left', validate='one_to_one')
    candidate_providers['population'] = pd.to_numeric(candidate_providers.population, errors='coerce')
    if 'working_credit_present' in candidate_providers:
        credited = candidate_providers.working_credit_present.fillna(False).astype(bool)
        context = candidate_providers.get('population_role', pd.Series('', index=candidate_providers.index)) == 'external_context_nonadditive'
        candidate_providers.loc[~credited & ~context, 'population'] = np.nan
    origins['local_supply_status'] = 'unknown'
    origins.loc[origins.source_record_id.isin(candidate_providers.center_id), 'local_supply_status'] = 'mapped_present'
    absent = providers.loc[(providers.supply_status == 'confirmed_absent') & (numeric == 0), 'center_id']
    origins.loc[origins.source_record_id.isin(absent), 'local_supply_status'] = 'confirmed_absent'
    costs = costs.copy()
    costs['origin_id'] = costs.origin_id.astype(str)
    costs['destination_id'] = costs.destination_id.astype(str)
    costs = costs.loc[costs.origin_id.isin(origins.source_record_id) & costs.destination_id.isin(candidate_providers.center_id)].copy()
    if costs.duplicated(['origin_id', 'destination_id']).any():
        raise ValueError('Duplicate routing pair')
    costs['cost_minutes'] = pd.to_numeric(costs.cost_minutes, errors='coerce')
    if (costs.cost_minutes.dropna() < 0).any():
        raise ValueError('Negative route time')
    finite = np.isfinite(costs.cost_minutes)
    accepted_statuses = {'routed', 'reachable', 'recorded_route', 'routed_static_car_2021', 'routed_graph_static_car_2021'}
    inconsistent = finite & ~costs.route_status.isin(accepted_statuses)
    if inconsistent.any():
        raise ValueError('Finite cost has unsupported route_status: '+str(costs.loc[inconsistent, 'route_status'].unique().tolist()))
    costs = costs.loc[finite & costs.route_status.isin(accepted_statuses)].copy()
    # Zero local time approximates presence in the same NP, not measured travel
    # inside a large settlement and not adequate facility capacity.
    own = origins.loc[origins.local_supply_status == 'mapped_present', 'source_record_id']
    costs = costs.loc[costs.origin_id != costs.destination_id]
    diagonal = pd.DataFrame({'origin_id': own, 'destination_id': own, 'cost_minutes': 0.0, 'route_status': 'local_presence_zero_cost_assumption'})
    costs = pd.concat([costs, diagonal], ignore_index=True)
    alternatives = costs.merge(candidate_providers[['center_id', 'supply_value', 'population']], left_on='destination_id', right_on='center_id', how='inner', validate='many_to_one')
    return origins, candidate_providers, alternatives


def evaluate_scenario(origins, providers, alternatives, *, function, service_order,
                      model, family, half_life_minutes, kernel_floor, max_links=3, common_transport_ceiling_minutes=None):
    """Rank known alternatives; keep absolute screening and missingness separate.

    Shares exclude unknown supply and unrecorded destinations. No invented
    outside=1 term is inserted. These are not estimated trip probabilities.
    """
    if not (0 <= kernel_floor < 1):
        raise ValueError('kernel_floor must be in [0,1)')
    if model not in {'nearest', 'population', 'functional'}:
        raise ValueError(f'Unknown model: {model}')
    alt = alternatives.copy()
    if common_transport_ceiling_minutes is not None:
        alt = alt.loc[alt.cost_minutes <= common_transport_ceiling_minutes].copy()
    alt['decay_factor'] = decay(alt.cost_minutes.to_numpy(), half_life_minutes, family)
    alt['is_local'] = alt.origin_id == alt.destination_id
    route_count = alt.groupby('origin_id').size()
    alt = alt.loc[alt.decay_factor >= kernel_floor].copy()
    if model == 'nearest':
        nearest = alt.groupby('origin_id').cost_minutes.transform('min')
        alt['score'] = np.isclose(alt.cost_minutes, nearest, rtol=0, atol=1e-9).astype(float)
    elif model == 'population':
        alt['score'] = alt.population.where((alt.population > 0) & np.isfinite(alt.population)) * alt.decay_factor
    else:
        alt['score'] = alt.supply_value * alt.decay_factor
    alt = alt.loc[alt.score.notna() & (alt.score > 0)].copy()
    alt = alt.sort_values(['origin_id', 'score', 'cost_minutes', 'destination_id'], ascending=[True, False, True, True], kind='stable')
    alt['candidate_rank'] = alt.groupby('origin_id').cumcount() + 1
    alt['conditional_share'] = alt.score / alt.groupby('origin_id').score.transform('sum')
    candidate_count = alt.groupby('origin_id').size()
    maximum_score = alt.groupby('origin_id').score.transform('max')
    tie_count = alt.loc[np.isclose(alt.score, maximum_score, rtol=1e-12, atol=0)].groupby('origin_id').size()
    top = alt.loc[alt.candidate_rank == 1, ['origin_id', 'destination_id', 'cost_minutes', 'score', 'conditional_share', 'decay_factor', 'is_local']].copy()
    top = top.rename(columns={'origin_id': 'source_record_id', 'destination_id': 'primary_candidate_id', 'cost_minutes': 'primary_cost_minutes', 'conditional_share': 'primary_conditional_share', 'score': 'primary_score', 'decay_factor': 'primary_decay_factor', 'is_local': 'primary_is_local'})
    outcome = origins.merge(top, on='source_record_id', how='left', validate='one_to_one')
    outcome['recorded_reachable_known_providers'] = outcome.source_record_id.map(route_count).fillna(0).astype(int)
    outcome['screened_positive_candidates'] = outcome.source_record_id.map(candidate_count).fillna(0).astype(int)
    outcome['primary_is_local'] = outcome.primary_is_local.astype('boolean')
    outcome['top_tied_candidates'] = outcome.source_record_id.map(tie_count).fillna(0).astype(int)
    outcome['primary_candidate_is_unique'] = outcome.top_tied_candidates == 1
    outcome['outcome'] = 'external_candidate_local_supply_unknown'
    outcome.loc[outcome.local_supply_status == 'mapped_present', 'outcome'] = 'external_candidate_with_known_local_presence'
    outcome.loc[outcome.local_supply_status == 'confirmed_absent', 'outcome'] = 'external_candidate_with_confirmed_local_absence'
    outcome.loc[outcome.primary_is_local.fillna(False), 'outcome'] = 'local_candidate_preferred'
    outcome.loc[outcome.primary_candidate_id.isna(), 'outcome'] = 'no_positive_candidate_after_scenario_screen'
    outcome.loc[outcome.recorded_reachable_known_providers == 0, 'outcome'] = 'no_recorded_route_to_known_supply'
    if providers.empty:
        outcome['outcome'] = 'no_mapped_known_supply'
    outcome['origin_population_status'] = np.where(outcome.population.isna(), 'unknown', np.where(outcome.population > 0, 'positive', 'zero'))
    outcome['population_baseline_known_providers_missing_mass'] = int((providers.population.isna() | (providers.population <= 0)).sum()) if model == 'population' else 0
    outcome['established_external_link'] = False
    outcome['choice_scope'] = 'conditional_on_mapped_known_supply_and_recorded_routes'
    outcome['missing_local_supply_could_change_choice'] = outcome.local_supply_status == 'unknown'
    # Budgeted matrices leave destinations outside the route sample unresolved.
    outcome['outside_route_sample_unknown'] = True
    if kernel_floor == 0:
        screening_time_bound = float('inf')
    elif family == 'exponential':
        screening_time_bound = -math.log(kernel_floor, 2) * half_life_minutes
    else:
        screening_time_bound = half_life_minutes * (kernel_floor ** (-0.5) - 1) / (math.sqrt(2) - 1)
    metadata = {'common_transport_ceiling_minutes': common_transport_ceiling_minutes,
                'kernel_tail_censored': common_transport_ceiling_minutes is not None and screening_time_bound > common_transport_ceiling_minutes,
                'screening_time_bound_minutes': screening_time_bound, 'function': function, 'service_order': service_order, 'model': model,
                'decay_family': family, 'half_life_minutes': half_life_minutes, 'kernel_floor': kernel_floor}
    links = alt.loc[alt.candidate_rank <= max_links].copy()
    for key, value in metadata.items():
        outcome[key] = value
        links[key] = value
    return outcome, links


def scenario_stability(outcomes):
    """Agreement across selected scenarios is robustness, never ground truth."""
    columns = ['source_record_id', 'function', 'service_order', 'model']
    columns += [x for x in ['source_scenario', 'observation_year', 'supply_transform'] if x in outcomes]
    rows = []
    for keys, group in outcomes.groupby(columns, dropna=False, sort=False):
        choices = group.primary_candidate_id.fillna('__NO_SUPPORTED_CANDIDATE__')
        counts = choices.value_counts()
        rows.append(dict(zip(columns, keys)) | {
            'scenario_count': len(group), 'distinct_primary_states': len(counts),
            'modal_primary_state': counts.index[0], 'modal_state_fraction': float(counts.iloc[0] / len(group)),
            'all_scenarios_same_state': len(counts) == 1,
            'all_scenarios_have_candidate': bool(group.primary_candidate_id.notna().all()),
            'established_external_link': False})
    return pd.DataFrame(rows)


def _read(path):
    if path.suffix == '.parquet':
        return pd.read_parquet(path)
    return pd.read_csv(path, dtype={'source_record_id': str, 'center_id': str, 'origin_id': str, 'destination_id': str})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['settlements', 'supply', 'costs', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--max-cost-minutes', type=float, default=180., help='Common computational routing ceiling including connectors; not empirical service radius')
    parser.add_argument('--context-supply', type=Path, help='Explicit nonadditive external providers, e.g. federal cities')
    parser.add_argument('--half-lives', default='15,30,60', help='Exploratory minutes, not fitted Russian coefficients')
    parser.add_argument('--floors', default='0.01,0.05,0.1', help='Exploratory screening; 0 retains all recorded routes')
    parser.add_argument('--families', default='exponential,power')
    parser.add_argument('--models', default='nearest,population,functional')
    parser.add_argument('--supply-transform', choices=['as_provided', 'object_count', 'binary'], default='as_provided')
    parser.add_argument('--source-scenarios', default='', help='Comma-separated source assignment scenarios; empty=all separately')
    parser.add_argument('--functions', default='')
    parser.add_argument('--orders', default='')
    parser.add_argument('--regions', default='', help='Origin regions only; outside providers retained')
    parser.add_argument('--collapse-orders', action='store_true', help='Diagnostic broad-function layer, NOT a clinical/educational service order')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    settlements, supply = map(_read, [args.settlements, args.supply])
    if args.context_supply:
        context_supply = _read(args.context_supply)
        if 'population_role' not in context_supply or not context_supply.population_role.eq('external_context_nonadditive').all():
            raise ValueError('Context providers require explicit external_context_nonadditive role')
        supply = pd.concat([supply, context_supply], ignore_index=True)
    if args.regions:
        settlements = settlements.loc[settlements.region.isin(args.regions.split(','))].copy()
    compact_columns = [x for x in ['source_record_id', 'root', 'name', 'region', 'population', 'lon', 'lat', 'census_year', 'working_credit_present', 'accepted_point_present'] if x in settlements]
    settlements = settlements[compact_columns]
    all_outcomes, reference_links, input_summary = [], [], []
    if args.source_scenarios:
        supply = supply.loc[supply.scenario.isin(args.source_scenarios.split(','))]
    if args.functions:
        supply = supply.loc[supply.function.isin(args.functions.split(','))]
    if args.orders:
        supply = supply.loc[supply.service_order.isin(args.orders.split(','))]
    if 'scenario' not in supply:
        supply['scenario'] = 'unspecified_source_scenario'
    if 'observation_year' not in supply:
        supply['observation_year'] = pd.NA
    if args.collapse_orders:
        keys = ['scenario', 'observation_year', 'function', 'center_id']
        # Sum only recorded object-count proxies, never assumed capacities.
        aggregations = {col: ('sum' if col == 'object_count_proxy' else 'first') for col in supply.columns if col not in keys}
        supply = supply.groupby(keys, dropna=False, as_index=False).agg(aggregations)
        supply['service_order'] = 'broad_recorded_function_not_service_order'
        supply['supply_value'] = 1.0
        if args.supply_transform == 'as_provided':
            raise ValueError('For collapsed orders choose --supply-transform binary or object_count explicitly')
    families = args.families.split(',')
    half_lives = list(map(float, args.half_lives.split(',')))
    floors = list(map(float, args.floors.split(',')))
    if args.costs.suffix == '.parquet':
        costs = pd.read_parquet(args.costs, columns=['origin_id', 'destination_id', 'cost_minutes', 'route_status'],
            filters=[('origin_id', 'in', settlements.source_record_id.astype(str).tolist()),
                     ('destination_id', 'in', supply.center_id.astype(str).unique().tolist()),
                     ('cost_minutes', '>=', 0), ('cost_minutes', '<=', args.max_cost_minutes)])
    else:
        costs = _read(args.costs)
    for (source_scenario, observation_year, function, order), subset in supply.groupby(['scenario', 'observation_year', 'function', 'service_order'], dropna=False):
        origins, providers, alternatives = prepare_inputs(settlements, subset, costs, str(function), str(order), args.supply_transform)
        input_summary.append({'source_scenario': str(source_scenario), 'observation_year': None if pd.isna(observation_year) else int(observation_year), 'function': str(function), 'service_order': str(order), 'origins': len(origins),
                              'mapped_positive_providers': len(providers),
                              'recorded_candidate_routes_including_local_assumption': len(alternatives),
                              'origins_local_supply_unknown': int((origins.local_supply_status == 'unknown').sum())})
        source_year_metadata = {}
        for field in ['document_catalogue_year', 'planning_target_year']:
            if field in subset:
                distinct = subset[field].dropna().unique()
                if len(distinct) == 1:
                    source_year_metadata[field] = int(distinct[0])
        input_summary[-1].update(source_year_metadata)
        for model in args.models.split(','):
            for family in families:
                for half_life in half_lives:
                    for floor in floors:
                        result, links = evaluate_scenario(origins, providers, alternatives, function=str(function), service_order=str(order), model=model,
                            family=family, half_life_minutes=half_life, kernel_floor=floor, common_transport_ceiling_minutes=args.max_cost_minutes)
                        for frame in [result, links]:
                            frame['source_scenario'] = str(source_scenario)
                            frame['observation_year'] = observation_year
                            frame['supply_transform'] = args.supply_transform
                            for field, value in source_year_metadata.items():
                                frame[field] = value
                        all_outcomes.append(result)
                        # A named reference, never selected as optimum by results.
                        if family == families[0] and half_life == half_lives[len(half_lives)//2] and floor == floors[len(floors)//2]:
                            reference_links.append(links)
    if not all_outcomes:
        raise ValueError('No supply function/order groups')
    outcomes = pd.concat(all_outcomes, ignore_index=True)
    stability = scenario_stability(outcomes)
    links = pd.concat(reference_links, ignore_index=True) if reference_links else pd.DataFrame()
    outcomes.to_parquet(args.output/'scenario_outcomes.parquet', index=False)
    stability.to_parquet(args.output/'scenario_stability.parquet', index=False)
    links.to_parquet(args.output/'reference_links.parquet', index=False)
    groups = ['source_scenario', 'observation_year', 'supply_transform', 'function', 'service_order', 'model', 'decay_family', 'half_life_minutes', 'kernel_floor', 'outcome']
    outcomes.groupby(groups, dropna=False).size().rename('settlements').reset_index().to_csv(args.output/'scenario_counts.csv', index=False)
    summary = {'status': 'uncalibrated_conditional_supply_proxy_scenarios_not_observed_sgrt', 'inputs': input_summary,
               'common_transport_ceiling_minutes': args.max_cost_minutes, 'supply_transform': args.supply_transform, 'outcome_rows': len(outcomes), 'reference_link_rows': len(links),
               'parameters': {'half_lives_minutes': half_lives, 'kernel_floors': floors, 'families': families},
               'stability': stability.groupby(['source_scenario', 'observation_year', 'function', 'service_order', 'model'], dropna=False).agg(settlements=('source_record_id', 'size'),
                   identical_choice_all_scenarios=('all_scenarios_same_state', 'sum'), candidate_all_scenarios=('all_scenarios_have_candidate', 'sum')).reset_index().pipe(lambda frame: json.loads(frame.to_json(orient='records'))),
               'limits': ['Unknown local supply is not zero', 'Mapped-object counts are not capacities', 'Missing route records do not prove unreachable',
                          'Zero local cost approximates same-NP presence', 'Shares are conditional weights, not trip probabilities',
                          'No observed links or capacity constraints fitted', 'Numerical parameters are research choices, not Russian estimates']}
    (args.output/'model_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
