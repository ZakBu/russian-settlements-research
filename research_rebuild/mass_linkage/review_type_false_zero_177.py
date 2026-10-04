#!/usr/bin/env python3
"""Independent, read-only review of 177 type-helper false-zero point candidates."""
from __future__ import annotations
import csv, hashlib, json, math, re, sys, unicodedata, zipfile
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd
import duckdb

W=Path('/workspace')
ROOT=W/'settlements-work/continuation_20261004'
A=ROOT/'root/point_gap_spatial_diagnostic_after_afipsky/helper_type_false_zero_audit'
OUT=ROOT/'independent_review/type_false_zero_177_review'
TESTS=Path(__file__).parent/'tests/test_review_type_false_zero_177.py'
READY=A/'reviewed_ready_177_type_context_point_candidates.csv'
ORIG=A/'type_only_false_zero_review_candidates.csv'
SELECTED=W/'settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet'
RAW=W/'settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
GN=W/'settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip'
ADM=W/'settlements-raw/data/raw/coordinate_candidates/geonames_admin1CodesASCII_20260907.txt'
BLOCK=W/'settlements-work/continuation_20261003/blocked_point_reuse_targets_v1.json'
POINTS=ROOT/'accepted_mass_ninth_reviewed_legacy202/accepted_point_uses.parquet'
GRAPH=ROOT/'accepted_mass_ninth_reviewed_legacy202/accepted_identity_edges.parquet'
RES=ROOT/'accepted_mass_ninth_reviewed_legacy202/joint_residual.parquet'
REGION=W/'settlements-work/coordinates/region_screen_v1/region_point_screen.parquet'
SCREEN=A.parent/'screen_receipt.json'
SUPP=A/'type_only_supplement_receipt.json'
READY_RECEIPT=A/'reviewed_ready_177_packet_receipt.json'
PINS={
 'ready_candidates':(READY,'b0ba6640e1eeeb27b28cf85c0b8246791dce832859bcb6e507a78dd7e4b05b8a'),
 'original_supplement_candidates':(ORIG,'51f86ecf785c9f284faff432b5316dca7513aacbd8d64cab6ed0ab590b33d696'),
 'selected':(SELECTED,'4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657'),
 'tochno_raw':(RAW,'86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'),
 'geonames_zip':(GN,'9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4'),
 'geonames_admin1':(ADM,'590651498043f674accda2b7f46d21286cda0e290b02f8561c5005eee9a5448c'),
 'point_blocklist':(BLOCK,'7a715254f965d996541001d08d3422828299f5c300dfae4cbe78b79f9a5b0e70'),
 'current_ninth_points':(POINTS,'264812092d0bc1df17929d945609d6f12f096ab28d085a85bb26dee09cc17d5b'),
 'current_ninth_graph':(GRAPH,'a9fec4648d24afc7345ae23fca9f45058c0962e8fd41d9124deaf01839ef58b6'),
 'current_ninth_residual':(RES,'ac4b3ac18ca189ce73da07a0ceaaa5f0c60270928f0dec624e862fefa6750485'),
 'region_geometry_index':(REGION,'6c27e8c077808421ae6c202ba95ab4f1aeb58ac1b48d054f5208958b76ac765a'),
'original_screen_receipt':(SCREEN,'844d681c9bdc2936557cf120b029380364c35fdd1bde36113f5d4dfb8755d74b'),
 'type_supplement_receipt':(SUPP,'05e7849bb92a727c11384bc9bc07fedfa66ba9d6c90f6fec899e3c855d5a5e34'),
'ready_packet_receipt':(READY_RECEIPT,'34ac600c9257de9d9617cf1f250bf18c2a68ff432aab6ea130000f8741a0cd36'),
}
PHYSICAL={'PPL','PPLA','PPLA2','PPLA3','PPLA4','PPLA5','PPLC'}
RAIL_PREFIXES=('железнодорожная станция ','железнодорожный разъезд ','железнодорожная будка ','железнодорожная казарма ','железнодорожный остановочный пункт ','железнодорожный блокпост ','ж.д. будка ')

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def req(ok,msg):
 if not ok: raise ValueError(msg)
def norm(x):
 if x is None or pd.isna(x): return ''
 return ' '.join(unicodedata.normalize('NFKC',str(x)).replace('ё','е').casefold().split())
def rawstr(x):
 return None if x is None or pd.isna(x) else str(x)
def regkey(x):
 s=norm(x).replace('-',' ').replace('–',' ').replace('—',' ')
 aliases={'рсо':'северная осетия алания','кчр':'карачаево черкесская','кбр':'кабардино балкарская','якутия':'саха якутия','удмуртия':'удмуртская','чувашия':'чувашская','нижегород':'нижегородская','чувашская республика чувашия':'чувашская'}
 s=aliases.get(s,s); s=re.sub(r'^республика\s+','',s)
 s=re.sub(r'\s+(область|обл\.?|край|края|республика|респ\.?|автономный округ|автономная область)$','',s)
 return ' '.join(s.split())
def hav(lat1,lon1,lat2,lon2):
 p1,p2=map(math.radians,(lat1,lat2)); dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
 a=math.sin(dlat/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
 return 6371.0088*2*math.asin(math.sqrt(a))
def publisher_class(obj, selected):
 o,t=norm(obj),norm(selected)
 if not o:return None
 if o==t or o.startswith(t+' '): return ('literal_object_name_type_prefix',o[len(t):].strip())
 if t=='город' and re.match(r'^г\.?\s+',o):return ('literal_publisher_city_abbreviation',re.sub(r'^г\.?\s+','',o).strip())
 if t=='пгт' and o.startswith(('рабочий поселок ','городской поселок ','поселок городского типа ','пгт ')):
  for p in ('рабочий поселок ','городской поселок ','поселок городского типа ','пгт '):
   if o.startswith(p): return ('publisher_urban_settlement_alias',o[len(p):].strip())
 if t=='железнодорожный объект':
  for p in RAIL_PREFIXES:
   if o.startswith(norm(p)): return ('publisher_physical_railway_subtype_under_broad_class',o[len(norm(p)):].strip())
 if t=='выселок' and o.startswith(('выселки ','выселок ')):
  for p in ('выселки ','выселок '):
   if o.startswith(p):return ('publisher_vyselok_name_form',o[len(p):].strip())
 return None
def helper_relation(selected, compact, full):
 s,c,f=norm(selected),norm(compact),norm(full)
 compact_map={'д':'деревня','п':'поселок','с':'село','х':'хутор','высел':'выселок','ст':'станция','ж/д_ст':'железнодорожная станция','ж/д_рзд':'железнодорожный разъезд','рп':'рабочий поселок'}
 c_sem=compact_map.get(c,c); f_sem=f
 if not c and not f:return 'helper_fields_missing_unknown'
 rail_map={'железнодорожная станция':'железнодорожный объект','железнодорожный разъезд':'железнодорожный объект','станция':'железнодорожный объект'}
 s_sem=rail_map.get(s,s)
 if c_sem==s_sem and f_sem in {s,s_sem}:return 'helper_semantically_agrees_after_documented_abbreviation'
 if c_sem==s_sem or f_sem==s or f_sem==s_sem:return 'one_helper_field_agrees_other_differs'
 if s=='пгт' and c_sem=='рабочий поселок' and f_sem=='рабочий поселок':return 'working_settlement_alias_for_pgt'
 if s=='выселок' and c_sem=='выселок' and f_sem.startswith('высел'):return 'vyselok_inflection_alias'
 if s_sem=='железнодорожный объект' and (c_sem in rail_map or f_sem in rail_map):return 'detailed_railway_subtype_of_selected_broad_class'
 return 'helper_conflict_retained_publisher_type_replayed_separately'
def null_equiv(a,b):
 return (pd.isna(a) and (b=='' or pd.isna(b))) or (pd.isna(b) and (a=='' or pd.isna(a))) or str(a)==str(b)
def coord_key(lat,lon):
 return f"{pd.Series([float(lat)]).round(6).iloc[0]}|{pd.Series([float(lon)]).round(6).iloc[0]}"
def admin_code_key(x):
 s=str(x).strip()
 try:
  f=float(s)
  if f.is_integer():return str(int(f))
 except (ValueError,TypeError):pass
 return s
def numeric_id_key(x):
 s=str(x).strip()
 try:
  f=float(s)
  if f.is_integer():return str(int(f))
 except (ValueError,TypeError):pass
 return s
def verify_inputs():
 d={}
 for n,(p,h) in PINS.items():
  req(p.is_file(),f'missing {n}: {p}')
  actual=sha(p); req(actual==h,f'hash mismatch {n}: {actual}'); d[n]=actual
 return d
def main():
 input_hashes=verify_inputs()
 cand=pd.read_csv(READY,dtype=str,keep_default_na=False,engine='python')
 orig=pd.read_csv(ORIG,dtype=str,keep_default_na=False,engine='python')
 req(len(cand)==len(orig)==177 and cand.target_source_record_id.is_unique and orig.target_source_record_id.is_unique,'177 source candidate vector changed')
 req(set(cand.target_source_record_id)==set(orig.target_source_record_id),'ready adapter did not preserve exact source candidate keys')
 req(set(cand.candidate_status)=={'candidate_only_not_admitted'},'source packet already altered/admitted')
 # Re-read selected publisher rows, source raw rows, point ledger and current full-chain residual independently.
 ids=cand.target_source_record_id.tolist(); rownums=[int(x.rsplit(':',1)[1]) for x in ids]
 q=lambda p:"'"+str(p).replace("'","''")+"'"
 con=duckdb.connect(config={'threads':1,'memory_limit':'1GB','preserve_insertion_order':False})
 selected=con.execute(f"SELECT source_record_id,census_year,source_file,source_sheet,source_row,source_native_id,source_name_raw,settlement_name,settlement_type,region_raw,district_raw,population,latitude,longitude,coordinate_source,coordinate_quality,is_additive_settlement_record,population_scope,source_sha256,source_locator,oktmo,okato FROM read_parquet({q(SELECTED)}) WHERE census_year=2021 AND source_record_id IN (SELECT unnest(?))",[ids]).fetchdf()
 # Full selected 2021 native-code and typed name uniqueness vectors are small enough to read with projection.
 selected_all=con.execute(f"SELECT source_record_id,source_native_id,settlement_name,settlement_type,region_raw,latitude,longitude FROM read_parquet({q(SELECTED)}) WHERE census_year=2021").fetchdf()
 point_rows=con.execute(f"SELECT target_source_record_id,target_year,latitude,longitude,coordinate_source,coordinate_provider,point_origin_file,point_origin_sha256,point_origin_locator FROM read_parquet({q(POINTS)}) WHERE target_year IN (2021,'2021.0') AND target_source_record_id IN (SELECT unnest(?))",[ids]).fetchdf()
 full_res=con.execute(f"SELECT source_record_id,census_year,joint_full,population,population_scope,is_additive_settlement_record FROM read_parquet({q(RES)}) WHERE census_year=2021 AND source_record_id IN (SELECT unnest(?))",[ids]).fetchdf()
 con.close()
 req(len(selected)==len(full_res)==177,'not all candidate rows map to current selected/ninth-residual rows')
 s_map=selected.set_index('source_record_id',drop=False);res_map=full_res.set_index('source_record_id',drop=False)
 raw=pd.read_parquet(RAW,columns=['object_level','object_name','settlement','region','oktmo','population','latitude_dadata','longitude_dadata','settlement_type_dadata','settlement_type_full_dadata','settlement_with_type_dadata','settlement_dadata','fias_id_dadata','fias_level_dadata','qc_geo_dadata','qc_dadata'])
 req(len(raw)>=max(rownums),'raw source archive no longer has candidate locators')
 raw_rows=[raw.iloc[n-1] for n in rownums]
 # Selected native code uniqueness, point uniqueness, and type/name/region uniqueness against all 2021 rows.
 sel_code=selected_all.source_native_id.fillna('').astype(str).str.strip().value_counts().to_dict()
 type_name_key=(selected_all.settlement_name.map(norm)+'|'+selected_all.settlement_type.map(norm)+'|'+selected_all.region_raw.map(regkey))
 type_name_count=type_name_key.value_counts().to_dict()
 selected_coordkey=(selected_all.latitude.round(6).astype(str)+'|'+selected_all.longitude.round(6).astype(str))
 coord_count=selected_coordkey.value_counts().to_dict()
 exact_coordkey=(selected_all.latitude.astype(str)+'|'+selected_all.longitude.astype(str))
 exact_coord_count=exact_coordkey.value_counts().to_dict()
 # Raw publisher code uniqueness across the 2021 archive.
 raw_code=raw.oktmo.fillna('').astype(str).str.strip().value_counts().to_dict()
 points_targets=set(point_rows.target_source_record_id.astype(str))
 blocked=set(map(str,json.loads(BLOCK.read_text(encoding='utf-8')).get('blocked_target_source_record_ids',[])))
 # Ninth identity/component graph coverage and path are pinned; no old component IDs are persisted in point seeds.
 req(sha(GRAPH)==PINS['current_ninth_graph'][1],'latest graph changed during review')
 graph_edges=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id'])
 parent={}; rank={}
 def find(x):
  if x not in parent: parent[x]=x;rank[x]=0
  if parent[x]!=x: parent[x]=find(parent[x])
  return parent[x]
 def union(a,b):
  ra,rb=find(a),find(b)
  if ra==rb:return
  if rank[ra]<rank[rb]:ra,rb=rb,ra
  parent[rb]=ra
  if rank[ra]==rank[rb]:rank[ra]+=1
 for a,b in graph_edges.itertuples(index=False,name=None):union(str(a),str(b))
 target_roots={sid:find(sid) for sid in ids}
 selected_years=pd.read_parquet(SELECTED,columns=['source_record_id','census_year'])
 years_by_root=defaultdict(set)
 for sid,year in selected_years.itertuples(index=False,name=None):years_by_root[find(str(sid))].add(int(year))
 fullchain_now={sid:{2002,2010,2021}.issubset(years_by_root.get(root,set())) for sid,root in target_roots.items()}
 # Build GeoNames name/ADM1 index from the pinned full snapshot (not candidate line claims).
 with zipfile.ZipFile(GN) as z:
  gnbytes=z.read('RU.txt'); readme=z.read('readme.txt')
  admin_bytes=ADM.read_bytes()
 lines=gnbytes.splitlines(keepends=True); offsets=[]; offset=0
 gnrows=[]; adm1={}; alias_ix=defaultdict(list)
 # Candidate alias key set bounds the in-memory index to matching possible names.
 candidate_keys=set()
 for r in cand.itertuples(index=False):
  code=admin_code_key(r.expected_admin1_code)
  candidate_keys.add((code,norm(r.settlement_name)))
  if code.isdigit():candidate_keys.add((code.zfill(2),norm(r.settlement_name)))
 for line_no,line in enumerate(lines,1):
  offsets.append(offset); offset+=len(line)
  c=line.decode('utf-8').rstrip('\r\n').split('\t')
  if len(c)!=19:continue
  if c[6]=='A' and c[7]=='ADM1' and c[8]=='RU':
   adm1[c[10]]={'name':c[1],'asciiname':c[2],'aliases':c[3],'geonameid':c[0],'line':line_no,'sha':hashlib.sha256(line).hexdigest()}
  if c[6]!='P' or c[7] not in PHYSICAL or c[8]!='RU':continue
  try: lat,lon=float(c[4]),float(c[5])
  except (ValueError,TypeError):continue
  row={'geonameid':c[0],'name':c[1],'asciiname':c[2],'aliases':c[3],'lat':lat,'lon':lon,'feature':c[7],'adm1':c[10],'line':line_no,'start':offset-len(line),'end':offset,'sha':hashlib.sha256(line).hexdigest()}
  for alias in {norm(x) for x in [c[1],*c[3].split(',')] if norm(x)}:
   key=(c[10],alias)
   if key in candidate_keys:alias_ix[key].append(row)
 # ADM1 code crosswalk: GeoNames ADM1 aliases and supplied ASCII code file.
 admcode_map=defaultdict(set)
 ac={}
 for i,line in enumerate(admin_bytes.splitlines(keepends=True),1):
  c=line.decode('utf-8').rstrip('\r\n').split('\t')
  if len(c)==4 and c[0].startswith('RU.'):
   code=c[0].split('.',1)[1]; ac[code]=c
 for code,a in adm1.items():
  m=ac.get(code)
  if not m or m[0]!='RU.'+code or m[3]!=a['geonameid']:continue
  for alias in [a['name'],*a['aliases'].split(',')]:
   if alias.strip():admcode_map[regkey(alias)].add(code)
 # Spatial polygon loader is read-only; validate both provider point and GeoNames witness per candidate.
 sys.path.insert(0,'/workspace/russian-settlements-research')
 from research_rebuild.mass_linkage.coordinate_validation_packet import _load_region_geometries,_point_inside_source_region
 geoms,region_iso=_load_region_geometries()
 # Current region geometry map is pinned via exact source file hash and existing screen artifact.
 region_map=con.execute(f"SELECT source_record_id,geometry_iso FROM read_parquet({q(REGION)}) WHERE source_record_id IN (SELECT unnest(?))",[ids]).fetchdf() if False else None
 # use pandas projection rather than keeping a DuckDB handle.
 region_rows=pd.read_parquet(REGION,columns=['source_record_id','geometry_iso'])
 region_map=dict(zip(region_rows.source_record_id.astype(str),region_rows.geometry_iso.astype(str)))
 blocklist_raw=json.loads(BLOCK.read_text(encoding='utf-8'))
 out=[]; sample_candidates=[]
 for idx,(r,rr) in enumerate(zip(cand.to_dict('records'),raw_rows)):
  sid=str(r['target_source_record_id']); s=s_map.loc[sid]; current_res=res_map.loc[sid]
  pubtype=publisher_class(rr.get('object_name'),s.settlement_type)
  category=pubtype[0] if pubtype else 'unsupported_publisher_type'
  suffix=pubtype[1] if pubtype else ''
  # Raw 2021 publisher/source row and selected native settlement row are replayed separately from helper fields.
  rawrow_exact=(norm(rr.object_level)=='населенный пункт' and norm(rr.settlement)==norm(s.source_name_raw)==norm(r['raw_settlement'])
    and norm(s.settlement_name)==norm(r['settlement_name'])
    and norm(rr.region)==norm(s.region_raw)==norm(r['region_raw'])
    and str(rr.oktmo).strip()==str(s.oktmo).strip()==str(r['source_native_oktmo_raw']).strip()
    and float(rr.population)==float(s.population)==float(r['population'])
    and float(rr.latitude_dadata)==float(s.latitude) and float(rr.longitude_dadata)==float(s.longitude)
    and float(rr.latitude_dadata)==float(r['source_raw_latitude']) and float(rr.longitude_dadata)==float(r['source_raw_longitude']))
  code=str(s.oktmo).strip()
  code_unique=bool(code) and sel_code.get(code,0)==1 and raw_code.get(code,0)==1
  namekey=norm(s.settlement_name)+'|'+norm(s.settlement_type)+'|'+regkey(s.region_raw)
  name_unique=type_name_count.get(namekey,0)==1
  ck=coord_key(s.latitude,s.longitude)
  exact_ck=f'{float(s.latitude)}|{float(s.longitude)}'
  point_unique=exact_coord_count.get(exact_ck,0)==1
  source_additive=bool(s.is_additive_settlement_record) and norm(s.population_scope)=='settlement'
  # Type prefix/specific subtype must be paired with the same literal place name in object_name.
  suffix_same_place=bool(suffix) and norm(suffix)==norm(s.settlement_name)
  if category=='literal_object_name_type_prefix' and norm(rr.object_name).startswith(norm(s.settlement_type)+' '):
   suffix_norm=norm(norm(rr.object_name)[len(norm(s.settlement_type))+1:])
   if norm(s.settlement_type)=='пгт': suffix_norm=re.sub(r'\s+рп$','',suffix_norm)
   suffix_same_place=suffix_norm==norm(s.settlement_name)
  if category=='literal_publisher_city_abbreviation': suffix_same_place=norm(suffix)==norm(s.settlement_name)
  if category=='publisher_physical_railway_subtype_under_broad_class': suffix_same_place=norm(suffix)==norm(s.settlement_name)
  if category=='publisher_urban_settlement_alias': suffix_same_place=norm(suffix)==norm(s.settlement_name)
  if category=='publisher_vyselok_name_form': suffix_same_place=norm(suffix)==norm(s.settlement_name)
  # Helper fields remain separate, raw and full are not collapsed to one interpretation.
  helper_raw_same=null_equiv(rr.settlement_type_dadata,r['source_helper_type_raw_conflict_retained'])
  helper_full_same=null_equiv(rr.settlement_type_full_dadata,r['source_helper_type_full_raw_conflict_retained'])
  helper_status=helper_relation(s.settlement_type,rr.settlement_type_dadata,rr.settlement_type_full_dadata)
  # Re-resolve expected ADM1 and exact normalized physical GeoNames candidates.
  expected_codes=sorted(admcode_map.get(regkey(s.region_raw),set()))
  expected_code=expected_codes[0] if len(expected_codes)==1 else ''
  candidate_admin=int(float(r['expected_admin1_code'])) if str(r['expected_admin1_code']).strip() else -1
  candidate_witness_admin=int(float(r['geonames_admin1_code'])) if str(r['geonames_admin1_code']).strip() else -2
  adm1_matches=(len(expected_codes)==1 and int(expected_code)==candidate_admin and candidate_witness_admin==int(expected_code))
  raw_lat,raw_lon=float(rr.latitude_dadata),float(rr.longitude_dadata)
  possible=alias_ix.get((expected_code,norm(s.settlement_name)),[]) if expected_code else []
  near=[]
  for g in possible:
   dist=hav(raw_lat,raw_lon,g['lat'],g['lon'])
   if dist<=1.0:near.append((dist,g))
  near_ids={g['geonameid'] for _,g in near}; near_coords={(round(g['lat'],6),round(g['lon'],6)) for _,g in near}
  gn_unique=len(near_ids)==1 and len(near_coords)==1 and len(near)>0
  chosen=min(near,key=lambda x:x[0])[1] if gn_unique else None
  line_match=bool(chosen and chosen['geonameid']==numeric_id_key(r['geonames_witness_geonameid']) and chosen['line']==int(float(r['geonames_ru_line_1based']))
    and chosen['start']==int(float(r['geonames_ru_byte_start_0based'])) and chosen['end']==int(float(r['geonames_ru_byte_end_0based']))
    and chosen['sha']==str(r['geonames_ru_line_sha256']) and chosen['feature']==str(r['geonames_feature_code'])
    and chosen['adm1']==expected_code
    and norm(s.settlement_name) in {norm(x) for x in [chosen['name'],*chosen['aliases'].split(',')]}
    and abs(min(x[0] for x in near)-float(r['geonames_distance_km']))<1e-8)
  iso=str(r['expected_region_geometry_iso'])
  src_inside=False;gn_inside=False
  if iso and chosen:
   src_inside=bool(_point_inside_source_region(raw_lat,raw_lon,iso,geoms,region_iso)[0])
   gn_inside=bool(_point_inside_source_region(chosen['lat'],chosen['lon'],iso,geoms,region_iso)[0])
  latest_point_absent=sid not in points_targets
  unblocked=sid not in blocked
  full_chain=bool(fullchain_now.get(sid,False))
  gates={
   'source_raw_atomic_row_exact':bool(rawrow_exact),
   'selected_native_OKTMO_unique_in_selected_and_raw_archive':bool(code_unique),
   'selected_name_type_region_unique':bool(name_unique),
   'additive_settlement_grain':bool(source_additive),
   'literal_publisher_type_context_matches_selected_class':category!='unsupported_publisher_type' and suffix_same_place,
   'raw_helper_compact_field_preserved':helper_raw_same,
   'raw_helper_full_field_preserved':helper_full_same,
   'source_point_not_shared_by_other_current_rows':bool(point_unique),
   'exact_GeoNames_physical_name_ADM1_witness_unique_within_1km':bool(gn_unique),
   'GeoNames_witness_line_offsets_hash_feature_and_alias_replayed':bool(line_match),
   'publisher_coordinate_inside_expected_region_geometry':bool(src_inside),
   'GeoNames_coordinate_inside_expected_region_geometry':bool(gn_inside),
   'expected_GeoNames_ADM1_resolves_uniquely_from_publisher_region':bool(adm1_matches),
   'not_already_in_current_ninth_point_ledger':bool(latest_point_absent),
   'not_on_frozen_global_point_blocklist':bool(unblocked),
   'current_2021_component_still_full_chain_in_ninth_snapshot':full_chain,
  }
  holds=[k for k,v in gates.items() if not v]
  # A point candidate is eligible only as a current point seed; never a provider/QID/native historical binding.
  eligible=not holds
  pair={**{k:r.get(k,'') for k in ['target_source_record_id','target_year','population','settlement_name','settlement_type','region_raw','source_native_oktmo_raw','source_raw_latitude','source_raw_longitude','source_coordinate_source','source_coordinate_quality','geonames_witness_geonameid','geonames_witness_raw_name','geonames_feature_code','geonames_distance_km']},
        'publisher_type_evidence_independent':category,'publisher_type_label_suffix':suffix,
        'helper_type_compact_raw':rawstr(rr.settlement_type_dadata),'helper_type_full_raw':rawstr(rr.settlement_type_full_dadata),
        'helper_field_interpretation':helper_status,'helper_raw_preserved':rawstr(rr.settlement_type_dadata),'helper_full_preserved':rawstr(rr.settlement_type_full_dadata),
        'selected_native_code_raw_literal':str(s.oktmo),'raw_publisher_native_code_literal':str(rr.oktmo),
        'raw_object_level':rawstr(rr.object_level),'raw_object_name':rawstr(rr.object_name),'raw_publisher_settlement':rawstr(rr.settlement),'raw_publisher_region':rawstr(rr.region),
        'raw_Dadata_coordinates_latitude':raw_lat,'raw_Dadata_coordinates_longitude':raw_lon,'raw_QC_geo':rawstr(rr.qc_geo_dadata),'raw_QC':rawstr(rr.qc_dadata),
        'selected_source_file':str(s.source_file),'selected_source_sheet':rawstr(s.source_sheet),'selected_source_row':rawstr(s.source_row),
        'selected_source_sha256':rawstr(s.source_sha256),'selected_source_locator':rawstr(s.source_locator),
        'point_origin_file':str(RAW),'point_origin_sha256':PINS['tochno_raw'][1],
        'point_origin_locator':f"parquet_row_1based={rownums[idx]};fields=object_level,object_name,settlement,region,oktmo,population,latitude_dadata,longitude_dadata",
        'source_file_sha256':str(r['selected_source_sha256']),'source_row_locator':str(r['selected_source_locator']),
        'screen_expected_admin1_code_raw':str(r['expected_admin1_code']),'independent_resolved_admin1_code':expected_code,
        'original_screen_coordinate_duplicate_count_raw':str(r.get('raw_source_coordinate_exact_duplicate_current_rows','')),
        'original_screen_gate_flags_json':json.dumps({k:str(v).strip().lower()=='true' for k,v in r.items() if k.startswith('screen_gate_')},sort_keys=True),
        'screen_coordinate_lookup_zero_but_full_precision_coordinate_unique':str(r.get('raw_source_coordinate_exact_duplicate_current_rows',''))=='0' and point_unique,
        'GeoNames_file_sha256':PINS['geonames_zip'][1],'GeoNames_line_1based':chosen['line'] if chosen else None,'GeoNames_byte_start_0based':chosen['start'] if chosen else None,'GeoNames_byte_end_0based':chosen['end'] if chosen else None,'GeoNames_line_sha256':chosen['sha'] if chosen else None,
        'GeoNames_raw_name':chosen['name'] if chosen else None,'GeoNames_aliases_raw':chosen['aliases'] if chosen else None,'GeoNames_admin1_code':chosen['adm1'] if chosen else None,
        'raw_point_to_GeoNames_witness_km':min((x[0] for x in near),default=None),'source_region_geometry_iso':iso,
        'component_full_chain_latest':full_chain,'latest_current_point_present':not latest_point_absent,'global_blocklisted':not unblocked,
        'rule_checks_json':json.dumps(gates,ensure_ascii=False,sort_keys=True),'hold_reasons_json':json.dumps(holds,ensure_ascii=False),
        'review_status':'independently_eligible_current_point_seed_pending_root_admission' if eligible else 'held_independent_review',
        'coordinate_use_scope':'2021 source row direct-point candidate only; no QID/provider binding, no historical use; direct source coordinate remains the raw Dadata/Tochno payload, GeoNames is independent physical-name corroboration only',
        'measurement_date_precision_or_historical_claim':False}
  out.append(pair)
 # Fixed 20 row risk sample, across source type-evidence families, including top-mass, railway, and near-threshold cases.
 pdf=pd.DataFrame(out); selected_sample={}
 def add(rows,tag,n=None):
  if n is not None:rows=rows.head(n)
  for x in rows.to_dict('records'): selected_sample.setdefault(x['target_source_record_id'],set()).add(tag)
 eligible_pdf=pdf[pdf.review_status.eq('independently_eligible_current_point_seed_pending_root_admission')].copy()
 eligible_pdf['pop_num']=pd.to_numeric(eligible_pdf.population,errors='coerce')
 add(eligible_pdf[eligible_pdf.publisher_type_evidence_independent.eq('literal_publisher_city_abbreviation')].sort_values('pop_num',ascending=False),'all_city_abbreviation')
 add(eligible_pdf[eligible_pdf.publisher_type_evidence_independent.str.contains('railway')].sort_values('pop_num',ascending=False),'railway_top_mass',n=5)
 add(eligible_pdf[eligible_pdf.publisher_type_evidence_independent.str.contains('railway')].sort_values('raw_point_to_GeoNames_witness_km',ascending=False),'railway_near_1km_risk',n=2)
 add(eligible_pdf[eligible_pdf.publisher_type_evidence_independent.eq('literal_object_name_type_prefix')].sort_values('pop_num',ascending=False),'literal_prefix_top_mass',n=7)
 # Largest distances and a deterministic hash-ranked residual sample fill to exactly 20.
 add(eligible_pdf.sort_values('raw_point_to_GeoNames_witness_km',ascending=False),'largest_distance_risk',n=3)
 if len(selected_sample)<20:
  remain=eligible_pdf[~eligible_pdf.target_source_record_id.isin(selected_sample)].copy()
  remain['seed_order']=remain.target_source_record_id.map(lambda x:hashlib.sha256(('20261004|'+x).encode()).hexdigest())
  add(remain.sort_values('seed_order'),'fixed_hash_seed_fill',n=20-len(selected_sample))
 sample=pdf[pdf.target_source_record_id.isin(selected_sample)].copy()
 sample['fixed_risk_strata']=sample.target_source_record_id.map(lambda x:'|'.join(sorted(selected_sample[x])))
 sample['sample_method']='deterministic_union:publisher_type_families_topmass_and_1km_distance_risk_plus_sha256_seed20261004'
 req(len(sample)==20 if len(eligible_pdf)>=20 else len(sample)==len(eligible_pdf),'risk sample size mismatch')
 # Freeze output only after every input vector and full cohort has been checked.
 if OUT.exists() and any(OUT.iterdir()):raise ValueError(f'refusing to overwrite {OUT}')
 OUT.mkdir(parents=True,exist_ok=True)
 elig=pdf[pdf.review_status.eq('independently_eligible_current_point_seed_pending_root_admission')].copy()
 held=pdf[pdf.review_status.eq('held_independent_review')].copy()
 outputs={}
 for name,frame in [('independently_eligible_point_seed_list',elig),('held_point_candidates',held),('fixed_20_risk_sample',sample),('all_177_independent_review',pdf)]:
  for ext in ('csv','parquet'):
   p=OUT/f'{name}.{ext}'
   frame.drop(columns=['pop_num','seed_order'],errors='ignore').to_csv(p,index=False,quoting=csv.QUOTE_MINIMAL) if ext=='csv' else frame.drop(columns=['pop_num','seed_order'],errors='ignore').to_parquet(p,index=False)
   outputs[f'{name}_{ext}']={'path':str(p),'sha256':sha(p),'rows':len(frame),'bytes':p.stat().st_size}
 # Cross-year point-gap population is a current-row source population upper bound only.
 eligible_pop=float(pd.to_numeric(elig.population,errors='coerce').sum())
 summary={
  'status':'independent_type_helper_false_zero_point_review_complete_candidate_only',
  'rule':'Accept a current direct point seed only when the pinned source row is an additive named settlement; raw published name/object label independently supports its selected type or specific rail subtype; raw source coordinates exactly reproduce selected coordinates; raw literal current native OKTMO, source name/type/region, code uniqueness, no existing point/blocked target/duplicate point, unique physical GeoNames exact-name witness within 1km in the same resolved ADM1, and both points fall inside the source-region geometry. Compact/full helper fields remain separate preserved fields and are not corrected or promoted as a new identity binding.',
  'candidate_rows':len(pdf),'independently_eligible_rows':len(elig),'held_rows':len(held),'candidate_source_population_sum':float(pd.to_numeric(pdf.population,errors='coerce').sum()),
  'eligible_source_population_sum_conditional_only':eligible_pop,'held_source_population_sum':float(pd.to_numeric(held.population,errors='coerce').sum()),
  'eligibility_type_categories':elig.publisher_type_evidence_independent.value_counts().to_dict(),
  'eligibility_helper_interpretations':elig.helper_field_interpretation.value_counts().to_dict(),
  'conditional_fullchain_count_latest_graph':int(elig.component_full_chain_latest.sum()),
  'candidate_overlaps_existing_ninth_point_ledger':int(pdf.latest_current_point_present.sum()),
  'original_screen_rounded_coordinate_lookup_zero_full_precision_unique_rows':int(elig.screen_coordinate_lookup_zero_but_full_precision_coordinate_unique.sum()),
  'distinct_current_fullchain_components':len(set(target_roots.values())),
  'global_blocked_candidate_count':int(pdf.global_blocklisted.sum()),
  'point_use_interpretation':'Conditional current 2021 point coverage only; values are source population sums and are not a computed net coverage gain or an accepted spatial metric. Coordinates have no asserted measurement date/precision, historical use, GN provider binding, or historical identity role.',
  'hard_holds':held[['target_source_record_id','hold_reasons_json']].to_dict('records'),
  'current_points_sha256':PINS['current_ninth_points'][1],'current_graph_sha256':PINS['current_ninth_graph'][1],
  'rule_predicate_counts':{k:int(pdf.rule_checks_json.map(lambda s:json.loads(s)[k]).sum()) for k in json.loads(pdf.iloc[0].rule_checks_json)},
  'source_hashes':input_hashes,'review_producer':{'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))},
  'review_tests':{'path':str(TESTS.resolve()),'sha256':sha(TESTS)},'outputs':outputs,
  'fixed_risk_sample':{'rows':len(sample),'sha256':outputs['fixed_20_risk_sample_csv']['sha256'],'strata_counts':sample.fixed_risk_strata.value_counts().to_dict()},
  'admissions':{'point_uses':0,'identity_bindings':0,'historical_provider_bindings':0,'historical_coordinate_uses':0},
  'mutations':{'canonical_graph':False,'accepted_point_ledger':False,'selected_observations':False,'source_data':False}}
 rp=OUT/'independent_review_receipt.json';rp.write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':summary['status'],'eligible':len(elig),'held':len(held),'eligible_population_conditional':eligible_pop,'receipt':str(rp),'receipt_sha256':sha(rp),'predicate_counts':summary['rule_predicate_counts']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
