"""Apply one exact-source, equal-FIAS-UUID current point to graph16.

This is point-only: it leaves population, identity links, historical points,
and boundary comparability untouched. The read-only candidate package and all
canonical inputs are SHA-pinned, and the original point ledger is streamed as
an unchanged prefix into a separate successor ledger.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq


PKG = Path('/workspace/settlements-work/continuation_20261004/regions/full3_current_point3_recovery_v1')
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
GRAPH = Path('/workspace/settlements-work/continuation_20261004/accepted_mass_sixteenth_large4_point4952/accepted_identity_edges.parquet')
POINTS = GRAPH.parent / 'accepted_point_uses.parquet'
RAW = Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
CLASS = Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql')
TARGET = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46737'
ROW = 46737
UUID = '12893c78-6cb3-4c12-afb7-eb032b2cc964'
LAT, LON = 45.0822595, 39.1995747


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def q(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def main(output: Path) -> dict:
    rec = json.loads((PKG / 'receipt.json').read_text(encoding='utf-8'))
    if not rec.get('read_only_candidate_package'):
        raise ValueError('candidate package was not read-only')
    for name, digest in rec['output_sha256'].items():
        if sha(PKG / name) != digest:
            raise ValueError(f'candidate-package output pin mismatch: {name}')
    for path, digest in rec['input_sha256'].items():
        if path == 'wikidata_truthy_claims_manifest_sha256':
            continue
        p = Path(path)
        if sha(p) != digest:
            raise ValueError(f'candidate-package input pin mismatch: {p}')
    cand_path = PKG / 'eligible_point_candidates.csv'
    with cand_path.open(encoding='utf-8-sig', newline='') as f:
        candidates = list(csv.DictReader(f))
    if len(candidates) != 1 or candidates[0]['target_source_record_id'] != TARGET:
        raise ValueError('expected exactly the independently reviewed Biofabriki candidate')
    c = candidates[0]
    if c['status'] != 'eligible_point_candidate_pending_root_application' or c['exact_UUID_binding'] != 'True':
        raise ValueError('candidate status or exact-UUID finding changed')
    if (float(c['latitude']), float(c['longitude'])) != (LAT, LON):
        raise ValueError('candidate coordinates changed')

    # Independently read the exact selected source and raw publisher row.
    con = duckdb.connect(':memory:')
    sid, = con.execute(f"SELECT count(*) FROM read_parquet({q(SELECTED)}) WHERE source_record_id=?", [TARGET]).fetchone()
    if sid != 1:
        raise ValueError('target is not a unique selected source row')
    selected = con.execute(f"SELECT * FROM read_parquet({q(SELECTED)}) WHERE source_record_id=?", [TARGET]).fetchdf().iloc[0]
    raw = con.execute(f"SELECT * FROM (SELECT row_number() OVER () AS __rn, * FROM read_parquet({q(RAW)})) WHERE __rn=?", [ROW]).fetchdf()
    if len(raw) != 1:
        raise ValueError('raw publisher row locator is not unique')
    raw = raw.iloc[0]
    expected = {
        'object_name': str(c['source_name_raw']), 'oktmo': str(c['selected_native_OKTMO']),
        'settlement_fias_id_dadata': UUID, 'fias_id_dadata': UUID,
    }
    for field, value in expected.items():
        if str(raw[field]).strip() != value:
            raise ValueError(f'raw source field mismatch {field}: {raw[field]!r}')
    if (float(raw.latitude_dadata), float(raw.longitude_dadata)) != (LAT, LON):
        raise ValueError('raw publisher coordinates changed')
    if str(selected['fias_id']) != UUID or str(selected['oktmo']) != str(c['selected_native_OKTMO']):
        raise ValueError('selected FIAS/OKTMO do not bind to the candidate')
    if int(selected.population) != int(c['population_context_only']) or int(selected.census_year) != 2021:
        raise ValueError('selected year or population-context source differs')
    line = CLASS.read_text(encoding='utf-8', errors='replace').splitlines()[6970]
    if '03401973006' not in line or 'Подсобного Производственного Хозяйства Биофабрики' not in line:
        raise ValueError('pinned 2009 classifier line is not the named locality witness')

    # Require this row to have no prior accepted point and no same-year point
    # collision; preserve the whole prior parquet byte-for-byte as an Arrow prefix.
    schema = pq.read_schema(POINTS)
    old = pq.ParquetFile(POINTS)
    statuses = {'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
                'reviewed_extension_rule_accepted', 'reviewed_case_accepted'}
    rows = pq.read_table(POINTS, columns=['target_source_record_id', 'target_year', 'coordinate_admission_status', 'latitude', 'longitude']).to_pylist()
    if any(x['target_source_record_id'] == TARGET and x['coordinate_admission_status'] in statuses for x in rows):
        raise ValueError('target already has an admitted point')
    for x in rows:
        if x['coordinate_admission_status'] in statuses and x['target_year'] is not None and int(float(x['target_year'])) == 2021 and x['target_source_record_id'] != TARGET:
            if abs(float(x['latitude']) - LAT) < 1e-10 and abs(float(x['longitude']) - LON) < 1e-10:
                raise ValueError('same-year exact-coordinate collision')

    point = {field.name: None for field in schema}
    point.update({
        'target_source_record_id': TARGET, 'target_year': 2021,
        'latitude': LAT, 'longitude': LON,
        'coordinate_quality': 'source-publisher point with exact equal FIAS-6 UUID; provider display label differs',
        'coordinate_source': 'Tochno/DaData raw coordinate preserved in exact 2021 publisher row',
        'coordinate_source_record_id': UUID, 'coordinate_provider': 'DaData (as embedded by source publisher)',
        'coordinate_provider_id': UUID, 'source_name': str(selected['settlement_name']),
        'source_type': str(selected['settlement_type']), 'source_region': str(selected['region_raw']),
        'source_file': str(RAW), 'source_row': ROW, 'source_sha256': sha(RAW),
        'source_locator': f'parquet row 1-based {ROW}; exact source payload SHA {c["point_source_locator"].split("payload SHA ")[-1]}',
        'coordinate_provenance': ('2021 source-publisher coordinate; exact source row has locality grain, matching name/type/region/population, unique OKTMO 3701000226, and its own FIAS-6 UUID equals the response UUID. Provider display says “п Пригородный”; this mismatch is retained. Coordinate date is unknown; no historical measurement, boundary continuity, or population comparability is asserted.'),
        'admission_rule': 'root_checked_exact_2021_locality_source_and_equal_FIAS6_UUID_point_20261005',
        'provider_binding_status': 'source_row_FIAS6_UUID_equals_raw_response_FIAS6_UUID; provider display name differs',
        'provider_fias_binding_status': 'equal_source_and_response_FIAS6_UUID; exact source locality/code/population checked',
        'coordinate_admission_status': 'reviewed_case_accepted',
        'coordinate_measurement_date_unknown': True, 'boundary_comparability_asserted': False,
        'coordinate_provider_family': 'embedded_FIAS_DaData_source_publisher',
        'source_oktmo_raw': '3701000226', 'provider_query_receipt_missing': True,
        'coordinate_uncertainty_flags_json': json.dumps({'measurement_date_unknown': True, 'provider_display_name_differs': True,
            'provider_response_fias_uuid_equal_to_source_uuid': True, 'historical_boundary_and_population_comparability_not_asserted': True}, sort_keys=True),
        'coordinate_application_family': 'graph16_biofabriki_point_only_20261005',
        'review_id': 'root_exact_source_equal_fias_uuid_review_20261005',
        'application_inference_kind': 'direct_current_source_row_point_use',
        'direct_historical_coordinate_measurement': False,
        'population_scope_comparability_asserted': False, 'admission_allowed': True,
        'application_gate_status': 'exact_raw_locality_source_plus_unique_native_OKTMO_plus_equal_FIAS6_UUID; display-name ambiguity retained',
        'coordinate_source_sha256': sha(RAW), 'coordinate_source_locator': f'parquet row 1-based {ROW}',
        'coordinate_source_file': str(RAW), 'coordinate_source_origin': '2021 publisher source row; embedded DaData response',
        'coordinate_source_date': None, 'coordinate_source_latitude_raw': LAT,
        'coordinate_source_longitude_raw': LON, 'point_origin_file': str(RAW),
        'point_origin_sha256': sha(RAW), 'point_origin_locator': f'parquet row 1-based {ROW}',
        'point_origin_kind': 'exact_2021_source_locality_row_equal_fias6_uuid',
        'coordinate_application_review_sha256': sha(PKG / 'receipt.json'),
        'coordinate_admitted': True, 'point_admitted': True, 'identity_edge_admitted': False,
        'historical_propagation_allowed': False, 'historical_measurement_claimed': False,
        'modern_provider_binding_claimed': True, 'fias_identifier_binding_claimed': True,
        'source_lineage_independence_proven': False, 'upstream_independent_lineage_proven': False,
        'source_record_id': TARGET, 'source_population': str(int(selected.population)),
        'source_oktmo': '3701000226', 'target_source_name_raw': str(raw.object_name),
        'target_population': int(selected.population), 'target_population_scope': str(selected.population_scope),
        'target_population_value_quality': str(selected.population_value_quality),
        'target_source_record_json': json.dumps({'source_record_id': TARGET, 'census_year': 2021,
            'settlement_name': str(selected.settlement_name), 'settlement_type': str(selected.settlement_type),
            'population': int(selected.population), 'oktmo': str(selected.oktmo), 'fias_id': str(selected.fias_id)}, ensure_ascii=False, sort_keys=True),
        'source_raw_file': str(RAW), 'source_raw_file_sha256': sha(RAW),
        'source_raw_row_1based': ROW, 'source_raw_row_locator_status': 'exact_row_replayed',
    })
    # Strict schema conversion: reject, rather than silently dropping, bad types.
    casted = {}
    for field in schema:
        value = point.get(field.name)
        if value is None:
            casted[field.name] = None
        elif pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
            casted[field.name] = str(value)
        elif pa.types.is_binary(field.type) or pa.types.is_large_binary(field.type):
            casted[field.name] = value if isinstance(value, bytes) else str(value).encode('utf-8')
        elif pa.types.is_boolean(field.type):
            casted[field.name] = bool(value)
        elif pa.types.is_integer(field.type):
            if float(value) != int(float(value)):
                raise ValueError(f'non-integral {field.name}: {value!r}')
            casted[field.name] = int(float(value))
        elif pa.types.is_floating(field.type):
            casted[field.name] = float(value)
        elif pa.types.is_decimal(field.type):
            casted[field.name] = Decimal(str(value))
        else:
            raise TypeError(f'unsupported schema field {field.name}: {field.type}')
    addition = pa.Table.from_pylist([casted], schema=schema)
    output.mkdir(parents=True, exist_ok=False)
    out = output / 'accepted_point_uses.parquet'
    with pq.ParquetWriter(out, schema, compression='zstd') as writer:
        for batch in old.iter_batches(batch_size=2048):
            writer.write_batch(batch)
        writer.write_table(addition, row_group_size=1)
    check = pq.ParquetFile(out)
    if check.metadata.num_rows != old.metadata.num_rows + 1:
        raise ValueError('output point ledger row count mismatch')
    appended = pq.read_table(out, columns=['target_source_record_id', 'coordinate_admission_status', 'latitude', 'longitude']).slice(old.metadata.num_rows, 1).to_pylist()[0]
    if appended['target_source_record_id'] != TARGET or appended['coordinate_admission_status'] != 'reviewed_case_accepted':
        raise ValueError('appended point use readback failed')
    result = {'status': 'single_point_only_application_complete', 'target_source_record_id': TARGET,
        'coordinates': [LAT, LON], 'population_context_only': int(selected.population),
        'identity_edges_added': 0, 'population_changed': False, 'historical_point_propagated': False,
        'boundary_or_population_comparability_asserted': False, 'provider_display_mismatch_retained': True,
        'candidate_package_receipt_sha256': sha(PKG / 'receipt.json'), 'raw_source_sha256': sha(RAW),
        'selected_observations_sha256': sha(SELECTED), 'graph_sha256_unchanged': sha(GRAPH),
        'input_point_uses_sha256': sha(POINTS), 'input_point_rows': old.metadata.num_rows,
        'output_point_rows': check.metadata.num_rows, 'output_point_uses_sha256': sha(out),
        'classifier_2009_file_sha256': sha(CLASS), 'appended_status': appended['coordinate_admission_status']}
    (output / 'application_receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(main(args.output), ensure_ascii=False, indent=2))
