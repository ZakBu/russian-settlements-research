"""Readback of every unchanged row plus exact reviewed replacement witnesses."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def run(manifest_path, output_root):
    manifest_path = Path(manifest_path); output_root = Path(output_root)
    manifest = json.loads(manifest_path.read_text())
    old_path = Path(manifest['points']['path'])
    new_path = output_root / 'accepted_point_uses.parquet'
    predecessor_path = output_root / 'superseded_point_uses.parquet'
    application_path = output_root / 'receipt.json'
    application = json.loads(application_path.read_text())
    for p, digest in [(old_path, manifest['points']['sha256']),
                      (new_path, application['outputs'][new_path.name]),
                      (predecessor_path, application['outputs'][predecessor_path.name])]:
        assert sha(p) == digest
    approved_path = Path(manifest['approved']['path'])
    assert sha(approved_path) == manifest['approved']['sha256']
    approved = {r['historical_source_record_id']: r for r in csv.DictReader(approved_path.open())}
    wanted = pa.array(sorted(approved))
    old = pq.ParquetFile(old_path); new = pq.ParquetFile(new_path)
    old_fields = old.schema_arrow.names
    assert old.metadata.num_rows == new.metadata.num_rows
    unchanged, replaced, predecessors = 0, [], []
    for before, after in zip(old.iter_batches(batch_size=8192), new.iter_batches(batch_size=8192), strict=True):
        assert len(before) == len(after)
        assert before['target_source_record_id'].equals(after['target_source_record_id'])
        corrected = pc.is_in(before['target_source_record_id'], value_set=wanted)
        remaining = pc.invert(corrected)
        a = before.filter(remaining)
        b = after.select(old_fields).filter(remaining)
        assert a.equals(b), 'A row outside the independently reviewed target list changed'
        unchanged += len(a)
        predecessors.append(before.filter(corrected))
        replaced.extend(after.filter(corrected).to_pylist())
    expected_predecessors = pa.Table.from_batches(predecessors).sort_by([('target_source_record_id', 'ascending')])
    actual_predecessors = pq.read_table(predecessor_path).sort_by([('target_source_record_id', 'ascending')])
    assert expected_predecessors.equals(actual_predecessors)
    assert len(replaced) == len(approved) == application['superseded_targets']
    for row in replaced:
        witness = approved[row['target_source_record_id']]
        assert row['latitude'] == float(witness['proposed_latitude'])
        assert row['longitude'] == float(witness['proposed_longitude'])
        assert row['point_origin_sha256'] == witness['proposed_point_origin_sha256']
        assert row['point_origin_locator'] == witness['proposed_point_origin_locator']
        assert row['point_supersession_old_latitude'] == float(witness['old_latitude'])
        assert row['point_supersession_old_longitude'] == float(witness['old_longitude'])
        assert row['coordinate_provider_id'] is None
        assert row['direct_historical_coordinate_measurement'] is False
    path = output_root / 'root_independent_projection_readback.json'
    assert not path.exists()
    receipt = {'status': 'all_unmodified_point_rows_and_full_predecessors_verified',
               'unchanged_rows_all_original_fields': unchanged, 'replaced_rows': len(replaced),
               'full_predecessors_equal_previous_rows': True,
               'new_coordinates_and_origin_locators_match_review_exactly': True,
               'application_receipt_sha256': sha(application_path),
               'manifest_sha256': sha(manifest_path), 'script_sha256': sha(__file__)}
    path.write_text(json.dumps(receipt, indent=2) + '\n'); print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--manifest', required=True); parser.add_argument('--output-root', required=True)
    args = parser.parse_args(); run(args.manifest, args.output_root)
