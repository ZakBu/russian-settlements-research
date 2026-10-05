#!/usr/bin/env python3
"""Apply a single independently reviewed 2002↔2010 historical-code bridge.

The admission is bounded to Московская Пески. It does not infer a 2021 edge.
The exact selected population values, including the protected 2010 value, are
preserved. One unique 2011 GeoKLADR representative point is used for both
observations with its historical date and uncertainty stated explicitly.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
GRAPH26 = Path('/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_identity_edges.parquet')
POINTS26 = Path('/tmp/graph26_gaikodzor_continuity_20261005/accepted_point_uses.parquet')
COHORT = Path('/workspace/settlements-work/continuation_20261004/independent_review/historical_urban_code_bridge_1258_audit_v1/cohort.csv')
RAW_OKATO = Path('/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql')
RAW_GEO = Path('/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf')
SOURCE2002 = Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls')
SOURCE2010 = Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls')
RESIDUAL = Path('/workspace/settlements-work/continuation_20261004/accepted_graph24_anapa_20261005/scoped_joint_residual.parquet')
OUT = Path('/tmp/graph27_peski_code_bridge_20261005')
IDS = {
    2002: '2002:1_TOM_01_04.xls:0:1143',
    2010: '2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:10189',
}
EXPECTED = {
    'selected': '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
    'graph26': '1cc307f2855d15c7503dd226a278c49bdab72f178f5e2564c5e20fa4195a7d1a',
    'points26': '5e153f1864471421d29d3edfa0ccfee4297f5e0a4e9e0cda20c4682c5471f3c8',
    'cohort': '2f60214f1b52acc4883effbcc4d2f10fb4e1e6e8c614b43c1c4e5469701389f4',
    'raw_okato': '6062e097ad504ba8b4bc130599ca4825c54f2b98486d16aed15ac143fcd705db',
    'raw_geo': 'd1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650',
    'source2002': '745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3',
    'source2010': 'cf5b5d57327bf0d32723a7f49bb58db503a201af83a6e2bda4b874986f864167',
}
ACCEPTED = {
    'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
    'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def raw_dbf_record(path: Path, onebased: int) -> tuple[dict[str, str], int]:
    data = path.read_bytes()
    nrec = struct.unpack('<I', data[4:8])[0]
    hlen = struct.unpack('<H', data[8:10])[0]
    rlen = struct.unpack('<H', data[10:12])[0]
    assert 1 <= onebased <= nrec
    offset = hlen + (onebased - 1) * rlen
    record = data[offset:offset + rlen]
    assert record[:1] != b'*'
    fields, pos, field_offset = [], 32, 1
    while pos + 32 <= hlen - 1 and data[pos] != 13:
        desc = data[pos:pos + 32]
        name = desc[:11].split(b'\0')[0].decode('ascii', 'replace')
        length = desc[16]
        fields.append((name, length, field_offset))
        field_offset += length
        pos += 32
    values = {}
    for name, length, start in fields:
        values[name] = record[start:start + length].decode('cp1251', 'replace').strip()
    return values, offset


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f'immutable output already exists: {OUT}')
    paths = {'selected': SELECTED, 'graph26': GRAPH26, 'points26': POINTS26,
             'cohort': COHORT, 'raw_okato': RAW_OKATO, 'raw_geo': RAW_GEO,
             'source2002': SOURCE2002, 'source2010': SOURCE2010}
    for name, path in paths.items():
        assert sha(path) == EXPECTED[name], (name, sha(path))

    cohort = pd.read_csv(COHORT, dtype={'source_record_id': str,
                                       'classifier_okato_2009_raw': str,
                                       'geokladr_okato_2011_raw': str})
    bridge = cohort.loc[cohort.source_record_id.isin(IDS.values())].set_index('source_record_id')
    assert set(bridge.index.astype(str)) == set(IDS.values())
    for year, sid in IDS.items():
        r = bridge.loc[sid]
        assert int(r.year) == year and str(r.settlement_name) == 'Пески'
        assert str(r.settlement_type) == 'пгт' and str(r.region_norm) == 'московская'
        assert int(r.population) == {2002: 3736, 2010: 3847}[year]
        assert str(r.classifier_okato_2009_raw) == '46222554'
        assert str(r.geokladr_okato_2011_raw) == '46222554000'
        assert str(r.KOD3_raw).zfill(3) == '000'
        assert bool(r.prefix8_match) and bool(r.geo_suffix000) and bool(r.name_exact)
        assert bool(r.type_exact) and float(r.region_name_type_key_count) == 1
        assert bool(r.compatible_structure) and bool(r.source_row_exact) and bool(r.source_file_resolved)
        assert int(r.shared_point_n) == 1 and int(r.shared_point_distinct_okato_n) == 1
        assert int(r.point_record) == 73090
        assert abs(float(r.point_lat) - 55.211577) < 1e-9
        assert abs(float(r.point_lon) - 38.773192) < 1e-9

    dbf, dbf_offset = raw_dbf_record(RAW_GEO, 73090)
    assert dbf_offset == 28_870_860
    assert dbf['TER'] + dbf['KOD1'] + dbf['KOD2'] + dbf['KOD3'] == '46222554000'
    assert dbf['KOD3'] == '000' and dbf['NAME1'] == 'Пески'
    assert dbf['LAT'] == '55.211577' and dbf['LONG'] == '38.773192'
    classifier_lines = [line.rstrip('\n\r') for line in RAW_OKATO.read_text(encoding='utf-8', errors='replace').splitlines()
                        if line.split('\t', 1)[0].strip() == '46222554']
    assert len(classifier_lines) == 1

    con = duckdb.connect(config={'threads': '1', 'memory_limit': '2GB'})
    observations = con.execute(
        'SELECT source_record_id,census_year,settlement_name,settlement_type,region_norm,population,'
        'population_value_quality,is_additive_settlement_record,population_scope,source_file,source_sheet,source_row '
        'FROM read_parquet(?) WHERE source_record_id IN (SELECT unnest(?))',
        [str(SELECTED), list(IDS.values())],
    ).fetchdf().set_index('source_record_id')
    expected = {
        IDS[2002]: (2002, 3736, 'direct_published_census_value'),
        IDS[2010]: (2010, 3847, 'secondary_confidentiality_protected_value_exact_scope_unverified'),
    }
    assert set(observations.index.astype(str)) == set(IDS.values())
    for sid, (year, population, quality) in expected.items():
        row = observations.loc[sid]
        assert (int(row.census_year), int(row.population), str(row.settlement_name),
                str(row.settlement_type), str(row.region_norm)) == (year, population, 'Пески', 'пгт', 'московская')
        assert str(row.population_value_quality) == quality and bool(row.is_additive_settlement_record)
        assert str(row.population_scope) == 'settlement'
    residual_ids = set(con.execute('SELECT source_record_id FROM read_parquet(?)', [str(RESIDUAL)]).fetchdf().source_record_id.astype(str))
    assert set(IDS.values()) <= residual_ids

    edges_path = OUT / 'accepted_identity_edges.parquet'
    edge_schema = pq.read_schema(GRAPH26)
    old_edges = con.execute(
        'SELECT decision_id,from_source_record_id,to_source_record_id,relation,decision_status FROM read_parquet(?)',
        [str(GRAPH26)],
    ).fetchdf()
    assert not set(IDS.values()).intersection(
        set(old_edges.loc[old_edges.decision_status.isin(ACCEPTED), 'from_source_record_id'].astype(str)) |
        set(old_edges.loc[old_edges.decision_status.isin(ACCEPTED), 'to_source_record_id'].astype(str))
    )
    decision_id = 'GRAPH27-PESKI-2002-2010-HISTORICAL-CODE-BRIDGE'
    assert decision_id not in set(old_edges.decision_id.astype(str))
    edge = {name: None for name in edge_schema.names}
    edge.update({
        'decision_id': decision_id, 'relation': 'same_place',
        'from_source_record_id': IDS[2002], 'from_year': '2002',
        'to_source_record_id': IDS[2010], 'to_year': '2010',
        'decision_class': 'bounded_historical_code_bridge_case_review',
        'decision_status': 'independent_case_review_accepted',
        'decision_rule': 'unique_exact_typed_name_region_key_plus_identical_2009_OKATO_2011_GeoKLADR_code_and_unique_named_point_v1',
        'reviewer': 'independent bounded candidate screen; primary application review',
        'reviewed_at': '2026-10-05',
        'evidence_uri': str(COHORT), 'evidence_sha256': sha(COHORT),
        'population_scope_interpretation': 'Identity and representative-point continuity only. 2010 selected population 3847 retains secondary confidentiality-protected exact-scope-unverified quality. No 2021 identity edge or population-boundary comparability is asserted; the nearby 2021 transition candidate is held.',
        'selection_projection_status': 'active_endpoints_selected',
        'application_review_id': 'graph27_moscow_peski_bounded_code_bridge_review_20261005',
        'application_review_sha256': sha(COHORT),
        'boundary_comparability_asserted': False,
        'population_comparability_asserted': False,
    })
    edge_table = pa.Table.from_pylist([edge], schema=edge_schema)
    OUT.mkdir(parents=True)
    writer = pq.ParquetWriter(edges_path, edge_schema, compression='zstd')
    base = pq.ParquetFile(GRAPH26)
    for batch in base.iter_batches(batch_size=25_000):
        writer.write_batch(batch)
    writer.write_table(edge_table)
    writer.close()

    point_schema = pq.read_schema(POINTS26)
    template_df = con.execute(
        'SELECT * FROM read_parquet(?) WHERE target_source_record_id=?',
        [str(POINTS26), '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:100081'],
    ).fetchdf()
    assert len(template_df) == 1
    template = {name: (None if pd.isna(value) else value) for name, value in template_df.iloc[0].to_dict().items()}
    geo_locator = 'raw_dbf_record_number_1based=73090;byte_offset_0based=28870860'
    point_rows = []
    for year, sid in IDS.items():
        source = observations.loc[sid]
        row = dict(template)
        row.update({
            'target_source_record_id': sid, 'target_year': f'{year}.0',
            'latitude': 55.211577, 'longitude': 38.773192,
            'coordinate_quality': 'independently_reviewed_historical_code_bridge_point',
            'coordinate_source': 'GeoKLADR 2011 named typed locality point; exact raw classifier and GeoKLADR code bridge',
            'coordinate_source_record_id': 'GeoKLADR2011:OKATO:46222554000',
            'coordinate_provider': 'GeoKLADR 2011 raw locality DBF',
            'source_name': 'Пески', 'source_type': 'пгт', 'source_region': 'московская',
            'source_file': str(source.source_file), 'source_row': float(source.source_row),
            'source_sha256': EXPECTED['source2002'] if year == 2002 else EXPECTED['source2010'],
            'source_locator': f"{source.source_sheet}:{int(source.source_row)}; selected ID={sid}",
            'coordinate_provenance': 'Unique 2011 GeoKLADR representative point, cross-checked against raw 2009 OKATO classifier code 46222554. Both selected rows independently have exact name/type/region key and resolve to the identical 2011 code 46222554000; the point is one shared physical reference, not independent census-date measurements.',
            'admission_rule': 'unique exact typed name-region key + identical raw 2009 OKATO / 2011 GeoKLADR code + unique point origin + canonical graph collision check',
            'provider_binding_status': 'No external provider binding asserted; point belongs to the named GeoKLADR DBF record.',
            'provider_fias_binding_status': 'No FIAS/provider identifier claim.',
            'coordinate_admission_status': 'reviewed_case_accepted',
            'coordinate_measurement_date_unknown': True,
            'boundary_comparability_asserted': False,
            'coordinate_application_family': 'graph27_moscow_peski_historical_code_bridge_20261005',
            'review_id': 'independent_historical_urban_code_bridge_and_bounded_pair_review_20261005',
            'application_inference_kind': 'historical_named_place_representative_point_code_bridge',
            'direct_historical_coordinate_measurement': False,
            'population_scope_comparability_asserted': False,
            'admission_allowed': True, 'coordinate_admitted': True, 'point_admitted': True,
            'identity_edge_admitted': False, 'historical_propagation_allowed': True,
            'coordinate_source_sha256': EXPECTED['raw_geo'],
            'coordinate_source_locator': geo_locator,
            'coordinate_source_file': str(RAW_GEO),
            'coordinate_source_origin': 'GeoKLADR 2011 historical representative point; physical measurement date unknown',
            'coordinate_source_input_artifact_sha256': EXPECTED['raw_okato'],
            'coordinate_source_date': '2011 edition; measurement date unknown',
            'coordinate_source_latitude_raw': '55.211577',
            'coordinate_source_longitude_raw': '38.773192',
            'point_origin_file': str(RAW_GEO), 'point_origin_sha256': EXPECTED['raw_geo'],
            'point_origin_locator': geo_locator,
            'point_origin_kind': 'geokladr_2011_raw_dbf_coordinate',
            'point_use_id': f'graph27-peski-code-bridge:{sid}',
            'population': int(source.population),
            'supporting_2009_sql_code_literal': '46222554',
            'supporting_2011_dbf_code_literal': '46222554000',
            'supporting_2011_dbf_raw_point_distance_km': '0',
            'historical_identity_asserted': '2002 and 2010 rows only; no 2021 edge',
            'native_identifier_binding_asserted': 'exact 2009 classifier-to-2011 GeoKLADR code bridge; no modern provider ID asserted',
            'census_date_measurement_asserted': 'false',
            'point_origin_row_1based': '73090',
            'point_origin_raw_payload_sha256': EXPECTED['raw_geo'],
            'source_raw_object_level': 'named settlement; typed pgt; selected census row',
            'boundary_comparability': 'not asserted',
            'historical_reuse': 'explicit code-based representative-point continuity across selected 2002 and 2010 locality rows',
            'coordinate_uncertainty_flags_json': json.dumps({'measurement_date_unknown': True, 'boundary_comparability_not_asserted': True, '2021_identity_not_asserted': True}, sort_keys=True),
            'target_source_name_raw': str(source.source_file) + '; exact selected source row',
        })
        for field in point_schema:
            value = row.get(field.name)
            if value is None or pd.isna(value):
                row[field.name] = None
            elif pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
                row[field.name] = str(value)
            elif pa.types.is_boolean(field.type):
                row[field.name] = bool(value)
            elif pa.types.is_integer(field.type):
                row[field.name] = int(value)
            elif pa.types.is_floating(field.type):
                row[field.name] = float(value)
        point_rows.append(row)
    point_path = OUT / 'accepted_point_uses.parquet'
    point_writer = pq.ParquetWriter(point_path, point_schema, compression='zstd')
    point_base = pq.ParquetFile(POINTS26)
    for batch in point_base.iter_batches(batch_size=25_000):
        point_writer.write_batch(batch)
    point_writer.write_table(pa.Table.from_pylist(point_rows, schema=point_schema))
    point_writer.close()

    # Recheck every active same_place component for duplicate years.
    all_rows = con.execute('SELECT source_record_id,census_year FROM read_parquet(?)', [str(SELECTED)]).fetchall()
    years = {str(s): int(y) for s, y in all_rows}
    parent = {s: s for s in years}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for a, b in con.execute("SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) WHERE relation='same_place' AND decision_status IN (SELECT unnest(?))", [str(edges_path), sorted(ACCEPTED)]).fetchall():
        a, b = str(a), str(b)
        assert a in parent and b in parent
        union(a, b)
    comp_years = {}
    for sid, year in years.items():
        comp_years.setdefault(find(sid), []).append(year)
    assert all(len(v) == len(set(v)) for v in comp_years.values())

    receipt = {
        'status': 'bounded_peski_2002_2010_identity_and_point_uses_applied',
        'inputs': {key: {'path': str(path), 'sha256': sha(path)} for key, path in paths.items()},
        'new_identity_edge': {'decision_id': decision_id, 'from': IDS[2002], 'to': IDS[2010],
                              'relation': 'same_place', 'status': 'independent_case_review_accepted',
                              'population_comparability_asserted': False},
        'new_point_uses': [{'source_record_id': sid, 'year': year, 'latitude': 55.211577,
                            'longitude': 38.773192, 'status': 'reviewed_case_accepted',
                            'population': int(observations.loc[sid].population)} for year, sid in IDS.items()],
        'selected_population_values_changed': False,
        'same_year_graph_collisions': 0,
        'point_origin': {'file': str(RAW_GEO), 'sha256': EXPECTED['raw_geo'],
                         'dbf_record_1based': 73090, 'byte_offset_0based': dbf_offset,
                         'okato2009': '46222554', 'geokladr2011': '46222554000',
                         'latitude': dbf['LAT'], 'longitude': dbf['LONG']},
        'limitations': [
            'Point edition is 2011 GeoKLADR; physical measurement date is unknown and it is not a census-date measurement.',
            '2010 selected population remains secondary confidentiality-protected with exact scope unverified.',
            'No 2021 identity edge is admitted: nearby 2021 settlement changes from pgt to rural type and requires a separate event/source witness.',
            'Population boundary comparability is not asserted.',
        ],
        'outputs': {
            'accepted_identity_edges.parquet': {'path': str(edges_path), 'sha256': sha(edges_path), 'rows': pq.ParquetFile(edges_path).metadata.num_rows},
            'accepted_point_uses.parquet': {'path': str(point_path), 'sha256': sha(point_path), 'rows': pq.ParquetFile(point_path).metadata.num_rows},
        },
    }
    (OUT / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
