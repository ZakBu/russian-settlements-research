#!/usr/bin/env python3
"""Apply three bounded 2002↔2010 OKATO/GeoKLADR code bridges.

No 2021 links, population replacements, or population-boundary equivalence are
asserted. The only additions are two selected observations per place and
2011 named GeoKLADR representative-point continuity for those same rows.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path('/workspace')
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH27 = Path('/tmp/graph27_peski_code_bridge_20261005/accepted_identity_edges.parquet')
POINTS27 = Path('/tmp/graph27_peski_code_bridge_20261005/accepted_point_uses.parquet')
COHORT = ROOT / 'settlements-work/continuation_20261004/independent_review/historical_urban_code_bridge_1258_audit_v1/cohort.csv'
RAW_OKATO = ROOT / 'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
RAW_GEO = ROOT / 'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
SOURCE_2002 = ROOT / 'settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls'
SOURCE_2010_MOSCOW = ROOT / 'settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls'
SOURCE_2010_PERM = ROOT / 'settlements-raw/data/raw/2010/016_802d308e41_8._20Or_Penz_Perm_Samar_Saratov_Uly_2010.xls'
RESIDUAL = ROOT / 'settlements-work/continuation_20261004/accepted_graph24_anapa_20261005/scoped_joint_residual.parquet'
OUT = Path('/tmp/graph28_three_code_bridge_20261005')

PAIRS = [
    {
        'slug': 'pirogovskiy_moscow', 'name': 'Пироговский', 'type': 'пгт', 'region': 'московская',
        'code8': '46234562', 'code11': '46234562000', 'dbf_record': 73988,
        'lat': 55.981716, 'lon': 37.741212,
        2002: '2002:1_TOM_01_04.xls:0:1198',
        2010: '2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:11126',
        'pop': {2002: 6260, 2010: 6676}, 'source2010': SOURCE_2010_MOSCOW,
        'classifier_line': 98692, 'dbf_offset': 29225570,
    },
    {
        'slug': 'lvovskiy_moscow', 'name': 'Львовский', 'type': 'пгт', 'region': 'московская',
        'code8': '46246554', 'code11': '46246554000', 'dbf_record': 74968,
        'lat': 55.314830, 'lon': 37.523598,
        2002: '2002:1_TOM_01_04.xls:0:1268',
        2010: '2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:12103',
        'pop': {2002: 11906, 2010: 10856}, 'source2010': SOURCE_2010_MOSCOW,
        'classifier_line': 99878, 'dbf_offset': 29612670,
    },
    {
        'slug': 'yubileyniy_perm', 'name': 'Юбилейный', 'type': 'пгт', 'region': 'пермский',
        'code8': '57412558', 'code11': '57412558000', 'dbf_record': 93412,
        'lat': 58.780733, 'lon': 57.779170,
        2002: '2002:1_TOM_01_04.xls:0:6671',
        2010: '2010:016_802d308e41_8._20Or_Penz_Perm_Samar_Saratov_Uly_2010.xls:!!!:7832',
        'pop': {2002: 1698, 2010: 1099}, 'source2010': SOURCE_2010_PERM,
        'classifier_line': 124960, 'dbf_offset': 36898050,
    },
]

EXPECTED = {
    'selected': '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
    'graph27': '607347a69514a3f0b83d0681520bd642a7973d08d7dc1418723cb0050867d914',
    'points27': 'c24a596af84094f119c9ded8a07dbb22b98b1be2c0384698c455300baf17263f',
    'cohort': '2f60214f1b52acc4883effbcc4d2f10fb4e1e6e8c614b43c1c4e5469701389f4',
    'raw_okato': '6062e097ad504ba8b4bc130599ca4825c54f2b98486d16aed15ac143fcd705db',
    'raw_geo': 'd1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650',
    'source2002': '745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3',
    'source2010_moscow': 'cf5b5d57327bf0d32723a7f49bb58db503a201af83a6e2bda4b874986f864167',
    'source2010_perm': '754aae620807b1275e59fc7bf8ce086ca91e7ec863d4d304f5a0a8b228a8d990',
}
ACCEPTED_EDGES = {
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


def dbf_record(path: Path, onebased: int) -> tuple[dict[str, str], int]:
    data = path.read_bytes()
    nrec = struct.unpack('<I', data[4:8])[0]
    hlen = struct.unpack('<H', data[8:10])[0]
    rlen = struct.unpack('<H', data[10:12])[0]
    assert 1 <= onebased <= nrec
    offset = hlen + (onebased - 1) * rlen
    record = data[offset:offset + rlen]
    assert record[:1] != b'*'
    fields, pos, start = [], 32, 1
    while pos + 32 <= hlen - 1 and data[pos] != 13:
        d = data[pos:pos + 32]
        name, width = d[:11].split(b'\0')[0].decode('ascii', 'replace'), d[16]
        fields.append((name, width, start)); start += width; pos += 32
    return {name: record[begin:begin + width].decode('cp1251', 'replace').strip()
            for name, width, begin in fields}, offset


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f'immutable output already exists: {OUT}')
    input_paths = {
        'selected': SELECTED, 'graph27': GRAPH27, 'points27': POINTS27, 'cohort': COHORT,
        'raw_okato': RAW_OKATO, 'raw_geo': RAW_GEO, 'source2002': SOURCE_2002,
        'source2010_moscow': SOURCE_2010_MOSCOW, 'source2010_perm': SOURCE_2010_PERM,
    }
    for key, path in input_paths.items():
        actual = sha(path)
        assert actual == EXPECTED[key], (key, actual)

    cohort = pd.read_csv(COHORT, dtype={
        'source_record_id': str, 'classifier_okato_2009_raw': str, 'geokladr_okato_2011_raw': str,
    })
    selected = pd.read_parquet(SELECTED, columns=[
        'source_record_id', 'census_year', 'settlement_name', 'settlement_type', 'region_norm',
        'population', 'population_value_quality', 'is_additive_settlement_record', 'population_scope',
        'source_file', 'source_sheet', 'source_row',
    ])
    if selected.source_record_id.astype(str).duplicated().any():
        raise ValueError('selected source IDs are not unique')
    selected = selected.set_index('source_record_id', drop=False)
    residual_ids = set(pd.read_parquet(RESIDUAL, columns=['source_record_id']).source_record_id.astype(str))
    raw_lines = RAW_OKATO.read_text(encoding='utf-8', errors='replace').splitlines()

    pairs = []
    for p in PAIRS:
        rows = cohort.loc[cohort.source_record_id.isin([p[2002], p[2010]])].set_index('source_record_id')
        assert set(rows.index.astype(str)) == {p[2002], p[2010]}
        assert len(cohort.loc[(cohort.year == 2002) & cohort.settlement_name.eq(p['name']) &
                              cohort.settlement_type.eq(p['type']) & cohort.region_norm.eq(p['region'])]) == 1
        assert len(cohort.loc[(cohort.year == 2010) & cohort.settlement_name.eq(p['name']) &
                              cohort.settlement_type.eq(p['type']) & cohort.region_norm.eq(p['region'])]) == 1
        for year in (2002, 2010):
            r = rows.loc[p[year]]
            assert (int(r.year), str(r.settlement_name), str(r.settlement_type), str(r.region_norm), int(r.population)) == (
                year, p['name'], p['type'], p['region'], p['pop'][year]
            )
            assert str(r.classifier_okato_2009_raw) == p['code8']
            assert str(r.geokladr_okato_2011_raw) == p['code11']
            assert str(r.KOD3_raw).zfill(3) == '000'
            assert int(r.region_name_type_key_count) == 1 and bool(r.name_exact) and bool(r.type_exact)
            assert bool(r.prefix8_match) and bool(r.geo_suffix000)
            assert int(r.shared_point_n) == 1 and int(r.shared_point_distinct_okato_n) == 1
            assert int(r.point_record) == p['dbf_record']
            assert abs(float(r.point_lat) - p['lat']) < 1e-9 and abs(float(r.point_lon) - p['lon']) < 1e-9
            assert bool(r.source_row_exact) and bool(r.source_file_resolved)
            s = selected.loc[p[year]]
            assert int(s.census_year) == year and int(s.population) == p['pop'][year]
            assert str(s.settlement_name) == p['name'] and str(s.settlement_type) == p['type']
            assert str(s.region_norm) == p['region'] and bool(s.is_additive_settlement_record)
            assert str(s.population_scope) == 'settlement'
            assert p[year] in residual_ids
        exact_lines = [(i + 1, line.rstrip('\n\r')) for i, line in enumerate(raw_lines)
                       if line.split('\t', 1)[0].strip() == p['code8']]
        assert len(exact_lines) == 1 and exact_lines[0][0] == p['classifier_line']
        clf = exact_lines[0][1].split('\t')
        assert clf[1].strip() == p['name'] and clf[2].strip() == p['name']
        assert clf[3].strip() == 'поселок городского типа' and clf[5].strip().lower() == 't'
        dbf, offset = dbf_record(RAW_GEO, p['dbf_record'])
        assert offset == p['dbf_offset']
        assert dbf['TER'] + dbf['KOD1'] + dbf['KOD2'] + dbf['KOD3'] == p['code11']
        assert dbf['KOD3'] == '000' and dbf['NAME1'] == p['name']
        assert dbf['LAT'] == f"{p['lat']:.6f}" and dbf['LONG'] == f"{p['lon']:.6f}"
        if p['slug'] != 'yubileyniy_perm':
            assert dbf['SCOKATO'] == 'пгт'
        pairs.append({'pair': p, 'dbf': dbf, 'dbf_offset': offset})

    edges = pd.read_parquet(GRAPH27)
    points = pd.read_parquet(POINTS27)
    if edges.decision_id.astype(str).duplicated().any():
        raise ValueError('duplicate decision identifiers in Graph27 inputs')
    existing_point_ids = set(points.point_use_id.dropna().astype(str))
    ids = set(selected.source_record_id.astype(str))
    parent = {sid: sid for sid in ids}
    years = selected.census_year.astype(int).to_dict()
    comp_years = {sid: {int(years[sid])} for sid in ids}
    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: str, b: str) -> str:
        ra, rb = find(a), find(b)
        if ra == rb:
            return 'already_connected'
        if comp_years[ra] & comp_years[rb]:
            return 'year_collision'
        if len(comp_years[ra]) < len(comp_years[rb]):
            ra, rb = rb, ra
        parent[rb] = ra
        comp_years[ra] |= comp_years.pop(rb)
        return 'merged'
    accepted = edges.loc[edges.relation.eq('same_place') & edges.decision_status.isin(ACCEPTED_EDGES)]
    for a, b in accepted[['from_source_record_id', 'to_source_record_id']].astype(str).itertuples(index=False, name=None):
        assert a in parent and b in parent
        assert union(a, b) != 'year_collision'

    edge_schema = pq.read_schema(GRAPH27)
    new_edges = []
    point_schema = pq.read_schema(POINTS27)
    template = points.iloc[0].to_dict()
    new_points = []
    for item in pairs:
        p, dbf, offset = item['pair'], item['dbf'], item['dbf_offset']
        a, b = p[2002], p[2010]
        assert a not in set(accepted.from_source_record_id.astype(str)) | set(accepted.to_source_record_id.astype(str))
        assert b not in set(accepted.from_source_record_id.astype(str)) | set(accepted.to_source_record_id.astype(str))
        decision_id = 'GRAPH28-' + p['slug'].upper() + '-2002-2010-HISTORICAL-CODE-BRIDGE'
        assert decision_id not in set(edges.decision_id.astype(str))
        edge = {name: None for name in edge_schema.names}
        edge.update({
            'decision_id': decision_id, 'relation': 'same_place',
            'from_source_record_id': a, 'from_year': '2002',
            'to_source_record_id': b, 'to_year': '2010',
            'decision_class': 'bounded_historical_code_bridge_pair_review',
            'decision_status': 'independent_case_review_accepted',
            'decision_rule': 'unique_exact_typed_name_region_key_plus_identical_2009_OKATO_2011_GeoKLADR_code_and_unique_named_point_v1',
            'reviewer': 'independent bounded pair-only code bridge review; primary application checks',
            'reviewed_at': '2026-10-05',
            'evidence_uri': str(COHORT), 'evidence_sha256': EXPECTED['cohort'],
            'population_scope_interpretation': 'Only selected 2002↔2010 physical-place identity and 2011 named representative point continuity. No 2021 endpoint, population-boundary comparability, or population comparability is asserted. The 2010 value retains its selected source quality.',
            'selection_projection_status': 'active_endpoints_selected',
            'application_review_id': 'graph28_' + p['slug'] + '_bounded_pair_application_20261005',
            'application_review_sha256': EXPECTED['cohort'],
            'boundary_comparability_asserted': False,
            'population_comparability_asserted': False,
        })
        new_edges.append(edge)
        assert union(a, b) == 'merged'
        locator = f"raw_dbf_record_number_1based={p['dbf_record']};byte_offset_0based={offset}"
        for year, sid in ((2002, a), (2010, b)):
            source = selected.loc[sid]
            row = {k: (None if pd.isna(v) else v) for k, v in template.items()}
            row.update({
                'target_source_record_id': sid, 'target_year': f'{year}.0',
                'latitude': p['lat'], 'longitude': p['lon'],
                'coordinate_quality': 'independently_reviewed_historical_code_bridge_point',
                'coordinate_source': 'GeoKLADR 2011 named typed locality point; exact raw classifier and GeoKLADR code bridge',
                'coordinate_source_record_id': 'GeoKLADR2011:OKATO:' + p['code11'],
                'coordinate_provider': 'GeoKLADR 2011 raw locality DBF',
                'source_name': p['name'], 'source_type': p['type'], 'source_region': p['region'],
                'source_file': str(source.source_file), 'source_row': float(source.source_row),
                'source_sha256': EXPECTED['source2002'] if year == 2002 else sha(p['source2010']),
                'source_locator': f"{source.source_sheet}:{int(source.source_row)}; selected ID={sid}",
                'coordinate_provenance': f"One unique 2011 GeoKLADR point at {p['lat']:.6f},{p['lon']:.6f}. Both selected census rows resolve to exact 2009 OKATO {p['code8']} and 2011 code {p['code11']}; raw point origin is one shared named locality record, not independent census-date measurements.",
                'admission_rule': 'unique exact typed name-region key + identical raw 2009 OKATO / 2011 GeoKLADR code + unique point origin + canonical graph collision check',
                'provider_binding_status': 'No external provider binding asserted; point belongs to the named GeoKLADR DBF record.',
                'provider_fias_binding_status': 'No FIAS/provider identifier claim.',
                'coordinate_admission_status': 'reviewed_case_accepted',
                'coordinate_measurement_date_unknown': True,
                'boundary_comparability_asserted': False,
                'coordinate_application_family': 'graph28_' + p['slug'] + '_historical_code_bridge_20261005',
                'review_id': 'independent_historical_urban_code_bridge_and_bounded_pair_review_20261005',
                'application_inference_kind': 'historical_named_place_representative_point_code_bridge',
                'direct_historical_coordinate_measurement': False,
                'population_scope_comparability_asserted': False,
                'admission_allowed': True, 'coordinate_admitted': True, 'point_admitted': True,
                'identity_edge_admitted': False, 'historical_propagation_allowed': True,
                'coordinate_source_sha256': EXPECTED['raw_geo'],
                'coordinate_source_locator': locator,
                'coordinate_source_file': str(RAW_GEO),
                'coordinate_source_origin': 'GeoKLADR 2011 historical representative point; physical measurement date unknown',
                'coordinate_source_input_artifact_sha256': EXPECTED['raw_okato'],
                'coordinate_source_date': '2011 edition; measurement date unknown',
                'coordinate_source_latitude_raw': dbf['LAT'],
                'coordinate_source_longitude_raw': dbf['LONG'],
                'point_origin_file': str(RAW_GEO), 'point_origin_sha256': EXPECTED['raw_geo'],
                'point_origin_locator': locator,
                'point_origin_kind': 'geokladr_2011_raw_dbf_coordinate',
            'point_use_id': f'graph28-{p["slug"]}:{sid}',
                'population': p['pop'][year],
                'supporting_2009_sql_code_literal': p['code8'],
                'supporting_2011_dbf_code_literal': p['code11'],
                'supporting_2011_dbf_raw_point_distance_km': '0',
                'historical_identity_asserted': '2002 and 2010 rows only; no 2021 edge',
                'native_identifier_binding_asserted': 'exact 2009 classifier-to-2011 GeoKLADR code bridge; no modern provider ID asserted',
                'census_date_measurement_asserted': 'false',
                'point_origin_row_1based': str(p['dbf_record']),
                'point_origin_raw_payload_sha256': EXPECTED['raw_geo'],
                'source_raw_object_level': 'named settlement; typed pgt; selected census row',
                'boundary_comparability': 'not asserted',
                'historical_reuse': 'explicit code-based representative-point continuity across selected 2002 and 2010 locality rows',
                'coordinate_uncertainty_flags_json': json.dumps({'measurement_date_unknown': True,
                    'boundary_comparability_not_asserted': True, '2021_identity_not_asserted': True}, sort_keys=True),
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
            new_points.append(row)

    new_point_ids = [row['point_use_id'] for row in new_points]
    if len(new_point_ids) != len(set(new_point_ids)) or set(new_point_ids) & existing_point_ids:
        raise ValueError('Graph28 point-use identifiers collide with each other or existing non-null IDs')

    OUT.mkdir(parents=True)
    edge_path, point_path = OUT / 'accepted_identity_edges.parquet', OUT / 'accepted_point_uses.parquet'
    ew = pq.ParquetWriter(edge_path, edge_schema, compression='zstd')
    base = pq.ParquetFile(GRAPH27)
    for batch in base.iter_batches(batch_size=25000):
        ew.write_batch(batch)
    ew.write_table(pa.Table.from_pylist(new_edges, schema=edge_schema)); ew.close()
    pw = pq.ParquetWriter(point_path, point_schema, compression='zstd')
    basep = pq.ParquetFile(POINTS27)
    for batch in basep.iter_batches(batch_size=25000):
        pw.write_batch(batch)
    pw.write_table(pa.Table.from_pylist(new_points, schema=point_schema)); pw.close()

    receipt = {
        'status': 'three_bounded_2002_2010_historical_code_bridges_and_six_points_applied',
        'inputs': {key: {'path': str(path), 'sha256': sha(path)} for key, path in input_paths.items()},
        'independent_review': 'same bounded pair-only 2002↔2010 rule used for Graph27 Peski; no 2021 endpoint is required or asserted',
        'new_pairs': [{
            'name': p['name'], 'type': p['type'], 'region': p['region'],
            '2002_id': p[2002], '2010_id': p[2010], 'populations': p['pop'],
            'code_2009_okato': p['code8'], 'code_2011_geokladr': p['code11'],
            'dbf_record_1based': p['dbf_record'], 'dbf_offset_0based': p['dbf_offset'],
            'latitude': p['lat'], 'longitude': p['lon'], 'boundary_comparability_asserted': False,
            'population_comparability_asserted': False, '2021_identity_edge_admitted': False,
        } for p in PAIRS],
        'selected_population_values_changed': False,
        'added_identity_edges': len(new_edges), 'added_point_uses': len(new_points),
        'same_year_graph_collisions': 0,
        'final_accepted_edge_count': pq.ParquetFile(edge_path).metadata.num_rows,
        'final_point_use_count': pq.ParquetFile(point_path).metadata.num_rows,
        'outputs': {'accepted_identity_edges.parquet': {'path': str(edge_path), 'sha256': sha(edge_path)},
                    'accepted_point_uses.parquet': {'path': str(point_path), 'sha256': sha(point_path)}},
        'limitations': [
            'GeoKLADR is a 2011 representative point; measurement date and positional uncertainty are unknown.',
            'The 2010 values remain secondary confidentiality-protected values with exact scope unverified.',
            'No 2021 endpoint is connected; any 2021 homonym, type transition, or potential successor requires separate evidence.',
            'Identity and coordinates do not imply comparable population boundaries.',
        ],
    }
    (OUT / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
