"""Apply native source-context links and own external coordinate repairs."""
import json
from pathlib import Path
import pandas as pd
from current_chain_state_20261007 import sha, distance_km
from working_state_20261007 import load, E

A = E / 'large_observed_year_recovery_20261007'
B = E / 'corrected_own_wiki_point_batch_20261007'
W = Path('/workspace/settlements-work/corrected_own_wiki_point_batch_20261007')
OUT = E / 'own_year_and_corrected_points_application_20261007'


def main():
    receipts = [json.loads((A/'ordinary_simulation_receipt.json').read_text()),
                json.loads((B/'receipt.json').read_text())]
    pins = {}
    def check(path, expected):
        path = Path(path)
        if not path.is_absolute():
            path = E.parents[1] / path
        pins.setdefault(str(path), sha(path))
        if pins[str(path)] != expected:
            raise ValueError('Candidate/source changed: ' + str(path))
    for review in receipts:
        for key in ['inputs', 'outputs']:
            for name, value in review.get(key, {}).items():
                expected = value['sha256'] if isinstance(value, dict) else value
                path = Path(name)
                if key == 'outputs' and len(path.parts) == 1:
                    path = A / path
                check(path, expected)
    state = load(15)
    before = state.metrics()
    if before != receipts[1]['baseline'] or before != receipts[0]['before']:
        raise ValueError('Stage15 baseline changed')
    edges = pd.concat([pd.read_csv(A/'candidate_ordinary_identity_edges.csv', keep_default_na=False),
                       pd.read_csv(W/'candidate_actual_missing_year_identity_edges.csv', keep_default_na=False)], ignore_index=True)
    points = pd.concat([pd.read_csv(A/'candidate_ordinary_point_uses.csv', keep_default_na=False),
                        pd.read_csv(W/'candidate_corrected_external_own_point_delta.csv', keep_default_na=False)], ignore_index=True).fillna('')
    if len(edges) != 5 or len(points) != 38:
        raise ValueError('Unexpected packet')
    for row in edges.to_dict('records'):
        a, b = row['from_source_record_id'], row['to_source_record_id']
        if state.uf.find(a) == state.uf.find(b):
            raise ValueError('Previously connected candidate')
        if not state.by_id.loc[a, 'is_additive_settlement_record'] or not state.by_id.loc[b, 'is_additive_settlement_record']:
            raise ValueError('Non-locality endpoint')
        if state.by_id.loc[a, 'region_norm'] != state.by_id.loc[b, 'region_norm']:
            raise ValueError('Conflicting source region')
        state.union(a, b)
    occupied = {}
    for sid, p in state.point_rows.items():
        key = (int(state.by_id.loc[sid, 'census_year']), p['latitude'], p['longitude'])
        occupied.setdefault(key, set()).add(sid)
    for row in points.to_dict('records'):
        target = row['target_source_record_id']
        if target in state.point_rows:
            raise ValueError('Point target already admitted')
        lat, lon = float(row['latitude']), float(row['longitude'])
        key = (int(state.by_id.loc[target, 'census_year']), lat, lon)
        if occupied.get(key, set()) - {target}:
            raise ValueError('New exact shared-point collision')
        occupied.setdefault(key, set()).add(target)
        origin = row['point_origin_file']
        check(origin, row['point_origin_sha256'])
        # Provider IDs such as Q1647878 are not census record IDs.
        donor = row.get('coordinate_origin_ledger_target_source_record_id', '')
        if not donor and row.get('coordinate_source_record_id', '') in state.by_id.index:
            donor = row['coordinate_source_record_id']
        if donor:
            if state.uf.find(target) != state.uf.find(donor):
                raise ValueError('Point donor identity differs')
            p = state.point_rows[donor]
            if distance_km((lat, lon), (p['latitude'], p['longitude'])) > .00001:
                raise ValueError('Accepted donor coordinate differs')
        if row.get('source_name', '') and row['source_name'] != state.by_id.loc[target, 'settlement_name']:
            raise ValueError('Own locality label differs')
    OUT.mkdir(parents=True, exist_ok=True)
    edges['decision_status'] = 'checked_rule_accepted'
    points['coordinate_admission_status'] = 'reviewed_extension_rule_accepted'
    if 'admission_allowed' in points:
        points['admission_allowed'] = True
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv', index=False)
    points.to_csv(OUT/'accepted_point_use_delta.csv', index=False)
    state.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv'])
    after = state.metrics()
    expected = dict(zip(['2002','2010','2021'], [126165144,123394194,123980432]))
    if any(after[y]['covered_population'] != expected[y] for y in expected):
        raise ValueError('Unexpected combined population union')
    receipt = {'status': 'applied_native_own_year_and_direct_external_point_batch',
               'stage_before': 15, 'stage_after': 16, 'new_edges': len(edges),
               'new_point_uses': len(points), 'new_complete_triplets': 3,
               'before': before, 'after': after,
               'population_gain': {y: after[y]['covered_population']-before[y]['covered_population'] for y in before},
               'source_population_values_modified': False,
               'wrong_unaccepted_provider_points_not_promoted': True,
               'boundary_comparability_asserted': False,
               'inputs': pins, 'outputs': {p.name: sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: receipt[k] for k in ['new_edges','new_point_uses','population_gain','after']}))


if __name__ == '__main__':
    main()
