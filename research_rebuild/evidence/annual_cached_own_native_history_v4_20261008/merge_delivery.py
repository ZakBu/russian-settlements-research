"""Join frozen additional-year claims to actual exported native triplet UIDs.

No census-value replacement or population-coverage credit is performed.
"""
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
E = ROOT / 'research_rebuild/evidence'
D = Path('/workspace/settlements-delivery/working-full-chain-20261007')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    native_export = D / 'ordinary_full3_all_own_points_complete_numbers.csv.gz'
    current_to_uid = {}
    with gzip.open(native_export, 'rt') as stream:
        for row in csv.DictReader(stream):
            key = row['source_record_id_2021']
            assert key not in current_to_uid
            current_to_uid[key] = row['entity_uid']
    receipts = [E / 'annual_cached_own_native_history_20261008/receipt.json',
                E / 'annual_cached_own_native_history_v4_20261008/receipt.json']
    observations, bindings, input_pins = [], {}, {}
    for receipt_path in receipts:
        receipt = json.loads(receipt_path.read_text())
        input_pins[str(receipt_path)] = sha(receipt_path)
        for filename, pin in receipt['outputs'].items():
            path = Path(filename)
            assert sha(path) == pin['sha256'] and path.stat().st_size == pin['bytes']
            input_pins[filename] = pin['sha256']
            with gzip.open(path, 'rt') as stream:
                rows = list(csv.DictReader(stream))
            if path.name == 'observations.csv.gz':
                observations.extend(rows)
            else:
                for row in rows:
                    assert row['wikidata_qid'] not in bindings
                    row['entity_uid'] = current_to_uid[row['current_source_record_id']]
                    bindings[row['wikidata_qid']] = row
    assert len({row['source_uid'] for row in observations}) == len(observations) == 10952
    assert len(bindings) == 3195
    for row in observations:
        assert int(row['observed_year']) not in (2002, 2010, 2021)
        binding = bindings[row['wikidata_qid']]
        row['entity_uid'] = binding['entity_uid']
        for field in ['current_source_record_id', 'current_name', 'current_type',
                      'current_region', 'current_native_oktmo', 'current_latitude', 'current_longitude']:
            row[field] = binding[field]
    files = {}
    for name, rows in [('other_dated_population_observations.csv.gz', observations),
                       ('other_dated_population_current_bindings.csv.gz', list(bindings.values()))]:
        path = D / name
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with gzip.open(path, 'wt', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        files[name] = {'sha256': sha(path), 'bytes': path.stat().st_size, 'rows': len(rows)}
    grouped = defaultdict(list)
    for row in observations:
        grouped[int(row['observed_year'])].append(row)
    summary = []
    for year, rows in sorted(grouped.items()):
        per_uid = defaultdict(set)
        for row in rows:
            per_uid[row['entity_uid']].add(int(row['population_value']))
        single = {key: next(iter(values)) for key, values in per_uid.items() if len(values) == 1}
        summary.append({'year': year, 'literal_observations': len(rows),
                        'entities_with_observation': len(per_uid),
                        'entities_with_one_population_value_in_year': len(single),
                        'entities_with_conflicting_values_in_year': len(per_uid) - len(single),
                        'partial_descriptive_population_sum': sum(single.values()),
                        'national_coverage_claim': False})
    path = D / 'other_dated_population_year_summary.csv'
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader(); writer.writerows(summary)
    files[path.name] = {'sha256': sha(path), 'bytes': path.stat().st_size, 'rows': len(summary)}
    receipt = {'status': 'frozen_secondary_claims_joined_to_actual_exported_native_triplet_UIDs',
               'native_export_sha256': sha(native_export), 'input_pins': input_pins,
               'observations': len(observations), 'entities': len(bindings), 'observed_years': len(grouped),
               'no_census_population_or_coverage_changes': True,
               'historical_coordinates_are_continuity_inferences': True,
               'primary_source_verification': 'not_established',
               'boundary_comparability': 'UNKNOWN', 'outputs': files}
    (D / 'other_dated_population_delivery_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: receipt[key] for key in ['status', 'observations', 'entities', 'observed_years']}))


if __name__ == '__main__':
    main()
