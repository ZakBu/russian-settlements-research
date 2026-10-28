"""Inbound network isochrones, displayed as explicitly bounded road corridors.

Every route search uses the full directed national graph. Polygon buffers are
cartographic approximations of reachable roads, not evidence that every place
inside a buffer can reach the centre within the stated budget.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer
import shapely
from shapely.geometry import mapping
from shapely.ops import transform

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.routes import load_graph, GRAPH_SHA256
from scripts.sgrt_saratov.native_road_shapes import osm_axis,build_native_edges,native_reachable_lines

CRS = 'EPSG:32638'
THRESHOLDS = (10., 20., 30., 60.)
WIDTHS = (100., 250.)
ROAD_PREFIX = 'research/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/road_nodes/'
SLUGS = {'118372':'saratov', '118308':'engels', '116499':'balakovo',
         '116550':'balashov', '117415':'novouzensk', '117733':'piterka'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def partial_fraction(minutes, destination_cost, edge_cost):
    """Accessible fraction measured from v towards u on ORIGINAL u->v.

    d(v) already includes the destination's connector. An alternative route
    making d(u) small does not make the whole u->v edge accessible.
    """
    if not np.isfinite(minutes) or minutes < 0:
        raise ValueError('Require a finite nonnegative time budget')
    destination_cost = np.asarray(destination_cost, dtype=float)
    edge_cost = np.asarray(edge_cost, dtype=float)
    if np.any(~np.isfinite(edge_cost)) or np.any(edge_cost < 0):
        raise ValueError('Require finite nonnegative edge costs')
    residual = minutes-destination_cost
    ratio = np.divide(residual, edge_cost, out=np.zeros_like(residual), where=edge_cost>0)
    ratio = np.where((edge_cost == 0) & (residual >= 0), 1., ratio)
    return np.clip(ratio, 0., 1.)


def inbound_arc_arrays(reverse, arrival, maximum):
    """Extract original u->v arcs whose destination v is within the budget."""
    destinations = np.flatnonzero(np.isfinite(arrival) & (arrival <= maximum))
    counts = np.diff(reverse.indptr)[destinations].astype('int64')
    starts = reverse.indptr[destinations].astype('int64')
    count = int(counts.sum())
    offsets = np.cumsum(counts)-counts
    positions = np.arange(count, dtype='int64') + np.repeat(starts-offsets, counts)
    v = np.repeat(destinations, counts)
    return reverse.indices[positions].astype('int64'), v, reverse.data[positions]


def reachable_lines(u, v, weight, arrival, x, y, minutes, node_count):
    """Deduplicate full undirected shapes; keep both distinct partial pieces."""
    fractions = partial_fraction(minutes, arrival[v], weight)
    keep = fractions > 0
    u, v, fractions = u[keep], v[keep], fractions[keep]
    lo, hi = np.minimum(u,v), np.maximum(u,v)
    keys = lo.astype('int64')*int(node_count)+hi
    full = fractions >= 1
    full_keys, first = np.unique(keys[full], return_index=True)
    full_u, full_v = u[full][first], v[full][first]
    # A complete accessible edge already contains either partial copy.
    partial = (~full) & ~np.isin(keys, full_keys)
    a = np.column_stack([x[full_u], y[full_u]])
    b = np.column_stack([x[full_v], y[full_v]])
    pu, pv, pf = u[partial], v[partial], fractions[partial]
    start = np.column_stack([x[pv],y[pv]])
    end = start + pf[:,None]*(np.column_stack([x[pu],y[pu]])-start)
    a = np.concatenate([a,start]); b = np.concatenate([b,end])
    lengths = np.hypot(*(b-a).T)
    nonzero = lengths > 1e-7
    pieces = shapely.linestrings(np.stack([a[nonzero], b[nonzero]], axis=1))
    geometry = shapely.line_merge(shapely.multilinestrings(pieces))
    return geometry, {'directed_arc_parts':int(keep.sum()),
                      'deduplicated_full_shapes':len(full_keys),
                      'retained_partial_shapes':int(partial.sum()),
                      'nonzero_shapes':int(nonzero.sum()),
                      'drawn_length_m':float(lengths[nonzero].sum())}


def coordinates(directory, node_count, catalog_path):
    """Read existing immutable node coordinates without copying 190 MB."""
    catalog = json.loads(Path(catalog_path).read_text())
    pinned = {r['path']:catalog['objects'][r['blob']]
              for r in catalog['files'] if r['path'].startswith(ROAD_PREFIX)}
    lat=np.full(node_count,np.nan);lon=np.full(node_count,np.nan)
    seen=np.zeros(node_count,dtype=bool);proof=[]
    files=sorted(Path(directory).glob('part_*.parquet'))
    if len(files)!=len(pinned):raise ValueError('Road coordinate part inventory differs')
    for path in files:
        logical=ROAD_PREFIX+path.name; spec=pinned[logical]
        if path.stat().st_size!=spec['bytes'] or sha(path)!=spec['sha256']:
            raise ValueError('Road coordinates differ from public catalogue: '+logical)
        frame=pd.read_parquet(path,columns=['node_index','lat','lon'])
        ids=frame.node_index.to_numpy(dtype='int64')
        if (ids<0).any() or (ids>=node_count).any() or seen[ids].any() or len(np.unique(ids))!=len(ids):
            raise ValueError('Duplicate/out-of-range road node identity')
        lat[ids]=frame.lat;lon[ids]=frame.lon;seen[ids]=True
        proof.append({'path':logical,'bytes':spec['bytes'],'sha256':spec['sha256']})
    if not seen.all() or not np.isfinite(lat).all() or not np.isfinite(lon).all():
        raise ValueError('National graph lacks complete coordinate identity')
    return lat,lon,proof


def nested_geographies(raw_lines, previous, widths, simplify_m, to_wgs):
    """Return delivered WGS84 cumulative shapes and their exact differences."""
    geographies={};bands={};stats={}
    for width in widths:
        # Cascaded union avoids the quadratic memory use of a monolithic
        # MultiLineString buffer on a dense city network. Buffer distributes
        # over the union; the cartographic operation is unchanged.
        parts=shapely.get_parts(raw_lines)
        poly=shapely.union_all(shapely.buffer(parts,width,quad_segs=2)).simplify(simplify_m,preserve_topology=True)
        # Quantize the base contour, then do final overlays at full precision.
        # Re-snapping newly created intersections can introduce tiny slivers.
        poly=shapely.set_precision(shapely.set_precision(transform(to_wgs.transform,poly),1e-7),0)
        if width in previous:
            poly=shapely.union(poly,previous[width])
            band=shapely.difference(poly,previous[width])
        else:band=poly
        if poly.is_empty or not poly.is_valid or poly.geom_type not in {'Polygon','MultiPolygon'}:
            raise ValueError('Invalid or empty isochrone polygon')
        geographies[width]=poly;bands[width]=band
        stats[width]={'cumulative_vertices':int(shapely.get_num_coordinates(poly)),
                      'band_vertices':int(shapely.get_num_coordinates(band))}
    return geographies,bands,stats


def feature(geometry, properties):
    # Preserve exact overlay intersections. Re-rounding them would break the
    # literal nesting/disjointness of the delivered polygon sets.
    geo=mapping(geometry)
    return {'type':'Feature','geometry':geo,'properties':properties}


def write_geojson(path, features):
    Path(path).write_text(json.dumps({'type':'FeatureCollection','features':features},
        ensure_ascii=False,separators=(',',':'))+'\n')


def run(centres_path,settlements_path,graph_dir,road_nodes,output,*,
        thresholds=THRESHOLDS,widths=WIDTHS,display_width=250.,simplify_m=20.,catalog_path=None,
        native_ways=None,native_nodes=None,routes_only=False,geometry_only=False,allow_chord_diagnostic=False):
    from scipy.sparse.csgraph import dijkstra
    thresholds=sorted(set(map(float,thresholds))); widths=sorted(set(map(float,widths)))
    if not thresholds or min(thresholds)<=0 or display_width not in widths or min(widths)<=0 or simplify_m<0:
        raise ValueError('Invalid time or cartographic parameters')
    if routes_only and geometry_only:raise ValueError('Choose only one phase')
    if (native_ways or native_nodes) and not geometry_only:
        raise ValueError('Native drawing requires --geometry-only after a saved --routes-only phase')
    if not routes_only and not(native_ways and native_nodes) and not allow_chord_diagnostic:
        raise ValueError('Original source-way geometry is required; chords are diagnostic only')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    centres=pd.read_csv(centres_path); settlements=pd.read_parquet(settlements_path)
    if centres.source_record_id.duplicated().any() or settlements.source_record_id.duplicated().any():
        raise ValueError('Non-unique settlement identity')
    graph=load_graph(graph_dir); reverse=graph.T.tocsr(); n=graph.shape[0]
    lat,lon,coordinate_proof=coordinates(road_nodes,n,catalog_path or REPO/'data/catalog.json')
    projected_x=np.full(n,np.nan);projected_y=np.full(n,np.nan)
    forward=Transformer.from_crs('EPSG:4326',CRS,always_xy=True)
    backward=Transformer.from_crs(CRS,'EPSG:4326',always_xy=True)
    axis=osm_axis(road_nodes,n)
    route_contract={'graph_sha256':GRAPH_SHA256,'centres_sha256':sha(centres_path),
        'settlements_sha256':sha(settlements_path),'stored_road_arrival_maximum_minutes':max(thresholds)}
    saved_arrivals=None;native_records=None;native_facts={}
    if geometry_only:
        existing=json.loads((output/'route_phase.json').read_text())
        if existing!=route_contract:raise ValueError('Saved route phase differs from current exact inputs')
        saved_arrivals=pd.read_parquet(output/'road_arrivals.parquet')
    if native_ways and native_nodes:
        if saved_arrivals is None:
            needed=pd.read_parquet(output/'needed_road_vertices.parquet').node_index.to_numpy(dtype='int64')
        else:needed=saved_arrivals.node_index.unique()
        native_records,native_table,native_facts=build_native_edges(native_ways,native_nodes,axis,graph,needed,forward,lat,lon)
        native_table.to_parquet(output/'native_edges.parquet',index=False,compression='zstd')
    known_endpoint=(settlements.road_endpoint_accepted.eq(True)&settlements.road_node_index.notna()
                    &settlements.snap_km.between(0,10))
    np_positions=np.flatnonzero(known_endpoint)
    np_nodes=settlements.loc[known_endpoint,'road_node_index'].to_numpy(dtype='int64')
    raw_writer=None;road_writer=None; all_times=[]; cumulative=[]; bands=[]; diagnostics=[]; coverage=[]
    for centre in centres.itertuples(index=False):
        started=time.monotonic();cid=str(centre.source_record_id)
        if not centre.road_endpoint_accepted or not np.isfinite(centre.road_node_index) or not 0<=centre.snap_km<=10:
            raise ValueError('Centre lacks accepted endpoint')
        destination_connector=float(centre.snap_km)*4.
        if geometry_only:
            arrival=np.full(n,np.inf); part=saved_arrivals[saved_arrivals.centre_id.eq(cid)]
            arrival[part.node_index.to_numpy(dtype='int64')]=part.time_minutes_to_centre
        else:arrival=dijkstra(reverse,directed=True,indices=int(centre.road_node_index))+destination_connector
        u,v,weights=inbound_arc_arrays(reverse,arrival,max(thresholds),)
        used=np.unique(np.concatenate([u,v]));new=used[np.isnan(projected_x[used])]
        projected_x[new],projected_y[new]=forward.transform(lon[new],lat[new])
        lengths=np.hypot(projected_x[u]-projected_x[v],projected_y[u]-projected_y[v])
        previous={};centre_bands=[]
        for minutes in ([] if routes_only else thresholds):
            if native_records is not None:lines,arcstats=native_reachable_lines(native_records,arrival,minutes)
            else:lines,arcstats=reachable_lines(u,v,weights,arrival,projected_x,projected_y,minutes,n)
            raw=pd.DataFrame([{'centre_id':cid,'centre_name':centre.name,'minutes':minutes,
                'crs':CRS,'reachable_road_geometry_wkb':shapely.to_wkb(lines)}])
            table=pa.Table.from_pandas(raw,preserve_index=False)
            if raw_writer is None:raw_writer=pq.ParquetWriter(output/'reachable_roads_wkb.parquet',table.schema,compression='zstd')
            raw_writer.write_table(table)
            current,band_shapes,geometry_stats=nested_geographies(lines,previous,widths,simplify_m,backward)
            previous=current
            lower=0. if minutes==thresholds[0] else thresholds[thresholds.index(minutes)-1]
            props={'id':cid+'__'+str(int(minutes)),'name':f'{centre.name}: {int(lower)}–{int(minutes)} мин',
                   'centre_id':cid,'centre_name':centre.name,'minutes':minutes,'band_from_minutes':lower,
                   'direction':'to_centre','display_corridor_half_width_m':display_width,
                   'geometry_scope':'cartographic_corridor_of_reachable_road_segments_not_landscape_or_service_catchment'}
            b=feature(band_shapes[display_width],props);centre_bands.append(b);bands.append(b)
            cumulative.append(feature(current[display_width],{**props,'name':f'{centre.name}: до {int(minutes)} мин','band_from_minutes':0.}))
            row={'centre_id':cid,'centre_name':centre.name,'minutes':minutes,**arcstats,
                 'maximum_candidate_arc_length_m':float(lengths.max(initial=0)),
                 'p95_candidate_arc_length_m':float(np.percentile(lengths,95)) if len(lengths) else None,
                 'candidate_arcs_longer_than_2km':int((lengths>2000).sum())}
            for width,g in current.items():
                row[f'area_km2_width_{int(width)}']=transform(forward.transform,g).area/1e6
                row[f'vertices_width_{int(width)}']=geometry_stats[width]['cumulative_vertices']
            diagnostics.append(row)
        slug=SLUGS.get(cid.rsplit(':',1)[-1],cid.rsplit(':',1)[-1])
        if not routes_only:write_geojson(output/f'isochrones_bands_{slug}.geojson',centre_bands)
        if geometry_only:
            print(json.dumps({'centre':centre.name,'geometry_only':True,
                'native_geometry':native_records is not None,'elapsed_seconds':round(time.monotonic()-started,2)},ensure_ascii=False),flush=True)
            continue
        selected=np.flatnonzero(np.isfinite(arrival)&(arrival<=max(thresholds)))
        roads=pd.DataFrame({'centre_id':cid,'node_index':selected,'time_minutes_to_centre':arrival[selected],
                            'lat':lat[selected],'lon':lon[selected]})
        table=pa.Table.from_pandas(roads,preserve_index=False)
        if road_writer is None:road_writer=pq.ParquetWriter(output/'road_arrivals.parquet',table.schema,compression='zstd')
        road_writer.write_table(table)
        fields=['source_record_id','name','lat','lon','population_2021','credit_2021',
                'budget_population_credit','settlement_type_2021','accepted_point_present']
        result=settlements[[c for c in fields if c in settlements]].rename(columns={'source_record_id':'origin_id'}).copy()
        result['centre_id']=cid;result['centre_name']=centre.name
        result['network_minutes']=np.nan;result['origin_connector_minutes']=np.nan
        result['destination_connector_minutes']=destination_connector
        result.loc[known_endpoint,'network_minutes']=arrival[np_nodes]-destination_connector
        result.loc[known_endpoint,'origin_connector_minutes']=settlements.loc[known_endpoint,'snap_km']*4
        result['time_minutes_total']=result.network_minutes+result.origin_connector_minutes+destination_connector
        result['status']=np.where(known_endpoint,'modelled_directed_route','no_accepted_current_endpoint')
        result.loc[known_endpoint&np.isinf(result.time_minutes_total),'status']='no_directed_path_in_this_graph'
        result.loc[np.isinf(result.time_minutes_total),'time_minutes_total']=np.nan
        result['self_point_zero']=result.origin_id.eq(cid)
        result.loc[result.self_point_zero,'time_minutes_total']=0.
        for minutes in thresholds:
            result[f'within_{int(minutes)}min_exact_cost']=result.time_minutes_total.le(minutes).where(result.time_minutes_total.notna())
            within=result.time_minutes_total.le(minutes)
            positive=result.population_2021.gt(0)
            credited=(result.credit_2021.eq(True)&result.budget_population_credit.eq(True))
            coverage.append({'centre_id':cid,'centre_name':centre.name,'minutes':minutes,
                'all_current_records_in_region':len(result),
                'positive_population_records_in_region':int(positive.sum()),
                'unknown_route_records':int(result.time_minutes_total.isna().sum()),
                'records_within_exact_cost':int(within.sum()),
                'positive_population_records_within_exact_cost':int((within&positive).sum()),
                'zero_population_records_within_exact_cost':int((within&result.population_2021.eq(0)).sum()),
                'uncredited_positive_records_within_exact_cost':int((within&positive&~credited).sum()),
                'credited_population_within_exact_cost':float(result.loc[within&credited,'population_2021'].sum()),
                'counts_are_not_polygon_inclusion':True})
        all_times.append(result)
        print(json.dumps({'centre':centre.name,'road_nodes_within_maximum':len(selected),
            'original_arc_candidates':len(u),'elapsed_seconds':round(time.monotonic()-started,2)},ensure_ascii=False),flush=True)
    if raw_writer:raw_writer.close()
    if road_writer:road_writer.close()
    if not geometry_only:
        pd.concat(all_times,ignore_index=True).to_parquet(output/'settlement_travel_times.parquet',index=False,compression='zstd')
        pd.DataFrame(coverage).to_csv(output/'settlement_accessibility_counts.csv',index=False)
        roadrows=pd.read_parquet(output/'road_arrivals.parquet',columns=['node_index'])
        needed=np.unique(roadrows.node_index)
        pd.DataFrame({'node_index':needed,'osm_id':axis[needed]}).to_parquet(output/'needed_road_vertices.parquet',index=False,compression='zstd')
        (output/'route_phase.json').write_text(json.dumps(route_contract,indent=2)+'\n')
    if not routes_only:
        pd.DataFrame(diagnostics).to_csv(output/'geometry_diagnostics.csv',index=False)
        write_geojson(output/'isochrones_cumulative.geojson',cumulative)
        write_geojson(output/'isochrones_bands.geojson',bands)
    files={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in output.glob('*') if p.is_file() and p.name!='summary.json'}
    summary={'schema':'sgrt.saratov.network_isochrones.v1','graph_sha256':GRAPH_SHA256,
        'graph_nodes':n,'graph_arcs':graph.nnz,'direction':'to_centre_full_reverse_graph_dijkstra',
        'search_time_limit':None,'threshold_minutes':thresholds,'cartographic_half_widths_m':widths,
        'display_half_width_m':display_width,'simplification_m':simplify_m,'working_crs':CRS,
        'base_contour_precision_degrees':1e-7,'final_overlay_precision':'full floating; no post-overlay coordinate rounding',
        'topology_precision_grid_degrees':0.,
        'phase':'routes_only' if routes_only else 'geometry_only' if geometry_only else 'complete',
        'geometry_source':'original_accepted_source_way_polylines' if native_records is not None else 'none_routes_only' if routes_only else 'REJECTED_compressed_endpoint_chords_diagnostic_only',
        'native_geometry_validation':native_facts,
        'centre_records':len(centres),'regional_settlement_records':len(settlements),
        'coordinate_source_files':coordinate_proof,'files':files,
        'limits':['Road corridors are a cartographic approximation, not complete accessible land area.',
                  'No observed traffic, ferry schedules or service catchments are established.',
                  'Polygon inclusion is not substituted for exact settlement-to-centre costs.',
                  'The national graph is not clipped at the administrative boundary.']}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['centres','settlements','graph-dir','road-nodes','output']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--catalog',type=Path,default=REPO/'data/catalog.json')
    p.add_argument('--native-ways',type=Path)
    p.add_argument('--native-nodes',type=Path)
    p.add_argument('--routes-only',action='store_true')
    p.add_argument('--geometry-only',action='store_true')
    p.add_argument('--allow-chord-diagnostic',action='store_true')
    a=p.parse_args()
    result=run(a.centres,a.settlements,a.graph_dir,a.road_nodes,a.output,catalog_path=a.catalog,
        native_ways=a.native_ways,native_nodes=a.native_nodes,routes_only=a.routes_only,
        geometry_only=a.geometry_only,allow_chord_diagnostic=a.allow_chord_diagnostic)
    print(json.dumps({k:v for k,v in result.items() if k not in {'files','coordinate_source_files'}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
