#!/usr/bin/env python3
"""Add an explicit coordinate-plus-path axis for the census years each place actually has."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from research_rebuild.mass_linkage.coverage import identity_sets

CONTROLS = {2002: 145166731, 2010: 142856536, 2021: 147182123}
ACCEPTED_EDGE_STATUSES = {
    'checked_rule_accepted',
    'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review',
    'case_specific_independent_review_accepted',
    'case_review_accepted',
    'independent_case_review_accepted',
    'accepted_case_specific',
}
ACCEPTED_POINT_STATUSES = {
    'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
    'reviewed_extension_rule_accepted', 'reviewed_case_accepted',
}


def measure(config_path: Path, residual_path: Path, output_path: Path, additions_path: Path) -> dict:
    cfg = json.loads(config_path.read_text())
    scope_path = Path(cfg['working_scoped_joint_coverage'])
    graph_path = Path(cfg['working_identity_graph'])
    points_path = Path(cfg['working_point_uses'])
    selected_path = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')

    selected = pd.read_parquet(selected_path, columns=[
        'source_record_id', 'census_year', 'population', 'population_scope', 'is_additive_settlement_record'
    ])
    if selected.source_record_id.isna().any() or selected.source_record_id.astype(str).duplicated().any():
        raise ValueError('selected observation IDs must be unique and nonnull')
    edges = pd.read_parquet(graph_path, columns=[
        'from_source_record_id', 'to_source_record_id', 'relation', 'decision_status'
    ])
    edges = edges.loc[
        edges.relation.eq('same_place') & edges.decision_status.isin(ACCEPTED_EDGE_STATUSES)
    ].copy()
    points = pd.read_parquet(points_path, columns=[
        'target_source_record_id', 'latitude', 'longitude', 'coordinate_admission_status'
    ])
    if points.target_source_record_id.isna().any() or points.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('accepted point ledger contains blank or duplicate target IDs')
    if not points.coordinate_admission_status.isin(ACCEPTED_POINT_STATUSES).all():
        raise ValueError('unadmitted point candidate found in accepted point ledger')
    if not pd.to_numeric(points.latitude, errors='coerce').between(-90, 90).all():
        raise ValueError('accepted latitude outside WGS84')
    if not pd.to_numeric(points.longitude, errors='coerce').between(-180, 180).all():
        raise ValueError('accepted longitude outside WGS84')

    # This independent DFS fails closed on absent graph endpoints, unaccepted
    # edges, and same-year collisions. It returns components across the actual
    # selected census rows only; no unobserved census row is created.
    linked, full_three, components = identity_sets(selected, edges)
    year_by_id = selected.set_index('source_record_id').census_year.astype(int).to_dict()
    additive_by_id = selected.set_index('source_record_id').is_additive_settlement_record.fillna(False).astype(bool).to_dict()
    scope_by_id = selected.set_index('source_record_id').population_scope.to_dict()
    point_ids = set(points.target_source_record_id.astype(str))

    observed_path_ids: set[str] = set()
    two_census_path_ids: set[str] = set()
    observed_years_by_id: dict[str, str] = {}
    two_year_component_count = 0
    component_summary = defaultdict(int)
    for component in components:
        observed_years = {year_by_id[sid] for sid in component}
        if len(observed_years) < 2:
            continue
        if not all(additive_by_id[sid] and scope_by_id.get(sid) != 'federal_city_region' for sid in component):
            component_summary['nonadditive_or_federal_components_excluded'] += 1
            continue
        if len(observed_years) == 2:
            two_census_path_ids.update(component)
            two_year_component_count += 1
        elif observed_years != {2002, 2010, 2021}:
            component_summary['unexpected_observed_year_shape_excluded'] += 1
            continue
        observed_path_ids.update(component)
        encoded_years = ','.join(map(str, sorted(observed_years)))
        for sid in component:
            observed_years_by_id[sid] = encoded_years

    # The current scope-aware score already includes its reviewed three-date
    # trajectories and territorial layers. Add only ordinary selected rows it
    # left in the residual, and only where that exact row has an accepted point
    # and its accepted component links all census years actually selected for
    # that place. This preserves non-additive exclusions and prevents overlap.
    residual = pd.read_parquet(residual_path)
    if residual.source_record_id.isna().any() or residual.source_record_id.astype(str).duplicated().any():
        raise ValueError('scope-aware residual IDs are blank or duplicated')
    residual_ids = set(residual.source_record_id.astype(str))
    selected_ids = set(selected.source_record_id.astype(str))
    if not residual_ids.issubset(selected_ids):
        raise ValueError(f'scope-aware residual contains {len(residual_ids - selected_ids)} IDs absent from selected observations')
    if 'is_additive_settlement_record' in residual.columns:
        if not residual.is_additive_settlement_record.fillna(False).astype(bool).all():
            raise ValueError('scope-aware residual includes non-additive rows')
    if 'missing_joint_axis' not in residual.columns:
        raise ValueError('scope-aware residual lacks missing_joint_axis classification')
    unexpected_axes = set(residual.missing_joint_axis.dropna().astype(str)) - {
        'identity_path', 'identity_and_point', 'coordinate', 'point',
        'population_scope', 'outside_coverage', 'event_or_scope'
    }
    if unexpected_axes:
        raise ValueError(f'unrecognized residual classifications: {sorted(unexpected_axes)}')
    additions = residual.loc[
        residual.source_record_id.astype(str).isin(observed_path_ids & point_ids)
    ].copy()
    additions = additions.loc[additions.missing_joint_axis.eq('identity_path')].copy()
    if additions.empty:
        raise ValueError('no coordinate-plus-actual-year-path additions found')
    additions['observed_census_years'] = additions.source_record_id.astype(str).map(observed_years_by_id)
    additions['actual_year_path_rule'] = 'accepted_same_place_component_with_all_selected_census_years_connected; no missing-year row imputed'
    additions['was_two_census_year_path'] = additions.source_record_id.astype(str).isin(two_census_path_ids)

    # Reconcile the exact added source rows to selected population values.
    selected_by_id = selected.set_index('source_record_id')
    for row in additions.itertuples(index=False):
        sid = str(row.source_record_id)
        if sid not in selected_by_id.index:
            raise ValueError(f'residual row absent from selected layer: {sid}')
        if int(row.census_year) != int(selected_by_id.loc[sid].census_year):
            raise ValueError(f'census-year mismatch for residual row: {sid}')
        if float(row.population) != float(selected_by_id.loc[sid].population):
            raise ValueError(f'population changed for residual row: {sid}')

    base = json.loads(scope_path.read_text())
    result = {}
    for year, control in CONTROLS.items():
        selected_year = selected.loc[selected.census_year.astype(int).eq(year)]
        base_population = int(base['results'][str(year)]['available_scope_joint_population'])
        added = additions.loc[additions.census_year.astype(int).eq(year)]
        added_population = int(added.population.sum())
        total = base_population + added_population
        denominator = int(selected_year.population.sum())
        result[str(year)] = {
            'official_control_population': control,
            'selected_known_population': denominator,
            'existing_scope_aware_full_three_year_and_reviewed_scope_population': base_population,
            'additional_ordinary_rows_with_complete_actual_observed_year_path_and_accepted_point': added_population,
            'additional_rows': int(len(added)),
            'additional_two_selected_census_year_path_population': int(added.loc[added.was_two_census_year_path, 'population'].sum()),
            'coordinate_and_actual_observed_year_path_population': total,
            'control_fraction_percent': 100 * total / control,
            'selected_population_fraction_percent': 100 * total / denominator if denominator else None,
            'remaining_to_99_percent': max(0, math.ceil(control * .99) - total),
            'remaining_to_100_percent': max(0, control - total),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    additions_path.parent.mkdir(parents=True, exist_ok=True)
    additions.sort_values(['census_year', 'population', 'source_record_id'], ascending=[True, False, True]).to_csv(
        additions_path, index=False
    )
    summary = {
        'status': 'actual_observed_census_year_path_coverage_measured',
        'definition': 'A selected additive census record counts on this supplemental axis when it has an accepted point and belongs to an accepted same_place component with at least two distinct selected census years. All selected records represented in that accepted component are connected; duplicate source rows per year fail closed. The axis does not claim that the component exhausts every source row that might correspond to the place in other years; any unlinked third-year row remains uncovered. This supplements the existing scope-aware full-2002-2010-2021 metric; it does not impute missing census observations, accept candidates, harmonize boundaries, or include federal aggregates in the ordinary graph.',
        'edge_statuses_used': sorted(ACCEPTED_EDGE_STATUSES),
        'point_statuses_used': sorted(ACCEPTED_POINT_STATUSES),
        'accepted_edges': int(len(edges)),
        'accepted_point_uses': int(len(points)),
        'components_with_two_selected_census_years': two_year_component_count,
        'two_census_path_endpoint_rows': int(len(two_census_path_ids)),
        'ordinary_actual_path_rows_in_current_scope_residual': int(len(additions)),
        'current_three_census_full_chain_ids': int(len(full_three)),
        'residual_input_rows': int(len(residual)),
        'existing_scope_aware_result_sha256': cfg.get('working_scoped_joint_coverage_sha256'),
        'input_paths': {
            'selected': str(selected_path), 'identity_graph': str(graph_path),
            'point_uses': str(points_path), 'scope_aware_residual': str(residual_path),
            'scope_aware_coverage': str(scope_path),
        },
        'component_exclusions': dict(component_summary),
        'results': result,
        'additions_csv': str(additions_path),
    }
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', type=Path, default=Path('config/mass_joint_20261004.json'))
    ap.add_argument('--residual', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--additions', type=Path, required=True)
    args = ap.parse_args()
    measure(args.config, args.residual, args.output, args.additions)


if __name__ == '__main__':
    main()
