#!/usr/bin/env python3
"""Stream a Graph17 long-table successor while preserving non-core rows.

The refreshed core/secondary projection replaces exact observation IDs in the
prior complete long table. Prior-only Wikidata display rows and the typed
2001/2014 observations are retained as-is. Current 2021 entity anchors are
asserted unchanged, so those scoped event entity IDs remain valid.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb


OLD = Path('/workspace/settlements-work/continuation_20261004/root/long_graph16_complete_20261005_streamed2/settlements_long_graph16_complete_20261005.parquet')
REFRESHED = Path('/workspace/settlements-work/continuation_20261004/root/long_graph17_core_secondary_20261005/settlements_long_with_secondary_history.parquet')
REFRESH_RECEIPT = Path('/workspace/settlements-work/continuation_20261004/root/long_graph17_core_secondary_20261005/run_receipt.json')
GRAPH = Path('/workspace/settlements-work/continuation_20261004/accepted_graph17_nizhny_noiber_only_20261005/accepted_identity_edges.parquet')
POINTS = Path('/workspace/settlements-work/continuation_20261004/accepted_graph17_nizhny_noiber_only_20261005/accepted_point_uses.parquet')
OUT = Path('/workspace/settlements-work/continuation_20261004/root/long_graph17_complete_20261005')
EXPECTED_OLD_ROWS = 865395
EXPECTED_CORE_ROWS = 862926
EXPECTED_OLD_ONLY_ROWS = 2469
EXPECTED_CENSUS_ROWS = 465800
EXPECTED_CENSUS_POPULATION = 434700152


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if OUT.exists():
        raise FileExistsError(OUT)
    receipt = json.loads(REFRESH_RECEIPT.read_text())
    if receipt.get('status') != 'staged_final_config_long_plus_separate_secondary_history_overlay':
        raise ValueError('unexpected core/secondary refresh status')
    if receipt['core_builder']['census_rows'] != EXPECTED_CENSUS_ROWS:
        raise ValueError('Graph17 core census row count changed')
    if receipt['secondary_overlay']['rows'] != EXPECTED_CORE_ROWS - 500320:
        raise ValueError('secondary-history row count changed')
    if sha(GRAPH) != json.loads((GRAPH.parent / 'receipt.json').read_text())['outputs']['accepted_identity_edges.parquet']:
        raise ValueError('Graph17 edge layer does not match its application receipt')
    if sha(POINTS) != json.loads((POINTS.parent / 'receipt.json').read_text())['outputs']['accepted_point_uses.parquet']:
        raise ValueError('Graph17 point layer does not match its application receipt')

    OUT.mkdir(parents=True)
    destination = OUT / 'settlements_long_graph17_complete_20261005.parquet'
    # The anti-join must retain observation IDs for 865k rows; 256 MiB was
    # insufficient even though source scans are streamed. Keep one thread and
    # avoid insertion-order buffers while allowing a bounded 2 GiB hash join.
    con = duckdb.connect(config={'threads': '1', 'memory_limit': '2GB', 'preserve_insertion_order': 'false'})
    con.execute(f"CREATE VIEW old_long AS SELECT * FROM read_parquet('{OLD}')")
    con.execute(f"CREATE VIEW refreshed AS SELECT * FROM read_parquet('{REFRESHED}')")
    old_n = con.execute('SELECT count(*) FROM old_long').fetchone()[0]
    new_n = con.execute('SELECT count(*) FROM refreshed').fetchone()[0]
    if old_n != EXPECTED_OLD_ROWS or new_n != EXPECTED_CORE_ROWS:
        raise ValueError(f'input row count mismatch: old={old_n}, refreshed={new_n}')
    missing = con.execute('''
      SELECT count(*) FROM refreshed n LEFT JOIN old_long o USING (observation_id)
      WHERE o.observation_id IS NULL
    ''').fetchone()[0]
    if missing:
        raise ValueError(f'{missing} refreshed observations are absent from the prior complete table')
    duplicate_new = con.execute('SELECT count(*)-count(DISTINCT observation_id) FROM refreshed').fetchone()[0]
    duplicate_old = con.execute('SELECT count(*)-count(DISTINCT observation_id) FROM old_long').fetchone()[0]
    if duplicate_new or duplicate_old:
        raise ValueError('duplicate observation IDs in pinned source long tables')
    current_entity_changes = con.execute('''
      SELECT count(*) FROM old_long o JOIN refreshed n USING (observation_id)
      WHERE o.record_type='census' AND n.record_type='census'
        AND o.observation_year=2021 AND n.observation_year=2021
        AND o.entity_id IS DISTINCT FROM n.entity_id
    ''').fetchone()[0]
    if current_entity_changes:
        raise ValueError(f'{current_entity_changes} 2021 anchors changed; event-layer remap required')
    extras = con.execute('''
      SELECT record_type,count(*) FROM old_long o
      WHERE NOT EXISTS (SELECT 1 FROM refreshed n WHERE n.observation_id=o.observation_id)
      GROUP BY record_type ORDER BY record_type
    ''').fetchall()
    extra_n = sum(row[1] for row in extras)
    if extra_n != EXPECTED_OLD_ONLY_ROWS:
        raise ValueError(f'prior-only typed/display row count changed: {extra_n}')
    con.execute(f'''
      COPY (
        SELECT * FROM refreshed
        UNION ALL BY NAME
        SELECT o.* FROM old_long o
        WHERE NOT EXISTS (SELECT 1 FROM refreshed n WHERE n.observation_id=o.observation_id)
      ) TO '{destination}' (FORMAT PARQUET, COMPRESSION ZSTD)
    ''')
    final_n = con.execute(f"SELECT count(*) FROM read_parquet('{destination}')").fetchone()[0]
    census = con.execute(f"SELECT count(*),round(sum(population_value)) FROM read_parquet('{destination}') WHERE record_type='census'").fetchone()
    if final_n != EXPECTED_OLD_ROWS or census != (EXPECTED_CENSUS_ROWS, EXPECTED_CENSUS_POPULATION):
        raise ValueError(f'final row/population guard failed: rows={final_n}, census={census}')
    changes = con.execute(f'''
      SELECT source_record_id,entity_id,latitude,longitude,census_full_chain,
        census_2002_status,census_2010_status,census_2021_status
      FROM read_parquet('{destination}') WHERE source_record_id IN (
        '2002:035_e1bf1fa87f_02c_Chechnya.xls:Sheet1:202',
        '2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:38',
        '2010:005_888282bccc_13._20Краснодарский_край_2010.xls:КК:1573')
    ''').fetchall()
    if len(changes) != 3:
        raise ValueError('expected targeted Nizhny Noiber/Biofabriki census rows are absent')
    result = {
        'status': 'graph17_long_complete_refreshed_by_exact_observation_id',
        'old_long': {'path': str(OLD), 'sha256': sha(OLD), 'rows': old_n},
        'refreshed_core_secondary': {'path': str(REFRESHED), 'sha256': sha(REFRESHED), 'rows': new_n},
        'graph17': {'path': str(GRAPH), 'sha256': sha(GRAPH)},
        'point_uses': {'path': str(POINTS), 'sha256': sha(POINTS)},
        'refreshed_core_ids_missing_from_old_long': missing,
        'prior_only_rows_preserved': extra_n,
        'prior_only_record_types': {k: v for k, v in extras},
        'current_2021_entity_anchor_changes': current_entity_changes,
        'final_rows': final_n,
        'census_rows': census[0],
        'selected_census_population_sum': census[1],
        'population_values_modified': False,
        'targeted_readback': [dict(zip(['source_record_id','entity_id','latitude','longitude','census_full_chain','census_2002_status','census_2010_status','census_2021_status'], row)) for row in changes],
        'outputs': {destination.name: {'path': str(destination), 'sha256': sha(destination), 'bytes': destination.stat().st_size}},
    }
    (OUT / 'refresh_receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
