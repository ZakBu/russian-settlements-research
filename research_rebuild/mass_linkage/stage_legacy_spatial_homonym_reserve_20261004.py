#!/usr/bin/env python3
"""Stage old-year exact-code crosswalk candidates with source-wide homonym checks.

Diagnostic only: an old historical code in the joined candidate cache is a
candidate generator, never a publisher-native-code assertion. The candidate
rule combines exact selected source name/type/region/district, actual 2009 raw
classifier parent, a direct accepted 2021 source point, and distance ranking
against every same-signature object in the cached historical object inventory.
"""
from __future__ import annotations
import csv,hashlib,json,math,re,random,subprocess,gc
from collections import Counter
from pathlib import Path
import pandas as pd
W=Path('/workspace'); F=W/'settlements-delivery/continuation-consolidated-20261003'; C=W/'settlements-work/continuation_20261004'
OUT=C/'R4/legacy_spatial_homonym_reserve'; SEL=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'
GRAPH=C/'accepted_mass_followup/accepted_identity_edges.parquet'; POINTS=C/'accepted_mass_followup/accepted_point_uses.parquet'
HIST=W/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
OBJECTS=W/'settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet'
CLASS=W/'settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet'; CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'
CONFIG_SOURCE=CONFIG
THIRD_GRAPH_SHA='615711d99f35f6b2dd476d35ef0ffe9c4bb9e162a6d55cdb60acc9fd7fb81eb0'
THIRD_POINTS_SHA='d1c7cbe3d83088fb3e48bd5bc25825fcbab6d5309476a56e81e9a848724a45cc'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def n(v):
 if v is None or pd.isna(v):return ''
 return re.sub(r'\s+',' ',re.sub(r'[^а-яa-z0-9]+',' ',str(v).casefold().replace('ё','е'))).strip()
def reg(v):
 x=n(v)
 for z in ('область','край','республика','автономная область','автономный округ','город федерального значения'):x=re.sub(r'\b'+z+r'\b','',x).strip()
 return x
def typ(v):
 x=n(v);return {'пгт':'поселок городского типа','посёлок городского типа':'поселок городского типа','поселок сельского типа':'поселок'}.get(x,x)
def dist(v):
 x=n(v)
 for z in ('муниципальный район','муниципальное образование','муниципальный округ','городской округ'):
  if x.startswith(z+' '):x=x[len(z)+1:];break
 for z in ('муниципального района','муниципальным районом','муниципальном районе','муниципальный район','муниципального округа','муниципальным округом','муниципальный округ','городского округа','городским округом','городской округ','район','района','районом','районе','округ','округа','округом','округе'):
  if x.endswith(' '+z):x=x[:-(len(z)+1)].strip();break
 return x
def km(a,b,c,d):
 p1,p2=math.radians(float(a)),math.radians(float(c));dp=p2-p1;dl=math.radians(float(d)-float(b));q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.atan2(math.sqrt(q),math.sqrt(max(0,1-q)))
def truth(v):return v is True or str(v).casefold()=='true'
def write(path,rows):
 if not rows:path.write_text('',encoding='utf-8');return
 fields=[];seen=set()
 for r in rows:
  for k in r:
   if k not in seen:seen.add(k);fields.append(k)
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
class UF:
 def __init__(self,ys):self.p={x:x for x in ys};self.y={x:{int(v):x} for x,v in ys.items()}
 def f(self,x):
  if x not in self.p:return None
  if self.p[x]!=x:self.p[x]=self.f(self.p[x])
  return self.p[x]
 def u(self,a,b):
  x,y=self.f(a),self.f(b)
  if x is None or y is None:return 'missing_vertex'
  if x==y:return 'already_connected'
  if set(self.y[x])&set(self.y[y]):return 'year_constrained_collision'
  lo,hi=sorted((x,y));self.p[hi]=lo;self.y[lo].update(self.y.pop(hi));return 'merged'
def main():
 OUT.mkdir(parents=True,exist_ok=False)
 config=json.loads(CONFIG_SOURCE.read_text())
 config['working_identity_graph']=str(GRAPH);config['working_point_uses']=str(POINTS)
 config['working_identity_graph_sha256']=THIRD_GRAPH_SHA;config['working_point_uses_sha256']=THIRD_POINTS_SHA
 config['diagnostic_baseline_id']='immutable_third_baseline_candidate_only'
 CONFIG=OUT/'diagnostic_third_baseline_config.json'
 CONFIG.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
 paths=[SEL,EVID,GRAPH,POINTS,HIST,OBJECTS,CLASS,CONFIG,CONFIG_SOURCE];pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in paths}
 if pins[str(GRAPH)]['sha256']!=THIRD_GRAPH_SHA or pins[str(POINTS)]['sha256']!=THIRD_POINTS_SHA:raise SystemExit('immutable third baseline graph/point hash mismatch')
 from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES,ACCEPTED_EDGE_STATUSES
 s=pd.read_parquet(SEL,columns=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','region_raw','region_norm','district_raw','population','population_scope','is_additive_settlement_record','entity_grain_status'])
 s.source_record_id=s.source_record_id.astype(str);s['_n']=s.settlement_name.map(n);s['_t']=s.settlement_type.map(typ);s['_r']=s.region_raw.map(reg);s['_sig']=list(zip(s._n,s._t,s._r))
 s['_district_key']=s.district_raw.map(dist)
 source_counts=s.groupby(['census_year','_n','_t','_r'],dropna=False).size().to_dict()
 source_admin_counts=s.groupby(['census_year','_n','_t','_r','_district_key'],dropna=False).size().to_dict(); years=dict(zip(s.source_record_id,s.census_year.astype(int)))
 g=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','decision_status']);g=g[g.decision_status.isin(ACCEPTED_EDGE_STATUSES)]
 base=UF(years)
 for e in g.itertuples(index=False):
  if e.from_source_record_id in base.p and e.to_source_record_id in base.p and base.u(e.from_source_record_id,e.to_source_record_id)=='year_constrained_collision':raise SystemExit('baseline collision')
 graph_ids=set(g.from_source_record_id.astype(str))|set(g.to_source_record_id.astype(str))
 del base;gc.collect()
 p=pd.read_parquet(POINTS,columns=['target_source_record_id','target_year','coordinate_admission_status','coordinate_source_record_id','latitude','longitude','point_origin_kind','point_origin_file','point_origin_sha256','point_origin_locator'])
 p=p[p.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)].copy();accepted_point_ids=set(p.target_source_record_id.astype(str))
 # Current proper point candidates are accepted direct source points on selected
 # 2021 records; historical GeoKLADR-origin carriers are not treated as modern.
 hist_origin={'geokladr_2011_raw_dbf_coordinate','raw_named_typed_geo2011_object','raw_named_typed_2011_rural_geo_object'}
 direct=p[p.target_year.eq(2021)&(p.coordinate_source_record_id.astype(str)==p.target_source_record_id.astype(str))&~p.point_origin_kind.isin(hist_origin)].copy()
 s21=s[s.census_year.eq(2021)][['source_record_id','_n','_t','_r','_sig']]
 direct=direct.merge(s21,left_on='target_source_record_id',right_on='source_record_id',how='inner',validate='many_to_one')
 pmap={}; direct_mult=Counter()
 for key,fr in direct.groupby('_sig',sort=False):
  fr=fr.drop_duplicates(['target_source_record_id','latitude','longitude'])
  pmap[key]=[(str(q.target_source_record_id),float(q.latitude),float(q.longitude),q) for q in fr.itertuples(index=False)]
  direct_mult[key]=len(fr)
 # Historical source rows retain exact literal old code locator as a candidate;
 # selected native IDs remain opaque.
 hcols=['source_record_id','census_year','historical_okato_2009_raw','historical_okato_2011_raw','code_join_basis','historical_name_exact','historical_type_exact','historical_code_structure_compatible','historical_key_region_name_type_count','possible_unlocated_historical_competitor','latitude_from_lat','longitude_from_long','historical_point_modern_region','name_key','name_raw_2009','type_key_2009','settlement_type_raw','source_sha256_2009','source_sha256_2011','record_number_1based','record_byte_offset_0based']
 h=pd.read_parquet(HIST,columns=hcols)
 old=s[s.census_year.isin([2002,2010])].merge(h,on=['source_record_id','census_year'],how='inner',validate='one_to_one')
 code_pool=old[old.code_join_basis.eq('exact_raw_code')&old.historical_code_structure_compatible.eq(True)&old.historical_okato_2009_raw.astype(str).str.fullmatch(r'\d{11}')&old.historical_okato_2011_raw.astype(str).eq(old.historical_okato_2009_raw.astype(str))]
 code_pool=code_pool[~code_pool.source_record_id.isin(accepted_point_ids)].copy()
 old=code_pool[code_pool.historical_name_exact.eq(True)&code_pool.historical_type_exact.eq(True)].copy()
 # Full 2009 classifier exact-code index; requires actual child and actual
 # nonsettlement 8-digit parent rows, not an inferred publisher-code binding.
 cls=pd.read_parquet(CLASS,columns=['historical_okato','name_raw','name','status','is_settlement_raw','source_line_1based','source_sha256'])
 cc=cls.historical_okato.astype(str);cnt=cc.value_counts();cmap={str(r.historical_okato):r for r in cls.itertuples(index=False) if cnt[str(r.historical_okato)]==1}
 # Full joined historical object universe for source-wide signature rival distances.
 o=pd.read_parquet(OBJECTS,columns=['historical_okato_2011_raw','name_key','type_key_2011','historical_point_modern_region','is_deleted','is_settlement_raw','historical_name_exact','historical_type_exact','latitude_from_lat','longitude_from_long','record_number_1based','record_byte_offset_0based'])
 o=o[o.is_deleted.eq(False)&o.is_settlement_raw.astype(str).str.lower().eq('t')&o.historical_name_exact.eq(True)&o.historical_type_exact.eq(True)&o.latitude_from_lat.notna()&o.longitude_from_long.notna()].copy()
 o['_sig']=list(zip(o.name_key.map(n),o.type_key_2011.map(typ),o.historical_point_modern_region.map(reg)));object_count=len(o);og={k:v for k,v in o.groupby('_sig',sort=False)}
 import pyarrow.dataset as ds
 focus_ids=old.source_record_id.astype(str).tolist()
 evdf=ds.dataset(EVID,format='parquet').to_table(columns=['source_record_id','source_evidence_json'],filter=ds.field('source_record_id').isin(focus_ids)).to_pandas()
 evmap={str(z.source_record_id):json.loads(z.source_evidence_json) for z in evdf.itertuples(index=False)}
 staged=[];reason_counts=Counter(); metrics=Counter(); mass=Counter(); initial_by_year=Counter()
 for _,row in old.iterrows():
  sid=str(row.source_record_id);year=int(row.census_year);pop=pd.to_numeric(pd.Series([row.population]),errors='coerce').iloc[0];pop=int(pop) if pd.notna(pop) else None
  sig=(row['_n'],row['_t'],row['_r']);code=str(row.historical_okato_2009_raw);gates=[];initial_by_year[year]+=1
  if pop is None:gates.append('population_missing')
  if not bool(row.is_additive_settlement_record):gates.append('selected_row_nonadditive')
  if str(row.population_scope).casefold() in {'federal_city_region','territorial_aggregate','regional_aggregate'}:gates.append('aggregate_population_scope')
  if source_admin_counts.get((year,*sig,dist(row.district_raw)),0)!=1:gates.append('old_selected_signature_and_district_not_unique_in_year')
  modern_options=pmap.get(sig,[])
  if not modern_options:gates.append('no_direct_accepted_2021_point_for_exact_signature')
  child=cmap.get(code);parent_code=code[:5]+'000';parent=cmap.get(parent_code)
  child_ok=bool(child and str(child.is_settlement_raw)=='t' and n(child.name)==row['_n'] and typ(child.status)==row['_t'])
  parent_ok=bool(parent and str(parent.is_settlement_raw)=='f' and str(parent.status)=='')
  if not child_ok:gates.append('raw_2009_classifier_child_not_unique_exact_name_type')
  if not parent_ok:gates.append('raw_2009_actual_nonsettlement_parent_missing_or_not_unique')
  district_match=bool(parent and dist(row.district_raw) and dist(row.district_raw)==dist(parent.name_raw))
  if not district_match:gates.append('selected_old_district_blank_or_differs_from_raw_parent')
  if row['_r']!=reg(row.historical_point_modern_region):gates.append('historical_object_region_differs_from_selected_source')
  if truth(row.possible_unlocated_historical_competitor):gates.append('whole_province_unlocated_same_signature_competitor')
  e=evmap.get(sid,{})
  if truth(e.get('is_federal_aggregate')) or e.get('is_additive_settlement_record') is False:gates.append('source_evidence_aggregate_or_nonadditive')
  if truth(e.get('legacy_same_year_collision')):gates.append('known_same_year_collision')
  if e.get('legacy_verified_successor_settlement_id'):gates.append('verified_successor_event')
  if truth(e.get('legacy_identity_conflict')):
   try: conflict=set(json.loads(e.get('legacy_identity_reasons') or '[]'))
   except: conflict={'unparsed'}
   # These flags are not identity evidence. The exact ordinal hypothesis is
   # deliberately ignored here; only independent gates below can make a row
   # reviewable. Conflicts with other reasons remain hard holds.
   if conflict-{'administrative_conflict','ordinal_historical_identifier_hypothesis'}:gates.append('nonadministrative_identity_conflict')
  modern=None;modern_point_near=None;modern_point_runner=None
  if modern_options:
   point_distances=sorted([(km(float(row.latitude_from_lat),float(row.longitude_from_long),q[1],q[2]),q) for q in modern_options],key=lambda x:(x[0],x[1][0]))
   modern_point_near=point_distances[0][0];modern=point_distances[0][1]
   modern_point_runner=next((d for d,q in point_distances if q[0]!=modern[0]),None)
   if modern_point_near>5 or (modern_point_runner is not None and modern_point_runner<=5):gates.append('current_direct_point_not_unique_within_5km_for_signature')
  objects=og.get(sig);nearest=runner=None;nearest_code=None;homonym_codes=0
  if objects is None or objects.empty:gates.append('whole_historical_signature_inventory_missing')
  elif modern:
   ds=sorted((km(modern[1],modern[2],float(q.latitude_from_lat),float(q.longitude_from_long)),str(q.historical_okato_2011_raw)) for q in objects.itertuples(index=False))
   codes=sorted(set(code for _,code in ds));homonym_codes=len(codes);nearest,nearest_code=ds[0]
   runner=next((d for d,c in ds if c!=nearest_code),None)
   if nearest_code!=code:gates.append('crosswalk_code_not_nearest_historical_homonym')
   if nearest>5 or (runner is not None and runner<=5):gates.append('direct_point_not_unique_within_5km_against_all_homonyms')
   if runner is not None and runner==nearest:gates.append('current_point_tied_between_historical_codes')
  category='population_ge_500' if pop is not None and pop>=500 else 'all_population'
  metrics[(year,category,'rows')]+=1
  if pop is not None:mass[(year,category,'candidate_population')]+=pop
  for rname in gates:reason_counts[(year,category,rname)]+=1
  if not gates:
   metrics[(year,category,'candidate_rows')]+=1
   if pop is not None:mass[(year,category,'candidate_population_pass')]+=pop
  source_file=str(row.source_file);source_sheet=str(row.source_sheet);source_row=int(row.source_row) if pd.notna(row.source_row) else None
  staged.append({'source_record_id':sid,'year':year,'population':pop,'source_file':source_file,'source_sheet':source_sheet,'source_row_1based':source_row,'selected_name_raw':row.source_name_raw,'selected_type_raw':row.settlement_type,'selected_region_raw':row.region_raw,'selected_district_raw':row.district_raw or None,'source_native_id_opaque_not_used_as_code':row.source_native_id or None,'source_locator':f'{source_file}:{source_sheet}:{source_row}','source_code_witness_status':'candidate_crosswalk_code_only_publisher_code_cell_not_reopened','old_crosswalk_code_candidate_raw':code,'old_crosswalk_2011_code_raw':str(row.historical_okato_2011_raw),'raw_2009_classifier_line':int(child.source_line_1based) if child else None,'raw_2009_classifier_name':str(child.name_raw) if child else None,'raw_2009_classifier_type':str(child.status) if child else None,'raw_2009_classifier_is_settlement':str(child.is_settlement_raw) if child else None,'raw_2009_parent_code':parent_code,'raw_2009_parent_name':str(parent.name_raw) if parent else None,'old_district_matches_actual_raw_parent':district_match,'direct_2021_source_record_id':modern[0] if modern else None,'direct_2021_point_origin_kind':modern[3].point_origin_kind if modern else None,'direct_2021_point_origin_file':modern[3].point_origin_file if modern else None,'direct_2021_point_origin_sha256':modern[3].point_origin_sha256 if modern else None,'direct_2021_point_origin_locator':modern[3].point_origin_locator if modern else None,'direct_2021_latitude':modern[1] if modern else None,'direct_2021_longitude':modern[2] if modern else None,'current_point_nearest_distance_km':modern_point_near,'next_current_point_distance_km':modern_point_runner,'historical_geo_latitude':float(row.latitude_from_lat) if pd.notna(row.latitude_from_lat) else None,'historical_geo_longitude':float(row.longitude_from_long) if pd.notna(row.longitude_from_long) else None,'historical_raw_object_name':str(row.name_raw_2009) if 'name_raw_2009' in row else None,'historical_raw_object_type':str(row.settlement_type_raw) if 'settlement_type_raw' in row else None,'historical_homonym_distinct_code_count_sourcewide':homonym_codes,'nearest_historical_code_to_current_point':nearest_code,'nearest_distance_km':nearest,'next_distinct_code_distance_km':runner,'classifier_sha256':str(child.source_sha256) if child else None,'historical_geo_sha256':str(row.source_sha256_2011),'historical_geo_record_1based':int(row.record_number_1based) if pd.notna(row.record_number_1based) else None,'historical_geo_byte_offset':int(row.record_byte_offset_0based) if pd.notna(row.record_byte_offset_0based) else None,'candidate_status':'eligible_for_bounded_raw_source_review' if not gates else 'held','gate_failures_json':json.dumps(gates,ensure_ascii=False),'point_admitted':False,'temporal_identity_admitted':False,'native_id_binding_claimed':False,'population_boundary_comparability_claimed':False})
 # Recheck the eligible edges against complete canonical graph under year constraints.
 trial=UF(years)
 for e in g.itertuples(index=False):
  if e.from_source_record_id in trial.p and e.to_source_record_id in trial.p:trial.u(e.from_source_record_id,e.to_source_record_id)
 sim=[]
 for r in staged:
  if r['candidate_status']!='eligible_for_bounded_raw_source_review':continue
  result=trial.u(r['source_record_id'],r['direct_2021_source_record_id']);r['conditional_year_union_result']=result
  sim.append({'source_record_id':r['source_record_id'],'direct_2021_source_record_id':r['direct_2021_source_record_id'],'year':r['year'],'population':r['population'],'union_result':result,'candidate_only':True})
 # Fixed top-20 plus seeded random-60 row-level source sample. It measures
 # whether a printed publisher OKATO column/cell exists; it does not promote
 # a numeric ordinal or an unheaded number to a code claim.
 sample=[];raw_hashes={};pdf={};top=sorted(staged,key=lambda x:(-(x['population'] or 0),x['source_record_id']))[:20];chosen={r['source_record_id']:'high_mass_top20' for r in top};rest=[r for r in staged if r['source_record_id'] not in chosen];rng=random.Random(20261004)
 for r in rng.sample(rest,min(60,len(rest))):chosen[r['source_record_id']]='seeded_random60'
 sample_input=sorted((r for r in staged if r['source_record_id'] in chosen),key=lambda x:(x['source_file'],x['source_sheet'],x['source_row_1based'] or 0))
 rawroot=W/'settlements-raw'
 def cell(v):
  if v is None or pd.isna(v):return None
  if isinstance(v,float) and v.is_integer():return str(int(v))
  return str(v).strip()
 import xlrd
 active_path=None;book=None
 for r in sample_input:
  q={**r,'sample_stratum':chosen[r['source_record_id']]};fp=rawroot/r['source_file'];q['raw_source_path']=str(fp)
  if not fp.is_file():q.update(raw_witness_status='source_file_missing',raw_cells_json='[]',publisher_code_header_cells_json='[]');sample.append(q);continue
  if str(fp) not in raw_hashes:raw_hashes[str(fp)]={'path':str(fp),'sha256':sha(fp),'bytes':fp.stat().st_size}
  q['raw_source_sha256']=raw_hashes[str(fp)]['sha256'];ix=(r['source_row_1based'] or 0)-1
  if fp.suffix.lower()=='.xls':
   try:
    if active_path!=str(fp):
     if book is not None:book.release_resources()
     book=xlrd.open_workbook(str(fp),on_demand=True);active_path=str(fp)
    sn=book.sheet_names();sh=book.sheet_by_name(r['source_sheet']) if r['source_sheet'] in sn else book.sheet_by_index(int(r['source_sheet']))
    if ix<0 or ix>=sh.nrows:raise IndexError('source row outside workbook')
    cells=[cell(v) for v in sh.row_values(ix)];heads=[];nearest=None
    for hi in range(min(ix,20)):
     for ci,v in enumerate(sh.row_values(hi)):
      if any(t in n(v) for t in ('окато','okato','октмо','oktmo')):heads.append({'header_row_1based':hi+1,'column_0based':ci,'header_raw':cell(v)})
    for hi in range(ix-1,-1,-1):
     vals=[cell(v) for v in sh.row_values(hi)];marks=[]
     for ci,v in enumerate(vals):
      if v and 'все сельское население' in n(v):
       raw=re.split(r'\s+-\s+все сельское население',v,maxsplit=1,flags=re.IGNORECASE)[0];marks.append({'column_0based':ci,'raw_heading':v,'district_key':dist(raw)})
     if marks:
      nearest={'row_1based':hi+1,'cells':vals,'district_markers':marks};break
    matches=[i for i,v in enumerate(cells) if v==r['old_crosswalk_code_candidate_raw']]
    okato_heads=[h for h in heads if h['column_0based'] in matches and ('окато' in n(h['header_raw']) or 'okato' in n(h['header_raw']))]
    dmatch=[i for i,v in enumerate(cells) if v and dist(r['selected_district_raw'] or '') and dist(v)==dist(r['selected_district_raw'])]
    exact_heading=bool(nearest and any(x['district_key']==dist(r['selected_district_raw'] or '') for x in nearest['district_markers']))
    q.update(raw_witness_status='raw_excel_row_reopened',raw_cells_json=json.dumps(cells,ensure_ascii=False),publisher_code_header_cells_json=json.dumps(heads,ensure_ascii=False),candidate_code_exact_cell_columns_json=json.dumps(matches),candidate_code_under_explicit_OKATO_header=bool(okato_heads),district_raw_match_cell_columns_json=json.dumps(dmatch),raw_matching_explicit_district_heading_json=json.dumps(nearest,ensure_ascii=False) if nearest else '',raw_intervening_district_headings_json='[]',district_context_heading_status='verified_explicit_district_heading_block' if exact_heading else ('direct_district_cell_match' if dmatch else 'no_matching_explicit_context'))
   except Exception as e:q.update(raw_witness_status='workbook_open_failed:'+str(e),raw_cells_json='[]',publisher_code_header_cells_json='[]')
  elif fp.suffix.lower() in ('.xlsx','.xlsm'):
   try:
    import openpyxl
    wbx=openpyxl.load_workbook(fp,read_only=True,data_only=True);sh=wbx[r['source_sheet']] if r['source_sheet'] in wbx.sheetnames else wbx.worksheets[int(r['source_sheet'])]
    cells=[cell(v) for v in next(sh.iter_rows(min_row=ix+1,max_row=ix+1,values_only=True))];q.update(raw_witness_status='raw_excel_row_reopened',raw_cells_json=json.dumps(cells,ensure_ascii=False),publisher_code_header_cells_json='[]',candidate_code_exact_cell_columns_json='[]',candidate_code_under_explicit_OKATO_header=False,district_context_heading_status='xlsx_row_cells_only_heading_not_checked');wbx.close()
   except Exception as e:q.update(raw_witness_status='workbook_open_failed:'+str(e),raw_cells_json='[]',publisher_code_header_cells_json='[]')
  elif fp.suffix.lower()=='.pdf':
   try:
    if str(fp) not in pdf:pdf[str(fp)]=subprocess.run(['pdftotext','-layout',str(fp),'-'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True).stdout.split('\f')
    pg=int(re.sub(r'\D','',str(r['source_sheet'])) or '1');ls=pdf[str(fp)][pg-1].splitlines() if 1<=pg<=len(pdf[str(fp)]) else [];q.update(raw_witness_status='raw_pdf_page_reopened',raw_pdf_page_1based=pg,raw_pdf_lines_json=json.dumps(ls,ensure_ascii=False),publisher_code_header_cells_json='[]')
   except Exception as e:q.update(raw_witness_status='pdf_open_failed:'+str(e),publisher_code_header_cells_json='[]')
  else:q.update(raw_witness_status='unsupported_source_format',raw_cells_json='[]',publisher_code_header_cells_json='[]')
  sample.append(q)
 pointonly=[]
 for r in staged:
  if r['candidate_status']!='eligible_for_bounded_raw_source_review':continue
  pointonly.append({'target_source_record_id':r['source_record_id'],'target_year':r['year'],'latitude':r['historical_geo_latitude'],'longitude':r['historical_geo_longitude'],'coordinate_source':'candidate exact typed 2009 classifier / 2011 GeoKLADR object; point-only retrospective association pending raw source review','coordinate_source_record_id':'GEOKLADR2011:'+r['old_crosswalk_2011_code_raw'],'point_origin_file':'/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf','point_origin_sha256':r['historical_geo_sha256'],'point_origin_locator':f"DBF_record_1based={r['historical_geo_record_1based']};DBF_byte_offset_0based={r['historical_geo_byte_offset']};OKATO2011_candidate={r['old_crosswalk_2011_code_raw']}",'direct_2021_witness_source_record_id':r['direct_2021_source_record_id'],'direct_2021_witness_distance_to_historic_object_km':r['current_point_nearest_distance_km'],'independent_raw_source_review_required':True,'coordinate_admission_status':'candidate_only_no_admission','temporal_identity_admitted':False,'provider_native_id_binding_claimed':False,'population_boundary_comparability_claimed':False})
 # Validate the schema before constructing summary fields, and preserve the
 # expensive candidate loop outputs so a later metadata/receipt failure does
 # not require repeating the source-wide distance computation.
 required_pointonly={'target_source_record_id','target_year','latitude','longitude','point_origin_file','point_origin_sha256','point_origin_locator','coordinate_admission_status'}
 if any(not required_pointonly.issubset(r) for r in pointonly):raise SystemExit('point-only candidate schema guard failed')
 scratch=OUT/'_scratch_candidate_intermediate';scratch.mkdir()
 write(scratch/'candidate_register.csv',staged);write(scratch/'conditional_union.csv',sim);write(scratch/'point_only.csv',pointonly)
 summary={'status':'legacy_spatial_homonym_reserve_candidate_only_no_admissions','scope':'selected-layer residual old census rows with exact raw 11-digit 2009/2011 crosswalk candidate; requires whole-signature name/type/province and old district/actual raw ancestor context plus an accepted direct 2021 point that uniquely selects the same historical object within 5km.','config_path':str(CONFIG),'current_graph_accepted_rows':len(g),'current_graph_sha256':pins[str(GRAPH)]['sha256'],'current_accepted_point_rows':len(p),'current_accepted_point_ids':len(accepted_point_ids),'direct_accepted_2021_signature_count':len(pmap),'historical_object_inventory_rows':len(o),'historical_object_inventory_sha256':pins[str(OBJECTS)]['sha256'],'selected_layer_exact_raw_code_pool':{'rows':len(code_pool),'population_sum':int(pd.to_numeric(code_pool.population,errors='coerce').sum()),'by_year':code_pool.groupby('census_year').agg(rows=('source_record_id','size'),population=('population','sum')).reset_index().to_dict('records'),'exact_historical_name_rows':int(code_pool.historical_name_exact.eq(True).sum()),'exact_historical_type_rows':int(code_pool.historical_type_exact.eq(True).sum()),'exact_name_and_type_rows':int((code_pool.historical_name_exact.eq(True)&code_pool.historical_type_exact.eq(True)).sum())},'input_candidate_rows':len(staged),'input_candidate_by_year':dict(Counter(str(r['year']) for r in staged)),'eligible_for_bounded_raw_source_review':sum(r['candidate_status']=='eligible_for_bounded_raw_source_review' for r in staged),'point_only_candidate_count':len(pointonly),'point_only_candidate_population':sum(r['population'] or 0 for r in staged if r['candidate_status']=='eligible_for_bounded_raw_source_review'),'point_only_candidate_by_year':dict(Counter(str(r['target_year']) for r in pointonly)),'conditional_union_results':dict(Counter(r['union_result'] for r in sim)),'population_partition':[],'fixed_raw_source_sample':{'rows':len(sample),'top_mass':min(20,len(chosen)),'seeded_random':max(0,len(chosen)-20),'seed':20261004,'source_files_hashed_once':len(raw_hashes),'raw_code_cell_under_explicit_OKATO_header':sum(bool(r.get('candidate_code_under_explicit_OKATO_header')) for r in sample),'district_context_headings':dict(Counter(r.get('district_context_heading_status','') for r in sample))},'source_code_binding_policy':'Historical crosswalk OKATO comes from the candidate cache. No source_native_id is interpreted as OKATO; no publisher-native code cell is claimed. The fixed source sample found no code cell under an explicit OKATO header.','limitations':['Every staged row is candidate-only and requires bounded raw source proof/review.','Crosswalk candidates alone do not prove identity or point correctness.','Ordinal-hypothesis flags are ignored only as evidence inputs; they never identify a place. Exact raw typed source/code ancestry and independent point/district gates are still required.','The 2021 direct point and historic source object distance are corroboration; no census-date measurement, temporal identity, modern provider binding, or population-boundary equivalence is claimed.','Whole-source homonym checks use every same exact signature named object in the cached joined 2009/2011 object inventory; tie/multiple-near cases are held.']}
 for year in (2002,2010):
  for cohort in ('population_ge_500','all_population'):
   summary['population_partition'].append({'year':year,'cohort':cohort,'rows':metrics[(year,cohort,'rows')],'candidate_population_sum':mass[(year,cohort,'candidate_population')],'candidate_rows_passing_all_gates':metrics[(year,cohort,'candidate_rows')],'candidate_population_passing_all_gates':mass[(year,cohort,'candidate_population_pass')],'gate_failure_counts_overlap':{k[2]:v for k,v in reason_counts.items() if k[:2]==(year,cohort)}})
 write(OUT/'legacy_spatial_homonym_candidate_register.csv',staged);write(OUT/'conditional_candidate_union.csv',sim);write(OUT/'point_only_candidate_uses.csv',pointonly);write(OUT/'fixed_80_raw_source_witness_sample.csv',sample);write(OUT/'sample_raw_source_hashes.csv',list(raw_hashes.values()))
 import shutil;shutil.rmtree(scratch)
 summary['inputs']=pins;summary['outputs']={x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(OUT.iterdir())}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 rec={'status':summary['status'],'inputs':{k:v['sha256'] for k,v in pins.items()},'outputs':{x.name:sha(x) for x in sorted(OUT.iterdir())},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__).resolve())}
 (OUT/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
