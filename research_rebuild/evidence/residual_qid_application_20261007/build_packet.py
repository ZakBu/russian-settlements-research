#!/usr/bin/env python3
"""Fail-closed residual QID application packet for the Oct-7 live graph."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import pandas as pd

ROOT = Path('/workspace/russian-settlements-research')
OUT = ROOT / 'research_rebuild/evidence/residual_qid_application_20261007'
CAND = Path('/workspace/settlements-work/continuation_20261004/federal_and_history/historical_residual_status_diagnostic/current_qid_oldpair_year_binding_candidates.csv')
REVIEW = Path('/workspace/settlements-work/continuation_20261004/independent_review/review_wd_signature_delta_post2000_1951/all_qid_review.csv')
sys.path.insert(0, str(ROOT / 'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import State, normalize


def sha(path: Path) -> str:
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    state = State()
    cand = pd.read_csv(CAND, dtype=str, keep_default_na=False)
    review = pd.read_csv(REVIEW, dtype=str, keep_default_na=False)
    # Remove artifacts from any earlier exploratory build in this same assigned folder.
    stale = OUT / 'reviewed_candidates.csv'
    if stale.exists():
        stale.unlink()
    all_candidate_residual_count = int(cand.apply(lambda r:
        state.uf.find(r.old_2010_source_record_id) != state.uf.find(r.current_source_record_id), axis=1).sum())
    # Current-state residual only. Keep the original exact candidate screen intact.
    residual = cand[cand.review_candidate_eligible == 'True'].copy()
    residual = residual[residual.apply(lambda r:
        state.uf.find(r.old_2010_source_record_id) != state.uf.find(r.current_source_record_id), axis=1)]
    # One remaining pair has a unique exact typed regional key in 2010. Uniqueness
    # is necessary but not sufficient: the independent full competitor review holds it.
    source10 = state.obs[state.obs.census_year == 2010].copy()
    source10['_key'] = source10.apply(lambda r: '|'.join(normalize(r[c]) for c in
        ('settlement_name', 'settlement_type', 'region_norm')), axis=1)
    key_counts = source10['_key'].value_counts()
    def key(sid):
        r = state.by_id.loc[sid]
        return '|'.join(normalize(r[c]) for c in ('settlement_name','settlement_type','region_norm'))
    residual['_physical_key_count_2010'] = residual.old_2010_source_record_id.map(lambda sid: int(key_counts.get(key(sid), 0)))
    unique = residual[residual._physical_key_count_2010 == 1].copy()
    assert len(unique) == 1
    qid = unique.iloc[0].wikidata_qid
    adjudicated = review[review.wikidata_qid == qid]
    assert len(adjudicated) == 1
    rr = adjudicated.iloc[0]
    assert rr.decision == 'hold'
    assert 'multiple_QIDs' in rr.failures
    r = unique.iloc[0]
    sid10, sid02, sid21 = r.old_2010_source_record_id, r.old_2002_source_record_id, r.current_source_record_id
    old10, old02, current = state.by_id.loc[sid10], state.by_id.loc[sid02], state.by_id.loc[sid21]
    raw10 = Path('/workspace/settlements-raw') / r.old_2010_source_file
    raw02 = Path('/workspace/settlements-raw') / r.old_2002_source_file
    point = state.point_rows.get(sid21)
    assert point and sid10 not in state.point_rows
    origin = json.loads(r.accepted_current_point_origins_json)[0]
    point_file = Path(point['point_origin_file'])
    # QID competition is the decisive hold: do not emit an edge or point admission.
    hold = {
        'wikidata_qid': qid,
        'competing_qid': 'Q23871697',
        'review_decision': rr.decision,
        'review_failure': rr.failures,
        'hold_reason': 'Independent whole-alternative review finds the same exact 2002 and 2010 source endpoints assigned as candidates to two QIDs; a population signature cannot resolve this identity conflict.',
        'source_pair_signature_count': r.matching_source_pair_count,
        'current_state_2010_to_2021_connected': False,
        'old_2002_to_current_state_connected': state.uf.find(sid02) == state.uf.find(sid21),
        'physical_2010_name_type_region_key_cardinality': 1,
        'old_2010_source_record_id': sid10,
        'old_2002_source_record_id': sid02,
        'current_source_record_id': sid21,
        'wikidata_current_label_P764_P31_exact': all(r[k] == 'True' for k in ('fetched_ru_label_exact','fetched_p764_exact','fetched_physical_p31')),
        'identity_rule_candidate': 'exact_normalized_name_type_region_unique_2010_source_row_plus_exact_current_QID_binding_v1',
        'population_fingerprint_used_to_break_tie': False,
        'old_2010_name': old10.settlement_name, 'old_2010_type': old10.settlement_type,
        'old_2010_region': old10.region_norm,
        'current_name': current.settlement_name, 'current_type': current.settlement_type,
        'current_region': current.region_norm, 'current_oktmo': str(current.oktmo),
        'raw_2010_source_file': str(raw10), 'raw_2010_source_sha256': sha(raw10),
        'raw_2010_source_sheet': r.old_2010_source_sheet,
        'raw_2010_source_row_1based': int(float(r.old_2010_source_row)),
        'raw_2010_source_locator_json': j({'source_record_id':sid10,'file':str(raw10),'sha256':sha(raw10),'sheet':r.old_2010_source_sheet,'row_1based':int(float(r.old_2010_source_row))}),
        'raw_2002_source_file': str(raw02), 'raw_2002_source_sha256': sha(raw02),
        'raw_2002_source_sheet': r.old_2002_source_sheet,
        'raw_2002_source_row_1based': int(float(r.old_2002_source_row)),
        'raw_2002_source_locator_json': j({'source_record_id':sid02,'file':str(raw02),'sha256':sha(raw02),'sheet':r.old_2002_source_sheet,'row_1based':int(float(r.old_2002_source_row))}),
        'population_2002': r.old_2002_source_population,
        'population_2010': r.old_2010_source_population,
        'P1082_2002_delta': r.p1082_2002_delta, 'P1082_2010_delta': r.p1082_2010_delta,
        'candidate_point_latitude': point['latitude'], 'candidate_point_longitude': point['longitude'],
        'candidate_point_provider': origin.get('coordinate_provider',''),
        'candidate_point_origin_file': str(point_file),
        'candidate_point_origin_sha256': point['point_origin_sha256'],
        'candidate_point_origin_locator_json': j({'source_record_id':sid21,'point_origin_file':str(point_file),'sha256':point['point_origin_sha256'],'row_locator':point['point_origin_locator'],'provider_id':origin.get('coordinate_provider_id','')}),
        'point_use_status': 'held_with_identity_edge',
        'review_artifact': str(REVIEW),
        'review_artifact_sha256': sha(REVIEW),
    }
    pd.DataFrame([hold]).to_csv(OUT / 'reviewed_holds.csv', index=False)
    # Standard shaped accepted files are deliberately header-only after the independent hold.
    edge_cols = ['from_source_record_id','from_year','to_source_record_id','to_year','relation','decision_status','from_population','to_population','population_ratio_max_over_min','identity_rule','coordinate_measurement_date_unknown','population_comparability_asserted','boundary_comparability_asserted']
    point_cols = ['target_source_record_id','target_year','latitude','longitude','coordinate_quality','coordinate_source','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','source_name','source_type','source_region','source_file','source_row','source_sha256','source_locator','coordinate_provenance','admission_rule','coordinate_admission_status','coordinate_measurement_date_unknown','boundary_comparability_asserted','population_scope_comparability_asserted','coordinate_application_family','application_inference_kind','direct_historical_coordinate_measurement','admission_allowed','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','population','population_value_quality','review_note']
    pd.DataFrame(columns=edge_cols).to_csv(OUT / 'accepted_identity_edge_delta.csv', index=False)
    pd.DataFrame(columns=point_cols).to_csv(OUT / 'accepted_point_use_delta.csv', index=False)
    inputs = {}
    for p in [CAND, REVIEW, raw10, raw02, point_file, *state.inputs]:
        p = Path(p)
        inputs[str(p)] = {'sha256': sha(p), 'bytes': p.stat().st_size}
    receipt = {
        'status':'no_residual_qid_admission_after_current_state_and_independent_competitor_review',
        'current_state':'State loaded from current_chain_state_20261007.py (base graph plus 9 accepted deltas)',
        'current_state_all_candidate_pairs_with_2010_endpoint_disconnected':all_candidate_residual_count,
        'current_state_residual_review_eligible_pairs':int(len(residual)),
        'current_state_pairs_passing_unique_2010_physical_key':int(len(unique)),
        'independently_held_unique_key_pairs':int(len(adjudicated)),
        'accepted_identity_edges':0,
        'accepted_point_uses':0,
        'population_values_changed':False,
        'identity_rule_screen':'Unique exact normalized name/type/region key in the full selected 2010 layer plus exact current QID label/P764/P31 checks. P1082/population values are not used to break ties.',
        'decisive_independent_review':{'path':str(REVIEW),'sha256':sha(REVIEW),'qid':qid,'decision':rr.decision,'failure':rr.failures},
        'why_point_not_applied':'The only residual unique-key candidate is held on QID competition; its otherwise accepted current point cannot be inherited before identity is resolved.',
        'inputs':inputs,
        'outputs':{},
        'limitations':['The 236-pair residual screen is candidate generation, not identity admission.','No residual candidate has both a unique 2010 physical source key and a clear full-alternative QID competition review.','No point value or population was changed.']
    }
    for name in ('reviewed_holds.csv','accepted_identity_edge_delta.csv','accepted_point_use_delta.csv'):
        p=OUT/name; receipt['outputs'][name]={'sha256':sha(p),'bytes':p.stat().st_size}
    (OUT/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (OUT/'README.md').write_text(
        '# Residual QID application 2026-10-07\n\n'
        'This packet rechecks the Oct-4 candidate pairs against the live Oct-7 graph state. The complete candidate screen has 236 source pairs whose 2010 endpoint is still disconnected; these remain candidates, not admitted links. Of the review-eligible subset, exactly one residual pair has a unique exact normalized 2010 name/type/region key.\n\n'
        'That pair is Q23871676 / Новая Деревня. The independent whole-alternative review in `review_wd_signature_delta_post2000_1951/all_qid_review.csv` marks it **hold** because the exact same 2002 and 2010 source endpoints compete with Q23871697. The exact population signature cannot resolve that conflict. Its current point is therefore recorded as a blocked candidate use, not applied.\n\n'
        '`reviewed_holds.csv` contains the raw source file hashes and sheet/row locators, selected source IDs, current code/claim checks, point-origin hash/locator JSON and the independent review pin. `accepted_identity_edge_delta.csv` and `accepted_point_use_delta.csv` are intentionally header-only. No population or point value changed.\n', encoding='utf-8')

if __name__ == '__main__': main()
