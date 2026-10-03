import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / 'research_rebuild/mass_linkage/primary_2010_gap_inventory.py'
SPEC = importlib.util.spec_from_file_location('primary_2010_gap_inventory', MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Primary2010GapInventoryTests(unittest.TestCase):
    def test_real_gorod_prefix_localities_are_not_headers(self):
        # These names were lost by a historical startswith("Город") exclusion.
        for name in ('Городец', 'Городище', 'Городовиковск'):
            with self.subTest(name=name):
                row_kind, settlement_type, settlement_name = MODULE.classify_label(f'г. {name}')
                self.assertEqual((row_kind, settlement_type, settlement_name),
                                 ('settlement', 'город', name))

    def test_source_dash_is_preserved_and_positive_row_is_retained(self):
        row = MODULE.parse_count_tokens('село Проверочное 12 - 7 100,0 -')
        self.assertIsNotNone(row)
        self.assertEqual(row['row_kind'], 'settlement')
        self.assertEqual(row['population_raw'], '12')
        self.assertEqual(row['men_raw'], '-')
        self.assertEqual(row['women_raw'], '7')
        self.assertTrue(row['dash_present'])
        self.assertIsNone(row['population_interpreted'])

    def test_parent_aggregate_not_classed_as_additive_locality(self):
        row_kind, settlement_type, settlement_name = MODULE.classify_label(
            'город N с подчиненными населенными пунктами')
        self.assertEqual((row_kind, settlement_type, settlement_name),
                         ('aggregate_or_parent', None, None))


if __name__ == '__main__':
    unittest.main()
