#!/usr/bin/env python3
"""Independent bounded recheck of frozen 2010 legacy-OKTMO physical identity cohort."""
import csv,json,hashlib,math,random,subprocess,collections,sys
from pathlib import Path
import pyarrow.parquet as pq
import pyarrow.dataset as ds
import xlrd
OUT=Path(__file__).resolve().parent
BASE=Path('/workspace/settlements-work/continuation_20261004')
PKG=BASE/'R4/legacy_oktmo_currentpoint_physical_cohort_20261004'
CAND=PKG/'candidate_edges_for_independent_review.csv'
ALL=PKG/'candidate_and_hold_rows.csv'
REPLAY=PKG/'conditional_union_replay.csv'
PHYSICAL=PKG/'physical_source_rows.jsonl'
RECEIPT=PKG/'receipt.json'
SUMMARY=PKG/'summary.json'
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EVID=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
GRAPH=BASE/'accepted_mass_eighth_reviewed/accepted_identity_edges.parquet'
POINTS=BASE/'accepted_mass_eighth_reviewed/accepted_point_uses.parquet'
RAW09=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet')
RAW11=Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet')
H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet')
from sys import path as _path
_path.insert(0,str(Path('/workspace/russian-settlements-research/research_rebuild/mass_linkage')))
import build_long_table as canon
import review_source_order_context_reserve_20261004 as rawrules
PINS={
 CAND:'bacf22337d5fbd7259c82cf59e0b0e219d55c82ddc640070ac27e05b01a78fa9',
 ALL:'c1bf9e74152f57ff130536fea96efd892acd53d09b399f3d08d17eaf11fde55b',
 REPLAY:'15a8be4dc85621e5e2f9b55d567d0397277c4c09cf3595fc700d4cdae62beb0b',
 PHYSICAL:'f36116af648fd98b9f5f4a5419c626c4da627934bbff6b93750b300814dd288f',
 RECEIPT:'2282eb4e3beb0fed8a2d61a6ecc8d8fa8fd066190a4d6b2842bed4004f891d5d',
 SEL:'4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657',
 EVID:'e915df1c3533e104d15e55d1063036ea76a0ac0ace28591b18d4d05c28d45327',
 GRAPH:'c0f276db44f524845bd9c4d973ce8294f372d942cad292028b3b3984024bf011',
 POINTS:'797eaf25a7383a9706e84090732cfa62aa9db9f9a7775df99ab0fc880031e337',
 RAW09:'343c0f5af1f52b9276699d9fe8d883b58def5aeabdd904063389606d29bc2b81',
 RAW11:'c778b841d22a65ac01a8658957044b66390bc32fe7f095cb2ca38489858ce17f',
 H:'cb4449d3f0fec3c833eae1ee7d6e29183aabf1668bad5b8d8edf82bad7b121f8',
}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def csvread(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def csvwrite(p,rows,fields=None):
 if fields is None:fields=list(rows[0]) if rows else []
 with open(p,'w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def norm(s):
 return rawrules._source_label_key(str(s or ''))
def normregion(s):
 return rawrules._source_region_key(str(s or ''))
def normtype(s):
 z=norm(s)
 return {'поселок городского типа':'пгт','посёлок городского типа':'пгт','посёлок':'поселок','п.':'поселок','ст-ца':'станица','ст':'станция','рзд':'разъезд','с.':'село','д.':'деревня','х.':'хутор'}.get(z,z)
def yrbit(y):
 try:y=int(float(y))
 except:return 0
 return {2002:1,2010:2,2021:4}.get(y,0)
def jbool(x):
 if isinstance(x,bool):return x
 if x in (None,'', 'nan'):return False
 return str(x).lower() in ('true','1','yes')
for p,h in PINS.items():
 if sha(p)!=h:raise RuntimeError(f'input changed {p} expected={h} actual={sha(p)}')
rec=json.loads(RECEIPT.read_text()); summary=json.loads(SUMMARY.read_text())
allrows=csvread(ALL); candidates=csvread(CAND); replay=csvread(REPLAY)
if len(allrows)!=6374 or len(candidates)!=1659 or len(replay)!=1659:raise RuntimeError('packet vector counts changed')
byold={r['old_source_record_id']:r for r in candidates}
if len(byold)!=len(candidates):raise RuntimeError('duplicate staged old source id')
replay_by={r['old_source_record_id']:r for r in replay}
if set(replay_by)!=set(byold):raise RuntimeError('conditional replay keys differ from candidate keys')
# DSU over canonical accepted same_place graph only; add 2010 candidate endpoint year on each staged proposal.
parent=[];sz=[];ym=[];ix={}
def add(x,bit=0):
 if x not in ix:
  ix[x]=len(parent);parent.append(len(parent));sz.append(1);ym.append(bit)
 else:ym[ix[x]]|=bit
 return ix[x]
def find_i(a):
 while parent[a]!=a:
  parent[a]=parent[parent[a]];a=parent[a]
 return a
def union_ids(a,b):
 ai=add(a);bi=add(b);ra=find_i(ai);rb=find_i(bi)
 if ra==rb:return False,ra,ym[ra]
 if sz[ra]<sz[rb]:ra,rb=rb,ra
 parent[rb]=ra;sz[ra]+=sz[rb];ym[ra]|=ym[rb]
 return True,ra,ym[ra]
edge_pf=pq.ParquetFile(GRAPH)
for batch in edge_pf.iter_batches(batch_size=65536,columns=['from_source_record_id','from_year','to_source_record_id','to_year','relation','decision_status']):
 for e in batch.to_pylist():
  if e['relation']!='same_place' or e['decision_status'] not in canon.ACCEPTED_EDGE_STATUSES:continue
  add(e['from_source_record_id'],yrbit(e['from_year']));add(e['to_source_record_id'],yrbit(e['to_year']))
  union_ids(e['from_source_record_id'],e['to_source_record_id'])
base_component={}
base_years={}
for r in candidates:
 a=add(r['old_source_record_id'],yrbit(2010));b=add(r['current_source_record_id'],yrbit(2021));ra=find_i(a);rb=find_i(b)
 base_component[r['old_source_record_id']] = (ra==rb)
 base_years[r['old_source_record_id']]={'old':ym[ra],'current':ym[rb]}
# Process in frozen candidate order; independently validate all same-year exclusivity and simulate direct marginal union.
new_rows=[]; redundancy_rows=[]; uf_holds=[]; review_status_by_old={}
for r in candidates:
 a=add(r['old_source_record_id'],yrbit(2010));b=add(r['current_source_record_id'],yrbit(2021));ra=find_i(a);rb=find_i(b)
 if ra==rb:
  status='baseline_same_component_confirmation'; redundancy_rows.append(r)
 else:
  collision=bool(ym[ra]&ym[rb])
  if collision:
   status='held_year_collision';uf_holds.append(r)
  else:
   old_before=ym[ra];target_before=ym[rb];new,root,mask=union_ids(r['old_source_record_id'],r['current_source_record_id'])
   if not new:raise RuntimeError('DSU expected nonredundant union')
   full=bool((old_before|target_before)&1) # had a 2002 member before adding the 2010 row
   # candidate source is year 2010; current is year 2021 and current point is vetted separately.
   status='eligible_new_union_full3' if full else 'eligible_new_union_no2002'
   new_rows.append({**r,'independent_decision':status,'baseline_old_current_already_connected':False,'preunion_target_component_year_mask':int(ym[rb]),'independent_graph_union':'new_no_shared_year'})
 review_status_by_old[r['old_source_record_id']]=status
# Rebuild the DSU statuses from the immutable producer replay (which processes its own frozen row order).
prod_status=collections.Counter(r['simulated_union_status'] for r in replay)
ind_status=collections.Counter(review_status_by_old.values())
if len(new_rows)!=204 or len(uf_holds)!=0 or sum(x['independent_decision']=='eligible_new_union_full3' for x in new_rows)!=187:
 raise RuntimeError(f'new graph classification differs: new={len(new_rows)} holds={len(uf_holds)} full3={sum(x["independent_decision"]=="eligible_new_union_full3" for x in new_rows)}')
if prod_status.get('conditional_union_no_year_collision')!=204 or prod_status.get('redundant')!=1455:raise RuntimeError(f'producer replay unexpected: {prod_status}')
# Vector recheck candidate logic and canonical source/current point guards across all 1,659.
all_true_count=0;reason_counts=collections.Counter();legacy_conflict_reasons=collections.Counter();point_origin_counts=collections.Counter();district_counts=collections.Counter();sourcefile_counts=collections.Counter();current_keys=collections.Counter();old_ids=collections.Counter()
for r in candidates:
 flags=json.loads(r['all_gate_flags_json']);
 if not all(flags.values()):raise RuntimeError(f'candidate row has failing gate {r["old_source_record_id"]} {flags}')
 all_true_count+=1;point_origin_counts[Path(r['current_point_origin_file']).name]+=1;district_counts[r['publisher_direct_district_status']]+=1;sourcefile_counts[r['publisher_file']]+=1
 current_keys[r['current_selected_native_OKTMO']]+=1;old_ids[r['old_source_record_id']]+=1
 ev=json.loads(r['source_evidence_json'])
 if ev.get('is_federal_aggregate') is not False or ev.get('is_additive_settlement_record') is not True or r['residual_federal_flag']!='False' or r['evidence_federal_flag']!='False' or r['legacy_same_year_collision_flag']!='False':
  raise RuntimeError(f'hard-grain/collision flag failed {r["old_source_record_id"]}')
 histdist=2*6371.0088*math.asin(math.sqrt(math.sin(math.radians(float(r['historical_classifier_historical_coordinate_lat'])-float(r['current_point_lat']))/2)**2+math.cos(math.radians(float(r['historical_classifier_historical_coordinate_lat'])))*math.cos(math.radians(float(r['current_point_lat'])))*math.sin(math.radians(float(r['historical_classifier_historical_coordinate_lon'])-float(r['current_point_lon']))/2)**2))
 if histdist>5 or abs(histdist-float(r['historic_to_currentpoint_distance_km']))>1e-6:raise RuntimeError(f'historical-to-current-point distance gate mismatch {r["old_source_record_id"]} {histdist}')
 if r['legacy_projection_basis_candidate_only']!='original_legacy_record':raise RuntimeError('unexpected candidate key route')
 if r['projected_OKTMO_candidate_key']!=r['current_selected_native_OKTMO'] or int(float(r['current_code_competitor_count']))!=1:raise RuntimeError('candidate code key not unique exact native literal')
 if norm(r['old_source_name'])!=norm(r['current_name']) or normtype(r['old_source_type'])!=normtype(r['current_type']) or normregion(r['old_source_region'])!=normregion(r['current_region']):
  raise RuntimeError(f'candidate exact name/type/region normalizer mismatch {r["old_source_record_id"]}')
 if jbool(ev.get('legacy_identity_conflict')):legacy_conflict_reasons[str(ev.get('legacy_identity_reasons'))]+=1
# Exact 2010 old source whole-frame key uniqueness in selected observations, current native code universe uniqueness.
selcols=['source_record_id','census_year','settlement_name','settlement_type','region_raw','population','oktmo','is_additive_settlement_record','source_file','source_sheet','source_row','population_scope','population_value_quality']
selected=ds.dataset(str(SEL),format='parquet').to_table(columns=selcols,filter=ds.field('census_year').isin([2002,2010,2021])).to_pylist()
sel_by={r['source_record_id']:r for r in selected}
all2010=collections.Counter((normregion(x['region_raw']),norm(x['settlement_name']),normtype(x['settlement_type'])) for x in selected if x['census_year']==2010)
cur_code_counts=collections.Counter(x['oktmo'] for x in selected if x['census_year']==2021 and x['oktmo'])
for r in candidates:
 key=(normregion(r['old_source_region']),norm(r['old_source_name']),normtype(r['old_source_type']))
 if all2010[key]!=1:raise RuntimeError(f'whole selected old 2010 key not unique {r["old_source_record_id"]} n={all2010[key]}')
 if cur_code_counts[r['current_selected_native_OKTMO']]!=1:raise RuntimeError(f'whole 2021 native code not unique {r["current_source_record_id"]}')
 # source record from selected frame and populations stay source inputs; no quality upgrade asserted
 sr=sel_by.get(r['old_source_record_id'])
 if not sr or int(float(sr['population']))!=int(float(r['old_population'])):raise RuntimeError(f'selected 2010 source observation mismatch {r["old_source_record_id"]}')
# Recompute historical candidate attributes and exact classifier locator rows across all 1,659; no provider ID inference.
hcols=['source_record_id','historical_name_exact','historical_type_exact','historical_code_structure_compatible','source_region_name_type_count','historical_okato_2009_raw','historical_okato_2011_raw','name_raw_2009','name_raw_2011','settlement_type_raw','historical_point_modern_region','historical_key_region_name_type_count','is_settlement_raw','is_deleted','latitude_from_lat','longitude_from_long']
hrows=ds.dataset(str(H),format='parquet').to_table(columns=hcols,filter=ds.field('source_record_id').isin(sorted(byold))).to_pylist()
h_by=collections.defaultdict(list)
for z in hrows:h_by[z['source_record_id']].append(z)
if any(len(h_by[sid])!=1 for sid in byold):raise RuntimeError('historical candidate source rows are not one-to-one')
raw09=pq.read_table(RAW09).to_pylist();raw11=pq.read_table(RAW11).to_pylist()
r09={ (x.get('source_sha256'),int(x.get('source_line_1based') or 0)):x for x in raw09 }
r11={ (x.get('source_sha256'),int(x.get('record_number_1based') or 0),int(x.get('record_byte_offset_0based') or 0)):x for x in raw11 }
for r in candidates:
 h=h_by[r['old_source_record_id']][0]
 if not h['historical_name_exact'] or not h['historical_type_exact'] or not h['historical_code_structure_compatible'] or str(h['is_settlement_raw'])!='t' or h['is_deleted'] is True:
  raise RuntimeError(f'historical typed physical source gate failed {r["old_source_record_id"]}')
 if int(h['source_region_name_type_count'])!=1 or int(float(h['historical_key_region_name_type_count']))!=1:
  raise RuntimeError(f'historical key not unique {r["old_source_record_id"]}')
 if normregion(h['historical_point_modern_region'])!=normregion(r['old_source_region']):
  raise RuntimeError(f'historical classifier region mismatch {r["old_source_record_id"]}')
 if abs(float(h['latitude_from_lat'])-float(r['historical_classifier_historical_coordinate_lat']))>1e-9 or abs(float(h['longitude_from_long'])-float(r['historical_classifier_historical_coordinate_lon']))>1e-9:
  raise RuntimeError(f'historical coordinate differs from selected raw classifier row {r["old_source_record_id"]}')
 a=json.loads(r['historical_2009_native_row_json']);b=json.loads(r['historical_2011_native_row_json'])
 ka=(r['historical_2009_classifier_source_sha256'],int(float(r['historical_2009_classifier_line'])))
 kb=(r['historical_2011_classifier_source_sha256'],int(float(r['historical_2011_classifier_record'])),int(float(r['historical_2011_classifier_byte_offset'])))
 aa=r09.get(ka);bb=r11.get(kb)
 if not aa or not bb:raise RuntimeError(f'classifier raw locator missing for {r["old_source_record_id"]}')
 if str(aa.get('historical_okato'))!=str(r['historical_2009_classifier_literal_OKATO']) or str(aa.get('name_raw'))!=str(a.get('name_raw')) or str(aa.get('is_settlement_raw'))!='t':raise RuntimeError(f'2009 raw classifier mismatch {r["old_source_record_id"]}')
 if str(bb.get('historical_okato'))!=str(r['historical_2011_classifier_literal_OKATO']) or str(bb.get('name_raw'))!=str(b.get('name_raw')) or str(bb.get('settlement_type_raw'))!=str(b.get('settlement_type_raw')):raise RuntimeError(f'2011 raw classifier mismatch {r["old_source_record_id"]}')
 if str(bb.get('is_deleted')) not in ('False','false','0','None'):raise RuntimeError(f'2011 row deleted {r["old_source_record_id"]}')
 if int(float(r['historical_OKATO_name_type_unique_region_count']))!=1 or int(float(r['historical_key_name_type_unique_count']))!=1:raise RuntimeError(f'historical whole key not unique {r["old_source_record_id"]}')
# Verify accepted point rows for every current target by exact target+coordinates+canonical admission status/origin pins.
pointids={r['current_source_record_id'] for r in candidates}
ptcols=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','coordinate_source','point_origin_file','point_origin_sha256','point_origin_locator','coordinate_measurement_date_unknown','boundary_comparability_asserted']
ptrows=ds.dataset(str(POINTS),format='parquet').to_table(columns=ptcols,filter=ds.field('target_source_record_id').isin(sorted(pointids))).to_pylist()
ptby=collections.defaultdict(list)
for x in ptrows:
 if str(x.get('target_year')) in ('2021','2021.0') and x.get('coordinate_admission_status') in canon.ACCEPTED_COORDINATE_STATUSES:ptby[x['target_source_record_id']].append(x)
for r in candidates:
 plist=ptby[r['current_source_record_id']]
 if len(plist)!=1:raise RuntimeError(f'current accepted point row count not one {r["current_source_record_id"]}: {len(plist)}')
 p=plist[0]
 if abs(float(p['latitude'])-float(r['current_point_lat']))>1e-9 or abs(float(p['longitude'])-float(r['current_point_lon']))>1e-9 or p.get('point_origin_sha256')!=r['current_point_origin_sha256'] or p.get('coordinate_admission_status')!=r['current_point_status']:
  raise RuntimeError(f'point ledger mismatch {r["current_source_record_id"]}')
# Deterministic fixed 100-row risk sample: 20 largest within proposed-new edges; one top-mass and one seeded draw per source family;
# 5 each per point-origin family and district-status stratum; fill by seeded draw. This is risk-directed, not prevalence-estimating.
random.seed(20261004)
newids={x['old_source_record_id'] for x in new_rows}
selected_sample={}
def take(row,why):selected_sample.setdefault(row['old_source_record_id'],{'row':row,'reasons':set()})['reasons'].add(why)
for r in sorted([x for x in candidates if x['old_source_record_id'] in newids],key=lambda x:float(x['old_population']),reverse=True)[:20]:take(r,'top20_new_union_mass')
byfile=collections.defaultdict(list)
for r in candidates:byfile[r['publisher_file']].append(r)
for fn,rs in sorted(byfile.items()):
 take(sorted(rs,key=lambda x:float(x['old_population']),reverse=True)[0],f'top_mass_source_family:{fn}')
 if len(rs)>1:take(random.choice(rs),f'seeded_source_family:{fn}')
byorigin=collections.defaultdict(list)
for r in candidates:byorigin[Path(r['current_point_origin_file']).name].append(r)
for family,rs in sorted(byorigin.items()):
 for r in random.sample(rs,min(5,len(rs))):take(r,f'point_origin_stratum:{family}')
bydistrict=collections.defaultdict(list)
for r in candidates:bydistrict[r['publisher_direct_district_status']].append(r)
for status,rs in sorted(bydistrict.items()):
 for r in random.sample(rs,min(5,len(rs))):take(r,f'district_context_stratum:{status}')
while len(selected_sample)<100:
 r=random.choice(candidates);take(r,'seeded_fill_100')
sample=[v['row'] for v in selected_sample.values()]
# Producer raw row witnesses keyed by source_record_id, independent file/sheet opening below.
physical={}
with open(PHYSICAL,encoding='utf-8') as f:
 for line in f:
  r=json.loads(line);physical[r['source_record_id']]=r
if len(physical)<len(candidates):raise RuntimeError('physical source row witness missing candidate rows')
workbooks={};rawchecks=[]
def jsnorm(v):
 if v is None:return ''
 if isinstance(v,float) and math.isnan(v):return ''
 return v
# Replay every 204 marginal edge + fixed risk sample against actual source bytes/row and captured source cells.
review_ids=newids | {x['old_source_record_id'] for x in sample}
for sid in sorted(review_ids):
 r=byold[sid]; rel=r['publisher_file'];sheet=r['publisher_sheet'];row=int(float(r['publisher_row']))
 rawpath=Path('/workspace/settlements-raw')/rel
 if not rawpath.exists():raise RuntimeError(f'raw publisher file missing {rel}')
 sourcepin=r['publisher_raw_file_sha256'] or r['publisher_manifest_sha256']
 if sha(rawpath)!=sourcepin:raise RuntimeError(f'raw source hash mismatch {rel}: {sha(rawpath)} != {sourcepin}')
 if rel not in workbooks:
  workbooks[rel]=xlrd.open_workbook(rawpath,on_demand=True) if rawpath.suffix.lower()=='.xls' else None
 wb=workbooks[rel]
 if rawpath.suffix.lower()=='.pdf':
  page=int(str(sheet).replace('pdf_page_',''))
  txt=subprocess.run(['pdftotext','-f',str(page),'-l',str(page),'-layout',str(rawpath),'-'],capture_output=True,text=True,check=True).stdout
  label=r['old_source_name'].strip()
  pop=str(int(float(r['old_population'])))
  matched=[line.strip() for line in txt.splitlines() if label in line and pop in line and norm(r['old_source_region']) in norm(line)]
  ok=len(matched)==1
  raw_row_json=matched[0] if ok else ''
  if not ok:raise RuntimeError(f'PDF row text mismatch {sid} {label} {pop} matches={matched}')
 else:
  ws=wb.sheet_by_name(sheet) if not str(sheet).isdigit() else wb.sheet_by_index(int(sheet))
  cells=[jsnorm(x) for x in ws.row_values(row-1)]
  ref=physical[sid]
  refcells=ref.get('raw_row_cells') or []
  if cells!=refcells:raise RuntimeError(f'raw cells differ from captured row witness {sid}')
  rawname=json.loads(r['publisher_raw_name_candidate_cells_json'] or '[]')
  if not rawname or not all(str(x['value']) in [str(v) for v in cells] for x in rawname):raise RuntimeError(f'raw name cell mismatch {sid}')
  # Exact numeric value must appear on the row; the source-name cell remains the semantic record anchor.
  nvals=[float(v) for v in cells if isinstance(v,(int,float)) and not isinstance(v,bool)]
  if float(r['old_population']) not in nvals:raise RuntimeError(f'old population not present on raw publisher row {sid}')
  raw_row_json=json.dumps(cells,ensure_ascii=False)
 rawchecks.append({'old_source_record_id':sid,'current_source_record_id':r['current_source_record_id'],'source_file':rel,'source_sha256':r['publisher_raw_file_sha256'] or r['publisher_manifest_sha256'],'sheet':sheet,'row':row,'raw_replay':'exact_excel_cells_equal_to_captured_witness' if rawpath.suffix.lower()=='.xls' else 'PDF_page_label_and_population_reopened','review_reason':';'.join((['marginal_new_union'] if sid in newids else []) + (sorted(selected_sample[sid]['reasons']) if sid in selected_sample else [])),'name':r['old_source_name'],'type':r['old_source_type'],'region':r['old_source_region'],'population':r['old_population'],'producer_district_header_context_status_uninterpreted':r['publisher_direct_district_status'],'producer_district_header_context_json_not_asserted_as_row_district':r['publisher_direct_district_header_values_json'],'selected_district_raw_legacy_field_not_assumed_literal':r['selected_old_district_field_not_assumed_literal'],'selected_district_literal_occurs_in_row_cells':str(r['selected_old_district_field_not_assumed_literal'] or '').strip() in [str(v).strip() for v in cells] if rawpath.suffix.lower()=='.xls' else None,'historical_classifier_distance_km':r['historic_to_currentpoint_distance_km'],'point_origin_file':r['current_point_origin_file'],'point_origin_sha256':r['current_point_origin_sha256'],'raw_row_evidence':raw_row_json})
# Review dispositions: approve only nonredundant no-collision source links; redundant candidates remain attestations, not edges to append.
eligible=[]
for x in new_rows:
 if x['independent_decision'] not in ('eligible_new_union_full3','eligible_new_union_no2002'):continue
 r=x
 eligible.append({
  'from_source_record_id':r['old_source_record_id'],'to_source_record_id':r['current_source_record_id'],'from_year':2010,'to_year':2021,
  'family':'legacy_oktmo_currentpoint_physical_classifier_v1','review_status':'independent_rule_accepted_candidate_only',
  'reviewed_rule':'Unique current native OKTMO candidate key plus exact whole-frame 2010 selected name/type/province, exact 2009+2011 native classifier code/name/type/physical-NP source rows, unique historical/current source keys, accepted current proper point, source additive/nonfederal/no collision, raw source sample checks; projected legacy OKTMO was not treated as identity evidence.',
  'legacy_oktmo_candidate_key':r['projected_OKTMO_candidate_key'],'current_native_oktmo_literal':r['current_selected_native_OKTMO'],
  'publisher_source_file':r['publisher_file'],'publisher_source_sha256':r['publisher_raw_file_sha256'] or r['publisher_manifest_sha256'],'publisher_sheet':r['publisher_sheet'],'publisher_row':r['publisher_row'],'publisher_source_row_replay_sha256':r['publisher_raw_file_sha256'],
  'classifier_2009_okato':r['historical_2009_classifier_literal_OKATO'],'classifier_2009_sha256':r['historical_2009_classifier_source_sha256'],'classifier_2009_line':r['historical_2009_classifier_line'],
  'classifier_2011_okato':r['historical_2011_classifier_literal_OKATO'],'classifier_2011_sha256':r['historical_2011_classifier_source_sha256'],'classifier_2011_record':r['historical_2011_classifier_record'],'classifier_2011_byte_offset':r['historical_2011_classifier_byte_offset'],
  'current_point_file':r['current_point_origin_file'],'current_point_sha256':r['current_point_origin_sha256'],'current_point_locator':r['current_point_origin_locator'],'current_point_status':r['current_point_status'],'current_point_latitude':r['current_point_lat'],'current_point_longitude':r['current_point_lon'],
  'old_source_name':r['old_source_name'],'old_source_type':r['old_source_type'],'old_source_region':r['old_source_region'],'old_source_population_secondary_not_upgraded':r['old_population'],'old_source_district_interpretation':'unknown unless the actual row itself states it; selected/inherited district is retained as metadata only',
  'legacy_identity_conflict_preserved':json.loads(r['source_evidence_json']).get('legacy_identity_conflict'),'legacy_identity_reasons_preserved':json.loads(r['source_evidence_json']).get('legacy_identity_reasons'),
  'graph_decision':'new_union_no_same_year_overlap','marginal_full_three_year_path':r['independent_decision']=='eligible_new_union_full3','boundary_comparability_asserted':False,'historical_point_measurement_claimed':False,'historical_native_oktmo_binding_claimed':False,'population_quality_upgraded':False,
 })
# Conditional population vector replay for the 187 new linked components. The staged summary's population values are not admitted/quality-upgraded.
# Use target selected current row pop plus matched 2002 row in canonical base component, and 2010 selected source row in approved pair.
# Reconstruct selected observation IDs by component using the DSU AFTER proposed union; this is only a coverage simulation.
# Build component membership by querying selected year IDs and adding values once per year; only one 2002/2010/2021 member is allowed.
selected_year_rows=selected
components=collections.defaultdict(lambda:collections.defaultdict(list))
for s in selected_year_rows:
 if s['source_record_id'] not in ix:continue
 root=find_i(ix[s['source_record_id']]);components[root][int(s['census_year'])].append(s)
for id0 in list(ix):
 find_i(ix[id0])
components=collections.defaultdict(lambda:collections.defaultdict(list))
for s in selected_year_rows:
 if s['source_record_id'] not in ix:continue
 root=find_i(ix[s['source_record_id']]);components[root][int(s['census_year'])].append(s)
# New root may have these selected rows: avoid counting candidate 2010 row with selected current if multiple source rows remain in same component.
full_new=[];base_component_row_mismatches=[]
for x in new_rows:
 if x['independent_decision']!='eligible_new_union_full3':continue
 root=find_i(ix[x['current_source_record_id']])
 year_rows=components[root]
 d={str(y):len(year_rows.get(y,[])) for y in [2002,2010,2021]}
 if any(d[str(y)]!=1 for y in [2002,2010,2021]):
  base_component_row_mismatches.append({'old_source_record_id':x['old_source_record_id'],'current_source_record_id':x['current_source_record_id'],'year_member_counts':d})
  continue
 vals={str(y):int(float(year_rows[y][0]['population'])) for y in [2002,2010,2021]}
 full_new.append({'old_source_record_id':x['old_source_record_id'],'current_source_record_id':x['current_source_record_id'],'population_by_year':vals,'current_name':x['current_name'],'current_type':x['current_type'],'current_region':x['current_region'],'current_point_origin_file':x['current_point_origin_file'],'marginal_full3_population':vals})
# Receipt stats include no claim that candidate population values are newly primary or boundary comparable.
outputs={}
for n in ['eligible_identity_edges.csv','redundant_same_component_confirmations.csv','fixed_raw_source_review_sample.csv','conditional_full3_component_population.csv','review_summary.json']:
 p=OUT/n
 if p.exists():outputs[n]={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'rows':sum(1 for _ in p.open(encoding='utf-8'))-1 if p.suffix=='.csv' else None}
# Write output files after checks.
csvwrite(OUT/'eligible_identity_edges.csv',eligible)
redundant_out=[]
for r in redundancy_rows:
 redundant_out.append({'from_source_record_id':r['old_source_record_id'],'to_source_record_id':r['current_source_record_id'],'from_year':2010,'to_year':2021,'disposition':review_status_by_old[r['old_source_record_id']],'old_population':r['old_population'],'name':r['old_source_name'],'type':r['old_source_type'],'region':r['old_source_region'],'legacy_oktmo_candidate_key':r['projected_OKTMO_candidate_key'],'current_native_oktmo_literal':r['current_selected_native_OKTMO'],'why_not_new_edge':'already connected by baseline accepted same_place component; retained as source proof/confirmation, no duplicate edge append'})
csvwrite(OUT/'redundant_same_component_confirmations.csv',redundant_out)
csvwrite(OUT/'fixed_raw_source_review_sample.csv',rawchecks)
csvwrite(OUT/'conditional_full3_component_population.csv',full_new)
summary_out={'status':'independent_legacy_oktmo_currentpoint_review_complete_candidate_only','candidate_packet_sha256':sha(CAND),'candidate_count':len(candidates),'candidate_population_2010':sum(float(r['old_population']) for r in candidates),'independent_union_edge_count':len(new_rows),'independent_full3_component_count':sum(x['independent_decision']=='eligible_new_union_full3' for x in new_rows),'independent_no2002_union_count':sum(x['independent_decision']=='eligible_new_union_no2002' for x in new_rows),'independent_uf_hardholds':len(uf_holds),'baseline_redundant_confirmations':len(redundancy_rows),'producer_replay_counts':dict(prod_status),'independent_graph_status_counts':dict(ind_status),'raw_publisher_replay_count':len(rawchecks),'raw_replay_scope':'all 204 proposed marginal union rows plus fixed 100-row risk sample (overlap deduplicated) using source-workbook SHA, exact worksheet row cells, or literal PDF page text','fixed_sample_definition':{'seed':20261004,'target_n':100,'strata':['top 20 2010 population among new union rows','top-mass and seeded random row per publisher source file','five random rows per accepted point-origin file family','five random rows per publisher district-context status','seeded random fill to 100'],'interpretation':'risk-directed sample; not a prevalence estimate'},'all_candidate_vector_rules_passed':all_true_count,'all_candidate_canonical_additive_nonfederal_collision_guards_passed':len(candidates),'all_candidate_2009_2011_raw_classifier_locators_replayed':len(candidates),'all_candidate_historical_name_type_region_and_unique_key_rows_replayed':len(candidates),'all_candidate_historical_coordinate_distances_recomputed_and_within_5km':len(candidates),'all_candidate_accepted_current_points_replayed':len(candidates),'all_candidate_2010_source_key_and_current_native_code_uniqueness_replayed':len(candidates),'population_quality_upgrades':0,'identity_or_coordinate_ledger_mutations':0,'same_year_holds':len(uf_holds),'conditional_full3_population_vectors':{str(y):sum(x['population_by_year'][str(y)] for x in full_new) for y in [2002,2010,2021]},'component_source_year_count_mismatches':base_component_row_mismatches[:10],'legacy_identity_conflict_reason_counts':dict(legacy_conflict_reasons),'source_family_counts':dict(sourcefile_counts),'current_point_origin_family_counts':dict(point_origin_counts),'direct_district_status_counts':dict(district_counts),'source_interpretation':'The producer district-status fields are header-profile observations; they are not used to claim district identity or blankness. Exact raw source rows were independently reopened for every marginal edge plus fixed risk sample. Legacy projected OKTMO remains a candidate key only. It is not cited as native historical binding. District blanks remain unknown and inherited selected district fields are not promoted to publisher fact. 2010 protected counts remain secondary, with no quality upgrade. Modern accepted points support retrospective physical continuity, not 2010 coordinate measurement or boundary comparison. Distinct native code families and all legacy conflict reasons remain retained.'}
(OUT/'review_summary.json').write_text(json.dumps(summary_out,ensure_ascii=False,indent=2)+'\n')
# refresh output pins
for n in ['eligible_identity_edges.csv','redundant_same_component_confirmations.csv','fixed_raw_source_review_sample.csv','conditional_full3_component_population.csv','review_summary.json']:
 p=OUT/n;outputs[n]={'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size,'rows':sum(1 for _ in p.open(encoding='utf-8'))-1 if p.suffix=='.csv' else None}
receipt_out={'status':'independent_legacy_oktmo_currentpoint_review_complete_candidate_only','review_decision':'approve exact 204 marginal same_place candidate edges under the frozen scoped rule; retain 1455 already-connected source rows as confirmations and do not append them as new edges','candidate_artifact':{'path':str(CAND),'sha256':sha(CAND),'expected_sha256':PINS[CAND]},'base_graph':{'path':str(GRAPH),'sha256':sha(GRAPH)},'base_selected':{'path':str(SEL),'sha256':sha(SEL)},'base_points':{'path':str(POINTS),'sha256':sha(POINTS)},'base_source_evidence':{'path':str(EVID),'sha256':sha(EVID)},'source_family_classifier_inputs':{'raw_2009_path':str(RAW09),'raw_2009_sha256':sha(RAW09),'raw_2011_path':str(RAW11),'raw_2011_sha256':sha(RAW11),'historical_named_candidate_path':str(H),'historical_named_candidate_sha256':sha(H)},'frozen_producer_receipt_sha256':sha(RECEIPT),'rule':'Candidate-key-only legacy projected OKTMO must equal one unique literal current selected native OKTMO, but is not historical code binding evidence. Identity support is exact old/current physical name+type+province, exact raw 2009 and 2011 native classifier code/name/type rows with unique whole source keys and physical settlement status, accepted current point, additive nonfederal no-collision source, and old-source-to-current-target fan-in uniqueness. No population equality used as identity proof.','admission_scope':{'eligible_edge_rows':len(eligible),'redundant_confirmation_rows':len(redundant_out),'current_population_2010_secondary_total':sum(float(r['old_population']) for r in candidates),'historical_point_distance_cap_used_by_candidate_rule_km':5.0,'boundary_comparability_asserted':False,'historical_2010_coordinate_measurement_claimed':False,'historical_native_OKTMO_binding_claimed':False,'population_quality_upgraded':False},'holds':{'union_year_collision':len(uf_holds),'raw_source_replay_failures':0,'classifier_locator_failures':0,'accepted_current_point_mismatches':0,'native_code_uniqueness_failures':0},'output_files':outputs,'limitations':['This review approves physical same-place edges only; it does not certify 2010 protected counts as primary.','2011 historical coordinate distance can be source-dependent when the accepted current point itself comes from the 2011 GeoKLADR source; no independent coordinate claim is made for those rows.',"Publisher district blanks remain unknown; the source row selected/inherited district field is not direct publisher evidence.",'A nonblank district/header value is retained literally; no general administrative-boundary crosswalk is asserted.','Native 2009/2011 OKATO evidence does not prove old 2010 publisher OKTMO binding; do not carry or repair codes across systems.','Modern point reuse is retrospective stable-place continuity with unknown coordinate measurement date, not exact 2010 census geometry.'],'review_outputs':outputs,'review_script_path':str(Path(__file__).resolve()),'review_script_sha256':sha(__file__)}
(OUT/'review_receipt.json').write_text(json.dumps(receipt_out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':receipt_out['status'],'eligible':len(eligible),'redundant':len(redundant_out),'full3':len(full_new),'uf_holds':len(uf_holds),'raw_replays':len(rawchecks),'pop_vectors':summary_out['conditional_full3_population_vectors'],'outputs':outputs,'receipt_sha256':sha(OUT/'review_receipt.json')},ensure_ascii=False,indent=2))
