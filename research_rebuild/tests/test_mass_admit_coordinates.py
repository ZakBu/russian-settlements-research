import json

import pandas as pd

from research_rebuild.mass_linkage.admit_coordinates import (
    _proposal_rows,
    build_dsu,
    edge_path,
    normalized_code,
    physical_scope,
    union_candidate_points,
)


def test_code_normalization_only_removes_serialization_dot_zero():
    assert normalized_code('05653410126.0') == '05653410126'
    assert normalized_code('5653410126') == '5653410126'
    assert normalized_code('5653410126.00') is None
    assert normalized_code('  ') is None


def test_explicit_aggregate_flags_override_a_misleading_settlement_scope():
    physical, reasons = physical_scope({
        'population_scope': 'settlement',
        'settlement_type': 'город',
        'raw_object_level': 'Населенный пункт',
        'is_territorial_aggregate': True,
    })
    assert not physical
    assert 'explicit_is_territorial_aggregate' in reasons


def test_scope_label_alone_does_not_block_a_physical_city():
    physical, reasons = physical_scope({
        'population_scope': 'settlement',
        'settlement_type': 'город',
        'raw_object_level': 'Населенный пункт',
        'federal_city_region_scope': False,
        'is_territorial_aggregate': False,
    })
    assert physical
    assert reasons == []


def test_identical_coordinates_collapse_but_distinct_alternatives_hold_without_averaging():
    same = [
        {'latitude': 56.1, 'longitude': 44.2},
        {'latitude': 56.1, 'longitude': 44.2},
    ]
    collapsed = union_candidate_points(same)
    assert collapsed['distinct_point_count'] == 1
    assert collapsed['proposed_latitude'] == 56.1
    assert collapsed['proposed_longitude'] == 44.2
    assert collapsed['admission_allowed'] is False

    alternatives = [
        {'latitude': 56.1, 'longitude': 44.2},
        {'latitude': 56.2, 'longitude': 44.3},
    ]
    held = union_candidate_points(alternatives)
    assert held['distinct_point_count'] == 2
    assert held['proposed_latitude'] is None
    assert held['proposed_longitude'] is None
    assert held['point_choice_status'] == 'hold_multiple_distinct_coordinate_claims'


def test_forced_wikidata_multipoint_hold_cannot_be_overridden_by_other_provider_point():
    choice = union_candidate_points([{'latitude': 55.0, 'longitude': 37.0}], force_hold=True)
    assert choice['proposed_latitude'] is None
    assert choice['admission_allowed'] is False
    assert choice['point_choice_status'] == 'hold_ambiguous_multipoint_family'


def test_overlapping_candidate_families_form_one_nonaccepted_source_proposal():
    points = pd.DataFrame([
        {
            'source_record_id': 'S2021', 'target_year': 2021,
            'candidate_point_id': 'p-da', 'candidate_families_json': json.dumps(['A_rural_exact_code_and_own_name_type']),
            'coordinate_provider_family': 'tochno_dadata', 'coordinate_source_record_id': 'S2021',
            'coordinate_source_locator': 'raw.parquet:10', 'coordinate_provider_id': 'fias-a',
            'provider_general_fias_id': 'fias-a', 'settlement_provider_id': 'fias-a',
            'latitude': 56.1, 'longitude': 44.2, 'source_name': 'Тест', 'source_type': 'село',
            'source_region': 'Область', 'source_native_id': '123', 'source_file': 'raw.parquet',
            'source_row': 10, 'source_sha256': 'abc', 'source_oktmo_raw': '12345678901',
            'source_okato_raw': '12345678901', 'population_scope': 'settlement',
        },
        {
            'source_record_id': 'S2021', 'target_year': 2021,
            'candidate_point_id': 'p-wd', 'candidate_families_json': json.dumps(['C_wikidata_physical_source_city_point']),
            'coordinate_provider_family': 'wikimedia_wikidata_one_evidence_family', 'coordinate_source_record_id': 'S2021',
            'coordinate_source_locator': 'truthy.tsv:2', 'coordinate_provider_id': 'Q123',
            'provider_general_fias_id': 'fias-a', 'settlement_provider_id': 'fias-a',
            'latitude': 56.1, 'longitude': 44.2, 'source_name': 'Тест', 'source_type': 'село',
            'source_region': 'Область', 'source_native_id': '123', 'source_file': 'raw.parquet',
            'source_row': 10, 'source_sha256': 'abc', 'source_oktmo_raw': '12345678901',
            'source_okato_raw': '12345678901', 'population_scope': 'settlement',
        },
    ])
    families = pd.DataFrame([{
        'source_record_id': 'S2021',
        'candidate_families': ['A_rural_exact_code_and_own_name_type', 'C_wikidata_physical_source_city_point'],
        'entity_component_id': None, 'identity_graph_component_status': 'no_accepted_identity_graph_edge',
        'provider_id_binding_status': 'unresolved', 'holds': [], 'reviews': [],
        'wikidata_multipoint_review_hold': False,
    }])
    frozen = pd.DataFrame(columns=[
        'target_source_record_id', 'coordinate_claim_id', 'decision_id', 'target_year',
        'coordinate_source_record_id', 'latitude', 'longitude', 'decision_status', 'decision_rule',
        'temporal_applicability', 'evidence_uri', 'evidence_sha256',
    ])
    result = _proposal_rows(points, families, frozen)
    assert len(result) == 1
    assert set(json.loads(result.loc[0, 'candidate_families_json'])) == {
        'A_rural_exact_code_and_own_name_type', 'C_wikidata_physical_source_city_point'
    }
    assert result.loc[0, 'proposed_latitude'] == 56.1
    assert not bool(result.loc[0, 'admission_allowed'])
    assert result.loc[0, 'coordinate_admission_status'] == 'candidate_only_pending_independent_coordinate_review'


def test_known_hold_flags_null_out_candidate_point():
    points = pd.DataFrame([{
        'source_record_id': 'S2021', 'target_year': 2021, 'candidate_point_id': 'p1',
        'candidate_families_json': '[]', 'coordinate_provider_family': 'tochno_dadata',
        'coordinate_source_record_id': 'S2021', 'coordinate_source_locator': 'x:1',
        'coordinate_provider_id': 'fias-a', 'latitude': 56.1, 'longitude': 44.2,
        'source_name': 'Тест', 'source_type': 'село', 'source_region': 'Область',
    }])
    families = pd.DataFrame([{
        'source_record_id': 'S2021', 'candidate_families': ['A'], 'entity_component_id': None,
        'identity_graph_component_status': 'none', 'provider_id_binding_status': 'unresolved',
        'holds': ['provider_point_duplicate'], 'reviews': [], 'wikidata_multipoint_review_hold': False,
    }])
    frozen = pd.DataFrame(columns=[
        'target_source_record_id', 'coordinate_claim_id', 'decision_id', 'target_year',
        'coordinate_source_record_id', 'latitude', 'longitude', 'decision_status', 'decision_rule',
        'temporal_applicability', 'evidence_uri', 'evidence_sha256',
    ])
    row = _proposal_rows(points, families, frozen).iloc[0]
    assert row.proposed_latitude is None
    assert row.point_choice_status == 'hold_ambiguous_multipoint_family'
    assert not bool(row.admission_allowed)


def test_accepted_identity_component_path_is_traceable():
    edges = pd.DataFrame([
        {'from_source_record_id': 'old', 'to_source_record_id': 'middle', 'decision_id': 'e1'},
        {'from_source_record_id': 'middle', 'to_source_record_id': 'modern', 'decision_id': 'e2'},
    ])
    comp, members, adjacency = build_dsu(edges)
    assert comp['old'] == comp['modern']
    assert {'old', 'middle', 'modern'} == set(members[comp['old']])
    assert edge_path('old', 'modern', adjacency) == ['e1', 'e2']
