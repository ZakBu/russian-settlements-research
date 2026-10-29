"""Directed population fields for the complete Saratov 2021 settlement roster.

An exact forward reachability union reduces computation, not the geographical
source frame. Every path of cost <= H from a regional origin stays in that
union, since all nonnegative prefixes have cost <= H. Sparse absent pairs mean
not reached within the computational horizon, never zero cost or no demand.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_mass.routes import load_graph,GRAPH_SHA256,haversine_km
from scripts.sgrt_field_pilot.field_model import prepare_sources,kernel

REFERENCE='sgrt/zero20261025/context/analysis_reference.parquet'
ENDPOINTS='sgrt/identity20261026/routes/endpoint_network_quality.parquet'
HALF_TIMES=(5.,10.,15.,20.,30.,40.,60.,80.,120.)


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def fingerprint(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def prepare(reference,endpoints,regional_roster):
    s=prepare_sources(reference,endpoints)
    s=s.loc[s.source_record_id.notna()].sort_values('source_record_id').reset_index(drop=True)
    if s.source_record_id.duplicated().any():raise ValueError('Nonunique current settlement identity')
    current=regional_roster[['source_record_id']].copy()
    if current.source_record_id.duplicated().any():raise ValueError('Duplicate regional origin')
    roster=current.merge(s,on='source_record_id',how='left',validate='one_to_one')
    if roster['region'].isna().any():raise ValueError('Regional record missing from national reference')
    roster['row_index']=np.arange(len(roster),dtype='int32')
    dest=s.loc[s.accepted_source_endpoint].copy().reset_index(drop=True)
    dest['destination_index']=np.arange(len(dest),dtype='int32')
    dest['destination_connector_minutes']=4*dest.snap_km
    roster['origin_connector_minutes']=4*roster.snap_km
    roster['route_row_status']=np.where(roster.accepted_source_endpoint,'computed_to_horizon','origin_endpoint_unavailable')
    return s,roster,dest


def forward_union(graph,origin_nodes,horizon):
    from scipy.sparse.csgraph import dijkstra
    if not np.isfinite(horizon) or horizon<=0:raise ValueError('Positive finite horizon required')
    nodes=np.unique(np.asarray(origin_nodes,dtype='int64'))
    if np.any(nodes<0) or np.any(nodes>=graph.shape[0]):raise ValueError('Origin outside graph')
    distances=dijkstra(graph,directed=True,indices=nodes,min_only=True,limit=horizon)
    keep=np.flatnonzero(np.isfinite(distances)).astype('int32')
    del distances
    reduced=graph[keep][:,keep].tocsr();reduced.sort_indices()
    old_to_new=np.full(graph.shape[0],-1,dtype='int32');old_to_new[keep]=np.arange(len(keep),dtype='int32')
    return reduced,keep,old_to_new


def build_inputs(reference_path,endpoints_path,regional_path,graph_dir,output,horizon=480.):
    from scipy.sparse import save_npz,load_npz
    from scipy.sparse.csgraph import dijkstra
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    s,roster,dest=prepare(pd.read_parquet(reference_path),pd.read_parquet(endpoints_path),pd.read_parquet(regional_path))
    s.to_parquet(output/'national_reference_with_endpoints.parquet',index=False,compression='zstd')
    roster.to_parquet(output/'regional_roster.parquet',index=False,compression='zstd')
    dest.to_parquet(output/'destinations.parquet',index=False,compression='zstd')
    started=time.monotonic();graph=load_graph(graph_dir)
    print(json.dumps({'event':'full_graph_loaded','seconds':time.monotonic()-started,'shape':graph.shape,'arcs':graph.nnz}),flush=True)
    if (output/'reduced_graph.npz').is_file():
        old=json.loads((output/'graph_summary.json').read_text())
        if old['horizon_minutes']!=horizon or old['regional_roster_sha256']!=fingerprint(regional_path) or old['reference_sha256']!=fingerprint(reference_path) or old['endpoints_sha256']!=fingerprint(endpoints_path):raise ValueError('Stale cached reduced graph')
        reduced=load_npz(output/'reduced_graph.npz');keep=np.load(output/'road_node_axis.npy')
        mapping=np.full(graph.shape[0],-1,dtype='int32');mapping[keep]=np.arange(len(keep),dtype='int32')
    else:
        origins=roster.loc[roster.accepted_source_endpoint,'road_node_index'].astype('int64').to_numpy()
        start=time.monotonic();reduced,keep,mapping=forward_union(graph,origins,horizon)
        save_npz(output/'reduced_graph.npz',reduced,compressed=True);np.save(output/'road_node_axis.npy',keep)
        facts={'schema':'sgrt.saratov.regional_graph_union.v1','graph_sha256':GRAPH_SHA256,'horizon_minutes':horizon,
            'direction':'forward_from_regional_origins','zero_seed_offsets_give_conservative_union':True,
            'full_nodes':graph.shape[0],'full_arcs':graph.nnz,'reduced_nodes':reduced.shape[0],'reduced_arcs':reduced.nnz,
            'regional_roster_sha256':fingerprint(regional_path),'reference_sha256':fingerprint(reference_path),
            'endpoints_sha256':fingerprint(endpoints_path),'build_seconds':time.monotonic()-start,
            'proof':'For any directed origin path of cost <=H, each nonnegative prefix costs <=H; all of its vertices belong to the forward multisource union. Induced routing preserves all such paths. Administrative boundaries do not restrict the graph.'}
        write_json(output/'graph_summary.json',facts)
    sample=roster.loc[roster.accepted_source_endpoint].iloc[np.linspace(0,int(roster.accepted_source_endpoint.sum())-1,5,dtype=int)]
    times=[]
    for row in sample.itertuples():
        t=time.monotonic();d=dijkstra(reduced,directed=True,indices=int(mapping[int(row.road_node_index)]),limit=horizon);times.append(time.monotonic()-t)
    facts=json.loads((output/'graph_summary.json').read_text());facts['single_query_benchmark_seconds']=times
    facts['serial_regional_query_seconds_estimate']=float(np.mean(times)*roster.accepted_source_endpoint.sum());write_json(output/'graph_summary.json',facts)
    print(json.dumps({'event':'reduced_graph_ready','facts':facts},ensure_ascii=False),flush=True)
    return graph,reduced,mapping,s,roster,dest



def known_costs_from_sparse(matrix,row,columns):
    """Explicit zeros survive; absent costs remain unknown/censored."""
    columns=np.asarray(columns,dtype='int64');out=np.full(len(columns),np.nan)
    a,b=matrix.indptr[row:row+2];indices=matrix.indices[a:b]
    positions=np.searchsorted(indices,columns);good=positions<len(indices)
    good[good]&=indices[positions[good]]==columns[good]
    out[good]=matrix.data[a:b][positions[good]]
    return out


def top_group_candidates(costs,group_codes,groups,k=3):
    """Cheapest distinct destinations; ties at kth group are all retained."""
    costs=np.asarray(costs,dtype=float);group_codes=np.asarray(group_codes,dtype='int32')
    best=np.full(len(groups),np.inf);np.minimum.at(best,group_codes,costs)
    finite=np.flatnonzero(np.isfinite(best))
    if not len(finite):return []
    threshold=np.partition(best[finite],min(k,len(finite))-1)[min(k,len(finite))-1]
    chosen=finite[best[finite]<=threshold+1e-10]
    ordered=chosen[np.lexsort((np.asarray(groups,dtype=str)[chosen],best[chosen]))]
    return [(int(g),float(best[g]),int(1+(best[finite]<best[g]-1e-10).sum())) for g in ordered]


def physical_contract(catalog,mapping):
    p=pd.read_parquet(catalog).reset_index(drop=True)
    if 'source_record_id' not in p and 'correctsource_record_id' in p:p['source_record_id']=p['correctsource_record_id']
    required={'provider_id','family','source_record_id','road_node_index','destination_connector_minutes','accepted_snap'}
    if not required<=set(p):raise ValueError('Physical provider catalogue lacks '+str(required-set(p)))
    p=p.loc[p.accepted_snap.eq(True)&p.road_node_index.notna()&p.destination_connector_minutes.ge(0)&np.isfinite(p.destination_connector_minutes)].copy().reset_index(drop=True)
    nodes=p.road_node_index.to_numpy(dtype='int64')
    if np.any(nodes<0) or np.any(nodes>=len(mapping)):raise ValueError('Physical node outside original graph')
    p['reduced_node_index']=mapping[nodes]
    p['destination_group_key']=p['provider_destination_key'] if 'provider_destination_key' in p else np.where(p.source_record_id.notna(),'np:'+p.source_record_id.fillna('').astype(str),'physical:'+p.get('catalog_id',p.provider_id).astype(str))
    result=[]
    for family,f in p.groupby('family',sort=True):
        groups,codes=np.unique(f.destination_group_key.astype(str),return_inverse=True)
        result.append((str(family),f.reset_index(drop=True),groups,codes.astype('int32')))
    return result


def provider_rows(distances,row,contract,horizon):
    records=[]
    for family,p,groups,codes in contract:
        node=p.reduced_node_index.to_numpy(dtype='int64');cost=np.full(len(p),np.inf)
        ok=node>=0;cost[ok]=distances[node[ok]]+p.destination_connector_minutes.to_numpy(dtype=float)[ok]+4*float(row.snap_km)
        cost[(~np.isfinite(cost))|(cost>horizon)]=np.inf
        for group,minutes,rank in top_group_candidates(cost,codes,groups):
            candidates=np.flatnonzero((codes==group)&np.isclose(cost,minutes,atol=1e-10,rtol=0))
            chosen=min(candidates,key=lambda j:str(p.iloc[j].get('catalog_id',p.iloc[j].provider_id)));source=p.iloc[chosen]
            records.append({'origin_id':str(row.source_record_id),'family':family,'provider_id':str(source.provider_id),
                'catalog_id':str(source.get('catalog_id',source.provider_id)),
                'source_record_id':None if pd.isna(source.source_record_id) else str(source.source_record_id),
                'destination_group_key':str(groups[group]),'cost_minutes':minutes,'rank':rank,
                'equally_cheap_provider_records_in_group':len(candidates),'within_search_horizon':True})
    return records


def scalar_origin_result(row,reduced,mapping,dest,sources,half_times,horizon,provider_contract=None):
    from scipy.sparse.csgraph import dijkstra
    started=time.monotonic()
    node=int(mapping[int(row.road_node_index)])
    if node<0:raise ValueError('Accepted origin missing from forward union')
    distances=dijkstra(reduced,directed=True,indices=node,limit=horizon)
    destnodes=dest.road_node_index.to_numpy(dtype='int64');newnodes=mapping[destnodes]
    costs=np.full(len(dest),np.inf);ok=newnodes>=0
    costs[ok]=distances[newnodes[ok]]+dest.destination_connector_minutes.to_numpy(dtype=float)[ok]+4*float(row.snap_km)
    own=np.flatnonzero(dest.source_record_id.astype(str).to_numpy()==str(row.source_record_id))
    if len(own):costs[own[0]]=0.
    reached=np.isfinite(costs)&(costs<=horizon)
    index=np.flatnonzero(reached).astype('int32');data=costs[reached]
    massmask=dest.positive_source_mass.to_numpy(dtype=bool)
    main=reached&massmask;unreached=(~reached)&massmask
    p=dest.source_mass_2021.to_numpy(dtype=float)
    field_rows=[]
    ownmass=float(row.source_mass_2021) if bool(row.positive_source_mass) else 0.
    maincost=costs[main];mainpop=p[main]
    # A finite-speed model lower bound tightens, but does not add to, the
    # truncated tail. It uses the same spherical radius as the archived graph.
    lower=haversine_km(float(row.lat),float(row.lon),dest.loc[unreached,'lat'].to_numpy(float),dest.loc[unreached,'lon'].to_numpy(float))/130.*60.
    if np.any(~np.isfinite(lower)):raise ValueError('Credited routed source lacks coordinates')
    lower=np.maximum(horizon,lower)
    unmapped=sources.loc[sources.positive_source_mass&~sources.accepted_source_endpoint]
    unpop=unmapped.source_mass_2021.to_numpy(float)
    unlb=haversine_km(float(row.lat),float(row.lon),unmapped.lat.to_numpy(float),unmapped.lon.to_numpy(float))/130.*60.
    if np.any(~np.isfinite(unlb)):unlb=np.where(np.isfinite(unlb),unlb,0.)
    raw=pd.to_numeric(sources.population_2021,errors='coerce')
    omitted=sources.loc[raw.gt(0)&np.isfinite(raw)&~sources.population_known_credited]
    ompop=pd.to_numeric(omitted.population_2021).to_numpy(float)
    # Missing coordinates retain K<=1 rather than an invented distance.
    omlb=haversine_km(float(row.lat),float(row.lon),pd.to_numeric(omitted.lat,errors='coerce').to_numpy(float),pd.to_numeric(omitted.lon,errors='coerce').to_numpy(float))/130.*60.
    omlb=np.where(np.isfinite(omlb),omlb,0.)
    dest_omitted=(~dest.population_known_credited.to_numpy(bool))&pd.to_numeric(dest.population_2021).gt(0).to_numpy()
    for family in ('exponential','gaussian'):
        for h in half_times:
            value=float(np.dot(mainpop,kernel(maincost,h,family)))
            tail=float(np.dot(p[unreached],kernel(lower,h,family)))
            unmapped_raw=float(unpop.sum())
            unmapped_bound=float(np.dot(unpop,kernel(unlb,h,family)))
            published_envelope=float(np.dot(ompop,kernel(omlb,h,family)))
            # Tighten raw-envelope rows for which an actual route is known.
            reached_om=reached&dest_omitted
            if reached_om.any():
                q=pd.to_numeric(dest.loc[reached_om,'population_2021']).to_numpy(float)
                geometric=haversine_km(float(row.lat),float(row.lon),dest.loc[reached_om,'lat'].to_numpy(float),dest.loc[reached_om,'lon'].to_numpy(float))/130.*60.
                geometric=np.where(np.isfinite(geometric),geometric,0.)
                published_envelope-=float(np.dot(q,kernel(geometric,h,family)))
                published_envelope+=float(np.dot(q,kernel(costs[reached_om],h,family)))
            for include_self in (True,False):
                v=value-(0. if include_self else ownmass)
                if v<0 and v>-1e-7:v=0.
                field_rows.append({'source_record_id':str(row.source_record_id),'kernel':family,'half_time':float(h),
                    'include_self':include_self,'value':v,'known_field':v,'own_credited_mass':ownmass,
                    'tail_upper':tail,'unmapped_mass_upper':unmapped_bound,'unmapped_mass_upper_without_distance_assumption':unmapped_raw,
                    'accepted_mass_field_upper':v+tail+unmapped_bound,'omitted_published_reference_envelope':max(0.,published_envelope-(float(row.population_2021) if not include_self and not bool(row.population_known_credited) and np.isfinite(row.population_2021) and row.population_2021>0 else 0.)),
                    'within_horizon_mass':float(mainpop.sum()),'within_horizon_mass_sources':int(main.sum()),
                    'population_model_scope':'accepted_additive_population_2021','speed_bound_kmh':130.,
                    'computational_horizon_minutes':float(horizon),'status':'computed_to_horizon',
                    'published_envelope_respects_include_self':True,
                    'unmapped_distance_bound_is_conditional_on_same_maximum_speed':True})
    neighbour=reached&dest.ordinary_spatial_2021.eq(True).to_numpy()&(dest.source_record_id.astype(str).to_numpy()!=str(row.source_record_id))
    ni=np.flatnonzero(neighbour);neighbours=[]
    if len(ni):
        threshold=np.partition(costs[ni],min(6,len(ni))-1)[min(6,len(ni))-1]
        chosen=ni[costs[ni]<=threshold+1e-10]
        for j in sorted(chosen,key=lambda j:(costs[j],str(dest.iloc[j].source_record_id))):
            rank=int(1+(costs[ni]<costs[j]-1e-10).sum())
            neighbours.append({'origin_id':str(row.source_record_id),'destination_id':str(dest.iloc[j].source_record_id),
                'minutes':float(costs[j]),'rank':rank,'in_k3':rank<=3,'in_k6':rank<=6,
                'comparison_direction':'outgoing_national_k_nearest','destination_region':str(dest.iloc[j].region)})
    physical=provider_rows(distances,row,provider_contract,horizon) if provider_contract is not None else []
    return int(row.row_index),index,data,field_rows,neighbours,physical,time.monotonic()-started


def load_checkpoint(output,rows,half_times):
    """Fail closed if cost shards and field scenarios are not one checkpoint."""
    from scipy.sparse import load_npz
    output=Path(output);parts=sorted((output/'cost_chunks').glob('part_*.npz'))
    if [p.name for p in parts]!=[f'part_{i:03d}.npz' for i in range(len(parts))]:raise ValueError('Noncontiguous checkpoint shards')
    shapes=[load_npz(p).shape for p in parts]
    if any(s[0]!=32 for s in shapes[:-1]) or len({s[1] for s in shapes})>1:raise ValueError('Inconsistent checkpoint shard shapes')
    completed=sum(s[0] for s in shapes)
    if completed>len(rows) or (completed<len(rows) and completed%32):raise ValueError('Incomplete checkpoint batch')
    old=pd.read_parquet(output/'fields_in_progress.parquet')
    ids=set(str(r.source_record_id) for r in rows[:completed])
    expected=len(ids)*len(half_times)*4
    if len(old)!=expected or set(old.source_record_id.astype(str))!=ids:raise ValueError('Field checkpoint does not match route shards')
    if old.duplicated(['source_record_id','kernel','half_time','include_self']).any():raise ValueError('Duplicate checkpoint field scenarios')
    if set(old.kernel)!=set(('exponential','gaussian')) or set(old.half_time)!=set(map(float,half_times)) or set(old.include_self)!=set((True,False)):raise ValueError('Checkpoint scenario contract changed')
    return completed,old


def run(reference_path,endpoints_path,regional_path,graph_dir,output,*,horizon=480.,workers=4,provider_catalog=None,half_times=HALF_TIMES,resume=False):
    from scipy.sparse import csr_matrix,save_npz,vstack
    from concurrent.futures import ThreadPoolExecutor
    output=Path(output)
    graph,reduced,mapping,sources,roster,dest=build_inputs(reference_path,endpoints_path,regional_path,graph_dir,output,horizon)
    (output/'cost_chunks').mkdir(exist_ok=True)
    if (output/'destination_costs.npz').exists() and not resume:raise ValueError('Completed matrix exists; use a new output folder or explicit --resume')
    if not resume:
        for stale in (output/'cost_chunks').glob('part_*.npz'):stale.unlink()
    all_fields=[];all_neighbours=[];all_physical=[];missing_physical=[];timings=[]
    rows=list(roster.loc[roster.accepted_source_endpoint].itertuples(index=False));provider=None;start=time.monotonic()
    completed=0
    if resume:
        completed,old=load_checkpoint(output,rows,half_times)
        all_fields=old.to_dict('records')
        missing_physical=[int(r.row_index) for r in rows[:completed]]
        print(json.dumps({'event':'resuming_completed_route_shards','completed_origins':completed}),flush=True)
    for begin in range(completed,len(rows),32):
        if provider is None and provider_catalog is not None and Path(provider_catalog).is_file():
            provider=physical_contract(provider_catalog,mapping)
            print(json.dumps({'event':'physical_catalogue_attached','families':len(provider),'after_origins':begin}),flush=True)
        batch=rows[begin:begin+32]
        def one(row):return scalar_origin_result(row,reduced,mapping,dest,sources,half_times,horizon,provider)
        with ThreadPoolExecutor(max_workers=workers) as executor:results=list(executor.map(one,batch))
        matrices=[]
        for row_index,indices,costs,fields,neighbors,physical,seconds in results:
            a=csr_matrix((costs,indices,np.array([0,len(costs)],dtype='int64')),shape=(1,len(dest)))
            matrices.append(a);all_fields.extend(fields);all_neighbours.extend(neighbors);all_physical.extend(physical);timings.append(seconds)
            if provider is None:missing_physical.append(row_index)
        save_npz(output/'cost_chunks'/f'part_{begin//32:03d}.npz',vstack(matrices,format='csr'),compressed=True)
        pd.DataFrame(all_fields).to_parquet(output/'fields_in_progress.parquet',index=False,compression='zstd')
        print(json.dumps({'event':'regional_progress','completed_origins':min(begin+32,len(rows)),'total_origins':len(rows),
            'elapsed_seconds':time.monotonic()-start,'mean_query_with_fields_seconds':float(np.mean(timings)),
            'stored_pairs_this_chunk':sum(a.nnz for a in matrices)}),flush=True)
    chunks=[__import__('scipy').sparse.load_npz(p) for p in sorted((output/'cost_chunks').glob('part_*.npz'))]
    routed=vstack(chunks,format='csr');del chunks
    # Reinsert all seven uncomputed roster rows as empty sparse rows. Their
    # explicit origin status distinguishes them from censored cost pairs.
    valid_rows=roster.loc[roster.accepted_source_endpoint,'row_index'].to_numpy('int32')
    coo=routed.tocoo();matrix=csr_matrix((coo.data,(valid_rows[coo.row],coo.col)),shape=(len(roster),len(dest)));del routed,coo
    matrix.sort_indices();save_npz(output/'destination_costs.npz',matrix,compressed=True)
    regional=np.full((len(roster),len(roster)),np.nan);dest_index=dict(zip(dest.source_record_id.astype(str),dest.destination_index))
    columns=np.array([dest_index.get(str(x),-1) for x in roster.source_record_id],dtype='int64');ok=columns>=0
    for row in valid_rows:regional[row,ok]=known_costs_from_sparse(matrix,int(row),columns[ok])
    np.save(output/'regional_costs.npy',regional)
    normalize_field_table(pd.DataFrame(all_fields),roster,half_times,horizon).to_parquet(output/'fields.parquet',index=False,compression='zstd')
    if resume and completed:
        # kNN recovery uses the stored exact route costs, including explicit zeros.
        ordinary=dest.ordinary_spatial_2021.eq(True).to_numpy();destination_ids=dest.source_record_id.astype(str).to_numpy()
        for row in rows[:completed]:
            a,b=matrix.indptr[int(row.row_index):int(row.row_index)+2];indices=matrix.indices[a:b];costs=matrix.data[a:b]
            allowed=ordinary[indices]&(destination_ids[indices]!=str(row.source_record_id))
            ids=indices[allowed];values=costs[allowed]
            if not len(ids):continue
            threshold=np.partition(values,min(6,len(ids))-1)[min(6,len(ids))-1]
            for j,t in sorted(zip(ids[values<=threshold+1e-10],values[values<=threshold+1e-10]),key=lambda x:(x[1],destination_ids[x[0]])):
                rank=int(1+(values<t-1e-10).sum())
                all_neighbours.append({'origin_id':str(row.source_record_id),'destination_id':destination_ids[j],
                    'minutes':float(t),'rank':rank,'in_k3':rank<=3,'in_k6':rank<=6,
                    'comparison_direction':'outgoing_national_k_nearest','destination_region':str(dest.iloc[j].region)})
    pd.DataFrame(all_neighbours).sort_values(['origin_id','rank','destination_id']).to_parquet(output/'national_neighbors.parquet',index=False,compression='zstd')
    if provider_catalog is not None:
        if provider is None:
            if not Path(provider_catalog).is_file():raise ValueError('Physical catalogue still unavailable after regional transport pass')
            provider=physical_contract(provider_catalog,mapping);missing_physical=list(valid_rows)
        from scipy.sparse.csgraph import dijkstra
        by_index={int(r.row_index):r for r in rows}
        def recover_physical(i):
            row=by_index[i]
            d=dijkstra(reduced,directed=True,indices=int(mapping[int(row.road_node_index)]),limit=horizon)
            return provider_rows(d,row,provider,horizon)
        for begin in range(0,len(missing_physical),32):
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for records in executor.map(recover_physical,missing_physical[begin:begin+32]):all_physical.extend(records)
            print(json.dumps({'event':'physical_candidates_recovered','completed':min(begin+32,len(missing_physical)),'total':len(missing_physical)}),flush=True)
        pd.DataFrame(all_physical).to_parquet(output/'physical_provider_candidates.parquet',index=False,compression='zstd')
    # One-hop national outgoing neighbours need their own field values. Their
    # forward union may be larger, but regional rows already remain exact.
    regional_ids=set(roster.source_record_id.astype(str));halo_ids=sorted(set(r['destination_id'] for r in all_neighbours)-regional_ids)
    halo=sources.set_index('source_record_id').loc[halo_ids].reset_index() if halo_ids else sources.iloc[:0].copy()
    halo['row_index']=np.arange(len(halo),dtype='int32');halo.to_parquet(output/'halo_roster.parquet',index=False,compression='zstd')
    halo_fields=[];halo_pairs=[]
    if len(halo):
        more=np.r_[roster.loc[roster.accepted_source_endpoint,'road_node_index'].to_numpy('int64'),halo.road_node_index.to_numpy('int64')]
        larger,_,new_mapping=forward_union(graph,more,horizon)
        for row in halo.itertuples(index=False):
            _,idx,data,fr,_,_,_=scalar_origin_result(row,larger,new_mapping,dest,sources,half_times,horizon,None)
            halo_fields.extend(fr);halo_pairs.append(csr_matrix((data,idx,np.array([0,len(data)],dtype='int64')),shape=(1,len(dest))))
        save_npz(output/'halo_destination_costs.npz',vstack(halo_pairs,format='csr'),compressed=True)
    normalize_field_table(pd.DataFrame(halo_fields),halo,half_times,horizon).to_parquet(output/'halo_fields.parquet',index=False,compression='zstd')
    summary={'schema':'sgrt.saratov.regional_fields.v1','direction':'origin_i_to_source_or_provider_j',
        'current_regional_records':len(roster),'computed_regional_origins':len(rows),'origins_without_endpoint':int((~roster.accepted_source_endpoint).sum()),
        'national_destination_records':len(dest),'stored_finite_cost_pairs':int(matrix.nnz),'halo_field_origins':len(halo),
        'half_times_minutes':list(half_times),'kernel_families':['exponential','gaussian'],'horizon_minutes':horizon,
        'graph_sha256':GRAPH_SHA256,'known_credited_mass':float(sources.loc[sources.positive_source_mass,'source_mass_2021'].sum()),
        'credited_mass_without_endpoint':float(sources.loc[sources.positive_source_mass&~sources.accepted_source_endpoint,'source_mass_2021'].sum()),
        'elapsed_regional_and_halo_seconds':time.monotonic()-start,'matrix_absent_is_never_zero':True,
        'self_zero_is_explicit_stored_entry_only_for_accepted_origin_endpoint':True,
        'field_is_potential_not_observed_flow':True,'hierarchy_or_service_catchments_inferred_by_this_module':False,
        'regional_roster_sha256':fingerprint(regional_path),'reference_sha256':fingerprint(reference_path),'endpoints_sha256':fingerprint(endpoints_path),
        'provider_catalog_sha256':fingerprint(provider_catalog) if provider_catalog is not None else None}
    write_json(output/'summary.json',summary);print(json.dumps({'event':'regional_fields_complete','summary':summary}),flush=True)
    return summary


def normalize_field_table(frame,roster,half_times=HALF_TIMES,horizon=480.):
    """Complete the explicit unknown frame and preserve self-envelope policy.

    The flag makes this operation idempotent. It also upgrades an in-progress
    table produced before reference-envelope self exclusion was introduced,
    without changing a single route or known potential value.
    """
    if frame.empty:
        return frame
    frame=frame.copy()
    respected=frame.get('published_envelope_respects_include_self',pd.Series(False,index=frame.index)).eq(True)
    source=roster.set_index('source_record_id')
    if source.index.duplicated().any():raise ValueError('Nonunique roster')
    raw=pd.to_numeric(frame.source_record_id.map(source.population_2021),errors='coerce')
    credible=frame.source_record_id.map(source.population_known_credited).eq(True)
    fix=(~respected)&frame.include_self.eq(False)&(~credible)&raw.gt(0)&np.isfinite(raw)
    frame.loc[fix,'omitted_published_reference_envelope']=(frame.loc[fix,'omitted_published_reference_envelope']-raw.loc[fix]).clip(lower=0.)
    frame['published_envelope_respects_include_self']=True
    present=set(frame.source_record_id.astype(str));unknown=[]
    for r in roster.itertuples(index=False):
        if str(r.source_record_id) in present:continue
        if bool(r.accepted_source_endpoint):raise ValueError('Missing computed accepted origin: '+str(r.source_record_id))
        for family in ('exponential','gaussian'):
            for h in half_times:
                for own in (True,False):
                    record={column:np.nan for column in frame.columns}
                    record.update(source_record_id=str(r.source_record_id),kernel=family,half_time=float(h),include_self=own,
                        status='origin_endpoint_unavailable',population_model_scope='accepted_additive_population_2021',
                        published_envelope_respects_include_self=True,computational_horizon_minutes=float(horizon),
                        speed_bound_kmh=130.,unmapped_distance_bound_is_conditional_on_same_maximum_speed=True,
                        own_credited_mass=float(r.source_mass_2021) if bool(r.positive_source_mass) else 0.)
                    unknown.append(record)
    if unknown:frame=pd.concat([frame,pd.DataFrame(unknown)],ignore_index=True)
    return frame.sort_values(['source_record_id','kernel','half_time','include_self']).reset_index(drop=True)


_CURRENT_PROVIDER_CONTEXT=None

def _initialize_current_provider_worker(graph,mapping,roster,contract,pairs,horizon):
    global _CURRENT_PROVIDER_CONTEXT
    _CURRENT_PROVIDER_CONTEXT=(graph,mapping,roster,contract,pairs,horizon)


def _current_provider_origin(origin):
    from scipy.sparse.csgraph import dijkstra
    graph,mapping,roster,contract,pairs,horizon=_CURRENT_PROVIDER_CONTEXT
    row=next(roster.loc[[origin]].itertuples(index=False))
    distance=dijkstra(graph,directed=True,indices=int(mapping[int(row.road_node_index)]),limit=horizon)
    return [r for r in provider_rows(distance,row,contract,horizon)
            if (str(r['origin_id']),str(r['family'])) in pairs]


def current_provider_candidates(output,provider_catalog,workers=4):
    """Re-evaluate TOP3 only where historical records could displace current ones.

    If every baseline TOP3 record is nonhistorical, it is already the exact
    TOP3 over the nonhistorical subset. Otherwise routing is repeated for the
    affected origin/family. Filtering baseline TOP3 alone is never sufficient.
    """
    from scipy.sparse import load_npz
    from scipy.sparse.csgraph import dijkstra
    from concurrent.futures import ThreadPoolExecutor
    output=Path(output);baseline=pd.read_parquet(output/'physical_provider_candidates.parquet')
    catalog=pd.read_parquet(provider_catalog)
    historical=catalog.loc[catalog.historical_only.eq(True),['family','catalog_id']].drop_duplicates()
    tagged=baseline.merge(historical.assign(_historical=True),on=['family','catalog_id'],how='left',validate='many_to_one')
    affected=tagged.loc[tagged._historical.eq(True),['origin_id','family']].drop_duplicates()
    pairs=set(map(tuple,affected.to_numpy()))
    retain=np.array([(str(a),str(b)) not in pairs for a,b in zip(tagged.origin_id,tagged.family)])
    kept=baseline.loc[retain].to_dict('records');recomputed=[]
    affected_ids=sorted(set(affected.origin_id.astype(str)))
    if affected_ids:
        graph=load_npz(output/'reduced_graph.npz');axis=np.load(output/'road_node_axis.npy')
        mapping=np.full(int(axis.max())+1,-1,dtype='int32');mapping[axis]=np.arange(len(axis),dtype='int32')
        # physical_contract expects the complete national vertex axis, while
        # vertices outside the union must remain -1.
        maximum=int(pd.to_numeric(catalog.road_node_index,errors='coerce').max())
        if maximum>=len(mapping):mapping=np.pad(mapping,(0,maximum+1-len(mapping)),constant_values=-1)
        contract=physical_contract(provider_catalog,mapping)
        current=[]
        for family,providers,groups,codes in contract:
            if family not in set(affected.family):continue
            selected=providers.loc[~providers.historical_only.eq(True)].reset_index(drop=True)
            groups,codes=np.unique(selected.destination_group_key.astype(str),return_inverse=True)
            current.append((family,selected,groups,codes.astype('int32')))
        roster=pd.read_parquet(output/'regional_roster.parquet').set_index('source_record_id',drop=False)
        scope=output/'summary.json'
        if not scope.is_file():scope=output/'graph_summary.json'
        horizon=float(json.loads(scope.read_text())['horizon_minutes'])
        arguments=(graph,mapping,roster,current,pairs,horizon)
        def consume(results):
            for i,records in enumerate(results,1):
                recomputed.extend(records)
                if i%32==0 or i==len(affected_ids):
                    print(json.dumps({'event':'nonhistorical_provider_recovery','completed':i,'total':len(affected_ids)}),flush=True)
        import multiprocessing
        if workers>1 and 'fork' in multiprocessing.get_all_start_methods():
            # SciPy's graph search can retain the GIL. Linux fork workers share
            # the immutable CSR and provider arrays; each origin is independent.
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('fork'),
                    initializer=_initialize_current_provider_worker,initargs=arguments) as executor:
                consume(executor.map(_current_provider_origin,affected_ids,chunksize=1))
        elif workers>1:
            # Portable numerical fallback; slower where graph search holds GIL.
            _initialize_current_provider_worker(*arguments)
            with ThreadPoolExecutor(max_workers=workers) as executor:
                consume(executor.map(_current_provider_origin,affected_ids))
        else:
            _initialize_current_provider_worker(*arguments)
            consume(map(_current_provider_origin,affected_ids))
    result=pd.DataFrame(kept+recomputed,columns=baseline.columns).sort_values(['origin_id','family','rank','destination_group_key']).reset_index(drop=True)
    result.to_parquet(output/'physical_provider_candidates_current.parquet',index=False,compression='zstd')
    facts={'schema':'sgrt.saratov.nonhistorical_nearest_sensitivity.v1','historical_source_rows':len(historical),
        'recomputed_origins':len(affected_ids),'recomputed_origin_family_pairs':len(pairs),
        'current_candidate_rows':len(result),'current_means_nonhistorical_source_not_verified_operation':True,
        'method':'Baseline TOP3 reused only when all selected offers are nonhistorical. Affected origin/family pairs recomputed against the entire nonhistorical provider subset on the same directed graph.'}
    write_json(output/'current_provider_summary.json',facts);return facts


def finalize_existing(output):
    """Finish a completed older field table with the current explicit schema."""
    output=Path(output);summary=json.loads((output/'summary.json').read_text())
    for prefix in ('','halo_'):
        p=output/(prefix+'fields.parquet');r=output/(prefix+'roster.parquet')
        if prefix=='':r=output/'regional_roster.parquet'
        frame=normalize_field_table(pd.read_parquet(p),pd.read_parquet(r),summary['half_times_minutes'],summary['horizon_minutes'])
        frame.to_parquet(p,index=False,compression='zstd')
    summary['explicit_unknown_origin_field_rows']=int((pd.read_parquet(output/'fields.parquet').status=='origin_endpoint_unavailable').sum())
    summary['field_table_policy']='known mass and omitted-published envelope both respect include_self; missing endpoints have explicit unknown scenario rows'
    write_json(output/'summary.json',summary)

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--reference',type=Path,required=True);p.add_argument('--endpoints',type=Path,required=True)
    p.add_argument('--regional-roster',type=Path,required=True);p.add_argument('--graph-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--horizon',type=float,default=480.)
    p.add_argument('--current-provider-only',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--finalize-existing',action='store_true');p.add_argument('--prepare-only',action='store_true');p.add_argument('--workers',type=int,default=4);p.add_argument('--provider-catalog',type=Path);p.add_argument('--half-times',type=float,nargs='+',default=list(HALF_TIMES))
    a=p.parse_args()
    if a.current_provider_only:current_provider_candidates(a.output,a.provider_catalog,a.workers)
    elif a.finalize_existing:finalize_existing(a.output)
    elif a.prepare_only:build_inputs(a.reference,a.endpoints,a.regional_roster,a.graph_dir,a.output,a.horizon)
    else:run(a.reference,a.endpoints,a.regional_roster,a.graph_dir,a.output,horizon=a.horizon,workers=a.workers,provider_catalog=a.provider_catalog,half_times=a.half_times,resume=a.resume)

if __name__=='__main__':main()
