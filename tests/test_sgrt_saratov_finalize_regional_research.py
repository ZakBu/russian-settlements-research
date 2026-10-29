"""Preserved data reuse cannot weaken the numerical or source checks."""
from pathlib import Path
import copy
import hashlib
import json
import stat
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from scripts.sgrt_saratov import finalize_regional_research as finalizer


def original_control():
    return {'tables': {'current.parquet': {'rows': 7, 'sha256': 'exact'},
        **{name: {'rows': 8, 'sha256': 'old'} for name in finalizer.HISTORICAL['tables']}},
        'scientific_summaries': {'current/summary.json': {'known_mass': 144329319},
            **{name: {'origins': 8} for name in finalizer.HISTORICAL['scientific_summaries']}},
        'matrices': {'costs.npz': {'sha256': 'all-explicit-zeros-and-nans'}},
        'geojson': {'map.geojson': {'features': 511}}, 'numeric_decimal_places': 8}


def wrapper():
    return '''TAG = "fixed"
def inputs(): return ["pinned.csv"]
def build(): return "horizon480"
def array_control(x): return round(x,8)
def scientific_files(x): return x
def package(x): return x
'''


class PreservedComputation(unittest.TestCase):
    def test_only_the_exact_three_old_probe_names_can_be_removed(self):
        original = original_control()
        current = finalizer.trimmed_original_control(original)
        self.assertEqual(finalizer.verify_control_inventory(original, current, current), current)
        bad = copy.deepcopy(current); del bad['tables']['current.parquet']
        with self.assertRaisesRegex(ValueError, 'exactly the original'):
            finalizer.verify_control_inventory(original, bad, bad)
        changed = copy.deepcopy(current); changed['matrices']['costs.npz']['sha256'] = 'lost-nan-mask'
        with self.assertRaisesRegex(ValueError, 'Preserved actual'):
            finalizer.verify_control_inventory(original, current, changed)
        changed = copy.deepcopy(current); changed['numeric_decimal_places'] = 7
        with self.assertRaisesRegex(ValueError, 'exactly the original'):
            finalizer.verify_control_inventory(original, changed, changed)

    def test_build_inputs_and_numeric_precision_are_protected_by_ast(self):
        old = wrapper()
        current = old+'\nHISTORICAL_PROBE_FILES = '+repr(set().union(*finalizer.HISTORICAL.values()))+'\n'
        finalizer.verify_wrapper_change(old, current)
        for before, after in [('round(x,8)', 'round(x,7)'), ('horizon480', 'horizon600'),
                              ('pinned.csv', 'fresh-live-query.csv')]:
            with self.subTest(after=after), self.assertRaisesRegex(ValueError, 'Protected producer'):
                finalizer.verify_wrapper_change(old, current.replace(before, after))
        with self.assertRaisesRegex(ValueError, 'exactly the documented'):
            finalizer.verify_wrapper_change(old, old+'\nHISTORICAL_PROBE_FILES={"entire_current.parquet"}\n')

    def test_model_code_catalogues_and_renderer_cannot_change(self):
        for name in ['scripts/sgrt_saratov/functional_fields.py', 'data/catalog.json',
                     'requirements-saratov-fields.txt', 'references/primary/reader_extract.txt',
                     'web/src/components/custom-map-layers.ts', 'sgrt/saratov/documented_school_sites_20261029.csv']:
            with self.subTest(name=name):
                self.assertFalse(finalizer.allowed_noncomputational_change(name))
        self.assertTrue(finalizer.allowed_noncomputational_change(finalizer.SELF_PATH))
        self.assertTrue(finalizer.allowed_noncomputational_change(finalizer.EXPECTED_PATH))
        self.assertTrue(finalizer.allowed_noncomputational_change('sgrt/saratov/REGIONAL_RESULTS_20261029.md'))

    def test_archive_traversal_symlinks_duplicate_names_and_extra_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cases = ['../escape', '/absolute', 'results/../../escape', 'results\\escape', 'secret.json']
            for number, name in enumerate(cases):
                p = root/f'bad{number}.zip'
                with zipfile.ZipFile(p, 'w') as z: z.writestr(name, 'x')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    finalizer.safe_extract(p, root/f'out{number}', allowed_roots={'results'})
            p = root/'link.zip'
            with zipfile.ZipFile(p, 'w') as z:
                info = zipfile.ZipInfo('results/link'); info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, '/outside')
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                finalizer.safe_extract(p, root/'link-out', allowed_roots={'results'})
            p = root/'duplicate.zip'
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(p, 'w') as z:
                    z.writestr('results/a', 'x'); z.writestr('results/a', 'y')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                finalizer.safe_extract(p, root/'duplicate-out')

    def test_only_the_exact_unpublished_notice_is_an_allowed_root_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'good.zip'
            with zipfile.ZipFile(source, 'w') as z:
                z.writestr('results/table.json', '{}')
                z.writestr('UNPUBLISHED.txt', finalizer.UNPUBLISHED_NOTICE)
            names = finalizer.safe_extract(source, root/'good', allowed_roots={'results'},
                allowed_root_files={'UNPUBLISHED.txt'}, expected_members=2)
            self.assertEqual(len(names), 2)
            self.assertEqual((root/'good/UNPUBLISHED.txt').read_text(), finalizer.UNPUBLISHED_NOTICE)
            with zipfile.ZipFile(root/'nested.zip', 'w') as z:
                z.writestr('UNPUBLISHED.txt/hidden.json', '{}')
            with self.assertRaisesRegex(ValueError, 'Unexpected archive root'):
                finalizer.safe_extract(root/'nested.zip', root/'bad', allowed_roots={'results'},
                    allowed_root_files={'UNPUBLISHED.txt'})

    def test_original_archive_is_declared_not_falsely_claimed_as_redownloaded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); results = root/'results'; docs = results/'source_documents'
            docs.mkdir(parents=True); (docs/'commerce').mkdir()
            def spec(path):
                raw = path.read_bytes()
                return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            (docs/'reader.txt').write_text('frozen source')
            (docs/'commerce/locator_raw.json').write_text('{"data":[]}')
            primary = root/'references/primary/saratov_magnit_20261028'; primary.mkdir(parents=True)
            for name in ('locator_query.json','locator_shops_route_Da75p-8i.js'):
                (primary/name).write_text('source'); (docs/'commerce'/name).write_text('source')
            frozen = root/'frozen.json'
            frozen.write_text(json.dumps({'assets': [{'path': 'deleted-input.zip', 'bytes': 99, 'sha256': 'old'}],
                'files': [{'path': 'reader.txt', **spec(docs/'reader.txt')}]}))
            provenance = root/'provenance.json'
            provenance.write_text(json.dumps({'raw_response': spec(docs/'commerce/locator_raw.json')}))
            with patch.object(finalizer, 'REPO', root), patch.object(finalizer.producer, 'FROZEN', frozen), \
                    patch.object(finalizer.producer, 'MAGNIT_PROVENANCE', provenance), \
                    patch.object(finalizer.producer, 'inputs', return_value={}), \
                    patch.object(finalizer.producer, 'curated_source_proofs', return_value=[]):
                declarations = finalizer.declared_original_inputs(results, {'receipt': True})
            self.assertFalse(declarations[0]['original_archive_downloaded_or_reverified_by_finalizer'])
            self.assertEqual(declarations[0]['original_archive_declarations'][0]['path'], 'deleted-input.zip')
            self.assertFalse((docs/'deleted-input.zip').exists())


if __name__ == '__main__':
    unittest.main()
