import pandas as pd
from research_rebuild.mass_linkage.historical_named_points import geo_name,named_objects,numeric_provider_code_equal


def test_literal_type_prefix_preserves_actual_city_names():
    assert geo_name('г Городец','г')=='городец'
    assert geo_name('Городец','г')=='городец'
    assert geo_name('г. Городище','г')=='городище'
    assert geo_name('Городовиковск','г')=='городовиковск'


def test_structured_type_is_required_with_exact_name():
    c=pd.DataFrame([{'historical_okato':'01234567001','is_settlement_raw':'t','name':'Городец','name_raw':'Городец','status':'город'}])
    g=pd.DataFrame([{'historical_okato':'01234567001','name_raw':'г Городец','settlement_type_raw':'г','kod3_raw_text':'001'}])
    result=named_objects(c,g)
    assert result.iloc[0].historical_name_exact and result.iloc[0].historical_type_exact
    g.loc[0,'settlement_type_raw']='п'
    assert not named_objects(c,g).iloc[0].historical_type_exact


def test_urban_zero_group_join_preserves_raw_codes_and_checks_type():
    c=pd.DataFrame([{'historical_okato':'01401000','is_settlement_raw':'t','name':'Барнаул','name_raw':'Барнаул','status':'город'}])
    g=pd.DataFrame([{'historical_okato':'01401000000','name_raw':'Барнаул','settlement_type_raw':'г','kod3_raw_text':'000'}])
    r=named_objects(c,g).iloc[0]
    assert r.historical_okato_2009_raw=='01401000'
    assert r.historical_okato_2011_raw=='01401000000'
    assert r.historical_name_exact and r.historical_type_exact
    g.loc[0,'kod3_raw_text']='001'
    assert not named_objects(c,g).iloc[0].historical_code_structure_compatible


def test_numeric_cell_comparison_does_not_pad_native_textual_codes():
    assert numeric_provider_code_equal(3401000000.0,'03401000000')
    assert numeric_provider_code_equal('3401000000.0','03401000000')
    assert not numeric_provider_code_equal('3401000000','03401000000')
    assert not numeric_provider_code_equal(3401000000.1,'03401000000')
    assert not numeric_provider_code_equal(3401000000.0,'03401000001')
