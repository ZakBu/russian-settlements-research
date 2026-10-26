#!/usr/bin/env python3
"""Recompute semantic-corrected routes without altering the frozen v1 bundle.

Only exact ID/coordinate geometry from a documented graph cache is reused.
No radius, population weighting, observed trips or territorial grouping added.
"""
from __future__ import annotations
import argparse
import gc
import json
import os
import shutil
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transport import (prepare_provider_rows, reuse_prepared_geometry, nearest_service,
                       origin_geometry_fingerprint, load_graph, sha256)

EDUCATION = ('preschool', 'school_general', 'vocational_education', 'higher_education')
COMMERCE = ('comparison_retail', 'daily_food_specialist', 'daily_grocery',
            'marketplace_unspecified_assortment', 'postal_service', 'shopping_centre')


def changed_rows(before, after):
    """Outer identity join: lost/duplicated origins are errors, not changes."""
    if not before.origin_id.is_unique or not after.origin_id.is_unique:
        raise ValueError('Duplicate route origins')
    if set(before.origin_id) != set(after.origin_id):
        raise ValueError('Changed origin universe')
    fields = ['selected_provider_id', 'provider_settlement_id', 'cost_minutes',
              'unconstrained_nearest_provider_id', 'unconstrained_nearest_cost_minutes']
    old = before.set_index('origin_id').sort_index()
    new = after.set_index('origin_id').sort_index()
    flags = {}
    for field in fields:
        a, b = old[field], new[field]
        if field.endswith('minutes'):
            same = (a.isna() & b.isna()) | np.isclose(a.astype(float), b.astype(float), rtol=0, atol=1e-9, equal_nan=True)
        else:
            same = a.fillna('__NULL__').eq(b.fillna('__NULL__'))
        flags[field + '_changed'] = ~same
    mask = pd.DataFrame(flags).any(axis=1)
    out = old.loc[mask, fields].add_prefix('before_').join(new.loc[mask, fields].add_prefix('after_'))
    for key, value in flags.items(): out[key] = value.loc[mask]
    return out.reset_index(), {key: int(value.sum()) for key, value in flags.items()}


def verify_cache(path, endpoints):
    manifest = path.parent / 'provider_preparation.json'
    info = json.loads(manifest.read_text())
    if info['provider_seeds_sha256'] != sha256(path):
        raise ValueError('Road geometry cache hash mismatch')
    if info['origin_geometry_fingerprint'] != origin_geometry_fingerprint(endpoints):
        raise ValueError('Road geometry cache origin mismatch')
    return info



def export_geometry_cache(source, target, endpoints, providers=None):
    """Portable geometry only; source interpretations are always read afresh."""
    original = verify_cache(source, endpoints)
    keys = ['provider_id', 'source_record_id', 'input_kind', 'site_lat', 'site_lon']
    geometry = ['road_node_index', 'road_osm_node', 'road_snap_lat', 'road_snap_lon', 'snap_km', 'weak_component',
                'nearest_vertex_distance_tie', 'nearest_vertex_tie_osm_ids_json', 'destination_connector_minutes',
                'accepted_snap', 'connector_scenario_kmh', 'road_snap_is_not_a_mapped_driveway', 'snap_limit_km']
    frame = pd.read_parquet(source, columns=keys + geometry).drop_duplicates()
    if providers is not None:
        exact_id = frame.provider_id.isin(set(providers.provider_id))
        np_fallback = frame.input_kind.eq('np') & frame.source_record_id.isin(set(providers.loc[providers.input_kind.eq('np'), 'source_record_id']))
        frame = frame[exact_id | np_fallback].copy()
    target.mkdir(parents=True, exist_ok=True)
    path = target / 'provider_road_seeds.parquet'
    frame.to_parquet(path, index=False, compression='zstd')
    meta = dict(original)
    meta['provider_seeds_sha256'] = sha256(path)
    meta['geometry_only_cache'] = True
    meta['source_cache_sha256'] = sha256(source)
    meta['source_cache_manifest_sha256'] = sha256(source.parent / 'provider_preparation.json')
    meta['exported_columns'] = list(frame.columns)
    meta['source_function_metadata_is_not_reused'] = True
    (target / 'provider_preparation.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
    verify_cache(path, endpoints)
    return path


def retain_source(source, target):
    """Retain exact bytes; an existing unequal file must never be overwritten."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(source) != sha256(target):raise ValueError('Retained source differs: ' + str(target))
        return
    try:os.link(source, target)
    except OSError:shutil.copyfile(source, target)
    if sha256(source) != sha256(target):raise ValueError('Retained source checksum mismatch')

def run(args):
    started = time.monotonic()
    bundle = args.bundle.resolve()
    output = args.output.resolve()
    if output == bundle or bundle in output.parents:
        raise ValueError('Corrected results must be outside frozen input bundle')
    if (output / 'summary.json').exists():
        raise ValueError('Refusing to overwrite a finished rerouting run')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'nearest').mkdir(exist_ok=True)
    (output / 'changes').mkdir(exist_ok=True)
    ep_path = bundle / 'routes/endpoints.parquet'
    ep = pd.read_parquet(ep_path)
    inputs = [ep_path]
    initial_code = {str(p): sha256(p) for p in [Path(__file__), Path(__file__).with_name('transport.py')]}
    initial_hashes = {str(ep_path): sha256(ep_path)}
    configs = [('education', args.education, args.education_cache, 'physical_sites.parquet', 'np_supply.parquet', EDUCATION),
               ('commerce', args.commerce, args.commerce_cache, 'sites.parquet', 'supply.parquet', COMMERCE)]
    if getattr(args, 'medical', None):
        configs.append(('health', args.medical, args.medical_cache,
                        'physical_sites.parquet', 'np_supply.parquet', ('medical_basic_primary',)))
    if getattr(args, 'food_host', None):
        configs.append(('food_host', args.food_host, args.food_host_cache,
                        'sites.parquet', 'supply.parquet', ('daily_grocery_current_retail_host',)))
    source_meta = {}
    rows = []
    graph = load_graph(args.graph_dir)
    reverse = graph.T.tocsr()
    del graph
    gc.collect()
    for domain, folder, cache_path, site_name, supply_name, services in configs:
        if getattr(args,'services',None):
            services = tuple(x for x in services if x in args.services.split(','))
            if not services:continue
        cache_info = verify_cache(cache_path, ep)
        site_path, supply_path = folder / site_name, folder / supply_name
        domain_paths = [site_path, supply_path, cache_path, cache_path.parent / 'provider_preparation.json']
        inputs.extend(domain_paths)
        initial_hashes.update({str(p): sha256(p) for p in domain_paths})
        providers = prepare_provider_rows([(site_path, pd.read_parquet(site_path))],
                                          [(supply_path, pd.read_parquet(supply_path))], ep)
        cached = pd.read_parquet(cache_path)
        providers = reuse_prepared_geometry(providers, cached,
            allow_local_presence_without_geometry=getattr(args,'allow_local_presence_without_geometry',False))
        del cached
        gc.collect()
        compact_cache = export_geometry_cache(cache_path, output/'geometry_cache'/domain, ep, providers)
        # The exact same metadata-plus-geometry merge is checked independently
        # below without feeding duplicated road columns back into the merge.
        fresh = prepare_provider_rows([(site_path, pd.read_parquet(site_path))], [(supply_path, pd.read_parquet(supply_path))], ep)
        recovered = reuse_prepared_geometry(fresh, pd.read_parquet(compact_cache),
            allow_local_presence_without_geometry=getattr(args,'allow_local_presence_without_geometry',False))
        pd.testing.assert_frame_equal(providers, recovered)
        del fresh, recovered
        retain_source(site_path, output/'sources'/domain/site_name)
        retain_source(supply_path, output/'sources'/domain/supply_name)
        source_meta[domain] = {'portable_geometry_cache': str(compact_cache.relative_to(output)), 'compact_geometry_merge_exact': True, 'geometry_reuse_rule': 'exact provider ID and coordinates, or exact census NP ID and coordinates',
                              'road_geometry': cache_info['road_geometry'],
                              'provider_rows': len(providers)}
        for service in services:
            t = time.monotonic()
            result = nearest_service(ep, providers, reverse, service)
            source_hashes = {str(p): sha256(p) for p in [site_path, supply_path, cache_path]}
            result['source_supply_sha256'] = json.dumps(source_hashes, sort_keys=True)
            target = output / 'nearest' / (service + '.parquet')
            result.to_parquet(target, index=False, compression='zstd')
            old_path = bundle / 'routes/nearest' / (service + '.parquet')
            inputs.append(old_path)
            initial_hashes[str(old_path)] = sha256(old_path)
            changes, counts = changed_rows(pd.read_parquet(old_path), result)
            changes.to_parquet(output / 'changes' / (service + '.parquet'), index=False, compression='zstd')
            row = {'domain': domain, 'service_code': service, 'origins': len(result),
                   'known_local': int(result.known_local_supply.sum()),
                   'finite_nearest': int(result.cost_minutes.notna().sum()),
                   'any_route_evidence_change': len(changes), **counts,
                   'output_sha256': sha256(target), 'elapsed_seconds': round(time.monotonic()-t, 3)}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        del providers
        gc.collect()
    final_hashes = {str(p): sha256(p) for p in inputs}
    if final_hashes != initial_hashes:raise ValueError('Source inputs changed during rerouting')
    if initial_code != {p: sha256(Path(p)) for p in initial_code}:raise ValueError('Rerouting code changed during execution')
    meta = {'source_inputs_unchanged': True, 'source_bundle': str(bundle), 'source_inputs_sha256': final_hashes,
            'origin_geometry_fingerprint': origin_geometry_fingerprint(ep), 'source_metadata': source_meta,
            'services': rows, 'observed_trips_validated': False, 'territorial_systems_computed': False,
            'geometry_or_census_changed': False, 'routing_time_cutoff': None,
            'code_sha256': sha256(Path(__file__)), 'transport_code_sha256': sha256(Path(__file__).with_name('transport.py')),
            'elapsed_seconds': round(time.monotonic()-started, 3)}
    (output / 'summary.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ['bundle', 'education', 'commerce', 'education-cache', 'commerce-cache', 'graph-dir', 'output']:
        p.add_argument('--' + flag, type=Path, required=True)
    p.add_argument('--services', help='Optional comma-separated classes; omitted classes are not recalculated')
    p.add_argument('--medical', type=Path, help='Optional corrected medical source folder')
    p.add_argument('--medical-cache', type=Path)
    p.add_argument('--food-host', type=Path)
    p.add_argument('--food-host-cache', type=Path)
    p.add_argument('--allow-local-presence-without-geometry', action='store_true',
                   help='NP aggregates explicitly excluded from external routing need no invented road snap')
    args=p.parse_args()
    if args.medical and not args.medical_cache:p.error('--medical requires --medical-cache')
    if args.food_host and not args.food_host_cache:p.error('--food-host requires --food-host-cache')
    if args.services and (not set(args.services.split(',')) <= set(EDUCATION+COMMERCE+('medical_basic_primary','daily_grocery_current_retail_host'))):
        p.error('Unknown service class in --services')
    run(args)


if __name__ == '__main__': main()
