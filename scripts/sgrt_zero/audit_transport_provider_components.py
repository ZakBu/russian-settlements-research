#!/usr/bin/env python3
"""Read-only public-route access diagnostic; no observed driveway or barrier-free connector claim."""
from pathlib import Path
import sys,json,numpy as np,pandas as pd
from scipy.spatial import cKDTree
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/sgrt_mass'));from site_geometry import sphere_xyz,chord_km
import argparse
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--prepared-root',type=Path);parser.add_argument('--roads',type=Path);parser.add_argument('--graph-dir',type=Path);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)

w=args.output;m=args.prepared_root;roads=pd.read_parquet(args.roads,columns=['node_index','osm_id','lat','lon','weak_component']);sizes=roads.weak_component.value_counts();large=roads[roads.weak_component==sizes.index[0]];tree=cKDTree(sphere_xyz(large.lat,large.lon));frames=[]
cols=['provider_id','service_code','source_record_id','site_lat','site_lon','road_node_index','weak_component','snap_km','input_kind','admitted_offer','road_endpoint_accepted']
for folder in ['routes_complete_scope_corrected','routes_education_commerce_corrected','routes_commerce_components_corrected','routes_wb','routes_yandex']:
 f=pd.read_parquet(m/folder/'provider_road_seeds.parquet',columns=cols);frames.append(f)
d=pd.concat(frames).drop_duplicates(['provider_id','service_code','site_lat','site_lon']);d=d[d.input_kind.eq('sites')&d.admitted_offer&d.road_endpoint_accepted].copy();d['component_nodes']=d.weak_component.map(sizes);small=d[d.component_nodes.lt(100)].copy();dist,idx=tree.query(sphere_xyz(small.site_lat,small.site_lon),workers=1);small['nearest_largest_component_snap_km']=chord_km(dist);small['alternative_road_node_index']=large.iloc[idx].node_index.to_numpy();small['alternative_access_verified']=False;small.to_parquet(w/'small_component_provider_inventory.parquet',index=False);counts=[]
for svc,g in d.groupby('service_code'):
 t=small[small.service_code.eq(svc)];counts.append({'service':svc,'accepted_physical_provider_seeds':len(g),'component_lt100':len(t),'of_small_main_network_within100m':int(t.nearest_largest_component_snap_km.le(.1).sum()),'of_small_main_network_within500m':int(t.nearest_largest_component_snap_km.le(.5).sum()),'of_small_main_network_within_original2km':int(t.nearest_largest_component_snap_km.le(2).sum())})
pd.DataFrame(counts).to_csv(w/'provider_access_component_summary.csv',index=False);print(pd.DataFrame(counts).to_string(index=False));(w/'provider_access_component_summary.json').write_text(json.dumps(counts,indent=2))
