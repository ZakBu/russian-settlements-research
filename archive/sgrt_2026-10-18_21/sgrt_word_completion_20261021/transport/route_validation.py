#!/usr/bin/env python3
from pathlib import Path
import json,time,subprocess
import numpy as np,pandas as pd
from scipy.sparse import load_npz
from compute_matrix import export_graph,ROOT,REPO,RAW,sha

def run():
 t=time.time();export_graph();run=RAW/'validation_route';run.mkdir(exist_ok=True)
 for name in ['rev_indptr.bin','rev_indices.bin','rev_weights.bin']:
  p=run/name
  if not p.exists():p.symlink_to(RAW/name)
 sourcepath=REPO/'research/sgrt_word_completion_20261021/validation/medical_territories_2024_all_rows.parquet';d=pd.read_parquet(sourcepath);pairs=d[['origin_id','destination_id']].dropna().drop_duplicates().copy();snap=pd.read_parquet(ROOT/'settlement_road_snap.parquet').set_index('id');accepted=snap[snap.snap_km<=10];target=accepted.loc[accepted.index.isin(pairs.origin_id)].reset_index();centers=accepted.loc[accepted.index.isin(pairs.destination_id)].reset_index()
 target.road_node_index.to_numpy('uint32').tofile(run/'target_nodes.bin');centers.road_node_index.to_numpy('uint32').tofile(run/'source_nodes.bin');target.snap_km.mul(4).to_numpy('float32').tofile(run/'target_connectors.bin');centers.snap_km.mul(4).to_numpy('float32').tofile(run/'source_connectors.bin');np.full(len(centers),720,dtype='float32').tofile(run/'source_budgets.bin')
 (run/'route_checkpoint.txt').unlink(missing_ok=True)
 subprocess.run(['g++','-O3','-std=c++17',str(ROOT/'route_matrix.cpp'),'-o',str(run/'route_matrix')],check=True);subprocess.run([str(run/'route_matrix'),str(run)],check=True)
 raw=np.fromfile(run/'matrix_pairs.bin',dtype=[('origin','<u4'),('center','<u4'),('network_minutes','<f4')]);computed=pd.DataFrame({'origin_id':target.id.to_numpy()[raw['origin']],'destination_id':centers.id.to_numpy()[raw['center']],'network_minutes':raw['network_minutes']});computed['connector_minutes']=computed.origin_id.map(accepted.snap_km)*4+computed.destination_id.map(accepted.snap_km)*4;computed['travel_minutes']=computed.network_minutes+computed.connector_minutes;same=computed.origin_id.eq(computed.destination_id);computed.loc[same,['network_minutes','connector_minutes','travel_minutes']]=0
 result=pairs.merge(computed,on=['origin_id','destination_id'],how='left',validate='one_to_one');result['origin_snap_km']=result.origin_id.map(snap.snap_km);result['destination_snap_km']=result.destination_id.map(snap.snap_km);result['origin_component']=result.origin_id.map(snap.weak_component);result['destination_component']=result.destination_id.map(snap.weak_component)
 result['route_status']=np.select([result.travel_minutes.notna(),result.origin_snap_km.isna()|result.destination_snap_km.isna(),result.origin_snap_km.gt(10)|result.destination_snap_km.gt(10),result.origin_component.ne(result.destination_component)],['routed','unlocated_or_outside_snap_axis','snap_over10km','different_weak_components'],default='not_reachable_within720min_or_directed_disconnection');result['is_external']=result.origin_id.ne(result.destination_id);result['not_blind_holdout']=True;result['not_measured_patient_trips']=True;result.to_parquet(ROOT/'independent_medical_validation_travel.parquet',index=False)
 receipt={'status':'COMPUTED','graph_sha256':sha(ROOT/'routing_graph.npz'),'access_repair_receipt_sha256':sha(ROOT/'access_repair_receipt.json'),'yearround_profile_receipt_sha256':sha(ROOT/'yearround_profile_receipt.json'),'source_path':str(sourcepath),'unique_resolved_source_pairs':len(pairs),'unique_external_pairs':int(result.is_external.sum()),'source_providers':pairs.destination_id.nunique(),'accepted_provider_snaps':len(centers),'accepted_origin_snaps':len(target),'route_status_counts':result.route_status.value_counts().to_dict(),'external_route_status_counts':result.loc[result.is_external].route_status.value_counts().to_dict(),'budget_minutes':720,'time_model':'scenario_freeflow+explicit15kmhconnector','validation_use':'postdevelopment_geoaccessibilitycheck;notmeasuredtripandnotblindholdout','seconds':time.time()-t};(ROOT/'validation_routing_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
