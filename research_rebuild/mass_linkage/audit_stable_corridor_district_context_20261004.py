#!/usr/bin/env python3
"""Audit district-context holds in the frozen stable-corridor candidate set.

This is a bounded diagnostic only. It does not create or admit identity edges.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_long_table import ACCEPTED_COORDINATE_STATUSES

FREEZE = Path('/workspace/settlements-work/continuation_20261004/R4/stable_type_corridor_mass/review_freeze_v2')
OUT = Path('/workspace/settlements-work/continuation_20261004/R4/district_context_semantic_audit')
SELECTED = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
EVIDENCE = Path('/workspace/settlements-delivery/continuation-consolidated-20261003/source_evidence.parquet')
ACCEPTED_POINTS = Path('/workspace/settlements-work/continuation_20261004/accepted_mass_extensions/accepted_point_uses.parquet')
SEED = 20261004


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def s(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ''
    return str(value).strip()


def district_key(value: str) -> tuple[str, str]:
    """Only fold exact suffix/administrative forms; do not stem adjectives."""
    raw = s(value).casefold().replace('ё', 'е')
    raw = re.sub(r'[\u00a0\s]+', ' ', raw).strip(' .,:;')
    raw = re.sub(r'\s+', ' ', raw)
    suffixes = (
        'муниципальным районом', 'муниципального района', 'муниципальному району',
        'муниципальный район', 'муниципальном районе',
        'муниципальным округом', 'муниципального округа', 'муниципальному округу',
        'муниципальный округ', 'муниципальном округе',
        'городским округом', 'городского округа', 'городскому округу',
        'городской округ', 'городском округе',
        'районом', 'района', 'району', 'район', 'районе',
        'округом', 'округа', 'округу', 'округ', 'округе',
    )
    for suffix in suffixes:
        if raw == suffix:
            return '', suffix
        if raw.endswith(' ' + suffix):
            return raw[:-(len(suffix) + 1)].strip(), suffix
    return raw, ''


def adjective_case_key(value: str) -> str:
    """Conservative diagnostic only: expose likely Russian adjective inflections."""
    parts = value.split()
    if not parts:
        return ''
    word = parts[-1]
    endings = (
        ('ского', 'ск'), ('скому', 'ск'), ('ским', 'ск'), ('ском', 'ск'), ('ский', 'ск'),
        ('ская', 'ск'), ('ской', 'ск'), ('скую', 'ск'), ('ское', 'ск'),
        ('цкого', 'цк'), ('цкому', 'цк'), ('цким', 'цк'), ('цком', 'цк'), ('цкий', 'цк'),
        ('цкая', 'цк'), ('цкой', 'цк'), ('цкую', 'цк'),
    )
    for ending, canonical in endings:
        if word.endswith(ending):
            parts[-1] = word[:-len(ending)] + canonical
            break
    return ' '.join(parts)


def context_class(a: str, b: str) -> tuple[str, str, str, str, str]:
    ka, sa = district_key(a)
    kb, sb = district_key(b)
    if not s(a) or not s(b):
        return 'unknown_blank_or_unasserted', ka, kb, sa, sb
    if ka and ka == kb:
        if sa == sb:
            return 'same_normalized_district_label', ka, kb, sa, sb
        return 'exact_name_suffix_or_case_alias', ka, kb, sa, sb
    if ka and kb and ka != kb and adjective_case_key(ka) == adjective_case_key(kb):
        return 'possible_adjective_case_or_spelling_alias_unresolved', ka, kb, sa, sb
    return 'different_named_district_context', ka, kb, sa, sb


def as_bool(v) -> bool:
    return str(v).strip().casefold() in {'true', '1', 'yes'}


def name_key(value: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^а-яa-z0-9]+', ' ', s(value).casefold().replace('ё', 'е'))).strip()


def coordinate_range(value, lower: float, upper: float) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and lower <= number <= upper
    except (TypeError, ValueError):
        return False


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit(f'output directory is not empty: {OUT}')
    OUT.mkdir(parents=True, exist_ok=True)
    freeze = json.loads((FREEZE / 'freeze_manifest.json').read_text(encoding='utf-8'))
    frozen_summary = json.loads((FREEZE / 'summary.json').read_text(encoding='utf-8'))
    for name, expected in freeze['files'].items():
        actual = sha256(FREEZE / name)
        if actual != expected:
            raise SystemExit(f'frozen file hash mismatch: {name}: {actual} != {expected}')
    input_hashes = {str(SELECTED): sha256(SELECTED), str(EVIDENCE): sha256(EVIDENCE), str(ACCEPTED_POINTS): sha256(ACCEPTED_POINTS)}
    expected_selected = frozen_summary['sources']['sha256'][str(SELECTED)]
    expected_evidence = frozen_summary['sources']['sha256'][str(EVIDENCE)]
    if input_hashes[str(SELECTED)] != expected_selected or input_hashes[str(EVIDENCE)] != expected_evidence:
        raise SystemExit('selected/source_evidence input pin mismatch')
    if input_hashes[str(ACCEPTED_POINTS)] != frozen_summary['sources']['sha256'][str(ACCEPTED_POINTS)]:
        raise SystemExit('accepted point ledger input pin mismatch')
    for pin_path in [
        '/workspace/settlements-raw/data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql',
        '/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf',
    ]:
        actual = sha256(Path(pin_path))
        expected = frozen_summary['sources']['sha256'][pin_path]
        if actual != expected:
            raise SystemExit(f'historical evidence source hash mismatch: {pin_path}: {actual} != {expected}')
        input_hashes[pin_path] = actual

    disp_path = FREEZE / 'all_candidate_dispositions.csv'
    with disp_path.open(encoding='utf-8', newline='') as f:
        all_dispositions = list(csv.DictReader(f))
    candidates = [r for r in all_dispositions if 'explicit_source_district_context_differs' in json.loads(r['hold_reasons_json'])]
    if len(candidates) != 8174:
        raise SystemExit(f'expected 8174 district-held rows, got {len(candidates)}')

    needed = {'source_record_id', 'census_year', 'source_file', 'source_sheet', 'source_row', 'source_name_raw',
              'settlement_type', 'region_raw', 'district_raw', 'population', 'latitude', 'longitude', 'source_sha256',
              'source_locator', 'source_raw_line', 'population_scope', 'is_additive_settlement_record',
              'entity_grain_status', 'population_value_quality'}
    selected = pd.read_parquet(SELECTED, columns=sorted(needed))
    selected['source_record_id'] = selected['source_record_id'].astype(str)
    if selected['source_record_id'].duplicated().any():
        raise SystemExit('selected observations source_record_id is not unique')
    smap = {r['source_record_id']: r for r in selected.to_dict('records')}
    evidence = pd.read_parquet(EVIDENCE, columns=['source_record_id', 'source_evidence_json'])
    evidence['source_record_id'] = evidence['source_record_id'].astype(str)
    emap = dict(zip(evidence.source_record_id, evidence.source_evidence_json))
    pts = pd.read_parquet(ACCEPTED_POINTS, columns=['target_source_record_id', 'target_year', 'coordinate_admission_status',
        'coordinate_source_record_id', 'point_origin_kind', 'latitude', 'longitude'])
    pts = pts[(pts.target_year == 2021) & pts.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
    point_map = {r['target_source_record_id']: r for r in pts.to_dict('records')}

    classified: list[dict] = []
    source_field_mismatches = []
    for x in candidates:
        a, b = x['district_from_raw'], x['district_to_raw']
        cls, ka, kb, sa, sb = context_class(a, b)
        reasons = json.loads(x['hold_reasons_json'])
        f_id, t_id = x['from_source_record_id'], x['to_source_record_id']
        sf, st = smap.get(f_id), smap.get(t_id)
        f_match = sf is not None and s(sf.get('district_raw')) == s(a)
        t_match = st is not None and s(st.get('district_raw')) == s(b)
        if not f_match or not t_match:
            source_field_mismatches.append({'edge_id': x['edge_id'], 'from_id': f_id, 'to_id': t_id,
                'disposition_from_district': a, 'selected_from_district': s(sf.get('district_raw')) if sf else None,
                'disposition_to_district': b, 'selected_to_district': s(st.get('district_raw')) if st else None,
                'from_lookup_ok': sf is not None, 'to_lookup_ok': st is not None})
        # Exact suffix variants can clear the false text-comparison hold only when
        # the independent historic and direct-point witnesses are present and no
        # other hold remains. This is a scoped context resolution, never admission.
        historic_witness = (
            x.get('historical_geokladr_row_1based', '') != ''
            and x.get('historical_geokladr_raw_latitude', '') != ''
            and x.get('historical_geokladr_raw_longitude', '') != ''
            and x.get('historical_name_type_region_match_count', '') == '1'
            and s(x.get('classifier_to_geokladr_code_bridge', '')) in {'exact_11_digit', 'literal_8_digit_plus_000'}
            and name_key(x.get('historical_classifier_name_parsed', '')) == name_key(x.get('name_exact_norm', ''))
            and name_key(x.get('historical_named_object_name_parsed_2009', '')) == name_key(x.get('name_exact_norm', ''))
            and name_key(x.get('historical_classifier_type_raw', '')) == name_key(x.get('type_from_raw', '')) == name_key(x.get('type_to_raw', ''))
            and name_key(x.get('historical_geokladr_region_raw', '')) == name_key(x.get('region_from_raw', ''))
            and coordinate_range(x.get('historical_geokladr_raw_latitude'), -90, 90)
            and coordinate_range(x.get('historical_geokladr_raw_longitude'), -180, 180)
        )
        try:
            distance = float(x['max_direct_point_distance_km'])
        except (TypeError, ValueError):
            distance = math.inf
        point_id = x.get('point_witness_2021_source_record_id', '')
        point = point_map.get(point_id)
        direct_point = bool(point) and point.get('coordinate_source_record_id') == point_id and point.get('point_origin_kind') == 'tochno_2021_dadata_raw_parquet_point'
        spatial_witness = bool(point_id) and direct_point and distance <= 5.0
        exact_scope = as_bool(x.get('whole_region_exact_name_unique_across_types_from')) and as_bool(x.get('whole_region_exact_name_unique_across_types_to'))
        other_holds = [r for r in reasons if r != 'explicit_source_district_context_differs']
        context_resolved = (
            cls in {'same_normalized_district_label', 'exact_name_suffix_or_case_alias'}
            and f_match and t_match and historic_witness and spatial_witness and exact_scope and not other_holds
        )
        row = dict(x)
        row.update({
            'district_context_audit_class': cls,
            'district_from_key_exact_suffix_rule': ka,
            'district_to_key_exact_suffix_rule': kb,
            'district_from_suffix_form': sa,
            'district_to_suffix_form': sb,
            'from_district_matches_selected_source_row': f_match,
            'to_district_matches_selected_source_row': t_match,
            'historical_sql_geokladr_point_witness_present': historic_witness,
            'direct_2021_point_within_5km_present': spatial_witness,
            'point_witness_is_accepted_direct_2021_source_coordinate': direct_point,
            'whole_region_exact_name_type_unique_both_endpoints': exact_scope,
            'other_hold_reasons_json': json.dumps(other_holds, ensure_ascii=False),
            'scoped_context_hold_resolved_candidate_only': context_resolved,
            'identity_admitted': False,
            'resolution_justification': (
                'Both original district strings reduce to the same exact locality name under suffix/case-form aliases; selected rows match source fields; exact unique name/type/region and source-verified historical SQL+GeoKLADR point plus direct 2021 witness within 5 km corroborate the same context. This removes only the literal district-text hold for independent review.'
                if context_resolved else ''
            ),
        })
        classified.append(row)

    # Fixed stratified sample: top 20 by greater endpoint population, plus 60
    # seeded random distinct candidate rows from the remainder.
    sorted_by_mass = sorted(candidates, key=lambda x: max(float(x.get('from_population') or 0), float(x.get('to_population') or 0)), reverse=True)
    sample_ids = {x['edge_id']: 'high_mass_top20' for x in sorted_by_mass[:20]}
    rest = [x for x in candidates if x['edge_id'] not in sample_ids]
    rng = random.Random(SEED)
    for x in rng.sample(rest, 60):
        sample_ids[x['edge_id']] = 'seeded_random60'

    # Cache each raw input workbook/parquet and hash once. Keep full raw row values,
    # plus bounded adjacent worksheet cells for inspection; never infer hierarchy.
    raw_frame_cache: dict[tuple[str, str], pd.DataFrame] = {}
    excel_sheet_names: dict[str, list[str]] = {}
    pdf_text_cache: dict[str, list[str]] = {}
    raw_file_hashes: dict[str, dict] = {}
    raw_root = Path('/workspace/settlements-raw')
    sample_review: list[dict] = []
    for x in candidates:
        if x['edge_id'] not in sample_ids:
            continue
        for side, recid, rec_file, rec_sheet, rec_row, disp_district in [
            ('from', x['from_source_record_id'], x['from_source_file'], '', x['from_source_locator'], x['district_from_raw']),
            ('to', x['to_source_record_id'], x['to_source_file'], '', x['to_source_locator'], x['district_to_raw']),
            ('point_witness', x['point_witness_2021_source_record_id'], '', '', '', ''),
        ]:
            if not recid:
                continue
            sr = smap.get(recid)
            if sr is None:
                sample_review.append({'edge_id': x['edge_id'], 'sample_stratum': sample_ids[x['edge_id']], 'side': side,
                    'source_record_id': recid, 'raw_review_status': 'selected_source_id_missing'})
                continue
            source_file = s(sr.get('source_file'))
            file_path = raw_root / source_file
            year = int(sr['census_year'])
            selected_district = s(sr.get('district_raw'))
            row_idx = int(float(sr['source_row']))
            result = {
                'edge_id': x['edge_id'], 'sample_stratum': sample_ids[x['edge_id']], 'side': side,
                'source_record_id': recid, 'year': year, 'source_file': source_file,
                'source_sheet': s(sr.get('source_sheet')), 'source_row_1based_or_record_index': row_idx,
                'source_sha256_selected': s(sr.get('source_sha256')) or None,
                'source_locator_selected': s(sr.get('source_locator')) or None,
                'selected_district_raw': selected_district or None,
                'disposition_district_raw': disp_district or None,
                'selected_and_disposition_district_exact_match': selected_district == s(disp_district) if side != 'point_witness' else None,
                'selected_name_raw': s(sr.get('source_name_raw')),
                'selected_type': s(sr.get('settlement_type')),
                'selected_region_raw': s(sr.get('region_raw')),
                'selected_population': s(sr.get('population')),
                'source_evidence_json': s(emap.get(recid)),
            }
            if not file_path.exists():
                result.update({'raw_review_status': 'raw_source_file_missing', 'raw_cells_json': '[]'})
                sample_review.append(result)
                continue
            path_key = str(file_path)
            if path_key not in raw_file_hashes:
                raw_file_hashes[path_key] = {'path': path_key, 'sha256': sha256(file_path), 'bytes': file_path.stat().st_size}
            result['actual_source_file_sha256'] = raw_file_hashes[path_key]['sha256']
            if source_file.lower().endswith('.parquet'):
                key = (path_key, 'parquet')
                if key not in raw_frame_cache:
                    raw_frame_cache[key] = pd.read_parquet(file_path)
                df = raw_frame_cache[key]
                # Source row is the zero-based parquet row index encoded in source ID.
                idx = row_idx - 1
                if idx < 0 or idx >= len(df):
                    result.update({'raw_review_status': 'raw_record_index_out_of_range', 'raw_cells_json': '[]'})
                else:
                    raw = df.iloc[idx].to_dict()
                    raw_district_fields = {k: raw.get(k) for k in ['region', 'mun_upper', 'mun_lower', 'settlement', 'object_name', 'object_level'] if k in raw}
                    raw_district_serial = json.dumps({k: s(v) if pd.notna(v) else None for k, v in raw_district_fields.items()}, ensure_ascii=False)
                    # The 2021 district is derived from source hierarchy columns; keep those raw columns in full.
                    result.update({'raw_review_status': 'raw_row_loaded', 'raw_column_names_json': json.dumps(list(df.columns), ensure_ascii=False),
                                   'raw_district_context_columns_json': raw_district_serial,
                                   'raw_cells_json': json.dumps({k: (None if pd.isna(v) else s(v)) for k, v in raw.items()}, ensure_ascii=False)})
            elif source_file.lower().endswith('.pdf'):
                if path_key not in pdf_text_cache:
                    proc = subprocess.run(['pdftotext', '-layout', str(file_path), '-'], check=True,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    pdf_text_cache[path_key] = proc.stdout.split('\f')
                locator = {}
                try:
                    locator = json.loads(s(sr.get('source_locator')) or '{}')
                except json.JSONDecodeError:
                    pass
                page_num = int(locator.get('pdf_page_1based') or row_idx)
                line_num = int(locator.get('text_line_start_1based') or row_idx)
                pages = pdf_text_cache[path_key]
                page_text = pages[page_num - 1] if 1 <= page_num <= len(pages) else ''
                lines = page_text.splitlines()
                line_text = lines[line_num - 1] if 1 <= line_num <= len(lines) else ''
                result.update({'raw_review_status': 'raw_pdf_page_and_line_loaded' if page_text else 'raw_pdf_locator_page_missing',
                               'raw_pdf_page_1based': page_num, 'raw_pdf_line_1based': line_num,
                               'raw_pdf_locator_json': json.dumps(locator, ensure_ascii=False),
                               'raw_pdf_exact_line_text': line_text,
                               'raw_pdf_page_all_lines_json': json.dumps(lines, ensure_ascii=False),
                               'raw_cells_json': json.dumps({'page': page_num, 'line': line_num, 'text': line_text}, ensure_ascii=False)})
            else:
                sheet_label = s(sr.get('source_sheet'))
                if path_key not in excel_sheet_names:
                    excel_sheet_names[path_key] = pd.ExcelFile(file_path, engine='xlrd').sheet_names
                sheet_selector = sheet_label if sheet_label in excel_sheet_names[path_key] else (int(sheet_label) if sheet_label.isdigit() else sheet_label)
                key = (path_key, str(sheet_selector))
                if key not in raw_frame_cache:
                    raw_frame_cache[key] = pd.read_excel(file_path, sheet_name=sheet_selector, header=None, dtype=object, engine='xlrd')
                df = raw_frame_cache[key]
                idx = row_idx - 1
                if idx < 0 or idx >= len(df):
                    result.update({'raw_review_status': 'raw_record_index_out_of_range', 'raw_cells_json': '[]'})
                else:
                    row_cells = df.iloc[idx].tolist()
                    preceding = []
                    for ri in range(max(0, idx - 8), idx):
                        vals = [None if pd.isna(v) else s(v) for v in df.iloc[ri].tolist()]
                        preceding.append({'row_1based': ri + 1, 'cells': vals})
                    clean_cells = [None if pd.isna(v) else s(v) for v in row_cells]
                    explicit_cell_indexes = [i for i, v in enumerate(clean_cells) if v == selected_district and v]
                    near_heading_matches = []
                    if selected_district:
                        for near in preceding:
                            for i, v in enumerate(near['cells']):
                                if v == selected_district:
                                    near_heading_matches.append({'row_1based': near['row_1based'], 'column_0based': i, 'value': v})
                    result.update({'raw_review_status': 'raw_row_loaded', 'raw_row_all_cells_json': json.dumps(clean_cells, ensure_ascii=False),
                                   'raw_cells_json': json.dumps(clean_cells, ensure_ascii=False),
                                   'raw_previous_8_rows_all_cells_json': json.dumps(preceding, ensure_ascii=False),
                                   'raw_district_exact_cell_columns_0based_json': json.dumps(explicit_cell_indexes),
                                   'raw_district_text_in_previous_8_rows_json': json.dumps(near_heading_matches, ensure_ascii=False),
                                   'raw_source_row_district_present_as_cell': bool(explicit_cell_indexes) if selected_district else False})
            sample_review.append(result)

    # Summaries avoid double-counting multi-edge source records: preserve separate
    # edge-level metrics and unique source endpoint totals.
    class_counts = Counter(r['district_context_audit_class'] for r in classified)
    class_by_year = defaultdict(lambda: {'candidate_edges': 0, 'from_population_sum_diagnostic': 0, 'to_population_sum_diagnostic': 0,
                                         'unique_from_ids': set(), 'unique_to_ids': set()})
    for r in classified:
        k = f"{r['from_year']}-{r['to_year']}|{r['district_context_audit_class']}"
        d = class_by_year[k]
        d['candidate_edges'] += 1
        d['from_population_sum_diagnostic'] += int(float(r.get('from_population') or 0))
        d['to_population_sum_diagnostic'] += int(float(r.get('to_population') or 0))
        d['unique_from_ids'].add(r['from_source_record_id'])
        d['unique_to_ids'].add(r['to_source_record_id'])
    summarized = []
    for k, v in sorted(class_by_year.items()):
        summarized.append({'year_pair_and_class': k, 'candidate_edges': v['candidate_edges'],
                           'from_population_sum_diagnostic': v['from_population_sum_diagnostic'],
                           'to_population_sum_diagnostic': v['to_population_sum_diagnostic'],
                           'unique_from_records': len(v['unique_from_ids']), 'unique_to_records': len(v['unique_to_ids'])})

    resolved = [r for r in classified if r['scoped_context_hold_resolved_candidate_only']]
    write_csv(OUT / 'district_context_all_8174_classified.csv', classified)
    write_csv(OUT / 'scoped_context_resolved_candidate_row_ids.csv', resolved)
    write_csv(OUT / 'fixed_80_raw_source_district_review.csv', sample_review)
    write_csv(OUT / 'source_field_disposition_mismatches.csv', source_field_mismatches)
    write_csv(OUT / 'raw_source_hashes.csv', list(raw_file_hashes.values()))
    summary = {
        'status': 'district_context_semantic_audit_candidate_only_no_admissions',
        'input_candidate_rows_with_explicit_source_district_context_differs': len(candidates),
        'candidate_rows_by_context_class': dict(class_counts),
        'year_pair_context_metrics': summarized,
        'fixed_sample': {'n_edges': 80, 'high_mass_top20': 20, 'seeded_random60': 60, 'seed': SEED,
                         'raw_endpoint_records': len(sample_review),
                         'raw_rows_loaded': sum(r.get('raw_review_status') == 'raw_row_loaded' for r in sample_review),
                         'raw_files_sha256_checked': len(raw_file_hashes)},
        'source_field_disposition_mismatches': len(source_field_mismatches),
        'scoped_exact_alias_context_resolved_candidate_rows': len(resolved),
        'candidate_identity_admissions': 0,
        'resolved_rows_rule': 'Exact safe suffix/case-form locality name equality only, with direct selected source-field match, whole-region exact name/type uniqueness at both endpoints, unique raw SQL+GeoKLADR historical named point and an independently accepted 2021 point witness within 5 km; all other hold reasons must be absent. This is a context-hold resolution candidate only; root independent review required.',
        'interpretation': {
            'unknown_blank_or_unasserted': 'At least one original source district field is blank; this is not a positive contradiction. Raw blank remains preserved and is not filled.',
            'different_named_district_context': 'Both fields are nonblank and exact safe suffix folding still leaves different names. These remain blocked absent specific historical administrative/spatial mapping evidence.',
            'exact_name_suffix_or_case_alias': 'Both fields reduce to the same locality name under the enumerated suffix/case forms. Resolution still requires independent source, name/type/region, and spatial witness criteria.',
            'no_admissions': 'All rows are candidate-only; no graph or point ledger was edited.'},
        'inputs': input_hashes | {str(FREEZE / 'all_candidate_dispositions.csv'): sha256(disp_path),
                                  str(FREEZE / 'freeze_manifest.json'): sha256(FREEZE / 'freeze_manifest.json'),
                                  str(FREEZE / 'summary.json'): sha256(FREEZE / 'summary.json')},
        'raw_source_hashes_count': len(raw_file_hashes),
        'outputs': {},
    }
    for p in sorted(OUT.iterdir()):
        summary['outputs'][p.name] = {'sha256': sha256(p), 'bytes': p.stat().st_size}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest = {'status': summary['status'], 'seed': SEED, 'inputs': summary['inputs'], 'outputs': {},
                'script': str(Path(__file__).resolve()), 'script_sha256': sha256(Path(__file__).resolve())}
    for p in sorted(OUT.iterdir()):
        if p.name != 'receipt.json':
            manifest['outputs'][p.name] = sha256(p)
    (OUT / 'receipt.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
