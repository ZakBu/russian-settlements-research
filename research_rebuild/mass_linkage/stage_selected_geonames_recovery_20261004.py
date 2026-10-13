#!/usr/bin/env python3
"""Stage 2021 Tochno source points with a bounded exact-name GeoNames witness.

This produces coordinate-only review candidates, not admissions or provider-ID links.
"""
from __future__ import annotations
import hashlib, json, math, re, zipfile, random
from collections import Counter, defaultdict
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,'/workspace/russian-settlements-research')

ROOT=Path('/workspace/settlements-work')
OUT=ROOT/'continuation_20261004/wikidata_points/extensions/source_point_geonames_recovery'
RESIDUAL=ROOT/'continuation_20261004/root/mass_union_joint_residual.parquet'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
PROVIDER=ROOT/'wikidata/wide_v5/provider_code_candidate_screen.parquet'
REGION_SCREEN=Path('/workspace/settlements-work/coordinates/region_screen_v1/region_point_screen.parquet')
GEONAMES_ZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
ADM1_CODES=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_admin1CodesASCII_20260907.txt')
GEONAMES_ZIP_SHA='9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4'
GEONAMES_RU_SHA='3ef8f69d9c6b8adbd53afc35f6dc774b1d01b04f566622e1892a6d2f00d2f4d0'
BLOCKED_JSON=ROOT/'continuation_20261003/blocked_point_reuse_targets_v1.json'
WIKIDATA_REVIEW_RECEIPT=ROOT/'continuation_20261004/independent_review/wikidata_review_receipt_final.json'
FEDERAL_ACCEPTED=ROOT/'continuation_20261004/federal_application/accepted_territory_reference_points.parquet'
BASE_ACCEPTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/accepted_point_uses.parquet')
R4_ACCEPTED=ROOT/'continuation_20261004/root/R4/working_application/merged_point_uses.parquet'
PHYSICAL_CODES={'PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLA5','PPLC'}
GN_FIELDS='geonameid name asciiname alternatenames latitude longitude feature_class feature_code country_code cc2 admin1 admin2 admin3 admin4 population elevation dem timezone modification_date'.split()
SOURCE_FIELDS=['object_level','object_name','oktmo','region','mun_upper','mun_lower','settlement','population','settlement_with_type_dadata','settlement_type_dadata','settlement_type_full_dadata','settlement_dadata','fias_level_dadata','latitude_dadata','longitude_dadata']


def sha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def sha_file(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def norm(v)->str:
 if v is None or pd.isna(v):return ''
 return ' '.join(re.sub(r'\s+',' ',str(v).replace('ё','е').casefold()).split())
def region_key(v)->str:
 s=norm(v)
 s=re.sub(r'[-–—]+',' ',s)
 alias={'рсо':'северная осетия алания','кчр':'карачаево черкесская','кбр':'кабардино балкарская','якутия':'саха якутия','удмуртия':'удмуртская','чувашия':'чувашская','нижегород':'нижегородская','чувашская республика чувашия':'чувашская'}
 s=alias.get(' '.join(s.split()),s)
 s=re.sub(r'^республика\s+','',s)
 s=re.sub(r'\s+(область|обл\.?|край|края|республика|респ\.?|автономный округ|автономная область)$','',s)
 return ' '.join(s.split())
def aliases(row):
 return {t.strip() for t in [row['name'],*row['alternatenames'].split(',')] if t.strip() and re.search('[А-Яа-яЁё]',t)}
def haversine_km(a,b):
 p1,p2=map(math.radians,(a[0],b[0]));dp=p2-p1;dl=math.radians(b[1]-a[1]);h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.asin(math.sqrt(h))
def exact(s,v):return str(s)==str(v) and s is not None
def source_typed_label_matches(raw_label, selected_type, selected_name):
 """Exact typed prefix/name check, allowing only known settlement prefixes."""
 label=norm(raw_label); typ=norm(selected_type); name=norm(selected_name)
 if not label or not typ or not name:return False
 prefixes={
  'город':['г','город'],'деревня':['д','дер','деревня'],'село':['с','село'],
  'поселок':['п','пос','поселок'],'посёлок':['п','пос','поселок'],
  'пгт':['пгт','поселок городского типа'],'поселок городского типа':['пгт','поселок городского типа'],
  'хутор':['х','хутор'],'станица':['ст-ца','станица'],'станция':['ст','станция'],
  'разъезд':['рзд','разъезд'],'аул':['аул'],'починок':['починок'],'выселок':['выселок'],
  'казарма':['казарма'],'местечко':['местечко'],'погост':['погост'],'кордон':['кордон'],
 }
 for pre in prefixes.get(typ,[typ]):
  m=re.match(r'^'+re.escape(pre)+r'(?:\.\s*|\s+)(.+)$',label)
  if m:
   tail=m.group(1)
   # The raw Dadata label may carry a recognized settlement suffix (e.g. КП).
   return tail==name or bool(re.fullmatch(re.escape(name)+r'(?:\s+(?:кп|рп|сп))?',tail))
 return False

def source_raw_row(path, row_1based, cache):
 if path not in cache:
  cache[path]=pd.read_parquet(path,columns=SOURCE_FIELDS)
 row_index=int(row_1based)-1
 if row_index<0 or row_index>=len(cache[path]):return None
 return cache[path].iloc[row_index]

def row_payload(row):
 if row is None:return None
 out={k:(None if pd.isna(row[k]) else (row[k].item() if hasattr(row[k],'item') else row[k])) for k in SOURCE_FIELDS}
 return out

def load_holds():
 blocked=json.loads(BLOCKED_JSON.read_text())['blocked_target_source_record_ids']
 wd=json.loads(WIKIDATA_REVIEW_RECEIPT.read_text())['decision']['hard_geo_point_choice_hold_ids']
 wd+=json.loads(WIKIDATA_REVIEW_RECEIPT.read_text())['decision']['four_frozen_known_holds_not_in_candidate_pool']
 fed=set(pd.read_parquet(FEDERAL_ACCEPTED,columns=['source_record_id']).source_record_id.astype(str))
 base=pd.read_parquet(BASE_ACCEPTED,columns=['target_source_record_id','target_year'])
 base=set(base.loc[base.target_year.eq(2021),'target_source_record_id'].astype(str))
 r4=pd.read_parquet(R4_ACCEPTED,columns=['target_source_record_id','target_year'])
 r4=set(r4.loc[r4.target_year.eq(2021),'target_source_record_id'].astype(str))
 sets={'known_quarantine_31':set(blocked),'wikidata_hard_point_conflict_3':set(wd[:3]),'frozen_city_holds_4':set(wd[3:]),'federal_territory_points_6':fed,'frozen_current_point_uses_2021':base,'r4_current_point_uses_2021':r4}
 return sets

def load_gn_source(needed_keys, expected_regions):
 if sha_file(GEONAMES_ZIP)!=GEONAMES_ZIP_SHA:raise RuntimeError('GeoNames ZIP hash changed')
 with zipfile.ZipFile(GEONAMES_ZIP) as z:
  body=z.read('RU.txt');readme=z.read('readme.txt')
 if sha_bytes(body)!=GEONAMES_RU_SHA:raise RuntimeError('GeoNames RU.txt member hash changed')
 regions={}; p_rows=[]; line_no=0;byte_offset=0; all_rows=0; physical_current=0
 for raw in body.splitlines(keepends=True):
  line_no+=1;all_rows+=1; start=byte_offset;byte_offset+=len(raw)
  cells=raw.decode('utf-8').rstrip('\r\n').split('\t')
  if len(cells)!=len(GN_FIELDS):raise ValueError(f'GN RU.txt row field count {line_no}: {len(cells)}')
  row=dict(zip(GN_FIELDS,cells));row['source_line_1based']=line_no;row['ru_txt_byte_offset_start']=start;row['ru_txt_byte_offset_end']=byte_offset;row['ru_txt_line_sha256']=sha_bytes(raw)
  if row['country_code']!='RU':continue
  if row['feature_class']=='A' and row['feature_code']=='ADM1':
   matches=defaultdict(list)
   for alias in sorted(aliases(row)):
    key=region_key(alias)
    if key in expected_regions:matches[key].append(alias)
   if len(matches)==1:
    key=next(iter(matches));code=row['admin1']
    if code in regions:raise RuntimeError(f'duplicate RU ADM1 code {code}')
    regions[code]={'region_norm':key,'geonameid':row['geonameid'],'alias':matches[key][0],'line':line_no,'byte_start':start,'byte_end':byte_offset,'line_sha256':row['ru_txt_line_sha256'],'name':row['name']}
  if row['feature_class']=='P' and row['feature_code'] in PHYSICAL_CODES:
   physical_current+=1
   code=row['admin1']
   if not code:continue
   for alias in sorted(aliases(row)):
    key=(norm(alias),regions.get(code,{}).get('region_norm'))
    if key in needed_keys:p_rows.append({**row,'matched_alias':alias,'matched_name_norm':key[0],'matched_region_norm':key[1]})
 # Pin the ASCII admin1 crosswalk to the PPL ADM1 code used above.
 adm_sha=sha_file(ADM1_CODES); adm={}
 rawadm=ADM1_CODES.read_bytes()
 for n,line in enumerate(rawadm.splitlines(),1):
  c=line.decode('utf-8').split('\t')
  if len(c)!=4:raise ValueError(f'ADM1 code row {n}')
  if c[0].startswith('RU.'):
   adm[c[0].split('.',1)[1]]={'name':c[1],'ascii_name':c[2],'geonameid':c[3],'line':n,'raw_sha256':sha_bytes(line)}
 for code,rec in regions.items():
  if code not in adm or adm[code]['geonameid']!=rec['geonameid']:
   raise RuntimeError(f'RU.txt and admin1CodesASCII disagree for RU.{code}')
 return p_rows,regions,adm,readme,body,{'ru_txt_rows':all_rows,'physical_current_PPL_rows':physical_current,'adm1_codes_ru_rows':len(adm),'ru_txt_member_sha256':sha_bytes(body),'admin1_codes_sha256':adm_sha,'readme_sha256':sha_bytes(readme)}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 residual=pd.read_parquet(RESIDUAL)
 r=residual.loc[residual.census_year.eq(2021)&~residual.potential_point.fillna(False)].copy()
 selected=pd.read_parquet(SELECTED)
 selected=selected.loc[selected.census_year.eq(2021)].copy()
 selected['source_record_id']=selected.source_record_id.astype(str)
 r['source_record_id']=r.source_record_id.astype(str)
 provider=pd.read_parquet(PROVIDER,columns=['source_record_id','source_is_physical_np'])
 provider['source_record_id']=provider.source_record_id.astype(str)
 r=r.merge(provider,on='source_record_id',how='left',validate='one_to_one')
 # Native selected observation rows provide the exact normalized locality label;
 # the source Parquet row below is reopened at its 1-based source locator.
 r=r.merge(selected[['source_record_id','settlement_name','settlement_type','region_raw','region_norm','population','oktmo','okato','source_file','source_native_id','source_sha256','source_locator','latitude','longitude','population_scope','is_additive_settlement_record','name_norm','type_norm']],on='source_record_id',how='left',validate='one_to_one',suffixes=('','_selected'))
 hold_sets=load_holds(); all_hold=set().union(*hold_sets.values())
 # Existing accepted point uses and all named holds remain excluded.
 r['known_hold_memberships']=r.source_record_id.map(lambda sid:json.dumps([k for k,v in hold_sets.items() if sid in v],separators=(',',':')))
 r['existing_hold']=r.source_record_id.isin(all_hold)
 r['source_coord_wgs84_valid']=r.latitude.between(-90,90)&r.longitude.between(-180,180)
 r['basic_source_physical_scope']=r.source_is_physical_np.fillna(False).astype(bool)&r.population_scope.eq('settlement')&r.is_additive_settlement_record.fillna(False).astype(bool)
 # Only records with a real native OKTMO and a direct source coordinate can use this path.
 r['has_exact_source_native_code']=r.oktmo.notna()&r.oktmo.astype(str).str.strip().ne('')
 # Each 1-based Parquet source locator is parsed from source_record_id and pinned by source asset SHA.
 loc=r.source_record_id.str.rsplit(':',n=1).str[-1]
 r['source_parquet_row_1based']=pd.to_numeric(loc.str.replace('parquet:','',regex=False),errors='coerce')
 r['source_asset_path']=r.source_file.map(lambda f:str(Path('/workspace/settlements-raw')/str(f)) if pd.notna(f) else '')
 raw_by_path={};source_hash_by_path={};source_row_check=[]
 for t in r.itertuples(index=False):
  p=Path(t.source_asset_path)
  if not p.exists():source_row_check.append((t.source_record_id,None,None,'source_asset_missing'));continue
  if p not in raw_by_path:raw_by_path[p]=pd.read_parquet(p,columns=SOURCE_FIELDS)
  n=int(t.source_parquet_row_1based) if pd.notna(t.source_parquet_row_1based) else 0
  raw=source_raw_row(p,n,raw_by_path)
  if raw is None:source_row_check.append((t.source_record_id,None,None,'source_row_locator_invalid'));continue
  payload=row_payload(raw);payload_json=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))
  if p not in source_hash_by_path:source_hash_by_path[p]=sha_file(p)
  raw_point=(float(raw.latitude_dadata),float(raw.longitude_dadata)) if pd.notna(raw.latitude_dadata) and pd.notna(raw.longitude_dadata) else None
  selected_point=(float(t.latitude),float(t.longitude)) if pd.notna(t.latitude) and pd.notna(t.longitude) else None
  dist=haversine_km(raw_point,selected_point) if raw_point and selected_point else None
  coords_match=(raw_point is None and selected_point is None) or (dist is not None and dist<=0.001)
  checks={
   'proper_source_object_level':norm(raw.object_level)=='населенный пункт',
   'source_native_oktmo_equal':norm(raw.oktmo)==norm(t.oktmo),
   'source_raw_settlement_label_equal':norm(raw.settlement)==norm(t.source_name_raw),
   'source_raw_region_equal':norm(raw.region)==norm(t.region_raw),
   'source_raw_population_equal':float(raw.population)==float(t.population) if pd.notna(raw.population) and pd.notna(t.population) else False,
   'source_raw_coordinate_matches_selected_within_1m_or_both_missing':coords_match,
   'source_raw_coordinate_wgs84_valid':raw_point is not None and -90<=raw_point[0]<=90 and -180<=raw_point[1]<=180,
  }
  ok=all(checks[k] for k in ['proper_source_object_level','source_native_oktmo_equal','source_raw_settlement_label_equal','source_raw_region_equal','source_raw_population_equal','source_raw_coordinate_matches_selected_within_1m_or_both_missing'])
  source_row_check.append((t.source_record_id,raw_point,{'payload_json':payload_json,'payload_sha256':sha_bytes(payload_json.encode()),'file_sha256':source_hash_by_path[p],'row_1based':n,'checks':checks,'source_point':raw_point,'selected_source_distance_m':dist*1000 if dist is not None else None,'raw':payload},'verified' if ok else 'source_row_contradiction'))
 # Unique native code check in residual target universe, before applying GN name candidates.
 row_meta={sid:(rawpt,meta,status) for sid,rawpt,meta,status in source_row_check}
 r['source_raw_row_review']=r.source_record_id.map(lambda sid:row_meta[sid][2])
 r['source_raw_object_level_ok']=r.source_record_id.map(lambda sid:bool(row_meta[sid][1] and row_meta[sid][1].get('checks',{}).get('proper_source_object_level')))
 r['source_raw_payload_sha256']=r.source_record_id.map(lambda sid:row_meta[sid][1].get('payload_sha256') if row_meta[sid][1] else None)
 r['source_raw_payload_json']=r.source_record_id.map(lambda sid:row_meta[sid][1].get('payload_json') if row_meta[sid][1] else None)
 r['source_file_sha256_verified']=r.source_record_id.map(lambda sid:row_meta[sid][1].get('file_sha256') if row_meta[sid][1] else None)
 r['source_raw_latitude']=r.source_record_id.map(lambda sid:row_meta[sid][1].get('source_point',[None,None])[0] if row_meta[sid][1] and row_meta[sid][1].get('source_point') else None)
 r['source_raw_longitude']=r.source_record_id.map(lambda sid:row_meta[sid][1].get('source_point',[None,None])[1] if row_meta[sid][1] and row_meta[sid][1].get('source_point') else None)
 r['source_raw_row_checks_json']=r.source_record_id.map(lambda sid:json.dumps(row_meta[sid][1].get('checks',{}) if row_meta[sid][1] else {},sort_keys=True,separators=(',',':')))
 r['source_row_locator_status']=r.source_record_id.map(lambda sid:row_meta[sid][2])
 r['source_native_code_duplicate_count']=r.groupby('oktmo').source_record_id.transform('size')
 # Scope the exact-name scan to target row literal names and expected regions.
 target_base=r.loc[r.basic_source_physical_scope&r.source_coord_wgs84_valid&r.has_exact_source_native_code&~r.existing_hold].copy()
 target_by_id={x.source_record_id:x for x in target_base.itertuples(index=False)}
 expected_regions=set(target_base.region_norm.dropna().astype(str))
 name_to_sources=defaultdict(list)
 for x in target_base.itertuples(index=False):
  name=norm(x.settlement_name);reg=str(x.region_norm)
  if name and reg:name_to_sources[(name,reg)].append(x.source_record_id)
 p_rows,region_map,adm1_map,readme,gn_body,gn_meta=load_gn_source(set(name_to_sources),expected_regions)
 by_key=defaultdict(list)
 for row in p_rows:by_key[(row['matched_name_norm'],row['matched_region_norm'])].append(row)
 # Check points against expected generalised ADM1 geometry, not a provider quality score.
 from research_rebuild.mass_linkage.coordinate_validation_packet import _load_region_geometries,_point_inside_source_region
 geometries,region_codes=_load_region_geometries()
 region_frame=pd.read_parquet(REGION_SCREEN,columns=['source_record_id','geometry_iso'])
 geometry_by_source=region_frame.set_index('source_record_id').geometry_iso.to_dict()
 result=[]
 for x in r.itertuples(index=False):
  sid=x.source_record_id; base_gates={
   'residual_potential_point_false':True,
   'proper_source_np_population_scope':bool(x.basic_source_physical_scope),
   'source_wgs84_valid':bool(x.source_coord_wgs84_valid),
   'source_native_code_present':bool(x.has_exact_source_native_code),
   'known_hold_or_existing_point':bool(x.existing_hold),
   'source_row_reopened_and_exact':x.source_row_locator_status=='verified',
   'raw_source_object_is_settlement':bool(x.source_raw_object_level_ok),
   'source_native_code_unique_in_candidate_universe':int(x.source_native_code_duplicate_count)==1,
  }
  raw=target_by_id.get(sid)
  if raw is None:
   result.append({'source_record_id':sid,'source_population':x.population,'target_name':x.settlement_name,'target_type':x.settlement_type,'target_region':x.region_raw,'rule_status':'held_out_of_rule_scope','candidate_only':False,'existing_hold':bool(x.existing_hold),'source_row_review_label':'not_independently_resolved','gate_summary_json':json.dumps(base_gates,separators=(',',':')),'match_details_json':'[]'})
   continue
  region=geometry_by_source.get(sid)
  source_point=(float(row_meta[sid][1]['source_point'][0]),float(row_meta[sid][1]['source_point'][1])) if row_meta[sid][1] and row_meta[sid][1].get('source_point') else None
  source_inside=bool(source_point and _point_inside_source_region(source_point[0],source_point[1],region,geometries,region_codes)[0])
  key=(norm(raw.settlement_name),str(raw.region_norm)); hits=by_key.get(key,[])
  details=[]
  for h in hits:
   try:pt=(float(h['latitude']),float(h['longitude']))
   except Exception:pt=None
   wgs=bool(pt and -90<=pt[0]<=90 and -180<=pt[1]<=180)
   near=haversine_km(source_point,pt) if source_point and wgs else None
   admcode=h['admin1'];adm=adm1_map.get(admcode,{})
   adm1_region_ok=region_map.get(admcode,{}).get('region_norm')==key[1] and bool(adm) and adm.get('geonameid')==region_map.get(admcode,{}).get('geonameid')
   gn_inside=bool(wgs and _point_inside_source_region(pt[0],pt[1],region,geometries,region_codes)[0])
   details.append({'geonameid':h['geonameid'],'geonames_name_raw':h['name'],'geonames_alias_raw':h['matched_alias'],'feature_class':h['feature_class'],'feature_code':h['feature_code'],'country_code':h['country_code'],'admin1_code':admcode,'expected_region_norm':key[1],'admin1_raw_alias':region_map.get(admcode,{}).get('alias'),'admin1_geonameid':region_map.get(admcode,{}).get('geonameid'),'admin1_ascii_name':adm.get('ascii_name'),'admin1_codes_line':adm.get('line'),'admin1_codes_line_sha256':adm.get('raw_sha256'),'latitude':pt[0] if pt else None,'longitude':pt[1] if pt else None,'distance_to_source_km':near,'source_line_1based':h['source_line_1based'],'ru_txt_byte_offset_start':h['ru_txt_byte_offset_start'],'ru_txt_byte_offset_end':h['ru_txt_byte_offset_end'],'ru_txt_line_sha256':h['ru_txt_line_sha256'],'admin1_region_binding_ok':adm1_region_ok,'geonames_point_inside_expected_adm1':gn_inside,'wgs84_valid':wgs})
  all_geom=bool(details) and all(d['geonames_point_inside_expected_adm1'] and d['admin1_region_binding_ok'] and d['wgs84_valid'] for d in details)
  near=[d for d in details if d['distance_to_source_km'] is not None and d['distance_to_source_km']<=1]
  if source_inside and all_geom and len(details)==1 and len(near)==1:status='eligible_unique_exact_name_region_PPL_within_1km'; family='source_row_exact_native_OKTMO+raw_proper_NP+literal_current_PPL_name+ADM1+source_PPL_distance_le_1km'
  elif source_inside and len(details)>1 and len(near)==len(details) and all_geom and max(haversine_km((d['latitude'],d['longitude']),(e['latitude'],e['longitude'])) for i,d in enumerate(details) for e in details[i+1:])<=1:status='eligible_all_exact_name_region_PPL_matches_within_1km_cluster';family='source_row_exact_native_OKTMO+raw_proper_NP+literal_current_PPL_name+ADM1+all_PPL_matches_one_1km_cluster'
  elif not source_inside:status='hold_source_point_outside_expected_adm1';family=''
  elif not details:status='unresolved_no_literal_current_PPL_name_region_witness';family=''
  elif not all_geom:status='hold_geonames_wrong_or_unverified_ADM1_or_invalid_point';family=''
  elif len(near)==0:status='hold_exact_name_PPL_over_1km_from_source_point';family=''
  else:status='hold_same_name_region_has_disparate_PPL_candidates';family=''
  src_dupes=len(name_to_sources.get(key,[]))
  maxdist=max((d['distance_to_source_km'] or 0 for d in details),default=None)
  candidate=status.startswith('eligible_') and not x.existing_hold and x.source_row_locator_status=='verified' and int(x.source_native_code_duplicate_count)==1 and source_inside
  if x.existing_hold:status='preserve_known_hold';family=''
  result.append({'source_record_id':sid,'source_population':x.population,'target_name':raw.settlement_name,'source_raw_name':x.source_name_raw,'target_type':raw.settlement_type,'target_region':raw.region_raw,'source_oktmo_raw':raw.oktmo,'source_okato_raw':raw.okato,'source_point_latitude':source_point[0] if source_point else None,'source_point_longitude':source_point[1] if source_point else None,'source_coordinate_file':raw.source_file,'source_parquet_row_1based':raw.source_parquet_row_1based,'source_file_sha256_verified':row_meta[sid][1].get('file_sha256') if row_meta[sid][1] else None,'source_row_payload_sha256':row_meta[sid][1].get('payload_sha256') if row_meta[sid][1] else None,'source_raw_row_locator':f"{raw.source_file}:parquet-row-1based={int(raw.source_parquet_row_1based)}",'source_raw_row_checks_json':raw.source_raw_row_checks_json,'source_name_region_source_record_count':src_dupes,'selected_source_point_inside_expected_adm1':source_inside,'exact_name_region_geonames_hit_count':len(details),'within_1km_geonames_hit_count':len(near),'max_source_to_geonames_distance_km':maxdist,'rule_status':status,'rule_family':family,'candidate_only':bool(candidate),'existing_hold':bool(x.existing_hold),'provider_id_binding_asserted':False,'upstream_coordinate_lineage_independence_proven':False,'geonames_current_alias_date_proven':False,'census_date_point_measurement_proven':False,'coordinate_measurement_precision_upgraded':False,'source_row_review_label':('verified_consistent_source_raw_row_and_literal_GN_PPL_witness; upstream independence unknown' if candidate else ('genuine_source_or_spatial_contradiction' if status.startswith('hold_') and ('outside' in status or 'over_1km' in status or 'disparate' in status) else 'not_independently_resolved')),'gate_summary_json':json.dumps(base_gates,separators=(',',':')),'geonames_witness_rows_json':json.dumps(details,ensure_ascii=False,separators=(',',':'))})
 ledger=pd.DataFrame(result)
 # Keep full raw source pins available for every sample stratum, including holds.
 raw_evidence=[]
 for sid,rawpt,meta,status in source_row_check:
  raw_evidence.append({'source_record_id':sid,'source_asset_sha256_verified':meta.get('file_sha256') if meta else None,'source_raw_payload_sha256':meta.get('payload_sha256') if meta else None,'source_raw_point_latitude':rawpt[0] if rawpt else None,'source_raw_point_longitude':rawpt[1] if rawpt else None,'source_raw_row_locator_status':status,'source_raw_row_checks_json_all':json.dumps(meta.get('checks',{}) if meta else {},sort_keys=True,separators=(',',':'))})
 ledger=ledger.merge(pd.DataFrame(raw_evidence),on='source_record_id',how='left',validate='one_to_one')
 # Candidate-only proposals use the exact current raw source point, never GN population or GN coordinate.
 proposals=ledger.loc[ledger.candidate_only].copy()
 proposals['proposed_coordinate_source']='raw Tochno source-row latitude/longitude'
 proposals['proposed_latitude']=proposals.source_point_latitude
 proposals['proposed_longitude']=proposals.source_point_longitude
 proposals['coordinate_use_admission']='review_required_not_admitted'
 proposals['scope_limitation']='2021 source-row point only; coordinate correctness scope only; no FIAS/provider-ID/temporal/boundary/population comparability assertion'
 ledger['population_band']=pd.cut(ledger.source_population,[-0.001,499,1999,9999,float('inf')],labels=['<500','500-1,999','2,000-9,999','10,000+']).astype(str)
 ledger['risk_stratum']=ledger.rule_status
 # Fixed sample: top 20 candidates, then deterministic risk/status × population-band sample, fill from remaining ledger.
 sample_ids=[]
 sample_ids += ledger.sort_values(['source_population','source_record_id'],ascending=[False,True]).head(20).source_record_id.tolist()
 rng_seed=20261004
 quotas={'eligible_unique_exact_name_region_PPL_within_1km':12,'eligible_all_exact_name_region_PPL_matches_within_1km_cluster':8,'hold_exact_name_PPL_over_1km_from_source_point':10,'hold_same_name_region_has_disparate_PPL_candidates':10,'unresolved_no_literal_current_PPL_name_region_witness':12,'hold_geonames_wrong_or_unverified_ADM1_or_invalid_point':8,'hold_source_point_outside_expected_adm1':5,'held_out_of_rule_scope':5}
 for status,q in quotas.items():
  pool=ledger[(ledger.rule_status==status)&~ledger.source_record_id.isin(sample_ids)].sort_values('source_record_id')
  if len(pool)>q:pool=pool.sample(n=q,random_state=rng_seed+len(sample_ids))
  sample_ids+=pool.source_record_id.tolist()
 if len(sample_ids)<100:
  pool=ledger[~ledger.source_record_id.isin(sample_ids)].copy()
  # Weight a fixed fraction to remaining high population and the rest to seeded general residual.
  top=pool.sort_values(['source_population','source_record_id'],ascending=[False,True]).head(100-len(sample_ids)//2)
  sample_ids+=top[~top.source_record_id.isin(sample_ids)].head(100-len(sample_ids)).source_record_id.tolist()
 if len(sample_ids)<100:
  pool=ledger[~ledger.source_record_id.isin(sample_ids)].sort_values('source_record_id')
  sample_ids+=pool.sample(n=min(100-len(sample_ids),len(pool)),random_state=rng_seed).source_record_id.tolist()
 sample=ledger[ledger.source_record_id.isin(sample_ids)].copy()
 sample['fixed_sample_seed']=rng_seed
 sample['sample_design']='top-20-proposals + risk-stratum quotas + seeded residual fill; not a probability estimate'
 sample=sample.sort_values(['source_population','source_record_id'],ascending=[False,True]).head(100)
 sample_raw_verified=[];sample_gn_verified=[];sample_labels=[];sample_notes=[]
 for x in sample.itertuples(index=False):
  sid=x.source_record_id; meta=row_meta.get(sid,(None,None,'missing'))[1]
  checks=meta.get('checks',{}) if meta else {}
  source_reopened=bool(meta and meta.get('file_sha256') and meta.get('payload_sha256') and meta.get('row_1based'))
  gn_raw=getattr(x,'geonames_witness_rows_json','[]')
  gn_details=json.loads(gn_raw) if isinstance(gn_raw,str) and gn_raw else []
  gn_ok=True
  for d in gn_details:
   a=int(d['ru_txt_byte_offset_start']);b=int(d['ru_txt_byte_offset_end']);raw_line=gn_body[a:b]
   cells=raw_line.decode('utf-8').rstrip('\r\n').split('\t')
   gn_ok &= sha_bytes(raw_line)==d['ru_txt_line_sha256'] and len(cells)==len(GN_FIELDS)
   if len(cells)==len(GN_FIELDS):
    raw_gn=dict(zip(GN_FIELDS,cells))
    gn_ok &= raw_gn['geonameid']==str(d['geonameid']) and raw_gn['feature_class']=='P' and raw_gn['feature_code'] in PHYSICAL_CODES and raw_gn['country_code']=='RU'
    gn_ok &= d['geonames_alias_raw'] in aliases(raw_gn)
  source_core_ok=all(checks.get(k,False) for k in ['source_native_oktmo_equal','source_raw_settlement_label_equal','source_raw_region_equal','source_raw_population_equal','source_raw_coordinate_matches_selected_within_1m_or_both_missing'])
  if not source_reopened:label='not_independently_resolved';note='source raw row locator or payload pin missing'
  elif x.existing_hold:label='preserve_existing_hold';note='known/frozen hold retained; no candidate admission'
  elif not source_core_ok:label='genuine_source_row_contradiction';note='raw source row fails exact native code/name/region/population/coordinate reconciliation'
  elif pd.isna(getattr(x,'source_point_latitude',float('nan'))) or pd.isna(getattr(x,'source_point_longitude',float('nan'))):label='not_independently_resolved';note='source identity row verified but no valid selected source coordinate is available'
  elif bool(x.candidate_only) and gn_ok:label='verified_consistent_source_row_and_literal_GN_PPL_witness; upstream independence unknown';note='raw source row and GeoNames bytes agree with staged rule; upstream measurement independence unknown'
  elif gn_details and not gn_ok:label='genuine_GeoNames_raw_line_contradiction';note='GN raw row bytes fail recorded witness locator/hash/feature/alias'
  elif x.rule_status in ['hold_exact_name_PPL_over_1km_from_source_point','hold_same_name_region_has_disparate_PPL_candidates','hold_geonames_wrong_or_unverified_ADM1_or_invalid_point','hold_source_point_outside_expected_adm1']:
   label='genuine_point_witness_contradiction_or_scope_hold';note=x.rule_status
  else:label='not_independently_resolved';note='no literal current PPL witness or rule scope does not admit candidate'
  sample_raw_verified.append(source_reopened and source_core_ok)
  sample_gn_verified.append(gn_ok and bool(gn_details))
  sample_labels.append(label);sample_notes.append(note)
 sample['sample_source_row_reopened_and_core_fields_verified']=sample_raw_verified
 sample['sample_geonames_raw_line_hash_and_feature_alias_verified']=sample_gn_verified
 sample['sample_independent_review_label']=sample_labels
 sample['sample_review_note']=sample_notes
 # Clear current historic/other route overlap for root review, but do not silently suppress candidates.
 alternate_ids=set()
 for p in [ROOT/'continuation_20261004/historical_points/staged_point_uses.parquet',ROOT/'continuation_20261004/historical_points/recovery/additional_point_only_staged_uses.parquet']:
  if p.exists():
   d=pd.read_parquet(p)
   for c in ['target_source_record_id','source_record_id']:
    if c in d:alternate_ids.update(d[c].dropna().astype(str))
 proposals['alternate_historical_point_route_overlap']=proposals.source_record_id.isin(alternate_ids)
 # Risk strata and high-mass summary use selected source census population, never GeoNames population.
 risk=ledger.groupby(['rule_status','population_band'],dropna=False).agg(rows=('source_record_id','size'),source_population=('source_population','sum'),high_mass_rows=('source_population',lambda s:int(s.gt(2000).sum()))).reset_index()
 OUT.mkdir(parents=True,exist_ok=True)
 ledger.to_csv(OUT/'residual_point_rule_ledger.csv',index=False,encoding='utf-8')
 proposals.to_csv(OUT/'staged_source_point_candidates.csv',index=False,encoding='utf-8')
 sample.to_csv(OUT/'fixed_100_review_sample.csv',index=False,encoding='utf-8')
 risk.to_csv(OUT/'risk_strata.csv',index=False,encoding='utf-8')
 (OUT/'geonames_readme.txt').write_bytes(readme)
 # Summary hashes include direct raw-source and gazetteer pins.
 targetpop=int(pd.to_numeric(r.population,errors='coerce').sum())
 high=ledger.loc[pd.to_numeric(ledger.source_population,errors='coerce').gt(2000)]
 prop_high=proposals.loc[pd.to_numeric(proposals.source_population,errors='coerce').gt(2000)]
 summary={
  'status':'candidate_only_no_coordinate_or_identity_admissions',
  'scope':'2021 residual point targets with potential_point=False; only raw current Tochno source-point plus literal GeoNames current PPL witness route',
  'candidate_pool_after_exact_hold_and_physical_scope_gates':{'rows':len(target_base),'source_population':int(target_base.population.sum()),'high_mass_rows_over_2000':int(target_base.population.gt(2000).sum()),'high_mass_source_population':int(target_base.loc[target_base.population.gt(2000),'population'].sum())},
  'residual_potential_point_false_universe':{'rows':len(r),'source_population':targetpop,'known_hold_union_rows':int(r.existing_hold.sum()),'source_physical_settlement_scope_and_coordinate_rows':int(target_base.shape[0])},
  'source_rule_results':{'candidate_rows':len(proposals),'candidate_population':int(proposals.source_population.sum()),'high_mass_candidate_rows_over_2000':len(prop_high),'high_mass_candidate_population_over_2000':int(prop_high.source_population.sum()),'proposal_coordinate':'the raw Tochno source-row point (not GeoNames coordinate); GN is exact-name/ADM1/current-PPL witness only','provider_id_binding_asserted':False,'upstream_lineage_independence_proven':False,'census_date_measurement_claimed':False},
  'excluded_hold_counts':{k:len(v) for k,v in hold_sets.items()},
  'geonames_parse':gn_meta,
  'fixed_sample':{'rows':len(sample),'seed':rng_seed,'source_row_reopened_and_core_fields_verified':int(sample.sample_source_row_reopened_and_core_fields_verified.sum()),'GN_raw_witness_lines_verified':int(sample.sample_geonames_raw_line_hash_and_feature_alias_verified.sum()),'review_labels':sample.sample_independent_review_label.value_counts().to_dict(),'design':'top 20 residual population rows plus risk-stratum quotas and seeded residual fill; descriptive only'},
  'input_sha256':{str(p):sha_file(p) for p in [RESIDUAL,SELECTED,PROVIDER,REGION_SCREEN,GEONAMES_ZIP,ADM1_CODES,BLOCKED_JSON,WIKIDATA_REVIEW_RECEIPT,FEDERAL_ACCEPTED,BASE_ACCEPTED,R4_ACCEPTED]},
  'raw_source_assets':{str(Path('/workspace/settlements-raw')/f):sha_file(Path('/workspace/settlements-raw')/f) for f in sorted(r.source_file.dropna().astype(str).unique())},
  'coordinate_rule':'proper raw source object_level=Населенный пункт, source population scope settlement, additive record, exact unique source OKTMO row, original source coordinate matches selected coordinate within 1 m and both source/GN points inside expected ADM1; GeoNames literal Cyrillic alias exact after NFKC/casefold/ё-to-е and exact source ADM1; only current RU/P PPL/PPLA/PPLA2/PPLA3/PPLA4/PPLA5/PPLC; all exact name/ADM1 hits must be unique and within 1km, or comprise one <=1km near cluster; candidate point remains raw source coordinate.',
  'limits':['No FIAS/legal provider identifier binding is asserted.','GeoNames upstream coordinate lineage is unknown; no independent measurement claim.','GeoNames aliases have no language or validity dates.','No census-date point measurement, historical identity, temporal propagation, boundary comparability, or population comparability is asserted.','GeoNames population is never used.','Known quarantine, frozen city, federal territory, current accepted-point, and Wikidata hard point-choice holds are excluded.','Historical point routes may overlap staged proposals; overlap is flagged for parent integration.'],
  'outputs':{}
 }
 for name in ['residual_point_rule_ledger.csv','staged_source_point_candidates.csv','fixed_100_review_sample.csv','risk_strata.csv','geonames_readme.txt']:
  p=OUT/name;summary['outputs'][name]={'sha256':sha_file(p),'bytes':p.stat().st_size}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'candidate_pool':summary['candidate_pool_after_exact_hold_and_physical_scope_gates'],'results':summary['source_rule_results'],'highmass_universe':{'rows':int(len(high)),'population':int(high.source_population.sum())},'highmass_candidate':{'rows':len(prop_high),'population':int(prop_high.source_population.sum())},'sample':summary['fixed_sample'],'GN':gn_meta,'output_hashes':{k:v['sha256'] for k,v in summary['outputs'].items()}},ensure_ascii=False,indent=2))

def main_gn_point_family():
 """Stage direct current GeoNames points under whole-region/name/code gates."""
 out=OUT/'gn_point_recovery_v6'
 if out.exists(): raise FileExistsError(f'Immutable output exists: {out}')
 out.mkdir(parents=True)
 residual=pd.read_parquet(RESIDUAL)
 r=residual.loc[residual.census_year.eq(2021)&~residual.potential_point.fillna(False)].copy()
 selected=pd.read_parquet(SELECTED)
 selected=selected.loc[selected.census_year.eq(2021)].copy()
 selected['source_record_id']=selected.source_record_id.astype(str)
 r['source_record_id']=r.source_record_id.astype(str)
 provider=pd.read_parquet(PROVIDER,columns=['source_record_id','source_is_physical_np'])
 provider['source_record_id']=provider.source_record_id.astype(str)
 selected=selected.merge(provider,on='source_record_id',how='left',validate='one_to_one')
 r=r.merge(selected[['source_record_id','settlement_name','settlement_type','region_raw','region_norm','population','oktmo','source_file','source_locator','source_sha256','latitude','longitude','population_scope','is_additive_settlement_record','name_norm','type_norm','source_name_raw','source_native_id','source_is_physical_np']],on='source_record_id',how='left',validate='one_to_one',suffixes=('','_sel'))
 holds=load_holds(); held=set().union(*holds.values())
 r['hold_names']=r.source_record_id.map(lambda sid:json.dumps([k for k,v in holds.items() if sid in v],separators=(',',':')))
 r['existing_hold']=r.source_record_id.isin(held)
 # Whole 2021 selected universe uniqueness, before residual scoping.
 physical=selected.loc[selected.source_is_physical_np.fillna(False)&selected.population_scope.eq('settlement')&selected.is_additive_settlement_record.fillna(False)].copy()
 physical['name_type_region_n']=physical.groupby(['name_norm','type_norm','region_norm'],dropna=False).source_record_id.transform('size')
 physical['native_code_n']=physical.groupby('oktmo',dropna=False).source_record_id.transform('size')
 u=physical.set_index('source_record_id')[['name_type_region_n','native_code_n']]
 r=r.join(u,on='source_record_id',rsuffix='_whole2021')
 raw_cache={};raw_meta={};source_file_hashes={}
 for x in r.itertuples(index=False):
  path=Path('/workspace/settlements-raw')/str(x.source_file)
  sid=x.source_record_id
  if not path.exists():raw_meta[sid]={'status':'source_asset_missing'};continue
  if path not in raw_cache:raw_cache[path]=pd.read_parquet(path,columns=SOURCE_FIELDS)
  try:n=int(str(sid).rsplit(':',1)[-1].replace('parquet:',''))
  except Exception:n=0
  if n<1 or n>len(raw_cache[path]):raw_meta[sid]={'status':'source_locator_invalid'};continue
  raw=raw_cache[path].iloc[n-1]; payload=row_payload(raw); ps=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))
  if path not in source_file_hashes:source_file_hashes[path]=sha_file(path)
  raw_meta[sid]={'status':'verified' if norm(raw.object_level)=='населенный пункт' and norm(raw.oktmo)==norm(x.oktmo) and norm(raw.settlement)==norm(x.source_name_raw) and norm(raw.region)==norm(x.region_raw) and pd.notna(raw.population) and float(raw.population)==float(x.population) else 'source_row_contradiction',
    'source_file_sha256':source_file_hashes[path],'source_file':str(path),'row_1based':n,'payload_sha256':sha_bytes(ps.encode()),'payload_json':ps,'payload':payload,
    'raw_name':raw.settlement,'raw_type':raw.settlement_type_full_dadata,'raw_type_short':raw.settlement_type_dadata,'raw_object_level':raw.object_level,'raw_oktmo':raw.oktmo,'raw_region':raw.region,'raw_population':raw.population,
    'raw_latitude':raw.latitude_dadata,'raw_longitude':raw.longitude_dadata,
    'checks':{'object_level_is_NP':norm(raw.object_level)=='населенный пункт','native_code_exact':norm(raw.oktmo)==norm(x.oktmo),'raw_name_equals_source_name_raw':norm(raw.settlement)==norm(x.source_name_raw),'raw_region_exact':norm(raw.region)==norm(x.region_raw),'population_exact':pd.notna(raw.population) and float(raw.population)==float(x.population)}}
 # Literal whole-region GN primary-name/alias map. Keep all distinct place IDs.
 expected=set(r.region_norm.dropna().astype(str)); all_names={(norm(x.settlement_name),str(x.region_norm)) for x in physical.itertuples(index=False) if norm(x.settlement_name) and pd.notna(x.region_norm)}
 p_rows,region_map,adm1_map,readme,gn_body,gn_meta=load_gn_source(all_names,expected)
 gn_by=defaultdict(list)
 for h in p_rows:gn_by[(h['matched_name_norm'],h['matched_region_norm'])].append(h)
 from research_rebuild.mass_linkage.coordinate_validation_packet import _load_region_geometries,_point_inside_source_region
 geometries,region_codes=_load_region_geometries()
 region_frame=pd.read_parquet(REGION_SCREEN,columns=['source_record_id','geometry_iso']);geom_by=region_frame.set_index('source_record_id').geometry_iso.to_dict()
 # Historic typed/raw-code corroboration is a separate source family and is used only for alias-only or long-distance cases.
 hist_path=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet')
 hist=pd.read_parquet(hist_path)
 hist['oktmo_key']=hist.oktmo_2011_raw.fillna(hist.oktmo_raw_text).astype(str).str.strip()
 hist_by=defaultdict(list)
 for h in hist.itertuples(index=False):
  if bool(h.is_deleted) or str(h.is_settlement_raw).casefold()!='t':continue
  code=str(h.oktmo_key).strip(); keyname=norm(h.name); typ=norm(h.status)
  if code and keyname:hist_by[code].append({'oktmo':code,'name':h.name,'status':h.status,'name_key':keyname,'type_key':typ,'lat':h.latitude_from_lat,'lon':h.longitude_from_long,'line':h.source_line_1based,'byte_offset':h.record_byte_offset_0based,'sha2009':h.source_sha256_2009,'sha2011':h.source_sha256_2011,'region':h.historical_point_modern_region,'record':h.record_number_1based})
 result=[]
 for x in r.itertuples(index=False):
  sid=x.source_record_id; code=str(x.oktmo) if pd.notna(x.oktmo) else ''; key=(norm(x.settlement_name),str(x.region_norm)); hs=gn_by.get(key,[])
  raw=raw_meta.get(sid,{}); selected_source=(float(raw['raw_latitude']),float(raw['raw_longitude'])) if raw.get('raw_latitude') is not None and pd.notna(raw.get('raw_latitude')) and raw.get('raw_longitude') is not None and pd.notna(raw.get('raw_longitude')) else None
  geo=geom_by.get(sid); hits=[]
  for g in hs:
   try:pt=(float(g['latitude']),float(g['longitude']))
   except Exception:continue
   if not (-90<=pt[0]<=90 and -180<=pt[1]<=180):continue
   adm=g['admin1']; admok=region_map.get(adm,{}).get('region_norm')==key[1] and adm in adm1_map
   inside=bool(_point_inside_source_region(pt[0],pt[1],geo,geometries,region_codes)[0])
   prim=norm(g['name'])==key[0]
   dist=haversine_km(selected_source,pt) if selected_source else None
   hist_rows=[]
   for h in hist_by.get(code,[]):
    hn=norm(h['name']); ht=h['type_key']; typ=norm(x.settlement_type)
    type_ok=ht==typ or (typ=='город' and ht in ('город','г.'))
    region_ok=not h['region'] or region_key(h['region'])==region_key(x.region_raw)
    try:hd=haversine_km((float(h['lat']),float(h['lon'])),pt)
    except Exception:hd=None
    if hn==key[0] and type_ok and region_ok and hd is not None and hd<=1:
     hist_rows.append({**h,'distance_to_gn_km':hd,'typed_name_code_region_match':True})
   hits.append({'geonameid':g['geonameid'],'geonames_name_raw':g['name'],'matched_literal_alias':g['matched_alias'],'matched_alias_is_primary_name':prim,'feature_code':g['feature_code'],'latitude':pt[0],'longitude':pt[1],'admin1_code':adm,'admin1_alias':region_map.get(adm,{}).get('alias'),'admin1_name':adm1_map.get(adm,{}).get('name'),'admin1_region_matches':admok,'point_inside_source_expected_adm1':inside,'source_point_distance_km_diagnostic':dist,'gn_line_1based':g['source_line_1based'],'gn_byte_start':g['ru_txt_byte_offset_start'],'gn_byte_end':g['ru_txt_byte_offset_end'],'gn_line_sha256':g['ru_txt_line_sha256'],'historical_typed_code_matches_within_1km':hist_rows})
  g_ids={h['geonameid'] for h in hits}; unique_whole_gn=len(g_ids)==1
  target_name_type_n=int(x.name_type_region_n) if pd.notna(x.name_type_region_n) else 0
  code_n=int(x.native_code_n) if pd.notna(x.native_code_n) else 0
  validhits=[h for h in hits if h['admin1_region_matches'] and h['point_inside_source_expected_adm1']]
  # A PPL row can match multiple literal aliases after normalization; count/place
  # uniqueness is by QID, and one deterministic row witness represents that QID.
  by_qid={}
  for h in validhits:
   old=by_qid.get(h['geonameid'])
   if old is None or (h['matched_alias_is_primary_name'],h['matched_literal_alias'])>(old['matched_alias_is_primary_name'],old['matched_literal_alias']):by_qid[h['geonameid']]=h
  validhits=list(by_qid.values())
  locraw=raw.get('status')=='verified'
  # A literal alias is supported by whole-region uniqueness plus exact typed-source,
  # unique-native-code and ADM1 context; historical raw-code matches strengthen only high-risk cases.
  hist_supported=any(h['historical_typed_code_matches_within_1km'] for h in validhits)
  primary=any(h['matched_alias_is_primary_name'] for h in validhits)
  rowtyped=source_typed_label_matches(raw.get('raw_name'),x.settlement_type,x.settlement_name)
  broad=unique_whole_gn and len(validhits)==len(g_ids)==1 and target_name_type_n==1 and code_n==1 and locraw and bool(x.source_is_physical_np) and rowtyped and bool(x.is_additive_settlement_record) and x.population_scope=='settlement' and not bool(x.existing_hold)
  d=validhits[0]['source_point_distance_km_diagnostic'] if len(validhits)==1 else None
  if bool(x.existing_hold):status='preserve_known_hold'
  elif not broad:status='hold_or_unresolved_failed_whole_region_identity_type_code_or_point_gate'
  elif d is not None and d>5 and not hist_supported:status='hold_GN_point_over_5km_source_disagreement_without_historical_support'
  elif d is not None and d>5:status='candidate_direct_GN_point_over_5km_with_typed_historical_support_high_risk'
  elif d is None:status='candidate_direct_GN_point_source_coordinate_missing'
  elif d<=5:status='candidate_direct_GN_point_source_distance_le_5km_diagnostic'
  else:status='candidate_direct_GN_point'
  candidate=status.startswith('candidate_direct_GN_point')
  selected_hit=validhits[0] if len(validhits)==1 else None
  result.append({'source_record_id':sid,'source_population':x.population,'source_name_raw':x.source_name_raw,'target_name':x.settlement_name,'target_type':x.settlement_type,'target_region':x.region_raw,'source_oktmo_raw':x.oktmo,'source_physical_np_screen':bool(x.source_is_physical_np),'source_population_scope':x.population_scope,'source_additive':bool(x.is_additive_settlement_record),'whole_2021_source_name_type_region_count':target_name_type_n,'whole_2021_source_native_code_count':code_n,'source_raw_row_status':raw.get('status'),'source_raw_typed_label_matches_selected_type_name':rowtyped,'source_raw_row_locator':f"{raw.get('source_file')}#row1based={raw.get('row_1based')}" if raw else None,'source_raw_file_sha256':raw.get('source_file_sha256'),'source_raw_payload_sha256':raw.get('payload_sha256'),'source_raw_checks_json':json.dumps(raw.get('checks',{}),separators=(',',':')),'source_raw_type':raw.get('raw_type'),'source_point_latitude':raw.get('raw_latitude'),'source_point_longitude':raw.get('raw_longitude'),'gn_whole_region_exact_alias_distinct_qid_count':len(g_ids),'gn_current_physical_ppl_rows_json':json.dumps(hits,ensure_ascii=False,separators=(',',':')),'gn_admin_and_point_valid_count':len(validhits),'primary_literal_name_match':primary,'historical_typed_code_name_region_match':hist_supported,'source_point_distance_km_diagnostic':d,'rule_status':status,'candidate_only':candidate,'proposed_latitude':selected_hit['latitude'] if candidate and selected_hit else None,'proposed_longitude':selected_hit['longitude'] if candidate and selected_hit else None,'proposed_coordinate_source':'literal current RU GeoNames physical PPL record' if candidate else None,'geonameid_for_internal_raw_locator_only':selected_hit['geonameid'] if candidate and selected_hit else None,'provider_id_binding_asserted':False,'GN_upstream_coordinate_independence_proven':False,'GN_alias_validity_date_proven':False,'census_date_point_measurement_proven':False,'coordinate_precision_upgraded':False,'existing_hold':bool(x.existing_hold),'hold_memberships_json':x.hold_names,'population_used_for_point_choice':False})
 ledger=pd.DataFrame(result)
 # Fixed high-mass/risk-labelled sample, deterministic and descriptive only.
 ledger['population_band']=pd.cut(pd.to_numeric(ledger.source_population,errors='coerce'),[-.001,499,1999,9999,float('inf')],labels=['<500','500-1999','2000-9999','10000+']).astype(str)
 ids=[];ids+=ledger.sort_values(['source_population','source_record_id'],ascending=[False,True]).head(30).source_record_id.tolist()
 for status,q in [('candidate_direct_GN_point_source_distance_le_5km_diagnostic',25),('candidate_direct_GN_point_source_coordinate_missing',15),('candidate_direct_GN_point_over_5km_with_typed_historical_support_high_risk',10),('hold_alias_only_without_typed_historical_corroboration',10),('hold_or_unresolved_failed_whole_region_identity_type_code_or_point_gate',10)]:
  pool=ledger[(ledger.rule_status==status)&~ledger.source_record_id.isin(ids)].sort_values('source_record_id')
  if len(pool)>q:pool=pool.sample(q,random_state=20261005+len(ids))
  ids+=pool.source_record_id.tolist()
 if len(ids)<100:
  pool=ledger[~ledger.source_record_id.isin(ids)].sort_values('source_record_id')
  need=min(100-len(ids),len(pool));ids+=pool.sample(n=need,random_state=20261005).source_record_id.tolist()
 sample=ledger[ledger.source_record_id.isin(ids)].copy().sort_values(['source_population','source_record_id'],ascending=[False,True]).head(100)
 sample_gn_checked=[];sample_src_checked=[];sample_labels=[];sample_notes=[]
 for row in sample.itertuples(index=False):
  rawhits=json.loads(row.gn_current_physical_ppl_rows_json) if isinstance(row.gn_current_physical_ppl_rows_json,str) else []
  gn_ok=True
  for h in rawhits:
   a=int(h['gn_byte_start']);b=int(h['gn_byte_end']);line=gn_body[a:b];cells=line.decode('utf-8').rstrip('\r\n').split('\t')
   if len(cells)!=len(GN_FIELDS):gn_ok=False;continue
   rawgn=dict(zip(GN_FIELDS,cells))
   gn_ok &= sha_bytes(line)==h['gn_line_sha256'] and rawgn['geonameid']==str(h['geonameid']) and rawgn['country_code']=='RU' and rawgn['feature_class']=='P' and rawgn['feature_code'] in PHYSICAL_CODES and h['matched_literal_alias'] in aliases(rawgn)
   gn_ok &= rawgn['admin1']==str(h['admin1_code']) and rawgn['name']==h['geonames_name_raw'] and abs(float(rawgn['latitude'])-float(h['latitude']))<1e-10 and abs(float(rawgn['longitude'])-float(h['longitude']))<1e-10
   gn_ok &= h['admin1_region_matches'] and region_map.get(rawgn['admin1'],{}).get('region_norm')==region_key(row.target_region)
  sample_gn_checked.append(gn_ok and bool(rawhits))
  source_meta=raw_meta.get(row.source_record_id,{})
  source_ok=False
  if source_meta.get('payload_json') and source_meta.get('source_file') and source_meta.get('row_1based'):
   frame=raw_cache[Path(source_meta['source_file'])]; raw_sample=row_payload(frame.iloc[int(source_meta['row_1based'])-1])
   source_ok=(sha_bytes(json.dumps(raw_sample,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())==source_meta.get('payload_sha256') and source_meta.get('status')=='verified' and bool(row.source_raw_typed_label_matches_selected_type_name))
  sample_src_checked.append(source_ok)
  if row.existing_hold:label='preserve_existing_hold';note='known/frozen hold retained'
  elif not source_ok:label='genuine_source_row_contradiction';note='raw source row reopen/payload or exact typed locality label failed'
  elif rawhits and not gn_ok:label='genuine_GeoNames_raw_line_contradiction';note='raw GN bytes/hash/feature/alias failed'
  elif row.candidate_only and gn_ok:label='verified_candidate_rule_inputs; GN upstream independence unknown';note='raw source and GN witnesses re-opened; source-to-GN separation/measurement origin unknown'
  elif row.rule_status.startswith('hold_GN_point_over_5km'):label='genuine_source_GN_coordinate_conflict_hold';note='>5km source-point disagreement kept held absent typed historical same-code support'
  elif len(rawhits)>0:label='not_independently_resolved';note='candidate rule not passed; preserved ambiguity or failed whole-region/type/context gate'
  else:label='not_independently_resolved';note='no literal current RU PPL witness'
  sample_labels.append(label);sample_notes.append(note)
 sample['sample_source_row_payload_reopened_and_typed']=sample_src_checked;sample['sample_GN_raw_lines_alias_features_coords_and_ADM1_verified']=sample_gn_checked;sample['sample_review_label']=sample_labels;sample['sample_review_note']=sample_notes
 ledger.to_csv(out/'direct_gn_point_rule_ledger.csv',index=False,encoding='utf-8')
 ledger[ledger.candidate_only].to_csv(out/'staged_direct_gn_point_candidates.csv',index=False,encoding='utf-8')
 sample.to_csv(out/'fixed_100_direct_gn_point_review_sample.csv',index=False,encoding='utf-8')
 risk=ledger.groupby(['rule_status','population_band'],dropna=False).agg(rows=('source_record_id','size'),source_population=('source_population','sum')).reset_index();risk.to_csv(out/'risk_strata.csv',index=False,encoding='utf-8')
 (out/'geonames_readme.txt').write_bytes(readme)
 high=ledger[pd.to_numeric(ledger.source_population,errors='coerce').gt(2000)];cand=ledger[ledger.candidate_only]; ch=cand[pd.to_numeric(cand.source_population,errors='coerce').gt(2000)]
 files=['direct_gn_point_rule_ledger.csv','staged_direct_gn_point_candidates.csv','fixed_100_direct_gn_point_review_sample.csv','risk_strata.csv','geonames_readme.txt']
 summary={'status':'candidate_only_no_admissions','scope':'2021 residual potential_point=False; direct literal current GeoNames point candidate family','whole_2021_uniqueness':'selected current source physical NP rows; exact normalized name+type+region unique; exact source native OKTMO unique','GN_uniqueness':'literal current RU/P PPL-family primary/alternate alias distinct place IDs counted across whole ADM1 region; no proximity uniqueness restriction','coordinate_rule':'actual GN PPL point in expected ADM1; source-point distance diagnostic only; <=5km broad candidate; >5km requires exact typed/name/code/region historical source point within 1km. Unique raw typed-source label, unique source name/type/region+native code and unique GN name across the ADM1 supply additional context for literal alias matches; no fuzzy aliases.','source_type_rule':'reopened original raw Tochno NP object row; exact native code/name/region/population and exact known typed-prefix plus locality-name match in raw source label; target additive settlement population scope','upstream_lineage_independence_proven':False,'provider_id_binding_asserted':False,'potential_population':{'all_candidates':{'rows':len(cand),'source_population':int(cand.source_population.sum())},'over_2000':{'rows':len(ch),'source_population':int(ch.source_population.sum())},'high_mass_universe_over_2000':{'rows':len(high),'source_population':int(high.source_population.sum())}},'candidate_status_counts':ledger.rule_status.value_counts().to_dict(),'GN_parse':gn_meta,'fixed_review_sample':{'rows':len(sample),'design':'top 30 source-population rows plus seeded rule-risk fills; descriptive, not probability estimate','labels':pd.Series(sample_labels).value_counts().to_dict(),'source_rows_reopened_typed_and_verified':sum(sample_src_checked),'raw_GN_rows_alias_features_coords_and_ADM1_verified':sum(sample_gn_checked)},'input_hashes':{str(p):sha_file(p) for p in [RESIDUAL,SELECTED,PROVIDER,REGION_SCREEN,GEONAMES_ZIP,ADM1_CODES,BLOCKED_JSON,WIKIDATA_REVIEW_RECEIPT,FEDERAL_ACCEPTED,BASE_ACCEPTED,R4_ACCEPTED,hist_path]},'raw_source_assets':{str(Path('/workspace/settlements-raw')/f):sha_file(Path('/workspace/settlements-raw')/f) for f in sorted(r.source_file.dropna().astype(str).unique())},'outputs':{f:{'sha256':sha_file(out/f),'bytes':(out/f).stat().st_size} for f in files}}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'candidate_count':len(cand),'candidate_population':int(cand.source_population.sum()),'over_2000_rows':len(ch),'over_2000_population':int(ch.source_population.sum()),'highmass_pool_rows':len(high),'highmass_pool_population':int(high.source_population.sum()),'status_counts':summary['candidate_status_counts'],'outputs':summary['outputs']},ensure_ascii=False,indent=2))

if __name__=='__main__':
 if '--gn-point-family' in sys.argv: main_gn_point_family()
 else: main()
