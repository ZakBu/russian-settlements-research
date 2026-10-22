#!/usr/bin/env python3
from pathlib import Path
import argparse,json,hashlib,numpy as np,pandas as pd
H=Path(__file__).resolve().parent;REPO=H.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--inputs',type=Path,required=True);a=ap.parse_args();config=a.inputs.resolve();cfg=json.loads(config.read_text());axis=REPO/cfg['axis'];d=pd.read_parquet(axis,columns=['id','name','region','lat','lon']);assert d.id.is_unique
 d['point_role']='current_full_axis';rows=[]
 for anchor in cfg['external_large_city_anchors']:
  assert anchor['id'] not in set(d.id);rows.append({'id':anchor['id'],'name':anchor['name'],'region':None,'lat':anchor['anchor_lat'],'lon':anchor['anchor_lon'],'point_role':'external_metropolitan_accessibility_context_only'})
 d=pd.concat([d,pd.DataFrame(rows)],ignore_index=True);assert d.id.is_unique;d['point_coordinates_available']=np.isfinite(d[['lat','lon']]).all(axis=1);d.to_parquet(H/'routing_points.parquet',index=False)
 dest=H.parent/'cycle05_destination_extension7/route_destination_index.parquet';target=pd.read_parquet(dest,columns=['id']);assert target.id.isin(d.id).all()
 snapshot=H/'point_configuration.snapshot.json';snapshot.write_bytes(config.read_bytes());sources={str(p.relative_to(REPO)):sha(p) for p in [config,axis,dest]}
 for x in cfg['external_large_city_anchors']:
  p=REPO/x['source_receipt'];assert sha(p)==x['source_receipt_sha256'];sources[str(p.relative_to(REPO))]=sha(p)
 receipt={'status':'FULL_CURRENT_AXIS_AND_EXPLICIT_CONTEXT_POINTS_FROZEN_BEFORE_SNAPPING','source_sha256':sources,'axis_rows':len(d)-len(rows),'external_context_rows':len(rows),'point_rows':len(d),'finite_coordinate_rows':int(d.point_coordinates_available.sum()),'missing_coordinate_rows':int((~d.point_coordinates_available).sum()),'current_potential_destination_union_rows':len(target),'all_current_destinations_in_points':True,'coordinates_are_existing_axis_locations_not_proven_exact_historical_coordinates':True,'external_context_population_not_injected':True,'routing_points_sha256':sha(H/'routing_points.parquet'),'durable_point_configuration_snapshot':{'path':snapshot.name,'sha256':sha(snapshot)}}
 (H/'routing_points_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
