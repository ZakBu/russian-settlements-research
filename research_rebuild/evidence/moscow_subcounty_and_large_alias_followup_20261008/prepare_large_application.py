import sys,json,shutil
from pathlib import Path
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,distance_km
O=Path(__file__).parent;A=R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008';A.mkdir(exist_ok=True)
s=load(26);before=s.metrics();initial_roots={s.uf.find(sid) for sid in s.by_id.index if s.years[s.uf.find(sid)]=={2002,2010,2021}};edges=[];points=[];reject=[];cases=[];holds=[]
rule='Actual native whole NP rows; own urban classifier/code context with literal type suffix or documented own former name; preserve printed labels, protected population, and quality'
def addcase(name,ids,bid,proof,wrong=False):
 p=s.point_rows[bid];roots={s.uf.find(x) for x in ids};yy=[]
 for r in roots:yy+=list(s.years[r])
 if len(yy)!=len(set(yy)):holds.append({'case':name,'reason':'Real repeated-year component'});return
 for x in ids:
  old=s.point_rows.get(x)
  if old and distance_km((old['latitude'],old['longitude']),(p['latitude'],p['longitude']))>5:
   if not wrong or x!='2002:1_TOM_01_04.xls:0:153':holds.append({'case':name,'reason':'Unresolved real coordinate conflict','target':x});return
   reject.append({'target_source_record_id':x,'rejection_status':'reviewed_rejected_coordinate_claim_only','old_latitude':old['latitude'],'old_longitude':old['longitude'],'origin_ledger':old['point_ledger_path'],'origin_ledger_sha256':sha(Path(old['point_ledger_path'])),'reason':'2011 modern GeoKLADR representative is approximately 86 km from positively own-code-bound current locality; independent Wiki own P721/P625 and current publisher own code15212551000 agree within0.18km. Not a historical measured position.','provider_identifier_binding_status':'Modern provider coordinate rejected; native historical own code binding retained separately','old_point_json':json.dumps(old,ensure_ascii=False)})
 for x in ids:
  if s.uf.find(x)!=s.uf.find(bid):
   edges.append({'from_source_record_id':x,'to_source_record_id':bid,'relation':'same_place','decision_status':'checked_rule_accepted','case':name,'admission_rule':rule,'source_binding_proof':proof,'population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
   s.union(x,bid)
 for x in ids:
  if x not in s.point_rows or any(q['target_source_record_id']==x for q in reject):
   pp={k:v for k,v in p.items() if k!='point_ledger_path'};pp.update(target_source_record_id=x,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_origin_ledger=p['point_ledger_path'],coordinate_origin_ledger_sha256=sha(Path(p['point_ledger_path'])),coordinate_origin_target_source_record_id=bid,admission_rule='Reuse positively admitted own modern representative after source-backed same-place union',point_temporal_interpretation='Retrospective modern representative; not census-date measurement',population_boundary_comparability_asserted=False);points.append(pp)
 cases.append({'case':name,'source_ids_json':json.dumps(ids,ensure_ascii=False),'current_own_source_record_id':bid,'binding':proof,'populations_by_year':json.dumps({str(int(s.by_id.loc[x].census_year)):int(s.by_id.loc[x].population) for x in ids}),'quality_preserved_json':json.dumps({x:s.by_id.loc[x].population_value_quality for x in ids},ensure_ascii=False)})
for r in pd.read_csv(O/'standalone_type_suffix_candidates.csv').to_dict('records'):
 addcase(r['canonical_name'],[r['old2002_source_record_id'],r['from_source_record_id'],r['current_source_record_id']],r['current_source_record_id'],'standalone_type_suffix_actual_source_checks.csv; own classifier '+str(r['historical_own_code_2009'])+' / modern '+str(r['historical_own_code_2011']))
cent=pd.read_csv(O/'large_actual_native_row_and_alias_proofs.csv').query("case=='Centoroy'").iloc[0]
addcase('Центорой → Ахмат-Юрт',['2002:035_e1bf1fa87f_02c_Chechnya.xls:Sheet1:250',cent.source_record_id,cent.current_source_record_id],cent.current_source_record_id,'Own cached article1952452 revision150522565 explicitly preserves Центорой alias; existing own2002→2021 former-name edge; native2010 county from independent two-sided native2002 source anchors')
addcase('Дубровка',['2002:1_TOM_01_04.xls:0:153','ROSSTAT2010:T5:p16:l18','2021:data_allsettlements_anon_156_v20251217.parquet:parquet:173865'],'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:173865','Own urban native2009 code15212551 →2011/current15212551000; printed2002 Дубровский heading and2010primarycounty; currentQ1965217 exactown P721/P625 and rawpublisher owncode/point. Village namesake15212551003 retained.',True)
pd.DataFrame(edges).to_csv(A/'accepted_identity_edge_delta.csv',index=False);pd.DataFrame(points).to_csv(A/'accepted_point_use_delta.csv',index=False);pd.DataFrame(reject).to_csv(A/'accepted_point_rejection_delta.csv',index=False);pd.DataFrame(cases).to_csv(A/'accepted_case_source_bindings.csv',index=False);pd.DataFrame(holds+[{'case':'БЕРДЫКЕЛ / Комсомольское','reason':'Known2010 article explicitly includes Primykanie; atomic population grain unresolved. No edge or credit.'}]).to_csv(A/'held_cases.csv',index=False)
# Reload actual baseline, applying rejection before replacements; no shared accepted input is changed.
s=load(26);s.reject_point_uses(A/'accepted_point_rejection_delta.csv');s.add_deltas([A/'accepted_identity_edge_delta.csv'],[A/'accepted_point_use_delta.csv']);after=s.metrics()
roots={s.uf.find(x) for r in cases for x in json.loads(r['source_ids_json'])};newroots=[r for r in roots if s.years[r]=={2002,2010,2021}];members=s.obs[s.obs.source_record_id.map(s.uf.find).isin(newroots)];assert members.source_record_id.isin(s.point_rows).all();assert not members.source_record_id.isin(s.conflicting_point_targets).any()
for f in ['standalone_type_suffix_actual_source_checks.csv','standalone_type_suffix_candidates.csv','large_actual_native_row_and_alias_proofs.csv','large_2010_two_sided_historical_native_county_anchors.csv']:shutil.copy2(O/f,A/f)
receipt={'status':'Candidate application prepared; explicit stage26 replay passed; awaiting root freeze notice','baseline_stage':26,'before':before,'after':after,'net_population_by_year':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'net_rows_by_year':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'accepted_edges':len(edges),'accepted_point_uses':len(points),'coordinate_only_rejections':len(reject),'finite_all3_components_after_in_batch':len(newroots),'finite_all3_batch_population_by_year':{str(int(y)):int(d.population.sum()) for y,d in members.groupby('census_year')},'source_population_values_and_quality_unchanged':True,'boundary_comparability_asserted':False,'State_API_replay_passed':True,'input_pins':{str(p):sha(p) for p in s.inputs if Path(p).exists() and not str(p).startswith(str(A))},'output_pins':{p.name:sha(p) for p in A.iterdir() if p.name!='application_receipt.json'}}
(A/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({k:receipt[k] for k in ['accepted_edges','accepted_point_uses','coordinate_only_rejections','net_population_by_year','net_rows_by_year','finite_all3_components_after_in_batch','after']},ensure_ascii=False))
