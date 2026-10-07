#!/usr/bin/env python3
"""Stage candidate own-locality points for leading strict ordinary residual rows."""
from __future__ import annotations
import hashlib,json,re,sys
from collections import defaultdict,Counter
from pathlib import Path
import pandas as pd, duckdb
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km
from measure_event_aware_path_union_20261005 import SELECTED
OUT=Path(__file__).resolve().parent
TOP=ROOT/'research_rebuild/evidence/working_full_chain_20261007'
TOPFILES={y:TOP/f'top100_strict_joint_residual_{y}.csv' for y in (2002,2010,2021)}
TOCHNO=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
ROUTES=OUT/'source_point_routes.csv'; SCREEN=OUT/'top20_screen.csv'; RECEIPT=OUT/'receipt.json'
STATION_PREFIXES=[r'^при станции\s+',r'^станции\s+',r'^станция\s+',r'^железнодорожной станции\s+',r'^железнодорожного разъезда\s+',r'^железнодорожном разъезде\s+',r'^разъезда\s+',r'^п\.?\s+']

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def code(x):
 if pd.isna(x):return ''
 s=str(x).strip();return s[:-2] if s.endswith('.0') else s
def name_aliases(name):
 n=normalize(name); out={n}
 for pat in STATION_PREFIXES:out.add(re.sub(pat,'',n))
 return {x for x in out if x}
def region_key(value):
 s=normalize(value)
 s=re.sub(r'[^а-яa-z0-9 ]',' ',s)
 toks=[t for t in s.split() if t not in {'область','край','республика','автономная','округ','россия'}]
 return ' '.join(toks)
def region_match(a,b):
 aa=region_key(a).split();bb=region_key(b).split()
 return bool(aa and bb) and all(any(y.startswith(x[:5]) or x.startswith(y[:5]) for y in bb) for x in aa)
def type_match(target,source):
 t,s=normalize(target),normalize(source)
 if t in {'пгт','поселок городского типа'}:return s in {'пгт','поселок городского типа'}
 if t in {'поселок','поселок'}:return s=='поселок' or s.startswith('поселок ') or s=='сельский поселок'
 if t in {'город','городской округ'}:return s=='город' or s.startswith('город ')
 if t=='село':return s=='село'
 if t=='деревня':return s=='деревня'
 if t=='станица':return s=='станица'
 if t=='хутор':return s=='хутор'
 return t==s

def boolval(v):return str(v).strip().lower()=='true'
def main():
 state=load(stage=10); baseline=state.metrics(); selected_ids=set(state.by_id.index.astype(str))
 top_frames=[]; excluded=Counter()
 for year,path in TOPFILES.items():
  frame=pd.read_csv(path,dtype=str,keep_default_na=False)
  frame['population_num']=pd.to_numeric(frame.population,errors='coerce')
  picked=[]
  for _,r in frame.iterrows():
   sid=str(r.source_record_id)
   if sid not in selected_ids:excluded['top_row_not_selected_in_stage10']+=1;continue
   if boolval(r.covered_by_complete_partition_scope) or boolval(r.covered_by_qualified_physical_scope):excluded['qualified_partition_or_physical_scope']+=1;continue
   root=state.uf.find(sid);g=state.obs[state.obs.source_record_id.map(state.uf.find).eq(root)]
   if any(str(x) in state.point_rows for x in g.source_record_id):excluded['accepted_point_on_target_component']+=1;continue
   if sid in state.conflicting_point_targets:excluded['accepted_point_conflict']+=1;continue
   picked.append((float(r.population_num) if pd.notna(r.population_num) else 0,r,g,r['source_record_id']))
  picked.sort(key=lambda z:(-z[0],z[3]));
  for rank,(mass,r,g,sid) in enumerate(picked[:20],1):top_frames.append({'source_year':year,'rank_in_year':rank,'residual_population':mass,'record':r,'group':g,'root':state.uf.find(sid)})
 # Batch lookup selected 2021 raw context for all top targets and their current 2021 chain members.
 query_ids=set()
 for x in top_frames:
  query_ids.add(str(x['record'].source_record_id))
  query_ids.update(str(sid) for sid in x['group'].source_record_id)
 con=duckdb.connect(config={'threads':1,'memory_limit':'1GB'})
 raw_selected=con.execute("SELECT source_record_id,settlement_name,settlement_type,region_raw,district_raw,oktmo,okato,latitude,longitude FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))",[str(SELECTED),sorted(query_ids)]).fetchdf()
 raw_selected.source_record_id=raw_selected.source_record_id.astype(str);raw_idx=raw_selected.set_index('source_record_id')
 provider=con.execute("SELECT file_row_number,object_level,object_name,settlement_dadata,settlement_type_full_dadata,region,mun_upper,mun_lower,fias_level_dadata,qc_geo_dadata,oktmo,oktmo_dadata,latitude_dadata,longitude_dadata FROM read_parquet(?,file_row_number=true) WHERE object_level='Населенный пункт' AND fias_level_dadata=6 AND qc_geo_dadata=3 AND latitude_dadata IS NOT NULL AND longitude_dadata IS NOT NULL",[str(TOCHNO)]).fetchdf()
 tup=defaultdict(list)
 for _,p in provider.iterrows():tup[(normalize(p.settlement_dadata),normalize(p.settlement_type_full_dadata),normalize(p.region))].append(p)
 raw_coord_ids=defaultdict(set)
 for _,r in state.obs[state.obs.census_year.astype(int).eq(2021)].iterrows():
  if pd.notna(r.latitude) and pd.notna(r.longitude):raw_coord_ids[(float(r.latitude),float(r.longitude))].add(str(r.source_record_id))
 accepted_point_roots=defaultdict(set)
 for sid,point in state.point_rows.items():
  root=state.uf.find(str(sid))
  if 2021 in state.years[root]:accepted_point_roots[(float(point['latitude']),float(point['longitude']))].add(root)
 provisional=[]; screened=[]
 for x in top_frames:
  r=x['record'];target_id=str(r.source_record_id);g=x['group'];root=x['root'];root_years=state.years[root]
  cur=g[g.census_year.astype(int).eq(2021)]
  source_id='';source_current=None
  if len(cur)==1:
   source_id=str(cur.iloc[0].source_record_id);source_current=raw_idx.loc[source_id]
  target_raw=raw_idx.loc[target_id] if target_id in raw_idx.index else None
  query=source_current if source_current is not None else target_raw
  if query is None:
   screened.append({'source_year':x['source_year'],'rank':x['rank_in_year'],'target_source_record_id':target_id,'name':r.settlement_name,'region':r.region_norm,'status':'held_no_selected_raw_context','missing_years':','.join(map(str,sorted({2002,2010,2021}-root_years)))});continue
  exact_name=str(query.settlement_name);exact_type=str(query.settlement_type);exact_region=str(query.region_raw);aliases=name_aliases(exact_name);source_candidates=[]
  for (pname,ptype,pregion),plist in tup.items():
   if pname not in aliases or not type_match(exact_type,ptype):continue
   if not region_match(exact_region,pregion):continue
   if len(plist)!=1:continue
   p=plist[0]
   # If selected row is available, use native current OKTMO to select the source record.
   native=code(query.oktmo)
   if native and code(p.oktmo)!=native:continue
   # If source census district is explicit, it must be represented by the source municipal path.
   district=str(query.district_raw) if pd.notna(query.district_raw) else ''
   if district.strip():
    m=normalize(p.mun_upper)+' '+normalize(p.mun_lower)
    d=normalize(district)
    if d not in m and not any(tok in m for tok in d.split() if len(tok)>4):continue
   source_candidates.append((pname,ptype,pregion,p))
  if len(source_candidates)!=1:
   screened.append({'source_year':x['source_year'],'rank':x['rank_in_year'],'target_source_record_id':target_id,'name':r.settlement_name,'region':r.region_norm,'status':'held_no_unique_exact_named_provider_source' if not source_candidates else 'held_multiple_provider_source_tuples','candidate_count':len(source_candidates),'missing_years':','.join(map(str,sorted({2002,2010,2021}-root_years)))});continue
  pname,ptype,pregion,p=source_candidates[0];lat,lon=float(p.latitude_dadata),float(p.longitude_dadata);coord=(lat,lon)
  if source_current is not None and pd.notna(source_current.latitude) and pd.notna(source_current.longitude):
   dist=distance_km(coord,(float(source_current.latitude),float(source_current.longitude)))
   if dist>0.05:
    screened.append({'source_year':x['source_year'],'rank':x['rank_in_year'],'target_source_record_id':target_id,'name':r.settlement_name,'region':r.region_norm,'status':'held_provider_point_differs_from_selected_current_record','distance_km':round(dist,6),'missing_years':','.join(map(str,sorted({2002,2010,2021}-root_years)))});continue
  else:dist=None
  # Full 3-year/partial accepted identity paths are useful routes. If there is no 2021 vertex, this is only a modern point candidate pending identity.
  point_current_id=source_id or ''
  if source_current is None:
   source_current=None
  component_population={str(int(y)):int(g.loc[g.census_year.astype(int).eq(y),'population'].fillna(0).sum()) for y in sorted(root_years)}
  potential=sum(component_population.values()) if source_current is not None else float(r.population_num)
  route='accepted_full3_component_point_candidate' if root_years=={2002,2010,2021} else ('accepted_partial_component_point_candidate' if source_current is not None else 'modern_named_point_candidate_requires_identity_route')
  locator=(f"file_row_number={int(p.file_row_number)} (0-based); settlement_dadata={p.settlement_dadata}; settlement_type_full_dadata={p.settlement_type_full_dadata}; region={p.region}; mun_upper={p.mun_upper}; mun_lower={p.mun_lower}; object_name={p.object_name}; object_level={p.object_level}; fias_level_dadata={p.fias_level_dadata}; qc_geo_dadata={p.qc_geo_dadata}; oktmo={code(p.oktmo)}; oktmo_dadata={code(p.oktmo_dadata)}")
  provisional.append({'source_year':x['source_year'],'rank':x['rank_in_year'],'population':float(r.population_num),'target_id':target_id,'target_name':str(r.settlement_name),'target_type':str(r.settlement_type),'target_region':str(r.region_norm),'target_district':str(r.district_raw),'component_ids':list(map(str,g.source_record_id)),'component_years':sorted(root_years),'missing_years':sorted({2002,2010,2021}-root_years),'component_populations':component_population,'potential_mass':potential,'route':route,'point_source_current_record_id':point_current_id,'point_lat':lat,'point_lon':lon,'point_distance_km_to_current':dist,'provider':p,'locator':locator,'source_tuple':(pname,ptype,pregion),'coord':coord})
  screened.append({'source_year':x['source_year'],'rank':x['rank_in_year'],'target_source_record_id':target_id,'name':r.settlement_name,'region':r.region_norm,'status':'candidate_source_found','route':route,'potential_population':potential,'point_source_current_record_id':point_current_id,'missing_years':','.join(map(str,sorted({2002,2010,2021}-root_years))),'provider_row':int(p.file_row_number)})
 # Reject shared proposed points and collisions with other raw current or accepted current points.
 groups=defaultdict(list)
 for x in provisional:groups[x['coord']].append(x)
 routes=[]; collision_counts=Counter()
 for x in provisional:
  own=set(x['component_ids']);raw_collision=raw_coord_ids.get(x['coord'],set())-own
  accepted_collision=accepted_point_roots.get(x['coord'],set())-{x['point_source_current_record_id']}
  staged_collision=len(groups[x['coord']])>1
  if raw_collision or accepted_collision or staged_collision:
   collision_counts['shared_or_conflicting_point']+=1
   xrow=next(y for y in screened if y['target_source_record_id']==x['target_id'] and y['source_year']==x['source_year'] and y['rank']==x['rank'])
   xrow.update(status='held_shared_or_conflicting_point',collision_current_ids=' | '.join(sorted(raw_collision)),accepted_roots=len(accepted_collision),staged_count=len(groups[x['coord']]))
   continue
  p=x['provider'];routes.append({'source_year':x['source_year'],'rank_in_year':x['rank'],'target_source_record_id':x['target_id'],'target_year':x['source_year'],'target_name':x['target_name'],'target_type':x['target_type'],'target_region_norm':x['target_region'],'target_district_raw':x['target_district'],'accepted_component_source_record_ids':' | '.join(x['component_ids']),'accepted_component_years':','.join(map(str,x['component_years'])),'exact_missing_years':','.join(map(str,x['missing_years'])),'potential_population_mass':x['potential_mass'],'candidate_route_status':x['route'],'point_source_current_record_id':x['point_source_current_record_id'],'point_latitude':x['point_lat'],'point_longitude':x['point_lon'],'provider_point_distance_to_selected_current_km':x['point_distance_km_to_current'],'source_url':'https://dadata.ru/','source_file':str(TOCHNO),'source_sha256':sha(TOCHNO),'source_locator':x['locator'],'source_label':p.settlement_dadata,'source_type':p.settlement_type_full_dadata,'source_region':p.region,'source_county_upper':p.mun_upper,'source_county_lower':p.mun_lower,'source_native_oktmo':code(p.oktmo),'source_oktmo_dadata':code(p.oktmo_dadata),'source_object_level':p.object_level,'source_fias_level':p.fias_level_dadata,'source_qc_geo':p.qc_geo_dadata,'provider_binding_asserted':False,'provider_binding_separate':True,'admission_status':'candidate_only_no_admission'})
 route_df=pd.DataFrame(routes);screen_df=pd.DataFrame(screened)
 route_df.to_csv(ROUTES,index=False);screen_df.to_csv(SCREEN,index=False)
 after=state.metrics(extra_point_ids=route_df.target_source_record_id.astype(str).tolist()) if not route_df.empty else baseline
 inputs={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in state.inputs}
 topins={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in TOPFILES.values()}
 receipt={'status':'candidate_only_named_locality_point_routes_no_admission','stage':10,'top20_per_year_requested':20,'target_rows_screened':len(top_frames),'target_rows_with_sourcepoint_candidates':len(provisional),'routes_after_collision_screen':len(route_df),'candidate_only_not_admitted':True,'provider_binding_asserted':False,'provider_binding_separate':True,'candidate_routes_by_kind':dict(Counter(route_df.candidate_route_status)) if not route_df.empty else {},'screen_outcomes':dict(Counter(screen_df.status)),'population_candidate_potential_by_year':{str(y):float(route_df.loc[route_df.target_year.eq(str(y)),'potential_population_mass'].sum()) if not route_df.empty else 0 for y in (2002,2010,2021)},'state_baseline_metrics':baseline,'metrics_if_candidate_rows_were_pointed_directly':after,'source_inputs':{str(SELECTED):{'sha256':sha(SELECTED),'bytes':SELECTED.stat().st_size},str(TOCHNO):{'sha256':sha(TOCHNO),'bytes':TOCHNO.stat().st_size}},'top100_inputs':topins,'working_state_stage10_inputs':inputs,'source_point_routes_sha256':sha(ROUTES),'screen_sha256':sha(SCREEN),'build_script_sha256':sha(Path(__file__)),'rules':{'candidate_source':'Tochno 2021 own-locality provider record; exact locality name (limited printed type prefix alias), compatible provider locality type, region match, county context retained, exact native OKTMO when a selected 2021 vertex exists, unique full provider label/type/region tuple, own-locality object_level=Населенный пункт, FIAS6/QCgeo3; provider point crosschecked to selected 2021 raw point within 50m where such a selected vertex exists','route':'Only accepted graph component members are listed as exact route. Full3 means full-chain potential; partial means accepted linked years only; an isolated older row is marked as requiring an identity route and receives no transfer claim. Population values are copied as context and are not modified.','collision':'Candidate source points sharing exact coordinates with another 2021 raw object, accepted current point, or another staged route are withheld; no coordinate offsets are introduced','scopes':'Rows already qualified by complete partition or physical scope, or having an accepted point anywhere on the current component, were excluded before top-20 ranking'}}
 RECEIPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'screened':len(top_frames),'pointable_before_collisions':len(provisional),'routes_after_collision_screen':len(route_df),'route_statuses':dict(Counter(route_df.candidate_route_status)) if not route_df.empty else {},'screen':dict(Counter(screen_df.status)),'potential_mass':receipt['population_candidate_potential_by_year']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
