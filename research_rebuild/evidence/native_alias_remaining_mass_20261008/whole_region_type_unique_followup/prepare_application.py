import sys,json,importlib.util
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
s=load(39);base=O.parent/'existing_ownpoint_native02_mass';sp=importlib.util.spec_from_file_location('frozen3',base/'apply.py');app=importlib.util.module_from_spec(sp);sp.loader.exec_module(app);app.apply(s)
sp=importlib.util.spec_from_file_location('finite',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
before=s.metrics();bf=fm.finite_metrics(s);assert bf=={'histories':138338,'populations_by_year':{'2002':126687106,'2010':123850180,'2021':124456319}}
f=pd.read_csv(O/'whole_region_exact_type_native02_candidates.csv.gz',dtype=str,keep_default_na=False).to_dict('records');raw=pd.read_csv(O/'verified_original_native02_leaf_rows.csv.gz',dtype=str,keep_default_na=False);assert len(raw)==8 and raw.raw_own_label_and_first_population_exact.eq('True').all()
extra=pd.read_csv(O/'typed_cases_current_native_source_context.csv.gz',dtype=str,keep_default_na=False)
for z in extra.to_dict('records'):
 z['old_source_record_id']='2002:064_d017f142fc_Tyva.xls:Sheet1:395' if z['name']=='Сой' else '2002:006_1916564aaa_02c_Kaluzhskaja.xls:Sheet1:1189';f.append(z)
pins=json.loads((O/'original_source_pins.json').read_text());pins.update({str(p):sha(p) for p in s.inputs});pins[str(base/'application_receipt.json')]=sha(base/'application_receipt.json');pins[str(base/'accepted_identity_edge_delta.csv')]=sha(base/'accepted_identity_edge_delta.csv');pins[str(base/'accepted_point_use_delta.csv')]=sha(base/'accepted_point_use_delta.csv');edges=[];points=[];competitors=[];proof=[];held=[]
for z in f:
 a=s.by_id.loc[z['old_source_record_id']];b=s.by_id.loc[z['native2010_source_record_id']];n=s.by_id.loc[z['current_source_record_id']]
 assert a.name_norm==b.name_norm==n.name_norm and a.region_norm==b.region_norm==n.region_norm
 assert s.years[s.uf.find(a.source_record_id)]=={2002} and s.years[s.uf.find(n.source_record_id)]=={2010,2021}
 exactclass=a.type_norm==b.type_norm==n.type_norm
 np=s.point_rows[n.source_record_id];bp=s.point_rows[b.source_record_id];assert distance_km((np['latitude'],np['longitude']),(bp['latitude'],bp['longitude']))<=5
 bad=[]
 for y in [2002,2010,2021]:
  peers=s.obs[s.obs.census_year.eq(y)&s.obs.region_norm.eq(n.region_norm)&s.obs.name_norm.eq(n.name_norm)&s.obs.is_additive_settlement_record.fillna(False)]
  compatible=peers[peers.type_norm.eq(n.type_norm)] if exactclass else peers
  assert len(compatible)==1
  for _,p in peers.iterrows():
   pp=s.point_rows.get(p.source_record_id);dist=distance_km((np['latitude'],np['longitude']),(pp['latitude'],pp['longitude'])) if pp else None
   shared={str(v) for v in [n.okato,n.oktmo] if not pd.isna(v) and str(v)}&{str(v) for v in [p.okato,p.oktmo] if not pd.isna(v) and str(v)}
   sameq=bool(pp and str(np.get('coordinate_source_record_id','')).startswith('Q') and np.get('coordinate_source_record_id')==pp.get('coordinate_source_record_id'))
   competitor={'target_current_source_record_id':n.source_record_id,'census_year':y,'competitor_source_record_id':p.source_record_id,'native_name':p.settlement_name,'native_type':p.settlement_type,'native_county':p.district_raw,'native_population':p.population,'native_okato':p.okato,'native_oktmo':p.oktmo,'component_years_before_application':str(sorted(s.years[s.uf.find(p.source_record_id)])),'same_native_class_as_target':p.type_norm==n.type_norm,'all_region_exact_name_native_class_count':len(compatible),'whole_region_all_class_name_count':len(peers),'admitted_own_point_json':json.dumps(pp,ensure_ascii=False) if pp else '', 'distance_to_target_current_km':dist,'shared_current_own_code':bool(shared),'same_current_own_QID_point':sameq}
   competitors.append(competitor)
   if y==2021 and p.source_record_id!=n.source_record_id and (shared or sameq):bad.append(competitor)
 if bad:
  held.append({'old_source_record_id':a.source_record_id,'current_source_record_id':n.source_record_id,'name':n.settlement_name,'reason':'Unexplained OTHER-class current owncode/QID collision','competitors':json.dumps(bad,ensure_ascii=False)});continue
 assert not any(x in s.conflicting_point_targets for x in [a.source_record_id,b.source_record_id,n.source_record_id])
 case=n.settlement_name+':'+a.source_record_id
 rule='Original census ownNP printed labels/classes and protected count leaves; exact literal name and unchanged class unique across ALL selected NP rows separately in each whole region/year, retaining OTHER-class namesakes before component filtering; globally unique names permit physicalNP printed-class evolution with original2010NP leaf corroboration; independently accepted2010/2021 identity and own representative points within5km; no contradictory owncode/QID/event/point observed; native values and quality unchanged'
 edges.append({'from_source_record_id':a.source_record_id,'to_source_record_id':n.source_record_id,'relation':'same_place','decision_status':'checked_rule_accepted','case':case,'admission_rule':rule,'source_binding_proof':'accepted_source_bindings.csv.gz;verified_original_native02_leaf_rows.csv.gz;typed_cases_original_native2010_leaf_rows.csv.gz;all_native_literal_region_name_competitors.csv.gz','population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
 if a.source_record_id not in s.point_rows:
  p={k:v for k,v in np.items() if k!='point_ledger_path'};p['target_source_record_id']=a.source_record_id;p['coordinate_admission_status']='reviewed_extension_rule_accepted';p.update(case=case,coordinate_binding_rule=rule,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,point_use_inference='modern_own_representative_point_on_native2002_whole_region_unique_literal_name_class_identity');points.append(p)
 z.update(name=n.settlement_name,population2002=a.population,population2010=b.population,population2021=n.population,native02_type=a.settlement_type,native2010_type=b.settlement_type,current_type=n.settlement_type,unchanged_native_class_in_all3=exactclass,current_own_point_json=json.dumps(np,ensure_ascii=False),native2010_own_point_json=json.dumps(bp,ensure_ascii=False));proof.append(z)
pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(competitors).to_csv(O/'all_native_literal_region_name_competitors.csv.gz',index=False,compression='gzip');pd.DataFrame(proof).to_csv(O/'accepted_source_bindings.csv.gz',index=False,compression='gzip');pd.DataFrame(held,columns=['old_source_record_id','current_source_record_id','name','reason','competitors']).to_csv(O/'current_other_class_holds.csv',index=False)
for p,h in pins.items():assert sha(Path(p))==h,p
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();af=fm.finite_metrics(s);net={'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in ['2002','2010','2021']}};assert net['histories']==len(edges)
names=['accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','accepted_source_bindings.csv.gz','all_native_literal_region_name_competitors.csv.gz','verified_original_native02_leaf_rows.csv.gz','typed_cases_original_native2010_leaf_rows.csv.gz','typed_cases_current_native_source_context.csv.gz','current_other_class_holds.csv','screening_receipt.json']
r={'baseline_stage':39,'baseline_kind':'actual39_plus_frozen_NEW3_explicit_composition','baseline_additional_application':{'receipt':str(base/'application_receipt.json'),'receipt_sha256':sha(base/'application_receipt.json'),'identity_edge_delta':str(base/'accepted_identity_edge_delta.csv'),'identity_edge_sha256':sha(base/'accepted_identity_edge_delta.csv'),'point_use_delta':str(base/'accepted_point_use_delta.csv'),'point_use_sha256':sha(base/'accepted_point_use_delta.csv')},'status':'Frozen actual39 plus NEW3 composition source/output-pinned CSV application passed; not labeled actual40/41','accepted_cases':len(edges),'edges':len(edges),'point_uses':len(points),'current_other_class_holds':len(held),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':net,'input_pins':pins,'output_pins':{n:sha(O/n) for n in names},'all_native_and_current_competitors_checked_before_component_filter':True,'native_populations_quality_source_spelling_unchanged':True,'historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False}
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
code=(base/'apply.py').read_text().replace('apply(load(39))',"state=load(39)\n    spec=importlib.util.spec_from_file_location('baseline_NEW3',O.parent/'existing_ownpoint_native02_mass/apply.py')\n    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.apply(state)\n    apply(state)").replace('stage39 state','actual39 plus frozen NEW3 composed state');(O/'apply.py').write_text(code)
print(json.dumps({'accepted':len(edges),'current_other_class_holds':held,'before_finite':bf,'after_finite':af,'net':net,'receipt_sha256':sha(O/'application_receipt.json')},ensure_ascii=False))
