from pathlib import Path
import csv,json,re,unicodedata,hashlib,collections
import pyarrow.parquet as pq
H=Path(__file__).resolve().parent;E=H.parent
OCR=E/'extended_population_sources_20261013/bulk_ocr_locality_candidates.csv';B=E/'extended_population_history_20261013/current_physical_bindings.parquet';P=E/'extended_population_history_20261013/population_history_long.parquet'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(v):return ' '.join(unicodedata.normalize('NFKC',str(v or '')).casefold().replace('ё','е').split())
def cleanname(v):return norm(re.sub(r'[.|]+',' ',str(v or '')).strip())
def region(v):
 # Only case/spacing and literal administrative noun forms; historical aliases not guessed.
 s=norm(v);s=re.sub(r'\b(область|обл\.|край|республика|асср)\b',' ',s);return ' '.join(s.split())
def integer(v):
 s=str(v or '').strip().strip('|').strip()
 if re.fullmatch(r'[0-9\s]+',s):return int(re.sub(r'\s','',s)) if re.search(r'\d',s) else None
 return None
bindings=pq.read_table(B).to_pylist();idx=collections.defaultdict(list)
for b in bindings:idx[norm(b['native_name'])].append(b)
pop=collections.defaultdict(list)
for p in pq.read_table(P,columns=['root','observed_year','population_value','statement_guid','raw_date_literal','date_precision','primary_verification','boundary_comparability']).to_pylist():
 if p['observed_year'] in [1979,1989]:pop[(p['root'],p['observed_year'])].append(p)
cols=['population_1979_present_ocr_raw','population_1979_permanent_ocr_raw','population_1989_present_ocr_raw','population_1989_permanent_ocr_raw'];queue=[];stats=collections.Counter()
with OCR.open() as f:
 for r in csv.DictReader(f):
  stats['OCR_candidate_rows']+=1;hits=idx.get(cleanname(r['name_ocr_raw']),[])
  if not hits:continue
  stats['literal_name_bound_rows']+=1
  qualified=[b for b in hits if region(r['region_ocr_raw']) and region(r['region_ocr_raw'])==region(b['source_region_raw'])]
  selected=qualified if qualified else hits
  for b in selected:
   values={};matched=[];allvalues={}
   for col in cols:
    n=integer(r[col]);values[col.removesuffix('_ocr_raw')+'_literal_integer']=n;year=1979 if '1979' in col else 1989;ps=pop[(b['root'],year)];matches=[v for v in ps if n is not None and v['population_value']==n]
    values[col.removesuffix('_ocr_raw')+'_exact_secondary_matches']=len(matches)
    allvalues[str(year)]=sorted({v['population_value'] for v in ps})
    if matches:matched.append({'OCR_column':col,'raw_OCR':r[col],'literal_integer':n,'secondary_statements':matches})
   if not matched:continue
   stats['numerically_corroborated_candidate_bindings']+=1;isq=b in qualified
   if isq:stats['region_qualified_numeric_candidates']+=1
   queue.append({**r,**values,'anchor_source_record_id':b['anchor_source_record_id'],'root':b['root'],'wikidata_qid':b['wikidata_qid'],'current_own_name':b['native_name'],'current_own_type':b['native_type'],'current_region_raw':b['source_region_raw'],'name_comparison':'literal_case_NFKC_yo_and_OCR_table_dot_pipe_cleanup_only','historical_region_qualification':'exact_normalized_administrative_name' if isq else 'NOT_QUALIFIED_missing_or_historical_name_needs_review','same_name_current_NP_candidates':len(hits),'qualified_same_name_candidates':len(qualified),'corroborated_columns':len(matched),'largest_corroborated_value':max(v['literal_integer'] for v in matched),'secondary_year_values_json':json.dumps(allvalues),'numeric_corroboration_json':json.dumps(matched,ensure_ascii=False),'review_status':'candidate_numeric_corroboration_only_OCR_NOT_ADMITTED','OCR_population_scope_present_permanent_not_inferred_from_P1082':True,'historical_boundary_comparability':'UNKNOWN','primary_verification':'NOT_PRIMARY_VERIFIED'})
queue.sort(key=lambda r:(r['historical_region_qualification'].startswith('exact'),r['corroborated_columns'],r['largest_corroborated_value']),reverse=True)
with (H/'numeric_corroboration_review_queue.csv').open('w',newline='') as f:w=csv.DictWriter(f,list(queue[0]) if queue else ['empty']);w.writeheader();w.writerows(queue)
receipt={'inputs':{str(p):sha(p) for p in [OCR,B,P]},'counts':dict(stats),'queue_rows':len(queue),'distinct_current_NP_UIDs':len({r['anchor_source_record_id'] for r in queue}),'autoaccepted_OCR_rows':0,'population_or_identity_coverage_gain_claimed':False,'historical_region_aliases_guessed':False,'numeric_equality_does_not_verify_population_scope_or_primary_transcription':True,'output':str(H/'numeric_corroboration_review_queue.csv')};(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
