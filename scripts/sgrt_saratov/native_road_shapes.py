"""Recover source-way shapes and their own costs, not compressed-node chords."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import shapely


def spherical_lengths(lat,lon):
    lat,lon=np.radians(lat),np.radians(lon)
    a=np.sin(np.diff(lat)/2)**2+np.cos(lat[:-1])*np.cos(lat[1:])*np.sin(np.diff(lon)/2)**2
    return 12742.0176*np.arcsin(np.sqrt(np.clip(a,0,1)))


def osm_axis(directory,node_count):
    result=np.full(node_count,-1,dtype='int64')
    for p in sorted(Path(directory).glob('part_*.parquet')):
        d=pd.read_parquet(p,columns=['node_index','osm_id'])
        result[d.node_index.to_numpy(dtype='int64')]=d.osm_id.to_numpy(dtype='int64')
    if (result<0).any() or not np.all(np.diff(result)>0):
        raise ValueError('Expected complete sorted source OSM-node axis')
    return result


def arc_cost(graph,u,v):
    begin,end=graph.indptr[u:u+2]
    position=int(np.searchsorted(graph.indices[begin:end],v))+int(begin)
    if position>=end or graph.indices[position]!=v:return None
    return float(graph.data[position])


def build_native_edges(ways_path,nodes_path,axis,graph,needed,project,graph_lat=None,graph_lon=None):
    """Reproduce per-way compression while preserving curves and parallel roads."""
    ways=pd.read_parquet(ways_path);nodes=pd.read_parquet(nodes_path)
    idcol='osm_id' if 'osm_id' in nodes else 'id'
    if nodes[idcol].duplicated().any():raise ValueError('Duplicate source vertex identity')
    location={int(r[0]):(float(r[1]),float(r[2])) for r in nodes[[idcol,'lat','lon']].itertuples(index=False,name=None)}
    needed=set(map(int,needed));records=[];table=[];matched={};slower=0;endpoint_error=0.
    for row in ways.itertuples(index=False):
        refs=np.asarray(row.refs,dtype='int64')
        index=np.searchsorted(axis,refs);valid=index<len(axis)
        valid[valid]&=axis[index[valid]]==refs[valid]
        cuts=np.flatnonzero(valid)
        if len(cuts)<2:continue
        if cuts[0]!=0 or cuts[-1]!=len(refs)-1:
            raise ValueError('Source-way ends do not match archived graph')
        try:raw=np.asarray([location[int(x)] for x in refs],dtype=float)
        except KeyError as e:raise ValueError('Original way lacks source vertex coordinates') from e
        lat,lon=raw[:,0],raw[:,1]
        lengths=np.r_[0.,np.cumsum(spherical_lengths(lat,lon))]
        speed=float(row.speed_kmh);oneway=int(row.oneway)
        if not np.isfinite(speed) or speed<=0 or oneway not in {-1,0,1}:raise ValueError('Invalid source-way profile')
        for a,z in zip(cuts[:-1],cuts[1:]):
            u,v=int(index[a]),int(index[z])
            if u not in needed and v not in needed:continue
            if graph_lat is not None and graph_lon is not None:
                error=max(abs(lat[a]-graph_lat[u]),abs(lon[a]-graph_lon[u]),
                          abs(lat[z]-graph_lat[v]),abs(lon[z]-graph_lon[v]))
                endpoint_error=max(endpoint_error,float(error))
                if error>1e-7:raise ValueError('Source endpoints differ from pinned graph coordinates')
            length=float(lengths[z]-lengths[a]);cost=length/speed*60.
            directions=[]
            if oneway>=0:directions.append((u,v))
            if oneway<=0:directions.append((v,u))
            for origin,destination in directions:
                expected=arc_cost(graph,origin,destination)
                if expected is None:raise ValueError(f'Native edge absent from graph: way={row.way_id},u={origin},v={destination}')
                if cost<expected-1e-7:raise ValueError(f'Native edge faster than pinned CSR: way={row.way_id},{cost},{expected}')
                if destination in needed:
                    key=(origin,destination);matched[key]=min(matched.get(key,float('inf')),cost)
                    slower+=int(cost>expected+1e-7)
            segment=np.column_stack([lon[a:z+1],lat[a:z+1]])
            xy=np.column_stack(project.transform(segment[:,0],segment[:,1]))
            records.append({'u':u,'v':v,'w':cost,'oneway':oneway,'xy':xy,
                            'lengths':lengths[a:z+1]-lengths[a],'way_id':int(row.way_id)})
            table.append({'u':u,'v':v,'u_osm':int(refs[a]),'v_osm':int(refs[z]),
                'way_id':int(row.way_id),'oneway':oneway,'native_length_km':length,'edge_minutes':cost,
                'speed_kmh':speed,'geometry_crs':'EPSG:4326','source_polyline_vertices':int(z-a+1),
                'native_geometry_wkb':shapely.to_wkb(shapely.LineString(segment))})
    reverse=graph.T.tocsr();missing=[];disagreements=[]
    for v in sorted(needed):
        begin,end=reverse.indptr[v:v+2]
        for u,cost in zip(reverse.indices[begin:end],reverse.data[begin:end]):
            key=(int(u),v)
            if key not in matched:missing.append(key)
            elif abs(matched[key]-float(cost))>1e-7:disagreements.append(key)
    if missing or disagreements:
        raise ValueError(f'Native geometry does not reconstruct relevant min-CSR arcs: missing={len(missing)},cost={len(disagreements)};examples={missing[:3]}')
    if not records:raise ValueError('No original source geometry recovered')
    return records,pd.DataFrame(table),{'native_segments':len(records),
        'reconstructed_directed_minimum_arcs':len(matched),'slower_parallel_directed_segments_retained':slower,
        'native_vertices':sum(len(x['xy']) for x in records),
        'endpoint_coordinate_check_performed':graph_lat is not None and graph_lon is not None,
        'maximum_endpoint_coordinate_difference_degrees':endpoint_error,
        'missing_minimum_arcs':len(missing),'minimum_arc_cost_disagreements':len(disagreements)}


def suffix_piece(xy,cumulative,fraction):
    """Cut by original spherical path length, preserving bends."""
    if fraction<=0:return None
    if fraction>=1:return xy
    total=float(cumulative[-1])
    if total<=0:return None
    target=(1.-fraction)*total
    i=min(int(np.searchsorted(cumulative,target,side='right'))-1,len(xy)-2)
    denominator=cumulative[i+1]-cumulative[i]
    if denominator<=0:raise ValueError('Non-increasing native interpolation')
    alpha=(target-cumulative[i])/denominator
    return np.vstack([xy[i]+alpha*(xy[i+1]-xy[i]),xy[i+1:]])


def native_reachable_lines(records,arrival,minutes):
    parts=[];full=0;partial=0;length=0.
    for row in records:
        w=row['w'];u=row['u'];v=row['v']
        def fraction(destination):
            residual=minutes-arrival[destination]
            return (1. if residual>=0 else 0.) if w==0 else float(np.clip(residual/w,0,1))
        f=fraction(v) if row['oneway']>=0 else 0.;r=fraction(u) if row['oneway']<=0 else 0.
        if max(f,r)>=1:pieces=[row['xy']];full+=1
        else:
            pieces=[]
            if f>0:pieces.append(suffix_piece(row['xy'],row['lengths'],f));partial+=1
            if r>0:pieces.append(suffix_piece(row['xy'][::-1],row['lengths'][-1]-row['lengths'][::-1],r));partial+=1
        for coords in pieces:
            if coords is not None and len(coords)>=2:
                segment=shapely.LineString(coords)
                if segment.length>1e-7:parts.append(segment);length+=segment.length
    return shapely.line_merge(shapely.multilinestrings(parts)),{
        'native_full_segments':full,'native_partial_pieces':partial,'nonzero_shapes':len(parts),
        'drawn_length_m':float(length),'native_polyline_geometry':True}
