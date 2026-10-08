#!/usr/bin/env python3
"""One frozen stage61 State replay; source-bound ownpoints and native identity."""
from pathlib import Path
import sys,json,math,time,hashlib,collections,base64
import pandas as pd
import duckdb
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;M=ROOT/'research_rebuild/mass_linkage';E=ROOT/'research_rebuild/evidence';REPORT=E/'working_full_chain_20261007'
sys.path.insert(0,str(M))
from current_chain_state_20261007 import sha,distance_km
from build_long_table import ACCEPTED_COORDINATE_STATUSES,ACCEPTED_EDGE_STATUSES,UnionFind
START=time.monotonic();PINS={}
def pin(p,expected=None):
 p=Path(p);s=str(p)
 if s not in PINS:PINS[s]={'sha256':sha(p),'bytes':p.stat().st_size}
 if expected is not None:assert PINS[s]['sha256']==expected,(s,expected,PINS[s])
 return p
def read(p):return pd.read_csv(pin(p),dtype=str,keep_default_na=False)
def receipt(p):
 r=json.loads(pin(p).read_text());assert r['baseline_stage']==61
 for q,h in r.get('input_pins',{}).items():pin(q,h)
 for q,h in r.get('output_pins',{}).items():pin(p.parent/q,h['sha256'] if isinstance(h,dict) else h)
 return r
CURRENT=E/'current_missing_point_mass_20261008';TEMP=E/'temporal_residual_mass_20261008'
# No replay starts until the final temporal admission packet exists.
assert (TEMP/'admission_receipt.json').is_file(),'Temporal packet not ready; do not start State load.'
initial=receipt(CURRENT/'receipt.json');screen=receipt(CURRENT/'initial_component_screen_receipt.json');provider=receipt(CURRENT/'provider_lexical_receipt.json');temporal=receipt(TEMP/'admission_receipt.json');article=receipt(CURRENT/'top4_article_acceptance_receipt.json');extended=receipt(CURRENT/'extended_P31_receipt.json');extended_screen=receipt(CURRENT/'extended_P31_component_screen_receipt.json')
assert screen['screened_accepted']==752 and provider['accepted_current_ownpoints']==191
assert temporal['status']=='sourcebound_temporal_admission_packet_ready_for_canonical_root_replay'
point_paths=[CURRENT/'accepted_point_use_delta_component_screened.csv.gz',CURRENT/'accepted_provider_lexical_point_use_delta.csv.gz',CURRENT/'accepted_top4_article_point_use_delta.csv.gz',CURRENT/'accepted_extended_P31_point_use_delta_component_screened.csv.gz',TEMP/'accepted_point_use_delta.csv.gz']
pointframes=[read(p) for p in point_paths];assert list(map(len,pointframes))==[752,191,article['accepted_current_ownpoints'],100,temporal['accepted_continuity_point_uses']]
edges=read(TEMP/'accepted_identity_edge_delta.csv.gz');assert len(edges)==temporal['accepted_edges']
for f in pointframes:
 assert f.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all()
 for q,h in set(zip(f.point_origin_file,f.point_origin_sha256)):
  assert q and h;pin(q,h)
assert edges.decision_status.isin(ACCEPTED_EDGE_STATUSES).all() and edges.relation.eq('same_place').all()
# Freeze HEAD fde535a loader bytes, compile at canonical path so relative resource paths retain their exact meaning.
loader=pin(OUT/'frozen_stage61_loader.py');api=pin(OUT/'frozen_State_API.py');pin(M/'current_chain_state_20261007.py',sha(api))
namespace={'__file__':str(M/'working_state_20261007.py'),'__name__':'frozen_primary_application_loader'}
exec(compile(loader.read_text(),namespace['__file__'],'exec'),namespace)
RESTORED='--restore-certified-snapshot' in sys.argv
if RESTORED:
 from current_chain_state_20261007 import State
 from measure_event_aware_path_union_20261005 import SELECTED,POINTS,POINT_DELTAS
 sr=json.loads(pin(TEMP/'state_snapshot_receipt.json').read_text());assert sr['baseline_stage']==61 and sr['canonical_loader_validated']
 for q,h in sr['source_input_pins'].items():pin(q,h['sha256'])
 cp=TEMP/'SHARED_component_snapshot_stage61.csv.gz';pp=TEMP/'SHARED_points_compact_stage61.parquet'
 for q in [cp,pp]:pin(q,sr['output_pins'][q.name]['sha256'])
 cs=read(cp);pf=pd.read_parquet(pp).fillna('').astype(str);assert cs.source_record_id.is_unique and pf.source_record_id.is_unique
 c=duckdb.connect(config={'threads':1,'memory_limit':'512MB'})
 columns='source_record_id,census_year,settlement_name,settlement_type,name_norm,type_norm,region_norm,district_raw,population,population_scope,is_additive_settlement_record,population_value_quality,latitude,longitude,oktmo,okato,source_file,source_path,source_sha256,source_locator'
 state=State.__new__(State);state.obs=c.execute('SELECT '+columns+' FROM read_parquet(?)',[str(SELECTED)]).fetchdf()
 state.by_id=state.obs.set_index('source_record_id',drop=False);state.inputs=[]
 namespace['apply_source_namespace_interpretations'](state,E/'eaoregion_source_namespace_mass_20261008/source_namespace_interpretation_delta.csv')
 state.uf=UnionFind(state.obs.source_record_id);assert set(cs.source_record_id)==set(state.obs.source_record_id)
 for r,g in cs.groupby('root'):
  for sid in g.source_record_id:state.uf.union(r,sid)
 state.obs['root']=state.obs.source_record_id.map(state.uf.find);assert dict(zip(cs.source_record_id,cs.root))==dict(zip(state.obs.source_record_id,state.obs.root))
 state.years={r:set(map(int,g.census_year)) for r,g in state.obs.groupby('root')};assert all(len(y)<=3 for y in state.years.values())
 assert cs.component_years.tolist()==[','.join(map(str,sorted(state.years[state.uf.find(sid)]))) for sid in cs.source_record_id]
 point_columns=['target_source_record_id','latitude','longitude','carrier_latitude','carrier_longitude','coordinate_admission_status','coordinate_source_record_id','source_sha256','source_locator','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']
 state.point_rows={};oldpaths={str(POINTS)}|{str(q) for q in POINT_DELTAS}
 for ledger,g in pf.groupby('point_ledger_path'):
  q=Path(ledger);pin(q)
  if q.suffix=='.parquet':
   available={r[0] for r in c.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(q)]).fetchall()};frame=c.execute('SELECT '+','.join(k for k in point_columns if k in available)+' FROM read_parquet(?) WHERE coordinate_admission_status IN (SELECT UNNEST(?))',[str(q),sorted(ACCEPTED_COORDINATE_STATUSES)]).fetchdf()
  else:frame=pd.read_csv(q,dtype=str,keep_default_na=False,usecols=(lambda k:k in point_columns) if ledger in oldpaths else None)
  ids=set(g.source_record_id);frame=frame[frame.target_source_record_id.isin(ids)];assert not frame.target_source_record_id.duplicated().any()
  bytarget=frame.set_index('target_source_record_id',drop=False).to_dict('index')
  for expected in g.to_dict('records'):
   sid=expected['source_record_id'];row=bytarget[sid]
   if 'latitude' not in row:row['latitude'],row['longitude']=row['carrier_latitude'],row['carrier_longitude']
   row['latitude'],row['longitude']=float(row['latitude']),float(row['longitude']);row['point_ledger_path']=ledger
   for field in ['coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator','point_origin_kind']:
    actual=row.get(field,'');actual='' if pd.isna(actual) else str(actual);assert actual==expected[field],(sid,field,actual,expected[field])
   assert (row['latitude'],row['longitude'])==(float(expected['latitude']),float(expected['longitude']))
   state.point_rows[sid]=row
 state.inputs=[Path(q) for q in sr['source_input_pins']];state.point_alternatives=[];state.conflicting_point_targets=set(sr['conflicting_point_targets']);c.close()
 assert len(state.point_rows)==sr['point_rows'] and state.metrics()==sr['metrics']
else:state=namespace['load'](stage=61)
for p in state.inputs:pin(p)
# Historical transferred points retain source carrier binding and explicit continuity semantics.
for row in pointframes[-1].to_dict('records'):
 sid=row['target_source_record_id'];year=int(state.by_id.loc[sid,'census_year'])
 if year<2021:
  assert row.get('historical_census_coordinate_asserted','False')=='False'
  assert 'modern_own_representative_point_reused_through_' in row.get('point_use_inference','') or 'continuity' in row.get('point_use_inference','')
  carriers=[(i,p) for i,p in state.point_rows.items() if p.get('point_origin_file')==row['point_origin_file'] and p.get('point_origin_sha256')==row['point_origin_sha256'] and (float(p['latitude']),float(p['longitude']))==(float(row['latitude']),float(row['longitude']))]
  assert carriers,'Historical transferred point lacks an active reviewed ownpoint carrier'
protected=state.obs.copy(deep=True);ordinary=state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((state.obs.census_year==2021)&state.obs.region_norm.eq('крым'))].copy()
sidecarsets={}
for key,name in [('partition','complete_publisher_partition_members.csv'),('qualified','qualified_scope_source_id_credit_union.csv'),('named','named_merger_lineage_constituents.csv'),('territorial','complete_territorial_scope_constituents.csv'),('direct','direct_inclusion_transformation_path_native_credit_union.csv'),('formation','formation_path_native_credit_union.csv')]:sidecarsets[key]=set(read(REPORT/name).source_record_id)-{''}
sidecar=set().union(*sidecarsets.values());common={2002:145166731,2010:142856536,2021:144699673};federal={2002:15043973,2010:16383067,2021:18612023};external={2002:11726,2010:493512,2021:0}
registry=json.loads(pin(E/'main_axis_residual_registry_20261008/receipt.json').read_text());baseline=json.loads(pin(REPORT/'coverage_receipt.json').read_text());assert baseline['working_stage']==61

def axes(additional_credit_ids=()):
 fullroots={r for r,y in state.years.items() if y=={2002,2010,2021}};allroots=set(fullroots)
 for sid in state.obs.source_record_id:
  if state.uf.find(sid) in allroots and sid not in state.point_rows:allroots.discard(state.uf.find(sid))
 blocked={state.uf.find(sid) for sid,pop in state.obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(pop) or not math.isfinite(float(pop))}
 allids={sid for sid in state.obs.source_record_id if state.uf.find(sid) in allroots};finite={sid for sid in allids if state.uf.find(sid) not in blocked};credited=finite|sidecar|set(additional_credit_ids);metrics={}
 for y,g in ordinary.groupby('census_year'):
  y=int(y);a=g[g.source_record_id.isin(allids)];f=g[g.source_record_id.isin(finite)];c=g[g.source_record_id.isin(credited)];left=g[~g.source_record_id.isin(credited)]
  total=int(c.population.sum())+federal[y];assert total+int(left.population.sum())+external[y]==common[y]
  metrics[str(y)]={'ordinary_all3_ownpoints_rows':len(a),'ordinary_all3_ownpoints_population':int(a.population.sum()),'ordinary_all3_ownpoints_unknown_rows':int(a.population.isna().sum()),'finite_all3_ownpoints_rows':len(f),'finite_all3_ownpoints_population':int(f.population.sum()),'primary_selected_UID_rows':len(c),'primary_axis_population':total,'remaining_primary_UID_rows':len(left),'remaining_primary_population':int(left.population.sum()),'remaining_unknown_rows':int(left.population.isna().sum()),'external_control_deficit_unallocated':external[y],'common_control':common[y],'percent_common_control':100*total/common[y]}
 return metrics,finite,credited
LIFE=E/'largest_lifecycle_residual_20261008'
life_receipt=json.loads(pin(LIFE/'packet_receipt.json').read_text())
assert life_receipt['status']=='reviewed_bounded_own_appearance_packet_root_replay_pending'
for q,h in life_receipt['input_pins'].items():pin(q,h)
for q,h in life_receipt['output_pins'].items():pin(LIFE/q,h['sha256'] if isinstance(h,dict) else h)
life_credits=read(LIFE/'accepted_source_UID_credit_union.csv');life_obs=read(LIFE/'accepted_own_sourceyear_observations.csv');life_points=read(LIFE/'accepted_own_point_references.csv');life_statuses=read(LIFE/'accepted_available_year_statuses.csv');life_context=read(LIFE/'actual_parent_city_three_year_context_only.csv')
life_ids=set(life_credits.source_record_id);assert len(life_credits)==len(life_ids)==4 and life_ids==set(life_obs.source_record_id)==set(life_points.target_source_record_id)
original_residual=set(read(E/'main_axis_residual_registry_20261008/primary_axis_remaining_source_records.csv.gz').source_record_id);assert life_ids<=original_residual
assert life_credits.ordinary_three_census_same_place_claim.eq('False').all() and life_credits.is_additive_to_original_final_mixed_census_axis.eq('False').all()
assert life_statuses.unknown_is_zero.eq('False').all() and life_statuses.parent_population_is_own.eq('False').all()
assert life_statuses.loc[~life_statuses.status.eq('actual_own_published_observation'),'own_population'].eq('').all()
for row in life_obs.to_dict('records'):
 native=state.by_id.loc[row['source_record_id']];assert int(native.census_year)==int(row['year']) and math.isfinite(float(native.population)) and float(native.population)==float(row['native_population']) and native.population_value_quality==row['native_population_quality']
for row in life_points.to_dict('records'):
 active=state.point_rows[row['target_source_record_id']];assert row['own_point_existing_accepted']=='True' and row['new_point_admission']=='False'
 assert (active['latitude'],active['longitude'])==(float(row['latitude']),float(row['longitude'])) and active['point_origin_file']==row['point_origin_file'] and active['point_origin_sha256']==row['point_origin_sha256']
 pin(row['point_origin_file'],row['point_origin_sha256'])
if 'source_record_id' in life_context:assert not set(life_context.source_record_id)&life_ids
assert pd.to_numeric(life_context.new_source_UID_credit).eq(0).all() and life_context.context_only.eq('True').all() and life_context.parent_count_copied_to_child.eq('False').all()
for name in ['accepted_source_UID_credit_union.csv','accepted_available_year_statuses.csv','accepted_own_sourceyear_observations.csv','accepted_own_point_references.csv','accepted_typed_context_edges.csv','actual_parent_city_three_year_context_only.csv']:
 (OUT/f'appearance_{name}').write_bytes((LIFE/name).read_bytes())
before,bfinite,bcredited=axes();before_state_metrics=state.metrics();before_point_targets=set(state.point_rows)
for y,z in before.items():
 assert z['primary_axis_population']==registry['by_year'][y]['primary_axis_population']==baseline['separate_sourceyear_formation_plus_direct_lifecycle_axis']['by_year'][y]['lifecycle_plus_formation_population']
 assert z['ordinary_all3_ownpoints_population']==baseline['ordinary_axes_by_year'][y]['axes']['full_three_census_with_all_component_points']['population']
 assert z['finite_all3_ownpoints_rows']==baseline['ordinary_complete_number_export']['rows']
# Preflight all supplied deltas before a canonical State mutation. Hard constraints produce explicit holds.
holds=[];merged={};accepted_points=[]
current_occupation=collections.defaultdict(set)
for sid,p in state.point_rows.items():
 if int(state.by_id.loc[sid,'census_year'])==2021:current_occupation[(float(p['latitude']),float(p['longitude']))].add(sid)
for path,frame in zip(point_paths,pointframes):
 for row in frame.to_dict('records'):
  sid=row['target_source_record_id'];lat=float(row['latitude']);lon=float(row['longitude']);reason=''
  assert sid in state.by_id.index and -90<=lat<=90 and -180<=lon<=180
  if sid in merged:
   old=merged[sid]
   if (float(old['latitude']),float(old['longitude']))!=(lat,lon):reason='duplicate supplied target has nonidentical point; no automatic confidence choice'
   else:holds.append({'kind':'point','source_record_id':sid,'input_path':str(path),'reason':'exact duplicate target/coordinates already merged'});continue
  if int(state.by_id.loc[sid,'census_year'])==2021 and current_occupation.get((lat,lon),set())-{sid}:reason='new own2021 point occupied by a distinct accepted or supplied current source ID'
  if sid in state.point_rows and distance_km((lat,lon),(state.point_rows[sid]['latitude'],state.point_rows[sid]['longitude']))>5:reason='supplied ownpoint contradicts active accepted target >5km'
  if not reason:
   root=state.uf.find(sid)
   for other in state.obs.loc[state.obs.root.eq(root),'source_record_id']:
    if other in state.point_rows and distance_km((lat,lon),(state.point_rows[other]['latitude'],state.point_rows[other]['longitude']))>5:reason='supplied ownpoint contradicts ownpoint in existing identity component >5km';break
  if reason:holds.append({'kind':'point','source_record_id':sid,'input_path':str(path),'reason':reason});continue
  row['integration_input_path']=str(path);merged[sid]=row
  if int(state.by_id.loc[sid,'census_year'])==2021:current_occupation[(lat,lon)].add(sid)
accepted_points=list(merged.values())
uf=UnionFind(state.obs.source_record_id);yearsets={};coordsets={}
for sid in state.obs.source_record_id:
 r=state.uf.find(sid);uf.union(r,sid)
for r,ys in state.years.items():yearsets[uf.find(r)]=set(ys)
for sid,p in state.point_rows.items():coordsets.setdefault(uf.find(sid),[]).append((p['latitude'],p['longitude']))
for sid,p in merged.items():coordsets.setdefault(uf.find(sid),[]).append((float(p['latitude']),float(p['longitude'])))
accepted_edges=[]
for row in edges.to_dict('records'):
 a,b=row['from_source_record_id'],row['to_source_record_id'];assert a in state.by_id.index and b in state.by_id.index;ra,rb=uf.find(a),uf.find(b);reason=''
 if ra==rb:reason='duplicate graph connectivity already supplied'
 elif yearsets[ra]&yearsets[rb]:reason='same-place delta repeats census year'
 elif any(distance_km(x,y)>5 for x in coordsets.get(ra,[]) for y in coordsets.get(rb,[])):reason='joined component has ownpoint contradiction >5km'
 if reason:holds.append({'kind':'edge','source_record_id':a,'to_source_record_id':b,'reason':reason});continue
 ys=yearsets[ra]|yearsets[rb];coords=coordsets.get(ra,[])+coordsets.get(rb,[]);uf.union(ra,rb);r=uf.find(ra);yearsets.pop(ra,None);yearsets.pop(rb,None);yearsets[r]=ys;coordsets.pop(ra,None);coordsets.pop(rb,None);coordsets[r]=coords;accepted_edges.append(row)
# Drop retrospective points tied to a newly held identity edge unless target was already ordinary full3.
heldedgeids={h['source_record_id'] for h in holds if h['kind']=='edge'}|{h.get('to_source_record_id') for h in holds if h['kind']=='edge'}
if heldedgeids:
 for sid in list(merged):
  if merged[sid]['integration_input_path']==str(point_paths[-1]) and state.years[state.uf.find(sid)]!={2002,2010,2021} and uf.find(sid) not in {uf.find(r['from_source_record_id']) for r in accepted_edges}:
   holds.append({'kind':'point','source_record_id':sid,'reason':'retrospective continuity has no newly admitted edge or preexisting full3'});merged.pop(sid)
accepted_points=list(merged.values());pointout=OUT/'accepted_point_use_delta.csv.gz';edgeout=OUT/'accepted_identity_edge_delta.csv.gz'
(pd.DataFrame(accepted_points) if accepted_points else pd.DataFrame(columns=['target_source_record_id','latitude','longitude','coordinate_admission_status'])).to_csv(pointout,index=False,compression={'method':'gzip','mtime':0})
(pd.DataFrame(accepted_edges) if accepted_edges else edges.iloc[:0]).to_csv(edgeout,index=False,compression={'method':'gzip','mtime':0})
state.add_deltas(edge_paths=[edgeout],point_paths=[pointout])
ordinary['root']=ordinary.source_record_id.map(state.uf.find)
after_core,afinite,corecredited=axes();after,_,acredited=axes(life_ids);after_state_metrics=state.metrics();life_gain={y:after[y]['primary_axis_population']-after_core[y]['primary_axis_population'] for y in after};assert life_gain=={'2002':0,'2010':6333,'2021':24808}
assert state.obs.drop(columns=['root']).equals(protected.drop(columns=['root'])),'Native source values/qualities/names/codes changed'
uid_by_root={}
for r,g in state.obs[state.obs.source_record_id.isin(afinite)].groupby('root'):
 ordered=g.sort_values('census_year').source_record_id.tolist();assert len(ordered)==3
 encoded=json.dumps(ordered,ensure_ascii=False,separators=(',',':'));uid_by_root[r]='np3:'+base64.urlsafe_b64encode(hashlib.sha256(encoded.encode()).digest()).decode().rstrip('=')
credited_rows=ordinary[ordinary.source_record_id.isin(acredited)][['source_record_id','census_year','population','population_value_quality']].copy();credited_rows['component_root']=credited_rows.source_record_id.map(state.uf.find);credited_rows['entity_uid']=credited_rows.component_root.map(uid_by_root).fillna('');credited_rows['finite_ordinary_full3_all_ownpoints']=credited_rows.source_record_id.isin(afinite);credited_rows['explicit_appearance_publication_absence_credit']=credited_rows.source_record_id.isin(life_ids);credited_rows.to_csv(OUT/'applied_primary_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
changed=ordinary[ordinary.source_record_id.isin(acredited-bcredited)].copy();assert not bcredited-acredited
changed[['source_record_id','census_year','settlement_name','region_norm','population','population_value_quality']].to_csv(OUT/'actual_newly_credited_primary_source_IDs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
remaining=ordinary[~ordinary.source_record_id.isin(acredited)].copy();remaining['has_own_point']=remaining.source_record_id.isin(state.point_rows);remaining['component_years']=remaining.source_record_id.map(lambda sid:','.join(map(str,sorted(state.years[state.uf.find(sid)]))));remaining=remaining.sort_values(['population','source_record_id'],ascending=[False,True],na_position='last');remaining.to_csv(OUT/'applied_remaining_primary.csv.gz',index=False,compression={'method':'gzip','mtime':0})
for y,g in remaining.groupby('census_year'):g.head(20).to_csv(OUT/f'top20_applied_remaining_primary_{int(y)}.csv',index=False)
pd.DataFrame(holds,columns=['kind','source_record_id','to_source_record_id','input_path','reason']).to_csv(OUT/'integration_holds.csv',index=False)
# Compact state snapshot enables continuation without another State load.
cs=state.obs[['source_record_id','root']].copy();cs['root']=cs.source_record_id.map(state.uf.find);cs['has_own_point']=cs.source_record_id.isin(state.point_rows);cs.to_csv(OUT/'applied_component_snapshot.csv.gz',index=False,compression={'method':'gzip','mtime':0})
pd.DataFrame([{'source_record_id':sid,**p} for sid,p in state.point_rows.items()]).fillna('').astype(str).to_parquet(OUT/'applied_point_snapshot.parquet',index=False,compression='zstd')
back=read(OUT/'applied_remaining_primary.csv.gz');assert back.source_record_id.is_unique and set(back.source_record_id)==set(remaining.source_record_id)
gain={y:{'newly_credited_source_IDs':int(changed.census_year.eq(int(y)).sum()),'net_primary_population_gain':after[y]['primary_axis_population']-before[y]['primary_axis_population'],'net_finite_all3_ownpoint_population_gain':after[y]['finite_all3_ownpoints_population']-before[y]['finite_all3_ownpoints_population'],'new_finite_all3_ownpoint_histories':after[y]['finite_all3_ownpoints_rows']-before[y]['finite_all3_ownpoints_rows']} for y in before}
for y,z in gain.items():assert z['net_primary_population_gain']==int(changed.loc[changed.census_year.eq(int(y)),'population'].sum())
outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file() and p.name!='application_receipt.json'}
r={'status':'applied_actual_frozen61_sourcebound_native_identity_and_ownpoint_core_batch','baseline_stage':61,'intended_working_stage':62,'frozen_baseline_commit':'fde535a7a284dcabb3581a7bcb2a94c868689371','actual_State_loads':1,'cache_hydration_used':RESTORED,'recovery_note':'First canonical stage61 loader completed; overly literal continuity substring gate failed before application. Recovery hydrates exact source-pinned certified component+point snapshots and full active ledger fields, proves baseline metrics/UID union, then applies canonical State.add_deltas; no second loader.' if RESTORED else '','accepted_edges':len(accepted_edges),'accepted_point_uses':len(accepted_points),'new_unique_point_targets':len(set(state.point_rows)-before_point_targets),'new_point_targets_by_year':{str(y):sum(int(state.by_id.loc[sid,'census_year'])==y for sid in set(state.point_rows)-before_point_targets) for y in [2002,2010,2021]},'changed_primary_unique_source_IDs':len(changed),'input_point_target_overlap_rows':sum(map(len,pointframes))-len(set().union(*[set(f.target_source_record_id) for f in pointframes])),'integration_holds':len(holds),'before':before,'after_core_formation_plus_direct_axis':after_core,'after':after,'primary_with_explicit_appearance_and_publication_absence_axis':after,'appearance_additional_unique_source_ID_population':life_gain,'appearance_native_source_IDs':sorted(life_ids),'appearance_changes_strict_ordinary_axis':False,'actual_gain_by_unique_source_ID_union':gain,'before_State_metrics':before_state_metrics,'after_State_metrics':after_state_metrics,'baseline_reproduced':True,'source_population_quality_names_codes_unchanged':True,'pending_2010_official512_overlay_included':False,'canonical_State_API_replay_passed':True,'all_three_component_points_and_three_finite_populations_required':True,'source_control_deficits_unallocated':external,'input_pins':PINS,'output_pins':outputs,'wall_seconds':round(time.monotonic()-START,3)}
(OUT/'application_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins','before_State_metrics','after_State_metrics']},ensure_ascii=False))
