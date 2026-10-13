#!/usr/bin/env python3
"""Systematic candidate-only audit of typed native historical point corridors.

Uses the full old-year historical named-point join, actual 2009 classifier and
2011 GeoKLADR records, exact same-type whole-region uniqueness, available raw
county context, and a direct accepted current point. P1082 is not consulted.
No row is admitted by this stage.
"""
from __future__ import annotations
import csv, gc, hashlib, json, math, random, re, sys, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq

W=Path('/workspace'); F=W/'settlements-delivery/continuation-consolidated-20261003'
C=W/'settlements-work/continuation_20261004'; R4=C/'R4'
OUT=R4/'typed_native_physical_corridor_v2_rerunfinal'
SEL=F/'selected_observations.parquet'; EVID=F/'source_evidence.parquet'; MANIFEST=F/'input_manifest.parquet'
CONFIG_SRC=W/'russian-settlements-research/config/mass_joint_20261004.json'
HIST=W/'settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet'
OBJECTS=W/'settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet'
CLASS=W/'settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet'
SQL=W/'settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql'
DBF=W/'settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf'
BLOCKED=W/'settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json'
APPLICATION_RECEIPT=C/'accepted_mass_rule_corrections_origin_corrected/receipt.json'
YEARS=(2002,2010,2021)
PHYSICAL={'город','пгт','поселок','деревня','село','хутор','станица','аул','кишлак','слобода','арбан','выселок','починок','местечко'}
HISTORICAL_POINT_KINDS={'geokladr_2011_raw_dbf_coordinate','raw_named_typed_geo2011_object','raw_named_typed_2011_rural_geo_object'}

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 return h.hexdigest()

def norm(v):
 if v is None or pd.isna(v): return ''
 return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').replace('\xa0',' ').split())

def canonical_type(v):
 s=norm(v).replace('.','').strip()
 return {'поселок сельского типа':'поселок','посёлок сельского типа':'поселок',
         'поселок городского типа':'пгт','посёлок городского типа':'пгт',
         'пгт':'пгт','пос':'поселок','п':'поселок','дер':'деревня','д':'деревня',
         'с':'село','х':'хутор','ст-ца':'станица','стца':'станица','станица':'станица',
         'г':'город','гор':'город','город':'город','аал':'аул','сл':'слобода',
         'разъезд':'','станция':''}.get(s,s)

def admin_key(v):
 s=norm(v)
 s=re.sub(r'^(городской округ|муниципальный округ|муниципальный район|городской район|район)\s+','',s)
 s=re.sub(r'\s+(муниципальный район|муниципальный округ|городской округ|район|округ)$','',s)
 s=re.sub(r'\s+',' ',s).strip()
 return s

def km(a,b,c,d):
 p1,p2=math.radians(float(a)),math.radians(float(c)); dp=p2-p1; dl=math.radians(float(d)-float(b))
 z=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.atan2(math.sqrt(z),math.sqrt(max(0,1-z)))

def truth(v): return v is True or str(v).casefold() in {'true','1','t','yes'}

def write_csv(path,rows):
 if not rows: Path(path).write_text('',encoding='utf-8'); return
 fields=[];seen=set()
 for r in rows:
  for k in r:
   if k not in seen: seen.add(k); fields.append(k)
 with Path(path).open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

class YearUF:
 def __init__(self,ids,year_values):
  self.idx={sid:i for i,sid in enumerate(ids)}
  self.parent=np.arange(len(ids),dtype=np.int32)
  bits={2002:1,2010:2,2021:4}
  self.mask=np.fromiter((bits[int(y)] for y in year_values),dtype=np.uint8,count=len(ids))
 def find(self,x):
  p=self.parent
  while p[x]!=x:
   p[x]=p[p[x]];x=p[x]
  return int(x)
 def union_ids(self,a,b):
  ia=self.idx.get(str(a));ib=self.idx.get(str(b))
  if ia is None or ib is None:return 'missing_vertex'
  x,y=self.find(ia),self.find(ib)
  if x==y:return 'already_connected'
  if self.mask[x]&self.mask[y]:return 'year_constrained_collision'
  if y<x:x,y=y,x
  self.parent[y]=x;self.mask[x]|=self.mask[y]
  return 'merged'
 def bits_by_row(self):
  return np.fromiter((int(self.mask[self.find(i)]) for i in range(len(self.parent))),dtype=np.uint8,count=len(self.parent))

def direct_dbf_witnesses(path,candidates):
 """Reopen exact DBF rows; candidates are already reduced to native-lineage cases."""
 from research_rebuild.mass_linkage.verify_geokladr_snapshot import parse_dbf_header
 out={}
 if not candidates:return out
 with Path(path).open('rb') as f:
  prefix=f.read(32); hdrlen=int.from_bytes(prefix[8:10],'little'); f.seek(0)
  n,hl,rl,fields=parse_dbf_header(f.read(hdrlen)); byname={x['name']:x for x in fields}
  if n!=151875 or hl!=705 or rl!=395: raise ValueError('2011 DBF snapshot layout changed')
  for row in candidates:
   rec=int(row['record_number_1based']);off=int(row['record_byte_offset_0based'])
   if rec<1 or rec>n or off!=hl+(rec-1)*rl: out[str(row['source_record_id'])]={'ok':False,'reason':'raw_dbf_locator_mismatch'};continue
   f.seek(off);raw=f.read(rl)
   if len(raw)!=rl:out[str(row['source_record_id'])]={'ok':False,'reason':'raw_dbf_short_read'};continue
   def field(name):
    spec=byname[name];a=spec['offset'];return raw[a:a+spec['width']].decode('cp1251').strip()
   code=field('TER')+field('KOD1')+field('KOD2')+field('KOD3')
   lat,lon=field('LAT'),field('LONG')
   try: latf,lonf=float(lat),float(lon)
   except Exception:latf=lonf=float('nan')
   checks={'record_1based':rec,'byte_offset_0based':off,'deleted_marker_raw':raw[:1].decode('ascii','replace'),
    'code_2011_raw':code,'name_2011_raw':field('NAME1'),'type_2011_raw':field('SCOKATO'),
    'latitude_raw':lat,'longitude_raw':lon,'data_update_raw':field('DATA_UPD')}
   wantcode=str(row['historical_okato_2011_raw']);
   ok=(checks['deleted_marker_raw']==' ' and code==wantcode and norm(checks['name_2011_raw'])==norm(row['name_raw_2011'])
       and canonical_type(checks['type_2011_raw'])==canonical_type(row['type_key_2011'])
       and math.isfinite(latf) and math.isfinite(lonf) and abs(latf-float(row['latitude_from_lat']))<1e-6
       and abs(lonf-float(row['longitude_from_long']))<1e-6)
   checks['ok']=bool(ok);checks['reason']='raw_dbf_literal_matches_candidate' if ok else 'raw_dbf_code_name_type_or_coordinate_mismatch'
   out[str(row['source_record_id'])]=checks
 return out

def metrics(selected,uf,point_ids):
 bits=uf.bits_by_row(); y=selected.census_year.to_numpy(dtype=np.int16); pop=pd.to_numeric(selected.population,errors='coerce').fillna(0).to_numpy(dtype=np.int64)
 ids=selected.source_record_id.astype(str).to_numpy();haspoint=np.fromiter((sid in point_ids for sid in ids),dtype=bool,count=len(ids))
 full=bits==7; joint=full&haspoint; out={}
 for yr in YEARS:
  m=y==yr;out[str(yr)]={'full_chain':{'rows':int((m&full).sum()),'population':int(pop[m&full].sum())},
    'joint_point_full_chain':{'rows':int((m&joint).sum()),'population':int(pop[m&joint].sum())}}
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=False)
 # Fail on missing projected fields before reading any large parquet columns.
 required_columns={
  SEL:['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','type_norm','region_raw','district_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','okato','oktmo'],
  HIST:['source_record_id','census_year','historical_okato_2009_raw','historical_okato_2011_raw','historical_name_exact','historical_type_exact','historical_code_structure_compatible','possible_unlocated_historical_competitor','historical_point_modern_region','name_key','type_key_2009','type_key_2011','name_raw_2009','name_raw_2011','settlement_type_raw','latitude_from_lat','longitude_from_long','record_number_1based','record_byte_offset_0based'],
  OBJECTS:['historical_okato_2009_raw','historical_okato_2011_raw','name_key','type_key_2011','historical_point_modern_region','is_deleted','is_settlement_raw','historical_name_exact','historical_type_exact','historical_code_structure_compatible','name_raw_2011','settlement_type_raw','latitude_from_lat','longitude_from_long','record_number_1based','record_byte_offset_0based','source_sha256_2009','source_sha256_2011'],
  CLASS:['historical_okato','name_raw','name','status','name_full','is_settlement_raw','source_line_1based','source_sha256'],
 }
 for path,needed in required_columns.items():
  missing=set(needed)-set(pq.ParquetFile(path).schema.names)
  if missing:raise SystemExit(f'input schema guard failed for {path}: {sorted(missing)}')
 from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_PROJECTION_STATUSES,ACCEPTED_COORDINATE_STATUSES
 from research_rebuild.mass_linkage.stage_legacy_temporal_20261004 import region_key
 config=json.loads(CONFIG_SRC.read_text())
 GRAPH=Path(config['working_identity_graph']);POINTS=Path(config['working_point_uses']);COVERAGE=Path(config['working_coverage'])
 input_paths=[SEL,EVID,MANIFEST,GRAPH,POINTS,COVERAGE,APPLICATION_RECEIPT,HIST,OBJECTS,CLASS,SQL,DBF,BLOCKED,CONFIG_SRC]
 pins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in input_paths}
 config['diagnostic_baseline_id']='corrected_fourth_current'
 config['diagnostic_source_graph_sha256']=pins[str(GRAPH)]['sha256'];config['diagnostic_source_points_sha256']=pins[str(POINTS)]['sha256']
 local_config=OUT/'diagnostic_input_config.json';local_config.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n')
 pins[str(local_config)]={'sha256':sha(local_config),'bytes':local_config.stat().st_size}
 if pins[str(GRAPH)]['sha256']!=config['working_identity_graph_sha256'] or pins[str(POINTS)]['sha256']!=config['working_point_uses_sha256']:
  raise SystemExit('current corrected-fourth ledger pins differ from config')
 app=json.loads(APPLICATION_RECEIPT.read_text())
 if app.get('outputs',{}).get('accepted_identity_edges.parquet')!=pins[str(GRAPH)]['sha256'] or app.get('outputs',{}).get('accepted_point_uses.parquet')!=pins[str(POINTS)]['sha256']:
  raise SystemExit('application receipt does not pin current graph/points')
 coverage=json.loads(COVERAGE.read_text())
 cov_out=app.get('outputs',{}).get('coverage.json')
 if cov_out and cov_out!=pins[str(COVERAGE)]['sha256']:raise SystemExit('coverage receipt hash mismatch')

 # Frozen selected population rows, reduced to fields needed for identities and provenance.
 scol=['source_record_id','census_year','source_file','source_sheet','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','name_norm','type_norm','region_raw','region_norm','district_raw','population','population_scope','is_additive_settlement_record','entity_grain_status','okato','oktmo']
 s=pd.read_parquet(SEL,columns=scol);s.source_record_id=s.source_record_id.astype(str)
 if s.source_record_id.duplicated().any():raise ValueError('selected layer has duplicate source IDs')
 s['src_name_key']=s.settlement_name.map(norm);s['src_type_key']=s.type_norm.map(canonical_type);s['src_region_key']=s.region_raw.map(region_key)
 s['src_sig']=list(zip(s['src_name_key'],s['src_type_key'],s['src_region_key']))
 validphysical=s['src_type_key'].isin(PHYSICAL)
 old=s[s.census_year.isin([2002,2010])&validphysical].copy();s21=s[s.census_year.eq(2021)&validphysical].copy()
 old_uni=old.groupby(['census_year','src_sig'],dropna=False).source_record_id.nunique().to_dict()
 cur_uni=s21.groupby('src_sig',dropna=False).source_record_id.nunique().to_dict()
 years=dict(zip(s.source_record_id,s.census_year.astype(int)))
 manifest=pd.read_parquet(MANIFEST,columns=['path','sha256']);manifest_sha=dict(zip(manifest.path.astype(str),manifest.sha256.astype(str)))

 # Full old census population of the historical joined point register, not a point-missing-only residual.
 hcols=['source_record_id','census_year','historical_okato_2009_raw','historical_okato_2011_raw','code_join_basis','historical_name_exact','historical_type_exact','historical_code_structure_compatible','historical_key_region_name_type_count','possible_unlocated_historical_competitor','historical_point_modern_region','name_key','type_key_2009','type_key_2011','name_raw_2009','name_raw_2011','settlement_type_raw','latitude_from_lat','longitude_from_long','record_number_1based','record_byte_offset_0based','source_line_1based','source_sha256_2009','source_sha256_2011','is_deleted','deleted_marker_raw','is_settlement_raw','source_region_name_type_count','is_additive_settlement_record','population_scope','population','source_file']
 h=pd.read_parquet(HIST,columns=hcols);h=h[h.census_year.isin([2002,2010])].copy();h.source_record_id=h.source_record_id.astype(str)
 old=old.merge(h,on=['source_record_id','census_year'],how='inner',validate='one_to_one',suffixes=('','_h'))
 # Keep only literal typed source to classifier candidates for the detailed audit; every hold remains in the register.
 old=old[old.historical_name_exact.eq(True)&old.historical_type_exact.eq(True)].copy()
 old['historical_okato_2009_raw']=old.historical_okato_2009_raw.fillna('').astype(str)
 old['historical_okato_2011_raw']=old.historical_okato_2011_raw.fillna('').astype(str)

 # Current proper direct points: canonical accepted status, self-sourced target,
 # physical current source, and not a reused historical GeoKLADR point.
 pcols=['target_source_record_id','target_year','latitude','longitude','coordinate_admission_status','coordinate_source_record_id','point_origin_kind','point_origin_file','point_origin_sha256','point_origin_locator','admission_rule','coordinate_application_family','coordinate_source_file','coordinate_source_sha256','coordinate_source_locator']
 p=pd.read_parquet(POINTS,columns=pcols);p=p[p.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)].copy();p.target_source_record_id=p.target_source_record_id.astype(str)
 if p.target_source_record_id.duplicated().any():raise ValueError('accepted point ledger has duplicate target IDs')
 point_ids=set(p.target_source_record_id)
 histkinds=HISTORICAL_POINT_KINDS
 direct=p[p.target_year.eq(2021)&(p.coordinate_source_record_id.astype(str)==p.target_source_record_id)&~p.point_origin_kind.isin(histkinds)].copy()
 direct=direct.merge(s21[['source_record_id','src_name_key','src_type_key','src_region_key','src_sig','population_scope','is_additive_settlement_record','entity_grain_status']],left_on='target_source_record_id',right_on='source_record_id',how='inner',validate='one_to_one')
 direct=direct[direct.src_type_key.isin(PHYSICAL)&direct.is_additive_settlement_record.eq(True)]
 direct=direct[pd.to_numeric(direct.latitude,errors='coerce').between(-90,90)&pd.to_numeric(direct.longitude,errors='coerce').between(-180,180)]
 direct_by_sig={k:[r for r in fr.itertuples(index=False)] for k,fr in direct.groupby('src_sig',sort=False)}

 # Load raw historical object universe and 2009 classifier once, then compact to exact typed signatures/codes.
 ocols=['historical_okato_2009_raw','historical_okato_2011_raw','name_key','type_key_2009','type_key_2011','historical_point_modern_region','is_deleted','is_settlement_raw','historical_name_exact','historical_type_exact','historical_code_structure_compatible','name_raw_2011','settlement_type_raw','latitude_from_lat','longitude_from_long','record_number_1based','record_byte_offset_0based','source_sha256_2009','source_sha256_2011']
 o=pd.read_parquet(OBJECTS,columns=ocols);o=o[o.is_deleted.eq(False)&o.is_settlement_raw.astype(str).str.lower().eq('t')].copy()
 o['hist_name_key']=o.name_key.map(norm);o['hist_type_key']=o.type_key_2011.map(canonical_type);o['hist_region_key']=o.historical_point_modern_region.map(region_key);o['hist_sig']=list(zip(o['hist_name_key'],o['hist_type_key'],o['hist_region_key']))
 o=o[o['hist_type_key'].isin(PHYSICAL)].copy()
 objects_by_sig={k:fr for k,fr in o.groupby('hist_sig',sort=False)}
 pairmap=defaultdict(set); reversemap=defaultdict(set); region_prefix=defaultdict(set)
 for r in o.itertuples(index=False):
  c9=str(r.historical_okato_2009_raw or '');c11=str(r.historical_okato_2011_raw or '')
  if c9 and c11:pairmap[c9].add(c11);reversemap[c11].add(c9)
  if c9[:2] and r.hist_region_key:region_prefix[c9[:2]].add(r.hist_region_key)
 del o;gc.collect()

 cls=pd.read_parquet(CLASS,columns=['historical_okato','name_raw','name','status','name_full','is_settlement_raw','source_line_1based','source_sha256'])
 cls['historical_okato']=cls.historical_okato.astype(str)
 class_counts=cls.historical_okato.value_counts();class_by_code={str(r.historical_okato):r for r in cls.itertuples(index=False) if class_counts[str(r.historical_okato)]==1}
 hist_sig_codes=defaultdict(set)
 for r in cls.itertuples(index=False):
  code=str(r.historical_okato or ''); status=canonical_type(r.status); name=norm(r.name)
  if not code or str(r.is_settlement_raw).lower()!='t' or status not in PHYSICAL or not name:continue
  regions=region_prefix.get(code[:2],set())
  if len(regions)==1: hist_sig_codes[(name,status,next(iter(regions)))].add(code)
 def parent_for(code):
  if len(code)==11:return class_by_code.get(code[:5]+'000')
  if len(code)==8:return class_by_code.get(code[:2]+'000000')
  return None
 def parent_name(code):
  q=parent_for(code)
  if q is None or str(q.is_settlement_raw).lower()!='f':return ''
  return norm(q.name_raw)

 # First pass through complete exact-typed cohort. Source uniqueness and current
 # direct point availability are independent of population and Wikidata.
 staged=[]; prelim=[]; holdcounts=Counter(); mass=Counter(); yearcohort=Counter()
 for r in old.itertuples(index=False):
  sid=str(r.source_record_id);yr=int(r.census_year);sig=r.src_sig;pop=pd.to_numeric(pd.Series([r.population]),errors='coerce').iloc[0];pop=int(pop) if pd.notna(pop) else None
  code9=str(r.historical_okato_2009_raw);code11=str(r.historical_okato_2011_raw);reasons=[]
  yearcohort[(yr,'exact_typed_historical_join')]+=1
  if pop is not None:mass[(yr,'exact_typed_historical_join')]+=pop
  if not r.is_additive_settlement_record:reasons.append('old_selected_source_nonadditive')
  if str(r.population_scope).casefold() in {'federal_city_region','territorial_aggregate','regional_aggregate','federal_territory'}:reasons.append('old_source_aggregate_scope')
  grain=norm(r.entity_grain_status)
  if any(t in grain for t in ('aggregate','federal_city','parent','derived_sum')):reasons.append('old_source_nonphysical_grain')
  if old_uni.get((yr,sig),0)!=1:reasons.append('old_exact_typed_name_region_not_unique_in_census')
  if not code9 or not code11 or not code9.isdigit() or not code11.isdigit():reasons.append('historical_native_code_pair_missing_or_nonliteral')
  if not bool(r.historical_code_structure_compatible):reasons.append('historical_code_structure_not_compatible')
  c9=class_by_code.get(code9);objrows=objects_by_sig.get(sig)
  class_ok=bool(c9 and str(c9.is_settlement_raw).lower()=='t' and canonical_type(c9.status)==r.src_type_key and norm(c9.name)==r.src_name_key)
  if not class_ok:reasons.append('actual_2009_classifier_row_not_exact_typed_physical_place')
  pair_ok=bool(code11 in pairmap.get(code9,set()) and len(pairmap.get(code9,set()))==1 and len(reversemap.get(code11,set()))==1)
  if not pair_ok:reasons.append('2009_to_2011_native_code_pair_not_one_to_one')
  histrow=None
  if objrows is not None:
   matches=objrows[(objrows.historical_okato_2009_raw.astype(str)==code9)&(objrows.historical_okato_2011_raw.astype(str)==code11)]
   if len(matches)==1:histrow=matches.iloc[0]
  if histrow is None:reasons.append('actual_named_typed_2011_object_pair_missing_or_nonunique')
  elif not bool(histrow.historical_name_exact) or not bool(histrow.historical_type_exact) or not bool(histrow.historical_code_structure_compatible):reasons.append('actual_2009_2011_object_name_type_or_code_structure_mismatch')
  if sig[2]!=region_key(r.historical_point_modern_region):reasons.append('historical_object_region_disagrees_with_published_source')
  source_count=old_uni.get((yr,sig),0);target_count=cur_uni.get(sig,0)
  if target_count!=1:reasons.append('current_exact_typed_name_region_not_unique_in_2021')
  targets=direct_by_sig.get(sig,[])
  if not targets:reasons.append('no_accepted_direct_current_proper_point_for_signature')
  # Old raw administrative context is compared with actual 2009 classifier parent
  # only where the published source field supplies it.
  district=norm(r.district_raw);district_key=admin_key(district);pname=parent_name(code9)
  explicit_district=bool(district_key)
  parent_match=bool(explicit_district and pname and admin_key(pname)==district_key)
  if len(code9)==11 and explicit_district and not parent_match:reasons.append('explicit_old_source_district_differs_from_actual_2009_parent')
  hist_group=hist_sig_codes.get(sig,set());hist_signature_count=len(hist_group)
  unlocated=truth(r.possible_unlocated_historical_competitor)
  if hist_signature_count>1 or unlocated:
   if not parent_match:reasons.append('historical_same_typed_name_region_requires_explicit_county_disambiguation')
   else:
    hits=[cc for cc in hist_group if admin_key(parent_name(cc))==district_key]
    if len(hits)!=1 or code9 not in hits:reasons.append('explicit_county_does_not_uniquely_select_historical_physical_object')
  histlat=histlon=None;hrec=None
  if histrow is not None:
   histlat=float(histrow.latitude_from_lat) if pd.notna(histrow.latitude_from_lat) else None
   histlon=float(histrow.longitude_from_long) if pd.notna(histrow.longitude_from_long) else None
   hrec={'source_record_id':sid,'historical_okato_2009_raw':code9,'historical_okato_2011_raw':code11,
    'name_raw_2011':histrow.name_raw_2011,'type_raw_2011':histrow.settlement_type_raw,
    'latitude_from_lat':histlat,'longitude_from_long':histlon,'record_number_1based':int(histrow.record_number_1based),
    'record_byte_offset_0based':int(histrow.record_byte_offset_0based),'type_key_2011':histrow.type_key_2011}
   if histlat is None or histlon is None:reasons.append('actual_named_2011_object_has_no_physical_point')
  distances=[]
  if histlat is not None and histlon is not None:
   for q in targets:
    d=km(histlat,histlon,float(q.latitude),float(q.longitude));distances.append((d,q))
   if not distances or min(x[0] for x in distances)>5:reasons.append('current_direct_point_more_than_5km_from_native_historic_point')
   elif any(d>5 for d,_ in distances):reasons.append('accepted_direct_current_point_alternatives_not_all_within_5km')
  best=min(distances,key=lambda x:(x[0],str(x[1].target_source_record_id))) if distances else None
  rec={'source_record_id':sid,'year':yr,'population':pop,'source_file':str(r.source_file),'source_sheet':str(r.source_sheet),
   'source_row_1based':int(r.source_row) if pd.notna(r.source_row) else None,'source_name_raw':r.source_name_raw,
   'source_name_normalized':r.src_name_key,'source_type_raw':r.settlement_type,'source_type_canonical':r.src_type_key,
   'source_region_raw':r.region_raw,'source_region_key':r.src_region_key,'source_district_raw':r.district_raw,
   'source_native_id_opaque_not_code':r.source_native_id,'source_OKATO_raw_not_used_as_publisher_code':r.okato,
   'source_OKTMO_raw_not_used_as_identity':r.oktmo,'old_source_signature_unique':source_count==1,
   'current_signature_unique_2021':target_count==1,'historical_2009_code_candidate':code9,'historical_2011_code_candidate':code11,
   'historical_code_join_basis':r.code_join_basis,'actual_2009_classifier_name_raw':str(c9.name_raw) if c9 else None,
   'actual_2009_classifier_type_raw':str(c9.status) if c9 else None,'actual_2009_classifier_is_settlement':str(c9.is_settlement_raw) if c9 else None,
   'actual_2009_classifier_line_1based':int(c9.source_line_1based) if c9 else None,
   'actual_2009_classifier_sha256':str(c9.source_sha256) if c9 else None,'actual_2009_parent_code':code9[:5]+'000' if len(code9)==11 else (code9[:2]+'000000' if len(code9)==8 else None),
   'actual_2009_parent_name_raw':str(parent_for(code9).name_raw) if parent_for(code9) else None,
   'old_source_district_context_status':'explicit_source_district_matches_actual_2009_parent' if parent_match else ('source_district_unknown' if not explicit_district else 'explicit_source_district_mismatch'),
   'historical_same_typed_name_region_code_count_in_actual_classifier':hist_signature_count,
   'historical_unlocated_same_signature_competitor_flag':unlocated,
   'historical_object_2011_raw_record_json':json.dumps(hrec,ensure_ascii=False) if hrec else None,
   'historical_classifier_file':str(SQL),'historical_classifier_file_sha256':pins[str(SQL)]['sha256'],
   'historical_dbf_file':str(DBF),'historical_dbf_file_sha256':pins[str(DBF)]['sha256'],
   'current_direct_source_record_id':str(best[1].target_source_record_id) if best else None,
   'current_point_origin_kind':str(best[1].point_origin_kind) if best else None,'current_point_origin_file':str(best[1].point_origin_file) if best else None,
   'current_point_origin_sha256':str(best[1].point_origin_sha256) if best else None,'current_point_origin_locator':str(best[1].point_origin_locator) if best else None,
   'current_latitude':float(best[1].latitude) if best else None,'current_longitude':float(best[1].longitude) if best else None,
   'native_historic_to_current_direct_point_min_distance_km':float(best[0]) if best else None,
   'native_historic_to_current_direct_point_all_distances_json':json.dumps([{'target_source_record_id':str(q.target_source_record_id),'distance_km':float(d),'point_origin_kind':q.point_origin_kind,'origin_file':q.point_origin_file,'origin_sha256':q.point_origin_sha256,'origin_locator':q.point_origin_locator} for d,q in distances],ensure_ascii=False),
   'selected_source_file_manifest_sha256':manifest_sha.get(str(r.source_file)),'candidate_status':'preliminary' if not reasons else 'held',
   'gate_failures_json':json.dumps(reasons,ensure_ascii=False),'rule_claim':'exact same typed source name/region uniqueness + actual 2009/2011 typed physical code lineage + applicable old district anchor + accepted 2021 proper point within 5 km; no P1082 used',
   'identity_admitted':False,'point_admitted':False,'native_publisher_code_asserted':False,'population_boundary_comparability_asserted':False}
  staged.append(rec)
  if not reasons:prelim.append((rec,r,hrec))
 del h;gc.collect()
 # Keep a recoverable checkpoint before expensive raw-row, graph, and metric gates.
 write_csv(OUT/'_scratch_candidate_register.csv',staged)

 # Reopen live DBF bytes for the preliminary native physical candidates.
 dbf_rows=direct_dbf_witnesses(DBF,[q[2] for q in prelim if q[2]])
 evidence_ids={q[0]['source_record_id'] for q in prelim}
 evmap={}
 if evidence_ids:
  evds=ds.dataset(EVID,format='parquet')
  evtable=evds.to_table(columns=['source_record_id','source_evidence_json'],filter=ds.field('source_record_id').isin(list(evidence_ids)))
  evmap={str(z['source_record_id']):json.loads(z['source_evidence_json']) for z in evtable.to_pylist()}
 blocked=set(json.loads(BLOCKED.read_text()).get('blocked_target_source_record_ids',[]))
 eligible=[]; hard_event_count=Counter()
 for rec,r,hrec in prelim:
  sid=rec['source_record_id'];gates=[];db=dbf_rows.get(sid,{})
  if not db.get('ok'):gates.append(db.get('reason','raw_dbf_record_not_reopened'))
  ev=evmap.get(sid,{})
  if sid in blocked:gates.append('blocked_hard_point_reuse_target')
  if truth(ev.get('is_federal_aggregate')) or truth(ev.get('legacy_same_year_collision')) or ev.get('legacy_verified_successor_settlement_id'):
   gates.append('source_evidence_aggregate_collision_or_verified_event')
  if ev.get('is_additive_settlement_record') is False:gates.append('source_evidence_nonadditive')
  if truth(ev.get('legacy_identity_conflict')):
   try:cf=set(json.loads(ev.get('legacy_identity_reasons') or '[]'))
   except Exception:cf={'unparsed_conflict'}
   cf-= {'administrative_conflict','ordinal_historical_identifier_hypothesis'}
   if cf:gates.append('unresolved_nonadministrative_identity_conflict:'+','.join(sorted(cf)))
  rec['source_evidence_legacy_identity_reasons_json']=ev.get('legacy_identity_reasons')
  rec['source_evidence_verified_successor_id']=ev.get('legacy_verified_successor_settlement_id')
  rec['source_evidence_same_year_collision']=truth(ev.get('legacy_same_year_collision'))
  rec['raw_live_2011_dbf_witness_json']=json.dumps(db,ensure_ascii=False)
  rec['candidate_status']='candidate_for_independent_rule_review' if not gates else 'held'
  rec['gate_failures_json']=json.dumps(gates,ensure_ascii=False)
  if gates:
   for g in gates:hard_event_count[g]+=1
  else:eligible.append(rec)

 write_csv(OUT/'_scratch_enriched_candidate_register.csv',staged)

 # Stage unique same_place edges and point-only retrospective uses. Point route
 # and temporal identity are separate candidate claims and neither is admitted.
 g=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','from_year','to_year','relation','decision_status','selection_projection_status'])
 if g.decision_status.isna().any() or not set(g.decision_status.astype(str)).issubset(ACCEPTED_EDGE_STATUSES):raise ValueError('noncanonical accepted graph statuses')
 if g.selection_projection_status.isna().any() or not set(g.selection_projection_status.astype(str)).issubset(ACCEPTED_PROJECTION_STATUSES):raise ValueError('noncanonical accepted projection statuses')
 if not g.relation.eq('same_place').all():raise ValueError('current graph contains non-same_place relation')
 uf=YearUF(s.source_record_id.astype(str).tolist(),s.census_year.astype(int).tolist())
 for e in g.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in uf.idx or b not in uf.idx:raise ValueError('accepted graph endpoint missing in selected layer')
  if int(years[a])!=int(e.from_year) or int(years[b])!=int(e.to_year):raise ValueError('accepted graph endpoint-year mismatch')
  outcome=uf.union_ids(a,b)
  if outcome=='year_constrained_collision':raise ValueError('current accepted graph has a same-year component collision')
 baseline=metrics(s,uf,point_ids)
 cov_metrics={str(x['year']):x for x in coverage['census_metrics']}
 baseline_checks={}
 for yr in YEARS:
  cov=cov_metrics[str(yr)]['axes'];b=baseline[str(yr)]
  baseline_checks[str(yr)]={'full_chain_matches_coverage':b['full_chain']=={'rows':int(cov['full_census_chain']['rows']),'population':int(cov['full_census_chain']['known_population'])},
   'joint_matches_coverage':b['joint_point_full_chain']=={'rows':int(cov['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(cov['joint_admitted_coordinate_and_full_chain']['known_population'])},
   'reproduced':b['full_chain']=={'rows':int(cov['full_census_chain']['rows']),'population':int(cov['full_census_chain']['known_population'])} and b['joint_point_full_chain']=={'rows':int(cov['joint_admitted_coordinate_and_full_chain']['rows']),'population':int(cov['joint_admitted_coordinate_and_full_chain']['known_population'])}}
 baseline_ok=all(x['reproduced'] for x in baseline_checks.values())
 if not baseline_ok:raise SystemExit('pinned accepted coverage could not be reproduced; no conditional gain will be reported')

 sim=[];point_uses=[];already_point=set(point_ids);edge_results=Counter()
 eligible.sort(key=lambda r:(-(r['population'] or 0),r['source_record_id']))
 for rec in eligible:
  sid=rec['source_record_id'];target=rec['current_direct_source_record_id'];outcome=uf.union_ids(sid,target);edge_results[outcome]+=1
  rec['conditional_union_result']=outcome
  if outcome=='year_constrained_collision':
   rec['candidate_status']='held_year_constrained_collision';rec['gate_failures_json']=json.dumps(['candidate_edge_creates_same_year_component_collision'],ensure_ascii=False)
  elif outcome=='missing_vertex':
   rec['candidate_status']='held_missing_graph_vertex';rec['gate_failures_json']=json.dumps(['candidate_endpoint_missing'],ensure_ascii=False)
  else:
   rec['candidate_edge_relation']='same_place';rec['identity_admitted']=False
   sim.append({'from_source_record_id':sid,'from_year':rec['year'],'to_source_record_id':target,'to_year':2021,'relation':'same_place','conditional_union_result':outcome,'population':rec['population'],'candidate_only':True,'identity_admitted':False})
   if sid not in already_point:
    db=json.loads(rec['raw_live_2011_dbf_witness_json'])
    point_uses.append({'target_source_record_id':sid,'target_year':rec['year'],'latitude':float(db['latitude_raw']),'longitude':float(db['longitude_raw']),
      'coordinate_source':'candidate exact typed physical GeoKLADR 2011 native object; point-only retrospective association pending independent review',
      'coordinate_source_record_id':'GEOKLADR2011:'+rec['historical_okato_2011_raw'],'point_origin_kind':'raw_named_typed_2011_physical_geo_object',
      'point_origin_file':str(DBF),'point_origin_sha256':pins[str(DBF)]['sha256'],
      'point_origin_locator':f"DBF_record_1based={db['record_1based']};DBF_byte_offset_0based={db['byte_offset_0based']};OKATO2011_raw={rec['historical_okato_2011_raw']}",
      'direct_2021_witness_source_record_id':target,'distance_to_2021_direct_point_km':rec['native_historic_to_current_direct_point_min_distance_km'],
      'coordinate_admission_status':'candidate_only_no_admission','temporal_identity_admitted':False,'native_publisher_code_binding_claimed':False,
      'population_boundary_comparability_asserted':False,'independent_rule_review_required':True})
  rec['temporal_identity_admitted']=False;rec['population_boundary_comparability_asserted']=False
 after=metrics(s,uf,point_ids|{x['target_source_record_id'] for x in point_uses})
 delta={yr:{axis:{m:after[yr][axis][m]-baseline[yr][axis][m] for m in ('rows','population')} for axis in ('full_chain','joint_point_full_chain')} for yr in baseline}

 # Population/rule partitions for the whole exact-typed joined H universe.
 gate_totals=Counter();gate_pop=Counter();status_counts=Counter();status_pop=Counter()
 for x in staged:
  status_counts[(x['year'],x['candidate_status'])]+=1
  if x['population'] is not None:status_pop[(x['year'],x['candidate_status'])]+=x['population']
  for reason in json.loads(x['gate_failures_json']):
   gate_totals[(x['year'],reason)]+=1
   if x['population'] is not None:gate_pop[(x['year'],reason)]+=x['population']
 # Fixed review-ready view: all eligibles plus deterministic high-mass/risk rows.
 sample=[];chosen={x['source_record_id']:'eligible_top_mass' for x in sorted(eligible,key=lambda z:(-(z['population'] or 0),z['source_record_id']))[:50]}
 rest=[x for x in staged if x['source_record_id'] not in chosen];rng=random.Random(20261004)
 risk=[x for x in rest if any(t in x['gate_failures_json'] for t in ('district','homonym','collision','duplicate'))]
 for x in rng.sample(risk,min(50,len(risk))):chosen[x['source_record_id']]='seeded_risk_50'
 bysid={x['source_record_id']:x for x in staged}
 for sid,label in chosen.items():sample.append({**bysid[sid],'sample_stratum':label})
 summary={'status':'typed_native_physical_corridor_candidate_only_no_admissions','rule':'Exact same-type selected source name and region unique at old and 2021 census dates; actual 2009 classifier and named typed 2011 native object code pair uniquely linked; actual 2009 parent county explicitly matches the old source county when supplied; duplicates are held unless that county uniquely selects the same physical object; accepted current direct proper point is within 5 km of actual historical point. P1082 is not used.','baseline_id':'corrected_fourth_current','baseline_graph_rows':len(g),'baseline_graph_sha256':pins[str(GRAPH)]['sha256'],'baseline_point_rows':len(p),'baseline_point_sha256':pins[str(POINTS)]['sha256'],'baseline_coverage_sha256':pins[str(COVERAGE)]['sha256'],'baseline_coverage_reproduced':baseline_ok,'baseline_reproduction_checks':baseline_checks,'old_typed_join_cohort':{'rows':len(staged),'by_year':dict(Counter(str(x['year']) for x in staged)),'population_by_year':{str(y):sum(x['population'] or 0 for x in staged if x['year']==y) for y in (2002,2010)}},'candidate_rows_for_independent_review':sum(x['candidate_status']=='candidate_for_independent_rule_review' or x.get('conditional_union_result') in {'merged','already_connected'} for x in eligible),'candidate_point_uses':len(point_uses),'conditional_union_results':dict(edge_results),'conditional_coverage_delta':delta if baseline_ok else None,'hard_hold_counts':dict(hard_event_count),'hold_reason_marginals_overlap':{f'{yr}:{reason}':n for (yr,reason),n in gate_totals.items()},'hold_population_marginals_overlap':{f'{yr}:{reason}':n for (yr,reason),n in gate_pop.items()},'sample':{'rows':len(sample),'design':'top 50 eligible population rows plus seeded 50 rule-risk rows','seed':20261004},'interpretation':['All identities and point uses remain candidates pending independent review.','Source native identifiers remain opaque; classifier/GeoKLADR codes identify actual historical objects and are not asserted as publisher IDs.','Population is carried for sizing only; no P1082 matching, interpolation, allocation, or boundary comparability is used.','Unknown or changed administrative context is retained; no legal boundary date is inferred.']}
 # Write final registers and receipt; all inputs remain immutable.
 write_csv(OUT/'typed_native_corridor_candidate_register.csv',staged)
 write_csv(OUT/'conditional_same_place_edges.csv',sim)
 write_csv(OUT/'conditional_point_only_uses.csv',point_uses)
 write_csv(OUT/'fixed_rule_risk_sample.csv',sample)
 (OUT/'_scratch_candidate_register.csv').unlink(missing_ok=True)
 (OUT/'_scratch_enriched_candidate_register.csv').unlink(missing_ok=True)
 summary['inputs']=pins
 summary['outputs']={x.name:{'sha256':sha(x),'bytes':x.stat().st_size} for x in sorted(OUT.iterdir()) if x.is_file() and x.name not in {'summary.json','receipt.json'}}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 receipt={'status':summary['status'],'input_sha256':{k:v['sha256'] for k,v in pins.items()},'output_sha256':{x.name:sha(x) for x in sorted(OUT.iterdir()) if x.is_file() and x.name!='receipt.json'},'script_path':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__))}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs','hold_population_marginals_overlap'}},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
