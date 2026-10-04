"""Adopt reviewed historical points and secondary inclusion references in a sidecar.

This does not alter the ordinary identity or coordinate ledgers. Existing primary
source rows are referenced once; current receiving-city values remain context.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import duckdb

from research_rebuild.mass_linkage.load_reviewed_inclusion_scope_20261004 import (
    DEFAULT_FOLDER, _verify_pins, load_scoped_inclusion_references,
)

C = Path('/workspace/settlements-work/continuation_20261004')
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
SELECTED_SHA = '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def run(output, points):
    output = Path(output)
    assert not output.exists(), 'Application outputs are immutable'
    assert sha(SELECTED) == SELECTED_SHA
    pins = _verify_pins(DEFAULT_FOLDER)
    build = json.loads((DEFAULT_FOLDER / 'build_receipt.json').read_text())
    for path, digest in build['inputs_sha256_before'].items():
        # The previous coordinate snapshot is an immutable provenance input;
        # current existing point references are checked separately below.
        assert sha(path) == digest, f'Reviewed input changed: {path}'
    observations = read_csv(DEFAULT_FOLDER / 'scoped_inclusion_observations.csv')
    zfolder = DEFAULT_FOLDER / 'zheleznodorozhny_secondary_context_supplement'
    zobservations = read_csv(zfolder / 'zheleznodorozhny_observations.csv')
    hooks = read_csv(DEFAULT_FOLDER / 'old_source_union_hooks.csv')
    receivers = read_csv(DEFAULT_FOLDER / 'current_receiver_contexts.csv')
    zhooks = read_csv(zfolder / 'zheleznodorozhny_old_city_proper_union_hooks.csv')
    ids = {r['source_record_id'] for r in observations + zobservations + receivers}
    ids.update(r['old_parent_city_proper_source_record_id'] for r in observations)
    ids.update(r['old_city_proper_parent_source_record_id'] for r in zhooks)
    ids.update(r['receiver_source_record_id'] for r in zobservations)
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'})
    selected = con.execute('select * from read_parquet(?) where source_record_id in(select unnest(?))',
                           [str(SELECTED), sorted(ids)]).fetch_arrow_table().to_pylist()
    by_id = {}
    for row in selected:
        row['type_raw'] = row['settlement_type']
        by_id[row['source_record_id']] = row
    assert set(by_id) == ids, 'Some selected source hooks are missing'
    zids = sorted(r['source_record_id'] for r in zobservations)
    existing = con.execute('select target_source_record_id,target_year,latitude,longitude,coordinate_admission_status,coordinate_source,coordinate_source_sha256,coordinate_source_locator from read_parquet(?) where target_source_record_id in(select unnest(?))',
                           [str(points), zids]).fetch_arrow_table().to_pylist()
    assert {r['target_source_record_id'] for r in existing} == set(zids)
    point_by_id = {r['target_source_record_id']: r for r in existing}
    new_points = []
    raw_points = {r['point_use_id']: r for r in read_csv(DEFAULT_FOLDER / 'scoped_point_uses.csv')}
    for row in observations:
        point = dict(raw_points[row['point_use_id']])
        assert point['point_use_status'] == 'approved_scoped_retrospective_context_only'
        assert row['source_record_id'] in json.loads(point['historical_source_record_ids_json'])
        point.update(target_source_record_id=row['source_record_id'],
                     target_year=int(row['source_year']),
                     coordinate_admission_status='reviewed_case_accepted',
                     admission_scope='secondary_reported_historical_inclusion_sidecar_only',
                     ordinary_coordinate_ledger_admission=False)
        # Root adopts the independently reviewed, origin-replayed point here.
        # The loader verifies literal raw GeoNames coordinates and source hooks.
        point_by_id[row['source_record_id']] = point
        new_points.append(point)
    references = load_scoped_inclusion_references(
        DEFAULT_FOLDER, by_id, point_by_id, include_zheleznodorozhny=True)
    assert len(references) == 9 and len(new_points) == 7
    assert len({r['source_record_id'] for r in references}) == 9
    output.mkdir(parents=True)
    refpath = output / 'accepted_scoped_inclusion_references.json'
    pointpath = output / 'accepted_scoped_point_uses.json'
    refpath.write_text(json.dumps(references, ensure_ascii=False, indent=2) + '\n')
    pointpath.write_text(json.dumps(new_points, ensure_ascii=False, indent=2) + '\n')
    receipt = dict(status='applied_reviewed_secondary_reported_large_inclusion_references',
                   observation_references=9, new_scoped_point_uses=7,
                   existing_canonical_points_referenced=2, ordinary_NP3_admission=False,
                   current_child_population_asserted=False, parent_population_transfer=False,
                   modern_boundary_harmonized=False, boundary_comparability='unknown',
                   legal_acts_independently_verified=False, source_population_values_modified=False,
                   outputs={p.name: sha(p) for p in [refpath, pointpath]},
                   inputs={str(SELECTED): SELECTED_SHA, str(points): sha(points),
                           str(DEFAULT_FOLDER / 'handoff_receipt.json'): sha(DEFAULT_FOLDER / 'handoff_receipt.json')},
                   frozen_handoff_pins=pins, script_sha256=sha(__file__))
    (output / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k not in {'outputs', 'inputs', 'frozen_handoff_pins'}}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--points', required=True)
    args = parser.parse_args()
    run(args.output, Path(args.points))
