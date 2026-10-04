"""Finite regressions for Kayerkan source-row joins and Norilsk partitions."""
import json
import pathlib
import unittest
import pyarrow.parquet as pq

OUT = pathlib.Path(__file__).parent

class KayerkanTypedScopeGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.obs = pq.read_table(OUT / 'scoped_primary_observations.parquet').to_pylist()
        cls.points = pq.read_table(OUT / 'scoped_point_uses.parquet').to_pylist()
        cls.edges = pq.read_table(OUT / 'accepted_typed_scope_edges.parquet').to_pylist()
        cls.schema = json.loads((OUT / 'loader_schema.json').read_text())
        cls.parents = json.loads((OUT / 'nonadditive_parent_partition_context.json').read_text())

    def test_schema_and_actual_year_source_ids(self):
        self.assertEqual(len(self.obs), 3)
        self.assertEqual({r['observation_year'] for r in self.obs}, {2002, 2010, 2021})
        byyear = {r['observation_year']: r for r in self.obs}
        self.assertEqual(byyear[2002]['source_record_id'], '2002:1_TOM_01_04.xls:0:8696')
        self.assertEqual(byyear[2002]['population'], 27116)
        self.assertIsNone(byyear[2010]['source_record_id'])
        self.assertIsNone(byyear[2021]['source_record_id'])
        self.assertEqual(self.schema['old_2002_union_hook']['source_record_id'], byyear[2002]['source_record_id'])
        self.assertIn('do not append a duplicate', self.schema['old_2002_union_hook']['action'])
        self.assertFalse(any(r['current_entity_id'] for r in self.obs))
        self.assertFalse(any(r['current_native_code_binding'] for r in self.obs))

    def test_parent_partitions_are_nonadditive_and_exact(self):
        self.assertTrue(all(r['national_additive'] is False for r in self.obs))
        self.assertTrue(all(r['is_parent_additive'] is False for r in self.obs))
        p = {r['year']: r for r in self.parents['observations']}
        self.assertEqual(p[2002]['children_sum'], p[2002]['parent_total'])
        self.assertEqual(p[2002]['separate_Norilsk_city'], 134832)
        self.assertEqual(p[2002]['Kayerkan'], 27116)
        self.assertEqual(sum(p[2010]['districts'].values()), p[2010]['Norilsk_city_partition'])
        self.assertEqual(sum(p[2021]['districts'].values()), p[2021]['Norilsk_city_partition'])
        self.assertEqual(len(self.edges), 2)
        self.assertTrue(all(r['parent_population_transfer'] is False for r in self.edges))

    def test_representative_point_is_not_historical_measurement_or_native_binding(self):
        self.assertEqual(len(self.points), 3)
        self.assertEqual({p['target_year'] for p in self.points}, {2002, 2010, 2021})
        self.assertTrue(all(p['subject_physical_place_qid'] == 'Q1020918' for p in self.points))
        self.assertTrue(all(p['direct_historical_coordinate_measurement'] is False for p in self.points))
        self.assertTrue(all(p['provider_identifier_binding_asserted'] is False for p in self.points))
        self.assertTrue(all(p['native_current_settlement_id_binding'] is False for p in self.points))

if __name__ == '__main__':
    unittest.main()
