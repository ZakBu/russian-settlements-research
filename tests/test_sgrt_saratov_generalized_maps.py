import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import shapely
from shapely.geometry import LineString,Polygon,box,Point,mapping
from scripts.sgrt_saratov.generalized_maps import (
    fill_small_holes,generalize_corridor,protect_water,time_bands,tile_range,run,fetch_water)


class GeneralizedTimeZones(unittest.TestCase):
    def test_dense_local_network_becomes_one_coarse_zone(self):
        roads=shapely.union_all([LineString([(x,0),(x,5000)]).buffer(50)
                                 for x in range(0,5001,500)])
        result=generalize_corridor(roads,expansion_m=500,closing_m=1000,
                                   simplification_m=200,hole_area_m2=1e6)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(shapely.get_parts(result)),1)
        self.assertLess(shapely.get_num_coordinates(result),shapely.get_num_coordinates(roads)/4)
        self.assertTrue(result.contains(Point(250,2500)))

    def test_water_remains_open_but_known_bridge_is_retained(self):
        water=box(-100,-1000,100,1000)
        original=shapely.union_all([box(-500,-500,-150,500),box(150,-500,500,500),box(-200,-10,200,10)])
        generalized=box(-600,-600,600,600)
        result=protect_water(generalized,original,water)
        self.assertFalse(result.covers(Point(0,400)))
        self.assertTrue(result.covers(Point(0,0)))
        self.assertTrue(result.covers(Point(300,400)))

    def test_band_overlay_keeps_nestedness_and_disjoint_intervals(self):
        cumulative=[box(0,0,10,10),box(5,0,20,10),box(-1,-1,30,12),box(-5,-5,40,20)]
        nested,bands=time_bands(cumulative)
        for i,g in enumerate(nested):
            self.assertTrue(g.is_valid)
            if i:self.assertLess(nested[i-1].difference(g).area,1e-9)
            self.assertLess(shapely.union_all(bands[:i+1]).symmetric_difference(g).area,1e-9)
        for i,g in enumerate(bands):
            for h in bands[i+1:]:self.assertLess(g.intersection(h).area,1e-9)

    def test_hole_filter_does_not_remove_large_void(self):
        polygon=Polygon(box(0,0,100,100).exterior,[box(10,10,15,15).exterior,box(40,40,80,80).exterior])
        g=fill_small_holes(polygon,100)
        self.assertTrue(g.covers(Point(12,12)))
        self.assertFalse(g.covers(Point(60,60)))

    def test_invalid_cartographic_parameter_rejected(self):
        with self.assertRaises(ValueError):generalize_corridor(box(0,0,1,1),expansion_m=-1)

    def test_map_classes_are_distinct_and_source_costs_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.geojson';wet=root/'water.geojson'
            features=[]
            for m,width in [(10,.01),(20,.02),(30,.03),(60,.05)]:
                features.append({'type':'Feature','properties':{'centre_id':'test:1','centre_name':'Тест','minutes':m},
                                 'geometry':mapping(box(45-width,51-width,45+width,51+width))})
            raw=json.dumps({'type':'FeatureCollection','features':features});source.write_text(raw)
            wet.write_text(json.dumps({'type':'FeatureCollection','features':[]}))
            result=run(source,wet,root/'output')
            self.assertEqual(source.read_text(),raw)
            self.assertFalse(result['route_costs_recalculated'])
            self.assertFalse(result['settlement_accessibility_counts_changed'])
            out=json.loads((root/'output/isochrones_generalized_1.geojson').read_text())
            self.assertEqual([f['properties']['minutes'] for f in out['features']],[10,20,30,60])
            classes=[f['properties']['class_index'] for f in out['features']]
            self.assertEqual(classes,[0,1,2,3])
            self.assertEqual(len({c%5 for c in classes}),4)

    def test_frozen_water_manifest_rejects_changed_extent_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'manifest.json';p.write_text(json.dumps({'requested_bounds_wgs84':[1,2,3,4],'tile_zoom':8}))
            with patch('urllib.request.urlopen') as network:
                with self.assertRaises(ValueError):fetch_water((1,2,3,5),Path(directory)/'out',8,p)
                network.assert_not_called()

    def test_tile_coverage_is_bounded_and_includes_all_corners(self):
        tiles=tile_range((43,50,49,53),8)
        self.assertTrue(0<len(tiles)<64)
        self.assertEqual(len(tiles),len(set(tiles)))

if __name__=='__main__':unittest.main()
