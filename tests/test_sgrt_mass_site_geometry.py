import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

MODULE=Path(__file__).resolve().parents[1]/'scripts/sgrt_mass/site_geometry.py'
spec=importlib.util.spec_from_file_location('site_geometry',MODULE)
geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)


class SiteGeometryTests(unittest.TestCase):
    def roads(self,coordinates,osm=None):
        return pd.DataFrame({'node_index':range(len(coordinates)),
                             'osm_id':osm or list(range(100,100+len(coordinates))),
                             'lat':[p[0] for p in coordinates],
                             'lon':[p[1] for p in coordinates],
                             'weak_component':[2]*len(coordinates)})

    def points(self,coordinates):
        return pd.DataFrame({'site_lat':[p[0] for p in coordinates],
                             'site_lon':[p[1] for p in coordinates],
                             'source_record_id':[None]*len(coordinates)})

    def test_dateline_uses_sphere_not_longitude_difference(self):
        roads=self.roads([(0,-179.9),(0,179.)])
        out=geometry.snap_points(self.points([(0,179.95)]),roads,max_snap_km=100)
        self.assertEqual(out.road_node_index.iloc[0],0)
        self.assertAlmostEqual(out.snap_km.iloc[0],16.679262035,places=5)

    def test_high_latitude_uses_true_distance(self):
        roads=self.roads([(89,10),(88.9,0)])
        out=geometry.snap_points(self.points([(89,0)]),roads,max_snap_km=100)
        self.assertEqual(out.road_node_index.iloc[0],1)

    def test_all_equal_distance_vertices_have_deterministic_osm_tie(self):
        roads=self.roads([(1,1),(1,1),(1,1),(1,1)],osm=[900,800,100,200])
        out=geometry.snap_points(self.points([(1,1)]),roads)
        self.assertEqual(out.road_osm_node.iloc[0],100)
        self.assertEqual(out.nearest_vertex_tie_osm_ids_json.iloc[0],'[100, 200, 800, 900]')
        self.assertTrue(out.nearest_vertex_distance_tie.iloc[0])

    def test_excessive_connector_is_retained_but_not_accepted(self):
        roads=self.roads([(0,0)])
        out=geometry.snap_points(self.points([(1,0)]),roads,max_snap_km=10)
        self.assertFalse(out.accepted_snap.iloc[0])
        self.assertGreater(out.snap_km.iloc[0],100)
        self.assertAlmostEqual(out.destination_connector_minutes.iloc[0],out.snap_km.iloc[0]*4)
        self.assertIsNone(out.source_record_id.iloc[0])

    def test_prepare_never_promotes_spatial_proxy_to_settlement_identity(self):
        source=pd.DataFrame({'provider_id':['ignored1','ignored2'],
            'site_id':['osm:node:1','osm:node:2'],'canonical_site_id':['osm:node:1','osm:node:2'],
            'service_code':['school_general','school_general'],'possible_duplicate_of':[None,None],
            'lat':[1.,1.],'lon':[1.,1.],'source_record_id':['npA','npA'],
            'current_identity_status':['spatial_proxy_not_identity_proof',geometry.STRICT_IDENTITY]})
        reference=pd.DataFrame({'source_record_id':['npA'],'name':['Село'],'region':['регион'],'lat':[1.],'lon':[1.]})
        out=geometry.prepare_sites(source,reference)
        self.assertTrue(pd.isna(out.source_record_id.iloc[0]))
        self.assertEqual(out.proxy_reference_source_record_id.iloc[0],'npA')
        self.assertEqual(out.source_record_id.iloc[1],'npA')
        self.assertFalse(out.nearest_reference_is_identity.any())
        self.assertTrue(out.geometry_direct.all())
        self.assertFalse(out.site_coordinate_is_building_entrance.any())

    def test_bad_coordinates_are_not_silently_placed(self):
        with self.assertRaises(ValueError):
            geometry.snap_points(self.points([(91,0)]),self.roads([(0,0)]))

    def test_actual_geometry_does_not_restore_explicitly_inactive_supply(self):
        source=pd.DataFrame({'site_id':['osm:node:1','osm:node:2'],
            'canonical_site_id':['osm:node:1','osm:node:2'],'service_code':['school_general','preschool'],
            'possible_duplicate_of':[None,None],'lat':[1.,1.],'lon':[1.,1.],
            'source_record_id':['npA','npA'],'current_identity_status':[geometry.STRICT_IDENTITY]*2,
            'temporal_eligible':[True,False],'lifecycle_eligible':[False,True]})
        reference=pd.DataFrame({'source_record_id':['npA'],'name':['Село'],'region':['регион'],'lat':[1.],'lon':[1.]})
        out=geometry.prepare_sites(source,reference)
        self.assertEqual(out.supply_status.tolist(),['excluded_lifecycle','excluded_temporal'])
        self.assertFalse(out.eligible_site_supply.any())
        self.assertTrue(out.geometry_direct.all())


if __name__=='__main__':unittest.main()
