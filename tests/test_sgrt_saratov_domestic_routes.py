import unittest
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box,LineString,Polygon
from scipy.sparse.csgraph import dijkstra
from scripts.sgrt_saratov.domestic_native_edges import inside_directed_arcs
from scripts.sgrt_saratov.domestic_routes import sparse_graph,domestic_status,connector_allowed,route_evidence


class CertifiedDomesticRoutes(unittest.TestCase):
    def test_outside_time_window_detour_is_not_reported_as_isolation_or_exact_minimum(self):
        coordinates={i:(.1+.1*i,.1+.1*i) for i in range(5)}
        edges=[(1,0,20,False),(2,1,5,True),(2,1,20,False),
               (2,3,1,False),(3,4,1,False),(4,1,14,False)]
        native=pd.DataFrame([{'u':u,'v':v,'edge_minutes':float(w),'oneway':1,
            'native_geometry_wkb':shapely.to_wkb(LineString([coordinates[u],(1.5,.5),coordinates[v]]
                if foreign else [coordinates[u],coordinates[v]]))} for u,v,w,foreign in edges])
        axis=np.arange(5);mask=box(0,0,1,1)
        before=sparse_graph(inside_directed_arcs(native,box(-1,-1,2,2)),axis)
        to_anchor=dijkstra(before.T.tocsr(),directed=True,indices=0)
        needed=set(axis[to_anchor<=30])
        self.assertEqual(needed,{0,1,2})
        window=native[native.u.isin(needed)|native.v.isin(needed)]
        full_domestic=sparse_graph(inside_directed_arcs(native,mask),axis)
        partial_domestic=sparse_graph(inside_directed_arcs(window,mask),axis)
        actual=dijkstra(full_domestic.T.tocsr(),directed=True,indices=1)[2]
        bound=dijkstra(partial_domestic.T.tocsr(),directed=True,indices=1)[2]
        self.assertEqual(actual,16.)
        self.assertEqual(bound,20.)
        horizon=30-to_anchor[1]
        self.assertEqual(horizon,10.)
        self.assertEqual(domestic_status(bound,horizon),'no_domestic_path_within_certificate')
        self.assertGreater(actual,horizon)
        self.assertNotEqual(bound,actual)  # The available path is only an upper bound.
        self.assertEqual(route_evidence(bound,5.,horizon),'no_domestic_path_within_certificate')
        # An available domestic path meeting the global lower bound proves
        # optimality even when the sufficient time-window condition is absent.
        self.assertEqual(route_evidence(16.,16.,None),'exact_domestic_cost_by_matching_lower_bound')
        self.assertEqual(route_evidence(20.,16.,None),'feasible_domestic_path_upper_bound_only')
        self.assertEqual(route_evidence(np.inf,16.,None),'not_resolved_by_available_native_graph')
        with self.assertRaises(ValueError):route_evidence(15.,16.,None)

    def test_a_connector_with_domestic_endpoints_can_still_cross_excluded_land(self):
        mask=Polygon(box(0,0,1,1).exterior,[box(.4,.4,.6,.6).exterior])
        self.assertFalse(connector_allowed(.1,.5,(.9,.5),mask))
        self.assertTrue(connector_allowed(.1,.1,(.9,.1),mask))

    def test_exact_cost_at_recorded_certificate_boundary_is_admitted(self):
        self.assertEqual(domestic_status(10.,10.),'exact_domestic_cost_within_certificate')
        self.assertEqual(domestic_status(10.,10.,False),'endpoint_or_connector_country_scope_unresolved')
