#!/usr/bin/env python3
"""Corrected coordinate + actual-year path coverage across every residual axis.

The original calculation filtered additions to ``identity_path`` rows. This
version includes any exact residual observation whose missing axis is resolved
by both an accepted point and an accepted same-place component spanning at
least two observed census years. It reports the old residual class for audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd



def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def measure_v2(config_path: Path, residual_path: Path, output_path: Path, additions_path: Path) -> dict:
    # Reuse pinned validation and accepted-status definitions, then independently
    # construct the inclusive residual additions from the same verified inputs.
    cfg = json.loads(config_path.read_text())
    selected_path = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
    graph_path = Path(cfg['working_identity_graph'])
    points_path = Path(cfg['working_point_uses'])
    selected = pd.read_parquet(selected_path, columns=[
        'source_record_id', 'census_year', 'population', 'is_additive_settlement_record'
    ])
    edges = pd.read_parquet(graph_path, columns=[
        'from_source_record_id', 'to_source_record_id', 'relation', 'decision_status'
    ])
    points = pd.read_parquet(points_path, columns=[
        'target_source_record_id', 'coordinate_admission_status', 'latitude', 'longitude'
    ])
    EDGE_STATUSES = {
        'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
        'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
        'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
    }
    POINT_STATUSES = {
        'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
        'reviewed_extension_rule_accepted', 'reviewed_case_accepted',
    }
    selected['source_record_id'] = selected.source_record_id.astype(str)
    selected['census_year'] = pd.to_numeric(selected.census_year, errors='raise').astype(int)
    points = points.loc[points.coordinate_admission_status.isin(POINT_STATUSES)].copy()
    points['target_source_record_id'] = points.target_source_record_id.astype(str)
    if points.target_source_record_id.duplicated().any():
        raise ValueError('accepted point target is duplicated')
    lat = pd.to_numeric(points.latitude, errors='coerce')
    lon = pd.to_numeric(points.longitude, errors='coerce')
    if not (lat.between(-90, 90).all() and lon.between(-180, 180).all()):
        raise ValueError('accepted point ledger contains invalid WGS84 coordinates')
    point_ids = set(points.target_source_record_id)
    active = edges.loc[edges.relation.eq('same_place') & edges.decision_status.isin(EDGE_STATUSES)]
    # Union-find over selected exact IDs; components with duplicate selected
    # records in a year are excluded, matching the original fail-closed rule.
    ids = set(selected.source_record_id)
    parent = {sid: sid for sid in ids}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in active[['from_source_record_id', 'to_source_record_id']].itertuples(index=False, name=None):
        a, b = str(a), str(b)
        if a not in parent or b not in parent:
            raise ValueError('accepted edge endpoint is absent from selected observations')
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    years_by_root: dict[str, list[int]] = {}
    for sid, year in selected[['source_record_id', 'census_year']].itertuples(index=False, name=None):
        years_by_root.setdefault(find(sid), []).append(int(year))
    valid_roots = {root for root, years in years_by_root.items()
                   if len(years) == len(set(years)) and len(set(years)) >= 2}
    path_ids = {sid for sid in ids if find(sid) in valid_roots}

    residual = pd.read_parquet(residual_path)
    if residual.source_record_id.isna().any() or residual.source_record_id.astype(str).duplicated().any():
        raise ValueError('residual IDs blank or duplicated')
    if not set(residual.missing_joint_axis.dropna().astype(str)) <= {
        'identity_path', 'identity_and_point', 'coordinate', 'point'
    }:
        raise ValueError('unrecognized residual axis')
    residual['source_record_id'] = residual.source_record_id.astype(str)
    residual['population'] = pd.to_numeric(residual.population, errors='coerce')
    if not set(residual.source_record_id).issubset(ids):
        raise ValueError('residual contains IDs absent from selected observations')
    if 'is_additive_settlement_record' in residual and not residual.is_additive_settlement_record.fillna(False).astype(bool).all():
        raise ValueError('residual includes non-additive records')
    source_check = selected.set_index('source_record_id')
    for row in residual[['source_record_id', 'census_year', 'population']].itertuples(index=False, name=None):
        sid, year, population = str(row[0]), int(row[1]), float(row[2])
        src = source_check.loc[sid]
        source_pop = pd.to_numeric(pd.Series([src.population]), errors='coerce').iloc[0]
        population_matches = (pd.isna(source_pop) and pd.isna(population)) or (
            not pd.isna(source_pop) and not pd.isna(population) and float(source_pop) == population
        )
        if int(src.census_year) != year or not population_matches:
            raise ValueError(f'residual population/year differs from selected layer: {sid}')
    residual['population'] = residual.population.fillna(0)
    additions = residual.loc[residual.source_record_id.isin(path_ids & point_ids)].copy()
    additions['actual_year_path_rule'] = 'accepted_same_place_component_with_at_least_two_actual_selected_census_years; no missing-year row imputed'
    additions['was_two_census_year_path'] = additions.source_record_id.isin(path_ids)
    additions['corrected_from_prior_filter'] = additions.missing_joint_axis.ne('identity_path')
    summary = {
        'status': 'corrected_all_residual_axes_actual_observed_year_path_coverage_measured',
        'definition': 'Every exact additive selected residual row counts if it has an accepted point and an accepted same_place component with at least two distinct actually observed selected census years. No missing-year observation is imputed. All old missing_joint_axis classes are eligible; any apparent inclusion is resolved by these two predicates.',
        'prior_measurement_correction': 'The prior implementation filtered to missing_joint_axis=identity_path, omitting rows that were classified identity_and_point before a newly admitted edge and point resolved both requirements.',
        'accepted_edges': int(len(active)),
        'accepted_point_uses': int(len(points)),
        'residual_input_rows': int(len(residual)),
        'qualifying_residual_rows': int(len(additions)),
        'qualifying_population_by_prior_axis': {str(axis): int(g.population.sum()) for axis, g in additions.groupby('missing_joint_axis', dropna=False)},
        'corrected_rows_by_prior_axis': {str(axis): int(n) for axis, n in additions.groupby('missing_joint_axis', dropna=False).size().items()},
        'corrected_from_prior_filter_population': int(additions.loc[additions.corrected_from_prior_filter, 'population'].sum()),
        'results': {},
        'inputs': {'config': str(config_path), 'residual': str(residual_path), 'identity_graph': str(graph_path), 'point_uses': str(points_path)},
        'input_sha256': {
            str(path): sha256(path)
            for path in (config_path, residual_path, selected_path, graph_path, points_path, Path(cfg['working_scoped_joint_coverage']))
        },
    }
    for year, group in additions.groupby('census_year', sort=True):
        pop = int(group.population.sum())
        # Base metric is the pinned scope-aware result, read from its config path.
        base_path = Path(cfg['working_scoped_joint_coverage'])
        base = json.loads(base_path.read_text())
        # tolerate the existing known schema while requiring the year entry
        by_year = base['results'][str(int(year))]
        base_pop = int(by_year.get('available_scope_joint_population', 0))
        # The source JSON stores this value in a named field; fall back to the
        # explicit configured Graph24 scope-aware metric receipt field.
        if not base_pop:
            raise ValueError(f'could not resolve pinned scope-aware baseline for {year}')
        control = int(cfg['official_controls'][str(int(year))])
        total = base_pop + pop
        summary['results'][str(int(year))] = {
            'official_control_population': control,
            'scope_aware_baseline_population': base_pop,
            'corrected_additional_population': pop,
            'coordinate_and_actual_observed_year_path_population': total,
            'control_fraction_percent': 100 * total / control,
            'remaining_to_99_percent': max(0, int((control * 99 + 99) // 100) - total),
        }
    additions.to_csv(additions_path, index=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--residual', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--additions', type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(measure_v2(args.config, args.residual, args.output, args.additions), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
