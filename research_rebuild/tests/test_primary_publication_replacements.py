import json
import pandas as pd
import pytest
from research_rebuild.mass_linkage.apply_primary_publication_replacements import replace_selected, verify_review_projection
from research_rebuild.mass_linkage.coverage import sha


def data():
    selected=pd.DataFrame([{'source_record_id':'old','census_year':2010,'population':42.0,
        'population_value_quality':'confidentiality_perturbed_within_ten','settlement_name':'Городец','settlement_type':'город',
        'source_file':'secondary.xls','source_sheet':'1','source_row':5,'oktmo':None,'okato':None,
        'source_population_raw':None,'source_name_raw':'г. Городец','source_path':None,'source_sha256':None,'source_locator':None,
        'source_native_id':None,'population_scope':'settlement','entity_grain_status':None,'source_selection_component':None,
        'district_raw':'Район','latitude':1.0,'longitude':2.0,'fias_id':None,'men':None,'women':None}])
    proposals=pd.DataFrame([{'r2_source_record_id':'old','replacement_source_record_id':'ROSSTAT2010:T5:p1:l4',
        'stage_status':'proposed_pending_independent_review','old_population_r2':42,'old_population_quality':'confidentiality_perturbed_within_ten',
        'proposed_primary_population':75,'proposed_primary_men':35,'proposed_primary_women':40,'pdf_page':1,'printed_page':1,
        'text_line_start_pypdf':4,'text_line_end_pypdf':4,'table5_label_raw':'г. Городец','primary_raw_district':'Район',
        'primary_source_sha256':'pinned','primary_raw_direct_typed_locality_row':True,'raw_pdf_line_independent_pypdf':'г. Городец 75 35 40'}])
    return selected,proposals


def test_source_correction_keeps_old_count_and_does_not_copy_point_into_primary():
    selected,proposals=data();result,bindings=replace_selected(selected,proposals,proposals.replacement_source_record_id.tolist(),'pinned')
    assert result.iloc[0].population==75
    assert bindings.iloc[0].old_population==42 and bindings.iloc[0].population_delta==33
    assert result.iloc[0].population_value_quality_original_tag=='confidentiality_perturbed_within_ten'
    assert result.iloc[0].settlement_name=='Городец'
    assert pd.isna(result.iloc[0].latitude) and pd.isna(result.iloc[0].oktmo)
    assert selected.iloc[0].population==42


def test_population_difference_alone_does_not_allow_cross_census_replacement():
    selected,proposals=data();selected.loc[0,'census_year']=2002
    with pytest.raises(ValueError,match='within 2010'):replace_selected(selected,proposals,proposals.replacement_source_record_id.tolist(),'pinned')


def test_sex_subtotals_and_raw_source_pin_are_hard_gates():
    selected,proposals=data();proposals.loc[0,'proposed_primary_women']=41
    with pytest.raises(ValueError,match='sexes'):replace_selected(selected,proposals,proposals.replacement_source_record_id.tolist(),'pinned')
    proposals.loc[0,'proposed_primary_women']=40
    with pytest.raises(ValueError,match='hash'):replace_selected(selected,proposals,proposals.replacement_source_record_id.tolist(),'wrong')


def test_native_codes_of_other_years_and_null_population_are_preserved():
    selected,proposals=data();another=selected.iloc[0].copy();another.source_record_id='r2021';another.census_year=2021
    another.oktmo='00000012345';another.population=None;another.population_value_quality='primary'
    selected=pd.concat([selected,pd.DataFrame([another])],ignore_index=True)
    result,_=replace_selected(selected,proposals,proposals.replacement_source_record_id.tolist(),'pinned')
    assert result.iloc[1].oktmo=='00000012345' and pd.isna(result.iloc[1].population)


def test_second_batch_preserves_first_batch_and_unreplaced_quality_provenance():
    selected, proposals = data()
    selected = pd.concat([selected, selected.assign(source_record_id='old2'),
                          selected.assign(source_record_id='keep_protected')], ignore_index=True)
    first, _ = replace_selected(selected, proposals, proposals.replacement_source_record_id.tolist(), 'pinned')
    second_proposals = proposals.copy()
    second_proposals['r2_source_record_id'] = 'old2'
    second_proposals['replacement_source_record_id'] = 'ROSSTAT2010:T5:p1:l8'
    second_proposals['old_population_quality'] = 'secondary_confidentiality_protected_value_exact_scope_unverified'
    second, _ = replace_selected(first, second_proposals,
                                 second_proposals.replacement_source_record_id.tolist(), 'pinned')
    pd.testing.assert_frame_equal(first.iloc[[0, 2]], second.iloc[[0, 2]])
    assert second.iloc[0].source_raw_line == 'г. Городец 75 35 40'
    assert second.iloc[0].displaced_source_record_id == 'old'
    assert second.iloc[2].population_value_quality_original_tag == 'confidentiality_perturbed_within_ten'
    assert second.iloc[2].population_quality_limitation == first.iloc[2].population_quality_limitation


def test_population_review_adapter_cannot_swap_pair_or_primary_count(tmp_path):
    _, proposals = data()
    mapping = tmp_path/'approved.csv'
    pd.DataFrame([{'r2_source_record_id': 'old', 'reference_id': 'ROSSTAT2010:T5:p1:l4',
                   'population': 42, 'table5_population': 75}]).to_csv(mapping, index=False)
    independent = tmp_path/'independent.json'
    independent.write_text(json.dumps({'verdict': 'approve_same_census_binding', 'approved_pairs': 1,
                                       'mapping_csv': mapping.name, 'mapping_sha256': sha(mapping)}))
    review = {'decision_author': 'primary_agent_after_independent_validation',
              'independent_review_path': str(independent), 'independent_review_sha256': sha(independent),
              'approved_replacement_source_record_ids': ['ROSSTAT2010:T5:p1:l4']}
    verify_review_projection(review, proposals)
    changed = proposals.copy()
    changed.loc[0, 'r2_source_record_id'] = 'another_settlement'
    with pytest.raises(ValueError, match='approved publication pairs'):
        verify_review_projection(review, changed)
    changed = proposals.copy()
    changed.loc[0, 'proposed_primary_population'] = 76
    with pytest.raises(ValueError, match='reviewed population'):
        verify_review_projection(review, changed)


def test_application_preserves_the_replacement_id_inside_source_evidence(tmp_path, monkeypatch):
    from research_rebuild.mass_linkage import apply_primary_publication_replacements as module
    selected, proposals = data()
    pdf=tmp_path/'primary.pdf';pdf.write_bytes(b'fixture primary publication')
    monkeypatch.setattr(module,'PRIMARY',pdf)
    proposals['primary_source_sha256']=sha(pdf)
    paths={name:tmp_path/(name+'.parquet') for name in ['selected','graph','points','evidence','proposals']}
    selected.to_parquet(paths['selected'],index=False)
    pd.DataFrame(columns=['from_source_record_id','to_source_record_id','decision_status']).to_parquet(paths['graph'],index=False)
    pd.DataFrame(columns=['target_source_record_id']).to_parquet(paths['points'],index=False)
    pd.DataFrame([{'source_record_id':'old','source_evidence_json':json.dumps({'source_record_id':'old'})}]).to_parquet(paths['evidence'],index=False)
    proposals.to_parquet(paths['proposals'],index=False)
    review=tmp_path/'review.json'
    review.write_text(json.dumps({'verdict':'APPROVE_BOUNDED_PRIMARY_PUBLICATION_REPLACEMENTS',
        'selected_sha256':sha(paths['selected']),'proposals_sha256':sha(paths['proposals']),
        'primary_pdf_sha256':sha(pdf),'approved_replacement_source_record_ids':proposals.replacement_source_record_id.tolist()}))
    out=tmp_path/'accepted'
    module.apply(paths['selected'],paths['graph'],paths['points'],paths['evidence'],paths['proposals'],review,out)
    evidence=pd.read_parquet(out/'source_evidence.parquet').iloc[0]
    value=json.loads(evidence.source_evidence_json)
    assert value['source_record_id']==evidence.source_record_id=='ROSSTAT2010:T5:p1:l4'
    assert value['publication_binding_old_source_record_id']=='old'
    assert value['population']==75
