"""Counterexamples for publishing conditional upper research without false ranks."""
from pathlib import Path
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from scripts.sgrt_zero import cloud_upper_research as cloud


class UpperReleaseTests(unittest.TestCase):
    def test_control_compares_all_columns_and_preserves_duplicate_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'np_diagnostic').mkdir(); path=root/'np_diagnostic/rows.parquet'
            for filename in ['municipal-scale-points.csv','conditional-cooperation-60-points.csv']:
                pd.DataFrame({'name':['point'],'lat':[50.],'lon':[40.],'value':[1]}).to_csv(root/filename,index=False)
            cloud.write(root/'map_scope.json',{'empirical_hierarchy_established':False})
            frame=pd.DataFrame({'id':['a','b'],'unshown_evidence':[1,2]})
            frame.to_parquet(path,index=False); first=cloud.control(root)
            frame.iloc[::-1].to_parquet(path,index=False)
            self.assertEqual(first,cloud.control(root))
            (root/'unpublished_future_diagnostic').mkdir()
            frame.to_parquet(root/'unpublished_future_diagnostic/not_in_this_producer.parquet',index=False)
            self.assertEqual(first,cloud.control(root))
            frame.loc[1,'unshown_evidence']=3;frame.to_parquet(path,index=False)
            self.assertNotEqual(first,cloud.control(root))
            pd.concat([frame,frame.iloc[:1]]).to_parquet(path,index=False)
            self.assertEqual(cloud.control(root)['tables']['np_diagnostic/rows.parquet']['rows'],3)
            (root/'census_workplace').mkdir()
            cloud.write(root/'census_workplace/evidence.json',[{'numerator':7,'unknown':None}])
            before=cloud.control(root)
            cloud.write(root/'census_workplace/evidence.json',[{'numerator':8,'unknown':None}])
            self.assertNotEqual(before,cloud.control(root))

    def test_existing_draft_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'bundle.zip').write_bytes(b'archive')
            cloud.write(root/'manifest.json',{'source_commit':'a'*40,'release_tag':cloud.TAG,
                'archive':{'asset':'bundle.zip','bytes':7,'sha256':cloud.sha(root/'bundle.zip')},'standalone_assets':{}})
            with patch.object(cloud,'clean_commit'),patch.object(cloud,'releases',return_value=[{'tag_name':cloud.TAG,'draft':True}]),patch.object(cloud.subprocess,'run') as command:
                with self.assertRaisesRegex(ValueError,'never be overwritten'):cloud.publish(root,'a'*40)
                command.assert_not_called()

    def test_verified_upload_stays_draft_until_root_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bundle.zip').write_bytes(b'archive')
            cloud.write(root/'manifest.json',{'source_commit':'a'*40,'release_tag':cloud.TAG,
                'archive':{'asset':'bundle.zip','bytes':7,'sha256':cloud.sha(root/'bundle.zip')},'standalone_assets':{}})
            (root/'release_notes.md').write_text('Scope')
            assets=[root/'bundle.zip',root/'manifest.json']
            draft={'id':42,'tag_name':cloud.TAG,'draft':True,'target_commitish':'a'*40,
                'assets':[{'name':p.name,'size':p.stat().st_size,'digest':'sha256:'+cloud.sha(p)} for p in assets]}
            with patch.object(cloud,'clean_commit'),patch.object(cloud,'releases',side_effect=[[],[draft]]),patch.object(cloud.subprocess,'run',side_effect=[SimpleNamespace(returncode=1,stderr='HTTP 404'),SimpleNamespace(returncode=0)]) as command:
                result=cloud.publish(root,'a'*40)
                self.assertTrue(result['draft'])
                self.assertEqual(result['draft_release_id'],42)
                self.assertEqual(command.call_count,2)
                self.assertFalse(any('PATCH' in call.args[0] for call in command.call_args_list))

    def test_producer_mismatch_is_rejected_before_any_network_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cloud.write(root/'manifest.json',{'source_commit':'b'*40,'release_tag':cloud.TAG})
            with patch.object(cloud,'clean_commit'),patch.object(cloud.subprocess,'run') as command:
                with self.assertRaisesRegex(ValueError,'Producer/tag mismatch'):cloud.publish(root,'a'*40)
                command.assert_not_called()

    def test_map_uses_representative_point_without_assigning_workers_to_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'municipal').mkdir();(root/'cooperation').mkdir()
            ref=pd.DataFrame({'source_record_id':['small','large','moscow','petersburg'],
                'name':['Малое','Большое','Москва','Санкт-Петербург'],'lat':[50.,51.,55.,60.],
                'lon':[40.,41.,37.,30.],'population_2021':[10.,1000.,13000000.,5600000.],
                'credit_2021':[True,True,False,False],'ordinary_spatial_2021':[True,True,False,False]})
            ref.to_parquet(root/'reference.parquet',index=False)
            pd.DataFrame({'source_record_id':ref.source_record_id,'matched_2021_parent_code':['12345678','12345678',None,None]}).to_parquet(root/'municipal/reference_parent_crosswalk.parquet',index=False)
            pd.DataFrame({'oktmo':['12345678','45000000','40000000'],'municipality':['Район','Москва','Санкт-Петербург'],
                'recorded_component_comparison_eligible':[True]*3,
                'partial_organisation_workers_2025_territorial':[9000.,4211363.,1565094.]}).to_parquet(root/'municipal/municipal_scale_comparisons.parquet',index=False)
            pd.DataFrame({'time_budget_scenario_minutes':[60.,30.],'spatial_time_admissible':[True,True],
                'core_name':['Малое']*2,'core_lat':[50.]*2,'core_lon':[40.]*2,
                'conditional_cooperation_link_with_territorial_scale_evidence':[False,True],
                'parent_name':['Большое']*2,'unit_id':['u']*2,'parent_origin_id':['large']*2}).to_parquet(root/'cooperation/urban_cooperation_candidates.parquet',index=False)
            cloud.site_exports(root,root/'reference.parquet')
            points=pd.read_csv(root/'municipal-scale-points.csv',dtype={'oktmo':str})
            point=points[points.oktmo.eq('12345678')].iloc[0]
            self.assertEqual(point.source_record_id,'large')
            self.assertEqual(point.value,9000.)
            self.assertIn('частичная численность работников МО',point['name'])
            self.assertIn('not_worker_location',point.point_scope)
            self.assertEqual(len(pd.read_csv(root/'conditional-cooperation-60-points.csv')),1)
            scope=json.loads((root/'map_scope.json').read_text())
            self.assertFalse(scope['municipal_workers_assigned_to_np'])
            self.assertFalse(scope['observed_flows_or_verified_agglomerations'])

    def test_workforce_raw_and_graph_sources_are_explicitly_pinned(self):
        self.assertEqual(cloud.MEMBER_BYTES,3305237)
        self.assertEqual(cloud.MEMBER_SHA256,'f643b394c11758f5d28e465380e263943c5e5e9e312a468daedca95b7e2f87d7')
        self.assertEqual(len(cloud.INPUTS['data/catalog.json']),3)
        for catalog,wanted in cloud.INPUTS.items():
            available={r['path'] for r in json.loads((cloud.REPO/catalog).read_text())['files']}
            self.assertFalse(set(wanted)-available)


if __name__=='__main__':unittest.main()
