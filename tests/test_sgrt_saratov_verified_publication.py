"""Automatic publication must follow exact bytes, never precede their check."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote
import zipfile

from scripts.sgrt_saratov import publish_verified_regional as publisher
from scripts.sgrt_saratov import verify_public_release as verifier

PRODUCER = 'a'*40


def fixture(root):
    payload = {'saratov-fields.zip': b'not-a-valid-zip',
        **{f'layer-{i}.geojson': b'{}' for i in range(17)}}
    def spec(name):
        data = payload[name]
        return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    manifest = {'release_tag': publisher.TAG, 'source_commit': PRODUCER,
        'archive': {'asset': 'saratov-fields.zip', **spec('saratov-fields.zip')},
        'standalone_assets': {name: spec(name) for name in payload if name != 'saratov-fields.zip'},
        'files': []}
    payload['manifest.json'] = (json.dumps(manifest)+'\n').encode()
    release = {'id': 7, 'tag_name': publisher.TAG, 'target_commitish': PRODUCER, 'draft': True,
        'assets': [{'id': i+1, 'name': name, 'size': len(data),
                    'digest': 'sha256:'+hashlib.sha256(data).hexdigest()}
                   for i, (name, data) in enumerate(payload.items())]}
    path = root/'manifest.json'; path.write_bytes(payload['manifest.json'])
    return manifest, release, payload, path


class IndependentPublication(unittest.TestCase):
    def test_wrong_tag_source_id_and_duplicate_assets_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, release, _, _ = fixture(Path(directory))
            self.assertEqual(len(publisher.snapshot(release, 7, PRODUCER)), 19)
            for key, value in [('id', 8), ('tag_name', 'sgrt-saratov-fields-20261029-v1'),
                               ('target_commitish', 'b'*40)]:
                bad = copy.deepcopy(release); bad[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    publisher.snapshot(bad, 7, PRODUCER)
            bad = copy.deepcopy(release); bad['assets'][1]['name'] = bad['assets'][0]['name']
            with self.assertRaisesRegex(ValueError, 'nineteen distinct'):
                publisher.snapshot(bad, 7, PRODUCER)

    def test_manifest_digest_or_extra_asset_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            _, release, _, path = fixture(Path(directory))
            publisher.check_manifest(release, path, PRODUCER)
            bad = copy.deepcopy(release); bad['assets'][0]['digest'] = 'sha256:'+'f'*64
            with self.assertRaisesRegex(ValueError, 'size/digest'):
                publisher.check_manifest(bad, path, PRODUCER)
            bad = copy.deepcopy(release); bad['assets'].append({'name': 'extra.bin'})
            with self.assertRaisesRegex(ValueError, 'inventories differ'):
                publisher.check_manifest(bad, path, PRODUCER)

    def test_actual_corrupt_archive_blocks_publication_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, release, payload, _ = fixture(root)
            downloads = root/'downloads'; registration = root/'registration'; calls = []
            def gh(*arguments):
                calls.append(arguments)
                if arguments[0] == 'release':
                    for name, raw in payload.items(): (downloads/name).write_bytes(raw)
                    return ''
                return json.dumps(release)
            with patch.dict('os.environ', {'GH_TOKEN': 'workflow-test-token'}), \
                    patch.object(publisher.subprocess, 'check_output', side_effect=[PRODUCER+'\n', '']), \
                    patch.object(publisher, '_gh', side_effect=gh), \
                    patch.object(publisher, 'verify_public') as public:
                with self.assertRaises(zipfile.BadZipFile):
                    publisher.publish(7, PRODUCER, downloads, registration)
                public.assert_not_called()
            self.assertFalse(any('PATCH' in args for args in calls))
            self.assertFalse(registration.exists())

    def test_public_download_failure_emits_no_registration_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, release, payload, _ = fixture(root)
            downloads = root/'downloads'; registration = root/'registration'; calls = []
            def gh(*arguments):
                calls.append(arguments)
                if arguments[0] == 'release':
                    for name, raw in payload.items(): (downloads/name).write_bytes(raw)
                    return ''
                if 'PATCH' in arguments: release['draft'] = False
                return json.dumps(release)
            with patch.dict('os.environ', {'GH_TOKEN': 'workflow-test-token'}), \
                    patch.object(publisher.subprocess, 'check_output', side_effect=[PRODUCER+'\n', '']), \
                    patch.object(publisher, '_gh', side_effect=gh), \
                    patch.object(publisher, 'register', return_value=({}, {'zip_members_verified': 1})), \
                    patch.object(publisher, 'verify_public', side_effect=ValueError('unsigned SHA mismatch')):
                with self.assertRaisesRegex(ValueError, 'unsigned SHA mismatch'):
                    publisher.publish(7, PRODUCER, downloads, registration)
            self.assertTrue(any('PATCH' in args for args in calls))
            self.assertFalse(registration.exists())

    def test_existing_public_release_retry_never_changes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); _, release, payload, _ = fixture(root)
            release['draft'] = False
            downloads = root/'downloads'; registration = root/'registration'; calls = []
            def gh(*arguments):
                calls.append(arguments)
                if arguments[0] == 'release':
                    for name, raw in payload.items(): (downloads/name).write_bytes(raw)
                    return ''
                return json.dumps(release)
            public = {'downloads': {str(i): {} for i in range(19)}, 'every_public_asset_downloaded_and_hashed': True}
            with patch.dict('os.environ', {'GH_TOKEN': 'workflow-test-token'}), \
                    patch.object(publisher.subprocess, 'check_output', side_effect=[PRODUCER+'\n', '']), \
                    patch.object(publisher, '_gh', side_effect=gh), \
                    patch.object(publisher, 'register', return_value=({}, {'zip_members_verified': 1})), \
                    patch.object(publisher, 'verify_public', return_value=public):
                result = publisher.publish(7, PRODUCER, downloads, registration)
            self.assertEqual(result['public_assets_verified'], 19)
            self.assertFalse(any('PATCH' in args for args in calls))
            self.assertTrue(all((registration/name).is_file() for name in publisher.REGISTRATION_FILES))

    def test_supplied_metadata_skips_api_but_all_nineteen_downloads_remain_unsigned(self):
        for supplied in (True, False):
            with self.subTest(supplied=supplied), tempfile.TemporaryDirectory() as directory:
                _, release, payload, path = fixture(Path(directory)); release['draft'] = False
                requested = []
                class Response(io.BytesIO):
                    status = 200
                    def __init__(self, raw, url): super().__init__(raw); self.url = url
                def fetch(request, **kwargs):
                    requested.append(request.full_url)
                    self.assertIsNone(request.get_header('Authorization'))
                    if request.full_url.startswith('https://api.github.com/'):
                        if supplied: self.fail('Supplied canonical metadata must not call the API again')
                        return Response(json.dumps(release).encode(), request.full_url)
                    return Response(payload[unquote(request.full_url.rsplit('/', 1)[1])], request.full_url)
                with patch.object(verifier, 'urlopen', side_effect=fetch):
                    proof = verifier.verify_public(path, release_metadata=release if supplied else None)
                self.assertEqual(len(proof['downloads']), 19)
                self.assertEqual(len(requested), 19 if supplied else 20)
                self.assertTrue(all(not d['authorization_header_sent'] for d in proof['downloads'].values()))

    def test_supplied_metadata_from_another_tag_is_rejected_before_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            _, release, _, path = fixture(Path(directory))
            release['draft'] = False; release['tag_name'] = 'another-version'
            with patch.object(verifier, 'urlopen') as download:
                with self.assertRaisesRegex(ValueError, 'Public release'):
                    verifier.verify_public(path, release_metadata=release)
                download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
