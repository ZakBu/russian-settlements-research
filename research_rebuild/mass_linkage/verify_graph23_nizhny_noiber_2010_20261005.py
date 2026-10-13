#!/usr/bin/env python3
"""Independent exact-source and coverage readback for Graph23 Noyber."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

ROOT = Path('/workspace')
REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / 'research_rebuild/evidence/mass_joint_20261004/graph23_nizhny_noiber_2010_point'
BASE = ROOT / 'settlements-work/continuation_20261004'
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH22 = BASE / 'accepted_graph22_krasnodar_20261005/accepted_identity_edges.parquet'
POINTS22 = BASE / 'accepted_graph22_krasnodar_20261005/accepted_point_uses.parquet'
GRAPH23 = BASE / 'accepted_graph23_nizhny_noiber_2010_20261005/accepted_identity_edges.parquet'
POINTS23 = BASE / 'accepted_graph23_nizhny_noiber_2010_20261005/accepted_point_uses.parquet'
LONG22 = BASE / 'root/long_graph22_krasnodar_komarovskiy_patch_20261005/settlements_long_refreshed.parquet'
LONG23 = BASE / 'root/long_graph23_nizhny_noiber_patch_v2_20261005/settlements_long_refreshed.parquet'
OLD = '2002:035_e1bf1fa87f_02c_Chechnya.xls:Sheet1:202'
MID = '2010:002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls:СК:1568'
NOW = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:161665'
DECISION = 'RESIDUAL-PAIR-20261005-02'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> None:
    graph_receipt = json.loads((GRAPH23.parent / 'receipt.json').read_text())
    point_receipt = json.loads((POINTS23.parent / 'point_application_receipt.json').read_text())
    long_receipt = json.loads((LONG23.parent / 'refresh_receipt.json').read_text())
    axes = json.loads((EVIDENCE / 'coverage_axes.json').read_text())
    scoped = json.loads((EVIDENCE / 'scoped_joint_coverage.json').read_text())
    con = duckdb.connect(config={'threads': '1', 'memory_limit': '2GB'})

    assert graph_receipt['status'] == 'applied_bounded_independent_case_review_identity_extension'
    assert graph_receipt['new_identity_rows'] == 1 and graph_receipt['new_point_uses'] == 0
    assert point_receipt['new_point_uses'] == 1
    edge = con.execute(
        'SELECT relation,from_source_record_id,from_year,to_source_record_id,to_year,decision_status '
        'FROM read_parquet(?) WHERE decision_id=?', [str(GRAPH23), DECISION]
    ).fetchall()
    assert edge == [('same_place', MID, '2010', NOW, '2021', 'independent_case_review_accepted')]
    assert con.execute(
        'SELECT count(*) FROM read_parquet(?) WHERE from_source_record_id=? OR to_source_record_id=?',
        [str(GRAPH23), MID, MID],
    ).fetchone()[0] == 1

    selected = con.execute(
        'SELECT census_year,population,population_value_quality,oktmo,settlement_type '
        'FROM read_parquet(?) WHERE source_record_id=?', [str(SELECTED), MID]
    ).fetchone()
    assert selected == (2010, 6784.0, 'secondary_confidentiality_protected_value_exact_scope_unverified', None, 'село')
    point_rows = con.execute(
        'SELECT target_year,latitude,longitude,coordinate_admission_status,direct_historical_coordinate_measurement,'
        'boundary_comparability_asserted,population_scope_comparability_asserted,target_population,'
        'target_population_value_quality FROM read_parquet(?) WHERE target_source_record_id IN (SELECT unnest(?))',
        [str(POINTS23), [OLD, MID, NOW]],
    ).fetchall()
    assert len(point_rows) == 3
    pt = {r[0]: r for r in point_rows}
    for year in ('2002', '2010', '2021'):
        assert pt[year][3] == 'reviewed_extension_rule_accepted'
    assert pt['2010'][1:3] == pt['2021'][1:3] == pt['2002'][1:3]
    assert pt['2010'][4:7] == (False, False, False)
    assert pt['2010'][7:] == (6784.0, 'secondary_confidentiality_protected_value_exact_scope_unverified')

    current = con.execute(
        'SELECT count(*),count(DISTINCT observation_id),count(*) FILTER(WHERE record_type=\'census\'),'
        'sum(population_value) FILTER(WHERE record_type=\'census\') FROM read_parquet(?)', [str(LONG23)]
    ).fetchone()
    baseline = con.execute(
        'SELECT count(*),count(DISTINCT observation_id),count(*) FILTER(WHERE record_type=\'census\'),'
        'sum(population_value) FILTER(WHERE record_type=\'census\') FROM read_parquet(?)', [str(LONG22)]
    ).fetchone()
    assert current == baseline == (865395, 865395, 465800, 434700152.0)
    assert long_receipt['exact_observation_ids_replaced'] == 3
    assert long_receipt['base_only_rows_preserved'] == 865392
    patched = con.execute(
        'SELECT source_record_id,entity_id,latitude,longitude,census_full_chain '
        'FROM read_parquet(?) WHERE source_record_id IN (SELECT unnest(?))', [str(LONG23), [OLD, MID, NOW]]
    ).fetchall()
    assert len(patched) == 3 and {r[0] for r in patched} == {OLD, MID, NOW}
    assert len({r[1] for r in patched}) == 1 and all(r[4] for r in patched)
    assert len({(r[2], r[3]) for r in patched}) == 1

    expected_scope = {
        '2002': (141200768, 97.26799455172687, 2514296),
        '2010': (139417460, 97.59263657352017, 2010511),
        '2021': (144693986, 98.30948422995638, 1016316),
    }
    scope_readback = {}
    for year, (population, percent, gap) in expected_scope.items():
        item = scoped['results'][year]
        assert item['available_scope_joint_population'] == population
        assert abs(item['available_scope_joint_percent'] - percent) < 1e-10
        assert item['remaining_population_to_99'] == gap
        scope_readback[year] = {'joint_population': population, 'percent': percent, 'gap_to_99': gap}
    expected_axes = {'2002': (125037427, 126093944), '2010': (122318695, 123665702),
                     '2021': (122869344, 124652227)}
    axis_readback = {}
    for row in axes['census_metrics']:
        y = str(row['year'])
        full, other = expected_axes[y]
        assert row['axes']['joint_admitted_coordinate_and_full_chain']['known_population'] == full
        assert row['axes']['joint_admitted_coordinate_and_other_census']['known_population'] == other
        axis_readback[y] = {'coordinate_plus_other_census': other, 'coordinate_plus_full_chain': full}

    files = [SELECTED, GRAPH22, POINTS22, GRAPH23, POINTS23, LONG22, LONG23,
             EVIDENCE / 'graph_application_receipt.json', EVIDENCE / 'point_application_receipt.json',
             EVIDENCE / 'independent_identity_review.json', EVIDENCE / 'coverage_axes.json',
             EVIDENCE / 'scoped_joint_coverage.json', EVIDENCE / 'long_refresh_receipt.json']
    result = {
        'status': 'independent_graph23_source_point_scope_and_full_long_readback_passed',
        'decision_id': DECISION,
        'accepted_link': {'from': MID, 'to': NOW, 'relation': 'same_place'},
        'point_use': {'target': MID, 'coordinate': [pt['2010'][1], pt['2010'][2]],
                      'inference': 'accepted same-place continuity from 2021; 2002 concordant',
                      'census_date_measurement': False},
        'population_row_unchanged': {'2010_value': selected[1], 'quality': selected[2],
                                     'conflicting_official_primary': 6780},
        'long_readback': {'rows': current[0], 'census_rows': current[2],
                          'selected_census_population': int(current[3]), 'patched_ids': 3},
        'coverage_scope_aware': scope_readback,
        'coverage_strict_axes': axis_readback,
        'input_sha256': {str(path): sha(path) for path in files},
        'accepted_graph_edge_rows': graph_receipt['accepted_graph_rows'],
        'accepted_point_use_rows': point_receipt['accepted_point_rows'],
        'conclusions': ['The 2010 identity and inferred point are admitted for this exact source row.',
                        'The selected 2010 population remains protected secondary and does not equal the cited primary value.',
                        'Population-boundary comparability remains unknown.',
                        'The 99% scope-aware target remains unmet in all three census years.'],
    }
    out = EVIDENCE / 'independent_readback.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
