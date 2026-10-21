"""Synthetic scientific edge cases; no empirical inputs or predictions are read."""
import json, hashlib
from pathlib import Path
import pandas as pd
from classify_complete import state,classify,admitted,truth
import numpy as np
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label)
check('missing not stable',state(None,100,True,True,11)[0]=='unavailable')
check('incomplete sum not decline',state(100,1,False,True,11)[0]=='unavailable')
check('missing completeness not true',state(100,100,pd.NA,True,11)[0]=='unavailable')
check('zeros not stable',state(0,0,True,True,11)[0]=='observed_zero_both')
check('emergence separate',state(0,5,True,True,11)[0]=='emergence_observed')
check('extinction separate',state(5,0,True,True,11)[0]=='extinction_observed')
check('negative unavailable',state(-1,5,True,True,11)[0]=='unavailable')
check('infinity unavailable',state(1,float('inf'),True,True,11)[0]=='unavailable')
check('positive unchanged stable',state(50,50,True,True,11)[0]=='stable')
check('threshold equality stable',state(100,100*1.0025**11,True,True,11)[0]=='stable')
check('above threshold growth',state(100,100*1.003**11,True,True,11)[0]=='growth')
check('not applicable distinct',state(None,None,False,False,11,applicable=False)[0]=='not_applicable')
objects={o:{'population':{str(y):f'{o}_{y}' for y in (2002,2010,2021)},'complete':{str(y):f'{o}_complete_{y}' for y in (2002,2010,2021)}} for o in ('own','center','rural','system')}
c={'unit_id_column':'id','kind_column':'kind','level_column':'resolution','rural_member_count_column':'nr','unknown_role_member_count_column':'nu','objects':objects,'quality_columns':['secondary_share','boundary_proven'],'quality_uncertainty_rules':[{'column':'secondary_share','rule':'positive_or_missing','label':'secondary2010'},{'column':'boundary_proven','rule':'not_true','label':'boundary_unproven'}],'unit_role_column':'unit_role','central_object_ids_column':'core_ids','central_object_definition_column':'central_definition','context_witnesses':[{'column':'school','label':'school_positive_witness','kind':'positive_count'}]}
rows=[]
for i,kind in enumerate(('atomic_settlement','functional_union','functional_union','external_context_anchor','superregional_overlay')):
 r={'id':str(i),'kind':kind,'resolution':'empirical_alpha','nr':0,'nu':0,'secondary_share':.2,'boundary_proven':False,'school':0,'unit_role':'territorial_unit','core_ids':'["core"]','central_definition':'one_focal_core'}
 for o,spec in objects.items():
  for y in (2002,2010,2021): r[spec['population'][str(y)]]=100.; r[spec['complete'][str(y)]]=True
 rows.append(r)
rows[2]['nu']=1
rows[3].update({f'{o}_complete_{y}':False for o in objects for y in (2002,2010,2021)})
rows[4]['school']=1
frame=pd.DataFrame(rows); before=frame.copy(deep=True); result,ev=classify(frame,c)
check('all source rows exactly covered',set(result.unit_id)==set(frame.id) and result.unit_id.is_unique)
check('all primary classes nonempty',result.primary_type_id.str.len().gt(0).all())
check('atomic only one independent recent object',result.loc[result.unit_id=='0','observed_dimension_count'].iloc[0]==1)
check('atomic only three period rows',len(ev[ev.unit_id=='0'])==3)
check('local zero zone not treated as observed stable rural',json.loads(result.loc[result.unit_id=='1','trajectory_class'].iloc[0])['rural']=='not_applicable')
check('unknown role not empty rural zone',result.loc[result.unit_id=='2','structural_class'].iloc[0]=='rural_composition_unknown')
check('unknown role rural lowerbound not complete',json.loads(result.loc[result.unit_id=='2','trajectory_class'].iloc[0])['rural']=='unavailable')
check('all missing gets explicit class',result.loc[result.unit_id=='3','classification_confidence'].iloc[0]=='structural_only')
check('zero catalogue no absence claim',result.loc[result.unit_id=='0','functional_context'].iloc[0]=='no_positive_witness_in_available_sources')
check('positive witness retained',result.loc[result.unit_id=='4','functional_context'].iloc[0]=='school_positive_witness')
check('secondary quality preserved',json.loads(result.loc[result.unit_id=='0','source_quality'].iloc[0])['secondary_share']==.2)
check('arbitrary hierarchy label preserved',set(result.level)=={'empirical_alpha'})
check('input unchanged',frame.equals(before))
check('order invariant',classify(frame.iloc[::-1],c)[0].sort_values('unit_id').reset_index(drop=True).equals(result.sort_values('unit_id').reset_index(drop=True)))
extra=frame.iloc[:1].copy(); extra.loc[extra.index[0],'unit_role']='protected_carry'
check('protected carry explicit and not territory',classify(extra,c)[0].iloc[0].structural_class=='protected_carry')
extra=frame.iloc[1:2].copy(); extra.loc[extra.index[0],'core_ids']='["a","b"]';extra.loc[extra.index[0],'central_definition']='all_supported_cores'
check('multicenter explicit',classify(extra,c)[0].iloc[0].structural_class=='multicenter_local_without_rural_zone')
check('no statistical independence claim',not result.statistical_independence_claimed.any())
check('unknown applicability is unavailable',state(100,100,True,True,11,applicable=None)[0]=='unavailable')
extra=frame.iloc[:1].copy(); extra['own_applicable']=pd.NA
import copy
cc=copy.deepcopy(c);cc['objects']['own']['applicable_column']='own_applicable'
x,e=classify(extra,cc)
check('unknown applicability not relabelled by sensitivity',json.loads(x.iloc[0].trajectory_class)['own']=='unavailable' and json.loads(x.iloc[0].alternative_type)=={})
for bad in ({'status':'REJECTED','all_checks_passed':True},{'status':'ACCEPTED','all_checks_passed':True,'n_failures':1},{'all_checks_passed':True}):
 try: admitted(bad);ok=False
 except AssertionError:ok=True
 check('reject unadmitted review '+str(bad),ok)
from audit_central_sets import validate_core_members
for label,args in [('wrong atomic core',(['a'],['b'],True,False,'protected_carry',{'a','b'})),('two atomic members',(['a','b'],['a'],True,False,'territorial_unit',{'a','b'})),('outside additive focalcore',(['a'],['b'],False,True,'context_overlay',{'a','b'})),('unflagged external context',(['a'],['ctx'],False,False,'context_overlay',{'a'}))]:
 try:validate_core_members(*args);ok=False
 except AssertionError:ok=True
 check(label+' rejected',ok)
validate_core_members(['a'],['ctx'],False,True,'context_overlay',{'a'})
check('explicit nonadditive context exception accepted',True)
check('native NumPy true handled',truth(np.bool_(True)) is True)
check('native NumPy false handled',truth(np.bool_(False)) is False)
print(json.dumps({'status':'SYNTHETIC_ONLY_NO_ACTUAL_CLASSIFICATION','checks_passed':len(checks),'checks':checks,'classifier_sha256':hashlib.sha256((Path(__file__).parent/'classify_complete.py').read_bytes()).hexdigest()},ensure_ascii=False,indent=2))
