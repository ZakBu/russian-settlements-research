import unittest
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scripts.sgrt_saratov.forward_column_canonicalization import forward_columns


class ForwardColumnCanonicalizationTests(unittest.TestCase):
    def fixture(self):
        graph=csr_matrix(([100.1,200.2,300.3,1000.],([0,1,2,3],[1,2,3,0])),shape=(4,4))
        origins=pd.DataFrame({'source_record_id':['a','b','unknown'],'road_node_index':[0.,3.,np.nan],
            'snap_km':[0.,0.,np.nan],'accepted_source_endpoint':[True,True,False]})
        destinations=pd.DataFrame({'source_record_id':['a','b'],'road_node_index':[0,3],
            'destination_connector_minutes':[0.,0.]})
        cached=np.array([[0.,dijkstra(graph,directed=True,indices=0)[3]+1e-12],[1000.,0.],[np.nan,np.nan]])
        matrix=csr_matrix((np.array([0.,0.]),(np.array([0,1]),np.array([0,1]))),shape=(3,2))
        return graph,origins,destinations,cached,matrix

    def test_beyond_prefix_forward_bits_and_unknown_rows(self):
        graph,origins,dest,cached,matrix=self.fixture()
        original=cached.copy()
        columns,proof=forward_columns(graph,origins,dest,cached,[(matrix,0)],[1],[0,1])
        self.assertEqual(proof['full_forward_extra_rows'],[0])
        self.assertEqual(columns[1][0],dijkstra(graph,directed=True,indices=0)[3])
        self.assertEqual(columns[1][1],0.)
        self.assertTrue(np.isnan(columns[1][2]))
        np.testing.assert_array_equal(cached,original)

    def test_unrelated_forward_prefix_bit_changes_are_rejected(self):
        graph,origins,dest,cached,matrix=self.fixture()
        bad=matrix.copy();bad[0,0]=1.
        with self.assertRaisesRegex(ValueError,'control vector'):
            forward_columns(graph,origins,dest,cached,[(bad,0)],[1],[0,1])

    def test_actual_distance_disagreement_is_not_hidden_as_roundoff(self):
        graph,origins,dest,cached,matrix=self.fixture();cached[0,1]+=1.
        with self.assertRaisesRegex(ValueError,'distances disagree'):
            forward_columns(graph,origins,dest,cached,[(matrix,0)],[1],[0,1])


if __name__=='__main__':unittest.main()
