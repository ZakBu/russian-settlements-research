import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from scripts.sgrt_zero.coordinate_quality import (
    DEFAULT_HOLDS, REPO, apply_coordinate_holds, load_coordinate_holds,
)


class CoordinateQualityTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(DEFAULT_HOLDS.read_text())
        record = self.document['records'][0]
        self.reference = pd.DataFrame([
            {'source_record_id': record['source_record_id'],
             **record['reference_fields'], 'budget_population_credit': False},
            {'source_record_id': 'another-record', **record['reference_fields'],
             'budget_population_credit': True},
        ], index=[7, 2])

    def load(self, document, reference=None, root=REPO):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'holds.json'
            path.write_text(json.dumps(document))
            return load_coordinate_holds(path, self.reference if reference is None else reference,
                                         repo_root=root)

    def test_preserves_all_rows_and_original_fields_even_uncredited(self):
        before = self.reference.copy(deep=True)
        holds = self.load(self.document)
        result = apply_coordinate_holds(self.reference, holds)
        pd.testing.assert_frame_equal(before, self.reference)
        pd.testing.assert_frame_equal(before, result[before.columns])
        self.assertEqual(result.coordinate_location_held.tolist(), [True, False])

    def test_every_reference_fingerprint_field_is_required_and_exact(self):
        for field in ['name', 'settlement_type_2021', 'region', 'district', 'lat', 'lon']:
            with self.subTest(field=field):
                changed = self.reference.copy()
                changed.loc[7, field] = 1.0 if field in ('lat', 'lon') else 'wrong'
                with self.assertRaises(ValueError):
                    self.load(self.document, changed)
                incomplete = copy.deepcopy(self.document)
                del incomplete['records'][0]['reference_fields'][field]
                with self.assertRaises(ValueError):
                    self.load(incomplete)

    def test_missing_duplicate_and_replaced_id_fail(self):
        for frame in [self.reference.iloc[1:], pd.concat([self.reference, self.reference.iloc[:1]])]:
            with self.assertRaises(ValueError):
                self.load(self.document, frame)
        duplicate = copy.deepcopy(self.document)
        duplicate['records'].append(copy.deepcopy(duplicate['records'][0]))
        with self.assertRaises(ValueError):
            self.load(duplicate)

    def test_bad_hash_http_status_missing_raw_and_wrong_object_fail(self):
        for key, value in [('sha256', '0' * 64), ('http_status', 503),
                           ('raw_path', 'references/primary/absent.json')]:
            changed = copy.deepcopy(self.document)
            changed['records'][0]['evidence'][0][key] = value
            with self.assertRaises(ValueError):
                self.load(changed)
        changed = copy.deepcopy(self.document)
        changed['records'][0]['evidence'][0]['object_fields']['osm_id'] = 999
        with self.assertRaises(ValueError):
            self.load(changed)

    def test_actual_frozen_body_mutation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for evidence in self.document['records'][0]['evidence']:
                for key in ('raw_path', 'metadata_path'):
                    target = root / evidence[key]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((REPO / evidence[key]).read_bytes())
            raw = root / self.document['records'][0]['evidence'][0]['raw_path']
            raw.write_bytes(raw.read_bytes() + b' ')
            with self.assertRaises(ValueError):
                self.load(self.document, root=root)


if __name__ == '__main__':
    unittest.main()
