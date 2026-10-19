"""Independent comparison audit; no imports of model implementations.

Distances are atan2(cross,dot) on three-dimensional unit vectors. Source acts,
not attachment rows, are the units of evidence. No national accuracy or CI.
"""
from pathlib import Path
from itertools import product
import hashlib
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'statistics' / 'results'
R = 6371.0088


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''):
            h.update(b)
    return h.hexdigest()


def sphere_vectors(coords):
    t = np.radians(np.asarray(coords, dtype=float))
    return np.column_stack([np.cos(t[:, 0]) * np.cos(t[:, 1]),
                            np.cos(t[:, 0]) * np.sin(t[:, 1]), np.sin(t[:, 0])])


def independent_distance(one, many):
    o, c = sphere_vectors(np.asarray(one)[None, :])[0], sphere_vectors(many)
    return R * np.arctan2(np.linalg.norm(np.cross(o, c), axis=1), c @ o)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {'axis': ROOT / 'data/point_axis.parquet',
             'inventory': ROOT / 'data/school_inventory_linked.csv',
             'edges': ROOT / 'model/documented_graph/service_edges_calculated.csv',
             'comparisons': ROOT / 'model/inventory_comparison/all_origin_model_comparisons.csv',
             'summary': ROOT / 'model/inventory_comparison/conditional_comparison_summary.csv',
             'scope': ROOT / 'model/inventory_comparison/candidate_scope_audit.csv'}
    axis = pd.read_parquet(paths['axis']).set_index('id', drop=False)
    inv = pd.read_csv(paths['inventory'])
    edges = pd.read_csv(paths['edges'])
    actual = pd.read_csv(paths['comparisons'])
    summary = pd.read_csv(paths['summary'])
    scope = pd.read_csv(paths['scope']).set_index('source_id')
    checks = []

    def check(name, ok, details=None):
        checks.append({'check': name, 'pass': bool(ok), 'details': details})
        assert ok, (name, details)

    check('point_ids_unique', axis.index.is_unique)
    check('provider_institution_ids_unique', inv.inventory_id.is_unique)
    # Merge known identities only; each unresolved source row keeps its own key.
    e = edges[edges.source_id.isin(inv.source_id)].copy()
    e['origin_key'] = e.origin_uid.fillna('')
    unresolved = e.origin_uid.isna()
    e.loc[unresolved, 'origin_key'] = 'unresolved:' + e.loc[unresolved, 'edge_id'].astype(str)
    audited, ledger, year_rows = [], [], []
    for source, es in e.groupby('source_id', sort=True):
        providers = inv[inv.source_id.eq(source) & ~inv.service_level.eq('evening_general')]
        counts = providers[providers.id.isin(axis.index)].groupby('id').size().sort_index()
        ca = axis.loc[counts.index]
        ids = counts.index.to_numpy()
        linked_n = providers.id.notna().sum()
        check(f'{source}_all_document_providers_counted',
              counts.sum() == linked_n)
        check(f'{source}_document_counts_match_scope', len(counts) == scope.loc[source, 'n_linked_ordinary_settlement_nodes'])
        for key, ge in es.groupby('origin_key', sort=True):
            origin = ge.origin_uid.iloc[0]
            record = {'source_id': source, 'origin_key': key, 'origin_uid': origin,
                      'origin_name': ge.origin_name.iloc[0], 'edge_ids': '|'.join(ge.edge_id.astype(str)),
                      'documented_target_names': '|'.join(sorted(set(ge.provider_settlement))),
                      'n_inventory_nodes_resolved': len(ids),
                      'n_ordinary_institutions_unresolved': int(len(providers) - linked_n),
                      'strict_function_comparable': bool(scope.loc[source, 'source_function_comparable']),
                      'complete_across_boundaries': False,
                      'validation': 'post_development_external_not_blind_holdout'}
            if pd.isna(origin) or origin not in axis.index:
                status = 'unresolved_origin'
            elif ge.geometry_status.eq('coordinate_conflict_quarantined').any():
                status = 'coordinate_conflict_quarantined'
            elif not ge.destination_uid.isin(ids).any():
                status = 'no_target_in_resolved_inventory'
            else:
                status = 'conditional_comparison'
            record['status'] = status
            reported = actual[actual.source_id.eq(source) & actual.source_edge_ids.eq(record['edge_ids'])]
            if status != 'conditional_comparison':
                check(f'{source}_{key}_retained_exclusion', len(reported) == 1 and reported.status.eq(status).all())
                ledger.append(record)
                continue
            orow = axis.loc[origin]
            d = independent_distance(orow[['lat', 'lon']].to_numpy(float), ca[['lat', 'lon']].to_numpy(float))
            target = np.array([x in set(ge.destination_uid.dropna()) for x in ids])
            models = [('nearest', -d)]
            for b, d0 in product([1.5, 2., 3.], [5., 10., 20.]):
                decay = np.power(1 + d / d0, -b)
                models += [(f'school_count_b{b:g}_d{d0:g}', counts.to_numpy() * decay),
                           (f'population2010_b{b:g}_d{d0:g}', ca.population_2010.to_numpy() * decay)]
                # Contemporary population as uncalibrated year sensitivity only.
                alt = ca.population_2021.to_numpy() * decay
                target_rank = 1 + np.sum(alt > np.max(alt[target]) + 1e-12)
                year_rows.append({'source_id': source, 'origin_uid': origin,
                                  'origin_name': record['origin_name'], 'beta': b, 'd0_km': d0,
                                  'population_year': 2021, 'rank': int(target_rank),
                                  'top1': bool(np.any(target & (np.abs(alt - alt.max()) <= 1e-12))),
                                  'selected_uid': ids[np.argmax(alt)],
                                  'role': 'unfitted_sensitivity_not_replacement_mass'})
            check(f'{source}_{key}_same19_models', len(reported) == 19)
            record['population_2010_origin'] = orow.population_2010
            record['population_2021_origin'] = orow.population_2021
            record['zero_population_2010_retained'] = bool(orow.population_2010 == 0)
            target_idx = np.flatnonzero(target)
            record['distance_to_nearest_documented_target_km'] = float(d[target_idx].min())
            record['documented_target_is_local'] = bool(origin in set(ge.destination_uid.dropna()))
            for model, score in models:
                top = np.argmax(score)
                rank = 1 + int(np.sum(score > np.max(score[target]) + 1e-12))
                top_hits = bool(np.any(target & (np.abs(score - score.max()) <= 1e-12)))
                expected = reported[reported.model.eq(model)]
                ok = len(expected) == 1
                if ok:
                    row = expected.iloc[0]
                    ok = (row.selected_center_uid == ids[top] and int(row.target_rank) == rank
                          and bool(row.top1_hits_documented_target) == top_hits
                          and bool(row.top2_hits_documented_target) == (rank <= 2)
                          and bool(row.top3_hits_documented_target) == (rank <= 3)
                          and np.isclose(row.selected_distance_km, d[top], rtol=0, atol=1e-8))
                check(f'{source}_{key}_{model}', ok)
                audited.append({'source_id': source, 'origin_uid': origin, 'model': model,
                                'selected_uid': ids[top], 'target_rank': rank, 'top1': top_hits,
                                'top2': rank <= 2, 'top3': rank <= 3})
                if model in ['nearest', 'population2010_b2_d10', 'school_count_b2_d10']:
                    name = model.replace('_b2_d10', '')
                    record[f'{name}_selected_name'] = ca.name.iloc[top]
                    record[f'{name}_selected_distance_km'] = float(d[top])
                    record[f'{name}_hits_documented_target'] = top_hits
            ledger.append(record)
    replay = pd.DataFrame(audited)
    cases = pd.DataFrame(ledger)
    years = pd.DataFrame(year_rows)
    check('all_reported_comparable_rows_replayed', len(replay) == actual.status.eq('conditional_comparison').sum())
    check('all_excluded_cases_kept_separately',
          cases[~cases.status.eq('conditional_comparison')].shape[0] == actual[~actual.status.eq('conditional_comparison')].shape[0])
    by_model = replay.groupby(['source_id', 'model']).agg(n_origins=('origin_uid', 'size'),
               top1_n=('top1', 'sum'), top2_n=('top2', 'sum'), top3_n=('top3', 'sum')).reset_index()
    for _, row in by_model.iterrows():
        s = summary[summary.source_id.eq(row.source_id) & summary.model.eq(row.model)].iloc[0]
        check(f'{row.source_id}_{row.model}_summary', row.n_origins == s.n_comparable_origins
              and row.top1_n == s.top1_numerator and row.top2_n == s.top2_numerator and row.top3_n == s.top3_numerator)
    sensitivity = []
    for source, rows in replay.groupby('source_id'):
        base = rows[rows.model.eq('nearest')].set_index('origin_uid')
        for family in ['school_count', 'population2010']:
            sub = rows[rows.model.str.startswith(family)]
            ncorrect = sub.groupby('model').top1.sum()
            selected = sub.groupby('origin_uid').selected_uid.nunique()
            robust_correct = sub.groupby('origin_uid').top1.all()
            robust_incorrect = ~sub.groupby('origin_uid').top1.any()
            ref = sub[sub.model.eq(f'{family}_b2_d10')].set_index('origin_uid')
            check(f'{source}_{family}_identical_origin_set', set(base.index) == set(ref.index))
            sensitivity.append({'source_id': source, 'family': family,
                                'n_origins': len(base), 'n_grid_models': len(ncorrect),
                                'top1_correct_min': int(ncorrect.min()), 'top1_correct_max': int(ncorrect.max()),
                                'correct_in_all9_scenarios': int(robust_correct.sum()),
                                'incorrect_in_all9_scenarios': int(robust_incorrect.sum()),
                                'origins_selected_node_changes_across9_scenarios': int(selected.gt(1).sum()),
                                'reference_disagrees_nearest': int(ref.selected_uid.ne(base.selected_uid).sum()),
                                'reference_better_than_nearest_n': int((ref.top1 & ~base.top1).sum()),
                                'reference_worse_than_nearest_n': int((~ref.top1 & base.top1).sum()),
                                'reference_both_correct_n': int((ref.top1 & base.top1).sum()),
                                'reference_both_incorrect_n': int((~ref.top1 & ~base.top1).sum()),
                                'strict_function_comparable': bool(scope.loc[source, 'source_function_comparable']),
                                'national_inference': False, 'parameters_selected_by_accuracy': False})
    year_summary = years.groupby(['source_id', 'beta', 'd0_km']).agg(n_origins=('origin_uid', 'size'),
                                                     population2021_top1_n=('top1', 'sum')).reset_index()
    for i, row in year_summary.iterrows():
        source = row.source_id
        model = f'population2010_b{row.beta:g}_d{row.d0_km:g}'
        original = replay[replay.source_id.eq(source) & replay.model.eq(model)].set_index('origin_uid')
        alt = years[years.source_id.eq(source) & years.beta.eq(row.beta) & years.d0_km.eq(row.d0_km)].set_index('origin_uid')
        year_summary.loc[i, 'population2010_top1_n'] = int(original.top1.sum())
        year_summary.loc[i, 'changed_selected_node_2010_to_2021_n'] = int(original.selected_uid.ne(alt.selected_uid).sum())
    strata = []
    eligible_cases = cases[cases.status.eq('conditional_comparison')]
    for year in [2010, 2021]:
        for source, source_cases in eligible_cases.groupby('source_id'):
            for level, mask in [('zero', source_cases[f'population_{year}_origin'].eq(0)),
                                ('positive', source_cases[f'population_{year}_origin'].gt(0))]:
                members = set(source_cases.loc[mask, 'origin_uid'])
                for model, rows in replay[replay.source_id.eq(source) & replay.origin_uid.isin(members)].groupby('model'):
                    strata.append({'source_id': source, 'population_year': year,
                                   'origin_population_stratum': level, 'model': model,
                                   'n_origins': len(rows), 'top1_n': int(rows.top1.sum()),
                                   'interpretation': 'census_reference_population_not_current_pupils_or_actual_demand'})
    output_tables = {'independent_model_replay.csv': replay, 'case_ledger.csv': cases,
                     'source_model_summary.csv': by_model, 'parameter_sensitivity.csv': pd.DataFrame(sensitivity),
                     'population_year_sensitivity.csv': year_summary,
                     'population_strata_summary.csv': pd.DataFrame(strata)}
    for file, frame in output_tables.items():
        frame.to_csv(OUT / file, index=False)
    manifest = {'status': 'PASS', 'independence': 'No author-model code imported; separate statistician not point-axis/linker/GIS/economy author',
                'method': 'atan2_norm_cross_dot_unit_sphere_R6371.0088',
                'n_source_school_documents': len(scope), 'n_model_rows_independently_replayed': len(replay),
                'n_comparable_origins': len(cases[cases.status.eq('conditional_comparison')]),
                'n_zero2010_comparable_origins': int(cases[cases.status.eq('conditional_comparison')].zero_population_2010_retained.sum()),
                'n_checks': len(checks), 'passed': sum(c['pass'] for c in checks),
                'inferential_test': 'not_run: only3document_clusters_and5nodes_in_the_only_strictly_comparable_source; permutations_of_q_would_not_identify_national_effect',
                'confidence_interval': 'not_estimated_no_national_sampling_frame',
                'test_status': 'post_development_external_not_blind_holdout',
                'inputs': {k: {'path': str(v.relative_to(ROOT)), 'sha256': digest(v)} for k,v in paths.items()},
                'outputs': [{'file': name, 'rows': len(frame), 'sha256': digest(OUT/name)} for name,frame in output_tables.items()],
                'checks': checks}
    (OUT / 'audit.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in manifest.items() if k in ['status','n_checks','passed','n_source_school_documents','n_model_rows_independently_replayed','n_comparable_origins','n_zero2010_comparable_origins']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
