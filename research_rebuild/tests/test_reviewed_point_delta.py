import json
import pandas as pd
import pytest
from research_rebuild.mass_linkage.admit_reviewed_point_delta import admit
from research_rebuild.mass_linkage.coverage import sha


def fixture(tmp_path):
    raw=tmp_path/'source.dbf';raw.write_bytes(b'raw point assertion')
    row={'target_source_record_id':'old','target_year':2002,'latitude':50.0,'longitude':40.0,
         'coordinate_admission_status':'reviewed_rule_accepted','coordinate_quality':'automatically_accepted_checked_rule',
         'admission_allowed':True,'point_origin_file':str(raw),'point_origin_sha256':sha(raw),'point_origin_locator':'row=1',
         'boundary_comparability_asserted':False,'population_scope_comparability_asserted':False,'direct_historical_coordinate_measurement':False}
    base=tmp_path/'base.parquet';pd.DataFrame([row]).to_parquet(base,index=False)
    new={**row,'target_source_record_id':'new','coordinate_admission_status':'staged_candidate_pending_root_review','admission_allowed':False}
    staged=tmp_path/'staged.parquet';pd.DataFrame([new]).to_parquet(staged,index=False)
    review=tmp_path/'review.json'
    review.write_text(json.dumps({'verdict':'APPROVE_BOUNDED_POINT_DELTA','base_point_uses_sha256':sha(base),
        'staged_point_uses_sha256':sha(staged),'approved_target_source_record_ids':['new']}))
    return base,staged,review,raw


def test_append_keeps_old_scientific_values_and_binds_review(tmp_path):
    base,staged,review,_=fixture(tmp_path)
    receipt=admit(base,staged,review,tmp_path/'accepted')
    result=pd.read_parquet(receipt['output']['path'])
    pd.testing.assert_frame_equal(result.iloc[:1][pd.read_parquet(base).columns],pd.read_parquet(base),check_dtype=False)
    assert result.iloc[1].coordinate_admission_status=='reviewed_extension_rule_accepted'
    assert receipt['accepted_added']==1


def test_postreview_changed_candidate_is_rejected(tmp_path):
    base,staged,review,_=fixture(tmp_path)
    d=pd.read_parquet(staged);d.loc[0,'latitude']=51.0;d.to_parquet(staged,index=False)
    with pytest.raises(ValueError,match='Review input hash'):admit(base,staged,review,tmp_path/'accepted')


def test_changed_raw_origin_rejected_even_when_candidate_unchanged(tmp_path):
    base,staged,review,raw=fixture(tmp_path);raw.write_bytes(b'changed source')
    with pytest.raises(ValueError,match='Raw origin hash'):admit(base,staged,review,tmp_path/'accepted')


def test_approval_cannot_silently_cover_another_target(tmp_path):
    base,staged,review,_=fixture(tmp_path)
    d=json.loads(review.read_text());d['approved_target_source_record_ids']=['unreviewed'];review.write_text(json.dumps(d))
    with pytest.raises(ValueError,match='absent'):admit(base,staged,review,tmp_path/'accepted')
