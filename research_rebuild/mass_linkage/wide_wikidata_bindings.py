"""Exact-code candidates from the broader frozen Wikidata/Wikipedia extracts.

No candidate here is an identity or coordinate admission. The TSV is a flat
query result (not a statement dump), and the module cache supplies points only.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .wikidata_evidence import normalize_code
from .coordinate_rules import haversine_km, valid_wgs84, in_broad_russia_envelope

SELECTED = Path('/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet')
TSV = Path('/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv')
MODULE = Path('/workspace/settlements-raw/data/raw/wikipedia_statistical/module_qid_entities.jsonl.gz')
TRUTHY = Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims')
COORDINATE_LEDGER = Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet')
OUTPUT = Path('/workspace/settlements-work/wikidata/wide')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def qid(value: Any) -> str | None:
    match = re.search(r'Q\d+', str(value or ''))
    return match.group(0) if match else None


def rdf_text(value: Any) -> str | None:
    """Extract text from the observed TSV's quoted literal / @lang syntax."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    match = re.match(r'^"((?:\\.|[^"\\])*)"(?:@[A-Za-z-]+|\^\^<[^>]+>)?$', raw)
    if match:
        return re.sub(r'\\(["\\])', r'\1', match.group(1))
    # csv.DictReader removes the literal's quotes but leaves the RDF language suffix.
    raw = re.sub(r'@[A-Za-z-]+$', '', raw)
    return raw.strip('<>')


def name_key(value: Any) -> str:
    import unicodedata
    text = unicodedata.normalize('NFKC', str(value or '')).casefold().replace('ё', 'е')
    return ' '.join(re.sub(r'[^\w]+', ' ', text).split())


def first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is None or pd.isna(value) or not str(value).strip():
            continue
        return value
    return None


def parse_point(value: Any) -> tuple[float | None, float | None]:
    match = re.fullmatch(r'\s*POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)\s*', str(value or ''), re.I)
    if not match:
        return None, None
    lon, lat = map(float, match.groups())
    return (lat, lon) if valid_wgs84(lat, lon) else (None, None)


def read_module(path: Path) -> tuple[dict[str, list[dict[str, Any]]], int]:
    points: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = 0
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            rows += 1
            row = json.loads(line)
            entity = qid(row.get('item'))
            lat, lon = parse_point(row.get('coord'))
            if entity and lat is not None:
                points[entity].append({'latitude': lat, 'longitude': lon, 'raw_point': row.get('coord'), 'line': line_no})
    return dict(points), rows


def truthy_property(value: Any) -> str:
    return str(value or '').rsplit('/', 1)[-1]


def truthy_value(value: Any) -> str | None:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return normalize_code(value)


def read_truthy(path: Path, source_by_code: dict[str, list[int]], source_by_okato: dict[str, list[int]],
                selected: pd.DataFrame) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], dict[str, dict[str, list[dict[str, Any]]]], dict[str, dict[str, list[dict[str, Any]]]], dict[str, Any], list[dict[str, str]]]:
    """Index direct exact P764 candidates, same-QID P721 checks and their cached claims."""
    files = sorted(path.glob('batch*.jsonl.gz'))
    wanted_oktmo = set(source_by_code)
    wanted_okato = set(source_by_okato)
    p764: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    p721: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    receipts: set[str] = set()
    total = 0
    for batch in files:
        with gzip.open(batch, 'rt', encoding='utf-8') as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                row = json.loads(line); total += 1
                prop = truthy_property(row.get('property'))
                if prop not in {'P764', 'P721'}:
                    continue
                code = normalize_code(row.get('value'))
                q = qid(row.get('item'))
                if not q or not code:
                    continue
                receipt = row.get('retrieved_at_utc')
                if receipt:
                    receipts.add(str(receipt))
                record = {'value_raw': row.get('value'), 'value_exact_digits': code, 'source_file': batch.name,
                          'line_number': line_no, 'retrieved_at_utc': receipt}
                if prop == 'P764' and code in wanted_oktmo:
                    p764[code][q].append(record)
                elif prop == 'P721' and code in wanted_okato:
                    p721[code][q].append(record)
    candidate_qids = {q for values in p764.values() for q in values}
    info: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    properties = {'P625', 'P31', 'P131', 'P17'}
    if candidate_qids:
        for batch in files:
            with gzip.open(batch, 'rt', encoding='utf-8') as stream:
                for line_no, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    q = qid(row.get('item')); prop = truthy_property(row.get('property'))
                    if q not in candidate_qids or prop not in properties:
                        continue
                    raw = row.get('value')
                    record: dict[str, Any] = {'value_raw': raw, 'source_file': batch.name,
                                              'line_number': line_no, 'retrieved_at_utc': row.get('retrieved_at_utc')}
                    if prop == 'P625':
                        lat, lon = parse_point(raw)
                        record.update({'latitude': lat, 'longitude': lon, 'wgs84_valid': lat is not None})
                    else:
                        record['value_qid'] = qid(raw)
                    info[q][prop].append(record)
    binding_p764: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    binding_p721: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for code, qid_map in p764.items():
        for q, claims in qid_map.items():
            binding_p764[code][q].extend(claims)
    for code, qid_map in p721.items():
        for q, claims in qid_map.items():
            binding_p721[code][q].extend(claims)
    hashes = [{'path': str(f), 'sha256': sha256(f)} for f in files]
    summary = {'truthy_file_count': len(files), 'truthy_statement_rows': total,
               'truthy_retrieval_receipts': sorted(receipts),
               'truthy_exact_p764_codes_matched': len(binding_p764),
               'truthy_p764_code_qid_pairs': sum(len(v) for v in binding_p764.values()),
               'truthy_exact_p764_candidate_qids': len(candidate_qids),
               'truthy_exact_p721_codes_matching_selected_projection': len(binding_p721),
               'truthy_p721_code_qid_pairs': sum(len(v) for v in binding_p721.values()),
               'truthy_candidate_qids_with_p625': sum(bool(claims.get('P625')) for claims in info.values()),
               'truthy_candidate_qids_with_p31': sum(bool(claims.get('P31')) for claims in info.values()),
               'truthy_candidate_qids_with_p131': sum(bool(claims.get('P131')) for claims in info.values()),
               'truthy_candidate_qids_with_p17': sum(bool(claims.get('P17')) for claims in info.values())}
    return dict(binding_p764), dict(binding_p721), dict(info), summary, hashes


def read_tsv(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Index only literal exact P764 codes; preserve raw cells and TSV lines."""
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    n = 0
    with path.open('r', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        expected = ['?item', '?oktmo', '?okato', '?coord', '?label', '?article', '?admin', '?adminLabel']
        if reader.fieldnames != expected:
            raise ValueError(f'unexpected TSV schema: {reader.fieldnames!r}')
        for line_no, row in enumerate(reader, 2):
            n += 1
            raw_code = row.get('?oktmo', '')
            code = normalize_code(rdf_text(raw_code))
            entity = qid(row.get('?item'))
            if not code or not entity:
                continue
            lat, lon = parse_point(row.get('?coord'))
            index[code].append({
                'qid': entity, 'tsv_line': line_no, 'raw_oktmo': raw_code,
                'raw_okato': row.get('?okato', ''), 'okato': normalize_code(rdf_text(row.get('?okato'))),
                'label_raw': row.get('?label', ''), 'label_ru': rdf_text(row.get('?label')),
                'article_raw': row.get('?article', ''), 'admin_raw': row.get('?admin', ''),
                'admin_qid': qid(row.get('?admin')), 'admin_label_raw': row.get('?adminLabel', ''),
                'admin_label_ru': rdf_text(row.get('?adminLabel')),
                'point_raw': row.get('?coord', ''), 'latitude': lat, 'longitude': lon,
            })
    unique_rows = sum(len(v) for v in index.values())
    qids = {row['qid'] for rows in index.values() for row in rows}
    return dict(index), {'tsv_data_rows': n, 'rows_with_parseable_qid_and_exact_digits_code': unique_rows,
                        'distinct_exact_oktmo_codes': len(index), 'distinct_qids': len(qids),
                        'codes_linking_multiple_qids': sum(len({r['qid'] for r in rows}) > 1 for rows in index.values())}


def build(selected_path: Path = SELECTED, tsv_path: Path = TSV, module_path: Path = MODULE,
          ledger_path: Path = COORDINATE_LEDGER, output_dir: Path = OUTPUT) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = pd.read_parquet(selected_path)
    selected = selected.loc[selected.census_year.eq(2021)].copy()
    selected['source_record_id'] = selected.source_record_id.astype(str)
    selected['source_oktmo_exact_digits'] = selected.oktmo.map(normalize_code)
    if selected.source_record_id.duplicated().any():
        raise ValueError('source_record_id must be unique in selected 2021 R2')
    source_by_code: dict[str, list[int]] = defaultdict(list)
    for ix, code in enumerate(selected.source_oktmo_exact_digits):
        if code:
            source_by_code[code].append(ix)

    tsv_index, tsv_meta = read_tsv(tsv_path)
    module_points, module_rows = read_module(module_path)
    source_by_okato: dict[str, list[int]] = defaultdict(list)
    for ix, code in enumerate(selected.okato.map(normalize_code)):
        if code:
            source_by_okato[code].append(ix)
    truthy_p764, truthy_p721, truthy_info, truthy_meta, truthy_hashes = read_truthy(
        TRUTHY, source_by_code, source_by_okato, selected)
    if ledger_path.is_file():
        ledger = pd.read_parquet(ledger_path, columns=['source_record_id', 'provider_latitude', 'provider_longitude', 'raw_oktmo_dadata', 'raw_fias_id_dadata', 'raw_fias_level_dadata', 'raw_object_level', 'raw_settlement_dadata', 'raw_settlement_type_full_dadata', 'provider_general_fias_duplicate_count', 'provider_coordinate_duplicate_count', 'baseline_provider_coordinate_conflict', 'provider_name_exact_selected_name', 'provider_type_exact_selected_type'])
        ledger['source_record_id'] = ledger.source_record_id.astype(str)
        selected = selected.merge(ledger.rename(columns={'provider_latitude': 'dadata_latitude', 'provider_longitude': 'dadata_longitude'}), on='source_record_id', how='left', validate='one_to_one')
    else:
        for col in ['dadata_latitude', 'dadata_longitude', 'raw_oktmo_dadata', 'raw_fias_id_dadata', 'raw_fias_level_dadata']:
            selected[col] = None

    provider_codes = pd.DataFrame()
    provider_code_metrics: dict[str, Any] = {}
    if ledger_path.is_file():
        provider_codes = selected.copy()
        provider_codes['source_oktmo_raw_preserved'] = provider_codes.oktmo
        provider_codes['provider_oktmo_raw_preserved'] = provider_codes.raw_oktmo_dadata
        provider_codes['source_oktmo_code_normalized'] = provider_codes.oktmo.map(normalize_code)
        provider_codes['provider_oktmo_code_normalized_dot_zero_only'] = provider_codes.raw_oktmo_dadata.astype('string').fillna('').str.strip().str.replace(r'\.0+$', '', regex=True).map(normalize_code)
        provider_codes['provider_code_normalization_note'] = 'terminal .0 removed only; no zero padding/truncation'
        provider_codes['source_provider_oktmo_exact_match'] = (
            provider_codes.source_oktmo_code_normalized.notna()
            & provider_codes.source_oktmo_code_normalized.eq(provider_codes.provider_oktmo_code_normalized_dot_zero_only)
        )
        provider_codes['source_oktmo_digit_width'] = provider_codes.source_oktmo_code_normalized.str.len()
        provider_codes['provider_oktmo_digit_width'] = provider_codes.provider_oktmo_code_normalized_dot_zero_only.str.len()
        provider_codes['source_is_physical_np'] = provider_codes.raw_object_level.astype('string').str.casefold().isin(['населенный пункт', 'населённый пункт'])
        provider_codes['provider_primary_fias_level_4_or_6'] = provider_codes.raw_fias_level_dadata.astype('string').isin(['4', '6'])
        provider_codes['provider_point_valid_wgs84'] = [valid_wgs84(a, b) for a, b in zip(provider_codes.dadata_latitude, provider_codes.dadata_longitude)]
        provider_codes['provider_point_inside_coarse_russia'] = [in_broad_russia_envelope(a, b) for a, b in zip(provider_codes.dadata_latitude, provider_codes.dadata_longitude)]
        provider_codes['provider_id_unique'] = provider_codes.provider_general_fias_duplicate_count.eq(1)
        provider_codes['provider_point_unique'] = provider_codes.provider_coordinate_duplicate_count.eq(1)
        provider_codes['no_baseline_hard_coordinate_conflict'] = ~provider_codes.baseline_provider_coordinate_conflict.fillna(False).astype(bool)
        provider_codes['provider_own_name_payload_present'] = provider_codes.raw_settlement_dadata.notna() & provider_codes.raw_settlement_dadata.astype('string').fillna('').ne('')
        provider_codes['provider_own_type_payload_present'] = provider_codes.raw_settlement_type_full_dadata.notna() & provider_codes.raw_settlement_type_full_dadata.astype('string').fillna('').ne('')
        provider_codes['provider_own_name_and_type_exact'] = provider_codes.provider_name_exact_selected_name.fillna(False) & provider_codes.provider_type_exact_selected_type.fillna(False)
        provider_codes['provider_code_candidate_core'] = (
            provider_codes.source_is_physical_np & provider_codes.provider_primary_fias_level_4_or_6
            & provider_codes.source_provider_oktmo_exact_match & provider_codes.provider_id_unique
            & provider_codes.provider_point_unique & provider_codes.provider_point_valid_wgs84
            & provider_codes.provider_point_inside_coarse_russia & provider_codes.no_baseline_hard_coordinate_conflict
        )
        provider_codes['city_level4_missing_name_type_exception_candidate'] = (
            provider_codes.provider_code_candidate_core & provider_codes.settlement_type.astype('string').str.casefold().eq('город')
            & provider_codes.raw_fias_level_dadata.astype('string').eq('4')
            & (~provider_codes.provider_own_name_payload_present | ~provider_codes.provider_own_type_payload_present)
        )
        provider_codes['strict_named_type_provider_code_candidate'] = provider_codes.provider_code_candidate_core & provider_codes.provider_own_name_and_type_exact
        provider_codes['unresolved_code_match_candidate'] = provider_codes.provider_code_candidate_core & ~provider_codes.strict_named_type_provider_code_candidate & ~provider_codes.city_level4_missing_name_type_exception_candidate
        provider_codes['coordinate_or_identity_admission'] = False
        provider_codes['candidate_status'] = 'hold_unexplained_code_or_name_or_object_or_coordinate'
        provider_codes.loc[provider_codes.provider_code_candidate_core, 'candidate_status'] = 'provider_oktmo_exact_code_review_candidate'
        provider_codes.loc[provider_codes.strict_named_type_provider_code_candidate, 'candidate_status'] = 'exact_source_provider_code_plus_own_name_type_review_candidate'
        provider_codes.loc[provider_codes.city_level4_missing_name_type_exception_candidate, 'candidate_status'] = 'city_level4_missing_provider_name_type_exception_requires_review'
        provider_code_metrics = {
            'selected_rows_with_source_provider_oktmo_exact_match': int(provider_codes.source_provider_oktmo_exact_match.sum()),
            'source_population_with_source_provider_oktmo_exact_match': int(provider_codes.loc[provider_codes.source_provider_oktmo_exact_match, 'population'].fillna(0).sum()),
            'provider_code_candidate_core_rows': int(provider_codes.provider_code_candidate_core.sum()),
            'provider_code_candidate_core_population': int(provider_codes.loc[provider_codes.provider_code_candidate_core, 'population'].fillna(0).sum()),
            'strict_named_type_provider_code_candidate_rows': int(provider_codes.strict_named_type_provider_code_candidate.sum()),
            'strict_named_type_provider_code_candidate_population': int(provider_codes.loc[provider_codes.strict_named_type_provider_code_candidate, 'population'].fillna(0).sum()),
            'city_level4_missing_name_type_exception_rows': int(provider_codes.city_level4_missing_name_type_exception_candidate.sum()),
            'city_level4_missing_name_type_exception_population': int(provider_codes.loc[provider_codes.city_level4_missing_name_type_exception_candidate, 'population'].fillna(0).sum()),
            'unresolved_code_match_candidate_rows': int(provider_codes.unresolved_code_match_candidate.sum()),
            'unresolved_code_match_candidate_population': int(provider_codes.loc[provider_codes.unresolved_code_match_candidate, 'population'].fillna(0).sum()),
            'source_oktmo_digit_width_frequency': {str(int(k)): int(v) for k, v in provider_codes.source_oktmo_digit_width.dropna().value_counts().sort_index().items()},
            'provider_oktmo_digit_width_frequency_after_dot_zero_only': {str(int(k)): int(v) for k, v in provider_codes.provider_oktmo_digit_width.dropna().value_counts().sort_index().items()},
            'candidate_core_by_source_type': {},
            'candidate_core_by_provider_fias_level': {},
        }
        for key, group in provider_codes.loc[provider_codes.provider_code_candidate_core].groupby('settlement_type', dropna=False):
            provider_code_metrics['candidate_core_by_source_type'][str(key)] = {
                'rows': int(len(group)), 'population': int(group.population.fillna(0).sum()),
                'strict_named_type_rows': int(group.strict_named_type_provider_code_candidate.sum()),
                'strict_named_type_population': int(group.loc[group.strict_named_type_provider_code_candidate, 'population'].fillna(0).sum()),
                'city_exception_rows': int(group.city_level4_missing_name_type_exception_candidate.sum()),
                'city_exception_population': int(group.loc[group.city_level4_missing_name_type_exception_candidate, 'population'].fillna(0).sum()),
            }
        for key, group in provider_codes.loc[provider_codes.provider_code_candidate_core].groupby('raw_fias_level_dadata', dropna=False):
            provider_code_metrics['candidate_core_by_provider_fias_level'][str(key)] = {
                'rows': int(len(group)), 'population': int(group.population.fillna(0).sum()),
                'strict_named_type_rows': int(group.strict_named_type_provider_code_candidate.sum()),
                'strict_named_type_population': int(group.loc[group.strict_named_type_provider_code_candidate, 'population'].fillna(0).sum()),
                'city_exception_rows': int(group.city_level4_missing_name_type_exception_candidate.sum()),
                'city_exception_population': int(group.loc[group.city_level4_missing_name_type_exception_candidate, 'population'].fillna(0).sum()),
            }
        provider_codes.to_parquet(output_dir / 'provider_code_candidate_screen.parquet', index=False)

    output_rows: list[dict[str, Any]] = []
    for ix, source in selected.reset_index(drop=True).iterrows():
        code = source.source_oktmo_exact_digits
        if not code:
            continue
        hits = tsv_index.get(code, [])
        truthy_code_matches = truthy_p764.get(code, {})
        candidate_qids = {r['qid'] for r in hits} | set(truthy_code_matches)
        if not candidate_qids:
            continue
        source_name = first_nonempty(source.get('settlement_name'), source.get('source_name_raw'))
        for candidate_qid in sorted(candidate_qids):
            qr = [r for r in hits if r['qid'] == candidate_qid]
            truthy_match_claims = truthy_code_matches.get(candidate_qid, [])
            truthy_props = truthy_info.get(candidate_qid, {})
            labels = sorted({r['label_ru'] for r in qr if r['label_ru']})
            admins = sorted({r['admin_label_ru'] for r in qr if r['admin_label_ru']})
            admin_qids = sorted({r['admin_qid'] for r in qr if r['admin_qid']})
            article_urls = sorted({r['article_raw'].strip('<>') for r in qr if r['article_raw']})
            tsv_points = sorted({(r['latitude'], r['longitude']) for r in qr if r['latitude'] is not None})
            module_qid_points = module_points.get(candidate_qid, [])
            truthy_point_rows = [p for p in truthy_props.get('P625', []) if p.get('wgs84_valid')]
            point_rows = ([{'latitude': a, 'longitude': b, 'source_kind': 'wikimedia_oktmo_tsv'} for a, b in tsv_points]
                          + [{'latitude': p['latitude'], 'longitude': p['longitude'], 'source_kind': 'wikipedia_statistical_module', 'module_line': p['line'], 'raw_point': p['raw_point']} for p in module_qid_points]
                          + [{'latitude': p['latitude'], 'longitude': p['longitude'], 'source_kind': 'wikidata_truthy_claim_cache', 'truthy_line': p['line_number'], 'source_file': p['source_file'], 'retrieved_at_utc': p['retrieved_at_utc'], 'raw_point': p['value_raw']} for p in truthy_point_rows])
            dists = [haversine_km(source.get('dadata_latitude'), source.get('dadata_longitude'), p['latitude'], p['longitude']) for p in point_rows]
            dists = [d for d in dists if d is not None]
            raw_okato_values = sorted({r['okato'] for r in qr if r['okato']})
            source_okato = normalize_code(source.get('okato'))
            p721_qid_matches = truthy_p721.get(source_okato, {}).get(candidate_qid, []) if source_okato else []
            output_rows.append({
                'source_record_id': source.source_record_id,
                'source_row': source.get('source_row'),
                'census_year': 2021,
                'source_oktmo_raw': source.oktmo,
                'source_oktmo_exact_digits': code,
                'source_oktmo_digit_width': len(code),
                'source_okato_projection_raw': source.get('okato'),
                'source_okato_projection_exact_digits': source_okato,
                'source_okato_projection_role_caveat': 'R2 selected projection; not asserted independent of other copied/provider sources',
                'source_name': source_name,
                'source_type': source.get('settlement_type'),
                'source_region': source.get('region_raw'),
                'source_district': source.get('district_raw'),
                'source_municipality': source.get('municipality_raw'),
                'source_population': source.get('population'),
                'source_population_scope': source.get('population_scope'),
                'wikidata_qid': candidate_qid,
                'wikidata_tsv_exact_p764_value_raw': sorted({r['raw_oktmo'] for r in qr})[0] if qr else None,
                'wikidata_truthy_exact_p764_claims_json': json.dumps(truthy_match_claims, ensure_ascii=False, sort_keys=True),
                'wikidata_truthy_exact_p764_match': bool(truthy_match_claims),
                'wikidata_truthy_exact_p721_projection_match_same_qid': bool(p721_qid_matches),
                'wikidata_truthy_exact_p721_claims_json': json.dumps(p721_qid_matches, ensure_ascii=False, sort_keys=True),
                'wikidata_truthy_p31_claims_json': json.dumps(truthy_props.get('P31', []), ensure_ascii=False, sort_keys=True),
                'wikidata_truthy_p131_claims_json': json.dumps(truthy_props.get('P131', []), ensure_ascii=False, sort_keys=True),
                'wikidata_truthy_p17_claims_json': json.dumps(truthy_props.get('P17', []), ensure_ascii=False, sort_keys=True),
                'wikidata_truthy_p625_claims_json': json.dumps(truthy_props.get('P625', []), ensure_ascii=False, sort_keys=True),
                'wikidata_tsv_matching_rows': len(qr),
                'wikidata_tsv_line_numbers_json': json.dumps(sorted(r['tsv_line'] for r in qr)),
                'wikidata_tsv_ru_labels_json': json.dumps(labels, ensure_ascii=False),
                'wikidata_name_exact_label': any(name_key(source_name) == name_key(label) for label in labels if name_key(label)),
                'wikidata_tsv_admin_qids_json': json.dumps(admin_qids),
                'wikidata_tsv_ru_admin_labels_json': json.dumps(admins, ensure_ascii=False),
                'wikidata_admin_context_available': bool(admins or admin_qids),
                'wikidata_tsv_article_urls_json': json.dumps(article_urls),
                'wikidata_tsv_okato_exact_values_json': json.dumps(raw_okato_values),
                'same_row_tsv_okato_matches_source_projection': bool(source_okato and source_okato in raw_okato_values),
                'okato_independence_established': False,
                'tsv_entity_competition_for_exact_oktmo': len({r['qid'] for r in hits}) > 1,
                'truthy_entity_competition_for_exact_oktmo': len(truthy_code_matches) > 1,
                'entity_competition_across_tsv_or_truthy': len(candidate_qids) > 1,
                'source_observation_competition_for_exact_oktmo': len(source_by_code[code]) > 1,
                'module_point_count': len(module_points.get(candidate_qid, [])),
                'tsv_distinct_point_count': len(tsv_points),
                'module_point_count_raw': len(module_qid_points),
                'truthy_p625_point_count': len(truthy_point_rows),
                'distinct_tsv_or_module_points_count': len({(p['latitude'], p['longitude']) for p in point_rows}),
                'wikimedia_point_sources_same_qid_overlap': bool(set(tsv_points) & {(p['latitude'], p['longitude']) for p in module_qid_points}),
                'any_wikidata_truthy_point_overlaps_tsv_or_module': bool({(p['latitude'], p['longitude']) for p in truthy_point_rows} & {(p['latitude'], p['longitude']) for p in point_rows if p['source_kind'] != 'wikidata_truthy_claim_cache'}),
                'points_json': json.dumps(point_rows, sort_keys=True),
                'points_all_wgs84_valid': all(valid_wgs84(p['latitude'], p['longitude']) for p in point_rows),
                'points_all_inside_coarse_russia_envelope': all(in_broad_russia_envelope(p['latitude'], p['longitude']) for p in point_rows),
                'nearest_wide_point_to_dadata_km': min(dists) if dists else None,
                'farthest_wide_point_to_dadata_km': max(dists) if dists else None,
                'dadata_provider_oktmo_raw': source.get('raw_oktmo_dadata'),
                'dadata_provider_oktmo_exact_digits': normalize_code(source.get('raw_oktmo_dadata')),
                'dadata_fias_id': source.get('raw_fias_id_dadata'),
                'dadata_fias_level': source.get('raw_fias_level_dadata'),
                'candidate_status': 'exact_code_candidate_requires_object_and_coordinate_review',
                'identity_admission': False,
                'coordinate_admission': False,
            })

    bindings = pd.DataFrame(output_rows)
    if not bindings.empty:
        bindings.to_parquet(output_dir / 'wide_point_bindings.parquet', index=False)
    else:
        pd.DataFrame(columns=['source_record_id', 'wikidata_qid']).to_parquet(output_dir / 'wide_point_bindings.parquet', index=False)

    module_qids = set(module_points)
    truthy_source_record_ids = set()
    for _, source in selected.reset_index(drop=True).iterrows():
        code = source.source_oktmo_exact_digits
        if code and truthy_p764.get(code):
            truthy_source_record_ids.add(str(source.source_record_id))
    tsv_source_record_ids = {str(source.source_record_id) for _, source in selected.iterrows()
                             if source.source_oktmo_exact_digits and tsv_index.get(source.source_oktmo_exact_digits)}
    summary: dict[str, Any] = {
        'selected_2021_rows': int(len(selected)),
        'selected_2021_population': int(pd.to_numeric(selected.population, errors='coerce').fillna(0).sum()),
        'selected_unique_exact_oktmo_values': len(source_by_code),
        'raw_tsv': tsv_meta,
        'module_jsonl_rows': module_rows,
        'module_distinct_qids_with_valid_wgs84_point': len(module_qids),
        'truthy_claim_cache': truthy_meta,
        'source_rows_with_exact_tsv_code_candidate': len(tsv_source_record_ids),
        'source_population_with_exact_tsv_code_candidate': int(selected.loc[selected.source_record_id.astype(str).isin(tsv_source_record_ids), 'population'].fillna(0).sum()),
        'source_rows_with_exact_truthy_p764_candidate': len(truthy_source_record_ids),
        'source_population_with_exact_truthy_p764_candidate': int(selected.loc[selected.source_record_id.astype(str).isin(truthy_source_record_ids), 'population'].fillna(0).sum()),
        'source_rows_with_exact_tsv_or_truthy_candidate': len(tsv_source_record_ids | truthy_source_record_ids),
        'source_population_with_exact_tsv_or_truthy_candidate': int(selected.loc[selected.source_record_id.astype(str).isin(tsv_source_record_ids | truthy_source_record_ids), 'population'].fillna(0).sum()),
        'truthy_only_candidate_source_rows': len(truthy_source_record_ids - tsv_source_record_ids),
        'tsv_and_truthy_overlap_source_rows': len(truthy_source_record_ids & tsv_source_record_ids),
        'provider_code_candidate_screen': provider_code_metrics,
        'source_rows_with_any_exact_tsv_p764_candidate': int(bindings.source_record_id.nunique()) if not bindings.empty else 0,
        'source_population_with_any_exact_tsv_p764_candidate': int(bindings.drop_duplicates('source_record_id').source_population.fillna(0).sum()) if not bindings.empty else 0,
        'candidate_bindings': int(len(bindings)),
        'candidate_qids': int(bindings.wikidata_qid.nunique()) if not bindings.empty else 0,
        'candidate_bindings_with_ru_label_exact': int(bindings.wikidata_name_exact_label.sum()) if not bindings.empty else 0,
        'candidate_bindings_with_admin_label_or_qid': int(bindings.wikidata_admin_context_available.sum()) if not bindings.empty else 0,
        'candidate_bindings_with_tsv_or_module_point': int(bindings.distinct_tsv_or_module_points_count.gt(0).sum()) if not bindings.empty else 0,
        'candidate_bindings_with_multiple_distinct_points': int(bindings.distinct_tsv_or_module_points_count.gt(1).sum()) if not bindings.empty else 0,
        'candidate_bindings_with_tsv_coordinate': int(bindings.tsv_distinct_point_count.gt(0).sum()) if not bindings.empty else 0,
        'candidate_bindings_with_module_coordinate': int(bindings.module_point_count_raw.gt(0).sum()) if not bindings.empty else 0,
        'candidate_bindings_with_truthy_p625_point': int(bindings.truthy_p625_point_count.gt(0).sum()) if not bindings.empty else 0,
        'candidate_bindings_truthy_point_overlaps_tsv_or_module': int(bindings.any_wikidata_truthy_point_overlaps_tsv_or_module.sum()) if not bindings.empty else 0,
        'candidate_bindings_tsv_module_same_point_overlap': int(bindings.wikimedia_point_sources_same_qid_overlap.sum()) if not bindings.empty else 0,
        'candidate_bindings_multiple_qids_in_tsv_for_code': int(bindings.tsv_entity_competition_for_exact_oktmo.sum()) if not bindings.empty else 0,
        'candidate_bindings_multiple_qids_in_truthy_for_code': int(bindings.truthy_entity_competition_for_exact_oktmo.sum()) if not bindings.empty else 0,
        'candidate_bindings_multiple_qids_across_tsv_or_truthy': int(bindings.entity_competition_across_tsv_or_truthy.sum()) if not bindings.empty else 0,
        'candidate_bindings_source_code_competition': int(bindings.source_observation_competition_for_exact_oktmo.sum()) if not bindings.empty else 0,
        'candidate_bindings_same_row_okato_projection_match': int(bindings.same_row_tsv_okato_matches_source_projection.sum()) if not bindings.empty else 0,
        'candidate_bindings_coordinate_within_0_5km_of_dadata': int(bindings.nearest_wide_point_to_dadata_km.le(.5).sum()) if not bindings.empty else 0,
        'candidate_bindings_coordinate_over_5km_from_dadata': int(bindings.nearest_wide_point_to_dadata_km.gt(5).sum()) if not bindings.empty else 0,
        'point_and_name_or_admin_strata_by_source_type': {},
        'admissions': 0,
    }
    if not bindings.empty:
        for source_type, group in bindings.groupby('source_type', dropna=False):
            unique_sources = group.drop_duplicates('source_record_id')
            summary['point_and_name_or_admin_strata_by_source_type'][str(source_type)] = {
                'candidate_rows': int(len(group)),
                'candidate_source_population_unique': int(unique_sources.source_population.fillna(0).sum()),
                'point_rows': int(group.distinct_tsv_or_module_points_count.gt(0).sum()),
                'exact_label_rows': int(group.wikidata_name_exact_label.sum()),
                'admin_context_rows': int(group.wikidata_admin_context_available.sum()),
            }

    manifest = {
        'implementation_version': 'wide_exact_p764_code_screen_v1',
        'implementation_sha256': sha256(Path(__file__)),
        'status': 'exact-code-candidates-only-no-identity-or-coordinate-admissions',
        'method': 'exact normalized source R2 P764-like OKTMO digit string join to literal ?oktmo in frozen Wikimedia TSV; no padding/truncation/fuzzy name join',
        'sources': {
            'selected_r2': {'path': str(selected_path), 'sha256': sha256(selected_path)},
            'wikimedia_oktmo_entities_tsv': {'path': str(tsv_path), 'sha256': sha256(tsv_path), 'header': ['?item','?oktmo','?okato','?coord','?label','?article','?admin','?adminLabel']},
            'wikipedia_statistical_module_qid_entities': {'path': str(module_path), 'sha256': sha256(module_path), 'schema_observed': {'item':'QID URI','coord':'POINT(longitude latitude)'}},
            'wikidata_truthy_claims_directory': {'path': str(TRUTHY), 'files': truthy_hashes},
            'coordinate_ledger_optional_join': {'path': str(ledger_path), 'sha256': sha256(ledger_path) if ledger_path.is_file() else None},
        },
        'source_semantics': {
            'tsv': 'Flat frozen extract with P764-like OKTMO, OKATO, P625 coordinate, ru label/article and administrative QID/label; original statement IDs, ranks, qualifiers, references, retrieval time, and P31 object type are not present.',
            'module': 'Wikipedia Statistical module QID-to-point cache; coordinate only; no identifier, label, type, admin, or statement lineage fields in observed JSONL rows.',
            'truthy_claims': 'Frozen truthy statement export scanned for exact source P764/P721 values; candidate QIDs then retain P31/P131/P17/P625 values with file, line and retrieved_at_utc. Truthy claims omit statement IDs/rank/qualifiers/references and do not prove source independence.',
            'provider_oktmo': 'Raw `oktmo_dadata` field from the frozen Tochno/DaData row is preserved. No per-query receipt or raw DaData response is present to independently establish provider response lineage or whether this field denotes target vs administrative code. Exact equality is joint source-code/geocoder-record consistency evidence, not an independent external source. Terminal `.0` is removed only from provider serialization; no padding, truncation, or prefix substitution.',
            'okato': 'TSV same-row OKATO and selected R2 OKATO are a concordance diagnostic only; independence is unestablished.',
            'points': 'TSV and module coordinates deduplicated by exact numeric pair for summary; raw line locators are retained for TSV rows/module rows.',
        },
        'metrics': summary,
        'outputs': {'wide_point_bindings.parquet': {'rows': int(len(bindings)), 'schema_columns': list(bindings.columns)},
                    **({'provider_code_candidate_screen.parquet': {'rows': int(len(provider_codes)), 'schema_columns': list(provider_codes.columns)}} if not provider_codes.empty else {})},
    }
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--selected', type=Path, default=SELECTED)
    parser.add_argument('--tsv', type=Path, default=TSV)
    parser.add_argument('--module', type=Path, default=MODULE)
    parser.add_argument('--ledger', type=Path, default=COORDINATE_LEDGER)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.selected, args.tsv, args.module, args.ledger, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
