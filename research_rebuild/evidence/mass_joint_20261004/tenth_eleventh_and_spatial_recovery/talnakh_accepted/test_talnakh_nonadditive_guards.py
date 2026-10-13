"""Finite regressions for Talnakh parent partition and 2002 source-row union."""
import pathlib
import unittest
import pandas as pd

OUT = pathlib.Path(__file__).parent

class TalnakhScopedLayerGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.obs = pd.read_parquet(OUT / "scoped_primary_observations.parquet")
        cls.points = pd.read_parquet(OUT / "scoped_point_uses.parquet")
        cls.edges = pd.read_parquet(OUT / "accepted_typed_scope_edges.parquet")
        cls.schema = __import__('json').loads((OUT / "loader_schema.json").read_text())
        cls.parents = __import__('json').loads((OUT / "nonadditive_parent_partition_context.json").read_text())

    def test_child_rows_remain_inside_norilsk_parent_partitions(self):
        self.assertEqual(len(self.obs), 3)
        self.assertTrue(self.obs.national_additive.eq(False).all())
        self.assertTrue(self.obs.is_parent_additive.eq(False).all())
        p = {x['year']: x for x in self.parents['observations']}
        self.assertEqual(p[2002]['parent_total'], 221908)
        self.assertEqual(p[2002]['children_sum'], 221908)
        self.assertEqual(sum(p[2010]['districts'].values()), p[2010]['Norilsk_city_partition'])
        self.assertEqual(sum(p[2021]['districts'].values()), p[2021]['Norilsk_city_partition'])
        self.assertEqual(len(self.edges), 2)
        self.assertTrue(self.edges.parent_population_transfer.eq(False).all())

    def test_2002_core_union_joins_existing_id_without_duplicate_or_new_current_id(self):
        hook = self.schema['old_2002_union_hook']
        self.assertEqual(hook['source_record_id'], '2002:1_TOM_01_04.xls:0:8697')
        self.assertIn('do not append a duplicate', hook['action'])
        old = self.obs[self.obs.observation_year == 2002]
        self.assertEqual(len(old), 1)
        self.assertEqual(old.iloc[0].source_record_id, hook['source_record_id'])
        self.assertTrue(self.obs.current_entity_id.isna().all())
        self.assertTrue(self.obs.current_native_code_binding.eq(False).all())
        self.assertTrue(self.points.provider_identifier_binding_asserted.eq(False).all())

if __name__ == '__main__':
    unittest.main()
