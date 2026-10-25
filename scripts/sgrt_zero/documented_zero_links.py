#!/usr/bin/env python3
"""Keep document-backed lower service stars separate from modeled choices.

No nearest point assigns a school to a settlement. No connected-component
closure joins intersecting stars. These are documentary functional fragments,
not a national partition or observed journeys.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from pyproj import Geod

GEOD = Geod(ellps='WGS84')
FAMILIES = {'school_lower_secondary': 'school_general',
            'medical_primary_fap': 'medical_basic_primary'}


def selected_lower_links(links):
    if links.link_id.duplicated().any():
        raise ValueError('Document link IDs must be unique')
    school = (links.service_code.eq('school_lower_secondary')
              & links.grade_span.eq('1-9')
              & links.evidence_kind.eq('normative_attachment'))
    health = (links.service_code.eq('medical_primary_fap')
              & links.evidence_kind.eq('provider_reported_service'))
    return links[school | health].copy()


def build_documented_stars(links, nodes, routes):
    """Return stars, documentary memberships and independent route comparison."""
    if nodes.source_record_id.isna().any() or nodes.source_record_id.duplicated().any():
        raise ValueError('Document nodes require unique non-null census identities')
    ref = nodes.set_index('source_record_id')
    selected = selected_lower_links(links)
    if selected.empty:
        raise ValueError('No explicit lower-grade or reported-FAP links in this document set')
    required = set(selected.origin_id) | set(selected.destination_id)
    if required - set(ref.index):
        raise ValueError('Every document endpoint must have an explicit census identity')
    route_maps = {}
    for family, frame in routes.items():
        if frame.origin_id.duplicated().any():
            raise ValueError(f'Duplicate modeled origins: {family}')
        route_maps[family] = frame.set_index('origin_id')
    stars, members, comparisons = [], [], []
    keys = ['destination_id', 'service_code', 'source_id', 'evidence_kind', 'document_date']
    for key, group in selected.groupby(keys, dropna=False, sort=True):
        centre, service, source, kind, date = key
        key_text = json.dumps([None if pd.isna(x) else str(x) for x in key], ensure_ascii=False)
        star_id = 'doc-star:' + hashlib.sha256(key_text.encode()).hexdigest()[:20]
        ids = sorted(set(group.origin_id))
        centre_node = ref.loc[centre]
        stars.append({'document_star_id': star_id, 'centre_id': centre,
                      'centre_name': centre_node['name'], 'service_code': service,
                      'grade_span': '1-9' if service == 'school_lower_secondary' else None,
                      'source_id': source, 'evidence_kind': kind,
                      'document_date': None if pd.isna(date) else str(date),
                      'member_count': len(ids), 'external_members': len(set(ids) - {centre}),
                      'centre_in_documented_members': centre in ids,
                      'territory_scope': 'full_selected_document_row_not_all_district',
                      'population_year': 2021,
                      'population_2021_known_sum': float(ref.loc[ids, 'population_2021'].sum(min_count=1)),
                      'population_2021_missing_members': int(ref.loc[ids, 'population_2021'].isna().sum()),
                      'observed_flow': False,
                      'general_sgrt_partition_established': False})
        for origin, rows in group.groupby('origin_id', sort=True):
            node = ref.loc[origin]
            members.append({'document_star_id': star_id, 'origin_id': origin,
                            'centre_id': centre, 'name': node['name'],
                            'centre_name': centre_node['name'], 'service_code': service,
                            'is_centre': origin == centre,
                            'lat': node.lat, 'lon': node.lon,
                            'population_2021': node.population_2021,
                            'source_id': source, 'evidence_kind': kind,
                            'document_link_ids_json': json.dumps(sorted(rows.link_id.tolist()))})
        for link in group.to_dict('records'):
            family = FAMILIES[service]
            table = route_maps.get(family)
            route = None if table is None or link['origin_id'] not in table.index else table.loc[link['origin_id']]
            out = dict(link)
            out.update(document_star_id=star_id, modeled_service_family=family,
                       modeled_route_present=route is not None,
                       document_destination_np_identity_established=True,
                       model_provider_np_identity_established=False,
                       exact_destination_np_match=None,
                       selected_point_to_documented_centre_km=None,
                       comparison_status='modeled_route_missing',
                       selected_provider_id=None, selected_provider_source_record_id=None,
                       cost_minutes=None,
                       institution_identity_match_established=False,
                       grade_coverage_match_established=False,
                       actual_journey_established=False,
                       model_grade_metadata=None)
            if route is not None:
                np_id = route.get('selected_provider_source_record_id')
                np_known = pd.notna(np_id) and str(np_id).strip() != ''
                out.update(selected_provider_id=route.get('selected_provider_id'),
                           selected_provider_source_record_id=np_id,
                           cost_minutes=route.get('cost_minutes'),
                           model_provider_np_identity_established=bool(np_known),
                           model_grade_metadata=route.get('provider_source_grades'))
                if np_known:
                    match = np_id == centre
                    out['exact_destination_np_match'] = bool(match)
                    out['comparison_status'] = 'same_documented_np' if match else 'different_known_np'
                else:
                    out['comparison_status'] = 'unknown_model_np_identity'
                lat, lon = route.get('selected_provider_site_lat'), route.get('selected_provider_site_lon')
                if all(pd.notna(v) for v in [lat, lon, centre_node.lat, centre_node.lon]):
                    _, _, metres = GEOD.inv(float(lon), float(lat), float(centre_node.lon), float(centre_node.lat))
                    out['selected_point_to_documented_centre_km'] = metres / 1000
            comparisons.append(out)
    return pd.DataFrame(stars), pd.DataFrame(members), pd.DataFrame(comparisons)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--links', type=Path, required=True)
    parser.add_argument('--nodes', type=Path, required=True)
    parser.add_argument('--school-routes', type=Path, required=True)
    parser.add_argument('--medical-routes', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    files = {'links': args.links, 'nodes': args.nodes,
             'school_general': args.school_routes, 'medical_basic_primary': args.medical_routes}
    hashes = {k: sha(v) for k, v in files.items()}
    stars, members, comparison = build_documented_stars(
        pd.read_parquet(args.links), pd.read_parquet(args.nodes),
        {key: pd.read_parquet(path) for key, path in files.items() if key in FAMILIES.values()})
    for name, frame in [('documented_stars', stars), ('documented_memberships', members), ('model_comparison', comparison)]:
        frame.to_parquet(args.output / f'{name}.parquet', index=False)
    if hashes != {k: sha(v) for k, v in files.items()}:
        raise ValueError('Input changed during document comparison')
    summary = {'documented_functional_stars': len(stars),
               'documented_memberships': len(members), 'comparison_rows': len(comparison),
               'comparison_status': comparison.comparison_status.value_counts().to_dict(),
               'observed_journeys': 0, 'general_sgrt_partition_established': False,
               'input_sha256': hashes,
               'limitations': ['Document years and provider/road years differ.',
                               'Nearest physical point does not establish NP or building identity.',
                               'School-general routes do not establish grades1-9 coverage.',
                               'Normative attachment and provider report are separate evidence kinds.',
                               'Overlapping function stars are not additive national territories.']}
    (args.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
