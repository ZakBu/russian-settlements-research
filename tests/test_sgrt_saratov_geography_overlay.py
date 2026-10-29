import hashlib
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from scripts.sgrt_saratov.geography_overlay import derive_inputs,validate_corrections,apply_provider_proxies,run

class GeographyOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        evidence=self.root/'point.json';evidence.write_text('{"published":"point"}')
        self.ref=pd.DataFrame({'source_record_id':['a','b'],'lat':[51.,52.],'lon':[48.,49.],
            'population_2021':[100,200],'credit_2021':[True,True],'base_lat':[51.,52.]})
        self.end=pd.DataFrame({'source_record_id':['a','b'],'road_node_index':[0.,1.],
            'snap_km':[.1,.2],'road_endpoint_accepted':[True,True],'weak_component':[1.,1.],
            'verified_component_id':[1,1],'verified_component_node_count':[100,100],
            'verified_road_out_degree':[3,4],'verified_road_in_degree':[3,4],
            'small_component_under_100_nodes':[False,False]})
        self.fix=pd.DataFrame([{'source_record_id':'a','expected_lat':51.,'expected_lon':48.,
            'corrected_lat':51.001,'corrected_lon':48.002,'source_id':'SOURCE',
            'source_url':'https://example.org/source','coordinate_kind':'official_published_point',
            'correction_basis':'Published point checked against original source.',
            'evidence_path':'point.json','evidence_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}])
        self.roads=pd.DataFrame({'node_index':[0,1,2],'osm_id':[10,11,12],
            'lat':[51.,52.,51.001],'lon':[48.,49.,48.002],'weak_component':[1,1,2]})
    def tearDown(self):self.temp.cleanup()
    def test_corrected_geometry_resnaps_without_mutating_base_or_population(self):
        before=self.ref.copy(deep=True);oldend=self.end.copy(deep=True)
        ref,end,snapped,summary=derive_inputs(self.ref,self.end,self.fix,self.roads,evidence_root=self.root)
        pd.testing.assert_frame_equal(self.ref,before);pd.testing.assert_frame_equal(self.end,oldend)
        self.assertEqual(ref.loc[0,'lat'],51.001);self.assertEqual(ref.loc[0,'pilot_original_lat'],51.)
        self.assertEqual(ref.loc[0,'base_lat'],51.)
        pd.testing.assert_series_equal(ref.population_2021,before.population_2021)
        pd.testing.assert_series_equal(ref.credit_2021,before.credit_2021)
        self.assertEqual(end.loc[0,'road_node_index'],2)
        self.assertEqual(end.loc[0,'pilot_original_road_node_index'],0)
        self.assertEqual(end.loc[0,'weak_component'],2)
        self.assertTrue(pd.isna(end.loc[0,'verified_component_id']))
        self.assertTrue(pd.isna(end.loc[0,'verified_road_out_degree']))
        self.assertEqual(end.loc[1,'verified_road_out_degree'],4)
        self.assertFalse(summary['original_reference_and_endpoint_sources_modified'])
    def test_only_np_proxy_moves_and_its_original_point_is_checked(self):
        ref,end,_,_=derive_inputs(self.ref,self.end,self.fix,self.roads,evidence_root=self.root)
        provider=pd.DataFrame({'catalog_id':['np-a','physical-a'],'correctsource_record_id':['a','a'],
            'input_kind':['np','sites'],'site_lat':[51.,51.0003],'site_lon':[48.,48.0004],
            'road_node_index':[0.,0.],'destination_connector_minutes':[.4,.4],
            'accepted_snap':[True,True],'routable_provider':[True,True]})
        changed,proof=apply_provider_proxies(provider,ref,end)
        self.assertEqual(changed.loc[0,'site_lat'],51.001)
        self.assertEqual(changed.loc[0,'road_node_index'],2)
        pd.testing.assert_series_equal(changed.loc[1,provider.columns],provider.loc[1],check_names=False)
        self.assertEqual(proof['np_point_proxies_corrected'],1)
        self.assertFalse(proof['physical_site_coordinates_modified'])
        bad=provider.copy();bad.loc[0,'site_lat']=50.
        with self.assertRaises(ValueError):apply_provider_proxies(bad,ref,end)

    def test_stale_expected_coordinates_or_source_hash_are_rejected(self):
        for field,value in [('expected_lon',48.2),('evidence_sha256','f'*64),
                             ('evidence_path','../point.json')]:
            fix=self.fix.copy();fix[field]=value
            with self.assertRaises(ValueError):validate_corrections(self.ref,self.end,fix,evidence_root=self.root)
    def test_polygon_source_must_cover_new_point_and_exclude_old_point(self):
        import json
        path=self.root/'polygon.json'
        path.write_text(json.dumps({'type':'Polygon','coordinates':[[[48.001,51.0005],[48.003,51.0005],
            [48.003,51.002],[48.001,51.002],[48.001,51.0005]]]}))
        fix=self.fix.copy();fix['coordinate_kind']='published_settlement_polygon_representative_point'
        fix['evidence_path']='polygon.json';fix['evidence_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        validate_corrections(self.ref,self.end,fix,evidence_root=self.root)
        fix['corrected_lon']=48.1
        with self.assertRaises(ValueError):validate_corrections(self.ref,self.end,fix,evidence_root=self.root)

    def test_cli_pipeline_cannot_overwrite_immutable_input_paths(self):
        with self.assertRaisesRegex(ValueError,'must not overwrite'):
            run(self.root/'analysis_reference.parquet',self.root/'end.parquet',self.root/'fix.csv',
                self.root/'roads',self.root/'catalog.json',self.root)

    def test_duplicate_identity_and_distant_snap_are_rejected(self):
        with self.assertRaises(ValueError):validate_corrections(self.ref,self.end,
            pd.concat([self.fix,self.fix]),evidence_root=self.root)
        distant=self.fix.copy();distant['corrected_lat']=0.;distant['corrected_lon']=0.
        with self.assertRaises(ValueError):derive_inputs(self.ref,self.end,distant,self.roads,evidence_root=self.root)

if __name__=='__main__':unittest.main()
