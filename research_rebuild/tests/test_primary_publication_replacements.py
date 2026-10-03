import pandas as pd
import pytest
from research_rebuild.mass_linkage.apply_primary_publication_replacements import replace_selected


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
