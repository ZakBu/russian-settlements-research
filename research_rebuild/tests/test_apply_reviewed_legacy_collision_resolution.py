"""Narrow regression tests for reviewed legacy-crosswalk collision resolutions."""
import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from research_rebuild.mass_linkage import apply_reviewed_mass_extensions_20261004 as app


def pin(path):
    return {'path': str(path), 'sha256': app.sha(path)}


def write_csv(path, rows):
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def make_review_scope(tmp_path, *, row=None, status='independent_legacy_collision_resolution_review_complete_candidate_only',
                      flagged=True, additive=True, federal=False, successor=None):
    evidence = tmp_path / 'source_evidence.parquet'
    pd.DataFrame([
        {'source_record_id':'old','source_evidence_json':json.dumps({
            'legacy_same_year_collision':flagged,'is_additive_settlement_record':additive,
            'is_federal_aggregate':federal,'legacy_verified_successor_settlement_id':successor})},
        {'source_record_id':'new','source_evidence_json':json.dumps({
            'legacy_same_year_collision':False,'is_additive_settlement_record':True,
            'is_federal_aggregate':False,'legacy_verified_successor_settlement_id':None})},
    ]).to_parquet(evidence,index=False)
    eligible=tmp_path/'eligible.csv'
    rows=[row or {'source_record_id':'old','from_source_record_id':'old','to_source_record_id':'new',
                  'resolution_status':'independently_resolved_legacy_crosswalk_collision',
                  'proof_json':json.dumps({'basis':'independent exact-source review','pin':'row=12'})}]
    write_csv(eligible,rows)
    receipt=tmp_path/'review.json'
    receipt.write_text(json.dumps({'status':status,'eligible_csv_sha256':app.sha(eligible),
                                  'frozen_source_evidence_sha256':app.sha(evidence)}))
    manifest={'frozen':{'source_evidence':pin(evidence)},
              'legacy_collision_resolution_reviews':[{'eligible':pin(eligible),'review_receipt':pin(receipt)}]}
    selected=pd.DataFrame([{'source_record_id':'old','census_year':2002},
                           {'source_record_id':'new','census_year':2021}])
    return manifest,selected,eligible,receipt


def test_exact_flagged_pair_endpoint_scope_loads_and_pins(tmp_path):
    manifest,selected,eligible,receipt=make_review_scope(tmp_path)
    resolutions,records=app.load_legacy_collision_resolution_reviews(manifest,selected)
    key=('old','new','old')
    assert key in resolutions
    assert resolutions[key]['resolution_status']=='independently_resolved_legacy_crosswalk_collision'
    assert resolutions[key]['proof_json']
    assert records[0]['eligible']['sha256']==app.sha(eligible)
    assert records[0]['review_receipt']['sha256']==app.sha(receipt)


def test_unpinned_eligible_csv_fails(tmp_path):
    manifest,selected,eligible,_=make_review_scope(tmp_path)
    eligible.write_text(eligible.read_text()+'\n')
    with pytest.raises(ValueError,match='legacy collision eligible endpoints.*checksum mismatch'):
        app.load_legacy_collision_resolution_reviews(manifest,selected)


def test_unreviewed_receipt_status_fails(tmp_path):
    manifest,selected,_,_=make_review_scope(tmp_path,status='candidate_only')
    with pytest.raises(ValueError,match='unexpected legacy collision resolution review status'):
        app.load_legacy_collision_resolution_reviews(manifest,selected)


def test_wrong_pair_endpoint_fails(tmp_path):
    row={'source_record_id':'unselected','from_source_record_id':'old','to_source_record_id':'new',
         'resolution_status':'independently_resolved_legacy_crosswalk_collision','proof_json':'{"basis":"checked"}'}
    manifest,selected,_,_=make_review_scope(tmp_path,row=row)
    with pytest.raises(ValueError,match='endpoint must be one endpoint'):
        app.load_legacy_collision_resolution_reviews(manifest,selected)


def test_missing_or_empty_proof_fails(tmp_path):
    for proof in ('', '{}', '[]', 'not-json'):
        case=tmp_path/('empty' if not proof else proof.replace('/','_'));case.mkdir(exist_ok=True)
        row={'source_record_id':'old','from_source_record_id':'old','to_source_record_id':'new',
             'resolution_status':'independently_resolved_legacy_crosswalk_collision','proof_json':proof}
        manifest,selected,_,_=make_review_scope(case,row=row)
        with pytest.raises(ValueError,match='proof'):
            app.load_legacy_collision_resolution_reviews(manifest,selected)


def test_wrong_resolution_status_fails(tmp_path):
    row={'source_record_id':'old','from_source_record_id':'old','to_source_record_id':'new',
         'resolution_status':'resolved','proof_json':'{"basis":"checked"}'}
    manifest,selected,_,_=make_review_scope(tmp_path,row=row)
    with pytest.raises(ValueError,match='unsupported legacy collision resolution status'):
        app.load_legacy_collision_resolution_reviews(manifest,selected)


@pytest.mark.parametrize('kwargs,message',[
    ({'flagged':False},'not actually flagged'),
    ({'additive':False},'cannot waive aggregate'),
    ({'federal':True},'cannot waive aggregate'),
    ({'successor':'successor-id'},'cannot waive aggregate'),
])
def test_resolution_cannot_waive_unflagged_or_hard_source_conditions(tmp_path,kwargs,message):
    manifest,selected,_,_=make_review_scope(tmp_path,**kwargs)
    with pytest.raises(ValueError,match=message):
        app.load_legacy_collision_resolution_reviews(manifest,selected)


def test_unreviewed_candidate_collision_remains_blocked(tmp_path):
    candidate=tmp_path/'candidate.csv';eligible=tmp_path/'eligible.csv';receipt=tmp_path/'review.json'
    row={'from':'old','to':'new','family':'rule','status':'reviewed','collision':'true','relation':'same_place'}
    write_csv(candidate,[row]);write_csv(eligible,[{'from':'old','to':'new','family':'rule'}]);receipt.write_text('{}')
    spec={'candidate':pin(candidate),'eligible':pin(eligible),'review_receipt':pin(receipt),
          'candidate_columns':{'from':'from','to':'to','family':'family','status':'status','collision':'collision'},
          'eligible_columns':{'from':'from','to':'to','family':'family'},
          'accepted_candidate_statuses':['reviewed'],'exclude_if_true':['collision']}
    with pytest.raises(ValueError,match=r'blocked identity edge \(collision\)'):
        app.load_identity({'identity_sources':[spec],'_reviewed_at':'2026-10-04T00:00:00+00:00'})


def test_candidate_collision_only_passes_exact_reviewed_pair_scope(tmp_path):
    manifest,selected,_,_=make_review_scope(tmp_path)
    resolutions,records=app.load_legacy_collision_resolution_reviews(manifest,selected)
    candidate=tmp_path/'candidate.csv';eligible=tmp_path/'eligible.csv';receipt=tmp_path/'review.json'
    row={'from':'old','to':'new','family':'rule','status':'reviewed','source_evidence_same_year_collision_endpoint':'true','relation':'same_place'}
    write_csv(candidate,[row]);write_csv(eligible,[{'from':'old','to':'new','family':'rule'}]);receipt.write_text('{}')
    spec={'candidate':pin(candidate),'eligible':pin(eligible),'review_receipt':pin(receipt),
          'candidate_columns':{'from':'from','to':'to','family':'family','status':'status'},
          'eligible_columns':{'from':'from','to':'to','family':'family'},
          'accepted_candidate_statuses':['reviewed']}
    new,_=app.load_identity({'identity_sources':[spec],'_reviewed_at':'2026-10-04T00:00:00+00:00',
                             '_legacy_collision_resolutions':resolutions,
                             '_legacy_collision_resolution_review_records':records})
    assert len(new)==1
    assert new.loc[0,'legacy_same_year_collision_original_flag_endpoint_ids_json']=='["old"]'
    assert json.loads(new.loc[0,'legacy_collision_resolution_records_json'])[0]['source_record_id']=='old'


def test_resolution_for_one_pair_cannot_authorize_another_pair(tmp_path):
    manifest,selected,_,_=make_review_scope(tmp_path)
    resolutions,_=app.load_legacy_collision_resolution_reviews(manifest,selected)
    candidate=tmp_path/'candidate.csv';eligible=tmp_path/'eligible.csv';receipt=tmp_path/'review.json'
    row={'from':'old','to':'other','family':'rule','status':'reviewed',
         'source_evidence_same_year_collision_endpoint':'true','relation':'same_place'}
    write_csv(candidate,[row]);write_csv(eligible,[{'from':'old','to':'other','family':'rule'}]);receipt.write_text('{}')
    spec={'candidate':pin(candidate),'eligible':pin(eligible),'review_receipt':pin(receipt),
          'candidate_columns':{'from':'from','to':'to','family':'family','status':'status'},
          'eligible_columns':{'from':'from','to':'to','family':'family'},
          'accepted_candidate_statuses':['reviewed']}
    with pytest.raises(ValueError,match='global collision/event/federal block'):
        app.load_identity({'identity_sources':[spec],'_reviewed_at':'2026-10-04T00:00:00+00:00',
                           '_legacy_collision_resolutions':resolutions})


def test_collision_exception_does_not_waive_event_gate(tmp_path):
    manifest,selected,_,_=make_review_scope(tmp_path)
    resolutions,_=app.load_legacy_collision_resolution_reviews(manifest,selected)
    candidate=tmp_path/'candidate.csv';eligible=tmp_path/'eligible.csv';receipt=tmp_path/'review.json'
    row={'from':'old','to':'new','family':'rule','status':'reviewed','source_evidence_same_year_collision_endpoint':'true','event':'true','relation':'same_place'}
    write_csv(candidate,[row]);write_csv(eligible,[{'from':'old','to':'new','family':'rule'}]);receipt.write_text('{}')
    spec={'candidate':pin(candidate),'eligible':pin(eligible),'review_receipt':pin(receipt),
          'candidate_columns':{'from':'from','to':'to','family':'family','status':'status','event':'event'},
          'eligible_columns':{'from':'from','to':'to','family':'family'},
          'accepted_candidate_statuses':['reviewed'],'exclude_if_true':['event']}
    with pytest.raises(ValueError,match=r'blocked identity edge \(event\)'):
        app.load_identity({'identity_sources':[spec],'_reviewed_at':'2026-10-04T00:00:00+00:00',
                           '_legacy_collision_resolutions':resolutions})


def test_generic_collision_flag_is_never_waived_even_with_review(tmp_path):
    manifest,selected,_,_=make_review_scope(tmp_path)
    resolutions,_=app.load_legacy_collision_resolution_reviews(manifest,selected)
    candidate=tmp_path/'candidate.csv';eligible=tmp_path/'eligible.csv';receipt=tmp_path/'review.json'
    row={'from':'old','to':'new','family':'rule','status':'reviewed','collision':'true','relation':'same_place'}
    write_csv(candidate,[row]);write_csv(eligible,[{'from':'old','to':'new','family':'rule'}]);receipt.write_text('{}')
    spec={'candidate':pin(candidate),'eligible':pin(eligible),'review_receipt':pin(receipt),
          'candidate_columns':{'from':'from','to':'to','family':'family','status':'status','collision':'collision'},
          'eligible_columns':{'from':'from','to':'to','family':'family'},
          'accepted_candidate_statuses':['reviewed'],'exclude_if_true':['collision']}
    with pytest.raises(ValueError,match='blocked identity edge \\(collision\\)'):
        app.load_identity({'identity_sources':[spec],'_reviewed_at':'2026-10-04T00:00:00+00:00',
                           '_legacy_collision_resolutions':resolutions})


def test_direct_point_collision_remains_blocked_even_with_identity_scope(tmp_path):
    manifest,selected,_,_=make_review_scope(tmp_path)
    resolutions,_=app.load_legacy_collision_resolution_reviews(manifest,selected)
    assert resolutions
    with pytest.raises(ValueError,match='point target is not an additive unblocked'):
        app.validate_direct_point_source_evidence({'is_additive_settlement_record':True,
            'is_federal_aggregate':False,'legacy_same_year_collision':True},'old',{})


def test_actual_duplicate_year_component_still_fails(tmp_path):
    selected=pd.DataFrame([{'source_record_id':'a','census_year':2002},
                           {'source_record_id':'b','census_year':2002},
                           {'source_record_id':'c','census_year':2021}])
    with pytest.raises(ValueError,match='same-year union-find collision'):
        app.validate_components_have_unique_years(selected,[{'a','b','c'}])
    app.validate_components_have_unique_years(selected,[{'a','c'},{'b'}])


def test_authoritative_endpoint_check_is_pair_scoped_and_never_uses_stale_row(tmp_path):
    manifest,selected,_,_=make_review_scope(tmp_path)
    resolutions,_=app.load_legacy_collision_resolution_reviews(manifest,selected)
    evidence={'old':{'is_additive_settlement_record':True,'is_federal_aggregate':False,
                     'legacy_verified_successor_settlement_id':None,'legacy_same_year_collision':True},
              'new':{'is_additive_settlement_record':True,'is_federal_aggregate':False,
                     'legacy_verified_successor_settlement_id':None,'legacy_same_year_collision':False},
              'other':{'is_additive_settlement_record':True,'is_federal_aggregate':False,
                     'legacy_verified_successor_settlement_id':None,'legacy_same_year_collision':False}}
    pair=pd.DataFrame([{'from_source_record_id':'old','to_source_record_id':'new'}])
    app.validate_identity_source_evidence(pair,evidence,{},resolutions)
    wrong=pd.DataFrame([{'from_source_record_id':'old','to_source_record_id':'other'}])
    with pytest.raises(ValueError,match='without exact reviewed pair scope'):
        app.validate_identity_source_evidence(wrong,evidence,{},resolutions)
