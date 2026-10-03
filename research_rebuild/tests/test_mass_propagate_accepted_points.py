import pandas as pd

from research_rebuild.mass_linkage.propagate_accepted_points import approved_edges, event_codes, samept


def test_only_accepted_same_place_edges_are_propagation_paths():
    frame = pd.DataFrame([
        {'relation': 'same_place', 'decision_status': 'checked_rule_accepted'},
        {'relation': 'same_place', 'decision_status': 'candidate'},
        {'relation': 'renamed_to', 'decision_status': 'checked_rule_accepted'},
    ])
    result = approved_edges(frame)
    assert len(result) == 1
    assert result.iloc[0].decision_status == 'checked_rule_accepted'


def test_event_index_uses_exact_native_oktmo_ids_and_keeps_date_context():
    events = [{'event_id': 'split-a', 'event_type': 'split_created',
        'source_asserted_effective_date': '2014-05-05',
        'from_settlement_id_legacy_candidate': 'RU-OKTMO-12345',
        'to_settlement_id_legacy_candidate': 'RU-OKTMO-12346'}]
    index = event_codes(events)
    assert index['12345'][0] == {'event_id': 'split-a', 'year': 2014, 'event_type': 'split_created'}
    assert index['12346'][0]['event_id'] == 'split-a'
    assert '012345' not in index


def test_carrier_coordinate_equality_is_exact():
    assert samept(55, 37, 55.0, 37.0)
    assert not samept(55, 37, 55.0000001, 37.0)
