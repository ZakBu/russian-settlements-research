"""Scientific edge cases of the static export, using small in-memory fixtures."""
import importlib.util
from pathlib import Path
import unittest

import pandas as pd

SPEC = importlib.util.spec_from_file_location('site_data', Path(__file__).parents[1] / 'scripts/build_site_data.py')
site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(site)


def fixture(source='record:1', **overrides):
    row = {'root': 'chain:1', 'source_record_id_2021': source,
           'accepted_point_present_2021': True, 'accepted_longitude_2021': 50., 'accepted_latitude_2021': 55.,
           'settlement_name_2021': 'Село', 'region_norm_2021': 'Регион', 'district_raw_2021': None,
           'settlement_type_2021': 'село', 'ordinary_full3': True}
    for year in site.YEARS:
        row.update({f'working_credit_present_{year}': True, f'effective_population_{year}': 100.,
                    f'population_{year}': 100., f'population_value_quality_{year}': 'published'})
    return {**row, **overrides}


def export(row):
    long = pd.DataFrame([{'census_year': 2021, 'source_record_id': row['source_record_id_2021'], 'is_additive_settlement_record': True}])
    return site.population_features(pd.DataFrame([row]), long)


class ExportTests(unittest.TestCase):
    def test_terrae_native_russian_names_and_auxiliary_territories_remain_distinct(self):
        raw = site.feature_collection([
            {'type': 'Feature', 'properties': {'adm2_id': 'r1143189', 'name': 'Ишимбайский район',
             'name_en': 'Ishimbaysky District', 'kind': 'division'},
             'geometry': {'type': 'Polygon', 'coordinates': [[[49,54],[51,54],[51,56],[49,56],[49,54]]]}},
            {'type': 'Feature', 'properties': {'adm2_id': 'x-r151225-lake-khanka', 'name': 'Lake Khanka',
             'name_en': 'Lake Khanka', 'kind': 'undivided', 'undivided_kind': 'water'},
             'geometry': {'type': 'Polygon', 'coordinates': [[[130,44],[131,44],[131,45],[130,45],[130,44]]]}}])
        asset = {'provider': 'Terrae', 'level': 'ADM2', 'epoch': 2026, 'snapshotDate': '2026-09-28', 'count': 2, 'renderSimplifyDegrees': .002}
        adapted = site.normalize_boundary_source(raw, asset)
        population, details, _ = export(fixture())
        features, coverage = site.boundary_features(adapted, asset, population, details)
        first, auxiliary = [feature['properties'] for feature in features]
        self.assertEqual(first['name'], 'Ишимбайский район')
        self.assertEqual(first['sourceName'], 'Ishimbaysky District')
        self.assertEqual(first['id'], 'r1143189')
        self.assertEqual(first['epoch'], 2026)
        self.assertEqual(first['sourceDate'], '2026-09-28')
        self.assertEqual(first['p21'], 100)
        self.assertEqual(auxiliary['name'], 'Озеро Ханка')
        self.assertEqual(auxiliary['kind'], 'undivided')
        self.assertEqual(coverage['ambiguousPoints'], 0)

    def test_compact_transport_preserves_nulls_zeroes_ids_coordinates_and_counts(self):
        features, _, _ = export(fixture(effective_population_2002=0, working_credit_present_2010=False))
        payload = site.compact_population(features)
        self.assertEqual(payload['format'], 'settlements-columnar-v1')
        self.assertEqual(len(payload['rows']), len(features))
        row = dict(zip(payload['columns'], payload['rows'][0]))
        original = features[0]
        self.assertEqual(row['id'], original['properties']['id'])
        self.assertEqual(payload['regions'][row['regionIndex']], original['properties']['region'])
        self.assertEqual([row['longitude'], row['latitude']], original['geometry']['coordinates'])
        self.assertEqual(row['p02'], 0)
        self.assertIsNone(row['p10'])
        self.assertIsNone(row['change'])
        self.assertFalse(row['comparable'])

    def test_boundary_transport_keeps_source_geometry_and_scientific_totals(self):
        polygon = {'type': 'Feature', 'properties': {'p21': 100, 'comparableCount': 2, 'sizeBins': [0, 2, 0, 0, 0]},
                   'geometry': {'type': 'Polygon', 'coordinates': [[[1.123456789, 2.123456789], [2, 2], [2, 3], [1.123456789, 2.123456789]]]}}
        display = site.display_boundaries([polygon])['features'][0]
        self.assertEqual(display['properties'], polygon['properties'])
        self.assertEqual(display['geometry']['coordinates'][0][0], [1.12346, 2.12346])
        self.assertEqual(display['geometry']['coordinates'][0][0], display['geometry']['coordinates'][0][-1])
        self.assertEqual(polygon['geometry']['coordinates'][0][0], [1.123456789, 2.123456789])

    def test_russian_region_labels_are_explicit_display_only(self):
        self.assertEqual(len(site.REGION_NAMES_RU), 83)
        self.assertEqual(site.REGION_NAMES_RU['RU-BA'], 'Республика Башкортостан')
        self.assertNotEqual(site.REGION_NAMES_RU['RU-MOW'], site.REGION_NAMES_RU['RU-MOS'])

    def test_uncredited_value_is_null_not_zero_but_raw_value_survives(self):
        features, details, _ = export(fixture(working_credit_present_2010=False, population_2010=123))
        self.assertIsNone(features[0]['properties']['p10'])
        self.assertFalse(features[0]['properties']['comparable'])
        detail = next(iter(details.values()))
        self.assertEqual(detail['rawPopulation']['2010'], 123)
        self.assertFalse(detail['credit']['2010'])

    def test_zero_baseline_has_no_infinite_percentage(self):
        features, _, _ = export(fixture(effective_population_2002=0))
        self.assertIsNone(features[0]['properties']['change'])
        self.assertEqual(features[0]['properties']['p02'], 0)

    def test_missing_point_is_not_inferred_from_other_census(self):
        features, _, _ = export(fixture(accepted_point_present_2021=False))
        self.assertEqual(features, [])

    def test_non_additive_record_is_not_mapped(self):
        row = fixture()
        long = pd.DataFrame([{'census_year': 2021, 'source_record_id': row['source_record_id_2021'], 'is_additive_settlement_record': False}])
        self.assertEqual(site.population_features(pd.DataFrame([row]), long)[0], [])

    def test_federal_city_context_does_not_duplicate_population(self):
        row = fixture()
        long = pd.DataFrame([{'census_year': 2021, 'source_record_id': row['source_record_id_2021'],
                              'is_additive_settlement_record': True, 'population_scope': 'federal_city_region'}])
        self.assertEqual(site.population_features(pd.DataFrame([row]), long)[0], [])

    def test_thumbnail_is_deterministic_real_point_selection(self):
        features, _, _ = export(fixture())
        point = features[0]
        other = {**point, 'properties': {**point['properties'], 'id': 'other', 'p21': 200}}
        result = site.preview_points([point, other])
        self.assertEqual(result, site.preview_points([other, point]))
        self.assertEqual(result[0][:2], point['geometry']['coordinates'])
        self.assertEqual(result[0][3], other['properties']['name'])
        self.assertEqual(result[0][4], 200)

    def test_polygon_sum_uses_only_strict_fixed_cohort(self):
        feature = {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]]},
                   'properties': {'shapeID': 'area', 'shapeName': 'Area'}}
        def point(x, comparable):
            return {'geometry': {'type': 'Point', 'coordinates': [x, 1]},
                    'properties': {'comparable': comparable, 'p02': 10, 'p10': 20, 'p21': 30}}
        result, coverage = site.boundary_features({'features': [feature]}, {'id': 'regions', 'count': 1, 'level': 'ADM1', 'epoch': 2017}, [point(1, True), point(2, False)])
        props = result[0]['properties']
        self.assertEqual((props['count'], props['comparableCount'], props['p21']), (2, 1, 30))
        self.assertEqual(props['p21KnownCount'], 2)
        self.assertEqual(props['sizeBins'], [2, 0, 0, 0, 0])
        self.assertIn('not_official', coverage['aggregation'])

    def test_overlapping_polygons_do_not_double_count(self):
        polygon = {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]]},
                   'properties': {'shapeID': 'a', 'shapeName': 'A'}}
        point = {'geometry': {'type': 'Point', 'coordinates': [1, 1]}, 'properties': {'comparable': True, 'p02': 1, 'p10': 1, 'p21': 1}}
        output, coverage = site.boundary_features({'features': [polygon, polygon]}, {'id': 'regions', 'count': 2, 'level': 'ADM1', 'epoch': 2017}, [point])
        self.assertEqual(coverage['ambiguousPoints'], 1)
        self.assertTrue(all(f['properties']['p21'] is None for f in output))

    def test_district_search_alias_is_not_identity_or_rename(self):
        polygon = {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]]},
                   'properties': {'shapeID': 'source-area', 'shapeName': 'Source Raion'}}
        point = {'geometry': {'type': 'Point', 'coordinates': [1, 1]},
                 'properties': {'id': 'np1', 'comparable': True, 'p02': 1, 'p10': 1, 'p21': 1}}
        result, _ = site.boundary_features({'features': [polygon]}, {'id': 'districts', 'count': 1, 'level': 'ADM2', 'epoch': 2017},
                                           [point], {'np1': {'district': 'Муниципальный округ'}})
        props = result[0]['properties']
        self.assertEqual(props['name'], 'Source Raion')
        self.assertEqual(props['sourceName'], 'Source Raion')
        self.assertEqual(props['searchAliases'], ['Муниципальный округ'])
        self.assertIn('not_verified_municipality_match', props['searchAliasBasis'])


if __name__ == '__main__':
    unittest.main()
