#!/usr/bin/env python3
"""Fixed raw-source sample and candidate packet for the all-residual 2010 corridor."""
import csv,hashlib,json,random,re,sys
from collections import Counter,defaultdict
from pathlib import Path
import duckdb,xlrd
ROOT=Path('/workspace'); OUT=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004/raw_review_v1';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'russian-settlements-research/research_rebuild/mass_linkage'))
import review_source_order_context_reserve_20261004 as oldreview
SEL=ROOT/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
GRAPH=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_identity_edges.parquet'
POINTS=ROOT/'settlements-work/continuation_20261004/accepted_mass_sixth_reviewed/accepted_point_uses.parquet'
EV=ROOT/'settlements-work/candidates/optimized_run/source_evidence.parquet'
MAN=ROOT/'settlements-baseline/output/input_manifest.csv';RAW=ROOT/'settlements-raw'
QUANT=ROOT/'settlements-work/continuation_20261004/root/R4/source_order_context_all_residual_2010_20261004'
QCSV=QUANT/'provisional_5row_candidates.csv'
PSTAT={'reviewed_rule_accepted','reviewed_extension_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_case_accepted'}
REL_ONLY={'ordinal_historical_identifier_hypothesis','legacy_not_accepted','stale_target_entity','text_similarity_only'}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def txt(x):return '' if x is None else str(x).strip()
def norm(x):
 import unicodedata
 return oldreview._source_label_key(unicodedata.normalize('NFKC',txt(x)).replace('ё','е'))
def num(x):
 if x is None:return None
 try:
  v=float(str(x).replace('\xa0','').replace(' ','').replace(',','.'))
  return int(v) if v.is_integer() else v
 except:return None
def jcells(row):
 out=[]
 for v in row:
  if v is None:out.append(None)
  elif isinstance(v,(int,float)):
   x=float(v);out.append(int(x) if x.is_integer() else x)
  else:out.append(str(v))
 return out

with open(QCSV,encoding='utf-8') as f:cand=list(csv.DictReader(f))
con=duckdb.connect();con.execute('SET threads=1');con.execute("SET memory_limit='1200MB'")
ids=set()
for r in cand:ids|={r['from_2010_id'],r['to_2002_id'],r['accepted_current_2021_id']}
con.register('cand_ids',duckdb.query('SELECT * FROM (VALUES '+','.join("('"+x.replace("'","''")+"')" for x in ids)+') t(id)').df())
relevant_files=sorted({r['source_file_2010'] for r in cand}|{r['source_file_2002'] for r in cand})
file_sql=','.join("'"+x.replace("'","''")+"'" for x in relevant_files)
rows=con.execute(f"SELECT source_record_id,census_year,source_file,source_sheet,source_row,source_name_raw,settlement_name,settlement_type,region_raw,district_raw,municipality_raw,population,population_scope,population_value_quality,entity_grain_status,is_additive_settlement_record,oktmo,okato,source_sha256,source_locator FROM read_parquet('{SEL}') WHERE source_record_id IN (SELECT id FROM cand_ids) OR (try_cast(census_year as int) IN (2002,2010) AND source_file IN ({file_sql}))").fetchall()
rec={r[0]:r for r in rows}
# Source-order homonym stratum: repeated exact typed name in old year/file/province.
old02=con.execute(f"SELECT source_record_id,settlement_name,settlement_type,region_raw,source_file FROM read_parquet('{SEL}') WHERE census_year=2002").fetchall()
hom=Counter((norm(x[1]),norm(x[2]),norm(x[3]),x[4]) for x in old02)
for r in cand:
 rr=rec[r['to_2002_id']];r['old_homonym_count']=hom[(norm(rr[6]),norm(rr[7]),norm(rr[8]),rr[2])]
 # Main selected value and source row facts used for downstream output.
 a=rec[r['from_2010_id']];b=rec[r['to_2002_id']];m=rec[r['accepted_current_2021_id']]
 r['_a']=a;r['_b']=b;r['_m']=m
 r['_population']=int(a[11] or 0)

# Deterministic disjoint risk strata: largest 34, old-year homonyms 33, seed 33.
chosen=[];seen=set()
def take(rows,n,label,order=None):
 sub=[x for x in rows if x['from_2010_id'] not in seen]
 if order:sub.sort(key=order,reverse=True)
 else:random.Random(20261004+len(chosen)).shuffle(sub)
 for r in sub[:n]:r['sample_stratum']=label;chosen.append(r);seen.add(r['from_2010_id'])
take(cand,34,'high_population',lambda x:x['_population'])
take([r for r in cand if int(r['old_homonym_count'])>1],33,'old2002_homonym_risk',lambda x:x['_population'])
take(cand,33,'seeded_source_pair_risk')
if len(chosen)<100:take(cand,100-len(chosen),'seeded_supplement')
if len(chosen)!=100:raise RuntimeError(f'Expected fixed sample size 100; got {len(chosen)}')

manifest={}
for line in csv.DictReader(open(MAN,encoding='utf-8-sig')):manifest[line['path']]=line.get('sha256','')
group=defaultdict(list)
for r in chosen:
 group[(r['_b'][2],r['_b'][3])].append(r['_b']);group[(r['_a'][2],r['_a'][3])].append(r['_a'])
rawmeta={};wb_cache={}
def workbook(rel):
 if rel in wb_cache:return wb_cache[rel]
 p=RAW/rel
 if not p.is_file():rawmeta[rel]={'exists':False,'path':str(p)};return None
 h=sha(p);rawmeta[rel]={'exists':True,'path':str(p),'sha256':h,'bytes':p.stat().st_size,'manifest_sha256':manifest.get(rel,''),'matches_manifest':bool(manifest.get(rel) and manifest[rel]==h)}
 w=xlrd.open_workbook(p,on_demand=True);wb_cache[rel]=w;return w

def get_sheet(rel,sheet):
 w=workbook(rel)
 if w is None:return None
 try:return w.sheet_by_name(str(sheet))
 except Exception:
  try:return w.sheet_by_index(int(sheet))
  except:return None

def labelmatch(v,expected):return norm(v)==norm(expected)
def typepass(label,expected):return oldreview.parse_type_label(label,expected)[0]
def header_col(sh,year,namecol):
 matches=[]
 for ri in range(min(40,sh.nrows)):
  for col in range(sh.ncols):
   k=norm(sh.cell_value(ri,col))
   if not k or col<=namecol:continue
   ok=(year==2002 and ('численность' in k or k=='население')) or (year==2010 and k in {'всего','все население','численность населения','численность'})
   if ok:matches.append((ri,col,k))
 if not matches:return None
 bestrow=min(x[0] for x in matches);same=[x for x in matches if x[0]==bestrow]
 same.sort(key=lambda x:(x[1]-namecol,x[1]));return same[0]

# Fetch every five-row selected sequence represented by the chosen window.
seq_cache={}
for year in (2002,2010):
 yrows=[r for r in rows if int(r[1])==year]
 filegroups=defaultdict(list)
 for r in yrows:filegroups[(r[2],str(r[3]))].append(r)
 for k,v in filegroups.items():seq_cache[(year,*k)]=sorted(v,key=lambda x:float(x[4] or 0))

sample_out=[];raw_witnesses=[];anchorlookup={}
for cnd in chosen:
 b=cnd['_b'];a=cnd['_a'];m=cnd['_m'];windows=json.loads(cnd['anchor_windows_5_json'])
 possible=[w for w in windows if w.get('id02')==cnd['to_2002_id'] and float(w.get('focal_row10',-1))==float(a[4])]
 win=max(possible,key=lambda w:(w['anchors_excluding_focal'],w['anchors_total'])) if possible else None
 if not win:raise RuntimeError('Candidate has no preserved exact 5-row window')
 year_evidence={};district_heading_proofs=[];sequence_ok=True;run_data={}
 for yr, focal, start_row in [(2002,b,win['start02']),(2010,a,win['start10'])]:
  filesheet=(focal[2],str(focal[3]));seq=seq_cache[(yr,*filesheet)]
  start_ix=next((i for i,x in enumerate(seq) if float(x[4])==float(start_row)),None)
  focal_id=cnd['to_2002_id'] if yr==2002 else cnd['from_2010_id']
  focal_ix=next((i for i,x in enumerate(seq) if x[0]==focal_id),None)
  if start_ix is None or focal_ix is None or focal_ix<start_ix or focal_ix>=start_ix+5:
   sequence_ok=False;year_evidence[str(yr)]={'status':'selected_row_window_mismatch'};continue
  wr=seq[start_ix:start_ix+5]
  if len(wr)!=5:sequence_ok=False
  sh=get_sheet(focal[2],focal[3])
  if sh is None:sequence_ok=False;year_evidence[str(yr)]={'status':'missing_raw_sheet'};continue
  entries=[]
  for selected in wr:
   raw_rownum=int(float(selected[4]));raw_row=sh.row_values(raw_rownum-1) if raw_rownum-1<sh.nrows else []
   expected=txt(selected[5]);found=[i for i,v in enumerate(raw_row) if labelmatch(v,expected)]
   namecol=found[0] if len(found)==1 else None;rawlab=txt(raw_row[namecol]) if namecol is not None else ''
   phead=header_col(sh,yr,namecol) if namecol is not None else None
   rawpop=raw_row[phead[1]] if phead and phead[1]<len(raw_row) else None
   expectedpop=int(selected[11]) if selected[11] is not None else None
   popnum=num(rawpop); popstatus='exact' if popnum is not None and expectedpop==popnum else ('raw_missing' if popnum is None else 'differs_from_selected')
   tp=typepass(rawlab,selected[7]) if namecol is not None else False
   rowentry={'source_record_id':selected[0],'row_1based':raw_rownum,'selected_order_name':selected[6],'selected_type':selected[7],'source_name_raw_selected':expected,'raw_label':rawlab,'raw_label_exact':bool(namecol is not None),'raw_type_prefix_pass':bool(tp),'population_header_row_1based':phead[0]+1 if phead else None,'population_header_text':phead[2] if phead else None,'raw_population_cell':txt(rawpop),'selected_population_unchanged':expectedpop,'raw_population_check':popstatus,'population_quality':selected[13],'population_scope':selected[12],'entity_grain_status':selected[14],'is_additive_settlement_record':selected[15],'district_raw_preserved':selected[9] if yr==2010 else selected[9],'row_all_cells_json':json.dumps(jcells(raw_row),ensure_ascii=False)}
   if not rowentry['raw_label_exact'] or not tp:sequence_ok=False
   entries.append(rowentry)
   if yr==2002 and selected[9]:
    dk=oldreview._district_key(selected[9]); matches=[]
    for rr in range(raw_rownum-1):
     for vv in sh.row_values(rr):
      lab=txt(vv)
      if 'район' in norm(lab) and dk and oldreview.district_context_matches(selected[9],lab):matches.append({'row_1based':rr+1,'raw_label':lab})
    nearest=matches[-1:] if matches else []
    district_heading_proofs.append({'source_record_id':selected[0],'selected_district_raw':selected[9],'matching_preceding_district_labels':nearest,'printed_parent_visible':bool(nearest)})
  tokens=[(norm(x['raw_label']),norm(x['selected_type'])) for x in entries]
  if len(entries)!=5 or len(set(tokens))<1:sequence_ok=False
  year_evidence[str(yr)]={'source_file':focal[2],'source_sheet':str(sh.name),'workbook_sha256':rawmeta[focal[2]]['sha256'],'raw_rows_in_source_order':entries,'five_raw_names_and_types_pass':all(x['raw_label_exact'] and x['raw_type_prefix_pass'] for x in entries),'raw_rows_increasing':all(int(entries[z]['row_1based'])<int(entries[z+1]['row_1based']) for z in range(4)),'exact_raw_values_and_populations_retained':True}
  run_data[yr]=wr
 # Verify five 2002 block records point at one actual printed district, and the focal target has a label.
 old_districts={norm(x[9]) for x in run_data.get(2002,[]) if x[9]}
 focal_district=txt(b[9]);focal_context=any(x['source_record_id']==b[0] and x['printed_parent_visible'] for x in district_heading_proofs)
 same_district=len(old_districts)==1 and bool(focal_district) and norm(focal_district) in old_districts
 nanchor=int(win['anchors_excluding_focal'])
 sample_out.append({'source_id_2010':a[0],'source_id_2002':b[0],'current_source_id_2021':m[0],'sample_stratum':cnd['sample_stratum'],'candidate_population_2010':int(a[11] or 0),'five_row_anchor_count_excluding_focal':nanchor,'raw_2010_district_value_preserved':a[9],'raw_2002_selected_district':focal_district,'raw_2002_nearest_printed_parent_visible':focal_context,'five_2002_rows_same_selected_district':same_district,'five_raw_rows_name_type_order_pass_both_years':sequence_ok,'raw_window_evidence_json':json.dumps(year_evidence,ensure_ascii=False),'five_2002_district_evidence_json':json.dumps(district_heading_proofs,ensure_ascii=False),'sample_status':'candidate_only_for_independent_review' if sequence_ok and same_district and focal_context else 'hold_raw_source_or_context_check'})

# Release cached workbooks before producing any bulky serialized output.
for w in wb_cache.values():
 try:w.release_resources()
 except:pass

# Preserve graph anchors supporting the sampled windows with accepted decision pins.
anchor_pairs=set()
for cnd in chosen:
 w=max(json.loads(cnd['anchor_windows_5_json']),key=lambda x:(x['anchors_excluding_focal'],x['anchors_total']))
 anchor_pairs.update((x['id02'],x['id10']) for x in w['anchor_pairs'])
for aa,bb,did,status,rid,rsha,euri,esha in con.execute(f"SELECT from_source_record_id,to_source_record_id,decision_id,decision_status,review_id,review_sha256,evidence_uri,evidence_sha256 FROM read_parquet('{GRAPH}') WHERE relation='same_place' AND decision_status IN ({','.join(repr(x) for x in sorted(oldreview.STATUSES))})").fetchall():
 if (aa,bb) in anchor_pairs or (bb,aa) in anchor_pairs:anchorlookup[(aa,bb)]={'decision_id':did,'decision_status':status,'review_id':rid,'review_sha256':rsha,'evidence_uri':euri,'evidence_sha256':esha}

# Enrich staged candidates with current native code + point receipt and exact source hierarchy roles.
point_rows=con.execute(f"SELECT target_source_record_id,latitude,longitude,coordinate_source,coordinate_source_record_id,source_sha256,source_locator,coordinate_admission_status,coordinate_source_origin,coordinate_provider_id FROM read_parquet('{POINTS}') WHERE try_cast(target_year as double)=2021 AND coordinate_admission_status IN ({','.join(repr(x) for x in sorted(PSTAT))})").fetchall()
pm=defaultdict(list)
for p in point_rows:pm[p[0]].append(p)
edge_rows=[]
for r in cand:
 a=r['_a'];b=r['_b'];m=r['_m'];ws=json.loads(r['anchor_windows_5_json']);best=max(ws,key=lambda x:(x['anchors_excluding_focal'],x['anchors_total']))
 edge_rows.append({'from_source_record_id':a[0],'to_source_record_id':m[0],'relation':'same_place_candidate','decision_status':'candidate_only_pending_independent_review','rule_family':'anchored_exact_typed_name_source_order_block_v1','to_supporting_2002_source_record_id':b[0],'focal_population_2010':int(a[11] or 0),'focal_population_quality':a[13],'focal_population_scope':a[12],'from_source_file':a[2],'from_source_sheet':str(a[3]),'from_source_row':a[4],'from_source_name_raw':a[5],'from_name':a[6],'from_type':a[7],'from_region_raw':a[8],'from_district_raw_preserved':a[9],'from_source_sha256_selected':a[18],'from_source_locator':a[19],'support_2002_source_file':b[2],'support_2002_source_sheet':str(b[3]),'support_2002_source_row':b[4],'support_2002_name_raw':b[5],'support_2002_name':b[6],'support_2002_type':b[7],'support_2002_region_raw':b[8],'support_2002_district_raw':b[9],'support_2002_source_sha256_selected':b[18],'support_2002_source_locator':b[19],'current_2021_name':m[6],'current_2021_type':m[7],'current_2021_region_raw':m[8],'current_2021_native_oktmo_raw':m[16],'current_2021_native_okato_raw':m[17],'current_source_sha256':m[18],'current_source_locator':m[19],'current_accepted_point_json':json.dumps([{'lat':p[1],'lon':p[2],'source':p[3],'coordinate_source_record_id':p[4],'sha256':p[5],'locator':p[6],'status':p[7],'origin':p[8],'provider_id':p[9]} for p in pm.get(m[0],[])],ensure_ascii=False),'order_window_rule':'five consecutive selected proper-province typed-name observations within each pinned source sheet, exact 2002/2010 token-vector equality, >=2 accepted same_place anchors excluding focal position','source_order_proof_json':json.dumps(best,ensure_ascii=False),'accepted_anchor_decisions_json':json.dumps([{'from_2002':x['id02'],'to_2010':x['id10'],**anchorlookup.get((x['id02'],x['id10']),anchorlookup.get((x['id10'],x['id02']),{}))} for x in best['anchor_pairs']],ensure_ascii=False),'raw_2002_actual_district_source':b[9],'raw_2010_district_preserved':a[9],'graph_safety_from_quantifier':'disjoint census-year components; current code+point unique per support component','identity_status':'inferred_same_physical_settlement_candidate','population_boundary_comparability':'not_asserted','point_action':'none; only accepted current point existing in baseline','admission_allowed':False})

review_path=OUT/'fixed_100_raw_source_order_review.csv'; edge_path=OUT/'candidate_identity_edges.csv'; hash_path=OUT/'raw_source_file_pins.csv'
with review_path.open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(sample_out[0]));w.writeheader();w.writerows(sample_out)
with edge_path.open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(edge_rows[0]),extrasaction='raise');w.writeheader();w.writerows(edge_rows)
with hash_path.open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=['source_file','path','sha256','bytes','manifest_sha256','matches_input_manifest']);w.writeheader()
 for rel,meta in sorted(rawmeta.items()):
  w.writerow({'source_file':rel,'path':meta.get('path',''),'sha256':meta.get('sha256',''),'bytes':meta.get('bytes',''),'manifest_sha256':meta.get('manifest_sha256',''),'matches_input_manifest':meta.get('matches_manifest',False)})

summary={'status':'candidate_only_raw_fixed_sample_no_admissions','candidate_edges':len(edge_rows),'candidate_population_2010_endpoint_sum':sum(int(x['focal_population_2010']) for x in edge_rows),'sample_size':len(sample_out),'sample_strata':dict(Counter(x['sample_stratum'] for x in sample_out)),'sample_raw_window_pass':sum(x['five_raw_rows_name_type_order_pass_both_years'] for x in sample_out),'sample_2002_same_district_pass':sum(x['five_2002_rows_same_selected_district'] for x in sample_out),'sample_focal_2002_parent_visible':sum(x['raw_2002_nearest_printed_parent_visible'] for x in sample_out),'sample_full_source_context_pass':sum(x['sample_status']=='candidate_only_for_independent_review' for x in sample_out),'sample_population_raw_exact_2010_rows':sum(sum(1 for q in json.loads(x['raw_window_evidence_json'])['2010']['raw_rows_in_source_order'] if q['raw_population_check']=='exact') for x in sample_out),'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in (SEL,GRAPH,POINTS,EV,MAN,QCSV)},'outputs':{},'limitations':['Source order is not written as district metadata. The selected 2010 district value is preserved unchanged, including null.','The source-order match is only candidate identity evidence; no edge or point use is admitted.','Populations remain exactly the selected values; raw comparison counts are reported separately and never substituted.','Candidate current points are existing accepted ledger uses; this packet adds none.']}
for p in (review_path,edge_path,hash_path):summary['outputs'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size,'rows':sum(1 for _ in open(p,encoding='utf-8'))-1}
summary['generator']=str(Path(__file__).resolve());summary['generator_sha256']=sha(Path(__file__))
(OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2))
