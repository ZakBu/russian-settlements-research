#!/usr/bin/env python3
"""Candidate-only ordinary mass rule where native historical point lookup is absent.

Pairs whole-source unique old and current physical census rows by exact typed
name/province keys, source-context compatibility, and an already accepted
proper current point attached to a uniquely coded current source object. An old
native point is not required; when an accepted old point exists it is used only
as a contradiction check. No population equality or P1082 evidence is used.
"""
from __future__ import annotations
import csv, hashlib, json, math, random, re, unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from research_rebuild.mass_linkage.stage_typed_native_physical_corridor_v2_20261004 import YearUF, metrics, truth, write_csv
from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, ACCEPTED_PROJECTION_STATUSES

W=Path('/workspace'); BASE=W/'settlements-work/continuation_20261004'; R4=BASE/'R4'
OUT=R4/'native_point_absent_unique_sourcekey_point_recovery_20261004'
F=W/'settlements-delivery/continuation-consolidated-20261003'
SEL=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'
HIST=W/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
CONFIG=W/'russian-settlements-research/config/mass_joint_20261004.json'

YEARS=(2002,2010,2021)
PHYSICAL={'город','пгт','поселок','деревня','село','хутор','станица','аул','кишлак','слобода','арбан','выселок','починок','местечко','разъезд','станция'}

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def norm(v):
 if v is None or pd.isna(v): return ''
 return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').replace('\xa0',' ').split())

def typ(v):
 s=norm(v).replace('.','').strip()
 return {'поселок сельского типа':'поселок','посёлок сельского типа':'поселок','поселок городского типа':'пгт','посёлок городского типа':'пгт','пгт':'пгт','пос':'поселок','п':'поселок','дер':'деревня','д':'деревня','с':'село','х':'хутор','ст-ца':'станица','стца':'станица','г':'город','гор':'город'}.get(s,s)

def district(v):
 s=norm(v)
 s=re.sub(r'^(городской округ|муниципальный округ|муниципальный район|городской район|район)\s+','',s)
 s=re.sub(r'\s+(муниципальный район|муниципальный округ|городской округ|район|округ)$','',s)
 return s.strip()

def digits(v):
 if v is None or pd.isna(v):return ''
 return re.sub(r'\D','',str(v))

def valid_point(lat,lon):
 try:
  a,b=float(lat),float(lon)
  return math.isfinite(a) and math.isfinite(b) and -90<=a<=90 and -180<=b<=180
 except Exception:return False

def km(a,b,c,d):
 p1,p2=math.radians(float(a)),math.radians(float(c));dp=p2-p1;dl=math.radians(float(d)-float(b))
 z=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.atan2(math.sqrt(z),math.sqrt(max(0,1-z)))

def raw_point(h):
 return bool(h and digits(h.get('historical_okato_2011_raw')) and valid_point(h.get('latitude_from_lat'),h.get('longitude_from_long')))

def population_int(v):
 try:
  q=float(v)
  if math.isfinite(q) and q>=0 and q.is_integer():return int(q)
 except Exception:pass
 return None

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 cfg=json.loads(CONFIG.read_text());G=Path(cfg['working_identity_graph']);P=Path(cfg['working_point_uses']);COV=Path(cfg['working_coverage'])
 # Freeze pins at start; accepted baseline never gets rewritten by this stage.
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SEL,EVID,HIST,G,P,COV,CONFIG]}
 if pins[str(G)]['sha256']!=cfg['working_identity_graph_sha256'] or pins[str(P)]['sha256']!=cfg['working_point_uses_sha256']:raise SystemExit('graph/point-use hashes changed from configuration')
 cols=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','type_norm','region_raw','district_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','okato','oktmo','source_locator','source_sha256']
 # The full source key counts use all selected rows before grain or scope
 # filtering, so nonphysical and duplicate rows can only make uniqueness harder.
 s=pd.read_parquet(SEL,columns=cols);s.source_record_id=s.source_record_id.astype(str)
 s['name_key']=s.settlement_name.map(norm);s['type_key']=s.settlement_type.map(typ);s['region_key']=s.region_raw.map(region_key)
 s['district_key']=s.district_raw.map(district);s['source_pop_int']=s.population.map(population_int)
 s['source_key_usable']=s.name_key.ne('')&s.type_key.ne('')&s.region_key.ne('')
 key=['census_year','name_key','type_key','region_key']
 keycounts=s[s.source_key_usable].groupby(key,dropna=False).source_record_id.nunique().rename('whole_source_key_count').reset_index()
 s=s.merge(keycounts,on=key,how='left');s['whole_source_key_count']=s.whole_source_key_count.fillna(0).astype(int)
 # Build the actual full selected-code uniqueness space for 2021 rows.
 curr_all=s[s.census_year==2021].copy()
 code_counts={}
 for field in ('oktmo','okato'):
  cc=curr_all[[field,'source_record_id']].copy();cc['code']=cc[field].map(digits);cc=cc[cc.code.str.len()==11]
  code_counts[field]=cc.groupby('code').source_record_id.nunique().to_dict()
 # Validate entire accepted temporal UF, canonical statuses, baseline metrics.
 ids=s.source_record_id.tolist();yearmap=dict(zip(s.source_record_id,s.census_year.astype(int)))
 uf=YearUF(ids,s.census_year.astype(int).tolist())
 g=pd.read_parquet(G,columns=['decision_id','from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if not set(g.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES) or not set(g.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES) or not g.relation.eq('same_place').all():raise SystemExit('accepted edge status guard failed')
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in uf.idx or b not in uf.idx or yearmap[a]!=int(e.from_year) or yearmap[b]!=int(e.to_year):raise SystemExit('accepted edge vertex/year mismatch')
  if uf.union_ids(a,b)=='year_constrained_collision':raise SystemExit('accepted graph has a year collision')
 p=pd.read_parquet(P,columns=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','coordinate_provider','coordinate_provider_id','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_source','coordinate_source_sha256','coordinate_source_locator','coordinate_source_file'])
 if p.target_source_record_id.astype(str).duplicated().any():raise SystemExit('duplicate accepted point target')
 if p.coordinate_admission_status.isna().any() or not set(p.coordinate_admission_status.astype(str)).issubset(ACCEPTED_COORDINATE_STATUSES):raise SystemExit('accepted point status guard failed')
 point_ids=set(p.target_source_record_id.astype(str));p.target_source_record_id=p.target_source_record_id.astype(str)
 baseline=metrics(s,uf,point_ids);coverage=json.loads(COV.read_text());control={str(z['year']):z['axes'] for z in coverage['census_metrics']}
 checks={}
 for y in YEARS:
  z=baseline[str(y)];c=control[str(y)]
  full={'rows':int(c['full_census_chain']['rows']),'population':int(c['full_census_chain']['known_population'])}
  joint={'rows':int(c['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(c['joint_admitted_coordinate_and_full_chain']['known_population'])}
  checks[str(y)]={'full_chain_reproduced':z['full_chain']==full,'joint_reproduced':z['joint_point_full_chain']==joint}
 if not all(q['full_chain_reproduced'] and q['joint_reproduced'] for q in checks.values()):raise SystemExit('baseline coverage did not replay; marginal claims suppressed')
 # Target rows: direct 2021 selected physical records with an already accepted
 # point and at least one unique exact 11-digit native current source code.
 cur=s[(s.census_year==2021)&(s.whole_source_key_count==1)&s.source_pop_int.notna()&s.is_additive_settlement_record.fillna(False)&s.type_key.isin(PHYSICAL)].copy()
 cur=cur.merge(p,left_on='source_record_id',right_on='target_source_record_id',how='inner')
 # The point ledger joins on target_source_record_id; disallow non-direct
 # current carrier ambiguity only when target row itself lacks a valid point.
 cur=cur[cur.apply(lambda r:valid_point(r.latitude,r.longitude),axis=1)&cur.coordinate_source_record_id.astype(str).eq(cur.target_source_record_id.astype(str))]
 code_rows=[]
 for r in cur.to_dict('records'):
  valid=[]
  for field in ('oktmo','okato'):
   c=digits(r.get(field))
   if len(c)==11 and code_counts[field].get(c,0)==1:valid.append((field,c))
  if valid:
   r['current_unique_native_codes_json']=json.dumps([{'field':a,'raw':r.get(a),'digits':b} for a,b in valid],ensure_ascii=False)
   r['current_native_code_uniqueness']='at_least_one_11_digit_code_unique_in_full_2021_source'
   code_rows.append(r)
 cur=pd.DataFrame(code_rows)
 stats=Counter()
 stats['current_full_source_unique_physical_rows_with_accepted_point_and_unique_native_code']=len(cur)
 # Old eligible sources are whole-source key unique, additive, and actual
 # publisher physical-NP rows. Missing native point lookup is the target cohort.
 old=s[s.census_year.isin([2002,2010])&(s.whole_source_key_count==1)&s.source_pop_int.notna()&s.is_additive_settlement_record.fillna(False)&s.type_key.isin(PHYSICAL)].copy()
 histcols=['source_record_id','historical_okato_2009_raw','historical_okato_2011_raw','historical_name_exact','historical_type_exact','historical_code_structure_compatible','is_settlement_raw','source_is_aggregate_scope','name_raw_2009','name_raw_2011','settlement_type_raw','record_number_1based','record_byte_offset_0based','latitude_from_lat','longitude_from_long','source_sha256_2009','source_sha256_2011']
 hd=ds.dataset(HIST,format='parquet').to_table(columns=histcols,filter=ds.field('source_record_id').isin(old.source_record_id.tolist())).to_pandas()
 hd.source_record_id=hd.source_record_id.astype(str)
 old=old.merge(hd,on='source_record_id',how='left',suffixes=('','_hist'))
 old['historical_native_point_available']=old.apply(lambda r:raw_point(r.to_dict()),axis=1)
 stats['old_unique_additive_physical_rows']=len(old)
 stats['old_rows_with_available_2011_native_point_lookup']=int(old.historical_native_point_available.sum())
 stats['old_rows_missing_2011_native_point_lookup']=int((~old.historical_native_point_available).sum())
 absent=old[~old.historical_native_point_available].copy()
 # Match exact same canonical physical source key. Exact source-key uniqueness
 # has already been checked against the entire selected file for each year.
 pairs=absent.merge(cur,on=['name_key','type_key','region_key'],suffixes=('_old','_current'),how='inner')
 stats['nativepoint_absent_old_rows_matching_current_unique_source_key']=len(pairs)
 # Compare explicit historical/current district context by narrowly removing
 # only named administrative descriptors. Two absent labels remain unknown;
 # one blank and one explicit, or two different cores, stay on hold.
 olddistrict=pairs.district_key_old.fillna('');newdistrict=pairs.district_key_current.fillna('')
 pairs['district_context_status']=['same_explicit_core' if a and b and a==b else 'both_blank_unknown' if not a and not b else 'unresolved_district_context' for a,b in zip(olddistrict,newdistrict)]
 pairs=pairs[pairs.district_context_status.isin(['same_explicit_core','both_blank_unknown'])].copy()
 stats['after_district_context']=len(pairs)
 # Existing accepted old point is checked only for contradiction; it never
 # establishes identity. Missing point is recorded as unknown.
 oldpts=p.copy();oldpts=oldpts[oldpts.target_year.isin([2002,2010])].copy()
 oldpts=oldpts.rename(columns={'target_source_record_id':'source_record_id_old','latitude':'old_accepted_point_latitude','longitude':'old_accepted_point_longitude','coordinate_provider':'old_accepted_point_provider','coordinate_provider_id':'old_accepted_point_provider_id','coordinate_source_record_id':'old_accepted_point_source_record_id','point_origin_file':'old_point_origin_file','point_origin_sha256':'old_point_origin_sha256','point_origin_locator':'old_point_origin_locator','point_origin_kind':'old_point_origin_kind','coordinate_source':'old_coordinate_source','coordinate_source_sha256':'old_coordinate_source_sha256','coordinate_source_locator':'old_coordinate_source_locator','coordinate_source_file':'old_coordinate_source_file'})
 pairs=pairs.merge(oldpts[['source_record_id_old','old_accepted_point_latitude','old_accepted_point_longitude','old_accepted_point_provider','old_accepted_point_provider_id','old_accepted_point_source_record_id','old_point_origin_file','old_point_origin_sha256','old_point_origin_locator','old_point_origin_kind','old_coordinate_source','old_coordinate_source_sha256','old_coordinate_source_locator','old_coordinate_source_file']],on='source_record_id_old',how='left')
 pairs['old_accepted_point_exists']=pairs.old_accepted_point_latitude.map(lambda x:pd.notna(x))&pairs.old_accepted_point_longitude.map(lambda x:pd.notna(x))
 pairs['old_to_current_accepted_point_distance_km']=pairs.apply(lambda r:km(r.old_accepted_point_latitude,r.old_accepted_point_longitude,r.latitude,r.longitude) if r.old_accepted_point_exists and valid_point(r.old_accepted_point_latitude,r.old_accepted_point_longitude) and valid_point(r.latitude,r.longitude) else None,axis=1)
 pairs['old_point_compatibility_status']=pairs.apply(lambda r:'no_old_accepted_point_unknown' if not r.old_accepted_point_exists else 'old_point_agrees_le_5km' if r.old_to_current_accepted_point_distance_km is not None and r.old_to_current_accepted_point_distance_km<=5 else 'old_point_conflicts_gt_5km_or_invalid',axis=1)
 pairs=pairs[pairs.old_point_compatibility_status.isin(['no_old_accepted_point_unknown','old_point_agrees_le_5km'])].copy()
 stats['after_existing_old_point_contradiction_check']=len(pairs)
 # Deduplicate both candidate endpoints against population scopes/events only
 # after source-key and native-code narrowing.
 endpoint_ids=set(pairs.source_record_id_old.astype(str))|set(pairs.source_record_id_current.astype(str))
 ev={}
 if endpoint_ids:
  tab=ds.dataset(EVID,format='parquet').to_table(columns=['source_record_id','source_evidence_json'],filter=ds.field('source_record_id').isin(endpoint_ids))
  ev={str(x['source_record_id']):json.loads(x['source_evidence_json']) for x in tab.to_pylist()}
 held=Counter();stage=[];point_candidates=[];identity_candidates=[]
 for r in pairs.to_dict('records'):
  a,b=str(r['source_record_id_old']),str(r['source_record_id_current']);why=[];hard=[]
  for eid in (a,b):
   e=ev.get(eid,{})
   if truth(e.get('is_federal_aggregate')) or truth(e.get('legacy_same_year_collision')) or e.get('legacy_verified_successor_settlement_id'):hard.append('aggregate_collision_or_verified_event:'+eid)
   if e.get('is_additive_settlement_record') is False:hard.append('source_evidence_nonadditive:'+eid)
   if truth(e.get('legacy_identity_conflict')):
    try:reasons=set(json.loads(e.get('legacy_identity_reasons') or '[]'))
    except Exception:reasons={'unparsed_identity_conflict'}
    reasons-={'administrative_conflict','ordinal_historical_identifier_hypothesis'}
    if reasons:hard.append('unresolved_nonadministrative_identity_conflict:'+eid+':'+','.join(sorted(reasons)))
  ia,ib=uf.idx.get(a),uf.idx.get(b)
  graph_status='vertex_missing'
  if ia is None or ib is None:why.append('selected_vertex_missing')
  else:
   ra,rb=uf.find(ia),uf.find(ib)
   if ra==rb:graph_status='already_connected_no_residual_year'
   elif uf.mask[ra]&uf.mask[rb]:graph_status='year_constrained_collision';why.append(graph_status)
   else:graph_status='distinct_year_safe_components'
  r['source_evidence_hold_reasons_json']=json.dumps(hard,ensure_ascii=False)
  r['accepted_identity_graph_status']=graph_status
  r['candidate_status']='held' if hard or graph_status in {'vertex_missing','year_constrained_collision'} else 'review_candidate'
  for reason in hard+([graph_status] if graph_status in {'vertex_missing','year_constrained_collision'} else []):held[reason]+=1
  if not hard and graph_status=='distinct_year_safe_components':identity_candidates.append(r)
  if not hard and graph_status=='already_connected_no_residual_year' and a not in point_ids:
   point_candidates.append(r)
  stage.append(r)
 stats['sourcekey_pairs_already_identity_connected']=sum(r['accepted_identity_graph_status']=='already_connected_no_residual_year' for r in stage)
 stats['residual_identity_edge_candidates']=len(identity_candidates)
 stats['missing_old_point_targets_eligible_for_explicit_current_point_continuity']=len(point_candidates)
 # Full accepted UF conditional simulation; order by largest old population.
 elig=identity_candidates
 elig.sort(key=lambda r:(-int(r['source_pop_int_old']),int(r['census_year_old']),str(r['source_record_id_old'])))
 edges=[];union=Counter()
 for r in elig:
  a,b=str(r['source_record_id_old']),str(r['source_record_id_current']);out=uf.union_ids(a,b);union[out]+=1
  r['conditional_union_result']=out
  if out=='merged':edges.append({'from_source_record_id':a,'from_year':int(r['census_year_old']),'to_source_record_id':b,'to_year':2021,'relation':'same_place','decision_rule':'whole_source_unique_native_point_absent_candidate_only','candidate_only':True,'identity_admitted':False})
  elif out!='merged':r['candidate_status']='held_conditional_union_'+out
 # Carry the current source's already accepted direct point across the existing
 # identity path only for old rows without an admitted point. This is an
 # explicit coordinate-continuity candidate, not a census-date measurement.
 pair_roots={uf.find(uf.idx[str(r['source_record_id_old'])]) for r in point_candidates}
 adjacency={}
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id);ia,ib=uf.idx.get(a),uf.idx.get(b)
  if ia is None or ib is None or uf.find(ia) not in pair_roots:continue
  edge={'decision_id':str(e.decision_id) if hasattr(e,'decision_id') else '', 'from_source_record_id':a,'from_year':int(e.from_year),'to_source_record_id':b,'to_year':int(e.to_year),'relation':str(e.relation)}
  adjacency.setdefault(a,[]).append((b,edge));adjacency.setdefault(b,[]).append((a,edge))
 def accepted_path(start,end):
  from collections import deque
  start,end=str(start),str(end);q=deque([start]);prev={start:None};via={}
  while q:
   node=q.popleft()
   if node==end:break
   for nxt,edge in adjacency.get(node,[]):
    if nxt not in prev:prev[nxt]=node;via[nxt]=edge;q.append(nxt)
  if end not in prev:return []
  out=[];node=end
  while prev[node] is not None:out.append(via[node]);node=prev[node]
  return list(reversed(out))
 point_uses=[]
 for r in point_candidates:
  oldid=str(r['source_record_id_old']);curid=str(r['source_record_id_current']);path=accepted_path(curid,oldid)
  if not path:
   held['accepted_identity_path_not_reconstructed']+=1;r['point_use_candidate_status']='held_path_not_reconstructed';continue
  origin={k:r.get(k+'_current',r.get(k)) for k in ['point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind','coordinate_source','coordinate_source_sha256','coordinate_source_locator','coordinate_source_file','coordinate_source_record_id','coordinate_provider','coordinate_provider_id','latitude','longitude']}
  r['accepted_identity_path_decision_ids_json']=json.dumps([e['decision_id'] for e in path],ensure_ascii=False)
  r['accepted_identity_path_edges_json']=json.dumps(path,ensure_ascii=False)
  r['point_use_candidate_status']='candidate_only_explicit_historical_continuity_pending_review'
  use={'target_source_record_id':oldid,'target_year':int(r['census_year_old']),'latitude':float(origin['latitude']),'longitude':float(origin['longitude']),
   'coordinate_source':'Accepted direct 2021 source point propagated through the already accepted same_place path under explicit ordinary continuity inference; not a census-date coordinate measurement.',
   'coordinate_source_record_id':origin['coordinate_source_record_id'],'coordinate_provider':origin['coordinate_provider'],'coordinate_provider_id':origin['coordinate_provider_id'],
   'point_origin_file':origin['point_origin_file'],'point_origin_sha256':origin['point_origin_sha256'],'point_origin_locator':origin['point_origin_locator'],'point_origin_kind':origin['point_origin_kind'],
   'coordinate_source_file':origin['coordinate_source_file'],'coordinate_source_sha256':origin['coordinate_source_sha256'],'coordinate_source_locator':origin['coordinate_source_locator'],
   'inference_modern_point_use_target_source_record_id':curid,'inference_identity_path_decision_ids_json':json.dumps([e['decision_id'] for e in path],ensure_ascii=False),
   'inference_identity_path_edges_json':json.dumps(path,ensure_ascii=False),'inference_identity_path_edge_count':len(path),'application_inference_kind':'ordinary_settlement_identity_point_continuity_candidate',
   'direct_historical_coordinate_measurement':False,'coordinate_measurement_date_unknown':True,'boundary_comparability_asserted':False,
   'coordinate_admission_status':'candidate_only_no_admission','identity_admitted':False,'point_admitted':False,'independent_rule_review_required':True,
   'candidate_source_record_id':oldid,'candidate_source_year':int(r['census_year_old']),'candidate_source_file':r['source_file_old'],'candidate_source_sheet':r['source_sheet_old'],'candidate_source_row':r['source_row_old'],
   'candidate_source_native_id_opaque':r['source_native_id_old'],'candidate_source_okato_raw':r['okato_old'],'candidate_source_oktmo_raw':r['oktmo_old'],
   'candidate_current_target_source_record_id':curid,'candidate_current_unique_native_codes_json':r['current_unique_native_codes_json'],'candidate_district_context_status':r['district_context_status'],'candidate_old_native_point_lookup_absent':True,
   'candidate_old_accepted_point_status':r['old_point_compatibility_status']}
  point_uses.append(use)
 new_point_ids=point_ids|{str(x['target_source_record_id']) for x in point_uses}
 after=metrics(s,uf,new_point_ids)
 delta={y:{ax:{m:after[y][ax][m]-baseline[y][ax][m] for m in ('rows','population')} for ax in ('full_chain','joint_point_full_chain')} for y in baseline}
 # Draw a fixed stratified raw-source review sample: 20 highest-population
 # candidates plus 40 reproducible PPS draws spread by year, district state,
 # and existing-old-point state. The sample is still candidate-only.
 for r in stage:
  r['review_stratum']=f"{r['census_year_old']}|{r['district_context_status']}|{r['old_point_compatibility_status']}"
 final=[r for r in point_candidates if r.get('point_use_candidate_status')=='candidate_only_explicit_historical_continuity_pending_review']
 final.sort(key=lambda r:(-int(r['source_pop_int_old']),str(r['source_record_id_old'])))
 chosen=[]; chosen_ids=set()
 for r in final[:20]:chosen.append(r);chosen_ids.add(r['source_record_id_old'])
 remaining=[r for r in final if r['source_record_id_old'] not in chosen_ids]
 strata={}
 for r in remaining:strata.setdefault(r['review_stratum'],[]).append(r)
 rng=random.Random(20261004);alloc={k:0 for k in strata}
 keys_sorted=sorted(strata)
 for i in range(min(40,len(remaining))):alloc[keys_sorted[i%len(keys_sorted)]]+=1
 for k,rows in strata.items():
  take=min(alloc[k],len(rows))
  # Fixed seed and source population weights; avoid replacement.
  weights=[max(1,int(x['source_pop_int_old'])) for x in rows]
  pool=rows[:]
  for _ in range(take):
   total=sum(max(1,int(x['source_pop_int_old'])) for x in pool);z=rng.randrange(total);acc=0;ix=0
   for ix,x in enumerate(pool):
    acc+=max(1,int(x['source_pop_int_old']))
    if z<acc:break
   q=pool.pop(ix);chosen.append(q);chosen_ids.add(q['source_record_id_old'])
 sample=[]
 for r in chosen:
  item=dict(r);item['sample_seed']=20261004;item['sample_design']='top20_old_population_plus_stratified_PPS40';item['candidate_only_no_admission']=True;sample.append(item)
 # Output lean candidate ledgers and source-literal audit sample, including
 # selected-source row locators/hashes, current point provenance, and the
 # absent-vs-present historical native-point lookup assessment.
 write_csv(OUT/'candidate_edges.csv',edges)
 write_csv(OUT/'candidate_endpoint_ledger.csv',stage)
 write_csv(OUT/'candidate_point_uses.csv',point_uses)
 write_csv(OUT/'fixed_stratified_raw_review_sample60.csv',sample)
 summary={'status':'native_point_absent_whole_source_key_candidate_only_no_admissions','baseline_id':cfg.get('diagnostic_baseline_id','current_config_pinned'),'baseline_graph_sha256':pins[str(G)]['sha256'],'baseline_point_uses_sha256':pins[str(P)]['sha256'],'baseline_coverage_reproduced':True,'baseline_checks':checks,'candidate_rule':'Old and current census source rows are actual additive physical settlement observations. The exact normalized physical type, locality name and canonical province key each occur once in the entire selected source-year key space. Current target has an already accepted direct proper point and at least one literal 11-digit OKTMO/OKATO value uniquely identifies a 2021 selected object. When both old/current districts are explicit their documented descriptor-stripped core must match; both blank remains unknown and is allowed only under whole-source key uniqueness. Existing accepted old point, if any, must be within 5 km of the accepted current point as a contradiction check only. Old native classifier/GeoKLADR point lookup is absent for this candidate cohort and is not treated as a negative identity fact. Source aggregates/events/collisions/nonadditive rows/unresolved nonadministrative conflicts and year-constrained UF collisions are held. No P1082 or population-value equality is used. For already-connected identity endpoints missing a coordinate, the current direct accepted point is staged as an explicit continuity candidate with the actual accepted decision-ID path.','stage_counts':dict(stats),'hold_reasons':dict(held),'nonredundant_conditional_identity_edges':len(edges),'conditional_union_outcomes':dict(union),'candidate_point_use_count':len(point_uses),'conditional_full_graph_metric_delta':delta,'fixed_sample_count':len(sample),'fixed_sample_seed':20261004,'fixed_sample_design':'top20 old-source population plus stratified PPS40 by old year, county-context state and prior old-point state; raw source file/sheet/row/locator/hash and native codes retained.','inputs':pins,'interpretation':['No identity or point admission was made.','Population observations are not changed or used as match evidence.','A blank/different district is not asserted to be a legal rename; blank is recorded as unknown and a different core remains held.','The old point check can reject a contradiction but is not independent positive proof.','The candidate rule does not use old ordinal IDs, name-only matching, P1082, or proximity alone.']}
 summary['outputs']={x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(OUT.iterdir()) if x.is_file() and x.name not in {'summary.json','receipt.json'}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 rec={'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{x.name:sha(x) for x in sorted(OUT.iterdir()) if x.is_file() and x.name!='receipt.json'},'script':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))}
 (OUT/'receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs'}},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
