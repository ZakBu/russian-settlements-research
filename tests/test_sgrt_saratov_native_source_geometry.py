import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from scripts.sgrt_saratov.native_source_geometry import load_profile,selected_way_row,extract,PROFILE_SHA256


class NativeSourceTests(unittest.TestCase):
    def test_original_v2_profile_is_pinned_and_ordered_geometry_refs_survive(self):
        row,reason=selected_way_row(9,[1,4,2,1],{'highway':'secondary'},1,'2020-01-01',load_profile())
        self.assertIsNone(reason)
        self.assertEqual(row['refs'],[1,4,2,1])
        self.assertEqual(row['source_profile_sha256'],PROFILE_SHA256)
        self.assertEqual(row['geometry_crs'],'EPSG:4326')

    def test_motorcar_denial_overrides_generic_permission(self):
        row,reason=selected_way_row(9,[1,2],{'highway':'secondary','motorcar':'no','access':'yes'},1,'2020',load_profile())
        self.assertIsNone(row)
        self.assertIn('deny',reason)

    def test_uncertain_literal_is_not_invented_as_public_access(self):
        row,reason=selected_way_row(9,[1,2],{'highway':'secondary','access':'residents'},1,'2020',load_profile())
        self.assertIsNone(row)
        self.assertIn('uncertain',reason)

    def test_reverse_oneway_is_retained_as_direction_not_coordinate_reordering(self):
        row,reason=selected_way_row(9,[1,3,2],{'highway':'secondary','oneway':'-1'},1,'2020',load_profile())
        self.assertIsNone(reason)
        self.assertEqual(row['oneway'],-1)
        self.assertEqual(row['refs'],[1,3,2])

    def test_two_source_passes_keep_an_intermediate_curve_node(self):
        import osmium
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pbf=root/'source.osm.pbf'
            with osmium.SimpleWriter(str(pbf)) as writer:
                for identity,xy in [(1,(46.,51.)),(2,(46.1,51.2)),(3,(46.2,51.)),(4,(46.3,51.))]:
                    writer.add_node(osmium.osm.mutable.Node(id=identity,location=xy,version=1))
                writer.add_way(osmium.osm.mutable.Way(id=10,nodes=[1,2,3],tags={'highway':'secondary'},version=1))
                writer.add_way(osmium.osm.mutable.Way(id=11,nodes=[3,4],tags={'highway':'secondary','access':'private'},version=1))
            needed=root/'needed.parquet';pd.DataFrame({'osm_id':[1,3]}).to_parquet(needed,index=False)
            with patch('scripts.sgrt_saratov.native_source_geometry.restore_pbf',return_value={'fixture_only':True}):
                result=extract(pbf,needed,root/'output')
            ways=pd.read_parquet(root/'output/ways.parquet');nodes=pd.read_parquet(root/'output/nodes.parquet').set_index('osm_id')
            self.assertEqual(ways.way_id.tolist(),[10])
            self.assertEqual(list(ways.iloc[0].refs),[1,2,3])
            self.assertEqual(set(nodes.index),{1,2,3})
            self.assertAlmostEqual(nodes.loc[2,'lat'],51.2)
            self.assertAlmostEqual(nodes.loc[2,'lon'],46.1)
            self.assertEqual(result['source_ways_with_missing_geometry'],0)
            self.assertEqual(result['selected_valid_profile_ways'],1)


if __name__=='__main__':unittest.main()
