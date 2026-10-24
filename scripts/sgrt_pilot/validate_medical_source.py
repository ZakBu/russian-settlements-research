#!/usr/bin/env python3
"""Compare every historical attachment row to a freshly obtained official XLS.

This checks transcription, not the historic name matching or observed patient trips.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


def normalize(value):
    return re.sub(r'\s+', ' ', str(value)).strip()


def header_key(value):
    return re.sub(r'[^а-яa-z0-9]+', ' ', normalize(value).lower().replace('ё', 'е')).strip()


def audit(raw, extracted, output):
    table = pd.read_parquet(extracted)
    excel = pd.ExcelFile(raw)
    frames = {name: excel.parse(name, header=None).fillna('') for name in excel.sheet_names}
    columns = {}
    for name, frame in frames.items():
        for _, row in frame.head(8).iterrows():
            origins = [i for i, value in enumerate(row) if re.search(r'населен+н?ы[йи]\s+пун?кт', header_key(value))]
            if origins:
                origin = origins[0]
                numbers = [i for i in range(origin + 1, len(row)) if 'численност' in header_key(row.iloc[i])]
                if numbers:
                    providers = [i for i, value in enumerate(row) if 'структурн' in header_key(value)]
                    columns[name] = (origin, numbers[0], providers[0] if providers else None)
                break
    checks = []
    for _, record in table.iterrows():
        frame = frames[record['sheet']]
        index = int(record['excel_row_1based']) - 1
        origin_column, population_column, provider_column = columns[record['sheet']]
        provider = ''
        if provider_column is not None:
            for raw_value in frame.iloc[:index + 1, provider_column]:
                if normalize(raw_value):
                    provider = normalize(raw_value)
        origin = normalize(frame.iloc[index, origin_column])
        number = pd.to_numeric(pd.Series([frame.iloc[index, population_column]]), errors='coerce').iloc[0]
        checks.append({
            'sheet': record['sheet'], 'excel_row_1based': index + 1,
            'origin_literal_equal': origin == normalize(record['origin_literal']),
            'provider_literal_equal': provider == normalize(record['provider_literal']),
            'published_population_equal': pd.notna(number) and float(number) == float(record['attached_population_as_published']),
            'source_origin_literal': origin,
            'extracted_origin_literal': record['origin_literal'],
        })
    result = pd.DataFrame(checks)
    output.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output / 'medical_source_row_checks.parquet', index=False)
    failures = result[~result.origin_literal_equal | ~result.published_population_equal | ~result.provider_literal_equal]
    failures.to_csv(output / 'medical_source_transcription_differences.csv', index=False)
    summary = {
        'source_url': 'https://lofoms.spb.ru/files/reshenie_2023_15_pril3_1.xls?1',
        'document_date': '2023-11-29', 'document_number': '610-О',
        'fresh_download_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
        'fresh_download_bytes': raw.stat().st_size,
        'source_sheets': len(excel.sheet_names),
        'extracted_rows_checked': len(result),
        'exact_origin_text_matches': int(result.origin_literal_equal.sum()),
        'exact_provider_literal_matches': int(result.provider_literal_equal.sum()),
        'exact_published_population_matches': int(result.published_population_equal.sum()),
        'transcription_differences': len(failures),
        'normative_attachments_not_observed_patient_trips': True,
        'published_populations_not_census_counts_or_capacity': True,
        'historical_identity_matching_independently_validated': False,
        'all_raw_rows_completeness_proven': False,
        'note': 'Every retained origin text, provider text and published count was compared to the freshly downloaded XLS; this does not independently prove completeness of extraction, provider interpretation or historic locality identity.',
    }
    (output / 'medical_source_audit.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if len(failures) else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--extracted', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(audit(args.raw, args.extracted, args.output))
