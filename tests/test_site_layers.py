"""A new research layer works through declarative adapters, not UI changes."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('layer_export', Path(__file__).parents[1] / 'scripts/build_site_data.py')
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)


def layer(adapter='csv-points', geometry='point'):
    return {'adapter': adapter, 'geometry': geometry,
            'fields': {'id': 'id', 'name': 'name', 'value': 'value', 'longitude': 'lon', 'latitude': 'lat'}}


class LayerTests(unittest.TestCase):
    def test_csv_coordinates_zero_and_null_value_survive(self):
        output = site.adapt_layer(layer(), b'id,name,value,lon,lat\na,Zero,0,0,0\nb,Unknown,,1,2\n', {})
        self.assertEqual(output['features'][0]['geometry']['coordinates'], [0, 0])
        self.assertEqual(output['features'][0]['properties']['value'], 0)
        self.assertIsNone(output['features'][1]['properties']['value'])

    def test_settlement_adapter_joins_only_exact_primary_key(self):
        specification = layer('csv-settlement')
        specification['fields'] = {'id': 'id', 'name': 'name', 'value': 'value', 'settlementKey': 'source'}
        lookup = {'accepted:1': {'geometry': {'type': 'Point', 'coordinates': [50, 55]}, 'properties': {'id': 'short'}}}
        output = site.adapt_layer(specification, b'id,name,value,source\na,Point,4,accepted:1\n', lookup)
        self.assertEqual(output['features'][0]['properties']['settlementId'], 'short')
        self.assertEqual(output['features'][0]['properties']['value'], 4)
        with self.assertRaisesRegex(ValueError, 'no accepted point'):
            site.adapt_layer(specification, b'id,name,value,source\na,Point,4,Point\n', lookup)

    def test_duplicate_id_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            site.adapt_layer(layer(), b'id,name,value,lon,lat\na,A,1,0,0\na,B,2,1,1\n', {})

    def test_outside_range_and_nonfinite_values_rejected(self):
        for data in [b'id,name,value,lon,lat\na,A,1,181,0\n', b'id,name,value,lon,lat\na,A,Infinity,1,1\n']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                site.adapt_layer(layer(), data, {})

    def test_geojson_cannot_claim_different_geometry(self):
        data = json.dumps({'type': 'FeatureCollection', 'features': [{'type': 'Feature',
            'properties': {'id': 'a', 'name': 'A', 'value': 1}, 'geometry': {'type': 'LineString', 'coordinates': [[0, 0], [1, 1]]}}]}).encode()
        specification = layer('geojson')
        specification['fields'] = {'id': 'id', 'name': 'name', 'value': 'value'}
        with self.assertRaisesRegex(ValueError, 'does not match'):
            site.adapt_layer(specification, data, {})
        specification['geometry'] = 'line'
        self.assertEqual(len(site.adapt_layer(specification, data, {})['features']), 1)

    def test_hash_failure_never_populates_trusted_cache(self):
        dataset = {'id': 'example', 'url': 'https://example.test/pinned.csv', 'sha256': 'a' * 64}
        stream = io.BytesIO(b'wrong bytes')
        stream.url = dataset['url']
        with tempfile.TemporaryDirectory() as temporary, patch.object(site, 'urlopen', return_value=stream):
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                site.layer_source(dataset, Path(temporary))
            self.assertEqual(list(Path(temporary).rglob('*.source')), [])

    def test_offline_cache_is_reverified(self):
        payload = b'id,name\na,A\n'
        sha = hashlib.sha256(payload).hexdigest()
        dataset = {'id': 'example', 'url': 'https://example.test/pinned.csv', 'sha256': sha}
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            (cache / 'layers').mkdir()
            target = cache / 'layers' / (sha + '.source')
            target.write_bytes(payload)
            self.assertEqual(site.layer_source(dataset, cache, offline=True), payload)
            target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                site.layer_source(dataset, cache, offline=True)

    def test_source_must_be_version_pinned(self):
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(ValueError, 'pin a version'):
            site.layer_source({'id': 'x', 'url': 'https://raw.githubusercontent.com/u/r/main/input.csv', 'sha256': 'a' * 64}, Path(temporary))


if __name__ == '__main__':
    unittest.main()
