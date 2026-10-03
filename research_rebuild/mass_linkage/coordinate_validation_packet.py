"""Build an immutable no-admission review packet for modern coordinate candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import resource
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .coordinate_rules import haversine_km, valid_wgs84, in_broad_russia_envelope

LEDGER = Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet')
WIDE_DIR = Path('/workspace/settlements-work/wikidata/wide_v5')
WIDE = WIDE_DIR / 'wide_point_bindings.parquet'
PROVIDER_CODES = WIDE_DIR / 'provider_code_candidate_screen.parquet'
BASELINE_DB = Path('/workspace/settlements-assets/baseline/legacy_database_20260929.duckdb')
P31_METADATA = Path('/workspace/settlements-work/coordinates/validation_packet/p31_type_metadata.json')
P31_HIERARCHY = Path('/workspace/settlements-work/coordinates/validation_packet/wikidata_type_hierarchy_v1/ancestry_metadata.json')
V4_OUTPUT = Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_04')
REGION_SCREEN = Path('/workspace/settlements-work/coordinates/region_screen_v1/region_point_screen.parquet')
REGION_RECEIPT = Path('/workspace/settlements-work/coordinates/region_screen_v1/receipt.json')
RUS_REGION_GEOMETRY = Path('/workspace/settlements-work/sources/region_geometry/RUS_ADM1_simplified.geojson')
UKR_REGION_GEOMETRY = Path('/workspace/settlements-work/sources/region_geometry/UKR_ADM1.geojson')
OUTPUT = Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_04')
SEED = 20261002
KNOWN_PHYSICAL_P31 = {'Q486972': 'human settlement', 'Q532': 'village', 'Q515': 'city'}
KNOWN_ADMIN_P31 = {'Q56061': 'administrative territorial entity', 'Q15642541': 'municipality'}
RUSSIA_QID = 'Q159'
UKRAINE_QID = 'Q212'
PHYSICAL_TYPE_ANCHORS = {'Q486972', 'Q515', 'Q532', 'Q10354598', 'Q7930989'}
ADMIN_ONLY_TYPE_ANCHORS = {'Q56061', 'Q15642541'}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def norm_code(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if re.fullmatch(r'\d+\.0+', text):
        text = text.split('.', 1)[0]
    return text if re.fullmatch(r'\d+', text) else None


def text_key(value: Any) -> str:
    if value is None or pd.isna(value):
        return ''
    text = unicodedata.normalize('NFKC', str(value)).casefold().replace('ё', 'е')
    return ' '.join(re.sub(r'[^\w]+', ' ', text).split())


def parse_json(value: Any) -> Any:
    if value is None or pd.isna(value) or not str(value).strip():
        return []
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def bool_value(value: Any) -> bool:
    return bool(value) if value is not None and not pd.isna(value) else False


def gt_one(value: Any) -> bool:
    try:
        return float(value) > 1
    except (TypeError, ValueError):
        return False


def metadata_entities(metadata: dict[str, Any]) -> dict[str, Any]:
    entities = dict(metadata.get('entities', {}))
    for batch in metadata.get('batches', []):
        entities.update((batch.get('data') or {}).get('entities', {}))
    return entities


def population_band(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 'unknown'
    if n <= 0:
        return '0'
    if n < 100:
        return '1-99'
    if n < 1_000:
        return '100-999'
    if n < 10_000:
        return '1k-9,999'
    return '10k+'


def p31_profile(claims: Any, country_claims: Any) -> dict[str, Any]:
    p31_rows = parse_json(claims)
    p17_rows = parse_json(country_claims)
    p31 = sorted({str(row.get('value_qid')) for row in p31_rows if row.get('value_qid')})
    p17 = sorted({str(row.get('value_qid')) for row in p17_rows if row.get('value_qid')})
    return {
        'p31_qids': p31,
        'p31_known_physical_qids': [qid for qid in p31 if qid in KNOWN_PHYSICAL_P31],
        'p31_known_admin_qids': [qid for qid in p31 if qid in KNOWN_ADMIN_P31],
        'p31_unknown_semantics_qids': [qid for qid in p31 if qid not in KNOWN_PHYSICAL_P31 and qid not in KNOWN_ADMIN_P31],
        'p17_qids': p17,
        'p17_has_russia': RUSSIA_QID in p17,
        'p17_has_ukraine': UKRAINE_QID in p17,
        'p17_country_claim_present': bool(p17),
        'p17_geopolitical_claim_is_not_coordinate_block': True,
    }


def strata_sample(frame: pd.DataFrame, n: int = 100, seed: int = SEED) -> pd.DataFrame:
    """Deterministic round-robin sample across region, settlement, size, code and risk."""
    if frame.empty or n <= 0:
        return frame.head(0).copy()
    work = frame.copy()
    work['_urban_rural'] = np.where(work.settlement_type.astype('string').str.casefold().isin(['город', 'пгт']), 'urban', 'rural_or_other')
    work['_population_band'] = work.population.map(population_band)
    work['_region_stratum'] = work.region_raw.map(text_key).replace('', 'unknown')
    work['_code_width_stratum'] = work.source_oktmo_digit_width.fillna(0).astype(int).astype(str)
    work['_risk_stratum'] = np.where(work.review_risk_flags_json.map(lambda s: bool(parse_json(s))), 'risk_flagged', 'screen_clear')
    keys = ['_urban_rural', '_population_band', '_code_width_stratum', '_risk_stratum', '_region_stratum']
    groups = []
    for key, group in work.groupby(keys, dropna=False, sort=True):
        g = group.copy()
        g['_stable_order'] = g.source_record_id.map(lambda sid: hashlib.sha256(f'{seed}|{sid}'.encode()).hexdigest())
        groups.append((key, g.sort_values('_stable_order')))
    rng = random.Random(seed)
    rng.shuffle(groups)
    selected_indices = []
    depth = 0
    while len(selected_indices) < min(n, len(work)):
        any_at_depth = False
        for _, group in groups:
            if depth < len(group):
                selected_indices.append(group.index[depth])
                any_at_depth = True
                if len(selected_indices) >= min(n, len(work)):
                    break
        if not any_at_depth:
            break
        depth += 1
    out = work.loc[selected_indices].copy()
    out['sample_seed'] = seed
    out['sample_stratum'] = out[keys].astype(str).agg('|'.join, axis=1)
    return out.drop(columns=['_urban_rural', '_population_band', '_region_stratum', '_code_width_stratum', '_risk_stratum', '_stable_order'], errors='ignore')


def _load_historical(db_path: Path) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, Any]]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        geo = conn.execute('SELECT historical_okato, name_raw, settlement_type_raw, kladr, oktmo_2011_raw, population_source_value, source_status, source_updated_at, latitude, longitude, coordinate_valid_russia_bbox, historical_okato_unique, source_page, source_archive_url, source_snapshot_date FROM historical_geokladr_coordinates_2011').df()
        classifier = conn.execute('SELECT historical_okato, name_raw, name, status, name_full, is_settlement_raw, historical_region_raw, historical_okato_unique, snapshot_revision, snapshot_url, classifier_occurrence, classifier_group_size FROM historical_okato_142_2009').df()
    finally:
        conn.close()
    region_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in classifier.to_dict('records'):
        code = norm_code(row.get('historical_okato'))
        if code:
            region_by_code[code].append({k: row.get(k) for k in ['historical_region_raw', 'name', 'name_full', 'status', 'is_settlement_raw', 'snapshot_revision', 'classifier_occurrence', 'classifier_group_size', 'historical_okato_unique']})
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in geo.to_dict('records'):
        row['okato_2009_context'] = region_by_code.get(norm_code(row.get('historical_okato')) or '', [])
        for key, raw in [('historical_okato', row.get('historical_okato')), ('oktmo_2011', row.get('oktmo_2011_raw')), ('kladr', row.get('kladr'))]:
            code = norm_code(raw)
            if code:
                index[(key, code)].append(row)
    return dict(index), {
        'historical_geokladr_2011_rows': int(len(geo)),
        'historical_okato_142_2009_rows': int(len(classifier)),
        'geo_schema': list(geo.columns), 'classifier_schema': list(classifier.columns),
    }


def _aggregate_wikidata(wide: pd.DataFrame, source_context: pd.DataFrame, metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    context_by_source = source_context.set_index('source_record_id')[['settlement_name', 'settlement_type', 'region_raw', 'district_raw', 'municipality_raw']].to_dict('index')
    w = wide.copy()
    w['wikidata_truthy_exact_p764_match'] = w.wikidata_truthy_exact_p764_match.fillna(False).astype(bool)
    w['wikidata_label_exact_source_name'] = w.wikidata_name_exact_label.fillna(False).astype(bool)
    w['wikidata_p17_claim_present'] = w.wikidata_truthy_p17_claims_json.fillna('[]').ne('[]')
    w['wikidata_p17_has_russia'] = w.wikidata_truthy_p17_claims_json.fillna('[]').str.contains(r'Q159(?!\d)',regex=True)
    w['wikidata_p17_has_ukraine'] = w.wikidata_truthy_p17_claims_json.fillna('[]').str.contains(r'Q212(?!\d)',regex=True)
    w['wikidata_p31_claim_present'] = w.wikidata_truthy_p31_claims_json.fillna('[]').ne('[]')
    w['wikidata_known_physical_p31'] = w.wikidata_truthy_p31_claims_json.fillna('[]').str.contains(r'"value_qid":\s*"(?:Q486972|Q532|Q515)"', regex=True)
    w['wikidata_known_admin_p31'] = w.wikidata_truthy_p31_claims_json.fillna('[]').str.contains(r'"value_qid":\s*"(?:Q56061|Q15642541)"', regex=True)
    w['wikidata_has_point_within_0_5km'] = pd.to_numeric(w.nearest_wide_point_to_dadata_km, errors='coerce').le(.5)
    context = context_by_source
    admin_exact = []
    for row in w[['source_record_id','wikidata_tsv_ru_admin_labels_json']].itertuples(index=False):
        ctx = context.get(str(row.source_record_id), {})
        expected = {text_key(ctx.get(k)) for k in ['region_raw','district_raw','municipality_raw'] if text_key(ctx.get(k))}
        labels = parse_json(row.wikidata_tsv_ru_admin_labels_json)
        admin_exact.append(any(text_key(label) in expected for label in labels if text_key(label)))
    w['wikidata_admin_context_exact'] = admin_exact
    grouped = w.groupby('source_record_id',sort=False).agg(
        wikidata_qids=('wikidata_qid',lambda s:json.dumps(sorted(set(map(str,s))))),
        wikidata_qid_count=('wikidata_qid','nunique'),
        wikidata_truthy_exact_p764_match=('wikidata_truthy_exact_p764_match','max'),
        wikidata_label_exact_source_name=('wikidata_label_exact_source_name','max'),
        wikidata_admin_context_exact=('wikidata_admin_context_exact','max'),
        wikidata_p31_claim_present=('wikidata_p31_claim_present','max'),
        wikidata_p17_claim_present=('wikidata_p17_claim_present','max'),
        wikidata_p17_has_russia=('wikidata_p17_has_russia','max'),
        wikidata_p17_has_ukraine=('wikidata_p17_has_ukraine','max'),
        wikidata_p31_physical_known=('wikidata_known_physical_p31','max'),
        wikidata_p31_admin_known=('wikidata_known_admin_p31','max'),
        wikidata_any_p625_within_0_5km=('wikidata_has_point_within_0_5km','max'),
        wikidata_nearest_p625_to_dadata_km=('nearest_wide_point_to_dadata_km','min'),
        wikidata_points_count=('distinct_tsv_or_module_points_count','max'),
    ).reset_index()
    grouped['wikidata_point_provider_family_id']='wikimedia_wikidata_one_evidence_family'
    return grouped.set_index('source_record_id').to_dict('index')


def _historical_matches(row: dict[str, Any], history: dict[tuple[str, str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    keys = [
        ('source_oktmo_to_historical_2011_oktmo', 'oktmo_2011', row.get('raw_oktmo')),
        ('selected_okato_projection_to_historical_okato', 'historical_okato', row.get('okato')),
        ('dadata_okato_to_historical_okato', 'historical_okato', row.get('raw_okato_dadata')),
        ('dadata_oktmo_to_historical_2011_oktmo', 'oktmo_2011', row.get('raw_oktmo_dadata')),
    ]
    results = []
    seen = set()
    for route, key, raw in keys:
        code = norm_code(raw)
        if not code:
            continue
        for hist in history.get((key, code), []):
            token = (route, hist.get('historical_okato'), hist.get('kladr'), hist.get('oktmo_2011_raw'), hist.get('name_raw'))
            if token in seen:
                continue
            seen.add(token)
            region_labels = [x.get('historical_region_raw') for x in hist.get('okato_2009_context', []) if x.get('historical_region_raw')]
            name_match = text_key(row.get('settlement_name')) != '' and text_key(row.get('settlement_name')) == text_key(hist.get('name_raw'))
            region_match = text_key(row.get('region_raw')) != '' and text_key(row.get('region_raw')) in {text_key(x) for x in region_labels}
            results.append({
                **hist, 'match_route': route, 'matched_code_raw': raw, 'matched_code_exact_digits': code,
                'geokladr_label_exact_source_name': name_match,
                'geokladr_region_exact_source_region': region_match,
                'geokladr_type_raw_preserved_only': hist.get('settlement_type_raw'),
                'geokladr_coordinate_role': 'historical_2011-era point; coordinate correctness and continuity require separate review',
                'historical_classifier_link': 'exact historical OKATO join to 142/2009 classifier rows; region/type candidate context only',
            })
    return results


def _region_context_wiki(sample: dict[str, Any]) -> dict[str, Any]:
    profile = p31_profile(sample.get('wikidata_truthy_p31_claims_json'), sample.get('wikidata_truthy_p17_claims_json'))
    labels = parse_json(sample.get('wikidata_tsv_ru_labels_json'))
    admins = parse_json(sample.get('wikidata_tsv_ru_admin_labels_json'))
    expected = {text_key(sample.get(k)) for k in ['region_raw', 'district_raw', 'municipality_raw'] if text_key(sample.get(k))}
    admin_matches = sorted({str(a) for a in admins if text_key(a) in expected})
    label_match = any(text_key(sample.get('settlement_name')) and text_key(x) == text_key(sample.get('settlement_name')) for x in labels)
    return {**profile, 'wikidata_label_exact_source_name': label_match,
            'wikidata_admin_labels_exact_region_context_json': json.dumps(admin_matches, ensure_ascii=False),
            'wikidata_admin_context_exact': bool(admin_matches)}


def _p31_frequency(wide: pd.DataFrame, source: pd.DataFrame, type_metadata: dict[str, Any]) -> pd.DataFrame:
    api_entities = metadata_entities(type_metadata)
    records: dict[str, dict[str, Any]] = {}
    for row in wide.to_dict('records'):
        source_id = str(row['source_record_id'])
        pop = row.get('source_population')
        qid = str(row.get('wikidata_qid'))
        for claim in parse_json(row.get('wikidata_truthy_p31_claims_json')):
            p31q = claim.get('value_qid')
            if not p31q:
                continue
            key = str(p31q)
            entry = records.setdefault(key, {'p31_qid': key, 'source_ids': set(), 'candidate_qids': set(), 'population_by_source': {}, 'claim_facts': [], 'retrieved_dates': set(), 'source_files': set(), 'line_numbers': set()})
            entry['source_ids'].add(source_id); entry['candidate_qids'].add(qid)
            entry['population_by_source'][source_id] = pop
            fact = {k: claim.get(k) for k in ['value_raw', 'source_file', 'line_number', 'retrieved_at_utc']}
            if fact not in entry['claim_facts']:
                entry['claim_facts'].append(fact)
            if claim.get('retrieved_at_utc'): entry['retrieved_dates'].add(claim['retrieved_at_utc'])
            if claim.get('source_file'): entry['source_files'].add(claim['source_file'])
            if claim.get('line_number') is not None: entry['line_numbers'].add(int(claim['line_number']))
    out=[]
    for qid, e in sorted(records.items(), key=lambda kv: (-len(kv[1]['source_ids']), kv[0])):
        entity=api_entities.get(qid,{}) if isinstance(api_entities,dict) else {}
        label_ru=((entity.get('labels') or {}).get('ru') or {}).get('value')
        label_en=((entity.get('labels') or {}).get('en') or {}).get('value')
        desc_ru=((entity.get('descriptions') or {}).get('ru') or {}).get('value')
        desc_en=((entity.get('descriptions') or {}).get('en') or {}).get('value')
        pop=sum(float(v) for v in e['population_by_source'].values() if v is not None and not pd.isna(v))
        out.append({'p31_qid':qid,'wikidata_label_ru':label_ru,'wikidata_label_en':label_en,'wikidata_description_ru':desc_ru,'wikidata_description_en':desc_en,
                    'api_type_metadata_available':bool(label_ru or label_en or desc_ru or desc_en),
                    'explicit_known_physical_type':qid in KNOWN_PHYSICAL_P31,'explicit_known_admin_type':qid in KNOWN_ADMIN_P31,
                    'candidate_qid_count':len(e['candidate_qids']),'source_record_count_unique':len(e['source_ids']),'population_sum_unique_source_per_p31':int(pop),
                    'raw_claim_facts_json':json.dumps(sorted(e['claim_facts'],key=lambda x:(x.get('source_file') or '',x.get('line_number') or -1)),ensure_ascii=False),
                    'retrieved_at_utc_values_json':json.dumps(sorted(e['retrieved_dates'])),'source_file_values_json':json.dumps(sorted(e['source_files'])),
                    'sample_line_numbers_json':json.dumps(sorted(e['line_numbers'])[:20]),
                    'claim_lineage_note':'truthy P31 row has item/property/value/retrieval/file/line; no statement ID/rank/qualifier/reference in this export'})
    return pd.DataFrame(out)


WIDE_SAMPLE_COLUMNS = [
    'wikidata_qid','source_oktmo_raw','source_oktmo_exact_digits','wikidata_truthy_exact_p764_claims_json',
    'wikidata_truthy_exact_p721_projection_match_same_qid','wikidata_truthy_exact_p721_claims_json',
    'wikidata_tsv_matching_rows','wikidata_tsv_line_numbers_json','wikidata_tsv_ru_labels_json',
    'wikidata_name_exact_label','wikidata_tsv_admin_qids_json','wikidata_tsv_ru_admin_labels_json',
    'wikidata_truthy_p31_claims_json','wikidata_truthy_p131_claims_json','wikidata_truthy_p17_claims_json',
    'wikidata_truthy_p625_claims_json','points_json','wikidata_p625_nearest_distance_km',
    'nearest_wide_point_to_dadata_km','farthest_wide_point_to_dadata_km',
    'wikimedia_point_sources_same_qid_overlap','any_wikidata_truthy_point_overlaps_tsv_or_module',
    'entity_competition_across_tsv_or_truthy','source_observation_competition_for_exact_oktmo',
]


def attach_wide_evidence(frame: pd.DataFrame, wide: pd.DataFrame) -> pd.DataFrame:
    """Keep detailed raw QID facts on sampled/targeted rows; full gates live in compact coverage file."""
    if frame.empty:
        frame['wikidata_sample_evidence_json'] = pd.Series(dtype='string')
        return frame
    wanted=set(frame.source_record_id.astype(str))
    subset=wide.loc[wide.source_record_id.astype(str).isin(wanted),[c for c in ['source_record_id',*WIDE_SAMPLE_COLUMNS] if c in wide.columns]]
    evidence=[]
    for sid,group in subset.groupby('source_record_id',sort=False):
        evidence.append({'source_record_id':str(sid),'wikidata_sample_evidence_json':json.dumps(group.drop(columns=['source_record_id']).to_dict('records'),ensure_ascii=False,sort_keys=True)})
    return frame.merge(pd.DataFrame(evidence),on='source_record_id',how='left',validate='many_to_one')


def coverage_columns(frame: pd.DataFrame) -> list[str]:
    wanted=[
        'source_record_id','source_file','source_row','source_native_id','source_name_raw','settlement_name','settlement_type','population','region_raw','district_raw','municipality_raw','population_scope',
        'raw_object_level','raw_object_name','raw_oktmo','oktmo','okato','raw_okato_dadata','raw_oktmo_dadata',
        'source_oktmo_code_normalized','provider_oktmo_code_normalized_dot_zero_only','source_oktmo_digit_width','provider_oktmo_digit_width','source_provider_oktmo_exact_match',
        'raw_fias_id_dadata','raw_fias_level_dadata','raw_settlement_fias_id_dadata','raw_settlement_dadata','raw_settlement_type_full_dadata',
        'provider_point_latitude','provider_point_longitude','provider_latitude','provider_longitude','qc_geo_dadata_raw','provider_query_receipt_missing','provider_measurement_date_unknown',
        'provider_general_fias_duplicate_count','provider_coordinate_duplicate_count','baseline_provider_coordinate_conflict','baseline_coordinate_corroborated_provider','baseline_coordinate_certified','baseline_baseline_other_claim_families_json','baseline_baseline_other_families_within_0_5km_json',
        'source_is_physical_np','provider_primary_fias_level_4_or_6','provider_point_valid_wgs84','provider_point_inside_coarse_russia','provider_id_unique','provider_point_unique','no_baseline_hard_coordinate_conflict','provider_own_name_payload_present','provider_own_type_payload_present','provider_name_exact_selected_name','provider_type_exact_selected_type','provider_own_name_and_type_exact','provider_code_candidate_core','strict_named_type_provider_code_candidate','city_level4_missing_name_type_exception_candidate','unresolved_code_match_candidate','candidate_status',
        'wikidata_qids','wikidata_qid_count','wikidata_truthy_exact_p764_match','wikidata_label_exact_source_name','wikidata_admin_context_exact','wikidata_p31_claim_present','wikidata_p31_physical_known','wikidata_p31_admin_known','wikidata_p17_claim_present','wikidata_p17_has_russia','wikidata_p17_has_ukraine','wikidata_any_p625_within_0_5km','wikidata_nearest_p625_to_dadata_km','wikidata_points_count','wikidata_point_provider_family_id',
        'geokladr_exact_code_candidate_count','geokladr_any_exact_code_label_match','geokladr_any_exact_code_source_region_match','geokladr_point_provider_family_id','geokladr_reuse_is_historical_continuity_inference','geokladr_no_polygon_or_censusdate_required',
    'candidate_rule_family_a_rural_exact_code_and_own_name_type','candidate_rule_family_a_urban_city_level4_wikimedia_context','candidate_rule_family_b_strict_name_code_and_independent_context',
        'review_risk_flags_json','candidate_hold_flags_json','candidate_review_gate_clear','candidate_status_no_acceptance','identity_admission','coordinate_admission',
    ]
    return [c for c in wanted if c in frame.columns]


def _json_hash(path: Path) -> str:
    return sha256(path) if path.is_file() else ''


def wikidata_type_lineage(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Classify only class QIDs whose P279 ancestry reaches a declared settlement anchor."""
    entities = metadata.get('entities', {})
    graph: dict[str, set[str]] = {}
    for qid, entity in entities.items():
        parents=set()
        for claim in (entity.get('claims') or {}).get('P279', []):
            value=claim.get('mainsnak',{}).get('datavalue',{}).get('value',{})
            if isinstance(value,dict) and value.get('id'):
                parents.add(str(value['id']))
        graph[str(qid)]=parents
    result={}
    for qid in graph:
        seen=set(); stack=[qid]; physical_path=set(); admin_path=set()
        while stack:
            current=stack.pop()
            if current in seen: continue
            seen.add(current)
            if current in PHYSICAL_TYPE_ANCHORS: physical_path.add(current)
            if current in ADMIN_ONLY_TYPE_ANCHORS: admin_path.add(current)
            stack.extend(graph.get(current,()))
        result[qid]={
            'physical_settlement_lineage':bool(physical_path),
            'physical_settlement_anchors':sorted(physical_path),
            'admin_only_lineage_without_physical_settlement':bool(admin_path and not physical_path),
            'admin_only_anchors':sorted(admin_path),
            'lineage_unknown_or_unresolved':not physical_path and not admin_path,
        }
    return result


def _load_region_geometries() -> tuple[dict[str, Any], dict[str, str]]:
    from shapely.geometry import shape
    geometries={}
    for path in (RUS_REGION_GEOMETRY, UKR_REGION_GEOMETRY):
        data=json.loads(path.read_text(encoding='utf-8'))
        for feature in data.get('features',[]):
            iso=(feature.get('properties') or {}).get('shapeISO')
            if iso and feature.get('geometry'):
                geometries[str(iso)]=shape(feature['geometry'])
    receipt=json.loads(REGION_RECEIPT.read_text(encoding='utf-8'))
    region_iso={text_key(region):str(iso) for region,iso in receipt.get('mapping',{}).items()}
    return geometries,region_iso


def _point_inside_source_region(latitude: Any, longitude: Any, source_region: Any,
                               geometries: dict[str, Any], region_iso: dict[str, str]) -> tuple[bool, str | None]:
    from shapely.geometry import Point
    try:
        lat=float(latitude); lon=float(longitude)
    except (TypeError,ValueError): return False,None
    raw_region=str(source_region or '')
    iso=raw_region if raw_region in geometries else region_iso.get(text_key(raw_region))
    geom=geometries.get(iso or '')
    if not geom or not valid_wgs84(lat,lon): return False,iso
    # Covers includes points on a simplified administrative boundary.
    return bool(geom.covers(Point(lon,lat))),iso


def is_physical_settlement_source(settlement_type: Any, population_scope: Any, source_is_physical_np: Any) -> bool:
    """Do not let territorial/federal-city aggregate rows borrow a settlement point."""
    scope=str(population_scope or '').strip().casefold()
    return (str(settlement_type or '').strip().casefold() == 'город'
            and scope == 'settlement' and bool_value(source_is_physical_np))


def build_semantic_v5(output_dir: Path = Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_05'),
                      sample_n: int = 100, seed: int = SEED) -> dict[str, Any]:
    """Enrich the frozen v4 packet with type ancestry and a separate point-only city family."""
    started=time.monotonic(); output_dir.mkdir(parents=True,exist_ok=False)
    v4_manifest=json.loads((V4_OUTPUT/'manifest.json').read_text(encoding='utf-8'))
    v4_coverage_path=V4_OUTPUT/'coordinate_candidate_rule_coverage.parquet'
    old_coverage=pd.read_parquet(v4_coverage_path)
    ledger=pd.read_parquet(LEDGER)
    wide=pd.read_parquet(WIDE)
    p31_frequency=V4_OUTPUT/'wikidata_p31_type_frequency.csv'
    hierarchy=json.loads(P31_HIERARCHY.read_text(encoding='utf-8'))
    type_profiles=wikidata_type_lineage(hierarchy)
    geometries,region_iso=_load_region_geometries()
    cities=ledger.loc[ledger.settlement_type.astype('string').str.casefold().eq('город')].copy()
    region_screen=pd.read_parquet(REGION_SCREEN)[['source_record_id','geometry_iso']]
    cities=cities.merge(region_screen,on='source_record_id',how='left',validate='one_to_one')
    provider_screen=pd.read_parquet(PROVIDER_CODES)[['source_record_id','source_is_physical_np','dadata_latitude','dadata_longitude']]
    cities=cities.merge(provider_screen,on='source_record_id',how='left',validate='one_to_one')
    city_ids=set(cities.source_record_id.astype(str))
    city_wide=wide.loc[wide.source_record_id.astype(str).isin(city_ids)].copy()
    city_context=cities.set_index('source_record_id')[['settlement_name','settlement_type','population','region_raw','geometry_iso','district_raw','municipality_raw','population_scope','source_is_physical_np','dadata_latitude','dadata_longitude','raw_oktmo','source_file','source_row','source_native_id','source_locator']].to_dict('index')
    point_rows=[]; qid_summaries=[]
    for row in city_wide.to_dict('records'):
        sid=str(row.get('source_record_id')); ctx=city_context.get(sid,{})
        code_exact=bool_value(row.get('wikidata_truthy_exact_p764_match'))
        name_exact=bool_value(row.get('wikidata_name_exact_label'))
        qid=str(row.get('wikidata_qid') or '')
        p31=[str(x.get('value_qid')) for x in parse_json(row.get('wikidata_truthy_p31_claims_json')) if x.get('value_qid')]
        physical_qids=sorted(q for q in p31 if type_profiles.get(q,{}).get('physical_settlement_lineage'))
        admin_only_qids=sorted(q for q in p31 if type_profiles.get(q,{}).get('admin_only_lineage_without_physical_settlement'))
        unique_qid=not bool_value(row.get('entity_competition_across_tsv_or_truthy'))
        unique_source_binding=not bool_value(row.get('source_observation_competition_for_exact_oktmo'))
        expected_region=ctx.get('region_raw')
        expected_geometry_iso=ctx.get('geometry_iso')
        source_physical_np=is_physical_settlement_source(ctx.get('settlement_type'),ctx.get('population_scope'),ctx.get('source_is_physical_np'))
        qid_context_candidate=code_exact and name_exact and bool(physical_qids) and unique_qid and unique_source_binding
        qid_candidate=source_physical_np and qid_context_candidate
        coords={}
        for point in parse_json(row.get('points_json')):
            try: lat=float(point.get('latitude')); lon=float(point.get('longitude'))
            except (TypeError,ValueError): continue
            if not valid_wgs84(lat,lon): continue
            key=(round(lat,7),round(lon,7))
            coords.setdefault(key,[]).append(point)
        inside_rows=[]
        for (lat,lon),observations in sorted(coords.items()):
            distance_to_provider=haversine_km(lat,lon,ctx.get('dadata_latitude'),ctx.get('dadata_longitude'))
            inside,iso=_point_inside_source_region(lat,lon,expected_geometry_iso or expected_region,geometries,region_iso)
            evidence_sources=sorted({str(p.get('source_kind') or p.get('source_file') or 'wikimedia_point') for p in observations})
            rec={
                'source_record_id':sid,'wikidata_qid':qid,'source_oktmo_raw':row.get('source_oktmo_raw'),
                'source_oktmo_exact_digits':row.get('source_oktmo_exact_digits'),'source_name':ctx.get('settlement_name'),
                'source_type':ctx.get('settlement_type'),'source_population':ctx.get('population'),'source_region_raw':expected_region,
                'source_population_scope':ctx.get('population_scope'),'source_is_physical_np':bool_value(ctx.get('source_is_physical_np')),
                'physical_settlement_source_gate':source_physical_np,
                'source_region_geometry_iso':iso,'wikidata_latitude':lat,'wikidata_longitude':lon,
                'wikidata_provider_point_distance_km':distance_to_provider,
                'large_city_provider_distance_gt_5km_review_only':bool(distance_to_provider is not None and distance_to_provider>5),
                'wikidata_point_evidence_json':json.dumps(observations,ensure_ascii=False,sort_keys=True),
                'wikidata_point_evidence_sources_json':json.dumps(evidence_sources,ensure_ascii=False),
                'wikidata_truthy_exact_p764_match':code_exact,'wikidata_exact_source_name_label':name_exact,
                'wikidata_p31_qids_json':json.dumps(p31),'wikidata_physical_lineage_qids_json':json.dumps(physical_qids),
                'wikidata_admin_only_lineage_qids_json':json.dumps(admin_only_qids),
                'wikidata_unique_qid_binding':unique_qid,'wikidata_unique_source_code_observation':unique_source_binding,
                'point_inside_expected_physical_source_region':inside,'point_coordinate_candidate_gate':bool(qid_candidate and inside),
                'point_context_candidate_without_source_scope_gate':bool(qid_context_candidate and inside),
                'provider_id_binding_decided_separately':False,'provider_coordinate_binding_decided_separately':False,
                'country_p17_is_context_not_geographic_veto':True,'admission_status':'candidate_only_independent_verification_required',
            }
            point_rows.append(rec)
            if qid_candidate and inside: inside_rows.append(rec)
        qid_summaries.append({
            'source_record_id':sid,'wikidata_qid':qid,'wikidata_truthy_exact_p764_match':code_exact,
            'wikidata_exact_source_name_label':name_exact,'wikidata_p31_claims_json':json.dumps(p31),
            'wikidata_exact_code_physical_class_lineage':bool(code_exact and physical_qids),
            'source_population_scope':ctx.get('population_scope'),'source_is_physical_np':bool_value(ctx.get('source_is_physical_np')),
            'physical_settlement_source_gate':source_physical_np,
            'wikidata_physical_lineage_qids_json':json.dumps(physical_qids),'wikidata_admin_only_lineage_qids_json':json.dumps(admin_only_qids),
            'wikidata_point_observation_count':int(row.get('distinct_tsv_or_module_points_count') or 0),
            'entity_competition_across_tsv_or_truthy':not unique_qid,'source_observation_competition_for_exact_oktmo':not unique_source_binding,
            'wikidata_candidate_qid_gate':bool(qid_candidate),'wikidata_valid_distinct_point_count':len(coords),
            'wikidata_pre_scope_context_inside_region_point_count':sum(bool(r['point_context_candidate_without_source_scope_gate']) for r in [x for x in point_rows if x['source_record_id']==sid and x['wikidata_qid']==qid]),
            'wikidata_inside_expected_region_point_count':sum(bool(r['point_inside_expected_physical_source_region']) for r in [x for x in point_rows if x['source_record_id']==sid and x['wikidata_qid']==qid]),
            'wikidata_eligible_inside_expected_region_point_count':len(inside_rows),
        })
    points=pd.DataFrame(point_rows)
    summaries=pd.DataFrame(qid_summaries)
    if not points.empty:
        # Output coordinate-level candidate evidence; no row is accepted here.
        points.to_parquet(output_dir/'wikidata_city_point_candidates.parquet',index=False)
    else:
        points.to_parquet(output_dir/'wikidata_city_point_candidates.parquet',index=False)
    # Collapse QID candidates by source row without hiding QID competition.
    row_rollup=[]
    for sid,g in summaries.groupby('source_record_id',sort=False):
        row_rollup.append({'source_record_id':str(sid),'wikidata_city_candidate_qid_count':int(g.wikidata_candidate_qid_gate.sum()),
                           'wikidata_city_candidate_qids_json':json.dumps(g.loc[g.wikidata_candidate_qid_gate,'wikidata_qid'].tolist()),
                           'wikidata_city_candidate_inside_region_points':int(g.wikidata_eligible_inside_expected_region_point_count.sum()),
                           'wikidata_city_pre_scope_context_inside_region_points':int(g.wikidata_pre_scope_context_inside_region_point_count.sum()),
                           'wikidata_city_any_candidate_point_inside_source_region':bool(g.wikidata_eligible_inside_expected_region_point_count.sum()),
                           'wikidata_city_any_qid_competition':bool(g.entity_competition_across_tsv_or_truthy.any()),
                           'wikidata_city_any_source_code_competition':bool(g.source_observation_competition_for_exact_oktmo.any()),
                           'wikidata_city_any_exact_source_label':bool(g.wikidata_exact_source_name_label.any()),
                           'wikidata_city_any_physical_class_lineage':bool(g.wikidata_physical_lineage_qids_json.map(lambda x:bool(parse_json(x))).any()),
                           'wikidata_city_any_exact_code_physical_class_lineage':bool(g.wikidata_exact_code_physical_class_lineage.any()),
                           'wikidata_city_physical_settlement_source_gate':bool(g.physical_settlement_source_gate.any()),
                           'wikidata_city_p31_semantics_json':json.dumps([{'qid':r.wikidata_qid,'p31':parse_json(r.wikidata_p31_claims_json),'physical_lineage':parse_json(r.wikidata_physical_lineage_qids_json),'admin_only_lineage':parse_json(r.wikidata_admin_only_lineage_qids_json)} for r in g.itertuples()],ensure_ascii=False)})
    city_rollup=pd.DataFrame(row_rollup)
    old_city=old_coverage.loc[old_coverage.source_record_id.astype(str).isin(city_ids)].copy()
    city=old_city.merge(city_rollup,on='source_record_id',how='left',validate='one_to_one')
    city['wikidata_city_candidate_qid_count']=city.wikidata_city_candidate_qid_count.fillna(0).astype(int)
    city['wikidata_city_candidate_inside_region_points']=city.wikidata_city_candidate_inside_region_points.fillna(0).astype(int)
    city['candidate_rule_family_a_urban_level4_physical_code_name_point_in_region']=(
        city.city_level4_missing_name_type_exception_candidate.fillna(False).astype(bool)
        &city.wikidata_city_any_candidate_point_inside_source_region.fillna(False).astype(bool)
        &city.wikidata_city_physical_settlement_source_gate.fillna(False).astype(bool))
    city['candidate_rule_family_c_wikidata_physical_source_city_point'] = (city.wikidata_city_any_candidate_point_inside_source_region.fillna(False).astype(bool)
        &city.wikidata_city_physical_settlement_source_gate.fillna(False).astype(bool))
    city['wikidata_coordinate_hold_flags_json']=[json.dumps(([] if bool_value(r.wikidata_city_physical_settlement_source_gate) else ['source_city_is_aggregate_not_physical_settlement']) +
        ([] if bool_value(r.wikidata_city_any_candidate_point_inside_source_region) else ['no_unique_exact_code_name_physical_type_region_point_candidate']),ensure_ascii=False) for r in city.itertuples()]
    # v4's preliminary P31 flag treated any admin-only parent as a veto. Replace it only
    # where the retrieved ancestry also proves physical settlement lineage; preserve all other provider holds.
    city['provider_binding_hold_flags_after_semantic_type_review_json']=[json.dumps([
        flag for flag in parse_json(raw)
        if not (flag=='known_admin_only_wikidata_type_without_known_physical_type' and bool_value(physical))
    ],ensure_ascii=False) for raw,physical in zip(city.candidate_hold_flags_json,city.wikidata_city_any_exact_code_physical_class_lineage)]
    city['identity_admission']=False; city['coordinate_admission']=False
    city['candidate_status_no_acceptance']='review_packet_candidate_only'
    city['city_coordinate_review_flags_json']=[json.dumps([x for x in [
        'wikidata_class_semantics_retrieved_from_P31_P279_claim_ancestry',
        'country_P17_does_not_veto_point',
        'coordinate_is_in_expected_ADM1_region_not_city_geometry',
        'provider_FIAS_ID_binding_is_separate_and_may_remain_unresolved',
        'Wikimedia_TSV_module_truthy_are_one_evidence_family',
        'admin_label_match_not_required_when_exact_code_name_and_physical_region_context_hold',
    ]],ensure_ascii=False) for _ in range(len(city))]
    city.to_parquet(output_dir/'city_coordinate_candidate_coverage.parquet',index=False)
    candidates=points.loc[points.point_coordinate_candidate_gate].copy() if not points.empty else points
    candidate_sources=set(candidates.source_record_id.astype(str)) if not candidates.empty else set()
    review=city.loc[city.source_record_id.astype(str).isin(candidate_sources)].copy()
    review['candidate_rule_family']='C_wikidata_physical_city_coordinate_in_source_region'
    review_sample=strata_sample(review,n=sample_n,seed=seed)
    if not candidates.empty:
        candidate_details=(candidates.groupby('source_record_id',sort=False)
                           .apply(lambda g:json.dumps(g[['wikidata_qid','source_oktmo_raw','wikidata_latitude','wikidata_longitude','wikidata_p31_qids_json','wikidata_physical_lineage_qids_json','wikidata_point_evidence_json']].to_dict('records'),ensure_ascii=False))
                           .rename('wikidata_candidate_point_evidence_json').reset_index())
        review_sample=review_sample.merge(candidate_details,on='source_record_id',how='left',validate='one_to_one')
    review_sample['sample_seed']=seed
    review_sample['sample_design_note']='Fixed-seed stratified sample for independent review; no accuracy estimate, identity or coordinate acceptance.'
    review_sample.to_parquet(output_dir/'city_wikidata_point_validation_sample.parquet',index=False)
    # Reuse the expensive raw facts/type counts from v4; this receipt pins that immutable artifact.
    v4_p31_path=V4_OUTPUT/'wikidata_p31_type_frequency.csv'
    v5_p31=pd.read_csv(v4_p31_path)
    label_entities=metadata_entities(json.loads(P31_METADATA.read_text(encoding='utf-8')))
    lineage_manifest=[]
    for qid,profile in sorted(type_profiles.items()):
        ent=hierarchy.get('entities',{}).get(qid,{})
        label=((ent.get('labels') or {}).get('en') or {}).get('value')
        lineage_manifest.append({'qid':qid,'label_en':label,**profile})
    pd.DataFrame(lineage_manifest).to_csv(output_dir/'wikidata_p31_lineage_profiles.csv',index=False)
    metrics={
        'source_city_rows':int(len(city)),'source_city_population':int(city.population.fillna(0).sum()),
        'city_level4_provider_code_exception_rows':int(city.city_level4_missing_name_type_exception_candidate.fillna(False).sum()),
        'city_A_level4_semantic_point_rows':int(city.candidate_rule_family_a_urban_level4_physical_code_name_point_in_region.sum()),
        'city_A_level4_semantic_point_population':int(city.loc[city.candidate_rule_family_a_urban_level4_physical_code_name_point_in_region,'population'].fillna(0).sum()),
        'city_C_wikidata_coordinate_candidate_rows':int(city.candidate_rule_family_c_wikidata_physical_source_city_point.sum()),
        'city_C_wikidata_coordinate_candidate_population':int(city.loc[city.candidate_rule_family_c_wikidata_physical_source_city_point,'population'].fillna(0).sum()),
        'city_C_rejected_aggregate_source_rows':int((city.wikidata_city_pre_scope_context_inside_region_points.gt(0)&~city.wikidata_city_physical_settlement_source_gate.fillna(False)).sum()),
        'city_C_rejected_aggregate_source_population':int(city.loc[city.wikidata_city_pre_scope_context_inside_region_points.gt(0)&~city.wikidata_city_physical_settlement_source_gate.fillna(False),'population'].fillna(0).sum()),
        'coordinate_point_candidate_records':int(len(candidates)),'point_samples_requested':sample_n,'point_sample_rows':int(len(review_sample)),
        'P31_type_frequency_rows_reused_from_v4':int(len(v5_p31)),'P31_type_frequency_sha256_reused':sha256(v4_p31_path),
        'type_hierarchy_entities':int(len(hierarchy.get('entities',{}))),'physical_lineage_type_count':sum(x['physical_settlement_lineage'] for x in type_profiles.values()),
        'admin_only_without_physical_lineage_type_count':sum(x['admin_only_lineage_without_physical_settlement'] for x in type_profiles.values()),
        'identity_or_coordinate_admissions':0,
    }
    output_files=['wikidata_city_point_candidates.parquet','city_coordinate_candidate_coverage.parquet','city_wikidata_point_validation_sample.parquet','wikidata_p31_lineage_profiles.csv']
    manifest={
        'status':'review_packet_only_no_identity_or_coordinate_admissions','packet_version':'coordinate_validation_packet_semantic_city_r2_seed_20261002',
        'parent_packet_manifest':str(V4_OUTPUT/'manifest.json'),'parent_packet_manifest_sha256':sha256(V4_OUTPUT/'manifest.json'),
        'reused_v4_frequency_artifact':{'path':str(v4_p31_path),'sha256':sha256(v4_p31_path),'rows':int(len(v5_p31))},
        'inputs':{
            'coordinate_ledger':{'path':str(LEDGER),'sha256':sha256(LEDGER),'rows':int(len(ledger))},
            'wide_point_bindings':{'path':str(WIDE),'sha256':sha256(WIDE),'rows':int(len(wide))},
            'provider_code_screen':{'path':str(PROVIDER_CODES),'sha256':sha256(PROVIDER_CODES),'rows':int(len(pd.read_parquet(PROVIDER_CODES)))},
            'region_point_screen':{'path':str(REGION_SCREEN),'sha256':sha256(REGION_SCREEN),'receipt':str(REGION_RECEIPT),'receipt_sha256':sha256(REGION_RECEIPT),'role':'provider point ADM1 diagnostic only; Wikidata candidate points are separately intersected against same versioned source polygons'},
            'physical_region_polygons':[{'path':str(p),'sha256':sha256(p)} for p in (RUS_REGION_GEOMETRY,UKR_REGION_GEOMETRY)],
            'type_P279_hierarchy':{'path':str(P31_HIERARCHY),'sha256':sha256(P31_HIERARCHY),'queried_type_and_ancestor_entities':int(len(hierarchy.get('entities',{}))),'batch_count':int(hierarchy.get('batch_count',0)),'max_expansion_depth':hierarchy.get('expansion_max_depth'),'unresolved_queue_count':hierarchy.get('unresolved_queue_count')},
            'type_label_description_metadata':{'path':str(P31_METADATA),'sha256':sha256(P31_METADATA),'entities':len(label_entities)},
        },
        'rules':{
            'C_wikidata_physical_city_coordinate_point':'Census source row typed city, population_scope=settlement, and source_is_physical_np=true (federal-city/territorial aggregates are excluded); one unambiguous QID bound by exact truthy source OKTMO; exact Russian source-name label; P31 class has retrieved P279 path to physical settlement anchors (Q486972/Q515/Q532/Q10354598/Q7930989); distinct valid WGS84 Wikidata point is inside the source expected ADM1 geometry. Does not require a FIAS provider ID or point match; provider binding remains separately reported. Wikimedia TSV/module/truthy points are one provider family. No row admitted.',
            'A_urban_level4_physical_code_name_point_in_region':'C city point candidate plus existing DaData exact source/provider OKTMO and FIAS level-4 city provider candidate. Provider returned own-name/type fields remain missing. Wiki point must be within correct physical ADM1; 0.5 km and P131 exact label are not universal hard gates. A region polygon does not establish exact intracity point placement; exact code/name + static physical city lineage is a binding candidate for independent review.',
            'admin_class_logic':'A type with both physical and administrative ancestry is retained as physical lineage (for example city classes). Only an explicitly retrieved admin-only ancestry without any physical-settlement anchor is flagged admin-only; unknown classes remain unknown.',
            'country_and_region_logic':'P17 is metadata only. The point must fall within the source physical ADM1 geometry selected from the census region context; this is geography, not a geopolitical P17 veto. Crimea/Sevastopol geometry mapping is inherited from the cited v1 receipt.',
            'distance_logic':'Distance to DaData/provider point is retained by v4 as a review cue, not proof of coordinate error. Large-city points require city-extent/static-object review if coordinate placement inside the city matters.',
        },
        'metrics':metrics,'runtime_seconds':time.monotonic()-started,'max_rss_kib':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        'implementation_sha256':sha256(Path(__file__)),'outputs':{str(output_dir/f):{'rows':int(len(pd.read_parquet(output_dir/f)) if f.endswith('.parquet') else len(pd.read_csv(output_dir/f))),'sha256':sha256(output_dir/f)} for f in output_files},
    }
    (output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def build_city_a_sample_supplement(output_dir: Path = Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_07'),
                                   sample_n: int = 100, seed: int = SEED) -> dict[str, Any]:
    """Sample the broadened provider-bound city family from frozen semantic-city v6 outputs."""
    output_dir.mkdir(parents=True,exist_ok=False); started=time.monotonic()
    v6_dir=Path('/workspace/settlements-work/coordinates/validation_packet/run_20261002_06')
    coverage_path=v6_dir/'city_coordinate_candidate_coverage.parquet'
    points_path=v6_dir/'wikidata_city_point_candidates.parquet'
    coverage=pd.read_parquet(coverage_path)
    points=pd.read_parquet(points_path)
    candidates=coverage.loc[coverage.candidate_rule_family_a_urban_level4_physical_code_name_point_in_region.fillna(False).astype(bool)].copy()
    candidates['candidate_rule_family']='A_urban_level4_physical_code_name_point_in_region'
    sampled=strata_sample(candidates,n=sample_n,seed=seed)
    eligible_points=points.loc[points.point_coordinate_candidate_gate.fillna(False).astype(bool)]
    if len(sampled) and len(eligible_points):
        details=(eligible_points.loc[eligible_points.source_record_id.astype(str).isin(set(sampled.source_record_id.astype(str)))]
                 .groupby('source_record_id',sort=False)
                 .apply(lambda g:json.dumps(g[['wikidata_qid','source_oktmo_raw','wikidata_latitude','wikidata_longitude','source_region_geometry_iso','wikidata_provider_point_distance_km','large_city_provider_distance_gt_5km_review_only','wikidata_p31_qids_json','wikidata_physical_lineage_qids_json','wikidata_point_evidence_json']].to_dict('records'),ensure_ascii=False))
                 .rename('wikidata_candidate_point_evidence_json').reset_index())
        sampled=sampled.merge(details,on='source_record_id',how='left',validate='one_to_one')
    sampled['sample_seed']=seed
    sampled['sample_design_note']='Fixed-seed stratified sample for independent city-object and point review. ADM1 containment is region context, not city-extent proof; no accuracy estimate or admission.'
    sampled['identity_admission']=False; sampled['coordinate_admission']=False
    sample_path=output_dir/'a_urban_level4_validation_sample.parquet'
    sampled.to_parquet(sample_path,index=False)
    manifest={
        'status':'review_sample_only_no_identity_or_coordinate_admissions','packet_version':'city_A_level4_sample_supplement_r1_seed_20261002',
        'parent_semantic_city_packet':str(v6_dir/'manifest.json'),'parent_manifest_sha256':sha256(v6_dir/'manifest.json'),
        'input_coverage':{'path':str(coverage_path),'sha256':sha256(coverage_path),'rows':int(len(coverage))},
        'input_point_candidates':{'path':str(points_path),'sha256':sha256(points_path),'rows':int(len(points))},
        'candidate_family':'physical census city settlement scope + exact source/provider OKTMO + FIAS level-4 city provider candidate + exact-code/name/physical-Wikidata P31 ancestry + Wikidata WGS84 point in expected physical ADM1; candidate only, no identity/coordinate acceptance.',
        'sample_seed':seed,'sample_rows_requested':sample_n,'sample_rows':int(len(sampled)),
        'sample_by_region':{str(k):int(v) for k,v in sampled.region_raw.fillna('<missing>').value_counts().items()},
        'sample_by_population_band':{str(k):int(v) for k,v in sampled.population.map(population_band).value_counts().items()},
        'sample_by_oktmo_width':{str(k):int(v) for k,v in sampled.source_oktmo_digit_width.value_counts(dropna=False).items()},
        'candidate_rows':int(len(candidates)),'candidate_population':int(candidates.population.fillna(0).sum()),
        'runtime_seconds':time.monotonic()-started,'max_rss_kib':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        'implementation_sha256':sha256(Path(__file__)),
        'output':{'path':str(sample_path),'sha256':sha256(sample_path),'rows':int(len(sampled)),'columns':list(sampled.columns)},
    }
    (output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def build(ledger_path: Path = LEDGER, wide_path: Path = WIDE, provider_codes_path: Path = PROVIDER_CODES,
          baseline_db_path: Path = BASELINE_DB, type_metadata_path: Path = P31_METADATA,
          output_dir: Path = OUTPUT, sample_n: int = 100, seed: int = SEED) -> dict[str, Any]:
    started=time.monotonic(); output_dir.mkdir(parents=True,exist_ok=True)
    ledger=pd.read_parquet(ledger_path)
    wide=pd.read_parquet(wide_path)
    codes=pd.read_parquet(provider_codes_path)
    with type_metadata_path.open('r',encoding='utf-8') as stream: type_metadata=json.load(stream)
    # Join only by exact selected source locator; source-level row linkage was validated in ledger.
    merged=ledger.merge(codes,on='source_record_id',how='left',suffixes=('','_provider_screen'),validate='one_to_one')
    source_context=merged[['source_record_id','population','settlement_name','settlement_type','region_raw','district_raw','municipality_raw','oktmo','okato']].copy()
    wide_coordinates=wide.merge(
        ledger[['source_record_id','provider_latitude','provider_longitude']].rename(columns={
            'provider_latitude':'dadata_provider_latitude','provider_longitude':'dadata_provider_longitude'}),
        on='source_record_id',how='left',validate='many_to_one')
    wiki_by_source=_aggregate_wikidata(wide_coordinates,source_context.rename(columns={'oktmo':'source_oktmo_raw','okato':'source_okato_projection_raw'}),type_metadata)
    wiki_summary=(pd.DataFrame.from_dict(wiki_by_source,orient='index')
                  .rename_axis('_source_record_id_string').reset_index())
    merged['_source_record_id_string']=merged.source_record_id.astype(str)
    merged=merged.merge(wiki_summary,on='_source_record_id_string',how='left',validate='one_to_one').drop(columns=['_source_record_id_string'])
    history,history_meta=_load_historical(baseline_db_path)
    hist_json=[];hist_counts=[];hist_label=False;hist_region=False;hist_points=[]
    for row in merged.to_dict('records'):
        matches=_historical_matches(row,history)
        hist_json.append(json.dumps(matches,ensure_ascii=False,sort_keys=True))
        hist_counts.append(len(matches)); hist_label |= any(m['geokladr_label_exact_source_name'] for m in matches); hist_region |= any(m['geokladr_region_exact_source_region'] for m in matches)
        hist_points.append([m for m in matches if m.get('latitude') is not None and m.get('longitude') is not None])
    merged['geokladr_exact_code_candidate_count']=hist_counts
    merged['geokladr_exact_code_candidates_json']=hist_json
    merged['geokladr_any_exact_code_label_match']=[any(x.get('geokladr_label_exact_source_name') for x in parse_json(v)) for v in hist_json]
    merged['geokladr_any_exact_code_source_region_match']=[any(x.get('geokladr_region_exact_source_region') for x in parse_json(v)) for v in hist_json]
    merged['geokladr_historical_points_json']=json.dumps([]) # per-row points below
    merged['geokladr_historical_points_json']=[json.dumps(x,ensure_ascii=False,sort_keys=True) for x in hist_points]
    merged['geokladr_point_provider_family_id']='geokladr_okato_snapshot_2011'
    merged['geokladr_reuse_is_historical_continuity_inference']=True
    merged['geokladr_no_polygon_or_censusdate_required']=True

    merged['wikidata_evidence_count']=merged.get('wikidata_qid_count',pd.Series(0,index=merged.index)).fillna(0).astype(int)
    merged['wikidata_label_exact_source_name']=merged.get('wikidata_label_exact_source_name',pd.Series(False,index=merged.index)).fillna(False).astype(bool)
    merged['wikidata_admin_context_exact']=merged.get('wikidata_admin_context_exact',pd.Series(False,index=merged.index)).fillna(False).astype(bool)
    merged['wikidata_p31_physical_known']=merged.get('wikidata_p31_physical_known',pd.Series(False,index=merged.index)).fillna(False).astype(bool)
    merged['wikidata_has_any_p17_claim']=merged.get('wikidata_p17_claim_present',pd.Series(False,index=merged.index)).fillna(False).astype(bool)
    merged['wikidata_point_consistent_le_0_5km']=merged.get('wikidata_any_p625_within_0_5km',pd.Series(False,index=merged.index)).fillna(False).astype(bool)

    # Rule families are candidate cohorts only. No coordinate or identity decision is generated.
    core=merged.get('provider_code_candidate_core',pd.Series(False,index=merged.index)).fillna(False).astype(bool)
    strict=merged.get('strict_named_type_provider_code_candidate',pd.Series(False,index=merged.index)).fillna(False).astype(bool)
    city4_exception=merged.get('city_level4_missing_name_type_exception_candidate',pd.Series(False,index=merged.index)).fillna(False).astype(bool)
    source_city=merged.settlement_type.astype('string').str.casefold().eq('город')
    family_a_rural=core&strict&~source_city
    wiki_urban_gate=(merged.wikidata_truthy_exact_p764_match.fillna(False).astype(bool)
                     &merged.wikidata_label_exact_source_name&merged.wikidata_has_any_p17_claim
                     &merged.wikidata_p31_physical_known&merged.wikidata_admin_context_exact
                     &merged.wikidata_point_consistent_le_0_5km)
    geokladr_independent_candidate=(merged.geokladr_any_exact_code_label_match.fillna(False).astype(bool)
                                    &merged.geokladr_any_exact_code_source_region_match.fillna(False).astype(bool)
                                    &merged.geokladr_exact_code_candidate_count.gt(0))
    family_a_urban=city4_exception&(wiki_urban_gate|geokladr_independent_candidate)
    wikimedia_independent_candidate=(merged.wikidata_truthy_exact_p764_match.fillna(False).astype(bool)
                                     &merged.wikidata_label_exact_source_name&merged.wikidata_p31_physical_known
                                     &merged.wikidata_admin_context_exact&merged.wikidata_point_consistent_le_0_5km)
    family_b= strict & merged.provider_primary_fias_level_4_or_6.fillna(False).astype(bool) & core & (wikimedia_independent_candidate|geokladr_independent_candidate)
    merged['candidate_rule_family_a_rural_exact_code_and_own_name_type']=family_a_rural
    merged['candidate_rule_family_a_urban_city_level4_wikimedia_context']=family_a_urban
    merged['candidate_rule_family_b_strict_name_code_and_independent_context']=family_b
    merged['candidate_status_no_acceptance']='review_packet_candidate_only'
    merged['identity_review_decision']=None; merged['coordinate_review_decision']=None; merged['coordinate_admission']=False; merged['identity_admission']=False
    # Common risk flags are retained in sample strata and a distinct targeted queue.
    risk_flags=[]; hold_flags=[]
    for row in merged.to_dict('records'):
        flags=[]
        holds=[]
        if bool_value(row.get('baseline_provider_coordinate_conflict')): flags.append('baseline_known_coordinate_conflict')
        if gt_one(row.get('provider_general_fias_duplicate_count')): flags.append('duplicate_provider_general_fias_id')
        if gt_one(row.get('provider_coordinate_duplicate_count')): flags.append('duplicate_provider_coordinate')
        if float(row.get('wikidata_p625_farthest_distance_km') or 0)>5:
            flags.append('wikidata_point_gt_5km_screen')
            # Distance screens flag disagreement for review; they do not prove a wrong point.
            if str(row.get('settlement_type','')).casefold() != 'город':
                holds.append('wikidata_point_gt_5km_unresolved_review_hold')
            else:
                flags.append('large_city_point_distance_requires_extent_or_static_object_review')
        if bool_value(row.get('wikidata_truthy_exact_p764_match')) and not bool_value(row.get('wikidata_label_exact_source_name')): flags.append('wiki_exact_code_but_label_mismatch')
        if bool_value(row.get('wikidata_p17_has_ukraine')) and not bool_value(row.get('wikidata_p17_has_russia')): flags.append('p17_ukraine_only_review_geopolitical_not_block')
        if bool_value(row.get('provider_query_receipt_missing')): flags.append('provider_query_receipt_missing_soft_lineage')
        if not bool_value(row.get('provider_point_valid_wgs84')): flags.append('provider_point_missing_or_invalid')
        if bool_value(row.get('wikidata_p31_admin_known')) and not bool_value(row.get('wikidata_p31_physical_known')):
            holds.append('known_admin_only_wikidata_type_without_known_physical_type')
        if bool_value(row.get('baseline_provider_coordinate_conflict')): holds.append('known_baseline_point_conflict_requires_resolution')
        if gt_one(row.get('provider_general_fias_duplicate_count')): holds.append('duplicate_provider_id_requires_resolution')
        if gt_one(row.get('provider_coordinate_duplicate_count')): holds.append('duplicate_provider_point_requires_resolution')
        risk_flags.append(flags)
        hold_flags.append(holds)
    merged['review_risk_flags_json']=[json.dumps(x,ensure_ascii=False) for x in risk_flags]
    merged['candidate_hold_flags_json']=[json.dumps(x,ensure_ascii=False) for x in hold_flags]
    merged['candidate_review_gate_clear']=[not x for x in hold_flags]
    merged['targeted_review_flags_json']=merged.review_risk_flags_json

    families={
        'A_rural_exact_code_plus_own_name_type':family_a_rural,
        'A_urban_level4_wiki_context_exception':family_a_urban,
        'B_strict_name_plus_external_context':family_b,
    }
    samples=[]; sample_stats={}
    for name,mask in families.items():
        group=merged.loc[mask].copy()
        sampled=strata_sample(group,n=sample_n,seed=seed)
        sampled['candidate_rule_family']=name
        samples.append(sampled)
        sample_stats[name]={
            'candidate_rows':int(len(group)),
            'candidate_population':int(group.population.fillna(0).sum()),
            'sample_rows':int(len(sampled)),
            'sample_unique_regions':int(sampled.region_raw.map(text_key).nunique()) if len(sampled) else 0,
            'sample_by_source_type':{str(k):int(v) for k,v in sampled.settlement_type.fillna('<missing>').value_counts().items()} if len(sampled) else {},
            'sample_by_population_band':{str(k):int(v) for k,v in sampled.population.map(population_band).value_counts().items()} if len(sampled) else {},
            'sample_by_oktmo_width':{str(k):int(v) for k,v in sampled.source_oktmo_digit_width.value_counts(dropna=False).items()} if len(sampled) else {},
            'sample_highrisk_count':int(sampled.review_risk_flags_json.map(lambda s: bool(parse_json(s))).sum()) if len(sampled) else 0,
        }
    sample=pd.concat(samples,ignore_index=True) if samples else merged.head(0).copy()
    sample=attach_wide_evidence(sample,wide)
    sample['sample_design_note']='Fixed-seed stratified verification packet. These rows are selected for reviewer work; no precision estimate or acceptance is implied.'
    sample_path=output_dir/'validation_sample.parquet'; sample.to_parquet(sample_path,index=False)

    # Separate deterministic targeted queue: highest-population cities, severe coordinate/identity outliers,
    # provider conflicts and duplicate IDs/coordinates, including rows excluded from ordinary cohorts.
    merged['target_largest_city']=source_city & merged.provider_point_valid_wgs84.fillna(False).astype(bool)
    merged['target_largest_city_rank']=merged.loc[merged.target_largest_city].population.rank(method='first',ascending=False)
    largest=merged[merged.target_largest_city & merged.target_largest_city_rank.le(100)].copy()
    outlier=merged[merged.review_risk_flags_json.map(lambda s:'wikidata_point_gt_5km_screen' in parse_json(s))].sort_values(['population','source_record_id'],ascending=[False,True]).head(250).copy()
    conflicts=merged[merged.review_risk_flags_json.map(lambda s:'baseline_known_coordinate_conflict' in parse_json(s))].sort_values(['population','source_record_id'],ascending=[False,True]).head(250).copy()
    duplicates=merged[merged.review_risk_flags_json.map(lambda s:any(x in parse_json(s) for x in ['duplicate_provider_general_fias_id','duplicate_provider_coordinate']))].sort_values(['population','source_record_id'],ascending=[False,True]).head(500).copy()
    target=pd.concat([largest,outlier,conflicts,duplicates],ignore_index=True).drop_duplicates('source_record_id')
    target=attach_wide_evidence(target,wide)
    target['targeted_queue_flags_json']=[json.dumps([flag for flag in ['largest_city','wikidata_point_gt_5km_screen','baseline_known_coordinate_conflict','duplicate_provider_general_fias_id','duplicate_provider_coordinate'] if (flag=='largest_city' and bool_value(row.get('target_largest_city'))) or flag in parse_json(row.get('review_risk_flags_json'))],ensure_ascii=False) for row in target.to_dict('records')]
    target['identity_review_decision']=None; target['coordinate_review_decision']=None; target['coordinate_admission']=False; target['identity_admission']=False
    target_path=output_dir/'targeted_audit_queue.parquet'; target.to_parquet(target_path,index=False)

    coverage=merged.loc[:,coverage_columns(merged)].copy()
    coverage_path=output_dir/'coordinate_candidate_rule_coverage.parquet'
    coverage.to_parquet(coverage_path,index=False)

    p31=_p31_frequency(wide,source_context,type_metadata)
    p31_path=output_dir/'wikidata_p31_type_frequency.csv'; p31.to_csv(p31_path,index=False)
    family_counts={name:int(mask.sum()) for name,mask in families.items()}
    runtime=time.monotonic()-started
    manifest={
        'status':'review_packet_only_no_identity_or_coordinate_admissions',
        'packet_version':'coordinate_validation_packet_r1_seed_20261002',
        'sample_seed':seed,'sample_per_rule_family_requested':sample_n,
        'sampling_note':'Fixed-seed stratified sample by urban/rural category, region, population band, source OKTMO width and risk flags. No confidence/precision statement is derived from n=100.',
        'rule_family_definitions':{
            'A_rural_exact_code_plus_own_name_type':'physical source row, exact raw source OKTMO equals returned DaData OKTMO after only terminal .0 removal, general FIAS object level 4/6, unique provider ID and point, WGS84/coarse geography, no baseline known conflict, exact own provider name/type; excludes source city rows.',
            'A_urban_level4_wiki_context_exception':'same provider-code core for source city + DaData FIAS level 4 with missing own name/type payload; requires either exact-code Wikidata context (exact Russian label, explicit P17 context, known physical P31 class, exact admin label/source context match, point within 0.5km) OR raw historical GeoKLADR exact code + source-name + source-region match. These are binding/context candidates, not a coordinate proof; a large-city point-distance disagreement is a targeted review flag requiring static object/extent evidence, not a distance-only rejection.',
            'B_strict_name_plus_external_context':'strict DaData own name/type and provider-code core plus exact-code-bound Wikidata P625/type/admin context or exact-coded GeoKLADR label/region context. Wikidata TSV/module/truthy are deduplicated as one evidence family; GeoKLADR carries 2011-era historical role. Candidate only; lineage independence still requires reviewer assessment.'},
        'country_handling':'P17 Q159 (Russia), Q212 (Ukraine), and all other raw QIDs are reported as claims. P17 alone never excludes a point or treats Crimea/Sevastopol as a wrong physical location; review target region/codes/admin context separately.',
        'coordinate_and_binding_separation':'Provider/QID/source-code object binding fields and point quality/distance fields remain separate. City-circle crosswalk, coordinate proximity, qc_geo, provider code agreement or missing receipt alone never admit a point.',
        'no_historical_polygon_requirement':'GeoKLADR 2011 evidence is a dated code/name/type/region/point candidate; earlier-year reuse remains a continuity inference, and no object requires an exact historical polygon solely to enter review.',
        'inputs':{
            'coordinate_ledger':{'path':str(ledger_path),'sha256':sha256(ledger_path),'rows':int(len(ledger)),'locator_contract':'source_record_id joins exact ledger row; ledger source_file/source_row/source_native_id/source_locator retained'},
            'wide_wikidata':{'path':str(wide_path),'sha256':sha256(wide_path),'rows':int(len(wide))},
            'provider_code_screen':{'path':str(provider_codes_path),'sha256':sha256(provider_codes_path),'rows':int(len(codes))},
            'baseline_legacy_database_read_only':{'path':str(baseline_db_path),'sha256':sha256(baseline_db_path),'tables':['historical_geokladr_coordinates_2011','historical_okato_142_2009'],'rows':history_meta},
            'p31_type_metadata':{'path':str(type_metadata_path),'sha256':sha256(type_metadata_path),'retrieval_receipts':[{'requested_at_utc':x.get('requested_at_utc'),'retrieved_at_utc':x.get('retrieved_at_utc'),'url':x.get('url'),'http_status':x.get('http_status'),'tls_verified_by_default_context':x.get('tls_verified_by_default_context'),'response_sha256':x.get('response_sha256'),'requested_count':len(x.get('requested_qids',[])),'returned_count':x.get('entity_count')} for x in type_metadata.get('batches',[])], 'entity_count':len(metadata_entities(type_metadata))},
        },
        'metrics':{
            'selected_rows':int(len(merged)),'selected_population':int(merged.population.fillna(0).sum()),
            'provider_code_core_rows':int(core.sum()),'provider_code_core_population':int(merged.loc[core,'population'].fillna(0).sum()),
            'provider_exact_own_name_type_rows':int(strict.sum()),'city_level4_missing_name_type_rows':int(city4_exception.sum()),
            'family_candidate_counts':family_counts,'samples':sample_stats,
            'targeted_queue_rows':int(len(target)),'targeted_largest_cities':int(len(largest)),'targeted_wikidata_point_outliers_pre_cap':int(merged.review_risk_flags_json.map(lambda s:'wikidata_point_gt_5km_screen' in parse_json(s)).sum()),
            'targeted_known_provider_conflicts_pre_cap':int(merged.review_risk_flags_json.map(lambda s:'baseline_known_coordinate_conflict' in parse_json(s)).sum()),
            'targeted_duplicate_id_or_coordinate_pre_cap':int(merged.review_risk_flags_json.map(lambda s:any(x in parse_json(s) for x in ['duplicate_provider_general_fias_id','duplicate_provider_coordinate'])).sum()),
            'wikidata_p31_type_count':int(len(p31)),'wikidata_p31_type_metadata_entities':len(metadata_entities(type_metadata)),
            'wikidata_p31_qids_with_known_physical_meaning':int(p31.explicit_known_physical_type.sum()) if len(p31) else 0,
            'wikidata_p31_qids_with_known_admin_meaning':int(p31.explicit_known_admin_type.sum()) if len(p31) else 0,
            'coordinate_or_identity_admissions':0,
        },
        'runtime_seconds':runtime,
        'max_rss_kib':int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        'implementation_sha256':sha256(Path(__file__)),
        'outputs':{
            str(sample_path):{'rows':int(len(sample)),'columns':list(sample.columns)},
            str(target_path):{'rows':int(len(target)),'columns':list(target.columns)},
            str(coverage_path):{'rows':int(len(coverage)),'columns':list(coverage.columns)},
            str(p31_path):{'rows':int(len(p31)),'columns':list(p31.columns)},
        },
    }
    (output_dir/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--sample-n',type=int,default=100)
    parser.add_argument('--seed',type=int,default=SEED)
    parser.add_argument('--semantic-city-v5',action='store_true',help='Build bounded city point/type-lineage packet reusing immutable v4 frequency artifact')
    parser.add_argument('--city-a-sample-supplement',action='store_true',help='Build the fixed-seed sample for widened FIAS-bound city candidate family from immutable v6 outputs')
    args=parser.parse_args()
    if args.city_a_sample_supplement:
        result=build_city_a_sample_supplement(output_dir=args.output,sample_n=args.sample_n,seed=args.seed)
    elif args.semantic_city_v5:
        result=build_semantic_v5(output_dir=args.output,sample_n=args.sample_n,seed=args.seed)
    else:
        result=build(output_dir=args.output,sample_n=args.sample_n,seed=args.seed)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
