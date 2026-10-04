"""Guards against correcting the wrong assertion or inventing provider binding."""
import pytest
from research_rebuild.mass_linkage.apply_reviewed_point_supersessions_20261004 import reviewed_replacement


def fixture():
    old = {'target_source_record_id': '2010:old', 'coordinate_admission_status': 'reviewed_rule_accepted',
           'latitude': 54.0, 'longitude': 40.0, 'point_origin_sha256': 'old-source',
           'point_origin_locator': 'old:record=123', 'coordinate_provider_id': 'old-provider-id'}
    carrier = {'target_source_record_id': '2021:current', 'coordinate_admission_status': 'reviewed_rule_accepted',
               'latitude': 55.0, 'longitude': 41.0, 'point_origin_sha256': 'new-source',
               'point_origin_locator': 'new:row=456', 'coordinate_provider_id': 'current-provider-id'}
    approved = {'old_latitude': '54', 'old_longitude': '40', 'old_point_source_sha256': 'old-source',
                'proposed_latitude': '55', 'proposed_longitude': '41', 'proposed_point_origin_sha256': 'new-source',
                'proposed_point_origin_locator': 'new:row=456', 'year': '2010',
                'identity_and_population_unchanged': 'True', 'proposed_point_is_retrospective_current_representative': 'True'}
    return old, carrier, approved


@pytest.mark.parametrize('change', ['wrong_old_coordinate', 'wrong_carrier_origin', 'unaccepted_carrier', 'disconnected'])
def test_reject_unreviewed_or_unconnected_coordinate_change(change):
    old, carrier, approved = fixture()
    paths = ['actual-edge']
    if change == 'wrong_old_coordinate': old['latitude'] = 54.001
    if change == 'wrong_carrier_origin': carrier['point_origin_sha256'] = 'different-source'
    if change == 'unaccepted_carrier': carrier['coordinate_admission_status'] = 'candidate'
    if change == 'disconnected': paths = []
    with pytest.raises(AssertionError):
        reviewed_replacement(old, carrier, approved, 'review', 'ledger', paths)


def test_coordinate_transfer_does_not_bind_old_target_to_current_provider_id():
    old, carrier, approved = fixture()
    changes = reviewed_replacement(old, carrier, approved, 'review', 'ledger', ['actual-edge'])
    assert changes['coordinate_provider_id'] is None
    assert changes['point_supersession_carrier_provider_id'] == 'current-provider-id'
    assert changes['direct_historical_coordinate_measurement'] is False
    assert changes['boundary_comparability_asserted'] is False
    assert 'target_source_record_id' not in changes and 'population' not in changes
    assert changes['point_supersession_old_latitude'] == 54.0
