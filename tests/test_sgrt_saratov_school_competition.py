import unittest
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scripts.sgrt_saratov.school_competition import edge_intervals,fraction_geometry,omit_empty_display_features,prepare_seeds
from scripts.sgrt_mass.routes import weighted_multisource

class SchoolCompetitionTests(unittest.TestCase):
    def test_kindergarten_and_unadmitted_presence_do_not_seed_a_school(self):
        catalog=pd.DataFrame(columns=['family','routable_provider','catalog_id','correctsource_record_id','location_precision'])
        roster=pd.DataFrame({'source_record_id':['kindergarten','school','held'],
            'road_endpoint_accepted':[True]*3,'road_node_index':[0,1,2],'snap_km':[0.]*3})
        presence=pd.DataFrame(columns=['family','source_record_id'])
        official=pd.DataFrame({'source_record_id':['kindergarten','school','held'],
            'service_code':['preschool','school_general','school_general'],
            'eligible_np_presence_proxy':[True,True,False],
            'provider_id':['a','b','c'],'name':['A','B','C'],'source_id':['source']*3})
        _,_,extra=prepare_seeds(catalog,roster,presence,official)
        self.assertEqual(extra.source_record_id.tolist(),['school'])

    def test_bidirectional_boundary_is_internal(self):
        r=edge_intervals(0.,0.,20.,0)
        self.assertEqual([(x[0],x[1],x[2]) for x in r],[(0.,.5,'u'),(.5,1.,'v')])
        self.assertEqual([x[3] for x in r],[0,0])
    def test_one_way_cannot_exit_wrong_endpoint(self):
        r=edge_intervals(0.,100.,20.,1)
        self.assertEqual(r,[])
        r=edge_intervals(100.,0.,20.,1)
        self.assertEqual([(x[0],x[1],x[3]) for x in r],[(0.,.5,1),(.5,1.,0)])
    def test_weighted_seeds_dont_add_connector_after_winner(self):
        # origin0 reachesseed1 in1min +10connector, seed2 in3min +0connector.
        reverse=csr_matrix(([1.,3.],([1,2],[0,0])),shape=(3,3))
        d,s=weighted_multisource(reverse,np.array([1,2]),np.array([10.,0.]))
        self.assertEqual(d[0],3.);self.assertEqual(s[0],1)
    def test_unknown_endpoints_do_not_create_zones(self):
        self.assertEqual(edge_intervals(np.inf,np.inf,3.,0),[])
        self.assertEqual(edge_intervals(1.,np.inf,3.,1),[])
    def test_piece_partition_matches_independent_point_costs(self):
        rng=np.random.default_rng(20261028)
        for _ in range(100):
            u,v,w=rng.uniform(0,100,3);direction=int(rng.choice([-1,0,1]))
            intervals=edge_intervals(u,v,w,direction)
            for x in np.linspace(.00013,.99973,53):
                costs=[]
                if direction<=0:costs.append((u+x*w,'u'))
                if direction>=0:costs.append((v+(1-x)*w,'v'))
                cost,endpoint=min(costs)
                got=[r for r in intervals if r[0]<x<r[1]]
                self.assertEqual(len(got),int(cost<=60))
                if got:
                    self.assertEqual(got[0][2],endpoint)
                    self.assertEqual(got[0][3],sum(cost>t for t in [10,20,30,60]))
    def test_empty_display_is_omitted_without_erasing_road_assignment(self):
        features=[{'type':'Feature','properties':{'id':'outside','name':'Outside school'},
            'geometry':{'type':'Polygon','coordinates':[]}},
            {'type':'Feature','properties':{'id':'inside','name':'Inside school'},
            'geometry':{'type':'Polygon','coordinates':[[[0,0],[1,0],[1,1],[0,0]]]}}]
        kept,omissions=omit_empty_display_features(features)
        self.assertEqual(len(kept),1);self.assertEqual(kept[0]['properties']['id'],'inside')
        self.assertTrue(omissions[0]['road_assignments_retained'])
        self.assertEqual(omissions[0]['id'],'outside')
    def test_bent_native_shape_is_not_chord(self):
        g=fraction_geometry(np.array([[48.,50.],[48.1,50.1],[48.2,50.]]),.1,.9)
        self.assertEqual(len(g.coords),3)
        self.assertAlmostEqual(g.coords[1][1],50.1)

if __name__=='__main__':unittest.main()
