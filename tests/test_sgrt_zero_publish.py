"""Release integrity tests; no live uploads or downloads."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero import publish as p


class PublicationTests(unittest.TestCase):
    def test_changed_federal_archive_is_not_accepted_or_written(self):
        from io import BytesIO
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(p.urllib.request,'urlopen',return_value=BytesIO(b'PK-changed')):
                with self.assertRaisesRegex(ValueError,'changed'):
                    p.freeze_federal(root,'a'*40)
            self.assertFalse((root/p.FEDERAL_NAME).exists())

    def test_federal_history_requires_intervals_and_no_legal_address_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);body=b'PK-test'
            with patch.object(p,'FEDERAL_SHA256',hashlib.sha256(body).hexdigest()), patch.object(p,'FEDERAL_BYTES',len(body)):
                (root/p.FEDERAL_NAME).write_bytes(body)
                manifest=p.freeze_federal(root,'a'*40)
            self.assertTrue(manifest['contains_history_not_just_current_records'])
            self.assertTrue(manifest['validity_requires_per_record_intervals'])
            self.assertTrue(manifest['legal_address_is_not_a_care_site'])

    def bundle(self, directory):
        root = Path(directory)
        for name in ('zero-data.zip', 'zero_atlas.pdf', 'preview.png'):
            (root / name).write_bytes(name.encode())
        cat = {'repository': p.REPOSITORY, 'release_tag': p.RESULT_TAG,
               'source_commit': 'a' * 40, 'assets': [{'asset': 'zero-data.zip',
                'bytes': (root / 'zero-data.zip').stat().st_size,
                'sha256': p.sha(root / 'zero-data.zip')}]}
        (root / 'zero_catalog.json').write_text(json.dumps(cat))
        return root

    def test_archive_mismatch_stops_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.bundle(tmp)
            (root / 'zero-data.zip').write_bytes(b'changed')
            with patch.object(p, 'gh') as gh, self.assertRaises(ValueError):
                p.publish(root)
            gh.assert_not_called()

    def test_published_version_on_later_page_is_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.bundle(tmp)
            with patch.object(p, 'gh', return_value=json.dumps([[], [{'tag_name': p.RESULT_TAG, 'draft': False}]])) as gh:
                with self.assertRaisesRegex(ValueError, 'immutable'):
                    p.publish(root)
            self.assertEqual(gh.call_count, 1)

    def test_remote_wrong_digest_blocks_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'one'
            path.write_bytes(b'a')
            with self.assertRaisesRegex(ValueError, 'SHA'):
                p.verify_remote({'assets': [{'name': 'one', 'size': 1, 'digest': 'sha256:bad'}]},
                    [path], {'one': {'bytes': 1, 'sha256': p.sha(path)}}, p.RESULT_TAG)

    def test_remote_without_digest_requires_downloaded_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'one'
            path.write_bytes(b'a')
            def download(*args):
                out = Path(args[args.index('--dir') + 1])
                (out / 'one').write_bytes(b'b')
            with patch.object(p, 'gh', side_effect=download), self.assertRaises(ValueError):
                p.verify_remote({'assets': [{'name': 'one', 'size': 1}]}, [path],
                    {'one': {'bytes': 1, 'sha256': p.sha(path)}}, p.RESULT_TAG)

    def test_verified_draft_publishes_with_make_latest_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.bundle(tmp)
            requests = []
            def gh(*args):
                if '--slurp' in args:
                    return '[[]]'
                if '--input' in args:
                    body = json.loads(Path(args[args.index('--input') + 1]).read_text())
                    requests.append(body)
                    return json.dumps({'id': 9, 'draft': True})
                if args[:2] == ('release', 'upload'):
                    return ''
                return json.dumps({'id': 9, 'draft': True, 'assets': [
                    {'name': f.name, 'size': f.stat().st_size, 'digest': 'sha256:' + p.sha(f)}
                    for f in (root / n for n in ('zero-data.zip', 'zero_catalog.json', 'zero_atlas.pdf', 'preview.png'))]})
            with patch.object(p, 'gh', side_effect=gh):
                result = p.publish(root)
            self.assertEqual(requests[-1]['draft'], False)
            self.assertEqual(requests[-1]['make_latest'], 'false')
            self.assertEqual(len(result['assets']), 4)

    def test_existing_wrong_medical_snapshot_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / p.MEDICAL_NAME
            path.write_bytes(b'wrong')
            with patch.object(p.urllib.request, 'urlopen') as request, self.assertRaises(ValueError):
                p.freeze_medical(root, 'a' * 40)
            request.assert_not_called()
            self.assertEqual(path.read_bytes(), b'wrong')

    def test_medical_manifest_uses_reference_year_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = b'%PDF-test'
            with patch.object(p, 'MEDICAL_SHA256', hashlib.sha256(body).hexdigest()), patch.object(p, 'MEDICAL_BYTES', len(body)):
                (root / p.MEDICAL_NAME).write_bytes(body)
                manifest = p.freeze_medical(root, 'a' * 40)
            self.assertEqual(manifest['snapshot_label'], '2021-12-31')
            self.assertEqual(manifest['release_tag'], p.MEDICAL_TAG)
            self.assertTrue(manifest['acquisition_is_not_reference_year'])


if __name__ == '__main__':
    unittest.main()
