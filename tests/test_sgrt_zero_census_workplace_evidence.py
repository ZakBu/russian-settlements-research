"""Counterexamples to falsely complete commuting data and double counted geography."""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts/sgrt_zero'))
from census_workplace_evidence import (
    observed_count, outside_np_components, regional_geography, parse_regional,
)


class CensusWorkplaceEvidenceTests(unittest.TestCase):
    def test_suppressed_and_absent_counts_are_not_published_zero(self):
        for value in ('K', 'К', None):
            self.assertIsNone(observed_count(value))
        self.assertEqual(observed_count('-'), 0)
        self.assertEqual(observed_count('1,234'), 1234)
        with self.assertRaises(ValueError):
            observed_count('not reported')
        with self.assertRaisesRegex(ValueError, 'missing counts'):
            outside_np_components(100, 60, 80, 10, 0, None, 30)

    def test_regional_rendering_keeps_suppression_in_component_cell(self):
        content = ('**Test region**\n'
                   '**Городское население****100****100****100****0****0****0****0****0****0****0**\n'
                   'своего субъекта Российской Федерации 80\n'
                   'из них на территории своего населенного пункта 60\n'
                   'другого субъекта Российской Федерации K\n'
                   'на территории иностранного государства -\n'
                   'не указавшие территорию нахождения работы 20\n')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'fixture.md').write_text(content)
            row = parse_regional(root, 'fixture.md', 10)[('Test region', 'Городское население')]
        self.assertIsNone(row['other_region'])
        self.assertEqual(row['abroad'], 0)

    def test_outside_np_can_be_known_even_with_unknown_destination_subject(self):
        # Actual Moscow oblast2021: subtracting all unknown-territory workers
        # from all-minus-sameNP would lose75,508 explicitly reported outsideNP.
        row = outside_np_components(
            4273439, 3055370, 3361658, 622932, 1683, 287166, 1006411)
        self.assertEqual(row['same_subject_other_np'], 306288)
        self.assertEqual(row['outside_np_with_unknown_territory'], 75508)
        self.assertEqual(row['unresolved_np_location'], 211658)
        self.assertNotEqual(4273439 - 3055370 - 287166, 1006411)

    def test_known_outside_cannot_disappear_or_exceed_unresolved_workers(self):
        with self.assertRaisesRegex(ValueError, 'OutsideNP contradicts'):
            outside_np_components(100, 60, 80, 10, 0, 10, 29)
        with self.assertRaisesRegex(ValueError, 'OutsideNP contradicts'):
            outside_np_components(100, 60, 80, 10, 0, 10, 41)
        with self.assertRaisesRegex(ValueError, 'OwnNP'):
            outside_np_components(100, 81, 80, 10, 0, 10, 10)

    def test_inclusive_oblast_and_autonomous_subject_are_flagged_as_overlapping(self):
        for label in ('Архангельская область', 'Ненецкий автономный округ',
                      'Тюменская область', 'Ханты-Мансийский автономный округ – Югра',
                      'Ямало-Ненецкий автономный округ'):
            self.assertEqual(regional_geography(label), ('federal_subject', True))
        self.assertEqual(regional_geography('Архангельская область без автономного округа'),
                         ('subject_remainder_without_autonomous_okrug', False))
        self.assertEqual(regional_geography('Северо-Западный федеральный округ'),
                         ('federal_district', True))
        self.assertEqual(regional_geography('Саратовская область'), ('federal_subject', False))


if __name__ == '__main__':
    unittest.main()
