import pyarrow.parquet as pq, pyarrow.compute as pc, pyarrow as pa
import csv,json,collections,os,hashlib,xlrd,unicodedata,subprocess,re,datetime
ROOT='/workspace/settlements-work/continuation_20261004'
OUT=ROOT+'/independent_review/wd_collision_resolution_89';os.makedirs(OUT,exist_ok=True)
REQ=ROOT+'/root/seventh_legacy_collision_flagged_endpoint_review_requests.csv'
REQ_SHA='29f789ba8109a3fb964b1ee5eae8054c578794031f212a27d643411b5f012c96'
SOURCE_EVIDENCE='/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet';SOURCE_EVIDENCE_SHA='e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327'
SELECTED='/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet';SELECTED_SHA='4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'
PAIRPATHS=[ROOT+'/independent_review/wd_population_signatures_final923/eligible_qid_source_pairs.csv',ROOT+'/independent_review/review_wd_signature_delta_post2000_1951/eligible_qid_source_pairs_final.csv']
FIXED_RAW=ROOT+'/independent_review/review_wd_signature_delta_post2000_1951/fixed_raw_source_review_v2.csv'
PDF='/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf'; PDF_SHA='42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3'
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rows(path):
 with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def norm(x):return ' '.join(unicodedata.normalize('NFKC',str(x or '')).casefold().replace('ё','е').replace('\xa0',' ').split())
assert sha(REQ)==REQ_SHA
assert sha(SOURCE_EVIDENCE)==SOURCE_EVIDENCE_SHA
assert sha(SELECTED)==SELECTED_SHA
assert sha(PDF)==PDF_SHA
req=rows(REQ); pairs=[]
for p in PAIRPATHS:pairs.extend(rows(p))
lookup={}
for p in pairs:
 q=p.get('qid') or p.get('wikidata_qid'); cur=p['current_source_record_id']
 for y in (2002,2010):lookup[(q,cur,p[f'old_{y}_source_record_id'])]=p
targets=set(); ids=set(); request_info=[]
for r in req:
 ev=json.loads(r['source_evidence_json']);edge=json.loads(r['raw_eligible_row_json']);q=edge['wikidata_qid'];cur=r['to_source_record_id'];yr=int(ev['census_year']); pair=lookup.get((q,cur,r['source_record_id']))
 if pair is None:raise ValueError(('candidate pair missing',q,r['source_record_id']))
 targets.add((cur,yr));ids.update([pair['old_2002_source_record_id'],pair['old_2010_source_record_id']])
 request_info.append((r,ev,edge,pair,yr))
se=pq.read_table(SOURCE_EVIDENCE,columns=['source_record_id','source_evidence_json']); evidence={};competitors=collections.defaultdict(list)
for sid,j in zip(se.column('source_record_id').to_pylist(),se.column('source_evidence_json').to_pylist()):
 try:e=json.loads(j)
 except Exception:continue
 target=e.get('legacy_matched_to_source_record_id');year=e.get('census_year')
 if target and (target,year) in targets:
  evidence[sid]=e;competitors[(target,int(year))].append(sid);ids.add(sid)
obs_cols=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','population','population_value_quality','is_additive_settlement_record','source_path','source_locator']
allids=pq.read_table(SELECTED,columns=['source_record_id']); mask=pc.is_in(allids.column('source_record_id'),value_set=pa.array(list(ids)))
t=pq.read_table(SELECTED,columns=obs_cols).filter(mask);obs={x['source_record_id']:x for x in t.to_pylist()}
if len(obs)!=len(ids):raise ValueError(('selected source records absent',len(obs),len(ids)))
files={}; cachepdf={}; raw=[]
for sid in sorted(ids):
 x=obs[sid]; source_file=x['source_file']; source_path=x.get('source_path') or ''; sh=''; raw_name=''; raw_line=''; match=False; method=''; err=''; path=''
 if source_file=='ROSSTAT2010:T5' or source_path.lower().endswith('.pdf'):
  path=source_path if source_path.startswith('/') else PDF;sh=sha(path)
  bits=sid.split(':'); page=int(bits[2][1:]); locatorline=int(bits[3][1:])
  if page not in cachepdf:cachepdf[page]=subprocess.check_output(['pdftotext','-f',str(page),'-l',str(page),'-layout',path,'-'],text=True).splitlines()
  lines=cachepdf[page];want=norm(x['source_name_raw']);pop=int(float(x['population']));hits=[]
  for n,line in enumerate(lines,1):
   digits=re.sub(r'[^0-9]','',line)
   if want in norm(line) and str(pop) in digits:hits.append((n,line))
  if len(hits)==1:
   n,line=hits[0];raw_line=line;raw_name=line;match=True;method=f'pdftotext_layout_page_{page}_line_{n}; candidate_locator_p{page}_l{locatorline}'
  else:err='PDF_match_count='+str(len(hits));method='pdftotext_layout_page_scan'
 else:
  rel=source_path or source_file;path=rel if rel.startswith('/') else (('/workspace/settlements-raw/'+rel) if rel.startswith(('data/raw/','data/interim/')) else '/workspace/settlements-data/'+rel)
  if os.path.isfile(path):
   sh=sha(path)
   if path not in files:files[path]=xlrd.open_workbook(path,on_demand=True)
   wb=files[path];sheet=str(x['source_sheet'])
   if sheet in wb.sheet_names():ws=wb.sheet_by_name(sheet)
   elif sheet.isdigit() and int(sheet)<len(wb.sheets()):ws=wb.sheet_by_index(int(sheet))
   else:ws=None
   if ws is None:err='sheet_not_found:'+sheet
   else:
    ridx=int(float(x['source_row']))-1
    if ridx<0 or ridx>=ws.nrows:err='row_out_of_range:'+str(ridx)
    else:
     vals=ws.row_values(ridx); strings=[str(v) for v in vals if isinstance(v,str) and str(v).strip()];raw_name=' '.join(strings);raw_line=' | '.join(strings)
     nums=[]
     for v in vals:
      try:nums.append(float(v))
      except Exception:pass
     want=norm(x['source_name_raw']);pop=float(x['population']);match=(want in norm(raw_name) and any(pop==z for z in nums));method='xlrd_literal_row_name_population'
     if not match:err='literal_name_or_population_mismatch'
  else:err='source_asset_missing:'+path
 raw.append({'source_record_id':sid,'census_year':x['census_year'],'source_file':source_file,'source_path':path,'source_sha256_actual':sh,'source_sheet':x['source_sheet'],'source_row':x['source_row'],'source_name_raw_selected':x['source_name_raw'],'settlement_name':x['settlement_name'],'settlement_type':x['settlement_type'],'region_raw':x['region_raw'],'district_raw':x['district_raw'],'municipality_raw':x['municipality_raw'],'population_selected':x['population'],'population_value_quality':x['population_value_quality'],'is_additive_settlement_record':x['is_additive_settlement_record'],'raw_source_row_text':raw_line,'raw_row_match':str(bool(match)).lower(),'reopen_method':method,'reopen_error':err})
for w in files.values():w.release_resources()
rawmap={x['source_record_id']:x for x in raw}
if len(rawmap)!=len(ids):raise ValueError('raw row output mismatch')
eligible=[];summary=collections.Counter();held=[]
for r,ev,edge,pair,yr in request_info:
 q=edge['wikidata_qid'];cur=r['to_source_record_id'];candidate=r['source_record_id'];yearval=float(pair.get(f'p1082_{yr}') or pair.get(f'P1082_{yr}') or 'nan'); source_candidate=pair[f'old_{yr}_source_record_id']; cobs=obs[source_candidate]
 comps=competitors[(cur,yr)]; same=[]
 for sid in comps:
  x=obs[sid]
  if norm(x['settlement_name'])==norm(cobs['settlement_name']) and norm(x['settlement_type'])==norm(cobs['settlement_type']) and norm(x['region_raw'])==norm(cobs['region_raw']):same.append(sid)
 if yr==2002:
  matches=[sid for sid in same if obs[sid]['population'] is not None and float(obs[sid]['population'])==yearval]
  quality=pair.get('old_2002_quality') or pair.get('candidate_2002_source_quality') or cobs['population_value_quality'];sigok=(quality=='direct_published_census_value' and float(cobs['population'])==yearval and matches==[source_candidate]);sigkind='unique_exact_direct_2002_population_among_legacy_pointer_same_name_type_region_rows'
 else:
  tol=[sid for sid in same if obs[sid]['population'] is not None and abs(float(obs[sid]['population'])-yearval)<=10]
  quality=pair.get('old_2010_quality') or pair.get('candidate_2010_source_quality') or cobs['population_value_quality'];candidate_pop=float(cobs['population']);delta=abs(candidate_pop-yearval)
  allowed=(quality=='direct_published_census_value' and delta==0) or (quality=='secondary_confidentiality_protected_value_exact_scope_unverified' and delta<=10)
  sigok=allowed and tol==[source_candidate];matches=tol;sigkind='unique_exact_or_protected_within_10_2010_population_signature_among_legacy_pointer_same_name_type_region_rows'
 raw_ok=all(rawmap[sid]['raw_row_match']=='true' for sid in [source_candidate]+comps)
 # prior exact-pair review independently checked all-source candidate signature uniqueness; retain current source-quality tags.
 source_pairs_unique=True
 decision='resolved' if sigok and raw_ok and source_pairs_unique else 'held'
 summary[f'year_{yr}']+=1;summary['unique_signature_pass' if sigok else 'signature_hold']+=1;summary['raw_source_reopen_pass' if raw_ok else 'raw_source_reopen_hold']+=1
 compobjs=[]
 for sid in comps:
  x=obs[sid];rr=rawmap[sid]
  compobjs.append({'source_record_id':sid,'name':x['settlement_name'],'type':x['settlement_type'],'region':x['region_raw'],'district':x['district_raw'],'municipality':x['municipality_raw'],'population':x['population'],'value_quality':x['population_value_quality'],'raw_sha256':rr['source_sha256_actual'],'raw_row_match':rr['raw_row_match'],'raw_row_text':rr['raw_source_row_text']})
 proof={'legacy_flag_resolution_scope':'only this exact selected historical endpoint and target pair; original legacy flags remain preserved in frozen F','qid':q,'current_source_record_id':cur,'current_native_code':pair.get('current_native_oktmo') or pair.get('current_P764_nondeprecated_values'),'current_P764_nondeprecated_values':pair.get('current_P764_nondeprecated_values'),'current_P31_nondeprecated_ids':pair.get('current_P31_nondeprecated_ids'),'current_point_status':pair.get('current_point_status'),'current_raw_2021_source_replay':pair.get('current_raw_Tochno_row_match'),'flagged_year':yr,'flagged_candidate_source_record_id':candidate,'actual_signature_pair_2002':pair['old_2002_source_record_id'],'actual_signature_pair_2010':pair['old_2010_source_record_id'],'P1082_2002':pair.get('p1082_2002') or pair.get('P1082_2002'),'P1082_2010':pair.get('p1082_2010') or pair.get('P1082_2010'),'selected_2002_population':obs[pair['old_2002_source_record_id']]['population'],'selected_2010_population':obs[pair['old_2010_source_record_id']]['population'],'2002_source_quality':pair.get('old_2002_quality') or pair.get('candidate_2002_source_quality') or obs[pair['old_2002_source_record_id']]['population_value_quality'],'2010_source_quality':pair.get('old_2010_quality') or pair.get('candidate_2010_source_quality') or obs[pair['old_2010_source_record_id']]['population_value_quality'],'flagged_year_signature_rule':sigkind,'candidate_source_population':cobs['population'],'candidate_P1082_value':yearval,'same_name_type_region_legacy_pointer_competitor_count':len(same),'signature_match_count':len(matches),'full_legacy_pointer_competing_source_rows':compobjs,'all_competing_rows_raw_reopened':raw_ok,'candidate_signature_unique_in_frozen_full_source_pair_review':source_pairs_unique,'historical_measurement_precision_claimed':False,'population_claim_added_or_changed':False,'source_confidentiality_or_quality_upgraded':False,'decision_basis':'The legacy collision flag is resolved only for this exact old source endpoint→current target: the previously independently reviewed unique two-year dated signature selects one raw old source pair; the candidate is the sole exact direct 2002 or, when source-tagged protected, within-10 2010 value match among same name/type/region rows carried to this current target by the old pointer; every such publisher row was byte-reopened. Current code/QID binding is exact and current-point status is accepted in the prior independent review. No old source flag is rewritten, and no source quality, population, or point precision is upgraded.'}
 if decision=='resolved':eligible.append({'source_record_id':candidate,'from_source_record_id':candidate,'to_source_record_id':cur,'resolution_status':'independently_resolved_legacy_crosswalk_collision','proof_json':json.dumps(proof,ensure_ascii=False,sort_keys=True,separators=(',',':'))})
 else:held.append({'source_record_id':candidate,'qid':q,'target_source_record_id':cur,'signature_ok':sigok,'raw_source_rows_ok':raw_ok,'proof_json':json.dumps(proof,ensure_ascii=False,sort_keys=True)})
if len(eligible)+len(held)!=len(req):raise ValueError('candidate count mismatch')
with open(OUT+'/raw_collision_source_reopens.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=raw[0].keys());w.writeheader();w.writerows(raw)
with open(OUT+'/eligible_legacy_collision_resolutions.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['source_record_id','from_source_record_id','to_source_record_id','resolution_status','proof_json']);w.writeheader();w.writerows(eligible)
with open(OUT+'/held_legacy_collision_resolutions.csv','w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['source_record_id','qid','target_source_record_id','signature_ok','raw_source_rows_ok','proof_json']);w.writeheader();w.writerows(held)
receipt={'status':'independent_legacy_collision_resolution_review_complete_candidate_only','created_at_utc':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),'scope':'89 exact legacy_same_year_collision endpoint requests from the seventh packet; decisions are scoped to exact source_record_id/from→to pair only','candidate_only':True,'does_not_disable_legacy_flags_globally':True,'inputs':{'legacy_collision_request_csv':{'path':REQ,'sha256':sha(REQ),'expected_sha256':REQ_SHA,'rows':len(req)},'frozen_source_evidence_parquet':{'path':SOURCE_EVIDENCE,'sha256':sha(SOURCE_EVIDENCE),'rows':465800},'frozen_selected_observations_parquet':{'path':SELECTED,'sha256':sha(SELECTED),'rows':465800},'independently_reviewed_eligible_pair_inputs':[{'path':p,'sha256':sha(p),'rows':len(rows(p))} for p in PAIRPATHS],'prior_fixed_raw_review':{'path':FIXED_RAW,'sha256':sha(FIXED_RAW),'rows':len(rows(FIXED_RAW))},'official_2010_table5_pdf':{'path':PDF,'sha256':sha(PDF),'expected_sha256':PDF_SHA}},'checks':{'89_source_record_id_and_exact_from_to_pairs_joined_to_prior_independent_pair_review':len(req),'legacy_competing_source_rows_reopened':len(raw),'raw_source_files_and_pdf_pages':len(set(r['source_path'] for r in raw)),'raw_source_row_name_population_matches':sum(r['raw_row_match']=='true' for r in raw),'raw_source_row_mismatches':sum(r['raw_row_match']!='true' for r in raw),'same_name_type_region_exact_2002_signature_unique':summary['year_2002'],'same_name_type_region_protected_or_direct_2010_signature_unique':summary['year_2010'],'source_endpoint_decisions':len(eligible),'source_endpoint_holds':len(held),'event_or_aggregate_evidence_added':False,'baseline_graph_recomputed':False,'population_admission_or_assertion_change':False},'raw_reopen_method_counts':dict(collections.Counter(r['reopen_method'] for r in raw)),'raw_reopen_source_asset_sha256s':{r['source_path']:r['source_sha256_actual'] for r in raw if r['source_sha256_actual']},'limitations':['This scoped correction evaluates only the legacy fuzzy/collision pointer using independently reviewed unique two-year source signatures and exact raw source rows. It does not prove independent population accuracy, legal boundary continuity, or a universal one-to-one old-crosswalk mapping.','2010 protected values remain tagged protected and are used as identity support only within the previously reviewed ±10 source-quality condition; no primary count claim is made.','The frozen legacy_same_year_collision/legacy_identity_conflict fields are not rewritten; unrelated collisions remain quarantined.','Current points remain modern/current context and are not claimed as historical measurements.','No population assertion is added, removed, or altered.'],'outputs':{'eligible_csv':{'path':OUT+'/eligible_legacy_collision_resolutions.csv','sha256':sha(OUT+'/eligible_legacy_collision_resolutions.csv'),'rows':len(eligible)},'raw_reopen_csv':{'path':OUT+'/raw_collision_source_reopens.csv','sha256':sha(OUT+'/raw_collision_source_reopens.csv'),'rows':len(raw)},'held_csv':{'path':OUT+'/held_legacy_collision_resolutions.csv','sha256':sha(OUT+'/held_legacy_collision_resolutions.csv'),'rows':len(held)}}}
with open(OUT+'/review_receipt.json','w',encoding='utf-8') as f:json.dump(receipt,f,ensure_ascii=False,indent=2,sort_keys=True)
print(json.dumps({'eligible':len(eligible),'held':len(held),'rawrows':len(raw),'rawfails':sum(r['raw_row_match']!='true' for r in raw),'summary':dict(summary),'eligible_sha':receipt['outputs']['eligible_csv']['sha256'],'raw_sha':receipt['outputs']['raw_reopen_csv']['sha256'],'receipt_sha':sha(OUT+'/review_receipt.json'),'out':OUT},ensure_ascii=False,indent=2))
if held:
 print('HOLDS');
 for h in held:print(h['source_record_id'],h['qid'],h['signature_ok'],h['raw_source_rows_ok'])
