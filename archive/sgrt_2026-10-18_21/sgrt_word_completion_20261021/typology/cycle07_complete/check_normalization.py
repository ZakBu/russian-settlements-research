"""Synthetic native-member aggregation cases, no empirical source reads."""
import json
import pandas as pd
from normalize_unit_populations import aggregate
nodes=[]
for ident,pop,rural,axis in [('c',100,False,True),('r',20,True,True),('u',7,None,True),('ctx',None,None,False),('missing',None,True,True)]:
 r={'id':ident,'_population_axis_row':axis,'accepted_statistical_rural_role2021':rural,'primary2010_overlay_applied':ident=='r','primary2010_numeric_changed':False,'primary2010_quality_changed':ident=='r'}
 for y in (2002,2010,2021):r[f'population_{y}']=pop;r[f'population_value_quality_{y}']='reviewed_primary_reported_value'
 r['population_2010_prior']=pop;r['population_value_quality_2010_prior']='secondary_confidentiality_protected_value_exact_scope_unverified' if ident=='r' else r['population_value_quality_2010'];nodes.append(r)
n=pd.DataFrame(nodes);n['source_school']=n.id.map({'r':2}).fillna(0)
u=pd.DataFrame([{'unit_id':uid,'core_id':core,'kind':kind,'unit_role':role,'resolution_index':lev} for uid,core,kind,role,lev in [('atom','r','atomic_settlement','territorial_unit',None),('union','c','functional_union','territorial_unit',1),('unknown','c','functional_union','territorial_unit',1),('context','ctx','external_context_anchor','context_overlay',1),('emptycontext','ctx','external_context_anchor','context_overlay',1),('carry','missing','atomic_settlement','protected_carry',None)]])
sets={'atom':['r'],'union':['c','r'],'unknown':['c','r','u'],'context':['ctx','r'],'emptycontext':['ctx'],'carry':['missing']}
m=pd.DataFrame([{'unit_id':uid,'id':ident} for uid,ids in sets.items() for ident in ids]);spec={'context_projection':[{'scope':'focal','kind':'positive_count','source':'synthetic','year':2021,'grain':'ownNP','absence_is_unknown':True,'columns':['source_school'],'output_column':'focal_school_witness','independent_source_unit_columns':['id']}]};r=aggregate(u,m,n,spec) .set_index('unit_id');checks=[]
def check(label,value):assert value,label;checks.append(label)
check('ordinary whole counted once',r.loc['union','system_population_known_sum_2010']==120)
check('rural excludes exact focal',r.loc['union','rural_external_population_known_sum_2010']==20)
check('rural unknown role incomplete',not r.loc['unknown','rural_population_complete_2010'])
check('ordinary whole remains complete despite unknown rural role',r.loc['unknown','system_population_complete_2010'])
check('context own never injected',pd.isna(r.loc['context','center_population_2010']))
check('context whole incomplete despite known rural',not r.loc['context','system_population_complete_2010'])
check('context additive known subtotal separate',r.loc['context','system_known_additive_member_population_sum_2010']==20)
check('emptywhole unknown notzero',pd.isna(r.loc['emptycontext','system_population_known_sum_2010']))
check('emptywhole incomplete',not r.loc['emptycontext','system_population_complete_2010'])
check('atomic prior secondary retains share',r.loc['atom','prior_secondary2010_population_share']==1)
check('atomic new primary current share zero',r.loc['atom','current_secondary2010_population_share']==0)
check('samevalue primary readback counted',r.loc['atom','n_members_primary2010_newly_recovered']==1 and r.loc['atom','n_members_primary2010_numeric_changed']==0 and r.loc['atom','n_members_primary2010_quality_changed']==1)
check('atomic sourcequality uses own series',r.loc['atom','classification_population_exact_primary_supported_2010'])
check('protected carry missing notzero',pd.isna(r.loc['carry','own_population_2010']) and not r.loc['carry','own_population_complete_2010'])
check('all arbitrary sourceunits retained',set(r.index)==set(u.unit_id))
check('positive focal witness retained',r.loc['atom','focal_school_witness'] is True or r.loc['atom','focal_school_witness']==True)
check('catalog zero not absence',pd.isna(r.loc['union','focal_school_witness']))
check('zero inventory not sourceobserved evidence',r.loc['union','focal_school_witness_n_source_observed_members']==0)
check('zero inventory no physical absence claim',pd.isna(r.loc['union','focal_school_witness_actual_source_observed_flag']))
check('one source unit not duplicated',r.loc['atom','focal_school_witness_n_distinct_observed_source_units']==1)
check('known rural population denominator',r.loc['union','rural_known_population2021_denominator']==20)
n['municipal_proxy']=-5.;n['municipal_code']='A';n['metric_observed']=n.id.eq('r')
numeric={'context_numeric_projection':[{'scope':'all_members','source':'synthetic','year':2021,'grain':'municipal','unit':'per1000','value_column':'municipal_proxy','observed_column':'metric_observed','independent_source_unit_columns':['municipal_code'],'output_prefix':'natural_context'}]}
z=aggregate(u,m,n,numeric).set_index('unit_id')
check('negative numeric context preserved',z.loc['union','natural_context_weighted_mean']==-5)
check('numeric coverage usesknownpopulation',abs(z.loc['union','natural_context_source_observed_population_coverage2021']-20/120)<1e-12)
check('municipal repeatedNP not independent',z.loc['union','natural_context_n_distinct_observed_source_units']==1)
check('numeric missing coverage not zero-valued covariate',pd.isna(z.loc['emptycontext','natural_context_weighted_mean']))
fast=aggregate(u,m,n,{}) .sort_values('unit_id').reset_index(drop=True).sort_index(axis=1)
reference=aggregate(u,m,n,{'disable_atomic_fast_path':True}).sort_values('unit_id').reset_index(drop=True).sort_index(axis=1)
pd.testing.assert_frame_equal(fast,reference,check_dtype=False)
check('scalar atom implementation equals full member readback',True)
print(json.dumps({'status':'SYNTHETIC_ONLY_NO_EMPIRICAL_NORMALIZATION','checks_passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
