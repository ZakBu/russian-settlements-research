import unittest

import numpy as np
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
import shapely
from shapely.geometry import LineString, MultiLineString, Point

from scripts.sgrt_saratov.isochrones import partial_fraction, reachable_lines, inbound_arc_arrays, nested_geographies


class IsochroneCounterexamples(unittest.TestCase):
    def test_partial_inbound_edge_includes_destination_connector(self):
        # Road edge10min, node v needs8min including connector: only2/10 of edge.
        np.testing.assert_allclose(partial_fraction(10.,np.array([8.]),np.array([10.])),[.2])
        np.testing.assert_allclose(partial_fraction(10.,np.array([11.]),np.array([10.])),[0.])

    def test_zero_cost_edge_is_reachable_only_if_destination_is(self):
        np.testing.assert_allclose(partial_fraction(10.,np.array([9.,11.]),np.array([0.,0.])),[1.,0.])

    def test_direction_is_not_silently_symmetrized(self):
        graph=csr_matrix(np.array([[0.,3.],[30.,0.]]))
        arrival=dijkstra(graph.T.tocsr(),directed=True,indices=1)
        np.testing.assert_allclose(arrival,[3.,0.])
        u,v,w=inbound_arc_arrays(graph.T.tocsr(),arrival,10)
        self.assertEqual({(int(a),int(b),float(c)) for a,b,c in zip(u,v,w)}, {(0,1,3.),(1,0,30.)})

    def test_two_reachable_ends_do_not_imply_reachable_middle(self):
        u=np.array([0,1]);v=np.array([1,0]);w=np.array([10.,10.]);arrival=np.array([0.,0.])
        shape,stats=reachable_lines(u,v,w,arrival,np.array([0.,1000.]),np.zeros(2),2.,2)
        self.assertAlmostEqual(shape.length,400.)
        self.assertFalse(shape.buffer(.01).covers(Point(500.,0.)))
        self.assertEqual(stats['retained_partial_shapes'],2)

    def test_full_bidirectional_edge_is_not_counted_twice(self):
        shape,stats=reachable_lines(np.array([0,1]),np.array([1,0]),np.array([10.,10.]),
            np.zeros(2),np.array([0.,1000.]),np.zeros(2),20.,2)
        self.assertAlmostEqual(shape.length,1000.)
        self.assertEqual(stats['deduplicated_full_shapes'],1)

    def test_corridor_does_not_fill_an_unobserved_gap_like_convex_hull(self):
        forward=Transformer.from_crs('EPSG:32638','EPSG:4326',always_xy=True)
        roads=MultiLineString([[(400000,5500000),(401000,5500000)],[(406000,5500000),(407000,5500000)]])
        current,_,_=nested_geographies(roads,{},[100.,250.],20.,forward)
        gap=Point(*forward.transform(403500,5500000))
        self.assertFalse(current[250.].covers(gap))

    def test_delivered_bands_remain_disjoint_and_nested(self):
        forward=Transformer.from_crs('EPSG:32638','EPSG:4326',always_xy=True)
        a,_,_=nested_geographies(LineString([(400000,5500000),(401000,5500000)]),{},[100.,250.],20.,forward)
        b,bands,_=nested_geographies(LineString([(400000,5500000),(402000,5500000)]),a,[100.,250.],20.,forward)
        for width in [100.,250.]:
            self.assertLess(a[width].difference(b[width]).area,1e-16)
            self.assertLess(bands[width].intersection(a[width]).area,1e-16)


if __name__=='__main__':unittest.main()
