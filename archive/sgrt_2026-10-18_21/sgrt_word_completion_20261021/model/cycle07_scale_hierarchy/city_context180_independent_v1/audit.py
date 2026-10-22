"""Independent full directed NP-to-city times; no producer helper import."""
from pathlib import Path
import json,hashlib
import numpy as np,pandas as pd,pyarrow.parquet as pq
BASE=next(p for p in Path(__file__).resolve().parents if (p/'transport').is_dir() and (p/'model').is_dir());OUT=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
mp=BASE/'transport/cycle07_geography_recovery_extension/candidate_travel_times_manifest.json';manifest=json.loads(mp.read_text());nodespath=BASE/'model_inputs_cycle07/institutional_mass477_v2/computed/effective_full_nodes.parquet';nodes=pd.read_parquet(nodespath,columns=['id','population_2021','accepted_formal_settlement_subtype2021','_population_axis_row','lat','lon'])
ordinary=nodes._population_axis_row.fillna(False)&nodes.population_2021.ge(100000)&nodes.accepted_formal_settlement_subtype2021.eq('город')&nodes[['lat','lon']].notna().all(axis=1)
anchors=sorted(nodes.loc[ordinary,'id'].tolist()+['ctx:RU-FED-MOW','ctx:RU-FED-SPB']);assert len(anchors)==171 and len(set(anchors))==171
op=mp.parent/manifest['origin_mapping']['path'];dp=mp.parent/manifest['destination_mapping']['path'];o=pd.read_parquet(op);d=pd.read_parquet(dp);watch={str(p):sha(p)for p in [Path(__file__),mp,nodespath,op,dp]};assert watch[str(mp)]=='11c0be3a5b9c2dd6e8980e254352f93bd971b08493c570b6734b1d616d2102f5';assert watch[str(op)]==manifest['origin_mapping']['sha256'] and watch[str(dp)]==manifest['destination_mapping']['sha256']
assert np.array_equal(o.origin_index,np.arange(len(o))) and np.array_equal(d.destination_index,np.arange(len(d)))
index={uid:i for i,uid in enumerate(anchors)};ranks=d.canonical_id.map(index).fillna(-1).to_numpy('int32');assert (ranks>=0).sum()==171;mins=np.full(len(o),np.inf);winner=np.full(len(o),171,dtype='int32');counts=[]
for part in manifest['parts']:
 p=mp.parent/part['path'];assert sha(p)==part['sha256'];watch[str(p)]=part['sha256'];z=pq.read_table(p,columns=['origin_index','destination_index','network_minutes']).to_pandas();a=z.origin_index.to_numpy('int64');b=z.destination_index.to_numpy('int64');r=ranks[b];take=r>=0;a=a[take];b=b[take];r=r[take];network=z.network_minutes.to_numpy('float32')[take]
 t=(network+(4*o.snap_km.to_numpy(float)[a]+4*d.snap_km.to_numpy(float)[b]).astype('float32')).astype('float32');same=o.canonical_id.to_numpy()[a]==d.canonical_id.to_numpy()[b];t[same]=0;assert np.isfinite(t).all() and (t>=0).all();valid=t.astype('float64')<=180.0001;a=a[valid];r=r[valid];t=t[valid]
 # Lexical cityID is integer rank; first compute min distance across ALL rows.
 np.minimum.at(mins,a,t)
 good=t==mins[a];np.minimum.at(winner,a[good],r[good])
 # Prior winners must be reset if this chunk gives a STRICTLY smaller distance.
 # Recompute winner against retained current distances using an explicit perchunkmin.
 # Store qualifying rows to reproduce lexicographic reduction after streaming.
 pd.DataFrame({'origin_index':a.astype('int32'),'anchor_rank':r,'minutes':t}).to_parquet(OUT/f'city_part_{len(counts):03}.parquet',index=False)
 counts.append(len(a))
# Second pass exact winner against FINAL min avoids stale ranks after laterparts.
winner[:]=171
for i in range(len(counts)):
 z=pd.read_parquet(OUT/f'city_part_{i:03}.parquet');a=z.origin_index.to_numpy();r=z.anchor_rank.to_numpy();hit=z.minutes.to_numpy()==mins[a];np.minimum.at(winner,a[hit],r[hit])
for uid,rank in index.items():
 ix=np.flatnonzero(o.canonical_id.to_numpy()==uid);assert len(ix)==1;mins[ix[0]]=0;winner[ix[0]]=rank
known=np.isfinite(mins);reference=pd.DataFrame({'id':o.canonical_id,'nearest_large_city_network_minutes':np.where(known,mins,np.nan),'nearest_large_city_id':[anchors[x]if x<171 else None for x in winner]});reference=nodes[['id']].merge(reference,on='id',how='left',validate='one_to_one');reference['network_suburban_30_60_minutes']=pd.Series(pd.NA,index=reference.index,dtype='boolean');ok=reference.nearest_large_city_network_minutes.notna();reference.loc[ok,'network_suburban_30_60_minutes']=reference.loc[ok,'nearest_large_city_network_minutes'].between(30,60)
reference.to_parquet(OUT/'independent_full_time_city_reference.parquet',index=False)
oldp=BASE/'analysis/cycle07_source477_city_context180_v1/large_city_context180.parquet';old=pd.read_parquet(oldp).set_index('id').loc[reference.id].reset_index();tv=reference.nearest_large_city_network_minutes.to_numpy();ov=old.nearest_large_city_network_minutes.to_numpy();value_diff=~(np.isclose(tv,ov,rtol=0,atol=0,equal_nan=True));id_diff=reference.nearest_large_city_id.fillna('NA').ne(old.nearest_large_city_id.fillna('NA'));band_diff=reference.network_suburban_30_60_minutes.astype('string').fillna('NA').ne(old.network_suburban_30_60_minutes.astype('string').fillna('NA'))
ledger=reference.loc[value_diff|id_diff|band_diff].copy();ledger['v1_raw_network_minutes']=old.loc[ledger.index,'nearest_large_city_network_minutes'];ledger['v1_raw_city_id']=old.loc[ledger.index,'nearest_large_city_id'];ledger['v1_raw_band']=old.loc[ledger.index,'network_suburban_30_60_minutes'];ledger.to_parquet(OUT/'v1_raw_network_only_defect_witnesses.parquet',index=False)
assert all(sha(Path(p))==h for p,h in watch.items());receipt={'status':'INDEPENDENT_FULL_TIME_REFERENCE_COMPUTED_V1_RAW_NETWORK_METRIC_REJECTED','all_checks_passed':False,'no_producer_helper_imported':True,'full_source_rows':manifest['rows'],'parts':len(counts),'fixed_population_city_anchors':171,'qualifying_full_time_city_pairs':sum(counts),'known_full_time_rows':int(ok.sum()),'v1_time_value_differences':int(value_diff.sum()),'v1_city_identity_differences':int(id_diff.sum()),'v1_30_60_band_differences':int(band_diff.sum()),'source_pins':watch,'output_sha256':sha(OUT/'independent_full_time_city_reference.parquet'),'defect_witness_sha256':sha(OUT/'v1_raw_network_only_defect_witnesses.parquet'),'source_precision':'float32network+float32(4snap_o+4snap_d), self0, float64<=180.0001; tieslexicalID'};(OUT/'reference_receipt.json').write_text(json.dumps(receipt,indent=2));print({k:v for k,v in receipt.items()if k!='source_pins'},flush=True)
for i in range(len(counts)):(OUT/f'city_part_{i:03}.parquet').unlink()
