"""Synthetic-only checks; never opens model outputs or analysis result files."""
import importlib.util,unittest,tempfile,json
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).with_name('run_regressions_cycle06.py');sp=importlib.util.spec_from_file_location('adapter',P);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
class AdapterTests(unittest.TestCase):
 def test_nested_ols_comparison(self):
  rng=np.random.default_rng(4);x=rng.normal(size=(120,3));y=x[:,0]*2+x[:,1]+rng.normal(size=120)*.1;g=np.repeat(np.arange(12),10)
  fits=[m.fit_ols(x[:,:k],y,g) for k in [1,2,3]];self.assertTrue(all(f['rank']==f['p'] for f in fits));self.assertGreaterEqual(fits[2]['r2'],fits[1]['r2']);self.assertGreaterEqual(fits[1]['r2'],fits[0]['r2'])
 def test_bootstrap_repeatable_and_region_paired(self):
  rng=np.random.default_rng(7);n=80;frame=pd.DataFrame({'system_id':['x'+str(i) for i in range(n)],'x':rng.normal(size=n),'y':rng.normal(size=n),'region':np.repeat(np.arange(8),10).astype(str)});frame['outcome_system_change_pct']=2*frame.x+.1*frame.y
  terms={'M1':['x'],'M2':['x','y'],'M3':['x','y']};config={'model_terms':terms,'seed':8,'cluster_bootstrap_replicates':199,'minimum_successful_bootstrap_fraction':.8};metrics=pd.DataFrame([{'scenario':'B_M1_M2_M3_configuration_observed__primary','outcome':'outcome_system_change_pct','level':1,'model':name,'dropped_constant_terms':'','dropped_collinear_terms':''} for name in terms]);pred=pd.DataFrame([{'scenario':'B_M1_M2_M3_configuration_observed__primary','outcome':'outcome_system_change_pct','level':1,'model':model,'system_id':uid} for model in terms for uid in frame.system_id]);a=m.region_bootstrap(frame,metrics,pred,config);b=m.region_bootstrap(frame,metrics,pred,config);pd.testing.assert_frame_equal(a,b);self.assertTrue(a.status.eq('COMPUTED').all());self.assertTrue(a.paired_region_draws_shared_across_M1_M2_M3.all());self.assertTrue(np.isfinite(a[['ci95_lower','ci95_upper']]).all().all())
 def test_two_families_keep_denominators_separate(self):
  config={'model_terms':{'M1':['a'],'M2':['a','log_agro_grain_yield2021'],'M3':['a','log_agro_grain_yield2021','yield2021_x_polycentric']}}
  scenarios=m.scenario_design(config);self.assertEqual(len(scenarios),22);self.assertEqual(sum(len(x[2]) for x in scenarios),55)
  for i in range(0,22,2):
   self.assertEqual(list(scenarios[i][2]),['M1','M2']);self.assertEqual(list(scenarios[i+1][2]),['M1','M2','M3'])
  byname={x[0]:x[2] for x in scenarios}
  regional=byname['A_M1_M2__regional_actual_land2021_sensitivity']['M2'];municipal=byname['A_M1_M2__ten_region_municipal_agrocensus2021_separate_sensitivity']['M2']
  self.assertIn('regional_sown_farmland2021',regional);self.assertNotIn('municipal_actual_sown_farmland2021',regional);self.assertIn('municipal_actual_sown_farmland2021',municipal);self.assertNotIn('regional_sown_farmland2021',municipal)
  self.assertIn('yield2010_x_polycentric',byname['B_M1_M2_M3_configuration_observed__historical_grain2010_primary2021_parent_boundary_unproven_sensitivity']['M3'])
 def test_own_center_time_is_level_direct_time_not_large_city_context(self):
  with tempfile.TemporaryDirectory() as folder:
   home=Path(folder);model=home/'model';output=home/'analysis';model.mkdir();output.mkdir();config=json.loads(P.with_name('analysis_inputs_cycle06_template.json').read_text());config.update({'model_output':str(model),'context_directory':str(home),'axis':str(model/'nodes.parquet'),'model_inputs':str(home/'model_config.json'),'provenance_sidecars':[]})
   ids=['c','r1','r2'];nodes=pd.DataFrame({'id':ids,'type':['город']*3,'region':['a']*3,'_population_axis_row':[True]*3,'population_2010':[100.,10.,30.],'population_2021':[110.,11.,33.],'population_value_quality_2010':['direct_published_census_value']*3,'population_value_quality_2021':['direct_published_census_value']*3,'lat':[50.,50.1,50.2],'lon':[40.,40.1,40.2],'axis_kind':['settlement']*3,'is_additive_source_unit':[True]*3,'accepted_statistical_rural_role2021':pd.array([False,True,True],dtype='boolean')})
   for alias in config['rural_features']:
    config['rural_features'][alias]={'table':'nodes.parquet','field':alias};nodes[alias]=.5
   nodes['bonitet_experimental_lower']=40.;nodes['bonitet_experimental_upper']=60.;nodes['rural_large_city_minutes']=100.
   nodes.to_parquet(model/'nodes.parquet',index=False);pd.DataFrame({'id':ids,'center_id_l1':['c']*3}).to_parquet(model/'memberships.parquet',index=False)
   system={'level':1,'center_id':'c','name':'center','region':'a','lat':50.,'lon':40.,'system_population_known_sum_2010':140.,'system_population_known_sum_2021':154.,'system_population_complete_2010':True,'system_population_complete_2021':True,'rural_external_population_known_sum_2010':40.,'rural_external_population_known_sum_2021':44.,'rural_external_population_complete_2010':True,'rural_external_population_complete_2021':True};pd.DataFrame([system]).to_parquet(model/'systems.parquet',index=False)
   pd.DataFrame({'id':ids,'own_positive_mass':[2.,1.,1.]}).to_parquet(model/'own_mass_components.parquet',index=False);pd.DataFrame({'id':ids}).to_parquet(model/'network_accessibility.parquet',index=False);pd.DataFrame({'level':[1],'center_id':['c'],'own_order_shared_origin_fraction':[float('nan')],'nested_child_configuration':['configuration_unknown'],'nested_shared_origin_fraction':[float('nan')],'modeled_configuration':['structural_assignment_unit']}).to_parquet(model/'system_configurations.parquet',index=False)
   (model/'run_receipt.json').write_text(json.dumps({'status':'COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW','statistical_rural_volume_policy':'known_rural_lowerbound'}));pairs=home/'pairs.parquet';pd.DataFrame({'id':['r1','r2'],'level':[1,1],'center_id':['c','c'],'direct_network_minutes':[10.,30.]}).to_parquet(pairs,index=False);receipt=home/'pairs_receipt.json';receipt.write_text(json.dumps({'status':'ACTUALLY_COMPUTED_ALL_LEVEL_DIRECT_NETWORK_DEMOGRAPHIC_GRADIENTS','source_sha256':{m.label(model/f):m.sha(model/f) for f in ['nodes.parquet','memberships.parquet']},'outputs':{pairs.name:m.sha(pairs)}}));config['own_center_network']={'path':str(pairs),'receipt':str(receipt)};inputs=home/'inputs.json';inputs.write_text(json.dumps(config));(home/'model_config.json').write_text('{}');(output/'effective_analysis_inputs.json').write_text(json.dumps(config));m.ROOT=output;m.INPUT_PATH=inputs
   frame,_=m.prepare(config);self.assertTrue(pd.isna(frame.iloc[0].polycentric_potential));self.assertFalse(frame.iloc[0].configuration_observed);self.assertTrue(pd.isna(frame.iloc[0].configuration_shared_origin_fraction));self.assertEqual(frame.iloc[0].rural_own_center_minutes,25.);self.assertEqual(frame.iloc[0].rural_large_city_minutes,100.);self.assertEqual(frame.iloc[0].rural_members_n,2);self.assertAlmostEqual(frame.iloc[0].log_rural_own_center_minutes,np.log1p(25.))
 def test_unknown_configuration_preserves_basic_family_and_matched_subsets(self):
  rng=np.random.default_rng(91);n=120;d=pd.DataFrame({'level':2,'system_id':['u'+str(i) for i in range(n)],'center_id':['c'+str(i) for i in range(n)],'name':'test','region':np.repeat(np.arange(12),10).astype(str),'lat':rng.uniform(50,60,n),'lon':rng.uniform(30,40,n),'x':rng.normal(size=n),'z':rng.normal(size=n),'poly':rng.integers(0,2,n).astype(float)})
  d.loc[:59,'poly']=np.nan;d['configuration_observed']=d.poly.notna();d['y']=2*d.x+d.z+rng.normal(size=n)
  for col in ['analysis_system2010_primary_source_only','analysis_system2021_primary_source_only','analysis_system2010_primary_supported_only']:d[col]=True
  for col in ['analysis_system2010_secondary_share_of_known_population','analysis_rural_external2010_secondary_share_of_known_population']:d[col]=0.
  c={'minimum_sample':20,'minimum_regions':3,'cv_folds':3,'moran_neighbors':3,'moran_permutations':9,'seed':10}
  a=m.fit_scenario(d,'A_M1_M2__test','y',{'M1':['x'],'M2':['x','z']},c)
  b=m.fit_scenario(d,'B_M1_M2_M3_configuration_observed__test','y',{'M1':['x'],'M2':['x','z'],'M3':['x','z','poly']},c)
  self.assertEqual([r['n'] for r in a[0]],[120,120]);self.assertEqual([r['n'] for r in b[0]],[60,60,60])
  for output in [a,b]:
   pred=pd.DataFrame(output[2]);self.assertTrue(pred.groupby('system_id').cv_fold.nunique().eq(1).all());self.assertEqual(output[6][0]['configuration_unknown_systems'],60)
 def test_unknown_external_core_never_becomes_complete_whole_city_outcome(self):
  ids=['ordinary','ctx:RU-FED-MOW','ctx:RU-FED-SPB'];nodes=pd.DataFrame({'id':ids,'axis_kind':['settlement','external_service_provider','external_service_provider'],'is_additive_source_unit':[True,False,False],'population_2010':[100.,np.nan,np.nan],'population_2021':[110.,np.nan,np.nan]})
  systems=pd.DataFrame({'center_id':ids,'system_population_complete_2010':[True]*3,'system_population_complete_2021':[True]*3,'rural_external_population_complete_2010':[True]*3,'rural_external_population_complete_2021':[True]*3,'system_population_known_sum_2010':[200.,300.,400.]})
  out=m.apply_whole_system_population_scope(systems,nodes)
  self.assertEqual(out.analysis_whole_including_center_population_complete_2010.tolist(),[True,False,False]);self.assertEqual(out.analysis_whole_including_center_population_complete_2021.tolist(),[True,False,False])
  self.assertEqual(out.analysis_whole_system_excluded_unknown_or_invalid_center_population.tolist(),[False,True,True]);self.assertTrue(out.rural_external_population_complete_2010.all());self.assertTrue(out.system_population_complete_2010.all());self.assertEqual(out.system_population_known_sum_2010.tolist(),[200.,300.,400.])
 def test_paths_are_repository_relative_and_absolute_safe(self):
  self.assertEqual(m.resolve('x'),m.REPO/'x');self.assertEqual(m.resolve('/tmp/x'),Path('/tmp/x'));self.assertEqual(m.label(m.REPO/'x'),'x')
if __name__=='__main__':unittest.main()
