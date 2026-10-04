import csv
import json
import unittest
from pathlib import Path

import pyarrow.parquet as pq


OUT = Path('/workspace/settlements-work/continuation_20261004/root/accepted_type_false_zero_177_source_points')
OLD_EXPERIMENT = Path('/workspace/settlements-work/continuation_20261004/root/accepted_type_false_zero_177_points')
SEEDS = Path('/workspace/settlements-work/continuation_20261004/independent_review/type_false_zero_177_review/independently_eligible_point_seed_list.csv')
BASE = Path('/workspace/settlements-work/continuation_20261004/root/accepted_point_gap_five_reviewed_origin_reconciled/accepted_point_uses.parquet')


class AppliedTypeFalseZero177Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads((OUT / 'receipt.json').read_text())
        cls.base = pq.ParquetFile(BASE)
        cls.output = pq.ParquetFile(OUT / 'accepted_point_uses.parquet')

    def test_baseline_prefix_and_expected_delta_are_pinned(self):
        self.assertEqual(self.receipt['baseline_point_rows'], 414890)
        self.assertEqual(self.receipt['baseline_prefix_rows_verified'], 414890)
        self.assertTrue(self.receipt['baseline_prefix_all_columns_equal'])
        self.assertEqual(self.output.metadata.num_rows, self.base.metadata.num_rows + 358)
        self.assertEqual(self.receipt['output_point_rows'], self.output.metadata.num_rows)

    def test_direct_points_use_raw_publisher_coordinates_not_geonames_witness(self):
        add = pq.read_table(OUT / 'accepted_point_uses.parquet', columns=[
            'target_source_record_id', 'target_year', 'latitude', 'longitude',
            'coordinate_provider_id', 'coordinate_admission_status', 'point_origin_file',
            'point_origin_sha256', 'point_origin_locator', 'coordinate_source_file',
            'coordinate_source_sha256', 'coordinate_source_locator',
            'application_inference_kind', 'coordinate_provenance', 'source_file', 'source_row',
        ]).slice(414890).to_pylist()
        direct = [r for r in add if r['application_inference_kind'] == 'direct_reviewed_current_point_seed']
        with SEEDS.open(encoding='utf-8-sig', newline='') as f:
            seeds = {r['target_source_record_id']: r for r in csv.DictReader(f)}
        self.assertEqual(len(direct), 177)
        for row in direct:
            seed = seeds[row['target_source_record_id']]
            self.assertEqual(int(row['target_year']), 2021)
            self.assertIsNone(row['coordinate_provider_id'])
            self.assertTrue(row['point_origin_file'].endswith('data_allsettlements_anon_156_v20251217.parquet'))
            self.assertIn('parquet_row_1based=', row['point_origin_locator'])
            self.assertEqual(row['point_origin_sha256'], '86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14')
            self.assertEqual(float(row['latitude']), float(seed['source_raw_latitude']))
            self.assertEqual(float(row['longitude']), float(seed['source_raw_longitude']))
            self.assertEqual(row['coordinate_source_file'], row['point_origin_file'])
            self.assertEqual(row['coordinate_source_sha256'], row['point_origin_sha256'])
            self.assertIn('GeoNames RU feature', row['coordinate_provenance'])
            self.assertIn('corroborating physical-name evidence only', row['coordinate_provenance'])
            self.assertEqual(row['source_file'], 'data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
            self.assertIsNotNone(row['source_row'])
            self.assertIn(f"parquet_row_1based={int(float(row['source_row']))}", row['point_origin_locator'])

    def test_superseded_geonames_choice_is_explicitly_unconsumed(self):
        attempted = pq.read_table(OLD_EXPERIMENT / 'accepted_point_uses.parquet', columns=[
            'target_source_record_id', 'coordinate_source_file', 'coordinate_source_sha256',
        ]).slice(414890).to_pylist()
        self.assertEqual(len(attempted), 358)
        self.assertTrue(all(r['coordinate_source_file'].endswith('geonames_RU_20260907.zip') for r in attempted[:177]))
        prior = self.receipt['supersedes_unconsumed_experimental_attempt']
        self.assertEqual(prior['sha256'], 'c4ee8570796682e5be83781f2f9b1e03d3b66afd8010b0bd9712a84ca81012bc')
        self.assertIn('wrong-coordinate-choice experiment', prior['disposition'])

    def test_retrospective_rows_are_graph_continuations_with_limits(self):
        add = pq.read_table(OUT / 'accepted_point_uses.parquet', columns=[
            'target_year', 'coordinate_provider_id', 'coordinate_admission_status',
            'application_inference_kind', 'historical_measurement_claimed',
            'boundary_comparability_asserted', 'inference_identity_path_edge_count',
        ]).slice(414890).to_pylist()
        history = [r for r in add if r['application_inference_kind'] == 'modern_representative_point_retrospective_continuity_inference']
        self.assertEqual(len(history), 181)
        self.assertEqual(sum(int(r['target_year']) == 2010 for r in history), 177)
        self.assertEqual(sum(int(r['target_year']) == 2002 for r in history), 4)
        for row in history:
            self.assertIsNone(row['coordinate_provider_id'])
            self.assertEqual(row['coordinate_admission_status'], 'reviewed_extension_rule_accepted')
            self.assertFalse(row['historical_measurement_claimed'])
            self.assertFalse(row['boundary_comparability_asserted'])
            self.assertGreaterEqual(int(row['inference_identity_path_edge_count']), 1)

    def test_year_weighted_population_counts_match_receipt(self):
        self.assertEqual(self.receipt['added_population_by_year'], {
            '2002': {'rows': 4, 'population': 37782.0},
            '2010': {'rows': 177, 'population': 98588.0},
            '2021': {'rows': 177, 'population': 89733.0},
        })
        self.assertFalse(self.receipt['identity_graph_mutated'])
        self.assertFalse(self.receipt['selected_observations_mutated'])
        self.assertFalse(self.receipt['global_blocklist_mutated'])


if __name__ == '__main__':
    unittest.main()
