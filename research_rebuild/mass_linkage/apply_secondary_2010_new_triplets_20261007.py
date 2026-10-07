"""Admit eight source-context triplets with explicit historical county evidence."""
import json
from pathlib import Path
import pandas as pd
from current_chain_state_20261007 import normalize, distance_km, sha
from working_state_20261007 import load, E
from apply_unique_county_name_bridge_20261007 import county_key

REVIEW = E / 'secondary_2010_new_triplets_20261007'
WORK = Path('/workspace/settlements-work/secondary_2010_new_triplets_20261007')
OUT = E / 'secondary_2010_new_triplets_application_20261007'


def main():
    review = json.loads((REVIEW/'receipt.json').read_text())
    pins = {}
    for key in ['inputs', 'raw_source_hashes']:
        for path, item in review.get(key, {}).items():
            h = item['sha256'] if isinstance(item, dict) else item
            if sha(Path(path)) != h:
                raise ValueError('Source input changed: '+path)
            pins[path] = h
    for path, item in review['outputs'].items():
        h = item['sha256'] if isinstance(item, dict) else item
        if sha(Path(path)) != h:
            raise ValueError('Candidate output changed: '+path)
        pins[path] = h
    state = load(stage=14)
    before = state.metrics()
    if before != review['baseline']:
        raise ValueError('Stage14 baseline mismatch')
    candidates = pd.read_csv(WORK/'candidates.csv', keep_default_na=False)
    edges = pd.read_csv(WORK/'candidate_identity_edges.csv', keep_default_na=False)
    points = pd.read_csv(WORK/'candidate_point_uses.csv', keep_default_na=False)
    if len(candidates) != 8 or len(edges) != 16 or len(points) != 16:
        raise ValueError('Unexpected bounded packet size')
    for a in candidates.to_dict('records'):
        ids = [a[k] for k in ['2002_endpoint_source_record_id', 'target_2010_source_record_id', '2021_endpoint_source_record_id']]
        rows = [state.by_id.loc[x] for x in ids]
        if not all(x['is_additive_settlement_record'] == True for x in rows):
            raise ValueError('Not whole physical settlement observations')
        if len({normalize(x['name_norm']) for x in rows}) != 1 or len({normalize(x['region_norm']) for x in rows}) != 1:
            raise ValueError('Exact source-name/region identity differs')
        if county_key(rows[0]['district_raw']) != county_key(rows[2]['district_raw']) or county_key(rows[0]['district_raw']) != a['inferred_county_key']:
            raise ValueError('Explicit historical county mismatch')
        if any('железнодорожный объект' in normalize(x['settlement_type']) for x in rows):
            raise ValueError('Unresolved railway feature grain')
        if any(len(state.years[state.uf.find(x)]) != 1 for x in ids):
            raise ValueError('Candidate already has a competing historical identity')
    for a in edges.to_dict('records'):
        state.union(a['from_source_record_id'], a['to_source_record_id'])
    for a in points.to_dict('records'):
        target, cur = a['target_source_record_id'], a['coordinate_source_record_id']
        if target in state.point_rows or state.uf.find(target) != state.uf.find(cur):
            raise ValueError('Point target is not newly eligible')
        donor = state.point_rows[cur]
        if distance_km((float(a['latitude']), float(a['longitude'])), (donor['latitude'], donor['longitude'])) > .00001:
            raise ValueError('Donor coordinate changed')
        ledger = Path(a['coordinate_origin_ledger'])
        if sha(ledger) != a['coordinate_origin_ledger_sha256']:
            raise ValueError('Point origin ledger changed')
        pins[str(ledger)] = a['coordinate_origin_ledger_sha256']
    OUT.mkdir(exist_ok=True, parents=True)
    edges['decision_status'] = 'checked_rule_accepted'
    edges['admission_rule'] = 'explicit_2002_county_and_checked_2010_source_context_unique_current_locality'
    edges['printed_type_changes_are_source_flags_not_legal_event_proof'] = True
    points['coordinate_admission_status'] = 'reviewed_extension_rule_accepted'
    points['point_origin_kind'] = 'retrospective_spatial_continuity_inference'
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv', index=False)
    points.to_csv(OUT/'accepted_point_use_delta.csv', index=False)
    state.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv'])
    after = state.metrics()
    if after != review['simulation']:
        raise ValueError('Applied result differs from simulation')
    receipt = {'status': 'applied_explicit_county_source_context_triplets', 'stage_before': 14, 'stage_after': 15,
               'new_edges': len(edges), 'new_point_uses': len(points), 'new_full3_entities': len(candidates),
               'before': before, 'after': after, 'population_gain': {y: after[y]['covered_population']-before[y]['covered_population'] for y in before},
               'source_population_values_modified': False, 'boundary_comparability_asserted': False, 'inputs': pins,
               'outputs': {p.name: sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: receipt[k] for k in ['new_edges', 'new_point_uses', 'population_gain', 'after']}))


if __name__ == '__main__':
    main()
