#!/usr/bin/env python3
"""Hydrate exact stage62 snapshots; apply finalized native deltas and typed sidecars."""
from pathlib import Path
import sys,json,hashlib,time,math,collections,base64
import pandas as pd
import duckdb
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;E=ROOT/'research_rebuild/evidence';M=ROOT/'research_rebuild/mass_linkage';BASE=E/'primary_residual_mass_application_20261008';REPORT=E/'working_full_chain_20261007'
sys.path.insert(0,str(M))
from current_chain_state_20261007 import State,sha,distance_km
from build_long_table import UnionFind,ACCEPTED_EDGE_STATUSES,ACCEPTED_COORDINATE_STATUSES
START=time.monotonic();PINS={};YEARS=(2002,2010,2021);COMMON={2002:145166731,2010:142856536,2021:144699673};FED={2002:15043973,2010:16383067,2021:18612023};EXTERNAL={2002:11726,2010:493512,2021:0}
def pin(p,expected=None):
 p=Path(p);k=str(p)
 if k not in PINS:PINS[k]={'sha256':sha(p),'bytes':p.stat().st_size}
 if expected is not None:assert PINS[k]['sha256']==expected,(k,expected,PINS[k])
 return p
def read(p):return pd.read_csv(pin(p),dtype=str,keep_default_na=False)
def checked_receipt(p,stage=62):
 p=Path(p);r=json.loads(pin(p).read_text());assert r.get('baseline_stage',r.get('stage_basis',stage))==stage
 for q,h in {**r.get('source_pins',{}),**r.get('input_pins',{})}.items():pin(q,h['sha256'] if isinstance(h,dict) else h)
 for q,h in {**r.get('outputs',{}),**r.get('output_pins',{})}.items():pin(p.parent/q,h['sha256'] if isinstance(h,dict) else h)
 return r
config=json.loads(pin(OUT/'finalized_packets.json').read_text());assert config['all_packets_finalized'] and config['baseline_commit']=='7b6924369e34e6cc21b661be03d40b80d437e5ef'
base=json.loads(pin(BASE/'application_receipt.json').read_text());assert base['intended_working_stage']==62 and base['canonical_State_API_replay_passed']
for q in ['applied_component_snapshot.csv.gz','applied_point_snapshot.parquet','applied_primary_credited_UID_roster.csv.gz']:pin(BASE/q,base['output_pins'][q]['sha256'])
api=pin(OUT/'frozen_State_API.py');pin(M/'current_chain_state_20261007.py',sha(api));loader=pin(OUT/'frozen_stage62_loader.py');ns={'__name__':'frozen63_baseline_loader','__file__':str(M/'working_state_20261007.py')};exec(compile(loader.read_text(),ns['__file__'],'exec'),ns)
# A hydrated canonical State object retains actual full active point-row fields; no load()/constructor replay.
selected=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');pin(selected)
c=duckdb.connect(config={'threads':1,'memory_limit':'512MB'});cols='source_record_id,census_year,settlement_name,settlement_type,name_norm,type_norm,region_norm,district_raw,population,population_scope,is_additive_settlement_record,population_value_quality,latitude,longitude,oktmo,okato,source_file,source_path,source_sha256,source_locator'
state=State.__new__(State);state.obs=c.execute('SELECT '+cols+' FROM read_parquet(?)',[str(selected)]).fetchdf();c.close();state.by_id=state.obs.set_index('source_record_id',drop=False);state.inputs=[]
ns['apply_source_namespace_interpretations'](state,E/'eaoregion_source_namespace_mass_20261008/source_namespace_interpretation_delta.csv')
cs=read(BASE/'applied_component_snapshot.csv.gz');assert cs.source_record_id.is_unique and set(cs.source_record_id)==set(state.obs.source_record_id)
state.uf=UnionFind(state.obs.source_record_id)
for r,g in cs.groupby('root'):
 for sid in g.source_record_id:state.uf.union(r,sid)
state.obs['root']=state.obs.source_record_id.map(state.uf.find);assert dict(zip(state.obs.source_record_id,state.obs.root))==dict(zip(cs.source_record_id,cs.root))
ys=state.obs.groupby('root').census_year.agg(['size','nunique']);assert ys['size'].eq(ys['nunique']).all() and ys['size'].le(3).all();state.years={r:set(map(int,v)) for r,v in state.obs.groupby('root').census_year}
pf=pd.read_parquet(BASE/'applied_point_snapshot.parquet').fillna('').astype(str);assert pf.source_record_id.is_unique and len(pf)==441128
state.point_rows={}
for row in pf.to_dict('records'):
 sid=row.pop('source_record_id');row['latitude'],row['longitude']=float(row['latitude']),float(row['longitude']);assert row['coordinate_admission_status'] in ACCEPTED_COORDINATE_STATUSES;assert -90<=row['latitude']<=90 and -180<=row['longitude']<=180;state.point_rows[sid]=row
state.point_alternatives=[];state.conflicting_point_targets=set();state.inputs += [BASE/'accepted_identity_edge_delta.csv.gz',BASE/'accepted_point_use_delta.csv.gz'];assert cs.has_own_point.eq('True').sum()==len(state.point_rows)
assert state.metrics()==base['after_State_metrics']
protected=state.obs.copy(deep=True);ordinary=state.obs[state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~((state.obs.census_year==2021)&state.obs.region_norm.eq('крым'))].copy()
sidecarsets={}
for k,n in [('partition','complete_publisher_partition_members.csv'),('qualified','qualified_scope_source_id_credit_union.csv'),('named','named_merger_lineage_constituents.csv'),('territorial','complete_territorial_scope_constituents.csv'),('direct','direct_inclusion_transformation_path_native_credit_union.csv'),('formation','formation_path_native_credit_union.csv')]:sidecarsets[k]=set(read(REPORT/n).source_record_id)-{''}
sidecar=set().union(*sidecarsets.values());appearance=set(read(BASE/'appearance_accepted_source_UID_credit_union.csv').source_record_id)
def axes(additional=()):
 fullroots={r for r,y in state.years.items() if y==set(YEARS)};allroots=set(fullroots)
 for sid in state.obs.source_record_id:
  if sid not in state.point_rows:allroots.discard(state.uf.find(sid))
 blocked={state.uf.find(sid) for sid,p in state.obs[['source_record_id','population']].itertuples(index=False,name=None) if pd.isna(p) or not math.isfinite(float(p))}
 allids={sid for sid in state.obs.source_record_id if state.uf.find(sid) in allroots};finite={sid for sid in allids if state.uf.find(sid) not in blocked};credited=finite|sidecar|set(additional);result={}
 for y,g in ordinary.groupby('census_year'):
  y=int(y);a=g[g.source_record_id.isin(allids)];f=g[g.source_record_id.isin(finite)];taken=g[g.source_record_id.isin(credited)];left=g[~g.source_record_id.isin(credited)];total=int(taken.population.sum())+FED[y];assert total+int(left.population.sum())+EXTERNAL[y]==COMMON[y]
  result[str(y)]={'ordinary_all3_ownpoints_rows':len(a),'ordinary_all3_ownpoints_population':int(a.population.sum()),'ordinary_all3_ownpoints_unknown_rows':int(a.population.isna().sum()),'finite_all3_ownpoints_rows':len(f),'finite_all3_ownpoints_population':int(f.population.sum()),'primary_selected_UID_rows':len(taken),'primary_axis_population':total,'remaining_primary_UID_rows':len(left),'remaining_primary_population':int(left.population.sum()),'remaining_unknown_rows':int(left.population.isna().sum()),'external_control_deficit_unallocated':EXTERNAL[y],'common_control':COMMON[y],'percent_common_control':100*total/COMMON[y]}
 return result,finite,credited
before_core,bfinite,bcore=axes();before,_,bcredited=axes(appearance)
assert before==base['after'] and before_core==base['after_core_formation_plus_direct_axis'];baseline_roster=read(BASE/'applied_primary_credited_UID_roster.csv.gz');assert set(baseline_roster.source_record_id)==set(ordinary.loc[ordinary.source_record_id.isin(bcredited),'source_record_id'])
# Read finalized round2 packets only; source proof generation belongs to packet authors.
pointframes=[];edgeframes=[];rejectionframes=[];packet_receipts={}
for spec in config['native_packets']:
 r=checked_receipt(spec['receipt']);packet_receipts[spec['receipt']]=r
 if spec.get('expected_status'):assert r['status']==spec['expected_status']
 for f in spec.get('point_files',[]):
  frame=read(f);frame['integration_input_path']=f;frame['integration_packet_kind']=spec.get('kind','native');pointframes.append(frame)
 for f in spec.get('edge_files',[]):edgeframes.append(read(f))
 for f in spec.get('rejection_files',[]):rejectionframes.append(read(f))
INC=E/'remaining_large_lifecycle_residual_20261008';ir=checked_receipt(INC/'packet_receipt.json');assert ir['status']=='reviewed_six_old_NP_included_in_root_replay_pending' and ir['accepted_event_cases']==6
incobs=read(INC/'accepted_historical_observations.csv');incpoints=read(INC/'accepted_former_locality_own_points.csv');incedges=read(INC/'accepted_included_in_event_edges.csv');inccontext=read(INC/'actual_receiving_city_three_census_context.csv');inccredits=read(INC/'accepted_direct_event_native_credit_union.csv');incids=set(inccredits.source_record_id)
assert len(incids)==len(inccredits)==len(incobs)==len(incpoints)==len(incedges)==6 and incids==set(incobs.source_record_id)==set(incpoints.target_source_record_id)==set(incedges.from_source_record_id)
assert incids<=set(ordinary.source_record_id)-bcredited and incedges.relation.eq('included_in').all() and incedges.same_place.eq('False').all() and incedges.graph_union_allowed.eq('False').all()
assert inccontext.is_receiving_city_context_only.eq('True').all() and pd.to_numeric(inccontext.new_national_credit_population).eq(0).all() and inccontext.child_count_substituted.eq('False').all() and not set(inccontext.source_record_id)&incids
assert inccredits.ordinary_three_census_same_place_claim.eq('False').all() and inccredits.is_additive_to_original_final_mixed_census_axis.eq('False').all();assert incpoints.own_locality_point.eq('True').all() and incpoints.recipient_point_assigned_to_child.eq('False').all()
for row in incobs.to_dict('records'):
 native=state.by_id.loc[row['source_record_id']];assert int(native.census_year)==int(row['year'])==2002 and math.isfinite(float(native.population)) and float(native.population)==float(row['native_population']) and native.population_value_quality==row['native_population_quality'];assert row['child_2021_population_assigned']=='False' and row['same_place_identity_asserted']=='False'
 assert state.years[state.uf.find(row['source_record_id'])]!=set(YEARS)
for row in inccontext.to_dict('records'):
 native=state.by_id.loc[row['source_record_id']];active=state.point_rows[row['source_record_id']];assert int(native.census_year)==int(row['census_year']) and float(native.population)==float(row['population']) and native.population_value_quality==row['population_value_quality'];assert (active['latitude'],active['longitude'])==(float(row['latitude']),float(row['longitude']))
for scope,g in inccontext.groupby('scope_id'):assert len(g)==3 and set(g.census_year)=={'2002','2010','2021'} and len({state.uf.find(sid) for sid in g.source_record_id})==1
for row in incedges.to_dict('records'):pin(row['event_source_file'],row['event_source_sha256'])
incpoints['integration_input_path']=str(INC/'accepted_former_locality_own_points.csv');incpoints['integration_packet_kind']='explicit_inclusion_ownpoint';pointframes.append(incpoints)
for name in ['accepted_direct_event_native_credit_union.csv','accepted_historical_observations.csv','accepted_former_locality_own_points.csv','accepted_included_in_event_edges.csv','actual_receiving_city_three_census_context.csv','accepted_available_year_statuses.csv','accepted_inclusion_events.csv','literal_own_inclusion_source_excerpts.csv','packet_receipt.json','verification_receipt.json']:(OUT/f'inclusion_{name}').write_bytes((INC/name).read_bytes())
# Minimal representative-replacement proposals gain complete actual current-carrier provenance.
carrier_rejections={row['target_source_record_id']:row for frame in rejectionframes for row in frame.to_dict('records')}
for frame_index,frame in enumerate(pointframes):
 if not frame.integration_packet_kind.eq('representative_supersession').any():continue
 enriched=[]
 for candidate in frame.to_dict('records'):
  sid=candidate['target_source_record_id'];rejection=carrier_rejections[sid];carrier=rejection['carrier_source_record_id'];assert state.uf.find(sid)==state.uf.find(carrier) and state.years[state.uf.find(sid)]==set(YEARS) and int(state.by_id.loc[carrier,'census_year'])==2021
  origin=state.point_rows[carrier];assert (origin['latitude'],origin['longitude'])==(float(candidate['latitude']),float(candidate['longitude']))
  row={k:v for k,v in origin.items() if k not in ['target_source_record_id','point_ledger_path']};row.update(candidate);row.update(target_source_record_id=sid,current_ownpoint_carrier_source_record_id=carrier,point_use_inference='modern_own_representative_point_reused_through_existing_accepted_full3_identity;reviewed_old_Geo_default_supersession',historical_census_coordinate_asserted=False,provider_identifier_binding_asserted=False,external_provider_ID_binding_asserted=False,coordinate_binding_scope='current_carrier_ownpoint_bound;old_source_year_continuity_inferred;no_old_providerID_binding',coordinate_binding_rule='Root-authorized source-positive existing full3 current ownpoint carrier; old Geo default explicitly superseded with preserved raw origin/ledger evidence; no population/identity/boundary claim changed')
  enriched.append(row)
 pointframes[frame_index]=pd.DataFrame(enriched)
EXTRA=E/'largest_available_year_lifecycle_round2_20261008';er=checked_receipt(EXTRA/'packet_receipt.json');assert er['status']=='reviewed_four_lifecycle_available_year_paths_root_replay_pending'
extraobs=read(EXTRA/'accepted_own_sourceyear_observations.csv');extrarefs=read(EXTRA/'accepted_own_point_references.csv');extracredits=read(EXTRA/'accepted_source_UID_credit_union.csv');extrastatus=read(EXTRA/'accepted_available_year_statuses.csv');extracontext=read(EXTRA/'actual_parent_three_year_context_only.csv');extraedges=read(EXTRA/'accepted_typed_context_edges.csv');extraids=set(extracredits.source_record_id)
assert len(extraids)==len(extracredits)==len(extraobs)==len(extrarefs)==6 and extraids==set(extraobs.source_record_id)==set(extrarefs.target_source_record_id)
assert extraids<=set(ordinary.source_record_id)-bcredited-incids and extraedges.graph_union_allowed.eq('False').all() and pd.to_numeric(extraedges.parent_UID_credit).eq(0).all()
assert extrastatus.unknown_is_zero.eq('False').all() and extrastatus.parent_count_assigned_to_child.eq('False').all() and extrastatus.loc[~extrastatus.status.eq('actual_own_published_observation'),'own_population'].eq('').all()
assert extracredits.ordinary_three_census_same_place_claim.eq('False').all() and extracredits.is_additive_to_original_final_mixed_census_axis.eq('False').all()
for row in extraobs.to_dict('records'):
 native=state.by_id.loc[row['source_record_id']];assert int(native.census_year)==int(row['year']) and math.isfinite(float(native.population)) and float(native.population)==float(row['native_population']) and native.population_value_quality==row['native_population_quality'];assert row['ordinary_three_census_same_place_claim']=='False'
for row in extrarefs.to_dict('records'):
 pin(row['point_origin_file'],row['point_origin_sha256'])
 if row['independent_article_point_file']:pin(row['independent_article_point_file'],row['independent_article_point_sha256'])
 if row['existing_accepted_own_point']=='True':
  active=state.point_rows[row['target_source_record_id']];assert (active['latitude'],active['longitude'])==(float(row['latitude']),float(row['longitude']))
 else:assert row['new_point_admission']=='True'
assert extracontext.context_only.eq('True').all() and pd.to_numeric(extracontext.new_UID_credit).eq(0).all() and extracontext.child_count_substituted.eq('False').all() and not set(extracontext.source_record_id)&extraids
for row in extracontext.to_dict('records'):
 native=state.by_id.loc[row['source_record_id']];active=state.point_rows[row['source_record_id']];assert int(native.census_year)==int(row['census_year']) and float(native.population)==float(row['population']) and native.population_value_quality==row['population_quality'] and (active['latitude'],active['longitude'])==(float(row['latitude']),float(row['longitude']))
extrapoints=read(EXTRA/'accepted_point_use_delta.csv');assert len(extrapoints)==1;extrapoints['integration_input_path']=str(EXTRA/'accepted_point_use_delta.csv');extrapoints['integration_packet_kind']='explicit_available_year_lifecycle_ownpoint';pointframes.append(extrapoints)
for name in ['accepted_source_UID_credit_union.csv','accepted_own_sourceyear_observations.csv','accepted_own_point_references.csv','accepted_available_year_statuses.csv','accepted_lifecycle_events.csv','accepted_typed_context_edges.csv','actual_parent_three_year_context_only.csv','packet_receipt.json','verification_receipt.json']:(OUT/f'lifecycle_round2_{name}').write_bytes((EXTRA/name).read_bytes())
points=pd.concat(pointframes,ignore_index=True).fillna('');edges=pd.concat(edgeframes,ignore_index=True).fillna('') if edgeframes else pd.DataFrame(columns=['from_source_record_id','to_source_record_id','relation','decision_status']);reject=pd.concat(rejectionframes,ignore_index=True).fillna('') if rejectionframes else pd.DataFrame(columns=['target_source_record_id','rejection_status','old_latitude','old_longitude','origin_ledger','origin_ledger_sha256'])
assert points.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES).all() and edges.decision_status.isin(ACCEPTED_EDGE_STATUSES).all() and edges.relation.eq('same_place').all();assert not(set(edges.from_source_record_id)|set(edges.to_source_record_id))&(incids|extraids)
for q,h in set(zip(points.point_origin_file,points.point_origin_sha256)):assert q and h;pin(q,h)
assert reject.target_source_record_id.is_unique and set(reject.target_source_record_id)<=set(points.target_source_record_id)
# Rejections require exact old active ledger/bytes/coordinates, and new positive own-locality source proof.
normalizations=[]
for index,row in enumerate(reject.to_dict('records')):
 old=state.point_rows[row['target_source_record_id']];assert old['point_ledger_path']==row['origin_ledger'] and (old['latitude'],old['longitude'])==(float(row['old_latitude']),float(row['old_longitude']))
 actual=sha(Path(row['origin_ledger']));claimed=row['origin_ledger_sha256']
 if claimed!=actual:
  # Correct only malformed hash transcription against an independently frozen canonical62 source pin.
  assert len(claimed)!=64 and base['input_pins'][row['origin_ledger']]['sha256']==actual
  reject.loc[index,'origin_ledger_sha256_raw_packet_claim']=claimed;reject.loc[index,'origin_ledger_sha256']=actual;reject.loc[index,'origin_ledger_sha256_normalization']='malformed_input_hash_transcription;actual_bytes_equal_frozen_canonical62_input_pin'
  normalizations.append({'source_record_id':row['target_source_record_id'],'ledger':row['origin_ledger'],'raw_packet_claim':claimed,'actual_and_frozen62_sha256':actual})
 pin(row['origin_ledger'],actual)
 if row.get('old_point_origin_file'):assert old['point_origin_file']==row['old_point_origin_file'] and old['point_origin_sha256']==row['old_point_origin_sha256']
(OUT/'ledger_hash_transcription_normalizations.json').write_text(json.dumps({'status':'immutable_source_packet_preserved;compiled_rejection_hashes_match_frozen62_actual_bytes','normalized_rows':len(normalizations),'rows':normalizations},ensure_ascii=False,indent=2)+'\n')
rejectout=OUT/'point_use_rejections.csv.gz';reject.to_csv(rejectout,index=False,compression={'method':'gzip','mtime':0})
prepoints=set(state.point_rows)
if len(reject):state.reject_point_uses(rejectout)
# Component coordinates index avoids scanning all native rows for every candidate.
component_coords=collections.defaultdict(list);occupation=collections.defaultdict(set)
for sid,p in state.point_rows.items():
 component_coords[state.uf.find(sid)].append((p['latitude'],p['longitude']))
 if int(state.by_id.loc[sid,'census_year'])==2021:occupation[(p['latitude'],p['longitude'])].add(sid)
holds=[];merged={}
for row in points.to_dict('records'):
 sid=row['target_source_record_id'];assert sid in state.by_id.index;lat=float(row['latitude']);lon=float(row['longitude']);assert -90<=lat<=90 and -180<=lon<=180;reason=''
 if sid in merged:
  other=merged[sid]
  if (float(other['latitude']),float(other['longitude']))!=(lat,lon):reason='duplicate target supplied with conflicting coordinates; no confidence-based selection'
  else:holds.append({'kind':'point','source_record_id':sid,'reason':'exact duplicate target/point supplied'});continue
 if sid in state.point_rows and distance_km((lat,lon),(state.point_rows[sid]['latitude'],state.point_rows[sid]['longitude']))>5:reason='active ownpoint contradiction >5km without explicit reviewed supersession'
 if int(state.by_id.loc[sid,'census_year'])==2021 and occupation.get((lat,lon),set())-{sid}:reason='point occupied by distinct current source ID'
 if row['integration_packet_kind']!='representative_supersession' and any(distance_km((lat,lon),p)>5 for p in component_coords[state.uf.find(sid)]):reason='existing identity component ownpoint contradiction >5km'
 if reason:holds.append({'kind':'point','source_record_id':sid,'reason':reason});continue
 merged[sid]=row
 if int(state.by_id.loc[sid,'census_year'])==2021:occupation[(lat,lon)].add(sid)
assert set(reject.target_source_record_id)<=set(merged),'Reviewed oldpoint rejected but its replacement blocked; stop before publishing'
# Every old temporal reuse retains an independently source-admitted carrier (baseline or new current packet).
carriers=set((p.get('point_origin_file',''),p.get('point_origin_sha256',''),float(p['latitude']),float(p['longitude'])) for p in state.point_rows.values())
carriers|={(p['point_origin_file'],p['point_origin_sha256'],float(p['latitude']),float(p['longitude'])) for sid,p in merged.items() if int(state.by_id.loc[sid,'census_year'])==2021}
for sid,row in merged.items():
 if int(state.by_id.loc[sid,'census_year'])<2021 and row['integration_packet_kind']=='temporal':
  assert (row['point_origin_file'],row['point_origin_sha256'],float(row['latitude']),float(row['longitude'])) in carriers
  assert row.get('historical_census_coordinate_asserted','False')=='False'
uf=UnionFind(state.obs.source_record_id)
for sid in state.obs.source_record_id:uf.union(state.uf.find(sid),sid)
yearsets={uf.find(r):set(y) for r,y in state.years.items()};coordsets=collections.defaultdict(list)
for sid,p in state.point_rows.items():coordsets[uf.find(sid)].append((p['latitude'],p['longitude']))
for sid,p in merged.items():coordsets[uf.find(sid)].append((float(p['latitude']),float(p['longitude'])))
accepted_edges=[]
for row in edges.to_dict('records'):
 a,b=row['from_source_record_id'],row['to_source_record_id'];assert a in state.by_id.index and b in state.by_id.index;ra,rb=uf.find(a),uf.find(b);reason=''
 if ra==rb:reason='duplicate supplied graph connectivity'
 elif yearsets[ra]&yearsets[rb]:reason='duplicate census year in proposed same-place component'
 elif any(distance_km(x,y)>5 for x in coordsets[ra] for y in coordsets[rb]):reason='newly joined component ownpoint contradiction >5km'
 if reason:holds.append({'kind':'edge','source_record_id':a,'to_source_record_id':b,'reason':reason});continue
 ys=yearsets[ra]|yearsets[rb];coords=coordsets[ra]+coordsets[rb];uf.union(ra,rb);r=uf.find(ra);yearsets.pop(ra,None);yearsets.pop(rb,None);coordsets.pop(ra,None);coordsets.pop(rb,None);yearsets[r]=ys;coordsets[r]=coords;accepted_edges.append(row)
# Never propagate historical coordinates through a held candidate identity.
accepted_edge_roots={uf.find(row['from_source_record_id']) for row in accepted_edges}
current_carriers_by_root=collections.defaultdict(set)
for sid,p in {**state.point_rows,**merged}.items():
 if int(state.by_id.loc[sid,'census_year'])==2021:
  current_carriers_by_root[uf.find(sid)].add((p['point_origin_file'],p['point_origin_sha256'],float(p['latitude']),float(p['longitude'])))
for sid in list(merged):
 row=merged[sid]
 if row['integration_packet_kind']=='temporal' and int(state.by_id.loc[sid,'census_year'])<2021:
  carrier=(row['point_origin_file'],row['point_origin_sha256'],float(row['latitude']),float(row['longitude']))
  if carrier not in current_carriers_by_root[uf.find(sid)]:
   holds.append({'kind':'point','source_record_id':sid,'reason':'continuity reuse lacks source-admitted current carrier in actual accepted identity component'});merged.pop(sid)

pointout=OUT/'accepted_point_use_delta.csv.gz';edgeout=OUT/'accepted_identity_edge_delta.csv.gz';pd.DataFrame(merged.values()).to_csv(pointout,index=False,compression={'method':'gzip','mtime':0});(pd.DataFrame(accepted_edges) if accepted_edges else edges.iloc[:0]).to_csv(edgeout,index=False,compression={'method':'gzip','mtime':0})
state.add_deltas(edge_paths=[edgeout],point_paths=[pointout]);ordinary['root']=ordinary.source_record_id.map(state.uf.find)
after_core,afinite,acore=axes();after_appearance,_,aappearance=axes(appearance);after_inclusion,_,ainclusion=axes(appearance|incids);after,_,acredited=axes(appearance|incids|extraids)
assert state.obs.drop(columns=['root']).equals(protected.drop(columns=['root']));assert all(sid in state.point_rows for sid in incids|extraids)
assert {y:after_inclusion[y]['primary_axis_population']-after_appearance[y]['primary_axis_population'] for y in after}=={'2002':30548,'2010':0,'2021':0}
assert {y:after[y]['primary_axis_population']-after_inclusion[y]['primary_axis_population'] for y in after}=={'2002':9172,'2010':700,'2021':14967}
uid_by_root={}
for r,g in state.obs[state.obs.source_record_id.isin(afinite)].groupby('root'):
 ids=g.sort_values('census_year').source_record_id.tolist();assert len(ids)==3;encoded=json.dumps(ids,ensure_ascii=False,separators=(',',':'));uid_by_root[r]='np3:'+base64.urlsafe_b64encode(hashlib.sha256(encoded.encode()).digest()).decode().rstrip('=')
credited=ordinary[ordinary.source_record_id.isin(acredited)][['source_record_id','census_year','population','population_value_quality']].copy();credited['component_root']=credited.source_record_id.map(state.uf.find);credited['entity_uid']=credited.component_root.map(uid_by_root).fillna('');credited['finite_ordinary_full3_all_ownpoints']=credited.source_record_id.isin(afinite);credited['explicit_appearance_publication_absence_credit']=credited.source_record_id.isin(appearance);credited['explicit_inclusion_credit']=credited.source_record_id.isin(incids);credited['explicit_available_year_lifecycle_round2_credit']=credited.source_record_id.isin(extraids);credited.to_csv(OUT/'applied_primary_credited_UID_roster.csv.gz',index=False,compression={'method':'gzip','mtime':0})
changed=ordinary[ordinary.source_record_id.isin(acredited-bcredited)].copy();lost=ordinary[ordinary.source_record_id.isin(bcredited-acredited)].copy();changed.to_csv(OUT/'actual_newly_credited_primary_source_IDs.csv.gz',index=False,compression={'method':'gzip','mtime':0});lost.to_csv(OUT/'actual_lost_primary_source_IDs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
remaining=ordinary[~ordinary.source_record_id.isin(acredited)].copy();remaining['has_own_point']=remaining.source_record_id.isin(state.point_rows);remaining['component_years']=remaining.source_record_id.map(lambda sid:','.join(map(str,sorted(state.years[state.uf.find(sid)]))));remaining=remaining.sort_values(['population','source_record_id'],ascending=[False,True],na_position='last');remaining.to_csv(OUT/'applied_remaining_primary.csv.gz',index=False,compression={'method':'gzip','mtime':0})
for y,g in remaining.groupby('census_year'):g.head(20).to_csv(OUT/f'top20_applied_remaining_primary_{int(y)}.csv',index=False)
pd.DataFrame(holds,columns=['kind','source_record_id','to_source_record_id','reason']).to_csv(OUT/'integration_holds.csv',index=False)
cs=state.obs[['source_record_id','root']].copy();cs['has_own_point']=cs.source_record_id.isin(state.point_rows);cs.to_csv(OUT/'applied_component_snapshot.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame([{'source_record_id':sid,**p} for sid,p in state.point_rows.items()]).fillna('').astype(str).to_parquet(OUT/'applied_point_snapshot.parquet',index=False,compression='zstd')
back=read(OUT/'applied_remaining_primary.csv.gz');assert back.source_record_id.is_unique and set(back.source_record_id)==set(remaining.source_record_id)
gains={y:{'newly_credited_source_IDs':int(changed.census_year.eq(int(y)).sum()),'lost_source_IDs':int(lost.census_year.eq(int(y)).sum()),'net_primary_population_gain':after[y]['primary_axis_population']-before[y]['primary_axis_population'],'net_core_formation_plus_direct_population_gain':after_core[y]['primary_axis_population']-before_core[y]['primary_axis_population'],'net_finite_all3_ownpoint_population_gain':after[y]['finite_all3_ownpoints_population']-before[y]['finite_all3_ownpoints_population'],'new_finite_all3_ownpoint_histories':after[y]['finite_all3_ownpoints_rows']-before[y]['finite_all3_ownpoints_rows']} for y in before}
for y,g in gains.items():assert g['net_primary_population_gain']==int(changed.loc[changed.census_year.eq(int(y)),'population'].sum())-int(lost.loc[lost.census_year.eq(int(y)),'population'].sum())
outputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file() and p.name!='application_receipt.json'}
result={'status':'applied_actual_frozen62_sourcebound_native_identity_ownpoints_and_explicit_inclusion_batch','baseline_stage':62,'intended_working_stage':63,'frozen_baseline_commit':config['baseline_commit'],'actual_State_loads':0,'application_recipe_version':2,'superseded_application_receipt_sha256':'abaec3afc2aba7d733542eb5fe92517aaeb79febbc10960cb39f7b0b9ce2f99e','recipe_correction':'allow source-admitted current carrier reuse in an already accepted two-year identity component; prior recipe incorrectly required full3; prior output bytes preserved in replay_v1_preserved','cache_hydration_used':True,'full_active_point_row_fields_hydrated':True,'baseline_reproduced':True,'canonical_State_API_replay_passed':True,'accepted_edges':len(accepted_edges),'accepted_point_uses':len(merged),'point_replacements':len(reject),'new_unique_point_targets':len(set(state.point_rows)-prepoints),'input_point_target_overlap_rows':len(points)-points.target_source_record_id.nunique(),'integration_holds':len(holds),'before':before,'before_core_formation_plus_direct_axis':before_core,'after_core_formation_plus_direct_axis':after_core,'after_appearance_axis':after_appearance,'after_inclusion_axis':after_inclusion,'after':after,'primary_with_explicit_appearance_and_inclusion_axis':after,'appearance_native_source_IDs':sorted(appearance),'new_inclusion_native_source_IDs':sorted(incids),'new_available_year_lifecycle_round2_source_IDs':sorted(extraids),'new_lifecycle_round2_additional_source_ID_population':{'2002':9172,'2010':700,'2021':14967},'new_lifecycle_packet_projections':[{'kind':'included_in','prefix':'inclusion_','credit_file':'inclusion_accepted_direct_event_native_credit_union.csv','UIDs':6},{'kind':'explicit_available_year_lifecycle','prefix':'lifecycle_round2_','credit_file':'lifecycle_round2_accepted_source_UID_credit_union.csv','UIDs':6}],'new_inclusion_additional_source_ID_population':{'2002':30548,'2010':0,'2021':0},'typed_inclusion_same_place_graph_union_allowed':False,'parent_context_new_population_credit':0,'unknown_population_imputed':False,'source_population_quality_names_codes_unchanged':True,'population510_overlay_included':False,'actual_gain_by_unique_source_ID_union':gains,'after_State_metrics':state.metrics(),'source_control_deficits_unallocated':EXTERNAL,'input_pins':PINS,'output_pins':outputs,'wall_seconds':round(time.monotonic()-START,3)}
(OUT/'application_receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['input_pins','output_pins','after_State_metrics']},ensure_ascii=False))
