import unittest
import shapely
from shapely.geometry import box, mapping, shape
from scripts.sgrt_saratov.country_scope import clip


class CountryScope(unittest.TestCase):
    def test_nested_bands_remain_inside_country_without_becoming_service_areas(self):
        mask=box(47,49,48,51)
        bands=[box(47.2,49.5,47.5,50),box(47.5,49.5,48.5,50)]
        doc={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'id':str(i),'minutes':10*(i+1)},'geometry':mapping(g)} for i,g in enumerate(bands)]}
        result,diag=clip(doc,mask)
        geos=[shape(f['geometry']) for f in result['features']]
        self.assertEqual(len(geos),2)
        self.assertTrue(all(mask.covers(g) for g in geos))
        self.assertEqual(geos[0].intersection(geos[1]).area,0)
        self.assertGreater(diag[1]['removed_display_area_km2'],0)
        self.assertFalse(result['features'][0]['properties']['foreign_transit_in_original_costs_verified'])
        self.assertEqual(result['features'][1]['properties']['minutes'],20)

    def test_entirely_foreign_feature_is_removed(self):
        doc={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'id':'foreign'},'geometry':mapping(box(48.1,49,49,50))}]}
        result,diag=clip(doc,box(47,49,48,51))
        self.assertEqual(result['features'],[])
        self.assertTrue(diag[0]['empty_after_clip'])
