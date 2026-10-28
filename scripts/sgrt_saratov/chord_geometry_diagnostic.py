"""Identify compressed arcs whose chord drawing needs original way geometry."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from pyproj import Transformer

REPO=Path(__file__).resolve().parents[2];sys.path.insert(0,str(REPO))
from scripts.sgrt_saratov.isochrones import coordinates,inbound_arc_arrays,partial_fraction
from scripts.sgrt_mass.routes import load_graph


def run(graph_dir,road_nodes,model,output):
    graph=load_graph(graph_dir);reverse=graph.T.tocsr();n=graph.shape[0]
    lat,lon,_=coordinates(road_nodes,n,REPO/'data/catalog.json')
    osmid=np.full(n,-1,dtype='int64')
    for p in sorted(Path(road_nodes).glob('part_*.parquet')):
        d=pd.read_parquet(p,columns=['node_index','osm_id']);osmid[d.node_index.to_numpy(dtype='int64')]=d.osm_id
    arrivals=pd.read_parquet(Path(model)/'road_arrivals.parquet')
    centres=pd.read_csv(Path(model).parent/'inputs/centres.csv').set_index('source_record_id')
    transform=Transformer.from_crs('EPSG:4326','EPSG:32638',always_xy=True)
    pieces=[];stats=[]
    for cid,g in arrivals.groupby('centre_id',sort=True):
        a=np.full(n,np.inf);a[g.node_index.to_numpy(dtype='int64')]=g.time_minutes_to_centre
        u,v,w=inbound_arc_arrays(reverse,a,60.)
        la,lb=np.radians(lat[u]),np.radians(lat[v]);dx=np.radians(lon[u]-lon[v])
        h=np.sin((la-lb)/2)**2+np.cos(la)*np.cos(lb)*np.sin(dx/2)**2
        chord=12742.0176*np.arcsin(np.sqrt(np.clip(h,0,1)))
        fraction=partial_fraction(60.,a[v],w);length=chord*fraction
        valid=(fraction>0)&(chord>0)
        uid=np.minimum(u,v).astype('int64')*n+np.maximum(u,v)
        frame=pd.DataFrame({'centre_id':cid,'centre_name':centres.loc[cid,'name'],
            'u':u[valid],'v':v[valid],'u_osm':osmid[u[valid]],'v_osm':osmid[v[valid]],
            'u_lat':lat[u[valid]],'u_lon':lon[u[valid]],'v_lat':lat[v[valid]],'v_lon':lon[v[valid]],
            'edge_minutes':w[valid],'destination_to_centre_minutes':a[v[valid]],
            'accessible_fraction':fraction[valid],'full_chord_km_haversine':chord[valid],
            'drawn_partial_chord_km':length[valid],
            'chord_implied_speed_kmh':np.divide(chord[valid]*60,w[valid],out=np.full(valid.sum(),np.nan),where=w[valid]>0),
            'unordered_edge_key':uid[valid]})
        # Keep one witness per undirected endpoint pair; this does not claim
        # partial opposite pieces are always contiguous or a native polyline.
        selected=frame.sort_values('drawn_partial_chord_km',ascending=False).drop_duplicates('unordered_edge_key')
        pieces.append(selected.head(10))
        stats.append({'centre_id':cid,'centre_name':centres.loc[cid,'name'],
            'directed_arcs_with_nonzero_drawn_fraction':len(frame),
            'unique_endpoint_pairs':len(selected),
            'maximum_full_chord_km':float(frame.full_chord_km_haversine.max()),
            'maximum_drawn_chord_km':float(frame.drawn_partial_chord_km.max())})
    witnesses=pd.concat(pieces,ignore_index=True)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    witnesses.to_csv(output/'long_arc_witnesses.csv',index=False)
    top=witnesses.sort_values('drawn_partial_chord_km',ascending=False).drop_duplicates('unordered_edge_key').head(10)
    top.to_csv(output/'long_arc_witnesses_top10.csv',index=False)
    (output/'long_arc_witnesses_summary.json').write_text(json.dumps({'schema':'sgrt.compressed_arc_chords.v1',
        'native_graph_has_degree2_compressed_geometry':True,
        'builder':'archive/sgrt_2026-10-18_21/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/assemble_graph2021.py',
        'scope':'Chord drawing diagnostic; costs retain original polyline lengths, but intermediate source vertices are not recovered by this script.',
        'centres':stats},ensure_ascii=False,indent=2)+'\n')
    print(top[['centre_name','u_osm','v_osm','full_chord_km_haversine','edge_minutes','chord_implied_speed_kmh']].to_string(index=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['graph-dir','road-nodes','model','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.graph_dir,a.road_nodes,a.model,a.output)
