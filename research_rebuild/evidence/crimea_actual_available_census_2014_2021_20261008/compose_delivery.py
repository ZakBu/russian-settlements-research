"""Apply frozen available-calendar deltas; never create Russian 2002/2010 observations."""
from pathlib import Path
import csv
import gzip
import hashlib
import json

HERE = Path(__file__).resolve().parent
E = HERE.parent
D = Path('/workspace/settlements-delivery/working-full-chain-20261007')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    with gzip.open(path, 'rt') as stream:
        return list(csv.DictReader(stream))


def write(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with gzip.open(path, 'wt', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return {'sha256': sha(path), 'bytes': path.stat().st_size, 'rows': len(rows)}


def main():
    extra = HERE / 'residual4_source_join'
    pins = {}
    for folder in [HERE, extra]:
        for filename, expected in json.loads((folder / 'source_pins.json').read_text()).items():
            expected = expected['sha256'] if isinstance(expected, dict) else expected
            if sha(filename) != expected:
                raise ValueError(f'Frozen source differs: {filename}')
            pins[filename] = expected
        for path in folder.glob('*'):
            if path.is_file() and path.name not in {'root_application_receipt.json', 'compose_delivery.py'}:
                pins[str(path)] = sha(path)
    observations = read(HERE / 'actually_available_census_observations.csv.gz')
    points = {row['target_source_record_id']: row for row in read(HERE / 'existing_accepted_point_references.csv.gz')}
    coverage = {row['source_record_id']: row for row in read(HERE / 'native_2021_available_calendar_coverage.csv.gz')}
    additions = read(extra / 'accepted_scoped_2014_observation_delta.csv.gz')
    delta_points = read(extra / 'accepted_available_calendar_point_use_delta.csv.gz')
    old_ids = {row['source_record_id'] for row in observations}
    for item in additions:
        sid, current = item['source_record_id'], item['current_2021_source_record_id']
        if sid in old_ids or current in coverage:
            raise ValueError('New primary observation or current credit already exists')
        shared = {'place_current_source_record_id': current, 'settlement_name': item['name_current_native'],
                  'grain': 'physical_settlement', 'Russian_2002_status': 'outside_scope',
                  'Russian_2010_status': 'outside_scope', 'strict_NP3_eligible': 'False',
                  'boundary_comparability': 'UNKNOWN',
                  'coordinate_basis': 'explicit_modern_own_representative_retrospective_continuity',
                  'point_reference_target_id': sid,
                  'existing_identity_review_status': 'root_accepted_source_bound_available_calendar_same_place'}
        observations.append(dict(shared, year='2014', source_record_id=sid,
             population=item['population'], population_raw=item['population_raw'],
             population_status='numeric_primary_archived_official', source_name_raw=item['source2014_caption_literal'],
             source_path=item['source_file'], source_sha256=item['source_sha256'],
             source_locator=item['source_locator'], native_code='', source_quality_original=item['population_quality']))
        observations.append(dict(shared, year='2021', source_record_id=current,
             population=item['current2021_population'], population_raw=item['current2021_population'],
             population_status='selected_native_numeric_unchanged', source_name_raw=item['current2021_name_raw'],
             source_path='/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet',
             source_sha256='86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14',
             source_locator='parquet:row_1based=' + current.rsplit(':', 1)[1],
             native_code=item['current_native_code'], source_quality_original='native_import_quality_not_upgraded'))
        coverage[current] = {'source_record_id': current, 'population_2021': item['current2021_population'],
             'population_2014': item['population'], 'numeric_2014': 'True', 'accepted_scoped_identity': 'True',
             'existing_accepted_ownpoint': 'True', 'complete_numeric_available_census_pair': 'True',
             'population_2014_presence_NULL': 'False', 'settlement_name': item['name_current_native']}
    for point in delta_points:
        points[point['target_source_record_id']] = point
        current = point['current_2021_source_record_id']
        coverage[current]['existing_accepted_ownpoint'] = 'True'
        if coverage[current]['numeric_2014'] == 'True':
            coverage[current]['complete_numeric_available_census_pair'] = 'True'
    federal = read(HERE / 'approved_federal_territory_point_reference.csv.gz')
    assert len(federal) == 1 and int(federal[0]['source_population']) == 547820
    territory = federal[0]
    territory_id = territory['source_record_id']
    points[territory_id] = dict(territory, target_source_record_id=territory_id,
        point_origin_file=territory['coordinate_claim_source_file'],
        point_origin_sha256=territory['coordinate_claim_source_sha256'],
        point_origin_locator='jsonl:line=' + territory['coordinate_claim_source_line'])
    for row in observations:
        if row['grain'] == 'federal_city_whole_territory':
            row['point_reference_target_id'] = territory_id
            row['coordinate_basis'] = 'approved_modern_whole_territory_reference_not_historical_measurement_or_NP_point'
            row['existing_identity_review_status'] = 'named_whole_territory_context_not_atomic_same_place_or_fixed_boundary_identity'
        point = points.get(row['point_reference_target_id'])
        if point:
            row['latitude'], row['longitude'] = point['latitude'], point['longitude']
            row['coordinate_evidence_file'] = point.get('review_packet_witness_point_origin_file') or point['point_origin_file']
            row['coordinate_evidence_sha256'] = point.get('review_packet_witness_point_origin_sha256') or point.get('point_origin_sha256', '')
            row['coordinate_evidence_locator'] = point.get('review_packet_witness_point_origin_locator') or point.get('point_origin_locator', '')
            row['coordinate_measurement_date'] = 'UNKNOWN'
            row['historical_coordinate_measurement_asserted'] = 'False'
    paired = [row for row in coverage.values() if row['complete_numeric_available_census_pair'] == 'True']
    assert len(observations) == len({row['source_record_id'] for row in observations}) == 2040
    assert len(coverage) == 1019 and len(paired) == 1008
    assert sum(int(row['population_2014']) for row in paired) == 1891465
    assert sum(int(row['population_2021']) for row in paired) == 1934562
    # Whole Sevastopol territory replaces all child observations in this axis.
    assert all(row.get('latitude') and row.get('longitude') for row in observations if row['grain'] == 'federal_city_whole_territory')
    outputs = {}
    for name, rows in [('actually_available_census_observations.csv.gz', observations),
                       ('actually_available_census_point_references.csv.gz', list(points.values())),
                       ('actually_available_census_native_2021_credit.csv.gz', list(coverage.values()))]:
        outputs[name] = write(D / name, rows)
    main_receipt = E / 'working_full_chain_20261007/coverage_receipt.json'
    report = json.loads(main_receipt.read_text())
    assert report['working_stage'] == 63
    pins[str(main_receipt)] = sha(main_receipt)
    baseline = report['separate_primary_available_year_lifecycle_axis63']['by_year']
    national21 = int(baseline['2021']['primary_extended_lifecycle_population']) + 1934562 + 547820
    receipt = {'status': 'root_applied_existing_primary_calendar_layer_and_four_source_bound_joins',
        'working_native_stage': 63, 'strict_Russian_2002_2010_2021_metrics_unchanged': True,
        'Crimea_Russian_2002_2010': 'outside_scope_no_observations_created',
        'Crimea_numeric_2014_2021_pairs': 1008, 'Crimea_numeric_pair_2014_population': 1891465,
        'Crimea_numeric_pair_2021_population': 1934562, 'Crimea_2021_control': 1934630,
        'Crimea_2021_numeric_pair_coverage_percent': 100 * 1934562 / 1934630,
        'Crimea_NULL_2014_records': 11, 'Crimea_NULL_2014_current2021_population': 68,
        'NULL_population_not_coerced_to_zero': True,
        'Sevastopol_scope': 'whole_federal_territory_2014_2021_published_totals_current_reference_point',
        'Sevastopol_2014_population': 393304, 'Sevastopol_2021_population': 547820,
        'Sevastopol_2014_point_measurement_and_boundary_equivalence_asserted': False,
        'national_2021_actually_available_calendar_population': national21,
        'national_2021_control': 147182123,
        'national_2021_actually_available_calendar_percent': 100 * national21 / 147182123,
        'national_2021_calendar_definition': 'Current common-territory primary available-year lifecycle axis plus numeric Crimea2014/2021 own-point paths and Sevastopol whole2014/2021 territory; excludes Sevastopol children; not literal Russian three-census population coverage',
        'coordinate_accuracy_calibrated': False, 'historical_boundary_comparability': 'UNKNOWN',
        'input_pins': pins, 'outputs': outputs, 'composition_code_sha256': sha(Path(__file__))}
    (D / 'actually_available_census_coverage_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    (HERE / 'root_application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ['Crimea_2021_numeric_pair_coverage_percent', 'national_2021_actually_available_calendar_percent']}))


if __name__ == '__main__':
    main()
