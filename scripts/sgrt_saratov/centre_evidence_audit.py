"""Audit model candidates without turning arbitrary thresholds into centres."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd


def audit(root):
    root = Path(root)
    p = pd.read_parquet(root/'basic_centre_profiles.parquet')
    p = p[p.evidence_scenario.eq('all_dated_known') & p.centre_in_regional_roster].copy()
    if p.centre_id.duplicated().any():
        raise ValueError('Repeated regional candidate')
    m = pd.read_parquet(root/'basic_centre_members.parquet')
    m = m[m.evidence_scenario.eq('all_dated_known') & m.population_2021_published.gt(0)
          & m.centre_id.isin(p.centre_id)].copy()
    if m.duplicated(['centre_id','origin_id']).any() or m.centre_id.eq(m.origin_id).any():
        raise ValueError('Nonunique or self external membership')
    expected = m.groupby('centre_id').size().reindex(p.centre_id).to_numpy()
    if not (expected == p.external_positive_origin_count.to_numpy()).all():
        raise ValueError('Profile and distinct inhabited external membership disagree')
    for n in (1, 2, 3):
        counts = m[m.contributing_basic_family_count.ge(n)].groupby('centre_id').size()
        p[f'external_origins_at_least_{n}_families'] = p.centre_id.map(counts).fillna(0).astype(int)
    other = pd.read_parquet(root/'basic_centre_profiles.parquet')
    other = other[other.evidence_scenario.eq('nonhistorical_evidence_only')]
    if other.empty:
        raise ValueError('Missing nonhistorical sensitivity scenario')
    # Inventory sensitivity is not proof that unrecorded providers do not exist.
    p['retained_without_historical_only_sources'] = p.centre_id.isin(other.centre_id)
    p['one_known_function_and_one_external_origin'] = (
        p.known_own_basic_function_count.eq(1) & p.external_positive_origin_count.eq(1))
    p['status'] = 'model_candidate_not_independently_established_centre'
    summary = {
        'regional_model_candidates': len(p),
        'known_own_function_counts': {str(int(k)): int(v) for k,v in p.known_own_basic_function_count.value_counts().sort_index().items()},
        'one_external_inhabited_origin': int(p.external_positive_origin_count.eq(1).sum()),
        'one_known_function_and_one_external_origin': int(p.one_known_function_and_one_external_origin.sum()),
        'at_least_one_external_origin_in_two_basic_families': int(p.external_origins_at_least_2_families.gt(0).sum()),
        'at_least_one_external_origin_in_three_basic_families': int(p.external_origins_at_least_3_families.gt(0).sum()),
        'retained_without_historical_only_sources': int(p.retained_without_historical_only_sources.sum()),
        'external_origin_count_median': float(p.external_positive_origin_count.median()),
        'independently_confirmed_centre_count': None,
        'new_centre_cutoff_imposed': False,
        'observed_trips_established': False,
        'interpretation': 'No count in this audit is a final count of territorial systems. Multiple functions can share incomplete-source bias.'}
    return p, summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--functions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    rows, summary = audit(args.functions)
    rows.to_csv(args.output/'centre_evidence_candidates.csv', index=False)
    (args.output/'centre_evidence_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
