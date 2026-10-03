"""Apply the independently reviewed, bounded coordinate-extension rules to staging.

This writes candidate proposals and a whole-row gate ledger.  It never updates the
accepted coordinate release; every newly emitted row remains staged for review.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

REVIEW = Path('/workspace/settlements-work/coordinates/extension_review_v1/review.json')
REVIEW_NOTES = Path('/workspace/settlements-work/coordinates/extension_review_v1/notes.md')
CANDIDATES = Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/historical_named_point_candidates.parquet')
CANDIDATE_RECEIPT = Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/receipt.json')
GEO_PARSED = Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet')
CLASSIFIER = Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet')
ACCEPTED = Path('/workspace/settlements-work/coordinates/accepted_modern_v1/accepted_point_uses.parquet')
GRAPH = Path('/workspace/settlements-work/identity/accepted_ordinary_v4/accepted_identity_edges.parquet')
SELECTED = Path('/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet')
PROPAGATION = Path('/workspace/settlements-work/coordinates/admission_staging_v1/coordinate_propagation.parquet')
EVENTS = Path('/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json')
MOSCOW_XLS = Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls')
WIKIDATA_GZ = Path('/workspace/settlements-raw/data/raw/wikidata_truthy_claims/batch_0139.jsonl.gz')
DEFAULT_OUT = Path('/workspace/settlements-work/coordinates/extension_application_v1')
MOSCOW_ID = 'ROSSTAT2002:T1:T4:sheet01-04:excel_row02155'
MOSCOW_POINT = (55.750556, 37.617500)
CITY_WIDTH_NAMES = {'Барнаул', 'Краснодар', 'Красноярск', 'Владивосток', 'Ставрополь', 'Хабаровск'}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def isnull(v: Any) -> bool:
    try:
        return v is None or bool(pd.isna(v))
    except (TypeError, ValueError):
        return v is None


def s(v: Any) -> str:
    return '' if isnull(v) else str(v).strip()


def truth(v: Any) -> bool:
    return False if isnull(v) else bool(v)


def number(v: Any) -> float | None:
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def valid_point(lat: Any, lon: Any) -> bool:
    a, b = number(lat), number(lon)
    return a is not None and b is not None and -90 <= a <= 90 and -180 <= b <= 180


def event_codes(event: dict[str, Any]) -> set[str]:
    out = set()
    for k, v in event.items():
        if 'settlement_id' not in k or not v:
            continue
        val = str(v)
        m = re.fullmatch(r'RU-OKTMO-(\d+)', val)
        if m:
            out.add(m.group(1))
    return out


def row_codes(row: Any) -> set[str]:
    # Preserve raw strings as keys: event binding does not pad, truncate, or infer
    # identity from names.  Only the explicit RU-OKTMO identifier representation
    # is compared with an exact selected OKTMO value.
    values = [getattr(row, c, None) for c in ('oktmo', 'oktmo_2011_raw', 'oktmo_raw_text')]
    return {str(v).strip() for v in values if not isnull(v) and str(v).strip()}


def events_for(row: Any, events: list[dict[str, Any]], start_year: int, end_year: int) -> list[str]:
    codes = row_codes(row)
    if not codes:
        return []
    hits = []
    for e in events:
        ecodes = event_codes(e)
        if not (codes & ecodes):
            continue
        # The legacy source date is an assertion; year matching is a temporal
        # relevance screen, not independent verification of the event itself.
        dates = [s(e.get(k)) for k in ('source_asserted_effective_date', 'valid_from', 'valid_to')]
        years = []
        for d in dates:
            m = re.search(r'(?:19|20)\d{2}', d)
            if m: years.append(int(m.group()))
        if not years or any(start_year <= y <= end_year for y in years):
            hits.append(s(e.get('event_id')) or 'event_without_id')
    return sorted(set(hits))


def source_is_physical(row: Any, require_unique_name_type: bool = True) -> tuple[bool, list[str]]:
    reasons = []
    nm, typ = s(getattr(row, 'settlement_name', None)), s(getattr(row, 'settlement_type', None)).lower()
    if not truth(getattr(row, 'is_additive_settlement_record', None)):
        reasons.append('selected_source_not_explicitly_additive_settlement_row')
    if not nm or not typ:
        reasons.append('selected_source_name_or_type_missing')
    if require_unique_name_type and int(number(getattr(row, 'source_region_name_type_count', 0)) or 0) != 1:
        reasons.append('selected_source_region_name_type_not_unique')
    grain = s(getattr(row, 'entity_grain_status', None)).lower()
    if any(w in grain for w in ('aggregate', 'federal_city', 'parent', 'derived_sum')):
        reasons.append('selected_source_grain_explicit_aggregate_or_parent')
    coverage = s(getattr(row, 'coverage_status', None)).lower()
    if any(w in coverage for w in ('aggregate', 'federal_city', 'parent_total', 'municipal_total')):
        reasons.append('selected_source_coverage_explicit_aggregate_or_parent')
    if typ and not any(x in typ for x in ('город', 'село', 'дерев', 'пос', 'пгт', 'станиц', 'станция', 'разъезд', 'хутор', 'аул', 'аал', 'улус', 'населённый пункт', 'населенный пункт', 'починок', 'местечко', 'кордон', 'слобод', 'рабоч', 'курорт', 'заимк', 'кишлак')):
        reasons.append('selected_source_type_not_recognized_physical_locality')
    if s(getattr(row, 'region_norm', None)).lower() == 'москва' and s(getattr(row, 'settlement_name', None)).lower() == 'москва' and s(getattr(row, 'census_year', '')) == '2010':
        reasons.append('2010_moscow_source_grain_legacy_aggregate_hold')
    if (s(getattr(row, 'region_norm', None)).lower(), nm.lower()) in {('санкт-петербург','санкт-петербург'),('севастополь','севастополь')} and s(getattr(row, 'census_year', '')) == '2010':
        reasons.append('2010_federal_city_source_grain_requires_explicit_review')
    return not reasons, reasons


def _mapping(df: pd.DataFrame, key: str) -> dict[str, dict[str, Any]]:
    return {str(getattr(r, key)): r._asdict() for r in df.itertuples(index=False) if not isnull(getattr(r, key))}


def resolve_source_file(source_file: str) -> Path | None:
    """Resolve known raw and relocated release assets without broad searching."""
    if not source_file:
        return None
    p = Path(source_file)
    candidates = [p] if p.is_absolute() else [Path('/workspace/settlements-raw') / p]
    if source_file.startswith('research_rebuild/evidence/'):
        candidates.append(Path('/workspace/settlements-data') / source_file)
        candidates.append(Path('/workspace/russian-settlements-research') / source_file)
    if source_file == 'evidence/ingestion/source/karelia_2010_rural_settlements.docx':
        candidates.append(Path('/workspace/settlements-karelia-inputs/build') / source_file)
    if source_file.endswith('arkhangelsk_2010_archived_original.html'):
        candidates.append(Path('/workspace/settlements-work/sources/r2-missing/arkhangelsk_2010_archived_original.html'))
    return next((x for x in candidates if x.is_file()), None)


def verify_path(path_ids: Any, target: str, modern: str, edge_by_id: dict[str, Any]) -> tuple[bool, str]:
    try:
        ids = json.loads(s(path_ids))
    except Exception:
        return False, 'identity_path_decision_ids_invalid_json'
    if not ids:
        return False, 'identity_path_empty'
    current = target
    for decision in ids:
        edge = edge_by_id.get(str(decision))
        accepted_statuses = {'checked_rule_accepted', 'checked_rule_accepted_redundant_graph_connectivity_effect',
                             'accepted_rule_family_after_independent_sample_review', 'case_specific_independent_review_accepted',
                             'case_review_accepted', 'independent_case_review_accepted', 'accepted_case_specific'}
        if edge is None or s(edge.get('relation')) != 'same_place' or s(edge.get('decision_status')) not in accepted_statuses:
            return False, 'identity_path_has_missing_or_unaccepted_edge'
        a, b = s(edge.get('from_source_record_id')), s(edge.get('to_source_record_id'))
        if current == a: current = b
        elif current == b: current = a
        else: return False, 'identity_path_edges_do_not_chain_from_target'
    if current != modern:
        return False, 'identity_path_does_not_end_at_exact_modern_point_source'
    return True, ''


def base_use(target_id: str, year: int, lat: float, lon: float, source_id: str,
             source_name: str, source_type: str, source_region: str, source_file: str,
             source_row: Any, source_hash: str, locator: str, provenance: str,
             rule: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        'target_source_record_id': target_id, 'target_year': int(year),
        'latitude': float(lat), 'longitude': float(lon),
        'coordinate_quality': 'reviewed_candidate_rule_pending_independent_coordinate_application',
        'coordinate_source': provenance, 'coordinate_source_record_id': source_id,
        'coordinate_provider': provenance, 'coordinate_provider_id': '',
        'source_name': source_name, 'source_type': source_type, 'source_region': source_region,
        'source_file': source_file, 'source_row': source_row, 'source_sha256': source_hash,
        'source_locator': locator, 'coordinate_provenance': provenance,
        'admission_rule': rule, 'provider_binding_status': 'not_asserted_by_coordinate_application',
        'provider_fias_binding_status': 'not_asserted_by_coordinate_application',
        'coordinate_admission_status': 'staged_candidate_pending_root_review',
        'coordinate_measurement_date_unknown': True, 'boundary_comparability_asserted': False,
        'coordinate_provider_family': None, 'source_oktmo_raw': None, 'source_okato_raw': None,
        'provider_query_receipt_missing': None, 'coordinate_uncertainty_flags_json': json.dumps([], ensure_ascii=False),
        **metadata,
    }


def verify_moscow(expected_workbook_hash: str) -> tuple[bool, str]:
    if not MOSCOW_XLS.exists() or sha(MOSCOW_XLS) == '':
        return False, 'moscow_2002_raw_workbook_missing'
    if not WIKIDATA_GZ.exists():
        return False, 'moscow_wikidata_raw_claim_file_missing'
    source_hash = sha(MOSCOW_XLS)
    if expected_workbook_hash and source_hash != expected_workbook_hash:
        return False, 'moscow_2002_raw_workbook_hash_differs_from_selected_release'
    # Reopen the selected workbook row and compare its exact locality and count.
    try:
        frame = pd.read_excel(MOSCOW_XLS, sheet_name='01-04', header=None)
        vals = frame.iloc[2154].tolist()
        row_ok = (str(vals[0]).strip() == 'г. Москва' and int(vals[1]) == 10126424
                  and int(vals[2]) == 4831405 and int(vals[3]) == 5295019)
    except Exception:
        row_ok = False
    if not row_ok:
        return False, 'moscow_2002_raw_workbook_row_mismatch'
    found = False
    class_found = False
    with gzip.open(WIKIDATA_GZ, 'rt', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if i == 13780:
                found = 'Q649' in line and 'P625' in line and '55.750556' in line and '37.617500' in line
            if 'Q649' in line and 'P31' in line and 'Q7930989' in line:
                class_found = True
            if i > 13780 and found and class_found:
                break
    return (found and class_found), '' if found and class_found else 'moscow_wikidata_raw_claim_locator_point_or_class_mismatch'


def apply(out: Path = DEFAULT_OUT) -> dict[str, Any]:
    review = json.loads(REVIEW.read_text(encoding='utf-8'))
    candidate_receipt = json.loads(CANDIDATE_RECEIPT.read_text(encoding='utf-8'))
    candidates = pd.read_parquet(CANDIDATES)
    accepted = pd.read_parquet(ACCEPTED)
    graph = pd.read_parquet(GRAPH)
    selected = pd.read_parquet(SELECTED)
    propagation = pd.read_parquet(PROPAGATION)
    events = json.loads(EVENTS.read_text(encoding='utf-8'))
    if len(candidates) != 465800 or len(accepted) != 97301 or len(graph) != 128569:
        raise ValueError('frozen coordinate extension input row counts differ from reviewed artifacts')
    if sha(CANDIDATES) != review['inputs']['historical_named_candidates_v4']['sha256']:
        raise ValueError('historical named candidate packet hash differs from review')
    if candidate_receipt.get('outputs', {}).get('historical_named_point_candidates.parquet') != sha(CANDIDATES):
        raise ValueError('historical candidate receipt output hash mismatch')
    if candidate_receipt.get('inputs', {}).get('geo', {}).get('sha256') != sha(GEO_PARSED):
        raise ValueError('raw GeoKLADR parsed input hash differs from candidate receipt')
    if candidate_receipt.get('inputs', {}).get('classifier', {}).get('sha256') != sha(CLASSIFIER):
        raise ValueError('raw OKATO classifier input hash differs from candidate receipt')
    if sha(GRAPH) != review['inputs']['accepted_identity_graph']['sha256']:
        raise ValueError('accepted graph hash differs from review')
    accepted_by_target = set(accepted.target_source_record_id.astype(str))
    accepted_row_by_target = _mapping(accepted, 'target_source_record_id')
    cand_by_id = candidates.set_index(candidates.source_record_id.astype(str), drop=False)
    source_by_id = _mapping(selected, 'source_record_id')
    edge_by_id = {s(r.decision_id): r._asdict() for r in graph.itertuples(index=False)}

    # Point reuse collisions are computed at exact stored GeoKLADR coordinates,
    # within historical year, against the whole named candidate packet.
    geo = candidates[candidates.historical_named_point_candidate.fillna(False)].copy()
    geo['_lat'] = pd.to_numeric(geo.latitude_from_lat, errors='coerce')
    geo['_lon'] = pd.to_numeric(geo.longitude_from_long, errors='coerce')
    geo['_coord_key'] = geo['_lat'].astype(str) + '|' + geo['_lon'].astype(str)
    geo_counts = geo.groupby(['census_year', '_coord_key']).source_record_id.transform('size')
    dup_by_id = dict(zip(geo.source_record_id.astype(str), geo_counts.gt(1)))

    audit: list[dict[str, Any]] = []
    staged_by_target: dict[str, dict[str, Any]] = {}
    priority_by_target: dict[str, int] = {}
    audit_index_by_target: dict[str, int] = {}
    selected_file_hash_cache: dict[str, str] = {}

    def record(candidate_id: str, family: str, target: str, row: Any, point: tuple[Any, Any],
               evidence: dict[str, Any], holds: list[str], priority: int, point_source: str,
               provenance: str, rule: str) -> None:
        target_year = int(number(getattr(row, 'census_year', 0)) or 0)
        lat, lon = point
        present = target in accepted_by_target or target in staged_by_target
        if target in accepted_by_target:
            holds.append('already_accepted_target_precedence')
        elif target in staged_by_target:
            if priority <= priority_by_target[target]:
                holds.append('staged_duplicate_target_lower_precedence')
            else:
                prior_i = audit_index_by_target[target]
                prior = audit[prior_i]
                prior['application_status'] = 'held'
                prior['proposed_for_staging'] = False
                prior['held_reasons_json'] = json.dumps(['staged_duplicate_target_lower_precedence'], ensure_ascii=False)
                staged_by_target.pop(target, None)
        allowed = not holds
        selected_row = source_by_id.get(target, {})
        candidate_details = {k: getattr(row, k, None) for k in (
            'settlement_name','settlement_type','region_norm','population','population_scope',
            'is_additive_settlement_record','entity_grain_status','source_region_name_type_count',
            'name_norm','type_norm','name_key','type_key_2009','code_join_basis',
            'historical_okato_2009_raw','historical_okato_2011_raw','kod3_raw_text',
            'oktmo_raw_text','oktmo_2011_raw','latitude_from_lat','longitude_from_long',
            'lat_raw_text','long_raw_text','source_updated_at','source_sha256_2009','source_sha256_2011','source_line_1based',
            'record_number_1based','record_byte_offset_0based','historical_name_exact',
            'historical_type_exact','historical_code_structure_compatible',
            'historical_key_region_name_type_count','possible_unlocated_historical_competitor',
            'is_settlement_raw','historical_point_modern_region','source_object_is_naselenniy_punkt',
            'source_is_aggregate_scope','provider_fias_level','provider_general_fias_id',
            'provider_general_fias_duplicate_count','provider_latitude','provider_longitude',
            'modern_provider_to_historical_point_km','modern_provider_code_matches_historical_code',
            'modern_numeric_provider_code_agrees_historical_code')}
        selected_details = {k: selected_row.get(k) for k in (
            'source_record_id','source_file','source_sheet','source_row','source_sha256',
            'source_locator','settlement_name','settlement_type','region_raw','population',
            'population_scope','is_additive_settlement_record','entity_grain_status','oktmo','okato')}
        audit.append({'candidate_id': candidate_id, 'candidate_family': family, 'target_source_record_id': target,
                      'target_year': target_year, 'application_status': 'candidate_staged_pending_root_review' if allowed else 'held',
                      'admission_allowed': False, 'proposed_for_staging': allowed,
                      'held_reasons_json': json.dumps(sorted(set(holds)), ensure_ascii=False),
                      'evidence_checks_json': json.dumps(evidence, ensure_ascii=False, default=str),
                      'candidate_source_row_json': json.dumps(candidate_details, ensure_ascii=False, default=str),
                      'selected_source_row_json': json.dumps(selected_details, ensure_ascii=False, default=str),
                      'coordinate_source_record_id': point_source, 'proposed_latitude': number(lat), 'proposed_longitude': number(lon),
                      'source_sha256': s(selected_row.get('source_sha256')),
                      'source_locator': s(selected_row.get('source_locator')) or json.dumps({
                          'source_file': selected_row.get('source_file'), 'source_sheet': selected_row.get('source_sheet'),
                          'source_row': selected_row.get('source_row')}, ensure_ascii=False, default=str),
                      'review_id': review.get('review_id')})
        if allowed:
            info = source_by_id.get(target, {})
            source_file = s(info.get('source_file')) or s(getattr(row, 'source_file', None))
            source_row = info.get('source_row', getattr(row, 'source_row', None))
            source_hash = s(info.get('source_sha256'))
            if not source_hash and source_file:
                local_source_path = resolve_source_file(source_file)
                if local_source_path:
                    if str(local_source_path) not in selected_file_hash_cache:
                        selected_file_hash_cache[str(local_source_path)] = sha(local_source_path)
                    source_hash = selected_file_hash_cache[str(local_source_path)]
            locator = s(info.get('source_locator')) or json.dumps({'source_file': info.get('source_file'),
                'source_sheet': info.get('source_sheet'), 'source_row': info.get('source_row')}, ensure_ascii=False, default=str)
            coordinate_source = accepted_row_by_target.get(point_source, {})
            coordinate_hash = s(getattr(row, 'source_sha256_2011', None)) or s(coordinate_source.get('coordinate_source_sha256'))
            coordinate_locator = s(coordinate_source.get('source_locator')) or json.dumps({
                'source_line_1based': getattr(row, 'source_line_1based', None),
                'record_number_1based': getattr(row, 'record_number_1based', None),
                'record_byte_offset_0based': getattr(row, 'record_byte_offset_0based', None),
                'retrieval_locator': getattr(row, 'source_locator', None)}, ensure_ascii=False, default=str)
            if family.startswith('M_'):
                coordinate_hash = sha(WIKIDATA_GZ) if WIKIDATA_GZ.exists() else ''
                coordinate_locator = 'batch_0139.jsonl.gz#line_13780; retrieved 2026-08-31T21:00:02.290898Z'
            if family.startswith('R_') and coordinate_source:
                coordinate_locator = json.dumps({'coordinate_source_record_id': point_source,
                    'coordinate_source': coordinate_source.get('coordinate_source'),
                    'coordinate_provider': coordinate_source.get('coordinate_provider'),
                    'coordinate_provenance': coordinate_source.get('coordinate_provenance'),
                    'provider_id': coordinate_source.get('coordinate_provider_id'),
                    'provider_binding_status': coordinate_source.get('provider_binding_status'),
                    'provider_fias_binding_status': coordinate_source.get('provider_fias_binding_status'),
                    'source_locator_in_accepted_claim': coordinate_source.get('source_locator')}, ensure_ascii=False, default=str)
            meta = {'coordinate_application_family': family, 'review_id': review.get('review_id'),
                    'application_inference_kind': 'dated_historical_source_point_candidate' if family.startswith('F_') or family.startswith('A_') else 'retrospective_representative_point_inference',
                    'direct_historical_coordinate_measurement': False, 'population_scope_comparability_asserted': False,
                    'admission_allowed': False,
                    'application_gate_status': 'candidate_only_pending_root_review',
                    'coordinate_source_sha256': coordinate_hash, 'coordinate_source_locator': coordinate_locator,
                    'coordinate_source_file': '/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet' if family.startswith(('F_', 'A_')) else ('/workspace/settlements-raw/data/raw/wikidata_truthy_claims/batch_0139.jsonl.gz' if family.startswith('M_') else ''),
                    'coordinate_source_origin': s(coordinate_source.get('coordinate_source')) if family.startswith('R_') else provenance,
                    'coordinate_source_input_artifact_sha256': 'c778b841d22a65ac01a8658957044b66390bc32fe7f095cb2ca38489858ce17f' if family.startswith(('F_', 'A_')) else '',
                    'coordinate_source_date': '2011 source update' if family.startswith('F_') or family.startswith('A_') else 'modern point measurement date unknown',
                    'coordinate_source_latitude_raw': s(getattr(row, 'lat_raw_text', None)) or s(lat),
                    'coordinate_source_longitude_raw': s(getattr(row, 'long_raw_text', None)) or s(lon),
                    'inference_modern_point_use_target_source_record_id': point_source if family.startswith('R_') else '',
                    'inference_identity_path_decision_ids_json': s(getattr(row, 'identity_edge_path_decision_ids_json', None)) if family.startswith('R_') else '',
                    'inference_identity_path_from_source_record_id': s(getattr(row, 'source_record_id', None)) if family.startswith('R_') else '',
                    'inference_identity_path_to_source_record_id': s(getattr(row, 'source_coordinate_source_record_id', None)) if family.startswith('R_') else '',
                    'inference_identity_path_edge_count': number(getattr(row, 'identity_path_edge_count', None)) if family.startswith('R_') else None}
            use = base_use(target, target_year, lat, lon, point_source,
                s(info.get('settlement_name')) or s(getattr(row, 'settlement_name', None)),
                s(info.get('settlement_type')) or s(getattr(row, 'settlement_type', None)),
                s(info.get('region_raw')) or s(getattr(row, 'region_norm', None)), source_file, source_row,
                source_hash, locator, provenance, rule, meta)
            if family.startswith('R_') and coordinate_source:
                # The modern point claim's origin and binding evidence travels
                # with its coordinates.  Only the historical target and the
                # inference metadata are new.
                for field in ('coordinate_quality','coordinate_source','coordinate_provider',
                              'coordinate_provider_id','coordinate_provenance','provider_binding_status',
                              'provider_fias_binding_status','coordinate_provider_family',
                              'source_oktmo_raw','source_okato_raw','provider_query_receipt_missing',
                              'coordinate_uncertainty_flags_json'):
                    use[field] = coordinate_source.get(field)
                use['coordinate_source_record_id'] = coordinate_source.get('coordinate_source_record_id')
                use['coordinate_source_sha256'] = coordinate_hash
                use['coordinate_source_locator'] = coordinate_locator
            staged_by_target[target] = use
            priority_by_target[target] = priority
            audit_index_by_target[target] = len(audit) - 1

    # Reviewed 775 modern-city-to-historical-point candidate rows, including
    # the independently checked typed 8/11-digit KOD3=000 bridge cohort.
    city = candidates[candidates.modern_city_historical_code_point_candidate.fillna(False)]
    for r in city.itertuples(index=False):
        sid, nm = s(r.source_record_id), s(r.settlement_name)
        holds: list[str] = []
        width = s(r.code_join_basis) == 'typed_urban_8digit_plus_zero_third_geo_group'
        # The independent reviewer clarified that the literal KOD3=000 bridge
        # was checked across this complete 775-row cohort.  Six named examples
        # in the frozen review illustrate serialization loss; they are not the
        # population of the approved typed-width bridge.
        if width and (len(s(r.historical_okato_2009_raw)) != 8
                      or len(s(r.historical_okato_2011_raw)) != 11
                      or s(r.kod3_raw_text) != '000'):
            holds.append('city_code_width_bridge_raw_width_or_literal_kod3_mismatch')
        if not width and s(r.code_join_basis) != 'exact_raw_code': holds.append('city_code_join_basis_not_reviewed_exact_code')
        if not valid_point(r.latitude_from_lat, r.longitude_from_long): holds.append('historical_geokladr_point_invalid')
        if not truth(r.historical_point_modern_region): holds.append('historical_geokladr_point_not_in_expected_modern_region')
        if not truth(r.historical_name_exact) or not truth(r.historical_type_exact): holds.append('historical_name_or_type_not_exact')
        if s(r.name_norm) != s(r.name_key) or s(r.type_norm) != s(r.type_key_2009):
            holds.append('selected_source_and_historical_classifier_name_type_not_exact')
        if not truth(r.historical_code_structure_compatible): holds.append('historical_code_structure_incompatible')
        if int(number(r.historical_key_region_name_type_count) or 0) != 1: holds.append('historical_typed_key_not_unique')
        if truth(r.possible_unlocated_historical_competitor): holds.append('unlocated_historical_competitor')
        if not truth(r.source_object_is_naselenniy_punkt) or truth(r.source_is_aggregate_scope): holds.append('modern_source_not_physical_city_or_aggregate_flagged')
        if s(r.provider_fias_level) != '4': holds.append('provider_fias_level4_binding_not_unique')
        if not s(r.provider_general_fias_id): holds.append('provider_fias_id_missing')
        if int(number(r.provider_general_fias_duplicate_count) or 0) > 1: holds.append('provider_fias_id_not_unique')
        if number(r.modern_provider_to_historical_point_km) is None or number(r.modern_provider_to_historical_point_km) > 5:
            holds.append('provider_to_historical_point_distance_gate_failed')
        if not (truth(r.modern_provider_code_matches_historical_code) or truth(r.modern_numeric_provider_code_agrees_historical_code)):
            holds.append('provider_okato_exact_or_explicit_numeric_serialization_gate_failed')
        evidence = {'raw_code_join_basis': s(r.code_join_basis), 'reviewed_typed_width_bridge': width,
                    'raw_code_2009': s(r.historical_okato_2009_raw), 'raw_code_2011': s(r.historical_okato_2011_raw),
                    'raw_kod3': s(r.kod3_raw_text), 'reviewed_775_rule': True,
                    'provider_fias_level': s(r.provider_fias_level),
                    'provider_fias_duplicate_count': number(r.provider_general_fias_duplicate_count),
                    'provider_distance_km': number(r.modern_provider_to_historical_point_km),
                    'provider_name_exact_selected_name': truth(r.provider_name_exact_selected_name),
                    'provider_type_exact_selected_type': truth(r.provider_type_exact_selected_type),
                    'provider_raw_code_exact': truth(r.modern_provider_code_matches_historical_code),
                    'provider_explicit_numeric_serialization_code_match': truth(r.modern_numeric_provider_code_agrees_historical_code),
                    'point_interpretation': 'GeoKLADR 2011 update, not census-date point'}
        point_id = 'GeoKLADR2011:OKATO:' + s(r.historical_okato_2011_raw)
        record(sid, 'A_775_modern_city_exact_historical_named_point', sid, r,
               (r.latitude_from_lat, r.longitude_from_long), evidence, holds, 3, point_id,
               'GeoKLADR 2011 dated named physical-city point; exact checked code/name/type candidate',
               'extension_review_v1_modern_city_historical_named_point_rule')

    # Generic F candidates are conditionally staged only after source-grain,
    # exact code/name/type, collision, chronology, and point checks.
    for r in geo.itertuples(index=False):
        year = int(number(r.census_year) or 0)
        if year not in (2002, 2010): continue
        sid = s(r.source_record_id); source = source_by_id.get(sid)
        holds: list[str] = []
        source_ctx = {**(source or {}), 'source_region_name_type_count': getattr(r, 'source_region_name_type_count', None)}
        physical, reasons = source_is_physical(type('R', (), source_ctx)()) if source else (False, ['selected_source_row_missing'])
        holds.extend(reasons)
        if not truth(r.historical_name_exact) or not truth(r.historical_type_exact): holds.append('historical_name_or_type_not_exact')
        if s(r.name_norm) != s(r.name_key) or s(r.type_norm) != s(r.type_key_2009):
            holds.append('selected_source_and_historical_classifier_name_type_not_exact')
        if s(r.is_settlement_raw).lower() not in {'t', 'true', '1'}: holds.append('historical_classifier_not_explicit_settlement_object')
        if s(r.code_join_basis) != 'exact_raw_code': holds.append('historical_code_not_exact_raw_join')
        if int(number(r.historical_key_region_name_type_count) or 0) != 1: holds.append('historical_named_key_not_unique')
        if int(number(r.source_region_name_type_count) or 0) != 1: holds.append('selected_source_region_name_type_not_unique')
        if truth(r.possible_unlocated_historical_competitor): holds.append('unlocated_historical_competitor')
        src_file = s(source.get('source_file')) if source else ''
        raw_path = resolve_source_file(src_file)
        selected_hash = s(source.get('source_sha256')) if source else ''
        selected_locator = s(source.get('source_locator')) if source else ''
        actual_source_hash = ''
        if raw_path:
            if str(raw_path) not in selected_file_hash_cache:
                selected_file_hash_cache[str(raw_path)] = sha(raw_path)
            actual_source_hash = selected_file_hash_cache[str(raw_path)]
        # The current R2 release binds some intentionally relocated source assets
        # by exact path, content hash and row locator.  That pinned provenance is
        # sufficient for staging when the raw asset is not mounted locally.
        if not raw_path and not (selected_hash and selected_locator): holds.append('selected_source_file_unresolved_and_release_hash_locator_missing')
        if raw_path and selected_hash and actual_source_hash != selected_hash: holds.append('selected_source_file_hash_mismatch')
        if not s(r.source_sha256_2009) or not s(r.source_sha256_2011): holds.append('dated_historical_point_source_hash_missing')
        if isnull(r.source_line_1based) or isnull(r.record_number_1based): holds.append('dated_historical_source_locator_missing')
        if not valid_point(r.latitude_from_lat, r.longitude_from_long): holds.append('geokladr_point_invalid')
        if not truth(r.historical_point_modern_region): holds.append('geokladr_point_outside_expected_region')
        if dup_by_id.get(sid, False): holds.append('within_year_shared_geokladr_point_group')
        if not physical: pass
        # Event source assertions are matched only by exact selected OKTMO key.
        fake = type('R', (), {**(source or {}), 'oktmo_raw_text': getattr(r, 'oktmo_raw_text', None),
                              'oktmo_2011_raw': getattr(r, 'oktmo_2011_raw', None)})()
        event_hits = events_for(fake, events, year, 2011)
        if event_hits: holds.append('exact_code_keyed_lineage_or_coverage_event_requires_review')
        evidence = {'selected_source_found': bool(source), 'selected_source_id_exact': s(source.get('source_record_id')) == sid if source else False,
                    'source_sha256_present': bool(s(source.get('source_sha256')) if source else ''),
                    'source_locator_present': bool(s(source.get('source_locator')) if source else ''),
                    'selected_source_exact_file': src_file, 'selected_source_file_path': str(raw_path) if raw_path else None,
                    'selected_source_file_resolved_locally': bool(raw_path), 'selected_source_file_hash_matches': bool(raw_path and selected_hash and actual_source_hash == selected_hash),
                    'selected_source_actual_sha256_locally_computed': actual_source_hash,
                    'selected_source_actual_sha256_locally_computed': actual_source_hash,
                    'selected_source_release_hash_present': bool(selected_hash), 'selected_source_release_locator_present': bool(selected_locator),
                    'source_selected_sheet_row_locator': f"{s(source.get('source_sheet'))}:{s(source.get('source_row'))}" if source else '',
                    'raw_source_reopened_and_rehashed': False,
                    'point_source_sha256_present': bool(s(r.source_sha256_2011)),
                    'point_source_record_number': number(r.record_number_1based),
                    'point_source_byte_offset': number(r.record_byte_offset_0based),
                    'additional_provider_point_available': valid_point(r.provider_latitude, r.provider_longitude),
                    'additional_provider_point_conflict_status': 'not_available_in_frozen_v4_candidate_row' if not valid_point(r.provider_latitude, r.provider_longitude) else 'risk_comparison_required',
                    'historical_code_join_basis': s(r.code_join_basis), 'exact_event_ids': event_hits,
                    'duplicate_point_group': bool(dup_by_id.get(sid, False)),
                    'null_population_scope_is_not_veto_when_additive_physical_row': isnull(source.get('population_scope')) and physical if source else False}
        point_id = 'GeoKLADR2011:OKATO:' + s(r.historical_okato_2011_raw)
        record(sid, 'F_generic_2002_2010_geokladr2011_point', sid, r,
               (r.latitude_from_lat, r.longitude_from_long), evidence, holds, 1, point_id,
               'GeoKLADR 2011 source coordinate', 'extension_review_v1_conditional_generic_historical_geokladr_point')

    # Retrospective continuity: explicit exact endpoint graph path and source row
    # grain.  2010 Moscow/SPB aggregate audit findings are unconditional holds.
    for r in propagation.itertuples(index=False):
        target, modern = s(r.source_record_id), s(r.target_source_record_id)
        year = int(number(r.target_year) or 0)
        source = source_by_id.get(target)
        holds: list[str] = []
        path_ok, path_reason = verify_path(r.identity_edge_path_decision_ids_json, target,
                                           s(r.source_coordinate_source_record_id), edge_by_id)
        if not path_ok: holds.append(path_reason)
        if s(r.source_coordinate_source_record_id) not in accepted_by_target:
            holds.append('modern_point_source_not_in_accepted_point_uses')
        candidate_ctx = cand_by_id.loc[target] if target in cand_by_id.index else None
        source_ctx = {**(source or {}), 'source_region_name_type_count': getattr(candidate_ctx, 'source_region_name_type_count', None) if candidate_ctx is not None else None}
        physical, reasons = source_is_physical(type('R', (), source_ctx)(), require_unique_name_type=False) if source else (False, ['selected_source_row_missing'])
        holds.extend(reasons)
        if source:
            # Selected row's raw OKTMO is the event key; names alone are never used.
            candidate_event_codes = candidate_ctx.to_dict() if candidate_ctx is not None else {}
            fake = type('R', (), {**source_ctx, **candidate_event_codes,
                'oktmo': source.get('oktmo'), 'oktmo_raw_text': candidate_event_codes.get('oktmo_raw_text'),
                'oktmo_2011_raw': candidate_event_codes.get('oktmo_2011_raw')})()
            event_hits = events_for(fake, events, year, 2021)
        else: event_hits = []
        modern_point = accepted_row_by_target.get(s(r.source_coordinate_source_record_id), {})
        try:
            modern_flags = json.loads(s(modern_point.get('coordinate_uncertainty_flags_json')) or '[]')
        except Exception:
            modern_flags = ['unparseable_coordinate_uncertainty_flags']
        hard_point_flags = [f for f in modern_flags if any(tok in str(f).lower() for tok in ('conflict','duplicate','multipoint','point_choice'))]
        if hard_point_flags: holds.append('accepted_modern_point_has_unresolved_conflict_or_duplicate_flags')
        modern_event_row = type('R', (), {'oktmo': modern_point.get('source_oktmo_raw'),
            'oktmo_raw_text': modern_point.get('source_oktmo_raw'),
            'oktmo_2011_raw': None})()
        modern_event_hits = events_for(modern_event_row, events, year, 2021)
        if event_hits: holds.append('exact_code_keyed_lineage_or_coverage_event_requires_review')
        if modern_event_hits: holds.append('modern_point_source_exact_code_keyed_event_requires_review')
        if year == 2010 and (s(source.get('region_norm') if source else ''), s(source.get('settlement_name') if source else '').lower()) in {
                ('москва', 'москва'), ('санкт-петербург', 'санкт-петербург'), ('севастополь', 'севастополь')}:
            holds.append('2010_federal_city_legacy_aggregate_point_reuse_hold')
        if not valid_point(r.latitude, r.longitude): holds.append('modern_representative_point_invalid')
        evidence = {'selected_source_found': bool(source), 'selected_source_id_exact': bool(source and s(source.get('source_record_id')) == target),
                    'physical_source_row': physical, 'entity_grain_status': s(source.get('entity_grain_status')) if source else '',
                    'source_population_scope': s(source.get('population_scope')) if source else '',
                    'source_population_scope_null_is_not_veto': bool(source and isnull(source.get('population_scope')) and physical),
                    'accepted_path_exact_endpoints': path_ok, 'path_edge_count': int(number(r.identity_path_edge_count) or 0),
                    'identity_path_decision_ids_json': s(r.identity_edge_path_decision_ids_json),
                    'identity_path_from_source_record_id': target,
                    'identity_path_to_modern_source_record_id': s(r.source_coordinate_source_record_id),
                    'exact_code_keyed_event_ids': event_hits, 'modern_source_code_keyed_event_ids': modern_event_hits,
                    'accepted_modern_point_uncertainty_flags': modern_flags,
                    'accepted_modern_point_hard_conflict_flags': hard_point_flags,
                    'direct_historical_measurement': False,
                    'boundary_comparability_asserted': False, 'population_scope_comparability_asserted': False,
                    'source_provenance_reopened_and_rehashed': False}
        pseudo = {**(source or {}), 'source_record_id':target, 'census_year':year,
                  'identity_edge_path_decision_ids_json':r.identity_edge_path_decision_ids_json,
                  'identity_path_edge_count':r.identity_path_edge_count,
                  'source_coordinate_source_record_id':r.source_coordinate_source_record_id}
        record(s(target), 'R_modern_accepted_point_retrospective_continuity', target, type('R', (), pseudo)(),
               (r.latitude, r.longitude), evidence, holds, 2, s(r.source_coordinate_source_record_id),
               'accepted modern representative point; retrospective continuity inference',
               'extension_review_v1_exact_accepted_graph_path_continuity')

    # Standalone, reviewed Moscow 2002 physical-city point.  It has no graph edge
    # and is not generalized to the other federal cities or 2010.
    moscow = source_by_id.get(MOSCOW_ID)
    ok, moscow_reason = verify_moscow(s(moscow.get('source_sha256')) if moscow else '')
    holds = []
    if not moscow: holds.append('reviewed_2002_moscow_source_row_missing')
    else:
        if int(number(moscow.get('population')) or 0) != 10126424: holds.append('reviewed_2002_moscow_population_mismatch')
        if s(moscow.get('population_scope')) != 'physical_settlement_city_only': holds.append('reviewed_2002_moscow_population_scope_mismatch')
    if not ok: holds.append(moscow_reason)
    if MOSCOW_ID in accepted_by_target: holds.append('already_accepted_target_precedence')
    pseudo = type('R', (), {**(moscow or {'census_year':2002}), 'source_record_id':MOSCOW_ID, 'census_year':2002})()
    record(MOSCOW_ID, 'M_2002_moscow_standalone_physical_city_point', MOSCOW_ID, pseudo,
           MOSCOW_POINT, {'review_exact_source_row': MOSCOW_ID, 'population': 10126424,
                          'wikidata_entity': 'Q649', 'raw_claim_file_exists': WIKIDATA_GZ.exists(),
                          'raw_claim_locator_verified': ok, 'raw_p31_physical_class_verified': ok,
                          'workbook_exists': MOSCOW_XLS.exists(),
                          'workbook_hash': sha(MOSCOW_XLS) if MOSCOW_XLS.exists() else None,
                          'raw_workbook_row_reparsed': ok, 'no_identity_edge_used': True,
                          'boundary_comparability_asserted': False}, holds, 4, 'WIKIDATA:Q649:P625:batch_0139:line13780',
           'Wikidata Q649 physical-city point; standalone spatial continuity inference',
           'extension_review_v1_moscow_2002_standalone_physical_city_point')

    # Precedence across families: frozen baseline, then modern point graph
    # continuity, then conditional GeoKLADR source points. A_775 is its own
    # modern-target family and is behind baseline but ahead of generic F rows.
    ledger = pd.DataFrame(audit)
    proposals = pd.DataFrame(list(staged_by_target.values()))
    metadata_cols = ['coordinate_application_family','review_id','application_inference_kind',
        'direct_historical_coordinate_measurement','population_scope_comparability_asserted','admission_allowed','application_gate_status',
        'coordinate_source_sha256','coordinate_source_locator','coordinate_source_file',
        'coordinate_source_origin','coordinate_source_input_artifact_sha256','coordinate_source_date',
        'coordinate_source_latitude_raw','coordinate_source_longitude_raw',
        'inference_modern_point_use_target_source_record_id','inference_identity_path_decision_ids_json',
        'inference_identity_path_from_source_record_id','inference_identity_path_to_source_record_id',
        'inference_identity_path_edge_count']
    for c in metadata_cols:
        if c not in accepted.columns: accepted[c] = pd.NA
    for c in accepted.columns:
        if c not in proposals.columns: proposals[c] = pd.NA
    proposals = proposals[accepted.columns]
    combined = pd.concat([accepted, proposals], ignore_index=True)
    if combined.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('staged output has duplicate target IDs after precedence resolution')
    out.mkdir(parents=True, exist_ok=True)
    ledger.to_parquet(out / 'coordinate_extension_application_checks.parquet', index=False)
    ledger[~ledger.proposed_for_staging].to_parquet(out / 'held_coordinate_extensions.parquet', index=False)
    combined.to_parquet(out / 'staged_proposed_point_uses.parquet', index=False)
    generic_ledger = ledger[ledger.candidate_family.eq('F_generic_2002_2010_geokladr2011_point')]
    generic_evidence = [json.loads(x) for x in generic_ledger.evidence_checks_json]
    source_provenance_summary = {
        'generic_historical_application_rows': len(generic_ledger),
        'selected_source_files_locally_hashed': sum(bool(x.get('selected_source_actual_sha256_locally_computed')) for x in generic_evidence),
        'selected_source_files_locally_hashed': sum(bool(x.get('selected_source_actual_sha256_locally_computed')) for x in generic_evidence),
        'selected_source_files_resolved_and_hash_checked': sum(bool(x.get('selected_source_file_hash_matches')) for x in generic_evidence),
        'selected_source_rows_pinned_by_release_hash_and_locator_without_local_raw_file': sum(
            bool(x.get('selected_source_release_hash_present') and x.get('selected_source_release_locator_present')
                 and not x.get('selected_source_file_resolved_locally')) for x in generic_evidence),
        'selected_source_rows_without_file_or_hash_locator': sum(
            not x.get('selected_source_file_resolved_locally')
            and not (x.get('selected_source_release_hash_present') and x.get('selected_source_release_locator_present')) for x in generic_evidence),
        'point_rows_with_raw_source_hash_and_record_locator': sum(
            bool(x.get('point_source_sha256_present') and x.get('point_source_record_number') is not None
                 and x.get('point_source_byte_offset') is not None) for x in generic_evidence)}
    report = {'status':'candidate_application_staged_pending_independent_root_review',
              'review_id':review['review_id'], 'application_script_sha256':sha(Path(__file__)),
              'inputs':{p.name:{'path':str(p),'sha256':sha(p),'bytes':p.stat().st_size} for p in [REVIEW, REVIEW_NOTES, CANDIDATES, CANDIDATE_RECEIPT, GEO_PARSED, CLASSIFIER, ACCEPTED, GRAPH, SELECTED, PROPAGATION, EVENTS]},
              'provenance_checks':{'selected_observation_release':'current R2 regional selected observations, pinned by the full release parquet sha256',
                'source_provenance_summary':source_provenance_summary,
                'selected_source_raw_rows_reparsed':False,
                'selected_source_assets_locally_rehashed_where_resolved':True,
                'moscow_2002_workbook_row_reparsed_and_hash_compared_with_selected_release':True,
                'geokladr_raw_record_reopened_per_candidate':False,
                'historical_geokladr_2011_source_hashes_present':int(candidates.source_sha256_2011.notna().sum()),
                'selected_sources_with_hash':int(selected.source_sha256.notna().sum()),'selected_sources_with_locator':int(selected.source_locator.notna().sum()),
                'lineage_events_are_candidates_not_accepted_events':True,
                'lineage_event_source_hash':sha(EVENTS)},
              'counts':{'input_accepted_rows':len(accepted),'input_candidates':len(candidates),'propagation_rows':len(propagation),
                'application_checks':len(ledger),'held_checks':int((~ledger.proposed_for_staging).sum()),
                'staged_new_targets':len(proposals),'output_rows':len(combined),
                'by_family':ledger.groupby('candidate_family').application_status.value_counts().unstack(fill_value=0).to_dict('index'),
                'staged_by_family':proposals.coordinate_application_family.value_counts().to_dict()},
              'outputs':{p.name:{'sha256':sha(p),'rows':len(pd.read_parquet(p))} for p in [out/'coordinate_extension_application_checks.parquet',out/'held_coordinate_extensions.parquet',out/'staged_proposed_point_uses.parquet']},
              'limits':['All new coordinates remain staged candidate uses; admission_allowed is false.',
                'A historical GeoKLADR 2011 point is not a census-date measurement.',
                'No coordinate averaging, boundary equivalence, population-scope equivalence, or new provider-ID binding is asserted.',
                'Source assets are presence/hash/locator audited as reported; raw source workbook/GeoKLADR records were not all reopened and independently rehashed here.',
                'Lineage candidate records are matched by exact OKTMO identifiers and chronology; a matched candidate is held for review, not treated as accepted event evidence.']}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    print(json.dumps(apply(args.output), ensure_ascii=False, indent=2, default=str))

if __name__ == '__main__':
    main()
