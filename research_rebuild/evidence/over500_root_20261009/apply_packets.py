"""Apply disjoint accepted >500 packets; keep linkage and population credit distinct."""
from pathlib import Path
import argparse, hashlib, json, math, sys, time
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
M = ROOT / 'research_rebuild/mass_linkage'
sys.path.insert(0, str(M))
from working_state_20261007 import load

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recipe', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    recipe_path = Path(args.recipe)
    recipe = json.loads(recipe_path.read_text())
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    state = load(71)
    original = state.obs.drop(columns=['root']).copy(deep=True)
    before_points = set(state.point_rows)
    before_roots = state.obs.set_index('source_record_id').root.to_dict()
    def paths(key):
        return [ROOT / x for x in recipe.get(key, [])]
    pins = {}
    declared_point_ids = set()
    for path in paths('points'):
        declared_point_ids.update(pd.read_csv(path, usecols=['target_source_record_id']).target_source_record_id)
    original_declared_points = {sid: (state.point_rows[sid]['latitude'], state.point_rows[sid]['longitude'])
                                for sid in declared_point_ids if sid in state.point_rows}
    for path in [recipe_path] + paths('edges') + paths('points') + paths('scope_overlays') + paths('point_rejections'):
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        pins[str(path)] = {'sha256': digest, 'bytes': path.stat().st_size}
    for path in paths('point_rejections'):
        state.reject_point_uses(path)
    state.add_deltas(edge_paths=paths('edges'), point_paths=paths('points'))
    pd.testing.assert_frame_equal(original, state.obs.drop(columns=['root']))
    point_delta_ids = set(state.point_rows) - before_points
    base = ROOT / 'publication/stage71'
    scopes = [pd.read_csv(base / 'accepted_large_record_scope_classification_overlay.csv', keep_default_na=False)]
    for path in paths('scope_overlays'):
        frame = pd.read_csv(path, keep_default_na=False)
        assert frame.source_record_id.is_unique
        scopes.append(frame)
    scope = pd.concat(scopes, ignore_index=True).fillna('')
    assert scope.source_record_id.is_unique, 'Scope overlays must be disjoint'
    scope.to_csv(out / 'accepted_large_record_scope_classification_overlay.csv', index=False)
    obs = state.obs.copy()
    obs['effective_population'] = obs.population
    overlay = pd.read_csv(base / 'applied_primary_population_source_overlay_2010.csv.gz', low_memory=False).set_index('original_source_record_id')
    mask = obs.census_year.eq(2010) & obs.source_record_id.isin(overlay.index)
    obs.loc[mask, 'effective_population'] = obs.loc[mask, 'source_record_id'].map(overlay.population)
    eligible = obs[obs.is_additive_settlement_record.fillna(False) &
                   ((obs.population > 500) | (obs.effective_population > 500)) &
                   ~obs.source_record_id.isin(scope.source_record_id)].copy()
    eligible['has_ownpoint'] = eligible.source_record_id.isin(state.point_rows)
    eligible['component_years'] = eligible.source_record_id.map(lambda sid: ','.join(map(str, sorted(state.years[state.uf.find(sid)]))))
    eligible['has_same_place_other_census'] = eligible.component_years.str.contains(',')
    eligible['has_full3_identity_component'] = eligible.component_years.eq('2002,2010,2021')
    eligible.to_csv(out / 'all_whole_NP_over500_record_status.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    missing = eligible[~eligible.has_ownpoint]
    missing.to_csv(out / 'remaining_whole_NP_over500_without_ownpoint.csv', index=False)
    pd.DataFrame([state.point_rows[sid] for sid in sorted(declared_point_ids)]).to_csv(out / 'accepted_point_use_delta.csv', index=False)
    ordinary = obs[obs.is_additive_settlement_record.fillna(False) &
                   ~obs.region_norm.isin(['москва', 'санкт петербург', 'севастополь', 'крым']) &
                   ~obs.source_record_id.isin(scope.source_record_id)]
    ordinary = ordinary.assign(has_ownpoint=ordinary.source_record_id.isin(state.point_rows),
                               has_finite_population=ordinary.population.map(lambda p: pd.notna(p) and math.isfinite(float(p))))
    stats = ordinary.groupby('root').agg(n_records=('source_record_id', 'size'),
                                        n_years=('census_year', 'nunique'),
                                        all_ownpoints=('has_ownpoint', 'all'),
                                        all_finite_populations=('has_finite_population', 'all'))
    complete_roots = set(stats[(stats.n_records == 3) & (stats.n_years == 3) &
                               stats.all_ownpoints & stats.all_finite_populations].index)
    full3 = set(ordinary.loc[ordinary.root.isin(complete_roots), 'source_record_id'])
    old_credit = pd.read_csv(base / 'applied_primary_credited_UID_roster.csv.gz', usecols=['source_record_id'])
    newly_full3 = full3 - set(old_credit.source_record_id)
    obs[obs.source_record_id.isin(newly_full3)].to_csv(out / 'newly_complete_full3_source_year_records.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    receipt = {
        'base_stage': 71, 'working_stage': 72, 'threshold_strictly_greater_than': 500,
        'raw_counts_source_metadata_unchanged': True,
        'whole_NP_source_year_records': len(eligible),
        'new_ownpoint_uses': len(point_delta_ids),
        'existing_ownpoint_coordinate_replacements': sum(old != (state.point_rows[sid]['latitude'], state.point_rows[sid]['longitude'])
                                                      for sid, old in original_declared_points.items()),
        'remaining_whole_NP_without_ownpoint': len(missing),
        'whole_NP_without_same_place_other_census': int((~eligible.has_same_place_other_census).sum()),
        'whole_NP_without_full3_identity_component': int((~eligible.has_full3_identity_component).sum()),
        'newly_complete_full3_source_year_records': len(newly_full3),
        'newly_complete_full3_population_by_year': obs[obs.source_record_id.isin(newly_full3)].groupby('census_year').effective_population.sum().to_dict(),
        'typed_scope_exclusions': len(scope),
        'input_pins': pins,
        'wall_seconds': round(time.monotonic() - start, 3),
        'incomplete_connected_series_not_automatically_credited_as_full3': True,
    }
    (out / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'input_pins'}, ensure_ascii=False, indent=2), flush=True)

if __name__ == '__main__':
    main()
