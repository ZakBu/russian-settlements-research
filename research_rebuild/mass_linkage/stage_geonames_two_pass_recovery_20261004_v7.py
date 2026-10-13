#!/usr/bin/env python3
"""Rebuild current 2021 coordinate candidates with order-independent GeoNames ADM1 joins.

The RU.txt scan is deliberately two-pass: first index every RU ADM1 node and
crosswalk, then resolve all current physical PPL rows against the complete map.
Outputs remain staged candidates; accepted ledgers are read-only.
"""
from __future__ import annotations
import csv, hashlib, json, math, re, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd

ROOT=Path('/workspace/settlements-work')
BASE=ROOT/'continuation_20261004'
OUT=BASE/'R4/wikidata_points/extensions/geonames_two_pass_v7'
REPO=Path('/workspace/russian-settlements-research')
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
SOURCE_EVIDENCE=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
POINTS=BASE/'accepted_mass_extensions/accepted_point_uses.parquet'
EDGES=BASE/'accepted_mass_extensions/accepted_identity_edges.parquet'
COVERAGE=BASE/'accepted_mass_extensions/coverage.json'
PROVIDER=ROOT/'wikidata/wide_v5/provider_code_candidate_screen.parquet'
REGION_SCREEN=ROOT/'coordinates/region_screen_v1/region_point_screen.parquet'
ZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
ADM=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_admin1CodesASCII_20260907.txt')
BLOCKED=ROOT/'continuation_20261003/blocked_point_reuse_targets_v1.json'
WD_RECEIPT=BASE/'independent_review/wikidata_review_receipt_final.json'
FEDERAL=BASE/'federal_application/accepted_territory_reference_points.parquet'
YEARS=(2002,2010,2021)
ZIP_SHA='9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4'
RU_SHA='3ef8f69d9c6b8adbd53afc35f6dc774b1d01b04f566622e1892a6d2f00d2f4d0'
PPL_CODES={'PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLA5','PPLC'}
FIELDS='geonameid name asciiname alternatenames latitude longitude feature_class feature_code country_code cc2 admin1 admin2 admin3 admin4 population elevation dem timezone modification_date'.split()
RAW_SOURCE_FIELDS=['object_level','object_name','oktmo','region','mun_upper','mun_lower','settlement','population','settlement_with_type_dadata','settlement_type_dadata','settlement_type_full_dadata','settlement_dadata','fias_level_dadata','latitude_dadata','longitude_dadata']

def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha_file(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def norm(v):
 if v is None or pd.isna(v): return ''
 return ' '.join(re.sub(r'\s+',' ',str(v).replace('ё','е').casefold()).split())
def region_key(v):
 s=norm(v);s=re.sub(r'[-–—]+',' ',s)
 aliases={'рсо':'северная осетия алания','кчр':'карачаево черкесская','кбр':'кабардино балкарская','якутия':'саха якутия','удмуртия':'удмуртская','чувашия':'чувашская','нижегород':'нижегородская','чувашская республика чувашия':'чувашская'}
 s=aliases.get(s,s);s=re.sub(r'^республика\s+','',s)
 s=s.replace('саха (якутия)','саха якутия')
 s=re.sub(r'\s+автономный округ(?=\s+югра$)','',s)
 s=re.sub(r'\s+(область|обл\.?|край|края|республика|респ\.?|автономный округ|автономная область)$','',s)
 return ' '.join(s.split())
def num(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (TypeError,ValueError): return None
def truth(v): return str(v).strip().casefold() in {'true','1','t','yes'}
def code_key(v):
 if v is None or pd.isna(v): return ''
 return re.sub(r'\.0$','',str(v).strip())
def aliases(row):
 return {norm(t) for t in [row['name'],*row['alternatenames'].split(',')] if str(t).strip() and re.search('[А-Яа-яЁё]',str(t))}
def hav(a,b):
 p1,p2=map(math.radians,(a[0],b[0]));dp=p2-p1;dl=math.radians(b[1]-a[1])
 z=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.asin(math.sqrt(z))
def compact(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def source_typed_label_matches(label,typ,name):
 label,typ,name=norm(label),norm(typ),norm(name)
 prefixes={'город':['г','город'],'деревня':['д','дер','деревня'],'село':['с','село'],'поселок':['п','пос','поселок'],'посёлок':['п','пос','поселок'],'пгт':['пгт','поселок городского типа'],'поселок городского типа':['пгт','поселок городского типа'],'хутор':['х','хутор'],'станица':['ст-ца','станица'],'станция':['ст','станция'],'разъезд':['рзд','разъезд'],'аул':['аул'],'починок':['починок'],'выселок':['выселок'],'местечко':['местечко'],'казарма':['казарма']}
 if not (label and typ and name): return False
 for pre in prefixes.get(typ,[typ]):
  m=re.match(r'^'+re.escape(pre)+r'(?:\.\s*|\s+)(.+)$',label)
  if m and m.group(1)==name:return True
 return False

class DSU:
 def __init__(self,ids,years):
  self.ix={x:i for i,x in enumerate(ids)};self.p=list(range(len(ids)));self.r=[0]*len(ids);self.mask=[1<<{2002:0,2010:1,2021:2}[int(y)] for y in years]
 def find(self,i):
  x=i
  while self.p[x]!=x:x=self.p[x]
  while self.p[i]!=i:n=self.p[i];self.p[i]=x;i=n
  return x
 def root(self,sid):return self.find(self.ix[sid])
 def union(self,a,b):
  x,y=self.find(self.ix[a]),self.find(self.ix[b])
  if x==y:return
  if self.r[x]<self.r[y]:x,y=y,x
  self.p[y]=x;self.mask[x]|=self.mask[y]
  if self.r[x]==self.r[y]:self.r[x]+=1

def load_holds():
 blocked=set(json.loads(BLOCKED.read_text())['blocked_target_source_record_ids'])
 dec=json.loads(WD_RECEIPT.read_text())['decision']
 wd3=set(dec['hard_geo_point_choice_hold_ids']);city4=set(dec['four_frozen_known_holds_not_in_candidate_pool'])
 fed=set(pd.read_parquet(FEDERAL,columns=['source_record_id']).source_record_id.astype(str))
 return {'known_quarantine_31':blocked,'wikidata_hard_point_conflict_3':wd3,'frozen_city_holds_4':city4,'federal_territory_points_6':fed}

def load_geonames(expected_regions, needed_names):
 if sha_file(ZIP)!=ZIP_SHA:raise RuntimeError('GeoNames ZIP byte hash changed')
 with zipfile.ZipFile(ZIP) as z:body=z.read('RU.txt');readme=z.read('readme.txt')
 if sha_bytes(body)!=RU_SHA:raise RuntimeError('GeoNames RU.txt member hash changed')
 raw_lines=body.splitlines(keepends=True)
 # PASS 1: build the complete RU ADM1 map before examining any place point.
 regions={};byte=0;adm1_rows=[]
 for n,raw in enumerate(raw_lines,1):
  start=byte;byte+=len(raw);cells=raw.decode('utf-8').rstrip('\r\n').split('\t')
  if len(cells)!=len(FIELDS):raise ValueError(f'GeoNames row {n} field count {len(cells)}')
  row=dict(zip(FIELDS,cells))
  if row['country_code']!='RU' or row['feature_class']!='A' or row['feature_code']!='ADM1':continue
  matches=defaultdict(list)
  for a in [row['name'],*row['alternatenames'].split(',')]:
   k=region_key(a)
   if k in expected_regions:matches[k].append(a)
  if len(matches)==1:
   k=next(iter(matches));c=row['admin1']
   if c in regions:raise RuntimeError(f'duplicate RU ADM1 code {c}')
   regions[c]={'region_norm':k,'geonameid':row['geonameid'],'matched_aliases':sorted(matches[k]),'name':row['name'],'line':n,'byte_start':start,'byte_end':byte,'line_sha256':sha_bytes(raw)}
  adm1_rows.append((n,start,raw,row))
 resolved_regions={r['region_norm'] for r in regions.values()}
 unresolved_regions=sorted(set(expected_regions)-resolved_regions)
 # Crosswalk each ADM1 code against the pinned ASCII table.
 adm={};adm_bytes=ADM.read_bytes()
 for n,line in enumerate(adm_bytes.splitlines(),1):
  c=line.decode('utf-8').split('\t')
  if len(c)!=4:raise ValueError(f'ADM1 crosswalk line {n} field count')
  if c[0].startswith('RU.'):
   adm[c[0].split('.',1)[1]]={'name':c[1],'ascii_name':c[2],'geonameid':c[3],'line':n,'line_sha256':sha_bytes(line)}
 for c,r in regions.items():
  if c not in adm or adm[c]['geonameid']!=r['geonameid']:raise RuntimeError(f'ADM1 crosswalk mismatch RU.{c}')
 # PASS 2: resolve every exact alias on every RU physical populated-place row.
 by_key=defaultdict(dict);physical_count=0;resolved_count=0;byte=0
 for n,raw in enumerate(raw_lines,1):
  start=byte;byte+=len(raw);cells=raw.decode('utf-8').rstrip('\r\n').split('\t');row=dict(zip(FIELDS,cells))
  if row['country_code']!='RU' or row['feature_class']!='P' or row['feature_code'] not in PPL_CODES:continue
  physical_count+=1;admrec=regions.get(row['admin1'])
  if not admrec:continue
  names=aliases(row);keys={(a,admrec['region_norm']) for a in names if a in needed_names}
  if not keys:continue
  resolved_count+=1
  rec={**row,'source_line_1based':n,'byte_start':start,'byte_end':byte,'line_sha256':sha_bytes(raw),
       'admin1_code':row['admin1'],'admin1_region_norm':admrec['region_norm'],'admin1_geonameid':admrec['geonameid'],
       'admin1_aliases':admrec['matched_aliases'],'admin1_crosswalk_name':adm[row['admin1']]['name'],'admin1_crosswalk_line':adm[row['admin1']]['line'],
       'matched_aliases':sorted(a for a in names if a in needed_names)}
  for key in keys:by_key[key][row['geonameid']]=rec
 return by_key,regions,adm,readme,body,{'ru_txt_total_rows':len(raw_lines),'ru_physical_current_PPL_rows':physical_count,'PPL_rows_resolved_after_complete_ADM1_index':resolved_count,'RU_ADM1_regions_expected':len(expected_regions),'RU_ADM1_regions_indexed':len(regions),'RU_ADM1_regions_unresolved_or_alias_ambiguous':unresolved_regions,'admin1_crosswalk_RU_rows':len(adm),'RU_txt_sha256':sha_bytes(body),'admin1_crosswalk_sha256':sha_file(ADM),'README_sha256':sha_bytes(readme),'algorithm':'pass1 all ADM1 nodes; pass2 all RU physical PPL-family rows; exact whole-ADM1 alias QID counts before distance/geometry filters'}

def main():
 if (OUT/'freeze_manifest.json').exists():raise SystemExit(f'refusing to overwrite frozen V7 review bundle: {OUT}')
 OUT.mkdir(parents=True,exist_ok=True)
 sys.path.insert(0,str(REPO))
 from research_rebuild.mass_linkage.coordinate_validation_packet import _load_region_geometries,_point_inside_source_region
 from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES,ACCEPTED_PROJECTION_STATUSES
 # Selected source records define the whole-year name and native-code uniqueness universe.
 selected=pd.read_parquet(SELECTED)
 selected=selected[selected.census_year.eq(2021)].copy();selected.source_record_id=selected.source_record_id.astype(str)
 if selected.source_record_id.duplicated().any():raise RuntimeError('2021 selected source IDs are not unique')
 accepted_points=pd.read_parquet(POINTS)
 if accepted_points.coordinate_admission_status.isna().any() or not accepted_points.coordinate_admission_status.astype(str).isin(ACCEPTED_COORDINATE_STATUSES).all():raise RuntimeError('invalid current point-use canonical status')
 current2021=set(accepted_points.loc[accepted_points.target_year.eq(2021),'target_source_record_id'].astype(str))
 allids=set(selected.source_record_id);unknown=current2021-allids
 if unknown:raise RuntimeError(f'{len(unknown)} accepted 2021 point targets absent from selected source')
 residual=selected[~selected.source_record_id.isin(current2021)].copy()
 if len(selected)!=155414 or len(current2021)!=144302 or len(residual)!=11112:raise RuntimeError(f'current residual frame mismatch selected={len(selected)} points={len(current2021)} residual={len(residual)}')
 # Whole 2021 name/type/region and raw-native-code uniqueness, before residual-specific screening.
 residual['name_key']=residual.settlement_name.map(norm);residual['type_key']=residual.settlement_type.map(norm);residual['region_key']=residual.region_norm.map(region_key);residual['code_key']=residual.oktmo.map(code_key)
 selected['name_key']=selected.settlement_name.map(norm);selected['type_key']=selected.settlement_type.map(norm);selected['region_key']=selected.region_norm.map(region_key);selected['code_key']=selected.oktmo.map(code_key)
 name_counts=selected.groupby(['name_key','type_key','region_key'],dropna=False).source_record_id.nunique().to_dict()
 code_counts=selected[selected.code_key.ne('')].groupby('code_key').source_record_id.nunique().to_dict()
 ev=pd.read_parquet(SOURCE_EVIDENCE,columns=['source_record_id','census_year','source_evidence_json']);ev.source_record_id=ev.source_record_id.astype(str)
 residual=residual.merge(ev[ev.census_year.eq(2021)],on=['source_record_id','census_year'],how='left',validate='one_to_one')
 provider=pd.read_parquet(PROVIDER,columns=['source_record_id','source_is_physical_np']);provider.source_record_id=provider.source_record_id.astype(str)
 residual=residual.merge(provider,on='source_record_id',how='left',validate='one_to_one')
 hold_sets=load_holds();allholds=set().union(*hold_sets.values())|current2021
 residual['hold_memberships_json']=residual.source_record_id.map(lambda x:compact([k for k,v in hold_sets.items() if x in v]+(['current_accepted_2021_point'] if x in current2021 else [])))
 residual['existing_hold']=residual.source_record_id.isin(allholds)
 # Reopen original source records from row locators and pin both source file and payload.
 rawcache={};filehash={};rawmeta={};raw_gn_source_paths={}
 for x in residual.itertuples(index=False):
  sf=Path('/workspace/settlements-raw')/str(x.source_file)
  rownum=num(str(x.source_record_id).rsplit(':',1)[-1])
  if not sf.exists() or rownum is None or rownum<1:
   rawmeta[x.source_record_id]={'status':'source_asset_or_locator_missing'};continue
  if sf not in rawcache:rawcache[sf]=pd.read_parquet(sf,columns=RAW_SOURCE_FIELDS)
  if sf not in filehash:filehash[sf]=sha_file(sf)
  ix=int(rownum)-1
  if ix>=len(rawcache[sf]):rawmeta[x.source_record_id]={'status':'source_row_locator_out_of_bounds'};continue
  q=rawcache[sf].iloc[ix]
  raw={k:(None if pd.isna(q[k]) else (q[k].item() if hasattr(q[k],'item') else q[k])) for k in RAW_SOURCE_FIELDS}
  rawjson=compact(raw);rawpt=(num(raw.get('latitude_dadata')),num(raw.get('longitude_dadata')))
  selpt=(num(x.latitude),num(x.longitude));d=hav(rawpt,selpt) if all(v is not None for v in rawpt+selpt) else None
  checks={'raw_object_level_is_NP':norm(raw.get('object_level'))=='населенный пункт',
          'raw_native_code_exact_after_trailing_dot_zero_only':code_key(raw.get('oktmo'))==code_key(x.oktmo),
          'raw_label_has_exact_known_type_prefix_and_exact_name':source_typed_label_matches(raw.get('settlement'),x.settlement_type,x.settlement_name),
          'raw_region_exact':norm(raw.get('region'))==norm(x.region_raw),
          'raw_population_exact':num(raw.get('population'))==num(x.population),
          'raw_source_coordinate_equals_selected_within_1m':d is not None and d<=0.001,
          'raw_source_coordinate_WGS84':all(v is not None for v in rawpt) and -90<=rawpt[0]<=90 and -180<=rawpt[1]<=180}
  rawmeta[x.source_record_id]={'status':'verified' if all(checks[k] for k in ['raw_object_level_is_NP','raw_native_code_exact_after_trailing_dot_zero_only','raw_label_has_exact_known_type_prefix_and_exact_name','raw_region_exact','raw_population_exact','raw_source_coordinate_equals_selected_within_1m']) else 'source_row_contradiction',
       'path':str(sf),'file_sha256':filehash[sf],'row_1based':int(rownum),'payload_json':rawjson,'payload_sha256':sha_bytes(rawjson.encode()),'checks':checks,
       'raw_latitude':rawpt[0],'raw_longitude':rawpt[1],'selected_latitude':selpt[0],'selected_longitude':selpt[1],'selected_source_coordinate_distance_m':d*1000 if d is not None else None}
 # Eligibility frame screens physical source observations but uses no inherited provider-quality score.
 eligible=[];name_to_ids=defaultdict(list)
 for x in residual.itertuples(index=False):
  source_raw=rawmeta.get(x.source_record_id,{})
  good=(not x.existing_hold and source_raw.get('status')=='verified' and truth(x.is_additive_settlement_record)
        and str(x.population_scope)=='settlement' and bool(x.source_is_physical_np)
        and bool(x.name_key and x.type_key and x.region_key) and x.code_key!=''
        and num(x.population) is not None and num(x.population)>=0
        and (int(name_counts.get((x.name_key,x.type_key,x.region_key),0))==1)
        and int(code_counts.get(x.code_key,0))==1)
  if good:
   eligible.append(x.source_record_id);name_to_ids[(x.name_key,x.region_key)].append(x.source_record_id)
 # Expected ADM1 are from exactly-scoped atomic source records; whole alias QID counts include all PPLs in ADM1.
 expected=set(residual.loc[residual.source_record_id.isin(eligible),'region_key'].astype(str))
 name_keys={k[0] for k in name_to_ids}
 gn_by,regions,adm1,readme,gn_body,gn_meta=load_geonames(expected,name_keys)
 geometries,region_codes=_load_region_geometries()
 region_screen=pd.read_parquet(REGION_SCREEN,columns=['source_record_id','geometry_iso']);geom_by=region_screen.set_index('source_record_id').geometry_iso.to_dict()
 # Materialize one row for every current 2021 residual, including explicit holds.
 results=[];proposals=[]
 for x in residual.itertuples(index=False):
  sid=x.source_record_id;raw=rawmeta.get(sid,{});pt=(raw.get('raw_latitude'),raw.get('raw_longitude'))
  key=(x.name_key,x.region_key);matches=list(gn_by.get(key,{}).values()) if sid in set(eligible) else []
  rawpoint_valid=all(v is not None for v in pt) and -90<=pt[0]<=90 and -180<=pt[1]<=180
  geo=geom_by.get(sid);source_inside=bool(rawpoint_valid and _point_inside_source_region(pt[0],pt[1],geo,geometries,region_codes)[0])
  witness=[]
  for g in matches:
   glat=num(g['latitude']);glon=num(g['longitude']);wgs=glat is not None and glon is not None and -90<=glat<=90 and -180<=glon<=180
   bind=(g['admin1_code'] in regions and regions[g['admin1_code']]['region_norm']==x.region_key
         and adm1.get(g['admin1_code'],{}).get('geonameid')==g['admin1_geonameid'])
   inside=bool(wgs and _point_inside_source_region(glat,glon,geo,geometries,region_codes)[0])
   dist=hav(pt,(glat,glon)) if rawpoint_valid and wgs else None
   aliases_hit=g['matched_aliases']
   witness.append({'geonameid':g['geonameid'],'geonames_name_raw':g['name'],'geonames_asciiname_raw':g['asciiname'],'matched_literal_aliases_norm':aliases_hit,
       'feature_class':g['feature_class'],'feature_code':g['feature_code'],'country_code':g['country_code'],'admin1_code':g['admin1_code'],
       'admin1_region_norm':g['admin1_region_norm'],'admin1_geonameid':g['admin1_geonameid'],'admin1_raw_aliases':g['admin1_aliases'],
       'admin1_crosswalk_name':g['admin1_crosswalk_name'],'admin1_crosswalk_line':g['admin1_crosswalk_line'],
       'latitude':glat,'longitude':glon,'source_point_distance_km_diagnostic':dist,
       'source_line_1based':g['source_line_1based'],'byte_start':g['byte_start'],'byte_end':g['byte_end'],'line_sha256':g['line_sha256'],
       'wgs84_valid':wgs,'admin1_region_binding_ok':bind,'point_inside_expected_ADM1_geometry':inside})
  # Uniqueness is calculated on every whole-ADM1 exact-name PPL QID before the
  # source-distance and spatial filters; these counts diagnose same-name rivals.
  all_valid=bool(witness) and all(y['wgs84_valid'] and y['admin1_region_binding_ok'] and y['point_inside_expected_ADM1_geometry'] for y in witness)
  source_near=[y for y in witness if y['source_point_distance_km_diagnostic'] is not None and y['source_point_distance_km_diagnostic']<=1.0]
  pairspread=max((hav((a['latitude'],a['longitude']),(b['latitude'],b['longitude'])) for i,a in enumerate(witness) for b in witness[i+1:]),default=0.0)
  compact_cluster=bool(witness) and pairspread<=1.0 and len(source_near)==len(witness)
  unique_place=len({y['geonameid'] for y in witness})==1
  src_route=bool(sid in set(eligible) and source_inside and all_valid and compact_cluster and not x.existing_hold)
  gn_route=bool(sid in set(eligible) and source_inside and all_valid and unique_place and len(witness)==1 and witness[0]['source_point_distance_km_diagnostic'] is not None and witness[0]['source_point_distance_km_diagnostic']<=5.0 and not x.existing_hold)
  if x.existing_hold:status='preserve_current_point_or_scoped_hold'
  elif sid not in set(eligible):status='hold_source_scope_native_name_or_exact_row_gate'
  elif x.region_key not in {v['region_norm'] for v in regions.values()}:status='hold_expected_ADM1_alias_unresolved_or_ambiguous'
  elif not witness:status='hold_no_literal_whole_ADM1_PPL_alias'
  elif not all_valid:status='hold_invalid_or_wrong_ADM1_physical_place_witness'
  elif src_route:status='candidate_raw_source_point_with_whole_ADM1_GN_exact_alias_cluster_le_1km'
  elif gn_route:status='candidate_actual_GN_point_unique_exact_alias_source_distance_le_5km'
  elif not source_inside:status='hold_raw_source_point_outside_expected_ADM1_geometry'
  elif len(witness)>1 and pairspread>1:status='hold_multiple_whole_ADM1_exact_PPL_places_spread_over_1km'
  elif not compact_cluster and not gn_route:status='hold_source_GN_disagreement_or_alias_cluster_unresolved'
  else:status='hold_unresolved_point_route'
  chosen=None;family=None
  if src_route:
   chosen={'latitude':pt[0],'longitude':pt[1]};family='source_raw_2021_point_exact_native_name_type_region_unique_plus_complete_ADM1_PPL_alias_cluster_within_1km'
  elif gn_route:
   chosen={'latitude':witness[0]['latitude'],'longitude':witness[0]['longitude']};family='actual_GN_PPL_point_exact_native_name_type_region_unique_plus_complete_ADM1_PPL_alias_unique_within_5km'
  candidate=chosen is not None
  record={'source_record_id':sid,'census_year':2021,'source_population':num(x.population),'source_name':x.settlement_name,'source_name_raw':x.source_name_raw,
      'source_type':x.settlement_type,'source_region_raw':x.region_raw,'source_region_norm':x.region_key,'source_oktmo_raw':x.oktmo,'source_code_key_dot_zero_only':x.code_key,
      'source_name_type_region_rows_whole_2021':int(name_counts.get((x.name_key,x.type_key,x.region_key),0)),'source_native_code_rows_whole_2021':int(code_counts.get(x.code_key,0)) if x.code_key else 0,
      'source_object_scope':x.population_scope,'source_additive':truth(x.is_additive_settlement_record),'source_is_physical_np_source_screen':truth(x.source_is_physical_np),
      'source_selected_file':x.source_file,'source_selected_sha256':x.source_sha256,'source_selected_locator':x.source_locator,
      'source_raw_file':raw.get('path'),'source_raw_file_sha256':raw.get('file_sha256'),'source_raw_row_1based':raw.get('row_1based'),'source_raw_payload_sha256':raw.get('payload_sha256'),
      'source_raw_row_checks_json':compact(raw.get('checks',{})),'source_raw_coordinate_latitude':pt[0],'source_raw_coordinate_longitude':pt[1],
      'selected_source_point_inside_expected_ADM1':source_inside,'whole_expected_ADM1_exact_PPL_place_QID_count':len({y['geonameid'] for y in witness}),
      'whole_expected_ADM1_exact_PPL_rows_json':compact(witness),'whole_alias_search_before_distance_or_geometry_filter':True,
      'max_alias_point_pairwise_spread_km':pairspread if witness else None,'source_GN_min_distance_km':min((y['source_point_distance_km_diagnostic'] for y in witness if y['source_point_distance_km_diagnostic'] is not None),default=None),
      'source_GN_max_distance_km':max((y['source_point_distance_km_diagnostic'] for y in witness if y['source_point_distance_km_diagnostic'] is not None),default=None),
      'source_point_rule_pass':src_route,'direct_GN_point_rule_pass':gn_route,'candidate_only':candidate,'rule_status':status,'candidate_rule_family':family,
      'proposed_latitude':chosen['latitude'] if chosen else None,'proposed_longitude':chosen['longitude'] if chosen else None,
      'proposed_coordinate_origin':'actual raw selected source point' if src_route else ('actual GeoNames RU PPL-family point' if gn_route else None),
      'alternative_actual_points_json':compact({'raw_source_point':[pt[0],pt[1]] if rawpoint_valid else None,'GeoNames_witnesses':witness}),
      'existing_hold':bool(x.existing_hold),'hold_memberships_json':x.hold_memberships_json,
      'provider_identifier_binding_asserted':False,'GN_upstream_measurement_independence_proven':False,'census_date_measurement_proven':False,
      'coordinate_precision_upgraded':False,'coordinate_admission':False,'candidate_only_not_admitted':True}
  results.append(record)
  if candidate:
   proposals.append({'point_use_id':'GN7-'+hashlib.sha256((sid+'|'+family).encode()).hexdigest()[:18],'target_source_record_id':sid,'target_year':2021,
      'latitude':chosen['latitude'],'longitude':chosen['longitude'],'coordinate_source':record['proposed_coordinate_origin'],
      'coordinate_admission_status':'candidate_only_pending_independent_review','candidate_only':True,'coordinate_admission':False,'candidate_rule_family':family,
      'source_raw_file':raw['path'],'source_raw_file_sha256':raw['file_sha256'],'source_raw_row_1based':raw['row_1based'],'source_raw_payload_sha256':raw['payload_sha256'],
      'geo_names_whole_ADM1_witnesses_json':compact(witness),'provider_identifier_binding_asserted':False,'GN_upstream_measurement_independence_proven':False,
      'census_date_measurement_proven':False,'coordinate_precision_upgraded':False})
 ledger=pd.DataFrame(results)
 uses=pd.DataFrame(proposals)
 # Canonical accepted graph baseline and conditional modern point continuity scenario.
 selected_all=pd.read_parquet(SELECTED,columns=['source_record_id','census_year','population']);selected_all=selected_all[selected_all.census_year.isin(YEARS)].copy();selected_all.source_record_id=selected_all.source_record_id.astype(str);selected_all.census_year=selected_all.census_year.astype(int)
 edges=pd.read_parquet(EDGES,columns=['from_source_record_id','to_source_record_id','relation','decision_status','selection_projection_status'])
 if edges.decision_status.isna().any() or not edges.decision_status.astype(str).isin(ACCEPTED_EDGE_STATUSES).all():raise RuntimeError('invalid canonical accepted edge status')
 if edges.selection_projection_status.isna().any() or not edges.selection_projection_status.astype(str).isin(ACCEPTED_PROJECTION_STATUSES).all() or not edges.relation.eq('same_place').all():raise RuntimeError('invalid accepted edge projection/relation')
 ids=selected_all.source_record_id.tolist();idset=set(ids);years=selected_all.census_year.tolist();dsu=DSU(ids,years)
 for e in edges.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in idset or b not in idset:raise RuntimeError('accepted identity endpoint missing from selected census')
  dsu.union(a,b)
 point_targets=set(accepted_points.target_source_record_id.astype(str))
 if accepted_points.target_source_record_id.duplicated().any():raise RuntimeError('duplicate current accepted point target')
 def coverage(newseeds=set()):
  full={dsu.find(i) for i in range(len(ids)) if dsu.mask[dsu.find(i)]==7};newroots={dsu.root(x) for x in newseeds if x in dsu.ix}
  out=defaultdict(lambda:[0,0,0,0])
  for x in selected_all.itertuples(index=False):
   root=dsu.root(x.source_record_id)
   if root not in full:continue
   y=int(x.census_year);pop=0 if pd.isna(x.population) else int(x.population);out[y][0]+=1;out[y][1]+=pop
   if x.source_record_id in point_targets or root in newroots:out[y][2]+=1;out[y][3]+=pop
  return out
 baseline=coverage();receipt=json.loads(COVERAGE.read_text())
 for m in receipt['census_metrics']:
  y=int(m['year']);expected=[int(m['axes']['full_census_chain']['rows']),int(m['axes']['full_census_chain']['known_population']),int(m['axes']['joint_admitted_coordinate_and_full_chain']['rows']),int(m['axes']['joint_admitted_coordinate_and_full_chain']['known_population'])]
  if baseline[y]!=expected:raise RuntimeError(f'canonical current baseline mismatch {y}: {baseline[y]} vs {expected}')
 candids=set(uses.target_source_record_id.astype(str)) if len(uses) else set()
 roots=defaultdict(list)
 for sid in candids:roots[dsu.root(sid)].append(sid)
 collisions={str(k):v for k,v in roots.items() if len(v)>1}
 if collisions:raise RuntimeError(f'multiple candidate seeds in same current identity component: {list(collisions.values())[:5]}')
 after=coverage(candids)
 gains=[]
 for y in YEARS:
  b=baseline[y];a=after[y];gains.append({'year':y,'baseline_joint_full_chain_rows':b[2],'baseline_joint_full_chain_population':b[3],
      'conditional_joint_full_chain_rows':a[2],'conditional_joint_full_chain_population':a[3],'marginal_rows':a[2]-b[2],'marginal_population':a[3]-b[3],
      'interpretation':'new candidate 2021 points reused through already-accepted full-chain component under explicit continuity inference; not a census-date measurement'})
 directpop=int(pd.to_numeric(ledger.loc[ledger.candidate_only,'source_population'],errors='coerce').sum())
 # Fixed 100 sample: top 25 proposed population, all major failure classes, seeded remainder.
 ledger['population_band']=pd.cut(pd.to_numeric(ledger.source_population,errors='coerce'),[-.001,499,1999,9999,float('inf')],labels=['<500','500-1,999','2,000-9,999','10,000+']).astype(str)
 sample_ids=ledger.sort_values(['candidate_only','source_population','source_record_id'],ascending=[False,False,True]).head(25).source_record_id.tolist()
 seed=20261004
 quotas={'candidate_raw_source_point_with_whole_ADM1_GN_exact_alias_cluster_le_1km':20,'candidate_actual_GN_point_unique_exact_alias_source_distance_le_5km':20,
 'hold_multiple_whole_ADM1_exact_PPL_places_spread_over_1km':15,'hold_source_GN_disagreement_or_alias_cluster_unresolved':10,
 'hold_no_literal_whole_ADM1_PPL_alias':10,'hold_source_scope_native_name_or_exact_row_gate':10,'preserve_current_point_or_scoped_hold':10}
 for status,q in quotas.items():
  pool=ledger[(ledger.rule_status==status)&~ledger.source_record_id.isin(sample_ids)].copy().sort_values('source_record_id')
  if len(pool)>q:pool=pool.sample(n=q,random_state=seed+len(sample_ids))
  sample_ids += pool.source_record_id.tolist()
 if len(sample_ids)<100:
  pool=ledger[~ledger.source_record_id.isin(sample_ids)].sort_values(['source_population','source_record_id'],ascending=[False,True])
  sample_ids+=pool.head(100-len(sample_ids)).source_record_id.tolist()
 sample=ledger[ledger.source_record_id.isin(sample_ids)].copy().sort_values(['source_population','source_record_id'],ascending=[False,True]).head(100)
 sample['sample_seed']=seed;sample['sample_design']='top-25 candidate mass plus fixed risk-status quotas and deterministic fill; descriptive, not probability sample'
 # Re-open the actual recorded source / GN bytes for sample witnesses.
 sample_source_ok=[];sample_gn_ok=[];sample_label=[]
 for r in sample.itertuples(index=False):
  meta=rawmeta.get(r.source_record_id,{});srcok=meta.get('status')=='verified'
  gnrows=json.loads(r.whole_expected_ADM1_exact_PPL_rows_json) if isinstance(r.whole_expected_ADM1_exact_PPL_rows_json,str) else []
  gnok=True
  for g in gnrows:
   rawline=gn_body[int(g['byte_start']):int(g['byte_end'])];cells=rawline.decode('utf-8').rstrip('\r\n').split('\t')
   gnok &= sha_bytes(rawline)==g['line_sha256'] and len(cells)==len(FIELDS)
   if len(cells)==len(FIELDS):
    rawgn=dict(zip(FIELDS,cells));gnok &= rawgn['geonameid']==str(g['geonameid']) and rawgn['admin1']==str(g['admin1_code']) and rawgn['feature_class']=='P' and rawgn['feature_code'] in PPL_CODES and rawgn['country_code']=='RU'
    gnok &= norm(g['geonames_name_raw'])==norm(rawgn['name']) and all(a in aliases(rawgn) for a in g['matched_literal_aliases_norm'])
  sample_source_ok.append(srcok);sample_gn_ok.append(gnok and bool(gnrows))
  if r.existing_hold:lab='preserve_existing_or_quarantined_hold'
  elif not srcok:lab='genuine_source_row_contradiction_or_unresolved'
  elif not gnok and gnrows:lab='genuine_GeoNames_raw_locator_or_alias_contradiction'
  elif r.candidate_only and gnok:lab='verified_consistent_rule_inputs; GN upstream measurement lineage unknown'
  elif len(gnrows)>1 and float(r.max_alias_point_pairwise_spread_km or 0)>1:lab='genuine_multiple_physical_place_candidates_hold'
  else:lab='not_independently_resolved'
  sample_label.append(lab)
 sample['sample_source_raw_row_reopened_and_checked']=sample_source_ok;sample['sample_GN_raw_bytes_alias_feature_ADM1_checked']=sample_gn_ok;sample['sample_review_label']=sample_label

 # Candidate use table has only actual modern direct coordinates.
 ledger.to_csv(OUT/'current_2021_residual_rule_ledger.csv',index=False,encoding='utf-8')
 uses.to_csv(OUT/'staged_point_uses.csv',index=False,encoding='utf-8')
 sample.to_csv(OUT/'fixed_100_review_sample.csv',index=False,encoding='utf-8')
 risk=ledger.groupby(['rule_status','population_band'],dropna=False).agg(rows=('source_record_id','size'),source_population=('source_population','sum'),candidate_rows=('candidate_only','sum')).reset_index()
 risk.to_csv(OUT/'risk_strata.csv',index=False,encoding='utf-8')
 (OUT/'geonames_readme.txt').write_bytes(readme)
 # Save parse-wide regional records and algorithm receipt to permit direct audit.
 (OUT/'geonames_two_pass_receipt.json').write_text(json.dumps(gn_meta,ensure_ascii=False,indent=2)+'\n')
 srcfiles=sorted({m['path'] for m in rawmeta.values() if m.get('path')})
 input_paths=[SELECTED,SOURCE_EVIDENCE,POINTS,EDGES,COVERAGE,PROVIDER,REGION_SCREEN,ZIP,ADM,BLOCKED,WD_RECEIPT,FEDERAL]
 inhash={str(p):sha_file(p) for p in input_paths}
 inhash.update({p:sha_file(Path(p)) for p in srcfiles})
 cov_json={str(y):{'full_chain_rows':baseline[y][0],'full_chain_population':baseline[y][1],'joint_full_rows':baseline[y][2],'joint_full_population':baseline[y][3]} for y in YEARS}
 summary={'status':'candidate_only_no_admissions','scope':'all current 2021 selected-source records without a canonical accepted 2021 point use; residual derived from accepted_mass_extensions/accepted_point_uses.parquet, not prior potential_point flags',
  'current_population_frame':{'selected_2021_rows':len(selected),'canonical_accepted_2021_point_uses':len(current2021),'current_2021_residual_rows':len(residual),'residual_population':int(pd.to_numeric(residual.population,errors='coerce').sum())},
  'two_pass_GeoNames_rule':'Pass 1 indexes all RU ADM1 nodes and validates ADM1 code crosswalk; pass 2 examines all RU physical PPL/PPLA family records only after complete ADM1 map exists. Counts every distinct QID matching the exact normalized alias in the expected whole ADM1 before applying source-distance or geometry tests.',
  'candidate_rules':{'raw_source_point':'unique whole-2021 source name+type+region and native code, additive source physical NP, reopened exact raw provider row, exact literal whole-ADM1 PPL-family alias place or compact <=1km alias-place cluster, all source/GN points valid and inside expected ADM1; proposed coordinate is actual raw source point.',
     'direct_GN_point':'same source gates and one distinct literal whole-ADM1 PPL-family QID, raw source point within 5km, all point/ADM1 checks; proposed coordinate is actual GN point. 5km is only this scoped route, not a universal accuracy veto.',
     'provider_identifier_binding_asserted':False,'upstream_measurement_independence_proven':False,'census_date_measurement_proven':False},
  'candidate_counts':{'rows':len(uses),'2021_source_population':directpop,'by_family':ledger[ledger.candidate_only].candidate_rule_family.value_counts().to_dict(),
     'rule_status_counts':ledger.rule_status.value_counts().to_dict(),'hold_intersections':{'known_quarantine31':int(ledger.source_record_id.isin(hold_sets['known_quarantine_31']).sum()),'WD_hard3':int(ledger.source_record_id.isin(hold_sets['wikidata_hard_point_conflict_3']).sum()),'frozen_city4':int(ledger.source_record_id.isin(hold_sets['frozen_city_holds_4']).sum()),'federal6':int(ledger.source_record_id.isin(hold_sets['federal_territory_points_6']).sum())}},
  'GN_parse':gn_meta,'conditional_full_chain_gain_by_year':gains,'baseline_canonical_coverage_by_year':cov_json,
  'fixed_sample':{'rows':len(sample),'seed':seed,'source_raw_rows_checked':int(sample.sample_source_raw_row_reopened_and_checked.sum()),'GN_raw_lines_checked':int(sample.sample_GN_raw_bytes_alias_feature_ADM1_checked.sum()),'review_labels':sample.sample_review_label.value_counts().to_dict(),'design':'top 25 candidate population plus risk strata and deterministic fill; descriptive only'},
  'limits':['No point or identity admission is made.','Point correctness and external-provider identifier binding are separate; no national provider binding is asserted.','GeoNames coordinate upstream lineage is unknown; exact alias agreement does not prove independent measurement.','Historical coordinate, census-date measurement, temporal continuity, boundary comparability and population comparability are not asserted.','All 31 legacy quarantine IDs, all 3 Wikidata hard point-choice conflicts, 4 frozen known city holds, and 6 federal territory point targets remain held unless separate scoped resolution evidence exists.','GeoNames population is never used.','Numeric source codes retain their raw digits; only trailing .0 is treated as representation formatting. No zero-padding or arbitrary width coercion.'],
  'input_hashes':inhash,'raw_source_assets':{p:inhash[p] for p in srcfiles},'outputs':{}}
 outfiles=['current_2021_residual_rule_ledger.csv','staged_point_uses.csv','fixed_100_review_sample.csv','risk_strata.csv','geonames_readme.txt','geonames_two_pass_receipt.json']
 for f in outfiles:summary['outputs'][f]={'sha256':sha_file(OUT/f),'bytes':(OUT/f).stat().st_size}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 manifest={'status':'frozen_candidate_only_review_bundle','generator_path':str(Path(__file__).resolve()),'generator_sha256':sha_file(Path(__file__).resolve()),
    'input_hashes':inhash,'outputs_sha256':{f:sha_file(OUT/f) for f in outfiles+['summary.json']},
    'non_admission_notice':'All output point rows are proposals only. Canonical accepted identity and point ledgers were read-only.'}
 (OUT/'freeze_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'out':str(OUT),'residual_rows':len(residual),'candidate_rows':len(uses),'candidate_population':directpop,'by_family':summary['candidate_counts']['by_family'],'marginal_full_chain':gains,'output_hashes':manifest['outputs_sha256']},ensure_ascii=False))

if __name__=='__main__':main()
