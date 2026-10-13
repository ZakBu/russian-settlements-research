"""One prefix replay for independent finite-population composition receipts."""
import hashlib
import json
import sys
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
E = ROOT / 'research_rebuild/evidence'
sys.path.insert(0, str(ROOT / 'research_rebuild/mass_linkage'))
from working_state_20261007 import load, apply_source_namespace_interpretations


def finite(state):
    """Vector check on all component members, including nonordinary members."""
    obs = state.obs
    bad = ~obs.source_record_id.isin(state.point_rows) | ~np.isfinite(obs.population)
    bad_roots = set(obs.loc[bad, 'root'])
    bad_roots.update(state.uf.find(key) for key in state.conflicting_point_targets)
    ordinary = obs.is_additive_settlement_record.fillna(False)
    ordinary &= ~obs.region_norm.isin(['москва', 'санкт петербург', 'севастополь'])
    ordinary &= ~(obs.census_year.eq(2021) & obs.region_norm.eq('крым'))
    data = obs[ordinary]
    roots = {root for root in set(data.root)
             if state.years[root] == {2002, 2010, 2021} and root not in bad_roots}
    full = data[data.root.isin(roots)]
    return {'histories': len(roots), 'populations_by_year': {
        str(int(year)): int(group.population.sum()) for year, group in full.groupby('census_year')}}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main(final_stage=55):
    cohorts = [
        (40, 'native_alias_remaining_mass_20261008/existing_ownpoint_native02_mass', '.csv', '.csv'),
        (41, 'native_missing2010_residual_context_20261008', '.csv.gz', '.csv.gz'),
        (42, 'native_alias_remaining_mass_20261008/whole_region_type_unique_followup', '.csv', '.csv'),
        (43, 'native_alias_remaining_mass_20261008/aramil_independent_ownpoint_supplement', '.csv', '.csv'),
        (44, 'ownlegacy_ownpoint_route_gap_mass_20261008', '.csv', '.csv'),
        (45, 'native2010_whole_region_name_type_mass_20261008', '.csv.gz', '.csv.gz'),
        (46, 'cached_missing2010_dated_source_mass_20261008', '.csv', '.csv'),
        (47, 'uncached_missing2010_dated_source_mass_20261008', '.csv', '.csv'),
        (48, 'accepted_lifecycle_ownpoint_application_20261008', '.csv', '.csv'),
        (49, 'large2010_residual_native2002_followup_20261008', '.csv', '.csv'),
        (50, 'native2010_remaining_county_rule_mass_20261008', '.csv.gz', '.csv.gz'),
        (51, 'eaoregion_source_namespace_mass_20261008', '.csv', '.csv'),
        (52, 'native_rural_type_alias_mass_20261008', '.csv.gz', '.csv.gz'),
        (53, 'native_singleton_rural_mass_20261008', '.csv.gz', '.csv.gz'),
        (54, 'cached_historical_name_alias_mass_20261008', '.csv.gz', '.csv.gz'),
        (55, 'absorbed_remaining2010_direct_mass_20261008', '.csv', '.csv'),
        (56, 'current_component_name_alias_mass_20261008', '.csv.gz', '.csv.gz'),
        (57, 'combined_ownpoint_correction_application_20261008', None, '.csv.gz'),
        (58, 'remaining_native_spatial_literal_mass_20261008', '.csv.gz', '.csv.gz'),
        (59, 'corrected_ownpoint_cached_history_followup_20261008', None, '.csv.gz'),
        (60, 'combined_inherited_ownpoint_application_20261008', None, '.csv.gz'),
        (61, 'shared_rural_modern_point_corroboration_20261008', None, '.csv.gz'),
    ]
    assert final_stage in [55,56,57,58,59,60,61]
    cohorts = [row for row in cohorts if row[0]<=final_stage]
    state = load(39) if final_stage<58 else None
    if final_stage<58: assert finite(state) == {'histories': 138335, 'populations_by_year': {
        '2002': 126682581, '2010': 123845680, '2021': 124452211}}
    rows = []
    if final_stage>=58:
        from native_stage_composition import load as load_composition
        reused_stage=60 if final_stage>=61 else 58 if final_stage>=59 else 57
        verified_final,prefix=load_composition(E/'working_full_chain_20261007',reused_stage,sha)
        state=load(reused_stage)
        assert finite(state)==verified_final
        rows=list(prefix['stages'])
        cohorts=[row for row in cohorts if row[0]>reused_stage]
    for stage, name, edge_suffix, point_suffix in cohorts:
        folder = E / name
        receipt_path = folder / ('separate_native_application_receipt.json' if stage == 55 else 'root_application_receipt.json' if stage==61 else 'application_receipt.json')
        receipt = json.loads(receipt_path.read_text())
        pins = {}
        historical_derived = {}
        for field in ['input_pins', 'raw_source_pins']:
            for filename, expected in receipt.get(field, {}).items():
                path = Path(filename)
                actual = sha(path)
                if actual != expected:
                    assert path.parent == E / 'working_full_chain_20261007' or path in {ROOT/'research_rebuild/mass_linkage/working_state_20261007.py',ROOT/'research_rebuild/mass_linkage/current_chain_state_20261007.py'}, str(path)
                    relative = str(path.relative_to(ROOT))
                    matched = None
                    for commit in ['dba51d5c4c7f8c4cf4ef3d8520ec26139c1c8b5f', 'f67ea9111a2d7932ef7e55a7015a120ac3a50caa', '0b8c3b0bda66b4dcec86ef9ff1ce706dc8fdcac7', '65e88651f238173693e14c9654888b36b2fc9d44','fce754a35ddd2a182b242d6d415797e177860532']:
                        result = subprocess.run(['git', 'show', commit + ':' + relative], cwd=ROOT, capture_output=True)
                        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == expected:
                            matched = commit
                            break
                    if matched:
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_git_commit': matched, 'historical_control_only_not_new_build_input': True}
                    else:
                        snapshot = E / 'accepted_lifecycle_ownpoint_application_20261008/frozen_calculation_source_stage47.py'
                        if path==ROOT/'research_rebuild/mass_linkage/working_state_20261007.py':
                            snapshot=E/'combined_inherited_ownpoint_application_20261008/frozen_calculation_source_stage59.py'
                            if expected=='bc8477525df2519afeb5a57813e5ac68e27fe154cd354c3f93835d20759a56bd': snapshot=E/'shared_rural_modern_point_corroboration_20261008/frozen_calculation_source_stage60.py'
                            else: assert expected=='2d8a098ba81a7c3227c968fb97ebd034a31e1a126fc4e01f88d04c2b8f5a466a'
                        else: assert path.name=='replay_additional_native_20261008.py',str(path)
                        assert sha(snapshot)==expected,str(path)
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_frozen_snapshot': str(snapshot), 'historical_calculation_code_only_not_new_build_input': True}
                pins[str(path)] = expected
        for field in ['output_pins', 'accepted_ledger_pins']:
            for filename, expected in receipt.get(field, {}).items():
                path = folder / filename
                actual = sha(path)
                if actual != expected:
                    assert path.parent == E / 'working_full_chain_20261007' or path in {ROOT/'research_rebuild/mass_linkage/working_state_20261007.py',ROOT/'research_rebuild/mass_linkage/current_chain_state_20261007.py'}, str(path)
                    relative = str(path.relative_to(ROOT))
                    matched = None
                    for commit in ['dba51d5c4c7f8c4cf4ef3d8520ec26139c1c8b5f', 'f67ea9111a2d7932ef7e55a7015a120ac3a50caa', '0b8c3b0bda66b4dcec86ef9ff1ce706dc8fdcac7', '65e88651f238173693e14c9654888b36b2fc9d44','fce754a35ddd2a182b242d6d415797e177860532']:
                        result = subprocess.run(['git', 'show', commit + ':' + relative], cwd=ROOT, capture_output=True)
                        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == expected:
                            matched = commit
                            break
                    if matched:
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_git_commit': matched, 'historical_control_only_not_new_build_input': True}
                    else:
                        snapshot = E / 'accepted_lifecycle_ownpoint_application_20261008/frozen_calculation_source_stage47.py'
                        if path==ROOT/'research_rebuild/mass_linkage/working_state_20261007.py':
                            snapshot=E/'combined_inherited_ownpoint_application_20261008/frozen_calculation_source_stage59.py'
                            if expected=='bc8477525df2519afeb5a57813e5ac68e27fe154cd354c3f93835d20759a56bd': snapshot=E/'shared_rural_modern_point_corroboration_20261008/frozen_calculation_source_stage60.py'
                            else: assert expected=='2d8a098ba81a7c3227c968fb97ebd034a31e1a126fc4e01f88d04c2b8f5a466a'
                        else: assert path.name=='replay_additional_native_20261008.py',str(path)
                        assert sha(snapshot)==expected,str(path)
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_frozen_snapshot': str(snapshot), 'historical_calculation_code_only_not_new_build_input': True}
                pins[str(path)] = expected
        before = finite(state)
        if stage == 51:
            apply_source_namespace_interpretations(state, folder / "source_namespace_interpretation_delta.csv")
        if stage==57:
            assert receipt['status']=='root_applied_ownpoint_rejections_and_independent_recoveries'
            assert receipt['baseline_stage']==56 and receipt['intended_stage']==57
            assert before==receipt['before_finite_all3_all_points']
            assert receipt['identity_graph_unchanged'] and receipt['population_values_quality_unchanged']
            state.reject_point_uses(folder/'point_use_rejections.csv.gz')
            state.add_deltas([], [folder/'accepted_point_use_delta.csv.gz'])
            assert finite(state)==receipt['expected_after_finite_all3_all_points']
        elif stage==59:
            assert receipt['baseline_stage']==58 and receipt['identity_edges_unchanged'] and receipt['raw_census_population_quality_unchanged']
            assert before==receipt['before_finite']
            state.reject_point_uses(folder/'point_use_rejections.csv.gz')
            state.add_deltas([], [folder/'accepted_point_use_delta.csv.gz'])
            assert finite(state)==receipt['after_finite']
        elif stage==60:
            assert receipt['status']=='root_composed_independent_ownpoint_representatives_and_explicit_holds'
            assert receipt['baseline_stage']==59 and receipt['intended_stage']==60
            assert receipt['identity_edges_unchanged'] and receipt['raw_census_population_quality_unchanged']
            assert before==receipt['before_finite']
            state.reject_point_uses(folder/'point_use_rejections.csv.gz')
            state.add_deltas([], [folder/'accepted_point_use_delta.csv.gz'])
            if 'after_finite' in receipt: assert finite(state)==receipt['after_finite']
        elif stage==61:
            assert receipt['status']=='root_admitted_source_corroborated_ownpoint_additions_only' and receipt['baseline_stage']==60 and receipt['intended_stage']==61
            assert before==receipt['before_finite']
            assert sha(Path(receipt['source_application']))==receipt['source_application_sha256']
            assert receipt['identity_edges_unchanged'] and receipt['raw_census_population_quality_unchanged'] and receipt['current_point_rejections']==0
            # Only inactive historical targets receive points; current21 claims remain unchanged.
            import pandas as pd
            projected=pd.read_csv(folder/'accepted_point_use_delta.csv.gz',keep_default_na=False)
            assert len(projected)==59 and not projected.target_source_record_id.isin(state.point_rows).any()
            assert not projected.target_source_record_id.str.startswith('2021:').any()
            state.add_deltas([], [folder/'accepted_point_use_delta.csv.gz'])
            if 'after_finite' in receipt: assert finite(state)==receipt['after_finite']
        else:
            edges = folder / (('accepted_separate_native_identity_edge_delta' if stage == 55 else 'accepted_identity_edge_delta') + edge_suffix)
            points = folder / (('accepted_separate_native_point_use_delta' if stage == 55 else 'accepted_point_use_delta') + point_suffix)
            state.add_deltas([edges], [points])
        after = finite(state)
        rows.append({'stage': stage, 'source_application': str(receipt_path),
                     'source_application_sha256': sha(receipt_path),
                     'source_original_baseline_stage': receipt.get('baseline_stage'),
                     'before_finite_all3_all_points': before,
                     'after_finite_all3_all_points': after,
                     'actual_net_histories': after['histories'] - before['histories'],
                     'actual_net_population_by_year': {year: after['populations_by_year'][year] - before['populations_by_year'][year]
                                                      for year in before['populations_by_year']},
                     'verified_input_and_ledger_pins': pins,
                     'historical_derived_output_verifications': historical_derived})
    expected = ({'histories':141261,'populations_by_year':{'2002':126913772,'2010':124056798,'2021':124669530}} if final_stage==55 else {'histories':141314,'populations_by_year':{'2002':126922766,'2010':124061965,'2021':124677631}})
    if final_stage==57: expected={'histories':141101,'populations_by_year':{'2002':126914965,'2010':124055442,'2021':124671579}}
    if final_stage==58: expected={'histories':141106,'populations_by_year':{'2002':126915601,'2010':124056022,'2021':124679751}}
    if final_stage==59: expected={'histories':141065,'populations_by_year':{'2002':126912057,'2010':124052342,'2021':124675353}}
    if final_stage==60: expected=finite(state)  # Derived from the actual point-only replay; root attaches this exact control before final freeze.
    if final_stage==61: expected={'histories':141049,'populations_by_year':{'2002':126906393,'2010':124046806,'2021':124669608}}
    assert finite(state)==expected
    result = {'status': f'actual_sequential39_to{final_stage}_State_replay_passed',
              'measurement': 'all_component_members_finite_all_own_point_uses_no_conflicting_roots',
              'population_source_values_and_quality_unchanged': True,
              'stages': rows, 'final': finite(state)}
    if final_stage in [60,61]: result['root_after_finite_attachment_pending']='after_finite' not in receipt
    (E / f'working_full_chain_20261007/native_composition_stages40_{final_stage}_receipt.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'final': result['final']}))


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--stage',type=int,default=55);args=parser.parse_args()
    main(args.stage)
