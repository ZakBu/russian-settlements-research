import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import pandas as pd
import shapely
from shapely.geometry import mapping, Polygon

from scripts.sgrt_saratov import cloud_isochrones as cloud


class GeometryControls(unittest.TestCase):
    def test_ring_orientation_and_feature_order_do_not_change_meaning(self):
        polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a.geojson', Path(folder)/'b.geojson'
            def feature(identity, geometry):
                return {'type': 'Feature', 'properties': {'id': identity, 'minutes': 20},
                        'geometry': mapping(geometry)}
            a.write_text(json.dumps({'type': 'FeatureCollection', 'features': [feature('a', polygon), feature('b', polygon)]}))
            b.write_text(json.dumps({'type': 'FeatureCollection', 'features': [feature('b', shapely.reverse(polygon)), feature('a', polygon)]}))
            self.assertEqual(cloud.geometry_control(a), cloud.geometry_control(b))

    def test_geometry_or_properties_change_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'shape.geojson'
            feature = {'type': 'Feature', 'properties': {'id': 'x', 'minutes': 20},
                       'geometry': mapping(Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))}
            def save():
                path.write_text(json.dumps({'type': 'FeatureCollection', 'features': [feature]}))
                return cloud.geometry_control(path)
            before = save()
            feature['properties']['minutes'] = 30
            self.assertNotEqual(before, save())
            feature['properties']['minutes'] = 20
            feature['geometry'] = mapping(Polygon([(0, 0), (1, 0), (1, 2), (0, 1)]))
            self.assertNotEqual(before, save())

    def test_invalid_geometry_and_duplicate_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'bad.geojson'
            feature = {'type': 'Feature', 'properties': {'id': 'x'},
                       'geometry': mapping(Polygon([(0, 0), (1, 1), (0, 1), (1, 0)]))}
            path.write_text(json.dumps({'type': 'FeatureCollection', 'features': [feature]}))
            with self.assertRaisesRegex(ValueError, 'Invalid'):
                cloud.geometry_control(path)
            feature['geometry'] = mapping(Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))
            path.write_text(json.dumps({'type': 'FeatureCollection', 'features': [feature, feature]}))
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                cloud.geometry_control(path)


class TableControls(unittest.TestCase):
    def test_missing_is_not_zero_and_lost_row_changes_control(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'time.parquet'
            frame = pd.DataFrame({'origin': ['a', 'b'], 'minutes': [None, 0.]})
            frame.to_parquet(path)
            original = cloud.table_control(path)
            frame.fillna({'minutes': 0}).to_parquet(path)
            self.assertNotEqual(original, cloud.table_control(path))
            frame.iloc[:1].to_parquet(path)
            self.assertNotEqual(original, cloud.table_control(path))

    def test_projected_geometry_compared_semantically(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'roads.parquet'
            geometry = shapely.MultiLineString([[(1, 1), (2, 2)], [(3, 3), (4, 4)]])
            pd.DataFrame({'crs': ['EPSG:32638'], 'reachable_road_geometry_wkb': [shapely.to_wkb(geometry)]}).to_parquet(path)
            before = cloud.table_control(path)
            pd.DataFrame({'crs': ['EPSG:32638'], 'reachable_road_geometry_wkb': [shapely.to_wkb(shapely.reverse(geometry))]}).to_parquet(path)
            self.assertEqual(before, cloud.table_control(path))

    def test_native_wgs84_geometry_does_not_use_projected_rounding(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'native.parquet'
            geometry = shapely.LineString([(46., 51.), (46.1, 51.1)])
            pd.DataFrame({'crs': ['EPSG:4326'], 'native_geometry_wkb': [shapely.to_wkb(geometry)]}).to_parquet(path)
            before = cloud.table_control(path)
            changed = shapely.LineString([(46., 51.), (46.1000001, 51.1)])
            pd.DataFrame({'crs': ['EPSG:4326'], 'native_geometry_wkb': [shapely.to_wkb(changed)]}).to_parquet(path)
            self.assertNotEqual(before, cloud.table_control(path))

    def test_all_declared_sources_exist_in_catalogues_once(self):
        count = 0
        for catalogue, selected in cloud.INPUTS.items():
            rows = json.loads((cloud.REPO/catalogue).read_text())['files']
            for name in selected:
                self.assertEqual(sum(row['path'] == name for row in rows), 1)
                count += 1
        self.assertEqual(count, 37)

    def test_ordered_native_way_references_are_fully_compared(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'ways.parquet'
            pd.DataFrame({'way_id': [1], 'refs': [[1, 2, 3]], 'speed_kmh': [30.]}).to_parquet(path)
            before = cloud.table_control(path)
            pd.DataFrame({'way_id': [1], 'refs': [[1, 3, 2]], 'speed_kmh': [30.]}).to_parquet(path)
            self.assertNotEqual(before, cloud.table_control(path))


class DraftProtection(unittest.TestCase):
    def prepare(self, folder):
        path = Path(folder)
        archive = path/'saratov-isochrones.zip'; archive.write_bytes(b'zip')
        standalone = {}
        for name in cloud.STANDALONE:
            item = path/name; item.write_text('{}')
            standalone[name] = {'bytes': item.stat().st_size, 'sha256': cloud.sha(item)}
        manifest = {'release_tag': cloud.TAG, 'source_commit': 'producer',
                    'archive': {'asset': archive.name, 'bytes': 3, 'sha256': cloud.sha(archive)},
                    'standalone_assets': standalone}
        (path/'manifest.json').write_text(json.dumps(manifest)); (path/'release_notes.md').write_text('Notes')
        return path, manifest

    @patch.object(cloud, 'clean_commit')
    def test_existing_draft_prevents_all_mutations(self, clean):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.prepare(folder)
            with patch.object(cloud, 'releases', return_value=[{'tag_name': cloud.TAG, 'draft': True}]), patch.object(cloud.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'never overwritten'):
                    cloud.draft(path, 'producer')
                run.assert_not_called()

    @patch.object(cloud, 'clean_commit')
    def test_401_does_not_establish_tag_absence(self, clean):
        with tempfile.TemporaryDirectory() as folder:
            path, _ = self.prepare(folder)
            with patch.object(cloud, 'releases', return_value=[]), patch.object(cloud.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='HTTP 401')) as run:
                with self.assertRaisesRegex(ValueError, 'Cannot establish absence'):
                    cloud.draft(path, 'producer')
                self.assertEqual(run.call_count, 1)

    @patch.object(cloud, 'clean_commit')
    def test_new_release_is_draft_only_and_all_uploaded_digests_checked(self, clean):
        with tempfile.TemporaryDirectory() as folder:
            path, manifest = self.prepare(folder)
            assets = [path/'saratov-isochrones.zip', path/'manifest.json'] + [path/name for name in cloud.STANDALONE]
            created = {'id': 123, 'tag_name': cloud.TAG, 'draft': True, 'target_commitish': 'producer',
                       'assets': [{'name': item.name, 'size': item.stat().st_size, 'digest': 'sha256:'+cloud.sha(item)} for item in assets]}
            with patch.object(cloud, 'releases', side_effect=[[], [created]]), patch.object(cloud.subprocess, 'run', side_effect=[SimpleNamespace(returncode=1, stderr='HTTP 404'), SimpleNamespace(returncode=0)]) as run:
                self.assertEqual(cloud.draft(path, 'producer'), 123)
                commands = [args.args[0] for args in run.call_args_list]
                self.assertIn('--draft', commands[1])
                self.assertFalse(any('PATCH' in command for command in commands))

    def test_incomplete_scientific_output_cannot_generate_expected_control(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'Completed scientific output'):
                cloud.control(Path(folder))


class NativeSourceAssembly(unittest.TestCase):
    def test_chords_or_requantized_final_overlay_cannot_be_published(self):
        valid = {'geometry_source': 'original_accepted_source_way_polylines',
                 'topology_precision_grid_degrees': 0,
                 'native_geometry_validation': {'missing_minimum_arcs': 0, 'minimum_arc_cost_disagreements': 0}}
        cloud.validate_model_summary(valid)
        with self.assertRaisesRegex(ValueError, 'compressed endpoint chords'):
            cloud.validate_model_summary({**valid, 'geometry_source': 'REJECTED_compressed_endpoint_chords_diagnostic_only'})
        with self.assertRaisesRegex(ValueError, 'intersection precision'):
            cloud.validate_model_summary({**valid, 'topology_precision_grid_degrees': 1e-7})
        with self.assertRaisesRegex(ValueError, 'reconstruct'):
            cloud.validate_model_summary({**valid, 'native_geometry_validation': {'missing_minimum_arcs': 1, 'minimum_arc_cost_disagreements': 0}})

    def test_pbf_part_order_and_combined_hash_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'input'
            parts = source/cloud.PBF_PREFIX
            parts.mkdir(parents=True)
            for n, byte in enumerate([b'a', b'b', b'c', b'd', b'e', b'f']):
                (parts/(cloud.PBF_NAME+f'.part{n:03d}')).write_bytes(byte)
            target = Path(folder)/'assembled/source.pbf'
            with patch.object(cloud, 'PBF_BYTES', 6), patch.object(cloud, 'PBF_SHA256', hashlib.sha256(b'abcdef').hexdigest()):
                cloud.join_native_pbf(source, target)
                self.assertEqual(target.read_bytes(), b'abcdef')
                target.unlink()
                (parts/(cloud.PBF_NAME+'.part001')).write_bytes(b'c')
                (parts/(cloud.PBF_NAME+'.part002')).write_bytes(b'b')
                with self.assertRaisesRegex(ValueError, 'differs'):
                    cloud.join_native_pbf(source, target)
                self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
