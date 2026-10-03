from types import SimpleNamespace

from research_rebuild.mass_linkage.apply_coordinate_extensions import (
    events_for, source_is_physical, valid_point, verify_path,
)


def test_valid_point_checks_wgs84_bounds_and_missing_values():
    assert valid_point(55.75, 37.6)
    assert not valid_point(91, 0)
    assert not valid_point(0, -181)
    assert not valid_point(None, 0)


def test_null_population_scope_is_not_a_physical_additive_row_veto():
    row = SimpleNamespace(settlement_name='Малое', settlement_type='деревня',
                          is_additive_settlement_record=True,
                          source_region_name_type_count=1, entity_grain_status=None,
                          population_scope=None, census_year=2002,
                          region_norm='тверская')
    ok, reasons = source_is_physical(row)
    assert ok
    assert reasons == []


def test_moscow_oblast_locality_and_pgt_are_not_federal_city_aggregates():
    row = SimpleNamespace(settlement_name='Пример', settlement_type='пгт',
                          is_additive_settlement_record=True,
                          source_region_name_type_count=1, entity_grain_status=None,
                          population_scope=None, census_year=2010,
                          region_norm='московская')
    ok, reasons = source_is_physical(row)
    assert ok
    assert reasons == []


def test_legacy_2010_physical_moscow_row_remains_on_explicit_aggregate_hold():
    row = SimpleNamespace(settlement_name='Москва', settlement_type='город',
                          is_additive_settlement_record=True,
                          source_region_name_type_count=1, entity_grain_status=None,
                          population_scope='settlement', census_year=2010,
                          region_norm='москва')
    ok, reasons = source_is_physical(row)
    assert not ok
    assert '2010_moscow_source_grain_legacy_aggregate_hold' in reasons


def test_accepted_graph_endpoint_can_resolve_duplicate_name_type_rows():
    row = SimpleNamespace(settlement_name='Пример', settlement_type='станция',
                          is_additive_settlement_record=True,
                          source_region_name_type_count=2, entity_grain_status=None,
                          population_scope=None, census_year=2010,
                          region_norm='тверская')
    ok, reasons = source_is_physical(row, require_unique_name_type=False)
    assert ok
    assert reasons == []


def test_historical_locality_type_names_are_recognized_as_physical_grain():
    for settlement_type in ('улус', 'населённый пункт', 'починок', 'аал', 'местечко', 'кордон'):
        row = SimpleNamespace(settlement_name='Пример', settlement_type=settlement_type,
                              is_additive_settlement_record=True,
                              source_region_name_type_count=1, entity_grain_status=None,
                              population_scope=None, census_year=2002,
                              region_norm='тверская')
        ok, reasons = source_is_physical(row)
        assert ok, (settlement_type, reasons)


def test_lineage_events_require_exact_code_key_and_relevant_year():
    event = {'event_id': 'split-x', 'event_type': 'split_created',
             'source_asserted_effective_date': '2014-05-05',
             'from_settlement_id_legacy_candidate': 'RU-OKTMO-12345678901',
             'note_raw': 'Малое'}
    matching = SimpleNamespace(oktmo='12345678901', oktmo_raw_text=None, oktmo_2011_raw=None)
    other_code_same_name = SimpleNamespace(oktmo='12345678902', oktmo_raw_text=None, oktmo_2011_raw=None)
    assert events_for(matching, [event], 2002, 2021) == ['split-x']
    assert events_for(matching, [event], 2002, 2011) == []
    assert events_for(other_code_same_name, [event], 2002, 2021) == []


def test_path_verification_requires_accepted_chained_exact_endpoints():
    edge = {'decision_id': 'e1', 'relation': 'same_place',
            'decision_status': 'checked_rule_accepted',
            'from_source_record_id': 'historic', 'to_source_record_id': 'modern'}
    assert verify_path('["e1"]', 'historic', 'modern', {'e1': edge}) == (True, '')
    assert verify_path('["e1"]', 'other', 'modern', {'e1': edge})[0] is False
    assert verify_path('["e1"]', 'historic', 'other', {'e1': edge})[0] is False
    rejected = {**edge, 'decision_status': 'pending_review'}
    assert verify_path('["e1"]', 'historic', 'modern', {'e1': rejected})[0] is False
