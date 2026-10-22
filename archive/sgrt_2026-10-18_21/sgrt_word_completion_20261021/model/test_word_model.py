"""Meaningful safeguards for zero/missing, routing, circularity and hierarchy conservation."""
import importlib.util
from pathlib import Path
import copy
import numpy as np
import pandas as pd

spec=importlib.util.spec_from_file_location('word_model',Path(__file__).with_name('run_word_model.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture():
 nodes=pd.DataFrame({'id':['v','c','h','u'],'name':['Village','Center','Higher','Unlocated'],'type':['деревня','город','город','деревня'],'region':['r']*4,'lat':[55,55.1,55.2,np.nan],'lon':[40,40.1,40.2,np.nan],'axis_kind':['ordinary']*4,'routable_coordinate':[True,True,True,False],'_population_axis_row':[True]*4,'population_2002':[10.,100.,1000.,2.],'population_2010':[0.,110.,1010.,np.nan],'population_2021':[3.,120.,1200.,np.nan]})
 centers=pd.DataFrame({'id':['c','h'],'own_positive_mass':[1.,3.],'intrinsic_empirical_rank':[1,2]})
 travel=pd.DataFrame({'origin_id':['v','v','c','c','h','h'],'destination_id':['c','h','c','h','c','h'],'travel_minutes':[10.,30.,0.,20.,20.,0.],'route_status':['routed']*6})
 config={'dynamic_initial_year':2010,'dynamic_final_year':2021,'model':{'time_decay_minutes':30.,'max_travel_minutes':180.,'outside_mass':.1,'minimum_choice_probability':.1,'competition_ratio':.8}}
 return nodes,centers,travel,config

def test_network_choice_and_self_core_diagnostics():
 n,c,t,g=fixture();x,e=m.huff_assign(n,c,t,g)
 raw=e[e.origin_id.eq('c')].sort_values('gravity',ascending=False).iloc[0]
 core=x.set_index('id').loc['c'];assert core.raw_model_center_id==raw.destination_id
 assert core.assigned_center_id=='c' and core.assigned_travel_minutes==0
 assert core.raw_top_travel_minutes==raw.travel_minutes
 assert x.set_index('id').loc['u','assignment_status']=='unlocated_source_entity'
 assert x.set_index('id').loc['u','assigned_center_id'] is np.nan or pd.isna(x.set_index('id').loc['u','assigned_center_id'])

def test_hierarchy_preserves_every_child_and_population():
 n,c,t,g=fixture();x,e=m.huff_assign(n,c,t,g);levels,edges=m.build_hierarchy(x,c,t,g)
 assert len(levels)==2 and edges.set_index('child_id').loc['c','parent_id']=='h'
 assert ((edges.parent_rank>edges.child_rank)|edges.self_retained).all()
 systems,balance=m.aggregate(n,x,levels,g);assert balance.known_population_conserved.all()
 assert systems[systems.level.eq(2)].n_population_axis_settlements.sum()==3
 assert balance.n_axis.eq(4).all() # Unlocated is retained in the national denominator.
 assert balance[balance.year.eq(2010)].n_missing_population.eq(1).all()
 assert systems.n_observed_zero_2010.sum()==2 # Same true zero retained at both hierarchy levels.

def test_unknown_thematic_attributes_never_become_ethnic_or_dacha():
 n,c,t,g=fixture();n.loc[n.id.eq('c'),'population_2021']=80.;n.loc[n.id.eq('h'),'population_2021']=800.;x,e=m.huff_assign(n,c,t,g);levels,h=m.build_hierarchy(x,c,t,g);s,b=m.aggregate(n,x,levels,g);types=m.classify_word_types(s,n,g)
 assert not types.rule_status.eq('satisfied_observed_indicators').any()
 assert types[types.word_type.isin([5,6,9])].rule_status.eq('unknown_missing_required_indicators').any()
 assert m.tri_all(True,None) is None and m.tri_all(False,None) is False

def test_mass_has_no_outcome_or_modeled_catchment_feedback():
 n,c,t,g=fixture();n['school_count']=[1.,3.,9.,np.nan]
 config={'mass_reference_year':2010,'physical_features':{'education':['school_count'],'healthcare':[],'hospital':[],'trade':[],'finance':[],'administration':[]},'components':[{'name':'own_population','block':'demographic','columns':['population_2010'],'transform':'log1p','year':2010},{'name':'schools','block':'service','physical':'education','transform':'log1p','year':2026},{'name':'missing_housing','block':'housing','columns':['not_available'],'transform':'log1p','year':2010}]}
 left,meta=m.build_mass(n,config)
 changed=n.copy();changed['population_2021']=[1e9]*len(n);changed['own_modeled_catchment_population']=[1e12]*len(n)
 right,_=m.build_mass(changed,config)
 pd.testing.assert_series_equal(left.own_positive_mass,right.own_positive_mass)
 assert left.missing_housing_z.isna().all()
 assert left.own_positive_mass.dropna().gt(0).all()
 assert not left.loc[3,'candidate_center'] # Unknown coordinates never become a routable candidate.
 assert meta[-1]['n_used_in_z']==0

def test_categorical_network_and_exact_word_suburban_belt():
 n,c,t,g=fixture()
 for key in ['origin_id','destination_id']:t[key]=pd.Categorical(t[key],categories=n.id)
 x,edges=m.huff_assign(n,c,t,g)
 context=m.network_context(n,c,t).set_index('id')
 assert context.loc['v','network_suburban_30_60_minutes'] # 30 minutes exactly.
 assert not context.loc['c','network_suburban_30_60_minutes'] # 20 is within30, not30–60.
 assert pd.isna(context.loc['u','network_suburban_30_60_minutes'])
 assert x.assigned_center_id.notna().sum()==3
 levels,hierarchy=m.build_hierarchy(x,c,t,g);systems,balances=m.aggregate(n,x,levels,g)
 assert systems.n_population_axis_settlements.gt(0).all()
 assert set(systems.center_id)<=set(c.id) # Categorical unused IDs cannot become empty phantom systems.

def test_type5_and6_allow_stable_rural_without_causal_claim():
 n,c,t,g=fixture();n['recreation_dacha_evidence']=True
 # Core c declines, rural v is exactly stable; observed rural composition differs.
 n.loc[n.id.eq('c'),'population_2021']=80.;n.loc[n.id.eq('v'),['population_2010','population_2021']]=[10.,10.]
 n['ethnicity_declared_persons2021']=[10.,80.,1200.,np.nan];n['ethnicity_russian_responses2021']=[1.,70.,1100.,np.nan]
 t=t[~((t.origin_id=='v')&(t.destination_id=='h'))]
 x,e=m.huff_assign(n,c,t,g);levels={1:x.assigned_center_id.copy()};systems,balance=m.aggregate(n,x,levels,g)
 types=m.classify_word_types(systems,n,g);picked=types[types.center_id.eq('c')&types.word_type.isin([5,6])]
 assert picked.rule_status.eq('unknown_missing_required_indicators').all()
 import json
 for truth in picked.required_criteria_truth_json.map(json.loads):assert truth['rural_growth_or_stability'] is True
 assert 'ethnocultural_demographic_mechanism' in picked[picked.word_type.eq(6)].unknown_required_criteria_json.iloc[0]
 assert systems.ethnicity_explains_growth_claim.eq(False).all()

def test_rural_context_uses_rural_members_not_city_context():
 n,c,t,g=fixture();n['agro_high_productivity_evidence']=[True,False,False,pd.NA]
 n['climate_gaez_sat_above10_cday_1981_2010']=[1500.,3500.,4000.,np.nan]
 t=t[~((t.origin_id=='v')&(t.destination_id=='h'))]
 x,e=m.huff_assign(n,c,t,g);s,b=m.aggregate(n,x,{1:x.assigned_center_id.copy()},g)
 z=s.set_index('center_id').loc['c']
 assert z.rural_agro_high_productivity_evidence
 assert z.rural_agro_high_productivity_evidence_population_coverage2021==1.
 assert z.rural_climate_gaez_sat_above10_cday_1981_2010_weighted_mean==1500.

def test_restricted_center_eligibility_does_not_protect_grocery_or_atm():
 n,c,t,g=fixture();n['type']='деревня';n['shop']=[1.,0.,0.,0.];n['school']=[0.,1.,0.,0.];n['bank']=[0.,1.,1.,0.]
 config={'center_eligibility':'restricted_multifunctional_or_independent_seat','mass_reference_year':2021,'physical_features':{'education':['school'],'healthcare':[],'hospital':[],'finance':['bank'],'administration':[],'trade':['shop']},'components':[{'name':'population','block':'demographic','columns':['population_2021'],'transform':'log1p','year':2021}]}
 mass,meta=m.build_mass(n,config);chosen=mass.set_index('id').candidate_center
 assert not chosen['v'] # Grocery only.
 assert chosen['c'] # School and bank.
 assert not chosen['h'] # ATM/bank only.
 assert mass.set_index('id').loc['v','physical_trade_positive_witness'] # Still sector provider.

def test_nonnull_secondary_population_is_not_exact_primary_coverage():
 n,c,t,g=fixture()
 n['population_value_quality_2010']='secondary_confidentiality_protected_value_exact_scope_unverified'
 n['population_value_quality_2021']='direct_published_census_value'
 x,e=m.huff_assign(n,c,t,g);s,b=m.aggregate(n,x,{1:x.assigned_center_id.copy()},g)
 assert s.system_population_complete_2010.all()
 assert not s.system_population_exact_primary_supported_2010.any()
 assert s.n_population_secondary_protected_scope_unverified_2010.sum()==3
 assert s.population_secondary_protected_scope_unverified_known_population_share_2010.eq(1).all()
 types=m.classify_word_types(s,n,g)
 assert types.dynamics_uses_secondary_protected_values.all()
 assert not types.population_pair_exact_primary_supported.any()

def test_hierarchy_requires_conditional_parent_threshold():
 n,c,t,g=fixture();c=pd.concat([c,pd.DataFrame({'id':['v'],'own_positive_mass':[3.],'intrinsic_empirical_rank':[2]})],ignore_index=True)
 t=pd.concat([t,pd.DataFrame({'origin_id':['c'],'destination_id':['v'],'travel_minutes':[20.],'route_status':['routed']})],ignore_index=True)
 g['model']['outside_mass']=0.;g['model']['minimum_choice_probability']=.6
 x,e=m.huff_assign(n,c,t,g);levels,h=m.build_hierarchy(x,c,t,g)
 assert h.set_index('child_id').loc['c','self_retained']
 assert levels[2][x.id.eq('c')].iloc[0]=='c'

def test_arrow_route_filter_keeps_required_long_hierarchy_and_context():
 n,c,t,g=fixture();t.loc[t.origin_id.eq('v'),'travel_minutes']=240.
 t=pd.concat([t,pd.DataFrame({'origin_id':['u'],'destination_id':['u'],'travel_minutes':[1.],'route_status':['routed']})],ignore_index=True)
 temporary=Path(__file__).with_name('_test_route_filter.parquet');t.to_parquet(temporary,index=False)
 try:
  g['travel_edges']=str(temporary.resolve());g['model']['hierarchy_max_travel_minutes']=360.
  mass=pd.DataFrame({'id':n.id,'physical_education_count_proxy':[np.nan,1.,np.nan,np.nan]})
  loaded,source=m.load_travel(g,n,c,mass)
  assert not ((loaded.origin_id=='v')&(loaded.destination_id=='c')).any() # Neither low-budget nor required high-tier context.
  assert ((loaded.origin_id=='v')&(loaded.destination_id=='h')).any() # Higher urban context at240minutes is retained.
  assert not loaded.destination_id.eq('u').any() # Irrelevant supplier excluded before pandas.
 finally:temporary.unlink(missing_ok=True)

def test_lowest_first_protects_higher_cores_without_stealing_local_village():
 n,c,t,g=fixture();low=c[c.intrinsic_empirical_rank.eq(1)]
 allrank,e=m.huff_assign(n,c,t,g)
 lowest,e=m.huff_assign(n,low,t,g,core_centers=c)
 assert allrank.set_index('id').loc['v','assigned_center_id']=='h'
 assert lowest.set_index('id').loc['v','assigned_center_id']=='c'
 assert lowest.set_index('id').loc['h','assigned_center_id']=='h'
 levels,hierarchy=m.build_hierarchy(lowest,c,t,g)
 assert levels[2][lowest.id.eq('v')].iloc[0]=='h'
 assert levels[1][lowest.id.eq('v')].iloc[0]=='c'

def test_pending_dependent_can_first_join_at_higher_level():
 n,c,t,g=fixture();t=t[~(t.origin_id.eq('v')&t.destination_id.eq('c'))]
 low=c[c.intrinsic_empirical_rank.eq(1)];x,e=m.huff_assign(n,low,t,g,core_centers=c)
 assert pd.isna(x.set_index('id').loc['v','assigned_center_id'])
 levels,hierarchy=m.build_hierarchy(x,c,t,g)
 assert pd.isna(levels[1][x.id.eq('v')].iloc[0])
 assert levels[2][x.id.eq('v')].iloc[0]=='h'
 row=hierarchy[hierarchy.child_id.eq('v')].iloc[0]
 assert row.pending_dependent_singleton_attachment and row.child_rank==0 and row.parent_rank==2
 systems,balance=m.aggregate(n,x,levels,g)
 assert balance.known_population_conserved.all()
 assert balance[balance.year.eq(2021)].n_assigned.tolist()==[2,3]

def test_observed_final_zero_declines_but_unknown_and_zero_baseline_stay_undefined():
 rates=m.annual_rate([10.,10.,0.,np.nan],[0.,np.nan,10.,0.],11)
 assert rates[0]==-1. and np.isnan(rates[1:]).all()
 n,c,t,g=fixture();t=t[~(t.origin_id.eq('v')&t.destination_id.eq('c'))];t.loc[t.origin_id.eq('v')&t.destination_id.eq('h'),'travel_minutes']=240.
 low=c[c.intrinsic_empirical_rank.eq(1)];x,e=m.huff_assign(n,low,t,g,core_centers=c)
 levels,h=m.build_hierarchy(x,c,t,g)
 assert pd.isna(levels[2][x.id.eq('v')].iloc[0]) # Pending individual180 budget, even if urbanhigher240 edge exists.

def test_source_correction_sensitivity_keeps_identical_membership_grid():
 n,c,t,g=fixture();n['original_population_2010']=n.population_2010;n.loc[n.id.eq('v'),'original_population_2010']=10.
 x,e=m.huff_assign(n,c,t,g);levels,h=m.build_hierarchy(x,c,t,g);systems,b=m.aggregate(n,x,levels,g)
 comparison=m.demographic_source_recovery_sensitivity(n,x,levels,systems,g)
 row=comparison[comparison.level.eq(1)&comparison.center_id.eq('h')].iloc[0]
 assert row.n_population_values_changed_in_system==1
 assert row.original_system_population_known_sum_initial-row.system_population_known_sum_2010==10.
 assert row.membership_grid_identical_between_source_variants
 assert row.system_annual_rate_original_source!=row.system_annual_rate_reviewed_source

def test_monotonic_gmm_boundaries_remove_low_tail_high_rank():
 means=np.array([0.,3.]);variances=np.array([.1,9.]);weights=np.array([.8,.2])
 boundary,details,order=m.monotonic_gmm_boundaries(means,variances,weights)
 assert 0<boundary[0]<3 and 'intersection' in details[0]['method']
 point=boundary[0];density=weights/np.sqrt(variances)*np.exp(-.5*(point-means)**2/variances)
 assert np.isclose(density[0],density[1])
 values=np.array([-5.,0.,1.,3.,8.]);ranks=np.searchsorted(boundary,values,side='right')+1
 assert ranks[0]==1 and np.all(np.diff(ranks)>=0)
 # Raw unequal-variance Gaussian label would wrongly call this weak -5 tail high.
 raw=weights/np.sqrt(variances)*np.exp(-.5*(-5-means)**2/variances)
 assert raw.argmax()==1

def test_higher_rank_parent_must_also_have_stronger_own_mass():
 n,c,t,g=fixture();c.loc[c.id.eq('h'),'own_positive_mass']=.5
 x,e=m.huff_assign(n,c,t,g);levels,h=m.build_hierarchy(x,c,t,g)
 assert h.set_index('child_id').loc['c','self_retained']

def test_custom_word_ci_rank_index_is_copied_without_mass_refit():
 n,c,t,g=fixture();n['custom_ci']=[0.,.25,.9,np.nan]
 cfg={'mass_reference_year':2021,'rank_feature_columns':['custom_ci'],'rank_index':{'column':'custom_ci','transform':'identity','uses_modeled_catchment':True},'model':{'random_seed':1,'maximum_rank_components':2,'minimum_rank_cluster_size':1},'physical_features':{'education':[],'healthcare':[],'hospital':[],'trade':[],'finance':[],'administration':[]},'components':[{'name':'population','block':'demography','columns':['population_2021'],'transform':'log1p','year':2021}]}
 mass,components=m.build_mass(n,cfg);pd.testing.assert_series_equal(mass.custom_ci,n.custom_ci)
 ordered,metadata=m.empirical_ranks(mass,cfg)
 assert ordered.sort_values('custom_ci').intrinsic_empirical_rank.is_monotonic_increasing
 assert metadata['catchment_size_used_for_ranks'] and not metadata['mass_refit_on_catchment']
 altered=n.copy();altered['custom_ci']=[1.,.9,.1,0.];other,_=m.build_mass(altered,cfg)
 pd.testing.assert_series_equal(mass.own_positive_mass,other.own_positive_mass)

def test_observed2021_frame_excludes_unmatched_history_without_imputing_it_zero():
 n,c,t,g=fixture();n['source_record_id_2021']=['s:v','s:c','s:h',None]
 n.loc[n.id.eq('u'),['lat','lon','routable_coordinate']]=[55.,40.,True]
 t=pd.concat([t,pd.DataFrame({'origin_id':['u'],'destination_id':['h'],'travel_minutes':[20.],'route_status':['routed']})],ignore_index=True)
 x,e=m.huff_assign(n,c,t,g);systems,balance=m.aggregate(n,x,{1:x.assigned_center_id.copy()},g);row=systems.set_index('center_id').loc['h']
 assert not row.rural_external_population_complete_2021
 assert row.rural_population_observed2021_frame_complete
 assert row.n_system_historical_units_without_native2021_record==1
 assert pd.isna(n.set_index('id').loc['u','population_2021'])

def test_word_ci_parent_strength_is_ci_while_gravity_remains_mi():
 n,c,t,g=fixture();c['own_positive_mass']=[3.,1.];c['ci']=[.2,.8];g['hierarchy_strength_column']='ci'
 x,e=m.huff_assign(n,c,t,g);levels,h=m.build_hierarchy(x,c,t,g)
 link=h[h.child_id.eq('c')].iloc[0]
 assert link.parent_id=='h' and link.parent_strength>link.child_strength
 assert link.hierarchy_strength_column=='ci'
 g['hierarchy_strength_column']='own_positive_mass'
 _,h=m.build_hierarchy(x,c,t,g);assert h[h.child_id.eq('c')].iloc[0].self_retained

if __name__=='__main__':
 tests=[test_word_ci_parent_strength_is_ci_while_gravity_remains_mi,test_network_choice_and_self_core_diagnostics,test_hierarchy_preserves_every_child_and_population,test_unknown_thematic_attributes_never_become_ethnic_or_dacha,test_mass_has_no_outcome_or_modeled_catchment_feedback,test_categorical_network_and_exact_word_suburban_belt,test_type5_and6_allow_stable_rural_without_causal_claim,test_rural_context_uses_rural_members_not_city_context,test_restricted_center_eligibility_does_not_protect_grocery_or_atm,test_nonnull_secondary_population_is_not_exact_primary_coverage,test_hierarchy_requires_conditional_parent_threshold,test_arrow_route_filter_keeps_required_long_hierarchy_and_context,test_lowest_first_protects_higher_cores_without_stealing_local_village,test_pending_dependent_can_first_join_at_higher_level,test_observed_final_zero_declines_but_unknown_and_zero_baseline_stay_undefined,test_source_correction_sensitivity_keeps_identical_membership_grid,test_monotonic_gmm_boundaries_remove_low_tail_high_rank,test_higher_rank_parent_must_also_have_stronger_own_mass,test_custom_word_ci_rank_index_is_copied_without_mass_refit,test_observed2021_frame_excludes_unmatched_history_without_imputing_it_zero]
 for test in tests:test();print(test.__name__,'PASS')
