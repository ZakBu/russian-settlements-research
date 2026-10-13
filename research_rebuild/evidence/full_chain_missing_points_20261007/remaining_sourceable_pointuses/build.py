#!/usr/bin/env python3
"""Find every remaining unpointed full3 chain with an exact own-locality provider point."""
from __future__ import annotations
import hashlib,json,re,sys
from collections import Counter,defaultdict
from pathlib import Path
import pandas as pd, duckdb
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,distance_km
from measure_event_aware_path_union_20261005 import SELECTED
OUT=Path(__file__).resolve().parent
TOCHNO=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
CSV=OUT/'remaining_point_use_delta.csv'; CONTEXT=OUT/'source_context.csv'; HELD=OUT/'held_candidates.csv'; RECEIPT=OUT/'receipt.json'
STATION_PREFIXES=[r'^при станции\s+',r'^станции\s+',r'^станция\s+',r'^железнодорожной станции\s+',r'^железнодорожного разъезда\s+',r'^железнодорожном разъезде\s+',r'^разъезда\s+',r'^при железнодорожной станции\s+']
LOCALITY_TYPES={'село','деревня','поселок','пгт','поселок городского типа','станица','аул','улус','арбан','аал','слобода','починок','выселок','заимка','местечко','сельский поселок','городской поселок','населенный пункт'}

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def code(v):
 if pd.isna(v):return ''
 s=str(v).strip()
 return s[:-2] if s.endswith('.0') else s
def aliases(name):
 n=normalize(name);out={n}
 for pat in STATION_PREFIXES:out.add(re.sub(pat,'',n))
 return {x for x in out if x and x!=n} | {n}
def compatible(target,source):
 t,s=normalize(target),normalize(source)
 if t in {'поселок','поселок городского типа'}:return s=='поселок' or s.startswith('поселок ') or s in {'сельский поселок','поселок городского типа'}
 if t=='пгт':return s=='поселок городского типа'
 if t=='населенный пункт':return s in {'населенный пункт','поселок','село','деревня','станция'}
 return t==s

def get_candidates(state):
 obs=state.obs.copy();obs['root']=obs.source_record_id.map(state.uf.find);strict=[]
 for root,g in obs.groupby('root',sort=False):
  years=state.years[state.uf.find(root)]
  if years!={2002,2010,2021} or len(g)!=3 or set(g.census_year.astype(int))!={2002,2010,2021}:continue
  if any(str(sid) in state.point_rows for sid in g.source_record_id):continue
  cur=g[g.census_year.astype(int).eq(2021)]
  if len(cur)!=1:continue
  strict.append((sum(int(x) for x in g.population if pd.notna(x)),root,g,cur.iloc[0]))
 return sorted(strict,key=lambda x:(-x[0],str(x[1])))

def main():
 state=load(stage=8);baseline=state.metrics();strict=get_candidates(state)
 # The graph loader keeps normalized region keys for linkage. Provider tuple
 # admission must compare against the selected row's raw region label.
 current_ids=[str(cur.source_record_id) for _,_,_,cur in strict]
 selcon=duckdb.connect(config={'threads':1,'memory_limit':'1GB'})
 selected=selcon.execute("SELECT source_record_id,region_raw,district_raw FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))",[str(SELECTED),current_ids]).fetchdf()
 selected.source_record_id=selected.source_record_id.astype(str);selected_idx=selected.set_index('source_record_id')
 provider=duckdb.connect(config={'threads':1,'memory_limit':'1GB'}).execute("SELECT file_row_number,object_level,settlement_dadata,settlement_type_full_dadata,region,fias_level_dadata,qc_geo_dadata,oktmo,latitude_dadata,longitude_dadata FROM read_parquet(?,file_row_number=true) WHERE object_level='Населенный пункт' AND fias_level_dadata=6 AND qc_geo_dadata=3 AND latitude_dadata IS NOT NULL AND longitude_dadata IS NOT NULL",[str(TOCHNO)]).fetchdf()
 fias4_city_rows=duckdb.connect(config={'threads':1,'memory_limit':'1GB'}).execute("SELECT count(*) FROM read_parquet(?) WHERE fias_level_dadata='4' AND qc_geo_dadata=3 AND latitude_dadata IS NOT NULL AND longitude_dadata IS NOT NULL",[str(TOCHNO)]).fetchone()[0]
 provider['coord']=[(float(a),float(b)) for a,b in zip(provider.latitude_dadata,provider.longitude_dadata)]
 tuple_index=defaultdict(list)
 for _,r in provider.iterrows():tuple_index[(normalize(r.settlement_dadata),normalize(r.settlement_type_full_dadata),normalize(r.region))].append(r)
 raw_coords=defaultdict(set)
 for _,r in state.obs[state.obs.census_year.astype(int).eq(2021)].iterrows():
  if pd.notna(r.latitude) and pd.notna(r.longitude):raw_coords[(float(r.latitude),float(r.longitude))].add(str(r.source_record_id))
 point_coords=defaultdict(set)
 for sid,p in state.point_rows.items():
  root=state.uf.find(str(sid));
  if 2021 in state.years[root]:point_coords[(float(p['latitude']),float(p['longitude']))].add(root)
 provisional=[];held=[];reason_counts=Counter()
 for rank,(mass,root,g,cur) in enumerate(strict,1):
  current_id=str(cur.source_record_id);ref=selected_idx.loc[current_id]
  target_name=str(cur.settlement_name);target_type=str(cur.settlement_type);region=normalize(ref.region_raw)
  target_lat,target_lon=cur.latitude,cur.longitude;oktmo=code(cur.oktmo)
  if normalize(target_type) not in LOCALITY_TYPES:
   held.append({'rank':rank,'source_record_id':str(cur.source_record_id),'name':target_name,'region':region,'reason':'nonpreferred_or_unknown_locality_type'});reason_counts['nonpreferred_or_unknown_locality_type']+=1;continue
  matches=[]; reasons=[]
  for alias in aliases(target_name):
   # Full provider name/type/region tuple must itself be unique in own-locality rows.
   keys=[k for k in tuple_index if k[0]==alias and k[2]==region]
   for key in keys:
    records=tuple_index[key]
    if len(records)!=1:
     reasons.append('provider_name_type_region_tuple_not_unique');continue
    p=records[0]
    if not compatible(target_type,p.settlement_type_full_dadata):
     reasons.append('provider_locality_type_disagrees');continue
    if code(p.oktmo)!=oktmo:
     reasons.append('provider_oktmo_disagrees');continue
    matches.append((key,p))
  # Remove repeated representations of the same exact source record.
  uniq={int(p.file_row_number):(k,p) for k,p in matches}
  matches=list(uniq.values())
  if len(matches)!=1:
   reason=('no_unique_exact_provider_tuple' if not matches else 'multiple_exact_provider_alias_matches')
   if reasons:reason=reasons[0] if not matches else reason
   held.append({'rank':rank,'source_record_id':str(cur.source_record_id),'name':target_name,'region':region,'reason':reason,'details':' | '.join(sorted(set(reasons)))});reason_counts[reason]+=1;continue
  key,p=matches[0];lat,lon=p.coord
  if pd.isna(target_lat) or pd.isna(target_lon):
   held.append({'rank':rank,'source_record_id':str(cur.source_record_id),'name':target_name,'region':region,'reason':'selected_2021_coordinate_missing'});reason_counts['selected_2021_coordinate_missing']+=1;continue
  d=distance_km((lat,lon),(float(target_lat),float(target_lon)))
  if d>0.05:
   held.append({'rank':rank,'source_record_id':str(cur.source_record_id),'name':target_name,'region':region,'reason':'provider_point_more_than_50m_from_selected_2021','details':f'{d:.3f} km'});reason_counts['provider_point_more_than_50m_from_selected_2021']+=1;continue
  provisional.append({'rank':rank,'mass':mass,'root':root,'group':g,'current':cur,'provider':p,'lat':lat,'lon':lon,'tuple':key,'distance_km':d})
 # Do not invent offsets for coordinates shared by distinct current census objects or accepted points.
 coord_groups=defaultdict(list)
 for x in provisional:coord_groups[(x['lat'],x['lon'])].append(x)
 ready=[]
 for x in provisional:
  own=set(x['group'].source_record_id.astype(str));coord=(x['lat'],x['lon']);colliders=(raw_coords.get(coord,set())-own)
  accepted_other=point_coords.get(coord,set())-{x['root']}
  if len(coord_groups[coord])>1 or colliders or accepted_other:
   reason='new_point_shared_in_selected_current_coordinates' if colliders or len(coord_groups[coord])>1 else 'new_point_shared_with_accepted_current_point'
   held.append({'rank':x['rank'],'source_record_id':str(x['current'].source_record_id),'name':str(x['current'].settlement_name),'region':normalize(x['current'].region_norm),'reason':reason,'details':f'raw_current_ids={sorted(colliders)}; accepted_roots={len(accepted_other)}; staged_same_coord={len(coord_groups[coord])}'})
   reason_counts[reason]+=1;continue
  ready.append(x)
 rows=[];context=[]
 provider_sha=sha(TOCHNO);selected_sha=sha(SELECTED)
 for x in ready:
  g=x['group'];current=x['current'];p=x['provider'];sid=str(current.source_record_id)
  locator=(f"file_row_number={int(p.file_row_number)} (0-based); settlement_dadata={p.settlement_dadata}; settlement_type_full_dadata={p.settlement_type_full_dadata}; region={p.region}; object_level={p.object_level}; fias_level_dadata={p.fias_level_dadata}; qc_geo_dadata={p.qc_geo_dadata}; oktmo={code(p.oktmo)}")
  for _,t in g.sort_values('census_year').iterrows():
   y=int(t.census_year);direct=y==2021
   origin=(f"Direct own-locality point from exact Tochno/DaData name, compatible type, region and OKTMO source tuple; object_level=Населенный пункт, FIAS6/QC geo3; provider point is within 50 m of selected 2021 coordinate. Provider ID binding is separate and unasserted." if direct else f"Retrospective spatial continuity inference from the accepted 2021 own-locality point over the already accepted full same_place chain; this old record has no historical point measurement. Provider ID binding is separate and unasserted.")
   rows.append({'target_source_record_id':str(t.source_record_id),'target_year':y,'latitude':x['lat'],'longitude':x['lon'],'source':str(TOCHNO),'source_sha256':provider_sha,'source_locator':locator,'coordinate_source_record_id':sid,'coordinate_admission_status':'reviewed_case_accepted','coordinate_quality':'own_locality_provider_point_current_2021' if direct else 'retrospective_full_chain_spatial_continuity','provider_binding_asserted':False,'provider_binding_separate':True,'coordinate_origin_kind':'direct_exact_provider_own_locality' if direct else 'accepted_same_place_spatial_continuity_inference','retrospective_old_record_id':not direct,'origin':origin})
  ref=selected_idx.loc[str(current.source_record_id)]
  context.append({'rank_by_three_year_population':x['rank'],'population_sum_2002_2010_2021':x['mass'],'name_2021':str(current.settlement_name),'type_2021':str(current.settlement_type),'region_2021':str(ref.region_raw),'district_2021':str(ref.district_raw),'oktmo_2021':code(current.oktmo),'selected_2021_latitude':current.latitude,'selected_2021_longitude':current.longitude,'provider_latitude':x['lat'],'provider_longitude':x['lon'],'provider_selected_distance_km':round(x['distance_km'],6),'provider_tuple_name':p.settlement_dadata,'provider_tuple_type':p.settlement_type_full_dadata,'provider_tuple_region':p.region,'provider_oktmo':code(p.oktmo),'object_level':p.object_level,'fias_level_dadata':p.fias_level_dadata,'qc_geo_dadata':p.qc_geo_dadata,'provider_row_locator':locator,'provider_file_row_number':int(p.file_row_number),'source_record_ids_2002_2010_2021':' | '.join(g.sort_values('census_year').source_record_id.astype(str)),'provider_binding_asserted':False,'provider_binding_separate':True})
 frame=pd.DataFrame(rows);ctx=pd.DataFrame(context);heldf=pd.DataFrame(held)
 if frame.target_source_record_id.duplicated().any():raise RuntimeError('duplicate target point use')
 if not frame.provider_binding_asserted.eq(False).all():raise RuntimeError('external provider binding must remain unasserted')
 frame.to_csv(CSV,index=False);ctx.to_csv(CONTEXT,index=False);heldf.to_csv(HELD,index=False)
 after=state.metrics(extra_point_ids=frame.target_source_record_id.astype(str).tolist())
 graph_inputs={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in state.inputs}
 receipt={'status':'staged_remaining_sourceable_full_chain_provider_points','stage':8,'full3_unpointed_components_examined':len(strict),'components_with_unique_eligible_provider_points':len(provisional),'components_held_before_collision_screen':len(strict)-len(provisional),'components_held_for_shared_coordinates':len(provisional)-len(ready),'components_ready':len(ready),'point_use_rows':len(frame),'held_reason_counts':dict(reason_counts),'fias4_qc3_point_rows_screened':int(fias4_city_rows),'source_inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SELECTED,TOCHNO]},'working_state_inputs':graph_inputs,'source_context_sha256':sha(CONTEXT),'held_candidates_sha256':sha(HELD),'point_use_delta_sha256':sha(CSV),'build_script_sha256':sha(Path(__file__)),'provider_binding_asserted':False,'provider_binding_separate':True,'coverage_before':baseline,'coverage_after_staged':after,'population_gain_by_year':{y:after[y]['covered_population']-baseline[y]['covered_population'] for y in baseline},'rules':{'component':'stage-8 working_state_20261007; complete 2002/2010/2021 component, exactly one selected row per year, no accepted point in component','provider':'own-locality object level, FIAS level 6, QC geo 3; unique full normalized provider tuple (locality label, type, region), compatible source type, exact region and selected OKTMO; station-name introduction aliases only; provider coordinates within 50m of the selected 2021 raw coordinate','fias4':'screened source for QC-geo-3 FIAS-level-4 point rows; none available in this provider file, so no FIAS4 city point admitted','collision':'withhold a candidate if exact coordinate is shared by another selected 2021 raw object, another staged source candidate, or an accepted full-chain point; no offset/coordinate perturbation','old_years':'same point extended to 2002/2010 only as retrospective inference over accepted identity; no provider identifier binding or historical point measurement'}}
 RECEIPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'full3_unpointed_examined':len(strict),'unique_provider_candidates':len(provisional),'collision_holds':len(provisional)-len(ready),'sourceable_components':len(ready),'point_rows':len(frame),'held_reasons':dict(reason_counts),'population_gain':receipt['population_gain_by_year']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
