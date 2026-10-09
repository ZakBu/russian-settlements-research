"""Apply disjoint accepted >500 packets; keep linkage and population credit distinct."""
from pathlib import Path
import argparse, hashlib, json, math, sys, time
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
M = ROOT / 'research_rebuild/mass_linkage'
sys.path.insert(0, str(M))
from working_state_20261007 import load

def append_reviewed_observations(state, observation_paths):
    """Restore actual omitted source leaves, never synthesize an absent census."""
    added = []
    for path in observation_paths:
        frame = pd.read_csv(path, keep_default_na=False)
        assert frame.source_record_id.is_unique
        assert not set(frame.source_record_id) & set(state.obs.source_record_id)
        for row in frame.to_dict('records'):
            sid = row['source_record_id']
            year = int(row['census_year'])
            pop = float(row['population'])
            assert year in {2002, 2010, 2021} and math.isfinite(pop) and pop >= 0
            assert row.get('source_sha256') and row.get('source_locator')
            assert row.get('population_value_quality')
            assert str(row['is_additive_settlement_record']).lower() == 'true'
            physical = Path(row['source_path'])
            assert physical.is_file(), 'Restored observation requires its original captured source'
            with physical.open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == row['source_sha256']
            state.uf.parent[sid] = sid
            state.years[sid] = {year}
            added.append(sid)
        frame['census_year'] = frame.census_year.astype(state.obs.census_year.dtype)
        frame['population'] = frame.population.astype(state.obs.population.dtype)
        frame['is_additive_settlement_record'] = True
        frame['root'] = frame.source_record_id
        for column in ['latitude', 'longitude']:
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors='coerce')
        state.obs = pd.concat([state.obs, frame.reindex(columns=state.obs.columns)], ignore_index=True)
        state.by_id = state.obs.set_index('source_record_id', drop=False)
        state.inputs.append(path)
    return added

def apply_reviewed_component_partitions(state, partition_paths):
    """Supersede a proved wrong component with an exact, UID-preserving partition."""
    changed = []
    for path in partition_paths:
        for row in pd.read_csv(path, keep_default_na=False).to_dict('records'):
            assert row['admission_status'] == 'reviewed_wrong_identity_component_partition_correction'
            proof = ROOT / row['source_binding_proof']
            with proof.open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == row['source_binding_proof_sha256']
            before = json.loads(row['expected_before_members_JSON'])
            after = json.loads(row['after_partition_JSON'])
            assert len(before) == len(set(before)) and before
            assert all(sid in state.by_id.index for sid in before)
            old_root = state.uf.find(before[0])
            actual = set(state.obs.loc[state.obs.source_record_id.map(state.uf.find).eq(old_root), 'source_record_id'])
            assert actual == set(before), 'Correction must match the complete actual baseline component'
            flat = [sid for group in after for sid in group]
            assert len(flat) == len(set(flat)) and set(flat) == actual
            assert len(after) > 1 and all(group for group in after)
            state.years.pop(old_root)
            for sid in before:
                state.uf.parent[sid] = sid
                state.years[sid] = {int(state.by_id.loc[sid, 'census_year'])}
            for group in after:
                for sid in group[1:]:
                    state.union(group[0], sid)
            changed.append({'before': before, 'after': after, 'proof_packet': str(path)})
        state.inputs.append(path)
    state.obs['root'] = state.obs.source_record_id.map(state.uf.find)
    return changed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recipe', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--write-snapshot', action='store_true')
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
    for path in [recipe_path] + paths('edges') + paths('points') + paths('scope_overlays') + paths('point_rejections') + paths('observations') + paths('component_partitions'):
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        pins[str(path)] = {'sha256': digest, 'bytes': path.stat().st_size}
    additional_observation_ids = append_reviewed_observations(state, paths('observations'))
    component_partitions = apply_reviewed_component_partitions(state, paths('component_partitions'))
    for path in paths('point_rejections'):
        state.reject_point_uses(path)
    state.add_deltas(edge_paths=paths('edges'), point_paths=paths('points'))
    pd.testing.assert_frame_equal(original, state.obs.iloc[:len(original)].drop(columns=['root']))
    point_delta_ids = set(state.point_rows) - before_points
    withdrawn_without_replacement = before_points - set(state.point_rows)
    assert len(state.point_rows) == len(before_points) + len(point_delta_ids) - len(withdrawn_without_replacement)
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
    whole = obs[obs.is_additive_settlement_record.fillna(False) &
                ~obs.source_record_id.isin(scope.source_record_id)].copy()
    whole['point_present'] = whole.source_record_id.isin(state.point_rows)
    whole['population_finite'] = whole.population.map(lambda value: pd.notna(value) and math.isfinite(float(value)))
    joint_stats = whole.groupby('root').agg(records=('source_record_id', 'size'), years=('census_year', 'nunique'),
                                          points=('point_present', 'all'), finite=('population_finite', 'all'))
    joint_roots = set(joint_stats[(joint_stats.records == 3) & (joint_stats.years == 3) &
                                 joint_stats.points & joint_stats.finite].index)
    eligible['has_full3_all_ownpoints_and_finite_counts'] = eligible.root.isin(joint_roots)
    # Raw latitude/longitude remain original claims; explicitly expose admitted own points.
    for field in ['latitude', 'longitude', 'coordinate_admission_status', 'point_origin_file', 'point_origin_sha256', 'point_origin_locator', 'point_origin_kind', 'coordinate_binding_rule', 'point_use_inference', 'point_temporal_interpretation', 'source_placement_uncertainty_m', 'diagnostic_map_registration_uncertainty_m', 'spatial_scope_uncertainty', 'historical_census_coordinate_asserted', 'direct_historical_coordinate_measurement', 'provider_binding_asserted', 'external_provider_ID_binding_asserted', 'population_boundary_comparability_asserted', 'boundary_comparability_asserted']:
        eligible['accepted_ownpoint_' + field] = eligible.source_record_id.map(
            lambda sid: state.point_rows.get(sid, {}).get(field, ''))
    eligible.to_csv(out / 'all_whole_NP_over500_record_status.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    by_year = []
    for year, rows in eligible.groupby('census_year'):
        denominator = float(rows.effective_population.sum())
        summary = {'census_year': int(year), 'records': len(rows),
                   'effective_population': denominator}
        for axis in ['has_ownpoint', 'has_same_place_other_census', 'has_full3_identity_component', 'has_full3_all_ownpoints_and_finite_counts']:
            summary[axis + '_records'] = int(rows[axis].sum())
            summary[axis + '_population'] = float(rows.loc[rows[axis], 'effective_population'].sum())
            summary[axis + '_population_percent'] = 100 * summary[axis + '_population'] / denominator
        by_year.append(summary)
    pd.DataFrame(by_year).to_csv(out / 'whole_NP_over500_coverage_by_year.csv', index=False)
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
    # Credit union membership is not a baseline full-three-year identity test.
    old_obs = original.copy()
    old_obs['root'] = old_obs.source_record_id.map(before_roots)
    old_ordinary = old_obs[old_obs.is_additive_settlement_record.fillna(False) &
                           ~old_obs.region_norm.isin(['москва', 'санкт петербург', 'севастополь', 'крым']) &
                           ~old_obs.source_record_id.isin(scope.source_record_id)].copy()
    old_ordinary['has_ownpoint'] = old_ordinary.source_record_id.isin(before_points)
    old_ordinary['has_finite_population'] = old_ordinary.population.map(lambda value: pd.notna(value) and math.isfinite(float(value)))
    old_stats = old_ordinary.groupby('root').agg(n_records=('source_record_id', 'size'),
                                              n_years=('census_year', 'nunique'),
                                              all_ownpoints=('has_ownpoint', 'all'),
                                              all_finite_populations=('has_finite_population', 'all'))
    old_complete_roots = set(old_stats[(old_stats.n_records == 3) & (old_stats.n_years == 3) & old_stats.all_ownpoints & old_stats.all_finite_populations].index)
    old_full3 = set(old_ordinary.loc[old_ordinary.root.isin(old_complete_roots), 'source_record_id'])
    lost_full3 = old_full3 - full3
    gained_full3 = full3 - old_full3
    obs[obs.source_record_id.isin(lost_full3)].to_csv(out / 'previous_full3_ids_without_current_full3.csv', index=False)
    old_credit = pd.read_csv(base / 'applied_primary_credited_UID_roster.csv.gz', usecols=['source_record_id'])
    newly_full3 = full3 - set(old_credit.source_record_id)
    obs[obs.source_record_id.isin(newly_full3)].to_csv(out / 'newly_complete_full3_source_year_records.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    receipt = {
        'base_stage': 71, 'working_stage': 72, 'threshold_strictly_greater_than': 500,
        'raw_counts_source_metadata_unchanged': True,
        'restored_actual_omitted_source_leaf_observations': len(additional_observation_ids),
        'proved_wrong_identity_component_partitions_superseded': component_partitions,
        'whole_NP_source_year_records': len(eligible),
        'new_ownpoint_uses': len(point_delta_ids),
        'baseline_ownpoint_uses_withdrawn_without_replacement': sorted(withdrawn_without_replacement),
        'existing_ownpoint_coordinate_replacements': sum(old != (state.point_rows[sid]['latitude'], state.point_rows[sid]['longitude'])
                                                      for sid, old in original_declared_points.items()),
        'remaining_whole_NP_without_ownpoint': len(missing),
        'whole_NP_without_same_place_other_census': int((~eligible.has_same_place_other_census).sum()),
        'whole_NP_without_full3_identity_component': int((~eligible.has_full3_identity_component).sum()),
        'whole_NP_without_full3_all_ownpoints_and_finite_counts': int((~eligible.has_full3_all_ownpoints_and_finite_counts).sum()),
        'ordinary_full3_complete_components': len(complete_roots),
        'actual_full3_source_year_ids_gained_vs_baseline_identity': len(gained_full3),
        'actual_previous_full3_ids_lost_after_proved_identity_correction': len(lost_full3),
        'newly_complete_full3_source_year_records': len(newly_full3),
        'newly_complete_full3_population_by_year': obs[obs.source_record_id.isin(newly_full3)].groupby('census_year').effective_population.sum().to_dict(),
        'typed_scope_exclusions': len(scope),
        'input_pins': pins,
        'wall_seconds': round(time.monotonic() - start, 3),
        'incomplete_connected_series_not_automatically_credited_as_full3': True,
    }
    if args.write_snapshot:
        state.obs.to_parquet(out / 'applied_state_observations.parquet', index=False, compression='zstd')
        state.obs[['source_record_id', 'root']].to_csv(out / 'applied_component_snapshot.csv.gz', index=False,
                                                   compression={'method': 'gzip', 'mtime': 0})
        sys.path.insert(0, str(ROOT / 'research_rebuild/evidence/main_axis_residual_application68_20261008'))
        from stream_point_snapshot import write_point_snapshot_from_active_rows
        write_point_snapshot_from_active_rows(state.point_rows, out / 'applied_point_snapshot.parquet')
        receipt['selected_observation_rows'] = len(state.obs)
        receipt['active_point_rows'] = len(state.point_rows)
    (out / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'input_pins'}, ensure_ascii=False, indent=2), flush=True)

if __name__ == '__main__':
    main()
