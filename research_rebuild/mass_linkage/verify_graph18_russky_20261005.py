#!/usr/bin/env python3
"""Independent exact-row, source-population, and scoped-metric readback for Graph18."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd


ROOT = Path('/workspace/settlements-work/continuation_20261004')
BASE = ROOT / 'accepted_graph17_nizhny_noiber_only_20261005'
OUT = ROOT / 'accepted_graph18_russky_only_20261005'
SCOPED = ROOT / 'coverage_graph18_russky_only_20261005/scoped_joint_coverage.json'
LONG_BASE = ROOT / 'root/long_graph17_complete_20261005/settlements_long_graph17_complete_20261005.parquet'
LONG_RECEIPT = ROOT / 'root/long_graph18_russky_patch_v2_20261005/refresh_receipt.json'
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
REVIEW = ROOT / 'regions/primorye_top_residual_graph16_recheck_20261005/independent_primary_review/russky_2002_2010_2021_identity_review.md'
RUSSKY_2002 = '2002:1_TOM_01_04.xls:0:9926'
RUSSKY_2010 = '2010:009_81f8a0e73c_17._20ДВ_ФО_2010.xls:ДВ:564'
RUSSKY_2021 = '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:100071'


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    base_graph = pd.read_parquet(BASE / 'accepted_identity_edges.parquet')
    graph = pd.read_parquet(OUT / 'accepted_identity_edges.parquet')
    base_points = pd.read_parquet(BASE / 'accepted_point_uses.parquet')
    points = pd.read_parquet(OUT / 'accepted_point_uses.parquet')
    selected = pd.read_parquet(SELECTED)
    receipt = json.loads((OUT / 'receipt.json').read_text())
    application_coverage = json.loads((OUT / 'coverage.json').read_text())
    scoped = json.loads(SCOPED.read_text())
    long_receipt = json.loads(LONG_RECEIPT.read_text())

    if receipt['base_graph_rows'] != 348644 or receipt['accepted_graph_rows'] != 348645:
        raise ValueError('Graph18 graph row counts fail')
    if receipt['new_identity_rows'] != 1 or receipt['new_continuity_point_uses'] != 1:
        raise ValueError('Graph18 increment is not exactly one edge plus one historical point use')
    if len(graph) != 348645 or len(points) != len(base_points) + 1:
        raise ValueError('Graph18 output graph/point layer counts fail')
    edge = graph[(graph.from_source_record_id.astype(str) == RUSSKY_2002) &
                 (graph.to_source_record_id.astype(str) == RUSSKY_2010)]
    if len(edge) != 1 or str(edge.iloc[0].relation) != 'same_place':
        raise ValueError('exact reviewed Русский edge is absent')
    if graph.decision_id.astype(str).duplicated().any():
        raise ValueError('duplicate decision IDs')
    if points.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('duplicate point targets')
    new_targets = set(points.target_source_record_id.astype(str)) - set(base_points.target_source_record_id.astype(str))
    if new_targets != {RUSSKY_2002}:
        raise ValueError(f'unexpected point-use delta: {sorted(new_targets)}')
    point = points.set_index(points.target_source_record_id.astype(str)).loc[RUSSKY_2002]
    if (float(point.latitude), float(point.longitude)) != (43.0224, 131.8601):
        raise ValueError('Русский 2002 inferred coordinate does not match accepted current carrier')
    if point.application_inference_kind != 'sourced_representative_point_reuse_across_accepted_observed_years':
        raise ValueError('Русский 2002 point is not explicitly typed as continuity inference')
    if bool(point.direct_historical_coordinate_measurement) or bool(point.boundary_comparability_asserted):
        raise ValueError('historical date measurement or boundary comparability was incorrectly asserted')
    observed_population = selected.set_index('source_record_id').loc[[RUSSKY_2002, RUSSKY_2010, RUSSKY_2021], 'population'].astype(int).tolist()
    if observed_population != [5204, 4428, 10424]:
        raise ValueError(f'selected population changed: {observed_population}')
    if receipt['source_population_values_modified'] is not False:
        raise ValueError('application receipt does not guarantee population preservation')

    expected_axes = {
        2002: (158072, (152976, 142572124), (140652, 136418794), (140154, 126282838),
               (132843, 125181688), (139439, 126072080), (132265, 125018527)),
        2010: (152314, (149456, 141802484), (135822, 123779504), (135956, 123820956),
               (132843, 122417902), (135062, 123637836), (132296, 122301883)),
        2021: (155414, (154495, 147166731), (151682, 127592317), (143231, 124817142),
               (132843, 122941885), (142229, 124628922), (132301, 122835232)),
    }
    axis_fields = ('coordinate_availability_by_exact_source_route', 'coordinate_admitted',
                   'identity_link_to_other_census', 'full_census_chain',
                   'joint_admitted_coordinate_and_other_census',
                   'joint_admitted_coordinate_and_full_chain')
    axes_readback = {}
    for metric in application_coverage['census_metrics']:
        year = int(metric['year'])
        if year not in expected_axes:
            raise ValueError(f'unexpected measurement year: {year}')
        values = [(metric['axes'][key]['rows'], metric['axes'][key]['known_population']) for key in axis_fields]
        if metric['selected_rows'] != expected_axes[year][0] or tuple(values) != expected_axes[year][1:]:
            raise ValueError(f'coordinate/identity/full-chain axis changed unexpectedly for {year}')
        axes_readback[str(year)] = {'selected_rows': metric['selected_rows'],
            **{key: {'rows': metric['axes'][key]['rows'], 'population': metric['axes'][key]['known_population'],
                     'row_fraction': metric['axes'][key]['row_fraction'],
                     'national_population_fraction': metric['axes'][key]['official_control_population_fraction']}
               for key in axis_fields}}

    expected = {
        '2002': (141181868, 97.25497503970108, 2533196, 125018527),
        '2010': (139400648, 97.5808681235278, 2027323, 122301883),
        '2021': (144659874, 98.28630750216858, 1050428, 122835232),
    }
    metrics = {}
    for year, vals in expected.items():
        row = scoped['results'][year]
        got = (row['available_scope_joint_population'], row['available_scope_joint_percent'],
               row['remaining_population_to_99'], row['strict_NP_joint_population'])
        if got[:1] != vals[:1] or abs(got[1] - vals[1]) > 1e-10 or got[2] != vals[2] or got[3] != vals[3]:
            raise ValueError(f'scoped coverage mismatch for {year}: {got}')
        metrics[year] = {
            'available_scope_joint_population': got[0], 'available_scope_joint_percent': got[1],
            'remaining_to_99': got[2], 'strict_NP_joint_population': got[3],
            'strict_NP_joint_percent': row['strict_NP_joint_population'] / row['control_population'] * 100,
            'strict_NP_full_chain_rows': row['strict_NP_joint_rows'],
        }

    con = duckdb.connect(config={'threads': '1', 'memory_limit': '2GB', 'preserve_insertion_order': 'false'})
    long_path = Path(long_receipt['final']['path'])
    long = con.execute(f"""SELECT source_record_id,entity_id,population_value,latitude,longitude,
      census_full_chain,census_2002_status,census_2010_status,census_2021_status
      FROM read_parquet('{long_path}') WHERE source_record_id IN ('{RUSSKY_2002}','{RUSSKY_2010}','{RUSSKY_2021}')
      ORDER BY observation_year""").fetchdf()
    if len(long) != 3 or not long.census_full_chain.fillna(False).all():
        raise ValueError('full-long exact rows do not show a three-census chain')
    if long.population_value.astype(int).tolist() != observed_population:
        raise ValueError('full-long selected population differs from frozen source')
    if int(long_receipt['final_rows']) != 865395 or int(long_receipt['census_rows']) != 465800 or int(long_receipt['selected_census_population_sum']) != 434700152:
        raise ValueError('full-long row or population controls fail')

    output = {
        'status': 'independent_readback_passed_graph18_russky_bounded_extension',
        'new_identity_edge': {'from': RUSSKY_2002, 'to': RUSSKY_2010, 'relation': 'same_place'},
        'new_point_use': RUSSKY_2002,
        'selected_populations_unchanged_2002_2010_2021': observed_population,
        'point_centroid_caveat_km_between_existing_2010_and_2021_points': 2.0229310777862928,
        'boundary_comparability_asserted': False,
        '2010_selected_population_4428_retained_vs_official_table5_reference_4703': True,
        'separate_quality_axes': axes_readback,
        'coverage': metrics,
        'full_long': {'path': str(long_path), 'sha256': sha(long_path), 'rows': long_receipt['final_rows'],
                      'census_rows': long_receipt['census_rows'], 'population_sum': long_receipt['selected_census_population_sum'],
                      'russky_rows': long.to_dict('records')},
        'input_sha256': {
            'graph17': sha(BASE / 'accepted_identity_edges.parquet'),
            'points17': sha(BASE / 'accepted_point_uses.parquet'),
            'graph18': sha(OUT / 'accepted_identity_edges.parquet'),
            'points18': sha(OUT / 'accepted_point_uses.parquet'),
            'application_receipt': sha(OUT / 'receipt.json'),
            'review': sha(REVIEW), 'scoped_coverage': sha(SCOPED), 'long_receipt': sha(LONG_RECEIPT),
        },
    }
    path = SCOPED.parent / 'independent_readback.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
