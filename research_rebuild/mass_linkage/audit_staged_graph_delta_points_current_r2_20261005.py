#!/usr/bin/env python3
"""Check whether staged point-propagation targets still add anything to Graph22/R2."""
from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from collections import defaultdict
from pathlib import Path

import duckdb

from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF, km

W = Path('/workspace')
STAGED = W / 'settlements-work/coordinates/graph_delta_propagation_v1/staged_point_uses.parquet'
SELECTED = W / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EDGES = W / 'settlements-work/continuation_20261004/accepted_graph22_krasnodar_20261005/accepted_identity_edges.parquet'
POINTS = W / 'settlements-work/continuation_20261004/accepted_graph22_krasnodar_20261005/accepted_point_uses.parquet'
OUT = W / 'russian-settlements-research/research_rebuild/evidence/mass_joint_20261004/graph21_komarovsky_graph22_krasnodar/staged_point_route_r2_recheck'
EDGE_STATUSES = [
    'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
    'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def norm(value: object) -> str:
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().replace('ё', 'е').split())


def locality_type(value: object) -> str:
    x = norm(value).replace('.', '')
    return {
        'рабочий поселок': 'пгт', 'рабочий посёлок': 'пгт',
        'поселок городского типа': 'пгт', 'посёлок городского типа': 'пгт',
    }.get(x, x)


def region(value: object) -> str:
    return norm(value).replace('область', '').replace('край', '').replace('республика', '').strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '512MB'})
    obs = con.execute(
        'select source_record_id,census_year,settlement_name,settlement_type,region_norm,population,population_value_quality '
        'from read_parquet(?)', [str(SELECTED)]
    ).fetchall()
    by_id = {str(r[0]): r for r in obs}
    uf = YearUF([str(r[0]) for r in obs], [int(r[1]) for r in obs])
    for a, b in con.execute(
        'select from_source_record_id,to_source_record_id from read_parquet(?) '
        'where decision_status in (select unnest(?))', [str(EDGES), EDGE_STATUSES]
    ).fetchall():
        if uf.union_ids(a, b) == 'year_constrained_collision':
            raise ValueError('accepted graph has same-year component collision')

    point_rows = con.execute(
        'select target_source_record_id,latitude,longitude from read_parquet(?) '
        'where coordinate_admission_status in (\'reviewed_rule_accepted\',\'frozen_r5b_reviewed_baseline_preserved\',\'reviewed_extension_rule_accepted\',\'reviewed_case_accepted\')',
        [str(POINTS)]
    ).fetchall()
    point_map = {str(r[0]): (float(r[1]), float(r[2])) for r in point_rows}
    if len(point_map) != len(point_rows):
        raise ValueError('current accepted point ledger has duplicate targets')
    staged = con.execute('select * from read_parquet(?)', [str(STAGED)]).fetchdf()
    if staged.target_source_record_id.duplicated().any():
        raise ValueError('staged target IDs are not unique')
    existing = set(staged.target_source_record_id.astype(str)) & set(point_map)
    missing = staged[~staged.target_source_record_id.astype(str).isin(existing)]
    if len(staged) != 1087 or len(existing) != 1044 or len(missing) != 43:
        raise ValueError('staged/current-point row counts changed')

    by_key = defaultdict(list)
    for r in obs:
        by_key[(int(r[1]), norm(r[2]), locality_type(r[3]), region(r[4]))].append(r)
    rows = []
    for x in missing.to_dict('records'):
        old_id = str(x['target_source_record_id'])
        if old_id in by_id:
            raise ValueError(f'missing point target is still in current selected data: {old_id}')
        key = (int(x['target_year']), norm(x['source_name']), locality_type(x['source_type']), region(x['source_region']))
        matches = by_key[key]
        if len(matches) != 1:
            raise ValueError(f'current R2 replacement is not unique: {old_id}; matches={len(matches)}')
        m = matches[0]
        new_id = str(m[0])
        if new_id not in point_map:
            raise ValueError(f'current R2 replacement has no accepted point: {new_id}')
        lat, lon = point_map[new_id]
        distance = km(float(x['latitude']), float(x['longitude']), lat, lon)
        if distance > 0.000001:
            raise ValueError(f'current replacement point differs from staged point: {new_id}; km={distance}')
        mask = int(uf.mask[uf.find(uf.idx[new_id])])
        if mask != 7:
            raise ValueError(f'current replacement is not in a complete three-year component: {new_id}; mask={mask}')
        rows.append({
            'staged_old_source_record_id': old_id, 'current_r2_source_record_id': new_id,
            'census_year': int(m[1]), 'name': str(m[2]), 'type': str(m[3]),
            'region': str(m[4]), 'population': int(m[5]), 'population_value_quality': str(m[6]),
            'staged_latitude': float(x['latitude']), 'staged_longitude': float(x['longitude']),
            'current_accepted_latitude': lat, 'current_accepted_longitude': lon,
            'point_distance_km': distance, 'accepted_component_years': '2002|2010|2021',
        })
    if len({r['current_r2_source_record_id'] for r in rows}) != 43:
        raise ValueError('replacement endpoints are not one-to-one')
    proof = OUT / 'r2_replacements_already_pointed.csv'
    with proof.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r['current_r2_source_record_id']))
    summary = {
        'status': 'no_net_coordinate_or_joint_coverage_gain_from_replaying_staged_point_package',
        'staged_unique_targets': len(staged), 'staged_targets_already_in_current_point_ledger': len(existing),
        'staged_ids_absent_current_ledger_and_selection': len(rows),
        'one_to_one_current_r2_replacement_rows': len(rows),
        'replacement_rows_already_have_exact_same_accepted_coordinates': sum(r['point_distance_km'] == 0 for r in rows),
        'replacement_rows_in_accepted_full_three_census_components': len(rows),
        'replacement_population_sum': sum(r['population'] for r in rows),
        'inputs_sha256': {str(p): sha(p) for p in (STAGED, SELECTED, EDGES, POINTS)},
        'proof': {'file': proof.name, 'rows': len(rows), 'sha256': sha(proof)},
        'script_sha256': sha(Path(__file__)),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
