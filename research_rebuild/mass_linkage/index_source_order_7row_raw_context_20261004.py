#!/usr/bin/env python3
"""Materialize raw 2002/2010 source context for the exact 7-row candidate packet.
Producer evidence only: never modifies selected observations, graph, points, or identity.
"""
import csv, hashlib, json, re, sys, unicodedata, bisect
from collections import defaultdict, Counter
from pathlib import Path
import duckdb, xlrd
ROOT=Path('/workspace')
IN=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004/provisional_7row_candidates.csv'
SEL=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
MAN=ROOT/'settlements-baseline/output/input_manifest.csv'
RAW=ROOT/'settlements-raw'
OUT=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004/supplemental_raw_context_index_20261004'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'russian-settlements-research/research_rebuild/mass_linkage'))
import review_source_order_context_reserve_20261004 as oldreview

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def txt(x): return '' if x is None else str(x).strip()
def norm(x):
 if isinstance(x,(int,float)) and float(x).is_integer():x=int(x)
 return oldreview._source_label_key(unicodedata.normalize('NFKC',txt(x)).replace('ё','е'))
def num(x):
 if x is None:return None
 try:
  z=float(str(x).replace('\xa0','').replace(' ','').replace(',','.'))
  return int(z) if z.is_integer() else z
 except:return None
def jcell(x):
 if x is None:return None
 if isinstance(x,(float,int)):
  z=float(x);return int(z) if z.is_integer() else z
 return str(x)
def json_cells(row):return [jcell(x) for x in row]
def source_type_pass(raw, typ):return oldreview.parse_type_label(raw,typ)[0]
def header_candidates(sh, year, namecol):
 out=[]
 for ri in range(min(50,sh.nrows)):
  row=sh.row_values(ri)
  for col,v in enumerate(row):
   if col<=namecol:continue
   k=norm(v)
   if not k:continue
   hit=(year==2002 and ('численность' in k or k=='население')) or (year==2010 and (k in {'всего','все население','численность населения','численность','total'} or k.startswith('всего ')))
   if hit:out.append({'header_row_1based':ri+1,'column_1based':col+1,'header_literal':txt(v),'normalized_header':k,'column_offset_from_name':col-namecol})
 if not out:return []
 first=min(x['header_row_1based'] for x in out)
 return sorted([x for x in out if x['header_row_1based']==first],key=lambda x:(x['column_offset_from_name'],x['column_1based']))
heading_cache={}
def parent_for(sh, rel, sheet, row0, expected):
 key=(rel,str(sheet))
 if key not in heading_cache:
  heads=[]
  for rr in range(sh.nrows):
   for cc,v in enumerate(sh.row_values(rr)):
    lab=txt(v)
    if 'район' in norm(lab):heads.append({'row0':rr,'row_1based':rr+1,'column_1based':cc+1,'literal':lab})
  heading_cache[key]=heads
 # Preserve the nearest literal printed район heading, whether or not it
 # agrees with selected metadata; matching-only search would hide conflicts.
 hits=heading_cache[key]
 pos=bisect.bisect_left([h['row0'] for h in hits],row0)-1
 return hits[pos] if pos>=0 else None

with open(IN,encoding='utf-8') as f:candidates=list(csv.DictReader(f))
manifest={}
with open(MAN,encoding='utf-8-sig') as f:
 for r in csv.DictReader(f):manifest[r.get('path','')]=r.get('sha256','')
# Keep only source rows in candidate-associated files (not full census tables).
files=sorted({r['source_file_2002'] for r in candidates}|{r['source_file_2010'] for r in candidates})
file_sql=','.join("'"+x.replace("'","''")+"'" for x in files)
con=duckdb.connect();con.execute('SET threads=1');con.execute("SET memory_limit='1200MB'")
selected=con.execute(f"SELECT source_record_id,try_cast(census_year as int),source_file,source_sheet,try_cast(source_row as double),source_name_raw,settlement_name,settlement_type,region_raw,district_raw,population,population_scope,population_value_quality,entity_grain_status,is_additive_settlement_record,source_sha256,source_locator,source_population_raw FROM read_parquet('{SEL}') WHERE source_file IN ({file_sql}) AND try_cast(census_year as int) IN (2002,2010)").fetchall()
by_file_sheet=defaultdict(list);byid={}
for row in selected:
 by_file_sheet[(row[1],row[2],str(row[3]))].append(row);byid[row[0]]=row
for key,rows in by_file_sheet.items():rows.sort(key=lambda r:(r[4] if r[4] is not None else -1,r[0]))
workbooks={};pin={}
def get_sheet(year, rel, name):
 key=(year,rel,str(name))
 if key in workbooks:return workbooks[key][1]
 path=RAW/rel
 if not path.is_file():
  pin[rel]={'source_file':rel,'path':str(path),'exists':False,'manifest_sha256':manifest.get(rel,'')};workbooks[key]=(None,None);return None
 if rel not in pin:
  h=sha(path);pin[rel]={'source_file':rel,'path':str(path),'exists':True,'sha256':h,'bytes':path.stat().st_size,'manifest_sha256':manifest.get(rel,''),'matches_input_manifest':bool(manifest.get(rel) and manifest[rel]==h)}
 wb=xlrd.open_workbook(path,on_demand=True)
 try:sh=wb.sheet_by_name(str(name))
 except Exception:
  try:sh=wb.sheet_by_index(int(name))
  except Exception:sh=None
 workbooks[key]=(wb,sh);return sh

window_out=[];candidate_out=[]
for n,c in enumerate(candidates,1):
 wins=json.loads(c['anchor_windows_5_json'])
 wins=[w for w in wins if int(w.get('window_size',0))==7 and w.get('id02')==c['to_2002_id'] and float(w.get('focal_row10',-1))==float(c['source_row_2010'])]
 if not wins:raise RuntimeError(f"No matching seven-row window for {c['from_2010_id']}")
 win=max(wins,key=lambda w:(int(w.get('anchors_excluding_focal',0)),int(w.get('anchors_total',0))))
 grouprows={}
 for yr,rel,sheet,start in [(2002,win['file02'],win['sheet02'],float(win['start02'])),(2010,win['file10'],win['sheet10'],float(win['start10']))]:
  seq=by_file_sheet[(yr,rel,str(sheet))]
  at=next((i for i,x in enumerate(seq) if x[4]==start),None)
  if at is None or at+7>len(seq):raise RuntimeError(f'Selected window mismatch: {yr} {rel} {sheet} {start}')
  block=seq[at:at+7]
  focalid=c['to_2002_id'] if yr==2002 else c['from_2010_id']
  if not any(x[0]==focalid for x in block):raise RuntimeError('Focal is not inside the seven-row selected window')
  sh=get_sheet(yr,rel,sheet)
  if sh is None:raise RuntimeError(f'Missing workbook sheet: {rel} {sheet}')
  evid=[]
  for row in block:
   sid,year,sfile,ssheet,srow,rawname,sname,stype,region,district,pop,scope,quality,grain,additive,sourcehash,locator,rawpop=row
   rawrow=sh.row_values(int(srow)-1)
   matched=[i for i,v in enumerate(rawrow) if norm(v)==norm(rawname)]
   selected_name_cells=[i for i,v in enumerate(rawrow) if norm(v)==norm(sname)]
   namecol=(matched[0] if len(matched)==1 else (selected_name_cells[0] if len(selected_name_cells)==1 else None))
   rawlabel=txt(rawrow[namecol]) if namecol is not None else ''
   typecell_matches=[]
   if namecol is not None:
    for i,v in enumerate(rawrow[:namecol]):
     if source_type_pass(v,stype):typecell_matches.append(i)
   typecell=(typecell_matches[-1] if typecell_matches else None)
   raw_type_cell=txt(rawrow[typecell]) if typecell is not None else ''
   name_type_pass=(norm(rawlabel)==norm(sname) and bool(typecell is not None)) or (norm(rawlabel)==norm(rawname) and source_type_pass(rawlabel,stype))
   typeok=source_type_pass(rawlabel,stype) if namecol is not None and norm(rawlabel)==norm(rawname) else bool(typecell is not None)
   parent=parent_for(sh,sfile,ssheet,int(srow)-1,district) if year==2002 and district else None
   header=header_candidates(sh,year,namecol) if namecol is not None else []
   h=head=header[0] if header else None
   cell=rawrow[h['column_1based']-1] if h and h['column_1based']-1<len(rawrow) else None
   selectednum=num(pop);cellnum=num(cell)
   if h:
    popcheck='header_cell_exact' if selectednum is not None and cellnum==selectednum else ('header_cell_blank_or_non_numeric' if cellnum is None else 'header_cell_differs_from_selected')
   else:
    elsewhere=[i+1 for i,x in enumerate(rawrow) if selectednum is not None and num(x)==selectednum]
    popcheck='unresolved_header_selected_number_occurs_elsewhere_only' if elsewhere else 'unresolved_header_selected_number_not_located'
   entry={'candidate_2010_id':c['from_2010_id'],'candidate_2002_id':c['to_2002_id'],'window_size':7,'window_start_2002_row':win['start02'],'window_start_2010_row':win['start10'],'window_anchor_count_excluding_focal':win['anchors_excluding_focal'],'year':year,'source_record_id':sid,'source_file':sfile,'source_sha256_raw_workbook':pin[rel].get('sha256',''),'manifest_sha256':pin[rel].get('manifest_sha256',''),'manifest_sha_matches':pin[rel].get('matches_input_manifest',False),'source_sheet':str(sh.name),'source_row_1based':int(srow),'source_locator_selected':locator,'selected_name':sname,'selected_type':stype,'raw_selected_label':rawname,'raw_label_from_workbook':rawlabel,'raw_name_exact':bool(namecol is not None and norm(rawlabel)==norm(sname)),'raw_type_cell_literal':raw_type_cell,'raw_type_cell_locator':f'{rel}#{sh.name}!R{int(srow)}C{typecell+1}' if typecell is not None else None,'raw_name_cell_locator':f'{rel}#{sh.name}!R{int(srow)}C{namecol+1}' if namecol is not None else None,'raw_name_and_type_cells_match_selection':bool(name_type_pass),'raw_type_prefix_pass':bool(typeok),'selected_population_unchanged':selectednum,'raw_source_population_field':rawpop,'population_scope':scope,'population_quality':quality,'grain_status':grain,'is_additive':additive,'district_selected_raw_preserved':district,'printed_2002_parent_literal':parent['literal'] if parent else None,'printed_2002_parent_locator':f"{rel}#{sh.name}!R{parent['row_1based']}C{parent['column_1based']}" if parent else None,'parent_matches_selected_district':bool(parent and district and oldreview.district_context_matches(district,parent['literal'])) if year==2002 else None,'population_header_context_ref':f'{rel}#{sh.name}#rows1-50' if year==2010 else '', 'population_header_row_1based':h['header_row_1based'] if h else None,'population_header_col_1based':h['column_1based'] if h else None,'population_header_literal':h['header_literal'] if h else None,'population_header_candidates_json':json.dumps(header,ensure_ascii=False),'population_cell_raw':txt(cell),'population_cell_numeric':cellnum,'population_check_status':popcheck,'selected_number_occurs_elsewhere_columns_json':json.dumps([i+1 for i,x in enumerate(rawrow) if selectednum is not None and num(x)==selectednum] if not h else [],ensure_ascii=False),'raw_row_cells_json':json.dumps(json_cells(rawrow),ensure_ascii=False)}
   evid.append(entry);window_out.append(entry)
  grouprows[yr]=evid
 old=grouprows[2002]; new=grouprows[2010]
 olddistricts={norm(x['district_selected_raw_preserved']) for x in old if x['district_selected_raw_preserved']}
 parentlabels={norm(x['printed_2002_parent_literal']) for x in old if x['printed_2002_parent_literal']}
 if len(old)!=7 or not all(x['printed_2002_parent_literal'] for x in old):why='missing_printed_parent_in_2002_window'
 elif any(x['parent_matches_selected_district'] is False for x in old):why='printed_parent_does_not_match_selected_district'
 elif len(olddistricts)>1:why='selected_2002_district_changes_within_window'
 elif len(parentlabels)>1:why='printed_parent_varies_within_window'
 else:why='all_seven_2002_rows_share_context_matching_selected_district'
 candrow={'from_2010_id':c['from_2010_id'],'to_2002_id':c['to_2002_id'],'accepted_current_2021_id':c['accepted_current_2021_id'],'window_start_2002_row':win['start02'],'window_start_2010_row':win['start10'],'anchor_count_excluding_focal':win['anchors_excluding_focal'],'district_consistency_flag':why=='all_seven_2002_rows_share_context_matching_selected_district','district_consistency_reason':why,'selected_2002_district_values_json':json.dumps(sorted(olddistricts),ensure_ascii=False),'printed_parent_values_json':json.dumps(sorted(parentlabels),ensure_ascii=False),'printed_parent_per_row_json':json.dumps([{'source_record_id':x['source_record_id'],'row':x['source_row_1based'],'literal':x['printed_2002_parent_literal'],'locator':x['printed_2002_parent_locator']} for x in old],ensure_ascii=False),'raw2002_window_type_name_order_all_pass':all(x['raw_name_and_type_cells_match_selection'] for x in old),'raw2010_window_type_name_order_all_pass':all(x['raw_name_and_type_cells_match_selection'] for x in new),'raw2010_header_resolved_rows':sum(bool(x['population_header_literal']) for x in new),'raw2010_header_unresolved_rows':sum(not bool(x['population_header_literal']) for x in new),'raw2010_header_value_exact_rows':sum(x['population_check_status']=='header_cell_exact' for x in new),'raw2010_unresolved_but_number_elsewhere_rows':sum(x['population_check_status']=='unresolved_header_selected_number_occurs_elsewhere_only' for x in new),'raw_workbook_hashes_json':json.dumps({x['source_file']:x['source_sha256_raw_workbook'] for x in old+new},ensure_ascii=False),'producer_scope':'raw-source context only; no identity adjudication; selected populations/districts unmodified'}
 candidate_out.append(candrow)
 if n%500==0:print(f'processed {n}/{len(candidates)}',flush=True)
# Release each distinct workbook.
for wb,_ in workbooks.values():
 if wb is not None:
  try:wb.release_resources()
  except:pass

def write_csv(path,rows):
 if not rows:raise RuntimeError('No rows to write: '+str(path))
 fields=list(rows[0])
 with path.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='raise');w.writeheader();w.writerows(rows)
ctx=OUT/'candidate_context_index.csv';winp=OUT/'seven_row_source_context.csv';pins=OUT/'raw_source_file_pins.csv';hdr=OUT/'source_sheet_header_context.csv'
write_csv(ctx,candidate_out);write_csv(winp,window_out)
with pins.open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['source_file','path','exists','sha256','bytes','manifest_sha256','matches_input_manifest']);w.writeheader()
 for rel,meta in sorted(pin.items()):w.writerow(meta)
header_rows=[]
for yr,rel,sheet in sorted({k for k in workbooks if k[0]==2010}):
 wb,sh=workbooks[(yr,rel,sheet)]
 if sh is None:continue
 for rr in range(min(50,sh.nrows)):
  vals=sh.row_values(rr);cells=[{'column_1based':i+1,'literal':txt(v)} for i,v in enumerate(vals) if txt(v)]
  if cells:header_rows.append({'source_file':rel,'source_sha256_raw_workbook':pin[rel].get('sha256',''),'source_sheet':str(sh.name),'header_context_ref':f'{rel}#{sh.name}#rows1-50','row_1based':rr+1,'nonempty_cells_json':json.dumps(cells,ensure_ascii=False)})
write_csv(hdr,header_rows)
# Explicit 2010 population header/check classifications; no numeric coincidence is promoted.
summary={'status':'producer_supplemental_source_context_only','candidate_count':len(candidate_out),'seven_row_source_context_rows':len(window_out),'district_consistency':dict(Counter(x['district_consistency_reason'] for x in candidate_out)),'2010_population_header_and_cell_classification':dict(Counter(x['population_check_status'] for x in window_out if x['year']==2010)),'2010_rows_header_resolved':sum(bool(x['year']==2010 and x['population_header_literal']) for x in window_out),'2010_rows_header_unresolved':sum(bool(x['year']==2010 and not x['population_header_literal']) for x in window_out),'2010_selected_value_occurs_elsewhere_but_header_unresolved':sum(x['year']==2010 and x['population_check_status']=='unresolved_header_selected_number_occurs_elsewhere_only' for x in window_out),'raw_files':len(pin),'raw_files_matching_manifest':sum(bool(x.get('matches_input_manifest')) for x in pin.values()),'inputs':{},'outputs':{},'limitations':['The nearest printed parent is a source-layout observation, not an asserted administrative boundary.','Header resolution is based only on literal source headers; if unresolved, a matching number elsewhere in the row is listed but never treated as population-column evidence.','Selected populations and district fields are preserved exactly; no replacement, identity decision, graph mutation, or point mutation is performed.','The historical point bridge review is independent; this packet is supplementary raw context only.']}
for p in (IN,SEL,MAN):summary['inputs'][str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
for p in (ctx,winp,pins,hdr):summary['outputs'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size,'rows':sum(1 for _ in open(p,encoding='utf-8'))-1}
summary['generator']=str(Path(__file__).resolve());summary['generator_sha256']=sha(Path(__file__))
(OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
