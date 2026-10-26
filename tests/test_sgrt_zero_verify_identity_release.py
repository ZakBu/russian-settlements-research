"""Release verification rejects changed bytes and a different Git producer."""
import hashlib
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from scripts.sgrt_zero.verify_identity_release import verify_archive_integrity, verify_reproduction, file_spec, verify_registry_csv


class IdentityReleaseVerificationTests(unittest.TestCase):
    def test_public_csv_actual_schema_without_internal_star_id_and_duplicate_NP(self):
        # The 17-column schema of the published registry, not its internal
        # Parquet schema. Every centre has one external participant here.
        headers = ['centre_settlement_id', 'centre_name', 'centre_region', 'type_code', 'type_label',
                   'lat', 'lon', 'own_known_basic_function_count', 'own_known_basic_functions_json',
                   'external_participant_count', 'core_diameter_km', 'ownership_evidence_class',
                   'selected_links_with_cartographic_ownership', 'population_budget_partial',
                   'centre_population_2021_source_value', 'own_offer_includes_documented_dated_school_presence',
                   'own_offer_includes_historical_only_source']
        rows = [dict.fromkeys(headers, '') for _ in range(50)]
        for number, row in enumerate(rows):
            row.update(centre_settlement_id='np-' + str(number), own_known_basic_function_count=3,
                       external_participant_count=1, core_diameter_km=number + .5)
        independent = {'external_pairs': 50, 'diameter_cases': [
            {'centre_settlement_id': row['centre_settlement_id'], 'reported_diameter_km': row['core_diameter_km'],
             'independent_spherical_diameter_km': row['core_diameter_km']} for row in rows]}
        member = 'frozen/registry/level0_centres.csv'
        manifest = {'archive_root': 'frozen/', 'registry_counts': {'registered_level0_centres': 50,
                    'by_recorded_own_basic_function_count': {'3': 50}, 'centre_member_pairs': 100,
                    'diameter_km': {'maximum': 49.5}}, 'standalone_assets': {}}
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder)/'registry.zip'
            def write():
                text = io.StringIO(newline='')
                writer = csv.DictWriter(text, fieldnames=headers)
                writer.writeheader(); writer.writerows(rows)
                content = text.getvalue().encode()
                spec = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                manifest['standalone_assets']['level0_centres.csv'] = {
                    'asset': 'level0_centres.csv', 'archive_member': member, **spec}
                with zipfile.ZipFile(archive, 'w') as out:
                    out.writestr(member, content)
                return {member: spec}
            checked = write()
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(verify_registry_csv(zipped, manifest, checked, independent)['registry_csv_rows'], 50)
            rows[0]['centre_settlement_id'] = rows[1]['centre_settlement_id']
            checked = write()
            with zipfile.ZipFile(archive) as zipped:
                with self.assertRaisesRegex(ValueError, 'Duplicate or empty CSV centre identity'):
                    verify_registry_csv(zipped, manifest, checked, independent)

    def test_changed_member_rejected_even_if_outer_zip_hash_was_updated(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder)/'result.zip'
            manifest = {'archive_root': 'frozen/', 'files': {
                'table.txt': {'bytes': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}}}
            def write(content):
                with zipfile.ZipFile(archive, 'w') as out:
                    out.writestr('frozen/table.txt', content)
                    out.writestr('frozen/manifest.json', json.dumps(manifest))
                manifest['archive'] = {'asset': archive.name, **file_spec(archive)}
            write(b'good')
            self.assertEqual(len(verify_archive_integrity(manifest, archive)), 2)
            # Recompute the outer archive checksum, but keep the pinned member
            # checksum: a valid ZIP/CRC and plausible outer SHA are insufficient.
            write(b'evil')
            with self.assertRaisesRegex(ValueError, 'Member size/SHA mismatch'):
                verify_archive_integrity(manifest, archive)

    def test_archived_code_must_match_the_requested_commit_not_current_worktree(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-q')
            git('config', 'user.email', 'fixture@example.invalid')
            git('config', 'user.name', 'Fixture')
            path = repo/'scripts/sgrt_zero/demo.py'
            path.parent.mkdir(parents=True)
            path.write_text('value = 1\n')
            git('add', '.')
            git('commit', '-qm', 'producer one')
            producer_one = git('rev-parse', 'HEAD')
            old = file_spec(path)
            path.write_text('value = 2\n')
            git('commit', '-qam', 'producer two')
            producer_two = git('rev-parse', 'HEAD')
            checked = {'frozen/reproduction/scripts/sgrt_zero/demo.py': old}
            self.assertTrue(verify_reproduction(None, 'frozen/', checked, producer_one, repo)['all_reproduction_files_match_producer'])
            with self.assertRaisesRegex(ValueError, 'differ from producer commit'):
                verify_reproduction(None, 'frozen/', checked, producer_two, repo)


if __name__ == '__main__':
    unittest.main()
