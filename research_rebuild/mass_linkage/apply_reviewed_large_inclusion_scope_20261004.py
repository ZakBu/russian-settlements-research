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
    DEFAULT_FOLDER, _verify_pins, load_scoped_inclusion_references, _get_canonical,
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


def run_tula_proposal(manifest_path, output, points):
    """Root adoption of the four independently reviewed Tula source references."""
    output = Path(output)
    assert not output.exists(), 'Application outputs are immutable'
    manifest = json.loads(Path(manifest_path).read_text())
    assert manifest['status'] == 'candidate_only_prepared_not_applied'
    assert manifest['observation_references'] == manifest['new_scoped_point_uses'] == 4
    assert sha(SELECTED) == SELECTED_SHA
    for path, pin in manifest['source_hash_pins'].items():
        assert sha(path) == pin['sha256'], f'Review input changed: {path}'
    proposal = manifest['output_candidate_json']
    assert sha(proposal['path']) == proposal['sha256']
    references = json.loads(Path(proposal['path']).read_text())
    expected_ids = {f'2002:1_TOM_01_04.xls:0:{row}' for row in range(1948, 1952)}
    assert {r['source_record_id'] for r in references} == expected_ids and len(references) == 4
    parent = '2002:1_TOM_01_04.xls:0:1941'
    receiver = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:152364'
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'})
    rows = con.execute('select source_record_id,census_year,population,settlement_type,population_scope,is_additive_settlement_record from read_parquet(?) where source_record_id in(select unnest(?))',
                       [str(SELECTED), sorted(expected_ids | {parent, receiver})]).fetch_arrow_table().to_pylist()
    selected = {r['source_record_id']: dict(r, type_raw=r['settlement_type']) for r in rows}
    _get_canonical(selected, parent, '2002', '481216', 'город')
    _get_canonical(selected, receiver, '2021', '473622', 'город')
    current = con.execute('select latitude,longitude,coordinate_admission_status from read_parquet(?) where target_source_record_id=?',
                          [str(points), receiver]).fetchall()
    from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES
    assert len(current) == 1 and current[0][2] in ACCEPTED_COORDINATE_STATUSES
    for row in references:
        sid = row['source_record_id']
        _get_canonical(selected, sid, '2002', str(row['population']), 'пгт')
        assert row['year'] == 2002 and row['source_type'] == 'пгт'
        assert row['old_same_year_city_proper_source_record_id'] == parent
        assert row['current_2021_receiver_source_record_id'] == receiver
        assert row['current_receiver_population_context_only'] == 473622
        assert row['status'] == 'secondary_reported_inclusion_context_only'
        assert not any(row[key] for key in ['population_additive', 'ordinary_same_place_claim', 'current_child_population_asserted'])
        point = row['point_row']
        assert point['target_source_record_id'] == sid and point['target_year'] == 2002
        assert point['coordinate_admission_status'] == 'reviewed_case_accepted'
        assert not point['ordinary_coordinate_ledger_admission'] and point['measurement_date'] == 'unknown'
        assert sha(point['point_origin_file']) == point['point_origin_sha256']
        qid = point['historical_place_qid']
        entity = json.loads(Path(point['point_origin_file']).read_text())['entities'][qid]
        active = [c for c in entity['claims']['P625'] if c.get('rank') != 'deprecated']
        assert len(active) == 1 and active[0]['id'] == point['wikidata_point_claim_guid']
        coordinate = active[0]['mainsnak']['datavalue']['value']
        assert coordinate['globe'] == 'http://www.wikidata.org/entity/Q2'
        assert float(point['latitude']) == coordinate['latitude'] and float(point['longitude']) == coordinate['longitude']
        assert -90 <= coordinate['latitude'] <= 90 and -180 <= coordinate['longitude'] <= 180
        ep = row['evidence_pins']
        assert sha(ep['source_file']) == ep['source_sha256']
        assert ep['independent_review_receipt_sha256'] == '804f679f2bbd780eb58075f80b91be4e2836029af95a8fcb7fae4345cd31975c'
        assert not ep['legal_acts_independently_verified']
        if sid.endswith(':1949'):
            assert ep['point_adjudication']['supersedes_original_point_class_hold_for_this_scoped_use']
    assert sum(row['population'] for row in references) == 49342
    output.mkdir(parents=True)
    refpath = output / 'accepted_scoped_inclusion_references.json'
    pointpath = output / 'accepted_scoped_point_uses.json'
    refpath.write_text(json.dumps(references, ensure_ascii=False, indent=2) + '\n')
    pointpath.write_text(json.dumps([r['point_row'] for r in references], ensure_ascii=False, indent=2) + '\n')
    receipt = dict(status='applied_reviewed_secondary_reported_large_inclusion_references',
                   observation_references=4, new_scoped_point_uses=4,
                   existing_canonical_points_referenced=0, ordinary_NP3_admission=False,
                   current_child_population_asserted=False, parent_population_transfer=False,
                   modern_boundary_harmonized=False, boundary_comparability='unknown',
                   legal_acts_independently_verified=False, source_population_values_modified=False,
                   outputs={p.name: sha(p) for p in [refpath, pointpath]},
                   inputs={str(SELECTED): SELECTED_SHA, str(points): sha(points),
                           str(manifest_path): sha(manifest_path)},
                   frozen_review_pins=manifest['source_hash_pins'], script_sha256=sha(__file__))
    (output / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'observation_references': 4, 'old2002_population_referenced_once': 49342}))


def run_reviewed_standalone_cities(folder, output, points):
    """Adopt source-checked independent old cities, retaining their own points."""
    folder, output, points = map(Path, (folder, output, points))
    assert not output.exists()
    reviewpath = folder/'review_receipt.json'
    review = json.loads(reviewpath.read_text())
    refs = json.loads((folder/'accepted_scoped_inclusion_references.json').read_text())
    assert len(refs) == 4 and len({r['source_record_id'] for r in refs}) == 4
    for sourcepath, pin in review['input_pins'].items():
        assert sha(sourcepath) == pin['sha256']
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '256MB'})
    ids = sorted({r['source_record_id'] for r in refs} | {r['current_2021_receiver_source_record_id'] for r in refs})
    selected = {r['source_record_id']: r for r in con.execute('select source_record_id,census_year,population,settlement_type,population_scope,is_additive_settlement_record from read_parquet(?) where source_record_id in(select unnest(?))', [str(SELECTED),ids]).fetch_arrow_table().to_pylist()}
    ledger = {r['target_source_record_id']: r for r in con.execute('select target_source_record_id,latitude,longitude,coordinate_admission_status from read_parquet(?) where target_source_record_id in(select unnest(?))', [str(points),ids]).fetch_arrow_table().to_pylist()}
    from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES
    for r in refs:
        sid = r['source_record_id']; receiver = r['current_2021_receiver_source_record_id']
        _get_canonical(selected, sid, str(r['year']), str(r['population']), 'город')
        assert r['historical_place_qid'] in {'Q153684','Q198759'}
        assert int(r['year']) in {2002,2010} and r['source_type'] == 'город'
        assert r['old_same_year_city_proper_source_record_id'] is None
        assert selected[receiver]['census_year'] == 2021 and selected[receiver]['settlement_type'] == 'город'
        assert selected[receiver]['population_scope'] == 'settlement' and selected[receiver]['is_additive_settlement_record']
        assert ledger[receiver]['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES
        point = r['point_row']; actual = ledger[sid]
        assert actual['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES
        assert (point['latitude'],point['longitude']) == (actual['latitude'],actual['longitude'])
        assert point['target_source_record_id'] == sid
        origin = r['point_origin_reference']; assert sha(origin['file']) == origin['sha256']
        entity = json.loads(Path(origin['file']).read_text())['entities'][r['historical_place_qid']]
        claims = [c for c in entity['claims']['P625'] if c['id'] == origin['claim_guid'] and c.get('rank') != 'deprecated']
        assert len(claims) == 1
        v = claims[0]['mainsnak']['datavalue']['value']
        assert v['globe'] == 'http://www.wikidata.org/entity/Q2' and (v['latitude'],v['longitude']) == (point['latitude'],point['longitude'])
        assert r['old_same_place_counterpart_source_record_id'] in selected
        assert r['old_existing_same_place_edge']
        assert not r['inclusion_reference']['legal_act_independently_verified']
        assert not any(r[k] for k in ('population_additive','ordinary_same_place_claim','current_child_population_asserted'))
        r['status'] = 'secondary_reported_inclusion_context_only'
        r['standalone_historical_city_reference'] = True
        r['current_receiver_population_context_only'] = int(selected[receiver]['population'])
    output.mkdir(parents=True)
    path = output/'accepted_scoped_inclusion_references.json'; pointpath = output/'accepted_scoped_point_uses.json'
    path.write_text(json.dumps(refs,ensure_ascii=False,indent=2)+'\n'); pointpath.write_text(json.dumps([],indent=2)+'\n')
    receipt = dict(status='applied_reviewed_secondary_reported_large_inclusion_references', observation_references=4,new_scoped_point_uses=0,existing_canonical_points_referenced=4,ordinary_NP3_admission=False,parent_population_transfer=False,modern_boundary_harmonized=False,legal_acts_independently_verified=False,source_population_values_modified=False,inputs={str(SELECTED):sha(SELECTED),str(points):sha(points),str(reviewpath):sha(reviewpath),str(folder/'accepted_scoped_inclusion_references.json'):sha(folder/'accepted_scoped_inclusion_references.json')},outputs={x.name:sha(x) for x in (path,pointpath)},script_sha256=sha(__file__))
    (output/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


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
    parser.add_argument('--tula-proposal-manifest')
    args = parser.parse_args()
    if args.tula_proposal_manifest:
        run_tula_proposal(Path(args.tula_proposal_manifest), args.output, Path(args.points))
    else:
        run(args.output, Path(args.points))
