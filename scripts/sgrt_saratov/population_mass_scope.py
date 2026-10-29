"""Accepted population mass: ordinary records plus federal territories once.

The census credit flags remain immutable. Accepted federal-territory totals
are added exactly once as coarse external reference anchors. Every declared
road-graph cost is evaluated without a computational distance cutoff. Missing
source endpoints remain explicit bounds rather than invented zero population.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import multiprocessing
import shutil
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.sgrt_mass.routes import load_graph, haversine_km, GRAPH_SHA256
from scripts.sgrt_field_pilot.field_model import kernel

FEDERAL_CSV_PATH = 'data/population/federal_territories.csv'
HALF_TIMES = (5., 10., 15., 20., 30., 40., 60., 80., 120.)
MASS_BASIS = 'accepted_foundation_ordinary_plus_separate_federal_territories_once'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def verify_federal_csv(path, catalog_path):
    catalog = json.loads(Path(catalog_path).read_text())
    spec = next(f for f in catalog['files'] if f['path'] == FEDERAL_CSV_PATH)
    expected = catalog['objects'][spec['blob']]['sha256']
    if Path(path).stat().st_size != spec['bytes'] or sha(path) != expected:
        raise ValueError('Accepted federal-territory source differs from the published foundation')


def mass_sources(reference, federal):
    """Separate field eligibility from all original credit/point-role flags."""
    source = reference.copy()
    if source.source_record_id.duplicated().any():
        raise ValueError('Nonunique population source identity')
    population = pd.to_numeric(source.population_2021, errors='coerce')
    ordinary = (source.population_role.eq('ordinary_settlement_record')
                & source.credit_2021.eq(True) & population.ge(0) & np.isfinite(population))
    selected = federal.loc[federal.census_year.eq(2021)].copy()
    if len(selected) != 2 or set(selected.territory_key) != {'RU-FED-MOW', 'RU-FED-SPB'}:
        raise ValueError('Expected the two accepted federal territories, not other outside-frame areas')
    if selected.population_source_record_id.duplicated().any():
        raise ValueError('Duplicate federal aggregate mass')
    source['eligible_ordinary_field_mass'] = ordinary
    source['eligible_federal_territory_field_mass'] = False
    source['field_mass_2021'] = population.where(ordinary)
    source['field_mass_role'] = np.where(ordinary, 'accepted_ordinary_population', 'not_in_accepted_field_mass')
    source['federal_territory_key'] = pd.Series(None, index=source.index, dtype=object)
    for territory in selected.itertuples(index=False):
        match = source.source_record_id.eq(territory.population_source_record_id)
        if int(match.sum()) != 1 or source.loc[match, 'eligible_ordinary_field_mass'].any():
            raise ValueError('Federal aggregate missing or already counted as ordinary mass')
        if not source.loc[match, 'population_role'].eq('external_context_nonadditive').all():
            raise ValueError('Federal territory must remain an explicit nonordinary context')
        if not np.allclose(population[match], float(territory.territory_population), rtol=0, atol=0):
            raise ValueError('Federal-territory population conflicts with its reference context')
        source.loc[match, 'field_mass_2021'] = float(territory.territory_population)
        source.loc[match, 'eligible_federal_territory_field_mass'] = True
        source.loc[match, 'field_mass_role'] = 'accepted_federal_territory_reference_anchor'
        source.loc[match, 'federal_territory_key'] = territory.territory_key
    source['eligible_field_mass'] = source.eligible_ordinary_field_mass | source.eligible_federal_territory_field_mass
    source['positive_field_mass'] = source.eligible_field_mass & source.field_mass_2021.gt(0)
    source['field_mass_basis'] = MASS_BASIS
    return source


def external_city_costs(graph, origins, anchors):
    """Original i→city cost via a full reverse-graph search, with both connectors."""
    from scipy.sparse.csgraph import dijkstra
    reverse = graph.transpose().tocsr()
    records = []
    for city in anchors.itertuples(index=False):
        if not bool(city.accepted_source_endpoint):
            raise ValueError('Accepted federal mass lacks a transport anchor')
        distance = dijkstra(reverse, directed=True, indices=int(city.road_node_index))
        for origin in origins.itertuples(index=False):
            accepted = bool(origin.accepted_source_endpoint)
            cost = np.nan
            status = 'origin_endpoint_unavailable'
            if accepted:
                cost = float(distance[int(origin.road_node_index)] + 4 * float(origin.snap_km) + 4 * float(city.snap_km))
                if str(origin.source_record_id) == str(city.source_record_id):
                    cost = 0.
                status = 'finite_uncensored_directed_cost' if np.isfinite(cost) else 'unreachable_in_directed_graph_model'
            records.append({'origin_id': str(origin.source_record_id), 'city_id': str(city.source_record_id),
                            'federal_territory_key': str(city.federal_territory_key),
                            'territory_population': float(city.field_mass_2021), 'cost_minutes': cost,
                            'status': status, 'direction': 'origin_to_federal_territory_anchor',
                            'computational_horizon_applied': False,
                            'anchor_is_territorial_reference_not_population_distribution': True})
        print(json.dumps({'event': 'uncensored_federal_territory_costs',
                          'territory': str(city.federal_territory_key), 'origins': len(origins)}), flush=True)
    return pd.DataFrame(records)

_CONTEXT = None


def _init_unbounded(context):
    global _CONTEXT
    _CONTEXT = context
    _CONTEXT['cost_cache'] = np.load(context['cost_cache_path'], mmap_mode='r+')


def _unbounded_origin(index):
    from scipy.sparse.csgraph import dijkstra
    c = _CONTEXT
    origin = c['origins'].iloc[index]
    identity = str(origin.source_record_id)
    if c.get('refresh_from_cache', False):
        costs = np.array(c['cost_cache'][index, :], copy=True)
    else:
        distance = dijkstra(c['graph'], directed=True, indices=int(origin.road_node_index))
        costs = distance[c['dest_nodes']] + c['dest_connectors'] + 4 * float(origin.snap_km)
        del distance
    own_indices = np.flatnonzero(c['dest_ids'] == identity)
    if len(own_indices) != 1:
        raise ValueError('Accepted origin does not have one exact destination identity')
    if c.get('refresh_from_cache', False) and costs[own_indices[0]] != 0.:
        raise ValueError('Cached accepted origin must retain its exact own zero cost')
    costs[own_indices[0]] = 0.
    if np.isnan(costs).any() or (costs < 0).any():
        raise ValueError('Unbounded route returned unknown or negative cost')
    c['cost_cache'][index, :] = costs
    own = c['source_by_id'].loc[identity]
    own_mass = float(own.field_mass_2021) if bool(own.positive_field_mass) else 0.
    own_ordinary = own_mass if bool(own.eligible_ordinary_field_mass) else 0.
    own_federal = own_mass if bool(own.eligible_federal_territory_field_mass) else 0.
    unmapped = c['unmapped']
    lower = haversine_km(float(origin.lat), float(origin.lon), unmapped.lat.to_numpy(float),
                        unmapped.lon.to_numpy(float)) / 130. * 60.
    lower = np.where(np.isfinite(lower), lower, 0.)
    outside_unmapped = c['outside_unmapped']
    outside_lower = haversine_km(float(origin.lat), float(origin.lon), outside_unmapped.lat.to_numpy(float),
                                outside_unmapped.lon.to_numpy(float)) / 130. * 60.
    outside_lower = np.where(np.isfinite(outside_lower), outside_lower, 0.)
    records = []
    city_records = []
    for city_index in c['city_indices']:
        city = c['dest'].iloc[city_index]
        city_records.append({'origin_id': identity, 'city_id': str(city.source_record_id),
            'region': str(city.region), 'population_2021': float(city.population_2021),
            'in_accepted_federal_territory_mass': bool(c['federal_dest'][city_index]),
            'cost_minutes': float(costs[city_index]), 'computational_horizon_applied': False,
            'status': 'finite_uncensored_directed_cost' if np.isfinite(costs[city_index]) else 'unreachable_in_directed_graph_model',
            'direction': 'origin_to_city_context_anchor',
            'anchor_is_territorial_reference_not_population_distribution': True})
    for family in ('exponential', 'gaussian'):
        for half in c['half_times']:
            k = kernel(costs, half, family)
            ordinary = float(np.dot(c['dest_mass'][c['ordinary_dest']], k[c['ordinary_dest']]))
            federal = float(np.dot(c['dest_mass'][c['federal_dest']], k[c['federal_dest']]))
            unmapped_bound = float(np.dot(unmapped.field_mass_2021.to_numpy(float), kernel(lower, half, family)))
            outside_routed = float(np.dot(c['raw_dest_pop'][c['outside_dest']], k[c['outside_dest']]))
            outside_bound = outside_routed + float(np.dot(outside_unmapped.population_2021.to_numpy(float),
                                                           kernel(outside_lower, half, family)))
            crimea = float(np.dot(c['raw_dest_pop'][c['crimea_dest']], k[c['crimea_dest']]))
            sev = float(np.dot(c['raw_dest_pop'][c['sevastopol_dest']], k[c['sevastopol_dest']]))
            for include_self in (True, False):
                ordinary_value = max(0., ordinary - (0. if include_self else own_ordinary))
                federal_value = max(0., federal - (0. if include_self else own_federal))
                value = ordinary_value + federal_value
                own_outside = (float(own.population_2021) if not include_self and not bool(own.eligible_field_mass)
                               and np.isfinite(own.population_2021) and own.population_2021 > 0 else 0.)
                outside = max(0., outside_bound - own_outside)
                records.append({'source_record_id': identity, 'full_row_index': int(index),
                    'kernel': family, 'half_time': float(half), 'include_self': include_self,
                    'value': value, 'known_field': value, 'ordinary_known_field': ordinary_value,
                    'federal_context_field': federal_value, 'own_credited_mass': own_mass,
                    'tail_upper': 0., 'unmapped_mass_upper': unmapped_bound,
                    'unmapped_mass_upper_without_distance_assumption': float(unmapped.field_mass_2021.sum()),
                    'credited_population_without_coordinates_upper': float(c['unlocated_mass']),
                    'accepted_mass_field_upper': value + unmapped_bound,
                    'omitted_published_reference_envelope': outside,
                    'outside_accepted_population_frame_envelope': outside,
                    'outside_frame_routed_reference_contribution': max(0., outside_routed - own_outside),
                    'outside_frame_crimea_routed_reference_contribution': crimea,
                    'outside_frame_sevastopol_routed_reference_contribution': sev,
                    'outside_frame_reference_values_may_overlap': True,
                    'routed_source_population_mass': float(c['dest_mass'][c['mass_dest'] & np.isfinite(costs)].sum()),
                    'routed_mass_source_count': int((c['mass_dest'] & np.isfinite(costs)).sum()),
                    'population_model_scope': 'accepted_ordinary_plus_separate_federal_territories_2021',
                    'source_mass_basis': MASS_BASIS, 'speed_bound_kmh': 130.,
                    'computational_horizon_minutes': np.nan, 'ordinary_source_horizon_minutes': np.nan,
                    'federal_context_costs_uncensored': True,
                    'federal_context_anchor_is_coarse_territory_reference': True,
                    'whole_field_is_unbounded': True,
                    'status': 'exact_unbounded_graph_field_with_unmapped_source_bounds',
                    'published_envelope_respects_include_self': True,
                    'unmapped_distance_bound_is_conditional_on_same_maximum_speed': True})
    return int(index), records, city_records


def _unknown_origin_fields(origin, index, source_by_id):
    own = source_by_id.loc[str(origin.source_record_id)]
    mass = float(own.field_mass_2021) if bool(own.positive_field_mass) else 0.
    return [{'source_record_id': str(origin.source_record_id), 'full_row_index': int(index),
             'kernel': family, 'half_time': half, 'include_self': include_self,
             'value': np.nan, 'known_field': np.nan, 'ordinary_known_field': np.nan,
             'federal_context_field': np.nan, 'own_credited_mass': mass,
             'source_mass_basis': MASS_BASIS, 'whole_field_is_unbounded': True,
             'status': 'origin_endpoint_unavailable'}
            for family in ('exponential', 'gaussian') for half in HALF_TIMES for include_self in (True, False)]


def run_unbounded(fields, federal_csv, graph_dir, catalog_path, output, cost_cache_dir,
                  workers=4, resume=False, refresh_from_cache=False):
    import time
    fields, output, work = Path(fields), Path(output), Path(cost_cache_dir)
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    verify_federal_csv(federal_csv, catalog_path)
    backup = output/'ordinary_horizon480_reference'
    if not backup.exists():
        backup.mkdir()
        for name in ('fields.parquet', 'halo_fields.parquet', 'summary.json'):
            shutil.copyfile(fields/name, backup/name)
    reference = pd.read_parquet(fields/'national_reference_with_endpoints.parquet')
    source = mass_sources(reference, pd.read_csv(federal_csv))
    source.to_parquet(fields/'population_mass_sources.parquet', index=False, compression='zstd')
    regional = pd.read_parquet(fields/'regional_roster.parquet')
    halo = pd.read_parquet(fields/'halo_roster.parquet')
    regional['origin_scope'] = 'regional'
    halo['origin_scope'] = 'halo'
    origins = pd.concat([regional, halo], ignore_index=True)
    origins['full_row_index'] = np.arange(len(origins), dtype='int32')
    if origins.source_record_id.duplicated().any():
        raise ValueError('Regional and halo origins overlap')
    dest = pd.read_parquet(fields/'destinations.parquet')
    graph = None if refresh_from_cache else load_graph(graph_dir)
    by_id = source.set_index('source_record_id')
    matched = by_id.loc[dest.source_record_id]
    cache_path = work/'full_destination_costs.npy'
    contract = {'graph_sha256': GRAPH_SHA256, 'reference_sha256': sha(fields/'national_reference_with_endpoints.parquet'),
                'regional_roster_sha256': sha(fields/'regional_roster.parquet'),
                'halo_roster_sha256': sha(fields/'halo_roster.parquet'),
                'destinations_sha256': sha(fields/'destinations.parquet'),
                'federal_territories_sha256': sha(federal_csv),
                'producer_module_sha256': sha(__file__), 'shape': [len(origins), len(dest)],
                'half_times': list(HALF_TIMES), 'ordinary_and_federal_cost_search_unbounded': True}
    if refresh_from_cache:
        if not json.loads((work/'complete.json').read_text()).get('complete'):
            raise ValueError('Scalar refresh requires a completed exact route pass')
        saved_contract = json.loads((work/'contract.json').read_text())
        # Route results survive a scalar-only refactor, but every frozen route
        # input, axis and model setting must still match. The original cost
        # producer SHA is preserved in contract.json.
        saved_contract.pop('producer_module_sha256')
        compatible_contract = dict(contract)
        compatible_contract.pop('producer_module_sha256')
        if saved_contract != compatible_contract:
            raise ValueError('Cached exact route inputs differ from scalar refresh inputs')
        cache = np.load(cache_path, mmap_mode='r+')
        if list(cache.shape) != contract['shape']:
            raise ValueError('Full destination-cost checkpoint axis differs')
    elif resume:
        if json.loads((work/'contract.json').read_text()) != contract:
            raise ValueError('Unbounded checkpoint inputs or producer code changed')
        cache = np.load(cache_path, mmap_mode='r+')
        if list(cache.shape) != contract['shape']:
            raise ValueError('Full destination-cost checkpoint axis differs')
    else:
        if cache_path.exists():
            raise ValueError('Full cost cache exists; choose a new folder or explicit --resume')
        cache = np.lib.format.open_memmap(cache_path, mode='w+', dtype='float64', shape=(len(origins), len(dest)))
        cache[:] = np.nan
        cache.flush()
        write_json(work/'contract.json', contract)
    unknown_indices = np.flatnonzero(~origins.accepted_source_endpoint.eq(True).to_numpy())
    if not np.isnan(cache[unknown_indices, :]).all():
        raise ValueError('Origins without accepted endpoints must retain entirely unknown cost rows')
    origins[['full_row_index', 'source_record_id', 'origin_scope', 'accepted_source_endpoint']].to_parquet(work/'origin_axis.parquet', index=False)
    dest[['destination_index', 'source_record_id']].to_parquet(work/'destination_axis.parquet', index=False)
    accepted = origins.index[origins.accepted_source_endpoint.eq(True)].tolist()
    chunks = work/'field_chunks'
    chunks.mkdir(exist_ok=True)
    parts = [] if refresh_from_cache else sorted(chunks.glob('fields_*.parquet'))
    completed = 0
    all_fields, all_cities = [], []
    for part_number, part in enumerate(parts):
        if part.name != f'fields_{part_number:04d}.parquet':
            raise ValueError('Noncontiguous unbounded checkpoint')
        frame = pd.read_parquet(part)
        indices = frame.full_row_index.drop_duplicates().astype(int).tolist()
        expected = accepted[completed:completed + len(indices)]
        if indices != expected or len(frame) != 36 * len(indices):
            raise ValueError('Field checkpoint does not match the full route-row axis')
        city_part = chunks/f'cities_{part_number:04d}.parquet'
        if not city_part.exists():
            raise ValueError('Missing federal-cost checkpoint')
        all_fields.extend(frame.to_dict('records'))
        all_cities.extend(pd.read_parquet(city_part).to_dict('records'))
        completed += len(indices)
    context = {'graph': graph, 'refresh_from_cache': refresh_from_cache, 'origins': origins, 'source_by_id': by_id, 'dest': dest,
        'dest_ids': dest.source_record_id.astype(str).to_numpy(),
        'dest_nodes': dest.road_node_index.to_numpy('int64'),
        'dest_connectors': dest.destination_connector_minutes.to_numpy(float),
        'dest_mass': matched.field_mass_2021.to_numpy(float),
        'ordinary_dest': (matched.eligible_ordinary_field_mass & matched.field_mass_2021.gt(0)).to_numpy(bool),
        'federal_dest': matched.eligible_federal_territory_field_mass.to_numpy(bool),
        'mass_dest': matched.positive_field_mass.to_numpy(bool),
        'outside_dest': (~matched.eligible_field_mass & matched.population_2021.gt(0) & np.isfinite(matched.population_2021)).to_numpy(bool),
        'crimea_dest': (dest.region.eq('крым') & matched.population_2021.gt(0).to_numpy()).to_numpy(bool),
        'sevastopol_dest': (dest.region.eq('севастополь') & matched.population_2021.gt(0).to_numpy()).to_numpy(bool),
        'raw_dest_pop': pd.to_numeric(dest.population_2021).to_numpy(float),
        'unmapped': source.loc[source.positive_field_mass & ~source.accepted_source_endpoint.eq(True)],
        'outside_unmapped': source.loc[~source.eligible_field_mass & source.population_2021.gt(0)
             & np.isfinite(source.population_2021) & ~source.accepted_source_endpoint.eq(True)],
        'unlocated_mass': float(source.loc[source.positive_field_mass & (source.lat.isna() | source.lon.isna()), 'field_mass_2021'].sum()),
        'city_indices': np.flatnonzero(dest.region.isin(['москва', 'санкт петербург', 'севастополь']).to_numpy()).tolist(),
        'cost_cache_path': str(cache_path), 'half_times': HALF_TIMES}
    start = time.monotonic()
    pending_fields, pending_cities, pending_count = [], [], 0
    starting_completed = completed
    def consume(results):
        nonlocal completed, pending_fields, pending_cities, pending_count
        for index, rows, cities in results:
            pending_fields.extend(rows)
            pending_cities.extend(cities)
            pending_count += 1
            completed += 1
            if pending_count == 32 or completed == len(accepted):
                cache.flush()
                number = (completed - pending_count) // 32
                city_path = chunks/f'cities_{number:04d}.parquet'
                field_path = chunks/f'fields_{number:04d}.parquet'
                if not refresh_from_cache:
                    pd.DataFrame(pending_cities).to_parquet(city_path, index=False, compression='zstd')
                    pd.DataFrame(pending_fields).to_parquet(field_path.with_suffix('.tmp'), index=False, compression='zstd')
                    field_path.with_suffix('.tmp').replace(field_path)
                all_fields.extend(pending_fields)
                all_cities.extend(pending_cities)
                pending_fields, pending_cities, pending_count = [], [], 0
                elapsed = time.monotonic() - start
                rate = (completed - starting_completed) / elapsed
                progress = {'event': 'exact_unbounded_population_fields', 'completed': completed,
                            'total': len(accepted), 'elapsed_seconds': elapsed,
                            'origins_per_second': rate,
                            'estimated_remaining_seconds': (len(accepted) - completed) / rate,
                            'full_matrix_ready': completed == len(accepted)}
                write_json(work/('scalar_refresh_progress.json' if refresh_from_cache else 'progress.json'), progress)
                print(json.dumps(progress), flush=True)
    remaining = accepted[completed:]
    if workers > 1 and 'fork' in multiprocessing.get_all_start_methods():
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('fork'),
                initializer=_init_unbounded, initargs=(context,)) as executor:
            consume(executor.map(_unbounded_origin, remaining, chunksize=1))
    else:
        _init_unbounded(context)
        consume(map(_unbounded_origin, remaining))
    for index in origins.index[~origins.accepted_source_endpoint.eq(True)]:
        all_fields.extend(_unknown_origin_fields(origins.iloc[index], index, by_id))
    table = pd.DataFrame(all_fields).sort_values(['source_record_id', 'kernel', 'half_time', 'include_self'])
    regional_ids = set(regional.source_record_id)
    table.loc[table.source_record_id.isin(regional_ids)].to_parquet(fields/'fields.parquet', index=False, compression='zstd')
    table.loc[~table.source_record_id.isin(regional_ids)].to_parquet(fields/'halo_fields.parquet', index=False, compression='zstd')
    city_table = pd.DataFrame(all_cities).sort_values(['origin_id', 'city_id'])
    city_table.to_parquet(fields/'external_city_costs.parquet', index=False, compression='zstd')
    selected_suffixes = ['118372', '118308', '116499', '116550', '117415', '117733',
                         '117079', '116610', '117219', '117322']
    selected = origins[origins.source_record_id.str.rsplit(':', n=1).str[-1].isin(selected_suffixes)]
    selected_indices = selected.full_row_index.to_numpy(int)
    selected[['full_row_index', 'source_record_id', 'name', 'origin_scope']].to_parquet(output/'selected_unbounded_origin_axis.parquet', index=False)
    np.savez_compressed(output/'selected_unbounded_full_costs.npz', costs=np.asarray(cache[selected_indices, :]),
                        full_row_indices=selected_indices)
    write_json(output/'selected_unbounded_cost_control.json', {
        'destination_count': len(dest),
        'destination_source_record_ids_sha256': hashlib.sha256(json.dumps(
            dest.source_record_id.astype(str).tolist(), ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest(),
        'destinations_parquet_sha256': sha(fields/'destinations.parquet'),
        'selected_origin_id_by_full_row_index': {
            str(int(row.full_row_index)): str(row.source_record_id)
            for row in selected.itertuples(index=False)},
    })
    summary = json.loads((fields/'summary.json').read_text())
    anchors = source.loc[source.eligible_federal_territory_field_mass]
    summary.update(source_mass_basis=MASS_BASIS,
        ordinary_field_mass=float(source.loc[source.eligible_ordinary_field_mass, 'field_mass_2021'].sum()),
        federal_territory_field_mass=float(anchors.field_mass_2021.sum()),
        known_credited_mass=float(source.field_mass_2021.sum()),
        credited_mass_without_endpoint=float(context['unmapped'].field_mass_2021.sum()),
        credited_mass_without_coordinates=context['unlocated_mass'],
        federal_territory_csv_sha256=sha(federal_csv), federal_territory_costs_uncensored=True,
        population_field_horizon_minutes=None, ordinary_source_horizon_minutes=None,
        whole_population_field_unbounded=True, original_population_credit_flags_unchanged=True,
        functional_nearest_cost_matrix_horizon_minutes=480.,
        population_field_computed_origins=len(accepted), population_field_unknown_origins=len(origins)-len(accepted),
        full_cost_cache_required_in_main_payload=False)
    write_json(fields/'summary.json', summary)
    facts = {key: summary[key] for key in ('source_mass_basis', 'ordinary_field_mass', 'federal_territory_field_mass',
        'known_credited_mass', 'credited_mass_without_endpoint', 'credited_mass_without_coordinates',
        'federal_territory_csv_sha256', 'whole_population_field_unbounded')}
    facts.update(graph_sha256=GRAPH_SHA256, field_rows=len(table), exact_routed_origins=len(accepted),
                 full_cost_cache_shape=list(cache.shape), selected_control_origins=len(selected),
                 original_fields_preserved_at='ordinary_horizon480_reference',
                 source_credit_flags_equal=bool(source.credit_2021.equals(reference.credit_2021)),
                 source_budget_flags_equal=bool(source.budget_population_credit.equals(reference.budget_population_credit)),
                 elapsed_seconds=time.monotonic()-start)
    write_json(output/'mass_scope_summary.json', facts)
    write_json(work/('scalar_refresh_complete.json' if refresh_from_cache else 'complete.json'), {'complete': True, 'shape': list(cache.shape),
        'origin_axis': 'origin_axis.parquet', 'destination_axis': 'destination_axis.parquet',
        'costs': 'full_destination_costs.npy', 'unknown_origins_nan': int((~origins.accepted_source_endpoint.eq(True)).sum()),
        'known_graph_unreachable_cost': 'positive_infinity', 'accepted_self_cost': 0.})
    print(json.dumps(facts, ensure_ascii=False), flush=True)
    return facts


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--fields', type=Path, required=True)
    parser.add_argument('--federal-csv', type=Path, required=True)
    parser.add_argument('--graph-dir', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, default=REPO/'data/catalog.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cost-cache-dir', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--refresh-fields-only', action='store_true',
                        help='Recompute population scalar fields from a completed exact full-cost cache, without routing')
    args = parser.parse_args()
    run_unbounded(args.fields, args.federal_csv, args.graph_dir, args.catalog, args.output,
                  args.cost_cache_dir, args.workers, args.resume, args.refresh_fields_only)


if __name__ == '__main__':
    main()
