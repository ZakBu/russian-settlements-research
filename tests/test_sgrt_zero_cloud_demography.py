"""Guard the map export and new-release-only publication contract."""
import subprocess
import json
from pathlib import Path
import tempfile
import hashlib
import zipfile
import unittest
from unittest.mock import patch
import pandas as pd

from scripts.sgrt_zero import cloud_centre_demography as cloud


class CloudDemographyTests(unittest.TestCase):
    def fixtures(self):
        centres = pd.DataFrame({'star_id': ['a', 'b'], 'centre_settlement_id': ['np-a', 'np-b'],
            'centre_name': ['А', 'Б'], 'centre_region': ['область']*2,
            'lat': [50., 51.], 'lon': [40., 41.]})
        rows = []
        for mode in ['strict_direct_observed', 'accepted_values']:
            for star, npid in [('a', 'np-a'), ('b', 'np-b')]:
                rows.append({'star_id': star, 'centre_settlement_id': npid, 'evidence_mode': mode,
                    'joint_centre_rural_external_2002_2021': 'unknown' if mode.startswith('strict') and star == 'a' else 'growth__growth',
                    'joint_centre_rural_external_2010_2021': 'unknown' if mode.startswith('strict') else 'decline__growth'})
        return pd.DataFrame(rows), centres

    def test_map_has_one_row_per_centre_and_main_class_never_uses_accepted_values(self):
        classes, centres = self.fixtures()
        result = cloud.site_frame(classes, centres).set_index('star_id')
        self.assertEqual(len(result), 2)
        self.assertEqual(result.loc['a', 'demography_rural_2002_category'], 0)
        self.assertEqual(result.loc['b', 'demography_rural_2002_category'], 2)
        self.assertEqual(result.loc['a', 'accepted_joint_centre_rural_external_2010_2021'], 'decline__growth')
        self.assertFalse(result.word_causal_type_established.any())
        self.assertFalse(result.historical_boundary_equivalence_established.any())
        self.assertEqual(result.loc['a', 'lat'], 50.)

    def test_missing_duplicate_modes_or_unrecognised_classes_fail(self):
        classes, centres = self.fixtures()
        for changed in [classes.iloc[1:], pd.concat([classes, classes.iloc[:1]])]:
            with self.assertRaises(ValueError): cloud.site_frame(changed, centres)
        classes.loc[0, 'joint_centre_rural_external_2002_2021'] = 'causal_word_type'
        with self.assertRaisesRegex(ValueError, 'Unexpected'): cloud.site_frame(classes, centres)

    def test_only_explicit_404_for_both_release_and_git_tag_is_safe(self):
        missing = subprocess.CompletedProcess([], 1, '', 'gh: Not Found (HTTP 404)')
        exists = subprocess.CompletedProcess([], 0, '{}', '')
        denied = subprocess.CompletedProcess([], 1, '', 'gh: Forbidden (HTTP 403)')
        with patch.object(cloud.subprocess, 'run', side_effect=[missing, missing]), \
             patch.object(cloud.subprocess, 'check_output', return_value='[[]]'): cloud.absent_tag()
        for responses in [[exists], [missing, exists]]:
            with patch.object(cloud.subprocess, 'run', side_effect=responses):
                with self.assertRaisesRegex(ValueError, 'new tag'): cloud.absent_tag()
        with patch.object(cloud.subprocess, 'run', return_value=denied):
            with self.assertRaises(RuntimeError): cloud.absent_tag()
        with patch.object(cloud.subprocess, 'run', side_effect=[missing, missing]), \
             patch.object(cloud.subprocess, 'check_output', return_value=json.dumps([[{'tag_name': cloud.TAG, 'draft': True}]])):
            with self.assertRaisesRegex(ValueError, 'existing draft is retained'): cloud.absent_tag()

    def draft_fixture(self, folder):
        assets = []
        for name in ['centre-demography.zip', 'manifest.json', 'centre_demography.csv', 'preview.png', 'comparison.png']:
            path = Path(folder)/name; path.write_text('frozen '+name); assets.append(path)
        release = {'id': 42, 'tag_name': cloud.TAG, 'draft': True, 'target_commitish': 'a'*40,
                   'html_url': 'https://github.com/example/releases/tag/untagged-temporary',
                   'assets': [{'name': p.name, 'size': p.stat().st_size, 'digest': 'sha256:'+cloud.sha(p)}
                              for p in assets]}
        return assets, release

    def test_draft_invisible_by_tag_is_resolved_by_paginated_list_then_id(self):
        with tempfile.TemporaryDirectory() as folder:
            assets, release = self.draft_fixture(folder)
            def api(command, **kwargs):
                endpoint = command[-1]
                if '/releases/tags/' in endpoint:
                    raise subprocess.CalledProcessError(1, command, stderr='gh: Not Found (HTTP 404)')
                if endpoint.endswith('/releases?per_page=100'):
                    self.assertIn('--paginate', command)
                    self.assertIn('--slurp', command)
                    return json.dumps([[{'id': 9, 'tag_name': 'unrelated', 'draft': True}], [release]])
                if endpoint.endswith('/releases/42'): return json.dumps(release)
                self.fail('Unexpected GitHub endpoint: '+endpoint)
            with patch.object(cloud.subprocess, 'check_output', side_effect=api) as mocked, \
                 patch.object(cloud.subprocess, 'run') as mutate:
                with self.assertRaises(subprocess.CalledProcessError):
                    cloud.subprocess.check_output(['gh', 'api', f'repos/example/releases/tags/{cloud.TAG}'])
                mocked.reset_mock()
                release_id = cloud.publish_created_draft('a'*40, assets)
                self.assertEqual(release_id, 42)
                self.assertEqual(len(mocked.call_args_list), 2)
                self.assertTrue(mocked.call_args_list[-1].args[0][-1].endswith('/releases/42'))
                mutate.assert_called_once_with(['gh', 'api', '--method', 'PATCH',
                    f'repos/{cloud.REPOSITORY}/releases/42', '-F', 'draft=false',
                    '-f', 'make_latest=false', '--silent'], check=True)

    def test_wrong_draft_target_or_asset_sha_prevents_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            assets, release = self.draft_fixture(folder)
            listing = json.dumps([[release]])
            wrong_target = {**release, 'target_commitish': 'b'*40}
            wrong_digest = json.loads(json.dumps(release)); wrong_digest['assets'][0]['digest'] = 'sha256:'+'0'*64
            for response, message in [(wrong_target, 'target differs'), (wrong_digest, 'SHA digests')]:
                with patch.object(cloud.subprocess, 'check_output', side_effect=[listing, json.dumps(response)]), \
                     patch.object(cloud.subprocess, 'run') as mutate:
                    with self.assertRaisesRegex(ValueError, message): cloud.publish_created_draft('a'*40, assets)
                    mutate.assert_not_called()

    def test_missing_or_duplicate_exact_tag_drafts_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as folder:
            assets, release = self.draft_fixture(folder)
            for listing in [[], [release, {**release, 'id': 43}]]:
                with patch.object(cloud.subprocess, 'check_output', return_value=json.dumps([listing])) as api:
                    with self.assertRaisesRegex(ValueError, 'Exactly one'): cloud.created_draft('a'*40, assets)
                    self.assertEqual(api.call_count, 1)

    def test_read_only_rebuild_reaches_package_when_output_tag_is_already_published(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); frozen = root/'frozen'; frozen.mkdir(); work = root/'rebuild'
            payloads = {'level0_centres.parquet': b'frozen centre records',
                        'level0_memberships.parquet': b'frozen member records'}
            def spec(data): return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            registry = {name: spec(data) for name, data in payloads.items()}
            with zipfile.ZipFile(frozen/'identity-centres.zip', 'w') as archive:
                for name, data in payloads.items(): archive.writestr('frozen/registry/'+name, data)
            archive_spec = {'asset': 'identity-centres.zip', **spec((frozen/'identity-centres.zip').read_bytes())}
            public = {'source_commit': 'frozen-producer', 'archive': archive_spec, 'archive_root': 'frozen/',
                      'files': {'registry/'+name: item for name, item in registry.items()}}
            (frozen/'manifest.json').write_text(json.dumps(public))
            reference_data = b'frozen census reference'
            facts = {'identity_tag': 'existing-public-input-release', 'identity_producer_commit': 'frozen-producer',
                'manifest': spec((frozen/'manifest.json').read_bytes()), 'archive': archive_spec,
                'registry': registry, 'reference': {'catalog_path': 'context/reference.parquet', **spec(reference_data)}}
            facts_path = root/'facts.json'; facts_path.write_text(json.dumps(facts))
            expected = {'all_row_semantics': 'same'}
            control_path = root/'control.json'; control_path.write_text(json.dumps(expected))
            def download(command, **kwargs):
                self.assertEqual(command[:3], ['gh', 'release', 'download'])
                target = Path(command[command.index('--dir')+1])
                for name in ['manifest.json', 'identity-centres.zip']:
                    (target/name).write_bytes((frozen/name).read_bytes())
            def compute(*args):
                if args[0] == 'scripts/research_data.py':
                    reference = work/'source/context/reference.parquet'
                    reference.parent.mkdir(parents=True); reference.write_bytes(reference_data)
            with patch.object(cloud, 'FACTS', facts_path), patch.object(cloud, 'CONTROL', control_path), \
                 patch.object(cloud, 'clean_commit') as clean, \
                 patch.object(cloud, 'absent_tag', side_effect=ValueError('Output tag already published')) as write_guard, \
                 patch.object(cloud.subprocess, 'run', side_effect=download) as network, \
                 patch.object(cloud, 'command', side_effect=compute) as commands, \
                 patch.object(cloud, 'control', return_value=(expected, pd.DataFrame())), \
                 patch.object(cloud, 'package', return_value=work/'built') as package:
                self.assertEqual(cloud.build(work, 'current-code'), work/'built')
                clean.assert_called_once_with('current-code')
                write_guard.assert_not_called()
                network.assert_called_once()
                self.assertEqual(commands.call_count, 3)
                package.assert_called_once()
            for name, data in payloads.items(): self.assertEqual((work/'registry'/name).read_bytes(), data)
            self.assertEqual(json.loads((work/'actual_control.json').read_text()), expected)


if __name__ == '__main__': unittest.main()
