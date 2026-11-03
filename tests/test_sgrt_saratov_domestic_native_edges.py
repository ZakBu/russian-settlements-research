import unittest
import pandas as pd
import shapely
from shapely.geometry import box,LineString
from scripts.sgrt_saratov.domestic_native_edges import inside_directed_arcs

class DomesticNativeArcs(unittest.TestCase):
    def test_cheapest_foreign_curve_does_not_keep_old_minimum_or_remove_inside_alternative(self):
        native=pd.DataFrame([
            {'u':100,'v':200,'edge_minutes':1.,'oneway':0,'native_geometry_wkb':shapely.to_wkb(LineString([(0.1,0.1),(1.5,0.5),(0.9,0.9)]))},
            {'u':100,'v':200,'edge_minutes':7.,'oneway':0,'native_geometry_wkb':shapely.to_wkb(LineString([(0.1,0.1),(0.9,0.9)]))}])
        arcs=inside_directed_arcs(native,box(0,0,1,1))
        self.assertEqual(arcs[['u','v','edge_minutes']].to_dict('records'),[
            {'u':100,'v':200,'edge_minutes':7.},{'u':200,'v':100,'edge_minutes':7.}])

    def test_source_reverse_oneway_and_parallel_minimum_are_preserved(self):
        g=shapely.to_wkb(LineString([(0.1,0.1),(0.9,0.9)]))
        native=pd.DataFrame([
            {'u':100,'v':200,'edge_minutes':7.,'oneway':-1,'native_geometry_wkb':g},
            {'u':100,'v':200,'edge_minutes':5.,'oneway':-1,'native_geometry_wkb':g}])
        arcs=inside_directed_arcs(native,box(0,0,1,1))
        self.assertEqual(arcs.to_dict('records'),[{'u':200,'v':100,'edge_minutes':5.}])
