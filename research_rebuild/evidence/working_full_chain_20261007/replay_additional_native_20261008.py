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


def main():
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
    ]
    state = load(39)
    assert finite(state) == {'histories': 138335, 'populations_by_year': {
        '2002': 126682581, '2010': 123845680, '2021': 124452211}}
    rows = []
    for stage, name, edge_suffix, point_suffix in cohorts:
        folder = E / name
        receipt_path = folder / ('separate_native_application_receipt.json' if stage == 55 else 'application_receipt.json')
        receipt = json.loads(receipt_path.read_text())
        pins = {}
        historical_derived = {}
        for field in ['input_pins', 'raw_source_pins']:
            for filename, expected in receipt.get(field, {}).items():
                path = Path(filename)
                actual = sha(path)
                if actual != expected:
                    assert path.parent == E / 'working_full_chain_20261007', str(path)
                    relative = str(path.relative_to(ROOT))
                    matched = None
                    for commit in ['dba51d5c4c7f8c4cf4ef3d8520ec26139c1c8b5f', 'f67ea9111a2d7932ef7e55a7015a120ac3a50caa', '0b8c3b0bda66b4dcec86ef9ff1ce706dc8fdcac7', '65e88651f238173693e14c9654888b36b2fc9d44']:
                        result = subprocess.run(['git', 'show', commit + ':' + relative], cwd=ROOT, capture_output=True)
                        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == expected:
                            matched = commit
                            break
                    if matched:
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_git_commit': matched, 'historical_control_only_not_new_build_input': True}
                    else:
                        snapshot = E / 'accepted_lifecycle_ownpoint_application_20261008/frozen_calculation_source_stage47.py'
                        assert path.name == 'replay_additional_native_20261008.py' and sha(snapshot) == expected, str(path)
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_frozen_snapshot': str(snapshot), 'historical_calculation_code_only_not_new_build_input': True}
                pins[str(path)] = expected
        for field in ['output_pins', 'accepted_ledger_pins']:
            for filename, expected in receipt.get(field, {}).items():
                path = folder / filename
                actual = sha(path)
                if actual != expected:
                    assert path.parent == E / 'working_full_chain_20261007', str(path)
                    relative = str(path.relative_to(ROOT))
                    matched = None
                    for commit in ['dba51d5c4c7f8c4cf4ef3d8520ec26139c1c8b5f', 'f67ea9111a2d7932ef7e55a7015a120ac3a50caa', '0b8c3b0bda66b4dcec86ef9ff1ce706dc8fdcac7', '65e88651f238173693e14c9654888b36b2fc9d44']:
                        result = subprocess.run(['git', 'show', commit + ':' + relative], cwd=ROOT, capture_output=True)
                        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == expected:
                            matched = commit
                            break
                    if matched:
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_git_commit': matched, 'historical_control_only_not_new_build_input': True}
                    else:
                        snapshot = E / 'accepted_lifecycle_ownpoint_application_20261008/frozen_calculation_source_stage47.py'
                        assert path.name == 'replay_additional_native_20261008.py' and sha(snapshot) == expected, str(path)
                        historical_derived[str(path)] = {'sha256': expected, 'verified_exact_frozen_snapshot': str(snapshot), 'historical_calculation_code_only_not_new_build_input': True}
                pins[str(path)] = expected
        before = finite(state)
        if stage == 51:
            apply_source_namespace_interpretations(state, folder / "source_namespace_interpretation_delta.csv")
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
    assert finite(state) == {'histories': 141261, 'populations_by_year': {
        '2002': 126913772, '2010': 124056798, '2021': 124669530}}
    result = {'status': 'actual_sequential39_to55_State_replay_passed',
              'measurement': 'all_component_members_finite_all_own_point_uses_no_conflicting_roots',
              'population_source_values_and_quality_unchanged': True,
              'stages': rows, 'final': finite(state)}
    (E / 'working_full_chain_20261007/native_composition_stages40_55_receipt.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'final': result['final']}))


if __name__ == '__main__':
    main()
