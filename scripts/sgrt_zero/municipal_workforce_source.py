#!/usr/bin/env python3
"""Freeze and inspect municipal workforce observations without allocating to NPs.

The source reports annual-average organisation workers, excluding small
businesses. It is not total jobs, resident employment or a commuting matrix.
Municipal groups remain explicit aggregates; federal-city totals are never
reconstructed by adding their wards. No existing census or L0 input is changed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile
import pandas as pd

try:
    from .cloud_common_systems import RemoteZip
except ImportError:
    from cloud_common_systems import RemoteZip

SOURCE_URL = ('https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/'
    'data_bdmo_118_v20260928/indicators/section32/data_Y48423005_112_v20260928.zip')
ARCHIVE_BYTES = 328270764
MEMBER = 'data_Y48423005_112_v20260928.parquet'
MEMBER_BYTES = 3305237
MEMBER_SHA256 = 'f643b394c11758f5d28e465380e263943c5e5e9e312a468daedca95b7e2f87d7'
INDICATOR = 'Y48423005'
TOTAL = 'Всего по обследуемым видам экономической деятельности'
PERIOD = 'Январь-декабрь'
UPPER = 'Муниципальное образование верхнего уровня'
LOWER = 'Муниципальное образование нижнего уровня'
FEDERALS = {'45000000': ('Москва', '45'), '40000000': ('Санкт-Петербург', '40')}
CITIES = {'45000000': ('Москва', 4211363), '40000000': ('Санкт-Петербург', 1565094),
          '65701000': ('Екатеринбург', 478059), '92701000': ('Казань', 348695),
          '75701000': ('Челябинск', 333254), '63701000': ('Саратов', 227538)}
MUNICIPAL_TYPES = {
    'Муниципальный район', 'Муниципальный округ',
    'Городской округ, городской округ с внутригородским делением',
    'Внутригородская территория города федерального значения',
    'Внутригородской район', 'Городское поселение', 'Сельское поселение',
}
KEY = ['indicator_code', 'oktmo', 'year', 'indicator_period', 'okved2']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract_source(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    target = output / MEMBER
    if target.exists():
        if target.stat().st_size != MEMBER_BYTES or sha(target) != MEMBER_SHA256:
            raise ValueError('Existing source differs from the frozen source; do not overwrite')
        return target, {'mode': 'verified_existing_member', 'bytes_transferred': 0}
    remote = RemoteZip(SOURCE_URL, ARCHIVE_BYTES)
    with zipfile.ZipFile(remote) as archive:
        if archive.namelist().count(MEMBER) != 1:
            raise ValueError('Missing or duplicated source ZIP member')
        if archive.getinfo(MEMBER).file_size != MEMBER_BYTES:
            raise ValueError('Unexpected uncompressed source size')
        # Reading to EOF checks the member CRC; SHA fixes the actual source bytes.
        data = archive.read(MEMBER)
    if len(data) != MEMBER_BYTES or hashlib.sha256(data).hexdigest() != MEMBER_SHA256:
        raise ValueError('Frozen source SHA or size mismatch')
    temporary = target.with_name(target.name + '.incoming')
    temporary.write_bytes(data)
    temporary.replace(target)
    return target, {'mode': 'http_ranges_frozen_member_sha256_and_zip_crc_verified',
                    'bytes_transferred': remote.transferred}


def classify_territory(row):
    code = str(row.get('oktmo', '')).strip()
    name = re.sub(r'\s+', ' ', str(row.get('municipality', ''))).strip()
    level = row.get('mun_level')
    # Real source examples have the same upper-level label as actual cities.
    # Source names and explicit grouped codes therefore override that label.
    if (re.match(r'^(?:Городские округа|Муниципальные районы|Муниципальные округа)\b', name)
            or re.fullmatch(r'\d{2}[567]00000', code)):
        return 'group_of_municipalities_aggregate'
    if code in FEDERALS and level == 'Субъект РФ':
        expected_name, expected_region = FEDERALS[code]
        if row.get('region_name') == expected_name and str(row.get('region_id')) == expected_region:
            return 'reported_federal_city_subject_total'
    if (level in {UPPER, LOWER} and re.fullmatch(r'\d{8}', code)
            and row.get('mun_type_oktmo') in MUNICIPAL_TYPES and name):
        # A source municipal territory, not an independently checked legal border.
        return 'municipal_territory_record'
    return 'unverified_territory_scope'


def select_2025(source):
    required = {*KEY, 'region_id', 'region_name', 'municipality', 'mun_level',
                'mun_type_oktmo', 'indicator_unit', 'indicator_value',
                'oktmo_year_from', 'oktmo_year_to'}
    if not required <= set(source):
        raise ValueError('Missing raw source fields: ' + ', '.join(sorted(required - set(source))))
    selected = source[source.indicator_code.eq(INDICATOR) & source.year.eq(2025)
                      & source.indicator_period.eq(PERIOD) & source.okved2.eq(TOTAL)].copy()
    if selected.empty:
        raise ValueError('No annual 2025 total observations; no quarterly/sector substitution')
    if selected.duplicated(KEY).any():
        raise ValueError('Duplicate territorial/year/period/industry keys; no silent aggregation')
    if not selected.indicator_unit.eq('Человек').all():
        raise ValueError('Unexpected workforce measurement unit')
    selected['source_territory_class'] = selected.apply(classify_territory, axis=1)
    selected['workforce_numeric_value'] = pd.to_numeric(selected.indicator_value, errors='coerce')
    if not selected.workforce_numeric_value.dropna().map(math.isfinite).all():
        raise ValueError('Nonfinite observed workforce')
    if selected.workforce_numeric_value.dropna().lt(0).any():
        raise ValueError('Negative observed workforce')
    selected['workforce_observation_status'] = 'unknown_or_nonnumeric_not_zero'
    selected.loc[selected.workforce_numeric_value.notna(), 'workforce_observation_status'] = 'observed_partial_workforce'
    start = pd.to_numeric(selected.oktmo_year_from, errors='coerce')
    end = pd.to_numeric(selected.oktmo_year_to, errors='coerce')
    selected['code_history_interval_requires_review'] = ((start.notna() & start.gt(2025))
                                                        | (end.notna() & end.lt(2025)))
    selected['eligible_as_individual_municipal_context'] = selected.source_territory_class.eq('municipal_territory_record')
    selected['is_reported_federal_city_total'] = selected.source_territory_class.eq('reported_federal_city_subject_total')
    selected['geography_automatically_equal_to_census_settlement'] = False
    selected['workers_allocated_to_settlements'] = False
    selected['total_jobs_or_resident_employment_measured'] = False
    selected['municipal_components_summed'] = False
    selected['legal_boundary_equivalence_independently_verified'] = False
    return selected.sort_values(['region_id', 'oktmo'], kind='stable').reset_index(drop=True)


def six_city_examples(selected):
    examples = []
    for code, (city, expected) in CITIES.items():
        rows = selected[selected.oktmo.eq(code)]
        if len(rows) != 1 or float(rows.workforce_numeric_value.iloc[0]) != expected:
            raise ValueError('Frozen six-city source row or observed value differs: ' + city)
        row = rows.iloc[0]
        raw_fields = [column for column in selected if column in [
            'indicator_section_code', 'indicator_section', 'indicator_code', 'indicator_name',
            'okved2', 'region_id', 'region_name', 'mun_level', 'mun_district', 'municipality',
            'oktmo', 'mun_type', 'mun_type_oktmo', 'oktmo_stable', 'oktmo_history',
            'oktmo_year_from', 'oktmo_year_to', 'year', 'indicator_value',
            'indicator_unit', 'indicator_period', 'comment']]
        raw = json.loads(rows[raw_fields].to_json(orient='records', force_ascii=False))[0]
        examples.append({'city_name_for_reading': city, 'raw_source_key': {k: raw[k] for k in KEY},
            'source_territory_class': row.source_territory_class,
            'scope': ('reported total of the whole federal-city subject; not a sum of wards'
                      if row.is_reported_federal_city_total else
                      'reported municipal territory; not automatically equal to the named census city'),
            'raw_source_row': raw, 'value': expected, 'observation_year': 2025,
            'total_jobs_or_commuting_flow_claimed': False})
    return examples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    path, retrieval = extract_source(args.output)
    source = pd.read_parquet(path)
    selected = select_2025(source)
    examples = six_city_examples(selected)
    selected.to_parquet(args.output / 'municipal_workforce_2025.parquet', index=False)
    (args.output / 'six_urban_territories_2025.json').write_text(
        json.dumps(examples, ensure_ascii=False, indent=2) + '\n')
    summary = {'source_id': 'BDMO_WORKFORCE_20260928', 'source_url': SOURCE_URL,
        'archive_bytes': ARCHIVE_BYTES, 'member': MEMBER, 'member_bytes': MEMBER_BYTES,
        'member_sha256': MEMBER_SHA256, 'source_rows': len(source),
        'selected_annual_total_2025_rows': len(selected),
        'regional_labels': int(selected.region_name.nunique()),
        'territory_class_counts': selected.source_territory_class.value_counts().to_dict(),
        'code_history_interval_review_rows': int(selected.code_history_interval_requires_review.sum()),
        'retrieval': retrieval, 'code_sha256': sha(Path(__file__)),
        'municipal_totals_not_allocated_to_NPs': True,
        'full_jobs_or_observed_commuting_claimed': False}
    (args.output / 'source_facts.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
