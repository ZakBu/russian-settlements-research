#!/usr/bin/env python3
"""Word-concept model with intrinsic standardized mass, empirical ranks and network Huff.

No model-generated catchment population trains the mass. Missing network routes never
become Euclidean minutes. Numerical outputs never imply fulfilled scientific/data gates.
"""
from pathlib import Path
import argparse, hashlib, json, math, time
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import pyarrow.compute as pc
from sklearn.mixture import GaussianMixture

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=ROOT.parents[1]
VALID_ROUTE={'routed','reachable','ok'}

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def dump(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def path(value):
 p=Path(value);return p if p.is_absolute() else REPO/p

def load_nodes(config):
 p=path(config['axis']);watched={p:sha(p)};axis=pd.read_parquet(p)
 if config.get('axis_id','id')!='id':axis=axis.rename(columns={config['axis_id']:'id'})
 required={'id','name','lat','lon'}
 if not required<=set(axis):raise ValueError('Axis missing '+repr(required-set(axis)))
 if axis.id.isna().any() or axis.id.duplicated().any():raise ValueError('Nonunique/null axis IDs')
 if 'axis_kind' not in axis:axis['axis_kind']='ordinary'
 axis['_population_axis_row']=axis.get('is_additive_source_unit',pd.Series(True,index=axis.index)).fillna(False)&~axis.axis_kind.fillna('').str.contains('territory|external_service',case=False)
 axis=axis.reset_index(drop=True)
 ext=config.get('external_centers')
 if ext:
  ep=path(ext);watched[ep]=sha(ep);e=pd.read_parquet(ep)
  if e.id.duplicated().any() or e.id.isna().any():raise ValueError('Duplicate/null external IDs')
  e=e[~e.id.isin(axis.id)].copy();e['axis_kind']='external_service_provider';e['_population_axis_row']=False
  axis=pd.concat([axis,e],ignore_index=True,sort=False)
 for l in config.get('layers',[]):
  p=path(l['path'])
  if not p.exists():
   if l.get('optional'):continue
   raise FileNotFoundError(p)
  watched[p]=sha(p)
  key=l.get('key','id');prefix=l.get('prefix','')
  required_columns={v for c in config.get('components',[]) for v in c.get('columns',[])}|{v for a in config.get('physical_features',{}).values() for v in a}
  thematic=['network_suburban_30_60_minutes','network_peripheral_evidence','commuting_observed','recreation_dacha_evidence','ethnocultural_demographic_evidence','resource_shift_evidence','industrial_decline_evidence','agro_high_productivity_evidence','agro_decline_evidence']
  required_columns|={prefix+t for t in thematic}
  required_columns|=set(config.get('required_input_columns',[]))
  required_columns|={v['source'] for v in config.get('evidence_overrides',[])}
  required_columns|={v[k] for v in config.get('population_overrides',[]) for k in ['value','quality','allowed','root_review_status']}
  required_columns|={v for a in config.get('derived_features',[]) for v in a.get('columns',[])}
  schema=pq.ParquetFile(p).schema_arrow.names
  selected=[key]+[c for c in schema if c!=key and (prefix+c in required_columns or any(c.startswith(t) for t in l.get('retain_prefixes',[])) or (l.get('retain_evidence_suffix',False) and c.endswith('_evidence')))]
  x=pd.read_parquet(p,columns=selected)
  if x[key].isna().any() or x[key].duplicated().any():raise ValueError('Layer key conflict '+str(p))
  prefix=l.get('prefix','');x=x.rename(columns={c:prefix+c for c in x if c!=key}).rename(columns={key:'id'})
  if l.get('normalize_route_aliases'):
   x['road_source_id_before_alias']=x.id;x['id']=x.id.replace(config.get('route_id_aliases',{}))
   if x.id.duplicated().any():raise ValueError('Route aliases collapse distinct source rows')
  overlap=(set(x)-{'id'})&set(axis)
  if overlap:raise ValueError('Layer shadows axis columns '+repr(overlap))
  axis=axis.merge(x,on='id',how='left',validate='one_to_one',sort=False)
 for override in config.get('population_overrides',[]):
  year=int(override['year']);value=pd.to_numeric(axis[override['value']],errors='coerce');raw_allowed=axis[override['allowed']]
  if not raw_allowed.dropna().isin([True,False]).all():raise ValueError('Population override permission is not boolean')
  allowed=raw_allowed.astype('boolean').fillna(False)
  accepted=axis[override['root_review_status']].eq('accepted_primary_same2010_unique_name_type_region')
  if (allowed&(~accepted|value.isna()|value.lt(0))).any():raise ValueError('Population override lacks accepted root/source review')
  pop=f'population_{year}';quality=f'population_value_quality_{year}'
  if 'original_'+pop not in axis:axis['original_'+pop]=axis[pop]
  if 'original_'+quality not in axis:axis['original_'+quality]=axis[quality] if quality in axis else pd.NA
  axis.loc[allowed,pop]=value[allowed];axis.loc[allowed,quality]=axis.loc[allowed,override['quality']]
  marker=f'root_reviewed_primary_override_applied_{year}'
  previous=axis[marker] if marker in axis else pd.Series(False,index=axis.index)
  axis[marker]=previous|allowed
 if config.get('external_context_reference'):
  ep=path(config['external_context_reference']);watched[ep]=sha(ep);reference=pd.read_csv(ep).set_index('id')
  reference_year=int(config.get('mass_reference_year',2021))
  axis['own_population_for_mass']=axis[f'population_{reference_year}']
  axis['context_territorial_population_for_mass_only']=np.nan
  axis['context_territorial_registered_economy_for_mass_only']=np.nan
  own_econ=f'legacy_econ_native_{reference_year}_legal_entities'
  axis['own_registered_economy_for_mass']=axis[own_econ] if own_econ in axis else np.nan
  external=axis.axis_kind.eq('external_service_provider')
  for i in axis.index[external]:
   key=axis.loc[i,'source_id'] if 'source_id' in axis else None
   if key not in reference.index:continue
   axis.loc[i,'context_territorial_population_for_mass_only']=reference.loc[key,f'population_{reference_year}']
   axis.loc[i,'own_population_for_mass']=reference.loc[key,f'population_{reference_year}']
   value=reference.loc[key,'econ_legacy_federal_2021_federal_coded_baseline_legal_entities']
   axis.loc[i,'context_territorial_registered_economy_for_mass_only']=value
   axis.loc[i,'own_registered_economy_for_mass']=value
 if config.get('independent_district_seats'):
  ap=path(config['independent_district_seats']);watched[ap]=sha(ap);admin=pd.read_parquet(ap,columns=['center_id','admin_level'])
  seat_ids=set(admin.loc[admin.admin_level.astype(str).eq('6'),'center_id'].dropna())
  axis['source_osm2026_admin_level6_seat_evidence']=axis.id.isin(seat_ids)
 for evidence in config.get('evidence_overrides',[]):
  source=axis[evidence['source']]
  if not source.dropna().isin([True,False,0,1]).all():raise ValueError('Nonboolean evidence override')
  target=evidence['target'];previous=axis[target] if target in axis else pd.Series(pd.NA,index=axis.index,dtype='boolean')
  axis[target]=source.astype('boolean').combine_first(previous.astype('boolean'))
 for definition in config.get('derived_features',[]):
  columns=[c for c in definition['columns'] if c in axis]
  if not columns:axis[definition['name']]=np.nan;continue
  if definition['operation']!='sum_disjoint':raise ValueError('Undeclared derived operation')
  axis[definition['name']]=axis[columns].apply(pd.to_numeric,errors='coerce').sum(axis=1,min_count=1)
 for y in [2002,2010,2021]:
  if f'population_{y}' not in axis:axis[f'population_{y}']=np.nan
  q=pd.to_numeric(axis[f'population_{y}'],errors='coerce')
  if (q.dropna()<0).any():raise ValueError('Negative population')
  axis[f'population_{y}']=q
 if 'type' not in axis:axis['type']=None
 if 'region' not in axis:axis['region']=None
 axis['routable_coordinate']=np.isfinite(axis[['lat','lon']].to_numpy(float)).all(axis=1)&axis.lat.between(-90,90)&axis.lon.between(-180,180)
 return axis,watched

def choose_physical(nodes,columns):
 found=[c for c in columns if c in nodes]
 if not found:return pd.Series(np.nan,index=nodes.index),[]
 vals=nodes[found].apply(pd.to_numeric,errors='coerce')
 if (vals<0).any().any():raise ValueError('Negative physical count')
 # Only positive catalog witnesses enter service-strength estimates. Zero accepted
 # records in an incomplete catalog does not establish absence of a physical service.
 vals=vals.where(vals>0)
 return vals.max(axis=1,skipna=True),found

def build_mass(nodes,config):
 mass=pd.DataFrame({'id':nodes.id});components=[];physical={};bindings={}
 for name,options in config['physical_features'].items():
  val,b=choose_physical(nodes,options);physical[name]=val;bindings[name]=b
  mass['physical_'+name+'_positive_witness']=val.gt(0)
  mass['physical_'+name+'_count_proxy']=val
 for c in config['components']:
  if c.get('physical'):
   val=physical[c['physical']];sources=bindings[c['physical']]
  else:
   found=[x for x in c.get('columns',[]) if x in nodes]
   val=nodes[found].apply(pd.to_numeric,errors='coerce').bfill(axis=1).iloc[:,0] if found else pd.Series(np.nan,index=nodes.index)
   sources=found
  transformed=np.log1p(val.where(val>=0)) if c.get('transform')=='log1p' else val
  observed=transformed.notna();mu=float(transformed.mean()) if observed.any() else 0.;sd=float(transformed.std(ddof=0)) if observed.any() else 0.
  # A constant feature supplies no cross-sectional ranking information.
  z=(transformed-mu)/sd if sd>1e-12 else pd.Series(np.nan,index=nodes.index)
  mass[c['name']+'_raw']=val;mass[c['name']+'_z']=z
  components.append({**c,'bound_columns':sources,'n_observed':int(observed.sum()),'n_used_in_z':int(z.notna().sum()),'mean_transformed':mu,'sd_transformed':sd,'computed_from_own_source_features':True})
 blocks={}
 for block in sorted({c['block'] for c in components}):
  cols=[c['name']+'_z' for c in components if c['block']==block]
  blocks[block]=mass[cols].mean(axis=1,skipna=True)
  mass['block_'+block+'_z']=blocks[block]
 b=pd.DataFrame(blocks);mass['n_observed_mass_blocks']=b.notna().sum(axis=1)
 mass['own_mean_standardized_index']=b.mean(axis=1,skipna=True)
 mass['own_positive_mass']=np.exp(np.clip(mass.own_mean_standardized_index,-20,20))
 mass.loc[mass.n_observed_mass_blocks==0,'own_positive_mass']=np.nan
 mass['mass_uses_modeled_catchment']=False
 mass['mass_mixes_observation_dates']=any(c.get('year',0)>config['mass_reference_year'] and c['n_used_in_z']>0 for c in components)
 urban=nodes.type.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 core_function=mass[['physical_'+f+'_positive_witness' for f in ['education','healthcare','hospital','finance','administration']]].any(axis=1)
 trade=mass.physical_trade_positive_witness
 econ=mass.get('registered_organization_economy_raw',pd.Series(np.nan,index=mass.index)).gt(0)
 mass['nonretail_observed_function_count']=mass[['physical_'+f+'_positive_witness' for f in ['education','healthcare','administration','finance']]].sum(axis=1)
 anchor=mass[['physical_'+f+'_positive_witness' for f in ['education','healthcare','administration']]].any(axis=1)
 districtseat=nodes.get('geonames_district_seat_evidence',pd.Series(False,index=nodes.index)).fillna(False)|nodes.get('source_osm2026_admin_level6_seat_evidence',pd.Series(False,index=nodes.index)).fillna(False)
 diverse=mass.nonretail_observed_function_count.ge(2)&anchor
 hospital=mass.physical_hospital_positive_witness
 external=nodes.axis_kind.eq('external_service_provider')
 if config.get('center_eligibility','broad_catalogue_sensitivity')=='restricted_multifunctional_or_independent_seat':
  eligible=urban|districtseat|diverse|hospital|external
  basis=np.select([external,urban,districtseat,hospital,diverse],['documented_external_context_anchor','urban_status_potential_center','independent_district_seat','hospital_documented_source_class','two_nonretail_functions_with_core_anchor'],default='not_integral_center_function_provider_only')
 else:
  eligible=urban|core_function|trade|external
  basis=np.select([external,core_function,urban,trade],['documented_external_context_anchor','own_physical_service','urban_status_potential_center','trade_only_potential_provider'],default='not_candidate')
 mass['candidate_center']=nodes.routable_coordinate&mass.own_positive_mass.notna()&eligible&~nodes.axis_kind.eq('federal_territory_source_unit')
 mass['candidate_basis']=basis
 mass['center_eligibility_scenario']=config.get('center_eligibility','broad_catalogue_sensitivity')
 mass['candidate_is_documented_external_center']=False
 return mass,components

def empirical_ranks(mass,config):
 cand=mass[mass.candidate_center].copy();x=np.log(cand.own_positive_mass.to_numpy(float))[:,None]
 if len(cand)<2:raise ValueError('Too few candidate centers')
 rng=np.random.default_rng(config['model']['random_seed']);sample=x if len(x)<=12000 else x[np.sort(rng.choice(len(x),12000,replace=False))]
 selection=[];models={}
 maxk=min(config['model']['maximum_rank_components'],len(cand)//config['model']['minimum_rank_cluster_size'])
 for k in range(1,max(1,maxk)+1):
  g=GaussianMixture(n_components=k,covariance_type='full',reg_covar=1e-4,random_state=config['model']['random_seed'],n_init=3,max_iter=250).fit(sample)
  label=g.predict(x);sizes=np.bincount(label,minlength=k)
  eligible=bool(sizes.min()>=config['model']['minimum_rank_cluster_size'])
  selection.append({'components':k,'bic_on_fixed_training_sample':float(g.bic(sample)),'aic_on_fixed_training_sample':float(g.aic(sample)),'cluster_sizes':sizes.tolist(),'minimum_cluster_size_pass':eligible,'converged':bool(g.converged_)})
  if eligible and g.converged_:models[k]=g
 if not models:raise ValueError('No admissible empirical clustering')
 best=min(models,key=lambda k:next(s['bic_on_fixed_training_sample'] for s in selection if s['components']==k));g=models[best]
 order=np.argsort(g.means_[:,0]);rankmap={int(label):int(rank+1) for rank,label in enumerate(order)}
 cand['intrinsic_empirical_rank']=[rankmap[int(t)] for t in g.predict(x)]
 cand['rank_max_posterior']=g.predict_proba(x).max(axis=1)
 means=[float(g.means_[label,0]) for label in order]
 cand['rank_method']='GMM_BIC_intrinsic_log_mass_not_quantiles_or_validated_service_order'
 return cand,{'selection':selection,'chosen_components':best,'means_log_mass_ordered':means,'training_sample_rows':len(sample),'full_candidate_rows':len(x),'catchment_size_used_for_ranks':False,'rank_hierarchy_claim':'empirical_statistical_orders_of_intrinsic_mass_not_proven_functional_service_levels'}

def verify_routing_scope(config,nodes,centers,mass):
 base=travel_source(config).parent
 rp=base/'routing_receipt.json';dp=base/'route_destination_index.parquet';xp=base/'route_destination_rejections.parquet';op=base/'route_origin_index.parquet'
 for p in [rp,dp,xp,op]:
  if not p.exists():raise FileNotFoundError('Routing completeness evidence absent: '+str(p))
 receipt=json.loads(rp.read_text())
 if receipt.get('status')!='COMPUTED':raise ValueError('Routing receipt is not completed')
 aliases=config.get('route_id_aliases',{});origin_ids=set(pd.read_parquet(op,columns=['id']).id.replace(aliases));snap_path=base/'settlement_road_snap.parquet'
 expected_origins=set(nodes.loc[nodes.routable_coordinate,'id'])
 if snap_path.exists():
  snap=pd.read_parquet(snap_path,columns=['id','snap_km']);snap['id']=snap.id.replace(aliases);expected_origins&=set(snap.loc[snap.snap_km.le(receipt.get('origin_snap_max_km',10)),'id'])
 missing_origins=expected_origins-origin_ids
 if missing_origins:raise ValueError('Accepted origins absent from exact routing source: '+repr(sorted(missing_origins)[:20]))
 destination_rows=pd.read_parquet(dp,columns=['id','routing_budget_minutes']);destination_rows['id']=destination_rows.id.replace(aliases)
 if destination_rows.id.duplicated().any():raise ValueError('Duplicate canonical routing destinations')
 destinations=destination_rows.set_index('id').routing_budget_minutes
 rejected=set(pd.read_parquet(xp,columns=['id']).id.replace(aliases))
 eligible=set(centers.id)
 for function in ['education','healthcare','hospital','trade','finance','administration']:
  col='physical_'+function+'_count_proxy'
  if col in mass:eligible.update(mass.loc[mass[col].gt(0),'id'])
 eligible&=set(nodes.loc[nodes.routable_coordinate,'id'])
 missing=eligible-set(destinations.index)-rejected
 if missing:raise ValueError('Model destinations neither routed nor explicitly rejected: '+repr(sorted(missing)[:20]))
 needed={u:config['model']['max_travel_minutes'] for u in eligible}
 for u in centers.loc[centers.intrinsic_empirical_rank.ge(2),'id']:needed[u]=config['model'].get('hierarchy_max_travel_minutes',360.)
 short=[u for u,budget in needed.items() if u in destinations.index and destinations[u]<budget]
 if short:raise ValueError('Incomplete matrix time budget for this scenario: '+repr(short[:20]))
 return {p:sha(p) for p in [rp,dp,xp,op]+([snap_path] if snap_path.exists() else [])},receipt,{'required_accepted_origin_count':len(expected_origins),'accepted_origin_mapping_count':len(origin_ids),'required_destination_count':len(eligible),'required_explicitly_rejected_count':len(eligible&rejected),'required_budget_shortfall_count':len(short)}

def travel_source(config):return path(config.get('travel_manifest',config['travel_edges']))

def load_compact_travel(config,nodes,centers,mass):
 p=travel_source(config);manifest=json.loads(p.read_text())
 if manifest.get('format')!='compact_parquet_parts_v1':raise ValueError('Unknown compact routing format')
 if sum(int(x['rows']) for x in manifest['parts'])!=int(manifest['rows']):raise ValueError('Compact manifest total rowcount mismatch')
 watched={};maps=[]
 for name in ['origin_mapping','destination_mapping']:
  info=manifest[name];mp=p.parent/info['path'];digest=sha(mp)
  if digest!=info['sha256']:raise ValueError('Compact mapping bytes differ from manifest: '+str(mp))
  watched[mp]=digest;mapping=pd.read_parquet(mp);mapping['id']=mapping.id.replace(config.get('route_id_aliases',{}))
  if 'canonical_id' in mapping and not mapping.id.equals(mapping.canonical_id):raise ValueError('Declared route aliases differ from source canonical mapping')
  if mapping.id.duplicated().any():raise ValueError('Duplicate canonical compact mapping IDs')
  column=info['index_column']
  if not np.array_equal(mapping[column].to_numpy(),np.arange(len(mapping))):raise ValueError('Compact mapping index/order invalid')
  maps.append(mapping)
 origins,destinations=maps;ids=pd.Index(nodes.id);origin_codes=ids.get_indexer(origins.id);destination_codes=ids.get_indexer(destinations.id)
 if (origin_codes<0).any() or (destination_codes<0).any():raise ValueError('Compact mappings outside node axis')
 origin_filter=np.ones(len(origins),dtype=bool) if not config.get('origin_id_filter') else origins.id.isin(config['origin_id_filter']).to_numpy()
 allowed=np.ones(len(destinations),dtype=bool);center_orig=np.zeros(len(origins),dtype=bool);center_dest=np.zeros(len(destinations),dtype=bool);higher_dest=np.zeros(len(destinations),dtype=bool)
 if centers is not None and mass is not None:
  eligible=set(centers.id)
  for function in ['education','healthcare','hospital','trade','finance','administration']:
   col='physical_'+function+'_count_proxy'
   if col in mass:eligible.update(mass.loc[mass[col].gt(0),'id'])
  allowed=destinations.id.isin(eligible).to_numpy();center_orig=origins.id.isin(centers.id).to_numpy();center_dest=destinations.id.isin(centers.id).to_numpy()
  urban=set(nodes.loc[nodes.type.fillna('').eq('город')|nodes.axis_kind.eq('external_service_provider'),'id'])
  high=set(centers.loc[centers.intrinsic_empirical_rank.ge(max(2,int(centers.intrinsic_empirical_rank.max())-1)),'id'])&urban
  higher_dest=destinations.id.isin(high).to_numpy()
 oc=origins.snap_km.to_numpy(float)*4.;dc=destinations.snap_km.to_numpy(float)*4.
 os=[];ds=[];ts=[];low=config['model']['max_travel_minutes'];upper=config['model'].get('hierarchy_max_travel_minutes',360.)
 for part in manifest['parts']:
  pp=p.parent/part['path'];digest=sha(pp)
  if digest!=part['sha256']:raise ValueError('Compact part bytes differ from manifest: '+str(pp))
  watched[pp]=digest;pf=pq.ParquetFile(pp)
  if pf.metadata.num_rows!=part['rows']:raise ValueError('Compact part rowcount mismatch')
  for batch in pf.iter_batches(batch_size=500000,columns=['origin_index','destination_index','network_minutes']):
   oi=batch.column('origin_index').to_numpy();di=batch.column('destination_index').to_numpy();network=batch.column('network_minutes').to_numpy()
   if len(oi) and (oi.max()>=len(origins) or di.max()>=len(destinations)):raise ValueError('Compact routing index outside mapping')
   keep=allowed[di]&origin_filter[oi];oi=oi[keep];di=di[keep];network=network[keep]
   connector=(oc[oi]+dc[di]).astype('float32');minutes=(network+connector).astype('float32');same=origin_codes[oi]==destination_codes[di];minutes[same]=0.
   longpair=(center_orig[oi]&center_dest[di])|higher_dest[di]
   usable=np.isfinite(minutes)&(minutes>=0)&((minutes<=low)|(longpair&(minutes<=upper)))
   os.append(origin_codes[oi[usable]].astype('int32'));ds.append(destination_codes[di[usable]].astype('int32'));ts.append(minutes[usable])
 if not os:raise ValueError('No compact route rows')
 d=pd.DataFrame({'origin_id':pd.Categorical.from_codes(np.concatenate(os),categories=ids),'destination_id':pd.Categorical.from_codes(np.concatenate(ds),categories=ids),'travel_minutes':np.concatenate(ts)})
 if d.duplicated(['origin_id','destination_id']).any():raise ValueError('Duplicate compact routing pairs')
 d['route_status']=pd.Categorical.from_codes(np.zeros(len(d),dtype='int8'),categories=['routed']);d.attrs['additional_source_sha256']=watched
 return d,p

def load_travel(config,nodes,centers=None,mass=None):
 if config.get('travel_manifest'):return load_compact_travel(config,nodes,centers,mass)
 p=path(config['travel_edges'])
 if not p.exists():raise FileNotFoundError('Required actual network travel edges absent: '+str(p))
 required=['origin_id','destination_id','travel_minutes','route_status'];table=pq.ParquetFile(p)
 if not set(required)<=set(table.schema_arrow.names):raise ValueError('Travel schema missing '+repr(set(required)-set(table.schema_arrow.names)))
 # Codes avoid materializing repeated long IDs for tens of millions of routed pairs.
 ids=pd.Index(nodes.id);origins=[];destinations=[];minutes=[]
 allowed=None;center_ids=None;high_ids=None
 if centers is not None and mass is not None:
  eligible=set(centers.id)
  for function in ['education','healthcare','hospital','trade','finance','administration']:
   col='physical_'+function+'_count_proxy'
   if col in mass:eligible.update(mass.loc[mass[col].gt(0),'id'])
  allowed=pa.array(sorted(eligible));center_ids=pa.array(centers.id)
  urban=set(nodes.loc[nodes.type.fillna('').eq('город')|nodes.axis_kind.eq('external_service_provider'),'id'])
  high_ids=pa.array(sorted(set(centers.loc[centers.intrinsic_empirical_rank.ge(max(2,int(centers.intrinsic_empirical_rank.max())-1)),'id'])&urban),type=pa.string())
 for batch in table.iter_batches(batch_size=500000,columns=required):
  if config.get('origin_id_filter'):batch=batch.filter(pc.is_in(batch.column('origin_id'),value_set=pa.array(config['origin_id_filter'])))
  if allowed is not None:
   low=pc.less_equal(batch.column('travel_minutes'),config['model']['max_travel_minutes'])
   long_pair=pc.or_(pc.and_(pc.is_in(batch.column('origin_id'),value_set=center_ids),pc.is_in(batch.column('destination_id'),value_set=center_ids)),pc.is_in(batch.column('destination_id'),value_set=high_ids))
   time_usable=pc.or_(low,pc.and_(long_pair,pc.less_equal(batch.column('travel_minutes'),config['model'].get('hierarchy_max_travel_minutes',360.))))
   batch=batch.filter(pc.and_(pc.is_in(batch.column('destination_id'),value_set=allowed),time_usable))
  d=batch.to_pandas();valid=d.route_status.isin(VALID_ROUTE)&np.isfinite(d.travel_minutes)&d.travel_minutes.ge(0)
  d=d.loc[valid];o=ids.get_indexer(d.origin_id.replace(config.get('route_id_aliases',{})));t=ids.get_indexer(d.destination_id.replace(config.get('route_id_aliases',{})))
  if (o<0).any() or (t<0).any():raise ValueError('Travel IDs do not match prepared axis')
  origins.append(o.astype('int32'));destinations.append(t.astype('int32'));minutes.append(d.travel_minutes.to_numpy(dtype='float32'))
 if not origins:raise ValueError('No usable routed network pairs')
 o=np.concatenate(origins);t=np.concatenate(destinations);v=np.concatenate(minutes)
 d=pd.DataFrame({'origin_id':pd.Categorical.from_codes(o,categories=ids),'destination_id':pd.Categorical.from_codes(t,categories=ids),'travel_minutes':v})
 if d.duplicated(['origin_id','destination_id']).any():raise ValueError('Travel graph versions/duplicate pairs unresolved')
 d['route_status']=pd.Categorical.from_codes(np.zeros(len(d),dtype='int8'),categories=['routed'])
 return d,p

def huff_assign(nodes,centers,travel,config,preserve_cores=True,core_centers=None):
 pars=config['model'];mass=centers.set_index('id').own_positive_mass
 edges=travel[travel.destination_id.isin(mass.index)&travel.travel_minutes.le(pars['max_travel_minutes'])].copy()
 edges['destination_mass']=edges.destination_id.map(mass)
 edges['gravity']=edges.destination_mass*np.exp(-edges.travel_minutes/pars['time_decay_minutes'])
 edges=edges[edges.gravity.gt(0)].sort_values(['origin_id','gravity','destination_id'],ascending=[True,False,True])
 totals=edges.groupby('origin_id',observed=True).gravity.sum()
 edges['huff_probability']=edges.gravity/(edges.origin_id.map(totals)+pars['outside_mass'])
 first=edges.drop_duplicates('origin_id');second=edges.groupby('origin_id',observed=True).nth(1).reset_index() if len(edges) else pd.DataFrame()
 out=nodes[['id','name','type','region','lat','lon','_population_axis_row','axis_kind','routable_coordinate']].copy().set_index('id')
 out['raw_model_center_id']=first.set_index('origin_id').destination_id
 out['raw_top_probability']=first.set_index('origin_id').huff_probability
 out['raw_top_gravity']=first.set_index('origin_id').gravity
 out['raw_top_travel_minutes']=first.set_index('origin_id').travel_minutes
 out['outside_probability']=pars['outside_mass']/(totals+pars['outside_mass'])
 if len(second):
  sec=second.set_index('origin_id');out['second_center_id']=sec.destination_id;out['second_probability']=sec.huff_probability;out['second_gravity']=sec.gravity
 else:out['second_center_id']=None;out['second_probability']=np.nan;out['second_gravity']=np.nan
 out['second_to_first_gravity_ratio']=out.second_gravity/out.raw_top_gravity
 out['ambiguous_competing_centers']=out.second_to_first_gravity_ratio.ge(pars['competition_ratio'])
 out['assigned_center_id']=out.raw_model_center_id.where(out.raw_top_probability.ge(pars['minimum_choice_probability']))
 out['assigned_travel_minutes']=out.raw_top_travel_minutes.where(out.assigned_center_id.notna())
 out['assignment_status']=np.where(out.raw_model_center_id.isna(),'no_routed_candidate',np.where(out.assigned_center_id.isna(),'outside_or_diffuse_probability','modeled_network_assignment'))
 out.loc[~out.routable_coordinate,'assignment_status']='unlocated_source_entity'
 out['protected_core']=False
 if preserve_cores:
  protected=centers if core_centers is None else core_centers
  present=out.index.intersection(protected.id);out.loc[present,'assigned_center_id']=present;out.loc[present,'assignment_status']='intrinsic_candidate_core_not_validated_external_center';out.loc[present,'protected_core']=True;out.loc[present,'assigned_travel_minutes']=0.
 out['network_connection_evidence_status']=np.where(out.raw_model_center_id.notna(),'has_computed_route_to_candidate',np.where(out.routable_coordinate,'coordinates_known_network_connection_unconfirmed','coordinates_unavailable'))
 out['distance_is_network_time']=True;out['observed_trip_claim']=False
 return out.reset_index(),edges

def build_hierarchy(members,centers,travel,config):
 ranks=centers.set_index('id').intrinsic_empirical_rank.to_dict();masses=centers.set_index('id').own_positive_mass.to_dict()
 active=set(members.assigned_center_id.dropna());current=members.assigned_center_id.copy();levels={1:current.copy()};edges=[]
 routes=travel[travel.origin_id.isin(centers.id)&travel.destination_id.isin(centers.id)].copy()
 # No invented radius expansion: all steps use explicit graph travel budget.
 for target_rank in range(2,int(centers.intrinsic_empirical_rank.max())+1):
  nextmap={u:u for u in active}
  eligible={u for u in active if ranks[u]>=target_rank}
  r=routes[routes.origin_id.isin(active)&routes.destination_id.isin(eligible)&routes.travel_minutes.le(config['model'].get('hierarchy_max_travel_minutes',config['model']['max_travel_minutes']))].copy()
  r=r[r.origin_id.map(ranks)<r.destination_id.map(ranks)]
  r['gravity']=r.destination_id.map(masses)*np.exp(-r.travel_minutes/config['model']['time_decay_minutes'])
  totals=r.groupby('origin_id',observed=True).gravity.sum()
  r['conditional_parent_probability']=r.gravity/(r.origin_id.map(totals)+config['model']['outside_mass'])
  r=r[r.conditional_parent_probability.ge(config['model']['minimum_choice_probability'])]
  r=r.sort_values(['origin_id','gravity','destination_id'],ascending=[True,False,True]).drop_duplicates('origin_id')
  winners=r.set_index('origin_id')
  for u in sorted(active):
   if ranks[u]<target_rank and u in winners.index:
    w=winners.loc[u];nextmap[u]=w.destination_id
   edges.append({'level':target_rank,'child_id':u,'parent_id':nextmap[u],'child_rank':int(ranks[u]),'parent_rank':int(ranks[nextmap[u]]),'self_retained':u==nextmap[u],'network_time_minutes':0. if u==nextmap[u] else float(winners.loc[u].travel_minutes),'conditional_parent_probability':None if u==nextmap[u] else float(winners.loc[u].conditional_parent_probability),'pending_dependent_singleton_attachment':False})
  current=current.map(nextmap)
  # A dependent settlement without a lowest-order unit remains NA at L1.
  # At a higher level it can join directly as a pending singleton, without
  # inventing a rural service center or splitting any already formed system.
  pending_ids=set(members.loc[current.isna()&members.routable_coordinate,'id'])
  if pending_ids and eligible:
   q=travel[travel.origin_id.isin(pending_ids)&travel.destination_id.isin(eligible)&travel.travel_minutes.le(config['model'].get('pending_singleton_max_travel_minutes',config['model']['max_travel_minutes']))].copy()
   q['gravity']=q.destination_id.map(masses)*np.exp(-q.travel_minutes/config['model']['time_decay_minutes'])
   qt=q.groupby('origin_id',observed=True).gravity.sum();q['conditional_parent_probability']=q.gravity/(q.origin_id.map(qt)+config['model']['outside_mass'])
   q=q[q.conditional_parent_probability.ge(config['model']['minimum_choice_probability'])].sort_values(['origin_id','gravity','destination_id'],ascending=[True,False,True]).drop_duplicates('origin_id')
   picks=q.set_index('origin_id').destination_id
   additions=members.id.map(picks);take=current.isna()&additions.notna();current.loc[take]=additions.loc[take]
   for _,row in q.iterrows():edges.append({'level':target_rank,'child_id':row.origin_id,'parent_id':row.destination_id,'child_rank':0,'parent_rank':int(ranks[row.destination_id]),'self_retained':False,'network_time_minutes':float(row.travel_minutes),'conditional_parent_probability':float(row.conditional_parent_probability),'pending_dependent_singleton_attachment':True,'service_eligibility_budget_minutes':config['model'].get('pending_singleton_max_travel_minutes',config['model']['max_travel_minutes'])})
  levels[target_rank]=current.copy();active=set(current.dropna())
 return levels,pd.DataFrame(edges)

def network_context(nodes,centers,travel):
 ranks=centers.set_index('id').intrinsic_empirical_rank
 urban=set(nodes.loc[nodes.type.fillna('').eq('город')|nodes.axis_kind.eq('external_service_provider'),'id'])
 high=set(centers.loc[centers.intrinsic_empirical_rank.ge(max(2,int(ranks.max())-1)),'id'])&urban
 z=travel[travel.destination_id.isin(high)&travel.origin_id.ne(travel.destination_id)].copy()
 z=z[z.destination_id.map(ranks)>z.origin_id.map(ranks).fillna(0)]
 closest=z.sort_values(['origin_id','travel_minutes','destination_id']).drop_duplicates('origin_id').set_index('origin_id')
 result=pd.DataFrame({'id':nodes.id}).set_index('id')
 result['nearest_higher_urban_center_id']=closest.destination_id
 result['nearest_higher_urban_network_minutes']=closest.travel_minutes
 value=result.nearest_higher_urban_network_minutes
 result['network_suburban_30_60_minutes']=pd.Series(pd.NA,index=result.index,dtype='boolean')
 result.loc[value.notna(),'network_suburban_30_60_minutes']=value[value.notna()].between(30,60)
 result['network_peripheral_evidence']=pd.Series(pd.NA,index=result.index,dtype='boolean')
 result.loc[value.notna(),'network_peripheral_evidence']=value[value.notna()].gt(90)
 result['model_accessibility_belt']=np.select([value.le(30),value.le(60),value.le(90),value.gt(90)],['within30minutes','30to60minutes','60to90minutes','beyond90minutes'],default='no_computed_reachable_higher_urban')
 result['accessibility_not_observed_commuting']=True
 return result.reset_index()


def function_specific_assignments(nodes,mass,centers,travel,config):
 result=[];choices=[]
 for function in ['education','healthcare','hospital','trade','finance','administration']:
  column='physical_'+function+'_count_proxy'
  if column not in mass:continue
  count=mass[column];positive=count.gt(0)
  if not positive.any():continue
  providers=mass.loc[positive,['id']].copy();providers['own_positive_mass']=np.log1p(count[positive].to_numpy())
  # Function providers do not require registered legal entities to exist.
  picked,edge=huff_assign(nodes,providers,travel,config,preserve_cores=True)
  picked['function_group']=function;picked['function_count_not_capacity']=True
  result.append(picked[['id','function_group','assigned_center_id','assigned_travel_minutes','raw_model_center_id','raw_top_probability','second_center_id','second_to_first_gravity_ratio','assignment_status','protected_core','function_count_not_capacity']])
 return pd.concat(result,ignore_index=True) if result else pd.DataFrame()


def functional_agreement(members,function_assignments):
 """Retain independent sector leaders instead of hiding them in one integral parent."""
 if function_assignments.empty:return pd.DataFrame(columns=['id','n_sector_leaders'])
 z=function_assignments.merge(members[['id','assigned_center_id']].rename(columns={'assigned_center_id':'integrated_center_id'}),on='id',validate='many_to_one')
 z['sector_matches_integrated']=z.assigned_center_id.eq(z.integrated_center_id)&z.assigned_center_id.notna()
 rows=[]
 for uid,g in z.groupby('id',sort=False):
  leaders=g.assigned_center_id.dropna();n=int(leaders.nunique());observed=len(leaders)
  rows.append({'id':uid,'n_assigned_sector_models':observed,'n_sector_leaders':n,'sector_model_integrated_agreement_fraction':float(g.loc[g.assigned_center_id.notna(),'sector_matches_integrated'].mean()) if observed else np.nan,'different_sector_leaders_potential':n>=2,'sector_leaders_json':json.dumps(dict(zip(g.function_group,g.assigned_center_id.astype(object).where(g.assigned_center_id.notna(),None))),ensure_ascii=False),'actual_multicenter_flows_observed':False})
 return pd.DataFrame(rows)

def configuration_table(nodes,members,systems,levels,centers):
 source=members.set_index('id');ranks=centers.set_index('id').intrinsic_empirical_rank.to_dict();rows=[]
 for level,assignment in levels.items():
  x=pd.DataFrame({'id':members.id,'parent_id':assignment.values,'low_center':levels[1].values,'ambiguous':members.ambiguous_competing_centers.values})
  for parent,g in x[x.parent_id.notna()].groupby('parent_id',observed=True):
   low=sorted(set(g.low_center.dropna()));rr=[ranks.get(v,0) for v in low];highest=max(rr) if rr else 0;peer=sum(v==highest for v in rr)
   ambiguity=float(g.ambiguous.mean());poly=bool(peer>=2 and ambiguity>=.1)
   rows.append({'level':level,'center_id':parent,'low_level_centers_preserved':len(low),'highest_intrinsic_rank_in_union':highest,'n_peer_centers_highest_rank':peer,'ambiguous_origin_fraction':ambiguity,'modeled_configuration':'polycentric_potential_candidate' if poly else ('monocentric_potential_candidate' if peer==1 else 'configuration_uncertain'),'actual_multicenter_service_flows_observed':False})
 return pd.DataFrame(rows)


def annual_rate(a,b,years):
 a=np.asarray(a,float);b=np.asarray(b,float);out=np.full(np.broadcast_shapes(a.shape,b.shape),np.nan)
 valid=np.isfinite(a)&np.isfinite(b)&(a>0)&(b>=0)
 out[valid]=np.power(b[valid]/a[valid],1./years)-1.
 return out

def aggregate(nodes,members,levels,config):
 d=nodes.set_index('id');rows=[];balances=[];rural=~d.type.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 for level,assignment in levels.items():
  temp=nodes[['id','_population_axis_row','population_2002','population_2010','population_2021']].copy();temp['center_id']=assignment.values
  ordinary=temp[temp._population_axis_row]
  for center,g in ordinary[ordinary.center_id.notna()].groupby('center_id',sort=True,observed=True):
   own=d.loc[center];row={'level':level,'center_id':center,'name':own['name'],'region':own['region'],'lat':own.lat,'lon':own.lon,'axis_kind':own.axis_kind,'n_population_axis_settlements':len(g),'n_external_settlements':int((g.id!=center).sum())}
   ext=g.id.ne(center)&g.id.map(rural)
   row['n_rural_external_settlements']=int(ext.sum())
   for year in [2002,2010,2021]:
    column=f'population_{year}';p=g[column];known_own=bool(own['_population_axis_row']) and pd.notna(own[column]);cp=own[column] if known_own else np.nan
    row[f'system_population_known_sum_{year}']=float(p.sum(min_count=1)) if p.notna().any() else np.nan
    row[f'system_population_complete_{year}']=bool(p.notna().all())
    row[f'n_missing_population_{year}']=int(p.isna().sum());row[f'n_observed_zero_{year}']=int(p.eq(0).sum())
    row[f'center_population_{year}']=float(cp) if pd.notna(cp) else np.nan
    row[f'rural_external_population_known_sum_{year}']=float(g.loc[ext,column].sum(min_count=1)) if g.loc[ext,column].notna().any() else (0. if not ext.any() else np.nan)
    row[f'rural_external_population_complete_{year}']=bool(g.loc[ext,column].notna().all())
    quality_column=f'population_value_quality_{year}'
    qualities=d.loc[g.id,quality_column].fillna('quality_unavailable') if quality_column in d else pd.Series('quality_unavailable',index=g.id)
    supported_values={'direct_published_census_value','reviewed_primary_reported_value','reviewed_primary_source_value_or_null','direct_official_city_value','fresh_primary_r5_source','reviewed_primary_source_child_partition','reviewed_primary_control_derived_zero'}
    primary=qualities.isin(supported_values)&g.set_index('id')[column].notna();protected=qualities.eq('secondary_confidentiality_protected_value_exact_scope_unverified')
    row[f'n_population_exact_primary_supported_{year}']=int(primary.sum());row[f'n_population_secondary_protected_scope_unverified_{year}']=int(protected.sum())
    row[f'system_population_exact_primary_supported_{year}']=bool(primary.all())
    gp=g.set_index('id')[column];denom=gp.sum(min_count=1)
    row[f'population_exact_primary_supported_known_population_share_{year}']=float(gp[primary].sum()/denom) if pd.notna(denom) and denom>0 else np.nan
    row[f'population_secondary_protected_scope_unverified_known_population_share_{year}']=float(gp[protected].sum()/denom) if pd.notna(denom) and denom>0 else np.nan
    row[f'population_quality_counts_json_{year}']=json.dumps(qualities.value_counts().to_dict(),ensure_ascii=False)
   # Rural-zone context uses rural population weights; repeated municipal hectares
   # are never summed. Equal observations within a municipality receive its TOTAL
   # rural population weight, equivalent to grouping that context by unique MO.
   rural_ids=g.loc[ext,'id'];rural_nodes=d.loc[rural_ids];weights=pd.to_numeric(rural_nodes.population_2021,errors='coerce');den=weights.sum(min_count=1)
   row['rural_context_population_weights_complete2021']=bool(weights.notna().all())
   row['rural_context_population_denominator2021']=float(den) if pd.notna(den) else np.nan
   row['rural_context_n_unique_municipalities2021']=int(rural_nodes.municipality_oktmo8_2021.nunique()) if 'municipality_oktmo8_2021' in rural_nodes else 0
   for flag in ['agro_high_productivity_evidence','agro_decline_evidence']:
    vals=rural_nodes[flag] if flag in rural_nodes else pd.Series(pd.NA,index=rural_ids,dtype='boolean')
    usable=vals.notna()&weights.notna()&weights.ge(0);known=weights[usable].sum();coverage=known/den if pd.notna(den) and den>0 else np.nan
    share=float((weights[usable]*vals[usable].astype(float)).sum()/known) if known>0 else np.nan
    row['rural_'+flag+'_population_coverage2021']=coverage;row['rural_'+flag+'_weighted_true_fraction2021']=share
    row['rural_'+flag]=bool(share>=.5) if np.isfinite(coverage) and coverage>=.8 and np.isfinite(share) else None
   for column in ['climate_gaez_sat_above10_cday_1981_2010','climate_gaez_summer_precipitation_over_pet_1981_2010','context_grain_yield_centner_per_ha_2021']:
    vals=pd.to_numeric(rural_nodes[column],errors='coerce') if column in rural_nodes else pd.Series(np.nan,index=rural_ids)
    usable=vals.notna()&weights.notna()&weights.ge(0);known=weights[usable].sum();coverage=known/den if pd.notna(den) and den>0 else np.nan
    row['rural_'+column+'_population_coverage2021']=coverage
    row['rural_'+column+'_weighted_mean']=float((vals[usable]*weights[usable]).sum()/known) if known>0 and np.isfinite(coverage) and coverage>=.8 else np.nan
   if 'recreation_dacha_evidence' in rural_nodes:
    row['rural_recreation_dacha_positive_witness']=True if rural_nodes.recreation_dacha_evidence.fillna(False).any() else None
   else:row['rural_recreation_dacha_positive_witness']=None
   for flag in ['recreation_facility_evidence','dacha_landuse_evidence','designated_resort_territory_evidence']:
    vals=rural_nodes[flag] if flag in rural_nodes else pd.Series(pd.NA,index=rural_ids,dtype='boolean')
    row['rural_n_positive_'+flag]=int(vals.fillna(False).sum())
   for count_column in ['sanatorium_map_points_within1km','official_resort_polygon_memberships','osm_allotment_geometries_within3km','osm_accommodation_points_within3km']:
    vals=pd.to_numeric(rural_nodes[count_column],errors='coerce') if count_column in rural_nodes else pd.Series(np.nan,index=rural_ids)
    # Number of member settlements with witnesses; facility proximity counts are NOT
    # added as unique sites because one object can witness multiple settlements.
    row['rural_n_settlements_with_'+count_column]=int(vals.gt(0).sum())
   strong_recreation=row.get('rural_n_positive_dacha_landuse_evidence',0)>0 or row.get('rural_n_positive_designated_resort_territory_evidence',0)>0 or row.get('rural_n_settlements_with_sanatorium_map_points_within1km',0)>0
   row['rural_recreation_dacha_stronger_context_witness']=True if strong_recreation else None
   # Nationality is an aggregate response profile, never language or an individual cause.
   if 'ethnicity_declared_persons2021' in d and 'ethnicity_russian_responses2021' in d:
    rural_ids=g.loc[ext,'id'];decl=d.loc[rural_ids,'ethnicity_declared_persons2021'];russian=d.loc[rural_ids,'ethnicity_russian_responses2021'];usable=decl.notna()&russian.notna()&decl.gt(0)&russian.ge(0)&russian.le(decl)
    rural_p2021=g.loc[ext].set_index('id').population_2021
    known_p=rural_p2021[rural_p2021.index.isin(decl.index[usable])].sum();all_p=rural_p2021.sum(min_count=1)
    coverage=known_p/all_p if pd.notna(all_p) and all_p>0 else np.nan
    share=(decl[usable].sum()-russian[usable].sum())/decl[usable].sum() if decl[usable].sum()>0 else np.nan
    own_decl=source_decl=own.get('ethnicity_declared_persons2021',np.nan);own_rus=own.get('ethnicity_russian_responses2021',np.nan)
    center_russian_majority=bool(own_rus/own_decl>.5) if pd.notna(own_decl) and own_decl>0 and pd.notna(own_rus) and 0<=own_rus<=own_decl else None
    contrast=(center_russian_majority and share>.5) if center_russian_majority is not None and np.isfinite(share) and np.isfinite(coverage) and coverage>=.8 else None
    row['rural_ethnicity_usable_population_coverage2021']=coverage;row['rural_nonrussian_share_of_declared2021']=share;row['center_russian_majority_among_declared2021']=center_russian_majority;row['ethnocultural_composition_contrast_observed']=contrast;row['ethnicity_explains_growth_claim']=False
   rows.append(row)
  for year in [2002,2010,2021]:
   col=f'population_{year}';unassigned=ordinary.center_id.isna();total=float(ordinary[col].sum());assigned=float(ordinary.loc[~unassigned,col].sum());rest=float(ordinary.loc[unassigned,col].sum())
   balances.append({'level':level,'year':year,'known_axis_sum':total,'assigned_known_sum':assigned,'unassigned_known_sum':rest,'n_axis':len(ordinary),'n_assigned':int((~unassigned).sum()),'n_missing_population':int(ordinary[col].isna().sum()),'known_population_conserved':abs(total-assigned-rest)<1e-6})
 return pd.DataFrame(rows),pd.DataFrame(balances)

def demographic_source_recovery_sensitivity(nodes,members,levels,systems,config):
 year=int(config['dynamic_initial_year']);final=int(config['dynamic_final_year']);original=f'original_population_{year}'
 if original not in nodes:return pd.DataFrame()
 source=nodes.set_index('id');rural=~nodes.type.fillna('').isin(['город','пгт','посёлок городского типа','рабочий посёлок'])
 rows=[]
 for level,assignment in levels.items():
  x=nodes[['id','_population_axis_row',original,f'population_{year}']].copy();x['center_id']=assignment.values;x['rural_external']=rural&x.id.ne(x.center_id)
  x=x[x._population_axis_row&x.center_id.notna()]
  for center,g in x.groupby('center_id',observed=True):
   ext=g[g.rural_external];orig=g[original];rural_orig=ext[original];row={'level':level,'center_id':center,'original_system_population_known_sum_initial':float(orig.sum(min_count=1)) if orig.notna().any() else np.nan,'original_system_population_complete_initial':bool(orig.notna().all()),'original_rural_population_known_sum_initial':float(rural_orig.sum(min_count=1)) if rural_orig.notna().any() else (0. if not len(ext) else np.nan),'original_rural_population_complete_initial':bool(rural_orig.notna().all()),'original_center_population_initial':source.loc[center,original] if source.loc[center,'_population_axis_row'] else np.nan,'n_population_values_changed_in_system':int((g[original].ne(g[f'population_{year}'])&~(g[original].isna()&g[f'population_{year}'].isna())).sum())}
   rows.append(row)
 result=pd.DataFrame(rows).merge(systems[['level','center_id',f'system_population_known_sum_{year}',f'system_population_known_sum_{final}',f'rural_external_population_known_sum_{year}',f'rural_external_population_known_sum_{final}',f'center_population_{year}',f'center_population_{final}']],on=['level','center_id'],validate='one_to_one')
 for group,old,new,last in [('system','original_system_population_known_sum_initial',f'system_population_known_sum_{year}',f'system_population_known_sum_{final}'),('rural','original_rural_population_known_sum_initial',f'rural_external_population_known_sum_{year}',f'rural_external_population_known_sum_{final}'),('center','original_center_population_initial',f'center_population_{year}',f'center_population_{final}')]:
  result[group+'_annual_rate_original_source']=annual_rate(result[old].to_numpy(),result[last].to_numpy(),final-year);result[group+'_annual_rate_reviewed_source']=annual_rate(result[new].to_numpy(),result[last].to_numpy(),final-year)
 result['membership_grid_identical_between_source_variants']=True
 return result

def descriptive_centrality(systems,centers,reference_year):
 """Word-style [0,1] mass+perimeter index for description; never fed back into mass/ranks."""
 z=systems.copy();lookup=centers.set_index('id')
 z['own_positive_mass']=z.center_id.map(lookup.own_positive_mass)
 z['intrinsic_empirical_rank']=z.center_id.map(lookup.intrinsic_empirical_rank)
 z['centrality_rural_population_reference_year']=reference_year
 col=f'rural_external_population_known_sum_{reference_year}'
 complete=z[f'rural_external_population_complete_{reference_year}']
 z['descriptive_centrality_posthoc_0_1']=np.nan
 for level,idx in z.groupby('level').groups.items():
  a=np.log(z.loc[idx,'own_positive_mass']);b=np.log1p(z.loc[idx,col].where(complete.loc[idx]))
  def normalized(v):
   span=v.max()-v.min()
   return (v-v.min())/span if span>0 else v.where(v.isna(),0.)
  score=pd.concat([normalized(a),normalized(b)],axis=1).mean(axis=1,skipna=False)
  z.loc[idx,'descriptive_centrality_posthoc_0_1']=score
 z['centrality_used_to_train_mass_or_rank']=False
 return z

def tri(value):
 if value is pd.NA or value is None or pd.isna(value):return None
 return bool(value)
def tri_all(*values):
 if any(v is False for v in values):return False
 return None if any(v is None for v in values) else True

def classify_word_types(systems,nodes,config):
 initial=config['dynamic_initial_year'];final=config['dynamic_final_year'];years=final-initial
 z=systems.copy();d=nodes.set_index('id');out=[]
 for _,r in z.iterrows():
  uid=r.center_id;source=d.loc[uid]
  complete=all(bool(r.get(f'{kind}_population_complete_{y}',False)) for kind in ['system','rural_external'] for y in [initial,final])
  exact_primary_pair=all(bool(r.get(f'system_population_exact_primary_supported_{y}',False)) for y in [initial,final])
  c0=r.get(f'center_population_{initial}',np.nan);c1=r.get(f'center_population_{final}',np.nan);r0=r.get(f'rural_external_population_known_sum_{initial}',np.nan);r1=r.get(f'rural_external_population_known_sum_{final}',np.nan)
  cr=float(annual_rate([c0],[c1],years)[0]);rr=float(annual_rate([r0],[r1],years)[0]);eps=.0025
  cdecl=None if not np.isfinite(cr) else cr<-eps;cgrow=None if not np.isfinite(cr) else cr>eps;cstable=None if not np.isfinite(cr) else abs(cr)<=eps;rdecl=None if not np.isfinite(rr) else rr<-eps;rgrow=None if not np.isfinite(rr) else rr>eps;rstable=None if not np.isfinite(rr) else abs(rr)<=eps
  def evidence(name):return tri(source.get(name,source.get('context_'+name,pd.NA)))
  suburban=evidence('network_suburban_30_60_minutes');agro=tri(r.get('rural_agro_high_productivity_evidence',None));agrodecl=tri(r.get('rural_agro_decline_evidence',None));recreation=tri(r.get('rural_recreation_dacha_stronger_context_witness',None));ethno=tri(r.get('ethnocultural_composition_contrast_observed',None));industry=evidence('industrial_decline_evidence');resource=evidence('resource_shift_evidence');peripheral=evidence('network_peripheral_evidence')
  center_nondecline=None if cdecl is None else not cdecl
  rural_nondecline=None if rdecl is None else not rdecl
  center_nonincrease=None if cgrow is None else not cgrow
  # Mandatory Word criteria are separate tri-state cells. Missing causal/functional
  # evidence must not be silently replaced by a regional name or municipal proxy.
  criteria={
   1:{'center_nondecline':center_nondecline,'suburban_30_60_minutes':suburban,'own_positive_migration':evidence('own_positive_migration_evidence'),'own_high_housing':evidence('own_high_housing_evidence'),'observed_commuting':evidence('commuting_observed'),'small_rural_perimeter':evidence('small_rural_perimeter_evidence'),'high_mass_and_within_rank_centrality':evidence('high_mass_and_within_rank_centrality_evidence'),'negative_demographic_distance_gradient':evidence('negative_demographic_distance_gradient_evidence')},
   2:{'center_nondecline':center_nondecline,'rural_decline':rdecl,'high_agro_productivity':agro,'peripheral_access':peripheral,'high_sown_farmland_share':evidence('high_sown_farmland_share_evidence'),'agro_processing_function':evidence('agro_processing_function_evidence'),'trade_and_administration_function':evidence('trade_and_administration_function_evidence')},
   3:{'center_stable':cstable,'rural_stable':rstable,'high_agro_productivity':agro,'high_sown_farmland_share':evidence('high_sown_farmland_share_evidence'),'favorable_agroclimate':evidence('favorable_agroclimate_evidence'),'developed_agro_infrastructure':evidence('developed_agro_infrastructure_evidence')},
   4:{'center_stable':cstable,'rural_stable':rstable,'peripheral_access':peripheral,'basic_administrative_service_function':evidence('basic_administrative_service_function_evidence'),'low_or_moderate_mass_centrality':evidence('low_or_moderate_mass_centrality_evidence')},
   5:{'center_decline_or_stagnation':center_nonincrease,'rural_growth_or_stability':rural_nondecline,'recreation_dacha_context':recreation,'high_housing_outside_center':evidence('high_housing_outside_center_evidence')},
   6:{'center_decline':cdecl,'rural_growth_or_stability':rural_nondecline,'descriptive_ethnic_composition_contrast':ethno,'ethnocultural_demographic_mechanism':evidence('ethnocultural_demographic_evidence')},
   7:{'center_decline':cdecl,'rural_decline':rdecl,'agro_decline':agrodecl,'nonchernozem_or_adverse_agroclimate':evidence('nonchernozem_or_adverse_agroclimate_evidence'),'peripheral_access':peripheral,'low_mass_and_centrality':evidence('low_mass_and_centrality_evidence')},
   8:{'center_decline':cdecl,'rural_decline':rdecl,'industrial_decline':industry,'historical_industrial_function':evidence('historical_industrial_function_evidence'),'low_centrality':evidence('low_centrality_evidence'),'no_compensating_agro_base':evidence('no_compensating_agro_base_evidence')},
   9:{'center_radical_decline':evidence('center_radical_decline_evidence'),'small_center':evidence('small_center_evidence'),'northern_territory':evidence('northern_territory_evidence'),'tiny_agro_component':evidence('tiny_agro_component_evidence'),'resource_origin':evidence('resource_origin_evidence'),'resource_shift':resource}
  }
  # Separate preregistered operational hypotheses from full Word interpretation.
  # P2021<=50k, latitude>=60, mass<=exp(0), Ci<=0.5 are explicit scenarios.
  mass_value=r.get('own_positive_mass',np.nan);ci=r.get('descriptive_centrality_posthoc_0_1',np.nan)
  lowmass=None if pd.isna(mass_value) else bool(mass_value<=1.)
  lowci=None if pd.isna(ci) else bool(ci<=.5)
  sat=r.get('rural_climate_gaez_sat_above10_cday_1981_2010_weighted_mean',np.nan)
  adverse=None if pd.isna(sat) else bool(sat<1800.)
  criteria[7]['nonchernozem_or_adverse_agroclimate']=adverse
  criteria[7]['low_mass_and_centrality']=tri_all(lowmass,lowci)
  criteria[4]['low_or_moderate_mass_centrality']=tri_all(lowmass,lowci)
  criteria[8]['low_centrality']=lowci
  criteria[9]['small_center']=None if pd.isna(c1) else bool(c1<=50000)
  criteria[9]['northern_territory']=None if pd.isna(source.lat) else bool(source.lat>=60)
  core={
   1:{'center_nondecline':center_nondecline,'suburban_access_30_60':suburban,'observed_commuting':evidence('commuting_observed')},
   2:{'center_nondecline':center_nondecline,'rural_decline':rdecl,'high_agro_productivity':agro,'peripheral_access':peripheral},
   3:{'center_stable':cstable,'rural_stable':rstable,'high_agro_productivity':agro},
   4:{'center_stable':cstable,'rural_stable':rstable,'peripheral_access':peripheral,'low_mass_expmeanZ_le1':lowmass,'low_ci_le0_5':lowci},
   5:{'center_decline_or_stagnation':center_nonincrease,'rural_growth_or_stability':rural_nondecline,'recreation_dacha_context':recreation},
   6:{'center_decline':cdecl,'rural_growth_or_stability':rural_nondecline,'observed_ethnic_composition_contrast':ethno},
   7:{'center_decline':cdecl,'rural_decline':rdecl,'agro_decline':agrodecl,'adverse_agroclimate_sat_lt1800':adverse,'peripheral_access':peripheral,'low_mass_expmeanZ_le1':lowmass,'low_ci_le0_5':lowci},
   8:{'center_decline':cdecl,'rural_decline':rdecl,'industrial_decline':industry,'historical_industrial_function':evidence('historical_industrial_function_evidence'),'low_ci_le0_5':lowci},
   9:{'center_decline':cdecl,'small_center_population_le50000':None if pd.isna(c1) else bool(c1<=50000),'north_latitude_ge60':None if pd.isna(source.lat) else bool(source.lat>=60),'tiny_agro':evidence('tiny_agro_component_evidence'),'resource_origin':evidence('resource_origin_evidence'),'resource_shift':resource}
  }
  names={1:'Урбанизирующиеся маятниково-миграционные (пригородные) СГРТ',2:'Урбанизирующиеся аграрно-сервисные СГРТ (региональные узлы)',3:'Стабильные аграрно-сервисные СГРТ в зонах высокой аграрной продуктивности',4:'Стабильные периферийные СГРТ',5:'Контрурбанизационные рекреационно-дачные СГРТ',6:'Контрурбанизационные этнические (анклавные) СГРТ',7:'Депрессивные аграрно-сервисные СГРТ Нечерноземья',8:'Депрессивные старопромышленные СГРТ',9:'Депрессивные ресурсно-вахтовые СГРТ северных территорий'}
  for typ,conditions in criteria.items():
   status=tri_all(*conditions.values())
   unknown=[k for k,v in conditions.items() if v is None];contradicted=[k for k,v in conditions.items() if v is False]
   supported=sum(v is True for v in conditions.values())
   out.append({'level':int(r.level),'center_id':uid,'word_type':typ,'rule_status':'satisfied_observed_indicators' if status is True and complete and exact_primary_pair else 'not_satisfied' if status is False else 'unknown_missing_required_indicators','population_pair_complete':complete,'population_pair_exact_primary_supported':exact_primary_pair,'dynamics_uses_secondary_protected_values':any(r.get(f'n_population_secondary_protected_scope_unverified_{y}',0)>0 for y in [initial,final]),'center_annual_rate':cr if np.isfinite(cr) else None,'rural_annual_rate':rr if np.isfinite(rr) else None,'required_criteria_truth_json':json.dumps(conditions,ensure_ascii=False),'unknown_required_criteria_json':json.dumps(unknown,ensure_ascii=False),'contradicted_required_criteria_json':json.dumps(contradicted,ensure_ascii=False),'n_observed_supporting_criteria':supported,'n_required_criteria':len(conditions),'descriptive_partial_candidate_not_proven_type':tri_all(*core[typ].values()) is True and complete and bool(unknown),'operational_hypothesis':tri_all(*core[typ].values()) is True and complete,'operational_core_truth_json':json.dumps(core[typ],ensure_ascii=False),'word_type_name':names[typ],'operational_status':'HYPOTHESIS' if tri_all(*core[typ].values()) is True and complete else 'NOT_ESTABLISHED','not_causal_or_full_functional_validation':True,'type6_evidence_is_composition_contrast_not_mechanism':typ==6})
 return pd.DataFrame(out)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',type=Path,default=HERE/'model_inputs_2021_restricted.json');ap.add_argument('--output',type=Path,default=HERE/'output_2021_restricted_baseline');ap.add_argument('--stage',choices=['prepare','full'],default='prepare');a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True);start=time.monotonic();config=json.loads(a.inputs.read_text())
 execution_sources={Path(__file__).resolve():sha(Path(__file__)),a.inputs.resolve():sha(a.inputs)}
 nodes,watched=load_nodes(config);watched.update(execution_sources);mass,components=build_mass(nodes,config);centers,ranks=empirical_ranks(mass,config)
 nodes.to_parquet(a.output/'nodes.parquet',index=False);mass.to_parquet(a.output/'own_mass_components.parquet',index=False);centers.merge(nodes[['id','name','type','region','lat','lon']],on='id',validate='one_to_one').to_parquet(a.output/'candidate_centers.parquet',index=False)
 dump(a.output/'mass_components.json',components);dump(a.output/'empirical_ranks.json',ranks)
 centers.groupby(['intrinsic_empirical_rank','n_observed_mass_blocks'],observed=True).agg(n_centers=('id','size'),mass_min=('own_positive_mass','min'),mass_median=('own_positive_mass','median'),mass_max=('own_positive_mass','max')).reset_index().to_csv(a.output/'rank_mass_profile_completeness.csv',index=False)
 receipt={'status':'PREPARED_NOT_FULL_WORD_RESULT','axis_rows':len(nodes),'population_axis_rows':int(nodes._population_axis_row.sum()),'candidate_centers':len(centers),'empirical_rank_count':ranks['chosen_components'],'source_sha256':{str(p.relative_to(REPO)):digest for p,digest in watched.items()},'missing_component_names':[c['name'] for c in components if c['n_used_in_z']==0],'mass_not_calibrated_on_own_catchment':True,'unavailable_transport_is_not_replaced_by_proxy':True,'scientific_acceptance':False,'target_run_id':config.get('target_run_id'),'linkage_scenario':config.get('linkage_mode','unspecified'),'configuration_sha256':execution_sources[a.inputs.resolve()],'model_code_sha256':execution_sources[Path(__file__).resolve()]}
 if a.stage=='full':
  try:
   transport_watched,transport_receipt,scope=verify_routing_scope(config,nodes,centers,mass);watched.update(transport_watched);receipt['routing_scope_verification']=scope
   travel_path=travel_source(config);watched[travel_path]=sha(travel_path)
   expected_output=transport_receipt.get('output_manifest_sha256') if config.get('travel_manifest') else transport_receipt.get('output_sha256')
   if watched[travel_path]!=expected_output:raise ValueError('Routing output bytes do not match completed receipt')
   travel,travel_path=load_travel(config,nodes,centers,mass);watched.update(travel.attrs.pop('additional_source_sha256',{}));receipt['source_sha256'][str(travel_path.relative_to(REPO))]=watched[travel_path]
   accessibility=network_context(nodes,centers,travel);nodes=nodes.merge(accessibility,on='id',how='left',validate='one_to_one')
   initial_centers=centers[centers.intrinsic_empirical_rank.eq(centers.intrinsic_empirical_rank.min())] if config.get('initial_assignment_center_scope')=='lowest_empirical_order_only' else centers
   members,choice=huff_assign(nodes,initial_centers,travel,config,core_centers=centers);levels,hierarchy=build_hierarchy(members,centers,travel,config)
   n_integral_choice_edges=len(choice)
   if not config.get('persist_full_choice_edges',False):del choice
   receipt['initial_assignment_center_scope']=config.get('initial_assignment_center_scope','all_ranks_compete')
   receipt['n_low_level_competing_centers']=len(initial_centers)
   higher_ids=set(centers.loc[centers.intrinsic_empirical_rank.gt(centers.intrinsic_empirical_rank.min()),'id'])
   higher_reachable=set(travel.loc[travel.destination_id.isin(higher_ids)&travel.travel_minutes.le(config['model'].get('hierarchy_max_travel_minutes',360.)),'origin_id'])
   members['reachable_only_higher_order_provider']=members.raw_model_center_id.isna()&members.id.isin(higher_reachable)&~members.protected_core
   members.loc[members.reachable_only_higher_order_provider,'assignment_status']='pending_at_lowest_level_reachable_only_higher_order_provider'
   members['dependent_service_eligibility_budget_minutes']=config['model'].get('pending_singleton_max_travel_minutes',config['model']['max_travel_minutes'])
   members['whole_system_parent_budget_minutes']=config['model'].get('hierarchy_max_travel_minutes',360.)
   members['first_assigned_hierarchy_level']=pd.Series(pd.NA,index=members.index,dtype='Int64')
   for level,assignment in levels.items():
    members[f'center_id_l{level}']=assignment.values
    newly=members.first_assigned_hierarchy_level.isna()&assignment.notna();members.loc[newly,'first_assigned_hierarchy_level']=level
   systems,balances=aggregate(nodes,members,levels,config);systems=descriptive_centrality(systems,centers,int(config['mass_reference_year']));types=classify_word_types(systems,nodes,config);configuration=configuration_table(nodes,members,systems,levels,centers);function_assignments=function_specific_assignments(nodes,mass,centers,travel,config)
   demographic_source_recovery_sensitivity(nodes,members,levels,systems,config).to_parquet(a.output/'demographic_source_recovery_sensitivity.parquet',index=False)
   function_assignments.to_parquet(a.output/'function_specific_memberships.parquet',index=False);functional_agreement(members,function_assignments).to_parquet(a.output/'functional_leader_agreement.parquet',index=False)
   accessibility.to_parquet(a.output/'network_accessibility.parquet',index=False);configuration.to_parquet(a.output/'system_configurations.parquet',index=False)
   members.to_parquet(a.output/'memberships.parquet',index=False);
   if config.get('persist_full_choice_edges',False):choice.to_parquet(a.output/'huff_choice_edges.parquet',index=False)
   else:(a.output/'huff_choice_edges.parquet').unlink(missing_ok=True)
   receipt['all_choice_edges_persisted']=bool(config.get('persist_full_choice_edges',False));receipt['n_integral_low_choice_edges_computed']=n_integral_choice_edges;receipt['choice_edge_recompute']='model/recompute_choice_edges.py; G=M*exp(-minutes/tau), P=G/(sumG+outside_mass)'
   hierarchy.to_parquet(a.output/'hierarchy.parquet',index=False);systems.to_parquet(a.output/'systems.parquet',index=False);balances.to_csv(a.output/'population_balances.csv',index=False);types.to_parquet(a.output/'word_type_hypotheses.parquet',index=False);types[types.operational_hypothesis].to_parquet(a.output/'operational_type_candidates.parquet',index=False)
   initial=int(config['dynamic_initial_year']);final=int(config['dynamic_final_year'])
   primary_supported=systems[f'system_population_exact_primary_supported_{initial}']&systems[f'system_population_exact_primary_supported_{final}']
   systems[primary_supported].to_parquet(a.output/'primary_source_supported_systems_sensitivity.parquet',index=False)
   types[types.population_pair_exact_primary_supported].to_parquet(a.output/'primary_source_supported_types_sensitivity.parquet',index=False)
   receipt['n_exact_primary_supported_systems_dynamic_pair']=int(primary_supported.sum())
   receipt['assigned_population_axis_by_level']={str(int(r.level)):int(r.n_assigned) for r in balances[balances.year.eq(final)].itertuples()}
   receipt['n_lowest_pending_reachable_only_higher_order']=int(members.reachable_only_higher_order_provider.sum())
   receipt['first_assigned_hierarchy_level_counts']={str(int(k)):int(v) for k,v in members.first_assigned_hierarchy_level.dropna().value_counts().items()}
   receipt['operational_hypothesis_count_by_word_type']={str(int(k)):int(v) for k,v in types[types.operational_hypothesis].word_type.value_counts().items()}
   assert balances.known_population_conserved.all()
   receipt.update(status='COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW',assigned_population_axis=int(members.loc[members._population_axis_row,'assigned_center_id'].notna().sum()),routed_origin_count=int(travel.origin_id.nunique()),levels=int(systems.level.nunique()),word_type_satisfied_count=int(types.rule_status.eq('satisfied_observed_indicators').sum()))
  except Exception as e:
   receipt.update(status='BLOCKED_FULL_WORD_RESULT',error=repr(e));dump(a.output/'run_receipt.json',receipt);raise
 receipt['source_sha256']={str(p.relative_to(REPO)):digest for p,digest in watched.items()}
 changed=[str(p) for p,digest in watched.items() if sha(p)!=digest]
 receipt['input_bytes_changed_during_run']=changed
 if changed:receipt['status']='REJECT_INPUT_CHANGED_DURING_COMPUTATION'
 receipt['seconds']=round(time.monotonic()-start,3);dump(a.output/'run_receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
