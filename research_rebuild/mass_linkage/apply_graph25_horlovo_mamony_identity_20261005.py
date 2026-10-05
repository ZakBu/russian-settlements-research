#!/usr/bin/env python3
"""Apply four independently reviewed identity edges for Horlovo and Mamony.

This bounded extension only appends same-place edges to an immutable Graph24
snapshot. Population values, accepted points, population-scope comparability,
and historical event dates are left unchanged/unknown.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path('/workspace')
BASE = ROOT / 'settlements-work/continuation_20261004'
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH24 = BASE / 'accepted_graph24_anapa_20261005/accepted_identity_edges.parquet'
POINTS24 = BASE / 'accepted_graph24_anapa_20261005/accepted_point_uses.parquet'
RESIDUAL24 = BASE / 'accepted_graph24_anapa_20261005/scoped_joint_residual.parquet'
EVIDENCE = Path(__file__).resolve().parents[1] / 'evidence/mass_joint_20261004/actual_observed_year_paths/residual_case_reviews_20261005'
HORLOVO = EVIDENCE / 'horlovo/decision.json'
MAMONY = EVIDENCE / 'mamony_strugi/decision.json'
STRUGI = EVIDENCE / 'strugi/adjudication.json'
RAW_2021 = Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
OUT = BASE / 'accepted_graph25_bounded_cases_20261005'

HORLOVO_IDS = [
    '2002:1_TOM_01_04.xls:0:1080',
    '2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:8353',
    '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:65692',
]
MAMONY_IDS = [
    '2002:070_48ec6f4a77_Irkut_obl_new.xls:Sheet1:393',
    'ROSSTAT2010:T5:p183:l43',
    '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:24325',
]
STRUGI_IDS = [
    '2002:1_TOM_01_04.xls:0:3213',
    'ROSSTAT2010:T5:p71:l47',
    '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:108423',
]
EDGES = [
    ('GRAPH25-HORLOVO-2002-2010', HORLOVO_IDS[0], HORLOVO_IDS[1], 2002, 2010, 'horlovo'),
    ('GRAPH25-HORLOVO-2010-2021', HORLOVO_IDS[1], HORLOVO_IDS[2], 2010, 2021, 'horlovo'),
    ('GRAPH25-MAMONY-2002-2010', MAMONY_IDS[0], MAMONY_IDS[1], 2002, 2010, 'mamony'),
    ('GRAPH25-MAMONY-2010-2021', MAMONY_IDS[1], MAMONY_IDS[2], 2010, 2021, 'mamony'),
    ('GRAPH25-STRUGI-2002-2010', STRUGI_IDS[0], STRUGI_IDS[1], 2002, 2010, 'strugi'),
    ('GRAPH25-STRUGI-2010-2021', STRUGI_IDS[1], STRUGI_IDS[2], 2010, 2021, 'strugi'),
]
EXPECTED = {
    'selected': '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
    'graph24': '31773a37a3d48488c955bb84d644f24b434fadcc4dc587400c9ba1db20597fc3',
    'points24': 'c3970a406c45b0478d012150e5597e1f008ef86b7fe3ba866e311a9a0ae62e63',
    'residual24': '669d2755db4c13504024d8d80cd899013886587bd7dad10d5759954c5d59750f',
    'horlovo_review': 'f802e06ffd797b959be5b86a6734ae738d9443bdef1ee8e581ece0a4b46aa15f',
    'mamony_review': 'e0274f2411bc646c97df281c2567b0cb915e231ebed1e760f205d8ffbee3b63f',
    'strugi_review': '768934b87aed4de39fa2c582e23970c4eb8c322ef1d9907c70609969769c3e79',
    'raw_2021': '86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14',
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


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f'immutable output already exists: {OUT}')
    pins = {'selected': SELECTED, 'graph24': GRAPH24, 'points24': POINTS24,
            'residual24': RESIDUAL24, 'horlovo_review': HORLOVO, 'mamony_review': MAMONY,
            'strugi_review': STRUGI, 'raw_2021': RAW_2021}
    for key, path in pins.items():
        got = sha(path)
        assert got == EXPECTED[key], f'{key} pin mismatch: {got}'
    horlovo_decision = json.loads(HORLOVO.read_text())
    mamony_decision = json.loads(MAMONY.read_text())
    strugi_decision = json.loads(STRUGI.read_text())
    assert len(horlovo_decision['candidate_new_edges']) == 2
    assert len(mamony_decision['cases'][0]['edge_proposals']) == 2
    assert strugi_decision['historical_identity_assessment']['status'].startswith('source_supported_three_date_same_place_candidate')

    con = duckdb.connect(config={'threads': '1', 'memory_limit': '2GB'})
    ids = HORLOVO_IDS + MAMONY_IDS + STRUGI_IDS
    rows = con.execute(
        'SELECT source_record_id,census_year,settlement_name,settlement_type,region_norm,population,'
        'population_value_quality,is_additive_settlement_record,population_scope '
        'FROM read_parquet(?) WHERE source_record_id IN (SELECT unnest(?))',
        [str(SELECTED), ids],
    ).fetchdf().set_index('source_record_id')
    assert set(rows.index.astype(str)) == set(ids)
    expected_rows = {
        HORLOVO_IDS[0]: (2002, 'Хорлово', 'пгт', 'московская', 3884),
        HORLOVO_IDS[1]: (2010, 'Хорлово', 'пгт', 'московская', 7850),
        HORLOVO_IDS[2]: (2021, 'Хорлово', 'пгт', 'московская', 3714),
        MAMONY_IDS[0]: (2002, 'Мамоны', 'село', 'иркутская', 1642),
        MAMONY_IDS[1]: (2010, 'Мамоны', 'село', 'иркутская', 3154),
        MAMONY_IDS[2]: (2021, 'Мамоны', 'село', 'иркутская', 7272),
        STRUGI_IDS[0]: (2002, 'Струги Красные', 'пгт', 'псковская', 8762),
        STRUGI_IDS[1]: (2010, 'Струги Красные', 'пгт', 'псковская', 8447),
        STRUGI_IDS[2]: (2021, 'Струги Красные', 'пгт', 'псковская', 4871),
    }
    for sid, expected in expected_rows.items():
        r = rows.loc[sid]
        observed = (int(r.census_year), str(r.settlement_name), str(r.settlement_type),
                    str(r.region_norm), int(r.population))
        assert observed == expected, (sid, observed, expected)
        assert bool(r.is_additive_settlement_record)

    residual_ids = set(con.execute(
        'SELECT source_record_id FROM read_parquet(?)', [str(RESIDUAL24)]
    ).fetchdf().source_record_id.astype(str))
    assert set(ids).issubset(residual_ids), 'case rows must all be outside the frozen Graph24 joint base'
    point_ids = set(con.execute('SELECT target_source_record_id FROM read_parquet(?)', [str(POINTS24)]).fetchdf().iloc[:, 0].astype(str))
    no_point_ids = set(HORLOVO_IDS + MAMONY_IDS)
    assert no_point_ids.issubset(point_ids), 'Horlovo/Mamony already have accepted points; do not duplicate'
    assert STRUGI_IDS[0] in point_ids and not set(STRUGI_IDS[1:]).intersection(point_ids)

    base_schema = pq.read_schema(GRAPH24)
    existing = con.execute(
        'SELECT decision_id,from_source_record_id,to_source_record_id,relation,decision_status '
        'FROM read_parquet(?)', [str(GRAPH24)]
    ).fetchdf()
    active_existing = existing.loc[existing.decision_status.isin(ACCEPTED) & existing.relation.eq('same_place')]
    assert not set(ids).intersection(set(active_existing.from_source_record_id.astype(str)) | set(active_existing.to_source_record_id.astype(str))), \
        'a target endpoint already participates in an accepted identity edge; review collision first'
    assert set(existing.decision_id.astype(str)).isdisjoint({e[0] for e in EDGES})
    assert existing.loc[existing.decision_status.isin(ACCEPTED), 'relation'].eq('same_place').all()

    additions = []
    for decision_id, source_id, target_id, y0, y1, case in EDGES:
        review = HORLOVO if case == 'horlovo' else MAMONY if case == 'mamony' else STRUGI
        rule = ('independent_exact_typed_rows_unique_2009_OKATO_2011_GeoKLADR_point_and_event_aware_identity_review_v1'
                if case == 'horlovo' else
                'independent_primary_rows_unique_historical_OKATO_classifier_current_OKTMO_FIAS_and_point_continuity_v1'
                if case == 'mamony' else
                'independent_primary_census_rows_classifier_separation_current_native_OKTMO_FIAS_and_point_pair_review_v1')
        scope_note = (
            'Identity only. Horlovo pgt remains the same named physical locality; Fosforitny is reported incorporated by 2004 and restored by 2019. Exact legal dates and census polygons are not verified. Selected population comparability is false; 2010 selected 7850 remains protected and distinct from official Table 5 7875.'
            if case == 'horlovo' else
            'Identity only. Exact published population values are retained; growth is not explained by the bounded review. Population boundary comparability is unasserted; historical OKATO/GeoKLADR code is not represented as historical OKTMO.'
            if case == 'mamony' else
            'Identity only. Exact typed pgt rows and separate classifier identities support continuity. Historical 2002/2010 populations and 2021 population remain source-specific; boundary/population comparability is unasserted. The legacy successor code resolves to a coexisting different locality and is scoped to this exact candidate only.'
        )
        row = {name: None for name in base_schema.names}
        row.update({
            'decision_id': decision_id,
            'relation': 'same_place',
            'from_source_record_id': source_id,
            'from_year': str(y0),
            'to_source_record_id': target_id,
            'to_year': str(y1),
            'decision_class': 'independent_case_specific_identity_review',
            'decision_status': 'independent_case_review_accepted',
            'decision_rule': rule,
            'reviewer': 'independent bounded source review; root application',
            'reviewed_at': '2026-10-05',
            'evidence_uri': str(review),
            'evidence_sha256': sha(review),
            'population_scope_interpretation': scope_note,
            'selection_projection_status': 'active_endpoints_selected',
            'application_review_id': f'graph25_{case}_identity_review_20261005',
            'application_review_sha256': sha(review),
            'boundary_comparability_asserted': False,
            'population_comparability_asserted': False,
        })
        additions.append(row)

    addition_table = pa.Table.from_pylist(additions, schema=base_schema)
    OUT.mkdir(parents=True)
    target = OUT / 'accepted_identity_edges.parquet'
    writer = pq.ParquetWriter(target, base_schema, compression='zstd')
    base = pq.ParquetFile(GRAPH24)
    for batch in base.iter_batches(batch_size=25_000):
        writer.write_batch(batch)
    writer.write_table(addition_table)
    writer.close()
    assert pq.ParquetFile(target).metadata.num_rows == base.metadata.num_rows + len(additions)

    # Full selected-row graph collision check, including every pre-existing
    # accepted component and the four new edges.
    all_ids = con.execute('SELECT source_record_id,census_year FROM read_parquet(?)', [str(SELECTED)]).fetchall()
    year_by_id = {str(sid): int(year) for sid, year in all_ids}
    parent = {sid: sid for sid in year_by_id}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    active = con.execute(
        "SELECT from_source_record_id,to_source_record_id FROM read_parquet(?) "
        "WHERE relation='same_place' AND decision_status IN "
        "('checked_rule_accepted','checked_rule_accepted_redundant_graph_connectivity_effect',"
        "'accepted_rule_family_after_independent_sample_review','case_specific_independent_review_accepted',"
        "'case_review_accepted','independent_case_review_accepted','accepted_case_specific')",
        [str(target)],
    ).fetchall()
    for a, b in active:
        a, b = str(a), str(b)
        assert a in parent and b in parent
        union(a, b)
    years_by_component = {}
    for sid, year in year_by_id.items():
        root = find(sid)
        years_by_component.setdefault(root, []).append(year)
    collision_components = [years for years in years_by_component.values() if len(years) != len(set(years))]
    assert not collision_components, f'accepted graph creates a same-year component: {collision_components[:3]}'
    for triplet in (HORLOVO_IDS, MAMONY_IDS, STRUGI_IDS):
        roots = {find(sid) for sid in triplet}
        years = {year_by_id[sid] for sid in triplet}
        assert len(roots) == 1 and years == {2002, 2010, 2021}

    receipt = {
        'status': 'bounded_case_review_identity_edges_applied_graph25',
        'base_graph24': {'path': str(GRAPH24), 'sha256': sha(GRAPH24), 'rows': base.metadata.num_rows},
        'inputs': {key: {'path': str(path), 'sha256': sha(path)} for key, path in pins.items()},
        'new_identity_edges': [
            {'decision_id': r['decision_id'], 'from': r['from_source_record_id'], 'to': r['to_source_record_id'],
             'relation': 'same_place', 'status': r['decision_status'], 'boundary_comparability_asserted': False}
            for r in additions
        ],
        'new_edge_count': len(additions),
        'new_point_uses': 2,
        'population_values_modified': False,
        'base_point_ledger_modified': False,
        'same_year_graph_collisions': 0,
        'selected_case_rows': {sid: {'year': expected_rows[sid][0], 'name': expected_rows[sid][1],
                                     'population': expected_rows[sid][4],
                                     'quality': str(rows.loc[sid].population_value_quality)} for sid in ids},
        'resulting_observed_years': {'Horlovo': [2002, 2010, 2021], 'Mamony': [2002, 2010, 2021], 'Strugi Krasnye': [2002, 2010, 2021]},
        'outputs': {'accepted_identity_edges.parquet': {'path': str(target), 'sha256': sha(target),
                                                       'rows': pq.ParquetFile(target).metadata.num_rows}},
        'limitations': [
            'No exact historical legal-date or polygon is asserted for the Horlovo/Fosforitny inclusion/restoration note.',
            'The selected 2010 Horlovo count remains protected and differs from official Table 5 (7850 vs 7875).',
            'Mamony population boundary comparability and causes of reported growth remain unasserted.',
            'Strugi current direct coordinate is publisher-row evidence, not a census-date measurement or asserted provider-ID binding.',
            'Strugi 2010 uses the already accepted 2002 GeoKLADR point retrospectively by explicitly admitted same-place continuity; no 2010 coordinate measurement is claimed.',
            'No population or boundary comparability is asserted for any case.',
        ],
    }

    # Add one direct current publisher-row point and one explicitly retrospective
    # continuity use. The 2010 point reuses the already accepted 2002 point only
    # after the two reviewed identity edges above; the source date remains unknown.
    point_schema = pq.read_schema(POINTS24)
    point_additions = []
    point_base_df = con.execute('SELECT * FROM read_parquet(?) WHERE target_source_record_id=?',
                                [str(POINTS24), STRUGI_IDS[0]]).fetchdf().iloc[0].to_dict()
    point_base = {name: (None if pd.isna(point_base_df.get(name)) else point_base_df.get(name))
                  for name in point_schema.names}
    selected_by_id = rows
    raw = con.execute('SELECT * FROM read_parquet(?) WHERE oktmo=? AND object_level=?',
                      [str(RAW_2021), '58656151051', 'Населенный пункт']).fetchdf()
    assert len(raw) == 1
    rawrow = raw.iloc[0]
    assert str(rawrow.object_name) == 'пгт Струги Красные'
    assert str(rawrow.region) == 'Псковская область'
    assert str(rawrow.settlement_fias_id_dadata) == '3d1be85a-9689-4213-899d-974fb642fffe'
    lat, lon = float(rawrow.latitude_dadata), float(rawrow.longitude_dadata)
    assert abs(lat - 58.2699884) < 1e-6 and abs(lon - 29.1074674) < 1e-6
    point_2021 = {name: None for name in point_schema.names}
    point_2021.update({
        'target_source_record_id': STRUGI_IDS[2], 'target_year': 2021,
        'latitude': lat, 'longitude': lon,
        'coordinate_quality': 'independently_reviewed_current_own_locality_source_point',
        'coordinate_source': 'Tochno raw current own-settlement row coordinate fields',
        'coordinate_provider': 'Tochno/DaData coordinate fields',
        'source_name': 'Струги Красные', 'source_type': 'пгт', 'source_region': 'псковская область',
        'source_file': 'data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet',
        'source_row': 108423, 'source_sha256': EXPECTED['raw_2021'],
        'source_locator': 'parquet row 108423; object_level=Населенный пункт; oktmo=58656151051; fias_level_dadata=6',
        'coordinate_provenance': 'Exact raw own-settlement publisher row; coordinate measurement date unknown; provider identifier binding not asserted; no historical measurement or boundary/population comparability asserted.',
        'admission_rule': 'independent exact current own-locality row adjudication; exact name/type/region + native OKTMO + FIAS level 6 + finite source coordinates',
        'provider_binding_status': 'provider identity binding not asserted; raw coordinate carried by Tochno publisher row',
        'provider_fias_binding_status': 'raw FIAS level 6 literal agrees with independently reviewed current row; no claim about coordinate-provider binding',
        'coordinate_admission_status': 'reviewed_case_accepted',
        'coordinate_measurement_date_unknown': True, 'boundary_comparability_asserted': False,
        'population_scope_comparability_asserted': False,
        'coordinate_application_family': 'graph25_strugi_current_point_and_continuity_20261005',
        'review_id': 'independent_strugi_primary_source_adjudication_20261005',
        'application_inference_kind': 'direct_current_publisher_row_coordinate',
        'direct_historical_coordinate_measurement': False,
        'coordinate_source_sha256': EXPECTED['raw_2021'],
        'coordinate_source_locator': 'parquet row 108423; raw current locality record',
        'coordinate_source_file': str(RAW_2021), 'coordinate_source_origin': 'Tochno 2021 raw coordinate fields',
        'coordinate_source_latitude_raw': str(rawrow.latitude_dadata),
        'coordinate_source_longitude_raw': str(rawrow.longitude_dadata),
        'point_origin_file': str(RAW_2021), 'point_origin_sha256': EXPECTED['raw_2021'],
        'point_origin_locator': 'parquet row 108423; native OKTMO=58656151051; FIAS6=3d1be85a-9689-4213-899d-974fb642fffe',
        'point_origin_kind': 'raw_named_typed_current_locality_source_point',
        'coordinate_application_review_sha256': EXPECTED['strugi_review'],
        'admission_allowed': True, 'coordinate_admitted': True, 'point_admitted': True,
        'identity_edge_admitted': False, 'historical_propagation_allowed': True,
        'coordinate_uncertainty_flags_json': json.dumps({'measurement_date_unknown': True, 'provider_coordinate_id_binding_not_asserted': True, 'historical_measurement_not_asserted': True, 'population_boundary_comparability_not_asserted': True}, sort_keys=True),
        'target_source_name_raw': 'Городское население - пгт Струги Красные',
        'target_source_evidence_json': json.dumps({'population': 4871, 'official_locator': 'Rosstat 2021 Table 5 row 7545', 'exact_raw_source_locator': 'parquet row 108423'}, ensure_ascii=False, sort_keys=True),
        'point_use_id': f'graph25-strugi-current:{STRUGI_IDS[2]}',
        'population': 4871,
    })
    point_additions.append(point_2021)
    point_2010 = dict(point_base)
    point_2010.update({
        'target_source_record_id': STRUGI_IDS[1], 'target_year': 2010,
        'source_name': 'Струги Красные', 'source_type': 'пгт', 'source_region': 'псковская область',
        'source_file': 'data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf',
        'source_sha256': '42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3',
        'source_locator': json.dumps({'table':'5','pdf_page_1based':71,'text_line_start_1based':47,'text_line_end_1based':47,'raw_label':'Городское население - пгт Струги Красные (рц)'}, ensure_ascii=False, sort_keys=True),
        'coordinate_quality': 'independently_reviewed_retrospective_named_place_continuity',
        'coordinate_provenance': str(point_base['coordinate_provenance']) + '; retrospectively assigned to the exact 2010 pgt observation through the accepted 2002-to-2010 same_place edge; no 2010 coordinate measurement, provider binding, or population-boundary comparability claimed.',
        'admission_rule': 'bounded independent primary-row identity review plus exact same-place continuity from accepted 2002 GeoKLADR point',
        'coordinate_admission_status': 'reviewed_case_accepted',
        'coordinate_application_family': 'graph25_strugi_current_point_and_continuity_20261005',
        'review_id': 'independent_strugi_primary_source_adjudication_20261005',
        'application_inference_kind': 'retrospective_named_place_point_continuity_from_accepted_2002_point',
        'direct_historical_coordinate_measurement': False,
        'coordinate_measurement_date_unknown': True,
        'coordinate_source_record_id': STRUGI_IDS[0],
        'coordinate_source_provider': 'GeoKLADR historical representative point',
        'coordinate_source_sha256': 'd1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650',
        'coordinate_source_file': '/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf',
        'coordinate_source_locator': 'accepted point ledger 2002 carrier; GeoKLADR DBF record 1based=101457; OKATO2011=58256551000',
        'coordinate_source_origin': 'accepted 2002 locality point; source point itself is a 2011 GeoKLADR representative point',
        'point_origin_file': '/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf',
        'point_origin_sha256': 'd1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650',
        'point_origin_locator': 'DBF_record_1based=101457;DBF_byte_offset_0based=40075825;OKATO2011_raw=58256551000',
        'point_origin_kind': 'raw_named_typed_geo2011_object',
        'coordinate_application_review_sha256': EXPECTED['strugi_review'],
        'inference_modern_point_use_target_source_record_id': STRUGI_IDS[2],
        'inference_identity_path_decision_ids_json': json.dumps(['GRAPH25-STRUGI-2002-2010','GRAPH25-STRUGI-2010-2021']),
        'inference_identity_path_from_source_record_id': STRUGI_IDS[1],
        'inference_identity_path_to_source_record_id': STRUGI_IDS[2],
        'inference_identity_path_edge_count': 1,
        'population_scope_comparability_asserted': False,
        'admission_allowed': True, 'coordinate_admitted': True, 'point_admitted': True,
        'identity_edge_admitted': False, 'historical_propagation_allowed': True,
        'coordinate_uncertainty_flags_json': json.dumps({'measurement_date_unknown': True, 'provider_binding_not_asserted': True, 'historical_coordinate_measurement_not_asserted': True, 'population_boundary_comparability_not_asserted': True}, sort_keys=True),
        'target_source_name_raw': 'Городское население - пгт Струги Красные (рц)',
        'target_source_evidence_json': json.dumps({'population':8447,'official_locator':'Rosstat 2010 Table 5 p.71 l.47'}, ensure_ascii=False, sort_keys=True),
        'point_use_id': f'graph25-strugi-continuity:{STRUGI_IDS[1]}',
        'population': 8447,
    })
    point_additions.append(point_2010)
    for point_row in point_additions:
        for field in point_schema:
            value = point_row.get(field.name)
            if value is None or pd.isna(value):
                point_row[field.name] = None
            elif pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
                point_row[field.name] = str(value)
            elif pa.types.is_boolean(field.type):
                point_row[field.name] = bool(value)
            elif pa.types.is_integer(field.type):
                point_row[field.name] = int(value)
            elif pa.types.is_floating(field.type):
                point_row[field.name] = float(value)
    point_table = pa.Table.from_pylist(point_additions, schema=point_schema)
    point_target = OUT / 'accepted_point_uses.parquet'
    point_writer = pq.ParquetWriter(point_target, point_schema, compression='zstd')
    point_base_file = pq.ParquetFile(POINTS24)
    for batch in point_base_file.iter_batches(batch_size=25_000):
        point_writer.write_batch(batch)
    point_writer.write_table(point_table)
    point_writer.close()
    assert pq.ParquetFile(point_target).metadata.num_rows == point_base_file.metadata.num_rows + 2
    receipt['outputs']['accepted_point_uses.parquet'] = {'path': str(point_target), 'sha256': sha(point_target), 'rows': pq.ParquetFile(point_target).metadata.num_rows}
    receipt['new_point_use_details'] = [
        {'target_source_record_id': STRUGI_IDS[2], 'latitude': lat, 'longitude': lon, 'status': 'reviewed_case_accepted', 'basis': 'exact 2021 raw own-locality source row'},
        {'target_source_record_id': STRUGI_IDS[1], 'latitude': point_2010['latitude'], 'longitude': point_2010['longitude'], 'status': 'reviewed_case_accepted', 'basis': 'retrospective continuity from accepted 2002 point after reviewed identity admission'},
    ]
    receipt['outputs']['accepted_identity_edges.parquet'] = {'path': str(target), 'sha256': sha(target), 'rows': pq.ParquetFile(target).metadata.num_rows}
    (OUT / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
