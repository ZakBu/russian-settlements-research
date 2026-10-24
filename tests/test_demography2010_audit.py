"""Substantive edge cases for the census trajectory diagnostic."""
import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec('pyarrow'), 'pyarrow required (requirements-handoff.txt)')
class Demography2010States(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.sgrt_pilot.audit_demography2010 import state
        cls.state = staticmethod(state)

    def test_zero_is_not_ordinary_stability(self):
        self.assertEqual(self.state(0, 0, 11), 'zero_both')
        self.assertEqual(self.state(0, 2, 11), 'zero_to_positive')
        self.assertEqual(self.state(2, 0, 11), 'positive_to_zero')
        self.assertEqual(self.state(2, 2, 11), 'stable')

    def test_missing_or_invalid_population_does_not_become_zero(self):
        for initial, final in [(None, 0), (0, None), (-1, 4), (3, float('inf')), (float('nan'), 3), (True, 2)]:
            self.assertEqual(self.state(initial, final, 11), 'unknown')

    def test_stability_band_and_direction_are_distinct(self):
        self.assertEqual(self.state(1000, 1010, 11), 'stable')
        self.assertEqual(self.state(1000, 1100, 11), 'growth')
        self.assertEqual(self.state(1000, 900, 11), 'decline')
        self.assertEqual(self.state(1000, 1010, 11, 0), 'growth')

    def test_invalid_time_span_and_threshold_are_rejected(self):
        for years, threshold in [(0, .0025), (-1, .0025), (11, -1), (11, 1)]:
            with self.assertRaises(ValueError):
                self.state(100, 100, years, threshold)


if __name__ == '__main__':
    unittest.main()
