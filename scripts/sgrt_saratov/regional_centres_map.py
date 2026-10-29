"""Locate regional basic-service centres without inventing catchment boundaries.

The map uses the preferred physical-offer inventory and one explicit evidence
scenario. Coordinates are joined by the immutable settlement ID; an unknown
point is held rather than guessed. Colours describe known own functions, not
city size, a centre rank, or completeness of actual services.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

import pandas as pd


def build(profiles, roster, scenario='all_dated_known'):
    if profiles.duplicated(['centre_id', 'evidence_scenario']).any():
        raise ValueError('Duplicate centre/scenario profile')
    if roster.source_record_id.duplicated().any():
        raise ValueError('Duplicate reference settlement identity')
    selected = profiles.loc[profiles.evidence_scenario.eq(scenario)
                            & profiles.centre_in_regional_roster.eq(True)].copy()
    if selected.empty:
        raise ValueError('No regional centres in requested evidence scenario')
    joined = selected.merge(roster[['source_record_id', 'lat', 'lon', 'accepted_point_present']],
                            left_on='centre_id', right_on='source_record_id',
                            how='left', validate='one_to_one', indicator=True)
    if not joined['_merge'].eq('both').all():
        raise ValueError('Regional centre absent from regional reference')
    features, held = [], []
    counts = {str(i): 0 for i in (1, 2, 3)}
    for row in joined.sort_values('centre_id').itertuples(index=False):
        n = int(row.known_own_basic_function_count)
        if n not in (1, 2, 3):
            raise ValueError('Basic centre must have one to three known basic functions')
        functions = json.loads(row.known_own_basic_functions_json)
        if len(set(functions)) != n or not set(functions) <= {'school', 'medical_basic', 'grocery'}:
            raise ValueError('Known function count differs from distinct basic family list')
        counts[str(n)] += 1
        point_accepted = pd.notna(row.accepted_point_present) and bool(row.accepted_point_present)
        if not point_accepted or not (
                pd.notna(row.lat) and pd.notna(row.lon) and math.isfinite(row.lat)
                and math.isfinite(row.lon) and -90 <= row.lat <= 90 and -180 <= row.lon <= 180):
            held.append({'centre_id': row.centre_id, 'reason': 'accepted_reference_point_unknown'})
            continue
        def finite_number(value):
            return float(value) if pd.notna(value) and math.isfinite(value) else None
        props = {
            'id': row.centre_id, 'settlementKey': row.centre_id, 'name': row.centre_name,
            'class_index': n - 1, 'known_own_basic_function_count': n,
            'known_own_basic_functions': functions,
            'centre_population_2021': finite_number(row.centre_population_2021),
            'external_positive_origin_count': int(row.external_positive_origin_count),
            'external_demographic_origin_count': int(getattr(row, 'external_demographic_origin_count', row.external_positive_origin_count)),
            'external_zero_population_origin_count': int(getattr(row, 'external_zero_population_origin_count', 0)),
            'demographic_membership_scope': getattr(row, 'demographic_membership_scope', 'inhabited_only'),
            'zero_population_locations_do_not_establish_current_service_demand': True,
            'external_rural_positive_origin_count': int(row.external_rural_positive_origin_count),
            'external_credited_rural_population_2021': finite_number(row.external_credited_rural_population_2021),
            'external_rural_population_summary_complete': bool(row.external_rural_population_summary_complete),
            'external_rural_population_summary_scope': getattr(row, 'external_rural_population_summary_scope', 'published_positive_2021_origins'),
            'evidence_scenario': scenario, 'inventory_scenario': row.inventory_scenario,
            'exclusive_regional_partition_established': False,
            'observed_service_catchment_established': False,
            'missing_own_functions_mean_unknown_not_absent': True,
        }
        features.append({'type': 'Feature', 'properties': props,
                         'geometry': {'type': 'Point', 'coordinates': [float(row.lon), float(row.lat)]}})
    summary = {'regional_profile_count': len(selected), 'mapped_centre_count': len(features),
               'held_centre_count': len(held), 'held_centres': held,
               'known_own_basic_function_counts': counts, 'evidence_scenario': scenario,
               'coordinates_joined_by_exact_source_record_id': True,
               'catchment_boundaries_inferred': False, 'centre_rank_assigned': False,
               'observed_trip_flows_established': False}
    return {'type': 'FeatureCollection', 'features': features}, summary


def run(functions, reference, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    geo, summary = build(pd.read_parquet(Path(functions) / 'basic_centre_profiles.parquet'),
                         pd.read_parquet(reference))
    (output / 'saratov-basic-centres.geojson').write_text(
        json.dumps(geo, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
    (output / 'basic_centres_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--functions', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.functions, args.reference, args.output), ensure_ascii=False))
