"""Measured, document-specific external service graph; never a forced nationwide zoning.

Uses manually sourced service edges linked by the independent data agent.
Provider inventory is selected from all rows of each source act, not external edges.
Only exact resolved geographic links enter distance/coverage statistics.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from functional_fields import distances_km, sha


def gradient(group: pd.DataFrame) -> dict:
    unique = group.drop_duplicates('origin_uid').copy()
    n_linked = len(unique)
    unique = unique[unique.distance_km.notna()].copy()
    d = unique.distance_km.to_numpy(dtype=float)
    y = np.log1p(unique.population_2021_origin.to_numpy(dtype=float)) - np.log1p(unique.population_2010_origin.to_numpy(dtype=float))
    enough = len(unique) >= 5 and np.ptp(d) > 0
    return {
        'n_external_origins': n_linked,
        'n_geometry_eligible_origins': len(unique),
        'gradient_status': 'descriptive_small_catchment' if enough else 'insufficient_n_or_distance_range',
        'slope_log1p_population_change_per_km': np.polyfit(d, y, 1)[0] if enough else np.nan,
        'spearman_distance_log1p_change': spearmanr(d, y).statistic if enough and np.ptp(y) > 0 else np.nan,
        'min_distance_km': float(np.min(d)) if len(d) else np.nan,
        'max_distance_km': float(np.max(d)) if len(d) else np.nan,
        'median_distance_km': float(np.median(d)) if len(d) else np.nan,
    }


def build(axis_path: Path, edges_path: Path, out: Path,
          origin_col: str, destination_col: str, quarantine_path: Path | None = None) -> None:
    axis = pd.read_parquet(axis_path)
    assert axis.id.is_unique
    edges = pd.read_csv(edges_path)
    assert edges.edge_id.is_unique
    assert origin_col in edges and destination_col in edges
    edges = edges.rename(columns={origin_col: 'origin_uid', destination_col: 'destination_uid'})
    cols = ['id', 'name', 'type', 'region', 'lat', 'lon',
            'population_2002', 'population_2010', 'population_2021']
    for role, key in [('origin', 'origin_uid'), ('destination', 'destination_uid')]:
        a = axis[cols].rename(columns={c: f'{c}_{role}' for c in cols if c != 'id'}).rename(columns={'id': key})
        edges = edges.merge(a, how='left', on=key, validate='many_to_one')
    resolved = edges.origin_uid.isin(axis.id) & edges.destination_uid.isin(axis.id)
    edges['geography_status'] = np.where(resolved, 'both_exactly_linked', 'unresolved_preserved')
    edges['distance_km'] = np.nan
    for i in edges.index[resolved]:
        r = edges.loc[i]
        edges.at[i, 'distance_km'] = distances_km(np.array([[r.lat_origin, r.lon_origin]]),
                                               np.array([[r.lat_destination, r.lon_destination]]))[0, 0]
    quarantine = pd.read_csv(quarantine_path) if quarantine_path else pd.DataFrame(columns=['id', 'reason'])
    assert {'id', 'reason'} <= set(quarantine)
    quarantine_ids = set(quarantine.id.dropna())
    conflict = edges.origin_uid.isin(quarantine_ids) | edges.destination_uid.isin(quarantine_ids)
    edges['geometry_status'] = np.select([~resolved, conflict], ['unresolved', 'coordinate_conflict_quarantined'], default='reference2021_point_not_independently_resurveyed')
    edges['distance_km_from_input_unverified'] = edges['distance_km']
    edges.loc[conflict, 'distance_km'] = np.nan
    edges['is_external_resolved'] = resolved & edges.origin_uid.ne(edges.destination_uid)
    edges['observed_population_scope'] = 'all_2021_census_residents_in_documented_origins_not_service_users'
    edges['measured_trips_claim'] = False
    out.mkdir(parents=True, exist_ok=False)
    edges.to_csv(out / 'service_edges_calculated.csv', index=False)
    edges.to_parquet(out / 'service_edges_calculated.parquet', index=False)
    used = edges[edges.is_external_resolved].copy()
    summaries, gradients, bins = [], [], []
    for (source, dest), group in used.groupby(['source_id', 'destination_uid']):
        u = group.drop_duplicates('origin_uid')
        r = u.iloc[0]
        row = {'source_id': source, 'destination_uid': dest,
               'destination_name': r.name_destination,
               'n_documented_external_origins_linked': len(u),
               'n_documented_edges_linked': len(group),
               'source_document_date': r.source_document_date,
               'all_document_origins_extracted_asserted': False,
               'center_function': 'documented_external_service_not_all_functions',
               'flow_count_observed': False}
        for year in [2002, 2010, 2021]:
            row[f'external_census_population_{year}'] = float(u[f'population_{year}_origin'].sum())
            row[f'own_census_population_{year}'] = float(r[f'population_{year}_destination'])
        row['external_population_2021_per_own_population_2021'] = (
            row['external_census_population_2021'] / row['own_census_population_2021']
            if row['own_census_population_2021'] > 0 else np.nan)
        summaries.append(row)
        g = gradient(group)
        gradients.append({'source_id': source, 'destination_uid': dest, 'destination_name': r.name_destination,
                          'temporal_scope': 'retrospective_demography_in_document_year_service_territory', **g})
        u = u[u.distance_km.notna()].copy()
        if len(u) >= 5:
            # Origin distance terciles; equal-distance points stay together.
            labels = pd.qcut(u.distance_km, q=3, duplicates='drop')
            u = u.assign(distance_bin=labels)
            for interval, v in u.groupby('distance_bin', observed=True):
                p10, p21 = v.population_2010_origin.sum(), v.population_2021_origin.sum()
                bins.append({'source_id': source, 'destination_uid': dest, 'destination_name': r.name_destination,
                             'distance_interval_km': str(interval), 'n_origins': len(v),
                             'population_2010': float(p10), 'population_2021': float(p21),
                             'population_change_2010_2021': float(p21-p10),
                             'population_change_fraction': float(p21/p10-1) if p10 > 0 else np.nan,
                             'includes_all_zero_population_origins': True})
    pd.DataFrame(summaries).to_csv(out / 'documented_functional_centers.csv', index=False)
    pd.DataFrame(gradients).to_csv(out / 'documented_catchment_gradients.csv', index=False)
    pd.DataFrame(bins).to_csv(out / 'documented_distance_bins.csv', index=False)
    # Unique origin census population is counted once across overlapping destinations.
    totals = []
    for source, group in edges.groupby('source_id'):
        e = group[group.is_external_resolved]
        u = e.drop_duplicates('origin_uid')
        totals.append({'source_id': source, 'n_source_edges': len(group),
                       'n_resolved_edges': int(group.geography_status.eq('both_exactly_linked').sum()),
                       'n_resolved_external_edges': len(e), 'n_unique_external_origins': len(u),
                       'n_unique_external_centers': e.destination_uid.nunique(),
                       'n_multiple_destination_origins': int(e.groupby('origin_uid').destination_uid.nunique().gt(1).sum()),
                       'external_origin_census_population_2021_unique': float(u.population_2021_origin.sum()),
                       'n_population2010_zero_origins_retained': int(u.population_2010_origin.eq(0).sum())})
    pd.DataFrame(totals).to_csv(out / 'source_coverage.csv', index=False)
    assert len(edges) == len(pd.read_csv(edges_path))
    assert used.origin_uid.ne(used.destination_uid).all()
    assert used.distance_km.dropna().ge(0).all()
    assert not used.measured_trips_claim.any()
    for (source, dest), group in used.groupby(['source_id', 'destination_uid']):
        expected = group.drop_duplicates('origin_uid').population_2021_origin.sum()
        actual = [s['external_census_population_2021'] for s in summaries if s['source_id'] == source and s['destination_uid'] == dest][0]
        assert expected == actual
    manifest = {'status': 'PASS', 'input_sha256': {'axis': sha(axis_path), 'linked_edges': sha(edges_path)},
                'n_input_edges': len(edges), 'n_resolved_external_edges': len(used),
                'n_coordinate_quarantined_edges': int(conflict.sum()),
                'n_document_source_centers': len(summaries), 'observed_trip_count_available': False,
                'full_SGRT_claim': False, 'national_extrapolation': False,
                'evidence': 'documented_service_attachment_not_observed_travel',
                'demography': 'resident_cohort_not_number_of_schoolchildren',
                'checks': {'all_edges_preserved': True, 'self_excluded_from_external': True,
                           'population_double_count_within_center_avoided': True,
                           'population2010_zeros_retained': True,
                           'unresolved_not_geometrically_forced': True},
                'outputs': [{'file': p.name, 'sha256': sha(p)} for p in sorted(out.iterdir())]}
    if quarantine_path:
        manifest['input_sha256']['coordinate_quarantine'] = sha(quarantine_path)
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ['status', 'n_input_edges', 'n_resolved_external_edges', 'n_document_source_centers']}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--axis', type=Path, required=True)
    p.add_argument('--edges', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--origin-col', default='origin_uid')
    p.add_argument('--destination-col', default='destination_uid')
    p.add_argument('--coordinate-quarantine', type=Path)
    a = p.parse_args()
    build(a.axis, a.edges, a.out, a.origin_col, a.destination_col, a.coordinate_quarantine)
