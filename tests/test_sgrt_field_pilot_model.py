"""Scientific counterexamples for sampled road potentials and maxima."""
import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sgrt_field_pilot.field_model import (kernel, field_from_costs,
                                        neighbor_edges, plateau_peaks, prepare_sources)


class FieldModelTests(unittest.TestCase):
    def test_half_time_and_zero_are_comparable_and_finite(self):
        for family in ['exponential', 'gaussian']:
            np.testing.assert_allclose(kernel([0, 20, np.inf, np.nan], 20, family)[:3], [1, .5, 0])
            self.assertTrue(np.isnan(kernel([np.nan], 20, family)[0]))
        with self.assertRaises(ValueError): kernel([1], 0)
        with self.assertRaises(ValueError): kernel([-1], 2)

    def test_self_and_unknown_are_different_objects(self):
        c = np.array([[0., 10., np.nan, np.inf], [20., 0., 10., 30.]])
        p = np.array([100., 10., 5., 7.])
        included, count, mass = field_from_costs(c, p, 10)
        excluded, _, _ = field_from_costs(c, p, 10, own_source_indices=[0, 1], include_self=False)
        self.assertAlmostEqual(included[0], 105)
        self.assertEqual(count[0], 1)
        self.assertEqual(mass[0], 5)
        np.testing.assert_allclose(included - excluded, [100, 10])
        # Directed 10 vs20 costs are retained, not averaged to15.
        self.assertAlmostEqual(included[1], 25 + 10 + 2.5 + 7/8)

    def test_plateau_is_one_peak_with_stable_identity(self):
        ids = np.array(['b', 'a', 'c'])
        out = plateau_peaks([5, 5, 1], [(0,1), (1,2)], ids).set_index('source_record_id')
        self.assertEqual(out.loc['a', 'plateau_id'], 'a')
        self.assertEqual(out.loc['b', 'plateau_id'], 'a')
        self.assertEqual(out.loc['a', 'plateau_size'], 2)
        self.assertTrue(out.loc['a', 'is_sampled_local_maximum'])
        self.assertFalse(out.loc['c', 'is_sampled_local_maximum'])
        self.assertTrue(plateau_peaks([1], [], ['x']).comparison_isolated.iloc[0])
        self.assertFalse(plateau_peaks([1], [], ['x']).is_sampled_local_maximum.iloc[0])

    def test_tolerance_chains_are_explicit(self):
        out = plateau_peaks([0, .9, 1.8], [(0,1), (1,2)], ['a','b','c'], atol=1, rtol=0)
        self.assertTrue(out.tolerance_chain_span_exceeds_tolerance.all())

    def test_knn_ties_and_permutations_do_not_select_random_neighbor(self):
        c = np.array([[0, 2, 2], [2, 0, 5], [2, 5, 0]], dtype=float)
        ids = np.array(['a','b','c'])
        e, _, _ = neighbor_edges(c, ids, k=1)
        self.assertEqual(set(e), {(0,1),(0,2)})
        p = [2,0,1]
        e2, _, _ = neighbor_edges(c[np.ix_(p,p)], ids[p], k=1)
        before = {tuple(sorted((ids[a],ids[b]))) for a,b in e}
        after = {tuple(sorted((ids[p][a],ids[p][b]))) for a,b in e2}
        self.assertEqual(before, after)

    def test_uncredited_and_city_context_cannot_create_mass(self):
        f = pd.DataFrame({'source_record_id':['a','b','city_context',None,None],
                          'population_2021':[100,70,1000,8,9],
                          'credit_2021':[True,False,True,False,False],
                          'budget_population_credit':[True,False,False,False,False],
                          'ordinary_spatial_2021':[True,True,False,False,False]})
        e = pd.DataFrame({'source_record_id':['a','b','city_context'],
                          'road_endpoint_accepted':[True]*3,
                          'road_node_index':[0,1,2], 'snap_km':[0.,0.,0.]})
        s = prepare_sources(f,e)
        self.assertEqual(s.source_mass_2021.sum(), 100)
        self.assertTrue(s.loc[s.source_record_id.eq('b'),'source_mass_2021'].isna().all())

    def test_valid_metric_can_create_new_peak_at_larger_scale(self):
        # A fixed symmetric weighted tree, not a nonmetric hand-made matrix.
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import shortest_path
        edges = [(1,0,6),(2,0,7),(3,2,8),(4,0,5),(5,4,1)]
        a = np.zeros((6,6))
        for i,j,t in edges: a[i,j] = a[j,i] = t
        c = shortest_path(csr_matrix(a), directed=False)
        p = [52,36,58,75,34,17]
        neighbor = [(i,j) for i,j,_ in edges]
        counts = []
        for h in [2,4,8]:
            v,_,_ = field_from_costs(c,p,h*np.log(2))  # exp(-c/h)
            peaks = plateau_peaks(v, neighbor, [str(i) for i in range(6)])
            counts.append(int(peaks.is_sampled_local_maximum.sum()))
        self.assertEqual(counts, [1,2,1])


if __name__ == '__main__':
    unittest.main()
