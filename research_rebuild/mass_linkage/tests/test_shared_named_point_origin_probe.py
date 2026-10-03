import pandas as pd

from research_rebuild.mass_linkage.shared_named_point_origin_probe import candidate_pairs, is_eventful, parse_geo_locator


def fixture_rows():
    rows = pd.DataFrame([
        {"point_origin_file":"geo.dbf","point_origin_sha256":"sha","point_origin_locator":"raw_dbf_record_number_1based=7;byte_offset_0based=60","name_norm":"альфа","type_norm":"село","region_norm":"регион","target_year":2002,"is_additive_settlement_record":True,"is_federal_aggregate":False,"population":10,"population_scope":"settlement","target_source_record_id":"a","lineage_event_roles_json":None,"legacy_identity_conflict":False,"legacy_same_year_collision":False,"known_point_conflict_hold":False,"latitude":55.0,"longitude":37.0,"point_origin_kind":"geokladr_2011_raw_dbf_coordinate","admission_rule":"extension_review_v1_conditional_generic_historical_geokladr_point","settlement_name":"Альфа","settlement_type":"село","region_raw":"регион","source_locator":"row=1","oktmo":""},
        {"point_origin_file":"geo.dbf","point_origin_sha256":"sha","point_origin_locator":"raw_dbf_record_number_1based=7;byte_offset_0based=60","name_norm":"альфа","type_norm":"село","region_norm":"регион","target_year":2010,"is_additive_settlement_record":True,"is_federal_aggregate":False,"population":11,"population_scope":"settlement","target_source_record_id":"b","lineage_event_roles_json":None,"legacy_identity_conflict":False,"legacy_same_year_collision":False,"known_point_conflict_hold":False,"latitude":55.0,"longitude":37.0,"point_origin_kind":"geokladr_2011_raw_dbf_coordinate","admission_rule":"extension_review_v1_conditional_generic_historical_geokladr_point","settlement_name":"Альфа","settlement_type":"село","region_raw":"регион","source_locator":"row=2","oktmo":""},
    ])
    geo = pd.DataFrame([{"record_number_1based":7,"record_byte_offset_0based":60,"source_sha256_2011":"sha","historical_okato_2011_raw":"001","name_raw_2011":"с Альфа","settlement_type_raw":"с","historical_point_modern_region":"регион","historical_key_region_name_type_count":1,"is_deleted":False,"is_settlement_raw":"t","historical_name_exact":True,"historical_type_exact":True,"name_key":"альфа","type_key_2011":"село","longitude_from_long":37.0,"latitude_from_lat":55.0}])
    hist = pd.DataFrame([{"target_source_record_id":"a","candidate_historical_okato_2009_raw":"001","candidate_historical_okato_2011_raw":"001","candidate_code_join_basis":"exact_raw_code","candidate_classifier_line":8,"candidate_classifier_sha256":"sha2009","candidate_geo_sha256":"sha","candidate_record_number":7,"candidate_byte_offset":60,"candidate_name_key":"альфа","candidate_type_key_2009":"село","candidate_historical_name_exact":True,"candidate_historical_type_exact":True,"candidate_code_structure_compatible":True,"candidate_is_settlement_raw":"t","candidate_source_region_name_type_count":1,"candidate_source_object_is_np":True,"candidate_source_is_aggregate_scope":False,"candidate_key_region_name_type_count":1,"candidate_possible_unlocated_competitor":False},{"target_source_record_id":"b","candidate_historical_okato_2009_raw":"001","candidate_historical_okato_2011_raw":"001","candidate_code_join_basis":"exact_raw_code","candidate_classifier_line":8,"candidate_classifier_sha256":"sha2009","candidate_geo_sha256":"sha","candidate_record_number":7,"candidate_byte_offset":60,"candidate_name_key":"альфа","candidate_type_key_2009":"село","candidate_historical_name_exact":True,"candidate_historical_type_exact":True,"candidate_code_structure_compatible":True,"candidate_is_settlement_raw":"t","candidate_source_region_name_type_count":1,"candidate_source_object_is_np":True,"candidate_source_is_aggregate_scope":False,"candidate_key_region_name_type_count":1,"candidate_possible_unlocated_competitor":False}])
    selected = pd.DataFrame([{"name_norm":"альфа","type_norm":"село","region_norm":"регион","census_year":2002,"source_record_id":"a"},{"name_norm":"альфа","type_norm":"село","region_norm":"регион","census_year":2010,"source_record_id":"b"}])
    return rows, selected, geo, hist


def test_strict_locator_and_event_parser():
    assert parse_geo_locator("raw_dbf_record_number_1based=7;byte_offset_0based=60") == (7, 60)
    assert parse_geo_locator("record=7;offset=60") is None
    assert not is_eventful("[]")
    assert is_eventful("not-json")


def test_same_literal_object_produces_candidate_only_pair():
    rows, selected, geo, hist = fixture_rows()
    pairs, groups = candidate_pairs(rows, selected, set(), geo, hist, set())
    assert len(pairs) == 1
    assert len(groups) == 1 and bool(groups.iloc[0].all_endpoint_gates_pass)
    assert pairs.iloc[0].candidate_only


def test_event_or_graph_component_blocks_pair():
    rows, selected, geo, hist = fixture_rows()
    rows.loc[1, "oktmo"] = "77"
    pairs, groups = candidate_pairs(rows, selected, set(), geo, hist, {"77"})
    assert pairs.empty
    rows, selected, geo, hist = fixture_rows()
    selected = pd.concat([selected, pd.DataFrame([{"name_norm":"альфа","type_norm":"село","region_norm":"регион","census_year":2021,"source_record_id":"c"}])], ignore_index=True)
    pairs, _ = candidate_pairs(rows, selected, {"c"}, geo, hist, set())
    assert pairs.empty


def test_missing_or_mismatched_raw_classifier_binding_blocks_pair():
    rows, selected, geo, hist = fixture_rows()
    hist.loc[1, "candidate_historical_okato_2009_raw"] = "002"
    pairs, groups = candidate_pairs(rows, selected, set(), geo, hist, set())
    assert pairs.empty
    assert not bool(groups.iloc[0].all_endpoint_gates_pass)
    rows, selected, geo, hist = fixture_rows()
    hist.loc[1, "candidate_historical_okato_2009_raw"] = None
    pairs, _ = candidate_pairs(rows, selected, set(), geo, hist, set())
    assert pairs.empty
