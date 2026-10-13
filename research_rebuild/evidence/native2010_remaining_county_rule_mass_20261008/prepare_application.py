import sys,json,re,importlib.util,math
from pathlib import Path
import pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize,distance_km
from scan import nm,ty,fm,cn
s=load(49);scan=json.loads((O/'scan_receipt.json').read_text());before=s.metrics();bf=fm.finite(s);assert before==scan['before'] and bf==scan['before_finite_all3_all_points'];protected=s.obs[['source_record_id','population','population_value_quality','settlement_name','settlement_type']].copy()
f=pd.read_csv(O/'positive_literal_native_county_ownpoint_candidates.csv.gz',keep_default_na=False);sel=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');con=duckdb.connect();meta=con.execute('select source_record_id,source_row,source_sheet,source_name_raw from read_parquet(?)',[str(sel)]).fetchdf().set_index('source_record_id');con.close();pins={str(p):sha(p) for p in [sel,*s.inputs,*[O/n for n in ['scan_receipt.json','positive_literal_native_county_ownpoint_candidates.csv.gz','all_native_name_type_county_competitors.csv.gz','ranked_remaining2010_mass.csv.gz']]]};pins.update(scan['exclusion_input_pins']);pins[scan['source_context_pin']['path']]=scan['source_context_pin']['sha256'];raw=[];books={};rawseen=set()
def original(row):
 sid=row.source_record_id
 if sid in rawseen:return
 rawseen.add(sid);m=meta.loc[sid];p=Path('/workspace/settlements-raw')/row.source_file
 if not p.exists():p=Path(str(row.source_path))
 if p.exists() and str(p) not in pins:pins[str(p)]=sha(p)
 if p.suffix=='.xls' and p.exists():
  if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
  b=books[p];sh=b.sheet_by_name(str(m.source_sheet)) if str(m.source_sheet) in b.sheet_names() else b.sheet_by_index(int(m.source_sheet));rn=int(m.source_row)-1;vals=sh.row_values(rn);label=normalize(m.source_name_raw);pos=[i for i,v in enumerate(vals) if isinstance(v,str) and normalize(v)==label];assert pos,(sid,'label')
  numeric=[v for v in vals[min(pos)+1:] if isinstance(v,(int,float)) or (isinstance(v,str) and re.fullmatch(r'[0-9]+',v.strip()))];passed=bool(numeric) and float(numeric[0])==row.population
  if not passed:passed=any(float(v)==row.population for v in numeric)
  assert passed,(sid,'population');assert not re.search('сельсовет|сельское поселение|все население|всего|городское население|сельское население',label),(sid,'aggregate label')
  raw.append({'source_record_id':sid,'source_file':str(p),'source_sha256':pins[str(p)],'source_locator':f'sheet={sh.name};row1based={rn+1}','raw_own_label':m.source_name_raw,'protected_population':row.population,'protected_quality':row.population_value_quality,'literal_label_count_passed':True,'row_cells_json':json.dumps(vals,ensure_ascii=False)})
 else:raw.append({'source_record_id':sid,'source_file':str(p),'source_sha256':pins.get(str(p),''),'source_locator':row.source_locator,'raw_own_label':m.source_name_raw,'protected_population':row.population,'protected_quality':row.population_value_quality,'literal_label_count_passed':'existing_selected_published_own_NP_source_no_new_count_derived'})
edges=[];points=[];proof=[];holds=[];header_checks=[]
def header_break(z):
 good_old=[];good_cur=[]
 for field in ['old_native_two_sided_source_bracket_json','current_native_two_sided_source_bracket_json']:
  for candidate,l,r,lo,hi in json.loads(z.get(field,'[]')):
   kind='old' if field.startswith('old') else 'current';bad=[]
   if kind=='old':
    row=s.by_id.loc[candidate];m=meta.loc[candidate];p=Path('/workspace/settlements-raw')/row.source_file
    if p.suffix!='.xls' or not p.exists():continue
    if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
    if str(p) not in pins:pins[str(p)]=sha(p)
    book=books[p];sh=book.sheet_by_name(str(m.source_sheet)) if str(m.source_sheet) in book.sheet_names() else book.sheet_by_index(int(m.source_sheet))
    for rn in range(lo,hi-1):
     vals=sh.row_values(rn);texts=[normalize(v) for v in vals if isinstance(v,str) and v.strip()]
     if any(re.search(r'сельсовет|сельский совет|с/с|с\./с\.|сельское поселение|городское поселение|\bрайон(?:а)?$',v) for v in texts):bad.append({'row1based':rn+1,'row_cells_json':json.dumps(vals,ensure_ascii=False)})
   else:
    prefix=candidate.rsplit(':',1)[0]+':'
    for rn in range(lo+1,hi):
     sid=prefix+str(rn)
     if sid in s.by_id.index and cn(s.by_id.loc[sid,'district_raw']) not in ['',z['county_key']]:bad.append({'source_record_id':sid,'county_raw':s.by_id.loc[sid,'district_raw']})
   header_checks.append({'target2010_source_record_id':z['native2010_source_record_id'],'kind':kind,'candidate_source_record_id':candidate,'interval_low':lo,'interval_high':hi,'boundary_breaks_json':json.dumps(bad,ensure_ascii=False),'no_printed_boundary_break':not bool(bad)})
   if not bad:(good_old if kind=='old' else good_cur).append((candidate,l,r,lo,hi))
 oldreq=bool(json.loads(z.get('old_native_two_sided_source_bracket_json','[]')));curreq=bool(json.loads(z.get('current_native_two_sided_source_bracket_json','[]')))
 if oldreq and not good_old:return True
 if curreq and not good_cur:return True
 z['old_native_two_sided_source_bracket_json']=json.dumps(good_old,ensure_ascii=False);z['current_native_two_sided_source_bracket_json']=json.dumps(good_cur,ensure_ascii=False);return False
for z in f.to_dict('records'):
 if header_break(z):holds.append({**z,'reason':'actual_printed_native_boundary_break_in_candidate_anchor_interval'});continue
 ids0=[z[k] for k in ['native2002_source_record_id','native2010_source_record_id','native2021_source_record_id']];old,b,current=[s.by_id.loc[x] for x in ids0];roots={s.uf.find(i) for i in ids0};combined=set()
 for rr in roots:
  if combined&s.years[rr]:holds.append({**z,'reason':'sequential_same_year_competing_candidate'});break
  combined|=s.years[rr]
 else:
  if combined!={2002,2010,2021}:holds.append({**z,'reason':'missing_complete_native_triplet'});continue
  assert nm(old.settlement_name)==nm(b.settlement_name)==nm(current.settlement_name);assert ty(old.settlement_type)==ty(b.settlement_type);assert ty(current.settlement_type)==ty(b.settlement_type) or bool(z.get('existing2010_current_identity_allows_printed_class_change'));assert old.region_norm==b.region_norm==current.region_norm
  memberids={i for i in s.by_id.index if s.uf.find(i) in roots};pp=s.point_rows[current.source_record_id];assert all(i not in s.conflicting_point_targets for i in memberids)
  for i in memberids:original(s.by_id.loc[i])
  for anchor in json.loads(z['county_source_anchors_json']):
   for key in ['native_source_record_id','anchor_native2002_source_record_id']:original(s.by_id.loc[anchor[key]])
  op=Path(pp.get('point_origin_file',''))
  if op.is_file():pins[str(op)]=sha(op)
  rule='Literal native own NP name with only printed class-designator/quotation removal; compatible printed native class; unique all-regional same-year name/type/county route before graph filtering; raw own-NP labels and native counts verified; accepted2010-current identity supplies own printed current county over stale extraction where available; bounded accepted native source anchors when county omitted; indistinguishable county namesakes require unique old native row inside a two-sided printed source interval bounded by independently accepted identical own NP anchors, at most120rows, preserving all rival rows; accepted own current physical point reused by continuity; no population equality gate or count/grain edits'
  for row in [old,current]:
   if s.uf.find(row.source_record_id)!=s.uf.find(b.source_record_id):edges.append({'from_source_record_id':row.source_record_id,'to_source_record_id':b.source_record_id,'relation':'same_place','decision_status':'checked_rule_accepted','case':b.settlement_name+':'+b.source_record_id,'admission_rule':rule,'source_binding_proof':'accepted_native_source_binding_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;all_native_name_type_county_competitors.csv.gz','population_boundary_comparability_asserted':False});s.union(row.source_record_id,b.source_record_id)
  for i in memberids:
   if i in s.point_rows:continue
   p={k:v for k,v in pp.items() if k!='point_ledger_path'};p.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule=rule,point_use_inference='modern_own_representative_point_reused_on_source_bound_historical_identity',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,case=b.settlement_name+':'+b.source_record_id);points.append(p);s.point_rows[i]=dict(p)
  proof.append({**z,'all_component_native_IDs_json':json.dumps(sorted(memberids)),'source_positive_point_origin_json':json.dumps(pp,ensure_ascii=False),'protected_native_value_quality_unchanged':True})
for name,rows,cols in [('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('accepted_native_source_binding_witnesses.csv.gz',proof,None),('actual_native_raw_source_checks.csv.gz',raw,None),('application_holds.csv.gz',holds,None),('actual_source_anchor_boundary_checks.csv.gz',header_checks,None)]:
 (pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols or ['source_record_id'])).to_csv(O/name,index=False,compression={'method':'gzip','mtime':0})
s.obs['root']=s.obs.source_record_id.map(s.uf.find);pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);after=s.metrics();af=fm.finite(s);outputs=['accepted_identity_edge_delta.csv.gz','accepted_point_use_delta.csv.gz','accepted_native_source_binding_witnesses.csv.gz','actual_native_raw_source_checks.csv.gz','application_holds.csv.gz','actual_source_anchor_boundary_checks.csv.gz']
r={'baseline_stage':49,'status':'actual49 source/count verified consolidated native mass application ready for independent replay','accepted_cases':len(proof),'edges':len(edges),'point_uses':len(points),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},'net_population_by_year':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'input_pins':pins,'output_pins':{p:sha(O/p) for p in outputs},'all_regional_rivals_before_graph_filter':True,'all_source_population_quality_names_unchanged':True,'historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False,'qualified_sidecar_separate_no_new_rows':True};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins','before','after']},ensure_ascii=False))
