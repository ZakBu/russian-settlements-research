"""Trace documented rural school counterexamples without calibrating road speeds.

Original graph costs are model values. A repeated shortest path confirms
arithmetic, not the completeness of roads or the journey of a school bus.
"""
from __future__ import annotations
import argparse,hashlib,heapq,json,math
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.sgrt_saratov.regional_independent_checks import original_graph

PAIRS=[('117729','117728'),('117730','117728'),('117734','117733')]
SOURCE_EXCERPT=Path(__file__).resolve().parents[2]/'references/primary/saratov_rural_roads_2021'

def read_table(path,columns=None):
    path=Path(path)
    if path.suffix=='.json':
        payload=json.loads(path.read_text());frame=pd.DataFrame(payload['records'],columns=payload['columns'])
        return frame[columns] if columns is not None else frame
    return pd.read_parquet(path,columns=columns)

def verify_excerpt(folder):
    folder=Path(folder);manifest=folder/'manifest.json'
    if not manifest.exists():return
    data=json.loads(manifest.read_text())
    for name,spec in data['files'].items():
        path=folder/name
        if path.stat().st_size!=spec['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=spec['sha256']:
            raise ValueError('Frozen original-source excerpt differs: '+name)



def path_heap(graph,origin,destination):
    queue=[(0.,int(origin))];best={int(origin):0.};previous={};popped=0
    while queue:
        cost,u=heapq.heappop(queue)
        if cost!=best[u]:continue
        popped+=1
        if u==destination:
            path=[u]
            while path[-1]!=origin:path.append(previous[path[-1]])
            return cost,list(reversed(path)),popped
        for at in range(int(graph.indptr[u]),int(graph.indptr[u+1])):
            v,w=int(graph.indices[at]),float(graph.data[at]);proposed=cost+w
            if w<0 or not math.isfinite(w):raise ValueError('Invalid graph edge')
            if proposed<best.get(v,math.inf):
                best[v]=proposed;previous[v]=u;heapq.heappush(queue,(proposed,v))
    raise ValueError('Documented control has no path in frozen graph')


def sphere_distance(a,b):
    p1,p2=map(math.radians,(a[1],b[1]));delta_p=p2-p1;delta_l=math.radians(b[0]-a[0])
    h=math.sin(delta_p/2)**2+math.cos(p1)*math.cos(p2)*math.sin(delta_l/2)**2
    return 6371.0088*2*math.asin(math.sqrt(min(1.,max(0.,h))))


def run(roster_path,graph_dir,road_nodes,output,native_sources=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    roster=pd.read_parquet(roster_path)
    by_suffix={str(r.source_record_id).rsplit(':',1)[-1]:r for r in roster.itertuples(index=False)}
    graph=original_graph(graph_dir);traces=[];wanted=set()
    for a,b in PAIRS:
        origin,target=by_suffix[a],by_suffix[b]
        cost,path,popped=path_heap(graph,int(origin.road_node_index),int(target.road_node_index))
        traces.append((origin,target,cost,path,popped));wanted.update(path)
    columns=['node_index','osm_id','lat','lon'];frames=[]
    node_source=Path(road_nodes)
    parts=[node_source] if node_source.is_file() else sorted(node_source.glob('part_*.parquet'))
    for part in parts:
        d=read_table(part,columns=columns);frames.append(d[d.node_index.isin(wanted)])
    nodes=pd.concat(frames,ignore_index=True).drop_duplicates('node_index').set_index('node_index')
    if set(nodes.index)!=wanted:raise ValueError('Missing original road vertex coordinates')
    rows=[];features=[];edge_rows=[]
    for origin,target,cost,path,popped in traces:
        coordinates=[[float(nodes.loc[u,'lon']),float(nodes.loc[u,'lat'])] for u in path]
        lower=math.fsum(sphere_distance(a,b) for a,b in zip(coordinates[:-1],coordinates[1:]))
        direct=sphere_distance([float(origin.lon),float(origin.lat)],[float(target.lon),float(target.lat)])
        connector=4.*(float(origin.snap_km)+float(target.snap_km))
        identity=str(origin.source_record_id)+'|'+str(target.source_record_id)
        for k,(u,v) in enumerate(zip(path[:-1],path[1:])):
            ix=range(int(graph.indptr[u]),int(graph.indptr[u+1]));weights=[float(graph.data[z]) for z in ix if int(graph.indices[z])==v]
            edge_rows.append({'route_id':identity,'edge_order':k,'u':u,'v':v,
                'u_osm':int(nodes.loc[u,'osm_id']),'v_osm':int(nodes.loc[v,'osm_id']),
                'u_lon':coordinates[k][0],'u_lat':coordinates[k][1],
                'v_lon':coordinates[k+1][0],'v_lat':coordinates[k+1][1],
                'edge_minutes':min(weights),'endpoint_chord_km_lower_bound':sphere_distance(coordinates[k],coordinates[k+1])})
        row={'origin_id':str(origin.source_record_id),'destination_id':str(target.source_record_id),
            'origin_name':str(origin.name),'destination_name':str(target.name),
            'origin_published_population_2021':float(origin.population_2021),
            'destination_published_population_2021':float(target.population_2021),
            'origin_population_2021_additive_credit':bool(origin.credit_2021),
            'observed_current_pupil_count':None,
            'direct_great_circle_km':direct,'network_minutes':cost,'connector_minutes':connector,
            'model_total_minutes':cost+connector,'compressed_path_vertices':len(path),
            'compressed_chord_length_km_lower_bound':lower,'chord_detour_ratio_lower_bound':lower/direct,
            'origin_snap_km':float(origin.snap_km),'destination_snap_km':float(target.snap_km),
            'heap_vertices_popped':popped,'observed_school_bus_travel_time':None,
            'transport_model_reliability_flag':'documented_campus_assignment_with_large_modelled_road_detour_requires_source_road_audit',
            'route_is_verified_actual_journey':False,'chord_geometry_is_original_road_shape':False}
        rows.append(row);features.append({'type':'Feature','properties':row,'geometry':{'type':'LineString','coordinates':coordinates}})
    edge_frame=pd.DataFrame(edge_rows)
    edge_frame.to_parquet(output/'rural_school_counterexample_path_edges.parquet',index=False,compression='zstd')
    nodes.reset_index().to_parquet(output/'rural_school_counterexample_road_vertices.parquet',index=False,compression='zstd')
    report={'schema':'sgrt.saratov.rural_school_transport_counterexamples.v1','routes':rows,
        'interpretation':'Exact frozen-graph route reconstruction plus original graph-node coordinates. Chord length is only a lower bound; speed/profile and missing-road explanations need the original OSM ways and independent road/school-bus evidence.'}
    (output/'rural_school_transport_counterexamples.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'rural_school_counterexample_graph_paths.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=False)+'\n')
    if native_sources is not None:
        report=attach_native_profiles(output,Path(native_sources))
    print(json.dumps(report,ensure_ascii=False),flush=True)


def attach_native_profiles(output,native_sources):
    """Reconcile every traced CSR arc with the original source-way polyline."""
    output=Path(output);native_sources=Path(native_sources)
    verify_excerpt(native_sources)
    ways=read_table(native_sources/('ways.json' if (native_sources/'ways.json').exists() else 'ways.parquet'))
    nodes=read_table(native_sources/('nodes.json' if (native_sources/'nodes.json').exists() else 'nodes.parquet'))
    location={int(r.osm_id):(float(r.lon),float(r.lat)) for r in nodes.itertuples(index=False)}
    edges=pd.read_parquet(output/'rural_school_counterexample_path_edges.parquet')
    report=json.loads((output/'rural_school_transport_counterexamples.json').read_text())
    way_rows=[];by_osm={}
    for row in ways.itertuples(index=False):
        refs=list(map(int,row.refs));tags=json.loads(row.source_tags_json)
        item=(row,refs,tags);way_rows.append(item)
        for ref in set(refs):by_osm.setdefault(ref,[]).append(item)
    matched=[];native_features=[];route_points={}
    for edge in edges.itertuples(index=False):
        options=[]
        for row,refs,tags in by_osm.get(int(edge.u_osm),[]):
            if int(edge.v_osm) not in refs:continue
            starts=[i for i,ref in enumerate(refs) if ref==int(edge.u_osm)]
            ends=[i for i,ref in enumerate(refs) if ref==int(edge.v_osm)]
            for start in starts:
                for end in ends:
                    if start==end or (row.oneway==1 and start>end) or (row.oneway==-1 and start<end):continue
                    chosen=refs[start:end+1] if start<end else list(reversed(refs[end:start+1]))
                    coords=[location[r] for r in chosen]
                    length=math.fsum(sphere_distance(a,b) for a,b in zip(coords[:-1],coords[1:]))
                    model_cost=length/float(row.speed_kmh)*60.
                    if abs(model_cost-float(edge.edge_minutes))<=1e-7:
                        options.append((int(row.way_id),length,model_cost,coords,row,tags))
        if not options:raise ValueError('Original source way cannot explain traced minimum-cost CSR arc '+str((edge.u,edge.v)))
        way,length,cost,coords,row,tags=min(options,key=lambda x:x[0])
        matched.append({'route_id':edge.route_id,'edge_order':int(edge.edge_order),'way_id':way,
            'native_length_km':length,'source_profile_speed_kmh':float(row.speed_kmh),
            'source_profile_minutes':cost,'original_graph_minutes':float(edge.edge_minutes),
            'highway':str(row.highway),'surface':tags.get('surface','unspecified'),
            'maxspeed':tags.get('maxspeed','unspecified'),'source_tags_json':row.source_tags_json,
            'source_timestamp':str(row.source_timestamp),'source_way_version':int(row.osm_version),
            'observed_speed_or_duration':False})
        points=route_points.setdefault(edge.route_id,[])
        points.extend(coords if not points else coords[1:])
    matched=pd.DataFrame(matched)
    matched.to_parquet(output/'rural_school_native_profile_edges.parquet',index=False,compression='zstd')
    profiles=[]
    for record in report['routes']:
        identity=record['origin_id']+'|'+record['destination_id'];group=matched[matched.route_id.eq(identity)]
        record['native_road_length_km']=math.fsum(group.native_length_km)
        record['native_detour_ratio']=record['native_road_length_km']/record['direct_great_circle_km']
        record['profile_implied_mean_road_speed_kmh_not_observed']=record['native_road_length_km']/record['network_minutes']*60.
        record['all_traced_arcs_reconciled_with_original_osm_ways']=True
        record['source_way_count']=group.way_id.nunique()
        classes=[]
        for (highway,surface),part in group.groupby(['highway','surface'],sort=True):
            classes.append({'highway':highway,'surface':surface,'native_length_km':math.fsum(part.native_length_km),
                'profile_minutes':math.fsum(part.source_profile_minutes),'profile_speeds_kmh':sorted(part.source_profile_speed_kmh.unique().tolist())})
        record['profile_components']=classes
        native_features.append({'type':'Feature','properties':record,'geometry':{'type':'LineString','coordinates':route_points[identity]}})
    report['interpretation']='Every traced frozen-graph arc is reconciled with original 2021 OSM-way geometry and its static public-car speed profile. Reproduction proves source/profile arithmetic, not observed bus travel, current road condition or completeness of alternative roads.'
    report['maximum_native_arc_cost_difference_minutes']=float((matched.source_profile_minutes-matched.original_graph_minutes).abs().max())
    (output/'rural_school_transport_counterexamples.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (output/'rural_school_counterexample_native_paths.geojson').write_text(json.dumps({'type':'FeatureCollection','features':native_features},ensure_ascii=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['roster','graph-dir','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--road-nodes',type=Path,default=SOURCE_EXCERPT/'graph_vertex_subset.json')
    p.add_argument('--native-sources',type=Path,default=SOURCE_EXCERPT)
    p.add_argument('--attach-native-only',action='store_true')
    a=p.parse_args()
    if a.attach_native_only: print(json.dumps(attach_native_profiles(a.output,a.native_sources),ensure_ascii=False))
    else:run(a.roster,a.graph_dir,a.road_nodes,a.output,a.native_sources)
