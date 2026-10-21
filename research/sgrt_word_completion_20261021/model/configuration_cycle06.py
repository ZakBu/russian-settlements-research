#!/usr/bin/env python3
"""Auditable Word configurations from comparable same-order shared rural fields.

Returns (one row per systems key, auxiliary DataFrame dictionary). No hard
membership, mass, rank or demographic quantity is changed. The caller persists
auxiliary tables and calls configuration_protocol() BEFORE classification.
"""
from pathlib import Path
import argparse,hashlib,itertools,json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

PROTOCOL_VERSION='cycle06_word_configuration_preregistered_v1'
DEFAULTS={'mass_ratio':.5,'mass_ratio_sensitivity':[.33,.5,.67],
 'substantial_shared_origin_fraction':.1,'mono_probability':.8,
 'mono_origin_fraction':.9,'mono_minimum_eligible_origins':3,
 'minimum_shared_origins':1,'near_origin_chunk_size':3000}
REPO=Path(__file__).resolve().parents[3]
TOL=1e-4

def configuration_protocol(config):
 p={**DEFAULTS,**config.get('configuration_policy',{})}
 model=config.get('model',{})
 p.update(competition_ratio=float(model.get('competition_ratio',.8)),
          pair_joint_probability_min=float(p.get('pair_joint_probability_min',model.get('minimum_choice_probability',.35))),
          outside_mass=float(model.get('outside_mass',0)),time_decay_minutes=float(model.get('time_decay_minutes',30)),
          lower_order_field_budget_minutes=float(model.get('max_travel_minutes',180)),
          higher_order_field_budget_minutes=float(model.get('hierarchy_max_travel_minutes',360)))
 assert 0<p['mass_ratio']<=1 and all(0<v<=1 for v in p['mass_ratio_sensitivity'])
 assert 0<p['competition_ratio']<=1 and 0<=p['pair_joint_probability_min']<=1
 assert p['outside_mass']>=0 and p['time_decay_minutes']>0
 return {'version':PROTOCOL_VERSION,'parameters':p,
  'word_basis':'Original Word configuration paragraphs: comparable own mass; centers of same order; common rural territory with close probabilities; higher-order suburban child complexes.',
  'field':'All reachable modeled centers of the SAME intrinsic empirical order in denominator; r1 direct<=180, r>=2 direct<=360 unless explicitly configured otherwise; same declared outside option. No hierarchical leg sums.',
  'eligible_origins':'Ordinary additive with explicit native source_record_id_2021, known V3 statistically rural, observed population2021>0; source center cores of same/higher intrinsic order excluded. Lower-order rural centers may be dependent origins for higher orders.',
  'frame_completeness':'Primary field is the observed native2021 frame. Unknown roles/population in that native frame block positive mono. Historical-only additive rows outside native2021 are counted separately, never assumed extinct/zero; full historical-axis completeness is a separate stricter diagnostic.',
  'raw_overlap':'Both endpoints g/gmax >= competition_ratio; distinct same-order center IDs. Preserve raw witnesses even if mass comparability or additional pair-joint-Huff strength fails.',
  'support':'Comparable min/max ownMi>=threshold AND sum of the two full-order Huff probabilities>=pair_joint_probability_min. Additional joint-strength gate is operational, not a literal Word requirement.',
  'complex':'A single common origin with a mutually mass-comparable near-top center set. Never merge chains of overlap pairs into one comparable-mass complex.',
  'L1':'Structural hard-assignment unit only; cross-boundary peer-overlap memberships reported separately, never structural one-core=>functional monocentricity.',
  'nested':'Highest represented intrinsic child order STRICTLY below parent order, excluding superior parent. Both peers AND shared origin must belong to the same current higher union.',
  'mono':'Positive dominant-field test q>=mono_probability for >=mono_origin_fraction of >=mono_minimum_eligible_origins; complete bounded matrix field and no unresolved population/role frame or snap-tie ambiguity. No supported pairs is never sufficient.',
  'coverage':'Exact loaded pair membership and float32-time bits, route counts, plus two commutative pair/time diagnostics compared against exact compact matrix; all same-order destinations must have declared sufficient source budgets. This proves bounded computational field completeness, not real service or road inventory completeness.',
  'decision_order':'L1 structural; otherwise positive shared-field support first, then positive dominant-field support, otherwise unknown. Nested child configuration is a separate axis.',
  'interpretation':'Modeled potential only; empirical orders are not independently established service tiers; no observed joint trips, actual functional mono/poly or causal effect asserted.',
  'source_or_model_agreements_used_to_tune_parameters':False,'helper_code_sha256':_sha(Path(__file__))}

def _sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 return h.hexdigest()

def _path(value):
 p=Path(value);return p if p.is_absolute() else REPO/p

def _codes(s,ids):
 if isinstance(s.dtype,pd.CategoricalDtype) and np.array_equal(s.cat.categories.to_numpy(),ids.to_numpy()):return s.cat.codes.to_numpy(dtype='int32',copy=False)
 return ids.get_indexer(s.to_numpy()).astype('int32')

def _signature(o,d,t):
 if not len(o):return (0,0,0)
 # Explicit modulo-2**64 arithmetic, order-independent multiset diagnostics.
 x=(o.astype('uint64')<<np.uint64(32))|d.astype('uint64')
 x^=t.astype('float32').view('uint32').astype('uint64')*np.uint64(0x9E3779B97F4A7C15)
 x^=x>>np.uint64(30);x*=np.uint64(0xBF58476D1CE4E5B9);x^=x>>np.uint64(27)
 return (len(o),int(x.sum(dtype='uint64')),int(np.bitwise_xor.reduce(x)))

def _combine(a,b):return (a[0]+b[0],(a[1]+b[1])%(1<<64),a[2]^b[2])

def _source_coverage(config,ids,ranks,eligible,loaded_signatures,budgets,loaded_records):
 """Independently compare retained fields with the complete bounded source."""
 rows=[];source={};snap_ties=np.zeros(len(ids),dtype=bool)
 if config.get('_configuration_inline_test_source',False):
  assert config.get('_configuration_test_only',False),'Inline completeness is only allowed in explicit synthetic fixtures'
  for value in config.get('_configuration_test_snap_tie_ids',[]):
   where=ids.get_indexer([value]);assert where[0]>=0;snap_ties[where[0]]=True
  return ({r:True for r in budgets},pd.DataFrame([{'order':r,'field_budget_minutes':b,'status':'EXPLICIT_SYNTHETIC_COMPLETE_TABLE','field_source_complete':True,'loaded_routes':loaded_signatures[r][0]} for r,b in budgets.items()]),source,snap_ties)
 value=config.get('travel_manifest')
 if not value:
  return ({r:False for r in budgets},pd.DataFrame([{'order':r,'field_budget_minutes':b,'status':'NO_COMPACT_SOURCE_PROOF','field_source_complete':False,'loaded_routes':loaded_signatures[r][0]} for r,b in budgets.items()]),source,snap_ties)
 mp=_path(value);m=json.loads(mp.read_text());source[str(mp)]=_sha(mp)
 assert m['format']=='compact_parquet_parts_v1'
 maps=[]
 for key in ['origin_mapping','destination_mapping']:
  p=mp.parent/m[key]['path'];assert _sha(p)==m[key]['sha256'];source[str(p)]=_sha(p);maps.append(pd.read_parquet(p))
 origin,dest=maps;aliases=config.get('route_id_aliases',{})
 oc=ids.get_indexer(origin.id.replace(aliases)).astype('int32');dc=ids.get_indexer(dest.id.replace(aliases)).astype('int32')
 assert (oc>=0).all() and (dc>=0).all(),'Routing mappings outside prepared nodes'
 origin_minutes=origin.snap_km.to_numpy(float)*4;dest_minutes=dest.snap_km.to_numpy(float)*4
 expected={r:(0,0,0) for r in budgets};destination_complete={};source_mismatches={r:0 for r in budgets}
 for r,budget in budgets.items():
  have=dest.loc[dest.id.replace(aliases).isin(ids[ranks==r]),'routing_budget_minutes']
  destination_complete[r]=len(have)==int((ranks==r).sum()) and have.ge(budget-TOL).all()
 for part in m['parts']:
  pp=mp.parent/part['path'];assert _sha(pp)==part['sha256'];source[str(pp)]=part['sha256']
  q=pq.read_table(pp,columns=['origin_index','destination_index','network_minutes']);oi=q['origin_index'].to_numpy();di=q['destination_index'].to_numpy();o=oc[oi];d=dc[di];t=(q['network_minutes'].to_numpy()+(origin_minutes[oi]+dest_minutes[di]).astype('float32')).astype('float32');t[o==d]=0
  for r,budget in budgets.items():
   mask=eligible&(ranks<r);take=mask[o]&(ranks[d]==r)&np.isfinite(t)&(t>=0)&(t<=budget+TOL)
   if config.get('origin_id_filter'):take&=np.isin(o,ids.get_indexer(config['origin_id_filter']))
   expected[r]=_combine(expected[r],_signature(o[take],d[take],t[take]))
   keys=(o[take].astype('uint64')<<np.uint64(32))|d[take].astype('uint64');record=loaded_records[r];positions=np.searchsorted(record['key'],keys);ok=positions<len(record['key'])
   if ok.any():
    at=np.flatnonzero(ok);ok[at]&=record['key'][positions[at]]==keys[at]
   if ok.any():
    at=np.flatnonzero(ok);ok[at]&=record['time'][positions[at]].view('uint32')==t[take][at].astype('float32').view('uint32')
   source_mismatches[r]+=int((~ok).sum());record['seen'][positions[ok]]=True
 snap=mp.parent/'settlement_road_snap.parquet'
 if snap.exists():
  schema=pq.read_schema(snap).names
  if 'nearest_vertex_distance_tie' in schema:
   s=pd.read_parquet(snap,columns=['id','nearest_vertex_distance_tie']);ix=ids.get_indexer(s.id.replace(aliases));ok=ix>=0;snap_ties[ix[ok]]=s.loc[ok,'nearest_vertex_distance_tie'].fillna(False).to_numpy(bool);source[str(snap)]=_sha(snap)
 complete={}
 for r,b in budgets.items():
  matched=expected[r]==loaded_signatures[r];exact=source_mismatches[r]==0 and expected[r][0]==loaded_signatures[r][0] and bool(loaded_records[r]['seen'].all()) and loaded_records[r]['unique'];complete[r]=bool(matched and exact and destination_complete[r]);rows.append({'order':r,'field_budget_minutes':b,'status':'EXACT_BOUNDED_SOURCE_FIELD_MATCH' if complete[r] else 'INCOMPLETE_OR_DIFFERENT_RETAINED_FIELD','field_source_complete':complete[r],'declared_destination_budgets_complete':bool(destination_complete[r]),'loaded_routes':loaded_signatures[r][0],'source_routes':expected[r][0],'loaded_signature_sum':str(loaded_signatures[r][1]),'source_signature_sum':str(expected[r][1]),'loaded_signature_xor':str(loaded_signatures[r][2]),'source_signature_xor':str(expected[r][2]),'pair_time_signature_match':bool(matched),'exact_pair_time_membership_match':bool(exact),'source_rows_missing_or_different_in_loaded_field':source_mismatches[r],'loaded_rows_not_seen_in_source':int((~loaded_records[r]['seen']).sum()),'known_road_snap_ties_in_frame':int(snap_ties.sum())})
 return complete,pd.DataFrame(rows),source,snap_ties


def _mass_windows(group,threshold):
 a=group if isinstance(group,list) else group.sort_values(['mass','c'],ascending=[False,True]).to_dict('records');last_end=-1
 for start in range(len(a)):
  end=start
  while end<len(a) and a[end]['mass']>=threshold*a[start]['mass']-1e-12:end+=1
  if end-start>=2 and end>last_end:
   yield a[start:end]
   last_end=end


def configuration_table(nodes,members,systems,levels,centers,travel,config):
 protocol=configuration_protocol(config);p=protocol['parameters'];ids=pd.Index(nodes.id)
 assert ids.is_unique and np.array_equal(nodes.id.to_numpy(),members.id.to_numpy())
 assert not systems.duplicated(['level','center_id']).any()
 required=['accepted_statistical_rural_role2021','_population_axis_row','population_2021']
 if not set(required)<=set(nodes):raise ValueError('Missing explicit statistical-rural source fields')
 role=nodes.accepted_statistical_rural_role2021.astype('boolean');population=pd.to_numeric(nodes.population_2021,errors='coerce').to_numpy(float)
 axis=nodes._population_axis_row.fillna(False).to_numpy(bool)
 if 'source_record_id_2021' in nodes:native2021=nodes.source_record_id_2021.notna().to_numpy()
 elif config.get('_configuration_test_only'):native2021=axis.copy()
 else:raise ValueError('Require explicit source_record_id_2021 to distinguish observed2021 frame from historical-only axis')
 eligible=axis&native2021&role.fillna(False).to_numpy(bool)&np.isfinite(population)&(population>0)
 c=centers[['id','intrinsic_empirical_rank','own_positive_mass']].sort_values('id').reset_index(drop=True)
 assert c.id.is_unique and c.own_positive_mass.gt(0).all() and np.isfinite(c.own_positive_mass).all()
 ci=ids.get_indexer(c.id);assert (ci>=0).all();ranks=np.zeros(len(nodes),dtype='int16');ranks[ci]=c.intrinsic_empirical_rank.to_numpy('int16');mass=np.zeros(len(nodes),dtype=float);mass[ci]=c.own_positive_mass.to_numpy(float)
 order_values=sorted(int(v) for v in c.intrinsic_empirical_rank.unique());budgets={r:p['lower_order_field_budget_minutes'] if r==1 else p['higher_order_field_budget_minutes'] for r in order_values}
 o=_codes(travel.origin_id,ids);d=_codes(travel.destination_id,ids);assert (o>=0).all() and (d>=0).all();minutes=travel.travel_minutes.to_numpy('float32');routeok=np.isfinite(minutes)&(minutes>=0)
 if 'route_status' in travel:routeok&=travel.route_status.isin(['routed','reachable','ok']).to_numpy()
 field_parts=[];near_parts=[];pair_parts=[];loaded={};field_arrays={};loaded_records={}
 for r,budget in budgets.items():
  depends=eligible&(ranks<r);take=routeok&depends[o]&(ranks[d]==r)&(minutes<=budget+TOL);oo=o[take];dd=d[take];tt=minutes[take]
  loaded[r]=_signature(oo,dd,tt);keys=(oo.astype('uint64')<<np.uint64(32))|dd.astype('uint64');permutation=np.argsort(keys);sortedkeys=keys[permutation];loaded_records[r]={'key':sortedkeys,'time':tt[permutation],'seen':np.zeros(len(oo),dtype=bool),'unique':bool(len(sortedkeys)<2 or (sortedkeys[1:]!=sortedkeys[:-1]).all())};g=mass[dd]*np.exp(-tt.astype(float)/p['time_decay_minutes']);totals=np.bincount(oo,weights=g,minlength=len(nodes));counts=np.bincount(oo,minlength=len(nodes));best=np.zeros(len(nodes));np.maximum.at(best,oo,g);winner=np.full(len(nodes),len(c),dtype='int32');lexrank=np.full(len(nodes),len(c),dtype='int32');lexrank[ci]=np.arange(len(c),dtype='int32');attop=np.abs(g-best[oo])<=1e-12*np.maximum(best[oo],1e-300);np.minimum.at(winner,oo[attop],lexrank[dd[attop]]);prob=np.divide(g,totals[oo]+p['outside_mass'],out=np.zeros_like(g),where=(totals[oo]+p['outside_mass'])>0);q=np.divide(best,totals+p['outside_mass'],out=np.full(len(nodes),np.nan),where=(counts>0)&((totals+p['outside_mass'])>0));haswinner=winner<len(c);winner[haswinner]=ci[winner[haswinner]];winner[~haswinner]=-1
  ii=np.flatnonzero(depends);field_parts.append(pd.DataFrame({'order':r,'origin_code':ii,'origin_id':ids[ii].to_numpy(),'population_2021':population[ii],'routed_same_order_centers':counts[ii],'maximum_gravity':best[ii],'same_order_gravity_sum':totals[ii],'dominant_probability':q[ii],'dominant_center_code':winner[ii],'dominant_center_id':[None if v<0 else ids[v] for v in winner[ii]],'field_budget_minutes':budget}))
  field_arrays[r]={'count':counts,'winner':winner,'q':q,'depends':depends}
  close=(g>0)&(best[oo]>0)&(g>=p['competition_ratio']*best[oo]*(1-1e-12));near=pd.DataFrame({'o':oo[close],'c':dd[close],'time':tt[close],'g':g[close],'p':prob[close],'mass':mass[dd[close]]});assert not near.duplicated(['o','c']).any(),'Duplicate direct origin-peer route'
  number=near.groupby('o',sort=False).size();near=near[near.o.isin(number[number>=2].index)].sort_values(['o','c']);near['order']=r;near_parts.append(near)
  originlist=near.o.unique()
  for start in range(0,len(originlist),int(p['near_origin_chunk_size'])):
   chunk=near[near.o.isin(originlist[start:start+int(p['near_origin_chunk_size'])])];pairs=chunk.merge(chunk,on=['o','order'],suffixes=('_a','_b'));pairs=pairs[pairs.c_a<pairs.c_b].copy()
   if len(pairs):
    pairs['mass_ratio']=np.minimum(pairs.mass_a,pairs.mass_b)/np.maximum(pairs.mass_a,pairs.mass_b);pairs['pair_joint_probability']=pairs.p_a+pairs.p_b;pairs['gravity_ratio']=np.minimum(pairs.g_a,pairs.g_b)/np.maximum(pairs.g_a,pairs.g_b);pairs['joint_strength_supported']=pairs.pair_joint_probability.ge(p['pair_joint_probability_min']);pair_parts.append(pairs)
 complete,coverage,source_pins,snap_ties=_source_coverage(config,ids,ranks,eligible,loaded,budgets,loaded_records)
 del loaded_records
 for r,budget in budgets.items():
  a=field_arrays[r];take=routeok&a['depends'][o]&(ranks[d]==r)&(minutes<=budget+TOL);tie=np.zeros(len(nodes),dtype=bool);np.logical_or.at(tie,o[take],snap_ties[d[take]]);a['contributing_destination_snap_tie']=tie
 fields=pd.concat(field_parts,ignore_index=True) if field_parts else pd.DataFrame();raw=pd.concat(pair_parts,ignore_index=True) if pair_parts else pd.DataFrame(columns=['o','order','c_a','c_b','time_a','time_b','g_a','g_b','p_a','p_b','mass_a','mass_b','mass_ratio','pair_joint_probability','gravity_ratio','joint_strength_supported'])
 if len(raw):
  raw['origin_id']=ids[raw.o.to_numpy('int32')].to_numpy();raw['peer_a_id']=ids[raw.c_a.to_numpy('int32')].to_numpy();raw['peer_b_id']=ids[raw.c_b.to_numpy('int32')].to_numpy();raw['population_2021']=population[raw.o.to_numpy('int32')];raw['origin_road_snap_tie']=snap_ties[raw.o.to_numpy('int32')];raw['peer_road_snap_tie']=snap_ties[raw.c_a.to_numpy('int32')]|snap_ties[raw.c_b.to_numpy('int32')]
 for column,dtype in [('origin_id','string'),('peer_a_id','string'),('peer_b_id','string'),('population_2021','float64'),('origin_road_snap_tie','bool'),('peer_road_snap_tie','bool')]:
  if column not in raw:raw[column]=pd.Series(index=raw.index,dtype=dtype)
 raw['joint_strength_supported']=raw.joint_strength_supported.fillna(False).astype(bool)
 raw['observed_shared_service_flows']=False
 raw['origin_is_lower_order_rural_center']=ranks[raw.o.to_numpy('int32')]>0
 sensitivities=sorted(set(float(v) for v in p['mass_ratio_sensitivity'])|{float(p['mass_ratio'])})
 supported_parts=[];complex_origins=[]
 for ratio in sensitivities:
  supported=raw[raw.joint_strength_supported&raw.mass_ratio.ge(ratio-1e-12)].copy();supported['mass_ratio_threshold']=ratio
  if len(supported):
   a=supported.groupby(['order','peer_a_id','peer_b_id'],sort=True).agg(n_shared_positive_rural_origins=('origin_id','nunique'),shared_population2021=('population_2021','sum'),minimum_joint_probability=('pair_joint_probability','min'),minimum_gravity_ratio=('gravity_ratio','min'),own_mass_ratio=('mass_ratio','first')).reset_index();a['mass_ratio_threshold']=ratio;supported_parts.append(a)
 for near in near_parts:
  for origin,group in near.groupby('o',sort=False):
   candidates=group.sort_values(['mass','c'],ascending=[False,True]).to_dict('records');order=int(group.order.iloc[0])
   for ratio in sensitivities:
    for window in _mass_windows(candidates,ratio):
     codes=sorted(int(a['c']) for a in window);names=[str(ids[k]) for k in codes];text=json.dumps(names,ensure_ascii=False,separators=(',',':'));identity=hashlib.sha256((str(order)+'|'+str(ratio)+'|'+text).encode()).hexdigest()[:24];probs=sorted(float(a['p']) for a in window);complex_origins.append({'complex_id':identity,'order':order,'mass_ratio_threshold':ratio,'origin_code':int(origin),'origin_id':ids[int(origin)],'population_2021':float(population[int(origin)]),'peer_ids_json':text,'n_peer_centers':len(codes),'minimum_to_maximum_mass_ratio':min(a['mass'] for a in window)/max(a['mass'] for a in window),'all_pair_joint_strength_supported':probs[0]+probs[1]>=p['pair_joint_probability_min']-1e-12,'joint_probability':sum(probs),'common_origin_source_witness':True,'transitive_chain_merge_used':False})
 complexes_long=pd.DataFrame(complex_origins,columns=['complex_id','order','mass_ratio_threshold','origin_code','origin_id','population_2021','peer_ids_json','n_peer_centers','minimum_to_maximum_mass_ratio','all_pair_joint_strength_supported','joint_probability','common_origin_source_witness','transitive_chain_merge_used'])
 if len(complexes_long):
  complexes=complexes_long.groupby(['complex_id','order','mass_ratio_threshold','peer_ids_json','n_peer_centers'],sort=True).agg(n_shared_rural_origins=('origin_id','nunique'),shared_population2021=('population_2021','sum'),minimum_to_maximum_mass_ratio=('minimum_to_maximum_mass_ratio','min'),n_joint_strength_supported_origins=('all_pair_joint_strength_supported','sum')).reset_index();complexes['transitive_chain_merge_used']=False
 else:complexes=pd.DataFrame(columns=['complex_id','order','mass_ratio_threshold','peer_ids_json','n_peer_centers','n_shared_rural_origins','shared_population2021','minimum_to_maximum_mass_ratio','n_joint_strength_supported_origins','transitive_chain_merge_used'])
 assignment={};groups={};excluded=[]
 systemkeys=set(zip(systems.level.astype(int),systems.center_id.astype(str)))
 for level,values in levels.items():
  assert len(values)==len(nodes);codes=_codes(pd.Series(values.to_numpy()),ids);assignment[int(level)]=codes;valid=np.flatnonzero(codes>=0)
  for parent,g in pd.DataFrame({'parent':codes[valid],'i':valid}).groupby('parent',sort=False):
   groups[(int(level),int(parent))]=g.i.to_numpy('int32')
   if (int(level),str(ids[int(parent)])) not in systemkeys:excluded.append({'level':int(level),'center_id':str(ids[int(parent)]),'n_assignment_rows':len(g),'reason':'assignment_key_absent_from_population_systems_no_phantom_configuration'})
 pair_lookup={}
 for key,g in raw.groupby('order',sort=False):pair_lookup[int(key)]=g
 focal_lookup={};union_lookup={}
 if len(raw):
  endpoints=pd.concat([raw[['order','c_a']].rename(columns={'c_a':'peer'}).assign(row=raw.index),raw[['order','c_b']].rename(columns={'c_b':'peer'}).assign(row=raw.index)],ignore_index=True)
  for key,g in endpoints.groupby(['order','peer'],sort=False):focal_lookup[(int(key[0]),int(key[1]))]=g.row.to_numpy('int64')
  for lev,assigned in assignment.items():
   indexed=pd.DataFrame({'parent':assigned[raw.o.to_numpy('int32')],'order':raw.order.to_numpy(),'row':raw.index.to_numpy()})
   for key,g in indexed.groupby(['parent','order'],sort=False):union_lookup[(int(lev),int(key[0]),int(key[1]))]=g.row.to_numpy('int64')
 rows=[];sensitivity_rows=[];system_witness_parts=[]
 for item in systems[['level','center_id']].itertuples(index=False):
  level=int(item.level);parent=int(ids.get_indexer([item.center_id])[0]);assert parent>=0;indices=groups.get((level,parent),np.array([],dtype='int32'));parentrank=int(ranks[parent]);children=indices[(ranks[indices]>0)&(ranks[indices]<parentrank)&(indices!=parent)];childrank=int(ranks[children].max()) if len(children) else None
  external_axis=axis[indices]&(indices!=parent);role_missing=role.iloc[indices].isna().to_numpy();rural_missing_population=role.iloc[indices].fillna(False).to_numpy(bool)&~np.isfinite(population[indices])
  unknown_role=int((external_axis&native2021[indices]&role_missing).sum());historical_unknown_role=int((external_axis&~native2021[indices]&role_missing).sum());missing_rural_population=int((external_axis&native2021[indices]&rural_missing_population).sum());historical_missing_rural_population=int((external_axis&~native2021[indices]&rural_missing_population).sum())
  base={'level':level,'center_id':item.center_id,'focal_intrinsic_order':parentrank if parentrank else None,'child_order_evaluated':childrank,'n_distinct_contained_lower_order_centers':len(children),'unknown_statistical_role_members':unknown_role,'unknown_statistical_role_native2021_members':unknown_role,'unknown_statistical_role_historical_only_members':historical_unknown_role,'known_rural_members_missing_population2021':missing_rural_population,'known_rural_historical_only_members_missing_population2021':historical_missing_rural_population,'historical_axis_role_population_complete':bool(unknown_role+historical_unknown_role+missing_rural_population+historical_missing_rural_population==0),'n_historical_only_external_axis_members':int((external_axis&~native2021[indices]).sum()),'historical_only_external_population_known_sum2021':float(np.nansum(population[indices][external_axis&~native2021[indices]])),'historical_only_external_population_known_count2021':int((external_axis&~native2021[indices]&np.isfinite(population[indices])).sum()),'configuration_frame':'observed_native2021_positive_rural','actual_multicenter_service_flows_observed':False,'hard_partition_changed':False,'configuration_is_empirical_order_potential_only':True}
  for ratio in sensitivities:
   result={**base,'mass_ratio_threshold':ratio}
   def evaluate(order,peer_subset=None,focal=None,scope='own_order'):
    if order is None or order not in field_arrays:return {'n':0,'shared':0,'share':np.nan,'popshare':np.nan,'source_complete':False,'dominance_share':np.nan,'dominant_center':None,'mono':False,'poly':False,'road_tie':False,'literal_shared':0,'literal_share':np.nan}
    a=field_arrays[order];ii=indices[a['depends'][indices]];n=len(ii);denpop=float(population[ii].sum()) if n else 0.;lookup=focal_lookup.get((order,focal),[]) if focal is not None else union_lookup.get((level,parent,order),[]);w=raw.loc[lookup];w=w[w.mass_ratio.ge(ratio-1e-12)]
    if focal is not None:w=w[w.c_a.eq(focal)|w.c_b.eq(focal)]
    if peer_subset is not None:w=w[w.c_a.isin(peer_subset)&w.c_b.isin(peer_subset)]
    w=w[w.o.isin(ii)];literal_shared=np.unique(w.o.to_numpy('int32'));literal_share=len(literal_shared)/n if n else np.nan;w=w.loc[w.joint_strength_supported.fillna(False).astype(bool)]
    if len(w) and np.isclose(ratio,p['mass_ratio']):
     links=w[['origin_id','peer_a_id','peer_b_id','order','time_a','time_b','g_a','g_b','p_a','p_b','mass_ratio','pair_joint_probability','population_2021']].copy();links['level']=level;links['system_center_id']=item.center_id;links['configuration_scope']=scope;links['peer_a_in_current_union']=assignment[level][w.c_a.to_numpy('int32')]==parent;links['peer_b_in_current_union']=assignment[level][w.c_b.to_numpy('int32')]==parent;links['shared_origin_in_current_union']=True;system_witness_parts.append(links)
    shared=np.unique(w.o.to_numpy('int32'));share=len(shared)/n if n else np.nan;popshare=float(population[shared].sum()/denpop) if denpop>0 else np.nan
    votes=a['winner'][ii];strong=np.isfinite(a['q'][ii])&(a['q'][ii]>=p['mono_probability']);vote_counts=pd.Series(votes[strong&votes.__ge__(0)]).value_counts();dom=int(vote_counts.index[0]) if len(vote_counts) else None;dominance=float(vote_counts.iloc[0]/n) if n and len(vote_counts) else np.nan
    if focal is not None:dominance=float(((votes==focal)&strong).sum()/n) if n else np.nan;dom=focal if n else None
    if peer_subset is not None and dom not in set(peer_subset):dominance=np.nan;dom=None
    road_tie=bool(snap_ties[ii].any() or a['contributing_destination_snap_tie'][ii].any() or (focal is not None and snap_ties[focal]) or (dom is not None and snap_ties[dom]))
    source_complete=bool(complete.get(order,False) and n and (a['count'][ii]>0).all() and unknown_role==0 and missing_rural_population==0 and not road_tie)
    mono=bool(n>=p['mono_minimum_eligible_origins'] and source_complete and np.isfinite(dominance) and dominance>=p['mono_origin_fraction'])
    poly=bool(complete.get(order,False) and n and len(shared)>=p['minimum_shared_origins'] and share>=p['substantial_shared_origin_fraction'])
    return {'n':n,'shared':len(shared),'share':share,'popshare':popshare,'source_complete':source_complete,'dominance_share':dominance,'dominant_center':None if dom is None else str(ids[dom]),'mono':mono,'poly':poly,'road_tie':road_tie,'literal_shared':len(literal_shared),'literal_share':literal_share}
   own=evaluate(parentrank,focal=parent) if parentrank else evaluate(None)
   nested=evaluate(childrank,peer_subset=children[ranks[children]==childrank],scope='nested_child') if childrank is not None else evaluate(None)
   ownlabel='structural_assignment_unit' if level==1 else ('polycentric_peer_field_potential' if own['poly'] else 'monocentric_field_potential' if own['mono'] else 'configuration_unknown')
   nestedlabel='polycentric_child_complex_potential' if nested['poly'] else 'monocentric_child_field_potential' if nested['mono'] else 'configuration_unknown'
   def reason(label,evidence):
    if label=='structural_assignment_unit':return 'hard_partition_one_core_does_not_establish_functional_configuration'
    if label!='configuration_unknown':return 'positive_conditional_modeled_field_evidence_not_observed_flows'
    if evidence['n']==0:return 'no_eligible_positive_rural_origins'
    if evidence['literal_shared'] and not evidence['shared']:return 'literal_comparable_overlap_preserved_but_additional_joint_strength_filter_not_met'
    if evidence['road_tie']:return 'road_attachment_tie_affects_evaluated_field'
    return 'incomplete_or_mixed_field_no_positive_configuration_test'
   result.update(own_order_status_reason=reason(ownlabel,own),nested_status_reason=reason(nestedlabel,nested),modeled_configuration=ownlabel,same_order_configuration=ownlabel,nested_child_configuration=nestedlabel,own_order_eligible_positive_rural_origins=own['n'],own_order_literal_shared_origins=own['literal_shared'],own_order_literal_shared_origin_fraction=own['literal_share'],own_order_shared_origins=own['shared'],own_order_shared_origin_fraction=own['share'],own_order_shared_population_fraction=own['popshare'],own_order_dominance_fraction=own['dominance_share'],own_order_field_complete=own['source_complete'],own_order_road_snap_tie=own['road_tie'],nested_eligible_positive_rural_origins=nested['n'],nested_literal_shared_origins=nested['literal_shared'],nested_literal_shared_origin_fraction=nested['literal_share'],nested_shared_origins=nested['shared'],nested_shared_origin_fraction=nested['share'],nested_shared_population_fraction=nested['popshare'],nested_dominance_fraction=nested['dominance_share'],nested_dominant_child_id=nested['dominant_center'],nested_field_complete=nested['source_complete'],nested_road_snap_tie=nested['road_tie'],cross_boundary_peer_overlap_member=bool(own['shared']>0),own_order_substantial_polycentric_field_support=own['poly'],nested_substantial_polycentric_field_support=nested['poly'])
   sensitivity_rows.append(result)
   if np.isclose(ratio,p['mass_ratio']):rows.append(result)
 result=pd.DataFrame(rows);assert len(result)==len(systems) and list(zip(result.level,result.center_id))==list(zip(systems.level,systems.center_id))
 if len(fields):
  fields['field_source_complete']=fields['order'].map(complete);fields['origin_road_snap_tie']=snap_ties[fields.origin_code.to_numpy('int32')];fields['contributing_destination_snap_tie']=np.concatenate([field_arrays[int(r)]['contributing_destination_snap_tie'][fields.loc[fields.order.eq(r),'origin_code'].to_numpy('int32')] for r in order_values]);fields['region']=nodes.region.iloc[fields.origin_code.to_numpy('int32')].fillna('REGION_UNKNOWN').to_numpy() if 'region' in nodes else 'REGION_UNKNOWN';regional=fields.groupby(['order','region'],dropna=False).agg(eligible_positive_rural_origins=('origin_id','size'),origins_with_any_same_order_route=('routed_same_order_centers',lambda x:int(x.gt(0).sum())),road_snap_tie_origins=('origin_road_snap_tie','sum'),origins_with_contributing_destination_snap_tie=('contributing_destination_snap_tie','sum')).reset_index()
 else:regional=pd.DataFrame(columns=['order','region','eligible_positive_rural_origins','origins_with_any_same_order_route','road_snap_tie_origins'])
 source_frame=pd.DataFrame({'region':nodes.region.fillna('REGION_UNKNOWN').to_numpy() if 'region' in nodes else 'REGION_UNKNOWN','axis_unit':axis,'native2021_axis_unit':axis&native2021,'historical_only_axis_unit':axis&~native2021,'unknown_statistical_rural_role':axis&native2021&role.isna().to_numpy(),'unknown_statistical_role_historical_only':axis&~native2021&role.isna().to_numpy(),'known_rural_population_missing':axis&native2021&role.fillna(False).to_numpy(bool)&~np.isfinite(population),'known_positive_rural_population':eligible,'road_snap_tie':snap_ties});source_frame=source_frame.groupby('region',dropna=False).sum().reset_index()
 tie_rows=nodes.loc[snap_ties,['id']].copy();tie_rows['intrinsic_order']=ranks[snap_ties];tie_rows['population_2021']=population[snap_ties];tie_rows['attachment_choice_sensitivity_used_to_clear_ambiguity']=False
 protocol_table=pd.DataFrame([{'protocol_version':PROTOCOL_VERSION,'protocol_json':json.dumps(protocol,ensure_ascii=False,sort_keys=True),'helper_code_sha256':_sha(Path(__file__)),'bounded_source_sha256_json':json.dumps(source_pins,sort_keys=True)}])
 aux={'peer_shared_origins':raw,'supported_peer_pairs':pd.concat(supported_parts,ignore_index=True) if supported_parts else pd.DataFrame(columns=['order','peer_a_id','peer_b_id','n_shared_positive_rural_origins','shared_population2021','mass_ratio_threshold']),
  'system_peer_witnesses':pd.concat(system_witness_parts,ignore_index=True) if system_witness_parts else pd.DataFrame(columns=['origin_id','peer_a_id','peer_b_id','order','time_a','time_b','g_a','g_b','p_a','p_b','mass_ratio','pair_joint_probability','population_2021','level','system_center_id','configuration_scope','peer_a_in_current_union','peer_b_in_current_union','shared_origin_in_current_union']),'common_origin_complexes':complexes,'complex_shared_origins':complexes_long,'order_field_summary':fields,'field_source_coverage':coverage,'regional_field_coverage':regional,
  'regional_source_frame':source_frame,'road_snap_ties':tie_rows,'sensitivity_summary':pd.DataFrame(sensitivity_rows),'excluded_system_keys':pd.DataFrame(excluded,columns=['level','center_id','n_assignment_rows','reason']),'protocol':protocol_table}
 return result,aux

def run_semantic_self_checks():
 """Counterexamples check Word meaning, not implementation-generated expected rows."""
 ids=['A','B','P','x','y','z'];n=pd.DataFrame({'id':ids,'accepted_statistical_rural_role2021':[False,False,False,True,True,True],'_population_axis_row':True,'population_2021':100.,'region':'synthetic'});n['source_record_id_2021']=n.id
 members=n[['id']].copy();centers=pd.DataFrame({'id':['A','B','P'],'intrinsic_empirical_rank':[1,1,2],'own_positive_mass':[10.,9.,100.]});levels={1:pd.Series(['A','B','P','A','B','A']),2:pd.Series(['P']*6)};systems=pd.DataFrame({'level':[1,1,1,2],'center_id':['A','B','P','P']})
 travel=pd.DataFrame([(o,d,float(t)) for o in ['x','y','z'] for d,t in [('A',10),('B',10),('P',20)]],columns=['origin_id','destination_id','travel_minutes']);config={'_configuration_test_only':True,'_configuration_inline_test_source':True};passed=[]
 result,aux=configuration_table(n,members,systems,levels,centers,travel,config);higher=result[result.level.eq(2)].iloc[0]
 assert result[result.level.eq(1)].same_order_configuration.eq('structural_assignment_unit').all();assert higher.same_order_configuration=='monocentric_field_potential' and higher.nested_child_configuration=='polycentric_child_complex_potential';assert set(aux['peer_shared_origins'].origin_id)=={'x','y','z'};assert aux['system_peer_witnesses'].query("configuration_scope=='nested_child'").peer_a_in_current_union.all();assert aux['system_peer_witnesses'].query("configuration_scope=='nested_child'").peer_b_in_current_union.all();passed.append('Nested child polycentricity coexists with parent-order dominance; L1 structural only')
 weak=centers.copy();weak.loc[weak.id.eq('B'),'own_positive_mass']=1.;balanced=travel.copy();balanced.loc[balanced.destination_id.eq('A'),'travel_minutes']=30*np.log(10);balanced.loc[balanced.destination_id.eq('B'),'travel_minutes']=0.
 result,aux=configuration_table(n,members,systems,levels,weak,balanced,config);assert len(aux['peer_shared_origins'])==3 and len(aux['supported_peer_pairs'])==0;assert result[result.level.eq(2)].nested_child_configuration.eq('configuration_unknown').all();passed.append('Equal local gravity cannot substitute for comparable own mass')
 result,aux=configuration_table(n,members,systems,levels,centers,travel,{**config,'model':{'outside_mass':1000.}});assert len(aux['peer_shared_origins'])==3 and len(aux['supported_peer_pairs'])==0;passed.append('Raw close-field witnesses retained when outside option defeats joint strength')
 result,aux=configuration_table(n,members,systems,levels,centers,travel,{});assert result[result.level.eq(2)].same_order_configuration.eq('configuration_unknown').all();passed.append('Nonmissing dominant routes do not establish complete source field')
 zero=n.copy();zero.loc[zero.id.isin(['x','y','z']),'population_2021']=0.;result,aux=configuration_table(zero,members,systems,levels,centers,travel,config);assert result[result.level.eq(2)].same_order_configuration.eq('configuration_unknown').all();assert len(aux['peer_shared_origins'])==0;assert {'origin_id','peer_a_id','peer_b_id'}<=set(aux['peer_shared_origins']);passed.append('Zero eligible residents produces unknown, not monocentricity, with stable empty witness schema')
 # A weak third destination is not near-top, but its uncertain attachment still enters the denominator.
 nn=pd.concat([n,pd.DataFrame([{'id':'Q','accepted_statistical_rural_role2021':False,'_population_axis_row':True,'population_2021':100.,'region':'synthetic'}])],ignore_index=True);cc=pd.concat([centers,pd.DataFrame([{'id':'Q','intrinsic_empirical_rank':2,'own_positive_mass':1.}])],ignore_index=True);mm=nn[['id']].copy();ll={1:pd.Series(['A','B','P','A','B','A','Q']),2:pd.Series(['P','P','P','P','P','P','Q'])};ss=pd.concat([systems,pd.DataFrame({'level':[1,2],'center_id':['Q','Q']})],ignore_index=True);tt=pd.concat([travel,pd.DataFrame([(v,'Q',20.) for v in ['x','y','z']],columns=travel.columns)],ignore_index=True)
 result,aux=configuration_table(nn,mm,ss,ll,cc,tt,{**config,'_configuration_test_snap_tie_ids':['Q']});rr=result[(result.level.eq(2))&result.center_id.eq('P')].iloc[0];assert rr.same_order_configuration=='configuration_unknown' and rr.own_order_road_snap_tie;assert not aux['peer_shared_origins'].peer_a_id.eq('Q').any() and not aux['peer_shared_origins'].peer_b_id.eq('Q').any();passed.append('Weak non-near snap-tied contributor forbids false complete-field mono')
 # Comparable adjacent pairs do not make one globally comparable three-center complex.
 cn=pd.DataFrame({'id':['A','B','C','P','u','v','w'],'accepted_statistical_rural_role2021':[False]*4+[True]*3,'_population_axis_row':True,'population_2021':100.,'region':'synthetic'});cm=cn[['id']].copy();cc=pd.DataFrame({'id':['A','B','C','P'],'intrinsic_empirical_rank':[1,1,1,2],'own_positive_mass':[9.,5.,3.,100.]});cl={1:pd.Series(['A','B','C','P','A','B','C']),2:pd.Series(['P']*7)};cs=pd.DataFrame({'level':[1,1,1,1,2],'center_id':['A','B','C','P','P']});ct=pd.DataFrame([(v,d,t) for v in ['u','v','w'] for d,t in [('A',30*np.log(3)),('B',30*np.log(5/3)),('C',0.),('P',20.)]],columns=travel.columns)
 result,aux=configuration_table(cn,cm,cs,cl,cc,ct,config);primary=aux['common_origin_complexes'][aux['common_origin_complexes'].mass_ratio_threshold.eq(.5)];assert primary.n_peer_centers.max()==2;assert set(primary.peer_ids_json)=={'["A","B"]','["B","C"]'};assert aux['common_origin_complexes'].query('mass_ratio_threshold==.33').n_peer_centers.max()==3;passed.append('Common-origin complexes obey global mass comparability; transitive chain never merged')
 # Six mutually comparable near-equal centers remain literal multicentric evidence even if pairP<.35.
 sixids=[f'S{i}' for i in range(6)];sn=pd.DataFrame({'id':sixids+['P','x','y','z'],'accepted_statistical_rural_role2021':[False]*7+[True]*3,'_population_axis_row':True,'population_2021':100.,'region':'synthetic'});sm=sn[['id']].copy();sc=pd.DataFrame({'id':sixids+['P'],'intrinsic_empirical_rank':[1]*6+[2],'own_positive_mass':[10.]*6+[100.]});sl={1:pd.Series(sixids+['P','S0','S1','S2']),2:pd.Series(['P']*10)};ssix=pd.DataFrame({'level':[1]*7+[2],'center_id':sixids+['P','P']});st=pd.DataFrame([(v,d,10.) for v in ['x','y','z'] for d in sixids+['P']],columns=travel.columns)
 result,aux=configuration_table(sn,sm,ssix,sl,sc,st,config);sr=result[result.level.eq(2)].iloc[0];assert sr.nested_child_configuration=='configuration_unknown' and sr.nested_literal_shared_origins==3 and sr.nested_shared_origins==0;assert aux['common_origin_complexes'].query('mass_ratio_threshold==.5').n_peer_centers.max()==6;assert len(aux['peer_shared_origins'])==45;assert sr.nested_status_reason.startswith('literal_comparable_overlap');passed.append('Six-peer literal multicentric evidence retained despite pair-joint-strength gate; unknown never means absent overlap')
 # Real compact source proof must catch a missing weak destination despite all focal routes being present.
 import tempfile
 with tempfile.TemporaryDirectory(prefix='configuration_source_fixture_') as temp:
  folder=Path(temp);proof_centers=pd.concat([centers,pd.DataFrame([{'id':'Q','intrinsic_empirical_rank':2,'own_positive_mass':1.}])],ignore_index=True);origin=nn[['id']].copy();origin['snap_km']=0.;dest=proof_centers[['id']].copy();dest['snap_km']=0.;dest['routing_budget_minutes']=dest.id.map({'A':180.,'B':180.,'P':360.,'Q':360.});origin.to_parquet(folder/'orig.parquet',index=False);dest.to_parquet(folder/'dest.parquet',index=False)
  source_table=pd.DataFrame({'origin_index':pd.Index(origin.id).get_indexer(tt.origin_id).astype('uint32'),'destination_index':pd.Index(dest.id).get_indexer(tt.destination_id).astype('uint32'),'network_minutes':tt.travel_minutes.to_numpy('float32')});source_table.to_parquet(folder/'part.parquet',index=False);manifest={'format':'compact_parquet_parts_v1','origin_mapping':{'path':'orig.parquet','sha256':_sha(folder/'orig.parquet')},'destination_mapping':{'path':'dest.parquet','sha256':_sha(folder/'dest.parquet')},'parts':[{'path':'part.parquet','sha256':_sha(folder/'part.parquet')}]};(folder/'matrix.json').write_text(json.dumps(manifest));proof={'travel_manifest':str(folder/'matrix.json'),'_configuration_test_only':True}
  result,aux=configuration_table(nn,mm,ss,ll,proof_centers,tt,proof);assert aux['field_source_coverage'].exact_pair_time_membership_match.all();assert result.query("level==2 and center_id=='P'").same_order_configuration.iloc[0]=='monocentric_field_potential'
  result,aux=configuration_table(nn,mm,ss,ll,proof_centers,tt[tt.destination_id.ne('Q')],proof);assert not aux['field_source_coverage'].query('order==2').field_source_complete.iloc[0];assert result.query("level==2 and center_id=='P'").same_order_configuration.iloc[0]=='configuration_unknown';passed.append('Exact compact-source membership catches missing weak competitors; complete-looking loaded focal rows cannot prove mono')
 lower=n.copy();lower.loc[lower.id.eq('A'),'accepted_statistical_rural_role2021']=True;extended=pd.concat([travel,pd.DataFrame([('A','P',240.)],columns=travel.columns)],ignore_index=True);result,aux=configuration_table(lower,members,systems,levels,centers,extended,config);assert aux['order_field_summary'].query("order==2 and origin_id=='A'").routed_same_order_centers.iloc[0]==1;assert len(aux['order_field_summary'].query("order==1 and origin_id=='A'"))==0;passed.append('Lower-order rural core is dependent at higher order with direct240min route; excluded at own order')
 # Historical-only unknown records are outside the native2021 field, not zeros.
 frame=n.copy();frame['source_record_id_2021']=frame.id;frame=pd.concat([frame,pd.DataFrame([{'id':'H','accepted_statistical_rural_role2021':pd.NA,'_population_axis_row':True,'population_2021':np.nan,'region':'synthetic','source_record_id_2021':pd.NA}])],ignore_index=True);fm=frame[['id']].copy();fl={k:pd.concat([v,pd.Series(['P'])],ignore_index=True) for k,v in levels.items()}
 result,_=configuration_table(frame,fm,systems,fl,centers,travel,config);rr=result.query("level==2 and center_id=='P'").iloc[0];assert rr.same_order_configuration=='monocentric_field_potential' and rr.unknown_statistical_role_historical_only_members==1 and rr.unknown_statistical_role_native2021_members==0 and not rr.historical_axis_role_population_complete
 frame.loc[frame.id.eq('H'),'source_record_id_2021']='native_H';result,_=configuration_table(frame,fm,systems,fl,centers,travel,config);rr=result.query("level==2 and center_id=='P'").iloc[0];assert rr.same_order_configuration=='configuration_unknown' and rr.unknown_statistical_role_native2021_members==1;passed.append('Historical-only unknown rows are reported outside native2021 field; actual native2021 role uncertainty blocks mono')
 # Source arrays and hard memberships are immutable inputs.
 assert np.array_equal(members.id,n.id) and levels[1].tolist()==['A','B','P','A','B','A'];passed.append('Hard partitions preserved')
 return {'status':'PASS','semantic_counterexamples':len(passed),'checks':passed,'actual_national_classifications_run':False}

if __name__=='__main__':
 ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--write-protocol',type=Path);g.add_argument('--self-check',action='store_true');a=ap.parse_args()
 if a.self_check:print(json.dumps(run_semantic_self_checks(),ensure_ascii=False,indent=2))
 else:
  assert not a.write_protocol.exists(),'Never overwrite a preregistration';a.write_protocol.parent.mkdir(parents=True,exist_ok=True);a.write_protocol.write_text(json.dumps(configuration_protocol({}),ensure_ascii=False,indent=2)+'\n');print(a.write_protocol)
