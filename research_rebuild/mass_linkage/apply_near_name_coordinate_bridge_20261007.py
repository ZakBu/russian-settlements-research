"""Admit restricted name variants with independently sourced own-point agreement."""
import hashlib, json, re, subprocess
from pathlib import Path
import pandas as pd
from current_chain_state_20261007 import sha, distance_km, normalize
from working_state_20261007 import load, E
from apply_unique_county_name_bridge_20261007 import county_key

REVIEW = E / 'near_name_coordinate_bridge_20261007'
WORK = Path('/workspace/settlements-work/near_name_coordinate_bridge_20261007')
OUT = E / 'near_name_coordinate_application_20261007'


def main():
    review = json.loads((REVIEW/'receipt.json').read_text())
    readback = json.loads((REVIEW/'final_readback.json').read_text())
    checks = json.loads((REVIEW/'source_check_receipt.json').read_text())
    required = ['unique_old_endpoints', 'unique_current_year_endpoints',
                'all_raw_coordinate_code_counts_one', 'no_all_current_alternatives',
                'numeric_tokens_preserved', 'bounded_physical_checks_pass']
    if not all(readback[k] for k in required) or not checks['all_requested_checks_pass']:
        raise ValueError('Concrete source/ambiguity checks failed')
    pins = {}
    def check(path, expected):
        path = Path(path)
        pins.setdefault(str(path), sha(path))
        if pins[str(path)] == expected:
            return
        if path.name == 'working_state_20261007.py':
            raw = subprocess.check_output(['git','show','f86fdbd7ce2fb22474a4662e6e08aa259565dc9b:research_rebuild/mass_linkage/working_state_20261007.py'], cwd=E.parents[1])
            if hashlib.sha256(raw).hexdigest() == expected:
                return
        raise ValueError('Candidate source changed: '+str(path))
    for path, expected in review['inputs'].items(): check(path, expected)
    for path, record in review['outputs'].items(): check(path, record['sha256'])
    for key in ['inputs_sha256', 'old_census_source_hashes']:
        for path, expected in checks[key].items(): check(path, expected)
    state = load(16)
    before = state.metrics()
    edges = pd.read_csv(WORK/'candidate_identity_edges.csv', keep_default_na=False)
    points = pd.read_csv(WORK/'candidate_point_uses.csv', keep_default_na=False)
    candidates = pd.read_csv(WORK/'candidates.csv.gz', keep_default_na=False)
    if len(edges) != 162 or len(points) != 20 or len(candidates) != 162:
        raise ValueError('Unexpected bounded batch')
    for row in candidates.to_dict('records'):
        a, b = row['old_source_record_id'], row['current_source_record_id']
        aa, bb = state.by_id.loc[a], state.by_id.loc[b]
        if aa.region_norm != bb.region_norm or county_key(aa.district_raw) != county_key(bb.district_raw):
            raise ValueError('Explicit source geography differs')
        if re.findall(r'\d+', aa.settlement_name) != re.findall(r'\d+', bb.settlement_name):
            raise ValueError('Numerical name tokens differ')
        bp = state.point_rows[b]
        if distance_km((float(row['old_latitude']),float(row['old_longitude'])),
                       (bp['latitude'],bp['longitude'])) > 5:
            raise ValueError('Independent own points disagree')
        if a in state.point_rows:
            ap = state.point_rows[a]
            if distance_km((ap['latitude'],ap['longitude']), (bp['latitude'],bp['longitude'])) > 5:
                raise ValueError('Active point contradicts candidate')
    for row in edges.to_dict('records'):
        state.union(row['from_source_record_id'], row['to_source_record_id'])
    occupied = {}
    for sid, p in state.point_rows.items():
        occupied.setdefault((int(state.by_id.loc[sid,'census_year']),p['latitude'],p['longitude']),set()).add(sid)
    origin_fields = ['point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']
    records = []
    already_admitted_point_confirmations = []
    for row in points.to_dict('records'):
        target, donor = row['target_source_record_id'], row['coordinate_source_record_id']
        if state.uf.find(target) != state.uf.find(donor):
            raise ValueError('Point donor lineage differs')
        dp = state.point_rows[donor]
        lat,lon = float(row['latitude']),float(row['longitude'])
        if target in state.point_rows:
            active = state.point_rows[target]
            distance = distance_km((active['latitude'],active['longitude']), (dp['latitude'],dp['longitude']))
            if distance > 5:
                raise ValueError('Newly admitted own point contradicts lineage')
            already_admitted_point_confirmations.append({'target_source_record_id':target, 'distance_to_current_point_km':distance, 'active_point_retained':True})
            continue
        if distance_km((lat,lon),(dp['latitude'],dp['longitude'])) > .00001:
            raise ValueError('Donor point changed')
        key = (int(state.by_id.loc[target,'census_year']),lat,lon)
        if occupied.get(key,set())-{target}: raise ValueError('New same-year point collision')
        occupied.setdefault(key,set()).add(target)
        check(row['coordinate_origin_ledger'], row['coordinate_origin_ledger_sha256'])
        for field in origin_fields: row[field] = dp.get(field,'')
        row['point_use_inference'] = 'retrospective_spatial_continuity_restricted_name_variant'
        row['coordinate_admission_status'] = 'reviewed_extension_rule_accepted'
        records.append(row)
    OUT.mkdir(parents=True,exist_ok=True)
    edges['decision_status'] = 'checked_rule_accepted'
    edges['admission_rule'] = 'restricted_literal_name_variant_same_county_unique_independent_ownpoints_within5km'
    edges.to_csv(OUT/'accepted_identity_edge_delta.csv',index=False)
    pd.DataFrame(records).to_csv(OUT/'accepted_point_use_delta.csv',index=False)
    state.add_deltas(point_paths=[OUT/'accepted_point_use_delta.csv'])
    after = state.metrics()
    gain = {y:after[y]['covered_population']-before[y]['covered_population'] for y in before}
    if gain != review['marginal_population_gain']: raise ValueError('Current-stage population gain differs')
    receipt = {'status':'applied_restricted_near_name_independent_point_batch', 'stage_before':16,'stage_after':17,
               'new_edges':len(edges),'new_point_uses':len(records),'new_complete_triplets':143,
               'before':before,'after':after,'population_gain':gain,
               'source_population_values_modified':False,'boundary_comparability_asserted':False,
               'already_admitted_point_confirmations':already_admitted_point_confirmations,
               'source_loader_at_candidate_generation_commit':'f86fdbd7ce2fb22474a4662e6e08aa259565dc9b',
               'inputs':pins,'outputs':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['new_edges','new_point_uses','population_gain','after']}))


if __name__ == '__main__': main()
