import json
from pathlib import Path
import sys
import unittest
import pandas as pd
import shapely
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.geofabrik_identity import build_geofabrik_polygons
from scripts.sgrt_zero.cartographic_identity import ACCEPTED, assign_cartographic_identity, recompute_other_positive_places


def reference():
    return pd.DataFrame([{
        'source_record_id': 'a', 'name': 'А', 'region': 'тестовая',
        'lat': 55.5, 'lon': 37.5, 'settlement_type_2021': 'город',
        'population_2021': 10000., 'population_role': 'ordinary_settlement_record',
        'budget_population_credit': True, 'analysis_origin': True,
    }])


def feature(**changes):
    row = {'osm_id': '123', 'name': 'А', 'fclass': 'city',
           'geometry_wkb': shapely.to_wkb(box(37, 55, 38, 56)),
           'geometry_valid': True, 'source_shard': 'central-fed-district',
           'source_url': 'https://example.org/source.shp.zip',
           'source_snapshot': '2026-10-20T00:00:00Z',
           'source_component_sha256_json': '{"shp":"abc"}'}
    row.update(changes)
    return row


def site(**changes):
    row = {'site_id': 'school', 'site_lat': 55.6, 'site_lon': 37.6,
           'source_record_id': None, 'tags_json': '{}'}
    row.update(changes)
    return pd.DataFrame([row])


class GeofabrikIdentityTest(unittest.TestCase):
    def test_actual_osm_metadata_and_raw_owner_preserved(self):
        polygons, _ = build_geofabrik_polygons(pd.DataFrame([feature()]), reference())
        raw = site()
        result = assign_cartographic_identity(raw, polygons)
        pd.testing.assert_frame_equal(raw, result[raw.columns])
        row = result.iloc[0]
        self.assertEqual(row.cartographic_accepted_source_record_id, 'a')
        self.assertEqual(row.cartographic_source_dataset, 'geofabrik_places_a')
        self.assertEqual(row.cartographic_source_feature_id, '123')
        self.assertTrue(pd.isna(row.cartographic_source_wof_id))
        self.assertTrue(pd.isna(row.cartographic_source_repository_commit))
        self.assertEqual(row.cartographic_source_snapshot, '2026-10-20T00:00:00Z')

    def test_name_point_and_fclass_not_nearest_or_federal_district(self):
        polygons, rejected = build_geofabrik_polygons(pd.DataFrame([
            feature(name='Другой', source_shard='тестовая')]), reference())
        self.assertEqual(polygons.iloc[0].source_record_id, None)
        self.assertNotEqual(polygons.iloc[0].polygon_identity_status, ACCEPTED)
        self.assertEqual(rejected.iloc[0].reason, 'no_exact_name_and_compatible_type_in_whole_reference')

    def test_county_suburb_and_invalid_geometry_not_settlement_boundaries(self):
        polygons, rejected = build_geofabrik_polygons(pd.DataFrame([
            feature(fclass='county'), feature(osm_id='124', fclass='suburb'),
            feature(osm_id='125', geometry_valid=False)]), reference())
        self.assertEqual(len(polygons), 0)
        self.assertEqual(len(rejected), 3)

    def test_unresolved_primary_geometry_blocks_fallback(self):
        polygons, _ = build_geofabrik_polygons(pd.DataFrame([feature(name='Неизвестное')]), reference())
        row = assign_cartographic_identity(site(), polygons).iloc[0]
        self.assertTrue(row.cartographic_geometry_candidate_present)
        self.assertEqual(row.cartographic_identity_status, 'held_unresolved_primary_geometry')
        self.assertIsNone(row.cartographic_accepted_source_record_id)

    def test_nominal_outside_unique_in_entire_reference_and_opt_in(self):
        ref = reference()
        ref.loc[0, 'lon'] = 38.001
        raw = pd.DataFrame([feature()])
        polygons, _ = build_geofabrik_polygons(raw, ref)
        self.assertNotEqual(polygons.iloc[0].polygon_identity_status, ACCEPTED)
        polygons, _ = build_geofabrik_polygons(raw, ref, allow_nominal_outside=True)
        self.assertEqual(polygons.iloc[0].source_record_id, 'a')
        self.assertFalse(polygons.iloc[0].reference_point_in_polygon)
        self.assertEqual(polygons.iloc[0].mapping_basis, 'unique_literal_name_and_fclass_reference_point_outside')
        # An unlocated same-name record must still prevent nominal uniqueness.
        other = dict(ref.iloc[0], source_record_id='b', lat=float('nan'), lon=float('nan'), analysis_origin=False)
        ref = pd.concat([ref, pd.DataFrame([other])], ignore_index=True)
        polygons, rejected = build_geofabrik_polygons(raw, ref, allow_nominal_outside=True)
        self.assertNotEqual(polygons.iloc[0].polygon_identity_status, ACCEPTED)
        self.assertEqual(rejected.iloc[0].reason, 'nominal_same_name_not_unique_in_whole_reference')

    def test_marked_parts_not_counted_as_other_independent_places(self):
        ref = reference()
        ref = pd.concat([ref, pd.DataFrame([dict(ref.iloc[0], source_record_id='part',
            name='А (часть 1)', lat=55.7, lon=37.7)])], ignore_index=True)
        polygons, _ = build_geofabrik_polygons(pd.DataFrame([feature()]), ref)
        self.assertEqual(polygons.iloc[0].other_positive_census_places, 0)
        self.assertEqual(assign_cartographic_identity(site(), polygons).iloc[0].cartographic_accepted_source_record_id, 'a')

    def test_independent_village_not_swallowed_despite_broad_postal_city(self):
        ref = reference()
        ref = pd.concat([ref, pd.DataFrame([dict(ref.iloc[0], source_record_id='village',
            name='Б', lat=55.7, lon=37.7, settlement_type_2021='село')])], ignore_index=True)
        polygons, _ = build_geofabrik_polygons(pd.DataFrame([feature()]), ref)
        self.assertEqual(polygons.iloc[0].other_positive_census_places, 1)
        row = assign_cartographic_identity(site(tags_json='{"addr:city":"А"}'), polygons).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'held_finer_census_places_inside_cartographic_polygon')

    def test_source_owner_and_finer_place_conflicts_remain_held(self):
        polygons, _ = build_geofabrik_polygons(pd.DataFrame([feature()]), reference())
        row = assign_cartographic_identity(site(source_record_id='original'), polygons).iloc[0]
        self.assertEqual(row.source_record_id, 'original')
        self.assertEqual(row.cartographic_identity_status, 'held_existing_source_owner_conflict')
        row = assign_cartographic_identity(site(tags_json='{"addr:place":"Б"}'), polygons).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'held_literal_locality_conflict')

    def test_uncredited_nonanalysis_neighbour_is_still_a_physical_np(self):
        ref = reference()
        ref = pd.concat([ref, pd.DataFrame([dict(ref.iloc[0], source_record_id='uncredited',
            name='Б', lat=55.7, lon=37.7, settlement_type_2021='село',
            budget_population_credit=False, analysis_origin=False)])], ignore_index=True)
        polygons, _ = build_geofabrik_polygons(pd.DataFrame([feature()]), ref)
        self.assertEqual(polygons.iloc[0].other_positive_census_places, 1)
        self.assertEqual(json.loads(polygons.iloc[0].other_positive_census_place_ids_json), ['uncredited'])
        # Refresh does not remap the source owner and uses the same raw IDs.
        stale = polygons.copy()
        stale['other_positive_census_places'] = 0
        stale['other_positive_census_place_ids_json'] = '[]'
        updated = recompute_other_positive_places(stale, ref)
        pd.testing.assert_series_equal(stale.source_record_id, updated.source_record_id)
        self.assertEqual(updated.iloc[0].other_positive_census_places, 1)
        row = assign_cartographic_identity(site(tags_json='{"addr:city":"А"}'), updated).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'held_finer_census_places_inside_cartographic_polygon')


if __name__ == '__main__':
    unittest.main()
