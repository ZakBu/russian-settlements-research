from pathlib import Path
import sys,json,re,collections,ast
import pandas as pd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;s=load(37);before=s.metrics();pins={str(p):sha(p) for p in s.inputs};f=pd.read_csv(O/'refined_native2010_candidates.csv.gz',keep_default_na=False).sort_values('native2010_population',ascending=False);checks=pd.read_csv(O/'all_literal_native2010_source_checks.csv.gz',keep_default_na=False).set_index('source_record_id');refined=pd.read_csv(O/'refined_all_competitor_witness.csv.gz',keep_default_na=False);edges=[];points=[];witness=[];held=[]
def county(v):
 t=normalize(v);t=re.sub(r'(?<=район)\s*[-–—:]\s*(?:все сельское население|всего|все население).*$','',t);t=re.sub(r'(?<=улус)\s*[-–—:]\s*(?:все сельское население|всего|все население).*$','',t)
 if re.search(r'\bсс\b|сельсовет|сельск(?:ий|ое) (?:совет|поселение)|с[.]\s*а[.]',t):return ''
 return county_key(t)
def name(v):
 text=normalize(v);des=r'(?:поселок городского типа|рабочий поселок|дачный поселок|курортный поселок|пгт|рп|кп|дп|город|село|деревня|поселок|хутор|станица|аул|слобода|станция|разъезд|железнодорожная станция|железнодорожный разъезд)';text=re.sub('^'+des+r'\s+','',text);text=re.sub(r'\s*\('+des+r'\)\s*$','',text);text=re.sub(r'\s*,\s*'+des+r'\s*$','',text);text=re.sub(r'\s+(?:пгт|рп|кп|дп)\s*$','',text);return re.sub('[^а-яa-z0-9]+',' ',text).strip()
def tc(v):
 t=normalize(v)
 return 'unknown' if t in ['','объект'] else 'urban' if t in ['город','пгт','рп','поселок городского типа','рабочий поселок','дачный поселок','курортный поселок'] else 'rural'
rootrows={k:g.to_dict('records') for k,g in s.obs.groupby('root')};currentidx=collections.defaultdict(list)
for a in s.obs[s.obs.census_year.eq(2021)&s.obs.is_additive_settlement_record.fillna(False)].to_dict('records'):currentidx[(a['region_norm'],name(a['settlement_name']))].append(a)
targetdup=f.groupby('target2010_source_record_id').current2021_source_record_id.nunique().to_dict();occupied=collections.defaultdict(set)
for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
for z in f.to_dict('records'):
 cid,oid,sid=z['current2021_source_record_id'],z['old2002_source_record_id'],z['target2010_source_record_id'];a=s.by_id.loc[sid];cur=s.by_id.loc[cid];old=s.by_id.loc[oid];cp=s.point_rows[cid];ra,rc=s.uf.find(sid),s.uf.find(cid);reasons=[]
 if s.uf.find(oid)!=rc or s.years[rc]!={2002,2021}:reasons.append('37_endpoint_pair_not_missing2010_anymore')
 if s.years[ra]&s.years[rc]:reasons.append('37_real_duplicate_census_year_component')
 if targetdup[sid]>1:reasons.append('distinct_current_components_claim_same_native2010_target')
 # All ordinary current peers, including full3 and unpointed peers, precede graph filtering.
 peers=[];targetclass=tc(a.type_norm);dc=z['native2010_resolved_county'];keys={name(cur.settlement_name),name(old.settlement_name),name(a.settlement_name)}
 for key in keys:
  for b in currentidx[(cur.region_norm,key)]:
   if b['source_record_id']==cid:continue
   root=s.uf.find(b['source_record_id']);members=rootrows[root];historical=[x for x in members if int(x['census_year']) in [2002,2010]];types={tc(x['type_norm']) for x in historical}-{'unknown'};types=types or {tc(b['type_norm'])};contexts={county(x['district_raw']) for x in members}-{''};matchesclass=targetclass in types or 'unknown' in types;matchescounty=not contexts or not dc or dc in contexts
   if matchesclass and matchescounty:peers.append(b['source_record_id'])
 if peers and not z['native_own_code_agreement']:reasons.append('all_current_same_name_type_county_physical_competitors')
 if any(x in s.conflicting_point_targets for x in [cid,oid,sid]):reasons.append('active_point_conflict')
 op=s.point_rows[oid];sp=s.point_rows.get(sid)
 if distance_km((op['latitude'],op['longitude']),(cp['latitude'],cp['longitude']))>5 or sp and distance_km((sp['latitude'],sp['longitude']),(cp['latitude'],cp['longitude']))>5:reasons.append('point_contradiction_over5km')
 if occupied[(2010,cp['latitude'],cp['longitude'])]-{sid}:reasons.append('distinct_2010_ownNP_already_uses_donor_point')
 check=checks.loc[sid];assert check.literal_pass and check.selected_population_unmodified==a.population
 if reasons:held.append({'current_source_record_id':cid,'target_source_record_id':sid,'name':cur.settlement_name,'population2010':a.population,'reason':' | '.join(reasons),'competing_current_IDs_json':json.dumps(sorted(set(peers)))});continue
 s.union(sid,cid);sourceproof={'raw_target_file':check.raw_source_file,'raw_target_sha256':check.raw_source_sha256,'raw_target_locator':check.raw_source_locator,'raw_target_label':check.raw_own_label,'raw_population_unmodified':a.population,'source_county':dc,'source_county_proof':json.loads(z['source_county_proof_json']),'typed_primary_urban_regionunique':bool(z['typed_primary_urban_regionunique']),'population_growth_flag':bool(z['growth_flag']),'all_source2010_competitors_enumerated_before_graph_gate':True,'all_current_source_competitors':sorted(set(peers))};proof=json.dumps(sourceproof,ensure_ascii=False)
 edges.append({'from_source_record_id':sid,'to_source_record_id':cid,'relation':'same_place','decision_status':'checked_rule_accepted','admission_rule':'all regional native2010 typed competitors before graph gates; own printed county or standalone urban source role; existing accepted02/21 ownpoints agree <=5km; literal source label/count preserved','source_binding_proof':proof,'population_boundary_comparability_asserted':False,'boundary_comparability':'UNKNOWN','population_values_and_quality':'unchanged_selected_native_sources'})
 if sid not in s.point_rows:
  p={k:cp.get(k,'') for k in ['latitude','longitude','coordinate_source_record_id','source_sha256','source_locator','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']};p.update(target_source_record_id=sid,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule='retrospective use of independently admitted current ownNP point through source-bound native2010 identity and accepted02/21 core',point_use_inference='retrospective_continuity_not_historical_coordinate_measurement',point_claim_quality='auto_rule',population_boundary_comparability_asserted=False);points.append(p);s.point_rows[sid]=dict(p,point_ledger_path=str(O/'accepted_point_use_delta.csv'));occupied[(2010,cp['latitude'],cp['longitude'])].add(sid)
 witness.append({**z,'actual37_source_years_before':'[2002,2021] + [2010]','accepted_edge_from_source_record_id':sid,'point_origin_file':cp.get('point_origin_file',''),'point_origin_sha256':cp.get('point_origin_sha256',''),'point_origin_locator':cp.get('point_origin_locator',''),'independent_current_point_source_record_id':cp.get('coordinate_source_record_id',''),'old02_current21_point_distance_km':distance_km((op['latitude'],op['longitude']),(cp['latitude'],cp['longitude'])),'raw_target_source_binding':proof})
after=s.metrics();pd.DataFrame(edges,columns=['from_source_record_id','to_source_record_id','relation','decision_status','admission_rule','source_binding_proof','population_boundary_comparability_asserted','boundary_comparability','population_values_and_quality']).to_csv(O/'accepted_identity_edge_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False);pd.DataFrame(witness).to_csv(O/'accepted_source_binding_witness.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(held).to_csv(O/'actual37_application_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0});pins.update({str(O/'refined_native2010_candidates.csv.gz'):sha(O/'refined_native2010_candidates.csv.gz'),str(O/'all_literal_native2010_source_checks.csv.gz'):sha(O/'all_literal_native2010_source_checks.csv.gz')});r={'baseline_stage':37,'status':'accepted_native2010_source_bound_identity_and_own_point_continuity','accepted_edges':len(edges),'accepted_point_uses':len(points),'baseline':before,'after':after,'net_native_strict_UID_union_gain':{y:{'rows':after[y]['covered_rows']-before[y]['covered_rows'],'population':after[y]['covered_population']-before[y]['covered_population']} for y in before},'held_cases':len(held),'no_new_secondary_counts_or_UIDs':True,'native_population_and_quality_unchanged':True,'historical_coordinate_measurement_asserted':False,'boundary_comparability':'UNKNOWN','input_pins':pins,'raw_source_pins':json.load(open(O/'refined_receipt.json'))['input_raw_pins'],'accepted_ledger_pins':{p.name:sha(p) for p in [O/'accepted_identity_edge_delta.csv.gz',O/'accepted_point_use_delta.csv']}};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','raw_source_pins','baseline','after','accepted_ledger_pins']},ensure_ascii=False))
