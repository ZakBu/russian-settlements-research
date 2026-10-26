import json
from pathlib import Path
import sys
import unittest
import pandas as pd
from shapely.geometry import box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.cartographic_identity import build_locality_polygons, assign_cartographic_identity


def feature(wof_id=10, name='А', bounds=(37, 55, 38, 56), region_id=1, **changes):
    geometry = mapping(box(*bounds))
    props = {'wof:name': name, 'name:rus_x_preferred': [name], 'src:geom': 'quattroshapes'}
    props.update(changes.pop('properties', {}))
    row = {'wof_id': wof_id, 'wof_name': name, 'placetype': 'locality',
           'geometry_type': 'Polygon', 'is_current': 1,
           'geometry_json': json.dumps(geometry),
           'hierarchy_json': json.dumps([{'region_id': region_id}]),
           'all_properties_json': json.dumps(props)}
    row.update(changes)
    return row


def reference(extra=False):
    rows = [{'source_record_id': 'a', 'name': 'А', 'region': 'тестовая',
             'lat': 55.5, 'lon': 37.5, 'population_2021': 10000,
             'population_role': 'ordinary_settlement_record', 'budget_population_credit': True,
             'settlement_type_2021': 'город', 'analysis_origin': True}]
    if extra:
        rows.append(dict(rows[0], source_record_id='b', name='Б', lat=55.8,
                         lon=37.8, population_2021=100, settlement_type_2021='село'))
    return pd.DataFrame(rows)


def mapped(features=None, ref=None):
    parent = pd.DataFrame([{'wof_id': 1, 'all_properties_json': json.dumps({'wof:name': 'Тестовая область'})}])
    return build_locality_polygons(pd.DataFrame(features or [feature()]), parent,
                                  ref if ref is not None else reference(),
                                  {'github_commit': 'c' * 40, 'sha256': 's' * 64})


def sites(**changes):
    row = {'site_id': 'school:1', 'site_lat': 55.6, 'site_lon': 37.6,
           'source_record_id': None, 'tags_json': '{}', 'name': 'Школа'}
    row.update(changes)
    return pd.DataFrame([row])


class CartographicIdentityTest(unittest.TestCase):
    def test_named_containment_is_cartographic_and_raw_fields_survive(self):
        polygons, _ = mapped()
        raw = sites()
        result = assign_cartographic_identity(raw, polygons)
        pd.testing.assert_frame_equal(raw, result[raw.columns])
        self.assertEqual(result.iloc[0].verified_boundary_source_record_id, 'a')
        self.assertTrue(result.iloc[0].cartographic_not_legal_boundary)
        self.assertFalse(result.iloc[0].cartographic_identity_is_observed_assignment)
        self.assertEqual(result.iloc[0].cartographic_source_repository_commit, 'c' * 40)

    def test_name_alone_or_closest_point_never_maps_polygon(self):
        polygons, rejected = mapped([feature(bounds=(38, 55, 39, 56))])
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'named_contained_census_identity_not_unique')

    def test_localadmin_and_unknown_currency_not_promoted(self):
        polygons, rejected = mapped([feature(placetype='localadmin'), feature(wof_id=11, is_current=-1)])
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'currency_not_explicit_current')

    def test_region_conflict_and_source_type_conflict_hold(self):
        polygons, rejected = mapped([feature(region_id=2)])
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'regional_hierarchy_unknown')
        polygons, rejected = mapped([feature(properties={'place': 'village'})])
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'literal_source_settlement_type_conflict')

    def test_other_census_place_not_silently_donated_to_city(self):
        polygons, _ = mapped(ref=reference(extra=True))
        unknown = assign_cartographic_identity(sites(), polygons).iloc[0]
        self.assertEqual(unknown.cartographic_identity_status, 'held_finer_census_places_inside_cartographic_polygon')
        self.assertIsNone(unknown.verified_boundary_source_record_id)
        literal = assign_cartographic_identity(sites(tags_json='{"addr:city":"А"}'), polygons).iloc[0]
        self.assertIsNone(literal.verified_boundary_source_record_id)
        self.assertEqual(literal.cartographic_identity_status, 'held_finer_census_places_inside_cartographic_polygon')
        self.assertTrue(literal.cartographic_contains_other_census_places)

    def test_finer_literal_conflict_beats_broad_city_and_same_polygon(self):
        polygons, _ = mapped(ref=reference(extra=True))
        row = assign_cartographic_identity(sites(tags_json='{"addr:city":"А","addr:place":"Б"}'), polygons).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'held_literal_locality_conflict')
        self.assertIsNone(row.verified_boundary_source_record_id)

    def test_existing_source_owner_is_never_replaced(self):
        polygons, _ = mapped()
        row = assign_cartographic_identity(sites(source_record_id='original-other'), polygons).iloc[0]
        self.assertEqual(row.source_record_id, 'original-other')
        self.assertEqual(row.cartographic_identity_status, 'held_existing_source_owner_conflict')

    def test_two_overlapping_different_named_nps_are_held(self):
        ref = reference(extra=True)
        polygons, _ = mapped([feature(bounds=(37, 55, 37.7, 55.7)),
                              feature(wof_id=11, name='Б', bounds=(37.55, 55.55, 38, 56))], ref)
        row = assign_cartographic_identity(sites(), polygons).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'held_overlapping_different_census_localities')
        self.assertIsNone(row.verified_boundary_source_record_id)

    def test_boundary_and_invalid_coordinates_not_accepted(self):
        polygons, _ = mapped()
        row = assign_cartographic_identity(sites(site_lon=37), polygons).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'held_point_on_cartographic_boundary')
        row = assign_cartographic_identity(sites(site_lat=100), polygons).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'invalid_source_coordinates')

    def test_saratov_engels_remain_different_named_polygons(self):
        ref = reference(extra=True)
        ref.loc[0, 'name'] = 'Саратов'
        ref.loc[1, 'name'] = 'Энгельс'
        polygons, _ = mapped([feature(name='Саратов', bounds=(37, 55, 37.7, 55.7)),
                              feature(wof_id=11, name='Энгельс', bounds=(37.75, 55.75, 38, 56))], ref)
        self.assertEqual(set(polygons.source_record_id), {'a', 'b'})
        self.assertEqual(len(polygons), 2)


    def test_unknown_current_is_separate_tier_not_a_cessation(self):
        parent = pd.DataFrame([{'wof_id': 1, 'all_properties_json': json.dumps({'wof:name': 'Тестовая область'})}])
        polygons, rejected = build_locality_polygons(pd.DataFrame([feature(is_current=-1)]), parent,
            reference(), include_unknown_current=True)
        self.assertEqual(len(polygons), 1)
        self.assertEqual(polygons.iloc[0].cartographic_currency, 'dated_cartographic_unknown_currency')
        row = assign_cartographic_identity(sites(), polygons).iloc[0]
        self.assertEqual(row.cartographic_accepted_source_record_id, 'a')
        self.assertEqual(row.cartographic_currency, 'dated_cartographic_unknown_currency')

    def test_known_cessation_does_not_enter_unknown_currency_scenario(self):
        parent = pd.DataFrame([{'wof_id': 1, 'all_properties_json': json.dumps({'wof:name': 'Тестовая область'})}])
        polygons, rejected = build_locality_polygons(pd.DataFrame([
            feature(is_current=-1, properties={'edtf:cessation': '2017-01-01'})]), parent,
            reference(), include_unknown_current=True)
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'superseded_locality')

    def test_russian_alias_and_homonym_are_checked_inside_each_polygon(self):
        polygons, rejected = mapped([feature(name='Angliyskoe', properties={'name:rus_x_preferred': ['А']})])
        self.assertEqual(polygons.iloc[0].source_record_id, 'a')
        ref = reference(extra=True)
        ref.loc[1, 'name'] = 'А'
        polygons, rejected = mapped(ref=ref)
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'named_contained_census_identity_not_unique')

    def test_nominal_outside_is_opt_in_named_bridge_not_nearest(self):
        parent = pd.DataFrame([{'wof_id': 1, 'all_properties_json': json.dumps({'wof:name': 'Тестовая область'})}])
        ref = reference()
        ref.loc[0, 'lon'] = 38.001
        polygons, rejected = build_locality_polygons(pd.DataFrame([feature()]), parent, ref)
        self.assertEqual(len(polygons), 0)
        polygons, rejected = build_locality_polygons(pd.DataFrame([feature()]), parent, ref,
                                                    allow_nominal_outside=True)
        self.assertEqual(polygons.iloc[0].source_record_id, 'a')
        self.assertEqual(polygons.iloc[0].mapping_basis, 'unique_literal_name_and_region_reference_point_outside')
        self.assertFalse(polygons.iloc[0].reference_point_in_polygon)
        self.assertGreater(polygons.iloc[0].reference_point_polygon_offset_km, 0)

    def test_nominal_far_or_same_region_homonym_is_held(self):
        parent = pd.DataFrame([{'wof_id': 1, 'all_properties_json': json.dumps({'wof:name': 'Тестовая область'})}])
        ref = reference()
        ref.loc[0, 'lon'] = 39.
        polygons, rejected = build_locality_polygons(pd.DataFrame([feature()]), parent, ref,
                                                    allow_nominal_outside=True)
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'nominal_identity_reference_point_too_far_from_polygon')
        ref = reference(extra=True)
        ref.loc[:, 'name'] = 'А'
        ref.loc[:, 'lon'] = [38.001, 38.002]
        polygons, rejected = build_locality_polygons(pd.DataFrame([feature()]), parent, ref,
                                                    allow_nominal_outside=True)
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'named_contained_census_identity_not_unique')

    def test_nominal_district_disagreement_is_held(self):
        parent = pd.DataFrame([
            {'wof_id': 1, 'all_properties_json': json.dumps({'wof:name': 'Тестовая область'})},
            {'wof_id': 2, 'all_properties_json': json.dumps({'wof:name': 'Другой район', 'name:rus_x_preferred': ['Другой район']})},
        ])
        ref = reference()
        ref.loc[0, 'lon'] = 38.001
        ref['district'] = 'Первый район'
        f = feature()
        f['hierarchy_json'] = json.dumps([{'region_id': 1, 'county_id': 2}])
        polygons, rejected = build_locality_polygons(pd.DataFrame([f]), parent, ref,
                                                    allow_nominal_outside=True)
        self.assertEqual(len(polygons), 0)
        self.assertEqual(rejected.iloc[0].reason, 'district_hierarchy_conflict_for_nominal_outside')

    def test_new_nominal_duplicate_does_not_erase_contained_named_match(self):
        parent = pd.DataFrame([{'wof_id': 1, 'all_properties_json': json.dumps({'wof:name': 'Тестовая область'})}])
        polygons, rejected = build_locality_polygons(pd.DataFrame([
            feature(), feature(wof_id=11, bounds=(37.51, 55.49, 37.52, 55.51))]),
            parent, reference(), allow_nominal_outside=True)
        self.assertEqual(polygons.wof_id.tolist(), [10])
        self.assertEqual(rejected.iloc[0].reason, 'nominal_polygon_competes_with_contained_polygon')

    def test_wof_guard_keeps_uncredited_nonanalysis_physical_neighbour(self):
        ref = reference(extra=True)
        ref.loc[1, ['budget_population_credit', 'analysis_origin']] = False
        polygons, _ = mapped(ref=ref)
        self.assertEqual(polygons.iloc[0].other_positive_census_places, 1)
        self.assertEqual(json.loads(polygons.iloc[0].other_positive_census_place_ids_json), ['b'])
        row = assign_cartographic_identity(sites(tags_json='{"addr:city":"А"}'), polygons).iloc[0]
        self.assertEqual(row.cartographic_identity_status, 'held_finer_census_places_inside_cartographic_polygon')


if __name__ == '__main__':
    unittest.main()
