#!/usr/bin/env python3
"""Independent readback for the bounded Graph24 Anapa point/identity increment."""
from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path

import duckdb

ROOT = Path('/workspace/russian-settlements-research')
EVIDENCE = ROOT / 'research_rebuild/evidence/mass_joint_20261004/graph24_anapa_four_localities'
CONFIG = ROOT / 'config/mass_joint_20261004.json'
REVIEW = Path('/workspace/russian-settlements-research/research_rebuild/evidence/mass_joint_20261004/graph24_anapa_four_localities/review.json')
BASE = Path('/workspace/settlements-work/continuation_20261004/accepted_graph23_nizhny_noiber_2010_20261005')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    review = json.loads(REVIEW.read_text())
    app = json.loads((EVIDENCE / 'graph_application_receipt.json').read_text())
    long_receipt = json.loads((EVIDENCE / 'long_refresh_receipt.json').read_text())
    coverage = json.loads((EVIDENCE / 'coverage_axes.json').read_text())
    scoped = json.loads((EVIDENCE / 'scoped_joint_coverage.json').read_text())
    graph = Path(cfg['working_identity_graph'])
    points = Path(cfg['working_point_uses'])
    full_long = Path(cfg['working_full_long'])
    selected = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
    source_edges = EVIDENCE / 'eligible_edges.csv'
    source_points = EVIDENCE / 'approved_points.csv'
    rcsi = Path('/workspace/settlements-raw/data/raw/coordinate_candidates/rcsi_github_settlements.csv')
    g23 = BASE / 'accepted_identity_edges.parquet'
    p23 = BASE / 'accepted_point_uses.parquet'
    con = duckdb.connect(config={'threads': '1', 'memory_limit': '1GB'})

    cases = review['cases']
    target_ids = {sid for case in cases for sid in case['ids'].values()}
    direct_ids = {case['ids']['2021'] for case in cases}
    expected_continuity = {
        '2002:1_TOM_01_04.xls:0:6411', 'ROSSTAT2010:T5:p135:l51',
        '2002:1_TOM_01_04.xls:0:8707', 'ROSSTAT2010:T5:p178:l51',
    }
    assert app['status'] == 'applied_manifest_pinned_reviewed_mass_extensions'
    assert app['new_identity_rows'] == 4
    assert app['new_direct_point_uses'] == 4
    assert app['new_continuity_point_uses'] == 4
    assert app['source_population_values_modified'] is False
    assert long_receipt['status'] == 'full_long_exact_census_observation_patch_passed'
    assert long_receipt['exact_observation_ids_replaced'] == 18
    assert long_receipt['final_rows'] == 865395
    assert long_receipt['census_rows'] == 465800
    assert int(long_receipt['selected_census_population_sum']) == 434700152
    assert long_receipt['population_values_modified'] is False

    # All prior accepted endpoints remain, each new decision is unique, and the
    # graph has no same-year collisions after joining these exact four pairs.
    assert con.execute('select count(*) from read_parquet(?)', [str(graph)]).fetchone()[0] == 348660
    assert con.execute('select count(*) from read_parquet(?)', [str(g23)]).fetchone()[0] == 348656
    assert con.execute("select count(*) from read_parquet(?) where decision_id like 'graph24-anapa-%'", [str(graph)]).fetchone()[0] == 4
    assert con.execute('select count(distinct target_source_record_id) from read_parquet(?)', [str(points)]).fetchone()[0] == 428168
    assert con.execute('select count(*) from read_parquet(?)', [str(points)]).fetchone()[0] == 428168
    assert con.execute('select count(*) from read_parquet(?)', [str(p23)]).fetchone()[0] == 428160
    pairs = con.execute("select from_source_record_id,to_source_record_id from read_parquet(?) where decision_id like 'graph24-anapa-%'", [str(graph)]).fetchall()
    expected_pairs = {(case['ids']['2010'], case['ids']['2021']) for case in cases}
    assert set(pairs) == expected_pairs

    # Direct points are the four exact RCSI rows. Provider/entity binding,
    # coordinate date, coordinate precision, and boundary equivalence remain
    # unasserted. Gai-Kodzor's disputed old endpoints stay unpointed.
    direct = con.execute("select target_source_record_id,latitude,longitude,coordinate_source,coordinate_measurement_date_unknown,boundary_comparability_asserted from read_parquet(?) where target_source_record_id in (select unnest(?))", [str(points), sorted(direct_ids)]).fetchall()
    assert {x[0] for x in direct} == direct_ids and len(direct) == 4
    assert all(x[3] and x[4] and not x[5] for x in direct)
    # Replay each raw RCSI locator/hash and prove that the joined target was
    # uniquely identified by the comparison-only leading-zero convention.
    rcsi_sha = sha(rcsi)
    assert rcsi_sha == '50317de1174e35fca893f5c8d965d9c7f40d6a60a06149b96672bb1a134268d0'
    raw_lines = rcsi.read_bytes().splitlines(keepends=True)
    direct_by_id = {r[0]: r for r in direct}
    localities = []
    for case in cases:
        row = case['ids']['2021']
        candidate = next(r for r in csv.DictReader((EVIDENCE / 'corridor_and_points.csv').open(encoding='utf-8')) if r['name'] == case['name'])
        line_no = int(candidate['rcsi_line_1based'])
        raw = raw_lines[line_no - 1]
        assert hashlib.sha256(raw.rstrip(b'\r\n')).hexdigest() == case['rcsi']['line_sha256']
        fields = next(csv.reader([raw.decode('utf-8').rstrip('\r\n')], delimiter=';', quotechar='"'))
        assert fields[3] == case['name'] and fields[4] == 'с' and fields[11] == case['oktmo']
        assert direct_by_id[row][1] == float(fields[9]) and direct_by_id[row][2] == float(fields[10])
        native_oktmo = candidate['current_native_oktmo_raw']
        normalized = native_oktmo.zfill(11)
        assert normalized == case['oktmo']
        assert con.execute("select count(*) from read_parquet(?) where census_year=2021 and lpad(cast(oktmo as varchar),11,'0')=?", [str(selected), normalized]).fetchone()[0] == 1
        localities.append(case['name'])
    # The publisher coordinate rejected for these rows is shared across forty
    # selected entries near Anapa; it was never copied into the new RCSI uses.
    assert con.execute("select count(*) from read_parquet(?) where census_year=2021 and abs(latitude-44.8948984)<0.000001 and abs(longitude-37.3162896)<0.000001", [str(selected)]).fetchone()[0] == 40
    all_new_ids = set(con.execute(f"select target_source_record_id from read_parquet('{points}') p where not exists (select 1 from read_parquet('{p23}') b where b.target_source_record_id=p.target_source_record_id)").fetchdf().target_source_record_id.astype(str))
    assert all_new_ids == direct_ids | expected_continuity
    gai_old = cases[2]['ids']['2002']; gai_mid = cases[2]['ids']['2010']
    assert con.execute('select count(*) from read_parquet(?) where target_source_record_id in (select unnest(?))', [str(points), [gai_old, gai_mid]]).fetchone()[0] == 0

    # Read back the exact patched full-long observations and ensure the two
    # Gai-Kodzor historic rows have a chain but no accepted coordinate.
    long_ids = sorted(target_ids | expected_continuity | {
        '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:86565',
        '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:49262',
    })
    rows = con.execute("select observation_id,latitude,longitude,census_full_chain,population_value from read_parquet(?) where observation_id in (select unnest(?))", [str(full_long), ['census:' + x for x in long_ids]]).fetchall()
    assert len(rows) == 18
    assert all(r[3] for r in rows)
    for sid in (gai_old, gai_mid):
        row = next(r for r in rows if r[0] == 'census:' + sid)
        assert row[1] is None and row[2] is None

    axes = {}
    for y in (2002, 2010, 2021):
        metric = next(r for r in coverage['census_metrics'] if r['year'] == y)
        scope = scoped['results'][str(y)]
        axes[str(y)] = {
            'selected_population': metric['selected_known_population'],
            'coordinate_admitted_population': metric['axes']['coordinate_admitted']['known_population'],
            'full_census_chain_population': metric['axes']['full_census_chain']['known_population'],
            'coordinate_and_full_chain_population': metric['axes']['joint_admitted_coordinate_and_full_chain']['known_population'],
            'scope_aware_coordinate_and_available_year_path_population': scope['available_scope_joint_population'],
            'scope_aware_percent': scope['available_scope_joint_percent'],
            'remaining_to_99': scope['remaining_population_to_99'],
        }
    result = {
        'status': 'independent_graph24_anapa_readback_passed',
        'review_status': review['status'],
        'new_identity_edges': 4,
        'new_direct_RCSI_2021_points': 4,
        'RCSI_raw_rows_replayed': localities,
        'RCSI_source_sha256': rcsi_sha,
        'rejected_shared_publisher_coordinate_row_count': 40,
        'new_existing_rule_continuity_points': sorted(expected_continuity),
        'historical_Gai_Kodzor_point_reuse': 'held for 2002 and 2010; dislocated 2011 point conflict remains unresolved',
        'population_values_modified': False,
        'full_long': {'rows': 865395, 'census_rows': 465800, 'census_population_sum': 434700152, 'patched_exact_observations': 18},
        'coverage': axes,
        'artifact_sha256': {str(p): sha(p) for p in [graph, points, full_long]},
    }
    out = EVIDENCE / 'independent_readback.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
