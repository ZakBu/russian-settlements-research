"""The user-facing default must never silently return superseded SGRT models."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PrimaryPopulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=json.loads((ROOT/'data/catalog.json').read_text())
        if not cls.catalog.get('primary_dataset'):
            raise unittest.SkipTest('Primary population publication pending; frozen historical catalog retained')

    def test_default_and_current_are_only_the_population_foundation(self):
        selected={name:{r['path'] for r in self.catalog['files'] if name in r['profiles']}
                  for name in ['core','population','current']}
        self.assertEqual(selected['core'],selected['population'])
        self.assertEqual(selected['current'],selected['population'])
        self.assertEqual(len(selected['core']),6)
        self.assertTrue(all(p.startswith('data/population/') for p in selected['core']))
        legacy=[r for r in self.catalog['files'] if 'legacy_model' in r['profiles']]
        self.assertEqual(len(legacy),6)
        self.assertTrue(all(not {'core','current','population'}&set(r['profiles']) for r in legacy))

    def test_population_snapshot_and_coverage_are_explicit(self):
        d=self.catalog['primary_dataset']
        self.assertEqual(d['native_observations'],465929)
        self.assertEqual(d['ordinary_full3'],142765)
        self.assertEqual([r['credited_population'] for r in d['coverage']],[144637473,142172049,144329319])
        self.assertEqual([r['denominator'] for r in d['coverage']],[145166731,142856536,144699673])
        self.assertTrue(d['final_roster_exact_values_roots_flags_match'])
        self.assertIn('not percent of settlements',d['limits'][0])

if __name__=='__main__':unittest.main()
