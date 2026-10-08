#!/usr/bin/env python3
"""Apply finalized64 deltas to certified63 snapshots; no State.load replay."""
from pathlib import Path
import sys,json,hashlib,time,math,collections,base64
import pandas as pd
import duckdb
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];E=ROOT/'research_rebuild/evidence';M=ROOT/'research_rebuild/mass_linkage';BASE=E/'main_axis_residual_application63_20261008'
sys.path.insert(0,str(M))
from current_chain_state_20261007 import State,sha,distance_km
from build_long_table import UnionFind,ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES
from add_source_observations import append_reviewed_source_observations,apply_reviewed_parent_grain,STANDARD_COLUMNS
START=time.monotonic();PINS={};YEARS={2002,2010,2021};COMMON={2002:145166731,2010:142856536,2021:144699673};FED={2002:15043973,2010:16383067,2021:18612023};EXTERNAL={2002:11726,2010:493512,2021:0}
def pin(p,expected=None):
 p=Path(p);k=str(p)
 if k not in PINS:PINS[k]={'sha256':sha(p),'bytes':p.stat().st_size}
 if expected is not None:assert PINS[k]['sha256']==expected,(k,expected,PINS[k])
 return p
def read(p):return pd.read_csv(pin(p),dtype=str,keep_default_na=False)
def receipt(p):
 p=Path(p);r=json.loads(pin(p).read_text())
 for q,h in {**r.get('source_pins',{}),**r.get('input_pins',{})}.items():pin(ROOT/q if not Path(q).is_absolute() and not Path(q).exists() else q,h['sha256'] if isinstance(h,dict) else h)
 for q,h in {**r.get('outputs',{}),**r.get('output_pins',{})}.items():pin(Path(q) if Path(q).is_absolute() else p.parent/q,h['sha256'] if isinstance(h,dict) else h)
 return r
config=json.loads(pin(OUT/'finalized_packets.json').read_text());assert config['all_packets_finalized'] and config['capacity_authorized']
assert config['baseline_commit']=='af70fdf96d45c84c67df5afcdd6a216a10946140'
base=json.loads(pin(BASE/'application_receipt.json','a4933765ec9dd710b56a0bce0a273cd9e801e15707ef6850fe5f6c859a7abd22').read_text());assert base['intended_working_stage']==63 and base['canonical_State_API_replay_passed']
pin(OUT/'frozen_State_API63.py','002dacc1104d79d9330753ec0b5f5c528b62ca69574c7000df2e19fd5d16f76a')
api=pin(OUT/'frozen_State_API64.py','8c3aaa317bd2aff53a4ee40c30c69bbd88de40c22ad8cffbd7524dba941bd1ce');pin(M/'current_chain_state_20261007.py',sha(api))
loader=pin(OUT/'frozen_stage63_loader.py');ns={'__name__':'frozen64_baseline_loader','__file__':str(M/'working_state_20261007.py')};exec(compile(loader.read_text(),ns['__file__'],'exec'),ns)
selected=pin('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet','4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657')
c=duckdb.connect(config={'threads':1,'memory_limit':'512MB'});state=State.__new__(State);state.obs=c.execute('SELECT '+','.join(STANDARD_COLUMNS)+' FROM read_parquet(?)',[str(selected)]).fetchdf();c.close();state.by_id=state.obs.set_index('source_record_id',drop=False);state.inputs=[]
ns['apply_source_namespace_interpretations'](state,E/'eaoregion_source_namespace_mass_20261008/source_namespace_interpretation_delta.csv')
for name in ['applied_component_snapshot.csv.gz','applied_point_snapshot.parquet','applied_primary_credited_UID_roster.csv.gz']:pin(BASE/name,base['output_pins'][name]['sha256'])
cs=read(BASE/'applied_component_snapshot.csv.gz');assert cs.source_record_id.is_unique and set(cs.source_record_id)==set(state.obs.source_record_id)
state.uf=UnionFind(state.obs.source_record_id)
for r,g in cs.groupby('root'):
 for sid in g.source_record_id:state.uf.union(r,sid)
state.obs['root']=state.obs.source_record_id.map(state.uf.find);assert dict(zip(state.obs.source_record_id,state.obs.root))==dict(zip(cs.source_record_id,cs.root))
ys=state.obs.groupby('root').census_year.agg(['size','nunique']);assert ys['size'].eq(ys['nunique']).all() and ys['size'].le(3).all();state.years={r:set(map(int,g)) for r,g in state.obs.groupby('root').census_year}
pf=pd.read_parquet(BASE/'applied_point_snapshot.parquet').fillna('').astype(str);assert pf.source_record_id.is_unique and pf.source_record_id.ne('').all() and len(pf)==443637
state.point_rows={}
for row in pf.to_dict('records'):
 sid=row.pop('source_record_id');row['latitude'],row['longitude']=float(row['latitude']),float(row['longitude']);assert row['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES;state.point_rows[sid]=row
state.point_alternatives=[];state.conflicting_point_targets=set();assert set(state.point_rows)==set(cs.loc[cs.has_own_point.eq('True'),'source_record_id']);assert state.metrics()==base['after_State_metrics']
del pf;protected=state.obs.copy(deep=True);baseline=read(BASE/'applied_primary_credited_UID_roster.csv.gz');baseids=set(baseline.source_record_id);basefinite=set(baseline.loc[baseline.finite_ordinary_full3_all_ownpoints.eq('True'),'source_record_id'])
coremask=~(baseline.explicit_appearance_publication_absence_credit.eq('True')|baseline.explicit_inclusion_credit.eq('True')|baseline.explicit_available_year_lifecycle_round2_credit.eq('True'));coreextra=set(baseline.loc[coremask,'source_record_id'])-basefinite;mainextra=baseids-basefinite
appearance=set(baseline.loc[baseline.explicit_appearance_publication_absence_credit.eq('True'),'source_record_id']);inclusions=set(baseline.loc[baseline.explicit_inclusion_credit.eq('True'),'source_record_id']);round2=set(baseline.loc[baseline.explicit_available_year_lifecycle_round2_credit.eq('True'),'source_record_id'])
def ordinary_rows():return state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((state.obs.census_year==2021)&state.obs.region_norm.eq('крым'))].copy()
def axes(extra):
 roots={r for r,y in state.years.items() if y==YEARS}
 for sid in state.obs.source_record_id:
  if sid not in state.point_rows:roots.discard(state.uf.find(sid))
 blocked={state.uf.find(sid) for sid,p in state.obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(p) or not math.isfinite(float(p))};allids={sid for sid in state.obs.source_record_id if state.uf.find(sid) in roots};finite={sid for sid in allids if state.uf.find(sid) not in blocked};credit=finite|set(extra);out={}
 for y,g in ordinary_rows().groupby('census_year'):
  y=int(y);a=g[g.source_record_id.isin(allids)];f=g[g.source_record_id.isin(finite)];taken=g[g.source_record_id.isin(credit)];left=g[~g.source_record_id.isin(credit)];total=int(taken.population.sum())+FED[y];assert total+int(left.population.sum())+EXTERNAL[y]==COMMON[y]
  out[str(y)]={'ordinary_all3_ownpoints_rows':len(a),'ordinary_all3_ownpoints_population':int(a.population.sum()),'ordinary_all3_ownpoints_unknown_rows':int(a.population.isna().sum()),'finite_all3_ownpoints_rows':len(f),'finite_all3_ownpoints_population':int(f.population.sum()),'primary_selected_UID_rows':len(taken),'primary_axis_population':total,'remaining_primary_UID_rows':len(left),'remaining_primary_population':int(left.population.sum()),'remaining_unknown_rows':int(left.population.isna().sum()),'external_control_deficit_unallocated':EXTERNAL[y],'common_control':COMMON[y],'percent_common_control':100*total/COMMON[y]}
 return out,finite,credit
before,bfinite,bcredit=axes(mainextra);before_core,_,_=axes(coreextra);assert before==base['after'] and before_core==base['after_core_formation_plus_direct_axis'];assert baseids==set(ordinary_rows().loc[ordinary_rows().source_record_id.isin(bcredit),'source_record_id'])
supp=config['source_supplement'];ZONE=ROOT/supp['zone'];manifest=receipt(ZONE/'source_packet_manifest.json');assert sha(ZONE/'source_packet_manifest.json')==supp['manifest_sha256']
for name in [supp['observations'],supp['metadata'],supp['grain_delta'],'source_packet_manifest.json']:(OUT/name).write_bytes((ZONE/name).read_bytes())
source_admission=append_reviewed_source_observations(state,pin(OUT/supp['observations']),pin(OUT/supp['metadata']),observation_sha256=supp['observation_sha256'],metadata_sha256=supp['metadata_sha256'],accepted_metadata_statuses=supp['accepted_metadata_statuses']);grain=apply_reviewed_parent_grain(state,pin(OUT/supp['grain_delta']),delta_sha256=supp['grain_delta_sha256'],accepted_statuses=supp['accepted_grain_statuses'],baseline_credited_IDs=baseids);parent=grain['source_record_id'];source_addons=[]
for addon in config.get('source_observation_addons',[]):
 z=ROOT/addon['zone'];receipt(z/addon['manifest']);pin(z/addon['manifest'],addon['manifest_sha256'])
 for name in [addon['observations'],addon['metadata'],addon['manifest']]:(OUT/(addon['prefix']+name)).write_bytes((z/name).read_bytes())
 admitted=append_reviewed_source_observations(state,pin(OUT/(addon['prefix']+addon['observations'])),pin(OUT/(addon['prefix']+addon['metadata'])),observation_sha256=addon['observation_sha256'],metadata_sha256=addon['metadata_sha256'],accepted_metadata_statuses=addon['accepted_metadata_statuses'],expected_rows=addon['rows'],expected_population=addon['raw_source_population']);source_addons.append(admitted)
source_all_ids=set(source_admission['source_IDs']).union(*(set(a['source_IDs']) for a in source_addons));net_source_delta=sum(a['source_population'] for a in [source_admission,*source_addons])+grain['additive_population_delta'];EXTERNAL[2002]=11726-net_source_delta

source_only,_,_=axes(mainextra);assert all(source_only[y]['primary_axis_population']==before[y]['primary_axis_population'] for y in before)
pointframes=[];edgeframes=[]
for spec in config['native_packets']:
 z=ROOT/spec['zone'];pin(z/spec['receipt'],spec['receipt_sha256']);r=receipt(z/spec['receipt']);assert r.get('baseline_stage',r.get('actual_State_stage',63))==63
 for name in spec.get('point_files',[]):
  f=read(z/name);f['integration_input_path']=str(z/name);f['integration_packet_kind']=spec['kind'];pointframes.append(f)
 for name in spec.get('edge_files',[]):edgeframes.append(read(z/name))
points=pd.concat(pointframes,ignore_index=True).fillna('');edges=pd.concat(edgeframes,ignore_index=True).fillna('');assert points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all() and edges.decision_status.isin(ACCEPTED_EDGE_STATUSES).all() and edges.relation.eq('same_place').all();assert parent not in set(points.target_source_record_id)|(set(edges.from_source_record_id)|set(edges.to_source_record_id));assert not(set(edges.from_source_record_id)|set(edges.to_source_record_id))&(appearance|inclusions|round2), 'typed lifecycle endpoints cannot be ordinary same-place unions'
for q,h in set(zip(points.point_origin_file,points.point_origin_sha256)):assert q and h;pin(q,h)
coords=collections.defaultdict(list);occupation=collections.defaultdict(set)
for sid,p in state.point_rows.items():
 coords[state.uf.find(sid)].append((p['latitude'],p['longitude']))
 if int(state.by_id.loc[sid,'census_year'])==2021:occupation[(p['latitude'],p['longitude'])].add(sid)
holds=[];merged={};prepoints=set(state.point_rows)
for row in points.to_dict('records'):
 sid=row['target_source_record_id'];assert sid in state.by_id.index;lat,lon=float(row['latitude']),float(row['longitude']);assert -90<=lat<=90 and -180<=lon<=180;reason=''
 if sid in state.point_rows:reason='new packet target already has active ownpoint; no replacement authorization'
 if sid in merged:reason='duplicate supplied target; no confidence selection'
 if any(distance_km((lat,lon),p)>5 for p in coords[state.uf.find(sid)]):reason='existing identity component ownpoint contradiction >5km'
 if int(state.by_id.loc[sid,'census_year'])==2021 and occupation.get((lat,lon),set())-{sid}:reason='distinct current native point occupation'
 if reason:holds.append({'kind':'point','source_record_id':sid,'reason':reason});continue
 merged[sid]=row
 if int(state.by_id.loc[sid,'census_year'])==2021:occupation[(lat,lon)].add(sid)
uf=UnionFind(state.obs.source_record_id)
for sid in state.obs.source_record_id:uf.union(state.uf.find(sid),sid)
yearsets={uf.find(r):set(y) for r,y in state.years.items()};cc=collections.defaultdict(list)
for sid,p in {**state.point_rows,**merged}.items():cc[uf.find(sid)].append((float(p['latitude']),float(p['longitude'])))
accepted_edges=[]
for row in edges.to_dict('records'):
 a,b=row['from_source_record_id'],row['to_source_record_id'];assert a in state.by_id.index and b in state.by_id.index;ra,rb=uf.find(a),uf.find(b);reason=''
 if ra==rb:reason='duplicate graph connectivity'
 elif yearsets[ra]&yearsets[rb]:reason='duplicate census year in same-place component'
 elif any(distance_km(x,y)>5 for x in cc[ra] for y in cc[rb]):reason='new component ownpoint contradiction >5km'
 if reason:holds.append({'kind':'edge','source_record_id':a,'to_source_record_id':b,'reason':reason});continue
 ys=yearsets[ra]|yearsets[rb];cp=cc[ra]+cc[rb];uf.union(ra,rb);r=uf.find(ra);yearsets.pop(ra,None);yearsets.pop(rb,None);cc.pop(ra,None);cc.pop(rb,None);yearsets[r]=ys;cc[r]=cp;accepted_edges.append(row)
carriers=collections.defaultdict(set)
for sid,p in {**state.point_rows,**merged}.items():
 if int(state.by_id.loc[sid,'census_year'])==2021:carriers[uf.find(sid)].add((p['point_origin_file'],p['point_origin_sha256'],float(p['latitude']),float(p['longitude'])))
for sid in list(merged):
 row=merged[sid]
 if int(state.by_id.loc[sid,'census_year'])<2021:
  assert row.get('historical_census_coordinate_asserted','False')=='False'
  if (row['point_origin_file'],row['point_origin_sha256'],float(row['latitude']),float(row['longitude'])) not in carriers[uf.find(sid)]:holds.append({'kind':'point','source_record_id':sid,'reason':'historical continuity lacks independently admitted current carrier in actual accepted component'});merged.pop(sid)
pointout=OUT/'accepted_point_use_delta.csv.gz';edgeout=OUT/'accepted_identity_edge_delta.csv.gz';pd.DataFrame(merged.values()).to_csv(pointout,index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(accepted_edges).to_csv(edgeout,index=False,compression={'method':'gzip','mtime':0});state.add_deltas(edge_paths=[edgeout],point_paths=[pointout]);state.obs['root']=state.obs.source_record_id.map(state.uf.find)
after_core,afinite,_=axes(coreextra);after_appearance,_,_=axes(coreextra|appearance);after_inclusion,_,_=axes(coreextra|appearance|inclusions);after,_,acredit=axes(mainextra);old=state.obs[state.obs.source_record_id.isin(protected.source_record_id)].copy();old.loc[old.source_record_id.eq(parent),'is_additive_settlement_record']=True;old.loc[old.source_record_id.eq(parent),'population_scope']=protected.loc[protected.source_record_id.eq(parent),'population_scope'].iloc[0];assert old.drop(columns='root').reset_index(drop=True).equals(protected.drop(columns='root').reset_index(drop=True))
ordinary=ordinary_rows();changed=ordinary[ordinary.source_record_id.isin(acredit-bcredit)].copy();lost=ordinary[ordinary.source_record_id.isin(bcredit-acredit)].copy();changed.to_csv(OUT/'actual_newly_credited_primary_source_IDs.csv.gz',index=False,compression={'method':'gzip','mtime':0});lost.to_csv(OUT/'actual_lost_primary_source_IDs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
uid={}
for r,g in state.obs[state.obs.source_record_id.isin(afinite)].groupby('root'):
 ids=g.sort_values('census_year').source_record_id.tolist();assert len(ids)==3;uid[r]='np3:'+base64.urlsafe_b64encode(hashlib.sha256(json.dumps(ids,ensure_ascii=False,separators=(',',':')).encode()).digest()).decode().rstrip('=')
credit=ordinary[ordinary.source_record_id.isin(acredit)][['source_record_id','census_year','population','population_value_quality']].copy();credit['component_root']=credit.source_record_id.map(state.uf.find);credit['entity_uid']=credit.component_root.map(uid).fillna('');credit['finite_ordinary_full3_all_ownpoints']=credit.source_record_id.isin(afinite)
for label,ids in [('explicit_appearance_publication_absence_credit',appearance),('explicit_inclusion_credit',inclusions),('explicit_available_year_lifecycle_round2_credit',round2)]:credit[label]=credit.source_record_id.isin(ids)
credit['supplemental_secondary2002_source_observation']=credit.source_record_id.isin(source_all_ids);credit.to_csv(OUT/'applied_primary_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
remaining=ordinary[~ordinary.source_record_id.isin(acredit)].copy();remaining['has_own_point']=remaining.source_record_id.isin(state.point_rows);remaining['component_years']=remaining.source_record_id.map(lambda sid:','.join(map(str,sorted(state.years[state.uf.find(sid)]))));remaining=remaining.sort_values(['population','source_record_id'],ascending=[False,True],na_position='last');remaining.to_csv(OUT/'applied_remaining_primary.csv.gz',index=False,compression={'method':'gzip','mtime':0})
for y,g in remaining.groupby('census_year'):g.head(20).to_csv(OUT/f'top20_applied_remaining_primary_{int(y)}.csv',index=False)
pd.DataFrame(holds,columns=['kind','source_record_id','to_source_record_id','reason']).to_csv(OUT/'integration_holds.csv',index=False);cs=state.obs[['source_record_id','root']].copy();cs['has_own_point']=cs.source_record_id.isin(state.point_rows);cs.to_csv(OUT/'applied_component_snapshot.csv.gz',index=False,compression={'method':'gzip','mtime':0});snapshot=pd.DataFrame([{**p,'source_record_id':sid} for sid,p in state.point_rows.items()]).fillna('').astype(str);assert snapshot.source_record_id.ne('').all() and snapshot.source_record_id.is_unique and set(snapshot.source_record_id)==set(cs.loc[cs.has_own_point,'source_record_id']);snapshot.to_parquet(OUT/'applied_point_snapshot.parquet',index=False,compression='zstd')
state.obs.to_parquet(OUT/'applied_state_observations.parquet',index=False,compression='zstd');state.supplemental_source_metadata.to_csv(OUT/'applied_supplemental_source_metadata.csv.gz',index=False,compression={'method':'gzip','mtime':0});obsback=pd.read_parquet(OUT/'applied_state_observations.parquet');assert obsback.equals(state.obs) and obsback.source_record_id.is_unique and len(obsback)==len(protected)+len(source_all_ids);assert not bool(obsback.loc[obsback.source_record_id.eq(parent),'is_additive_settlement_record'].iloc[0]) and float(obsback.loc[obsback.source_record_id.eq(parent),'population'].iloc[0])==544
back=read(OUT/'applied_remaining_primary.csv.gz');assert set(back.source_record_id)==set(remaining.source_record_id) and back.source_record_id.is_unique
gains={y:{'newly_credited_source_IDs':int(changed.census_year.eq(int(y)).sum()),'lost_source_IDs':int(lost.census_year.eq(int(y)).sum()),'net_primary_population_gain':after[y]['primary_axis_population']-before[y]['primary_axis_population'],'net_core_formation_plus_direct_population_gain':after_core[y]['primary_axis_population']-before_core[y]['primary_axis_population'],'net_finite_all3_ownpoint_population_gain':after[y]['finite_all3_ownpoints_population']-before[y]['finite_all3_ownpoints_population'],'new_finite_all3_ownpoint_histories':after[y]['finite_all3_ownpoints_rows']-before[y]['finite_all3_ownpoints_rows']} for y in before}
for y,g in gains.items():assert g['net_primary_population_gain']==int(changed.loc[changed.census_year.eq(int(y)),'population'].sum())-int(lost.loc[lost.census_year.eq(int(y)),'population'].sum())
outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file() and p.name!='application_receipt.json'}
result={'status':'applied_actual_frozen63_native_temporal_ownpoints_and_reviewed_secondary_source_observation_batch','baseline_stage':63,'intended_working_stage':64,'frozen_baseline_commit':config['baseline_commit'],'approved_API64_sha256':sha(api),'historical_API63_sha256':'002dacc1104d79d9330753ec0b5f5c528b62ca69574c7000df2e19fd5d16f76a','actual_State_loads':0,'cache_hydration_used':True,'full_active_point_row_fields_hydrated':True,'baseline_reproduced':True,'canonical_State_API_replay_passed':True,'accepted_edges':len(accepted_edges),'accepted_point_uses':len(merged),'point_replacements':0,'new_unique_point_targets':len(set(state.point_rows)-prepoints),'integration_holds':len(holds),'before':before,'before_core_formation_plus_direct_axis':before_core,'after_source_admission_only':source_only,'after_core_formation_plus_direct_axis':after_core,'after_appearance_axis':after_appearance,'after_inclusion_axis':after_inclusion,'after':after,'source_observation_admission':source_admission,'source_observation_addons':source_addons,'source_observation_total_rows':len(source_all_ids),'net_selected_additive_source_population_delta':net_source_delta,'source_control_signed_gap':EXTERNAL,'source_grain_interpretation':grain,'source_population_values_and_original_selected_bytes_unchanged':True,'official1775_population_overlay_included':False,'prior_typed_lifecycle_UIDs_preserved_without_UF':True,'actual_gain_by_unique_source_ID_union':gains,'after_State_metrics':state.metrics(),'source_control_deficits_unallocated':EXTERNAL,'input_pins':PINS,'output_pins':outputs,'wall_seconds':round(time.monotonic()-START,3)}
(OUT/'application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['input_pins','output_pins','after_State_metrics','source_observation_admission']},ensure_ascii=False))
