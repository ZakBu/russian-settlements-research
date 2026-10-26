"""Scientific edge cases of the static export, using small in-memory fixtures."""
import importlib.util
from pathlib import Path
import unittest
import sqlite3
import tempfile

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

    def test_geopackage_selection_reads_real_ids_without_relabeling_source(self):
        from shapely.geometry import Polygon
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.gpkg'
            blob = b'GP' + bytes([0,1]) + (4326).to_bytes(4,'little') + Polygon([(49,54),(51,54),(51,56),(49,54)]).wkb
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE gpkg_geometry_columns (table_name TEXT,column_name TEXT,srs_id INTEGER)')
                conn.execute('INSERT INTO gpkg_geometry_columns VALUES ("adm1","geom",4326)')
                conn.execute('CREATE TABLE adm1 (fid INTEGER,geom BLOB,adm1_id TEXT,name TEXT,iso_3166_2 TEXT,unit_key TEXT)')
                conn.executemany('INSERT INTO adm1 VALUES (?,?,?,?,?,?)',[(1,blob,'crimea','Крим','UA-43','UKR'),(2,blob,'other','Інша область','UA-01','UKR')])
            asset = {'fileFormat':'gpkg','sourceLayer':'adm1','sourceTotalCount':2,'featureIds':['crimea']}
            raw = site.read_boundary_source(path,asset)
            self.assertEqual(len(raw['features']),1)
            props = raw['features'][0]['properties']
            self.assertEqual(props['adm1_id'],'crimea')
            self.assertEqual(props['name'],'Крим')
            self.assertEqual(props['iso_3166_2'],'UA-43')
            self.assertEqual(props['unit_key'],'UKR')
            self.assertNotIn('geom',props)
            with self.assertRaisesRegex(ValueError,'missing'):
                site.read_boundary_source(path,{**asset,'featureIds':['missing']})
            with self.assertRaisesRegex(ValueError,'unique'):
                site.read_boundary_source(path,{**asset,'featureIds':['crimea','crimea']})
            with self.assertRaisesRegex(ValueError,'source count'):
                site.read_boundary_source(path,{**asset,'sourceTotalCount':3})
            with sqlite3.connect(path) as conn:
                conn.execute('UPDATE gpkg_geometry_columns SET srs_id=3857')
            with self.assertRaisesRegex(ValueError,'WGS84'):
                site.read_boundary_source(path,asset)

    def test_reference_supplement_preserves_original_country_iso_names_and_source_counts(self):
        geometry = {'type': 'Polygon', 'coordinates': [[[49,54],[51,54],[51,56],[49,56],[49,54]]]}
        source = site.feature_collection([{'type':'Feature','geometry':geometry,'properties':{
            'adm1_id':'crimea-source','name':'Автономна Республіка Крим','name_en':'Autonomous Republic of Crimea',
            'iso_3166_2':'UA-43','unit_key':'UKR','kind':'division'}}])
        supplement = {'id':'regions-crimea','appendTo':'regions','provider':'Terrae','level':'ADM1',
            'epoch':2026,'snapshotDate':'2026-09-28','count':1,'divisionCount':1,'sourceCountry':'UKR',
            'nameOverrides':{'crimea-source':'Крым'}}
        original = {'id':'regions','provider':'Terrae','level':'ADM1','epoch':2026,'count':0}
        groups = site.merge_boundary_sources([(original,site.feature_collection([])),(supplement,source)])
        target, merged, raw, counts = groups[0]
        self.assertEqual(target,'regions')
        self.assertEqual(counts,{'regions':0,'regions-crimea':1})
        self.assertEqual(original['count'],0)
        self.assertEqual(merged['count'],1)
        population, details, _ = export(fixture(working_credit_present_2002=False))
        features, coverage = site.boundary_features(raw,merged,population,details)
        props = features[0]['properties']
        self.assertEqual(props['name'],'Крым')
        self.assertEqual(props['sourceLocalName'],'Автономна Республіка Крим')
        self.assertEqual(props['sourceCountry'],'UKR')
        self.assertEqual(props['iso'],'UA-43')
        self.assertTrue(props['referenceSupplement'])
        self.assertEqual(props['referenceSourceId'],'regions-crimea')
        self.assertEqual(props['count'],1)
        self.assertIsNone(props['p02'])
        self.assertIsNone(props['p10'])
        self.assertIsNone(props['p21'])
        self.assertEqual(coverage['ambiguousPoints'],0)

    def test_reference_sources_validate_counts_levels_and_ids_before_union(self):
        geometry = {'type':'Polygon','coordinates':[[[0,0],[1,0],[1,1],[0,0]]]}
        raw = site.feature_collection([{'type':'Feature','geometry':geometry,
            'properties':{'shapeID':'same','shapeName':'Территория'}}])
        asset = {'id':'regions','level':'ADM1','epoch':2026,'count':1}
        with self.assertRaisesRegex(ValueError,'count'):
            site.merge_boundary_sources([({**asset,'count':2},raw)])
        with self.assertRaisesRegex(ValueError,'Repeated'):
            site.merge_boundary_sources([(asset,raw),({**asset,'id':'extra','appendTo':'regions'},raw)])
        with self.assertRaisesRegex(ValueError,'level'):
            site.merge_boundary_sources([(asset,raw),({**asset,'id':'extra','appendTo':'regions','level':'ADM2'},raw)])

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

    def test_overview_keeps_history_large_places_when_latest_population_missing(self):
        first, _, _ = export(fixture(population_2002=15000,effective_population_2002=15000,
            working_credit_present_2010=False,working_credit_present_2021=False))
        payload = site.compact_population(first)
        overview = site.overview_population(payload)
        self.assertEqual(overview['format'],payload['format'])
        self.assertEqual(overview['columns'],payload['columns'])
        self.assertEqual(overview['regions'],payload['regions'])
        self.assertEqual(overview['rows'],payload['rows'])
        self.assertIsNone(overview['rows'][0][payload['columns'].index('p21')])
        self.assertEqual(overview['rows'][0][payload['columns'].index('p02')],15000)

    def test_overview_excludes_small_or_unknown_rows_without_mutating_full_transport(self):
        columns=['id','name','regionIndex','longitude','latitude','p02','p10','p21','change','comparable']
        rows=[['small','Малое',2,50,55,9999,500,1,-99,True],
              ['unknown','Нет сведений',1,51,56,None,None,None,None,False],
              ['edge','Граница',0,52,57,None,10000,None,None,False]]
        payload={'format':'settlements-columnar-v1','columns':columns,'regions':['А','Б','В'],'rows':rows}
        overview=site.overview_population(payload)
        self.assertEqual(len(payload['rows']),3)
        self.assertEqual(overview['rows'],[rows[2]])
        self.assertEqual(overview['regions'],['А','Б','В'])
        self.assertEqual(overview['rows'][0][2],0)
        self.assertIs(overview['rows'][0],payload['rows'][2])
        with self.assertRaisesRegex(ValueError,'positive'):
            site.overview_population(payload,0)

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
