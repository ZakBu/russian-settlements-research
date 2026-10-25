"""Reproduction failures must not silently change sources or publish stale roles."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec=importlib.util.spec_from_file_location('zero_reproduce',Path(__file__).resolve().parents[1]/'scripts/sgrt_zero/reproduce.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)


def put(root,relative,content=b'x'):
 p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content);return p


class ReproduceTests(unittest.TestCase):
 def test_full_sources_require_cryptographic_pin(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaisesRegex(ValueError,'immutable source manifest'):r.fetch_frozen_sources(Path(tmp),None)

 def test_medical_manifest_cannot_relabel_historical_source_as_current(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   manifest={'release_tag':r.MEDICAL_TAG,'source_reference_year':2026,'assets':[
    {'asset':r.MEDICAL_PDF,'sha256':r.MEDICAL_SHA256,'bytes':r.MEDICAL_BYTES}]}
   p=put(root,'medical.json',json.dumps(manifest).encode())
   with patch.object(r,'download',return_value=p) as get:
    with self.assertRaisesRegex(ValueError,'supplemental medical'):r.fetch_medical_source(root/'inputs')
   self.assertEqual(get.call_count,1)

 def test_source_zip_rejects_escape_and_symlink(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);z=root/'bad.zip'
   with zipfile.ZipFile(z,'w') as f:f.writestr('../escape','bad')
   with self.assertRaisesRegex(ValueError,'Unsafe ZIP'):r.safe_extract(z,root/'out')
   with zipfile.ZipFile(z,'w') as f:
    entry=zipfile.ZipInfo('link');entry.external_attr=(0o120777<<16);f.writestr(entry,'target')
   with self.assertRaisesRegex(ValueError,'Symlink'):r.safe_extract(z,root/'out')

 def test_frozen_internal_manifest_must_match_external(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'remote';source.mkdir();z=source/'source-inputs.zip'
   meta={'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}
   internal={'snapshot_label':'2026-10-25','files':{'file':meta}}
   with zipfile.ZipFile(z,'w') as f:
    f.writestr('source_inputs/file',b'x');f.writestr('source_inputs/source_manifest.json',json.dumps(internal))
   manifest={**internal,'source_release_tag':r.SOURCE_TAG,'archive':{'name':z.name,'bytes':z.stat().st_size,'sha256':r.digest(z)}}
   m=put(source,'source_manifest.json',json.dumps(manifest).encode())
   def local_download(url,path,expected_sha256=None,expected_bytes=None):
    p=put(Path(path).parent,Path(path).name,(source/url.rsplit('/',1)[-1]).read_bytes())
    self.assertEqual(r.digest(p),expected_sha256)
    return p
   with patch.object(r,'download',side_effect=local_download):
    folder,got=r.fetch_frozen_sources(root/'work',r.digest(m))
   self.assertEqual(got['snapshot_label'],'2026-10-25');self.assertEqual((folder/'file').read_bytes(),b'x')

 def test_compact_checks_every_hash_before_copying_and_ignores_derived(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);bundle=root/'bundle';put(bundle,'routes/nearest/a.parquet');put(bundle,'hierarchy/old/result',b'old')
   files={p.relative_to(bundle).as_posix():r.digest(p) for p in bundle.rglob('*') if p.is_file()}
   put(bundle,'checksums.json',json.dumps(files).encode());work=root/'work';work.mkdir()
   r.compact_prepare(bundle,work)
   self.assertTrue((work/'routes/nearest/a.parquet').exists());self.assertFalse((work/'hierarchy').exists())
   put(bundle,'routes/nearest/a.parquet',b'bad')
   with self.assertRaisesRegex(ValueError,'Bundle file differs'):r.compact_prepare(bundle,work)

 def test_final_health_and_federal_commerce_replace_old_roles(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   old=put(root,'routes/nearest/medical_basic_primary.parquet',b'old')
   extra=put(root,'routes_5post/nearest/daily_grocery_current_retail_host.parquet',b'diagnostic')
   corrected=put(root,'routes_health_corrected/nearest/medical_basic_primary.parquet',b'new')
   put(root,'health/np_supply.parquet',b'old');good=put(root,'health/public_scope_corrected/np_supply.parquet',b'new')
   put(root,'commerce/sites.parquet',b'old');final=put(root,'commerce/federal_context/sites.parquet',b'new')
   put(root,'routes/provider_road_seeds.parquet');put(root,'hierarchy/rejected/result')
   federal=put(root,'federal_medical/normalized/F038_history.parquet',b'history')
   put(root,'federal_medical/normalized/inputs/F038.xml',b'large_xml')
   files=r.payload_files(root)
   self.assertEqual(files['routes/nearest/medical_basic_primary.parquet'],corrected)
   self.assertEqual(files['commerce/sites.parquet'],final)
   self.assertEqual(files['routes/nearest/daily_grocery_current_retail_host.parquet'],extra)
   self.assertEqual(files['health/public_scope_corrected/np_supply.parquet'],good)
   self.assertEqual(files['federal_medical/normalized/F038_history.parquet'],federal)
   self.assertFalse(any(key.endswith('.xml') for key in files))
   self.assertNotIn('health/np_supply.parquet',files)
   self.assertFalse(any('rejected' in key or 'provider_road_seeds' in key for key in files))

 def test_complete_medical_scope_replaces_earlier_controls_without_deleting_them(self):
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp)
   old=put(work,'routes/nearest/medical_basic_primary.parquet',b'old')
   put(work,'routes_pediatric_scope_corrected/nearest/medical_basic_primary.parquet',b'age_only')
   final=put(work,'routes_complete_scope_corrected/nearest/medical_basic_primary.parquet',b'complete')
   put(work,'health/public_scope_corrected/np_supply.parquet',b'old')
   put(work,'health/public_scope_pediatric_corrected/np_supply.parquet',b'age_only')
   health=put(work,'health/public_scope_complete_corrected/np_supply.parquet',b'complete')
   functions=put(work,'federal_medical/functions_complete_scope_corrected/summary.json',b'{}')
   self.assertEqual(r.route_view(work)['medical_basic_primary'],final)
   self.assertEqual(r.canonical_health_supply(work),health)
   payload=r.payload_files(work)
   self.assertEqual(payload['routes/nearest/medical_basic_primary.parquet'],final)
   self.assertEqual(payload['health/public_scope_corrected/np_supply.parquet'],health)
   self.assertEqual(payload['federal_medical/functions/summary.json'],functions)
   self.assertEqual(old.read_bytes(),b'old')

 def test_incomplete_package_preserves_previous_local_build(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);old=put(root,'built/keep',b'old')
   with self.assertRaisesRegex(ValueError,'incomplete'):r.package(root,r.TAG,'f'*40)
   self.assertEqual(old.read_bytes(),b'old')

 def test_catalog_missing_required_pattern_is_an_error(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=put(Path(tmp),'cat.json',json.dumps({'files':[]}).encode())
   with self.assertRaisesRegex(ValueError,'Required catalogue'):r.catalog_plan(p,['missing'],'core')

 def test_source_corpus_is_portable_and_verified(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);sha=hashlib.sha256(b'data').hexdigest()
   put(root,'health/summary.json',json.dumps({'inputs_sha256':{'/absent/original.parquet':sha}}).encode())
   local=put(root,'inputs/source_corpus/'+sha[:16]+'_original.parquet',b'data')
   self.assertIn(local,r.source_corpus(root).values())
   local.write_bytes(b'bad')
   with self.assertRaisesRegex(ValueError,'differs'):r.source_corpus(root)

 def test_written_audit_with_any_violation_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp)
   for filename,n in [('level_zero_actual',1),('upward_actual',4),('extended_actual',6)]:
    rows=[{'failures':{'lost_origins':0,'over_bound':0}} for _ in range(n)]
    put(work,'checks/'+filename+'.json',json.dumps(rows[0] if n==1 else rows).encode())
   r.validate_actual_audits(work)
   path=work/'checks/extended_actual.json';rows=json.loads(path.read_text());rows[2]['failures']['over_bound']=1
   path.write_text(json.dumps(rows))
   with self.assertRaisesRegex(ValueError,'scientific audit failed'):r.validate_actual_audits(work)
   path.write_text('[]')
   with self.assertRaisesRegex(ValueError,'Incomplete actual audit'):r.validate_actual_audits(work)

 def test_extended_cannot_silently_audit_a_partial_run(self):
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp);main=r.SCENARIOS[0]
   for i in range(1,5):(work/'upward'/main/(str(i).zfill(2)+'_stage')).mkdir(parents=True)
   for mode in ['all_declared','partial_positive_two_domains']:
    for i in [2,3,4]:(work/'upward_extended'/main/mode/(str(i).zfill(2)+'_stage')).mkdir(parents=True)
   strict,extended=r.expected_stage_directories(work)
   self.assertEqual((len(strict),len(extended)),(4,6))
   extended[-1].rmdir()
   with self.assertRaisesRegex(ValueError,'all six actual stages'):r.expected_stage_directories(work)

 def test_grocery_diagnostic_cannot_silently_change_control_analysis(self):
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp);table=put(work,'derived_nearest/daily_grocery_evidence_union.parquet')
   self.assertIsNone(r.grocery_override(work))
   put(work,'analysis_options.json',json.dumps({'grocery_nearest':'derived_nearest/missing.parquet'}).encode())
   with self.assertRaisesRegex(ValueError,'grocery override missing'):r.grocery_override(work)
   put(work,'analysis_options.json',json.dumps({'grocery_nearest':'derived_nearest/daily_grocery_evidence_union.parquet'}).encode())
   self.assertEqual(r.grocery_override(work),table.resolve())

 def test_full_recipe_snaps_new_yandex_sites_instead_of_reusing_wb_cache(self):
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp);source=work/'frozen';source.mkdir()
   put(work,'source/external_fua/global.gpkg')
   commands=[]
   with patch.object(r,'fetch_frozen_sources',return_value=(source,{'snapshot_label':'2026-10-25'})), \
        patch.object(r,'fetch_medical_source',return_value=work/'historical.pdf'), \
        patch.object(r,'fetch_federal_source',return_value=work/'federal.zip'), \
        patch.object(r,'fetch_catalog'),patch.object(r,'copy_file'),patch.object(r,'safe_extract'), \
        patch.object(r,'digest',return_value='a'*64),patch.object(r,'run',side_effect=lambda *a:commands.append(a)):
    r.full_prepare(work,'b'*64)
   operator={str(a[-1]).rsplit('/',1)[-1]:a for a in commands if Path(a[0]).name=='transport.py'}
   ym=operator['routes_yandex'];wb=operator['routes_wb']
   self.assertIn('--road-nodes',ym);self.assertIn('--road-origins',ym)
   self.assertNotIn('--geometry-cache',ym)
   self.assertIn('--geometry-cache',wb)

 def test_all_five_scenarios_and_four_higher_stages_are_requested(self):
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp);put(work,'routes/nearest/medical_basic_primary.parquet')
   commands=[]
   with patch.object(r,'run',side_effect=lambda *a:commands.append(a)),patch.object(r,'scientific_checks'), \
        patch.object(r,'expected_stage_directories'),patch.object(r,'validate_actual_audits'), \
        patch.object(r,'canonical_health_supply',return_value=work/'health/public_scope_corrected/np_supply.parquet'):
    r.analyses(work)
   scenarios=[a[a.index('--scenario-id')+1] for a in commands if Path(a[0]).name=='hierarchy.py']
   self.assertEqual(scenarios,r.SCENARIOS)
   self.assertEqual(sum(Path(a[0]).name=='upward.py' for a in commands),1)
   self.assertFalse(any('fetch' in a for a in commands))

 def test_finished_bundle_readme_uses_actual_counts_and_distinguishes_commit_context(self):
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp)
   put(work,'checks/scientific_checks.json',json.dumps({'analysis_origins':153803,'ordinary_origins':153800,'nonadditive_context_origins':3}).encode())
   for index,scenario in enumerate(r.SCENARIOS):
    put(work,'hierarchy/'+scenario+'/summary.json',json.dumps({'level0_units':900+index,'inhabited_multi_np_service_areas':120+index}).encode())
   stage={'name':'test_function','parent_units':501,'new_merger_groups':7}
   put(work,'upward/'+r.SCENARIOS[0]+'/summary.json',json.dumps({'stages':[stage]}).encode())
   put(work,'upward_extended/'+r.SCENARIOS[0]+'/summary.json',json.dumps({'scenarios':{'all_declared':[stage]}}).encode())
   answer=r.result_readme(work,'a'*40)
   self.assertIn('**120 групп',answer)
   self.assertIn('| Основной: медицина и магазины 20 минут, школа 30 минут, Wildberries | 900 | 120 |',answer)
   self.assertNotIn('partial_positive_two_domains',answer)
   self.assertIn('| test_function | 501 | 7 |',answer)
   self.assertIn('состояние на момент исходного коммита',answer)
   self.assertIn('этими расчётами не установлен',answer)

 def test_actual_primary_scope_failure_cannot_pass_publication_validation(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=put(Path(tmp),'scope.json',json.dumps({'failures':{'child_primary_rows':1,'narrow_primary_rows':0}}).encode())
   with self.assertRaisesRegex(ValueError,'primary-care source scope audit failed'):r.validate_primary_scope_report(path)
   path.write_text(json.dumps({'failures':{'child_primary_rows':0,'narrow_primary_rows':0}}))
   r.validate_primary_scope_report(path)
   path.write_text('{}')
   with self.assertRaisesRegex(ValueError,'Missing actual'):r.validate_primary_scope_report(path)

 def test_astrakhan_counterexample_ignores_unkeyed_reference_rows(self):
  import pandas as pd
  with tempfile.TemporaryDirectory() as tmp:
   work=Path(tmp);(work/'context').mkdir()
   pd.DataFrame({'source_record_id':['a','b',None,None],'name':['Астрахань','Село','Не установлено','Не установлено'],
    'region':['астраханская']*4,'settlement_type_2021':['город','село',None,None],
    'lat':[46.35,46.40,None,None],'lon':[48.04,48.20,None,None]}).to_parquet(work/'context/analysis_reference.parquet',index=False)
   for relative in ['upward/'+r.SCENARIOS[0], 'upward_extended/'+r.SCENARIOS[0]+'/all_declared','upward_extended/'+r.SCENARIOS[0]+'/partial_positive_two_domains']:
    folder=work/relative/'04_urban_hightech';folder.mkdir(parents=True)
    pd.DataFrame({'origin_id':['a','b'],'unit_id':['u','u']}).to_parquet(folder/'memberships.parquet',index=False)
   result=r.astrakhan_scope_comparison(work)
   self.assertEqual(len(result),3)
   self.assertTrue(all(row['records']==2 and 10<row['diameter_km']<20 for row in result))


if __name__=='__main__':unittest.main()
