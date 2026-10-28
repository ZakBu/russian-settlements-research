"""Publication must not conceal missing transport costs or swapped axes."""
from pathlib import Path
import tempfile
import json
import unittest
import numpy as np
from scipy.sparse import csr_matrix,save_npz
from scripts.sgrt_saratov.cloud_regional_research import array_control,matrix_control,relative_path,summary_control,geojson_control

class PublicationTransportSemantics(unittest.TestCase):
    def test_dense_unknown_is_not_zero_and_axis_order_is_not_discarded(self):
        a=np.array([[0.,np.nan],[17.,0.]])
        b=np.nan_to_num(a)
        self.assertNotEqual(array_control(a),array_control(b))
        self.assertNotEqual(array_control(a),array_control(a.T))
        self.assertEqual(array_control(a),array_control(a.astype('>f8')))

    def test_sparse_absence_cannot_replace_an_explicit_self_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=csr_matrix(([0.,12.],([0,0],[0,1])),shape=(2,2))
            b=csr_matrix(([12.],([0],[1])),shape=(2,2))
            save_npz(root/'a.npz',a);save_npz(root/'b.npz',b)
            self.assertNotEqual(matrix_control(root/'a.npz'),matrix_control(root/'b.npz'))
            self.assertEqual(matrix_control(root/'a.npz')['explicit_zero_entries'],1)

    def test_input_archive_cannot_write_outside_its_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('../outside','/tmp/outside','water/../../outside'):
                with self.subTest(name=name),self.assertRaises(ValueError):relative_path(root,name)
            self.assertEqual(relative_path(root,'water/mask.geojson'),root/'water/mask.geojson')

    def test_topologically_valid_but_empty_map_polygon_is_not_publishable(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'empty.geojson'
            p.write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature',
                'properties':{'id':'outside-map'},'geometry':{'type':'Polygon','coordinates':[]}}]}))
            with self.assertRaisesRegex(ValueError,'Empty delivered geometry'):geojson_control(p)

    def test_runtime_changes_do_not_hide_changes_in_scientific_scope(self):
        a={'computed_regional_origins':1814,'elapsed_regional_and_halo_seconds':99.,'horizon_minutes':480.}
        b={**a,'elapsed_regional_and_halo_seconds':250.}
        self.assertEqual(summary_control(a),summary_control(b))
        self.assertNotEqual(summary_control(a),summary_control({**b,'horizon_minutes':600.}))

if __name__=='__main__':unittest.main()
