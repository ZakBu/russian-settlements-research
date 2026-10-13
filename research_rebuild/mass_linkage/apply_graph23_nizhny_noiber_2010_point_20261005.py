#!/usr/bin/env python3
"""Propagate the convergent accepted named-place point to reviewed Noyber 2010."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research_rebuild.mass_linkage.propagate_continuation_points import stage_point_use

ROOT = Path('/workspace')
BASE = ROOT / 'settlements-work/continuation_20261004'
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
EVIDENCE = ROOT / 'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
BASE_POINTS = BASE / 'accepted_graph22_krasnodar_20261005/accepted_point_uses.parquet'
GRAPH = BASE / 'accepted_graph23_nizhny_noiber_2010_20261005/accepted_identity_edges.parquet'
OUTDIR = BASE / 'accepted_graph23_nizhny_noiber_2010_20261005'
OUT = OUTDIR / 'accepted_point_uses.parquet'
GRAPH_RECEIPT = OUTDIR / 'receipt.json'
REVIEW = BASE / 'regions/chechnya_top_residual_graph16_recheck_20261005/source_chain_followup/2010_row_identity_review.json'

OLD = '2002:035_e1bf1fa87f_02c_Chechnya.xls:Sheet1:202'
MID = '2010:002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls:СК:1568'
NOW = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:161665'
DECISION = 'RESIDUAL-PAIR-20261005-02'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    pins = {
        'selected': (SELECTED, '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'),
        'source_evidence': (EVIDENCE, 'e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327'),
        'graph23': (GRAPH, '3283d85d8686395a01b238ad1a35ba3df9e3cf451efbe732b199e4d59fbe2e06'),
        'graph22_points': (BASE_POINTS, '22acb1205a70d36df44954539069362ce29f296c94664255d1edb8ffc12e4020'),
        'independent_review': (REVIEW, 'c4e2b14cd1a95d99bd8b44e38c31279a6e33e0eea569f7e1456841abc15ee84d'),
        'graph23_receipt': (GRAPH_RECEIPT, '9c717c283490e46ab24990e03636d4c1dc1ad939620e5f79ef279aed4643a40b'),
    }
    for name, (path, expected) in pins.items():
        got = sha(path)
        assert got == expected, f'{name} checksum mismatch: {got}'
    assert not OUT.exists(), f'immutable point ledger already exists: {OUT}'

    con = duckdb.connect(config={'threads': '1', 'memory_limit': '1GB'})
    rows = con.execute(
        'SELECT * FROM read_parquet(?) WHERE source_record_id IN (SELECT unnest(?))',
        [str(SELECTED), [MID, OLD, NOW]],
    ).fetchdf().set_index('source_record_id')
    assert set(rows.index.astype(str)) == {MID, OLD, NOW}
    assert int(rows.loc[MID, 'census_year']) == 2010 and int(rows.loc[MID, 'population']) == 6784
    assert rows.loc[MID, 'population_value_quality'] == 'secondary_confidentiality_protected_value_exact_scope_unverified'
    assert rows.loc[MID, 'population_scope'] == 'settlement'
    edge = con.execute(
        'SELECT from_source_record_id,to_source_record_id,decision_status FROM read_parquet(?) WHERE decision_id=?',
        [str(GRAPH), DECISION],
    ).fetchone()
    assert edge == (MID, NOW, 'independent_case_review_accepted')

    points = pq.ParquetFile(BASE_POINTS)
    point_schema = points.schema_arrow
    prior = con.execute(
        'SELECT target_source_record_id,latitude,longitude FROM read_parquet(?) '
        'WHERE target_source_record_id IN (SELECT unnest(?))',
        [str(BASE_POINTS), [OLD, MID, NOW]],
    ).fetchall()
    by_id = {r[0]: r for r in prior}
    assert OLD in by_id and NOW in by_id and MID not in by_id
    assert abs(by_id[OLD][1] - by_id[NOW][1]) < 1e-5
    assert abs(by_id[OLD][2] - by_id[NOW][2]) < 1e-5

    source_evidence = con.execute(
        'SELECT source_record_id,source_evidence_json FROM read_parquet(?) '
        'WHERE source_record_id IN (SELECT unnest(?))', [str(EVIDENCE), [MID, NOW]]
    ).fetchall()
    ev = {sid: json.loads(blob) for sid, blob in source_evidence}
    assert set(ev) == {MID, NOW}
    assert ev[MID]['legacy_identity_conflict'] is True
    assert ev[MID]['legacy_identity_reasons'] == '["legacy_not_accepted"]'
    assert ev[MID]['legacy_same_year_collision'] is False

    target = rows.loc[MID].copy()
    target['source_record_id'] = MID
    carrier = next(r for r in points.iter_batches(batch_size=25_000) for r in r.to_pylist()
                   if r['target_source_record_id'] == NOW)
    # The point comes from an accepted 2021 source point. The matching accepted
    # 2002 point is an independent same-component spatial concordance check.
    staged = stage_point_use(target, ev[MID], carrier, NOW, ev[NOW], [DECISION])
    staged.update(
        coordinate_admission_status='reviewed_extension_rule_accepted',
        coordinate_quality='automatically_accepted_checked_rule',
        coordinate_application_family='R_reviewed_same_place_sourced_point_continuity_20261004',
        application_inference_kind='sourced_representative_point_reuse_across_accepted_observed_years',
        coordinate_admitted=True,
        point_admitted=True,
        admission_allowed=True,
        review_id='nizhny_noiber_2010_row_primary_identity_followup_20261005',
        application_gate_status='passed_accepted_graph_sourced_point_continuity',
        coordinate_application_review_sha256=sha(REVIEW),
        blocked_conflict_resolution_approved=True,
        blocked_conflict_resolution_rationale=(
            'Exact selected 2010 source row independently bound to the physical place by the official 2010 census '
            'row cited in its Wikidata 2010 population statement, the unique typed name/region, and the entity\'s '
            'distinct OKTMO 96610491101. Resolved only legacy_not_accepted quarantine; no same-year collision.'
        ),
        target_population=6784,
        target_population_scope='settlement',
        target_population_value_quality='secondary_confidentiality_protected_value_exact_scope_unverified',
        target_population_quality_limitation=(
            'Selected 2010 6784 retained; official primary source and Wikidata claim give 6780. '
            'Exact scope of selected protected secondary value remains unverified.'
        ),
    )
    # The frozen ledger intentionally uses string years and nullable Arrow
    # booleans. Normalize the one projected row to the pinned schema.
    for field in point_schema:
        value = staged.get(field.name)
        if value is None:
            continue
        if pa.types.is_string(field.type) and not isinstance(value, str):
            staged[field.name] = str(value)
        elif pa.types.is_integer(field.type):
            staged[field.name] = int(value)
        elif pa.types.is_floating(field.type):
            staged[field.name] = float(value)
        elif pa.types.is_boolean(field.type) and not isinstance(value, bool):
            text = str(value).strip().casefold()
            if text in {'true', '1', '1.0'}:
                staged[field.name] = True
            elif text in {'false', '0', '0.0'}:
                staged[field.name] = False
            else:
                raise ValueError(f'cannot normalize boolean {field.name}: {value!r}')
    table = pa.Table.from_pylist([staged], schema=point_schema)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    writer = pq.ParquetWriter(OUT, point_schema, compression='zstd')
    for batch in points.iter_batches(batch_size=25_000):
        writer.write_batch(batch)
    writer.write_table(table)
    writer.close()
    assert pq.ParquetFile(OUT).metadata.num_rows == points.metadata.num_rows + 1
    assert con.execute(
        'SELECT count(*) FROM read_parquet(?) WHERE target_source_record_id=?', [str(OUT), MID]
    ).fetchone()[0] == 1
    got_point = con.execute(
        'SELECT latitude,longitude,coordinate_admission_status,direct_historical_coordinate_measurement,'
        'boundary_comparability_asserted,population_scope_comparability_asserted,target_population,'
        'target_population_value_quality FROM read_parquet(?) WHERE target_source_record_id=?', [str(OUT), MID]
    ).fetchone()
    assert got_point == (by_id[NOW][1], by_id[NOW][2], 'reviewed_extension_rule_accepted', False, False, False,
                         6784, 'secondary_confidentiality_protected_value_exact_scope_unverified')
    receipt = {
        'status': 'applied_reviewed_same_place_point_continuity_to_2010_row',
        'new_point_uses': 1,
        'base_point_rows': points.metadata.num_rows,
        'accepted_point_rows': pq.ParquetFile(OUT).metadata.num_rows,
        'target_source_record_id': MID,
        'carrier_source_record_id': NOW,
        'path_decision_ids': [DECISION],
        'coordinates': {'latitude': got_point[0], 'longitude': got_point[1]},
        'independent_same_component_spatial_concordance': '2002 accepted point differs by less than 0.00001 degrees',
        'date_specific_2010_coordinate_measurement_asserted': False,
        'provider_identifier_binding_to_2010_asserted': False,
        'boundary_comparability_asserted': False,
        'population_scope_comparability_asserted': False,
        'legacy_quarantine_disposition': 'Only legacy_not_accepted flag resolved for this exact independently reviewed endpoint; no same-year collision was present. Raw legacy conflict fields are retained in target evidence.',
        'population_value_changed': False,
        'population': 6784,
        'population_value_quality': got_point[7],
        'limitations': ['Selected 2010 count is four persons above the cited official primary count of 6780.',
                        'Selected protected value scope is unverified.',
                        'No census-boundary or population comparability claim.'],
        'input_pins': {name: {'path': str(path), 'sha256': sha(path)} for name, (path, _) in pins.items()},
        'output_sha256': {'accepted_point_uses.parquet': sha(OUT)},
        'script_sha256': sha(Path(__file__)),
    }
    (OUTDIR / 'point_application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
