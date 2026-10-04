#!/usr/bin/env python3
"""Stage candidate-only GeoNames points for current full-chain point gaps.

A whole-ADM1 GN alias alone does not select among homonyms. This narrow route
requires an exact unique typed 2009 classifier/2011 GeoKLADR physical point,
co-located with exactly one whole-ADM1 GeoNames PPL-family alias (<=5 km),
plus current primary-source row identity/name/type/region/native-code checks.
No provider-ID binding, census-date measurement, or coordinate precision is
claimed. New points remain candidate-only and do not modify accepted ledgers.
"""
from __future__ import annotations
import csv, hashlib, json, math, re, sys
from collections import defaultdict
from pathlib import Path
import pandas as pd

ROOT=Path('/workspace/settlements-work')
BASE=ROOT/'continuation_20261004'
OUT=BASE/'R4/current_full_chain_native_geonames_points_20261004'
REPO=Path('/workspace/russian-settlements-research')
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
SOURCE_EVIDENCE=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
TOP=BASE/'R4/top_population_joint_recovery/fourth_origin_corrected_20261004_0205/top200_residual_by_year_scope.csv'
GN_LEDGER=BASE/'R4/wikidata_points/extensions/geonames_two_pass_v7/current_2021_residual_rule_ledger.csv'
GRAPH=BASE/'accepted_mass_rule_corrections_origin_corrected/accepted_identity_edges.parquet'
POINTS=BASE/'accepted_mass_rule_corrections_origin_corrected/accepted_point_uses.parquet'
COVERAGE=BASE/'accepted_mass_rule_corrections_origin_corrected/coverage.json'
HIST=ROOT/'coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet'
RAW_TOCHNO=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
RAW_TOCHNO_SHA='86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'
YEARS=(2002,2010,2021)

def sha_file(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def norm(v):
 if v is None or pd.isna(v):return ''
 return ' '.join(re.sub(r'\s+',' ',str(v).replace('ё','е').casefold()).split())
def region_key(v):
 s=norm(v);s=re.sub(r'[-–—]+',' ',s)
 aliases={'рсо':'северная осетия алания','кчр':'карачаево черкесская','кбр':'кабардино балкарская','якутия':'саха якутия','удмуртия':'удмуртская','чувашия':'чувашская','нижегород':'нижегородская','чувашская республика чувашия':'чувашская'}
 s=aliases.get(s,s);s=re.sub(r'^республика\s+','',s);s=s.replace('саха (якутия)','саха якутия')
 s=re.sub(r'\s+автономный округ(?=\s+югра$)','',s)
 s=re.sub(r'\s+(область|обл\.?|край|края|республика|респ\.?|автономный округ|автономная область)$','',s)
 return ' '.join(s.split())
def num(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (TypeError,ValueError):return None
def code(v):
 if v is None or pd.isna(v):return ''
 return re.sub(r'\.0$','',str(v).strip())
def hav(a,b):
 p1,p2=map(math.radians,(a[0],b[0]));dp=p2-p1;dl=math.radians(b[1]-a[1])
 z=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 6371.0088*2*math.asin(math.sqrt(z))
def compact(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)

def raw_source_type_name(row, expected_type, expected_name):
 """Check the primary typed object label; tolerate publisher type suffixes."""
 label=norm(row.get('object_name') or row.get('settlement'))
 name=norm(expected_name);typ=norm(expected_type)
 prefixes={'город':('г.','г','город'),'пгт':('пгт','рп','поселок городского типа'),'поселок':('п','пос','поселок'),'село':('с','село'),'деревня':('д','дер','деревня'),'станица':('ст-ца','станица'),'хутор':('х','хутор')}
 for pre in prefixes.get(typ,(typ,)):
  pre=norm(pre)
  if label.startswith(pre+' '):
   rest=label[len(pre)+1:].strip()
   if rest==name or rest.startswith(name+' ') or rest.startswith(name+' ('):
    return True,pre,rest
 return False,None,label

class DSU:
 def __init__(self,frame):
  self.ids=frame.source_record_id.astype(str).tolist();self.ix={s:i for i,s in enumerate(self.ids)}
  if len(self.ix)!=len(self.ids):raise ValueError('duplicate selected source ids')
  self.parent=list(range(len(self.ids)));self.rank=[0]*len(self.ids);self.mask=[0]*len(self.ids)
  for i,y in enumerate(frame.census_year.astype(int).tolist()):self.mask[i]=1<<(y.bit_length()) # not used
  # use explicit year bits
  for i,y in enumerate(frame.census_year.astype(int).tolist()):self.mask[i]={2002:1,2010:2,2021:4}[y]
 def find(self,x):
  if isinstance(x,str):x=self.ix[x]
  while self.parent[x]!=x:self.parent[x]=self.parent[self.parent[x]];x=self.parent[x]
  return x
 def union(self,a,b):
  x,y=self.find(a),self.find(b)
  if x==y:return
  if self.mask[x]&self.mask[y]:raise ValueError('accepted identity edge creates same-year component')
  if self.rank[x]<self.rank[y]:x,y=y,x
  self.parent[y]=x;self.mask[x]|=self.mask[y]
  if self.rank[x]==self.rank[y]:self.rank[x]+=1

def main():
 if OUT.exists():raise SystemExit(f'refusing to overwrite candidate freeze: {OUT}')
 OUT.mkdir(parents=True)
 sys.path.insert(0,str(REPO))
 from research_rebuild.mass_linkage.build_long_table import ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES,ACCEPTED_PROJECTION_STATUSES
 # Selected target rows are top-population 2021 residuals with a completed identity chain and no point.
 top=pd.read_csv(TOP,low_memory=False)
 top=top[(top.census_year.eq(2021))&(top.diagnostic_reason.eq('missing_point_only'))&top.identity_full.astype(str).str.lower().eq('true')].sort_values(['population','source_record_id'],ascending=[False,True]).head(100).copy()
 top.source_record_id=top.source_record_id.astype(str)
 sel=pd.read_parquet(SELECTED,columns=['source_record_id','census_year','settlement_name','settlement_type','region_raw','region_norm','population','population_scope','is_additive_settlement_record','source_file','source_sha256','source_locator','source_native_id','oktmo','source_name_raw'])
 sel.source_record_id=sel.source_record_id.astype(str);sel.census_year=sel.census_year.astype(int)
 cur=sel[sel.census_year.eq(2021)].copy()
 if cur.source_record_id.duplicated().any():raise RuntimeError('current selected ids duplicate')
 cur['nk']=cur.settlement_name.map(norm);cur['tk']=cur.settlement_type.map(norm);cur['rk']=cur.region_norm.map(region_key);cur['ck']=cur.oktmo.map(code)
 top=top.merge(cur,on=['source_record_id','census_year'],how='left',suffixes=('_diag',''),validate='one_to_one')
 if top.settlement_name.isna().any():raise RuntimeError('top residual ids absent from selected')
 names=top.settlement_name.map(norm).tolist();regions=top.region_norm.map(region_key).tolist()
 # Check whole-year uniqueness and current code uniqueness before source/proxy evidence.
 current_name_counts=cur.groupby(['nk','tk','rk'],dropna=False).source_record_id.nunique().to_dict()
 current_code_counts=cur[cur.ck.ne('')].groupby('ck').source_record_id.nunique().to_dict()
 # One-pass exact source row payload read (small parquet, selected columns only).
 if sha_file(RAW_TOCHNO)!=RAW_TOCHNO_SHA:raise RuntimeError('current raw Tochno source pin changed')
 raw=pd.read_parquet(RAW_TOCHNO,columns=['object_level','object_name','oktmo','region','population','settlement','latitude_dadata','longitude_dadata'])
 if len(raw)!=176232:raise RuntimeError(f'unexpected raw Tochno row count {len(raw)}')
 gnledger=pd.read_csv(GN_LEDGER,low_memory=False).set_index('source_record_id',drop=False)
 # Exact historical typed physical rows from the existing merged 2009/2011 object inventory.
 h=pd.read_parquet(HIST,columns=['historical_okato','name','status','type_key_2009','type_key_2011','historical_name_exact','historical_type_exact','historical_point_modern_region','historical_key_region_name_type_count','latitude_from_lat','longitude_from_long','source_line_1based','source_sha256_2009','source_sha256_2011','record_number_1based','record_byte_offset_0based','historical_okato_2009_raw','historical_okato_2011_raw','name_raw_2009','name_raw_2011','settlement_type_raw','raw_point_source_sha256' ] if False else ['historical_okato','name','status','type_key_2009','type_key_2011','historical_name_exact','historical_type_exact','historical_point_modern_region','historical_key_region_name_type_count','latitude_from_lat','longitude_from_long','source_line_1based','source_sha256_2009','source_sha256_2011','record_number_1based','record_byte_offset_0based','historical_okato_2009_raw','historical_okato_2011_raw','name_raw_2009','name_raw_2011','settlement_type_raw'])
 h['nk']=h.name.map(norm);h['rk']=h.historical_point_modern_region.map(region_key)
 # exact upstream type table: census type -> both raw classifier and GeoKLADR status keys
 type_map={'город':'город','пгт':'пгт','поселок':'поселок','посёлок':'поселок','село':'село','деревня':'деревня','хутор':'хутор','станица':'станица','аул':'аул','станция':'станция','разъезд':'разъезд','слобода':'слобода'}
 h['hk']=h.type_key_2009.map(type_map).fillna('')
 h['historic_name_alias']=h.name.map(norm)
 # Publisher's explicit "кп" qualifier occurs in both raw years and current
 # primary label for Иноземцево; strip only with that three-source notation.
 h['historic_suffix_alias_ok']=(h['historic_name_alias'].str.endswith(' кп') &
     h.name_raw_2009.map(norm).str.endswith(' кп') & h.name_raw_2011.map(norm).str.endswith(' кп'))
 h.loc[h.historic_suffix_alias_ok,'historic_name_alias']=h.loc[h.historic_suffix_alias_ok,'historic_name_alias'].str[:-3].str.strip()
 h['historic_row_count_name_region']=h.groupby(['historic_name_alias','rk'],dropna=False).historical_okato.transform('size')
 hist_by=defaultdict(list)
 for r in h.itertuples(index=False):
  if bool(r.historical_name_exact) and bool(r.historical_type_exact) and r.hk:
   hist_by[(r.historic_name_alias,r.hk,r.rk)].append(r)
 # GeoNames whole ADM1 aliases for this cohort, using the same fully pinned parser and source bundle as V7.
 import importlib.util
 v7path=REPO/'research_rebuild/mass_linkage/stage_geonames_two_pass_recovery_20261004_v7.py'
 spec=importlib.util.spec_from_file_location('gnv7',v7path);gnv7=importlib.util.module_from_spec(spec);sys.modules['gnv7']=gnv7;spec.loader.exec_module(gnv7)
 expected=set(regions);needed=set(names)
 gn_by,gn_regions,adm1,readme,gnbody,gnmeta=gnv7.load_geonames(expected,needed)
 candidates=[];holds=[]
 for x in top.itertuples(index=False):
  sid=str(x.source_record_id);year=int(x.census_year);p=float(x.population_diag)
  info={'source_record_id':sid,'year':year,'population':p,'settlement_name':x.settlement_name,'settlement_type':x.settlement_type,'region_raw':x.region_raw,'region_norm':x.rk,'source_native_id':x.source_native_id,'source_file':x.source_file,'source_sha256':x.source_sha256,'source_locator':x.source_locator,'oktmo_raw':x.oktmo,'population_scope':x.population_scope,'additive':bool(x.is_additive_settlement_record)}
  reasons=[]
  rawix=int(sid.rsplit(':',1)[-1])-1
  if rawix<0 or rawix>=len(raw):reasons.append('raw_source_row_out_of_range');rr={}
  else:rr=raw.iloc[rawix].to_dict()
  curcode=code(x.oktmo);namekey=norm(x.settlement_name);typekey=norm(x.settlement_type);region=region_key(x.region_norm)
  labelok,prefix,labeltail=raw_source_type_name(rr,x.settlement_type,x.settlement_name)
  rawchecks={'object_level_is_NP':norm(rr.get('object_level'))=='населенный пункт','oktmo_equals_selected_dot_zero_only':code(rr.get('oktmo'))==curcode,
             'population_equals_selected':num(rr.get('population'))==num(x.population_diag),'raw_region_equals_selected':norm(rr.get('region'))==norm(x.region_raw),
             'primary_object_name_matches_selected_type_and_name':labelok,'current_code_unique_whole_2021':current_code_counts.get(curcode,0)==1,
             'current_name_type_region_unique_whole_2021':current_name_counts.get((namekey,typekey,region),0)==1,
             'additive_atomic_scope':bool(x.is_additive_settlement_record) and str(x.population_scope)=='settlement'}
  sourceok=all(rawchecks.values())
  if not sourceok:reasons.append('current_source_row_or_uniqueness_gate')
  # Existing explicit point quarantines remain a review flag. Only candidate if evidence can resolve without relying on them.
  old=gnledger.loc[sid] if sid in gnledger.index else None
  oldholds=json.loads(old.hold_memberships_json) if old is not None and isinstance(old.hold_memberships_json,str) else []
  # Direct whole-alias GN evidence, before source coordinate-distance filters.
  gns=list(gn_by.get((namekey,region),{}).values())
  # The independently named typed historical physical point is unique for the complete historic region/name/type key.
  histrows=hist_by.get((namekey,typekey,region),[])
  # A documented pgt/"поселок" status label transition is usable for point
  # selection only when exact normalized name+ADM1 occurs once across every
  # historic type, and the raw current source independently carries its type.
  if not histrows and typekey=='пгт':
   histrows=hist_by.get((namekey,'поселок',region),[])
   histrows=[q for q in histrows if int(q.historic_row_count_name_region or 0)==1]
  if not histrows:
   # Strip the documented resort-settlement suffix only when the selected
   # primary row itself retains that same suffix.
   raw_name_suffix=norm(rr.get('object_name') or rr.get('settlement')).endswith(' кп')
   if raw_name_suffix:
    histrows=hist_by.get((namekey,'пгт',region),[])
  histvalid=[]
  for q in histrows:
   lat,lon=num(q.latitude_from_lat),num(q.longitude_from_long)
   if lat is None or lon is None or not (-90<=lat<=90 and -180<=lon<=180):continue
   if int(q.historical_key_region_name_type_count or 0)!=1:continue
   histvalid.append((q,lat,lon))
  if len(histvalid)!=1:reasons.append('no_unique_exact_typed_historical_point')
  point_matches=[]
  if len(histvalid)==1:
   q,hlat,hlon=histvalid[0]
   for g in gns:
    glat,glon=num(g['latitude']),num(g['longitude'])
    if glat is None or glon is None or not(-90<=glat<=90 and -180<=glon<=180):continue
    distance=hav((hlat,hlon),(glat,glon))
    if distance<=5.0:point_matches.append((g,distance))
  if not gns:reasons.append('no_exact_whole_adm1_geonames_name_alias')
  close_matches=[(g,d) for g,d in point_matches if d<=1.0]
  selection_matches=point_matches if len(point_matches)==1 else close_matches
  selection_rule='one_alias_within_5km' if len(point_matches)==1 else ('one_alias_within_1km_historic_typed_point_disambiguates_all_same_ADM1_name_competitors' if len(close_matches)==1 else None)
  if len(selection_matches)!=1:reasons.append('historical_point_does_not_select_one_GN_physical_id_within_5km_or_strong_1km_disambiguation')
  if oldholds:
   reasons.append('existing_point_quarantine_requires_separate_resolution_receipt:'+','.join(oldholds))
  if histvalid and selection_matches:
   q,hlat,hlon=histvalid[0];g,dist=selection_matches[0]
  else:q=hlat=hlon=g=dist=None
  record={**info,'current_source_raw_row_1based':rawix+1,'current_source_raw_payload_json':compact(rr),'current_source_raw_payload_sha256':sha_bytes(compact(rr).encode()),
          'current_source_raw_checks_json':compact(rawchecks),'current_source_raw_typed_label_prefix':prefix,'current_source_raw_typed_label_tail':labeltail,
          'current_source_okato_native_identifier_binding_asserted':False,'current_source_coordinate_used':False,
          'historical_witness':None,'whole_adm1_gn_aliases':[],'point_candidate':False,'candidate_status':'hold','hold_reasons':reasons,
          'existing_v7_point_hold_memberships':oldholds,'coordinate_admission':False,'candidate_only':True}
  if q is not None:
   record['historical_witness']={'historical_okato_source_string':str(q.historical_okato),'historical_okato_2009_raw':str(q.historical_okato_2009_raw),'historical_okato_2011_raw':str(q.historical_okato_2011_raw),
       'classifier_type_2009':str(q.type_key_2009),'geokladr_type_2011':str(q.type_key_2011),'type_key_matches_current':str(q.hk)==typekey,
       'name_2009_raw':str(q.name_raw_2009),'name_2011_raw':str(q.name_raw_2011),'parsed_name':str(q.name),'historical_name_exact_2009_2011':bool(q.historical_name_exact),
       'historical_type_exact_2009_2011':bool(q.historical_type_exact),'whole_historical_region_name_type_key_count':int(q.historical_key_region_name_type_count),
       'historical_region_norm':str(q.rk),'lat_2011_raw':hlat,'lon_2011_raw':hlon,'point_locator':{'raw_sql_line_1based':int(q.source_line_1based),'geo_dbf_record_1based':int(q.record_number_1based),'geo_dbf_byte_offset_0based':int(q.record_byte_offset_0based)},
       'raw_2009_sha256':str(q.source_sha256_2009),'raw_2011_sha256':str(q.source_sha256_2011)}
  for gg in gns:
   record['whole_adm1_gn_aliases'].append({'geonameid':str(gg['geonameid']),'name':gg['name'],'asciiname':gg['asciiname'],'feature_code':gg['feature_code'],'admin1_code':gg['admin1_code'],'admin1_region_norm':gg['admin1_region_norm'],
        'latitude':num(gg['latitude']),'longitude':num(gg['longitude']),'matched_literal_aliases_norm':gg['matched_aliases'],'source_line_1based':gg['source_line_1based'],'byte_start':gg['byte_start'],'byte_end':gg['byte_end'],'line_sha256':gg['line_sha256'],
        'distance_from_historical_2011_point_km':next((d for qg,d in point_matches if qg['geonameid']==gg['geonameid']),None)})
  if sourceok and len(histvalid)==1 and len(selection_matches)==1 and not oldholds:
   g,dist=selection_matches[0]
   record['point_candidate']=True;record['candidate_status']='candidate_exact_current_source_identity_plus_unique_historic_typed_point_to_GN_alias_le_5km'
   record['hold_reasons']=[];record['geonames_selected_witness_id']=str(g['geonameid']);record['geonames_selected_feature_code']=g['feature_code']
   record['latitude']=num(g['latitude']);record['longitude']=num(g['longitude']);record['distance_historic_point_to_gn_km']=dist
   record['GN_alias_disambiguation_rule']=selection_rule
   record['coordinate_origin']='GeoNames RU PPL-family exact whole-ADM1 name alias; physical point corroborated by exact unique historical named typed 2009/2011 point'
   record['provider_identifier_binding_asserted']=False;record['GN_upstream_measurement_independence_proven']=False;record['measurement_date_proven']=False;record['precision_upgraded']=False
   candidates.append(record)
  else:holds.append(record)
 # Compute graph-safe conditional joint gains using the corrected current graph/point ledger.
 allsel=sel[sel.census_year.isin(YEARS)].copy().reset_index(drop=True)
 edges=pd.read_parquet(GRAPH,columns=['from_source_record_id','to_source_record_id','relation','decision_status','selection_projection_status'])
 if edges.decision_status.isna().any() or not edges.decision_status.astype(str).isin(ACCEPTED_EDGE_STATUSES).all():raise RuntimeError('canonical accepted edge status failure')
 if edges.selection_projection_status.isna().any() or not edges.selection_projection_status.astype(str).isin(ACCEPTED_PROJECTION_STATUSES).all() or not edges.relation.eq('same_place').all():raise RuntimeError('canonical projection status failure')
 points=pd.read_parquet(POINTS,columns=['target_source_record_id','target_year','coordinate_admission_status'])
 if points.coordinate_admission_status.isna().any() or not points.coordinate_admission_status.astype(str).isin(ACCEPTED_COORDINATE_STATUSES).all():raise RuntimeError('canonical accepted coordinate status failure')
 dsu=DSU(allsel)
 ids=set(dsu.ix)
 for e in edges.itertuples(index=False):
  a,b=str(e.from_source_record_id),str(e.to_source_record_id)
  if a not in ids or b not in ids:raise RuntimeError('accepted graph endpoint missing selected row')
  dsu.union(a,b)
 pointtargets=set(points.target_source_record_id.astype(str))
 if points.target_source_record_id.astype(str).duplicated().any():raise RuntimeError('duplicate accepted point target')
 def covered(seeds=set()):
  newroots={dsu.find(s) for s in seeds if s in dsu.ix};fullroots={i for i,m in enumerate(dsu.mask) if dsu.find(i)==i and m==7}
  sums={y:[0,0] for y in YEARS}
  for r in allsel.itertuples(index=False):
   root=dsu.find(str(r.source_record_id))
   if root not in fullroots:continue
   y=int(r.census_year);sums[y][0]+=1;sums[y][1]+=0 if pd.isna(r.population) else int(r.population)
  joint={y:[0,0] for y in YEARS}
  for r in allsel.itertuples(index=False):
   root=dsu.find(str(r.source_record_id))
   if root not in fullroots:continue
   if str(r.source_record_id) in pointtargets or root in newroots:
    y=int(r.census_year);joint[y][0]+=1;joint[y][1]+=0 if pd.isna(r.population) else int(r.population)
  return sums,joint
 baseline_full,baseline_joint=covered()
 expected=json.loads(COVERAGE.read_text())
 for m in expected['census_metrics']:
  y=int(m['year']);fc=m['axes']['full_census_chain'];jt=m['axes']['joint_admitted_coordinate_and_full_chain']
  if baseline_full[y]!=[int(fc['rows']),int(fc['known_population'])] or baseline_joint[y]!=[int(jt['rows']),int(jt['known_population'])]:
   raise RuntimeError(f'baseline coverage mismatch y={y}: {(baseline_full[y],baseline_joint[y])}')
 # Candidate point seeds cannot collide in an existing component or in a component with an accepted point.
 eligible=[];comp_members=defaultdict(list);comp_point=defaultdict(bool)
 for sid in dsu.ix:comp_members[dsu.find(sid)].append(sid)
 for sid in pointtargets:
  if sid in dsu.ix:comp_point[dsu.find(sid)]=True
 for c in candidates:
  sid=c['source_record_id'];root=dsu.find(sid)
  if comp_point[root]:c['candidate_status']='hold_component_already_has_accepted_point';c['point_candidate']=False;c['hold_reasons']=['existing_accepted_point_in_identity_component']
  elif any(x['source_record_id']==sid for x in eligible):c['candidate_status']='hold_duplicate_candidate_seed';c['point_candidate']=False;c['hold_reasons']=['duplicate_target_candidate']
  else:eligible.append(c)
 seeds={x['source_record_id'] for x in eligible}
 # Distinct candidate IDs must represent distinct current identity components.
 roots=defaultdict(list)
 for sid in seeds:roots[dsu.find(sid)].append(sid)
 if any(len(v)>1 for v in roots.values()):raise RuntimeError('multiple GN proposals in same identity component')
 after_full,after_joint=covered(seeds)
 gain=[]
 for y in YEARS:
  gain.append({'year':y,'baseline_full_chain_rows':baseline_full[y][0],'baseline_full_chain_population':baseline_full[y][1],
    'conditional_full_chain_rows':after_full[y][0],'conditional_full_chain_population':after_full[y][1],
    'baseline_joint_rows':baseline_joint[y][0],'baseline_joint_population':baseline_joint[y][1],
    'conditional_joint_rows':after_joint[y][0],'conditional_joint_population':after_joint[y][1],
    'marginal_joint_rows':after_joint[y][0]-baseline_joint[y][0],'marginal_joint_population':after_joint[y][1]-baseline_joint[y][1],
    'interpretation':'GN candidate point used as a continuity seed through existing accepted full-chain graph; no census-date coordinate measurement claimed'})
 # Per-target marginal within the existing full-chain component avoids reporting endpoint-only sums.
 by_sid={r.source_record_id:r for r in allsel.itertuples(index=False)}
 for c in candidates:
  if not c['point_candidate']:continue
  root=dsu.find(c['source_record_id']); pop_by={y:0 for y in YEARS};rows_by={y:0 for y in YEARS}
  for sid in comp_members[root]:
   r=by_sid[sid];y=int(r.census_year);rows_by[y]+=1;pop_by[y]+=0 if pd.isna(r.population) else int(r.population)
  c['conditional_component_rows_by_year_json']=compact(rows_by);c['conditional_component_population_by_year_json']=compact(pop_by)
  c['joint_increment_isolated_population_sum_diagnostic']=sum(pop_by.values())
 # Persist full cohort ledger, admitted-none candidates, holds, and a point-use shaped review file.
 ledger=holds+candidates
 ledger.sort(key=lambda r:(-float(r.get('population',0) or 0),r['source_record_id']))
 (OUT/'point_candidate_ledger.jsonl').write_text(''.join(compact(r)+'\n' for r in ledger),encoding='utf-8')
 columns=['point_use_id','target_source_record_id','target_year','latitude','longitude','coordinate_source','coordinate_admission_status','candidate_only','candidate_rule_family','historical_witness_json','geo_names_witness_json','provider_identifier_binding_asserted','GN_upstream_measurement_independence_proven','census_date_measurement_proven','coordinate_precision_upgraded']
 with (OUT/'staged_point_uses.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
  for c in candidates:
   if not c['point_candidate']:continue
   w.writerow({'point_use_id':'GNP-'+hashlib.sha256((c['source_record_id']+'|'+c['geonames_selected_witness_id']).encode()).hexdigest()[:18],'target_source_record_id':c['source_record_id'],'target_year':2021,'latitude':c['latitude'],'longitude':c['longitude'],'coordinate_source':c['coordinate_origin'],'coordinate_admission_status':'candidate_only_pending_independent_review','candidate_only':True,'candidate_rule_family':'exact_current_primary_row_plus_unique_typed_historical_point_to_unique_GN_alias_le_5km','historical_witness_json':compact(c['historical_witness']),'geo_names_witness_json':compact(c['whole_adm1_gn_aliases']),'provider_identifier_binding_asserted':False,'GN_upstream_measurement_independence_proven':False,'census_date_measurement_proven':False,'coordinate_precision_upgraded':False})
 (OUT/'conditional_joint_gain.json').write_text(json.dumps({'baseline_input_graph_sha256':sha_file(GRAPH),'baseline_input_points_sha256':sha_file(POINTS),'baseline_coverage_sha256':sha_file(COVERAGE),'candidate_point_count':len(seeds),'candidate_endpoint_population_sum_diagnostic':sum(c['population'] for c in candidates if c['point_candidate']),'baseline_full_chain':{str(y):baseline_full[y] for y in YEARS},'baseline_joint':{str(y):baseline_joint[y] for y in YEARS},'after_joint':{str(y):after_joint[y] for y in YEARS},'marginal_by_year':gain},indent=2),encoding='utf-8')
 summary={'status':'candidate_only_no_admissions','cohort_definition':'Top 100 current 2021 full-chain point-only residual records from the fourth origin-corrected residual audit (actual selected count reported below).','rule':'Current primary 2021 physical NP source row exact region/native-code/population/source label and whole-year unique code plus name/type/region; exact whole-ADM1 GeoNames PPL-family alias; exact unique historical 2009 classifier and 2011 GeoKLADR named typed physical point for the same name/type/modern ADM1; exactly one matching GeoNames physical ID within 5 km of that historical point. Current Tochno coordinates are not used. PPLA/PPL feature subtype alone is not identity evidence.','claims_not_made':['No provider identifier binding','No GN upstream measurement independence proof','No census-date coordinate measurement','No coordinate precision upgrade','No identity edge or population modification'],
   'top_cohort_rows':len(top),'cohort_population_sum_endpoint_diagnostic':int(top.population_diag.sum()),'candidate_point_count':len(seeds),'candidate_endpoint_population_sum_diagnostic':int(sum(c['population'] for c in candidates if c['point_candidate'])),'candidate_ids':[c['source_record_id'] for c in candidates if c['point_candidate']],
   'hold_count':len(holds),'hold_reasons':dict(pd.Series([z for c in holds for z in c['hold_reasons']]).value_counts()),'conditional_full_chain_baseline':{str(y):baseline_full[y] for y in YEARS},'conditional_joint_baseline':{str(y):baseline_joint[y] for y in YEARS},'conditional_joint_after':{str(y):after_joint[y] for y in YEARS},'conditional_joint_marginal':gain,
   'source_hashes':{str(p):sha_file(p) for p in [SELECTED,SOURCE_EVIDENCE,TOP,GN_LEDGER,GRAPH,POINTS,COVERAGE,HIST,RAW_TOCHNO]},'geo_names_input_metadata':gnmeta,'outputs':{}}
 for name in ['point_candidate_ledger.jsonl','staged_point_uses.csv','conditional_joint_gain.json']:
  summary['outputs'][name]={'sha256':sha_file(OUT/name),'bytes':(OUT/name).stat().st_size}
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 summary['outputs']['summary.json']={'sha256':sha_file(OUT/'summary.json'),'bytes':(OUT/'summary.json').stat().st_size}
 (OUT/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 print(json.dumps({'top':len(top),'candidates':len(seeds),'candidate_pop':summary['candidate_endpoint_population_sum_diagnostic'],'holds':len(holds),'gains':gain,'candidate_ids':summary['candidate_ids']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
