import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix,save_npz,load_npz
from scipy.sparse.csgraph import dijkstra
from scripts.sgrt_saratov.regional_fields import (forward_union,known_costs_from_sparse,top_group_candidates,normalize_field_table,prepare,scalar_origin_result,load_checkpoint,run,current_provider_candidates,physical_contract,provider_rows)

class RegionalFieldsTests(unittest.TestCase):
    def test_forward_union_preserves_path_through_nonregional_vertex(self):
        # Only vertex0 is a regional origin; the cheapest path to2 leaves it
        # through vertex1. Administrative vertex clipping would destroy it.
        graph=csr_matrix(([2.,2.,20.,1.],([0,1,0,3],[1,2,2,0])),shape=(4,4))
        reduced,axis,mapping=forward_union(graph,[0],5.)
        self.assertEqual(set(axis),{0,1,2})
        actual=dijkstra(reduced,directed=True,indices=mapping[0],limit=5.)
        self.assertEqual(actual[mapping[2]],4.)
        self.assertEqual(mapping[3],-1)

    def test_forward_union_cannot_be_replaced_by_reverse_union(self):
        graph=csr_matrix(([3.,2.],([0,2],[1,0])),shape=(3,3))
        _,axis,_=forward_union(graph,[0],4.)
        _,reverse_axis,_=forward_union(graph.T.tocsr(),[0],4.)
        self.assertEqual(set(axis),{0,1});self.assertEqual(set(reverse_axis),{0,2})

    def test_stored_zero_and_absent_pair_are_different(self):
        matrix=csr_matrix(([0.,12.],([0,0],[0,2])),shape=(2,4))
        row=known_costs_from_sparse(matrix,0,[0,1,2,3])
        self.assertEqual(row[0],0.);self.assertEqual(row[2],12.)
        self.assertTrue(np.isnan(row[[1,3]]).all())
        self.assertTrue(np.isnan(known_costs_from_sparse(matrix,1,[0,1])).all())

    def test_top_destinations_deduplicate_and_retain_boundary_ties(self):
        result=top_group_candidates([1.,3.,2.,4.,4.],[0,0,1,2,3],['a','b','c','d'],3)
        self.assertEqual(result,[(0,1.,1),(1,2.,2),(2,4.,3),(3,4.,3)])
        self.assertEqual(top_group_candidates([np.inf],[0],['a']),[])

    def test_resume_rejects_nonmatching_scenarios_and_incomplete_shards(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'cost_chunks').mkdir()
            save_npz(root/'cost_chunks'/'part_000.npz',csr_matrix((32,5)))
            rows=[SimpleNamespace(source_record_id=str(i)) for i in range(64)]
            frame=pd.DataFrame([{'source_record_id':str(i),'kernel':f,'half_time':10.,'include_self':own}
                for i in range(32) for f in ['exponential','gaussian'] for own in [True,False]])
            frame.to_parquet(root/'fields_in_progress.parquet',index=False)
            self.assertEqual(load_checkpoint(root,rows,[10.])[0],32)
            with self.assertRaises(ValueError):load_checkpoint(root,rows,[20.])
            save_npz(root/'cost_chunks'/'part_001.npz',csr_matrix((5,5)))
            with self.assertRaises(ValueError):load_checkpoint(root,rows,[10.])

    def test_nonhistorical_sensitivity_searches_beyond_historical_top_three(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);graph=csr_matrix(([1.,2.,3.,4.],([0,0,0,0],[1,2,3,4])),shape=(5,5))
            save_npz(root/'reduced_graph.npz',graph);np.save(root/'road_node_axis.npy',np.arange(5))
            (root/'summary.json').write_text(json.dumps({'horizon_minutes':480.}))
            roster=pd.DataFrame({'source_record_id':['origin'],'road_node_index':[0],'snap_km':[0.]})
            roster.to_parquet(root/'regional_roster.parquet',index=False)
            catalog=pd.DataFrame({'provider_id':['p1','p2','p3','p4'],'catalog_id':['c1','c2','c3','c4'],
                'family':['medical_basic']*4,'source_record_id':['b','c','d','e'],'road_node_index':[1,2,3,4],
                'destination_connector_minutes':[0.]*4,'accepted_snap':[True]*4,'historical_only':[True,True,True,False]})
            catalog.to_parquet(root/'providers.parquet',index=False)
            baseline=provider_rows(np.array([0.,1.,2.,3.,4.]),next(roster.itertuples(index=False)),physical_contract(root/'providers.parquet',np.arange(5)),480.)
            self.assertEqual(len(baseline),3);self.assertNotIn('p4',[r['provider_id'] for r in baseline])
            pd.DataFrame(baseline).to_parquet(root/'physical_provider_candidates.parquet',index=False)
            facts=current_provider_candidates(root,root/'providers.parquet',workers=1)
            result=pd.read_parquet(root/'physical_provider_candidates_current.parquet')
            self.assertEqual(facts['recomputed_origins'],1)
            self.assertEqual(result.provider_id.tolist(),['p4']);self.assertEqual(result.cost_minutes.tolist(),[4.])
            self.assertEqual(result['rank'].tolist(),[1])
            current_provider_candidates(root,root/'providers.parquet',workers=2)
            pd.testing.assert_frame_equal(result,pd.read_parquet(root/'physical_provider_candidates_current.parquet'))
            with patch('multiprocessing.get_all_start_methods',return_value=['spawn']):
                current_provider_candidates(root,root/'providers.parquet',workers=2)
            pd.testing.assert_frame_equal(result,pd.read_parquet(root/'physical_provider_candidates_current.parquet'))

    def fixture(self):
        ref=pd.DataFrame({'source_record_id':['a','b','c','d'],'population_2021':[100.,50.,20.,30.],
            'credit_2021':[True,True,False,True],'budget_population_credit':[True,True,False,True],
            'ordinary_spatial_2021':[True]*4,'accepted_point_present':[True]*4,
            'region':['саратовская']*4,'name':['a','b','c','d'],'lat':[51.]*4,'lon':[46.,46.001,46.002,46.003]})
        ep=pd.DataFrame({'source_record_id':['a','b','c','d'],'road_node_index':[0.,1.,2.,np.nan],
            'road_endpoint_accepted':[True,True,True,False],'snap_km':[0.,0.,0.,np.nan]})
        return prepare(ref,ep,pd.DataFrame({'source_record_id':['a','b','c','d']}))

    def test_resuming_completed_route_shards_preserves_fields_costs_and_neighbors(self):
        sources,roster,dest=self.fixture()
        graph=csr_matrix(([10.,20.,15.,15.],([0,1,0,2],[1,0,2,0])),shape=(3,3))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ['ref','ep','roster']:(root/name).write_text(name)
            with patch('scripts.sgrt_saratov.regional_fields.build_inputs',return_value=(graph,graph,np.arange(3),sources,roster,dest)):
                run(root/'ref',root/'ep',root/'roster',root,root,workers=1,half_times=[10.])
                matrix=load_npz(root/'destination_costs.npz');regional=np.load(root/'regional_costs.npy')
                fields=pd.read_parquet(root/'fields.parquet');neighbors=pd.read_parquet(root/'national_neighbors.parquet')
                run(root/'ref',root/'ep',root/'roster',root,root,workers=1,half_times=[10.],resume=True)
                actual=load_npz(root/'destination_costs.npz')
                np.testing.assert_array_equal(matrix.indptr,actual.indptr);np.testing.assert_array_equal(matrix.indices,actual.indices);np.testing.assert_allclose(matrix.data,actual.data,rtol=0,atol=0)
                np.testing.assert_allclose(regional,np.load(root/'regional_costs.npy'),rtol=0,atol=0,equal_nan=True)
                pd.testing.assert_frame_equal(fields,pd.read_parquet(root/'fields.parquet'))
                pd.testing.assert_frame_equal(neighbors,pd.read_parquet(root/'national_neighbors.parquet'))

    def test_known_field_uses_credited_mass_only_and_keeps_raw_envelope(self):
        sources,roster,dest=self.fixture()
        graph=csr_matrix(([10.,20.,15.,15.],([0,1,0,2],[1,0,2,0])),shape=(3,3))
        result=scalar_origin_result(next(roster.itertuples(index=False)),graph,np.arange(3),dest,sources,[10.],480.)
        fields=pd.DataFrame(result[3]);exp=fields[fields.kernel=='exponential']
        self.assertAlmostEqual(exp[exp.include_self].iloc[0]['value'],125.)
        self.assertAlmostEqual(exp[~exp.include_self].iloc[0]['value'],25.)
        self.assertAlmostEqual(exp.iloc[0].omitted_published_reference_envelope,20*2**(-1.5))
        self.assertGreater(exp.iloc[0].unmapped_mass_upper,0.)

    def test_missing_origin_rows_and_reference_own_exclusion_are_explicit_idempotent(self):
        _,roster,_=self.fixture()
        rows=[]
        for origin in ['a','b','c']:
            for family in ['exponential','gaussian']:
                for own in [True,False]:
                    rows.append({'source_record_id':origin,'kernel':family,'half_time':10.,'include_self':own,
                        'value':1.,'omitted_published_reference_envelope':30.,'status':'computed_to_horizon'})
        normalized=normalize_field_table(pd.DataFrame(rows),roster,[10.],480.)
        self.assertEqual(len(normalized),16)
        unknown=normalized[normalized.source_record_id=='d'];self.assertTrue(unknown.value.isna().all())
        self.assertTrue(unknown.status.eq('origin_endpoint_unavailable').all())
        c=normalized[(normalized.source_record_id=='c')&~normalized.include_self]
        self.assertTrue(c.omitted_published_reference_envelope.eq(10.).all())
        pd.testing.assert_frame_equal(normalized,normalize_field_table(normalized,roster,[10.],480.))

if __name__=='__main__':unittest.main()
