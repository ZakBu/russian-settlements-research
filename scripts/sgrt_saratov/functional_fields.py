"""Separate functional accessibility, alternatives and overlapping systems.

Provider presence is not capacity. A mapped site with unresolved settlement
identity stays in the physical search. Named local supply is retained at the
settlement scale, without assigning unknown local supply a zero value.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
SERVICE_FAMILIES = {
    'school_general': 'school', 'preschool': 'preschool',
    'vocational_education': 'vocational_education', 'higher_education': 'higher_education',
    'medical_basic_primary': 'medical_basic', 'medical_physician_primary': 'medical_physician',
    'medical_inpatient': 'medical_hospital', 'medical_specialized': 'medical_specialized',
    'medical_hightech_licensed': 'medical_hightech',
    'daily_grocery': 'grocery', 'daily_grocery_current_retail_host': 'grocery',
    'daily_food_specialist': 'food_specialist', 'comparison_retail': 'comparison_retail',
    'shopping_centre': 'shopping_centre', 'parcel_pickup': 'parcel_pickup',
    'marketplace_unspecified_assortment': 'marketplace_unspecified_assortment',
    'postal_service': 'postal_service',
}
BASIC_FAMILIES = ('school', 'medical_basic', 'grocery')
FAMILIES = tuple(dict.fromkeys(SERVICE_FAMILIES.values()))
SOURCE_COLUMNS = [
    'provider_id', 'source_record_id', 'service_code', 'supply_status',
    'eligible', 'eligible_site_supply', 'route_eligible', 'local_supply_eligible',
    'default_external_seed_eligible', 'site_lat', 'site_lon', 'lat', 'lon',
    'provider_name', 'name', 'source_id', 'source_year', 'observation_year',
    'historical_source_only', 'historical_supply_proxy',
    'historical_supply_needs_current_confirmation', 'actual_operational_status_verified',
    'actual_operational_status_checked', 'current_operation_verified',
    'named_child_only_contingent', 'restriction_scope_unknown',
    'medical_need_scope', 'education_need_scope', 'np_identity_basis',
    'location_precision', 'source_pool', 'source_address_locality',
    'source_capacity_numeric', 'capacity_total', 'capacity_unit', 'capacity_verified',
    'source_isced_level', 'source_grades', 'grades_known',
    'region', 'context_region', 'operator', 'source_name',
]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(4 << 20), b''): h.update(b)
    return h.hexdigest()


def truth(s, default=False):
    return s.map(lambda v: default if pd.isna(v) else v is True or v == 1 or str(v).lower() == 'true')


def scalar_true(value):
    return False if pd.isna(value) else value is True or value == 1 or str(value).lower() == 'true'


def read_thin(path):
    names = set(pq.read_schema(path).names)
    return pd.read_parquet(path, columns=[c for c in SOURCE_COLUMNS if c in names])


def normalize_offers(frame, kind, group):
    """Re-evaluate source admission; route_eligible alone is insufficient."""
    x = frame.copy()
    if x.provider_id.isna().any() or x.provider_id.duplicated().any():
        raise ValueError('Source provider IDs must be non-null and unique within source file')
    x['family'] = x.service_code.map(SERVICE_FAMILIES)
    x['input_kind'] = kind
    x['source_group'] = group
    x['admitted_offer'] = x.supply_status.isin(['observed', 'proxy']) & x.family.notna()
    for c in ['eligible', 'eligible_site_supply', 'route_eligible', 'local_supply_eligible']:
        if c in x: x['admitted_offer'] &= truth(x[c])
    x['explicit_child_only'] = truth(x.named_child_only_contingent) if 'named_child_only_contingent' in x else False
    # Whole-population fields cannot use a provider explicitly limited to children.
    medical_child_only = x.explicit_child_only & x.family.fillna('').str.startswith('medical_')
    x['admitted_general_population_offer'] = x.admitted_offer & ~medical_child_only
    x['external_seed_eligible'] = x.admitted_general_population_offer & (
        truth(x.default_external_seed_eligible) if 'default_external_seed_eligible' in x else kind == 'sites')
    x['correctsource_record_id'] = x.source_record_id.astype('string')
    for col, alias in [('site_lat', 'lat'), ('site_lon', 'lon')]:
        if col not in x: x[col] = x[alias] if alias in x else np.nan
    name = pd.Series(pd.NA, index=x.index, dtype='string')
    for c in ['provider_name', 'name', 'source_name']:
        if c in x: name = name.fillna(x[c].astype('string'))
    x['provider_name'] = name
    if 'source_year' not in x: x['source_year'] = x.get('observation_year', pd.NA)
    for c, default in [('historical_source_only', False), ('historical_supply_proxy', False),
                       ('historical_supply_needs_current_confirmation', False),
                       ('actual_operational_status_verified', False), ('restriction_scope_unknown', True)]:
        x[c] = truth(x[c], default) if c in x else default
    x['operation_verified'] = x.actual_operational_status_verified
    for c in ['current_operation_verified']:
        if c in x: x['operation_verified'] |= truth(x[c])
    x['historical_only'] = x.historical_source_only | x.historical_supply_proxy
    x['general_profile_match_required'] = x.family.isin(['medical_specialized', 'medical_hightech', 'medical_hospital'])
    # Counts and unspecified/total capacities are never used as attraction weights.
    x['capacity_used_as_attraction_weight'] = False
    x['catalog_id'] = group + ':' + kind + ':' + x.provider_id.astype(str)
    x['provider_destination_key'] = np.where(x.correctsource_record_id.notna(),
        'np:' + x.correctsource_record_id.fillna('').astype(str), 'site:' + x.catalog_id)
    return x


def prepare_catalog(source_root, output, catalog_path=REPO/'data/identity_catalog_20261026.json'):
    """Build a pinned physical-provider catalogue and distinct NP presence table."""
    source_root, output = Path(source_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(Path(catalog_path).read_text())
    specs = {r['path']: r for r in catalog['files']}
    proofs, inventories, candidates, presence = [], [], [], []
    for group, filename, kinds in [('education', 'physical_sites.parquet', ['sites', 'np']),
                                  ('health', 'physical_sites.parquet', ['sites', 'np']),
                                  ('commerce', 'sites.parquet', ['sites']),
                                  ('food_host', 'sites.parquet', ['sites'])]:
        seedpath = source_root/'geometry_cache'/group/'provider_road_seeds.parquet'
        relative = 'sgrt/identity20261026/routes/geometry_cache/'+group+'/provider_road_seeds.parquet'
        spec = specs[relative]
        if seedpath.stat().st_size != spec['bytes'] or digest(seedpath) != spec['blob']:
            raise ValueError('Pinned geometry seed file differs: '+str(seedpath))
        proofs.append({'catalog_member': relative, 'bytes': spec['bytes'], 'sha256': spec['blob']})
        seeds = pd.read_parquet(seedpath, columns=['provider_id', 'input_kind', 'site_lat', 'site_lon',
            'road_node_index', 'destination_connector_minutes', 'accepted_snap'])
        if seeds.duplicated(['provider_id', 'input_kind']).any(): raise ValueError('Duplicate geometry-cache provider')
        for kind in kinds:
            filename_here = 'np_supply.parquet' if kind == 'np' else filename
            path = source_root/'sources'/group/filename_here
            relative = 'sgrt/identity20261026/routes/sources/'+group+'/'+filename_here
            spec = specs[relative]
            if path.stat().st_size != spec['bytes'] or digest(path) != spec['blob']:
                raise ValueError('Pinned source file differs: '+str(path))
            proofs.append({'catalog_member': relative, 'bytes': spec['bytes'], 'sha256': spec['blob']})
            x = normalize_offers(read_thin(path), kind, group)
            inventories.append(x[['catalog_id', 'provider_id', 'source_group', 'input_kind', 'service_code', 'family',
                'correctsource_record_id', 'supply_status', 'admitted_offer', 'explicit_child_only',
                'admitted_general_population_offer', 'external_seed_eligible']].copy())
            admitted = x[x.admitted_general_population_offer].copy()
            presence.append(admitted[admitted.correctsource_record_id.notna()].copy())
            use = x[x.external_seed_eligible].copy()
            use = use.merge(seeds, on=['provider_id', 'input_kind'], how='left', suffixes=('', '_cached'), validate='one_to_one')
            # A new role or NP identity never permits reuse of a moved physical point.
            for c in ['site_lat', 'site_lon']:
                both = use[c].notna() & use[c+'_cached'].notna()
                if kind == 'sites' and not np.allclose(use.loc[both, c], use.loc[both, c+'_cached'], rtol=0, atol=1e-12):
                    raise ValueError('Physical site moved relative to pinned seed cache')
            use['accepted_snap'] = truth(use.accepted_snap)
            use['road_node_index'] = pd.to_numeric(use.road_node_index, errors='coerce')
            use['destination_connector_minutes'] = pd.to_numeric(use.destination_connector_minutes, errors='coerce')
            use['routable_provider'] = (use.accepted_snap & use.road_node_index.ge(0)
                & np.isfinite(use.road_node_index) & use.destination_connector_minutes.ge(0)
                & np.isfinite(use.destination_connector_minutes))
            for c in ['source_id', 'source_year', 'np_identity_basis', 'location_precision', 'medical_need_scope', 'education_need_scope', 'source_isced_level', 'source_grades', 'grades_known']:
                if c not in use: use[c] = None
                use[c] = use[c].map(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else None if pd.isna(v) else str(v))
            keep = ['catalog_id', 'provider_id', 'family', 'service_code', 'correctsource_record_id', 'provider_destination_key',
                    'source_group', 'input_kind', 'provider_name', 'site_lat', 'site_lon', 'road_node_index',
                    'destination_connector_minutes', 'accepted_snap', 'routable_provider', 'source_id', 'source_year',
                    'historical_only', 'historical_supply_needs_current_confirmation', 'operation_verified',
                    'restriction_scope_unknown', 'general_profile_match_required', 'np_identity_basis', 'location_precision',
                    'medical_need_scope', 'education_need_scope', 'capacity_used_as_attraction_weight']
            candidates.append(use[keep])
    inv = pd.concat(inventories, ignore_index=True)
    providers = pd.concat(candidates, ignore_index=True).sort_values(['family', 'catalog_id']).reset_index(drop=True)
    providers['source_record_id'] = providers.correctsource_record_id
    all_presence = pd.concat(presence, ignore_index=True)
    rows = []
    for (family, sid), g in all_presence.groupby(['family', 'correctsource_record_id'], sort=True):
        def vals(c):
            return json.dumps(sorted(set(str(v) for v in g[c].dropna())), ensure_ascii=False) if c in g else '[]'
        rows.append({'family': family, 'source_record_id': sid, 'known_presence': True,
            'source_id': vals('source_id'), 'source_year': vals('source_year'),
            'provider_records_not_capacity': len(g), 'any_nonhistorical_evidence': bool((~g.historical_only).any()),
            'historical_only': bool(g.historical_only.all()), 'operation_verified': bool(g.operation_verified.any()),
            'restriction_scope_unknown': bool(g.restriction_scope_unknown.any()),
            'representative_catalog_id': str(g.catalog_id.min()), 'observed_flow': False})
    np_presence = pd.DataFrame(rows)
    inv.to_parquet(output/'provider_admission_inventory.parquet', index=False, compression='zstd')
    providers.to_parquet(output/'provider_catalog.parquet', index=False, compression='zstd')
    np_presence.to_parquet(output/'np_function_presence.parquet', index=False, compression='zstd')
    summary = {'schema': 'sgrt.saratov.functional_provider_catalog.v1', 'provider_rows': len(providers),
        'routable_provider_rows': int(providers.routable_provider.sum()),
        'unresolved_np_physical_provider_rows': int(providers.correctsource_record_id.isna().sum()),
        'families': list(FAMILIES), 'known_np_function_pairs': len(np_presence),
        'provider_rows_by_family': providers.groupby('family').size().to_dict(),
        'source_files': proofs, 'source_catalog': 'data/identity_catalog_20261026.json',
        'current_np_identity_comes_from_source_not_geometry_cache': True,
        'capacity_or_facility_count_used_as_attraction_weight': False,
        'observed_trips_established': False}
    (output/'provider_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    prepare_education_scope(source_root, output, catalog_path)
    return summary


def prepare_education_scope(source_root, output, catalog_path=REPO/'data/identity_catalog_20261026.json'):
    """Preserve literal programme tags separately from the immutable route catalogue."""
    specs = {r['path']:r for r in json.loads(Path(catalog_path).read_text())['files']}
    frames = []
    for kind, filename in [('sites','physical_sites.parquet'),('np','np_supply.parquet')]:
        relative = 'sgrt/identity20261026/routes/sources/education/'+filename
        path = Path(source_root)/'sources'/'education'/filename
        spec = specs[relative]
        if path.stat().st_size != spec['bytes'] or digest(path) != spec['blob']:
            raise ValueError('Education scope metadata differs from pinned source')
        x = normalize_offers(read_thin(path), kind, 'education')
        x = x[x.admitted_general_population_offer].copy()
        for c in ['source_isced_level','source_grades','grades_known','education_need_scope']:
            if c not in x: x[c] = None
        frames.append(x[['catalog_id','source_isced_level','source_grades','grades_known','education_need_scope']])
    scope = pd.concat(frames, ignore_index=True)
    scope['grades_known'] = truth(scope.grades_known)
    scope['programme_and_admission_verified'] = False
    scope.to_parquet(Path(output)/'provider_education_scope.parquet', index=False, compression='zstd')
    return scope


def enrich_documented_presence(presence, path):
    """Add named branch-locality evidence, never a fictitious building seed."""
    if path is None: return presence.copy(), pd.DataFrame()
    source = pd.read_csv(path)
    required = {'provider_id', 'source_record_id', 'service_code', 'eligible_np_presence_proxy',
                'physical_route_seed_eligible', 'source_id', 'retrieval_year'}
    if not required <= set(source): raise ValueError('Documented locality evidence lacks provenance')
    if truth(source.physical_route_seed_eligible).any():
        raise ValueError('This intake accepts locality presence only, not invented physical road seeds')
    out = presence.copy(); changes = []
    for r in source.loc[truth(source.eligible_np_presence_proxy)].itertuples(index=False):
        family = SERVICE_FAMILIES.get(r.service_code)
        if family is None: continue
        if pd.isna(r.source_record_id):raise ValueError('Eligible supplementary offer lacks an accepted NP identity')
        historical = scalar_true(getattr(r,'historical_only',False))
        verified = scalar_true(getattr(r,'actual_operational_status_verified',False))
        if historical and verified:raise ValueError('Historical-only source cannot verify current operation')
        match = out.family.eq(family) & out.source_record_id.eq(r.source_record_id)
        old = bool(match.any())
        if old:
            i = out.index[match][0]
            previous = json.loads(out.loc[i, 'source_id'])
            out.loc[i, 'source_id'] = json.dumps(sorted(set(previous + [str(r.source_id)])), ensure_ascii=False)
            out.loc[i, 'historical_only'] = bool(out.loc[i,'historical_only']) and historical
            out.loc[i, 'any_nonhistorical_evidence'] = bool(out.loc[i,'any_nonhistorical_evidence']) or not historical
            out.loc[i, 'operation_verified'] = bool(out.loc[i,'operation_verified']) or verified
        else:
            evidence_year = getattr(r,'source_year','undated_official_page_retrieved_'+str(r.retrieval_year))
            evidence_year = str(evidence_year) if pd.notna(evidence_year) else 'content_date_unknown'
            row = {'family': family, 'source_record_id': str(r.source_record_id), 'known_presence': True,
                'source_id': json.dumps([str(r.source_id)]),
                'source_year': json.dumps([evidence_year]),
                'provider_records_not_capacity': 1, 'any_nonhistorical_evidence': not historical,
                'historical_only': historical, 'operation_verified': verified,
                'restriction_scope_unknown': True, 'representative_catalog_id': str(r.provider_id), 'observed_flow': False}
            out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)
        changes.append({'family': family, 'source_record_id': str(r.source_record_id),
            'known_before_documented_source': old, 'physical_seed_added': False,
            'source_id': str(r.source_id), 'operation_verified': verified,
            'incoming_historical_only':historical})
    if out.duplicated(['family', 'source_record_id']).any(): raise ValueError('Duplicate enriched NP presence')
    return out, pd.DataFrame(changes)


def select_functional_links(roster, presence, candidates, catalog, *, scenario='all_dated_known'):
    """One explicit outcome per origin/family; all equally close destinations retained."""
    if not roster.source_record_id.is_unique: raise ValueError('Origin identities must be unique')
    if catalog.catalog_id.duplicated().any(): raise ValueError('Provider catalogue identities must be unique')
    if scenario not in {'all_dated_known', 'nonhistorical_evidence_only'}: raise ValueError('Unknown evidence scenario')
    scope = presence if scenario == 'all_dated_known' else presence[~presence.historical_only]
    own = {(str(r.source_record_id), str(r.family)): r for r in scope.itertuples(index=False)}
    meta = catalog.set_index('catalog_id')
    c = candidates.copy()
    if len(c):
        if 'catalog_id' not in c: raise ValueError('Physical candidate lacks source identity')
        if not set(c.catalog_id) <= set(meta.index): raise ValueError('Physical candidate not in pinned provider catalogue')
        if c.duplicated(['origin_id', 'family', 'destination_group_key']).any(): raise ValueError('Duplicate destination candidate')
        if (~np.isfinite(c.cost_minutes) | c.cost_minutes.lt(0)).any(): raise ValueError('Invalid candidate cost')
        c['historical_only'] = c.catalog_id.map(meta.historical_only)
        if scenario == 'nonhistorical_evidence_only': c = c[~c.historical_only]
        c = c.sort_values(['origin_id', 'family', 'cost_minutes', 'destination_group_key', 'catalog_id'])
    groups = {k: g for k, g in c.groupby(['origin_id', 'family'], sort=False)} if len(c) else {}
    rows, members = [], []
    for r in roster.itertuples(index=False):
        identity = str(r.source_record_id)
        pop = getattr(r, 'population_2021', getattr(r, 'population', np.nan))
        for family in FAMILIES:
            local = own.get((identity, family))
            options = groups.get((identity, family), c.iloc[:0])
            selected = options.iloc[0] if len(options) else None
            sid = pid = key = source_id = source_year = None
            cost = np.nan; historical = operation = False; restricted = True
            unconstrained = float(selected.cost_minutes) if selected is not None else np.nan
            ties = []
            if local is not None:
                sid, key = identity, 'np:'+identity
                pid, source_id, source_year = local.representative_catalog_id, local.source_id, local.source_year
                cost, historical, operation = 0., bool(local.historical_only), bool(local.operation_verified)
                restricted = bool(local.restriction_scope_unknown)
                status = 'known_local_function_np_zero_cost_assumption'
                ties = [key]
            elif selected is not None:
                detail = meta.loc[selected.catalog_id]
                sid = None if pd.isna(detail.correctsource_record_id) else str(detail.correctsource_record_id)
                pid, key, cost = str(selected.catalog_id), str(selected.destination_group_key), float(selected.cost_minutes)
                source_id, source_year = detail.source_id, detail.source_year
                historical, operation, restricted = bool(detail.historical_only), bool(detail.operation_verified), bool(detail.restriction_scope_unknown)
                status = 'nearest_known_provider_site_np_identity_held' if sid is None else 'nearest_known_provider_in_other_or_same_np'
                ties = sorted(options.loc[np.isclose(options.cost_minutes, cost, atol=1e-10, rtol=0), 'destination_group_key'].astype(str))
            else:
                accepted = bool(getattr(r, 'accepted_source_endpoint', getattr(r, 'road_endpoint_accepted', False)))
                status = 'origin_road_geometry_unknown' if not accepted else 'no_known_eligible_provider_within_computational_horizon'
            alternatives = options[options.destination_group_key.ne(key)] if key is not None else options
            second = float(alternatives.cost_minutes.min()) if len(alternatives) else np.nan
            system = system_id(family, key) if key is not None else None
            row = {'origin_id': identity, 'family': family, 'evidence_scenario': scenario, 'is_primary': len(ties) == 1,
                'provider_settlement_id': sid, 'provider_site_id': pid, 'destination_group_key': key,
                'cost_minutes': cost, 'known_local_supply': local is not None,
                'local_supply_state': 'known_presence' if local is not None else 'unknown_not_absent',
                'unconstrained_nearest_physical_minutes': unconstrained,
                'second_distinct_destination_minutes': second,
                'extra_minutes_if_selected_known_np_unavailable': second-cost if np.isfinite(second) and np.isfinite(cost) else np.nan,
                'primary_destination_tie_count': len(ties), 'coequal_primary_keys_json': json.dumps(ties),
                'unique_primary_destination_in_known_catalogue': len(ties) == 1, 'ambiguous_primary': len(ties) > 1,
                'candidate_destinations_retained': len(options), 'link_kind': status, 'system_id': system,
                'source_id': source_id, 'source_year': source_year, 'historical_only': historical,
                'operation_verified': operation, 'restriction_scope_unknown': restricted,
                'provider_profile_match_required': family in {'medical_specialized', 'medical_hightech', 'medical_hospital'},
                'population_2021': pop, 'demand_status': 'published_positive_population' if pd.notna(pop) and pop > 0 else 'published_zero_population' if pop == 0 else 'population_unknown',
                'specific_institution_choice_established': False, 'observed_flow': False,
                'school_grades_verified': False if family in {'school', 'preschool'} else None,
                'educational_age_group_compatibility_established': False if family in {'school', 'preschool'} else None,
                'provider_inventory_complete': False, 'zero_within_np_is_point_model_assumption': local is not None}
            rows.append(row)
            if ties:
                for destination in ties:
                    target = destination[3:] if destination.startswith('np:') else None
                    members.append({'origin_id': identity, 'family': family, 'evidence_scenario': scenario, 'is_primary': len(ties) == 1,
                        'system_id': system_id(family, destination), 'centre_id': target,
                        'destination_group_key': destination, 'cost_minutes': cost,
                        'membership_status': 'known_local_self' if local is not None else 'coequal_nearest_known_destinations' if len(ties) > 1 else 'nearest_known_destination',
                        'model_choice_unique': len(ties) == 1, 'population_2021': pop,
                        'observed_flow': False, 'historical_only': historical})
    return pd.DataFrame(rows), pd.DataFrame(members)


def system_id(family, destination):
    return 'functional:'+hashlib.sha256((str(family)+'|'+str(destination)).encode()).hexdigest()[:24]


def attach_anchor_quality(links, catalog):
    """Keep NP proxies visibly distinct from sourced physical coordinates."""
    used = set(links.provider_site_id.dropna())
    metadata = {str(r.catalog_id):r._asdict() for r in catalog[catalog.catalog_id.isin(used)].itertuples(index=False)}
    precision, proxy, scope = [],[],[]
    for r in links.itertuples(index=False):
        detail = metadata.get(str(r.provider_site_id),{})
        if r.known_local_supply:
            precision.append('NP_point_local_function_zero_cost_assumption');proxy.append(True)
            scope.append('historical_NP_function_presence_current_operation_unknown' if r.historical_only else 'known_NP_function_presence_specific_site_and_current_operation_not_established')
        elif pd.notna(r.provider_site_id):
            p = detail.get('anchor_precision')
            if pd.isna(p):p = detail.get('location_precision')
            coarse = detail.get('input_kind') in {'np','documented_np_proxy'} or any(
                tag in str(p).lower() for tag in ['settlement_point','np_centroid','locality_proxy','settlement_centroid'])
            precision.append(p if pd.notna(p) else 'source_point_precision_unspecified');proxy.append(coarse)
            if str(r.provider_site_id).startswith('historical_school_code:'):
                scope.append('historical_legal_name_locality_candidate_not_current_school_building')
            elif coarse:
                scope.append('historical_NP_function_candidate_not_current_building' if r.historical_only else 'documented_NP_function_locality_not_geocoded_building')
            else:scope.append('physical_source_point_current_operation_not_established' if not r.operation_verified else 'physical_source_point_with_explicit_operation_evidence')
        else:
            precision.append(None);proxy.append(None);scope.append('destination_not_established')
    result = links.copy()
    result['destination_anchor_precision']=precision
    result['destination_is_np_proxy']=proxy
    result['offer_evidence_scope']=scope
    return result


def documented_campus_proxies(roster, presence, source, regional_costs, providers, candidates):
    """Route newly documented campus localities as explicitly coarse NP proxies.

    Existing physical providers remain primary evidence. Only previously unknown
    locality presence obtains an NP anchor; no building coordinate is invented.
    This enrichment uses supply locations, never the documented assignment edges.
    """
    accepted = providers.loc[providers.correctsource_record_id.notna() & (
        providers.routable_provider.fillna(False) if 'routable_provider' in providers else True)]
    known_all = set(zip(accepted.correctsource_record_id.astype(str), accepted.family.astype(str)))
    current = accepted[~accepted.historical_only]
    known_current = set(zip(current.correctsource_record_id.astype(str), current.family.astype(str)))
    axis = roster.set_index('source_record_id').row_index.to_dict()
    additions, routes = [], []
    source = source.copy()
    source['historical_only'] = truth(source.historical_only) if 'historical_only' in source else False
    source = source.sort_values('historical_only',kind='stable')
    for r in source.itertuples(index=False):
        sid, family = str(r.source_record_id), SERVICE_FAMILIES.get(r.service_code)
        historical = scalar_true(r.historical_only)
        known = known_all if historical else known_current
        if not scalar_true(r.eligible_np_presence_proxy) or (sid, family) in known or sid not in axis:
            continue
        known_all.add((sid,family))
        if not historical:known_current.add((sid,family))
        catalog_id = str(r.provider_id)
        year = getattr(r, 'source_year', None)
        year_label = str(int(year)) if pd.notna(year) and isinstance(year, (int,float,np.number)) else str(year) if pd.notna(year) else 'content_date_unknown' if getattr(r,'intake_kind','documented') == 'supplementary' else 'undated_official_page'
        addition = {'catalog_id': catalog_id, 'provider_id': catalog_id,
            'family': family, 'service_code': r.service_code, 'correctsource_record_id': sid,
            'source_record_id': sid, 'provider_destination_key': 'np:'+sid,
            'source_id': str(r.source_id), 'source_year': year_label,
            'historical_only': historical, 'operation_verified': False, 'restriction_scope_unknown': True,
            'general_profile_match_required': False, 'input_kind': 'documented_np_proxy',
            'source_group': 'official_school_campus' if getattr(r,'intake_kind','documented') == 'documented' else 'supplementary_regional_np_offer', 'provider_name': getattr(r, 'name', sid),
            'location_precision': 'settlement_point_not_building', 'anchor_precision': 'settlement_point_not_building',
            'proxy_reason': 'official_campus_locality_without_accepted_external_provider_anchor',
            'capacity_used_as_attraction_weight': False, 'source_grades': None,
            'grades_known': False, 'education_need_scope': 'grade_coverage_unknown'}
        if getattr(r,'intake_kind','documented') == 'supplementary':
            addition.update({'source_metadata_creation_year':getattr(r,'metadata_creation_year',None),
                'source_metadata_last_modified_year':getattr(r,'metadata_last_modified_year',None),
                'source_grade_name_signal':getattr(r,'grades_name_signal',None),
                'grade_inferred_from_name_not_verified':scalar_true(getattr(r,'grade_inferred_from_name',False))})
        additions.append(addition)
        j = int(axis[sid])
        for origin in roster.itertuples(index=False):
            minutes = float(regional_costs[int(origin.row_index), j])
            if np.isfinite(minutes):
                routes.append({'origin_id': str(origin.source_record_id), 'family': family,
                    'provider_id': catalog_id, 'catalog_id': catalog_id, 'source_record_id': sid,
                    'destination_group_key': 'np:'+sid, 'cost_minutes': minutes,
                    'anchor_precision': 'settlement_point_not_building'})
    combined = pd.concat([candidates, pd.DataFrame(routes)], ignore_index=True)
    combined = combined.sort_values(['cost_minutes', 'catalog_id']).drop_duplicates(
        ['origin_id', 'family', 'destination_group_key']).reset_index(drop=True)
    return pd.concat([providers, pd.DataFrame(additions)], ignore_index=True), combined, pd.DataFrame(additions)


def configuration_groups(links):
    """Exact everyday destination sets, without transitive geographic mergers."""
    rows = []
    basic = links[links.family.isin(BASIC_FAMILIES)]
    for (scenario, origin), group in basic.groupby(['evidence_scenario', 'origin_id'], sort=True):
        by_family = group.set_index('family')
        signature, destinations = [], set()
        for family in BASIC_FAMILIES:
            keys = json.loads(by_family.loc[family, 'coequal_primary_keys_json']) if family in by_family.index else []
            signature.append((family, keys))
            destinations.update(keys)
        known = sum(bool(keys) for _, keys in signature)
        complete = known == len(BASIC_FAMILIES)
        group_id = ('configuration:'+hashlib.sha256(json.dumps(signature, separators=(',', ':')).encode()).hexdigest()[:24]) if complete else None
        status = ('all_three_model_directions_known_single_destination' if complete and len(destinations) == 1 else
            'all_three_model_directions_known_multiple_destinations' if complete else
            'partly_unknown_basic_directions' if known else 'all_basic_directions_unknown')
        resolved = all(key.startswith('np:') for key in destinations)
        rows.append({'origin_id': origin, 'evidence_scenario': scenario, 'basic_configuration_id': group_id,
            'membership_status': status, 'known_basic_direction_count': known,
            'distinct_known_destinations': len(destinations),
            'all_known_destinations_have_np_identity': resolved if destinations else False,
            'destinations_json': json.dumps(sorted(destinations)),
            'primary_tie_present': bool(group.primary_destination_tie_count.gt(1).any()),
            'known_local_basic_function_count': int(group.known_local_supply.sum()),
            'maximum_basic_candidate_minutes': float(group.cost_minutes.max()) if group.cost_minutes.notna().any() else np.nan,
            'actual_inventory_or_flow_completeness_established': False,
            'demographic_type_assigned_here': False})
    return pd.DataFrame(rows)


def functional_potentials(roster, destinations, costs, presence, links, *, horizon=480., half_times=(10., 20., 40., 80.)):
    """Inventory-presence fields, not a Huff/SFCA capacity or flow model."""
    from scipy.sparse import coo_matrix
    dest_index = dict(zip(destinations.source_record_id.astype(str), destinations.destination_index.astype(int)))
    f_index = {f: i for i, f in enumerate(FAMILIES)}
    link_index = {(r.evidence_scenario, str(r.origin_id), str(r.family)):r
        for r in links.itertuples(index=False)}
    results = []
    for scenario in links.evidence_scenario.unique():
        p = presence if scenario == 'all_dated_known' else presence[~presence.historical_only]
        p = p[p.family.isin(FAMILIES)].drop_duplicates(['source_record_id', 'family']).copy()
        p['destination_index'] = p.source_record_id.map(dest_index)
        total = p.groupby('family').size().reindex(FAMILIES, fill_value=0).to_numpy(dtype=float)
        mapped = p[p.destination_index.notna()]
        incidence = coo_matrix((np.ones(len(mapped)),
            (mapped.destination_index.astype(int), mapped.family.map(f_index))), shape=(len(destinations), len(FAMILIES))).tocsr()
        located = np.asarray(incidence.sum(axis=0)).ravel()
        for r in roster.itertuples(index=False):
            ri = int(r.row_index); sid = str(r.source_record_id)
            begin, end = costs.indptr[ri:ri+2]
            cols, minutes = costs.indices[begin:end], costs.data[begin:end]
            if len(minutes) and (np.any(~np.isfinite(minutes)) or np.any(minutes < 0) or np.any(minutes > horizon+1e-8)):
                raise ValueError('Functional costs violate the explicit computational horizon')
            part = incidence[cols]
            reached = np.asarray(part.sum(axis=0)).ravel()
            known_origin = bool(getattr(r, 'accepted_source_endpoint', False))
            local = np.array([bool(link_index[(scenario, sid, f)].known_local_supply) for f in FAMILIES])
            for shape in ['exponential', 'gaussian']:
                for half in half_times:
                    if half <= 0 or not np.isfinite(half): raise ValueError('Invalid half-time scenario')
                    weight = np.exp2(-minutes/half if shape == 'exponential' else -(minutes/half)**2)
                    lower = np.asarray(part.T.dot(weight)).ravel()
                    tail_factor = float(np.exp2(-horizon/half if shape == 'exponential' else -(horizon/half)**2))
                    tail = np.maximum(0, located-reached)*tail_factor
                    unlocated = total-located
                    if not known_origin:
                        lower = local.astype(float)
                        upper = total.copy()
                    else: upper = lower+tail+unlocated
                    for fi, family in enumerate(FAMILIES):
                        link = link_index[(scenario, sid, family)]
                        nearest = link.cost_minutes
                        access = float(np.exp2(-nearest/half if shape == 'exponential' else -(nearest/half)**2)) if pd.notna(nearest) else np.nan
                        results.append({'origin_id': sid, 'family': family, 'evidence_scenario': scenario,
                            'kernel': shape, 'half_time_minutes': float(half),
                            'known_np_offer_potential': float(lower[fi]) if known_origin else np.nan,
                            'known_np_offer_potential_lower': float(lower[fi]),
                            'known_np_offer_potential_upper': float(upper[fi]),
                            'own_known_np_function_presence': int(local[fi]),
                            'external_known_np_offer_potential_lower': max(0., float(lower[fi])-int(local[fi])),
                            'external_known_np_offer_potential_upper': max(0., float(upper[fi])-int(local[fi])),
                            'known_np_function_offer_count': int(total[fi]),
                            'routed_np_offer_count_within_horizon': int(reached[fi]),
                            'known_np_offers_without_destination_endpoint': int(unlocated[fi]),
                            'nearest_known_offer_access_score': access,
                            'nearest_known_offer_minutes': nearest,
                            'origin_route_geometry_known': known_origin,
                            'source_inventory_complete': False,
                            'upper_bounds_cover_known_catalogue_only': True,
                            'all_existing_offers_potential_upper': np.nan,
                            'potential_unit': 'weighted_distinct_known_NP_function_presence_not_capacity',
                            'physical_held_sites_retained_in_nearest_search': True,
                            'functional_fields_summed_together': False,
                            'observed_flow': False})
    return pd.DataFrame(results)


def summarize_units(members, roster):
    origins = set(roster.source_record_id.astype(str))
    units = []
    for (scenario, system), g in members.groupby(['evidence_scenario', 'system_id'], sort=True):
        family, key = g.family.iloc[0], g.destination_group_key.iloc[0]
        centre = key[3:] if key.startswith('np:') else None
        positive = g.population_2021.gt(0)
        external = g.origin_id.ne(centre) if centre is not None else pd.Series(True, index=g.index)
        units.append({'system_id': system, 'family': family, 'evidence_scenario': scenario,
            'centre_id': centre, 'destination_group_key': key, 'member_records': len(g),
            'positive_population_member_records': int(positive.sum()),
            'external_positive_population_member_records': int((positive & external).sum()),
            'maximum_selected_minutes': float(g.cost_minutes.max()),
            'median_selected_minutes': float(g.cost_minutes.median()),
            'maximum_selected_minutes_scope':'all_model_members_including_zero_or_unknown_population',
            'median_selected_minutes_scope':'all_model_members_including_zero_or_unknown_population',
            'maximum_external_positive_minutes':float(g.loc[positive&external,'cost_minutes'].max()) if (positive&external).any() else np.nan,
            'median_external_positive_minutes':float(g.loc[positive&external,'cost_minutes'].median()) if (positive&external).any() else np.nan,
            'centre_np_identity_known': centre is not None,
            'centre_in_regional_origin_axis': centre in origins if centre is not None else False,
            'ambiguous_memberships': int((~g.model_choice_unique).sum()),
            'localness_not_decided_by_search_horizon': True,
            'observed_catchment_established': False})
    return pd.DataFrame(units)


def documented_assignment_comparison(links, path, inventory_scenario):
    source = pd.read_csv(path)
    x = source[source.origin_id.notna()].copy()
    school = links[links.family.eq('school') & links.evidence_scenario.eq('all_dated_known')]
    x = x.merge(school[['origin_id', 'provider_settlement_id', 'cost_minutes',
        'coequal_primary_keys_json', 'known_local_supply', 'link_kind']], on='origin_id', how='left', validate='one_to_one')
    x['documented_campus_in_model_primary_set'] = x.apply(lambda r:
        'np:'+str(r.campus_id) in json.loads(r.coequal_primary_keys_json)
        if isinstance(r.coequal_primary_keys_json, str) else False, axis=1)
    x['inventory_scenario'] = inventory_scenario
    x['assignment_used_to_select_decay_or_force_model_destination'] = False
    x['campus_supply_from_same_document_used'] = inventory_scenario != 'baseline_known_inventory'
    x['comparison_is_observed_journey_validation'] = False
    return x


def settlement_roles(roster, links, members, configurations):
    """Explain every current NP's modeled role without a population threshold."""
    rows = []
    for scenario in links.evidence_scenario.unique():
        l = links[links.evidence_scenario.eq(scenario)]
        m = members[members.evidence_scenario.eq(scenario)]
        c = configurations[configurations.evidence_scenario.eq(scenario)].set_index('origin_id')
        external = m[m.population_2021.gt(0) & m.centre_id.notna() & m.origin_id.ne(m.centre_id)]
        incoming = {sid:g for sid,g in external.groupby('centre_id')}
        by_origin = {sid:g for sid,g in l.groupby('origin_id')}
        for r in roster.itertuples(index=False):
            sid = str(r.source_record_id); own = by_origin[sid]
            inc = incoming.get(sid, m.iloc[:0])
            basic_local = own[own.family.isin(BASIC_FAMILIES)].known_local_supply
            role = ('known_local_multifunctional_centre_with_modelled_external_users'
                if basic_local.sum() == 3 and len(inc) else
                'known_functional_centre_with_modelled_external_users' if len(inc) else
                'known_local_functions_without_modelled_external_users' if own.known_local_supply.any() else
                'local_functions_unknown_not_absent')
            rows.append({'source_record_id':sid, 'evidence_scenario':scenario,
                'modelled_role':role, 'known_local_basic_function_count':int(basic_local.sum()),
                'known_local_family_count':int(own.known_local_supply.sum()),
                'external_positive_origins_at_least_one_family':int(inc.origin_id.nunique()),
                'external_positive_origin_family_memberships':len(inc),
                'external_user_families_json':json.dumps(sorted(inc.family.unique().tolist())),
                'configuration_status':c.loc[sid,'membership_status'],
                'basic_configuration_id':c.loc[sid,'basic_configuration_id'],
                'population_2021':r.population_2021,
                'own_population_used_to_impose_centre_order':False,
                'observed_external_user_flows_established':False})
    return pd.DataFrame(rows)


def family_distance_summary(links, units):
    rows = []
    for (scenario, family), g in links.groupby(['evidence_scenario','family'], sort=True):
        live = g[g.population_2021.gt(0)]
        external = live[~live.known_local_supply & live.cost_minutes.notna()]
        u = units[units.evidence_scenario.eq(scenario) & units.family.eq(family)]
        rows.append({'evidence_scenario':scenario,'family':family,
            'regional_origin_records':len(g),'published_positive_population_origins':len(live),
            'positive_origins_known_local_supply':int(live.known_local_supply.sum()),
            'positive_origins_nearest_external_known':len(external),
            'positive_origins_destination_unknown':int(live.cost_minutes.isna().sum()),
            'median_external_candidate_minutes':float(external.cost_minutes.median()) if len(external) else None,
            'p90_external_candidate_minutes':float(external.cost_minutes.quantile(.9)) if len(external) else None,
            'maximum_external_candidate_minutes':float(external.cost_minutes.max()) if len(external) else None,
            'systems_with_external_positive_members':int(u.external_positive_population_member_records.gt(0).sum()),
            'modelled_time_distribution_is_observed_trip_distribution':False,
            **{f'positive_origins_candidate_within_{h}_minutes':int(live.cost_minutes.le(h).sum())
               for h in [5,10,15,20,30,45,60,90]}})
    return pd.DataFrame(rows)


def loss_counterfactual(roster, links, candidates):
    """Remove one known destination per function; do not infer actual relocations."""
    population = {str(r.source_record_id):r._asdict() for r in roster.itertuples(index=False)}
    options = {}
    for r in candidates.itertuples(index=False):
        options.setdefault((str(r.origin_id),str(r.family)),[]).append((float(r.cost_minutes),str(r.destination_group_key)))
    rows = []
    for r in links.itertuples(index=False):
        source = population[r.origin_id]
        credited = (source.get('budget_population_credit') == 1 and source.get('credit_2021') == 1
            and pd.notna(source['population_2021']) and source['population_2021'] > 0)
        own_options = options.get((r.origin_id,r.family),[])
        keys = json.loads(r.coequal_primary_keys_json) or [None]
        for key in keys:
            alternative = [(minutes,destination) for minutes,destination in own_options if destination != key] if key is not None else []
            next_time = min((minutes for minutes,_ in alternative),default=np.nan)
            # Other coequal primaries survive a single-centre loss even if one
            # selected representative was needed for the tabular link record.
            if key is not None and len(keys) > 1:
                next_time = min(next_time, float(r.cost_minutes)) if np.isfinite(next_time) else float(r.cost_minutes)
            next_keys = sorted(destination for minutes,destination in alternative if abs(minutes-next_time) <= 1e-10) if np.isfinite(next_time) else []
            status = ('primary_direction_unknown_counterfactual_undefined' if key is None else
                'known_distinct_alternative_within_computational_horizon' if np.isfinite(next_time) else
                'no_known_distinct_alternative_within_computational_horizon_not_proof_of_absence')
            rows.append({'origin_id':r.origin_id,'family':r.family,'evidence_scenario':r.evidence_scenario,
                'removed_destination_group_key':key,
                'removed_centre_id':key[3:] if key is not None and key.startswith('np:') else None,
                'origin_distinct_from_known_centre':r.origin_id != key[3:] if key is not None and key.startswith('np:') else None,
                'removed_unit_scope':'all_known_sites_of_function_in_named_NP' if key is not None and key.startswith('np:') else 'one_identity_held_physical_site' if key is not None else 'undefined',
                'baseline_minutes':r.cost_minutes,'alternative_minutes':next_time,
                'additional_minutes':max(0.,next_time-float(r.cost_minutes)) if np.isfinite(next_time) and pd.notna(r.cost_minutes) else np.nan,
                'alternative_destination_keys_json':json.dumps(next_keys),
                'alternative_np_identity_unresolved':any(not k.startswith('np:') for k in next_keys),
                'unresolved_sites_may_belong_to_removed_np':bool(key is not None and key.startswith('np:')),
                'alternative_status':status,'primary_destination_tie_count':r.primary_destination_tie_count,
                'coequal_primary_is_unique_observed_demand_assignment':False,
                'population_2021_published':source['population_2021'],
                'credited_positive_population_2021':float(source['population_2021']) if credited else np.nan,
                'population_credit_eligible':bool(credited),
                'actual_service_closure_or_population_relocation_established':False,
                'unknown_unrecorded_alternatives_may_exist':True})
    detail = pd.DataFrame(rows)
    summaries = []
    for (scenario,family,key),g in detail[detail.removed_destination_group_key.notna()].groupby(
            ['evidence_scenario','family','removed_destination_group_key'],sort=True):
        if g.origin_id.duplicated().any():raise ValueError('Duplicate origin in one destination-loss counterfactual')
        positive = g[g.population_2021_published.gt(0)]
        credited = positive[positive.population_credit_eligible]
        external = credited[credited.origin_distinct_from_known_centre.eq(True)]
        summaries.append({'evidence_scenario':scenario,'family':family,'removed_destination_group_key':key,
            'removed_centre_id':g.removed_centre_id.iloc[0],
            'positive_origin_records':len(positive),'credited_positive_origin_records':len(credited),
            'credited_positive_population_2021':float(credited.credited_positive_population_2021.sum()),
            'external_credited_positive_origin_records':len(external),
            'external_credited_positive_population_2021':float(external.credited_positive_population_2021.sum()),
            'external_credited_population_with_additional_more_than_15_minutes':float(external.loc[external.additional_minutes.gt(15),'credited_positive_population_2021'].sum()),
            'external_credited_population_without_known_alternative_within_horizon':float(external.loc[external.alternative_minutes.isna(),'credited_positive_population_2021'].sum()),
            'credited_population_without_known_alternative_within_horizon':float(credited.loc[credited.alternative_minutes.isna(),'credited_positive_population_2021'].sum()),
            'credited_population_with_additional_more_than_15_minutes':float(credited.loc[credited.additional_minutes.gt(15),'credited_positive_population_2021'].sum()),
            'credited_population_with_additional_more_than_30_minutes':float(credited.loc[credited.additional_minutes.gt(30),'credited_positive_population_2021'].sum()),
            'maximum_additional_known_minutes':float(positive.additional_minutes.max()) if positive.additional_minutes.notna().any() else None,
            'median_additional_known_minutes':float(positive.additional_minutes.median()) if positive.additional_minutes.notna().any() else None,
            'population_may_not_be_summed_across_functions_or_coequal_centres':True,
            'counterfactual_conditioned_on_incomplete_known_inventory':True})
    return detail,pd.DataFrame(summaries)


def basic_centre_profiles(roster, members, presence, reference=None):
    """One NP-centre and one origin per centre across the three basic families."""
    population = {str(r.source_record_id):r._asdict() for r in roster.itertuples(index=False)}
    context = population.copy()
    if reference is not None:
        context.update({str(r.source_record_id):r._asdict() for r in reference.itertuples(index=False)})
        context.update(population)
    rural_types = {'село','посёлок','деревня','хутор','станция','железнодорожный объект',
        'железнодорожный разъезд','железнодорожная станция'}
    m = members[members.family.isin(BASIC_FAMILIES) & members.centre_id.notna()
        & members.origin_id.ne(members.centre_id) & members.population_2021.gt(0)].copy()
    union = []
    for (scenario,centre,origin),g in m.groupby(['evidence_scenario','centre_id','origin_id'],sort=True):
        r = population[str(origin)];pop = r['population_2021']
        credited = r.get('budget_population_credit') == 1 and r.get('credit_2021') == 1 and pd.notna(pop) and pop > 0
        rural = r.get('settlement_type_2021') in rural_types
        urban = r.get('settlement_type_2021') in {'город','пгт','посёлок городского типа','рабочий посёлок'}
        union.append({'evidence_scenario':scenario,'centre_id':centre,'origin_id':origin,
            'contributing_families_json':json.dumps(sorted(g.family.unique().tolist())),
            'contributing_basic_family_count':g.family.nunique(),
            'minimum_contributing_minutes':float(g.cost_minutes.min()),
            'maximum_contributing_minutes':float(g.cost_minutes.max()),
            'all_contributing_choices_unique_in_known_catalogue':bool(g.model_choice_unique.all()),
            'any_ambiguous_primary':bool((~g.model_choice_unique).any()),
            'population_2021_published':pop,'population_credit_eligible':bool(credited),
            'credited_population_2021':float(pop) if credited else np.nan,
            'rural_population_status':'rural' if rural else 'urban' if urban else 'settlement_kind_unknown',
            'credited_rural_population_2021':float(pop) if credited and rural else np.nan,
            'source_population_missing':pd.isna(pop),'observed_external_user_flow':False,
            'one_origin_can_belong_to_multiple_centres':True})
    if not union:
        return (pd.DataFrame(columns=['evidence_scenario','centre_id','centre_in_regional_roster',
                    'known_own_basic_function_count','external_positive_origin_count',
                    'external_credited_rural_population_2021']),
                pd.DataFrame(columns=['evidence_scenario','centre_id','origin_id',
                    'contributing_families_json','population_credit_eligible']))
    unique = pd.DataFrame(union)
    presence = presence[presence.family.isin(BASIC_FAMILIES) & presence.source_record_id.isin(unique.centre_id)]
    profiles = []
    for (scenario,centre),g in unique.groupby(['evidence_scenario','centre_id'],sort=True):
        if g.origin_id.duplicated().any():raise ValueError('Duplicate external origin in basic centre union')
        p = presence if scenario == 'all_dated_known' else presence[~presence.historical_only]
        local_families = set(p.loc[p.source_record_id.eq(centre)&p.family.isin(BASIC_FAMILIES),'family'])
        info = context.get(str(centre),{})
        profile = {'evidence_scenario':scenario,'centre_id':centre,
            'centre_name':info.get('name'),'centre_population_2021':info.get('population_2021'),
            'centre_settlement_type_2021':info.get('settlement_type_2021'),
            'centre_in_regional_roster':centre in population,
            'known_own_basic_function_count':len(local_families),
            'known_own_basic_functions_json':json.dumps(sorted(local_families)),
            'external_positive_origin_count':len(g),
            'external_credited_positive_origin_count':int(g.population_credit_eligible.sum()),
            'external_uncredited_positive_origin_count':int((~g.population_credit_eligible).sum()),
            'external_published_population_unknown_origin_count':int(g.source_population_missing.sum()),
            'external_rural_positive_origin_count':int(g.rural_population_status.eq('rural').sum()),
            'external_settlement_kind_unknown_count':int(g.rural_population_status.eq('settlement_kind_unknown').sum()),
            'external_credited_population_2021':float(g.credited_population_2021.sum()),
            'external_credited_rural_population_2021':float(g.credited_rural_population_2021.sum()),
            'external_uncredited_rural_origin_count':int((g.rural_population_status.eq('rural') & ~g.population_credit_eligible).sum()),
            'external_rural_population_summary_complete':bool((g.rural_population_status.eq('rural') <= g.population_credit_eligible).all() and not g.rural_population_status.eq('settlement_kind_unknown').any()),
            'external_ambiguous_primary_origin_count':int(g.any_ambiguous_primary.sum()),
            'contributing_families_are_not_independent_population_totals':True,
            'population_may_not_be_summed_across_centres':True,
            'exclusive_regional_partition_established':False,
            'observed_service_catchment_established':False,
            'modelled_role':'known_basic_function_centre_with_external_model_candidates',
            'missing_own_functions_mean_unknown_not_absent':True,
            'centre_order_assigned_from_population':False}
        for family in BASIC_FAMILIES:
            f = m[m.evidence_scenario.eq(scenario)&m.centre_id.eq(centre)&m.family.eq(family)]
            profile[family+'_external_positive_origin_count'] = f.origin_id.nunique()
            profile[family+'_median_external_minutes'] = float(f.cost_minutes.median()) if len(f) else np.nan
            profile[family+'_maximum_external_minutes'] = float(f.cost_minutes.max()) if len(f) else np.nan
            profile[family+'_median_external_positive_minutes'] = profile[family+'_median_external_minutes']
            profile[family+'_maximum_external_positive_minutes'] = profile[family+'_maximum_external_minutes']
            profile[family+'_external_minutes_scope'] = 'external_members_with_published_positive_population_2021'
            profile[family+'_own_presence_known'] = family in local_families
        profiles.append(profile)
    return pd.DataFrame(profiles),unique


def build_functional_results(fields_root, provider_root, output, *, documented_presence=None,
                             documented_assignments=None, current_candidates=None,
                             supplementary_presence=None, supplementary_provider_catalog=None,
                             supplementary_candidates=None, single_inventory=None):
    from scipy.sparse import load_npz
    fields_root, provider_root, output = Path(fields_root), Path(provider_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    roster = pd.read_parquet(fields_root/'regional_roster.parquet')
    destinations = pd.read_parquet(fields_root/'destinations.parquet')
    costs = load_npz(fields_root/'destination_costs.npz')
    base_providers = pd.read_parquet(provider_root/'provider_catalog.parquet')
    base_presence = pd.read_parquet(provider_root/'np_function_presence.parquet')
    base_candidates = pd.read_parquet(fields_root/'physical_provider_candidates.parquet')
    variants = [('baseline_known_inventory', base_presence, base_providers, base_candidates)]
    changes = pd.DataFrame(); proxies = pd.DataFrame()
    additional_physical = pd.DataFrame();additional_candidates = pd.DataFrame()
    if supplementary_provider_catalog is not None:
        if supplementary_candidates is None:raise ValueError('Additional physical providers need separately routed candidates')
        additional_physical = pd.read_parquet(supplementary_provider_catalog)
        additional_candidates = pd.read_parquet(supplementary_candidates)
        required = {'catalog_id','family','correctsource_record_id','source_id','source_year',
            'historical_only','operation_verified','restriction_scope_unknown','provider_destination_key'}
        if not required <= set(additional_physical):raise ValueError('Supplementary physical metadata incomplete')
        if additional_physical.catalog_id.duplicated().any() or set(additional_physical.catalog_id)&set(base_providers.catalog_id):
            raise ValueError('Supplementary physical identities duplicate existing catalogue')
        if not set(additional_physical.family) <= set(FAMILIES):raise ValueError('Unknown supplementary physical family')
        if not set(additional_candidates.catalog_id) <= set(additional_physical.catalog_id):
            raise ValueError('Additional routes do not belong to supplementary physical catalogue')
        extra_meta = additional_physical.set_index('catalog_id')
        if not additional_candidates.family.eq(additional_candidates.catalog_id.map(extra_meta.family)).all():
            raise ValueError('Additional route function differs from its source provider')
        if not additional_candidates.destination_group_key.eq(additional_candidates.catalog_id.map(extra_meta.provider_destination_key)).all():
            raise ValueError('Additional route destination identity differs from its source provider')
        additional_physical.to_parquet(output/'additional_physical_providers.parquet',index=False,compression='zstd')
        additional_candidates.to_parquet(output/'additional_physical_candidates.parquet',index=False,compression='zstd')
    if documented_presence is not None or supplementary_presence is not None or supplementary_provider_catalog is not None:
        paths = documented_presence if isinstance(documented_presence, (list, tuple)) else [documented_presence]
        paths = [p for p in paths if p is not None]
        supplementary_paths = supplementary_presence if isinstance(supplementary_presence,(list,tuple)) else [supplementary_presence]
        supplementary_paths = [p for p in supplementary_paths if p is not None]
        if len(additional_physical):
            named = additional_physical[additional_physical.correctsource_record_id.notna()].copy()
            inverse_family = {v:k for k,v in SERVICE_FAMILIES.items()}
            intake = pd.DataFrame({'provider_id':named.catalog_id,'source_record_id':named.correctsource_record_id,
                'service_code':named.family.map(inverse_family),'source_id':named.source_id,
                'source_year':named.source_year,'retrieval_year':2026,
                'eligible_np_presence_proxy':True,'physical_route_seed_eligible':False,
                'historical_only':named.historical_only,'actual_operational_status_verified':named.operation_verified})
            physical_intake_path = output/'additional_physical_np_presence.csv'
            intake.to_csv(physical_intake_path,index=False)
            supplementary_paths.append(physical_intake_path)
        source = pd.concat([pd.read_csv(p).assign(intake_kind='documented' if p in paths else 'supplementary')
            for p in paths+supplementary_paths], ignore_index=True)
        if source.provider_id.duplicated().any():raise ValueError('Duplicate documentary provider identity')
        presence = base_presence.copy(); change_frames = []
        for path in paths+supplementary_paths:
            presence, ch = enrich_documented_presence(presence, path)
            change_frames.append(ch)
        changes = pd.concat(change_frames, ignore_index=True)
        source_providers = pd.concat([base_providers,additional_physical],ignore_index=True) if len(additional_physical) else base_providers
        source_candidates = pd.concat([base_candidates,additional_candidates],ignore_index=True) if len(additional_candidates) else base_candidates
        source_candidates = source_candidates.sort_values(['cost_minutes','catalog_id']).drop_duplicates(['origin_id','family','destination_group_key'])
        providers, candidates, proxies = documented_campus_proxies(roster, base_presence,
            source, np.load(fields_root/'regional_costs.npy'), source_providers, source_candidates)
        variants.append(('documented_campus_enrichment', presence, providers, candidates))
        if supplementary_paths or supplementary_provider_catalog is not None:
            variants = [('official_regional_source_sensitivity',presence,providers,candidates)]
    if single_inventory is not None:
        if single_inventory == 'physical_official_enrichment' and supplementary_provider_catalog is None:
            raise ValueError('Physical enrichment requires the additional physical-provider source')
        _,presence,providers,candidates=variants[-1]
        variants=[(str(single_inventory),presence,providers,candidates)]
    summaries = []
    for vi, (inventory_scenario, presence, providers, candidates) in enumerate(variants):
        print(json.dumps({'event':'functional_inventory_started','inventory_scenario':inventory_scenario}),flush=True)
        links, members = select_functional_links(roster, presence, candidates, providers)
        if current_candidates is not None:
            current = pd.read_parquet(current_candidates)
            changed = set(providers.loc[providers.historical_only, 'family'])
            current_proxy_ids = set(proxies.loc[~proxies.historical_only,'catalog_id']) if len(proxies) else set()
            current_physical_ids = set(additional_physical.loc[~additional_physical.historical_only,'catalog_id']) if len(additional_physical) else set()
            current_all = pd.concat([candidates[~candidates.family.isin(changed)], current[current.family.isin(changed)],
                candidates[candidates.family.isin(changed)&candidates.catalog_id.isin(current_proxy_ids|current_physical_ids)]], ignore_index=True)
            current_all = current_all.sort_values(['cost_minutes','catalog_id']).drop_duplicates(['origin_id','family','destination_group_key'])
            l2, m2 = select_functional_links(roster, presence, current_all, providers, scenario='nonhistorical_evidence_only')
            links = pd.concat([links, l2], ignore_index=True); members = pd.concat([members, m2], ignore_index=True)
        scope_path = provider_root/'provider_education_scope.parquet'
        if scope_path.is_file():
            scope = pd.read_parquet(scope_path).set_index('catalog_id')
            for column in ['source_isced_level','source_grades','grades_known','education_need_scope']:
                links[column] = links.provider_site_id.map(scope[column])
            links['literal_grade_tags_do_not_verify_full_programme_or_admission'] = True
        links = attach_anchor_quality(links,providers)
        configurations = configuration_groups(links)
        print(json.dumps({'event':'functional_links_computed','inventory_scenario':inventory_scenario,'rows':len(links)}),flush=True)
        potentials = functional_potentials(roster, destinations, costs, presence, links)
        print(json.dumps({'event':'functional_potentials_computed','inventory_scenario':inventory_scenario,'rows':len(potentials)}),flush=True)
        units = summarize_units(members, roster)
        basic_profiles,basic_members = basic_centre_profiles(roster,members,presence,destinations)
        roles = settlement_roles(roster, links, members, configurations)
        distance_summary = family_distance_summary(links, units)
        losses = [];loss_summaries = []
        for evidence in links.evidence_scenario.unique():
            selected_candidates = candidates if evidence == 'all_dated_known' else current_all
            loss,loss_summary = loss_counterfactual(roster,links[links.evidence_scenario.eq(evidence)],selected_candidates)
            losses.append(loss);loss_summaries.append(loss_summary)
        tables = {'functional_links': links, 'functional_system_members': members,
            'basic_configuration_groups': configurations, 'functional_potentials': potentials,
            'functional_systems': units, 'np_functional_roles': roles,
            'basic_centre_profiles':basic_profiles,'basic_centre_members':basic_members,
            'loss_counterfactual':pd.concat(losses,ignore_index=True),
            'loss_counterfactual_centres':pd.concat(loss_summaries,ignore_index=True)}
        prefix = 'baseline_' if len(variants) > 1 and vi == 0 else ''
        for name, table in tables.items():
            table['inventory_scenario'] = inventory_scenario
            table.to_parquet(output/(prefix+name+'.parquet'), index=False, compression='zstd')
        distance_summary.to_csv(output/(prefix+'family_distance_summary.csv'), index=False)
        if documented_assignments is not None:
            comparison = documented_assignment_comparison(links, documented_assignments, inventory_scenario)
            comparison.to_parquet(output/(prefix+'documented_school_comparison.parquet'), index=False, compression='zstd')
        summaries.append({'inventory_scenario': inventory_scenario, 'origins': len(roster),
            'functional_outcomes': len(links), 'functional_systems': len(units),
            'functional_systems_with_external_positive_members': int(units.external_positive_population_member_records.gt(0).sum()),
            'configuration_records': len(configurations), 'potential_scenarios': len(potentials),
            'known_np_function_presence_pairs': len(presence),
            'link_status_counts': links.link_kind.value_counts().to_dict(),
            'configuration_counts': configurations.membership_status.value_counts().to_dict()})
    presence.to_parquet(output/'np_function_presence_enriched.parquet', index=False, compression='zstd')
    changes.to_csv(output/'documented_presence_changes.csv', index=False)
    proxies.to_parquet(output/'documented_np_campus_proxies.parquet', index=False, compression='zstd')
    if supplementary_presence is not None or supplementary_provider_catalog is not None:
        proxies.to_parquet(output/'supplementary_np_offer_proxies.parquet', index=False, compression='zstd')
    summary = {'schema': 'sgrt.saratov.functional_analysis.v2', 'families': list(FAMILIES),
        'inventory_scenarios': summaries, 'documented_additional_presence_rows': len(changes),
        'new_coarse_campus_proxy_destinations': int(proxies.source_group.eq('official_school_campus').sum()) if len(proxies) else 0,
        'physical_catalog_sha256': digest(provider_root/'provider_catalog.parquet'),
        'interpretation': 'Known-offer accessibility and overlapping modeled functional systems; no observed trip matrix or universal capacity model.',
        'search_horizon_is_service_radius': False, 'capacity_fabricated_from_POI_count_or_population': False,
        'missing_local_supply_treated_as_absent': False,
        'joint_configuration_is_transitive_cluster': False,
        'grade_coverage_of_generic_school_family_established': False,
        'additional_physical_provider_rows':len(additional_physical),
        'additional_physical_catalog_sha256':digest(supplementary_provider_catalog) if supplementary_provider_catalog is not None else None,
        'new_coarse_np_offer_proxy_destinations':len(proxies)}
    (output/'functional_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare-catalog', action='store_true')
    p.add_argument('--source-root', type=Path)
    p.add_argument('--fields-root', type=Path)
    p.add_argument('--provider-root', type=Path)
    p.add_argument('--documented-presence', type=Path, action='append')
    p.add_argument('--documented-assignments', type=Path)
    p.add_argument('--supplementary-presence', type=Path, action='append')
    p.add_argument('--supplementary-provider-catalog', type=Path)
    p.add_argument('--supplementary-candidates', type=Path)
    p.add_argument('--single-inventory',choices=['physical_official_enrichment'])
    p.add_argument('--current-candidates', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.prepare_catalog:
        if not a.source_root: p.error('--source-root is required')
        print(json.dumps(prepare_catalog(a.source_root, a.output), ensure_ascii=False, indent=2))
    else:
        if not a.fields_root or not a.provider_root: p.error('--fields-root and --provider-root required')
        print(json.dumps(build_functional_results(a.fields_root, a.provider_root, a.output,
            documented_presence=a.documented_presence, documented_assignments=a.documented_assignments, current_candidates=a.current_candidates,
            supplementary_presence=a.supplementary_presence,supplementary_provider_catalog=a.supplementary_provider_catalog,
            supplementary_candidates=a.supplementary_candidates,single_inventory=a.single_inventory), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
