import json
from pathlib import Path
import sys
import unittest
import pandas as pd
import shapely
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.geofabrik_identity import build_geofabrik_polygons
from scripts.sgrt_zero.cartographic_identity import assign_cartographic_identity
from scripts.sgrt_zero.nested_locality_masks import build_nested_locality_masks


def reference(child_lon=37.8, child_lat=55.8, context_parent=False):
    return pd.DataFrame([
        {'source_record_id': 'a', 'name': 'Город', 'region': 'тестовая',
         'lat': 55.5, 'lon': 37.5, 'settlement_type_2021': 'город',
         'population_2021': 10000., 'population_role': 'external_context_nonadditive' if context_parent else 'ordinary_settlement_record',
         'budget_population_credit': True, 'analysis_origin': True},
        {'source_record_id': 'b', 'name': 'Село', 'region': 'тестовая',
         'lat': child_lat, 'lon': child_lon, 'settlement_type_2021': 'село',
         'population_2021': 100., 'population_role': 'ordinary_settlement_record',
         'budget_population_credit': True, 'analysis_origin': True},
    ])


def features(child_bounds=(37.7, 55.7, 37.9, 55.9), include_child=True):
    rows = [{'osm_id': '1', 'name': 'Город', 'fclass': 'city',
             'geometry_wkb': shapely.to_wkb(box(37, 55, 38, 56)), 'geometry_valid': True}]
    if include_child:
        rows.append({'osm_id': '2', 'name': 'Село', 'fclass': 'village',
                     'geometry_wkb': shapely.to_wkb(box(*child_bounds)), 'geometry_valid': True})
    return pd.DataFrame(rows)


def sites():
    return pd.DataFrame([
        {'site_id': 'city-school', 'site_lat': 55.6, 'site_lon': 37.6,
         'source_record_id': None, 'tags_json': '{}'},
        {'site_id': 'village-school', 'site_lat': 55.8, 'site_lon': 37.8,
         'source_record_id': None, 'tags_json': '{}'},
    ])


class NestedLocalityMasksTest(unittest.TestCase):
    def test_actual_nested_footprint_carved_no_parent_donation(self):
        ref = reference()
        original, _ = build_geofabrik_polygons(features(), ref, allow_nominal_outside=True)
        before = original.copy(deep=True)
        derived, diagnostics = build_nested_locality_masks(original, ref)
        pd.testing.assert_frame_equal(original, before, check_exact=True)
        parent = derived[derived.source_record_id.eq('a')].iloc[0]
        self.assertTrue(parent.nested_mask_applied)
        self.assertEqual(parent.original_other_positive_census_places, 1)
        self.assertEqual(parent.other_positive_census_places, 0)
        self.assertEqual(json.loads(parent.nested_mask_census_ids_json), ['b'])
        self.assertEqual(parent.raw_geometry_wkb, before.iloc[0].geometry_wkb)
        classified = assign_cartographic_identity(sites(), derived)
        self.assertEqual(classified.cartographic_accepted_source_record_id.tolist(), ['a', 'b'])

    def test_samara_like_offset_point_with_touching_footprint(self):
        ref = reference(child_lon=37.999, child_lat=55.8)
        raw, _ = build_geofabrik_polygons(features(child_bounds=(38, 55.7, 38.1, 55.9)),
                                         ref, allow_nominal_outside=True)
        derived, _ = build_nested_locality_masks(raw, ref)
        parent = derived[derived.source_record_id.eq('a')].iloc[0]
        self.assertTrue(parent.nested_mask_applied)
        self.assertTrue(shapely.from_wkb(parent.geometry_wkb).equals(shapely.from_wkb(parent.raw_geometry_wkb)))
        self.assertGreater(json.loads(parent.nested_mask_reference_child_point_offsets_json)['b'], 0)
        self.assertEqual(parent.geometry_identity_resolution, 'named_child_footprints_separated')

    def test_missing_child_leaves_original_guard_and_geometry(self):
        ref = reference()
        raw, _ = build_geofabrik_polygons(features(include_child=False), ref)
        derived, _ = build_nested_locality_masks(raw, ref)
        self.assertFalse(derived.iloc[0].nested_mask_applied)
        self.assertEqual(derived.iloc[0].other_positive_census_places, 1)
        self.assertEqual(derived.iloc[0].geometry_wkb, raw.iloc[0].geometry_wkb)
        self.assertEqual(derived.iloc[0].nested_mask_status, 'held_missing_or_ambiguous_named_child_footprint')

    def test_parent_reference_point_inside_child_mask_held(self):
        ref = reference(child_lon=37.6, child_lat=55.6, context_parent=True)
        raw, _ = build_geofabrik_polygons(features(child_bounds=(37.4, 55.4, 37.7, 55.7)), ref)
        derived, _ = build_nested_locality_masks(raw, ref)
        parent = derived[derived.source_record_id.eq('a')].iloc[0]
        self.assertFalse(parent.nested_mask_applied)
        self.assertEqual(parent.nested_mask_status, 'held_parent_reference_point_in_child_mask')

    def test_mutual_physical_dependency_cycle_held(self):
        ref = reference(child_lon=37.6, child_lat=55.6)
        raw, _ = build_geofabrik_polygons(features(child_bounds=(37.4, 55.4, 37.7, 55.7)), ref)
        derived, _ = build_nested_locality_masks(raw, ref)
        self.assertFalse(derived.nested_mask_applied.any())
        self.assertTrue(derived.nested_mask_status.eq('held_cycle_or_dependency_on_cycle').all())

    def test_validated_coordinate_hold_resolves_only_its_point_not_location(self):
        ref = reference()
        raw, _ = build_geofabrik_polygons(features(include_child=False), ref)
        derived, _ = build_nested_locality_masks(raw, ref, coordinate_holds={'b'},
                                                coordinate_hold_provenance_sha256='proof')
        parent = derived.iloc[0]
        self.assertTrue(parent.nested_mask_applied)
        self.assertEqual(parent.geometry_wkb, parent.raw_geometry_wkb)
        self.assertEqual(parent.geometry_identity_resolution, 'invalid_census_point_held')
        self.assertEqual(json.loads(parent.coordinate_hold_census_ids_json), ['b'])
        self.assertEqual(parent.original_other_positive_census_places, 1)
        self.assertEqual(parent.other_positive_census_places, 0)
        self.assertEqual(parent.coordinate_hold_provenance_sha256, 'proof')
        with self.assertRaises(ValueError):
            build_nested_locality_masks(raw, ref, coordinate_holds={'invented-id'})

    def test_cannot_remask_already_derived_geometry(self):
        ref = reference()
        raw, _ = build_geofabrik_polygons(features(), ref)
        derived, _ = build_nested_locality_masks(raw, ref)
        with self.assertRaises(ValueError):
            build_nested_locality_masks(derived, ref)


if __name__ == '__main__':
    unittest.main()
