"""Exact guard/index/schema equivalence, not a relaxed spatial assignment."""
import json
from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd
from shapely.geometry import box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sgrt_zero.cartographic_identity import assign_cartographic_identity as slow, ACCEPTED
from scripts.sgrt_zero.cartographic_identity_fast import assign_cartographic_identity as fast


def polygon(sid='a', bounds=(0, 0, 2, 2), **changes):
    row = {'source_record_id': sid, 'name': sid.upper(), 'region': 'тестовая',
           'name_aliases_json': json.dumps([sid]), 'geometry_wkb': box(*bounds).wkb,
           'polygon_identity_status': ACCEPTED, 'other_positive_census_places': 0,
           'source_dataset': 'geofabrik_places_a', 'source_feature_id': 'osm-' + sid,
           'source_snapshot': '2026-10-26', 'wof_id': None}
    row.update(changes)
    return row


class CartographicFastTests(unittest.TestCase):
    def test_full_activity_address_is_not_lost_in_fast_row_projection(self):
        sites = pd.DataFrame({'site_lat':[1.], 'site_lon':[1.], 'source_record_id':[None],
                              'tags_json':[None], 'activity_address':['село Родниково, Бахчисарайская Улица 9']})
        result = self.equivalent(sites, pd.DataFrame([polygon()]))
        self.assertFalse(result.cartographic_identity_accepted.iloc[0])
        self.assertEqual(result.cartographic_identity_status.iloc[0], 'held_literal_locality_conflict')

    def equivalent(self, sites, polygons):
        left = slow(sites, polygons)
        right = fast(sites, polygons)
        pd.testing.assert_frame_equal(left, right, check_exact=True)
        return right

    def test_sparse_string_index_raw_owner_invalid_coordinates_and_literal_conflicts(self):
        sites = pd.DataFrame({'site_lat': [1., 1., 1., np.nan, 91., 1.],
                              'site_lon': [1., 1., 1., 1., 1., 1.],
                              'source_record_id': [None, 'b', None, None, None, 'a'],
                              'tags_json': ['{}', '{}', '{"addr:city":"b"}', '{}', '{}', '{}'],
                              'source_address_state': [None] * 6,
                              'raw_column': ['keep'] * 6},
                             index=pd.Index(['q', 'w', 'e', 'r', 't', 'y'], name='raw-row'))
        result = self.equivalent(sites, pd.DataFrame([polygon()]))
        self.assertEqual(result.loc['w', 'cartographic_identity_status'], 'held_existing_source_owner_conflict')
        self.assertEqual(result.loc['e', 'cartographic_identity_status'], 'held_literal_locality_conflict')
        self.assertEqual(result.loc['r', 'cartographic_identity_status'], 'invalid_source_coordinates')
        self.assertEqual(result.loc['w', 'source_record_id'], 'b')

    def test_overlapping_different_owners_and_unresolved_primary_are_not_bypassed(self):
        sites = pd.DataFrame({'site_lat': [1.], 'site_lon': [1.], 'source_record_id': [None]})
        result = self.equivalent(sites, pd.DataFrame([polygon(), polygon('b')]))
        self.assertEqual(result.cartographic_identity_status.iloc[0], 'held_overlapping_different_census_localities')
        result = self.equivalent(sites, pd.DataFrame([polygon(), polygon('b', polygon_identity_status='held_name_unknown')]))
        self.assertEqual(result.cartographic_identity_status.iloc[0], 'held_unresolved_primary_geometry')

    def test_multiple_independent_nps_are_held_even_when_postal_city_agrees(self):
        sites = pd.DataFrame({'site_lat': [1.], 'site_lon': [1.], 'tags_json': ['{"addr:city":"a"}']})
        result = self.equivalent(sites, pd.DataFrame([polygon(other_positive_census_places=2)]))
        self.assertFalse(result.cartographic_identity_accepted.iloc[0])
        self.assertEqual(result.cartographic_identity_status.iloc[0], 'held_finer_census_places_inside_cartographic_polygon')

    def test_boundary_is_held_and_same_owner_duplicate_metadata_keeps_query_order(self):
        sites = pd.DataFrame({'site_lat': [0., 1.], 'site_lon': [1., 1.]})
        first = polygon(source_feature_id='first', source_snapshot=None)
        second = polygon(source_feature_id='second', geometry_wkb=None,
                         geometry_json=json.dumps(mapping(box(0, 0, 2, 2))),
                         source_dataset='whosonfirst_locality', wof_id=123)
        result = self.equivalent(sites, pd.DataFrame([first, second]))
        self.assertEqual(result.cartographic_identity_status.iloc[0], 'held_point_on_cartographic_boundary')
        self.assertEqual(result.cartographic_polygon_matches.iloc[1], 2)

    def test_empty_and_previous_diagnostic_columns_have_identical_dtypes(self):
        sites = pd.DataFrame({'site_lat': [1.], 'site_lon': [1.],
                              'cartographic_polygon_matches': pd.Series([4], dtype='Int64'),
                              'cartographic_candidate_source_record_id': ['old']})
        self.equivalent(sites, pd.DataFrame())
        self.equivalent(sites.iloc[:0], pd.DataFrame([polygon()]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            fast(pd.concat([sites, sites]), pd.DataFrame([polygon()]))


if __name__ == '__main__':
    unittest.main()
