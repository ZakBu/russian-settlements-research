#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
import pandas as pd,numpy as np
from scipy.spatial import cKDTree
from link_osm_medical import xyz,norm,AXIS
ROOT=Path(__file__).resolve().parent;axis=pd.read_parquet(AXIS);uids=set(axis.id);res={}
for layer in ['current_20261019','history_20210101']:
 p=ROOT/layer;d=pd.read_parquet(p/'osm_medical_inventory.parquet');f=pd.read_parquet(p/'settlement_features.parquet');assert len(f)==len(axis) and f.id.is_unique and set(f.id)==uids;assert d.object_id.is_unique
 for c in ['baseline_uid','conditional_uid','coordinate_candidate_uid']:assert set(d[c].dropna())<=uids
 assert not(d.baseline_uid.notna()&d.conditional_uid.notna()).any()
 assert not d.actual_service_flow_observed.any();assert f.medical_osm_no_accepted_record_does_not_mean_no_service.all()
 coords=d[['lat','lon']].notna().all(axis=1);g=d[coords].copy();g['name_normalized']=g.name.fillna('').map(norm);pidx=g.index.to_numpy();tree=cKDTree(xyz(g.lat.to_numpy(),g.lon.to_numpy()));pairs=tree.query_pairs(2*np.sin(.03/(2*6371.0088)),output_type='ndarray');sus=[]
 for a,b in pairs:
  x,y=g.iloc[a],g.iloc[b]
  if x.name_normalized and x.name_normalized==y.name_normalized and x.broad_function==y.broad_function:
   sus.append({'object_id_1':x.object_id,'object_id_2':y.object_id,'same_normalized_name':x.name_normalized,'broad_function':x.broad_function,'interpretation':'possible_duplicate_or_same_named_colocated_services_not_automatically_merged'})
 pd.DataFrame(sus,columns=['object_id_1','object_id_2','same_normalized_name','broad_function','interpretation']).to_parquet(p/'possible_duplicate_pairs_30m.parquet',index=False)
 res[layer]={'uid_axis_complete':True,'unique_osm_objects':len(d),'coordinate_rows':int(coords.sum()),'possible_same_name_same_function_pairs_within30m':len(sus),'pair_diagnostic_not_identity_deduplication':True,'baseline_membership_valid':True,'observed_patient_flows':False,'features_sha256':hashlib.sha256((p/'settlement_features.parquet').read_bytes()).hexdigest()}
(ROOT/'validation_receipt.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n');print(json.dumps(res,ensure_ascii=False,indent=2))
