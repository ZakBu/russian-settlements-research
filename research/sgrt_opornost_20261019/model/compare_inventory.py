"""Conditional geometric diagnostics on documented school links and all inventoried suppliers.

This is post-development external checking, not blind holdout or national accuracy.
No E2 edge enters candidate counts, population masses, or parameter selection.
"""
from pathlib import Path
import argparse
import json
from itertools import product

import numpy as np
import pandas as pd

from functional_fields import distances_km, sha


def run(root: Path, graph: Path, out: Path) -> None:
    axis_path = root / 'data' / 'point_axis.parquet'
    inventory_path = root / 'data' / 'school_inventory_linked.csv'
    a = pd.read_parquet(axis_path).set_index('id', drop=False)
    inventory = pd.read_csv(inventory_path)
    e = pd.read_csv(graph / 'service_edges_calculated.csv')
    e = e[e.source_id.isin(inventory.source_id)].copy()
    all_results, alternatives, scopes = [], [], []
    for source, group in e.groupby('source_id'):
        original_inventory = inventory[inventory.source_id.eq(source)].copy()
        inv = original_inventory[~original_inventory.service_level.eq('evening_general')].copy()
        assert inv.inventory_id.is_unique
        candidates = inv[inv.id.isin(a.index)].groupby('id').size().rename('school_count').reset_index()
        candidates = candidates.merge(a[['id', 'lat', 'lon', 'population_2010', 'name']].reset_index(drop=True), on='id', validate='one_to_one')
        candidates = candidates.sort_values('id').reset_index(drop=True)
        ids = candidates.id.to_numpy()
        complete = inv.id.notna().all()
        target_level_comparable = source == 'SV2025'
        scope = 'first_grade_same_document_complete_provider_inventory' if target_level_comparable else 'exploratory_ordinary_school_node_not_grade_specific'
        scopes.append({'source_id': source, 'n_source_institutions': len(original_inventory),
                       'n_comparable_ordinary_institutions': len(inv),
                       'n_linked_ordinary_institutions': int(inv.id.notna().sum()),
                       'n_linked_ordinary_settlement_nodes': len(candidates),
                       'all_document_provider_coordinates_resolved': bool(complete),
                       'source_function_comparable': target_level_comparable,
                       'across_municipal_boundary_alternatives_inventoried': False,
                       'comparison_scope': scope})
        group = group.copy()
        group['comparison_origin_key'] = group.origin_uid.where(group.origin_uid.notna(), 'unresolved:' + group.edge_id.astype(str))
        for _, target_group in group.groupby('comparison_origin_key', dropna=False):
            origin = target_group.origin_uid.iloc[0]
            base = {'source_id': source, 'origin_uid': origin,
                    'source_edge_ids': '|'.join(target_group.edge_id.astype(str)),
                    'origin_name': target_group.origin_name.iloc[0],
                    'comparison_scope': scope,
                    'candidate_inventory_geographically_complete': bool(complete),
                    'strict_function_comparable': target_level_comparable,
                    'source_population_year': 2010,
                    'validation_status': 'post_development_external_not_blind_holdout'}
            if pd.isna(origin) or origin not in a.index:
                all_results.append({**base, 'model': 'not_comparable', 'status': 'unresolved_origin'})
                continue
            if target_group.geometry_status.eq('coordinate_conflict_quarantined').any():
                all_results.append({**base, 'model': 'not_comparable', 'status': 'coordinate_conflict_quarantined'})
                continue
            origin_row = a.loc[origin]
            d = distances_km(origin_row[['lat', 'lon']].to_numpy(dtype=float)[None, :],
                             candidates[['lat', 'lon']].to_numpy(dtype=float))[0]
            targets = set(target_group.destination_uid.dropna())
            target_mask = np.array([c in targets for c in ids])
            if not target_mask.any():
                all_results.append({**base, 'model': 'not_comparable', 'status': 'no_target_in_resolved_inventory'})
                continue
            nearest = np.argmin(d)
            models = [('nearest', -d)]
            for beta, d0 in product([1.5, 2., 3.], [5., 10., 20.]):
                models.append((f'school_count_b{beta:g}_d{d0:g}', candidates.school_count.to_numpy() / (1+d/d0)**beta))
                models.append((f'population2010_b{beta:g}_d{d0:g}', candidates.population_2010.to_numpy() / (1+d/d0)**beta))
            for model, score in models:
                top = np.argmax(score)
                target_best = np.max(score[target_mask])
                rank = 1 + int(np.sum(score > target_best + 1e-12))
                equal_top = np.abs(score - np.max(score)) <= 1e-12
                all_results.append({**base, 'model': model, 'status': 'conditional_comparison',
                                    'n_candidate_nodes': len(candidates),
                                    'target_center_uids': '|'.join(sorted(targets)),
                                    'selected_center_uid': ids[top],
                                    'selected_center_name': candidates.name.iloc[top],
                                    'selected_distance_km': d[top],
                                    'target_rank': rank,
                                    'top1_hits_documented_target': bool(np.any(target_mask & equal_top)),
                                    'top2_hits_documented_target': rank <= 2,
                                    'top3_hits_documented_target': rank <= 3,
                                    'n_tied_top': int(equal_top.sum()),
                                    'nearest_center_uid': ids[nearest]})
            for _, edge in target_group.iterrows():
                target_uid = edge.destination_uid
                if target_uid not in ids:
                    continue
                k = int(np.flatnonzero(ids == target_uid)[0])
                other = ids != target_uid
                if other.any():
                    alt_indices = np.flatnonzero(other)
                    alt = alt_indices[np.argmin(d[other])]
                    alt_distance = float(d[alt])
                    alt_uid = ids[alt]
                else:
                    alt_distance, alt_uid = np.nan, None
                alternatives.append({**base, 'edge_id': edge.edge_id,
                                     'documented_center_uid': target_uid,
                                     'documented_center_name': edge.provider_settlement,
                                     'distance_to_documented_center_km': float(d[k]),
                                     'nearest_observed_alternative_uid': alt_uid,
                                     'nearest_observed_alternative_distance_km': alt_distance,
                                     'alternative_minus_documented_distance_km': alt_distance - float(d[k]),
                                     'population_2021_origin_all_ages': origin_row.population_2021,
                                     'capacity_of_alternative_established': False,
                                     'interpretation': 'distance_diagnostic_not_measured_social_loss'})
    out.mkdir(parents=True, exist_ok=False)
    results = pd.DataFrame(all_results)
    results.to_csv(out / 'all_origin_model_comparisons.csv', index=False)
    pd.DataFrame(alternatives).to_csv(out / 'documented_provider_alternatives.csv', index=False)
    pd.DataFrame(scopes).to_csv(out / 'candidate_scope_audit.csv', index=False)
    summary = []
    comparable = results[results.status.eq('conditional_comparison')]
    for (source, model), rows in comparable.groupby(['source_id', 'model']):
        summary.append({'source_id': source, 'model': model, 'n_comparable_origins': len(rows),
                        'top1_numerator': int(rows.top1_hits_documented_target.sum()),
                        'top2_numerator': int(rows.top2_hits_documented_target.sum()),
                        'top3_numerator': int(rows.top3_hits_documented_target.sum()),
                        'candidate_inventory_geographically_complete': bool(rows.candidate_inventory_geographically_complete.all()),
                        'strict_function_comparable': bool(rows.strict_function_comparable.all()),
                        'national_accuracy_claim': False,
                        'parameter_chosen_by_this_result': False})
    pd.DataFrame(summary).to_csv(out / 'conditional_comparison_summary.csv', index=False)
    assert len(results) > 0
    assert not comparable.groupby(['source_id', 'origin_uid', 'model']).size().gt(1).any()
    manifest = {'status': 'PASS', 'source_validation': 'post_development_external_not_blind_holdout',
                'n_comparison_rows': len(results), 'n_documented_alternative_rows': len(alternatives),
                'mass_uses_demographic_outcome': False,
                'school_count_is_capacity': False,
                'source_scope': scopes,
                'inputs': {'axis': sha(axis_path), 'inventory': sha(inventory_path),
                           'graph_edges': sha(graph / 'service_edges_calculated.csv')},
                'outputs': [{'file': p.name, 'sha256': sha(p)} for p in sorted(out.iterdir())]}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: manifest[k] for k in ['status', 'n_comparison_rows', 'n_documented_alternative_rows']}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--graph', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    run(a.root, a.graph, a.out)
