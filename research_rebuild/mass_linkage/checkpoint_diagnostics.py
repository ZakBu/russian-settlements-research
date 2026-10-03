"""Write source-quality cross-tabs and population-prioritized unresolved records.

No admissions, population allocation, or annual nationwide denominators.
"""
from pathlib import Path
import argparse
import json
import pandas as pd
from .coverage import identity_sets, sha


def build(selected_path, graph_path, points_path, output):
    if output.exists():
        raise FileExistsError('New immutable diagnostic output required')
    selected = pd.read_parquet(selected_path)
    graph = pd.read_parquet(graph_path)
    points = pd.read_parquet(points_path)
    linked, full, components = identity_sets(selected, graph)
    if points.target_source_record_id.duplicated().any():
        raise ValueError('Duplicate point targets')
    d = selected.merge(points[['target_source_record_id', 'coordinate_quality', 'coordinate_admission_status']],
                       left_on='source_record_id', right_on='target_source_record_id',
                       how='left', validate='one_to_one', suffixes=('_source', '_admitted'))
    d['coordinate_admitted'] = d.target_source_record_id.notna()
    d['identity_linked'] = d.source_record_id.isin(linked)
    d['full_census_chain'] = d.source_record_id.isin(full)
    d['coordinate_and_full_chain'] = d.coordinate_admitted & d.full_census_chain
    output.mkdir(parents=True)
    cross = d.groupby(['census_year', 'population_value_quality', 'coordinate_admitted',
                       'identity_linked', 'full_census_chain'], dropna=False).agg(
                           records=('source_record_id', 'size'),
                           known_recorded_population=('population', 'sum'),
                           unknown_population_rows=('population', lambda s: s.isna().sum())).reset_index()
    cross.to_csv(output / 'population_quality_and_linkage.csv', index=False)
    point_quality = d[d.coordinate_admitted].groupby(
        ['census_year', 'coordinate_quality_admitted', 'coordinate_admission_status'], dropna=False
    ).agg(records=('source_record_id', 'size'), known_recorded_population=('population', 'sum')).reset_index()
    point_quality.to_csv(output / 'coordinate_quality_breakdown.csv', index=False)
    cols = ['source_record_id', 'census_year', 'region_raw', 'district_raw', 'settlement_name',
            'settlement_type', 'population', 'population_value_quality', 'population_scope',
            'coordinate_admitted', 'identity_linked', 'full_census_chain', 'oktmo', 'okato']
    for name, mask in {
        'unresolved_coordinates': ~d.coordinate_admitted,
        'unresolved_identity': ~d.identity_linked,
        'incomplete_census_chains': ~d.full_census_chain,
    }.items():
        d.loc[mask, cols].sort_values(['census_year', 'population', 'source_record_id'],
                                    ascending=[True, False, True], na_position='last').to_csv(
                                        output / (name + '.csv.gz'), index=False,
                                        compression={'method': 'gzip', 'mtime': 0})
    receipt = {'scope': 'Selected census records; year-row population sums are not unique-person totals',
               'rows': len(d), 'accepted_point_uses': len(points), 'identity_edges': len(graph),
               'full_census_components': len(full) // 3,
               'inputs': {str(p): sha(p) for p in [selected_path, graph_path, points_path]},
               'builder_sha256': sha(Path(__file__)),
               'files': {p.name: sha(p) for p in output.iterdir() if p.is_file()},
               'limits': ['A checked point does not upgrade the population source to an exact primary count.',
                          'Missing chains include real nonexistence and census-scope changes as well as unresolved links.',
                          'These diagnostics do not infer legal identifier intervals or comparable boundaries.']}
    (output / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ['selected', 'graph', 'points', 'output']:
        ap.add_argument('--' + k, required=True, type=Path)
    a = ap.parse_args()
    print(json.dumps(build(a.selected, a.graph, a.points, a.output), ensure_ascii=False))
