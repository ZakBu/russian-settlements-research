"""Replace only reviewed point assertions, preserving predecessor rows in full.

This is a coordinate correction projection, never an identity or population edit.
Wide accepted rows are streamed to avoid materializing the whole proof ledger.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
from collections import defaultdict, deque
import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def pinned(spec):
    path = Path(spec['path'])
    assert sha(path) == spec['sha256'], path
    return path


def reviewed_replacement(old, carrier, approved, review_sha, point_sha, path_ids):
    assert old['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES
    assert carrier['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES
    assert float(old['latitude']) == float(approved['old_latitude'])
    assert float(old['longitude']) == float(approved['old_longitude'])
    assert old['point_origin_sha256'] == approved['old_point_source_sha256']
    assert float(carrier['latitude']) == float(approved['proposed_latitude'])
    assert float(carrier['longitude']) == float(approved['proposed_longitude'])
    assert carrier['point_origin_sha256'] == approved['proposed_point_origin_sha256']
    assert carrier['point_origin_locator'] == approved['proposed_point_origin_locator']
    assert int(approved['year']) in {2002, 2010}
    assert approved['identity_and_population_unchanged'] == 'True'
    assert approved['proposed_point_is_retrospective_current_representative'] == 'True'
    assert path_ids, 'A reviewed current carrier must be connected by actual accepted edges'
    # Carry coordinate-source evidence. Historical source names/codes stay on the
    # target row; the entire previous row is preserved separately as a predecessor.
    fields = ['latitude', 'longitude', 'coordinate_source', 'coordinate_source_record_id',
              'coordinate_provider', 'coordinate_provider_family', 'point_origin_file',
              'point_origin_sha256', 'point_origin_locator', 'point_origin_kind',
              'point_claim_artifact_file', 'point_claim_artifact_sha256',
              'coordinate_source_file', 'coordinate_source_sha256', 'coordinate_source_locator',
              'coordinate_source_origin', 'coordinate_source_input_artifact_sha256',
              'coordinate_source_date', 'coordinate_source_latitude_raw', 'coordinate_source_longitude_raw']
    changes = {field: carrier.get(field) for field in fields if field in old}
    changes.update({
        'coordinate_quality': 'automatically_accepted_checked_rule',
        'coordinate_admission_status': 'reviewed_extension_rule_accepted',
        'coordinate_application_family': 'R_reviewed_same_place_sourced_point_continuity_20261004',
        'admission_rule': 'reviewed_point_supersession_distinct_current_point_and_single_coded_P625',
        'application_inference_kind': 'modern_representative_point_retrospective_continuity_inference',
        'coordinate_measurement_date_unknown': True,
        'direct_historical_coordinate_measurement': False,
        'boundary_comparability_asserted': False,
        'population_scope_comparability_asserted': False,
        'coordinate_provider_id': None,
        'provider_binding_status': 'historical_target_external_identifier_binding_not_asserted',
        'provider_fias_binding_status': 'historical_target_external_identifier_binding_not_asserted',
        'native_id_binding_asserted': False,
        'fias_identifier_binding_claimed': False,
        'provider_id_binding_asserted': False,
        'provider_identifier_binding_asserted': False,
        'modern_provider_binding_claimed': False,
        'inference_modern_point_use_target_source_record_id': carrier['target_source_record_id'],
        'inference_identity_path_decision_ids_json': json.dumps(path_ids),
        'inference_identity_path_from_source_record_id': old['target_source_record_id'],
        'inference_identity_path_to_source_record_id': carrier['target_source_record_id'],
        'inference_identity_path_edge_count': len(path_ids),
        'coordinate_application_review_sha256': review_sha,
        'coordinate_provenance': json.dumps({'kind': 'reviewed_point_supersession',
            'review_sha256': review_sha, 'carrier_target': carrier['target_source_record_id'],
            'accepted_identity_path_decision_ids': path_ids,
            'predecessor_point_ledger_sha256': point_sha,
            'predecessor_rows_artifact': 'superseded_point_uses.parquet',
            'historical_measurement_asserted': False}),
        'candidate_only': False,
        'point_supersession_kind': 'incorrect_raw_GeoKLADR_point_superseded_under_reviewed_rule',
        'point_supersession_review_sha256': review_sha,
        'point_supersession_predecessor_ledger_sha256': point_sha,
        'point_supersession_old_latitude': float(old['latitude']),
        'point_supersession_old_longitude': float(old['longitude']),
        'point_supersession_old_origin_sha256': old['point_origin_sha256'],
        'point_supersession_old_origin_locator': old['point_origin_locator'],
        'point_supersession_carrier_provider_id': None if carrier.get('coordinate_provider_id') is None else str(carrier['coordinate_provider_id']),
    })
    return changes


def run(manifest_path, output):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    graph = pinned(manifest['graph'])
    points = pinned(manifest['points'])
    approved_path = pinned(manifest['approved'])
    review_path = pinned(manifest['review'])
    review = json.loads(review_path.read_text())
    assert manifest['approved']['sha256'] in json.dumps(review), 'Review must pin exact eligible list'
    assert review['accepted_graph_sha256'] == manifest['graph']['sha256']
    assert review['accepted_point_sha256'] == manifest['points']['sha256']
    approved = list(csv.DictReader(approved_path.open()))
    assert len(approved) == review['eligible_coordinate_corrections']
    target_ids = [r['historical_source_record_id'] for r in approved]
    assert len(set(target_ids)) == len(target_ids)
    ids = set(target_ids) | {r['current_source_record_id'] for r in approved}
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '2GB'})
    con.read_parquet(str(points)).create_view('points')
    con.register('wanted', pa.table({'sid': sorted(ids)}))
    small = con.execute('select p.* from points p join wanted w on p.target_source_record_id=w.sid').fetch_arrow_table()
    records = {r['target_source_record_id']: r for r in small.to_pylist()}
    assert set(records) == ids
    adjacency = defaultdict(list)
    endpoint_years = {}
    con.read_parquet(str(graph)).create_view('graph')
    for a, b, decision, ay, by in con.execute('select from_source_record_id,to_source_record_id,decision_id,from_year,to_year from graph').fetchall():
        for sid, year in [(a, int(ay)), (b, int(by))]:
            assert endpoint_years.get(sid, year) == year
            endpoint_years[sid] = year
        adjacency[a].append((b, decision)); adjacency[b].append((a, decision))
    updates = {}
    origin_pins = {}
    for row in approved:
        target, current = row['historical_source_record_id'], row['current_source_record_id']
        # Reviewed primary rows use ROSSTAT2010/ARK2010 namespaces as well as
        # 2010: prefixes; years come from their accepted source-bound endpoints.
        assert endpoint_years[current] == 2021 and endpoint_years[target] == int(row['year'])
        queue, parents = deque([target]), {target: None}
        while queue and current not in parents:
            node = queue.popleft()
            for other, decision in adjacency[node]:
                if other not in parents:
                    parents[other] = (node, decision); queue.append(other)
        assert current in parents, (target, current)
        path_ids, node = [], current
        while node != target:
            node, decision = parents[node]; path_ids.append(decision)
        path_ids.reverse()
        updates[target] = reviewed_replacement(records[target], records[current], row,
                         manifest['review']['sha256'], manifest['points']['sha256'], path_ids)
        for key in ['old_point_source', 'proposed_point_origin']:
            path, digest = row[key + '_file'], row[key + '_sha256']
            assert origin_pins.get(path, digest) == digest
            origin_pins[path] = digest
    for path, digest in origin_pins.items():
        assert sha(path) == digest, path
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    # Complete predecessors, including arbitrary optional proof columns.
    predecessors = small.filter(pc.is_in(small['target_source_record_id'], value_set=pa.array(target_ids)))
    old_path = output / 'superseded_point_uses.parquet'
    pq.write_table(predecessors, old_path, compression='zstd')
    source = pq.ParquetFile(points)
    additions = [('point_supersession_kind', pa.string()), ('point_supersession_review_sha256', pa.string()),
                 ('point_supersession_predecessor_ledger_sha256', pa.string()),
                 ('point_supersession_old_latitude', pa.float64()), ('point_supersession_old_longitude', pa.float64()),
                 ('point_supersession_old_origin_sha256', pa.string()), ('point_supersession_old_origin_locator', pa.string()),
                 ('point_supersession_carrier_provider_id', pa.string())]
    schema = source.schema_arrow
    for name, datatype in additions:
        assert name not in schema.names, 'Do not supersede already corrected rows silently'
        schema = schema.append(pa.field(name, datatype))
    result_path = output / 'accepted_point_uses.parquet'
    changed, count = 0, 0
    with pq.ParquetWriter(result_path, schema, compression='zstd') as writer:
        for batch in source.iter_batches(batch_size=8192):
            batch_ids = batch.column(batch.schema.get_field_index('target_source_record_id')).to_pylist()
            affected = {i: updates[sid] for i, sid in enumerate(batch_ids) if sid in updates}
            arrays = list(batch.columns)
            for index, field in enumerate(batch.schema):
                if affected and any(field.name in delta for delta in affected.values()):
                    values = arrays[index].to_pylist()
                    for row_index, delta in affected.items():
                        if field.name in delta:
                            value = delta[field.name]
                            if value is not None and pa.types.is_string(field.type): value = str(value)
                            values[row_index] = value
                    arrays[index] = pa.array(values, type=field.type)
            for name, datatype in additions:
                values = [None] * len(batch)
                for row_index, delta in affected.items(): values[row_index] = delta[name]
                arrays.append(pa.array(values, type=datatype))
            corrected = pa.RecordBatch.from_arrays(arrays, schema=schema)
            corrected.validate(full=True)
            writer.write_batch(corrected)
            changed += len(affected); count += len(batch)
    assert changed == len(approved) and count == source.metadata.num_rows
    result = {'status': 'reviewed_coordinate_supersessions_applied_no_identity_population_edits',
              'manifest_sha256': sha(manifest_path), 'script_sha256': sha(__file__),
              'superseded_targets': changed, 'accepted_point_rows': count,
              'complete_predecessor_rows_retained': predecessors.num_rows,
              'identity_graph_changed': False, 'population_values_changed': False,
              'coordinate_count_coverage_changed': False, 'retrospective_continuity_inference': True,
              'historic_external_provider_id_binding_asserted': False,
              'origin_file_pins': origin_pins,
              'outputs': {p.name: sha(p) for p in [result_path, old_path]}}
    (output / 'receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.manifest, args.output)
