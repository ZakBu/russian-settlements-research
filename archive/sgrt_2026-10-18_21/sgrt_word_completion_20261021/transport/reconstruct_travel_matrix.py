#!/usr/bin/env python3
"""Decode SHA-verified compact matrix; optionally materialize the string interface."""
from pathlib import Path
import json,hashlib,time
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parent
SCHEMA=pa.schema([('origin_id',pa.string()),('destination_id',pa.string()),('travel_minutes',pa.float32()),('network_minutes',pa.float32()),('connector_minutes',pa.float32()),('route_status',pa.string()),('destination_budget_minutes',pa.float32())])
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(2**20),b''):h.update(block)
 return h.hexdigest()
def load_mappings():
 m=json.loads((ROOT/'candidate_travel_times_manifest.json').read_text());assert m['format']=='compact_parquet_parts_v1'
 for key in ['origin_mapping','destination_mapping']:assert sha(ROOT/m[key]['path'])==m[key]['sha256']
 origin=pd.read_parquet(ROOT/m['origin_mapping']['path']);dest=pd.read_parquet(ROOT/m['destination_mapping']['path']);assert np.array_equal(origin.origin_index,np.arange(len(origin))) and np.array_equal(dest.destination_index,np.arange(len(dest)))
 return m,origin,dest
def decode(table,origin,dest):
 oi=table['origin_index'].to_numpy();di=table['destination_index'].to_numpy();net=table['network_minutes'].to_numpy().copy();oc=origin.snap_km.to_numpy(dtype=float)*4;dc=dest.snap_km.to_numpy(dtype=float)*4;ids=origin.get('canonical_id',origin.id).to_numpy()[oi];centers=dest.get('canonical_id',dest.id).to_numpy()[di];connector=(oc[oi]+dc[di]).astype('float32');mins=net+connector;same=ids==centers;net[same]=0;connector[same]=0;mins[same]=0
 return pa.Table.from_arrays([pa.array(ids),pa.array(centers),pa.array(mins),pa.array(net),pa.array(connector),pa.array(['routed']*len(oi)),pa.array(dest.routing_budget_minutes.to_numpy('float32')[di])],schema=SCHEMA)
def iter_travel_tables(verify_parts=True):
 m,origin,dest=load_mappings();n=0
 for part in m['parts']:
  path=ROOT/part['path']
  if verify_parts:assert sha(path)==part['sha256'],str(path)
  table=pq.read_table(path);assert len(table)==part['rows'];n+=len(table);yield decode(table,origin,dest)
 assert n==m['rows']
def main():
 start=time.time();output=ROOT/'candidate_travel_times.parquet';temp=output.with_suffix('.parquet.tmp');writer=pq.ParquetWriter(temp,SCHEMA,compression='zstd');n=0
 for table in iter_travel_tables():writer.write_table(table);n+=len(table)
 writer.close();temp.replace(output);receipt={'status':'RECONSTRUCTED','rows':n,'output_sha256':sha(output),'input_manifest_sha256':sha(ROOT/'candidate_travel_times_manifest.json'),'seconds':time.time()-start};(ROOT/'reconstruction_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
