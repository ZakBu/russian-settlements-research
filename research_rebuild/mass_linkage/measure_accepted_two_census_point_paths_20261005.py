#!/usr/bin/env python3
"""Audit accepted point-bearing components with exactly two census years.

This is a separate axis from full 2002-2010-2021 chains. Missing third-year
records remain unknown. It does not add these rows to the mixed scope-aware
measure; callers must first deduplicate scope-layer source IDs.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF

ROOT = Path('/workspace')
REPO = ROOT / 'russian-settlements-research'
WORK = ROOT / 'settlements-work/continuation_20261004'
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EDGES = WORK / 'accepted_graph22_krasnodar_20261005/accepted_identity_edges.parquet'
POINTS = WORK / 'accepted_graph22_krasnodar_20261005/accepted_point_uses.parquet'
RESIDUAL = WORK / 'coverage_graph20_solnechny_20261005/joint_residual.parquet'
GRAPH_COVERAGE = WORK / 'accepted_graph22_krasnodar_20261005/coverage.json'
OUT = REPO / 'research_rebuild/evidence/mass_joint_20261004/graph21_komarovsky_graph22_krasnodar/two_census_partial_paths'
EDGE_STATUSES = (
    'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
    'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
)
POINT_STATUSES = (
    'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
    'reviewed_extension_rule_accepted', 'reviewed_case_accepted',
)
BITS = {2002: 1, 2010: 2, 2021: 4}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '512MB'})
    obs = pq.read_table(SELECTED, columns=['source_record_id', 'census_year']).to_pydict()
    uf = YearUF([str(x) for x in obs['source_record_id']], [int(x) for x in obs['census_year']])
    accepted = con.execute(
        "select from_source_record_id,to_source_record_id from read_parquet(?) "
        "where decision_status in (select unnest(?))", [str(EDGES), list(EDGE_STATUSES)]
    ).fetchall()
    for a, b in accepted:
        if uf.union_ids(a, b) == 'year_constrained_collision':
            raise ValueError(f'same-census collision: {a!r} {b!r}')

    residual = pq.read_table(RESIDUAL, columns=[
        'source_record_id', 'census_year', 'population', 'population_value_quality',
        'accepted_latitude', 'accepted_longitude', 'missing_joint_axis',
    ]).to_pylist()
    candidates = []
    for r in residual:
        if (r['missing_joint_axis'] != 'identity_path' or r['population'] is None
                or r['accepted_latitude'] is None or r['accepted_longitude'] is None):
            continue
        sid = str(r['source_record_id'])
        i = uf.idx.get(sid)
        if i is None:
            raise ValueError(f'residual ID missing from selected census frame: {sid}')
        mask = int(uf.mask[uf.find(i)])
        if mask.bit_count() == 2:
            years = '|'.join(str(y) for y, bit in BITS.items() if mask & bit)
            candidates.append({
                'source_record_id': sid, 'census_year': int(r['census_year']),
                'population': int(r['population']),
                'population_value_quality': r['population_value_quality'] or 'unknown',
                'accepted_latitude': float(r['accepted_latitude']),
                'accepted_longitude': float(r['accepted_longitude']),
                'observed_component_census_years': years,
            })

    ids = [r['source_record_id'] for r in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate partial-path source IDs')
    point_rows = con.execute(
        "select target_source_record_id, latitude, longitude "
        "from read_parquet(?) where coordinate_admission_status in (select unnest(?)) "
        "and target_source_record_id in (select unnest(?))",
        [str(POINTS), list(POINT_STATUSES), ids],
    ).fetchall()
    point_map = {str(sid): (float(lat), float(lon)) for sid, lat, lon in point_rows}
    if len(point_rows) != len(ids) or set(point_map) != set(ids):
        raise ValueError('candidate ID set does not match exact accepted point ledger ID set')
    for r in candidates:
        lat, lon = point_map[r['source_record_id']]
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f'invalid WGS84 point: {r["source_record_id"]}')
        if (lat, lon) != (r['accepted_latitude'], r['accepted_longitude']):
            raise ValueError(f'point mismatch: {r["source_record_id"]}')

    scopes = pq.read_table(SELECTED, columns=['source_record_id', 'population_scope']).to_pydict()
    scope_map = dict(zip(scopes['source_record_id'], scopes['population_scope']))
    if any(scope_map.get(r['source_record_id']) == 'federal_city_region' for r in candidates):
        raise ValueError('federal territory aggregate entered locality partial-path diagnostic')

    agg = defaultdict(lambda: {'rows': 0, 'population': 0, 'quality': defaultdict(lambda: {'rows': 0, 'population': 0})})
    for r in candidates:
        y, p, q = r['census_year'], r['population'], r['population_value_quality']
        agg[y]['rows'] += 1
        agg[y]['population'] += p
        agg[y]['quality'][q]['rows'] += 1
        agg[y]['quality'][q]['population'] += p

    proof = OUT / 'exact_two_year_point_rows.csv.gz'
    fields = ['source_record_id', 'census_year', 'population', 'population_value_quality', 'observed_component_census_years']
    with gzip.open(proof, 'wt', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in sorted(candidates, key=lambda z: (z['census_year'], z['source_record_id'])))

    coverage = json.loads(GRAPH_COVERAGE.read_text(encoding='utf-8'))
    controls = {int(x['year']): int(x['official_control']) for x in coverage['census_metrics']}
    output = {
        'status': 'diagnostic_separate_axis_not_added_to_scope_aware_total',
        'definition': 'Selected locality row has an admitted point and belongs to an accepted identity component containing exactly two distinct observed census years among 2002, 2010, 2021.',
        'unobserved_third_year': 'unknown/no selected row; never imputed as zero or treated as outside-scope without a separate status',
        'component_year_masks': {'2002|2010': 3, '2002|2021': 5, '2010|2021': 6},
        'totals': {
            str(y): {
                'rows': agg[y]['rows'], 'population': agg[y]['population'],
                'official_control': controls[y],
                'official_control_share': agg[y]['population'] / controls[y],
                'population_quality': dict(agg[y]['quality']),
            } for y in sorted(agg)
        },
        'combined_with_scope_aware_total': False,
        'reason_not_combined': 'Source-ID overlap against all accepted scope-aware layers has not been reconciled; these records may already contribute through another supported representation.',
        'inputs_sha256': {str(p): sha(p) for p in (SELECTED, EDGES, POINTS, RESIDUAL, GRAPH_COVERAGE)},
        'point_ledger_row_level_check': 'exact target ID set, accepted point status, and exact latitude/longitude agreement',
        'edge_filter': list(EDGE_STATUSES),
        'point_filter': list(POINT_STATUSES),
        'script_sha256': sha(Path(__file__)),
        'row_proof': {'path': proof.name, 'rows': len(candidates), 'sha256': sha(proof)},
    }
    result = OUT / 'summary.json'
    result.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'rows': len(candidates), 'proof_bytes': proof.stat().st_size, 'summary': output['totals']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
