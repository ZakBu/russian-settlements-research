from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent;BASE=next(p for p in HERE.parents if (p/'transport').is_dir() and (p/'model').is_dir())
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
r=json.loads((HERE/'reference_receipt.json').read_text());author=BASE/'analysis/cycle07_source477_city_context180_v2';receipt=json.loads((author/'receipt.json').read_text());a=pd.read_parquet(author/'large_city_context180.parquet');ref=pd.read_parquet(HERE/'independent_full_time_city_reference.parquet');assert a.id.equals(ref.id)
checks={};checks['all173864_axis_ids_order_exact']=a.id.equals(ref.id) and len(a)==173864
for c in ['nearest_large_city_network_minutes','nearest_large_city_id','network_suburban_30_60_minutes']:
 checks['allrows_'+c]=a[c].astype('string').fillna('NA').equals(ref[c].astype('string').fillna('NA'))
mp=BASE/'transport/cycle07_geography_recovery_extension/candidate_travel_times_manifest.json';m=json.loads(mp.read_text());o=pd.read_parquet(mp.parent/m['origin_mapping']['path']);d=pd.read_parquet(mp.parent/m['destination_mapping']['path']);oi=a.id.map(pd.Series(o.origin_index.to_numpy(),index=o.canonical_id));di=a.nearest_large_city_id.map(pd.Series(d.destination_index.to_numpy(),index=d.canonical_id));known=a.nearest_large_city_network_minutes.notna();valid=known&oi.notna()&di.notna();keys=(oi[valid].to_numpy('int64')*len(d)+di[valid].to_numpy('int64'));order=np.argsort(keys);wanted=keys[order];target_indices=np.flatnonzero(valid)[order];found=np.zeros(len(wanted),bool);network=np.full(len(wanted),np.nan);watch={str(p):h for p,h in r['source_pins'].items()};watch[str(author/'receipt.json')]=sha(author/'receipt.json');watch[str(author/'large_city_context180.parquet')]=sha(author/'large_city_context180.parquet');watch[str(Path(__file__))]=sha(Path(__file__))
anchors=pd.read_parquet(author/'fixed171_anchor_source_witnesses.parquet');checks['171_anchor_witness_identity']=set(anchors.id)==set(a.loc[a.nearest_large_city_id.eq(a.id),'id']) and len(anchors)==171
cityindices=set(d.loc[d.canonical_id.isin(anchors.id),'destination_index'])
for part in m['parts']:
 p=mp.parent/part['path'];z=pq.read_table(p,columns=['origin_index','destination_index','network_minutes']).to_pandas();keep=z.destination_index.isin(cityindices).to_numpy();aa=z.origin_index.to_numpy()[keep];bb=z.destination_index.to_numpy()[keep];k=aa.astype('int64')*len(d)+bb;pos=np.searchsorted(wanted,k);hit=pos<len(wanted);hit[hit]&=wanted[pos[hit]]==k[hit]
 assert not found[pos[hit]].any();found[pos[hit]]=True;network[pos[hit]]=z.network_minutes.to_numpy()[keep][hit]
assert found.all()
origin=oi.to_numpy()[target_indices].astype('int64');dest=di.to_numpy()[target_indices].astype('int64');connector=(4*o.snap_km.to_numpy()[origin]+4*d.snap_km.to_numpy()[dest]).astype('float32');same=o.canonical_id.to_numpy()[origin]==d.canonical_id.to_numpy()[dest];network[same]=0;connector[same]=0
checks['all_selected_network_component_source_exact']=np.array_equal(a.nearest_city_network_component_minutes.to_numpy()[target_indices],network)
checks['all_selected_connector_component_source_exact']=np.array_equal(a.nearest_city_connector_component_minutes.to_numpy()[target_indices],connector.astype(float))
checks['all_selected_total_float32_exact']=np.array_equal(a.nearest_large_city_network_minutes.to_numpy()[target_indices],(network.astype('float32')+connector).astype('float32').astype(float))
checks['unknown_components_remain_NA']=a.loc[~known,['nearest_city_network_component_minutes','nearest_city_connector_component_minutes','nearest_large_city_id']].isna().all().all()
checks['all_known_total_within180']=bool((a.loc[known,'nearest_large_city_network_minutes']<=180.0001).all());checks['unknown_no_absence_and_no_ranks']=a.unobserved_is_not_absence.eq(True).all() and a.context_uses_empirical_rank.eq(False).all()
checks['producer_740470_pairs_match_independent']=receipt['bounded_city_pairs_read']==r['qualifying_full_time_city_pairs']==740470
checks['source_and_producer_bytes_unchanged']=all(sha(Path(p))==h for p,h in watch.items())
assert all(checks.values()),checks
result={'status':'ACCEPTED_INDEPENDENT_ALLROW_V2_FULL_NP_TO_CITY_CONTEXT','all_checks_passed':True,'n_checks':len(checks),'checks':{k:bool(v)for k,v in checks.items()},'accepted_context_sha256':sha(author/'large_city_context180.parquet'),'accepted_source_receipt_sha256':sha(author/'receipt.json'),'known_rows':int(known.sum()),'fixed_anchor_count':171,'source_rows_independently_scanned':m['rows'],'all_selected_components_independently_source_replayed':int(found.sum()),'source_watch':watch,'v1_metric_rejected':True,'v1_time_differences':r['v1_time_value_differences'],'v1_city_identity_differences':r['v1_city_identity_differences'],'v1_30_60_band_differences':r['v1_30_60_band_differences']};(HERE/'v2_admission.json').write_text(json.dumps(result,indent=2));print({k:v for k,v in result.items()if k not in ['source_watch','checks']})
