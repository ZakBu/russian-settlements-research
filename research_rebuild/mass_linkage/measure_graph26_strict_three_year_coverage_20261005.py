#!/usr/bin/env python3
"""Reproduce strict point + accepted full 2002/2010/2021 chain coverage.

Graph24 is reconstructed semantically from the pinned Graph25 snapshot by
removing only the six Graph25 identity decisions and its two Strugi point uses.
This gives a like-for-like marginal comparison without rewriting frozen data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from research_rebuild.mass_linkage.coverage import identity_sets

ROOT = Path('/workspace')
SELECTED = ROOT / 'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH25 = ROOT / 'settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_identity_edges.parquet'
POINTS25 = ROOT / 'settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet'
POINTS26 = Path('/tmp/graph26_gaikodzor_continuity_20261005/accepted_point_uses.parquet')
OUTPUT = Path('/tmp/graph26_strict_three_year_coverage_20261005.json')
CONTROLS = {2002: 145_166_731, 2010: 142_856_536, 2021: 147_182_123}
EDGE_STATUSES = {
    'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
    'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific',
}
POINT_STATUSES = {
    'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
    'reviewed_extension_rule_accepted', 'reviewed_case_accepted',
}
GRAPH25_IDS = {
    'GRAPH25-HORLOVO-2002-2010', 'GRAPH25-HORLOVO-2010-2021',
    'GRAPH25-MAMONY-2002-2010', 'GRAPH25-MAMONY-2010-2021',
    'GRAPH25-STRUGI-2002-2010', 'GRAPH25-STRUGI-2010-2021',
}
STRUGI_POINT_IDS = {
    'graph25-strugi-current:2021:data_allsettlements_anon_156_v20251217.parquet:parquet:108423',
    'graph25-strugi-continuity:ROSSTAT2010:T5:p71:l47',
}
GAIKODZOR_POINT_IDS = {
    'graph26-gaikodzor-continuity:2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:354',
    'graph26-gaikodzor-continuity:2010:005_888282bccc_13._20Краснодарский_край_2010.xls:КК:52',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    selected = pd.read_parquet(SELECTED, columns=[
        'source_record_id', 'census_year', 'population', 'is_additive_settlement_record', 'population_scope'
    ])
    edges = pd.read_parquet(GRAPH25, columns=[
        'decision_id', 'from_source_record_id', 'to_source_record_id', 'relation', 'decision_status'
    ])
    points25 = pd.read_parquet(POINTS25, columns=[
        'point_use_id', 'target_source_record_id', 'coordinate_admission_status', 'latitude', 'longitude'
    ])
    points26 = pd.read_parquet(POINTS26, columns=[
        'point_use_id', 'target_source_record_id', 'coordinate_admission_status', 'latitude', 'longitude'
    ])
    assert set(edges.loc[edges.decision_id.astype(str).str.startswith('GRAPH25-'), 'decision_id'].astype(str)) == GRAPH25_IDS
    assert set(points25.loc[points25.point_use_id.astype(str).str.startswith('graph25-strugi-'), 'point_use_id'].astype(str)) == STRUGI_POINT_IDS
    assert set(points26.loc[points26.point_use_id.astype(str).str.startswith('graph26-gaikodzor-'), 'point_use_id'].astype(str)) == GAIKODZOR_POINT_IDS
    ids = set(selected.source_record_id.astype(str))
    assert set(edges.from_source_record_id.astype(str)) <= ids and set(edges.to_source_record_id.astype(str)) <= ids
    for ledger in (points25, points26):
        assert ledger.target_source_record_id.is_unique
        assert set(ledger.target_source_record_id.astype(str)) <= ids
        assert ledger.coordinate_admission_status.isin(POINT_STATUSES).all()
        lat, lon = pd.to_numeric(ledger.latitude, errors='coerce'), pd.to_numeric(ledger.longitude, errors='coerce')
        assert lat.between(-90, 90).all() and lon.between(-180, 180).all()

    cases = {
        'reconstructed_graph24': (edges.loc[~edges.decision_id.astype(str).isin(GRAPH25_IDS)],
                                  points25.loc[~points25.point_use_id.astype(str).isin(STRUGI_POINT_IDS)]),
        'graph25': (edges, points25),
        'graph26': (edges, points26),
    }
    results = {}
    for label, (e, p) in cases.items():
        active = e.loc[e.relation.eq('same_place') & e.decision_status.isin(EDGE_STATUSES)]
        _, full_ids, _ = identity_sets(selected, active)
        joint = set(p.target_source_record_id.astype(str)) & full_ids
        additive = selected.loc[selected.is_additive_settlement_record.fillna(False).astype(bool)].copy()
        additive['source_record_id'] = additive.source_record_id.astype(str)
        additive['population'] = pd.to_numeric(additive.population, errors='coerce').fillna(0).astype('int64')
        rows = {}
        for year, group in additive.groupby('census_year', sort=True):
            year = int(year)
            mask = group.source_record_id.isin(joint)
            population = int(group.loc[mask, 'population'].sum())
            identity_mask = group.source_record_id.isin(full_ids)
            identity_population = int(group.loc[identity_mask, 'population'].sum())
            rows[str(year)] = {
                'strict_full_2002_2010_2021_identity_chain_population': identity_population,
                'identity_chain_control_percent': 100 * identity_population / CONTROLS[year],
                'strict_full_2002_2010_2021_same_place_chain_with_accepted_point_population': population,
                'official_control_population': CONTROLS[year],
                'control_percent': 100 * population / CONTROLS[year],
                'selected_additive_rows': int(len(group)),
                'strict_joint_rows': int(mask.sum()),
                'remaining_to_99_percent': max(0, int((CONTROLS[year] * 99 + 99) // 100) - population),
            }
        results[label] = rows
    for year in map(str, CONTROLS):
        previous = results['reconstructed_graph24'][year]['strict_full_2002_2010_2021_same_place_chain_with_accepted_point_population']
        current = results['graph26'][year]['strict_full_2002_2010_2021_same_place_chain_with_accepted_point_population']
        results['graph26'][year]['marginal_vs_reconstructed_graph24'] = current - previous
    receipt = {
        'status': 'strict_additive_full_three_census_chain_coverage_reproduced',
        'definition': 'Selected additive census observations with an accepted WGS84 point and an admitted same_place component containing one selected record in each of 2002, 2010, and 2021. This is distinct from the two-or-more-observed-year and reviewed-scope metric.',
        'inputs': {k: {'path': str(p), 'sha256': sha(p)} for k, p in {
            'selected': SELECTED, 'graph25_identity_edges': GRAPH25,
            'graph25_point_uses': POINTS25, 'graph26_point_uses': POINTS26,
        }.items()},
        'reconstruction': {
            'base_graph24_semantically_reconstructed_from_graph25': True,
            'removed_graph25_decision_ids': sorted(GRAPH25_IDS),
            'removed_graph25_strugi_point_use_ids': sorted(STRUGI_POINT_IDS),
            'graph26_gaikodzor_point_use_ids': sorted(GAIKODZOR_POINT_IDS),
        },
        'results': results,
        'limitations': [
            'This strict calculation covers selected additive settlement rows only. Separately reviewed territorial and event-aware scope layers remain reported in the existing scope-aware metric.',
            'A same_place identity chain does not assert comparable population boundaries.',
            'No missing census-year observation is imputed.',
        ],
    }
    OUTPUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
