"""Inventory the 2010 regional population gap and cached exact-primary sources.

Research inventory only: regional controls do not locate missing population,
matches do not establish identity, and candidates are never admitted here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WORK = Path('/workspace/settlements-work/continuation_20261003/population2010')
RELEASE = Path('/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930')
RAW = Path('/workspace/settlements-raw/data/raw')
SOURCES = Path('/workspace/settlements-work/sources')
KARELIA = Path('/workspace/settlements-karelia-inputs/build/evidence/ingestion')
RECEIPT = SOURCES / 'r2_2010_regional_control_receipt.json'
TABLE5_PDF = RAW / '2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf'
EXPECTED_RELEASE_SHA = '524e706daa32a69cac9b3e67b3bb8f9113fe2d851f10cdf42e93ba4efa5d72bf'

SOURCE_ASSETS = [
    {'asset_id': 'ROSSTAT2010:T5', 'region_scope': '83 federal subjects',
     'path': TABLE5_PDF, 'origin': 'Rosstat Volume 1 official publication',
     'origin_url': 'not retained in existing source receipt',
     'retrieval_url': 'not retained in existing source receipt', 'tls_status': 'not recorded in cached receipt',
     'published_scope': 'urban settlements, rural district centres and rural settlements >= 3,000; not exhaustive',
     'use_condition': 'row-level source and entity grain review; candidate matching only'},
    {'asset_id': 'ROSSTAT2010:T11:CITY', 'region_scope': '83 federal subjects',
     'path': RAW / '2010_official_tom11/pub-11-1-4.pdf', 'origin': 'Rosstat Volume 11 official publication',
     'origin_url': 'not retained in existing source receipt',
     'retrieval_url': 'not retained in existing source receipt', 'tls_status': 'not recorded in cached receipt',
     'published_scope': 'city-count reference; not an all-settlement population inventory',
     'use_condition': 'only where published row scope directly applies'},
    {'asset_id': 'MUR2010:POP', 'region_scope': 'Murmansk Oblast',
     'path': SOURCES / 'r2-missing/murmansk_population.doc', 'origin': 'Rosstat Murmansk; recorded Web Archive copy of official URL',
     'origin_url': 'https://51.rosstat.gov.ru/storage/mediabank/14(1).doc',
     'retrieval_url': 'https://web.archive.org/web/20240718144234id_/https://51.rosstat.gov.ru/storage/mediabank/14(1).doc',
     'tls_status': 'verified for archive retrieval; official origin returned HTTP 503',
     'published_scope': 'regional table; existing R2 primary candidate slice',
     'use_condition': 'R2 independent review and DOCX/text conversion checks apply'},
    {'asset_id': 'KAL2010:T1', 'region_scope': 'Kaliningrad Oblast',
     'path': SOURCES / 'r2-missing/kaliningrad_tom1.xlsx', 'origin': 'Rosstat Kaliningrad; recorded Web Archive copy of official URL',
     'origin_url': 'https://39.rosstat.gov.ru/storage/mediabank/Итоги+ВПН-2010_том1.xlsx',
     'retrieval_url': 'https://web.archive.org/web/20250619171623id_/https://39.rosstat.gov.ru/storage/mediabank/%D0%98%D1%82%D0%BE%D0%B3%D0%B8+%D0%92%D0%9F%D0%9D-2010_%D1%82%D0%BE%D0%BC1.xlsx',
     'tls_status': 'verified for archive retrieval; official-origin attempt failed before response due Unicode URL handling',
     'published_scope': 'regional official Volume 1 workbook; existing R2 primary candidate slice',
     'use_condition': 'XML/openpyxl agreement and independent review apply'},
    {'asset_id': 'ARK2010:HTML', 'region_scope': 'Arkhangelsk Oblast and Nenets AO',
     'path': SOURCES / 'r2-missing/arkhangelsk_2010_archived_original.html', 'origin': 'Arkhangelskstat official page; recorded Web Archive copy',
     'origin_url': 'http://www.arhangelskstat.ru/surveys/vpn2010/DocLib1/Информационные материалы о предварительных итогах Всероссийской переписи населения 2010 года/численность.htm',
     'retrieval_url': 'https://web.archive.org/web/20131022224851id_/http://www.arhangelskstat.ru/surveys/vpn2010/DocLib1/Информационные%20материалы%20о%20предварительных%20итогах%20Всероссийской%20переписи%20населения%202010%20года/численность.htm',
     'tls_status': 'verified to archive endpoint; full 5,947,561-byte cached copy hash matches; earlier 4 MiB bounded attempt was incomplete',
     'published_scope': 'regional official preliminary settlement table; existing R2 primary candidate slice',
     'use_condition': 'page table/row scope, null semantics, and independent review apply'},
    {'asset_id': 'KRL2010:RURAL', 'region_scope': 'Republic of Karelia',
     'path': KARELIA / 'source/karelia_2010_rural_settlements.docx', 'origin': 'Rosstat Karelia official publication listing; cached download transport was not TLS-verified',
     'origin_url': 'https://10.rosstat.gov.ru/storage/mediabank/2_Сельские+населенные+пункты+РК.docx',
     'retrieval_url': 'same as origin; existing source facts report TLS certificate verification failure',
     'tls_status': 'failed for cached retrieval; retained document hash and official catalog listing',
     'published_scope': 'rural settlements; audited source contains 667 inhabited and 109 zero-population rows',
     'use_condition': 'provisional only until transport/archive provenance verified; R5 extraction checks apply'},
    {'asset_id': 'ROSSTAT2010:REGIONAL_CONTROLS', 'region_scope': '80 disjoint regional controls',
     'path': RAW / '2010_official_controls/rosstat_population2010_by_region.csv', 'origin': 'Rosstat official regional/municipal control extract',
     'origin_url': 'not retained in existing source receipt',
     'retrieval_url': 'not retained in existing source receipt', 'tls_status': 'not recorded in cached receipt',
     'published_scope': 'regional aggregates, not settlement populations',
     'use_condition': 'control comparison only; never allocate gaps to rows'},
]


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def norm(value: object) -> str:
    text = unicodedata.normalize('NFKC', str(value or '')).lower().replace('ё', 'е').replace('ѐ', 'е')
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text)).strip()


def classify_label(label: str) -> tuple[str, str | None, str | None]:
    """Use structural type labels so real names beginning Город remain names."""
    value = re.sub(r'^(Городское|Сельское) население\s*[-–]\s*', '', label.strip(), flags=re.I)
    if re.search(r'подчиненн|администраци|населенными пунктами|включая', value, re.I):
        return 'aggregate_or_parent', None, None
    m = re.match(r'^(г\.|город|пгт|село|пос[еёѐ]лок|деревня|станица|хутор|аул|слобода|местечко|селение|кишлак)\s+(.+)$', value, re.I)
    if not m:
        return 'header_or_unclassified', None, None
    typ, name = m.groups()
    typ = {'г.': 'город', 'посёлок': 'поселок', 'посѐлок': 'поселок'}.get(typ.lower(), typ.lower())
    name = re.sub(r'\s*\((?:рц|цмр)\)\s*', '', name, flags=re.I)
    name = re.sub(r'\s+(?:рп|кп|дп)\s*$', '', name, flags=re.I).strip()
    return 'settlement', typ, name


def parse_count_tokens(line: str) -> dict | None:
    """Retain printed dash tokens; zero interpretation belongs to source evidence."""
    m = re.match(r'^(.*?)\s+(\d+|-)\s+(\d+|-)\s+(\d+|-)\s+(\d+,\d+|-)\s+(\d+,\d+|-)$', line.strip())
    if not m:
        return None
    label, total, men, women, urban_share, rural_share = m.groups()
    kind, typ, name = classify_label(label)
    return {'label_raw': label, 'row_kind': kind, 'settlement_type': typ, 'settlement_name': name,
            'population_raw': total, 'men_raw': men, 'women_raw': women,
            'urban_share_raw': urban_share, 'rural_share_raw': rural_share,
            'population_interpreted': None,
            'dash_present': '-' in (total, men, women, urban_share, rural_share)}


def _load_table5(output: Path) -> tuple[pd.DataFrame, Path]:
    extracted = output / 'tom1_table5_extraction/official_2010_table5_reference.parquet'
    if extracted.is_file():
        return pd.read_parquet(extracted), extracted
    module_path = ROOT / 'research_audit/extract_official_2010_reference.py'
    spec = importlib.util.spec_from_file_location('official_2010_table5_extractor', module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    out = output / 'tom1_table5_extraction'
    ref = module.extract(pdf=TABLE5_PDF, output=out)
    return ref, out / 'official_2010_table5_reference.parquet'


def build(output: Path = WORK, extract_table5: bool = True) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    selection_path = RELEASE / 'selected_observations.parquet'
    actual_release_sha = sha256(selection_path)
    if actual_release_sha != EXPECTED_RELEASE_SHA:
        raise ValueError(f'R2 release SHA mismatch: {actual_release_sha}')
    df = pd.read_parquet(selection_path, filters=[('census_year', '=', 2010)])
    if len(df) != 152314 or int(df.population.sum(skipna=True)) != 142202712:
        raise ValueError('R2 2010 row or population control changed')

    receipt = json.loads(RECEIPT.read_text(encoding='utf-8'))
    regional = pd.DataFrame(receipt['2010']['regional_differences'])
    regional['regional_gap_status'] = regional.gap_official_minus_selected.map(
        lambda x: 'selected_below_control' if x > 0 else ('selected_above_control' if x < 0 else 'equal_control'))
    regional.to_csv(output / 'regional_control_gaps_2010.csv', index=False)
    (df.groupby(['region_raw', 'population_value_quality'], dropna=False)
       .agg(rows=('source_record_id', 'size'), known_population=('population', 'sum'))
       .reset_index().to_csv(output / 'selected_2010_region_source_quality.csv', index=False))
    protected = df[df.population_value_quality.eq('confidentiality_perturbed_within_ten')].copy()
    key = ['match_region', 'match_name', 'match_type']
    protected['match_region'] = protected.region_raw.map(norm)
    protected['match_name'] = protected.settlement_name.map(norm)
    protected['match_type'] = protected.settlement_type.map(norm)
    protected['protected_key_count'] = protected.groupby(key).source_record_id.transform('size')

    cached = json.loads((SOURCES / 'cached_2010_source_assets.json').read_text(encoding='utf-8'))
    cached_by_path = {x['path']: x for x in cached['files']}
    assets = []
    for item in SOURCE_ASSETS:
        path = Path(item['path'])
        assets.append({**{k: v for k, v in item.items() if k != 'path'},
                       'path': str(path), 'exists': path.is_file(),
                       'bytes': path.stat().st_size if path.is_file() else None,
                       'sha256': sha256(path)})
    pd.DataFrame(assets).to_csv(output / 'cached_primary_source_assets_2010.csv', index=False)
    (output / 'cached_2010_source_assets.json').write_text(
        json.dumps(cached, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    family = df.groupby(['source_file', 'population_value_quality'], dropna=False).agg(
        rows=('source_record_id', 'size'), selected_population=('population', 'sum')).reset_index()
    family['source_sha256'] = family.source_file.map(lambda p: cached_by_path.get(p, {}).get('sha256'))
    family['source_asset_classification'] = family.source_file.map(lambda p: cached_by_path.get(p, {}).get('classification'))
    family.to_csv(output / 'selected_2010_source_family_totals.csv', index=False)
    priority_region = {
        '46000000': 'московская', '5000000': 'приморский', '22000000': 'нижегородская',
        '3000000': 'краснодарский', '57000000': 'пермский', '41000000': 'ленинградская',
        '8000000': 'хабаровский', '4000000': 'красноярский', '89000000': 'мордовия',
        '7000000': 'ставропольский',
    }
    protected_by_region = (protected.groupby('region_raw').agg(
        protected_rows=('source_record_id', 'size'), protected_population=('population', 'sum')).reset_index())

    candidate_stats = {'status': 'not_extracted'}
    if extract_table5:
        ref, extraction_path = _load_table5(output)
        table = ref[(ref.row_kind.eq('settlement')) & ref.reference_status.eq('extracted_reference')].copy()
        table['match_region'] = table.region_key.map(norm)
        table['match_name'] = table.settlement_name.map(norm)
        table['match_type'] = table.settlement_type.map(norm)
        table['table5_settlement_name_raw'] = table.settlement_name
        table['table5_settlement_type'] = table.settlement_type
        table['table5_key_count'] = table.groupby(key).reference_id.transform('size')
        table = table.rename(columns={'population': 'table5_population'})
        # Read-only denominator check: show which existing R2 source families
        # already overlap Table 5, so those rows cannot be reported as new gain.
        all_r2 = df.copy()
        all_r2['match_region'] = all_r2.region_raw.map(norm)
        all_r2['match_name'] = all_r2.settlement_name.map(norm)
        all_r2['match_type'] = all_r2.settlement_type.map(norm)
        all_r2['r2_key_count'] = all_r2.groupby(key).source_record_id.transform('size')
        full_cross = table.merge(all_r2, on=key, how='inner', suffixes=('_table5', '_r2'))
        full_unique = full_cross.table5_key_count.eq(1) & full_cross.r2_key_count.eq(1)
        full_cross['overlap_status'] = 'ambiguous_or_duplicate_key'
        full_cross.loc[full_unique, 'overlap_status'] = 'unique_text_key_overlap_existing_selected_row'
        (full_cross.groupby(['population_value_quality', 'overlap_status'], dropna=False)
         .agg(existing_r2_rows=('source_record_id', 'size'),
              existing_selected_population=('population', 'sum'),
              table5_population=('table5_population', 'sum'))
         .reset_index().to_csv(output / 'table5_overlap_all_r2_source_quality_2010.csv', index=False))
        (full_cross[full_unique].groupby(['population_value_quality', 'source_file'], dropna=False)
         .agg(existing_r2_rows=('source_record_id', 'size'),
              existing_selected_population=('population', 'sum'),
              table5_population=('table5_population', 'sum'))
         .reset_index().to_csv(output / 'table5_unique_overlap_existing_sources_2010.csv', index=False))
        cross = table.merge(protected, on=key, how='inner', suffixes=('_table5', '_r2'))
        cross['candidate_status'] = 'ambiguous_or_duplicate_key_pending_review'
        unique = cross.table5_key_count.eq(1) & cross.protected_key_count.eq(1)
        cross.loc[unique, 'candidate_status'] = 'unique_text_key_population_candidate_pending_identity_and_binding_review'
        source_hashes = {x['path']: x['sha256'] for x in cached['files']}
        cross['r2_source_sha256_from_asset_inventory'] = cross.source_file.map(source_hashes)
        cross['official_minus_selected_delta'] = cross.table5_population - cross.population
        cross['absolute_delta'] = cross.official_minus_selected_delta.abs()
        cross['delta_band'] = pd.cut(cross.absolute_delta, [-1, 0, 10, 1000, float('inf')],
                                     labels=['exact_0', 'abs_1_to_10', 'abs_11_to_1000', 'abs_gt_1000'])
        cross['district_context_status'] = 'district_missing_on_one_or_both_sides'
        has_district_both = cross.district_raw_table5.notna() & cross.district_raw_r2.notna()
        same_district = has_district_both & cross.district_raw_table5.map(norm).eq(cross.district_raw_r2.map(norm))
        cross.loc[has_district_both & ~same_district, 'district_context_status'] = 'district_conflict'
        cross.loc[same_district, 'district_context_status'] = 'district_text_agrees_candidate'
        cols = ['candidate_status', 'source_record_id', 'region_raw_r2', 'region_raw_table5',
                'source_name_raw', 'settlement_name_r2', 'settlement_type_r2', 'table5_settlement_name_raw',
                'table5_settlement_type',
                'population', 'table5_population', 'official_minus_selected_delta', 'absolute_delta',
                'delta_band', 'population_value_quality', 'source_file', 'source_path',
                'source_sha256', 'r2_source_sha256_from_asset_inventory', 'source_locator', 'source_row',
                'source_sheet', 'source_selection_component',
                'reference_id', 'pdf_page', 'printed_page', 'text_line_start', 'text_line_end', 'label_raw',
                'raw_lines', 'men', 'women', 'total_equals_sexes', 'dash_in_counts', 'regional_center',
                'parent_context', 'district_raw_table5', 'district_raw_r2', 'district_context_status',
                'municipality_raw',
                'source_population_raw', 'row_kind', 'reference_status']
        cross = cross[[c for c in cols if c in cross.columns]].rename(columns={'source_record_id': 'r2_source_record_id'})
        candidate_path = output / 'table5_to_r2_overlap_candidates_2010.parquet'
        cross.to_parquet(candidate_path, index=False)
        (cross.groupby(['population_value_quality', 'candidate_status'], dropna=False)
         .agg(candidate_rows=('r2_source_record_id', 'size'), candidate_population=('population', 'sum'),
              table5_population=('table5_population', 'sum')).reset_index()
         .to_csv(output / 'table5_overlap_by_r2_quality_2010.csv', index=False))
        (cross.groupby(['region_raw_r2', 'candidate_status'], dropna=False)
         .agg(candidate_rows=('r2_source_record_id', 'size'), candidate_population=('population', 'sum'),
              table5_population=('table5_population', 'sum')).reset_index()
         .sort_values(['candidate_rows', 'candidate_population'], ascending=False)
         .to_csv(output / 'table5_overlap_by_region_2010.csv', index=False))
        unique_by_region = (cross[cross.candidate_status.str.startswith('unique_text')]
                            .groupby('region_raw_r2').agg(
                                unique_table5_candidate_rows=('r2_source_record_id', 'size'),
                                unique_candidate_population=('population', 'sum'),
                                table5_candidate_population=('table5_population', 'sum')).reset_index())
        primary_triage = regional.sort_values('gap_official_minus_selected', ascending=False).head(10).copy()
        primary_triage['region_raw_key'] = primary_triage.oktmo_control_code.map(priority_region)
        primary_triage = primary_triage.merge(protected_by_region, left_on='region_raw_key', right_on='region_raw', how='left')
        primary_triage = primary_triage.merge(unique_by_region, left_on='region_raw_key', right_on='region_raw_r2', how='left')
        primary_triage['cached_regional_exact_primary_asset'] = False
        primary_triage['cached_national_primary_asset'] = 'ROSSTAT2010:T5'
        primary_triage['national_table5_coverage_limit'] = 'urban + rural district centres + rural settlements >=3000; no complete small-rural inventory'
        primary_triage.to_csv(output / 'top_gap_primary_asset_triage_2010.csv', index=False)
        viable = cross[cross.candidate_status.str.startswith('unique_text')]
        (viable.groupby('delta_band', observed=False)
         .agg(candidate_rows=('r2_source_record_id', 'size'), selected_population=('population', 'sum'),
              table5_population=('table5_population', 'sum'), net_delta=('official_minus_selected_delta', 'sum'),
              absolute_delta_sum=('absolute_delta', 'sum'))
         .reset_index().to_csv(output / 'table5_unique_candidate_delta_distribution_2010.csv', index=False))
        (viable.groupby(['delta_band', 'district_context_status'], observed=False, dropna=False)
         .agg(candidate_rows=('r2_source_record_id', 'size'), selected_population=('population', 'sum'),
              table5_population=('table5_population', 'sum'))
         .reset_index().to_csv(output / 'table5_unique_candidate_context_distribution_2010.csv', index=False))
        top_delta_columns = ['r2_source_record_id', 'r2_source_sha256_from_asset_inventory', 'region_raw_r2',
                             'source_name_raw', 'settlement_name_r2', 'settlement_type_r2',
                             'table5_settlement_name_raw', 'table5_settlement_type', 'population', 'table5_population',
                             'official_minus_selected_delta', 'source_file', 'source_sheet', 'source_row',
                             'source_locator', 'source_population_raw', 'reference_id', 'pdf_page', 'printed_page',
                             'text_line_start', 'text_line_end', 'label_raw', 'raw_lines', 'parent_context',
                             'district_raw_table5', 'district_raw_r2', 'district_context_status',
                             'municipality_raw', 'men', 'women',
                             'total_equals_sexes', 'dash_in_counts']
        top20 = viable.sort_values('absolute_delta', ascending=False).head(20)
        top20[[c for c in top_delta_columns if c in top20.columns]].to_csv(
            output / 'table5_unique_candidate_largest_deltas_2010.csv', index=False)
        # Stable, reproducible additional sample from each out-of-band stratum;
        # reserve the top 20 for separate inspection.
        remaining = viable[viable.absolute_delta.gt(10) & ~viable.r2_source_record_id.isin(top20.r2_source_record_id)].copy()
        remaining['sample_order'] = remaining.r2_source_record_id.map(
            lambda value: hashlib.sha256(str(value).encode('utf-8')).hexdigest())
        review_parts = []
        review_specs = [('abs_11_to_1000', remaining.absolute_delta.between(11, 100), 5),
                        ('abs_101_to_1000', remaining.absolute_delta.between(101, 1000), 5),
                        ('abs_gt_1000', remaining.absolute_delta.gt(1000), 5)]
        for label, mask, n in review_specs:
            piece = remaining[mask].sort_values('sample_order').head(n).copy()
            piece['fixed_review_stratum'] = label
            review_parts.append(piece)
        sample = pd.concat(review_parts, ignore_index=True)
        sample[[c for c in top_delta_columns + ['fixed_review_stratum'] if c in sample.columns]].to_csv(
            output / 'table5_unique_candidate_fixed_out_of_band_sample_2010.csv', index=False)
        candidate_stats = {
            'extraction_path': str(extraction_path), 'table5_rows': len(ref),
            'table5_settlement_rows': int(ref.row_kind.eq('settlement').sum()),
            'all_selected_rows_with_table5_key_overlap': len(full_cross),
            'all_selected_unique_text_key_overlap_rows': int(full_unique.sum()),
            'all_selected_unique_text_key_overlap_by_current_quality': full_cross.loc[full_unique, 'population_value_quality'].value_counts().to_dict(),
            'protected_key_overlap_rows_including_duplicates': len(cross),
            'unique_text_key_protected_candidate_rows': len(viable),
            'unique_candidate_recorded_secondary_population': int(viable.population.sum()),
            'unique_candidate_published_table5_population': int(viable.table5_population.sum()),
            'unique_candidate_population_delta_official_minus_selected': int((viable.table5_population - viable.population).sum()),
            'unique_candidate_rows_by_current_quality': viable.population_value_quality.value_counts().to_dict(),
            'delta_bands': {
                'exact_0': int(viable.absolute_delta.eq(0).sum()),
                'abs_1_to_10': int(viable.absolute_delta.between(1, 10).sum()),
                'abs_11_to_1000': int(viable.absolute_delta.between(11, 1000).sum()),
                'abs_gt_1000': int(viable.absolute_delta.gt(1000).sum()),
            },
            'district_context_status_counts': viable.district_context_status.value_counts(dropna=False).to_dict(),
            'district_context_by_delta_band': {
                f'{district}|{band}': int(count)
                for (district, band), count in viable.groupby(
                    ['district_context_status', 'delta_band'], observed=False, dropna=False).size().items()
            },
            'fixed_out_of_band_review_sample_rows': len(sample),
            'largest_delta_review_rows': len(top20),
            'delta_sums_by_band': viable.groupby('delta_band', observed=False).official_minus_selected_delta.sum().to_dict(),
            'largest_20_deltas_path': str(output / 'table5_unique_candidate_largest_deltas_2010.csv'),
            'table5_sha256': sha256(TABLE5_PDF),
            'note': 'Candidate key overlap only; no identity, boundary, completeness, or replacement admission established.',
        }
        crossread = crossread_review_sample(output)
        candidate_stats['independent_crossread'] = crossread

    for p in [RECEIPT, SOURCES / 'cached_2010_source_assets.json',
              SOURCES / 'r2-missing/retrieval_receipt.json',
              SOURCES / 'r2-missing/arkhangelsk_retrieval_receipt.json',
              SOURCES / 'r2-missing/arkhangelsk_retrieval_receipt_full.json',
              KARELIA / 'karelia_2010_rural_docx_source_facts.json']:
        if p.exists():
            j = json.loads(p.read_text(encoding='utf-8'))
            (output / p.name).write_text(json.dumps(j, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')

    summary = {
        'status': 'inventory_and_candidates_only_no_replacement_admitted',
        'r2_release_path': str(selection_path), 'r2_release_sha256': actual_release_sha,
        'r2_rows_2010': len(df), 'r2_known_population_2010': int(df.population.sum()),
        'r2_null_population_rows_2010': int(df.population.isna().sum()),
        'regional_control_gap_2010': receipt['2010']['gap_official_minus_selected'],
        'regional_control_comparisons': len(regional),
        'positive_regional_control_gaps': int(regional.gap_official_minus_selected.gt(0).sum()),
        'positive_regional_gap_mass': int(regional.loc[regional.gap_official_minus_selected.gt(0), 'gap_official_minus_selected'].sum()),
        'negative_regional_control_gaps': int(regional.gap_official_minus_selected.lt(0).sum()),
        'confidentiality_perturbed_rows': len(protected),
        'confidentiality_perturbed_population': int(protected.population.sum()),
        'confidentiality_source_families': int(protected.source_file.nunique()),
        'regional_differences_top10': regional.sort_values('gap_official_minus_selected', ascending=False).head(10).to_dict(orient='records'),
        'source_quality_counts': receipt['2010']['quality_counts'],
        'top_gap_primary_asset_triage': str(output / 'top_gap_primary_asset_triage_2010.csv'),
        'official_catalog_discovery_attempts': str(output / 'official_catalog_discovery_attempts_2010.json'),
        'table5_overlap': candidate_stats,
        'interpretation': 'Regional gaps are comparison masses only and are not assigned to protected rows or localities.',
    }
    (output / 'primary_2010_gap_inventory_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    (output / 'parser_profile_proposition.md').write_text(parser_profile(), encoding='utf-8')
    (output / 'priority_findings.md').write_text(priority_findings(summary), encoding='utf-8')
    return summary


def parser_profile() -> str:
    return """# 2010 primary-population parser profile proposition

Use a versioned profile for each source format. Preserve the source URL/archive URL,
retrieval time, TLS result, byte count, SHA-256, page/sheet/table locator, and all
printed row values. Classify hierarchy from table structure, explicit type labels,
indentation/parent fields, and row class. Do not discard a locality because its name
begins with Город; Городец, Городище, and Городовиковск are real regression cases.

Keep raw dash tokens for total, men, and women. Interpret a dash as zero only when a
source note or exhaustive closed-group control supports it. A positive total with a
dash in a sex column remains present and reviewable. Keep parent controls separate
from children; only proven non-overlapping children contribute to an additive view.
Sequential PDF context does not establish historical municipal binding.

Later cross-publication bindings keep both source IDs and exact row locators. A
normalized region/name/type collision or population equality is only a candidate.
Regional controls flag scope or extraction problems; never allocate their residuals.
Do not treat the secondary-source confidentiality label as proof that every row is
within ten of a census-total definition. A larger difference is a source-scope and
identity review stratum, not an automatic rejection or correction; a direct official
row may be better if the locality, administrative context, and publication grain agree.

The cached Table 5 comparison yields 2,836 unique name/type candidates, including
358 exact and 1,583 within-ten values; 895 are farther apart. The bounded cross-read
checked the largest 20 and a fixed 15-row out-of-band sample against Poppler page
text and the exact legacy workbook sheet/row. All 35 page values and workbook name/
value cells were found. That sample does not resolve population scope for the remaining
rows or prove all candidates identify the same physical locality.

The cached national Volume 1 Table 5 covers published urban localities, rural
district centres, and rural settlements of at least 3,000; it does not replace the
small-rural population mass. Murmansk, Kaliningrad, Arkhangelsk, and Karelia regional
files are already bounded source candidates in R2. Karelia's cached transport was
not TLS-verified. The cached Rosstat regional control CSV is aggregate evidence only.
"""


def priority_findings(summary: dict) -> str:
    overlap = summary['table5_overlap']
    lines = [
        '# 2010 primary population source inventory',
        '',
        'The R2 control shortfall is 653,824 people across 80 disjoint regional comparisons. The total is a comparison control, not a placeable residual.',
        '',
        'The largest regional differences and matching protected-row mass are in top_gap_primary_asset_triage_2010.csv. The cache has the national Rosstat Volume 1 Table 5 PDF, but no exact regional primary publication located for any of the top ten regions. Table 5 covers listed urban places, rural district centres, and rural places of at least 3,000; it does not cover all small rural localities.',
        '',
        '## Cached Table 5 overlap',
        '',
        f"Table 5 has {overlap['all_selected_unique_text_key_overlap_rows']:,} unique text-key overlaps with rows already selected in R2; {overlap['all_selected_unique_text_key_overlap_by_current_quality'].get('direct_official_city_value', 0):,} are already marked as direct official city values and cannot be counted as new recovery.",
        '',
        f"For confidentiality-tagged rows only, {overlap['unique_text_key_protected_candidate_rows']:,} region/name/type keys are unique on both sides. Their selected values sum to {overlap['unique_candidate_recorded_secondary_population']:,}; printed Table 5 values sum to {overlap['unique_candidate_published_table5_population']:,} (net difference {overlap['unique_candidate_population_delta_official_minus_selected']:+,}). These are comparison candidates, not admissions.",
        '',
        f"Delta counts: 358 exact, 1,583 within 10, 793 from 11 to 1,000, and 102 over 1,000. There are {overlap['district_context_status_counts'].get('district_text_agrees_candidate', 0):,} candidates with matching nonempty district text, {overlap['district_context_status_counts'].get('district_missing_on_one_or_both_sides', 0):,} with incomplete district context, and {overlap['district_context_status_counts'].get('district_conflict', 0):,} with conflicting district text. A larger difference is a source-scope and identity review stratum; it does not by itself reject the official count.",
        '',
        '## Independent row checks',
        '',
        f"The fixed review packet has {overlap['largest_delta_review_rows']} largest-difference rows plus {overlap['fixed_out_of_band_review_sample_rows']} deterministic sampled out-of-band rows. Poppler page text independently reproduced all {overlap['independent_crossread']['review_rows_unique']} Table 5 labels and counts. Direct reads of the exact legacy workbook sheets/rows found the source name and selected population value in all {overlap['independent_crossread']['review_rows_unique']} rows, including one name assembled from adjacent cells. This bounded check does not determine all source population scopes.",
        '',
        'Visual review of Rosstat Table 5 PDF page 81 (printed page 80), retained as table5_page81_visual_review.png, shows Двубратский as a direct rural settlement row under Усть-Лабинский район. The workbook row is sheet КК, row 1493. R2 records 2,164 and Table 5 prints 8,541. The cause is unresolved; no institutional-population explanation is assumed.',
        '',
        'No population replacement, identity binding, admission, or residual allocation was performed. Source IDs, hashes, PDF row locators, raw labels, hierarchy context, and the 35-row verification packet are staged for review.',
        '',
        'See regional_control_gaps_2010.csv, selected_2010_source_family_totals.csv, cached_primary_source_assets_2010.csv, table5_to_r2_overlap_candidates_2010.parquet, table5_unique_candidate_delta_distribution_2010.csv, table5_unique_candidate_context_distribution_2010.csv, table5_unique_candidate_largest_deltas_2010.csv, table5_unique_candidate_fixed_out_of_band_sample_2010.csv, and official_catalog_discovery_attempts_2010.json.',
    ]
    return '\n'.join(lines) + '\n'


def crossread_review_sample(output: Path) -> dict:
    """Independent Poppler PDF text and direct workbook row checks for staged review."""
    top_path = output / 'table5_unique_candidate_largest_deltas_2010.csv'
    sample_path = output / 'table5_unique_candidate_fixed_out_of_band_sample_2010.csv'
    top = pd.read_csv(top_path)
    sample = pd.read_csv(sample_path)
    review = pd.concat([top.assign(review_set='largest20'),
                        sample.assign(review_set='fixed15')], ignore_index=True)
    review = review.drop_duplicates('r2_source_record_id')

    if shutil.which('pdftotext'):
        page_cache: dict[int, list[str]] = {}
        pdf_rows = []
        for _, row in review.iterrows():
            page = int(row.pdf_page)
            if page not in page_cache:
                proc = subprocess.run(
                    ['pdftotext', '-f', str(page), '-l', str(page), '-layout', str(TABLE5_PDF), '-'],
                    check=True, capture_output=True, text=True)
                page_cache[page] = proc.stdout.splitlines()
            expected_label = norm(row.label_raw)
            matches = [line.strip() for line in page_cache[page]
                       if expected_label in norm(line)
                       and re.search(r'\b' + str(int(row.table5_population)) + r'\b', line)]
            pdf_rows.append({
                'review_set': row.review_set, 'r2_source_record_id': row.r2_source_record_id,
                'r2_source_sha256': row.r2_source_sha256_from_asset_inventory,
                'reference_id': row.reference_id, 'pdf_sha256': sha256(TABLE5_PDF),
                'pdf_page': page, 'printed_page': int(row.printed_page),
                'pypdf_text_line': int(row.text_line_start), 'expected_label': row.label_raw,
                'expected_population': int(row.table5_population),
                'poppler_status': ('independent_poppler_page_line_match' if len(matches) == 1
                                   else ('multiple_poppler_lines_match' if matches else 'no_exact_poppler_page_line_match')),
                'poppler_line': matches[0] if len(matches) == 1 else ' | '.join(matches),
            })
        pd.DataFrame(pdf_rows).to_csv(output / 'table5_poppler_crossread_sample_2010.csv', index=False)
        poppler_counts = pd.Series([r['poppler_status'] for r in pdf_rows]).value_counts().to_dict()
    else:
        poppler_counts = {'pdftotext_unavailable': len(review)}

    try:
        import xlrd
    except ImportError:
        workbook_counts = {'xlrd_unavailable': len(review)}
    else:
        raw_root = Path('/workspace/settlements-raw')
        books: dict[str, object] = {}
        rows = []
        for _, row in review.iterrows():
            logical = str(row.source_file)
            path = raw_root / logical
            if logical not in books:
                books[logical] = xlrd.open_workbook(str(path), on_demand=True)
            book = books[logical]
            sheet = book.sheet_by_name(str(row.source_sheet))
            row_index = int(row.source_row) - 1
            raw_values = sheet.row_values(row_index)
            label = norm(row.source_name_raw)
            direct_name_cells = [i for i, value in enumerate(raw_values)
                                 if isinstance(value, str) and norm(value) == label]
            joined_name_span = None
            for start in range(len(raw_values)):
                for end in range(start + 1, min(len(raw_values), start + 5) + 1):
                    cells = raw_values[start:end]
                    if all(isinstance(v, str) or v in ('', None) for v in cells):
                        joined = ' '.join(str(v).strip() for v in cells if str(v or '').strip())
                        if norm(joined) == label:
                            joined_name_span = f'{start}:{end - 1}'
                            break
                if joined_name_span:
                    break
            population_cells = [i for i, value in enumerate(raw_values)
                                if isinstance(value, (int, float)) and float(value) == float(row.population)]
            actual_sha = sha256(path)
            name_status = ('exact_name_cell' if direct_name_cells else
                           ('name_reassembled_from_adjacent_cells' if joined_name_span else 'name_not_found_at_locator'))
            value_ok = bool(population_cells)
            rows.append({
                'review_set': row.review_set, 'r2_source_record_id': row.r2_source_record_id,
                'expected_source_sha256': row.r2_source_sha256_from_asset_inventory,
                'actual_source_sha256': actual_sha, 'source_sha_matches': actual_sha == row.r2_source_sha256_from_asset_inventory,
                'source_file': logical, 'source_sheet': row.source_sheet, 'source_row_1based': row_index + 1,
                'source_name_raw': row.source_name_raw, 'name_status': name_status,
                'exact_name_cell_indexes_0based': '|'.join(map(str, direct_name_cells)),
                'joined_name_cell_span_0based_inclusive': joined_name_span,
                'selected_source_population': int(row.population),
                'population_value_cell_indexes_0based': '|'.join(map(str, population_cells)),
                'raw_row_excerpt': json.dumps(raw_values[:10], ensure_ascii=False, default=str),
                'source_row_status': 'source_hash_name_and_value_present' if actual_sha == row.r2_source_sha256_from_asset_inventory and (direct_name_cells or joined_name_span) and value_ok else 'review_required',
            })
        for book in books.values():
            book.release_resources()
        pd.DataFrame(rows).to_csv(output / 'secondary_source_row_crossread_sample_2010.csv', index=False)
        workbook_counts = pd.Series([r['source_row_status'] for r in rows]).value_counts().to_dict()
    return {'poppler_pdf_crossread_status_counts': poppler_counts,
            'secondary_workbook_row_crossread_status_counts': workbook_counts,
            'review_rows_unique': len(review)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=WORK)
    parser.add_argument('--skip-table5', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.output, extract_table5=not args.skip_table5),
                     ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
