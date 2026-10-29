"""Exactly repair full route-cache rows/columns after documented point overlays.

The immutable population foundation is untouched. A forward search repairs each
changed/new origin; a reverse search repairs each changed destination. All other
shared costs must remain bit-for-bit identical. Reverse distances are equal
mathematically; floating-point path summation can differ at machine precision.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import dijkstra

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.routes import load_graph, GRAPH_SHA256

FILES = {'reference_sha256': 'national_reference_with_endpoints.parquet',
         'regional_roster_sha256': 'regional_roster.parquet',
         'halo_roster_sha256': 'halo_roster.parquet', 'destinations_sha256': 'destinations.parquet'}
POINT_COLUMNS = {'lat', 'lon', 'road_node_index', 'snap_km', 'origin_connector_minutes',
                 'destination_connector_minutes', 'context_coordinate_source_id',
                 'context_coordinate_precision_degrees', 'weak_component'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def origins(fields):
    tables = []
    for scope, name in [('regional', 'regional_roster'), ('halo', 'halo_roster')]:
        table = pd.read_parquet(Path(fields)/(name+'.parquet'))
        table['origin_scope'] = scope
        tables.append(table)
    result = pd.concat(tables, ignore_index=True)
    if result.source_record_id.duplicated().any():
        raise ValueError('Origin identities must be unique')
    result['full_row_index'] = np.arange(len(result), dtype='int32')
    return result


def check_derived_overlay(before, after, changed_ids, name):
    """Only explicit point/endpoint columns of documented records may change."""
    if before.source_record_id.duplicated().any() or after.source_record_id.duplicated().any():
        raise ValueError(f'Nonunique identities in {name}')
    if not before.source_record_id.equals(after.source_record_id):
        raise ValueError(f'Original national/regional/destination axis changed: {name}')
    if not set(before.columns).issubset(after.columns):
        raise ValueError(f'Original columns removed: {name}')
    if any(not c.startswith('pilot_') for c in set(after.columns)-set(before.columns)):
        raise ValueError(f'Unrecognised overlay metadata: {name}')
    affected = before.source_record_id.isin(changed_ids)
    for column in before.columns:
        selected = ~affected if column in POINT_COLUMNS else np.ones(len(before), dtype=bool)
        try:
            pd.testing.assert_series_equal(before.loc[selected, column].reset_index(drop=True),
                after.loc[selected, column].reset_index(drop=True), check_dtype=False, check_exact=True)
        except AssertionError as exc:
            raise ValueError(f'Undocumented change in {name}.{column}') from exc


def unaffected_hash(matrix, row_indices, column_mask):
    digest = hashlib.sha256()
    for start in range(0, len(row_indices), 16):
        block = np.asarray(matrix[np.asarray(row_indices[start:start+16], dtype=int), :])
        digest.update(np.ascontiguousarray(block[:, column_mask]).view('uint8'))
    return digest.hexdigest()


def corrected_costs(graph, new_origins, destinations, changed_ids, new_origin_ids=()):
    """Return exact directed row/column repairs, with both point connectors."""
    origin_rows = {}
    destination_columns = {}
    d_ids = destinations.source_record_id.astype(str).to_numpy()
    d_nodes = destinations.road_node_index.to_numpy('int64')
    d_connectors = destinations.destination_connector_minutes.to_numpy(float)
    affected_origins = set(changed_ids) | set(new_origin_ids)
    distance = None
    for index in np.flatnonzero(new_origins.source_record_id.isin(affected_origins)):
        origin = new_origins.iloc[index]
        if not bool(origin.accepted_source_endpoint):
            origin_rows[int(index)] = np.full(len(destinations), np.nan)
            continue
        distance = dijkstra(graph, directed=True, indices=int(origin.road_node_index))
        costs = distance[d_nodes] + d_connectors + 4*float(origin.snap_km)
        own = np.flatnonzero(d_ids == str(origin.source_record_id))
        if len(own) != 1:
            raise ValueError('Accepted origin needs exactly one destination identity')
        costs[own[0]] = 0.
        origin_rows[int(index)] = costs
        print(json.dumps({'event': 'corrected_origin_forward', 'source_record_id': str(origin.source_record_id)}), flush=True)
    del distance
    reverse = graph.transpose().tocsr()
    accepted = new_origins.accepted_source_endpoint.eq(True).to_numpy()
    for index in np.flatnonzero(destinations.source_record_id.isin(changed_ids)):
        destination = destinations.iloc[index]
        distance = dijkstra(reverse, directed=True, indices=int(destination.road_node_index))
        costs = np.full(len(new_origins), np.nan)
        # Preserve the original forward expression's connector addition order.
        costs[accepted] = (distance[new_origins.loc[accepted, 'road_node_index'].to_numpy('int64')]
            + float(destination.destination_connector_minutes)
            + 4*new_origins.loc[accepted, 'snap_km'].to_numpy(float))
        own = new_origins.source_record_id.eq(str(destination.source_record_id)).to_numpy()
        costs[own & accepted] = 0.
        destination_columns[int(index)] = costs
        print(json.dumps({'event': 'corrected_destination_reverse', 'source_record_id': str(destination.source_record_id)}), flush=True)
    # Forward rows are authoritative at intersections: fresh full production
    # evaluates forward shortest paths, not reverse summation order.
    for row_index, row in origin_rows.items():
        for col_index, col in destination_columns.items():
            if np.isnan(row[col_index]) and np.isnan(col[row_index]):
                continue
            if not np.isclose(row[col_index], col[row_index], rtol=1e-11, atol=1e-7):
                raise ValueError('Forward/reverse corrected intersection disagreement')
    return origin_rows, destination_columns


def run(before_fields, fields, cache_dir, graph_dir, overlay, output):
    before_fields, fields, cache_dir, output = map(Path, (before_fields, fields, cache_dir, output))
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use an empty correction output directory; existing proof is immutable')
    output.mkdir(parents=True, exist_ok=True)
    contract = json.loads((cache_dir/'contract.json').read_text())
    complete = json.loads((cache_dir/'complete.json').read_text())
    if not complete.get('complete') or contract.get('graph_sha256') != GRAPH_SHA256:
        raise ValueError('A completed original full-graph cache is required')
    correction = pd.read_csv(overlay)
    required = {'source_record_id', 'expected_lat', 'expected_lon', 'corrected_lat', 'corrected_lon'}
    if not required.issubset(correction):
        raise ValueError('Correction registry needs explicit before/after coordinates')
    changed_ids = set(correction.source_record_id.astype(str))
    if not changed_ids or len(changed_ids) != len(correction):
        raise ValueError('Nonempty unique documented correction identities required')
    before_reference = pd.read_parquet(before_fields/FILES['reference_sha256']).set_index('source_record_id')
    after_reference = pd.read_parquet(fields/FILES['reference_sha256']).set_index('source_record_id')
    for point in correction.itertuples(index=False):
        if point.source_record_id not in before_reference.index or point.source_record_id not in after_reference.index:
            raise ValueError('Documented correction is absent from the population reference')
        if not np.allclose(before_reference.loc[point.source_record_id, ['lat', 'lon']].to_numpy(float),
                           [point.expected_lat, point.expected_lon], rtol=0, atol=1e-12):
            raise ValueError('Original point differs from the correction registry')
        if not np.allclose(after_reference.loc[point.source_record_id, ['lat', 'lon']].to_numpy(float),
                           [point.corrected_lat, point.corrected_lon], rtol=0, atol=1e-12):
            raise ValueError('Corrected point differs from the correction registry')
    for key, name in FILES.items():
        if sha(before_fields/name) != contract[key]:
            raise ValueError(f'Before-input SHA differs from exact route contract: {name}')
        if name != 'halo_roster.parquet':
            check_derived_overlay(pd.read_parquet(before_fields/name), pd.read_parquet(fields/name), changed_ids, name)
        derived = pd.read_parquet(fields/name).set_index('source_record_id')
        for identity in sorted(changed_ids & set(derived.index)):
            if not np.allclose(derived.loc[identity, ['lat', 'lon', 'road_node_index', 'snap_km']].to_numpy(float),
                               after_reference.loc[identity, ['lat', 'lon', 'road_node_index', 'snap_km']].to_numpy(float),
                               rtol=0, atol=1e-12, equal_nan=True):
                raise ValueError(f'Corrected derived endpoint differs between input tables: {name}')
    old_origins, new_origins = origins(before_fields), origins(fields)
    old_dest = pd.read_parquet(before_fields/'destinations.parquet')
    new_dest = pd.read_parquet(fields/'destinations.parquet')
    old_halo = pd.read_parquet(before_fields/'halo_roster.parquet').set_index('source_record_id')
    new_halo = pd.read_parquet(fields/'halo_roster.parquet').set_index('source_record_id')
    shared_halo = sorted(set(old_halo.index)&set(new_halo.index))
    check_derived_overlay(old_halo.loc[shared_halo].reset_index().drop(columns=['row_index'], errors='ignore'),
        new_halo.loc[shared_halo].reset_index().drop(columns=['row_index'], errors='ignore'), changed_ids, 'shared_halo')
    old_axis = pd.read_parquet(cache_dir/'origin_axis.parquet')
    dest_axis = pd.read_parquet(cache_dir/'destination_axis.parquet')
    if not old_axis.source_record_id.equals(old_origins.source_record_id) or not dest_axis.source_record_id.equals(old_dest.source_record_id):
        raise ValueError('Saved exact route axes differ from before-input axes')
    cached = np.load(cache_dir/'full_destination_costs.npy', mmap_mode='r')
    if list(cached.shape) != contract['shape'] or cached.shape != (len(old_origins), len(old_dest)):
        raise ValueError('Original route cache shape differs')
    new_ids = set(new_origins.source_record_id)-set(old_origins.source_record_id)
    old_index = dict(zip(old_origins.source_record_id, range(len(old_origins))))
    shared_unchanged = [i for i, identity in enumerate(new_origins.source_record_id)
                        if identity in old_index and identity not in changed_ids]
    old_shared = [old_index[new_origins.iloc[i].source_record_id] for i in shared_unchanged]
    column_mask = ~old_dest.source_record_id.isin(changed_ids).to_numpy()
    before_hash = unaffected_hash(cached, old_shared, column_mask)
    graph = load_graph(graph_dir)
    rows, columns = corrected_costs(graph, new_origins, new_dest, changed_ids, new_ids)
    del graph
    removed_ids = set(old_origins.source_record_id)-set(new_origins.source_record_id)
    old_changed_indices = [old_index[identity] for identity in old_origins.source_record_id
                           if identity in changed_ids or identity in removed_ids]
    changed_col_indices = np.flatnonzero(old_dest.source_record_id.isin(changed_ids)).astype('int64')
    np.savez_compressed(output/'original_changed_costs.npz',
        row_indices=np.asarray(old_changed_indices), rows=np.asarray(cached[old_changed_indices, :]),
        column_indices=changed_col_indices, columns=np.asarray(cached[:, changed_col_indices]))
    np.savez_compressed(output/'corrected_changed_costs.npz',
        row_indices=np.asarray(list(rows)), rows=np.asarray(list(rows.values())),
        column_indices=np.asarray(list(columns)), columns=np.asarray(list(columns.values())).T)
    old_axis.to_parquet(output/'original_origin_axis.parquet', index=False, compression='zstd')
    write_json(output/'original_contract.json', contract)
    temporary = cache_dir/'corrected_full_destination_costs.npy'
    if temporary.exists():
        raise ValueError('An unfinished corrected cache exists; inspect before retrying')
    patched = np.lib.format.open_memmap(temporary, mode='w+', dtype='float64', shape=(len(new_origins), len(new_dest)))
    patched[:] = np.nan
    for start in range(0, len(new_origins), 16):
        new_indices = [i for i in range(start, min(start+16, len(new_origins))) if new_origins.iloc[i].source_record_id in old_index]
        previous = [old_index[new_origins.iloc[i].source_record_id] for i in new_indices]
        patched[new_indices, :] = cached[previous, :]
    for index, values in columns.items():
        patched[:, index] = values
    for index, values in rows.items():
        patched[index, :] = values
    patched.flush()
    after_hash = unaffected_hash(patched, shared_unchanged, column_mask)
    if before_hash != after_hash:
        raise ValueError('Unrelated route costs changed')
    accepted = new_origins.accepted_source_endpoint.eq(True).to_numpy()
    for i in range(len(new_origins)):
        if accepted[i]:
            if np.isnan(patched[i]).any() or (patched[i] < 0).any():
                raise ValueError('Corrected accepted-origin cost row is unknown or negative')
        elif not np.isnan(patched[i]).all():
            raise ValueError('Unknown origin must remain unknown throughout the cost row')
    new_contract = dict(contract)
    for key, name in FILES.items():
        new_contract[key] = sha(fields/name)
    new_contract['shape'] = list(patched.shape)
    new_contract['producer_module_sha256'] = sha(__file__)
    proof = {'complete': True, 'graph_sha256': GRAPH_SHA256, 'overlay_sha256': sha(overlay),
        'source_record_ids': sorted(changed_ids), 'new_halo_origin_ids': sorted(new_ids),
        'coordinate_changes': [{
            'source_record_id': str(point.source_record_id),
            'old_lat': float(point.expected_lat), 'old_lon': float(point.expected_lon),
            'new_lat': float(point.corrected_lat), 'new_lon': float(point.corrected_lon),
            'old_road_node_index': int(before_reference.loc[point.source_record_id, 'road_node_index']),
            'new_road_node_index': int(after_reference.loc[point.source_record_id, 'road_node_index']),
            'old_snap_km': float(before_reference.loc[point.source_record_id, 'snap_km']),
            'new_snap_km': float(after_reference.loc[point.source_record_id, 'snap_km']),
        } for point in correction.itertuples(index=False)],
        'removed_halo_origin_ids': sorted(removed_ids),
        'original_saved_rows_include_removed_halo_origins': True,
        'old_shape': list(cached.shape), 'new_shape': list(patched.shape),
        'corrected_forward_rows': len(rows), 'corrected_reverse_columns': len(columns),
        'unrelated_shared_costs_sha256_before': before_hash, 'unrelated_shared_costs_sha256_after': after_hash,
        'unrelated_shared_costs_exactly_unchanged': True,
        'reverse_summation_numerical_tolerance': {'absolute_minutes': 1e-7, 'relative': 1e-11},
        'original_changed_costs_sha256': sha(output/'original_changed_costs.npz'),
        'corrected_changed_costs_sha256': sha(output/'corrected_changed_costs.npz'),
        'old_input_contract': contract, 'new_input_contract': new_contract,
        'immutable_population_foundation_modified': False}
    del patched, cached
    original_cache = cache_dir/'full_destination_costs_before_coordinate_overlay.npy'
    if original_cache.exists():
        raise ValueError('Original-cache backup already exists')
    (cache_dir/'full_destination_costs.npy').rename(original_cache)
    temporary.rename(cache_dir/'full_destination_costs.npy')
    new_origins[['full_row_index', 'source_record_id', 'origin_scope', 'accepted_source_endpoint']].to_parquet(cache_dir/'origin_axis.parquet', index=False)
    write_json(cache_dir/'contract.json', new_contract)
    complete.update(shape=new_contract['shape'], coordinate_overlay_applied=True)
    write_json(cache_dir/'complete.json', complete)
    write_json(output/'summary.json', proof)
    print(json.dumps(proof, ensure_ascii=False), flush=True)
    return proof


def main():
    parser = argparse.ArgumentParser(__doc__)
    for arg in ('before-fields', 'fields', 'cache-dir', 'graph-dir', 'overlay', 'output'):
        parser.add_argument('--'+arg, type=Path, required=True)
    args = parser.parse_args()
    run(args.before_fields, args.fields, args.cache_dir, args.graph_dir, args.overlay, args.output)


if __name__ == '__main__':
    main()
