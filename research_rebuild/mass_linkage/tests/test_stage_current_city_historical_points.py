import unittest

from research_rebuild.mass_linkage.stage_current_city_historical_points import (
    city_code_bridge_ok, stage_row,
)


class CurrentCityHistoricalPointTests(unittest.TestCase):
    def test_literal_city_bridge_keeps_both_raw_widths(self):
        self.assertTrue(city_code_bridge_ok('46228501', '46228501000', '000', 'город', 'г'))
        self.assertFalse(city_code_bridge_ok('46228501', '46228501000', '001', 'город', 'г'))
        self.assertFalse(city_code_bridge_ok('46228501', '046228501000', '000', 'город', 'г'))
        self.assertFalse(city_code_bridge_ok('46228501000', '46228501000', '000', 'город', 'г'))
        self.assertFalse(city_code_bridge_ok('46228501', '46228501000', '000', 'село', 'г'))

    def test_all_gates_candidate_only_and_origin_is_geokladr(self):
        row = {
            'census_year': 2021, 'type_norm': 'город', 'is_additive_settlement_record': True,
            'entity_grain_status': 'physical_np', 'historical_named_point_candidate': True,
            'screen_source_object_is_naselenniy_punkt': True, 'screen_source_is_aggregate_scope': False,
            'screen_raw_object_level': 'Населенный пункт',
            'historical_name_exact': True, 'historical_type_exact': True,
            'historical_point_modern_region': 'московская', 'region_norm': 'московская',
            'source_region_name_type_count': 1, 'historical_key_region_name_type_count': 1,
            'possible_unlocated_historical_competitor': False,
            'historical_okato_2009_raw': '46228501', 'historical_okato_2011_raw': '46228501000',
            'kod3_raw_text': '000', 'status': 'город', 'settlement_type_raw': 'г',
            'latitude_from_lat': 55.55715, 'longitude_from_long': 37.708714,
            'modern_provider_to_historical_point_km': 0.6,
        }
        result = stage_row(row, graph_ok=True, conflict_hold=False)
        self.assertTrue(result['candidate_only_direct_geokladr_2011_point'])
        self.assertFalse(result['admission_allowed'])
        self.assertFalse(result['provider_level_or_identifier_admitted'])
        self.assertEqual(result['point_origin_latitude'], row['latitude_from_lat'])

    def test_wrong_level_is_not_a_gate_but_actual_conflict_holds(self):
        row = {
            'census_year': 2021, 'type_norm': 'город', 'is_additive_settlement_record': True,
            'entity_grain_status': 'physical_np', 'historical_named_point_candidate': True,
            'screen_source_object_is_naselenniy_punkt': True, 'screen_source_is_aggregate_scope': False,
            'screen_raw_object_level': 'Населенный пункт',
            'historical_name_exact': True, 'historical_type_exact': True,
            'historical_point_modern_region': 'московская', 'region_norm': 'московская',
            'source_region_name_type_count': 1, 'historical_key_region_name_type_count': 1,
            'possible_unlocated_historical_competitor': False,
            'historical_okato_2009_raw': '46228501', 'historical_okato_2011_raw': '46228501000',
            'kod3_raw_text': '000', 'status': 'город', 'settlement_type_raw': 'г',
            'latitude_from_lat': 55.55715, 'longitude_from_long': 37.708714,
            'modern_provider_to_historical_point_km': 0.6,
            'provider_fias_level': '3', 'provider_general_fias_id': 'wrong-level-id',
        }
        self.assertTrue(stage_row(row, graph_ok=True, conflict_hold=False)['candidate_only_direct_geokladr_2011_point'])
        held = stage_row(row, graph_ok=True, conflict_hold=True)
        self.assertFalse(held['candidate_only_direct_geokladr_2011_point'])
        self.assertIn('no_known_conflict_hold', held['hold_reasons_json'])

    def test_provider_distance_threshold_is_not_relaxed(self):
        row = {
            'census_year': 2021, 'type_norm': 'город', 'is_additive_settlement_record': True,
            'entity_grain_status': 'physical_np', 'historical_named_point_candidate': True,
            'screen_source_object_is_naselenniy_punkt': True, 'screen_source_is_aggregate_scope': False,
            'screen_raw_object_level': 'Населенный пункт',
            'historical_name_exact': True, 'historical_type_exact': True,
            'historical_point_modern_region': 'московская', 'region_norm': 'московская',
            'source_region_name_type_count': 1, 'historical_key_region_name_type_count': 1,
            'possible_unlocated_historical_competitor': False,
            'historical_okato_2009_raw': '46228501', 'historical_okato_2011_raw': '46228501000',
            'kod3_raw_text': '000', 'status': 'город', 'settlement_type_raw': 'г',
            'latitude_from_lat': 55.55715, 'longitude_from_long': 37.708714,
            'modern_provider_to_historical_point_km': 1.0001,
        }
        self.assertFalse(stage_row(row, graph_ok=True, conflict_hold=False)['candidate_only_direct_geokladr_2011_point'])


if __name__ == '__main__':
    unittest.main()
