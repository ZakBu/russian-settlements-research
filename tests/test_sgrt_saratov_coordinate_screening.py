import unittest
import pandas as pd
from shapely.geometry import box
from scripts.sgrt_saratov.coordinate_screening import screen


class GeographicScreening(unittest.TestCase):
    def test_osm_type_cannot_resolve_census_homonyms(self):
        refs = pd.DataFrame([dict(source_record_id=str(i), name='Красный Октябрь', district='x',
                                  settlement_type_2021=t, lat=51., lon=47.)
                             for i, t in enumerate(['пгт', 'посёлок'])])
        places = pd.DataFrame([dict(osm_id='a', name='Красный Октябрь', fclass='village',
                                    geometry_wkb=box(46.99, 50.99, 47.01, 51.01).wkb)])
        table, summary = screen(refs, places, box(46., 50., 48., 52.))
        self.assertTrue(table.status.eq('name_ambiguous_or_absent').all())
        self.assertFalse(summary['automatic_coordinate_corrections'])

    def test_far_namesake_outside_region_is_not_a_coordinate_error(self):
        refs = pd.DataFrame([dict(source_record_id='1', name='А', district='x',
                                  settlement_type_2021='село', lat=51., lon=47.)])
        places = pd.DataFrame([dict(osm_id='a', name='А', fclass='village',
                                    geometry_wkb=box(49., 51., 49.1, 51.1).wkb)])
        table, summary = screen(refs, places, box(46., 50., 48., 52.))
        self.assertEqual(table.status.iloc[0], 'name_ambiguous_or_absent')
        self.assertEqual(summary['osm_named_polygons_in_region'], 0)

    def test_identical_cross_shard_geometry_is_one_osm_candidate(self):
        refs = pd.DataFrame([dict(source_record_id='1', name='А', district='x',
                                  settlement_type_2021='село', lat=51., lon=47.)])
        place = dict(osm_id='a', name='А', fclass='village',
                     geometry_wkb=box(46.99, 50.99, 47.01, 51.01).wkb)
        table, summary = screen(refs, pd.DataFrame([place, place]), box(46., 50., 48., 52.))
        self.assertEqual(table.status.iloc[0], 'within_5km_of_named_polygon')
        self.assertEqual(summary['identical_cross_shard_extract_rows_deduplicated'], 1)


if __name__ == '__main__': unittest.main()
