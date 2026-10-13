import json
import pandas as pd
import pytest
from research_rebuild.mass_linkage.coverage import sha
from research_rebuild.mass_linkage.promote_coordinate_extensions import promote


def inputs(tmp_path):
    app=tmp_path/'app';norm=tmp_path/'norm';app.mkdir();norm.mkdir()
    df=pd.DataFrame([{'target_source_record_id':'Moscow-2002','coordinate_admission_status':'staged_candidate_pending_root_review','coordinate_application_family':'M_2002_moscow_standalone_physical_city_point','boundary_comparability_asserted':False,'latitude':55.75,'longitude':37.61}])
    df.to_parquet(app/'staged_proposed_point_uses.parquet',index=False)
    for field in ['point_origin_file','point_origin_sha256','point_origin_locator']:df[field]='verified-origin'
    p=norm/'normalized_point_uses.parquet';df.to_parquet(p,index=False)
    (norm/'receipt.json').write_text(json.dumps({'output':{'sha256':sha(p)},'original_columns_unchanged':True}))
    (app/'manifest.json').write_text('{}')
    review=tmp_path/'review.json';review.write_text(json.dumps({'verdict':'APPROVE this exact ledger','approved_new_point_uses':1,'normalized_point_uses_sha256':sha(p),'application_manifest_sha256':sha(app/'manifest.json')}))
    return norm,app,review


def test_review_cannot_be_reused_after_a_point_changes(tmp_path):
    norm,app,review=inputs(tmp_path)
    p=norm/'normalized_point_uses.parquet';df=pd.read_parquet(p);df.loc[0,'latitude']=1;df.to_parquet(p,index=False)
    with pytest.raises(ValueError,match='changed'):promote(norm,app,review,tmp_path/'out')


def test_approved_moscow_case_has_explicit_individual_quality(tmp_path):
    norm,app,review=inputs(tmp_path)
    promote(norm,app,review,tmp_path/'out')
    df=pd.read_parquet(tmp_path/'out/accepted_point_uses.parquet')
    assert df.coordinate_admission_status.iloc[0]=='reviewed_case_accepted'
    assert df.coordinate_quality.iloc[0]=='individually_reviewed'
