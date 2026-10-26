#!/usr/bin/env python3
"""Compare declared potential scenarios on exact pilot road pairs, no zoning."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
try:
    from .hierarchy_gravity_candidates import relative_potentials, digest
except ImportError:
    from hierarchy_gravity_candidates import relative_potentials, digest


def run(profiles_path, pairs_path, centres_path, output, *, half_lives=(10., 20., 30.),
        transforms=('linear', 'log1p'), mass_field='independent_positive_medical_stock_proxy'):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    source_paths = [Path(profiles_path), Path(pairs_path), Path(centres_path), Path(__file__),
                    Path(__file__).with_name('hierarchy_gravity_candidates.py')]
    source_hashes = {str(path): digest(path) for path in source_paths}
    profiles = pd.read_parquet(profiles_path); pairs = pd.read_parquet(pairs_path)
    centres = pd.read_parquet(centres_path) if Path(centres_path).suffix == '.parquet' else pd.read_csv(centres_path)
    key = 'centre_settlement_id' if 'centre_settlement_id' in centres else 'source_record_id'
    ids = set(centres[key].dropna())
    # Missing route outcomes stay in the immutable pilot cost table. Only
    # known road rows are duplicated across mass/decay sensitivities.
    finite = pairs[pairs.cost_minutes.notna() & pairs.origin_id.isin(ids)
                   & pairs.origin_id.ne(pairs.destination_id)].copy()
    metadata = profiles.set_index('source_record_id')
    rows = []; frames = []
    for transform in transforms:
        for half_life in half_lives:
            result = relative_potentials(profiles, finite, mass_column=mass_field,
                                        half_life_minutes=half_life, transform=transform)
            frames.append(result)
            for target, group in result.groupby('destination_id', sort=True):
                known = group[group.relative_potential_to_local_reservation.notna()]
                beats = known[known.beats_local_proxy_reservation]
                rows.append({'city': str(metadata.loc[target, 'name']),
                             'destination_id': target, 'mass_transform': transform,
                             'half_life_minutes': float(half_life),
                             'road_routed_registered_l0_centres': len(group),
                             'with_known_positive_local_proxy': len(known),
                             'unknown_local_proxy': len(group) - len(known),
                             'beats_local_proxy_centres': len(beats),
                             'max_road_minutes_where_beats_local': float(beats.cost_minutes.max()) if len(beats) else None,
                             'territorial_systems_assigned': 0})
    pd.concat(frames, ignore_index=True).to_parquet(output / 'potential_sensitivity_known_road_pairs.parquet', index=False)
    pd.DataFrame(rows).to_csv(output / 'six_city_potential_sensitivity.csv', index=False)
    summary = {'scope': 'Conditional address-stock proxy sensitivity, not capacity, jobs, trips or territorial hierarchy. Unknown route rows remain in the pilot input; repeated scenario rows use known-road registered-L0-centre origins only. Missing local proxy remains unknown.',
               'full_cost_pairs': len(pairs), 'finite_cost_registered_centre_external_pairs': len(finite),
               'half_life_scenarios': list(half_lives), 'mass_transform_scenarios': list(transforms),
               'mass_field': mass_field, 'candidate_pool_completeness_established': False,
               'territorial_systems_assigned': 0, 'input_sha256': source_hashes, 'rows': rows}
    if source_hashes != {str(path): digest(path) for path in source_paths}:
        raise RuntimeError('An input changed during potential sensitivity calculation')
    (output / 'gravity_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['profiles', 'pairs', 'centres', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--half-lives', type=float, nargs='+', default=[10., 20., 30.])
    parser.add_argument('--transforms', choices=['linear', 'log1p'], nargs='+', default=['linear', 'log1p'])
    parser.add_argument('--mass-field', default='independent_positive_medical_stock_proxy')
    args = parser.parse_args()
    result = run(args.profiles, args.pairs, args.centres, args.output, half_lives=args.half_lives,
                 transforms=args.transforms, mass_field=args.mass_field)
    print(json.dumps({'scenarios': len(result['rows']), 'finite_pairs': result['finite_cost_registered_centre_external_pairs'],
                      'territorial_assignments': 0}, ensure_ascii=False))
