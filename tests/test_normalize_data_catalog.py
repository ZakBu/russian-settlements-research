import copy
import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('normalize', Path(__file__).resolve().parents[1] / 'scripts/maintenance/normalize_data_catalog.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class NormalizeTests(unittest.TestCase):
    def test_real_source_special_cases_preserve_originals_and_are_idempotent(self):
        import json
        root = Path(__file__).resolve().parents[1]
        cat = json.loads((root/'data/catalog.json').read_text())
        special = json.loads((root/'data/source_special_files.json').read_text())
        originals = {s['original_blob']: copy.deepcopy(cat['objects'][s['original_blob']]) for s in special['files']}
        module.normalize(cat, special)
        rows = {r['path']: r for r in cat['files']}
        for s in special['files']:
            o = cat['objects'][s['original_blob']]
            for field in ('blob', 'bytes', 'sha256', 'asset'):
                self.assertEqual(o[field], originals[s['original_blob']][field])
            r = rows[s['path']]
            if s['kind'] == 'resolved_symlink_data':
                self.assertEqual(r['blob'], rows[s['resolved_target_path']]['blob'])
                self.assertTrue(r['usable_as_table'])
            else:
                self.assertEqual(r['blob'], s['original_blob'])
                self.assertFalse(r['usable_as_table'])
        self.assertEqual(len(cat['readability']['unavailable_historical_link_targets']), 2)
        self.assertEqual(cat['counts']['parquet_schema_errors'], 0)
        once = copy.deepcopy(cat)
        module.normalize(cat, special)
        self.assertEqual(cat, once)

if __name__ == '__main__':
    unittest.main()
