"""Reuse a pinned GeoNames dump as named physical-point candidates, never admissions."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .apply_historical_identity_rule import region_key
from .coordinate_ledger import haversine_array, norm

# PPLX is a populated-place section; PPLH/PPLQ are historical/abandoned,
# PPLS is a collection. These are not ordinary current settlement witnesses.
PHYSICAL_CURRENT_CODES = frozenset({'PPL', 'PPLA', 'PPLA2', 'PPLA3', 'PPLA4', 'PPLA5', 'PPLC'})
FIELDS = ('geonameid name asciiname alternatenames latitude longitude '
          'feature_class feature_code country_code cc2 admin1 admin2 admin3 '
          'admin4 population elevation dem timezone modification_date').split()


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def aliases(row: dict) -> set[str]:
    # Literal aliases are undated and language flags are absent in this dump.
    # No transliteration, fuzzy score or invented synonym is generated.
    return {text.strip() for text in [row['name'], *row['alternatenames'].split(',')]
            if text.strip() and re.search('[А-Яа-яЁё]', text)}


def physical(row: dict) -> bool:
    return (row['country_code'] == 'RU' and row['feature_class'] == 'P'
            and row['feature_code'] in PHYSICAL_CURRENT_CODES)


def parse_member(body: bytes) -> list[dict]:
    rows = []
    for number, line in enumerate(body.decode('utf-8').splitlines(), 1):
        cells = line.split('\t')
        if len(cells) != len(FIELDS):
            raise ValueError(f'GeoNames field count at RU.txt line {number}: {len(cells)}')
        rows.append(dict(zip(FIELDS, cells), source_line_1based=number))
    return rows


def region_bindings(rows: list[dict], expected_regions: set[str]) -> dict[str, dict]:
    mapping = {}
    for row in rows:
        if row['country_code'] != 'RU' or row['feature_class'] != 'A' or row['feature_code'] != 'ADM1':
            continue
        matches = defaultdict(list)
        for text in sorted(aliases(row)):
            key = region_key(text)
            if key in expected_regions:
                matches[key].append(text)
        if len(matches) == 1:
            key = next(iter(matches))
            if row['admin1'] in mapping:
                raise ValueError('Multiple GeoNames ADM1 records for one code')
            mapping[row['admin1']] = {'region_norm': key, 'admin1_geonameid': row['geonameid'],
                                      'admin1_raw_alias': matches[key][0],
                                      'admin1_source_line_1based': row['source_line_1based']}
    return mapping


def run(selected_path: Path, point_path: Path, provider_path: Path,
        zip_path: Path, admin_path: Path, manifest_path: Path, output: Path):
    if output.exists():
        raise FileExistsError('New immutable diagnostic output required')
    start = time.monotonic()
    manifest = pd.read_parquet(manifest_path)
    for path in (zip_path, admin_path):
        matches = manifest[manifest['path'].astype(str).str.endswith(path.name)]
        if len(matches) != 1 or str(matches.iloc[0]['sha256']) != sha(path):
            raise ValueError('Baseline manifest does not verify source: ' + path.name)
    with zipfile.ZipFile(zip_path) as archive:
        body = archive.read('RU.txt')
        readme = archive.read('readme.txt')
    rows = parse_member(body)
    selected = pd.read_parquet(selected_path)
    points = pd.read_parquet(point_path, columns=['target_source_record_id'])
    source = selected[selected.census_year.eq(2021)].copy()
    source['selected_name_region_count'] = source.groupby(['name_norm', 'region_norm'], dropna=False).source_record_id.transform('size')
    regions = region_bindings(rows, set(source.region_norm.dropna()))
    source = source[~source.source_record_id.isin(points.target_source_record_id)
                    & source.is_additive_settlement_record.eq(True)
                    & ~source.population_scope.isin(['federal_city_region', 'municipality', 'region', 'territorial_aggregate'])].copy()
    wanted = set(zip(source.name_norm, source.region_norm))
    found = []
    for row in rows:
        if not physical(row) or row['admin1'] not in regions:
            continue
        context = regions[row['admin1']]
        for raw_alias in sorted(aliases(row)):
            name = norm(raw_alias)
            if (name, context['region_norm']) not in wanted:
                continue
            found.append({**{k: row[k] for k in ['geonameid', 'name', 'latitude', 'longitude', 'feature_class',
                          'feature_code', 'country_code', 'admin1', 'admin2', 'modification_date', 'source_line_1based']},
                          **context, 'geonames_alias_raw': raw_alias, 'name_norm': name})
    candidates = pd.DataFrame(found).drop_duplicates(['geonameid', 'name_norm', 'region_norm'])
    if candidates.empty:
        raise ValueError('No named candidate found; report an explicit empty probe separately')
    candidates['geonames_name_region_count'] = candidates.groupby(['name_norm', 'region_norm']).geonameid.transform('nunique')
    candidates = candidates.rename(columns={'latitude': 'geonames_latitude', 'longitude': 'geonames_longitude', 'name': 'geonames_name_raw'})
    joined = source.merge(candidates, on=['name_norm', 'region_norm'], how='inner')
    provider_columns = ['source_record_id', 'provider_latitude', 'provider_longitude', 'provider_fias_level',
                        'provider_name_exact_selected_name', 'provider_type_exact_selected_type',
                        'source_object_is_naselenniy_punkt', 'source_is_aggregate_scope']
    provider = pd.read_parquet(provider_path, columns=provider_columns)
    joined = joined.merge(provider, on='source_record_id', how='left', validate='many_to_one')
    joined['provider_to_geonames_km'] = haversine_array(joined.provider_latitude, joined.provider_longitude,
                                                       joined.geonames_latitude, joined.geonames_longitude)
    joined['unique_name_region_both_sources'] = joined.selected_name_region_count.eq(1) & joined.geonames_name_region_count.eq(1)
    joined['provider_named_physical_object_screen'] = (joined.provider_name_exact_selected_name.eq(True)
        & joined.provider_type_exact_selected_type.eq(True) & joined.source_object_is_naselenniy_punkt.eq(True)
        & joined.source_is_aggregate_scope.eq(False) & joined.provider_fias_level.isin(['4', '6']))
    joined['distance_le_1km_screen_only'] = joined.provider_to_geonames_km.le(1)
    joined['candidate_only'] = True
    joined['admission_allowed'] = False
    joined['source_lineage_independence_proven'] = False
    joined['geonames_alias_current_date_proven'] = False
    joined['coordinate_measurement_at_census_date_proven'] = False
    joined['geonames_population_used'] = False
    output.mkdir(parents=True)
    joined.to_parquet(output/'named_point_candidates.parquet', index=False)
    unique = joined[joined.unique_name_region_both_sources].copy()
    unique.sort_values('population', ascending=False).head(60).to_csv(output/'top60_unique_candidates.csv', index=False)
    pd.DataFrame([dict(admin1=key, **value) for key, value in regions.items()]).to_csv(output/'adm1_literal_alias_bindings.csv', index=False)
    (output/'geonames_readme.txt').write_bytes(readme)
    summary = {'status': 'CANDIDATE_ONLY_NO_COORDINATE_OR_IDENTITY_ADMISSIONS',
        'raw_rows': len(rows), 'physical_current_rows': sum(physical(row) for row in rows),
        'literal_adm1_region_bindings': len(regions), 'unaccepted_2021_proper_np_rows': len(source),
        'matched_endpoint_rows': int(joined.source_record_id.nunique()), 'candidate_rows': len(joined),
        'unique_both_sources_endpoint_rows': len(unique), 'unique_both_sources_population': int(unique.population.sum()),
        'unique_named_provider_and_distance_le_1km_rows': int((unique.provider_named_physical_object_screen & unique.distance_le_1km_screen_only).sum()),
        'unique_named_provider_and_distance_le_1km_population': int(unique.loc[unique.provider_named_physical_object_screen & unique.distance_le_1km_screen_only, 'population'].sum()),
        'population_grain': 'selected recorded 2021 population only, not GeoNames population',
        'limits': ['Literal aliases lack language/date flags; country/ADM1 labels need independent source/context review.',
                   'GeoNames P class proves its source classification, not legal settlement type.',
                   'Different provider labels and point agreement do not prove independent upstream lineages.',
                   'No contemporary or retrospective point, provider-ID or identity admission is made.',
                   'Source-specific CC BY 4.0 notice is preserved; no project-wide data license is assigned.'],
        'inputs': {str(p): sha(p) for p in [selected_path, point_path, provider_path, zip_path, admin_path, manifest_path]},
        'uncompressed_member_sha256': hashlib.sha256(body).hexdigest(), 'builder_sha256': sha(Path(__file__)),
        'elapsed_seconds': round(time.monotonic()-start, 3),
        'outputs': {p.name: sha(p) for p in output.iterdir()}}
    (output/'receipt.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in {'inputs','outputs','limits'}}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('selected', 'points', 'provider', 'zip', 'admin', 'manifest', 'output'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    run(args.selected, args.points, args.provider, args.zip, args.admin, args.manifest, args.output)
