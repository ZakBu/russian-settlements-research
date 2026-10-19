"""Exact spherical functional fields, explicitly scenario-based, with no forced coverage.

Input origins: entity_uid, lat, lon, population_2021.
Input candidates: entity_uid, lat, lon, one or more supplied q_* columns.
Candidate selection and functional evidence must have their own provenance.
Each count is used separately. Scores and normalized weights are NOT observed flows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd

EARTH_KM = 6371.0088


def distances_km(origin_coords: np.ndarray, center_coords: np.ndarray) -> np.ndarray:
    a = np.radians(np.asarray(origin_coords, dtype=float))
    b = np.radians(np.asarray(center_coords, dtype=float))
    dy = a[:, None, 0] - b[None, :, 0]
    dx = a[:, None, 1] - b[None, :, 1]
    h = np.sin(dy / 2) ** 2 + np.cos(a[:, None, 0]) * np.cos(b[None, :, 0]) * np.sin(dx / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.suffix == '.parquet' else pd.read_csv(path)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(2**20), b''):
            digest.update(block)
    return digest.hexdigest()


def check_input(frame: pd.DataFrame, name: str, q_columns: list[str] = ()) -> None:
    required = ['entity_uid', 'lat', 'lon', *q_columns]
    assert set(required) <= set(frame), (name, set(required) - set(frame))
    assert not frame['entity_uid'].isna().any(), name
    assert frame['entity_uid'].is_unique, name
    assert np.isfinite(frame[['lat', 'lon']].to_numpy(dtype=float)).all(), name
    assert frame['lat'].between(-90, 90).all(), name
    assert frame['lon'].between(-180, 180).all(), name
    for q in q_columns:
        assert frame[q].notna().all(), f'{name}: q missingness needs explicit upstream treatment'
        assert np.isfinite(frame[q]).all() and frame[q].ge(0).all(), (name, q)


def compute_chunk(origins: pd.DataFrame, candidates: pd.DataFrame, q_column: str,
                  distances: np.ndarray, beta: float, d0: float, q_ref: float,
                  margin: float = 1.5) -> pd.DataFrame:
    ids = origins.entity_uid.to_numpy(dtype=str)
    cids = candidates.entity_uid.to_numpy(dtype=str)
    q = candidates[q_column].to_numpy(dtype=float)
    self_mask = ids[:, None] == cids[None, :]
    score = q[None, :] / q_ref * (1 + distances / d0) ** (-beta)
    local = np.sum(np.where(self_mask, score, 0), axis=1)
    external = np.where(self_mask, 0, score)
    n = len(origins)
    if len(candidates):
        best = np.argmax(external, axis=1)
        top = external[np.arange(n), best]
        ctop = cids[best].astype(object)
        dtop = distances[np.arange(n), best].copy()
        if len(candidates) > 1:
            second_scores = external.copy()
            second_scores[np.arange(n), best] = -1
            second = np.argmax(second_scores, axis=1)
            runner = np.maximum(second_scores[np.arange(n), second], 0)
            crunner = cids[second].astype(object)
            drunner = distances[np.arange(n), second].copy()
        else:
            runner = np.zeros(n)
            crunner = np.full(n, None, dtype=object)
            drunner = np.full(n, np.nan)
        ctop[top <= 0] = None
        dtop[top <= 0] = np.nan
        crunner[runner <= 0] = None
        drunner[runner <= 0] = np.nan
    else:
        top = runner = np.zeros(n)
        ctop = crunner = np.full(n, None, dtype=object)
        dtop = drunner = np.full(n, np.nan)
    total_external = external.sum(axis=1)
    denom = 1 + local + total_external
    alternative = np.maximum(np.maximum(runner, local), 1)
    dominance = top / alternative
    status = np.full(n, 'below_absolute_threshold', dtype=object)
    status[(top > 1) & (local >= top)] = 'local_option_at_least_as_strong'
    status[(top > 1) & (top > local) & (dominance < margin)] = 'contested'
    status[(top > 1) & (top > local) & (dominance >= margin)] = 'scenario_dominant'
    status[top <= 0] = 'no_observed_external_supplier'
    result = pd.DataFrame({
        'entity_uid': ids, 'function': q_column, 'beta': beta, 'd0_km': d0,
        'q_ref': q_ref, 'margin_scenario': margin, 'top_center_uid': ctop,
        'second_center_uid': crunner, 'top_distance_km': dtop,
        'second_distance_km': drunner, 'top_score': top, 'second_score': runner,
        'local_score': local, 'external_score_sum': total_external,
        'outside_weight': 1 / denom, 'local_weight': local / denom,
        'external_weight_sum': total_external / denom,
        'top_weight': top / denom, 'dominance_over_best_alternative': dominance,
        'status': status,
        'lose_observed_absolute_option_if_top_removed': (top > 1) & (runner <= 1) & (local <= 1),
        'evidence_status': 'scenario_potential_not_observed_flow',
    })
    np.testing.assert_allclose(result.outside_weight + result.local_weight + result.external_weight_sum, 1, atol=1e-12)
    assert not (result.entity_uid == result.top_center_uid).any()
    assert result.loc[result.status.eq('scenario_dominant'), 'top_score'].gt(1).all()
    return result


def synthetic_checks() -> dict:
    # 1 degree is ~111km; a remote lone candidate must not force strong assignment.
    origins = pd.DataFrame({'entity_uid': ['remote', 'between', 'self', 'tiny'],
                            'lat': [20., 0., 0., 0.], 'lon': [20., 0., 1., 2.01]})
    centers = pd.DataFrame({'entity_uid': ['left', 'self', 'tiny_service'],
                            'lat': [0., 0., 0.], 'lon': [-1., 1., 2.],
                            'q_Q': [100., 100., 1.]})
    ds = distances_km(origins[['lat', 'lon']].to_numpy(), centers[['lat', 'lon']].to_numpy())
    r = compute_chunk(origins, centers, 'q_Q', ds, beta=2, d0=10, q_ref=1)
    assert r.iloc[0].status == 'below_absolute_threshold'
    assert r.iloc[1].top_score == r.iloc[1].second_score
    assert r.iloc[1].status != 'scenario_dominant'
    assert r.iloc[2].top_center_uid != 'self'
    assert r.iloc[2].local_weight > r.iloc[2].top_weight
    # A single specialized supplier remains a candidate even if no second function exists.
    assert centers.loc[centers.entity_uid.eq('tiny_service'), 'q_Q'].iloc[0] == 1
    stronger = centers.copy()
    stronger['q_Q'] *= 2
    s = compute_chunk(origins, stronger, 'q_Q', ds, 2, 10, 1)
    np.testing.assert_allclose(s.top_score, 2 * r.top_score)
    far = compute_chunk(origins, centers, 'q_Q', ds + 10, 2, 10, 1)
    assert (far.top_score <= r.top_score).all()
    return {'status': 'PASS', 'checks': 8,
            'negative_cases': ['remote_lone_candidate', 'equal_competitors', 'local_self_supply'],
            'scope': 'algebra_and_implementation_not_empirical_validity'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origins', type=Path)
    parser.add_argument('--candidates', type=Path)
    parser.add_argument('--q-columns', nargs='+')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--beta', nargs='+', type=float, default=[1.5, 2., 3.])
    parser.add_argument('--d0', nargs='+', type=float, default=[5., 10., 20.])
    parser.add_argument('--q-ref', nargs='+', type=float, default=[1., 5.])
    parser.add_argument('--chunk', type=int, default=256)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    checks = synthetic_checks()
    if args.self_test:
        print(json.dumps(checks, ensure_ascii=False))
        return
    assert all([args.origins, args.candidates, args.q_columns, args.out])
    assert min(args.beta + args.d0 + args.q_ref) > 0
    origins = read_table(args.origins)
    candidates = read_table(args.candidates)
    check_input(origins, 'origins')
    check_input(candidates, 'candidates', args.q_columns)
    args.out.mkdir(parents=True, exist_ok=False)
    summaries, produced = [], []
    for function in args.q_columns:
        suppliers = candidates[candidates[function].gt(0)].copy()
        for beta, d0, q_ref in product(args.beta, args.d0, args.q_ref):
            pieces = []
            for start in range(0, len(origins), args.chunk):
                batch = origins.iloc[start:start + args.chunk]
                ds = distances_km(batch[['lat', 'lon']].to_numpy(), suppliers[['lat', 'lon']].to_numpy())
                pieces.append(compute_chunk(batch, suppliers, function, ds, beta, d0, q_ref))
            result = pd.concat(pieces, ignore_index=True)
            assert result.entity_uid.is_unique and len(result) == len(origins)
            path = args.out / f'{function}_b{beta:g}_d{d0:g}_q{q_ref:g}.parquet'
            result.to_parquet(path, index=False)
            produced.append({'file': path.name, 'rows': len(result), 'sha256': sha(path)})
            for status, group in result.groupby('status', dropna=False):
                summaries.append({'function': function, 'beta': beta, 'd0': d0, 'q_ref': q_ref,
                                  'status': status, 'n_origins': len(group)})
            print(json.dumps({'file': path.name, 'rows': len(result),
                              'suppliers': len(suppliers)}, ensure_ascii=False), flush=True)
    pd.DataFrame(summaries).to_csv(args.out / 'scenario_summary.csv', index=False)
    manifest = {'status': 'COMPUTED_SCENARIO_FIELDS', 'observed_flow_claim': False,
                'absolute_threshold_empirically_calibrated': False,
                'all_centers_exact': True, 'origins_sha256': sha(args.origins),
                'candidates_sha256': sha(args.candidates), 'outputs': produced,
                'q_columns': args.q_columns, 'synthetic_checks': checks,
                'distance': 'haversine_sphere_km_R6371.0088',
                'outside_option': 1, 'local_option': 'own_observed_supply_separate_from_external'}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
