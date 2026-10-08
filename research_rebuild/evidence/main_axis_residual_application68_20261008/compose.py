#!/usr/bin/env python3
"""Apply finalized68 deltas to certified67 snapshots; no State.load replay."""
from pathlib import Path
import sys,json,hashlib,time,math,collections,base64
import pandas as pd
import duckdb
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];E=ROOT/'research_rebuild/evidence';M=ROOT/'research_rebuild/mass_linkage';BASE=E/'main_axis_residual_application67_20261008'
sys.path.insert(0,str(M))
from current_chain_state_20261007 import State,sha,distance_km
from build_long_table import UnionFind,ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES

START=time.monotonic();PINS={};YEARS={2002,2010,2021};COMMON={2002:145166731,2010:142856536,2021:144699673};FED={2002:15043973,2010:16383067,2021:18612023};EXTERNAL={2002:-757,2010:493512,2021:0}
def pin(p,expected=None):
 p=Path(p);k=str(p)
 if k not in PINS:PINS[k]={'sha256':sha(p),'bytes':p.stat().st_size}
 if expected is not None:assert PINS[k]['sha256']==expected,(k,expected,PINS[k])
 return p
def read(p):return pd.read_csv(pin(p),dtype=str,keep_default_na=False)
def receipt(p):
 p=Path(p);r=json.loads(pin(p).read_text())
 for q,h in {**r.get('source_pins',{}),**r.get('input_pins',{}),**r.get('raw_workbook_pins',{}),**r.get('source_input_pins',{})}.items():pin(ROOT/q if not Path(q).is_absolute() and not Path(q).exists() else q,h['sha256'] if isinstance(h,dict) else h)
 for q,h in {**r.get('outputs',{}),**r.get('output_pins',{})}.items():pin(Path(q) if Path(q).is_absolute() else p.parent/q,h['sha256'] if isinstance(h,dict) else h)
 return r
config=json.loads(pin(OUT/'finalized_packets.json').read_text());assert config['all_packets_finalized'] and config['capacity_authorized'] and config['execution_authorized_by_root_GO']
assert config['application_authorized_after_checkpoint67'] and config['baseline_commit']
for proof in config.get('independent_review_proofs',[]):pin(ROOT/proof['path'],proof['sha256'])
base=json.loads(pin(BASE/'application_receipt.json','4f50f21c39099d1121e0e32374708066a775c79f597a3c76192cd4993b19d856').read_text());assert base['intended_working_stage']==67 and base['canonical_State_API_replay_passed']
api=pin(OUT/'frozen_State_API68.py',config['API_sha256']);pin(M/'current_chain_state_20261007.py',sha(api));pin(OUT/'frozen_stage67_loader.py',config['loader_sha256'])
for name in ['applied_state_observations.parquet','applied_component_snapshot.csv.gz','applied_point_snapshot.parquet','applied_primary_credited_UID_roster.csv.gz']:pin(BASE/name,base['output_pins'][name]['sha256'])
state=State.__new__(State);state.obs=pd.read_parquet(BASE/'applied_state_observations.parquet');state.by_id=state.obs.set_index('source_record_id',drop=False);state.inputs=[]
cs=read(BASE/'applied_component_snapshot.csv.gz');assert cs.source_record_id.is_unique and set(cs.source_record_id)==set(state.obs.source_record_id)
state.uf=UnionFind(state.obs.source_record_id)
for r,g in cs.groupby('root'):
 for sid in g.source_record_id:state.uf.union(r,sid)
state.obs['root']=state.obs.source_record_id.map(state.uf.find);assert dict(zip(state.obs.source_record_id,state.obs.root))==dict(zip(cs.source_record_id,cs.root))
ys=state.obs.groupby('root').census_year.agg(['size','nunique']);assert ys['size'].eq(ys['nunique']).all() and ys['size'].le(3).all();state.years={r:set(map(int,g)) for r,g in state.obs.groupby('root').census_year}
from hydrate_point_snapshot import hydrate_active_point_rows
from stream_point_snapshot import write_point_snapshot_from_active_rows
pin(OUT/'hydrate_point_snapshot.py');pin(OUT/'stream_point_snapshot.py')
state.point_rows,point_hydration_proof=hydrate_active_point_rows(BASE/'applied_point_snapshot.parquet',ACCEPTED_COORDINATE_STATUSES)
assert len(state.point_rows)==446139
state.point_alternatives=[];state.conflicting_point_targets=set();assert set(state.point_rows)==set(cs.loc[cs.has_own_point.eq('True'),'source_record_id']);assert state.metrics()==base['after_State_metrics']
protected=state.obs.copy(deep=True);baseline=read(BASE/'applied_primary_credited_UID_roster.csv.gz');baseids=set(baseline.source_record_id);basefinite=set(baseline.loc[baseline.finite_ordinary_full3_all_ownpoints.eq('True'),'source_record_id'])
g17ids=set(baseline.loc[baseline.explicit_gorodok17_inclusion_credit.eq('True'),'source_record_id']);assert len(g17ids)==1
coremask=~(baseline.explicit_appearance_publication_absence_credit.eq('True')|baseline.explicit_inclusion_credit.eq('True')|baseline.explicit_available_year_lifecycle_round2_credit.eq('True')|baseline.explicit_gorodok17_inclusion_credit.eq('True'));coreextra=set(baseline.loc[coremask,'source_record_id'])-basefinite;mainextra=baseids-basefinite-g17ids
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
before,bfinite,bcredit=axes(mainextra|g17ids);before_core,_,_=axes(coreextra);assert before==base['after'] and before_core==base['after_core_formation_plus_direct_axis'];assert baseids==set(ordinary_rows().loc[ordinary_rows().source_record_id.isin(bcredit),'source_record_id'])
g17credit=read(OUT/'g17_accepted_source_UID_credit.csv');g17ids=set(g17credit.source_record_id);assert len(g17ids)==1 and g17ids<=bcredit
g17sid=next(iter(g17ids));assert g17sid=='2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:3968';g17native=state.by_id.loc[g17sid];assert int(g17native.census_year)==2002 and float(g17native.population)==5495
for d in read(OUT/'g17_accepted_own_sourceyear_observation.csv').to_dict('records'):
 native=state.by_id.loc[d['source_record_id']];assert int(native.census_year)==int(d['year']) and float(native.population)==float(d['native_population']) and native.population_value_quality==d['native_population_quality']
g17contexts=read(OUT/'g17_accepted_typed_context_edges.csv');assert g17contexts.graph_union_allowed.eq('False').all() and g17contexts.parent_source_UID_credit.eq('0').all() and not set(g17contexts.to_source_record_id)&g17ids
parent='2002:038_218ac665d8_02c_Astraxanskaja.xls:Sheet1:456';source_metadata=read(pin(BASE/'applied_supplemental_source_metadata.csv.gz',base['output_pins']['applied_supplemental_source_metadata.csv.gz']['sha256']));source_all_ids=set(source_metadata.source_record_id);assert len(source_all_ids)==128; (OUT/'applied_supplemental_source_metadata.csv.gz').write_bytes((BASE/'applied_supplemental_source_metadata.csv.gz').read_bytes());assert not bool(state.by_id.loc[parent,'is_additive_settlement_record'])
pointframes=[];edgeframes=[];rejectionframes=[]
for spec in config['native_packets']:
 z=ROOT/spec['zone'];pin(z/spec['receipt'],spec['receipt_sha256']);
 if spec.get('manifest'):
  mp=pin(z/spec['manifest'],spec['manifest_sha256']);mf=json.loads(mp.read_text())
  for q,h in mf.get('source_input_guard_pins',{}).items():pin(q,h['sha256'] if isinstance(h,dict) else h)
  for q,h in mf.get('files',{}).items():pin(Path(q) if Path(q).is_absolute() else z/q,h['sha256'] if isinstance(h,dict) else h)
 for ep in spec.get('embedded_json_source_pins',[]):
  ev=read(z/ep['file'])
  for raw in ev[ep['column']]:
   claim=json.loads(raw);pin(claim[ep['path_key']],claim[ep['sha_key']])
 r=receipt(z/spec['receipt']);assert r.get('baseline_stage',r.get('actual_State_stage',r.get('actual_baseline',r.get('baseline',67))))==67
 for name in spec.get('point_files',[]):
  f=read(z/name);f['integration_input_path']=str(z/name);f['integration_packet_kind']=spec['kind'];pointframes.append(f)
 for name in spec.get('edge_files',[]):edgeframes.append(read(z/name))
 for name in spec.get('rejection_files',[]):rejectionframes.append(read(z/name))
points=pd.concat(pointframes,ignore_index=True).fillna('');edges=pd.concat(edgeframes,ignore_index=True).fillna('');raw_supplied_point_rows=len(points);raw_supplied_edge_rows=len(edges);corroboration_duplicates=[]
point_dedup=[]
for sid,g in points.groupby('target_source_record_id',sort=False):
 required=['coordinate_admission_status','coordinate_source_record_id','point_origin_file','point_origin_sha256','point_origin_locator']
 for k in required:assert g[k].astype(str).nunique()==1,('conflicting supplied point source/status',sid,k)
 assert len({(float(a),float(b)) for a,b in zip(g.latitude,g.longitude)})==1,('conflicting supplied coordinates',sid)
 point_dedup.append(g.iloc[0].to_dict())
 if len(g)>1:corroboration_duplicates.append({'kind':'point','source_record_id':sid,'supplied_rows':len(g),'proof_paths':g.integration_input_path.tolist()})
points=pd.DataFrame(point_dedup);edge_dedup={}
for row in edges.to_dict('records'):
 key=tuple(sorted([row['from_source_record_id'],row['to_source_record_id']]))
 if key in edge_dedup:
  prior=edge_dedup[key];assert row['relation']==prior['relation']=='same_place' and row['decision_status']==prior['decision_status'],('conflicting supplied edge',key)
  corroboration_duplicates.append({'kind':'edge','source_record_id':key[0],'to_source_record_id':key[1],'supplied_rows':2})
 else:edge_dedup[key]=row
edges=pd.DataFrame(edge_dedup.values());assert points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all() and edges.decision_status.isin(ACCEPTED_EDGE_STATUSES).all() and edges.relation.eq('same_place').all();assert parent not in set(points.target_source_record_id)|(set(edges.from_source_record_id)|set(edges.to_source_record_id));assert not(set(edges.from_source_record_id)|set(edges.to_source_record_id))&(coreextra|appearance|inclusions|round2|g17ids), 'typed lifecycle endpoints cannot be ordinary same-place unions'
for q,h in set(zip(points.point_origin_file,points.point_origin_sha256)):assert q and h;pin(q,h)
reject=pd.concat(rejectionframes,ignore_index=True).fillna('') if rejectionframes else pd.DataFrame(columns=['target_source_record_id','rejection_status','old_latitude','old_longitude','origin_ledger','origin_ledger_sha256']);assert reject.target_source_record_id.is_unique and set(reject.target_source_record_id)<=set(points.target_source_record_id)
for row in reject.to_dict('records'):
 old=state.point_rows[row['target_source_record_id']];assert old['point_ledger_path']==row['origin_ledger'] and (old['latitude'],old['longitude'])==(float(row['old_latitude']),float(row['old_longitude']));pin(row['origin_ledger'],row['origin_ledger_sha256'])
 if row.get('old_point_origin_file'):assert old['point_origin_file']==row['old_point_origin_file'] and old['point_origin_sha256']==row['old_point_origin_sha256']
prepoints=set(state.point_rows);rejectout=OUT/'point_use_rejections.csv.gz';reject.to_csv(rejectout,index=False,compression={'method':'gzip','mtime':0})
if len(reject):state.reject_point_uses(rejectout)
coords=collections.defaultdict(list);occupation=collections.defaultdict(set)
for sid,p in state.point_rows.items():
 coords[state.uf.find(sid)].append((p['latitude'],p['longitude']))
 if int(state.by_id.loc[sid,'census_year'])==2021:occupation[(p['latitude'],p['longitude'])].add(sid)
holds=[];merged={}
for row in points.to_dict('records'):
 sid=row['target_source_record_id'];assert sid in state.by_id.index;lat,lon=float(row['latitude']),float(row['longitude']);assert -90<=lat<=90 and -180<=lon<=180;reason=''
 if sid in state.point_rows:reason='new packet target already has active ownpoint; no replacement authorization'
 if sid in merged:reason='duplicate supplied target; no confidence selection'
 if any(distance_km((lat,lon),p)>5 for p in coords[state.uf.find(sid)]):reason='existing identity component ownpoint contradiction >5km'
 if int(state.by_id.loc[sid,'census_year'])==2021 and occupation.get((lat,lon),set())-{sid}:reason='distinct current native point occupation'
 if reason:holds.append({'kind':'point','source_record_id':sid,'reason':reason});continue
 merged[sid]=row
 if int(state.by_id.loc[sid,'census_year'])==2021:occupation[(lat,lon)].add(sid)
assert set(reject.target_source_record_id)<=set(merged),'A reviewed claim was rejected but its positive replacement blocked; stop before add_deltas'
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
 if int(state.by_id.loc[sid,'census_year'])<2021 and sid not in g17ids:
  assert row.get('historical_census_coordinate_asserted','False')=='False'
  if (row['point_origin_file'],row['point_origin_sha256'],float(row['latitude']),float(row['longitude'])) not in carriers[uf.find(sid)]:holds.append({'kind':'point','source_record_id':sid,'reason':'historical continuity lacks independently admitted current carrier in actual accepted component'});merged.pop(sid)
pointout=OUT/'accepted_point_use_delta.csv.gz';edgeout=OUT/'accepted_identity_edge_delta.csv.gz';pd.DataFrame(merged.values()).to_csv(pointout,index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(accepted_edges).to_csv(edgeout,index=False,compression={'method':'gzip','mtime':0});state.add_deltas(edge_paths=[edgeout],point_paths=[pointout]);state.obs['root']=state.obs.source_record_id.map(state.uf.find)
after_core,afinite,_=axes(coreextra);after_appearance,_,_=axes(coreextra|appearance);after_inclusion,_,_=axes(coreextra|appearance|inclusions);after_legacy,_,alegacy=axes(mainextra);after,_,acredit=axes(mainextra|g17ids);assert g17ids<=set(state.point_rows) and {y:after[y]['primary_axis_population']-after_legacy[y]['primary_axis_population'] for y in after}=={'2002':5495,'2010':0,'2021':0};assert state.obs.drop(columns='root').equals(protected.drop(columns='root'))
ordinary=ordinary_rows();changed=ordinary[ordinary.source_record_id.isin(acredit-bcredit)].copy();lost=ordinary[ordinary.source_record_id.isin(bcredit-acredit)].copy();changed.to_csv(OUT/'actual_newly_credited_primary_source_IDs.csv.gz',index=False,compression={'method':'gzip','mtime':0});lost.to_csv(OUT/'actual_lost_primary_source_IDs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
uid={}
for r,g in state.obs[state.obs.source_record_id.isin(afinite)].groupby('root'):
 ids=g.sort_values('census_year').source_record_id.tolist();assert len(ids)==3;uid[r]='np3:'+base64.urlsafe_b64encode(hashlib.sha256(json.dumps(ids,ensure_ascii=False,separators=(',',':')).encode()).digest()).decode().rstrip('=')
credit=ordinary[ordinary.source_record_id.isin(acredit)][['source_record_id','census_year','population','population_value_quality']].copy();credit['component_root']=credit.source_record_id.map(state.uf.find);credit['entity_uid']=credit.component_root.map(uid).fillna('');credit['finite_ordinary_full3_all_ownpoints']=credit.source_record_id.isin(afinite)
for label,ids in [('explicit_appearance_publication_absence_credit',appearance),('explicit_inclusion_credit',inclusions),('explicit_available_year_lifecycle_round2_credit',round2)]:credit[label]=credit.source_record_id.isin(ids)
credit['explicit_gorodok17_inclusion_credit']=credit.source_record_id.isin(g17ids);credit['supplemental_secondary2002_source_observation']=credit.source_record_id.isin(source_all_ids);credit.to_csv(OUT/'applied_primary_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
remaining=ordinary[~ordinary.source_record_id.isin(acredit)].copy();remaining['has_own_point']=remaining.source_record_id.isin(state.point_rows);remaining['component_years']=remaining.source_record_id.map(lambda sid:','.join(map(str,sorted(state.years[state.uf.find(sid)]))));remaining=remaining.sort_values(['population','source_record_id'],ascending=[False,True],na_position='last');remaining.to_csv(OUT/'applied_remaining_primary.csv.gz',index=False,compression={'method':'gzip','mtime':0})
for y,g in remaining.groupby('census_year'):g.head(20).to_csv(OUT/f'top20_applied_remaining_primary_{int(y)}.csv',index=False)
(OUT/'corroborating_packet_duplicate_claims.json').write_text(json.dumps(corroboration_duplicates,ensure_ascii=False,indent=2)+'\n');pd.DataFrame(holds,columns=['kind','source_record_id','to_source_record_id','reason']).to_csv(OUT/'integration_holds.csv',index=False);cs=state.obs[['source_record_id','root']].copy();cs['has_own_point']=cs.source_record_id.isin(state.point_rows);cs.to_csv(OUT/'applied_component_snapshot.csv.gz',index=False,compression={'method':'gzip','mtime':0});snapshot_keys=write_point_snapshot_from_active_rows(state.point_rows,OUT/'applied_point_snapshot.parquet');assert snapshot_keys==set(cs.loc[cs.has_own_point,'source_record_id'])
state.obs.to_parquet(OUT/'applied_state_observations.parquet',index=False,compression='zstd');obsback=pd.read_parquet(OUT/'applied_state_observations.parquet');assert obsback.equals(state.obs) and obsback.source_record_id.is_unique and len(obsback)==len(protected);assert not bool(obsback.loc[obsback.source_record_id.eq(parent),'is_additive_settlement_record'].iloc[0]) and float(obsback.loc[obsback.source_record_id.eq(parent),'population'].iloc[0])==544
back=read(OUT/'applied_remaining_primary.csv.gz');assert set(back.source_record_id)==set(remaining.source_record_id) and back.source_record_id.is_unique
gains={y:{'newly_credited_source_IDs':int(changed.census_year.eq(int(y)).sum()),'lost_source_IDs':int(lost.census_year.eq(int(y)).sum()),'net_primary_population_gain':after[y]['primary_axis_population']-before[y]['primary_axis_population'],'net_core_formation_plus_direct_population_gain':after_core[y]['primary_axis_population']-before_core[y]['primary_axis_population'],'net_finite_all3_ownpoint_population_gain':after[y]['finite_all3_ownpoints_population']-before[y]['finite_all3_ownpoints_population'],'new_finite_all3_ownpoint_histories':after[y]['finite_all3_ownpoints_rows']-before[y]['finite_all3_ownpoints_rows']} for y in before}
for y,g in gains.items():assert g['net_primary_population_gain']==int(changed.loc[changed.census_year.eq(int(y)),'population'].sum())-int(lost.loc[lost.census_year.eq(int(y)),'population'].sum())
outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file() and p.name!='application_receipt.json'}
result={'status':'applied_actual_frozen67_sourcepositive_railway_NP_and_sourcebound_former_name_identity_continuity_batch','baseline_stage':67,'intended_working_stage':68,'frozen_baseline_commit':config['baseline_commit'],'API_sha256':sha(api),'actual_State_loads':0,'cache_hydration_used':True,'baseline_reproduced':True,'canonical_State_API_replay_passed':True,'raw_supplied_edge_rows':raw_supplied_edge_rows,'raw_supplied_point_rows':raw_supplied_point_rows,'corroborating_supplied_claim_duplicates':len(corroboration_duplicates),'accepted_edges':len(accepted_edges),'accepted_point_uses':len(merged),'point_replacements':len(reject),'new_unique_point_targets':len(set(state.point_rows)-prepoints),'integration_holds':len(holds),'before':before,'before_core_formation_plus_direct_axis':before_core,'after_core_formation_plus_direct_axis':after_core,'after_appearance_axis':after_appearance,'after_inclusion_axis':after_inclusion,'after_legacy_available_year_lifecycle_axis':after_legacy,'after_explicit_inclusion65':after,'after':after,'explicit_Gorodok17_source_IDs':sorted(g17ids),'explicit_Gorodok17_new_source_ID_population':{'2002':0,'2010':0,'2021':0},'explicit_Gorodok17_inherited_source_ID_population':{'2002':5495,'2010':0,'2021':0},'explicit_Gorodok17_admin_date_vs_statistical_grain_caveat_preserved':True,'typed_inclusion65_UF_allowed':False,'typed_context65_new_population_credit':0,'source_observation_additions':0,'source_population_quality_names_codes_and_grain_unchanged':True,'official_population_overlay_included':False,'prior_typed_lifecycle_UIDs_preserved_without_UF':True,'actual_gain_by_unique_source_ID_union':gains,'after_State_metrics':state.metrics(),'point_snapshot_hydration_proof':point_hydration_proof,'point_snapshot_export_batch_size':8192,'source_control_signed_gap':EXTERNAL,'input_pins':PINS,'output_pins':outputs,'wall_seconds':round(time.monotonic()-START,3)}
(OUT/'application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['input_pins','output_pins','after_State_metrics']},ensure_ascii=False))
