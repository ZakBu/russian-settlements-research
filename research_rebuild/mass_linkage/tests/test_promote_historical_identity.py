"""Regressions for a contradictory approval and same-count endpoint substitution."""
import json

import pandas as pd
import pytest

from research_rebuild.mass_linkage.apply_identity_rules import _sha
from research_rebuild.mass_linkage.promote_historical_identity import promote


def stage(tmp_path):
    staging = tmp_path/'staging'
    staging.mkdir()
    (staging/'receipt.json').write_text('{}\n')
    for name in ['application_checks.parquet', 'source_row_checks.parquet']:
        pd.DataFrame({'status': ['checked']}).to_parquet(staging/name, index=False)
    pd.DataFrame([{'from_source_record_id': 'a', 'to_source_record_id': 'b',
                   'relation': 'same_place', 'decision_status': 'pending_independent_application_review'}]).to_parquet(staging/'staged_identity_edges.parquet', index=False)
    review = {'verdict': 'APPROVE BOUNDED DELTA', 'scope': {'staged_new_pairs': 1},
              'pins': {key: _sha(staging/name) for key, name in [
                  ('application_receipt_sha256', 'receipt.json'),
                  ('application_checks_sha256', 'application_checks.parquet'),
                  ('source_row_checks_sha256', 'source_row_checks.parquet'),
                  ('staged_identity_edges_sha256', 'staged_identity_edges.parquet')]},
              'checks': {'literal_object_proof': True},
              'approved_pairs': [{'from_source_record_id': 'a', 'to_source_record_id': 'b'}]}
    return staging, review


def test_positive_verdict_with_failed_check_is_not_promoted(tmp_path):
    staging, decision = stage(tmp_path)
    decision['checks']['literal_object_proof'] = False
    review = tmp_path/'review.json'
    review.write_text(json.dumps(decision))
    with pytest.raises(ValueError, match='failed checks'):
        promote(staging, review, tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_same_count_different_reviewed_endpoint_is_not_promoted(tmp_path):
    staging, decision = stage(tmp_path)
    decision['approved_pairs'][0]['to_source_record_id'] = 'another_locality'
    review = tmp_path/'review.json'
    review.write_text(json.dumps(decision))
    with pytest.raises(ValueError, match='exact reviewed endpoint set'):
        promote(staging, review, tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_exact_review_promotes_without_changing_endpoints(tmp_path):
    staging, decision = stage(tmp_path)
    review = tmp_path/'review.json'
    review.write_text(json.dumps(decision))
    result = promote(staging, review, tmp_path/'out')
    rows = pd.read_parquet(tmp_path/'out/accepted_identity_edges.parquet')
    assert result['new_accepted_pairs'] == 1
    assert rows[['from_source_record_id', 'to_source_record_id']].iloc[0].tolist() == ['a', 'b']
    assert rows.decision_status.tolist() == ['checked_rule_accepted']


def test_promoted_edge_cannot_retain_optional_candidate_only_status(tmp_path):
    staging, decision = stage(tmp_path)
    path=staging/'staged_identity_edges.parquet'
    rows=pd.read_parquet(path)
    rows['candidate_status']='candidate_pending_independent_application_review'
    rows['admission_status']='not_admitted'
    rows['candidate_only']=True
    rows['coordinate_admitted']=False
    rows.to_parquet(path,index=False)
    decision['pins']['staged_identity_edges_sha256']=_sha(path)
    review=tmp_path/'review.json';review.write_text(json.dumps(decision))
    promote(staging,review,tmp_path/'out')
    new=pd.read_parquet(tmp_path/'out/accepted_identity_edges.parquet').iloc[0]
    assert new.admission_status=='checked_rule_accepted'
    assert new.candidate_status=='accepted_after_independent_application_review'
    assert not bool(new.candidate_only)
    assert not bool(new.coordinate_admitted)
