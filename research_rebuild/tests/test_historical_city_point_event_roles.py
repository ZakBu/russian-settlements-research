from research_rebuild.mass_linkage.stage_historical_city_points import relevant_event_roles


def event(kind='absorbed_into_city', **kwargs):
    return {'event_id':'test','event_type':kind,'source_asserted_effective_date':'2005',
            'from_settlement_id_legacy_candidate':'RU-OKTMO-12300000002',
            'to_settlement_id_legacy_candidate':'RU-OKTMO-12300000001',**kwargs}


def test_only_absorption_receiver_is_exempt_from_point_veto():
    rows=relevant_event_roles([event()], '12300000001', 2002)
    assert rows and not rows[0]['point_veto']
    assert rows[0]['boundary_comparability']=='not_asserted'
    assert relevant_event_roles([event()], '12300000002', 2002)[0]['point_veto']


def test_split_parent_remains_held_without_new_event_evidence():
    assert relevant_event_roles([event('split_created')], '12300000001', 2002)[0]['point_veto']
    assert relevant_event_roles([event('relocated')], '12300000001', 2002)[0]['point_veto']


def test_event_code_width_and_unknown_date_are_not_repaired():
    assert relevant_event_roles([event()], '12300000', 2002)==[]
    assert relevant_event_roles([event(source_asserted_effective_date='')], '12300000002', 2010)[0]['point_veto']
    assert relevant_event_roles([event()], '12300000002', 2010)==[]


def test_dual_role_and_unrecognized_role_fail_closed():
    e=event(from_settlement_id_legacy_candidate='RU-OKTMO-12300000001')
    assert relevant_event_roles([e], '12300000001', 2002)[0]['point_veto']
