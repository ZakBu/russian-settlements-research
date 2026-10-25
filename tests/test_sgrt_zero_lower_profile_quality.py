import sys
from pathlib import Path
import unittest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from lower_profile_quality import analyse, part_inventory


def fixture(names, districts=None):
    ids = ['a', 'b']
    ref = pd.DataFrame({'source_record_id': ids, 'name': names, 'region': ['region'] * 2,
        'district': districts or ['district'] * 2, 'settlement_type_2021': ['село'] * 2,
        'lat': [51., 51.], 'lon': [39., 39.], 'population_2021': [100, 200],
        'budget_population_credit': [True, True], 'analysis_origin': [True, True]})
    members = pd.DataFrame({'unit_id': ['u', 'u'], 'origin_id': ids})
    units = pd.DataFrame({'unit_id': ['u'], 'inhabited_multi_np_service_area': [True],
        'member_geodesic_diameter_km': [0.], 'member_records': [2]})
    edges = pd.DataFrame({'origin_id': ids, 'provider_settlement_id': ['external', 'external'],
                          'l0_admitted': [True, True]})
    return ref, members, units, edges


class SourceGrainAndCentreTests(unittest.TestCase):
    def test_nova_usman_parts_are_not_two_whole_settlements_and_population_is_untouched(self):
        ref, members, units, edges = fixture(['Новая Усмань (часть 1)', 'Новая Усмань (часть 2)'])
        before = ref.copy(deep=True)
        result, quality, *_ = analyse(ref, members, units, edges)
        self.assertEqual(result['raw_multi_positive_source_record_profiles'], 1)
        self.assertEqual(result['profiles_with_at_least_two_diagnostic_entities_after_explicit_part_labels'], 0)
        self.assertEqual(quality.diagnostic_positive_entities_after_explicit_part_labels.iloc[0], 1)
        pd.testing.assert_frame_equal(ref, before)
        self.assertEqual(result['multi_profiles_all_known_np_suppliers_outside'], 1)

    def test_homonyms_and_distinct_district_parts_are_never_merged(self):
        ordinary = analyse(*fixture(['Ивановка', 'Ивановка']))[1]
        self.assertEqual(ordinary.diagnostic_positive_entities_after_explicit_part_labels.iloc[0], 2)
        different = analyse(*fixture(['Усмань (часть 1)', 'Усмань (часть 2)'], ['one', 'two']))[1]
        self.assertEqual(different.diagnostic_positive_entities_after_explicit_part_labels.iloc[0], 2)

    def test_word_part_in_proper_name_is_reviewed_without_parent_identity_invention(self):
        out, _ = part_inventory(pd.DataFrame({'name': ['Верхососенье Первая Часть', 'Большие Лызи 1 часть', 'Частихино']}))
        self.assertEqual(out.part_status.tolist(), ['part_word_in_name_identity_requires_review',
            'part_word_in_name_identity_requires_review', 'unmarked_whole_place_record'])

    def test_false_source_flag_is_not_truthy_and_unknown_provider_is_not_outside_proof(self):
        out, flags = part_inventory(pd.DataFrame({'name': ['Первое', 'Второе'], 'is_settlement_part': ['False', 'True']}))
        self.assertEqual(out.part_status.tolist(), ['unmarked_whole_place_record', 'explicit_source_part'])
        self.assertEqual(flags, ['is_settlement_part'])
        args = list(fixture(['Первое', 'Второе']))
        args[-1]['provider_settlement_id'] = None
        result, *_ = analyse(*args)
        self.assertEqual(result['multi_profiles_all_known_np_suppliers_outside'], 0)
        self.assertEqual(result['multi_profiles_without_any_known_np_supplier_in_membership'], 1)


if __name__ == '__main__':
    unittest.main()
