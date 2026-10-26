"""Semantic controls for every ownership, eligible choice and level-zero pair.

The control is emitted from a completed independent run, never from desired
counts. Absolute paths and Parquet/ZIP encoding are not scientific identities.
Directed minutes and distances are compared at eight decimal places.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

SCHEMA = 'sgrt.identity_model_control.v3'
DECIMALS = 8
SOURCE_TABLES = {
    'education': ('physical_sites.parquet', 'np_supply.parquet'),
    'commerce': ('sites.parquet', 'supply.parquet'),
    'health': ('physical_sites.parquet', 'np_supply.parquet'),
    'food_host': ('sites.parquet', 'supply.parquet'),
}
ROUTE_SERVICES = ('preschool', 'school_general', 'vocational_education', 'higher_education',
    'comparison_retail', 'daily_food_specialist', 'daily_grocery', 'marketplace_unspecified_assortment',
    'postal_service', 'shopping_centre', 'medical_basic_primary', 'daily_grocery_current_retail_host')


def truth(value, default=True):
    if value is None or pd.isna(value): return default
    return value is True or value == 1 or str(value).strip().lower() in {'true', '1', '1.0', 'yes'}


def scalar(value):
    if value is None or pd.isna(value): return None
    if isinstance(value, (bool, np.bool_)): return bool(value)
    if isinstance(value, (int, np.integer)): return int(value)
    if isinstance(value, (float, np.floating)):
        if not math.isfinite(value): return str(float(value))
        return round(float(value), DECIMALS)
    return str(value)


def table_hash(frame, columns):
    fields = pd.DataFrame({c: frame[c] if c in frame else pd.Series(None, index=frame.index)
                           for c in columns}, index=frame.index)
    # Sort fixed-size row digests, not hundreds of thousands of long JSON
    # strings containing provenance. Multiplicity is preserved; each cell is
    # still included. This keeps the all-row check within a normal worker's RAM.
    rows = sorted(hashlib.sha256(json.dumps([scalar(v) for v in row], ensure_ascii=False,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')).digest()
                  for row in fields.itertuples(index=False, name=None))
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row)
    return {'rows': len(frame), 'columns': columns,
            'hash_method':'sha256_sorted_fixed_size_sha256_row_digests', 'sha256': digest.hexdigest()}


def evidence_fields(frame, base):
    """Include temporal and spatial evidence metadata actually carried by a table."""
    exact = {'source_id', 'source_year', 'observation_year', 'source_snapshot',
             'geometry_identity_resolution', 'raw_geometry_sha256',
             'original_other_positive_census_places', 'original_other_positive_census_place_ids_json',
             'documented_cards_sha256', 'documented_card_json'}
    local_paths={'source_input','provider_source_input','selected_provider_source_input'}
    extra = [c for c in frame.columns if c not in local_paths and (c in exact or any(token in c for token in
        ('historical', 'coordinate_hold', 'coordinate_location_held', 'cartographic_',
         'nested_mask_', 'documented_dated_school_presence'))
        or c.startswith(('provider_source_', 'selected_provider_source_')))]
    return list(dict.fromkeys([*base, *sorted(extra)]))


def source_control(path, *, sites):
    frame = pd.read_parquet(path)
    status = frame.supply_status.isin(['observed', 'proxy'])
    eligible = status.copy()
    for field in ['eligible', 'route_eligible']:
        if field in frame: eligible &= frame[field].map(lambda v: truth(v, default=False))
    external = (frame.default_external_seed_eligible.map(lambda v: truth(v, default=False))
                if 'default_external_seed_eligible' in frame else pd.Series(sites, index=frame.index))
    frame['_semantic_admitted_offer'] = eligible
    frame['_semantic_external_seed_eligible'] = eligible & external
    return table_hash(frame, evidence_fields(frame, ['provider_id', 'service_code', 'source_record_id', 'supply_status',
        'source_record_id_before_identity_repair','np_identity_eligible',
        '_semantic_admitted_offer', '_semantic_external_seed_eligible', 'site_lat', 'site_lon',
        'identity_evidence_tier', 'np_identity_basis', 'need_scope_review_reason',
        'source_education_need_review_reason','source_education_need_review_status',
        'source_education_need_review_conflicting_general_signal','retail_need_scope_review_reason',
        'site_hold_np_presence_review_reason','source_identity_conflict_reason',
        'existing_owner_conflict_requires_review','source_location_conflict_reason',
        'source_location_conflict', 'cartographic_source_dataset', 'cartographic_source_feature_id']))


def build_control(sources, routes, scenario, registry, polygons=None):
    result = {'schema': SCHEMA, 'numeric_decimal_places': DECIMALS,
              'scope': 'all source offers, twelve route layers, admitted choices and registered level-zero identities',
              'source_tables': {}, 'route_tables': {}}
    for domain, files in SOURCE_TABLES.items():
        for index, filename in enumerate(files):
            result['source_tables'][domain + '/' + filename] = source_control(sources / domain / filename, sites=index == 0)
    route_fields = ['origin_id', 'service_code', 'selected_provider_id', 'provider_settlement_id',
                    'cost_minutes', 'known_local_supply', 'zero_cost_np_assumption', 'route_status',
                    'provider_identity_evidence_tier', 'provider_np_identity_basis']
    route_axis = None
    for service in ROUTE_SERVICES:
        path = routes / 'nearest' / (service + '.parquet')
        frame = pd.read_parquet(path)
        if not frame.origin_id.is_unique: raise ValueError('Duplicate route origin: ' + service)
        if set(frame.service_code.dropna()) != {service}: raise ValueError('Unexpected route service: ' + service)
        axis = set(frame.origin_id)
        if route_axis is None: route_axis = axis
        elif axis != route_axis: raise ValueError('Routing layers have different accepted origin universes')
        result['route_tables'][service] = table_hash(frame, evidence_fields(frame, route_fields))
    union_fields = route_fields
    path = routes / 'derived_nearest/daily_grocery_evidence_union.parquet'
    union = pd.read_parquet(path)
    result['grocery_union'] = table_hash(union, evidence_fields(union, union_fields))
    edges = pd.read_parquet(scenario / 'daily_edges.parquet')
    if set(edges.origin_id) != route_axis:
        raise ValueError('The centre scenario and routed origin universe differ')
    admitted = edges[edges.l0_admitted]
    result['all_admitted_choices'] = table_hash(admitted, evidence_fields(admitted, ['origin_id', 'service_family',
        'provider_settlement_id', 'provider_site_id', 'cost_minutes', 'local_service_present',
        'provider_identity_evidence_tier', 'provider_np_identity_basis']))
    centres = pd.read_parquet(registry / 'level0_centres.parquet')
    result['all_registered_centres'] = table_hash(centres, evidence_fields(centres, ['star_id', 'centre_settlement_id',
        'own_known_basic_function_count', 'type_code', 'own_known_basic_functions_json',
        'external_participant_count', 'core_diameter_km', 'ownership_evidence_class',
        'selected_links_with_cartographic_ownership', 'population_budget_partial',
        'own_offer_includes_documented_dated_school_presence', 'own_offer_includes_historical_only_source']))
    members = pd.read_parquet(registry / 'level0_memberships.parquet')
    if members.duplicated(['star_id', 'origin_id']).any(): raise ValueError('Duplicate registered centre/member pair')
    if not set(members.origin_id) <= route_axis:
        raise ValueError('A registered member is outside the routed population axis')
    result['all_registered_memberships'] = table_hash(members, ['star_id', 'centre_settlement_id',
        'origin_id', 'member_role', 'core_family_count', 'core_families_json'])
    summary = json.loads((registry / 'summary.json').read_text())
    if summary.get('registered_level0_centres') != len(centres) or summary.get('centre_member_pairs') != len(members):
        raise ValueError('Registry row counts differ from the scientific summary')
    result['registry_counts'] = {k: v for k, v in summary.items()
        if k not in {'inputs_sha256', 'diameter_km', 'full_centres_diameter_km'}}
    checks = json.loads((routes / 'independent_forward_checks.json').read_text())
    if checks['services'] != len(ROUTE_SERVICES) or checks['cases'] < len(ROUTE_SERVICES) or not checks['all_equal']:
        raise ValueError('Twelve independently checked routing classes are required')
    result['forward_checks'] = {'services': checks['services'], 'cases': checks['cases'], 'all_equal': True}
    if polygons:
        frame = pd.read_parquet(polygons)
        result['all_primary_polygons'] = table_hash(frame, evidence_fields(frame, ['source_feature_id', 'source_shard',
            'source_record_id', 'polygon_identity_status', 'geometry_sha256',
            'other_positive_census_places', 'other_positive_census_place_ids_json', 'mapping_basis']))
    return result


def lambda_names(path, wanted):
    import pyarrow.parquet as pq
    fields = set(pq.ParquetFile(path).schema.names)
    return [name for name in wanted if name in fields]


def compare(actual, expected):
    if actual != expected:
        differing = [k for k in sorted(set(actual) | set(expected)) if actual.get(k) != expected.get(k)]
        raise ValueError('Independent scientific control differs in: ' + ', '.join(differing))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['sources', 'routes', 'scenario', 'registry', 'output']:
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--polygons', type=Path)
    parser.add_argument('--expected', type=Path)
    args = parser.parse_args()
    control = build_control(args.sources, args.routes, args.scenario, args.registry, args.polygons)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(control, ensure_ascii=False, indent=2) + '\n')
    # On failure keep the actual all-row control for diagnosis; never publish.
    if args.expected: compare(control, json.loads(args.expected.read_text()))
    print(json.dumps({'control_equal': bool(args.expected), 'sources': len(control['source_tables']),
                      'routing_classes': len(control['route_tables']),
                      'admitted_choices': control['all_admitted_choices']['rows'],
                      'centre_member_pairs': control['all_registered_memberships']['rows']}))
