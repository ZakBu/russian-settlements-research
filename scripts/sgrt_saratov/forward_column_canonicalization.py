"""Recover fresh-forward floating-point bits after a reversible coordinate repair.

Reverse searches give mathematically identical distances, but reverse summation
can differ by ~1e-12 minutes. Reuse independently computed finite forward rows;
run full forward searches only for finite costs beyond that exact prefix.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy.sparse import load_npz
from scipy.sparse.csgraph import dijkstra

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_mass.routes import load_graph, GRAPH_SHA256
from scripts.sgrt_saratov.coordinate_cost_correction import sha,write_json,origins,FILES

CONTROL_SUFFIXES=('118372','118308','116499','116550','117415','117733','117079','116610','117219','117322')


def forward_columns(graph, origin_table, destinations, cached, matrices, column_indices, control_rows):
    """Return canonical columns without mutating the existing cache."""
    columns={int(j):np.array(cached[:,j],copy=True) for j in column_indices}
    present={int(j):np.zeros(len(origin_table),dtype=bool) for j in column_indices}
    comparison=[]
    for matrix,offset in matrices:
        for row in control_rows:
            local=int(row)-offset
            if 0<=local<matrix.shape[0]:
                lo,hi=matrix.indptr[local:local+2];indices=matrix.indices[lo:hi];values=matrix.data[lo:hi]
                keep=~np.isin(indices,column_indices)
                reference=np.asarray(cached[int(row),indices[keep]])
                if not np.array_equal(values[keep].view('uint64'),reference.view('uint64')):
                    raise ValueError('Finite forward prefix differs from the full forward control vector')
                comparison.append({'full_row_index':int(row),'exact_other_destination_pairs':int(keep.sum())})
        subset=matrix[:,column_indices].tocoo()
        for k,column in enumerate(column_indices):
            selected=subset.col==k;rows=subset.row[selected]+offset;values=subset.data[selected]
            if not np.allclose(values,cached[rows,column],rtol=1e-11,atol=1e-7):
                raise ValueError('Forward/reverse distances differ beyond arithmetic tolerance')
            columns[int(column)][rows]=values;present[int(column)][rows]=True
    pending=set()
    accepted=origin_table.accepted_source_endpoint.eq(True).to_numpy()
    for column in column_indices:
        missing=accepted & ~present[int(column)] & np.isfinite(cached[:,column])
        if np.any(cached[missing,column] < 480.-1e-7):
            raise ValueError('Known finite in-prefix cost is absent from finite forward data')
        pending.update(np.flatnonzero(missing).tolist())
    destination_nodes=destinations.road_node_index.to_numpy('int64')
    destination_connectors=destinations.destination_connector_minutes.to_numpy(float)
    for index in sorted(pending):
        origin=origin_table.iloc[index]
        distance=dijkstra(graph,directed=True,indices=int(origin.road_node_index))
        values=distance[destination_nodes]+destination_connectors+4*float(origin.snap_km)
        own=destinations.source_record_id.eq(str(origin.source_record_id)).to_numpy()
        values[own]=0.
        keep=~np.isin(np.arange(len(destinations)),column_indices)
        if not np.array_equal(values[keep].view('uint64'),np.asarray(cached[index,keep]).view('uint64')):
            raise ValueError('New full forward search changes unrelated destination bits')
        if not np.allclose(values[column_indices],cached[index,column_indices],rtol=1e-11,atol=1e-7):
            raise ValueError('Beyond-prefix forward/reverse distances disagree')
        for column in column_indices:
            columns[int(column)][index]=values[column]
    return columns,{'finite_forward_control_comparisons':comparison,
                    'full_forward_extra_rows':sorted(pending),
                    'finite_forward_pairs_used':{str(j):int(present[int(j)].sum()) for j in column_indices}}


def run(fields,cache_dir,graph_dir,overlay,output):
    fields,cache_dir,output=map(Path,(fields,cache_dir,output));output.mkdir(parents=True,exist_ok=True)
    if (output/'summary.json').exists():raise ValueError('Forward-bit proof already exists')
    contract=json.loads((cache_dir/'contract.json').read_text())
    for key,name in FILES.items():
        if sha(fields/name)!=contract[key]:raise ValueError('Forward-bit input differs from corrected route contract')
    if contract['graph_sha256']!=GRAPH_SHA256:raise ValueError('Unexpected road graph')
    origin_table=origins(fields);dest=pd.read_parquet(fields/'destinations.parquet')
    columns=np.flatnonzero(dest.source_record_id.isin(pd.read_csv(overlay).source_record_id).to_numpy())
    cached=np.load(cache_dir/'full_destination_costs.npy',mmap_mode='r+')
    control_rows=origin_table.index[origin_table.source_record_id.str.rsplit(':',n=1).str[-1].isin(CONTROL_SUFFIXES)].tolist()
    matrices=[(load_npz(fields/'destination_costs.npz'),0),
              (load_npz(fields/'halo_destination_costs.npz'),len(pd.read_parquet(fields/'regional_roster.parquet')))]
    graph=load_graph(graph_dir)
    corrected,proof=forward_columns(graph,origin_table,dest,cached,matrices,columns,control_rows)
    np.savez_compressed(output/'reverse_and_forward_columns.npz',column_indices=columns,
        reverse=np.asarray(cached[:,columns]),forward=np.stack([corrected[int(j)] for j in columns],axis=1))
    finite_differences=[]
    for j in columns:
        valid=np.isfinite(cached[:,j])
        finite_differences.append(np.abs(cached[valid,j]-corrected[int(j)][valid]).max(initial=0))
    proof.update(graph_sha256=GRAPH_SHA256,overlay_sha256=sha(overlay),column_indices=columns.tolist(),
        full_matrix_shape=list(cached.shape),fresh_forward_bits_complete=True,
        max_reverse_forward_absolute_minutes=float(max(finite_differences)))
    for j,values in corrected.items():cached[:,j]=values
    cached.flush()
    contract['producer_module_sha256']=sha(__file__);write_json(cache_dir/'contract.json',contract)
    proof['canonical_full_cost_npy_sha256']=sha(cache_dir/'full_destination_costs.npy')
    write_json(output/'summary.json',proof);print(json.dumps(proof),flush=True)
    return proof


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('fields','cache-dir','graph-dir','overlay','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.fields,a.cache_dir,a.graph_dir,a.overlay,a.output)


if __name__=='__main__':main()
