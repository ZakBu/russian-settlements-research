#!/usr/bin/env python3
"""Reconcile the old 923 Wikidata pair candidates with the current Graph24."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path('/workspace/russian-settlements-research')
WORK = Path('/workspace/settlements-work/continuation_20261004')
PAIRS = WORK / 'independent_review/wd_population_signatures_final923/eligible_qid_source_pairs.csv'
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EDGES = WORK / 'accepted_graph24_anapa_20261005/accepted_identity_edges.parquet'
POINTS = WORK / 'accepted_graph24_anapa_20261005/accepted_point_uses.parquet'
RESIDUAL = WORK / 'accepted_graph24_anapa_20261005/scoped_joint_residual.parquet'
ADDITIONS = ROOT / 'research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths/additions.csv'
OUT = ROOT / 'research_rebuild/evidence/mass_joint_20261004/actual_observed_year_paths'


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    pair = pd.read_csv(PAIRS, low_memory=False)
    assert len(pair) == 923 and pair.qid.is_unique
    selected = pd.read_parquet(SELECTED, columns=[
        'source_record_id', 'census_year', 'population', 'is_additive_settlement_record',
    ])
    selected = selected[selected.is_additive_settlement_record.fillna(False)].copy()
    selected['source_record_id'] = selected.source_record_id.astype(str)
    selected_by_id = selected.set_index('source_record_id')

    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    edges = pd.read_parquet(EDGES, columns=['from_source_record_id', 'to_source_record_id'])
    for left, right in edges.itertuples(index=False, name=None):
        union(str(left), str(right))

    years_by_component: dict[str, set[int]] = defaultdict(set)
    for row in selected.itertuples(index=False):
        sid = str(row.source_record_id)
        if sid in parent:
            years_by_component[find(sid)].add(int(row.census_year))

    point_rows = pd.read_parquet(POINTS, columns=['target_source_record_id'])
    point_ids = set(point_rows.target_source_record_id.astype(str))
    residual_ids = set(pd.read_parquet(RESIDUAL, columns=['source_record_id']).source_record_id.astype(str))
    additions_ids = set(pd.read_csv(ADDITIONS, usecols=['source_record_id']).source_record_id.astype(str))

    rows = []
    for record in pair.itertuples(index=False):
        ids = {
            2002: str(record.old_2002_source_record_id),
            2010: str(record.old_2010_source_record_id),
            2021: str(record.current_source_record_id),
        }
        roots = {year: find(sid) for year, sid in ids.items()}
        component_years = set(years_by_component.get(roots[2021], set()))
        selected_rows = {year: selected_by_id.loc[sid] for year, sid in ids.items()}
        assert all(int(selected_rows[year].census_year) == year for year in ids)
        assert len(set(roots.values())) == 1, f'pair not in one current component: {record.qid}'
        assert component_years == {2002, 2010, 2021}, (record.qid, component_years)
        rows.append({
            'qid': str(record.qid),
            'source_2002': ids[2002],
            'selected_population_2002': int(selected_rows[2002].population),
            'source_2010': ids[2010],
            'selected_population_2010': int(selected_rows[2010].population),
            'source_2021': ids[2021],
            'selected_population_2021': int(selected_rows[2021].population),
            'all_three_in_accepted_graph24_component': True,
            'component_years': '2002,2010,2021',
            'accepted_point_2002': ids[2002] in point_ids,
            'accepted_point_2010': ids[2010] in point_ids,
            'accepted_point_2021': ids[2021] in point_ids,
            'historical_2002_in_scope_base': ids[2002] not in residual_ids,
            'historical_2010_in_scope_base': ids[2010] not in residual_ids,
            'historical_2002_in_actual_year_additions': ids[2002] in additions_ids,
            'historical_2010_in_actual_year_additions': ids[2010] in additions_ids,
        })
    out_rows = pd.DataFrame(rows)
    assert out_rows[['accepted_point_2002', 'accepted_point_2010', 'accepted_point_2021']].all().all()
    assert out_rows.historical_2002_in_scope_base.all() and out_rows.historical_2010_in_scope_base.all()
    assert not out_rows.historical_2002_in_actual_year_additions.any()
    assert not out_rows.historical_2010_in_actual_year_additions.any()

    output_csv = OUT / 'wikidata_923_graph24_overlap.csv'
    output_json = OUT / 'wikidata_923_graph24_overlap.json'
    out_rows.to_csv(output_csv, index=False)
    result = {
        'status': 'read_only_wikidata_923_candidate_graph24_overlap_measured',
        'canonical_ledgers_changed': False,
        'candidate_pairs': len(pair),
        'source_pair_sha256': sha(PAIRS),
        'graph24_edge_sha256': sha(EDGES),
        'graph24_point_sha256': sha(POINTS),
        'selected_observations_sha256': sha(SELECTED),
        'all_pairs_already_have_accepted_three_census_component_and_points': bool(
            out_rows[['all_three_in_accepted_graph24_component', 'accepted_point_2002',
                      'accepted_point_2010', 'accepted_point_2021']].all().all()),
        'new_joint_coverage_if_candidate_edges_were_applied': {'2002': 0, '2010': 0, '2021': 0},
        'historical_selected_population_in_cohort': {
            '2002': int(out_rows.selected_population_2002.sum()),
            '2010': int(out_rows.selected_population_2010.sum()),
            '2021': int(out_rows.selected_population_2021.sum()),
        },
        'source_p1082_values_are_not_substituted_for_selected_population': True,
        'output_csv': {'path': str(output_csv), 'bytes': output_csv.stat().st_size,
                       'sha256': sha(output_csv)},
        'limitations': [
            'This only measures candidate overlap with Graph24; it does not validate the Wikidata citations.',
            'All candidate source IDs are already covered by existing accepted Graph24 components and points, so these edges would add no coverage.',
            'The earlier conditional gain receipt used an older graph snapshot and is not a current coverage estimate.',
        ],
    }
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
