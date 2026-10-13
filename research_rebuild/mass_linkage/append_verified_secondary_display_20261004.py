"""Append preserved raw statements for reviewed current bindings, display only."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import duckdb
import pyarrow.parquet as pq


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def run(manifest_path, output):
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    paths = {}
    for label, pin in manifest.items():
        path = Path(pin['path']); assert sha(path) == pin['sha256'], path
        paths[label] = path
    approved = {(r['wikidata_qid'], r['to_2021_source_record_id'])
                for r in csv.DictReader(paths['current_bindings'].open())}
    rows = pq.read_table(paths['append']).to_pylist()
    batches = {}
    for row in rows:
        assert (row['wikidata_id'], row['current_place_source_record_id']) in approved
        assert row['historical_identity_admitted'] is False
        assert row['historical_coordinate_asserted'] is False
        assert row['quantitative_year_eligible'] is False
        assert row['latitude'] is None and row['longitude'] is None and row['reference_date'] is None
        path = Path(row['entity_batch_file'])
        if path not in batches:
            assert sha(path) == row['entity_batch_sha256']
            batches[path] = json.loads(path.read_text())['entities']
        raw = batches[path][row['wikidata_id']]
        claims = [c for c in raw['claims']['P1082'] if c['id'] == row['wikidata_statement_id']]
        assert len(claims) == 1
        assert claims[0] == json.loads(row['raw_statement_json'])
        assert int(row['observation_year']) == int(row['secondary_raw_observed_year'])
        assert float(row['population_value']) == float(claims[0]['mainsnak']['datavalue']['value']['amount'])
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '1GB'})
    con.read_parquet(str(paths['base'])).create_view('base')
    con.read_parquet(str(paths['append'])).create_view('addition')
    assert con.execute('select count(*) from base join addition using(observation_id)').fetchone()[0] == 0
    assert con.execute('select count(*) from base b join addition a on b.wikidata_statement_id=a.wikidata_statement_id').fetchone()[0] == 0
    target = output / 'reviewed_secondary_history_observations.parquet'
    con.execute('copy (select * from base union all by name select * from addition) to ? '
                '(format parquet, compression zstd)', [str(target)])
    con.read_parquet(str(target)).create_view('result')
    base_count = con.execute('select count(*) from base').fetchone()[0]
    result_count = con.execute('select count(*) from result').fetchone()[0]
    assert result_count == base_count + len(rows)
    columns = pq.read_schema(paths['base']).names
    difference = ' or '.join(f'b."{c}" is distinct from r."{c}"' for c in columns)
    changed = con.execute('select count(*) from base b left join result r using(observation_id) '
                          'where r.observation_id is null or ' + difference).fetchone()[0]
    assert changed == 0
    receipt = {'status': 'secondary_display_append_applied_no_historical_identity_or_census_admission',
               'manifest_path': str(manifest_path), 'manifest_sha256': sha(manifest_path),
               'script_sha256': sha(__file__), 'base_rows': base_count,
               'new_raw_GUID_statements': len(rows), 'result_rows': result_count,
               'current_source_QID_bindings': len({(r['wikidata_id'], r['current_place_source_record_id']) for r in rows}),
               'all_existing_columns_preserved_by_null_safe_readback': columns,
               'historical_coordinates_asserted': False, 'primary_population_modified': False,
               'snapshot_GUID_conflicts_inserted': False,
               'outputs': {target.name: sha(target)}}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'all_existing_columns_preserved_by_null_safe_readback'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--manifest', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); run(args.manifest, args.output)
