import json
import tempfile
import unittest
from pathlib import Path

from research_rebuild.mass_linkage.stage_federal_named_population import (
    DEFAULT_RAW_2021,
    DEFAULT_REVIEW,
    DEFAULT_WORKBOOK,
    REVIEW_SHA256,
    label_parts,
    raw_source_point_candidates,
    review_records,
    stage,
)


class FederalNamedPopulationStageTests(unittest.TestCase):
    def test_exact_review_and_workbook_rows_yield_32_atomic_candidates(self):
        _, approved, held = review_records(DEFAULT_REVIEW, DEFAULT_WORKBOOK)
        self.assertEqual(len(approved), 32)
        self.assertEqual(sum(row['population'] for row in approved), 878643)
        self.assertEqual(sum(row['population'] for row in approved if row['federal_city'] == 'Санкт-Петербург'), 822633)
        self.assertEqual(sum(row['population'] for row in approved if row['federal_city'] == 'Севастополь'), 56010)
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]['source_row_excel_1based'], 7615)
        self.assertEqual(held[0]['label_raw'], 'Кронштадтский район - г. Кронштадт')
        self.assertTrue(all(row['men'] + row['women'] == row['population'] for row in approved))
        self.assertFalse(any(row['selected_into_primary_population'] for row in approved))

    def test_review_mutation_or_wrong_pin_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'review SHA-256'):
            review_records(DEFAULT_REVIEW, DEFAULT_WORKBOOK, '0' * 64)

    def test_printed_labels_preserve_type_and_sevastopol_name(self):
        self.assertEqual(label_parts('Санкт-Петербург', 'поселок Парголово'), ('Парголово', 'поселок'))
        self.assertEqual(label_parts('Санкт-Петербург', 'г. Колпино'), ('Колпино', 'город'))
        self.assertEqual(label_parts('Севастополь', 'Городское население - Балаклава'), ('Балаклава', None))
        self.assertEqual(label_parts('Севастополь', 'Городское население - поселок Кача'), ('Кача', 'поселок'))
        self.assertEqual(label_parts('Севастополь', 'Муниципальный округ г. Инкерман - городское население - г. Инкерман'), ('Инкерман', 'город'))

    def test_raw_point_screen_is_separate_and_only_unique_direct_matches_are_candidates(self):
        _, approved, _ = review_records(DEFAULT_REVIEW, DEFAULT_WORKBOOK)
        points = raw_source_point_candidates(approved, DEFAULT_RAW_2021)
        self.assertEqual(len(points), 32)
        direct = [row for row in points if row['point_candidate_status'].startswith('unique_exact')]
        self.assertEqual({row['settlement_name_from_population_label'] for row in direct},
                         {'Балаклава', 'Кача', 'Инкерман'})
        self.assertTrue(all(not row['point_binding_admitted'] and not row['identity_admitted']
                            and not row['coordinate_admitted'] for row in points))

    def test_stage_outputs_separate_source_delta_and_preserve_aggregate_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'stage'
            receipt = stage(DEFAULT_REVIEW, DEFAULT_WORKBOOK, DEFAULT_RAW_2021, output)
            self.assertEqual(receipt['approved_observation_rows'], 32)
            self.assertEqual(receipt['approved_population_total'], 878643)
            self.assertFalse(receipt['primary_selection_or_admission_performed'])
            self.assertFalse(receipt['existing_federal_aggregate_controls_modified'])
            observations = __import__('pandas').read_parquet(output / 'population_observations.parquet')
            self.assertEqual(len(observations), 32)
            self.assertTrue((observations['population_admission_allowed'] == False).all())
            self.assertEqual(receipt['review_sha256'], REVIEW_SHA256)
            self.assertTrue((output / 'held_review_rows.parquet').is_file())
            self.assertTrue((output / 'point_binding_candidates.parquet').is_file())


if __name__ == '__main__':
    unittest.main()
