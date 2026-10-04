"""Pin reviewed identity lists, retain confirmations, and reject combined year collisions.

This prepares an application manifest. It does not admit edges or point uses.
Packets must be explicit hash-pinned independent eligible lists and receipts.
"""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def pinned(spec):
    path = Path(spec['path'])
    if sha(path) != spec['sha256']:
        raise ValueError(f'Input hash differs: {path}')
    return path


def pin(path):
    return {'path': str(path), 'sha256': sha(path)}


def write_csv(path, rows):
    fields = ['from_source_record_id', 'to_source_record_id', 'from_year',
              'to_year', 'relation', 'family', 'review_status',
              'raw_independent_eligible_list_sha256', 'raw_eligible_row_json']
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(specification, output):
    # A reviewed bounded block can exceed the stdlib's 128 KiB default.
    # Preserve the original proof fields with an explicit finite upper bound.
    csv.field_size_limit(100_000_000)
    specification = Path(specification)
    spec = json.loads(specification.read_text())
    template = json.loads(pinned(spec['template']).read_text())
    config = json.loads(pinned(spec['config']).read_text())
    graph = Path(config['working_identity_graph'])
    points = Path(config['working_point_uses'])
    assert sha(graph) == config['working_identity_graph_sha256']
    assert sha(points) == config['working_point_uses_sha256']
    selected = pinned(template['frozen']['selected'])
    con = duckdb.connect(config={'threads': 1, 'memory_limit': '512MB'})
    con.read_parquet(str(selected)).create_view('selected')
    years = dict(con.execute('select source_record_id,census_year from selected').fetchall())
    parent = {sid: sid for sid in years}
    masks = {sid: {2002: 1, 2010: 2, 2021: 4}[int(year)] for sid, year in years.items()}

    def find(sid):
        while parent[sid] != sid:
            parent[sid] = parent[parent[sid]]
            sid = parent[sid]
        return sid

    def merge(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        if masks[ra] & masks[rb]:
            raise ValueError(f'Combined reviewed inputs compete for a census year: {a} / {b}')
        parent[rb] = ra
        masks[ra] |= masks.pop(rb)
        return True

    con.read_parquet(str(graph)).create_view('graph')
    for a, b in con.execute('select from_source_record_id,to_source_record_id from graph').fetchall():
        merge(a, b)
    output = Path(output)
    if output.exists():
        raise ValueError('Prepared batch must use a new immutable directory')
    prepared, confirmations, records = [], [], []
    # Complete all combined topology checks before creating output files.
    for packet in spec['packets']:
        original = pinned(packet['eligible'])
        review = pinned(packet['review_receipt'])
        rows, repeated = [], []
        with original.open() as handle:
            for raw in csv.DictReader(handle):
                status_column = packet.get('status_column')
                if status_column and raw[status_column] not in packet['eligible_statuses']:
                    raise ValueError(f'Noneligible row in independent list: {original}')
                a, b = raw[packet.get('from_column', 'from_source_record_id')], raw[packet.get('to_column', 'to_source_record_id')]
                if a not in years or b not in years or int(years[a]) == int(years[b]):
                    raise ValueError('Reviewed endpoints must be actual selected records of different censuses')
                for field, sid in [('from_year', a), ('to_year', b)]:
                    if raw.get(field) and int(float(raw[field])) != int(years[sid]):
                        raise ValueError(f'Reviewed year conflicts with actual selected endpoint: {sid}')
                relation = raw.get('relation', 'same_place')
                if relation not in {'same_place', 'same_place_candidate'}:
                    raise ValueError(f'Not an ordinary same-place reviewed relation: {relation}')
                family = raw[packet['family_column']] if packet.get('family_column') else packet['family']
                row = {'from_source_record_id': a, 'to_source_record_id': b,
                       'from_year': int(years[a]), 'to_year': int(years[b]),
                       'relation': relation, 'family': family, 'review_status': 'eligible',
                       'raw_independent_eligible_list_sha256': packet['eligible']['sha256'],
                       'raw_eligible_row_json': json.dumps(raw, ensure_ascii=False, sort_keys=True)}
                (rows if merge(a, b) else repeated).append(row)
        prepared.append((packet, rows))
        confirmations.extend(repeated)
        records.append({'name': packet['name'], 'original_eligible': pin(original),
                        'review_receipt': pin(review), 'new_component_merges': len(rows),
                        'already_connected_confirmations': len(repeated)})
    output.mkdir(parents=True)
    manifest = {k: v for k, v in template.items() if k not in {'identity_sources', 'point_sources', 'base', 'reviewed_at_utc'}}
    manifest.update(base={'graph': pin(graph), 'points': pin(points)}, identity_sources=[], point_sources=[],
                    reviewed_at_utc=datetime.now(timezone.utc).isoformat())
    for packet, rows in prepared:
        path = output / (packet['name'] + '_new_identity_adapter.csv')
        write_csv(path, rows)
        manifest['identity_sources'].append({
            'candidate': pin(path), 'eligible': pin(path), 'review_receipt': packet['review_receipt'],
            'candidate_columns': {'from': 'from_source_record_id', 'to': 'to_source_record_id', 'family': 'family', 'status': 'review_status'},
            'eligible_columns': {'from': 'from_source_record_id', 'to': 'to_source_record_id', 'family': 'family'},
            'accepted_candidate_statuses': ['eligible'], 'canonical_columns': {'relation': 'relation'},
            'additional_review_receipts': packet.get('additional_review_receipts', []),
        })
    write_csv(output / 'prior_or_transitive_pair_confirmations.csv', confirmations)
    path = output / 'application_manifest.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    result = {'status': 'prepared_only_from_pinned_independent_eligible_lists_no_admissions',
              'specification': pin(specification), 'config': spec['config'], 'packets': records,
              'combined_year_collision_check': 'passed; no greedy rejection of competing approved rows',
              'raw_eligible_rows_preserved_in_adapter_json': True,
              'point_sources_added': 0, 'script_sha256': sha(__file__),
              'outputs': {p.name: sha(p) for p in output.iterdir() if p.is_file()}}
    (output / 'preparation_receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'prepared_new_component_merges': sum(len(rows) for _, rows in prepared),
                      'confirmations': len(confirmations), 'manifest': str(path)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--specification', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.specification, args.output)
