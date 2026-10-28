import math
import unittest

from scripts.sgrt_saratov.regional_independent_checks import (
    actual_field_checks, all_pairs_relaxation, connected_cost, counterexamples, direct_members, ellipsoid_area_upper,
    forward_union_fixture, heap_nearest_terminal, heap_shortest, kernel_scalar, nearest_compatible,
    scalar_fields, sparse_known_cost,
)


class RegionalIndependentOracles(unittest.TestCase):
    def test_union_keeps_route_through_external_node(self):
        rows = forward_union_fixture(4, [(0, 1, 3), (1, 2, 3), (0, 2, 100), (2, 3, 3)], [0], 6)
        self.assertEqual(rows["retained_nodes"], [0, 1, 2])
        self.assertIn((0, 2, 6., 6.), rows["pairs_within_horizon_compared"])

    def test_forward_union_is_not_reverse_union(self):
        example = counterexamples()
        self.assertEqual(example["reverse_union_would_retain_only"], [0])
        self.assertNotEqual(example["forward_union_keeps_external_intermediate_vertex"]["retained_nodes"], [0])

    def test_sparse_unknown_does_not_become_free_transport(self):
        self.assertIsNone(sparse_known_cost([0], [0.], 1))
        self.assertEqual(sparse_known_cost([0], [0.], 0), 0.)

    def test_connectors_are_added_before_budget_classification(self):
        self.assertEqual(connected_cost(479., 1., 1.), 481.)
        self.assertIsNone(connected_cost(None, 0., 0.))
        self.assertEqual(connected_cost(99., 1., 1., same_record=True), 0.)

    def test_half_times_are_comparable_and_zero_is_finite(self):
        for family in ("exponential", "gaussian"):
            self.assertEqual(kernel_scalar(0., 20., family), 1.)
            self.assertEqual(kernel_scalar(20., 20., family), .5)
            self.assertEqual(kernel_scalar(math.inf, 20., family), 0.)
        self.assertIsNone(kernel_scalar(None, 20, "exponential"))

    def test_original_mass_not_credited_twice(self):
        row = scalar_fields({0: 0., 1: 10.}, [10., 20.], 10., "exponential", self_index=0)
        self.assertEqual(row["with_self"], 20.)
        self.assertEqual(row["without_self"], 10.)
        self.assertEqual(row["self_contribution"], 10.)

    def test_known_tail_is_not_dropped_or_added_as_observed_mass(self):
        row = scalar_fields({0: 0.}, [10., 20.], 10., "exponential", self_index=0, horizon=10.)
        self.assertEqual(row["with_self"], 10.)
        self.assertEqual(row["routable_tail_upper"], 10.)
        tighter = scalar_fields({0: 0.}, [10., 20.], 10., "exponential", self_index=0,
                               horizon=10., travel_lower_bounds=[0., 20.])
        self.assertEqual(tighter["routable_tail_upper"], 5.)
        with self.assertRaises(ValueError):
            scalar_fields({0: 0.}, [10., None], 10, "exponential")

    def test_nearest_basic_provider_is_not_population_competition(self):
        row = nearest_compatible({"small": 4., "million_city": 50.}, {"small", "million_city"})
        self.assertEqual(row["primary"], "small")
        own = nearest_compatible({"million_city": 3.}, {"own", "million_city"}, own_site="own")
        self.assertEqual(own["primary"], "own")

    def test_ties_are_retained_and_unknown_is_not_a_provider(self):
        row = nearest_compatible({"a": 4., "b": 4., "c": None}, {"a", "b", "c"})
        self.assertEqual(row["tied"], ["a", "b"])
        self.assertIsNone(nearest_compatible({"c": None}, {"c"})["primary"])

    def test_transitive_chain_cannot_expand_direct_radius(self):
        self.assertEqual(direct_members([0, 3, 6, 9], 5), [0, 1])

    def test_geographic_sliver_area_bound_does_not_reproject_vertices(self):
        from shapely.geometry import Polygon,box
        self.assertEqual(ellipsoid_area_upper(Polygon()),0.)
        # This linear geographic triangle is minuscule, irrespective of the
        # curvature introduced by joining reprojected endpoints.
        sliver=Polygon([(45.,50.),(46.,51.),(45.5,50.50000000000001)])
        self.assertLess(ellipsoid_area_upper(sliver),1.)
        self.assertGreater(ellipsoid_area_upper(box(45.,50.,45.01,50.01)),100000.)

    def test_terminal_connector_changes_nearest_provider(self):
        from scipy.sparse import csr_matrix
        graph=csr_matrix(([3.,10.],([0,0],[1,2])),shape=(3,3))
        value,winners,_=heap_nearest_terminal(graph,0,{1:20.,2:0.})
        self.assertEqual(value,10.)
        self.assertEqual(winners,{2})
        self.assertEqual(heap_nearest_terminal(graph,1,{1:20.,2:0.})[:2],(20.,{1}))
        with self.assertRaises(ValueError):heap_nearest_terminal(graph,0,{1:-1.})

    def test_original_direction_heap(self):
        from scipy.sparse import csr_matrix
        graph = csr_matrix(([3., 3., 10.], ([0, 1, 2], [1, 2, 0])), shape=(4, 4))
        self.assertEqual(heap_shortest(graph, 0, 2)[0], 6.)
        self.assertEqual(heap_shortest(graph, 2, 0)[0], 10.)
        self.assertTrue(math.isinf(heap_shortest(graph, 0, 2, maximum=5)[0]))
        self.assertTrue(math.isinf(heap_shortest(graph, 0, 3)[0]))

    def test_invalid_costs_and_horizons_rejected(self):
        with self.assertRaises(ValueError):
            all_pairs_relaxation(2, [(0, 1, -1)])
        with self.assertRaises(ValueError):
            forward_union_fixture(2, [(0, 1, 1)], [], 5)
        with self.assertRaises(ValueError):
            kernel_scalar(10., 0., "exponential")


class ActualOutputContracts(unittest.TestCase):
    def fixture(self, folder):
        import numpy as np
        import pandas as pd
        from scipy.sparse import csr_matrix,save_npz
        roster=pd.DataFrame({'row_index':[0,1,2],'source_record_id':['a','b','unknown'],
            'accepted_source_endpoint':[True,True,False],'source_mass_2021':[10.,20.,5.],
            'positive_source_mass':[True,True,True]})
        roster.to_parquet(folder/'regional_roster.parquet')
        pd.DataFrame({'destination_index':[0,1],'source_record_id':['a','b'],
            'ordinary_spatial_2021':[True,True],'source_mass_2021':[10.,20.],
            'positive_source_mass':[True,True]}).to_parquet(folder/'destinations.parquet')
        save_npz(folder/'destination_costs.npz',csr_matrix(([0.,10.,20.,0.],([0,0,1,1],[0,1,0,1])),shape=(3,2)))
        np.save(folder/'regional_costs.npy',np.array([[0.,10.,np.nan],[20.,0.,np.nan],[np.nan,np.nan,np.nan]]))
        pd.DataFrame({'origin_id':['a','b'],'destination_id':['b','a'],'minutes':[10.,20.],
            'rank':[1,1],'in_k3':[True,True],'in_k6':[True,True]}).to_parquet(folder/'national_neighbors.parquet')
        rows=[]
        for sid,mass,total in [('a',10.,20.),('b',20.,22.5),('unknown',5.,float('nan'))]:
            for own in (False,True):
                value=total-(0. if own else mass)
                rows.append({'source_record_id':sid,'kernel':'exponential','half_time':10.,
                    'include_self':own,'value':value,'tail_upper':0.,'unmapped_mass_upper':5.,
                    'unmapped_mass_upper_without_distance_assumption':5.,'accepted_mass_field_upper':value+5.,
                    'status':'origin_endpoint_unavailable' if sid=='unknown' else 'computed_to_horizon'})
        pd.DataFrame(rows).to_parquet(folder/'fields.parquet')

    def test_directed_matrix_and_unknown_origin_remain_distinct(self):
        import tempfile
        from pathlib import Path
        import numpy as np
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);self.fixture(folder)
            self.assertEqual(actual_field_checks(folder)['violations'],0)
            matrix=np.load(folder/'regional_costs.npy');matrix[0,1]=20.;matrix[1,0]=10.
            np.save(folder/'regional_costs.npy',matrix)
            report=actual_field_checks(folder)
            self.assertEqual(report['violations'],2)
            self.assertTrue(all('not a CSR subset' in x for x in report['errors']))

    def test_unavailable_origin_zero_is_rejected(self):
        import tempfile
        from pathlib import Path
        import pandas as pd
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);self.fixture(folder)
            fields=pd.read_parquet(folder/'fields.parquet')
            fields.loc[fields.source_record_id.eq('unknown'),'value']=0.
            fields.to_parquet(folder/'fields.parquet')
            report=actual_field_checks(folder)
            self.assertGreaterEqual(report['violations'],1)
            self.assertTrue(any('Unknown field appears numeric' in x for x in report['errors']))


if __name__ == "__main__":
    unittest.main()
