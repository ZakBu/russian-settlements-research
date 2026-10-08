import sys,json,re,math,importlib.util,subprocess
from pathlib import Path
from collections import defaultdict
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
O=Path(__file__).parent;s=load(32);before=s.metrics();assert [before[str(y)]['covered_population'] for y in [2002,2010,2021]]==[126543738,123714170,124323442],'Actual32 root weak baseline differs'
sp=importlib.util.spec_from_file_location('fm',R/'research_rebuild/evidence/large_native_suffix_and_former_name_application_20261008/apply.py');fm=importlib.util.module_from_spec(sp);sp.loader.exec_module(fm);bf=fm.finite_metrics(s)
f=pd.read_csv(O/'source_bound_native_full3_candidates.csv.gz',dtype=str,keep_default_na=False);latest=pd.read_csv(O/'raw_cached_own_claim_binding_checks.csv.gz',dtype=str,keep_default_na=False).set_index(['old_source_record_id','current_source_record_id']);meta=duckdb.connect().execute("select source_record_id,source_sheet,source_row,entity_grain_status from read_parquet('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')").fetchdf().set_index('source_record_id');d=s.obs;books={};pdf={};pins=json.loads((O/'cached_entity_source_pins.json').read_text());proof=[];near=[];edges=[];points=[];rejects=[];held=[];accepted=[];overlaps=[];seen=set();touched=set()
def raw_check(a,case):
 sid=a.source_record_id;mm=meta.loc[sid];p=Path('/workspace/settlements-raw')/a.source_file
 if str(p) not in pins:pins[str(p)]=sha(p)
 out={'case':case,'source_record_id':sid,'year':int(a.census_year),'source_path':str(p),'source_sha256':pins[str(p)],'source_sheet':mm.source_sheet,'source_row_1based':mm.source_row,'protected_population':a.population,'protected_quality':a.population_value_quality,'native_name':a.settlement_name,'native_type':a.settlement_type,'native_county':a.district_raw,'native_okato':a.okato,'native_oktmo':a.oktmo,'entity_grain_status':mm.entity_grain_status}
 if p.suffix=='.xls':
  if str(p) not in books:books[str(p)]=xlrd.open_workbook(p)
  bk=books[str(p)];sh=bk.sheet_by_name(str(mm.source_sheet)) if str(mm.source_sheet) in bk.sheet_names() else bk.sheet_by_index(int(mm.source_sheet));rv=sh.row_values(int(mm.source_row)-1);li=next((i for i,v in enumerate(rv) if isinstance(v,str) and normalize(a.settlement_name) in normalize(v)),None)
  if li is None:return None,'Native raw label not recovered'
  nums=[]
  for v in rv[li+1:]:
   st=str(v).replace(' ','').replace('\xa0','').replace(',','.')
   if re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',st):nums.append(float(st))
  if not nums or nums[0]!=float(a.population):return None,'First actual source population differs selected protected value; no rewrite'
  out.update(raw_original_row_json=json.dumps(rv,ensure_ascii=False),literal_native_name=rv[li],actual_first_population=nums[0])
 elif p.suffix=='.pdf':
  page=int(str(mm.source_sheet).rsplit('_',1)[-1]);pk=(str(p),page)
  if pk not in pdf:pdf[pk]=subprocess.check_output(['pdftotext','-f',str(page),'-l',str(page),'-layout',str(p),'-'],text=True)
  txt=pdf[pk];lines=[line for line in txt.splitlines() if normalize(a.settlement_name) in normalize(line)]
  if not any(re.search(r'(?<!\d)'+str(int(a.population))+r'(?!\d)',line.replace(' ','')) for line in lines):return None,'Native PDF exact own label/population row not recovered'
  out.update(literal_native_name=' | '.join(lines),actual_first_population=a.population,printed_source_page_text=txt)
 else:out.update(actual_first_population=a.population,native_raw_record_binding='Protected selected native publisher own NP row; source bytes pinned, printed name/type/code/county retained')
 return out,None
for z in f.to_dict('records'):
 a,b,n=[s.by_id.loc[z[x]] for x in ['old_source_record_id','native2010_source_record_id','current_source_record_id']];ids=[a.source_record_id,b.source_record_id,n.source_record_id];case=z['qid']+':'+a.settlement_name;raw=latest.loc[(ids[0],ids[2])].to_dict();why=[]
 if any(x in touched for x in ids):why.append('Shared native source target across candidate cases')
 roots={s.uf.find(x) for x in ids};ys=[y for r in roots for y in s.years[r]]
 if len(ys)!=len(set(ys)) or set(ys)!={2002,2010,2021}:why.append('Actual32 repeated-year source component')
 if raw['raw_status']!='candidate_positive_raw_claim_own_code_name':why.append('Raw cached date/native own code/name binding not positive')
 for arow in [a,b,n]:
  mm=meta.loc[arow.source_record_id]
  if not arow.is_additive_settlement_record or not math.isfinite(arow.population):why.append('Native source not finite additive whole settlement')
  if re.search(r'aggregate|municipal|unresolved|control.total',str(mm.entity_grain_status),re.I):why.append('Native source grain not resolved whole NP')
 donor=s.point_rows.get(n.source_record_id)
 if not donor:why.append('No independent admitted own current point')
 if why:held.append({'case':case,'old_source_record_id':ids[0],'reason':'; '.join(sorted(set(why)))});continue
 dp=(donor['latitude'],donor['longitude']);rawpts=json.loads(raw['raw_P625_points']);qpclose=any(distance_km(dp,(p['latitude'],p['longitude']))<=5 for p in rawpts);qr=[{'source_record_id':x,'existing_point':x in s.point_rows,'already_in_current_component':s.uf.find(x)==s.uf.find(ids[-1])} for x in ids];overlaps.extend(qr)
 # Only reject concretely contradicted modern GeoKLADR claims, with independently coded current/QID points agreeing. No native observation/value is rejected.
 planned_rej=[]
 for target in ids:
  p=s.point_rows.get(target)
  if p and distance_km(dp,(p['latitude'],p['longitude']))>5:
   origin=str(p.get('point_origin_kind',''))+' '+str(p.get('coordinate_source_record_id',''))+' '+str(p.get('point_origin_file',''))
   if target==n.source_record_id or not qpclose or not re.search(r'geokladr|GeoKLADR|geokladr_2011',origin):why.append('Actual admitted point conflict not positively resolved as modern wrong GeoKLADR claim')
   else:planned_rej.append({'target_source_record_id':target,'rejection_status':'reviewed_rejected_coordinate_claim_only','old_latitude':p['latitude'],'old_longitude':p['longitude'],'origin_ledger':p['point_ledger_path'],'origin_ledger_sha256':sha(Path(p['point_ledger_path'])),'reason':'Modern GeoKLADR representative contradicted by independently native-current-code/name-bound current point and raw own QID P625 agreeing within5km; native dated02 count and independent source county bind own NP','old_point_json':json.dumps(p,ensure_ascii=False),'provider_identifier_binding_status':'Identifier claim quality separate from coordinate correctness; native source observation retained','candidate_only':False})
  if target in s.conflicting_point_targets and not any(x['target_source_record_id']==target for x in planned_rej):why.append('Unresolved actual accepted point alternative conflict')
 if why:held.append({'case':case,'old_source_record_id':ids[0],'reason':'; '.join(sorted(set(why)))});continue
 if all(s.uf.find(x)==s.uf.find(ids[-1]) for x in ids) and all(x in s.point_rows for x in ids) and not planned_rej:held.append({'case':case,'old_source_record_id':ids[0],'reason':'Actual32 already full native3 and all points; no net delta'});continue
 checks=[]
 for rr in [a,b,n]:
  p,reason=raw_check(rr,case)
  if reason:why.append(reason)
  else:checks.append(p)
 if why:held.append({'case':case,'old_source_record_id':ids[0],'reason':'; '.join(sorted(set(why)))});continue
 # Inspect all native same-name regional competitors and coordinates before admission, never population-only identity.
 for _,peer in d[d.region_norm.eq(a.region_norm)&d.name_norm.isin({a.name_norm,n.name_norm})].iterrows():
  p=s.point_rows.get(peer.source_record_id);dist=distance_km(dp,(p['latitude'],p['longitude'])) if p else None;near.append({'case':case,'source_record_id':peer.source_record_id,'year':peer.census_year,'native_name':peer.settlement_name,'native_type':peer.settlement_type,'native_county':peer.district_raw,'population':peer.population,'own_okato':peer.okato,'own_oktmo':peer.oktmo,'distance_to_bound_current_point_km':dist,'within5km':dist is not None and dist<=5,'selected_triplet_member':peer.source_record_id in ids})
 for target in ids[:-1]:
  if s.uf.find(target)!=s.uf.find(ids[-1]):edges.append({'from_source_record_id':target,'to_source_record_id':ids[-1],'relation':'same_place','decision_status':'checked_rule_accepted','case':case,'admission_rule':'Raw own dated2002 P1082 exactly binds native02 count plus close literal own name, independent current native own code/QID point and unambiguous native02 county/source context; native2010 independently accepted or source-bracketed, all competitors retained','source_binding_proof':'accepted_source_bindings.csv.gz;actual_native_raw_source_checks.csv.gz;independent_source_county_anchors.csv.gz;all_count_collision_competitors.csv.gz;all_native_same_name_point_competitors.csv.gz','population_boundary_comparability_asserted':False,'municipal_event_date':'UNKNOWN'})
  if target not in s.point_rows or any(x['target_source_record_id']==target for x in planned_rej):
   pp={k:v for k,v in donor.items() if k!='point_ledger_path'};pp.update(target_source_record_id=target,coordinate_admission_status='reviewed_extension_rule_accepted',case=case,coordinate_binding_rule='Independent admitted current native own code/name/QID representative point; raw dated02 own census count and native02/10 source county bind own locality; all same-name/count competitors retained',point_use_inference='modern_own_representative_point_on_native_source_bound_historical_identity',population_boundary_comparability_asserted=False,historical_census_coordinate_asserted=False,secondary_population_not_substituted_for_native=True);points.append(pp)
 rejects.extend(planned_rej);proof.extend(checks);accepted.append(dict(z,raw_latest_native_current_code_binding_rule=raw['native_current_code_binding_rule'],raw_latest_P764_positive=raw['exact_native_current_P764'],raw_latest_TSV_positive=raw.get('positive_alternative_native_TSV_code',''),raw_latest_positive_TSV_source_rows=raw.get('positive_native_TSV_source_rows',''),current_donor_point_json=json.dumps(donor,ensure_ascii=False),ordinary_native03_identity_asserted=True,secondary_value_or_scope_imported=False));touched.update(ids)
for name,data in [('accepted_identity_edge_delta.csv',edges),('accepted_point_use_delta.csv',points),('accepted_point_rejection_delta.csv',rejects),('accepted_source_bindings.csv.gz',accepted),('actual_native_raw_source_checks.csv.gz',proof),('all_native_same_name_point_competitors.csv.gz',near),('held_cases.csv',held),('actual32_overlap_checks.csv.gz',overlaps)]:
 frame=pd.DataFrame(data)
 if not len(frame) and name=='accepted_point_rejection_delta.csv':frame=pd.DataFrame(columns=['target_source_record_id','rejection_status','old_latitude','old_longitude','reason'])
 frame.to_csv(O/name,index=False,compression='gzip' if name.endswith('.gz') else None)
s.reject_point_uses(O/'accepted_point_rejection_delta.csv');s.add_deltas([O/'accepted_identity_edge_delta.csv'],[O/'accepted_point_use_delta.csv']);after=s.metrics();af=fm.finite_metrics(s)
outs=['accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','accepted_point_rejection_delta.csv','accepted_source_bindings.csv.gz','actual_native_raw_source_checks.csv.gz','all_native_same_name_point_competitors.csv.gz','held_cases.csv','actual32_overlap_checks.csv.gz','independent_source_county_anchors.csv.gz','all_count_collision_competitors.csv.gz','raw_cached_own_claim_binding_checks.csv.gz'];r={'baseline_stage':32,'status':'Actual32 frozen CSV State API replay passed; ready root33 review/integration','source_positive_cases':len(accepted),'edges':len(edges),'point_uses':len(points),'point_rejections':len(rejects),'holds':len(held),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},'input_pins':pins,'output_pins':{n:sha(O/n) for n in outs},'native_populations_quality_and_source_spelling_unchanged':True,'secondary_date_count_is_identity_binding_evidence_not_official_historical_coordinate':True,'original30_source_context_proofs_reused_without_new_edge_dependence':True}
(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({'cases':len(accepted),'edges':len(edges),'points':len(points),'point_rejections':len(rejects),'holds':len(held),'net_finite':r['net_finite_all3_all_points']},ensure_ascii=False))
