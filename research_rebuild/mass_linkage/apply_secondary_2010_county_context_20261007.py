"""Admit selected secondary XLS endpoints by checked two-sided source context.

The context is a county mapped through accepted current identities, not a claim
that the current county name was printed in the 2010 source. Existing 2002/2021
identity is preserved. Population ratios and printed type/county changes remain
separate comparison flags, not substitutes for source identity evidence.
"""
import gzip
import json
from pathlib import Path

import pandas as pd
import xlrd

from current_chain_state_20261007 import distance_km, normalize, sha
from working_state_20261007 import E, load
from apply_unique_county_name_bridge_20261007 import county_key

REVIEW = E / 'secondary_2010_county_context_batch_20261007'
WORK = Path('/workspace/settlements-work/secondary_2010_county_context_batch_20261007')
OUT = E / 'secondary_2010_county_context_application_20261007'


def main():
    review = json.loads((REVIEW / 'receipt.json').read_text())
    pins = {**review['inputs'], **review['raw_source_hashes']}
    for path, h in pins.items():
        if sha(Path(path)) != h:
            raise ValueError('Changed candidate input: ' + path)
    for path, record in review['outputs'].items():
        if sha(Path(path)) != record['sha256']:
            raise ValueError('Changed candidate output: ' + path)
    rows = pd.read_csv(WORK / 'candidates.csv', keep_default_na=False)
    state = load(stage=13)
    before = state.metrics()
    if before != review['baseline']:
        raise ValueError('Stage 13 baseline mismatch')
    books = {}
    edges, points, held = [], [], []
    occupied = {(int(state.by_id.loc[sid, 'census_year']), p['latitude'], p['longitude']): sid
                for sid, p in state.point_rows.items()}
    for a in rows.to_dict('records'):
        sid, old, cur = (a[k] for k in ['target_2010_source_record_id',
                                      '2002_endpoint_source_record_id', '2021_endpoint_source_record_id'])
        endpoints = [state.by_id.loc[x] for x in [old, sid, cur]]
        if not all(x['is_additive_settlement_record'] == True for x in endpoints):
            raise ValueError('Not three physical additive observations')
        if any('железнодорожный объект' in normalize(x['settlement_type']) for x in endpoints):
            held.append(dict(a, hold_reason='unresolved_railway_feature_grain'))
            continue
        if state.uf.find(old) != state.uf.find(cur) or state.years[state.uf.find(cur)] != {2002, 2021}:
            raise ValueError('The existing historical/current identity is not the claimed pair')
        if state.years[state.uf.find(sid)] != {2010}:
            raise ValueError('2010 endpoint already has a competing identity')
        if normalize(endpoints[1]['name_norm']) != normalize(endpoints[2]['name_norm']):
            raise ValueError('Target/current name mismatch')
        if normalize(endpoints[1]['region_norm']) != normalize(endpoints[2]['region_norm']):
            raise ValueError('Target/current region mismatch')
        if a['inference'] != 'two_distinct_name_accepted_neighbors_within_20_physical_rows':
            raise ValueError('Unsupported county-context inference')
        labels = {normalize(endpoints[1]['settlement_name'])}
        for side in ['lower', 'upper']:
            anchor, current = a[f'{side}_anchor_2010_id'], a[f'{side}_anchor_current_id']
            if state.uf.find(anchor) != state.uf.find(current):
                raise ValueError('Anchor identity no longer accepted')
            if county_key(state.by_id.loc[current, 'district_raw']) != a['inferred_county_key']:
                raise ValueError('Anchor mapped county contradicts the target context')
            labels.add(normalize(state.by_id.loc[anchor, 'settlement_name']))
        if len(labels) != 3:
            raise ValueError('Context uses repeated locality names')
        n, lo, hi = (int(a[k]) for k in ['source_row_1based', 'lower_anchor_source_row', 'upper_anchor_source_row'])
        if not (0 < n-lo <= 20 and 0 < hi-n <= 20):
            raise ValueError('Source bracket exceeds the rule domain')
        path = a['source_file']
        if path not in books:
            books[path] = xlrd.open_workbook(path, on_demand=True)
        sh = books[path].sheet_by_name(a['source_sheet'])
        cells = sh.row_values(n-1)
        col = int(a['label_column_1based'])-1
        if normalize(cells[col]) != normalize(a['raw_label']):
            raise ValueError('Literal own source label differs')
        numbers = [v for v in cells[col+1:] if isinstance(v, (int, float))]
        if not numbers or numbers[0] != endpoints[1]['population']:
            raise ValueError('First population cell differs from the preserved source value')
        donor = state.point_rows[cur]
        if (donor['latitude'], donor['longitude']) != (float(a['latitude']), float(a['longitude'])):
            raise ValueError('Accepted donor point changed')
        for target in [old, sid]:
            existing = state.point_rows.get(target)
            if existing and distance_km((existing['latitude'], existing['longitude']),
                                        (donor['latitude'], donor['longitude'])) > 5:
                raise ValueError('Accepted component points contradict continuity')
        flags = {k: a[k] for k in ['printed_type_variation_flag', 'historical_current_county_change_flag',
                                  'population_scope_review_flag', 'population_ratio_max_over_min_three_years']}
        edges.append({'from_source_record_id': sid, 'to_source_record_id': cur, 'relation': 'same_place',
                      'decision_status': 'checked_rule_accepted', 'admission_rule': 'secondary_xls_two_sided_context_existing_2002_2021_identity',
                      'source_context_county_mapped_to_current': a['inferred_county_key'],
                      'historical_county_name_printed_asserted': False, 'boundary_comparability_asserted': False, **flags})
        state.union(sid, cur)
        for target in [sid, old]:
            if target in state.point_rows:
                continue
            year = int(state.by_id.loc[target, 'census_year'])
            key = (year, donor['latitude'], donor['longitude'])
            if key in occupied and occupied[key] != target:
                raise ValueError('New point shared by a distinct same-year source object')
            occupied[key] = target
            ledger = Path(donor['point_ledger_path'])
            pins.setdefault(str(ledger), sha(ledger))
            points.append({'target_source_record_id': target, 'target_year': year,
                           'latitude': donor['latitude'], 'longitude': donor['longitude'],
                           'coordinate_source_record_id': cur, 'coordinate_admission_status': 'reviewed_extension_rule_accepted',
                           'point_origin_kind': 'retrospective_spatial_continuity_inference',
                           'coordinate_origin_ledger': str(ledger), 'coordinate_origin_ledger_sha256': pins[str(ledger)],
                           'coordinate_origin_ledger_locator': 'target_source_record_id=' + cur,
                           'point_origin_file': donor.get('point_origin_file', ''),
                           'point_origin_sha256': donor.get('point_origin_sha256', ''),
                           'point_origin_locator': donor.get('point_origin_locator', ''),
                           'historical_coordinate_measurement_asserted': False,
                           'native_code_binding_asserted': False, 'boundary_comparability_asserted': False})
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(edges).to_csv(OUT / 'accepted_identity_edge_delta.csv', index=False)
    pd.DataFrame(points).to_csv(OUT / 'accepted_point_use_delta.csv', index=False)
    pd.DataFrame(held, columns=list(rows.columns)+['hold_reason']).to_csv(OUT / 'held_candidates.csv', index=False)
    for name in ['candidates.csv', 'literal_source_checks.csv.gz', 'all_selected_competitor_county_context.csv.gz']:
        data = (WORK / name).read_bytes()
        if name.endswith('.gz'):
            (OUT / name).write_bytes(data)
        else:
            (OUT / (name+'.gz')).write_bytes(gzip.compress(data, mtime=0))
    state.add_deltas(point_paths=[OUT / 'accepted_point_use_delta.csv'])
    after = state.metrics()
    if not held and after != review['simulation']:
        raise ValueError('Applied result differs from the candidate simulation')
    receipt = {'status': 'applied_source_context_rule', 'stage_before': 13, 'stage_after': 14,
               'new_edges': len(edges), 'new_point_uses': len(points), 'held_candidates': len(held),
               'before': before, 'after': after,
               'population_gain': {y: after[y]['covered_population']-before[y]['covered_population'] for y in before},
               'source_population_values_modified': False, 'source_district_fields_modified': False,
               'mapped_county_context_not_printed_historical_county': True,
               'existing_2002_2021_identity_is_a_preserved_input': True,
               'population_ratio_flags_retained_not_used_as_identity_proof': True,
               'boundary_comparability_asserted': False, 'inputs': pins,
               'outputs': {p.name: sha(p) for p in OUT.iterdir() if p.is_file()}}
    (OUT / 'application_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k: receipt[k] for k in ['new_edges', 'new_point_uses', 'held_candidates', 'population_gain', 'after']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
