import sys,json,importlib.util
from pathlib import Path
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
s=load(39)
sp=importlib.util.spec_from_file_location('finite',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm)
before=s.metrics();bf=fm.finite_metrics(s);assert bf=={'histories':138335,'populations_by_year':{'2002':126682581,'2010':123845680,'2021':124452211}}
f=pd.read_csv(O/'whole_region_unique_native02_candidates.csv.gz',dtype=str,keep_default_na=False);raw=pd.read_csv(O/'verified_original_native02_leaf_rows.csv.gz',dtype=str,keep_default_na=False);assert len(f)==3 and raw.raw_own_label_and_first_population_exact.eq('True').all()
pins=json.loads((O/'original_source_pins.json').read_text());pins.update({str(p):sha(p) for p in s.inputs});edges=[];points=[];competitors=[];proof=[]
for z in f.to_dict('records'):
 a=s.by_id.loc[z['old_source_record_id']];b=s.by_id.loc[z['native2010_source_record_id']];n=s.by_id.loc[z['current_source_record_id']];key=(n.region_norm,n.name_norm)
 assert a.name_norm==b.name_norm==n.name_norm and a.region_norm==b.region_norm==n.region_norm
 assert s.years[s.uf.find(a.source_record_id)]=={2002} and s.years[s.uf.find(n.source_record_id)]=={2010,2021}
 for y in [2002,2010,2021]:
  peers=s.obs[s.obs.census_year.eq(y)&s.obs.region_norm.eq(n.region_norm)&s.obs.name_norm.eq(n.name_norm)&s.obs.is_additive_settlement_record.fillna(False)]
  assert len(peers)==1
  for _,p in peers.iterrows():competitors.append({'target_current_source_record_id':n.source_record_id,'census_year':y,'competitor_source_record_id':p.source_record_id,'native_name':p.settlement_name,'native_type':p.settlement_type,'native_county':p.district_raw,'native_population':p.population,'component_years_before_application':str(sorted(s.years[s.uf.find(p.source_record_id)])),'whole_region_all_selected_NP_literal_name_count':len(peers)})
 np=s.point_rows[n.source_record_id];bp=s.point_rows[b.source_record_id];assert distance_km((np['latitude'],np['longitude']),(bp['latitude'],bp['longitude']))<=5
 assert not any(x in s.conflicting_point_targets for x in [a.source_record_id,b.source_record_id,n.source_record_id])
 case=n.settlement_name+':'+a.source_record_id
 rule='Whole-region literal native name unique among ALL selected NP rows separately in2002,2010,2021 before component filtering; ordinary compatible ownNP classes; independently accepted2010/2021 identity and both own representative points within5km; original2002ownNP printed label and count verified; no contradictory owncode/event/point observed; native values and quality unchanged'
 edges.append({'from_source_record_id':a.source_record_id,'to_source_record_id':n.source_record_id,'relation':'same_place','decision_status':'checked_rule_accepted','case':case,'admission_rule':rule,'source_binding_proof':'accepted_source_bindings.csv.gz;verified_original_native02_leaf_rows.csv.gz;all_native_literal_region_name_competitors.csv.gz','population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
 if a.source_record_id not in s.point_rows:
  p={k:v for k,v in np.items() if k!='point_ledger_path'};p['target_source_record_id']=a.source_record_id;p['coordinate_admission_status']='reviewed_extension_rule_accepted';p.update(case=case,coordinate_binding_rule=rule,historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,point_use_inference='modern_own_representative_point_on_native2002_whole_region_unique_literal_identity');points.append(p)
 proof.append(z)
pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(competitors).to_csv(O/'all_native_literal_region_name_competitors.csv.gz',index=False,compression='gzip');pd.DataFrame(proof).to_csv(O/'accepted_source_bindings.csv.gz',index=False,compression='gzip')
for p,h in pins.items():assert sha(Path(p))==h,p
s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();af=fm.finite_metrics(s);net={'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in ['2002','2010','2021']}};assert net=={'histories':3,'populations_by_year':{'2002':4525,'2010':4500,'2021':4108}}
names=['accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','accepted_source_bindings.csv.gz','all_native_literal_region_name_competitors.csv.gz','verified_original_native02_leaf_rows.csv.gz','selected_native02_leaf_metadata.csv.gz','screening_receipt.json']
r={'baseline_stage':39,'status':'Frozen actual39 source/output-pinned CSV application passed','accepted_cases':3,'edges':len(edges),'point_uses':len(points),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':net,'input_pins':pins,'output_pins':{n:sha(O/n) for n in names},'all_native_and_current_competitors_checked_before_component_filter':True,'native_populations_quality_source_spelling_unchanged':True,'historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False}
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
code=(O.parent/'all_cached_native2002_context_followup/apply.py').read_text().replace('stage38','stage39').replace('actual38','actual39').replace('Actual38','Actual39').replace('load(38)','load(39)');(O/'apply.py').write_text(code)
print(json.dumps({'before_finite':bf,'after_finite':af,'net':net,'receipt_sha256':sha(O/'application_receipt.json')},ensure_ascii=False))
