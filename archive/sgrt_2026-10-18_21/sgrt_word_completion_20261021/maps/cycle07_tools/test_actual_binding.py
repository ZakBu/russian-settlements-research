"""Synthetic-only binder accounting and strict final-ledger/source binding checks."""
from pathlib import Path
import tempfile,json,subprocess,sys,hashlib
import pandas as pd
P=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix='sgrt_binder_synthetic_') as td:
 h=Path(td)
 def save(name,d):
  p=h/(name+'.parquet');d.to_parquet(p,index=False);return {'path':str(p),'sha256':sha(p)}
 n=pd.DataFrame({'id':['np3:a','np3:b'],'name':['ТестА','ТестБ'],'lat':[55.,56.],'lon':[37.,38.],'population_2021':[1000001.,100.],'source_record_id_2021':['a','b'],'source2021_effective_settlement_type':['город','село'],'source2021_role_has_dated_source':[True,True],'is_additive_source_unit':[True,True]})
 views=[]
 for cap in [30,60]:
  uid='cap'+str(cap);u=pd.DataFrame({'unit_id':[uid],'operational_view_id':[uid],'display_retained':[True],'empirical_resolution_supported':[False],'candidate_cap':[cap],'partition_role':['supported_end_forest'],'kind':['functional_union'],'core_id':['np3:a']});t=pd.DataFrame({'unit_id':[uid],'primary_type_id':['T1'],'primary_type_name':['Синтетическийтип'],'structural_class':['mono'],'unit_role':['territorial_unit']});m=pd.DataFrame({'unit_id':[uid,uid],'id':['np3:a','np3:b'],'is_overlay_membership':[False,False]});ev=pd.DataFrame({'unit_id':[uid],'object':['center'],'period':['2010-2021'],'state':['growth']})
  views.append({'view_id':uid,'partition_role':'supported_end_forest','display_retained':True,'semantics':{'label':str(cap)+'мин','kind':'operational_forest'},'units':save(uid+'units',u),'types':save(uid+'types',t),'memberships':save(uid+'members',m),'trajectory':save(uid+'events',ev)})
 merge=save('merge',pd.DataFrame({'candidate_cap':[30,60],'merge_index':[0,0],'Q':[0.,0.]}));knee=save('knee',pd.DataFrame({'candidate_cap':[30,60],'knee_status':['no-knee']*2,'retained':[False]*2}));boot=save('boot',pd.DataFrame({'candidate_cap':[30]*50+[60]*50,'replicate_id':list(range(50))*2,'status':['no-knee']*100,'ari':[float('nan')]*100}))
 a=h/'SYNTHETIC_NOT_REAL_ADMISSION.json';a.write_text(json.dumps({'status':'ACCEPTED_SYNTHETIC_ONLY'}));ad={'path':str(a),'sha256':sha(a),'status_pointer':['status'],'expected_status':'ACCEPTED_SYNTHETIC_ONLY'}
 c={'family':'cycle07_bottomup','scope_status':'BASELINE_CHECKPOINT_NOT_FINAL477_INTEGRATED','nodes':save('nodes',n),'views':views,'primary_view_id':'cap60','merge_diagnostics':merge,'knee_diagnostics':knee,'bootstrap_diagnostics':boot,'independent_admissions':[ad,ad],'component_integration_status':{'synthetic':'only'},'population_frame_scope':{'source_rows':2,'geographic_partition_rows':2}}
 cp=h/'contract.json';cp.write_text(json.dumps(c));cmd=[sys.executable,str(P/'bind_actual_inputs.py'),'--contract',str(cp),'--output',str(h/'out')];r=subprocess.run(cmd,capture_output=True,text=True);assert r.returncode==0,r.stderr
 cfg=json.load(open(h/'out/map_config.json'));d=pd.read_parquet(h/'out/units.parquet');checks={'actual_bind_execution':True,'separate_partitions_not_pooled':len(d)==2 and len(cfg['retained_resolutions'])==2,'formal_city_guard':pd.read_parquet(h/'out/nodes.parquet').formal_city2021.tolist()==[True,False],'exact_membership_rows_retained':len(pd.read_parquet(h/'out/memberships.parquet'))==4}
 bad=pd.read_parquet(Path(boot['path'])).iloc[:-1];c['bootstrap_diagnostics']=save('incomplete_boot',bad);cp.write_text(json.dumps(c));cmd[-1]=str(h/'badout');r=subprocess.run(cmd,capture_output=True,text=True);checks['incomplete50ledger_rejected']=r.returncode!=0 and not (h/'badout').exists()
 assert all(checks.values());(P/'synthetic_binding_checks.json').write_text(json.dumps({'status':'SYNTHETIC_ONLY_PASS','checks':checks,'binder_sha256':sha(P/'bind_actual_inputs.py'),'actual_source_outputs_read':False},indent=2)+'\n');print(json.dumps(checks))
