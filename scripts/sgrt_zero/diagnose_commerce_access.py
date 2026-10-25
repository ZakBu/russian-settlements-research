#!/usr/bin/env python3
"""Inspect explicit restrictions in published commerce, without changing data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    path = a.root / 'commerce/sites.parquet'
    columns = ['provider_id', 'service_code', 'supply_status', 'source_record_id',
               'source_name', 'site_lat', 'site_lon', 'tags_json',
               'default_external_seed_eligible']
    source = pd.read_parquet(path, columns=columns)
    source = source[source.default_external_seed_eligible.fillna(False)].copy()
    tags = source.tags_json.map(lambda value: json.loads(value) if isinstance(value, str) else {})
    source['access_literal'] = tags.map(lambda value: value.get('access'))
    source['opening_literal'] = tags.map(lambda value: value.get('opening_hours'))
    source['explicit_restricted_access'] = source.access_literal.fillna('').str.strip().str.casefold().isin(
        ['no', 'private', 'permit', 'members', 'military'])
    source['explicit_closed_schedule'] = source.opening_literal.fillna('').str.strip().str.casefold().isin(
        ['closed', 'off', 'mo-su off', 'mo-su closed'])
    candidates = source[source.explicit_restricted_access | source.explicit_closed_schedule].copy()
    candidates.to_parquet(a.output / 'source_counterexamples.parquet', index=False)
    routes = list((a.root / 'routes/nearest').glob('*.parquet'))
    routes += list((a.root / 'derived_nearest').glob('*.parquet'))
    evidence, outcomes = [], []
    for route in sorted(routes):
        frame = pd.read_parquet(route)
        if 'selected_provider_id' not in frame:
            continue
        hit = frame[frame.selected_provider_id.isin(candidates.provider_id)].copy()
        if hit.empty:
            continue
        keep = [c for c in ['origin_id', 'name', 'region', 'population',
                            'selected_provider_id', 'cost_minutes', 'known_local_supply'] if c in hit]
        hit = hit[keep].merge(candidates, left_on='selected_provider_id', right_on='provider_id',
                             validate='many_to_one', suffixes=('_origin', '_site'))
        hit['route'] = route.relative_to(a.root).as_posix()
        evidence.append(hit)
        outcomes.append({'route': route.relative_to(a.root).as_posix(),
                         'origins_selecting_counterexample_site': len(hit),
                         'selected_counterexample_sites': hit.provider_id.nunique()})
    if evidence:
        pd.concat(evidence, ignore_index=True).to_parquet(a.output / 'selected_counterexample_sites.parquet', index=False)
    edges = pd.read_parquet(a.root / 'screens_final/daily_edges.parquet')
    main_edges = edges[edges.scenario_id.eq('daily_20_school30_wb')]
    main_hits = main_edges[main_edges.provider_site_id.isin(candidates.provider_id)].copy()
    main_hits.to_parquet(a.output / 'main_daily_counterexamples.parquet', index=False)
    result = {'published_source_sha256': sha(path), 'eligible_source_rows': len(source),
              'explicit_access_or_schedule_counterexample_rows': len(candidates),
              'source_service_counts': candidates.service_code.value_counts().to_dict(),
              'routes': outcomes,
              'main_origins_with_selected_counterexample_site': main_hits.origin_id.nunique(),
              'main_admitted_origins_with_counterexample_site': main_hits.loc[main_hits.l0_admitted, 'origin_id'].nunique(),
              'restricted_or_closed_tag_is_not_a_permanent_closure_observation': True,
              'known_np_presence_with_other_admissible_sources_not_removed_by_this_diagnostic': True}
    (a.output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
