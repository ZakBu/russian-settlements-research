#!/usr/bin/env python3
"""Candidate-only source-block bracketing diagnostic for 2002/2010 pairs.

Accepted cross-year links are used only as independent source-order anchors.
This script does not admit identity or point decisions.
"""
from __future__ import annotations
import csv, hashlib, json, re, sys, unicodedata
from collections import defaultdict, Counter, OrderedDict
from pathlib import Path
import duckdb, xlrd

ROOT=Path('/workspace')
REPO=ROOT/'russian-settlements-research'
sys.path.insert(0,str(REPO/'research_rebuild/mass_linkage'))
import review_source_order_context_reserve_20261004 as rawrules
import build_long_table as canonical_rules

OUT=ROOT/'settlements-work/continuation_20261004/R4/source_order_anchor_bracketed_localdistrict_corrected_v2_20261004'
OUT.mkdir(parents=True,exist_ok=True)
SEL=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
CONTROL=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004_independent_review_reconciled_20261004/reconciled_eligible_source_order_identity_edges.csv'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/accepted_identity_edges.parquet'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/accepted_point_uses.parquet'
BASEPOINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/accepted_point_uses.parquet'
EV=ROOT/'settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet'
RES=ROOT/'settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/joint_residual.parquet'
BASE_COV=ROOT/'settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/coverage.json'
RAW_CONTEXT=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004/supplemental_raw_context_index_20261004/seven_row_source_context.csv'
CONTROL_REPLAY=ROOT/'settlements-work/continuation_20261004/R4/control_uniqueness_replay/broad_replay_receipt.json'
MAN=ROOT/'settlements-baseline/output/input_manifest.csv'
RAW=ROOT/'settlements-raw'
ACCEPTED=canonical_rules.ACCEPTED_EDGE_STATUSES
PROJECTIONS=canonical_rules.ACCEPTED_PROJECTION_STATUSES
PSTATUS=canonical_rules.ACCEPTED_COORDINATE_STATUSES
PROPER={'город','пгт','посёлок','поселок','рабочий посёлок','село','деревня','хутор','станица','аул','аал','слобода','арбан','починок','заимка','выселок','местечко','станция','разъезд','кишлак','улус','кордон','мыза','платформа','участок'}

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def k(v):
 return rawrules._source_label_key(v)
def val(x): return '' if x is None else str(x).strip()
def popint(x):
 try:return int(float(x or 0))
 except:return 0
def jsonsafe(x):
 if isinstance(x,(float,int)):
  return int(x) if float(x).is_integer() else float(x)
 return val(x) or None
def canonical_type(t):
 z=k(t)
 return {'поселок городского типа':'пгт','поселок':'поселок','рабочий поселок':'рабочий поселок'}.get(z,z)

db=duckdb.connect();db.execute('SET threads=1');db.execute("SET memory_limit='1200MB'")
selrows=db.execute(f"""SELECT source_record_id,try_cast(census_year as int),source_file,source_sheet,
 try_cast(source_row as double),settlement_name,settlement_type,region_raw,district_raw,population,
 source_locator,oktmo FROM read_parquet('{SEL}') WHERE try_cast(census_year as int) IN (2002,2010,2021)""").fetchall()
byid={r[0]:r for r in selrows}; byyear=defaultdict(list)
for r in selrows: byyear[r[1]].append(r)
resids={r[0]:r for r in db.execute(f"SELECT source_record_id,population FROM read_parquet('{RES}') WHERE try_cast(census_year as int)=2010").fetchall()}
ev={i:(f,a,c,s) for i,f,a,c,s in db.execute(f"""SELECT source_record_id,
 try_cast(json_extract_string(source_evidence_json,'$.is_federal_aggregate') as boolean),
 try_cast(json_extract_string(source_evidence_json,'$.is_additive_settlement_record') as boolean),
 try_cast(json_extract_string(source_evidence_json,'$.legacy_same_year_collision') as boolean),
 json_extract_string(source_evidence_json,'$.legacy_verified_successor_settlement_id')
 FROM read_parquet('{EV}') WHERE census_year=2010""").fetchall()}
with open(CONTROL,encoding='utf-8-sig') as cf:
 control_all=list(csv.DictReader(cf))
control_by_pair={(r['source_id_2010'],r['source_id_2002_support']):r for r in control_all}
control_pairs=[];used_control_groups=set()
for r in sorted(control_all,key=lambda x:-popint(x.get('selected_population_2010_unchanged'))):
 group=(r['source_id_2002_support'].split(':',1)[0],r['source_id_2010'].split(':',1)[0])
 # Distinguish by raw publication artifact rather than prefix, selecting a fixed 10 source-pair controls.
 pairkey=(r['source_id_2002_support'].split(':')[1].split(':')[0],r['source_id_2010'].split(':')[1].split(':')[0])
 if pairkey in used_control_groups:continue
 used_control_groups.add(pairkey);control_pairs.append((r['source_id_2010'],r['source_id_2002_support']))
 if len(control_pairs)>=10:break
control_stage={pair:set() for pair in control_pairs}
control_by_2010=defaultdict(list)
control_by_2002=defaultdict(list)
for pair in control_pairs:control_by_2010[pair[0]].append(pair);control_by_2002[pair[1]].append(pair)

# Full accepted graph UF, including all years; accepted 2002-2010 edges are the anchors.
parent={};sizes={}
def find(x):
 if x not in parent:parent[x]=x;sizes[x]=1
 while parent[x]!=x: parent[x]=parent[parent[x]];x=parent[x]
 return x
def union(a,b):
 a=find(a);b=find(b)
 if a==b:return
 if sizes[a]<sizes[b]:a,b=b,a
 parent[b]=a;sizes[a]+=sizes[b]
edge_rows=db.execute(f"SELECT decision_id,from_source_record_id,try_cast(from_year as int),to_source_record_id,try_cast(to_year as int) FROM read_parquet('{GRAPH}') WHERE relation='same_place' AND decision_status IN ({','.join(repr(x) for x in sorted(ACCEPTED))}) AND selection_projection_status IN ({','.join(repr(x) for x in sorted(PROJECTIONS))})").fetchall()
adj=defaultdict(list)
for decision,a,ay,b,by in edge_rows:
 union(a,b);adj[a].append((b,decision));adj[b].append((a,decision))
comps=defaultdict(list)
for r in selrows:comps[find(r[0])].append(r)
compyears={c:{x[1] for x in rs} for c,rs in comps.items()}
pointids={r[0] for r in db.execute(f"SELECT DISTINCT target_source_record_id FROM read_parquet('{POINTS}') WHERE try_cast(target_year as int)=2021 AND coordinate_admission_status IN ({','.join(repr(x) for x in sorted(PSTATUS))})").fetchall()}
all_pointids={r[0] for r in db.execute(f"SELECT DISTINCT target_source_record_id FROM read_parquet('{POINTS}') WHERE coordinate_admission_status IN ({','.join(repr(x) for x in sorted(PSTATUS))})").fetchall()}
base_pointids={r[0] for r in db.execute(f"SELECT DISTINCT target_source_record_id FROM read_parquet('{BASEPOINTS}') WHERE coordinate_admission_status IN ({','.join(repr(x) for x in sorted(PSTATUS))})").fetchall()}
base_pointids_current={r[0] for r in db.execute(f"SELECT DISTINCT target_source_record_id FROM read_parquet('{BASEPOINTS}') WHERE try_cast(target_year as int)=2021 AND coordinate_admission_status IN ({','.join(repr(x) for x in sorted(PSTATUS))})").fetchall()}
full_roots={c for c,ys in compyears.items() if {2002,2010,2021}.issubset(ys)}
coverage=json.loads(BASE_COV.read_text(encoding='utf-8'))
coverage_by_year={int(x['year']):x for x in coverage['census_metrics']}
baseline_reproduction={'full_census_chain':{},'joint_admitted_coordinate_and_full_chain':{}}
for yr in (2002,2010,2021):
 fullrows=[r for r in byyear[yr] if find(r[0]) in full_roots]
 jointrows=[r for r in fullrows if r[0] in base_pointids]
 for axis,rows,keyname in [('full_census_chain',fullrows,'full_census_chain'),('joint_admitted_coordinate_and_full_chain',jointrows,'joint_admitted_coordinate_and_full_chain')]:
  expected=coverage_by_year[yr]['axes'][keyname]
  got={'rows':len(rows),'known_population':sum(popint(r[9]) for r in rows)}
  if got!={'rows':expected['rows'],'known_population':expected['known_population']}:
   raise RuntimeError(f'baseline {keyname} mismatch {yr}: expected {expected}, got {got}')
  baseline_reproduction[axis][str(yr)]=got
 correctedrows=[r for r in fullrows if r[0] in all_pointids]
 baseline_reproduction.setdefault('corrected_points_joint_full_chain',{})[str(yr)]={'rows':len(correctedrows),'known_population':sum(popint(r[9]) for r in correctedrows)}
expected_full_rows=coverage_by_year[2021]['axes']['full_census_chain']['rows']
if len(full_roots)!=expected_full_rows:raise RuntimeError(f'accepted full-chain baseline mismatch: expected {expected_full_rows}, got {len(full_roots)}')
anchor_paths={};accepted_pairs=[]
for comp,rows in comps.items():
 old=[r[0] for r in rows if r[1]==2002];new=[r[0] for r in rows if r[1]==2010]
 if len(old)!=1 or len(new)!=1:continue
 start,goal=old[0],new[0];queue=[start];prev={start:(None,None)}
 for node in queue:
  if node==goal:break
  for nxt,decision in adj.get(node,[]):
   if nxt not in prev:prev[nxt]=(node,decision);queue.append(nxt)
 if goal not in prev:raise RuntimeError('same accepted UF component has no accepted decision path')
 path=[];node=goal
 while node!=start:
  before,decision=prev[node];path.append(decision);node=before
 path.reverse();accepted_pairs.append((start,goal));anchor_paths[(start,goal)]=path
codecounts=Counter(val(r[11]) for r in byyear[2021] if val(r[11]))

# Accepted anchors only connect source-file/sheet pairs with equal reviewed province key.
groups=defaultdict(list)
for i02,i10 in accepted_pairs:
 a=byid[i02];b=byid[i10]
 if rawrules._source_region_key(a[7])!=rawrules._source_region_key(b[7]) or not a[2] or not b[2] or a[4] is None or b[4] is None:continue
 g=(rawrules._source_region_key(a[7]),a[2],str(a[3]),b[2],str(b[3]))
 groups[g].append((i02,i10,anchor_paths[(i02,i10)]))

# Candidate raw files are derived from all accepted-anchor groups. Each workbook hash is read once.
manifest={}
with open(MAN,encoding='utf-8-sig') as f:
 for r in csv.DictReader(f):manifest[r.get('path','')]=r.get('sha256','')
workbooks=OrderedDict();pins={};sheetcache={};unavailable_groups=[];raw_unparsed_groups=Counter()
def get_sheet(year,rel,sheet):
 key=(year,rel,str(sheet))
 if key in sheetcache:return sheetcache[key]
 p=rawrules.raw_path(rel)
 if not p.is_file():sheetcache[key]=None;pins.setdefault(rel,{'exists':False,'requested_path':str(RAW/rel),'path':str(p),'manifest_sha256':manifest.get(rel,''),'reader_status':'raw_file_unavailable'});return None
 if rel not in pins:
  filehash=sha(p)
  pins[rel]={'exists':True,'requested_path':str(RAW/rel),'path':str(p),'sha256':filehash,'bytes':p.stat().st_size,'manifest_sha256':manifest.get(rel,''),'matches_input_manifest':bool(manifest.get(rel) and filehash==manifest[rel])}
 wb=workbooks.pop(rel,None)
 if wb is None:
  try:
   if p.suffix.casefold()=='.xlsx':
    import openpyxl
    class OpenpyxlSheet:
     def __init__(self,ws):self.ws=ws;self.nrows=ws.max_row;self.name=ws.title
     def row_values(self,i):return list(next(self.ws.iter_rows(min_row=i+1,max_row=i+1,values_only=True)))
    class OpenpyxlBook:
     def __init__(self,book):self.book=book
     def sheet_by_name(self,name):return OpenpyxlSheet(self.book[str(name)])
     def sheet_by_index(self,index):return OpenpyxlSheet(self.book.worksheets[int(index)])
     def release_resources(self):self.book.close()
    wb=OpenpyxlBook(openpyxl.load_workbook(p,read_only=True,data_only=True))
   else:wb=xlrd.open_workbook(p,on_demand=True)
  except Exception as exc:
   sheetcache[key]=None
   pins[rel]['reader_status']='unsupported_or_unparsed'
   pins[rel]['reader_error']=type(exc).__name__+': '+str(exc)[:300]
   return None
  while len(workbooks)>=2:
   oldrel,oldwb=workbooks.popitem(last=False)
   try:oldwb.release_resources()
   except Exception:pass
   for sk in list(sheetcache):
    if sk[1]==oldrel:del sheetcache[sk]
  workbooks[rel]=wb
 else:workbooks[rel]=wb
 try:sh=wb.sheet_by_name(str(sheet))
 except Exception:
  try:sh=wb.sheet_by_index(int(sheet))
  except Exception:
   sh=None
   pins[rel].setdefault('unavailable_sheet_requests',[]).append(str(sheet))
 sheetcache[key]=sh;return sh

raw_label_profiles=defaultdict(Counter)
with open(RAW_CONTEXT,encoding='utf-8-sig',newline='') as rf:
 for row in csv.DictReader(rf):
  def loc_col(text):
   m=re.search(r'R\d+C(\d+)',text or '')
   return int(m.group(1)) if m else None
  namecol=loc_col(row.get('raw_name_cell_locator',''))
  typecol=loc_col(row.get('raw_type_cell_locator',''))
  if namecol:
   raw_label_profiles[(int(row['year']),row['source_file'],row['source_sheet'])][(typecol,namecol)]+=1
def label_profile(year,rel,sheet):
 vals=raw_label_profiles.get((int(year),rel,str(sheet)),Counter())
 if not vals:return None
 ranked=vals.most_common()
 if len(ranked)>1 and ranked[0][1]==ranked[1][1]:return {'status':'ambiguous_column_profile','alternatives':ranked}
 return {'status':'reviewed_context_column_profile','type_col':ranked[0][0][0],'name_col':ranked[0][0][1],'support_rows':ranked[0][1],'alternatives':ranked}

def typed_raw_rows(sh,year,rel,sheet):
 """Use the reviewed source name/type columns; emit exactly one record per physical row."""
 cachekey=(int(year),rel,str(sheet))
 if cachekey in rawtyped_cache:return rawtyped_cache[cachekey]
 out=[]
 profile=label_profile(year,rel,sheet)
 for ri in range(sh.nrows):
  cells=sh.row_values(ri)
  if not profile or profile['status']!='reviewed_context_column_profile':
   out.append({'row':ri+1,'col':None,'type_col':None,'literal':None,'name':None,'type':None,'raw_name_field':None,'typed_prefix_recognized':False,'raw_label_profile_status':'missing_or_ambiguous_reviewed_column_profile'})
   continue
  typecol,namecol=profile['type_col'],profile['name_col']
  text=val(cells[namecol-1]) if len(cells)>=namecol else ''
  type_text=val(cells[typecol-1]) if typecol and len(cells)>=typecol else ''
  source_text=type_text or text
  matches=sorted({canonical_type(t) for t in rawrules.TYPE_PREFIX if rawrules.parse_type_label(source_text,t)[0]}) if source_text else []
  m=rawrules.TYPE_RE.match(source_text) if source_text else None
  suffix=source_text[m.end():].strip(' .,:;—–-') if m else ''
  name_value=suffix if suffix else text
  name_value=re.sub(r'^\s*(?:'+ '|'.join(re.escape(x) for x in sorted(set(rawrules.TYPE_PREFIX.values()),key=len,reverse=True))+r')\s*','',name_value,flags=re.I).strip(' .,:;—–-')
  rawtype=matches[0] if len(matches)==1 else ('ambiguous:'+'|'.join(matches) if matches else None)
  out.append({'row':ri+1,'col':namecol,'type_col':typecol or namecol,'literal':source_text or None,'name':k(name_value) or None,'type':rawtype,'type_candidates':matches,'raw_name_field':text or None,'raw_type_field':type_text or None,'typed_prefix_recognized':len(matches)==1,'raw_label_profile_status':profile['status'],'raw_label_profile_support_rows':profile['support_rows']})
 rawtyped_cache[cachekey]=out
 return out

def parents(sh):
 headings=[]
 for ri in range(sh.nrows):
  for ci,v in enumerate(sh.row_values(ri)):
   lab=val(v)
   if 'район' in k(lab):headings.append((ri+1,ci+1,lab))
 out={}
 for rr in range(1,sh.nrows+1):
  prev=[h for h in headings if h[0]<=rr]
  out[rr]=prev[-1] if prev else None
 return out

parent_cache={}
def cached_parents(year,rel,sheet,sh):
 key=(int(year),rel,str(sheet))
 if key not in parent_cache:parent_cache[key]=parents(sh)
 return parent_cache[key]
rawtyped_cache={}

selected_by_sheet=defaultdict(list)
for r in selrows:
 if r[1] in (2002,2010) and r[4] is not None:
  selected_by_sheet[(r[1],r[2],str(r[3]))].append(r)
for kk in selected_by_sheet:selected_by_sheet[kk].sort(key=lambda x:(x[4],x[0]))

# Preflight every unique raw sheet once, persist compact source-column descriptors,
# and verify completion plus the fixed control-row names before generating candidates.
raw_cache_dir=OUT/'raw_descriptor_cache_v1';raw_cache_dir.mkdir(parents=True,exist_ok=True)
raw_cache_sheet_manifest=[]
raw_cache_rows_written=0
sheet_tasks=set()
for _,file02,sheet02,file10,sheet10 in groups:
 sheet_tasks.add((2002,file02,str(sheet02)));sheet_tasks.add((2010,file10,str(sheet10)))
for ti,(year,rel,sheet) in enumerate(sorted(sheet_tasks),1):
 sh=get_sheet(year,rel,sheet)
 profile=label_profile(year,rel,sheet)
 if sh is None:
  raw_cache_sheet_manifest.append({'year':year,'source_file':rel,'source_sheet':sheet,'status':'raw_sheet_unavailable','row_count':None,'descriptor_count':0})
  continue
 descriptors=typed_raw_rows(sh,year,rel,sheet)
 complete=len(descriptors)==sh.nrows and len({x['row'] for x in descriptors})==sh.nrows and all(x['row']==i+1 for i,x in enumerate(descriptors))
 cachefile=raw_cache_dir/(hashlib.sha256(f'{year}|{rel}|{sheet}'.encode()).hexdigest()+'.jsonl')
 with open(cachefile,'w',encoding='utf-8') as cf:
  for item in descriptors:cf.write(json.dumps(item,ensure_ascii=False)+'\n')
 raw_cache_rows_written+=len(descriptors)
 raw_cache_sheet_manifest.append({'year':year,'source_file':rel,'source_sheet':sheet,'status':'cached_complete' if complete else 'row_completion_mismatch',
  'row_count':sh.nrows,'descriptor_count':len(descriptors),'row_numbers_complete':complete,
  'label_column_profile':profile,'raw_source_sha256':pins.get(rel,{}).get('sha256'),'cache_file':cachefile.name,'cache_sha256':sha(cachefile),'cache_bytes':cachefile.stat().st_size})
 if not complete:raise RuntimeError(f'raw source descriptor row completion mismatch: {year} {rel} {sheet}')
if any(x['status'] not in ('cached_complete','raw_sheet_unavailable') for x in raw_cache_sheet_manifest):
 raise RuntimeError('invalid raw descriptor preflight status')
control_raw_checks=[]
for id10,id02 in control_pairs:
 for source_id in (id02,id10):
  r=byid[source_id];cache=rawtyped_cache.get((int(r[1]),r[2],str(r[3])))
  if cache is None:
   control_raw_checks.append({'source_id':source_id,'status':'missing_cached_sheet'});continue
  rec=next((x for x in cache if x['row']==int(r[4])),None)
  expected=(k(r[5]),canonical_type(r[6]))
  got=(rec.get('name'),rec.get('type')) if rec else (None,None)
  ok=bool(rec and rec.get('typed_prefix_recognized') and got==expected)
  control_raw_checks.append({'source_id':source_id,'year':r[1],'source_file':r[2],'sheet':str(r[3]),'row':int(r[4]),'expected_name_type':expected,'raw_name_type':got,'status':'pass' if ok else 'raw_control_row_name_type_mismatch'})
  if not ok:raise RuntimeError(f'authoritative raw label preflight control mismatch: {source_id}; expected={expected} got={got}')
cache_manifest={'status':'source_sheet_descriptor_preflight_complete','sheet_task_count':len(sheet_tasks),'row_descriptor_count':raw_cache_rows_written,
 'control_record_count':len(control_raw_checks),'control_records_passed':sum(x['status']=='pass' for x in control_raw_checks),
 'fixed_control_replay_receipt_sha256':sha(CONTROL_REPLAY),'sheets':raw_cache_sheet_manifest,'fixed_control_rows':control_raw_checks}
cache_manifest_path=OUT/'raw_descriptor_cache_preflight.json'
cache_manifest_path.write_text(json.dumps(cache_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

candidate_rows=[]; group_diagnostics=[]; reject=Counter()
for gi,(g,apairs) in enumerate(sorted(groups.items()),1):
 region,file02,sheet02,file10,sheet10=g
 seen=set();anchor_seeds=[]
 for control in control_pairs:
  c10=byid.get(control[0]);c02=byid.get(control[1])
  if c10 and c02 and (c02[2],str(c02[3]),c10[2],str(c10[3]))==(file02,sheet02,file10,sheet10):
   control_stage[control].add('accepted_uf_source_file_pair_present')
 unique_apairs={(a,b):path for a,b,path in apairs}
 for (a,b),path in sorted(unique_apairs.items(),key=lambda p:(byid[p[0][0]][4],byid[p[0][1]][4],p[0][0],p[0][1])):
  ra,rb=byid[a],byid[b]
  if (ra[4],rb[4]) in seen:continue
  seen.add((ra[4],rb[4]))
  anchor_seeds.append({'id02':a,'id10':b,'row02':float(ra[4]),'row10':float(rb[4]),'path':path,'district':ra[8]})
 sh02=get_sheet(2002,file02,sheet02);sh10=get_sheet(2010,file10,sheet10)
 if sh02 is None or sh10 is None:
  reject['raw workbook or sheet unavailable or unparsed']+=1
  reasons=[]
  for rel,sheet in ((file02,sheet02),(file10,sheet10)):
   meta=pins.get(rel,{})
   reason=meta.get('reader_status') or ('requested_sheet_not_found' if str(sheet) in meta.get('unavailable_sheet_requests',[]) else 'source_sheet_readable')
   reasons.append(f"{Path(rel).suffix.casefold() or 'no_extension'}:{reason}")
  raw_unparsed_groups.update(reasons)
  unavailable_groups.append({'region':region,'file_2002':file02,'sheet_2002':sheet02,'file_2010':file10,'sheet_2010':sheet10,'reason_2002':reasons[0],'reason_2010':reasons[1]})
  continue
 oldparent=cached_parents(2002,file02,sheet02,sh02)
 anchors=[]
 for a in anchor_seeds:
  pr=oldparent.get(int(a['row02'])); dparts=tuple(sorted(rawrules.district_stems(a['district'])))
  parent_matches=bool(pr and dparts and rawrules.district_context_matches(a['district'],pr[2]))
  a['district_key']=dparts;a['parent_matches']=parent_matches
  if parent_matches:
   anchors.append({**a,'parent':pr[2],'parent_row':pr[0],'parent_col':pr[1]})
  else:reject['anchor lacks matching printed 2002 district context']+=1
 leftarr=selected_by_sheet[(2002,file02,sheet02)];rightarr=selected_by_sheet[(2010,file10,sheet10)]
 if not leftarr or not rightarr:continue
 profile02=label_profile(2002,file02,sheet02);profile10=label_profile(2010,file10,sheet10)
 if not profile02 or profile02['status']!='reviewed_context_column_profile' or not profile10 or profile10['status']!='reviewed_context_column_profile':
  reject['raw name/type source-column profile missing or ambiguous']+=1
  continue
 left_raw=typed_raw_rows(sh02,2002,file02,sheet02);right_raw=typed_raw_rows(sh10,2010,file10,sheet10)
 # Partition anchors by district across this source pair, not by whole-province order.
 # Other-district anchors are considered only inside each candidate's 2010 bracket.
 bydistrict=defaultdict(list)
 for a in anchors:bydistrict[a['district_key']].append(a)
 runs=[sorted(run,key=lambda x:(x['row02'],x['id02'])) for run in bydistrict.values()]
 for control in control_pairs:
  c10=byid.get(control[0]);c02=byid.get(control[1])
  if not c10 or not c02 or (c02[2],str(c02[3]),c10[2],str(c10[3]))!=(file02,sheet02,file10,sheet10):continue
  ckey=tuple(sorted(rawrules.district_stems(c02[8])))
  if any(run and run[0]['district_key']==ckey and len(run)>=3 for run in runs):control_stage[control].add('same_district_local_anchor_group_ge3')
 emitted=0
 for run in runs:
  if len(run)<3:
   reject['local district block fewer than three anchors']+=1;continue
  district=run[0]['district_key']
  for ai in range(len(run)-1):
   left=run[ai];right=run[ai+1]
   l02,l10=left['row02'],left['row10'];r02,r10=right['row02'],right['row10']
   if not (l02<r02 and l10<r10):continue
   # Crossing anchors outside this candidate bracket do not veto the whole district.
   # Inside the bracket, all accepted same-district anchors must remain ordered and
   # every other-district anchor is a hard contradiction below.
   oldblock=[x for x in leftarr if l02<x[4]<r02]
   newblock=[x for x in rightarr if l10<x[4]<r10]
   for control in control_pairs:
    if control[1] in {x[0] for x in oldblock} and control[0] in {x[0] for x in newblock}:
     control_stage[control].add('approved_control_pair_inside_both_year_bracket')
   oldtokens=Counter((k(x[5]),canonical_type(x[6])) for x in oldblock)
   newtokens=Counter((k(x[5]),canonical_type(x[6])) for x in newblock)
   bad_inner=[a for a in anchor_seeds if
    (l10<a['row10']<r10 and a['district_key']!=district) or
    (l02<a['row02']<r02 and not a['parent_matches'])]
   if bad_inner:
    reject['contradictory other-district anchor inside 2010 bracket']+=1
    old_ids={x[0] for x in oldblock};new_ids={x[0] for x in newblock}
    for control in control_pairs:
     if control[1] in old_ids and control[0] in new_ids:
      control_stage[control].add('blocked_contradictory_other_district_anchor_inside_bracket')
    continue
   oldrawblock=[x for x in left_raw if l02<x['row']<r02]
   newrawblock=[x for x in right_raw if l10<x['row']<r10]
   for control in control_pairs:
    c_old=next((x for x in oldblock if x[0]==control[1]),None)
    c_new=next((x for x in newblock if x[0]==control[0]),None)
    if c_old and c_new:
     stages=control_stage[control]
     tokc=(k(c_old[5]),canonical_type(c_old[6]))
     if tokc==(k(c_new[5]),canonical_type(c_new[6])) and tokc[0] and tokc[1]:
      stages.add('control_selected_name_type_exact')
      oc=[x for x in oldrawblock if x['name']==tokc[0] and x['type']==tokc[1]]
      nc=[x for x in newrawblock if x['name']==tokc[0] and x['type']==tokc[1]]
      if len(oc)!=1:stages.add('control_old_raw_pair_not_unique')
      if len(nc)!=1:stages.add('control_new_raw_pair_not_unique')
      if len(oc)==1 and oc[0]['row']!=int(c_old[4]):stages.add('control_old_raw_selected_row_mismatch')
      if len(nc)==1 and nc[0]['row']!=int(c_new[4]):stages.add('control_new_raw_selected_row_mismatch')
      prc=oldparent.get(int(c_old[4]))
      if not prc or tuple(sorted(rawrules.district_stems(c_old[8])))!=district or not rawrules.district_context_matches(c_old[8],prc[2]):
       stages.add('control_old_parent_context_gate_failed')
      else:stages.add('control_old_parent_context_gate_pass')
     else:stages.add('control_selected_name_type_mismatch')
   for r02row in oldblock:
    tok=(k(r02row[5]),canonical_type(r02row[6]))
    if not tok[0] or not tok[1] or oldtokens[tok]!=1:continue
    if sum(1 for x in oldrawblock if x['name']==tok[0] and x['type']==tok[1])!=1:
     reject['2002 raw source block exact typed name/type not unique by physical row']+=1;continue
    possible_unknown=[x for x in oldrawblock if not x['typed_prefix_recognized'] and tok[0] and tok[0] in k(x.get('raw_name_field'))]
    if possible_unknown:
     reject['2002 untyped authoritative label could match candidate']+=1;continue
    oldraw=next((x for x in oldrawblock if x['row']==int(r02row[4]) and x['name']==tok[0] and x['type']==tok[1]),None)
    if not oldraw:continue
    pr=oldparent.get(int(r02row[4]))
    if not pr or tuple(sorted(rawrules.district_stems(r02row[8])))!=district or not rawrules.district_context_matches(r02row[8],pr[2]):continue
    c02=find(r02row[0]);cm=comps.get(c02,[])
    current=[x for x in cm if x[1]==2021 and val(x[11]) and val(x[11]).isdigit() and canonical_type(x[6]) in {canonical_type(t) for t in PROPER} and x[0] in pointids and codecounts[val(x[11])]==1]
    if len(current)!=1:
     for control in control_by_2002.get(r02row[0],[]):control_stage[control].add('failed_unique_proper_current_native_point_gate')
     continue
    for r10row in newblock:
     tok10=(k(r10row[5]),canonical_type(r10row[6]))
     if tok10!=tok or newtokens[tok]!=1:continue
     control_key=(r10row[0],r02row[0])
     if control_key in control_stage:control_stage[control_key].add('same_typed_pair_inside_anchor_bracket')
     if sum(1 for x in newrawblock if x['name']==tok[0] and x['type']==tok[1])!=1:
      reject['2010 raw source block exact typed name/type not unique by physical row']+=1;continue
     possible_unknown=[x for x in newrawblock if not x['typed_prefix_recognized'] and tok[0] and tok[0] in k(x.get('raw_name_field'))]
     if possible_unknown:
      reject['2010 untyped authoritative label could match candidate']+=1;continue
     newraw=next((x for x in newrawblock if x['row']==int(r10row[4]) and x['name']==tok[0] and x['type']==tok[1]),None)
     if not newraw:continue
     control_key=(r10row[0],r02row[0])
     if control_key in control_stage:control_stage[control_key].add('raw_exact_typed_pair_unique_inside_bracket')
     if r10row[0] not in resids:continue
     if control_key in control_stage:control_stage[control_key].add('proper_current_native_point_gate_pass')
     if r10row[0] not in resids:continue
     e=ev.get(r10row[0],(None,None,None,None))
     if e[0] is True or e[1] is False or e[2] is True or e[3]:continue
     if control_key in control_stage:control_stage[control_key].add('2010_source_event_additivity_guards_pass')
     c10=find(r10row[0])
     if c10==c02:
      if control_key in control_stage:control_stage[control_key].add('already_connected_in_seventh_baseline_control')
      continue
     if compyears.get(c02,set()) & compyears.get(c10,set()):continue
     oldrawblock_export=[{**x,'cells':[jsonsafe(v) for v in sh02.row_values(int(x['row'])-1)]} for x in oldrawblock]
     newrawblock_export=[{**x,'cells':[jsonsafe(v) for v in sh10.row_values(int(x['row'])-1)]} for x in newrawblock]
     candidate_rows.append({'from_2010_id':r10row[0],'to_2002_id':r02row[0],'accepted_current_2021_id':current[0][0],
      'population_2010':popint(r10row[9]),'name':r10row[5],'type':r10row[6],'region':r10row[7],
      'district_raw_2002':r02row[8],'district_raw_2010':r10row[8],
      'source_file_2002':file02,'source_sheet_2002':sheet02,'source_row_2002':r02row[4],
      'source_file_2010':file10,'source_sheet_2010':sheet10,'source_row_2010':r10row[4],
      'raw_workbook_sha256_2002':pins[file02].get('sha256'),'raw_workbook_sha256_2010':pins[file10].get('sha256'),
      'source_locator_2002':r02row[10],'source_locator_2010':r10row[10],
      'printed_parent_2002':pr[2],'printed_parent_locator_2002':f'{file02}#{sheet02}!R{pr[0]}C{pr[1]}',
      'bracket_left_anchor_2002':left['id02'],'bracket_left_anchor_2010':left['id10'],'bracket_right_anchor_2002':right['id02'],'bracket_right_anchor_2010':right['id10'],
      'anchors_total_local_block':len(run),'anchors_before_candidate':ai+1,'anchors_after_candidate':len(run)-ai-1,
      'anchor_district_key':district,'accepted_decision_path_json':json.dumps({'left02_to_2010':left['path'],'right02_to_2010':right['path']},ensure_ascii=False),
      'raw_2002_block_typed_rows_json':json.dumps(oldrawblock_export,ensure_ascii=False),'raw_2010_block_typed_rows_json':json.dumps(newrawblock_export,ensure_ascii=False),
      'candidate_only':True,'decision_status':'pending_independent_review','source_order_basis':'local_district_anchor_bracketed_source_block; no district transferred; no ordinal identity'})
     emitted+=1
 if emitted:group_diagnostics.append({'region':region,'file_2002':file02,'sheet_2002':sheet02,'file_2010':file10,'sheet_2010':sheet10,'anchor_count':len(anchors),'candidate_count':emitted})
 if gi%100==0:
  checkpoint=OUT/'.candidate_edges_checkpoint.csv'
  with open(checkpoint,'w',newline='',encoding='utf-8') as cf:
   fields=list(candidate_rows[0]) if candidate_rows else ['from_2010_id','to_2002_id','candidate_only']
   cw=csv.DictWriter(cf,fieldnames=fields,extrasaction='ignore');cw.writeheader();cw.writerows(candidate_rows)
  print(f'groups {gi}/{len(groups)} candidates {len(candidate_rows)}',flush=True)

# Deduplicate only exact source pair proposals; retain conflicting mappings as holds.
by_focal=defaultdict(list)
for x in candidate_rows:by_focal[x['from_2010_id']].append(x)
dedup=[];ambiguous=[]
for focal,vals in by_focal.items():
 if len({x['to_2002_id'] for x in vals})>1:
  ambiguous.extend(vals);continue
 per_target=defaultdict(list)
 for x in vals:per_target[x['to_2002_id']].append(x)
 for target,proposals in per_target.items():
  dedup.append(sorted(proposals,key=lambda x:(x['anchors_total_local_block'],x['source_row_2010']),reverse=True)[0])

# Replay the candidate-only edges against a fresh copy of the pinned accepted UF.
# This measures complete-chain and joint complete-chain marginal rows/population,
# deduplicating any collisions introduced by multiple candidate edges.
sim_parent=parent.copy();sim_size=sizes.copy()
sim_years={r:set(ys) for r,ys in compyears.items()}
sim_members={r:list(members) for r,members in comps.items()}
def sfind(x):
 if x not in sim_parent:sim_parent[x]=x;sim_size[x]=1;sim_years[x]=set();sim_members[x]=[]
 while sim_parent[x]!=x:sim_parent[x]=sim_parent[sim_parent[x]];x=sim_parent[x]
 return x
def sunion(a,b):
 a=sfind(a);b=sfind(b)
 if a==b:return a
 if sim_size[a]<sim_size[b]:a,b=b,a
 sim_parent[b]=a;sim_size[a]+=sim_size[b];sim_years[a]|=sim_years[b];sim_members[a].extend(sim_members[b]);return a
delta_rows=Counter();delta_pop=Counter();delta_joint_rows=Counter();delta_joint_pop=Counter();sim_accepted=[];sim_holds=Counter()
for cand in sorted(dedup,key=lambda x:(-x['population_2010'],x['from_2010_id'])):
 a=sfind(cand['from_2010_id']);b=sfind(cand['to_2002_id'])
 if a==b:sim_holds['already connected']+=1;continue
 if sim_years[a]&sim_years[b]:sim_holds['year collision with earlier candidate']+=1;continue
 members=list(sim_members[a])+list(sim_members[b])
 root=sunion(a,b)
 if {2002,2010,2021}.issubset(sim_years[root]):
  for yr in (2002,2010,2021):
   rows=[r for r in members if r[1]==yr]
   delta_rows[yr]+=len(rows);delta_pop[yr]+=sum(popint(r[9]) for r in rows)
   jrows=[r for r in rows if r[0] in all_pointids]
   delta_joint_rows[yr]+=len(jrows);delta_joint_pop[yr]+=sum(popint(r[9]) for r in jrows)
  sim_accepted.append(cand)
 else:sim_holds['candidate did not complete all three years']+=1
conditional_gain={'new_full_chain_rows_by_year':{str(y):delta_rows[y] for y in (2002,2010,2021)},
 'new_full_chain_population_by_year':{str(y):delta_pop[y] for y in (2002,2010,2021)},
 'new_joint_admitted_full_chain_rows_by_year':{str(y):delta_joint_rows[y] for y in (2002,2010,2021)},
 'new_joint_admitted_full_chain_population_by_year':{str(y):delta_joint_pop[y] for y in (2002,2010,2021)},
 'candidate_edges_used_after_simulated_year_guards':len(sim_accepted),'simulated_holds':dict(sim_holds)}

def write_csv(path,rows):
 with open(path,'w',newline='',encoding='utf-8') as f:
  fields=list(rows[0]) if rows else ['from_2010_id','to_2002_id','accepted_current_2021_id','population_2010','candidate_only']
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

outcsv=OUT/'candidate_edges.csv';write_csv(outcsv,dedup)
checkpoint=OUT/'.candidate_edges_checkpoint.csv'
if checkpoint.exists():checkpoint.unlink()
ambcsv=OUT/'ambiguous_candidate_mappings.csv';write_csv(ambcsv,ambiguous)
gcsv=OUT/'source_pair_blocks.csv';write_csv(gcsv,group_diagnostics)
pinrows=[{'source_file':rel,**meta} for rel,meta in sorted(pins.items())]
pinfile=OUT/'raw_source_pins.csv';write_csv(pinfile,pinrows)
heldfile=OUT/'held_raw_source_pairs.csv';write_csv(heldfile,unavailable_groups)

summary={'status':'candidate_only_local_district_anchor_bracketed_source_block','admission_authorized':False,
 'rule':'Within a same source-file/sheet pair, partition accepted UF 2002↔2010 anchors by actual selected 2002 district; every anchor must match its own nearest printed 2002 district parent (semantic heading variants are retained); each local district group has at least three anchors and only consecutive ordered anchors bound candidates. Any accepted other-district anchor inside the candidate 2010 bracket blocks it. Exact typed name is unique among selected rows and source-specific reviewed raw name/type columns in both bounded physical-row blocks; 2002 component has one proper native-code current endpoint with an accepted point; source event/additivity/federal/collision and year-unique graph guards pass. Anchor pairs can be connected through an accepted UF path; actual decision IDs are stored. No 2010 district copied or inferred.',
 'constraints':['No fuzzy or proximity identity basis.','No ordinal-derived IDs used.','2010 district remains raw selected value, including blank.','Raw typed block rows retained in each candidate; unmatched typed rows are visible as competitors.','Unknown untyped rows are not treated as proof of absence and need fixed review.','One typed descriptor per physical row is parsed from reviewed source name/type columns; metadata/wiki columns are not counted as separate physical observations.','No identity or point ledger modified.'],
 'source_group_count':len(groups),'source_groups_with_candidates':len(group_diagnostics),'raw_files_pinned':len(pins),
 'accepted_full_chain_component_count':len(full_roots),'accepted_anchor_pair_count':len(accepted_pairs),
 'baseline_reproduction':baseline_reproduction,
 'fixed_independently_approved_controls':{'source_file':str(CONTROL),'source_sha256':sha(CONTROL),'requested_control_count':len(control_pairs),
  'deterministic_controls':[{'from_2010_id':a,'to_2002_id':b,'stages':sorted(control_stage[(a,b)])} for a,b in control_pairs],
  'control_stage_counts':dict(Counter(stage for stages in control_stage.values() for stage in stages))},
 'candidate_rows_before_dedup':len(candidate_rows),'candidate_edges':len(dedup),'ambiguous_rows_held':len(ambiguous),
 'candidate_population_2010':sum(x['population_2010'] for x in dedup),
 'conditional_net_joint_gain':conditional_gain,
 'reject_group_reasons':dict(reject),'unparsed_raw_group_reason_counts':dict(raw_unparsed_groups),'reviewed_raw_column_profile_count':len(raw_label_profiles),
 'raw_descriptor_preflight':{'manifest_path':str(cache_manifest_path),'manifest_sha256':sha(cache_manifest_path),'sheet_task_count':len(sheet_tasks),'descriptor_rows':raw_cache_rows_written,'fixed_control_records_passed':cache_manifest['control_records_passed']},
 'inputs':{},'outputs':{},'script_sha256':sha(Path(__file__))}
for p in (SEL,GRAPH,POINTS,BASEPOINTS,EV,RES,BASE_COV,MAN,CONTROL,RAW_CONTEXT,CONTROL_REPLAY):summary['inputs'][str(p)]={'sha256':sha(p),'bytes':p.stat().st_size}
for p in (outcsv,ambcsv,gcsv,pinfile,heldfile,cache_manifest_path):summary['outputs'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size if p.exists() else 0,'rows':sum(1 for _ in open(p,encoding='utf-8'))-1 if p.exists() else 0}
summary['receipt_sha256_input_integration_graph']=summary['inputs'][str(GRAPH)]['sha256']
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
summary['summary_sha256']=sha(OUT/'summary.json')
(OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for wb in workbooks.values():
 try:wb.release_resources()
 except Exception:pass
print(json.dumps({'out':str(OUT),'candidate_edges':len(dedup),'population':sum(x['population_2010'] for x in dedup),'ambiguous':len(ambiguous),'groups':len(groups),'group_rejects':dict(reject),'receipt_sha256':sha(OUT/'receipt.json')},ensure_ascii=False,indent=2))
