import pandas as pd
import unittest

from research_rebuild.mass_linkage.coordinate_residual_candidates import (
    GEO_TYPE_2011,
    admin_norm,
    classify,
    code_text,
    enrich_historical_candidates,
    geo_name_typed_2011,
    norm,
    strict_code_text,
    type_norm,
)


class CoordinateResidualCandidateTests(unittest.TestCase):
  def test_code_text_keeps_width_and_leading_zeroes(self):
    self.assertEqual(code_text('01201802001'), '01201802001')
    self.assertEqual(code_text('01201802001.0'), '01201802001')
    self.assertNotEqual(code_text('1201802001'), code_text('01201802001'))


  def test_small_normalizers_are_narrow(self):
    self.assertEqual(norm('Ёлки'), 'елки')
    self.assertEqual(type_norm('пгт'), 'поселок городского типа')
    self.assertEqual(admin_norm('Кирилловский муниципальный район'), 'кирилловский район')


  def test_versioned_literal_code_and_anchored_historical_name(self):
    self.assertEqual(strict_code_text('01201802001'), ('01201802001', 'native_digits'))
    self.assertEqual(strict_code_text('01201802001.0'), ('01201802001', 'provider_integer_looking_dot_zero_serialization_normalized'))
    self.assertEqual(strict_code_text('01201802001.000'), ('01201802001', 'provider_integer_looking_dot_zero_serialization_normalized'))
    self.assertEqual(strict_code_text('1.201802001E10'), ('', 'invalid_or_nonliteral_code'))
    self.assertEqual(geo_name_typed_2011('г Великие Луки', 'г'), 'Великие Луки')
    self.assertEqual(geo_name_typed_2011('Великие Луки', 'г'), 'Великие Луки')
    self.assertEqual(geo_name_typed_2011('село Великие Луки', 'г'), 'село Великие Луки')
    self.assertEqual(GEO_TYPE_2011['ст'], 'станция')
    self.assertEqual(GEO_TYPE_2011['ст-ца'], 'станица')
    self.assertEqual(geo_name_typed_2011('ж/д ст Примерово', 'ж/д ст'), 'Примерово')


  def test_exact_historical_name_region_and_admin_stays_candidate_only(self):
    rem = pd.DataFrame([{
        'source_record_id': 'r1', 'raw_okato_dadata': '01205804001', 'raw_oktmo': '01234567890',
        'raw_oktmo_dadata': '99999999999', 'settlement_name': 'Примерово', 'settlement_type': 'деревня',
        'raw_region': 'Алтайский край', 'raw_mun_upper': 'Тестский муниципальный район',
        'raw_mun_lower': 'Сельское поселение', 'source_object_is_naselenniy_punkt': True,
        'source_is_aggregate_scope': False, 'provider_general_fias_id': 'fias-1',
        'provider_fias_level': '6', 'provider_name_exact_selected_name': True,
        'provider_type_exact_selected_type': True, 'provider_point_valid_wgs84': True,
        'provider_point_in_coarse_russia_envelope': True, 'baseline_provider_coordinate_conflict': False,
        'provider_general_fias_duplicate_count': 1, 'provider_coordinate_duplicate_count': 1,
        'gate_provider_secondary_settlement_id_not_contradictory': True, 'population': 10,
        'candidate_family_exact_named_physical_np_fias_point': True,
    }])
    geo = pd.DataFrame(columns=['historical_okato', 'historic_name', 'historic_type', 'is_deleted', 'region_code2', 'historical_region_name', 'oktmo_2011_raw', 'historical_admin_parent_name', 'same_name_type_region_count'])
    cls = pd.DataFrame([{
        'historical_okato': '01205804001', 'historic_name': 'Примерово', 'historic_type': 'деревня',
        'is_settlement_raw': 't', 'region_code2': '01', 'historical_region_name': 'Алтайский край',
        'source_snapshot_version': 'test', 'historical_admin_parent_name': 'Тестский район', 'same_name_type_region_count': 2,
    }])
    out = classify(enrich_historical_candidates(rem, geo, cls))
    self.assertTrue(bool(out.loc[0, 'candidate_rule_historical_exact_named_okato_region_admin']))
    self.assertTrue(bool(out.loc[0, 'candidate_rule_union']))
    self.assertTrue(bool(out.loc[0, 'provider_coordinate_candidate_only']))
    self.assertFalse(bool(out.loc[0, 'external_fias_binding_admission']))
    self.assertFalse(bool(out.loc[0, 'coordinate_admission']))


  def test_current_code_route_needs_exact_string_and_unique_selected_code(self):
    row = {
        'source_object_is_naselenniy_punkt': True, 'source_is_aggregate_scope': False,
        'provider_general_fias_id': 'fias-1', 'provider_fias_level': '6',
        'provider_name_exact_selected_name': True, 'provider_type_exact_selected_type': True,
        'provider_point_valid_wgs84': True, 'provider_point_in_coarse_russia_envelope': True,
        'baseline_provider_coordinate_conflict': False, 'provider_general_fias_duplicate_count': 1,
        'provider_coordinate_duplicate_count': 1, 'gate_provider_secondary_id_not_contradictory': True,
        'provider_oktmo_equals_source_oktmo_exact_digits': True, 'source_oktmo_unique_in_selected_np': True,
        'geo_named_code_region_admin_match': False, 'class_named_code_region_admin_match': False,
        'candidate_family_exact_named_physical_np_fias_point': True,
    }
    frame = pd.DataFrame([row])
    # classify expects the exact column name from the screen rule.
    frame['gate_provider_secondary_settlement_id_not_contradictory'] = True
    result = classify(frame)
    self.assertTrue(bool(result.loc[0, 'candidate_rule_current_exact_oktmo']))
    frame['source_oktmo_unique_in_selected_np'] = False
    self.assertFalse(bool(classify(frame).loc[0, 'candidate_rule_current_exact_oktmo']))


if __name__ == '__main__':
    unittest.main()
