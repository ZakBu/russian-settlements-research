"""Scientific controls detect changed ownership/admission, not serialization order."""
import importlib.util
import contextlib
import io
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from shapely.geometry import box
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts/sgrt_zero'))
from scripts.sgrt_zero.identity_control import source_control, table_hash, compare, evidence_fields
from scripts.sgrt_zero.cloud_identity_rebuild import retained_source_draft, read_source_release, refresh_place_guards, retain_official_coordinate_evidence, verify_standalone_registry, SOURCE_ZIP, SOURCE_ASSET_IDS, TAG
from scripts.sgrt_zero import pack_identity_results as packer
from scripts.sgrt_zero import cloud_identity_rebuild as worker


class IdentityScientificControlTests(unittest.TestCase):
    def test_every_owner_and_admission_flag_affects_the_control(self):
        base = pd.DataFrame([dict(provider_id='p', service_code='school_general', source_record_id='a',
                                 supply_status='observed', route_eligible=True,
                                 default_external_seed_eligible=True, site_lat=55., site_lon=37.)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.parquet'
            base.to_parquet(path, index=False)
            original = source_control(path, sites=True)
            for field, value in [('source_record_id', 'b'), ('route_eligible', False),
                                 ('default_external_seed_eligible', False), ('site_lat', 56.),
                                 ('source_year', 2013), ('source_snapshot', 'dated-only'),
                                 ('historical_source_only', True),
                                 ('cartographic_raw_geometry_sha256', 'different'),
                                 ('cartographic_nested_mask_census_ids_json', '["child"]')]:
                changed = base.copy(); changed.loc[0, field] = value
                changed.to_parquet(path, index=False)
                self.assertNotEqual(original['sha256'], source_control(path, sites=True)['sha256'], field)

    def test_row_order_is_irrelevant_but_duplicate_evidence_rows_are_retained(self):
        frame = pd.DataFrame({'id': ['b', 'a'], 'value': [2., 1.]})
        control = table_hash(frame, ['id', 'value'])
        self.assertEqual(control, table_hash(frame.iloc[::-1], ['id', 'value']))
        self.assertNotEqual(control['sha256'], table_hash(pd.concat([frame, frame.iloc[:1]]), ['id', 'value'])['sha256'])

    def test_comparison_never_replaces_expected_counts(self):
        with self.assertRaisesRegex(ValueError, 'registry_counts'):
            compare({'registry_counts': {'n': 100}}, {'registry_counts': {'n': 101}})

    def draft(self, *, published=False, extra=False):
        assets = [{'name': 'source-places.zip', 'size': SOURCE_ZIP['bytes'], 'id': SOURCE_ASSET_IDS['source-places.zip']},
                  {'name': 'source-acquisition.json', 'size': 100, 'id': SOURCE_ASSET_IDS['source-acquisition.json']}]
        if extra: assets.append({'name': 'unchecked-result.zip', 'size': 12})
        return json.dumps({'tag_name': TAG, 'draft': not published, 'assets': assets})

    def test_only_the_existing_two_source_assets_can_precede_publication(self):
        with patch('subprocess.check_output', return_value=self.draft()):
            self.assertTrue(retained_source_draft()['draft'])
        for payload in [self.draft(published=True), self.draft(extra=True)]:
            with patch('subprocess.check_output', return_value=payload):
                with self.assertRaisesRegex(ValueError, 'two retained source assets'):
                    retained_source_draft()

    def test_sealed_source_release_remains_readable_but_not_writable(self):
        release = json.loads(self.draft(published=True))
        release['assets'] += [{'name': name, 'size': 1, 'id': 10 + i} for i, name in enumerate([
            'identity-centres.zip', 'manifest.json', 'identity_repair_atlas.pdf', 'preview.png', 'level0_centres.csv'])]
        with patch('subprocess.check_output', return_value=json.dumps(release)):
            self.assertFalse(read_source_release(expected_asset_ids=SOURCE_ASSET_IDS)['draft'])
            with self.assertRaisesRegex(ValueError, 'existing draft'):
                retained_source_draft()

    def test_replaced_source_asset_is_rejected_even_after_publication(self):
        release = json.loads(self.draft(published=True))
        release['assets'][0]['id'] += 1
        with patch('subprocess.check_output', return_value=json.dumps(release)):
            with self.assertRaisesRegex(ValueError, 'source asset was replaced'):
                read_source_release(expected_asset_ids=SOURCE_ASSET_IDS)

    def test_bundle_really_contains_catalogs_fetcher_and_before_snapshot(self):
        commit = 'a' * 40
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); repo = folder / 'repo'; repo.mkdir()
            for name in packer.DEPENDENCY_CONTEXT:
                path = repo / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('dependency:' + name)
            sources = {}
            for name in ['analysis', 'routes', 'registry', 'boundaries']:
                sources[name] = folder / name; sources[name].mkdir()
            (sources['registry'] / 'summary.json').write_text('{"registered_level0_centres":0}')
            centre_csv = 'centre_settlement_id,centre_name\na,Example\n'
            (sources['registry'] / 'level0_centres.csv').write_text(centre_csv)
            with patch.object(packer, 'REPO', repo), patch('subprocess.check_output', side_effect=[commit + '\n', '']):
                with contextlib.redirect_stdout(io.StringIO()):
                    manifest = packer.package(sources['analysis'], sources['routes'], sources['registry'],
                                              sources['boundaries'], folder / 'built', commit)
            with zipfile.ZipFile(folder / 'built/identity-centres.zip') as archive:
                for name in packer.DEPENDENCY_CONTEXT:
                    logical = 'reproduction/' + name
                    self.assertIn(logical, manifest['files'])
                    self.assertEqual(archive.read(packer.PREFIX + logical).decode(), 'dependency:' + name)
                frozen_manifest = json.loads(archive.read(packer.PREFIX + 'manifest.json'))
                self.assertEqual(frozen_manifest['standalone_assets'], manifest['standalone_assets'])
                built_csv = folder / 'built/level0_centres.csv'
                built_csv.write_text(centre_csv)
                verify_standalone_registry(folder / 'built', manifest, archive)
                built_csv.write_text(centre_csv.replace('Example', 'Altered'))
                with self.assertRaisesRegex(ValueError, 'size/SHA'):
                    verify_standalone_registry(folder / 'built', manifest, archive)
                built_csv.unlink()
                with self.assertRaisesRegex(ValueError, 'size/SHA'):
                    verify_standalone_registry(folder / 'built', manifest, archive)

    def test_map_registry_cannot_substitute_a_different_archive_member(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            csv = directory / 'level0_centres.csv'; csv.write_bytes(b'id\na\n')
            spec = {'asset': csv.name, 'archive_member': 'frozen/registry/level0_centres.csv',
                    'bytes': csv.stat().st_size, 'sha256': hashlib.sha256(csv.read_bytes()).hexdigest()}
            manifest = {'archive_root': 'frozen/', 'standalone_assets': {csv.name: spec}}
            with zipfile.ZipFile(directory / 'bundle.zip', 'w') as archive:
                archive.writestr(spec['archive_member'], b'id\nb\n')
            with zipfile.ZipFile(directory / 'bundle.zip') as archive:
                with self.assertRaisesRegex(ValueError, 'differs from the archived registry'):
                    verify_standalone_registry(directory, manifest, archive)
                manifest['standalone_assets'] = {}
                with self.assertRaisesRegex(ValueError, 'Exactly'):
                    verify_standalone_registry(directory, manifest, archive)

    def test_publication_requires_and_uploads_exactly_five_complete_results(self):
        with tempfile.TemporaryDirectory() as directory:
            built = Path(directory); commit = 'f' * 40
            control = built / 'control.json'; control.write_text('{"proof":true}')
            csv = built / 'level0_centres.csv'; csv.write_bytes(b'id,lat,lon\na,50,40\n')
            for name in ['identity_repair_atlas.pdf', 'preview.png', 'release_notes.md']:
                (built / name).write_text('frozen')
            verification = {key: True for key in ['all_source_offer_rows_and_eligibility_equal',
                'all12_routing_layers_equal', 'all_admitted_choices_equal',
                'all_level0_centre_and_member_identities_equal', 'independent_registry_recheck_completed']}
            verification['source_commit'] = commit
            archive = built / 'identity-centres.zip'
            with zipfile.ZipFile(archive, 'w') as result:
                result.writestr('frozen/analysis/cloud_identity_control.json', control.read_bytes())
                result.writestr('frozen/analysis/scientific_verification.json', json.dumps(verification))
                result.writestr('frozen/registry/level0_centres.csv', csv.read_bytes())
            manifest = {'source_commit': commit, 'archive_root': 'frozen/',
                'archive': {'asset': archive.name, 'bytes': archive.stat().st_size, 'sha256': packer.sha(archive)},
                'standalone_assets': {csv.name: {'asset': csv.name, 'bytes': csv.stat().st_size,
                    'sha256': packer.sha(csv), 'archive_member': 'frozen/registry/level0_centres.csv'}}}
            (built / 'manifest.json').write_text(json.dumps(manifest))
            initial = json.loads(self.draft())
            names = ['identity-centres.zip', 'manifest.json', 'identity_repair_atlas.pdf', 'preview.png', csv.name]
            uploaded = {**initial, 'assets': initial['assets'] + [
                {'name': name, 'id': 100 + i, 'size': (built / name).stat().st_size}
                for i, name in enumerate(names)]}
            with patch.object(worker, 'CONTROL_DEFAULT', control), \
                 patch.object(worker, 'retained_source_draft', return_value=initial), \
                 patch('subprocess.check_output', return_value=json.dumps(uploaded)), \
                 patch('subprocess.run') as command, contextlib.redirect_stdout(io.StringIO()):
                worker.publish(built, commit)
                upload = command.call_args_list[0].args[0]
                self.assertEqual({Path(value).name for value in upload[4:-2]}, set(names))
                self.assertEqual(len(command.call_args_list), 2)
                (built / 'preview.png').unlink()
                command.reset_mock()
                with self.assertRaisesRegex(ValueError, 'Five complete result assets'):
                    worker.publish(built, commit)
                command.assert_not_called()

    def test_route_registry_and_polygon_evidence_flags_change_semantics(self):
        base = pd.DataFrame({'origin_id': ['a']})
        for field, value in [('provider_historical_source_only', True),
                             ('selected_provider_source_year', 2013),
                             ('origin_coordinate_location_held', True),
                             ('nested_mask_census_ids_json', '["child"]'),
                             ('raw_geometry_sha256', 'rawsha'),
                             ('original_other_positive_census_place_ids_json', '["hold"]'),
                             ('own_offer_includes_documented_dated_school_presence', True)]:
            changed = base.copy(); changed[field] = value
            self.assertNotEqual(table_hash(base, evidence_fields(base, ['origin_id'])),
                                table_hash(changed, evidence_fields(changed, ['origin_id'])), field)

    def test_machine_specific_source_path_does_not_change_scientific_identity(self):
        first=pd.DataFrame({'origin_id':['a'],'provider_source_year':['2026'],
                            'provider_source_input':['/workspace/local/sources/education.parquet']})
        cloud=first.copy();cloud['provider_source_input']='/runner/tmp/sources/education.parquet'
        self.assertEqual(table_hash(first,evidence_fields(first,['origin_id'])),
                         table_hash(cloud,evidence_fields(cloud,['origin_id'])))
        cloud['provider_source_year']='2021'
        self.assertNotEqual(table_hash(first,evidence_fields(first,['origin_id'])),
                            table_hash(cloud,evidence_fields(cloud,['origin_id'])))

    def test_official_pdf_is_pinned_and_corruption_is_never_retained(self):
        content = b'%PDF frozen scientific evidence'
        digest = hashlib.sha256(content).hexdigest()
        source = {'url': 'http://example.test/law.pdf', 'status': 200,
                  'bytes': len(content), 'sha256': digest}
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory); manifest = directory / 'holds.json'
            manifest.write_text(json.dumps({'records': [{'source_record_id': 'a', 'official_pdf_source': source}]}))
            response = unittest.mock.MagicMock()
            response.__enter__.return_value = response; response.status = 200
            response.read.return_value = content + b'changed'
            with patch('urllib.request.urlopen', return_value=response):
                with self.assertRaisesRegex(ValueError, 'size changed'):
                    retain_official_coordinate_evidence(manifest, directory / 'bad')
            self.assertFalse((directory / 'bad' / (digest + '.pdf')).exists())
            response.read.return_value = content
            with patch('urllib.request.urlopen', return_value=response):
                proof = retain_official_coordinate_evidence(manifest, directory / 'good')
            self.assertEqual(proof[0]['sha256'], digest)
            target = directory / 'good' / (digest + '.pdf')
            target.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'modified'):
                retain_official_coordinate_evidence(manifest, directory / 'good')

    def test_guard_refresh_counts_uncredited_nonanalysis_neighbour_in_held_geometry(self):
        reference = pd.DataFrame({'source_record_id': ['a', 'b'], 'name': ['А', 'Б'],
            'lat': [.5, 1.5], 'lon': [.5, 1.5], 'population_2021': [1000., 10.],
            'population_role': ['ordinary_settlement_record'] * 2,
            'budget_population_credit': [True, False], 'analysis_origin': [True, False]})
        inventory = pd.DataFrame({'source_record_id': ['a', None],
            'geometry_wkb': [box(0, 0, 2, 2).wkb] * 2,
            'polygon_identity_status': ['named', 'held'],
            'other_positive_census_places': [0, 0],
            'other_positive_census_place_ids_json': ['[]', '[]']})
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder); source = folder / 'source.parquet'; ref = folder / 'reference.parquet'
            output = folder / 'refreshed.parquet'
            inventory.to_parquet(source, index=False); reference.to_parquet(ref, index=False)
            before = source.read_bytes()
            with contextlib.redirect_stdout(io.StringIO()): refresh_place_guards(source, ref, output)
            result = pd.read_parquet(output)
            self.assertEqual(result.other_positive_census_places.tolist(), [1, 2])
            self.assertEqual(result.source_record_id.tolist(), ['a', None])
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(result.physical_neighbour_guard_uses_budget_credit.any())
            self.assertFalse(result.physical_neighbour_guard_uses_analysis_origin.any())
            with self.assertRaises(FileExistsError): refresh_place_guards(source, ref, output)


if __name__ == '__main__':
    unittest.main()
