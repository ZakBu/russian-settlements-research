import json

import pandas as pd

from research_rebuild.mass_linkage.coordinate_validation_packet import (
    KNOWN_PHYSICAL_P31,
    metadata_entities,
    norm_code,
    p31_profile,
    population_band,
    strata_sample,
    text_key,
    _historical_matches,
    attach_wide_evidence,
    wikidata_type_lineage,
    _point_inside_source_region,
    is_physical_settlement_source,
)


def test_code_normalization_removes_only_provider_dot_zero_and_never_pads():
    assert norm_code('001234.0') == '001234'
    assert norm_code('1234') == '1234'
    assert norm_code('001234.0') != norm_code('1234')
    assert norm_code('1.234e3') is None


def test_p31_type_screen_preserves_unknowns_and_country_claims_are_not_blocks():
    profile = p31_profile(
        json.dumps([{'value_qid': 'Q532'}, {'value_qid': 'Q999999'}]),
        json.dumps([{'value_qid': 'Q212'}]),
    )
    assert profile['p31_known_physical_qids'] == ['Q532']
    assert profile['p31_unknown_semantics_qids'] == ['Q999999']
    assert profile['p17_has_ukraine'] is True
    assert profile['p17_has_russia'] is False
    assert profile['p17_geopolitical_claim_is_not_coordinate_block'] is True
    assert set(KNOWN_PHYSICAL_P31) == {'Q486972', 'Q532', 'Q515'}


def test_sample_is_fixed_seed_and_stratified_without_precision_claim():
    rows = []
    for i in range(140):
        rows.append({
            'source_record_id': f's{i:03d}',
            'settlement_type': 'город' if i % 8 == 0 else 'деревня',
            'population': [0, 15, 500, 5000, 25000][i % 5],
            'region_raw': f'Регион {i % 9}',
            'source_oktmo_digit_width': 10 if i % 3 == 0 else 11,
            'review_risk_flags_json': '[]' if i % 4 else '["review"]',
        })
    frame = pd.DataFrame(rows)
    first = strata_sample(frame, n=100, seed=20261002)
    second = strata_sample(frame, n=100, seed=20261002)
    assert first.source_record_id.tolist() == second.source_record_id.tolist()
    assert len(first) == 100
    assert first.sample_seed.eq(20261002).all()
    assert first.sample_stratum.nunique() > 50
    assert set(first.sample_stratum.str.split('|').str[0]) == {'urban', 'rural_or_other'}


def test_historical_match_requires_exact_code_and_carries_version_role():
    row = {'raw_oktmo': '001234', 'okato': '99', 'raw_okato_dadata': None,
           'raw_oktmo_dadata': None, 'settlement_name': 'Ёлкино', 'region_raw': 'Область А'}
    history = {
        ('oktmo_2011', '001234'): [{
            'historical_okato': '99', 'name_raw': 'Елкино', 'settlement_type_raw': 'д',
            'kladr': '001234000', 'oktmo_2011_raw': '001234', 'latitude': 67.0, 'longitude': -175.0,
            'source_snapshot_date': '2012-01-15', 'source_updated_at': '2011/06/20',
            'okato_2009_context': [{'historical_region_raw': 'Область А'}],
        }],
    }
    matches = _historical_matches(row, history)
    assert len(matches) == 1
    assert matches[0]['geokladr_label_exact_source_name']
    assert matches[0]['geokladr_region_exact_source_region']
    assert matches[0]['geokladr_coordinate_role'].startswith('historical_2011-era')
    row['raw_oktmo'] = '1234'  # no implicit leading-zero repair
    assert not _historical_matches(row, history)


def test_api_type_metadata_batches_are_flattened():
    metadata = {'batches': [
        {'data': {'entities': {'Q532': {'labels': {'en': {'value': 'village'}}}}}},
        {'data': {'entities': {'Q515': {'labels': {'en': {'value': 'city'}}}}}},
    ]}
    assert metadata_entities(metadata)['Q532']['labels']['en']['value'] == 'village'
    assert text_key('Ёлкино') == text_key('Елкино')
    assert population_band(10000) == '10k+'


def test_raw_wikidata_evidence_can_attach_to_overlapping_rule_samples():
    sample = pd.DataFrame({'source_record_id': ['r1', 'r1'], 'candidate_rule_family': ['A', 'B']})
    wide = pd.DataFrame({'source_record_id': ['r1'], 'wikidata_qid': ['Q1']})
    attached = attach_wide_evidence(sample, wide)
    assert len(attached) == 2
    assert attached.wikidata_sample_evidence_json.notna().all()
    assert all('Q1' in value for value in attached.wikidata_sample_evidence_json)


def test_type_lineage_keeps_physical_city_with_admin_parent_and_flags_admin_only():
    metadata = {'entities': {
        'Q_city_variant': {'claims': {'P279': [
            {'mainsnak': {'datavalue': {'value': {'id': 'Q515'}}}},
            {'mainsnak': {'datavalue': {'value': {'id': 'Q56061'}}}},
        ]}},
        'Q_admin': {'claims': {'P279': [
            {'mainsnak': {'datavalue': {'value': {'id': 'Q56061'}}}},
        ]}},
        'Q_village_variant': {'claims': {'P279': [
            {'mainsnak': {'datavalue': {'value': {'id': 'Q532'}}}},
        ]}},
        'Q_unknown': {'claims': {}},
    }}
    lineage = wikidata_type_lineage(metadata)
    assert lineage['Q_city_variant']['physical_settlement_lineage']
    assert not lineage['Q_city_variant']['admin_only_lineage_without_physical_settlement']
    assert lineage['Q_admin']['admin_only_lineage_without_physical_settlement']
    assert lineage['Q_village_variant']['physical_settlement_lineage']
    assert lineage['Q_unknown']['lineage_unknown_or_unresolved']


def test_expected_region_geometry_is_geographic_and_supports_negative_longitude():
    from shapely.geometry import Polygon
    inside, iso = _point_inside_source_region(65, -175, 'Chukotka', {'RU-CHU': Polygon([(-180, 60), (-170, 60), (-170, 70), (-180, 70)])}, {'chukotka': 'RU-CHU'})
    assert inside and iso == 'RU-CHU'
    outside, _ = _point_inside_source_region(55, -175, 'Chukotka', {'RU-CHU': Polygon([(-180, 60), (-170, 60), (-170, 70), (-180, 70)])}, {'chukotka': 'RU-CHU'})
    assert not outside


def test_federal_city_region_aggregates_are_not_settlement_point_sources():
    assert is_physical_settlement_source('город', 'settlement', True)
    assert not is_physical_settlement_source('город', 'federal_city_region', False)
    assert not is_physical_settlement_source('город', 'federal_city_region', True)
