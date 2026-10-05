#!/usr/bin/env python3
"""Apply one reviewed 2010 identity edge to the immutable Graph22 snapshot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path('/workspace')
BASE = ROOT / 'settlements-work/continuation_20261004'
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH = BASE / 'accepted_graph22_krasnodar_20261005/accepted_identity_edges.parquet'
POINTS = BASE / 'accepted_graph22_krasnodar_20261005/accepted_point_uses.parquet'
REVIEW = BASE / 'regions/chechnya_top_residual_graph16_recheck_20261005/source_chain_followup/2010_row_identity_review.json'
OUT = BASE / 'accepted_graph23_nizhny_noiber_2010_20261005'

OLD = '2002:035_e1bf1fa87f_02c_Chechnya.xls:Sheet1:202'
MID = '2010:002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls:СК:1568'
NOW = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:161665'
DECISION = 'RESIDUAL-PAIR-20261005-02'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    assert not OUT.exists(), f'immutable output already exists: {OUT}'
    pins = {
        'selected': (SELECTED, '4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'),
        'graph22': (GRAPH, '36cf7cc785108ce198558f3347a02f7b75e6bdd667a8c4142cd537b0c324115c'),
        'points22': (POINTS, '22acb1205a70d36df44954539069362ce29f296c94664255d1edb8ffc12e4020'),
        'independent_review': (REVIEW, 'c4e2b14cd1a95d99bd8b44e38c31279a6e33e0eea569f7e1456841abc15ee84d'),
    }
    for label, (path, expected) in pins.items():
        got = sha(path)
        assert got == expected, f'{label} hash changed: {got}'

    ids = [OLD, MID, NOW]
    con = duckdb.connect(config={'threads': '1', 'memory_limit': '2GB'})
    rows = con.execute(
        'SELECT source_record_id,census_year,settlement_name,settlement_type,region_raw,population,'
        'population_value_quality,source_sha256,source_file,source_sheet,source_row,oktmo,settlement_name '
        'FROM read_parquet(?) WHERE source_record_id IN (SELECT unnest(?))',
        [str(SELECTED), ids],
    ).fetchdf().set_index('source_record_id')
    assert set(rows.index.astype(str)) == set(ids)
    assert (int(rows.loc[OLD, 'census_year']), int(rows.loc[MID, 'census_year']),
            int(rows.loc[NOW, 'census_year'])) == (2002, 2010, 2021)
    assert int(rows.loc[MID, 'population']) == 6784
    assert rows.loc[MID, 'population_value_quality'] == 'secondary_confidentiality_protected_value_exact_scope_unverified'
    assert rows.loc[MID, 'settlement_name'] == 'Нижний Нойбера'
    assert rows.loc[MID, 'settlement_type'] == 'село'
    assert rows.loc[MID, 'region_raw'] == 'чеченская'
    assert str(rows.loc[NOW, 'oktmo']) == '96610491101'
    assert rows.loc[NOW, 'settlement_name'] == 'Нижний-Нойбер'

    graph = pq.ParquetFile(GRAPH)
    schema = graph.schema_arrow
    edge_state = con.execute(
        'SELECT decision_id,from_source_record_id,to_source_record_id,decision_status '
        'FROM read_parquet(?) WHERE decision_id=? OR from_source_record_id=? OR to_source_record_id=?',
        [str(GRAPH), DECISION, MID, MID],
    ).fetchall()
    assert not edge_state, f'candidate edge already exists or decision ID collides: {edge_state}'
    old_pair = con.execute(
        'SELECT count(*) FROM read_parquet(?) WHERE relation=\'same_place\' AND '
        '((from_source_record_id=? AND to_source_record_id=?) OR '
        '(from_source_record_id=? AND to_source_record_id=?))',
        [str(GRAPH), OLD, NOW, NOW, OLD],
    ).fetchone()[0]
    assert old_pair == 1, 'previously accepted 2002↔2021 path is missing or duplicated'
    point_rows = con.execute(
        'SELECT target_source_record_id,latitude,longitude,coordinate_admission_status '
        'FROM read_parquet(?) WHERE target_source_record_id IN (SELECT unnest(?))',
        [str(POINTS), [OLD, MID, NOW]],
    ).fetchall()
    by_id = {r[0]: r for r in point_rows}
    assert OLD in by_id and NOW in by_id and MID not in by_id
    assert abs(by_id[OLD][1] - by_id[NOW][1]) < 1e-5
    assert abs(by_id[OLD][2] - by_id[NOW][2]) < 1e-5

    # Prove the proposed component has one selected source row per year.
    graph_rows = con.execute(
        'SELECT from_source_record_id,to_source_record_id FROM read_parquet(?)', [str(GRAPH)]
    ).fetchall()
    parent: dict[str, str] = {}
    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for a, b in graph_rows:
        union(str(a), str(b))
    component = {x for x in parent if find(x) == find(NOW)}
    assert {OLD, NOW}.issubset(component) and MID not in component
    component.add(MID)
    component_rows = con.execute(
        'SELECT source_record_id,census_year FROM read_parquet(?) '
        'WHERE source_record_id IN (SELECT unnest(?))', [str(SELECTED), sorted(component)]
    ).fetchall()
    years = [int(r[1]) for r in component_rows]
    assert len(years) == len(set(years)), 'proposed union creates same-year duplicate rows'
    assert set(years) == {2002, 2010, 2021}

    new = {name: None for name in schema.names}
    values = {
        'decision_id': DECISION,
        'relation': 'same_place',
        'from_source_record_id': MID,
        'from_year': '2010',
        'to_source_record_id': NOW,
        'to_year': '2021',
        'decision_class': 'independent_case_specific_identity_review',
        'decision_status': 'independent_case_review_accepted',
        'decision_rule': 'official_2010_source_item_population_and_unique_typed_name_region_plus_exact_OKTMO_bound_physical_entity_v1',
        'reviewer': 'independent_primary_source_review; root application',
        'reviewed_at': '2026-10-05',
        'evidence_uri': str(REVIEW),
        'evidence_sha256': sha(REVIEW),
        'population_scope_interpretation': 'Identity only. The selected 2010 value 6784 remains protected secondary and exact scope unverified; cited official primary census value is 6780. No population-value replacement or census-boundary comparability is asserted.',
        'selection_projection_status': 'active_endpoints_selected',
        'application_review_id': 'nizhny_noiber_2010_row_primary_identity_followup_20261005',
        'application_review_sha256': sha(REVIEW),
    }
    for k, v in values.items():
        if k in new:
            new[k] = v
    addition = pa.Table.from_pylist([new], schema=schema)

    OUT.mkdir(parents=True)
    target = OUT / 'accepted_identity_edges.parquet'
    writer = pq.ParquetWriter(target, schema, compression='zstd')
    for batch in graph.iter_batches(batch_size=25_000):
        writer.write_batch(batch)
    writer.write_table(addition)
    writer.close()
    assert pq.ParquetFile(target).metadata.num_rows == graph.metadata.num_rows + 1
    receipt = {
        'status': 'applied_bounded_independent_case_review_identity_extension',
        'base_graph_rows': graph.metadata.num_rows,
        'accepted_graph_rows': pq.ParquetFile(target).metadata.num_rows,
        'new_identity_rows': 1,
        'new_point_uses': 0,
        'population_values_modified': False,
        'coordinate_ledger_modified': False,
        'candidate_edge': {'decision_id': DECISION, 'relation': 'same_place',
                           'from_source_record_id': MID, 'to_source_record_id': NOW,
                           'from_year': 2010, 'to_year': 2021},
        'resulting_observed_years_in_component': [2002, 2010, 2021],
        '2010_population_retained': 6784,
        '2010_population_quality_retained': str(rows.loc[MID, 'population_value_quality']),
        'coordinate_route': 'Existing accepted 2002 and 2021 points agree within 0.00001 degrees; any 2010 coordinate is a continuity inference only, not a date-specific measurement.',
        'limitations': ['The selected 2010 value remains four persons above the cited official primary 6780.',
                        'Exact scope of the selected protected 2010 value remains unverified.',
                        'Population-boundary comparability across census years is unknown.'],
        'input_pins': {label: {'path': str(path), 'sha256': sha(path)} for label, (path, _) in pins.items()},
        'output_sha256': {'accepted_identity_edges.parquet': sha(target)},
        'script_sha256': sha(Path(__file__)),
    }
    (OUT / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
