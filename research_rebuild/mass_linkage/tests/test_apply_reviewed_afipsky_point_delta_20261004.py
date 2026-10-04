import csv
import json
from pathlib import Path
import unittest

from research_rebuild.mass_linkage.apply_reviewed_afipsky_point_delta_20261004 import (
    CARRIER_2021,
    NEW_LAT,
    NEW_LON,
    OLD_DBf_LAT,
    OLD_DBf_LON,
    TARGET_2002,
    TARGET_2010,
    TOCHNO_SHA,
    DBF_SHA,
    reviewed_replacement,
    validate_review_packet,
)


ROOT = Path('/workspace/settlements-work/continuation_20261004/independent_review/afipsky_point_supersession_review')


class AfipskyPointDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt_path = ROOT / 'independent_point_review_receipt.json'
        cls.csv_path = ROOT / 'reviewed_point_supersession_candidates.csv'
        cls.receipt = json.loads(cls.receipt_path.read_text(encoding='utf-8'))
        with cls.csv_path.open(encoding='utf-8', newline='') as f:
            cls.rows = list(csv.DictReader(f))

    def test_exact_review_packet_and_targets(self):
        old, current = validate_review_packet(
            self.rows, self.receipt,
            eligible_sha='68b20016f842c79ac69a31f42e8a149221d30647d68a8f4b7e6bcbdf55a4a3ae',
            receipt_sha='5dce72a6ae6c9f4cf887ab4528118c5089bc94b61b8ff138a4fd347b047eec83',
        )
        self.assertEqual(old['target_source_record_id'], TARGET_2002)
        self.assertEqual(current['target_source_record_id'], TARGET_2010)

    def test_wrong_year_or_target_rejected(self):
        rows = [dict(r) for r in self.rows]
        rows[0]['target_year'] = '2021'
        with self.assertRaises(ValueError):
            validate_review_packet(rows, self.receipt, eligible_sha=self.receipt['outputs']['reviewed_point_supersession_candidates.csv']['sha256'], receipt_sha='5dce72a6ae6c9f4cf887ab4528118c5089bc94b61b8ff138a4fd347b047eec83')
        rows = [dict(r) for r in self.rows]
        rows[0]['target_source_record_id'] = '2002:wrong'
        with self.assertRaises(ValueError):
            validate_review_packet(rows, self.receipt, eligible_sha=self.receipt['outputs']['reviewed_point_supersession_candidates.csv']['sha256'], receipt_sha='5dce72a6ae6c9f4cf887ab4528118c5089bc94b61b8ff138a4fd347b047eec83')

    def test_wrong_coordinate_or_origin_rejected(self):
        for key, value in [('reviewed_latitude', '44.90'), ('point_origin_sha256', DBF_SHA), ('point_origin_locator', 'unrelated')]:
            rows = [dict(r) for r in self.rows]
            rows[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_review_packet(rows, self.receipt, eligible_sha=self.receipt['outputs']['reviewed_point_supersession_candidates.csv']['sha256'], receipt_sha='5dce72a6ae6c9f4cf887ab4528118c5089bc94b61b8ff138a4fd347b047eec83')

    def test_supersession_preserves_population_and_old_origin_as_metadata(self):
        old = {
            'target_source_record_id': TARGET_2002, 'coordinate_admission_status': 'reviewed_extension_rule_accepted',
            'latitude': OLD_DBf_LAT, 'longitude': OLD_DBf_LON, 'point_origin_sha256': DBF_SHA,
            'point_origin_locator': 'DBF_record_1based=2700;DBF_byte_offset_0based=1066810;OKATO2011_raw=03243552000',
            'target_population': 17977.0, 'target_source_record_json': '{"population":17977}',
            'source_okato_raw': None, 'source_oktmo_raw': None, 'coordinate_provenance': '{"old":"raw"}',
            'coordinate_uncertainty_flags_json': None, 'native_id_binding_asserted': 'False',
            'provider_identifier_binding_asserted': 'False', 'point_supersession_old_origin_locator': None,
        }
        carrier = {
            'target_source_record_id': CARRIER_2021, 'coordinate_admission_status': 'reviewed_rule_accepted',
            'latitude': NEW_LAT, 'longitude': NEW_LON, 'point_origin_sha256': TOCHNO_SHA,
            'point_origin_file': '/raw/current.parquet', 'point_origin_locator': 'row=46138',
            'point_origin_kind': 'tochno_2021_dadata_raw_parquet_point', 'coordinate_source': 'tochno_dadata',
            'coordinate_source_record_id': CARRIER_2021, 'coordinate_provider': 'tochno_dadata',
            'coordinate_provider_id': 'provider-id-must-not-propagate', 'coordinate_source_file': '/raw/current.parquet',
        }
        changes = reviewed_replacement(old, carrier, review_sha='review-sha', points_sha='points-sha', path_ids=['edge-1'], eligible_sha='csv-sha')
        self.assertEqual(changes['latitude'], NEW_LAT)
        self.assertEqual(changes['longitude'], NEW_LON)
        self.assertIsNone(changes['coordinate_provider_id'])
        self.assertEqual(changes['point_supersession_old_origin_sha256'], DBF_SHA)
        self.assertEqual(changes['point_supersession_old_latitude'], OLD_DBf_LAT)
        self.assertEqual(changes['point_supersession_old_longitude'], OLD_DBf_LON)
        self.assertEqual(old['target_population'], 17977.0)
        self.assertEqual(old['target_source_record_json'], '{"population":17977}')
        self.assertEqual(old['source_okato_raw'], None)
        self.assertEqual(old['source_oktmo_raw'], None)
        self.assertFalse(changes['boundary_comparability_asserted'])
        self.assertFalse(changes['direct_historical_coordinate_measurement'])

    def test_missing_accepted_path_rejected(self):
        old = {'target_source_record_id': TARGET_2002}
        carrier = {'target_source_record_id': CARRIER_2021}
        with self.assertRaises(ValueError):
            reviewed_replacement(old, carrier, review_sha='r', points_sha='p', path_ids=[], eligible_sha='c')


if __name__ == '__main__':
    unittest.main()
