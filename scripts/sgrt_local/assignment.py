#!/usr/bin/env python3
"""Nearest *known eligible* supply by service, without weights for provider counts.

This is a potential-accessibility baseline, not an enrollment, referral or patient
flow model. Normative attachments belong to a separate evidence table. Capacity
is retained as an unallocated attribute, never silently treated as zero/infinity.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

SUPPLY_STATUSES = {'observed', 'proxy', 'unknown', 'confirmed_absent'}


def _require(frame: pd.DataFrame, columns: Iterable[str], name: str) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f'{name}: missing columns {sorted(missing)}')
    if frame[list(columns)].isna().any().any():
        raise ValueError(f'{name}: null required identifiers or values')


def _ids(frame: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    frame = frame.copy()
    for column in columns:
        frame[column] = frame[column].astype(str)
    return frame


def assign_nearest(
    origins: pd.DataFrame,
    supply: pd.DataFrame,
    costs: pd.DataFrame,
    *,
    service_codes: Iterable[str] | None = None,
    allow_proxy: bool = False,
    max_cost_minutes: float | None = None,
    tie_atol_minutes: float = 1e-6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (one row per origin/service, all admissible known candidates).

    origins: source_record_id (settlement identifier).
    supply: provider_id (activity site), source_record_id (its settlement),
      service_code (exact service/educational stage), supply_status. Optional
      capacity_total, observation_year, source_id are retained in candidates.
    costs: origin_id, provider_id, cost_minutes, optionally service_code.

    Missing route records remain unknown. In the absence of a recorded route, an
    observed same-settlement site receives a labeled zero-minute *NP-level*
    co-location assumption; it is not an estimate of actual within-city travel.
    Explicit recorded costs, including missing costs, are never overwritten.
    max_cost_minutes is an optional explicit scenario restriction, not a Russian
    standard. By default no reachability threshold is invented.
    """
    _require(origins, ['source_record_id'], 'origins')
    _require(supply, ['provider_id', 'source_record_id', 'service_code', 'supply_status'], 'supply')
    _require(costs, ['origin_id', 'provider_id'], 'costs')
    if 'cost_minutes' not in costs:
        raise ValueError('costs: missing cost_minutes')
    if max_cost_minutes is not None and (not np.isfinite(max_cost_minutes) or max_cost_minutes < 0):
        raise ValueError('max_cost_minutes must be finite and nonnegative')
    if not np.isfinite(tie_atol_minutes) or tie_atol_minutes < 0:
        raise ValueError('tie_atol_minutes must be finite and nonnegative')

    origins = _ids(origins, ['source_record_id'])
    supply = _ids(supply, ['provider_id', 'source_record_id', 'service_code'])
    costs = _ids(costs, ['origin_id', 'provider_id'])
    if origins.source_record_id.duplicated().any():
        raise ValueError('origins: duplicate source_record_id')
    if supply.duplicated(['provider_id', 'service_code']).any():
        raise ValueError('supply: duplicate provider/service; reconcile evidence first')
    if not supply.supply_status.isin(SUPPLY_STATUSES).all():
        raise ValueError('supply: unrecognized supply_status')
    if (supply.groupby('provider_id').source_record_id.nunique() > 1).any():
        raise ValueError('supply: one provider activity site has multiple settlements')
    if 'capacity_total' not in supply:
        supply['capacity_total'] = np.nan
    else:
        original = supply.capacity_total
        supply['capacity_total'] = pd.to_numeric(original, errors='coerce')
        if (original.notna() & supply.capacity_total.isna()).any():
            raise ValueError('supply: nonnumeric nonmissing capacity_total')
        if (supply.capacity_total.dropna() < 0).any() or np.isinf(supply.capacity_total.dropna()).any():
            raise ValueError('supply: invalid capacity_total')
    costs['cost_minutes'] = pd.to_numeric(costs.cost_minutes, errors='raise')
    if (costs.cost_minutes.dropna() < 0).any():
        raise ValueError('costs: negative cost_minutes')
    route_key = ['origin_id', 'provider_id']
    if 'service_code' in costs:
        _require(costs, ['service_code'], 'costs')
        costs = _ids(costs, ['service_code'])
        route_key.append('service_code')
    if costs.duplicated(route_key).any():
        raise ValueError('costs: duplicate origin/provider/service route')
    if not costs.origin_id.isin(origins.source_record_id).all():
        raise ValueError('costs: unknown origin_id')
    if not costs.provider_id.isin(supply.provider_id).all():
        raise ValueError('costs: unknown provider_id')

    services = sorted(set(map(str, service_codes))) if service_codes is not None else sorted(supply.service_code.unique())
    eligible_states = {'observed', 'proxy'} if allow_proxy else {'observed'}
    eligible = supply[supply.supply_status.isin(eligible_states)].copy()
    eligible = eligible.rename(columns={'source_record_id': 'provider_settlement_id'})
    route_columns = ['origin_id', 'provider_id', 'cost_minutes'] + (['service_code'] if 'service_code' in costs else [])
    route_columns += [column for column in ['network_minutes', 'connector_minutes', 'route_status', 'origin_snap_km', 'destination_snap_km', 'origin_connector_over_2km', 'destination_connector_over_2km', 'same_settlement_zero_cost_assumption', 'transport_source_id'] if column in costs]
    candidate_frames = []
    outcome_rows = []
    for service in services:
        providers = eligible[eligible.service_code.eq(service)].copy()
        route_subset = costs.loc[costs.service_code.eq(service), route_columns].copy() if 'service_code' in costs else costs[route_columns].copy()
        if 'service_code' in route_subset:
            route_subset = route_subset.drop(columns='service_code')
        route_subset['route_record_present'] = True
        # Only recorded routes are materialized; an origin with no route remains
        # unresolved unless known supply lies inside its own settlement.
        candidates = route_subset.merge(providers, on='provider_id', how='inner', validate='many_to_one')
        candidates['route_basis'] = 'recorded_cost'
        if 'same_settlement_zero_cost_assumption' in candidates:
            co_location = candidates.same_settlement_zero_cost_assumption.map(lambda value: str(value).lower() in {'true', '1'})
            candidates.loc[co_location, 'route_basis'] = 'same_settlement_zero_assumption'
        # Add missing same-settlement alternatives, but do not replace an
        # explicit null/inf cost (which can encode an unresolved route).
        local = providers[providers.provider_settlement_id.isin(origins.source_record_id)].copy()
        local['origin_id'] = local.provider_settlement_id
        existing_keys = set(zip(route_subset.origin_id, route_subset.provider_id))
        local = local.loc[[key not in existing_keys for key in zip(local.origin_id, local.provider_id)]].copy()
        local['cost_minutes'] = 0.0
        local['route_record_present'] = False
        local['route_basis'] = 'same_settlement_zero_assumption'
        candidates = pd.concat([candidates, local], ignore_index=True)
        candidates = candidates[np.isfinite(candidates.cost_minutes)].copy()
        if max_cost_minutes is not None:
            candidates = candidates[candidates.cost_minutes <= max_cost_minutes].copy()
        candidates['is_local'] = candidates.origin_id.eq(candidates.provider_settlement_id)
        candidates['capacity_status'] = np.where(candidates.capacity_total.isna(), 'unknown', 'reported_total_not_allocated')
        candidates['capacity_feasibility'] = 'not_estimated'
        candidates['evidence_kind'] = 'modeled_nearest_known_eligible'
        candidates['established_flow'] = False
        candidates['route_is_observed_trip'] = False
        candidates['selected_nearest'] = False
        candidates['tie_count'] = 0
        for origin in origins.source_record_id:
            subset = candidates[candidates.origin_id.eq(origin)]
            local_providers = providers[providers.provider_settlement_id.eq(origin)]
            local_source = supply[supply.source_record_id.eq(origin) & supply.service_code.eq(service)]
            if len(local_providers):
                local_status = 'known_service_present'
            elif len(local_source) and local_source.supply_status.eq('confirmed_absent').all():
                local_status = 'confirmed_absent_in_input'
            else:
                local_status = 'unknown'
            row = dict(origin_id=origin, service_code=service,
                       selected_provider_id=None, selected_provider_settlement_id=None,
                       nearest_cost_minutes=np.nan, tied_provider_ids='', tied_count=0,
                       candidate_count=len(subset), known_provider_count=len(providers),
                       local_supply_status=local_status, selected_capacity_total=np.nan,
                       selected_capacity_status='unknown', capacity_feasibility='not_estimated',
                       evidence_kind='modeled_nearest_known_eligible', established_flow=False,
                       local_supply_unknown_could_change_choice=local_status == 'unknown',
                       outside_known_supply_unknown=True,
                       max_cost_minutes=max_cost_minutes, proxy_supply_allowed=allow_proxy)
            if subset.empty:
                row['assignment_status'] = 'unresolved_no_known_eligible_provider' if providers.empty else 'unresolved_no_admissible_recorded_cost'
                row['route_basis'] = None
            else:
                minimum = float(subset.cost_minutes.min())
                nearest = subset[np.isclose(subset.cost_minutes, minimum, atol=tie_atol_minutes, rtol=0)].sort_values('provider_id')
                candidates.loc[nearest.index, 'selected_nearest'] = True
                candidates.loc[nearest.index, 'tie_count'] = len(nearest)
                row.update(nearest_cost_minutes=minimum, tied_provider_ids='|'.join(nearest.provider_id), tied_count=len(nearest))
                if len(nearest) > 1:
                    row['assignment_status'] = 'unresolved_equal_cost_candidates'
                    row['route_basis'] = None
                else:
                    chosen = nearest.iloc[0]
                    row.update(selected_provider_id=chosen.provider_id,
                               selected_provider_settlement_id=chosen.provider_settlement_id,
                               selected_capacity_total=chosen.capacity_total,
                               selected_capacity_status=chosen.capacity_status,
                               route_basis=chosen.route_basis,
                               assignment_status='local_candidate' if chosen.is_local else 'external_candidate')
            outcome_rows.append(row)
        candidate_frames.append(candidates)
    outcomes = pd.DataFrame(outcome_rows)
    candidates = pd.concat(candidate_frames, ignore_index=True) if candidate_frames else pd.DataFrame()
    return outcomes, candidates


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix.lower() == '.parquet' else pd.read_csv(path, dtype={'source_record_id': str, 'origin_id': str, 'provider_id': str, 'service_code': str})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origins', type=Path, required=True)
    parser.add_argument('--supply', type=Path, required=True)
    parser.add_argument('--costs', type=Path, required=True)
    parser.add_argument('--services', help='Comma-separated exact service codes; default all listed in supply')
    parser.add_argument('--allow-proxy', action='store_true', help='Explicit sensitivity scenario; default accepts only observed presence')
    parser.add_argument('--max-cost-minutes', type=float, default=None, help='Optional explicit scenario screen, no built-in radius')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    outcomes, candidates = assign_nearest(_read(args.origins), _read(args.supply), _read(args.costs),
        service_codes=args.services.split(',') if args.services else None,
        allow_proxy=args.allow_proxy, max_cost_minutes=args.max_cost_minutes)
    args.output.mkdir(parents=True, exist_ok=True)
    outcomes.to_csv(args.output/'assignments.csv', index=False)
    candidates.to_csv(args.output/'candidates.csv', index=False)
    outcomes.to_parquet(args.output/'assignments.parquet', index=False)
    candidates.to_parquet(args.output/'candidates.parquet', index=False)
    print(f'origin_service_rows={len(outcomes)} known_candidates={len(candidates)} established_flows=0')


if __name__ == '__main__':
    main()
