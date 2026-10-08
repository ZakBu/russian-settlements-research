"""One prefix replay for independent finite-population composition receipts."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
E = ROOT / 'research_rebuild/evidence'
sys.path.insert(0, str(ROOT / 'research_rebuild/mass_linkage'))
from working_state_20261007 import load


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
    ]
    state = load(39)
    assert finite(state) == {'histories': 138335, 'populations_by_year': {
        '2002': 126682581, '2010': 123845680, '2021': 124452211}}
    rows = []
    for stage, name, edge_suffix, point_suffix in cohorts:
        folder = E / name
        receipt_path = folder / 'application_receipt.json'
        receipt = json.loads(receipt_path.read_text())
        pins = {}
        for field in ['input_pins', 'raw_source_pins']:
            for filename, expected in receipt.get(field, {}).items():
                path = Path(filename)
                assert sha(path) == expected, str(path)
                pins[str(path)] = expected
        for field in ['output_pins', 'accepted_ledger_pins']:
            for filename, expected in receipt.get(field, {}).items():
                path = folder / filename
                assert sha(path) == expected, str(path)
                pins[str(path)] = expected
        before = finite(state)
        edges = folder / ('accepted_identity_edge_delta' + edge_suffix)
        points = folder / ('accepted_point_use_delta' + point_suffix)
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
                     'verified_input_and_ledger_pins': pins})
    assert finite(state) == {'histories': 138836, 'populations_by_year': {
        '2002': 126709814, '2010': 123868391, '2021': 124470404}}
    result = {'status': 'actual_sequential39_to46_State_replay_passed',
              'measurement': 'all_component_members_finite_all_own_point_uses_no_conflicting_roots',
              'population_source_values_and_quality_unchanged': True,
              'stages': rows, 'final': finite(state)}
    (E / 'working_full_chain_20261007/native_composition_stages40_46_receipt.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'final': result['final']}))


if __name__ == '__main__':
    main()
