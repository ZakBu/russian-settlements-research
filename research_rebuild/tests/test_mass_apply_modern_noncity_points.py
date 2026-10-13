from research_rebuild.mass_linkage.apply_modern_noncity_points import (
    HOLD_IDS,
    code_match,
    raw_object_level_conflicts,
    source_evidence_conflicts,
)


def test_six_frozen_record_holds_are_exact_and_distinct():
    assert len(HOLD_IDS) == 6
    assert sum(v == 'provider_settlement_fias_value_duplicate' for v in HOLD_IDS.values()) == 3
    assert 'source_grain_settlement_shared_okato_review' in HOLD_IDS.values()
    assert 'border_near_or_simplification_uncertain' in HOLD_IDS.values()
    assert 'native_oktmo_linked_lineage_coverage_event' in HOLD_IDS.values()


def test_wrong_source_object_level_and_source_conflicts_are_hard_holds():
    assert raw_object_level_conflicts('Населенный пункт') == []
    assert raw_object_level_conflicts('Муниципальный район') == ['raw_2021_wrong_object_level']
    assert source_evidence_conflicts({'legacy_identity_conflict': True,
        'legacy_same_year_collision': False, 'is_federal_aggregate': False,
        'is_additive_settlement_record': True}) == ['source_evidence_identity_conflict_or_collision']
    assert source_evidence_conflicts({'legacy_identity_conflict': False,
        'legacy_same_year_collision': False, 'is_federal_aggregate': False,
        'is_additive_settlement_record': True}) == []
    # Query-receipt absence is recorded as a provenance limitation, not a veto.
    assert source_evidence_conflicts({'legacy_identity_conflict': False,
        'legacy_same_year_collision': False, 'is_federal_aggregate': False,
        'is_additive_settlement_record': True, 'provider_query_receipt_missing': True}) == []


def test_historical_code_match_allows_only_exact_or_explicit_numeric_zero_serialization():
    assert code_match('05253000020', '05253000020', False)
    assert code_match('5253000020.0', '05253000020', True)
    assert not code_match('5253000020', '05253000020', False)
    assert not code_match('05253000021.0', '05253000020', True)
