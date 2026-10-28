import json
from pathlib import Path
import tempfile
import unittest
from scripts.sgrt_saratov.rural_route_diagnostics import path_heap,read_table,verify_excerpt

class RuralRouteDiagnostics(unittest.TestCase):
    def test_heap_does_not_reverse_oneway_route(self):
        from scipy.sparse import csr_matrix
        graph=csr_matrix(([3.,4.,20.],([0,1,2],[1,2,0])),shape=(3,3))
        self.assertEqual(path_heap(graph,0,2)[:2],(7.,[0,1,2]))
        self.assertEqual(path_heap(graph,2,0)[:2],(20.,[2,0]))

    def test_source_JSON_preserves_node_ID_and_coordinate_bits(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'nodes.json';value=47.123456789012344
            path.write_text(json.dumps({'columns':['osm_id','lon'],'records':[{'osm_id':1234567890123456,'lon':value}]}))
            row=read_table(path).iloc[0]
            self.assertEqual(int(read_table(path).osm_id.iloc[0]),1234567890123456)
            self.assertEqual(float(row.lon).hex(),value.hex())

    def test_committed_source_excerpt_fingerprints_and_sizes(self):
        directory=Path(__file__).resolve().parents[1]/'references/primary/saratov_rural_roads_2021'
        verify_excerpt(directory)
        self.assertEqual(len(read_table(directory/'graph_vertex_subset.json')),77)
        self.assertEqual(len(read_table(directory/'ways.json')),78)
        self.assertEqual(len(read_table(directory/'nodes.json')),2397)

if __name__=='__main__':unittest.main()
