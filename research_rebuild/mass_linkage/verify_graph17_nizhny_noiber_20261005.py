#!/usr/bin/env python3
"""Independent readback for the bounded Graph17 residual-identity extension."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb


BASE = Path('/workspace/settlements-work/continuation_20261004')
OUT = BASE / 'accepted_graph17_nizhny_noiber_only_20261005'
MEASURE = BASE / 'coverage_graph17_nizhny_noiber_only_20261005'
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
BASE_GRAPH = BASE / 'accepted_mass_sixteenth_large4_point4952/accepted_identity_edges.parquet'
BASE_POINTS = BASE / 'accepted_graph16_biofabriki_point_20261005/accepted_point_uses.parquet'
OLD_SCOPE = BASE / 'root/coverage_graph16_biofabriki_20261005/scoped_joint_coverage.json'
NEW_SCOPE = MEASURE / 'scoped_joint_coverage.json'
APP_COVERAGE = OUT / 'coverage.json'
OLD = '2002:035_e1bf1fa87f_02c_Chechnya.xls:Sheet1:202'
CURRENT = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:161665'
BIO_OLD = '2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:38'
BIO_2010 = '2010:005_888282bccc_13._20Краснодарский_край_2010.xls:КК:1573'
BIO_CURRENT = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:46737'
MAM_OLD = '2002:066_76aa869929_Altai_krai1.xls:Sheet1:1131'
MAM_CURRENT = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:39818'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    graph = OUT / 'accepted_identity_edges.parquet'
    points = OUT / 'accepted_point_uses.parquet'
    receipt = json.loads((OUT / 'receipt.json').read_text())
    assert receipt['status'] == 'applied_manifest_pinned_reviewed_mass_extensions'
    assert receipt['new_identity_rows'] == 1
    assert receipt['new_continuity_point_uses'] == 3

    con = duckdb.connect()
    ids = [OLD, CURRENT, BIO_OLD, BIO_2010, BIO_CURRENT, MAM_OLD, MAM_CURRENT]
    sqlids = ','.join("'" + value.replace("'", "''") + "'" for value in ids)
    selected = con.execute(
        f"SELECT source_record_id,census_year,settlement_name,settlement_type,region_raw,district_raw,population "
        f"FROM read_parquet('{SELECTED}') WHERE source_record_id IN ({sqlids})"
    ).fetchdf().set_index('source_record_id')
    assert int(selected.loc[OLD, 'population']) == 6806
    assert int(selected.loc[CURRENT, 'population']) == 10807
    assert int(selected.loc[BIO_OLD, 'population']) == 681
    assert int(selected.loc[BIO_2010, 'population']) == 2225
    assert int(selected.loc[BIO_CURRENT, 'population']) == 3302

    edge_delta = con.execute(
        f"SELECT decision_id,from_source_record_id,from_year,to_source_record_id,to_year,relation,decision_status "
        f"FROM read_parquet('{graph}') WHERE decision_id='RESIDUAL-PAIR-20261005-01'"
    ).fetchall()
    assert edge_delta == [('RESIDUAL-PAIR-20261005-01', OLD, '2002', CURRENT, '2021', 'same_place', 'checked_rule_accepted')]
    assert con.execute(
        f"SELECT count(*) FROM read_parquet('{graph}') WHERE "
        f"(from_source_record_id='{MAM_OLD}' AND to_source_record_id='{MAM_CURRENT}') OR "
        f"(from_source_record_id='{MAM_CURRENT}' AND to_source_record_id='{MAM_OLD}')"
    ).fetchone()[0] == 0

    prior_ids = {r[0] for r in con.execute(f"SELECT target_source_record_id FROM read_parquet('{BASE_POINTS}')").fetchall()}
    additions = con.execute(
        f"SELECT target_source_record_id,target_year,latitude,longitude,coordinate_admission_status,"
        f"coordinate_measurement_date_unknown,boundary_comparability_asserted,"
        f"inference_modern_point_use_target_source_record_id FROM read_parquet('{points}')"
    ).fetchall()
    added = [r for r in additions if r[0] not in prior_ids]
    assert {r[0] for r in added} == {OLD, BIO_OLD, BIO_2010}
    noiber = next(r for r in added if r[0] == OLD)
    carrier = con.execute(
        f"SELECT latitude,longitude FROM read_parquet('{points}') WHERE target_source_record_id='{CURRENT}'"
    ).fetchone()
    assert (noiber[2], noiber[3]) == carrier
    assert noiber[4] == 'reviewed_extension_rule_accepted' and noiber[5] is True and noiber[6] is False
    assert noiber[7] == CURRENT

    old_cov, new_cov = json.loads(OLD_SCOPE.read_text()), json.loads(NEW_SCOPE.read_text())
    app_cov = json.loads(APP_COVERAGE.read_text())
    expected = {
        '2002': (141175983, 141176664, 2539081, 2538400),
        '2010': (139393995, 139396220, 2033976, 2031751),
        '2021': (144649450, 144649450, 1060852, 1060852),
    }
    metrics = {}
    for year, (before, after, gap_before, gap_after) in expected.items():
        prior = old_cov['results'][year]
        now = new_cov['results'][year]
        assert prior['available_scope_joint_population'] == before
        assert now['available_scope_joint_population'] == after
        assert prior['remaining_population_to_99'] == gap_before
        assert now['remaining_population_to_99'] == gap_after
        metrics[year] = {
            'available_scope_joint_population': after,
            'available_scope_joint_percent': now['available_scope_joint_percent'],
            'change_people': after - before,
            'remaining_to_99': gap_after,
            'strict_NP_joint_population': now['strict_NP_joint_population'],
            'strict_NP_joint_percent': now['strict_NP_joint_population'] / now['control_population'] * 100,
        }
        app_metric = next(row for row in app_cov['census_metrics'] if int(row['year']) == int(year))
        other = app_metric['axes']['joint_admitted_coordinate_and_other_census']
        metrics[year]['ordinary_NP_coordinate_and_at_least_one_other_census'] = {
            'population': other['known_population'],
            'official_control_percent': other['official_control_population_fraction'] * 100,
        }

    result = {
        'status': 'independent_readback_passed_graph17_bounded_extension',
        'accepted_identity_delta': [{'from_source_record_id': OLD, 'to_source_record_id': CURRENT, 'relation': 'same_place'}],
        'accepted_population_changes': 0,
        'point_use_delta': [r[0] for r in added],
        'new_identity_edges': receipt['new_identity_rows'],
        'new_continuity_points': receipt['new_continuity_point_uses'],
        '2010_nizhny_noiber': 'held; protected 6784 remains unbound to the 2021 entity',
        'boundary_comparability_asserted': False,
        'historical_coordinate_measurement_asserted': False,
        'coverage': metrics,
        'mamontovo_hold': 'excluded from this application; 2010 and 2021 accepted point witnesses are 61.8489 km apart',
        'input_sha256': {
            str(p): sha(p) for p in [SELECTED, BASE_GRAPH, BASE_POINTS, graph, points,
                                     OLD_SCOPE, NEW_SCOPE, APP_COVERAGE, OUT/'receipt.json']
        },
        'output_sha256': {'accepted_identity_edges.parquet': sha(graph), 'accepted_point_uses.parquet': sha(points)},
    }
    path = MEASURE / 'independent_readback.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
