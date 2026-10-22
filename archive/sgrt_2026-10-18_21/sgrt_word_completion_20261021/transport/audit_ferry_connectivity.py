#!/usr/bin/env python3
"""Describe actual ferry endpoints against driving graph, without inventing schedules."""
from pathlib import Path
import json
import numpy as np,pandas as pd
from build_transport import distances
ROOT=Path(__file__).resolve().parent
nodes=pd.read_parquet(ROOT/'road_nodes.parquet',columns=['osm_id','node_index','weak_component']).set_index('osm_id');lookup=nodes.weak_component;rows=[]
for r in pd.read_parquet(ROOT/'ferry_way_inventory.parquet').itertuples():
 t=json.loads(r.tags_json);effective=t.get('motorcar',t.get('motor_vehicle',t.get('vehicle',t.get('access',''))));u,v=r.refs[0],r.refs[-1];cu,cv=lookup.get(u),lookup.get(v);rows.append({'osm_way_id':r.osm_id,'name':t.get('name'),'length_km':float(np.sum(distances(r.lat,r.lon))),'origin_endpoint_osm_id':u,'destination_endpoint_osm_id':v,'origin_road_component':cu,'destination_road_component':cv,'both_endpoints_in_road_graph':pd.notna(cu) and pd.notna(cv),'different_road_components':pd.notna(cu) and pd.notna(cv) and cu!=cv,'effective_vehicle_access':effective,'explicit_duration':t.get('duration'),'explicit_interval':t.get('interval'),'explicit_seasonal':t.get('seasonal'),'used_in_primary_routing':False})
d=pd.DataFrame(rows);d.to_parquet(ROOT/'ferry_connectivity_audit.parquet',index=False);receipt={'inventory_ways':len(d),'both_endpoints_in_road_graph':int(d.both_endpoints_in_road_graph.sum()),'potential_component_bridge_ways':int(d.different_road_components.sum()),'explicit_duration_count':int(d.explicit_duration.notna().sum()),'explicit_interval_count':int(d.explicit_interval.notna().sum()),'endpoint_match_scope':'Exact OSM ID match to retained compressed road vertices; missing match does not prove lack of uncompressed road access','not_all_are_vehicle_ferries':True,'not_used_in_primary_road_graph':True,'reason':'Vehicle permissions, boarding times, current operating season and waiting times require distinct multimodal scenario; no invented road link.'};(ROOT/'ferry_connectivity_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
