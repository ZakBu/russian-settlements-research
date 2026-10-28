import unittest

import pandas as pd

from scripts.sgrt_saratov.official_magnit import admitted_store, physical_locality


class OfficialMagnitTests(unittest.TestCase):
    def reference(self):
        return pd.DataFrame({
            'source_record_id': ['village', 'station'],
            'name': ['Питерка', 'Питерка'],
            'settlement_type_2021': ['село', 'поселок станции'],
            'district': ['Питерский', 'Питерский'],
            'lat': [50.68, 50.66], 'lon': [47.44, 47.44],
        })

    def test_cosmetics_opening_and_delivery_only_do_not_become_groceries(self):
        store = {'storeTypeV2': 'MC', 'isActive': True, 'status': 'STATUS_ACTIVE',
                 'deliveryTypeList': ['DELIVERY_TYPE_OFFLINE']}
        self.assertTrue(admitted_store(store))  # Моя цена, not М.Косметик.
        self.assertFalse(admitted_store({**store, 'storeTypeV2': 'DG'}))
        self.assertFalse(admitted_store({**store, 'storeTypeV2': 'MA'}))
        self.assertFalse(admitted_store({**store, 'status': 'STATUS_OPENING'}))
        self.assertFalse(admitted_store({**store, 'isActive': False}))
        self.assertFalse(admitted_store({**store, 'deliveryTypeList': ['DELIVERY_TYPE_DELIVERY']}))

    def test_explicit_village_type_beats_nearer_station_but_ambiguous_name_stays_held(self):
        reference = self.reference()
        result = physical_locality('Саратовская обл, с Питерка, ул Ленина, 1',
                                   50.661, 47.44, reference)
        self.assertEqual(result['source_record_id'], 'village')
        self.assertFalse(result['identity_is_nearest_only'])
        held = physical_locality('Саратовская обл, Питерка, ул Ленина, 1',
                                 50.661, 47.44, reference)
        self.assertIsNone(held['source_record_id'])
        self.assertEqual(held['literal_candidate_count'], 2)

    def test_street_name_and_large_coordinate_conflict_do_not_identify_a_settlement(self):
        reference = self.reference()
        street = physical_locality('Саратовская обл, ул Питерка, д 2', 50.68, 47.44, reference)
        self.assertIsNone(street['source_record_id'])
        distant = physical_locality('Саратовская обл, с Питерка, ул Ленина, 1',
                                    51.68, 47.44, reference)
        self.assertIsNone(distant['source_record_id'])
        self.assertEqual(distant['np_identity_basis'], 'held_literal_coordinate_conflict')

    def test_municipality_name_does_not_turn_into_the_city_settlement(self):
        reference = pd.DataFrame({'source_record_id': ['saratov'], 'name': ['Саратов'],
                                  'settlement_type_2021': ['город'], 'district': ['Саратов'],
                                  'lat': [51.5], 'lon': [46.]})
        municipal = physical_locality('Саратовская обл, городской округ Саратов, ул Ленина, 1',
                                       51.5, 46., reference)
        self.assertIsNone(municipal['source_record_id'])
        city = physical_locality('Саратовская обл, г Саратов, ул Ленина, 1',
                                  51.5, 46., reference)
        self.assertEqual(city['source_record_id'], 'saratov')


if __name__ == '__main__':
    unittest.main()
