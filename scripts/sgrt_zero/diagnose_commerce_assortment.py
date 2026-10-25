#!/usr/bin/env python3
"""Archive the literal-name/tag food contradictions and their model exposure."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from commerce import NONFOOD_ASSORTMENT_NAME, EXPLICIT_FOOD_ASSORTMENT_NAME


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before-sites', type=Path, required=True)
    p.add_argument('--after-sites', type=Path, required=True)
    p.add_argument('--before-routes', type=Path)
    p.add_argument('--after-routes', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    before, after = pd.read_parquet(a.before_sites), pd.read_parquet(a.after_sites)
    if len(before) != len(after) or before.provider_id.tolist() != after.provider_id.tolist():
        raise ValueError('Source rows/identities changed')
    raw = ['provider_id', 'source_object_id', 'canonical_source_site_id',
           'source_record_id', 'service_code', 'site_lat', 'site_lon',
           'source_name', 'source_address_locality', 'tags_json']
    pd.testing.assert_frame_equal(before[raw], after[raw], check_dtype=False)
    candidates = after[after.service_code.eq('daily_grocery')
                       & after.source_name.str.contains(NONFOOD_ASSORTMENT_NAME, na=False)].copy()
    candidates['review_conclusion'] = candidates.source_name.map(
        lambda n: 'positive_mixed_food_assortment_retain' if EXPLICIT_FOOD_ASSORTMENT_NAME.search(str(n))
        else 'literal_nonfood_name_food_tag_conflict_hold_unknown_assortment')
    candidates['evidence_scope'] = 'manual_read_of_all_saved_names_and_raw_tags_not_current_store_visit'
    candidates['confirmed_food_absence'] = False
    candidates['original_source_is_historical_2021'] = candidates.source_year.eq(2021)
    candidates.to_parquet(a.output / 'reviewed_name_tag_candidates.parquet', index=False)
    candidates[['provider_id', 'source_name', 'tags_json', 'review_conclusion',
                'supply_status']].to_csv(a.output / 'reviewed_name_tag_candidates.csv', index=False)
    newly = after.supply_status.eq('held_assortment_conflict') & before.supply_status.eq('observed')
    after[newly].to_parquet(a.output / 'newly_held_assortment_sites.parquet', index=False)
    ids = set(after.loc[newly, 'provider_id'])
    summary = {'before_normalized_rows': len(before), 'after_normalized_rows': len(after),
               'raw_columns_checked_exact': raw, 'literal_name_tag_reviewed_candidates': len(candidates),
               'review_conclusions': candidates.review_conclusion.value_counts().to_dict(),
               'newly_held_assortment_sites': int(newly.sum()),
               'food_absence_confirmed': False, 'observed_flows': 0}
    if a.before_routes:
        route = pd.read_parquet(a.before_routes)
        selected = route[route.selected_provider_id.isin(ids)].copy()
        selected.to_parquet(a.output / 'old_routes_to_held_assortment.parquet', index=False)
        summary['old_routes_to_held_sites'] = len(selected)
        summary['old_positive_population_routes_to_held_sites'] = int(selected.population.gt(0).sum())
        if a.after_routes:
            newroute = pd.read_parquet(a.after_routes)
            if newroute.selected_provider_id.isin(ids).any():
                raise ValueError('Held assortment provider survives new routing')
            joined = route[['origin_id', 'selected_provider_id', 'cost_minutes']].merge(
                newroute[['origin_id', 'selected_provider_id', 'cost_minutes']],
                on='origin_id', how='outer', validate='one_to_one', suffixes=('_before', '_after'), indicator=True)
            if not joined['_merge'].eq('both').all():
                raise ValueError('Route origins changed')
            changed = joined.selected_provider_id_before.ne(joined.selected_provider_id_after)
            summary['reselected_route_origins'] = int(changed.sum())
            joined[changed].to_parquet(a.output / 'reselected_routes.parquet', index=False)
    paths = [a.before_sites, a.after_sites, a.before_routes, a.after_routes]
    summary['input_sha256'] = {}
    for path in filter(None, paths):
        with path.open('rb') as stream:
            summary['input_sha256'][str(path)] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (a.output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
