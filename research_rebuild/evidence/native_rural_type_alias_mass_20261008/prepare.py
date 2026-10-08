import sys,json,re,collections,importlib.util
from pathlib import Path
import numpy as np,pandas as pd,duckdb,xlrd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'));sys.path.insert(0,str(R/'research_rebuild/evidence/native2010_remaining_county_rule_mass_20261008'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
from scan import nm as base_nm,ty,cn,fm
def nm(v):
 n=base_nm(v);n=re.sub(r'^(?:свх\.?|совхоз)\s+','совхоза ',n);n=re.sub(r'^(?:им\.)\s*','имени ',n);n=re.sub(r'^(?:п|с|д)\.\s*','',n);n=re.sub(r'\s+(?:д\.|с\.|п\.)$','',n)
 return n
F50=R/'research_rebuild/evidence/native2010_remaining_county_rule_mass_20261008';sp=importlib.util.spec_from_file_location('a50',F50/'apply.py');a50=importlib.util.module_from_spec(sp);sp.loader.exec_module(a50)
def baseline():return a50.apply(load(49))
s=baseline();before=s.metrics();bf=fm.finite(s);protected=s.obs[['source_record_id','population','population_value_quality','settlement_name','settlement_type']].copy();pins={str(p):sha(p) for p in [*s.inputs,F50/'application_receipt.json']};sel=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');pins[str(sel)]=sha(sel)
con=duckdb.connect();meta=con.execute('select source_record_id,source_sheet,source_row,source_name_raw from read_parquet(?)',[str(sel)]).fetchdf().set_index('source_record_id');con.close();members=collections.defaultdict(list);idx=collections.defaultdict(list)
for row in s.obs.itertuples():members[s.uf.find(row.source_record_id)].append(row.source_record_id);idx[(int(row.census_year),row.region_norm,nm(row.settlement_name))].append(row.source_record_id)
# Native county association is separate evidence from name/class uniqueness; retain literal source captions and named accepted anchors.
countyanchors=collections.defaultdict(list)
for root,ids in members.items():
 if s.years[root]!={2002,2010,2021} or not all(i in s.point_rows for i in ids) or any(i in s.conflicting_point_targets for i in ids):continue
 a,b,c=[next(s.by_id.loc[i] for i in ids if int(s.by_id.loc[i,'census_year'])==y) for y in [2002,2010,2021]]
 if a.region_norm!=b.region_norm or b.region_norm!=c.region_norm or nm(a.settlement_name)!=nm(c.settlement_name):continue
 ac,cc=cn(a.district_raw),cn(c.district_raw)
 if ac and cc:countyanchors[(a.region_norm,ac,cc)].append({'old_source_record_id':a.source_record_id,'old_name':a.settlement_name,'old_county_raw':a.district_raw,'native2010_source_record_id':b.source_record_id,'current_source_record_id':c.source_record_id,'current_name':c.settlement_name,'current_county_raw':c.district_raw})
excluded=set();scopepins={}
for parent in [F50]:
 for p in parent.glob('baseline49_union_*.gz'):
  q=pd.read_csv(p,keep_default_na=False)
  if 'source_record_id' in q:excluded.update(q.source_record_id.astype(str));scopepins[str(p)]=sha(p)
pins.update(scopepins);rural={'село','деревня','хутор','поселок','посёлок'};diag=[];positives=[];rivals=[];rows=s.obs[s.obs.census_year.eq(2010)&s.obs.is_additive_settlement_record.fillna(False)&~s.obs.region_norm.isin(['москва','санкт петербург','севастополь','еврейская'])].sort_values('population',ascending=False)
for b in rows.itertuples():
 sid=b.source_record_id;root=s.uf.find(sid)
 if s.years[root]!={2010,2021} or sid in excluded or ty(b.settlement_type) not in rural:continue
 current=next(s.by_id.loc[i] for i in members[root] if int(s.by_id.loc[i,'census_year'])==2021)
 if current.source_record_id not in s.point_rows:continue
 allby={y:idx.get((y,b.region_norm,nm(b.settlement_name)),[]) for y in [2002,2010,2021]};reason='';a=None
 for y,ids in allby.items():
  for i in ids:
   r=s.by_id.loc[i];rivals.append({'target2010_source_record_id':sid,'source_record_id':i,'year':y,'name':r.settlement_name,'type':r.settlement_type,'county_raw':r.district_raw,'population':r.population,'is_additive_settlement_record':r.is_additive_settlement_record,'component_years':str(sorted(s.years[s.uf.find(i)]))})
 oldcandidates=[];cc=cn(current.district_raw)
 for aid in allby[2002]:
  ar=s.by_id.loc[aid];ac=cn(ar.district_raw);anchors=countyanchors.get((b.region_norm,ac,cc),[])
  if ty(ar.settlement_type) in rural and ac and cc and (ac==cc or len(anchors)>=3):oldcandidates.append((ar,ac,anchors))
 same10=[]
 for tid in allby[2010]:
  tr=s.by_id.loc[tid];troot=s.uf.find(tid);tc=[i for i in members[troot] if int(s.by_id.loc[i,'census_year'])==2021];county=cn(s.by_id.loc[tc[0],'district_raw']) if len(tc)==1 else cn(tr.district_raw)
  if county==cc:same10.append(tid)
 if not allby[2002]:reason='no_literal_old_native_name'
 elif len(oldcandidates)!=1:reason='old_rural_name_county_ambiguous_or_no_source_county_route'
 elif len(same10)>1:reason='native2010_actual_same_name_same_county_rivals'
 else:
  a,ac,anchors=oldcandidates[0]
  if ty(current.settlement_type) not in rural:reason='native_own_rural_class_incompatible'
  elif s.years[s.uf.find(a.source_record_id)]&s.years[root]:reason='native02_component_occupied_year'
  elif any(i in s.conflicting_point_targets for i in members[root]+members[s.uf.find(a.source_record_id)]):reason='accepted_point_conflict'
  elif any(distance_km((s.point_rows[i]['latitude'],s.point_rows[i]['longitude']),(s.point_rows[current.source_record_id]['latitude'],s.point_rows[current.source_record_id]['longitude']))>5 for i in members[root]+members[s.uf.find(a.source_record_id)] if i in s.point_rows):reason='existing_own_historic_point_contradicts_current'
  else:
   positives.append({'native2002_source_record_id':a.source_record_id,'native2010_source_record_id':sid,'native2021_source_record_id':current.source_record_id,'name':b.settlement_name,'region':b.region_norm,'native02_type':a.settlement_type,'native2010_type':b.settlement_type,'native2021_type':current.settlement_type,'old_county_raw':a.district_raw,'current_county_raw':current.district_raw,'old_county_key':ac,'current_county_key':cc,'protected2010_population':b.population,'county_association_named_anchors_json':json.dumps(anchors[:5],ensure_ascii=False),'county_literal_equal':ac==cc,'point_origin_json':json.dumps(s.point_rows[current.source_record_id],ensure_ascii=False),'whole_region_native02_name_rivals':len(allby[2002]),'whole_region_native2010_name_rivals':len(allby[2010]),'whole_region_native2021_name_rivals':len(allby[2021])});reason='positive_county_qualified_literal_rural_class_sourcecounty_ownpoint'
 diag.append({'native2010_source_record_id':sid,'name':b.settlement_name,'region':b.region_norm,'population':b.population,'native2002_name_rivals':len(allby[2002]),'native2010_name_rivals':len(allby[2010]),'native2021_name_rivals':len(allby[2021]),'outcome':reason})
for n,f in [('discovery_ranked_rural_class_changes.csv.gz',diag),('all_regional_native_name_rivals.csv.gz',rivals),('source_positive_rural_type_candidates.csv.gz',positives)]:pd.DataFrame(f).to_csv(O/n,index=False,compression={'method':'gzip','mtime':0})
scan={'baseline_stage':50,'before':before,'before_finite_all3_all_points':bf,'remaining_current_bound_rural2010_components':len(diag),'gross_2010_population':int(sum(z['population'] for z in diag if np.isfinite(z['population']))),'positive_cases':len(positives),'positive2010_population':int(sum(z['protected2010_population'] for z in positives if np.isfinite(z['protected2010_population']))),'outcomes':dict(collections.Counter(z['outcome'] for z in diag))};(O/'scan_receipt.json').write_text(json.dumps(scan,ensure_ascii=False,indent=2));print(json.dumps(scan,ensure_ascii=False),flush=True)
books={};raw=[];seen=set();edges=[];points=[];proof=[];holds=[]
def original(row):
 sid=row.source_record_id
 if sid in seen:return
 m=meta.loc[sid];p=Path('/workspace/settlements-raw')/row.source_file
 if not p.exists():p=Path(str(row.source_path))
 if p.exists() and str(p) not in pins:pins[str(p)]=sha(p)
 if p.suffix=='.xls' and p.exists():
  if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
  book=books[p];sh=book.sheet_by_name(str(m.source_sheet)) if str(m.source_sheet) in book.sheet_names() else book.sheet_by_index(int(m.source_sheet));rn=int(m.source_row)-1;vals=sh.row_values(rn);pos=[i for i,v in enumerate(vals) if isinstance(v,str) and normalize(v)==normalize(m.source_name_raw)];pos += [i+1 for i in range(len(vals)-1) if isinstance(vals[i],str) and isinstance(vals[i+1],str) and normalize(vals[i]+' '+vals[i+1])==normalize(m.source_name_raw)];assert pos,(sid,'ownlabel');nums=[v for v in vals[min(pos)+1:] if isinstance(v,(int,float)) or (isinstance(v,str) and re.fullmatch(r'[0-9]+',v.strip()))];assert any(float(v)==row.population for v in nums),(sid,'count');assert not re.search('сельсовет|сельское поселение|все население|всего|городское население|сельское население',normalize(m.source_name_raw));raw.append({'source_record_id':sid,'source_file':str(p),'source_sha256':pins[str(p)],'source_locator':f'sheet={sh.name};row1based={rn+1}','raw_own_label':m.source_name_raw,'protected_population':row.population,'protected_quality':row.population_value_quality,'literal_own_label_count_passed':True,'row_cells_json':json.dumps(vals,ensure_ascii=False)})
 else:raw.append({'source_record_id':sid,'source_file':str(p),'source_sha256':pins.get(str(p),''),'source_locator':row.source_locator,'raw_own_label':m.source_name_raw,'protected_population':row.population,'protected_quality':row.population_value_quality,'literal_own_label_count_passed':'existing_selected_published_own_NP_source'})
 seen.add(sid)
def historic_county_witness(row):
 m=meta.loc[row.source_record_id];p=Path('/workspace/settlements-raw')/row.source_file
 if p.suffix!='.xls' or not p.exists():return None
 if p not in books:books[p]=xlrd.open_workbook(str(p),on_demand=True)
 if str(p) not in pins:pins[str(p)]=sha(p)
 book=books[p];sh=book.sheet_by_name(str(m.source_sheet)) if str(m.source_sheet) in book.sheet_names() else book.sheet_by_index(int(m.source_sheet));rn=int(m.source_row)-1;expected=cn(row.district_raw)
 for k in range(rn,max(-1,rn-4000),-1):
  vals=sh.row_values(k)
  for cell in vals:
   if not isinstance(cell,str) or not re.search(r'\bрайон(?:а)?\b',normalize(cell)):continue
   first=normalize(cell).split('район')[0];first=re.sub(r'ского\s*$','ский',first);key=cn(first)
   return {'raw_county_caption':cell,'raw_county_caption_key':key,'expected_historic_county_key':expected,'printed_county_binding_passed':key==expected or key.endswith(' '+expected),'source_file':str(p),'source_sha256':pins[str(p)],'source_locator':f'sheet={sh.name};row1based={k+1}'}
 return None
for z in positives:
 a,b,c=[s.by_id.loc[z[k]] for k in ['native2002_source_record_id','native2010_source_record_id','native2021_source_record_id']];ids=members[s.uf.find(a.source_record_id)]+members[s.uf.find(b.source_record_id)]
 countyproof=historic_county_witness(a)
 if not countyproof or not countyproof['printed_county_binding_passed']:holds.append({**z,'reason':'independent_actual_historical_county_header_missing_or_contradicts_selected_caption','historic_county_witness_json':json.dumps(countyproof,ensure_ascii=False)});continue
 z['historic_county_witness_json']=json.dumps(countyproof,ensure_ascii=False)
 if s.years[s.uf.find(a.source_record_id)]&s.years[s.uf.find(b.source_record_id)]:holds.append({**z,'reason':'sequential_occupied_year'});continue
 try:
  for i in ids:original(s.by_id.loc[i])
  for anchor in json.loads(z['county_association_named_anchors_json']):
   for k in ['old_source_record_id','native2010_source_record_id']:original(s.by_id.loc[anchor[k]])
 except AssertionError as err:
  holds.append({**z,'reason':'literal_raw_source_validation_hold','raw_validation_error':str(err)});continue
 pp=s.point_rows[c.source_record_id];op=Path(pp.get('point_origin_file',''))
 if op.is_file() and str(op) not in pins:pins[str(op)]=sha(op)
 rule='Literal own-name uniquely bound to independently printed historic/current county across ALL compatible rural NP classes; EVERY regional same-name rival retained separately in2002/2010/2021 before graph filtering; actual same-county native2010 rivals hardheld; compatible printed rural NP class changes; independently printed historical and current county, literal equality or at least3 named already accepted native full3 source anchors for specific county-caption association; already admitted2010-current own-place/physical point continuity; native labels and whole counts verified; no count-equality gate or source value/quality edits'
 edges.append({'from_source_record_id':a.source_record_id,'to_source_record_id':b.source_record_id,'relation':'same_place','decision_status':'checked_rule_accepted','case':b.settlement_name+':'+b.source_record_id,'admission_rule':rule,'source_binding_proof':'accepted_native_source_witnesses.csv.gz;actual_native_raw_source_checks.csv.gz;all_regional_native_name_rivals.csv.gz','population_boundary_comparability_asserted':False});s.union(a.source_record_id,b.source_record_id)
 for i in ids:
  if i in s.point_rows:continue
  p={k:v for k,v in pp.items() if k!='point_ledger_path'};p.update(target_source_record_id=i,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_binding_rule=rule,point_use_inference='modern_own_representative_point_reused_on_unique_native_name_rural_class_historical_identity',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False);points.append(p);s.point_rows[i]=dict(p)
 proof.append(z)
s.obs['root']=s.obs.source_record_id.map(s.uf.find);pd.testing.assert_frame_equal(protected,s.obs[protected.columns]);after=s.metrics();af=fm.finite(s)
outputs=[]
for n,f,cols in [('accepted_identity_edge_delta.csv.gz',edges,['from_source_record_id','to_source_record_id','relation','decision_status']),('accepted_point_use_delta.csv.gz',points,['target_source_record_id','latitude','longitude','coordinate_admission_status']),('accepted_native_source_witnesses.csv.gz',proof,None),('actual_native_raw_source_checks.csv.gz',raw,None),('application_holds.csv.gz',holds,None)]:
 (pd.DataFrame(f) if f else pd.DataFrame(columns=cols or ['source_record_id'])).to_csv(O/n,index=False,compression={'method':'gzip','mtime':0});outputs.append(n)
outputs+=['scan_receipt.json','discovery_ranked_rural_class_changes.csv.gz','all_regional_native_name_rivals.csv.gz','source_positive_rural_type_candidates.csv.gz']
r={'baseline_stage':50,'status':'source-pinned rural NP type-class continuation application ready','accepted_cases':len(proof),'edges':len(edges),'point_uses':len(points),'before':before,'after':after,'before_finite_all3_all_points':bf,'after_finite_all3_all_points':af,'net_finite_all3_all_points':{'histories':af['histories']-bf['histories'],'populations_by_year':{y:af['populations_by_year'][y]-bf['populations_by_year'][y] for y in bf['populations_by_year']}},'input_pins':pins,'output_pins':{p:sha(O/p) for p in outputs},'all_source_population_quality_names_types_unchanged':True,'historical_census_coordinate_asserted':False,'boundary_comparability_asserted':False};(O/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins','before','after']},ensure_ascii=False))
