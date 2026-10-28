import tempfile
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.sparse import csr_matrix
from scripts.sgrt_saratov.native_road_shapes import build_native_edges,spherical_lengths,suffix_piece


class NativeGeometryCounterexamples(unittest.TestCase):
    def test_partial_geometry_follows_the_bend_not_the_chord(self):
        xy=np.array([[0.,0.],[0.,10.],[10.,10.]])
        np.testing.assert_allclose(suffix_piece(xy,np.array([0.,10.,20.]),.5),[[0.,10.],[10.,10.]])
        np.testing.assert_allclose(suffix_piece(xy,np.array([0.,10.,20.]),.75),[[0.,5.],[0.,10.],[10.,10.]])

    def fixture(self,folder,include_fast=True):
        nodes=pd.DataFrame({'osm_id':[10,15,20],'lat':[51.5,51.52,51.5],'lon':[46.,46.005,46.01]})
        ways=pd.DataFrame({'way_id':[100,200],'refs':[[10,20],[10,15,20]],'speed_kmh':[60.,60.],'oneway':[0,0]})
        if not include_fast:ways=ways.iloc[[1]]
        nodepath=folder/'nodes.parquet';waypath=folder/'ways.parquet';nodes.to_parquet(nodepath,index=False);ways.to_parquet(waypath,index=False)
        weight=float(spherical_lengths(np.array([51.5,51.5]),np.array([46.,46.01])).sum())
        graph=csr_matrix(np.array([[0.,weight],[weight,0.]]))
        return waypath,nodepath,graph

    def test_slower_parallel_geometry_retains_its_own_time(self):
        with tempfile.TemporaryDirectory() as td:
            ways,nodes,graph=self.fixture(Path(td))
            records,table,facts=build_native_edges(ways,nodes,np.array([10,20]),graph,{1},
                Transformer.from_crs('EPSG:4326','EPSG:32638',always_xy=True))
            self.assertEqual(len(records),2)
            self.assertGreater(records[1]['w'],records[0]['w'])
            self.assertEqual(facts['slower_parallel_directed_segments_retained'],1)
            self.assertEqual(table.source_polyline_vertices.tolist(),[2,3])

    def test_missing_fast_parallel_source_does_not_silently_pass(self):
        with tempfile.TemporaryDirectory() as td:
            ways,nodes,graph=self.fixture(Path(td),include_fast=False)
            with self.assertRaisesRegex(ValueError,'does not reconstruct'):
                build_native_edges(ways,nodes,np.array([10,20]),graph,{1},
                    Transformer.from_crs('EPSG:4326','EPSG:32638',always_xy=True))


if __name__=='__main__':unittest.main()
