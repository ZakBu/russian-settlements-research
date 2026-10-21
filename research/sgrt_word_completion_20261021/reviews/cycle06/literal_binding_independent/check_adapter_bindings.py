"""Independent synthetic source/flag tests; no national model outcomes read."""
from pathlib import Path
import sys,json,hashlib,contextlib,io,importlib.util,datetime,types
import pandas as pd,numpy as np
H=Path(__file__).resolve().parent;ROOT=H.parents[2];REPO=ROOT.parents[1];sys.path.insert(0,str(ROOT/'model'))
import apply_literal_typology_cycle06 as a
m=a.m

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,j):p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
def build(folder,own_in_nodes=True):
 folder.mkdir();mod=folder/'physical';mod.mkdir();config={'dynamic_initial_year':2010,'dynamic_final_year':2021,'hierarchy_strength_column':'wordci_word_centrality_observed2021_frame_0_1','travel_manifest':str((folder/'synthetic_travel.json').relative_to(REPO))};dump(folder/'synthetic_travel.json',{'synthetic_fixture':True});config['travel_edges']=config['travel_manifest'];dump(folder/'config.json',config)
 nodes=pd.DataFrame({'id':['H','U','T','B'],'lat':55.,'population_2021':[80.,80.,100.,100.],'accepted_formal_settlement_subtype2021':'город','accepted_statistical_rural_role2021':False,'nonchernozem_geographic_evidence':pd.array([True,pd.NA,pd.NA,pd.NA],dtype='boolean'),'nonchernozem_exact_contemporary_geographic_evidence':pd.array([pd.NA]*4,dtype='boolean'),'trade_and_administration_function_evidence':pd.array([pd.NA,pd.NA,True,pd.NA],dtype='boolean'),'basic_administrative_service_function_evidence':pd.array([pd.NA,pd.NA,pd.NA,True],dtype='boolean'),'agro_processing_function_evidence':True})
 rows=[]
 for uid in nodes.id:
  row={'level':2,'center_id':uid,'own_positive_mass':.5,'descriptive_centrality_posthoc_0_1':.2,'center_population_2010':100.,'center_population_2021':80. if uid in ['H','U'] else 100.,'rural_external_population_known_sum_2010':1000.,'rural_external_population_known_sum_2021':1000. if uid=='B' else 800.,'rural_agro_decline_evidence':True,'rural_agro_high_productivity_evidence':True,'rural_land2021_regional_high_sown_share2021_evidence':True,'rural_climate_gaez_sat_above10_cday_1981_2010_weighted_mean':1500.}
  for y in [2010,2021]:
   row[f'system_population_complete_{y}']=True;row[f'rural_external_population_complete_{y}']=True;row[f'system_population_exact_primary_supported_{y}']=True
  rows.append(row)
 systems=pd.DataFrame(rows);nodes['network_peripheral_evidence']=True
 types=m.classify_word_types(systems,nodes,config)
 if not own_in_nodes:nodes=nodes.drop(columns=['trade_and_administration_function_evidence','basic_administrative_service_function_evidence'])
 for name,frame in [('nodes',nodes),('candidate_centers',pd.DataFrame({'id':nodes.id,'wordci_word_centrality_observed2021_frame_0_1':.2})),('own_mass_components',pd.DataFrame({'id':nodes.id,'own_positive_mass':.5})),('word_type_hypotheses',types),('systems',systems),('network_accessibility',pd.DataFrame({'id':nodes.id,'nearest_large_city_network_minutes':200.}))]:frame.to_parquet(mod/(name+'.parquet'),index=False)
 manifest={'configuration_sha256':sha(folder/'config.json'),'model_code_sha256':sha(Path(m.__file__)),'execution_source_snapshots':{name:{'sha256':sha(ROOT/'model'/name)} for name in ['run_word_model_cycle06.py','large_city_accessibility_cycle05.py','configuration_cycle06.py']},'files':{p.name:{'sha256':sha(p)} for p in mod.glob('*.parquet')}};dump(mod/'output_manifest.json',manifest)
 return folder/'config.json',mod

def main():
 if (H/'freeze_manifest.json').exists():raise FileExistsError('Frozen audit: copy this script alone into a new sibling review directory to replay')
 work=H/'runs'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');work.mkdir(parents=True);checks=[];case=work/'synthetic_existing_node_flags';config,model=build(case)
 with contextlib.redirect_stdout(io.StringIO()):a.run(config,model,case/'adapter')
 result=pd.read_parquet(case/'adapter/word_type_hypotheses.parquet');h=result.query("center_id=='H' and word_type==7").iloc[0];u=result.query("center_id=='U' and word_type==7").iloc[0]
 assert bool(h.operational_hypothesis) and not bool(h.operational_hypothesis_exact_contemporary_geography);assert json.loads(h.required_criteria_truth_exact_contemporary_geography_json)['nonchernozem_geographic_zone'] is None
 assert not bool(u.operational_hypothesis) and 'nonchernozem_geographic_zone' in json.loads(u.unknown_required_criteria_json)
 checks.append('Historical NCh positive enables disclosed operational type7 hypothesis while exact contemporary counterpart remains unknown; cold climate alone cannot replace missing geography')
 t=result.query("center_id=='T' and word_type==2").iloc[0];b=result.query("center_id=='B' and word_type==4").iloc[0];assert json.loads(t.required_criteria_truth_json)['trade_and_administration_function'] is True;assert json.loads(b.required_criteria_truth_json)['basic_administrative_service_function'] is True;checks.append('Existing frozen-node own trade/admin and basic-admin flags are read without supplementary layer and survive literal adaptation')
 case=work/'synthetic_unaccepted_review';config,model=build(case,False);own=pd.DataFrame({'id':['H','U','T','B'],'trade_and_administration_function_evidence':True,'basic_administrative_service_function_evidence':True});own.to_parquet(case/'own.parquet',index=False);dump(case/'not_reviewed.json',{'status':'NOT_REVIEWED','source_sha256':sha(case/'own.parquet')})
 rejected=False
 try:
  with contextlib.redirect_stdout(io.StringIO()):a.run(config,model,case/'adapter',case/'own.parquet',case/'not_reviewed.json')
 except ValueError as e:rejected=True
 spec=importlib.util.spec_from_file_location('independent_binder_probe',ROOT/'model_inputs_cycle06/bind_cycle06_final.py');binder=importlib.util.module_from_spec(spec);spec.loader.exec_module(binder);dump(case/'not_accepted.json',{'status':'NOT_ACCEPTED','source_sha256':sha(case/'own.parquet'),'n_failed':0});binder_rejected=False
 try:binder.accepted(case/'not_accepted.json',[sha(case/'own.parquet')])
 except ValueError:binder_rejected=True
 # Exercise actual binder candidate coverage/fingerprint gates on synthetic Ci files.
 for label,ci_ids,declared_count,bad_fingerprint in [('missing_candidate',['C1'],2,False),('extra_candidate',['C1','C2','C3'],3,False),('wrong_receipt_count',['C1','C2'],7,False),('wrong_mass_fingerprint',['C1','C2'],2,True)]:
  f=work/('binder_'+label);f.mkdir();ci_dir=f/'Ci';ci_dir.mkdir();mass=pd.DataFrame({'id':['C1','C2'],'own_positive_mass':[1.,2.],'candidate_center':[True,True]});mass.to_parquet(ci_dir/'fixed_own_mass_components.parquet',index=False);pd.DataFrame({'id':ci_ids,'own_positive_mass':[1.+i for i in range(len(ci_ids))],'word_centrality_observed2021_frame_0_1':.25}).to_parquet(ci_dir/'word_ci_center_features.parquet',index=False)
  (f/'matrix').write_text('synthetic matrix source');(f/'snap').write_text('synthetic snap source');pc={'cycle05_variant':'baseline','settlement_role_policy':{'rural_volume':'known_rural_lowerbound'},'travel_manifest':str((f/'matrix').relative_to(REPO)),'layers':[{'path':str((f/'snap').relative_to(REPO)),'prefix':'road_'}],'required_input_columns':[]};dump(f/'config.json',pc);fingerprint=hashlib.sha256(pd.util.hash_pandas_object(mass[['id','own_positive_mass']],index=False).to_numpy().tobytes()).hexdigest();dump(ci_dir/'receipt.json',{'input_bytes_changed':[],'own_mass_refit':False,'provisional_iterations':1,'input_sha256':{str((f/'config.json').resolve()):sha(f/'config.json')},'selected_rural_volume_policy':'known_rural_lowerbound','variant':'baseline','eligible_centers':declared_count,'own_mass_values_sha256':'wrong' if bad_fingerprint else fingerprint})
  reviewed=[f/'matrix',f/'snap',ROOT/'model_inputs_cycle05/thematic2021/settlement_thematic_features_2021.parquet',ROOT/'model_inputs_cycle06/nonchernozem_context_v1/settlement_nonchernozem_hypothesis_only.parquet'];dump(f/'reviews.json',{'status':'ACCEPTED','n_failed':0,'pinned_sha256':[sha(v) for v in reviewed]});args=types.SimpleNamespace(provisional_config=f/'config.json',ci_directory=ci_dir,transport_review=f/'reviews.json',thematic_review=f/'reviews.json',nonchernozem_review=f/'reviews.json',output=f/'new_final.json')
  try:binder.run(args)
  except ValueError as error:
   expected='fingerprint' if bad_fingerprint else 'eligible candidate identities';assert expected in str(error),(label,str(error));checks.append('Actual binder rejects '+label+' before reading any model source frame')
  else:raise AssertionError('Binder admitted '+label)
 # A positive explicit admission is accepted, while missing failed-count is rejected.
 dump(case/'accepted.json',{'status':'ACCEPTED','n_failed':0,'sha256':sha(case/'own.parquet')});binder.accepted(case/'accepted.json',[sha(case/'own.parquet')]);a.require_source_review(case/'accepted.json',case/'own.parquet');checks.append('Both review gates accept explicit approved status, zero failed checks and exact source SHA')
 for label,extra in [('missing_failed_count',{}),('nonzero_failed_count',{'n_failed':1})]:
  rf=case/(label+'.json');dump(rf,{'status':'ACCEPTED','sha256':sha(case/'own.parquet'),**extra})
  for name,fn in [('adapter',lambda:a.require_source_review(rf,case/'own.parquet')),('binder',lambda:binder.accepted(rf,[sha(case/'own.parquet')]))]:
   try:fn()
   except ValueError:checks.append(name+' rejects '+label+' even with approved status and source SHA')
   else:raise AssertionError(name+' admitted '+label)
 assert rejected and binder_rejected,'Unaccepted review guard regression'
 receipt={'status':'PASS_INDEPENDENT_LITERAL_FLAGS_AND_BINDING_GUARDS','national_model_outputs_read':False,'checks':checks,'own_function_unreviewed_source_rejected':rejected,'binder_explicit_NOT_ACCEPTED_source_rejected':binder_rejected,'reviewed_code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(a.__file__),ROOT/'model_inputs_cycle06/bind_cycle06_final.py']},'findings':([] if rejected else ['Adapter admitted NOT_REVIEWED own-function layer'])+([] if binder_rejected else ['Binder admitted explicit NOT_ACCEPTED source review'])};dump(H/'synthetic_independent_audit.json',receipt);print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
