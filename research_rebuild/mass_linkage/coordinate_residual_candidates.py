"""Bounded candidate diagnostics for the remaining 2021 physical-NP points.

This module joins the frozen coordinate screen to accepted 2021 point uses and
official historical OKATO snapshots. Every result is a review candidate or a
hold; this module cannot admit coordinates or provider/FIAS bindings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import numpy as np


SCREEN_DEFAULT = Path('/workspace/settlements-work/coordinates/ledger/coordinate_screen.parquet')
USES_DEFAULT = Path('/workspace/settlements-work/coordinates/accepted_final_v1/accepted_point_uses.parquet')
GEO2011_DEFAULT = Path('/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet')
CLASS2009_DEFAULT = Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet')
OUT_DEFAULT = Path('/workspace/settlements-work/continuation_20261003/coordinate_rule')
OUT_V2_DEFAULT = Path('/workspace/settlements-work/continuation_20261003/coordinate_rule_v2')
OUT_V3_DEFAULT = Path('/workspace/settlements-work/continuation_20261003/coordinate_rule_v3')
OUT_V4_DEFAULT = Path('/workspace/settlements-work/continuation_20261003/coordinate_rule_v4')
HISTORICAL_CONTEXT_DEFAULT = Path('/workspace/settlements-work/candidates/historical_spatial_v1/all_historical_object_context.parquet')
HISTORICAL_CONTEXT_RECEIPT_DEFAULT = Path('/workspace/settlements-work/candidates/historical_spatial_v1/receipt.json')
V1_RECEIPT_DEFAULT = OUT_DEFAULT / 'run_receipt.json'

SCREEN_COLUMNS = [
    'source_record_id', 'census_year', 'source_name_raw', 'settlement_name', 'settlement_type',
    'region_raw', 'population', 'population_scope', 'latitude', 'longitude', 'okato', 'oktmo',
    'raw_object_level', 'raw_object_name', 'raw_oktmo', 'raw_region', 'raw_mun_upper',
    'raw_mun_lower', 'raw_settlement', 'raw_settlement_fias_id_dadata', 'raw_settlement_dadata',
    'raw_settlement_type_full_dadata', 'raw_fias_id_dadata', 'raw_fias_level_dadata',
    'raw_okato_dadata', 'raw_oktmo_dadata', 'raw_latitude_dadata', 'raw_longitude_dadata',
    'provider_settlement_fias_id', 'provider_general_fias_id', 'provider_fias_level',
    'provider_settlement_name', 'provider_settlement_type_full', 'provider_latitude',
    'provider_longitude', 'source_object_is_naselenniy_punkt', 'source_is_aggregate_scope',
    'provider_general_fias_duplicate_count', 'provider_coordinate_duplicate_count',
    'baseline_provider_coordinate_conflict', 'provider_name_exact_selected_name',
    'provider_type_exact_selected_type', 'provider_point_valid_wgs84',
    'provider_point_in_coarse_russia_envelope', 'gate_provider_primary_fias_object_present_at_level_4_or_6',
    'gate_provider_secondary_settlement_id_not_contradictory',
    'gate_provider_primary_fias_id_unique_in_selected_rows',
    'gate_provider_coordinate_unique_in_selected_rows',
    'candidate_family_exact_named_physical_np_fias_point', 'candidate_status',
]
V2_SCREEN_COLUMNS = list(dict.fromkeys(SCREEN_COLUMNS + [
    'provider_settlement_fias_duplicate_count', 'raw_longitude_dadata', 'raw_latitude_dadata',
    'raw_okato_dadata', 'raw_settlement_fias_id_dadata', 'region_norm',
]))
GEO_TYPE_2011 = {
    'д': 'деревня', 'с': 'село', 'п': 'поселок', 'х': 'хутор', 'пгт': 'поселок городского типа',
    'г': 'город', 'ст': 'станция', 'ст-ца': 'станица', 'ж/д ст': 'железнодорожная станция',
    'рзд': 'железнодорожный разъезд', 'нп': 'населенный пункт', 'аул': 'аул',
    'починок': 'починок', 'сл': 'слобода', 'выселок': 'выселок', 'аал': 'аал',
    'м': 'местечко', 'заимка': 'заимка', 'ж/д рзд': 'железнодорожный разъезд',
    'ж/д остановочный пункт': 'железнодорожная остановка', 'ж/д казарма': 'железнодорожная казарма',
    'кордон': 'кордон', 'ж/д платформа': 'железнодорожная платформа', 'метеостанция': 'метеостанция',
    'монтерский пункт': 'монтерский пункт', 'гидрологический пост': 'гидрологический пост',
    'маяк': 'маяк', 'кп': 'курортный поселок', 'дп': 'дачный поселок',
}


def norm(value: object) -> str:
    if value is None or pd.isna(value):
        return ''
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().replace('ё', 'е').split())


def code_text(value: object) -> str:
    """Preserve string digits/width; remove only whitespace and numeric .0 artifact."""
    if value is None or pd.isna(value):
        return ''
    value = str(value).strip()
    return re.sub(r'\.0$', '', value)


def type_norm(value: object) -> str:
    s = re.sub(r'[^\w]+', ' ', norm(value), flags=re.UNICODE).strip()
    return {'пгт': 'поселок городского типа', 'посёлок городского типа': 'поселок городского типа'}.get(s, s)


def admin_norm(value: object) -> str:
    """Exact admin-name comparison after the census label's municipality wrapper."""
    s = norm(value)
    s = re.sub(r'\bмуниципальный\s+', '', s)
    return s


def region_from_classifier(classifier: pd.DataFrame) -> pd.DataFrame:
    # OKATO level-1 region row: XX000000; remain string-only to retain leading zeroes.
    r = classifier[classifier.historical_okato.str.fullmatch(r'\d{2}000000', na=False)].copy()
    r['region_code2'] = r.historical_okato.str[:2]
    r['historical_region_name'] = r.name_full
    return r[['region_code2', 'historical_region_name']].drop_duplicates()


def historical_tables(geo_path: Path, class_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    geo = pd.read_parquet(geo_path, columns=[
        'historical_okato', 'name_raw', 'settlement_type_raw', 'is_deleted', 'ter_raw_text',
        'oktmo_2011_raw', 'source_sha256',
    ])
    cls = pd.read_parquet(class_path, columns=[
        'historical_okato', 'name', 'status', 'name_full', 'is_settlement_raw',
        'source_sha256', 'source_snapshot_version',
    ])
    # The 2011 raw geo file has a one-row-per-OKATO record key. Normalize only the
    # documented one-letter type abbreviations; source strings and codes stay intact.
    short_type = {'д': 'деревня', 'с': 'село', 'г': 'город', 'п': 'поселок',
                  'пгт': 'поселок городского типа', 'х': 'хутор', 'ст': 'станция',
                  'жд ст': 'железнодорожная станция', 'м': 'местечко'}
    geo['historic_name'] = geo.name_raw.fillna('').astype(str).str.replace(r'^\s*\S+\s+', '', regex=True)
    geo['historic_type'] = geo.settlement_type_raw.fillna('').astype(str).str.strip().str.casefold().map(short_type).fillna('')
    geo['region_code2'] = geo.historical_okato.str[:2]
    geo = geo.merge(region_from_classifier(cls), on='region_code2', how='left', validate='many_to_one')
    geo['historical_code_source'] = 'geokladr_2011'
    # Classifier names/status provide a second frozen historical named-code witness.
    cls['historic_name'] = cls.name.fillna('').astype(str)
    cls['historic_type'] = cls.status.fillna('').astype(str)
    cls['region_code2'] = cls.historical_okato.str[:2]
    cls = cls.merge(region_from_classifier(cls), on='region_code2', how='left', validate='many_to_one')
    cls['historical_code_source'] = 'okato_classifier_2009'
    # For an 11-digit locality code, the first five-digit OKATO component plus
    # 000 is the enclosing district/city administration code in this snapshot.
    # Match that official parent label exactly against the 2021 upper admin field.
    parent_lookup = unique_map(cls, 'historical_okato', ['name_full'], 'parent')
    parent_lookup = parent_lookup.rename(columns={'historical_okato': 'admin_parent_code', 'name_full': 'historical_admin_parent_name'})
    cls['admin_parent_code'] = cls.historical_okato.str[:5] + '000'
    cls = cls.merge(parent_lookup[['admin_parent_code', 'historical_admin_parent_name']], on='admin_parent_code', how='left', validate='many_to_one')
    # GeoKladr points at the same historical OKATO object; derive its parent via
    # the independently parsed 2009 classifier's code hierarchy.
    geo['admin_parent_code'] = geo.historical_okato.str[:5] + '000'
    parent_for_geo = parent_lookup[['admin_parent_code', 'historical_admin_parent_name']].drop_duplicates('admin_parent_code')
    geo = geo.merge(parent_for_geo, on='admin_parent_code', how='left', validate='many_to_one')
    # Counts are diagnostic only: they show when an exact historical code and
    # parent resolve a same-region name/type homonym that name uniqueness misses.
    for frame in (geo, cls):
        keys = pd.DataFrame({'name': frame.historic_name.map(norm), 'type': frame.historic_type.map(type_norm), 'region': frame.historical_region_name.map(norm)}, index=frame.index)
        frame['same_name_type_region_count'] = keys.groupby(['name', 'type', 'region'], dropna=False)['name'].transform('size')
    return geo, cls


def unique_map(frame: pd.DataFrame, key: str, value_columns: list[str], prefix: str) -> pd.DataFrame:
    f = frame[frame[key].ne('')].copy()
    counts = f.groupby(key, sort=False).size().rename(prefix + '_record_count')
    f = f.drop_duplicates(key, keep=False)
    f = f[[key] + value_columns].merge(counts, on=key, validate='one_to_one')
    return f


def enrich_historical_candidates(rem: pd.DataFrame, geo: pd.DataFrame, cls: pd.DataFrame) -> pd.DataFrame:
    # Exact source OKATO value to raw historical object. A `.0` cleanup is allowed
    # for the upstream numeric serialization artifact; no integer conversion or
    # zero padding is done, so loss of leading zeroes causes a safe non-match.
    geo_u = unique_map(geo, 'historical_okato', ['historic_name', 'historic_type', 'is_deleted', 'region_code2', 'historical_region_name', 'oktmo_2011_raw', 'historical_admin_parent_name', 'same_name_type_region_count'], 'geo')
    cls_u = unique_map(cls, 'historical_okato', ['historic_name', 'historic_type', 'is_settlement_raw', 'region_code2', 'historical_region_name', 'source_snapshot_version', 'historical_admin_parent_name', 'same_name_type_region_count'], 'class')
    f = rem.copy()
    f['provider_okato_key'] = f.raw_okato_dadata.map(code_text)
    f['source_oktmo_key'] = f.raw_oktmo.map(code_text)
    f['provider_oktmo_key'] = f.raw_oktmo_dadata.map(code_text)
    for m, code, prefix in [(geo_u, 'provider_okato_key', 'geo'), (cls_u, 'provider_okato_key', 'class')]:
        renames = {'historical_okato': 'provider_okato_key', f'{prefix}_record_count': f'{prefix}_record_count'}
        renames.update({c: f'{prefix}_{c}' for c in m.columns if c not in {'historical_okato', f'{prefix}_record_count'}})
        right = m.rename(columns=renames)
        f = f.merge(right, on=code, how='left', validate='many_to_one')
        f[f'{prefix}_unique_named_historic_code'] = f[f'{prefix}_record_count'].eq(1)
        f[f'{prefix}_exact_historical_name'] = f.settlement_name.map(norm).eq(f[f'{prefix}_historic_name'].map(norm))
        f[f'{prefix}_exact_historical_type'] = f.settlement_type.map(type_norm).eq(f[f'{prefix}_historic_type'].map(type_norm))
        f[f'{prefix}_exact_historical_region'] = f.raw_region.map(norm).eq(f[f'{prefix}_historical_region_name'].map(norm))
        f[f'{prefix}_exact_historical_admin_parent'] = f.raw_mun_upper.map(admin_norm).eq(f[f'{prefix}_historical_admin_parent_name'].map(admin_norm))
        f[f'{prefix}_same_name_type_region_count'] = f[f'{prefix}_same_name_type_region_count'].astype('Float64').fillna(0).astype('int64')
        if prefix == 'geo':
            deleted = f.get(f'{prefix}_is_deleted', pd.Series(False, index=f.index)).astype('boolean').fillna(True).astype(bool)
            f[f'{prefix}_historical_record_active'] = ~deleted
        else:
            f[f'{prefix}_historical_record_active'] = f.get(f'{prefix}_is_settlement_raw', pd.Series('f', index=f.index)).astype(str).str.casefold().eq('t')
        f[f'{prefix}_named_code_region_admin_match'] = f[[f'{prefix}_unique_named_historic_code', f'{prefix}_exact_historical_name', f'{prefix}_exact_historical_type', f'{prefix}_exact_historical_region', f'{prefix}_exact_historical_admin_parent', f'{prefix}_historical_record_active']].all(axis=1)
    # Exact current OKTMO crosswalk between selected 2021 physical-NP row and
    # provider response. Both codes retain their text width and leading zeroes.
    if 'source_oktmo_selected_np_count' not in f:
        source_counts = f.groupby('source_oktmo_key', dropna=False).source_record_id.transform('size')
        f['source_oktmo_selected_np_count'] = source_counts
    f['source_oktmo_unique_in_selected_np'] = f.source_oktmo_key.ne('') & f.source_oktmo_selected_np_count.eq(1)
    f['provider_oktmo_equals_source_oktmo_exact_digits'] = f.source_oktmo_key.ne('') & f.source_oktmo_key.eq(f.provider_oktmo_key)
    return f


def classify(f: pd.DataFrame) -> pd.DataFrame:
    r = f.copy()
    for col in ['geo_same_name_type_region_count', 'class_same_name_type_region_count']:
        if col not in r:
            r[col] = 0
    base = (
        r.source_object_is_naselenniy_punkt.fillna(False).astype(bool)
        & ~r.source_is_aggregate_scope.fillna(True).astype(bool)
        & r.provider_general_fias_id.fillna('').astype(str).ne('')
        & r.provider_fias_level.isin(['4', '6'])
        & r.provider_name_exact_selected_name.fillna(False).astype(bool)
        & r.provider_type_exact_selected_type.fillna(False).astype(bool)
        & r.provider_point_valid_wgs84.fillna(False).astype(bool)
        & r.provider_point_in_coarse_russia_envelope.fillna(False).astype(bool)
        & ~r.baseline_provider_coordinate_conflict.fillna(False).astype(bool)
        & r.provider_general_fias_duplicate_count.eq(1)
        & r.provider_coordinate_duplicate_count.eq(1)
        & r.gate_provider_secondary_settlement_id_not_contradictory.fillna(False).astype(bool)
    )
    r['gate_provider_named_physical_fias_point_core'] = base
    r['gate_current_exact_code_unique'] = r.provider_oktmo_equals_source_oktmo_exact_digits & r.source_oktmo_unique_in_selected_np
    hist_geo = r.geo_named_code_region_admin_match.fillna(False)
    hist_cls = r['class_named_code_region_admin_match'].fillna(False)
    r['gate_exact_historical_named_okato_region_and_admin'] = hist_geo | hist_cls
    r['candidate_rule_current_exact_oktmo'] = base & r.gate_current_exact_code_unique
    r['candidate_rule_historical_exact_named_okato_region_admin'] = base & r.gate_exact_historical_named_okato_region_and_admin
    r['candidate_rule_union'] = r.candidate_rule_current_exact_oktmo | r.candidate_rule_historical_exact_named_okato_region_admin
    r['historical_same_region_homonym_count'] = r[['geo_same_name_type_region_count', 'class_same_name_type_region_count']].max(axis=1)
    r['candidate_rule_resolves_historical_regional_homonym'] = r.candidate_rule_historical_exact_named_okato_region_admin & r.historical_same_region_homonym_count.gt(1)
    r['provider_coordinate_candidate_only'] = True
    r['external_fias_binding_admission'] = False
    r['coordinate_admission'] = False
    # Persistent reasons are separate from the strongest positive route.
    r['residual_bucket'] = 'other_hold_or_no_strong_rule'
    r.loc[~r.provider_point_valid_wgs84.fillna(False), 'residual_bucket'] = 'provider_point_missing_or_invalid'
    r.loc[r.baseline_provider_coordinate_conflict.fillna(False), 'residual_bucket'] = 'known_coordinate_conflict'
    r.loc[r.provider_name_exact_selected_name.fillna(False).eq(False), 'residual_bucket'] = 'provider_name_mismatch'
    r.loc[r.provider_type_exact_selected_type.fillna(False).eq(False), 'residual_bucket'] = 'provider_type_mismatch'
    r.loc[r.provider_general_fias_id.fillna('').astype(str).eq(''), 'residual_bucket'] = 'no_provider_fias_object'
    r.loc[r.provider_general_fias_duplicate_count.ne(1), 'residual_bucket'] = 'competing_or_nonunique_provider_fias_id'
    r.loc[r.provider_coordinate_duplicate_count.ne(1), 'residual_bucket'] = 'competing_or_nonunique_point'
    if {'provider_okato_key', 'geo_record_count', 'class_record_count'}.issubset(r.columns):
        code_hit = r.provider_okato_key.ne('') & (r.geo_record_count.notna() | r['class_record_count'].notna())
    else:
        code_hit = pd.Series(False, index=r.index)
    context_mismatch = code_hit & ~r.gate_exact_historical_named_okato_region_and_admin & r.provider_name_exact_selected_name.fillna(False) & r.provider_type_exact_selected_type.fillna(False)
    r.loc[context_mismatch, 'residual_bucket'] = 'historical_code_region_or_admin_context_contradiction'
    r.loc[r.candidate_rule_current_exact_oktmo, 'residual_bucket'] = 'candidate_current_exact_oktmo'
    r.loc[~r.candidate_rule_current_exact_oktmo & r.candidate_rule_historical_exact_named_okato_region_admin, 'residual_bucket'] = 'candidate_historical_named_okato_region_admin'
    return r


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def weighted_table(frame: pd.DataFrame, group: str) -> list[dict[str, object]]:
    result = []
    for key, g in frame.groupby(group, dropna=False, sort=True):
        result.append({'group': str(key), 'rows': len(g), 'population': int(pd.to_numeric(g.population, errors='coerce').fillna(0).sum())})
    return result


def fixed_sample(frame: pd.DataFrame, n_per_stratum: int = 12) -> pd.DataFrame:
    chosen_ids = fixed_sample_ids(frame, n_per_stratum)
    f = frame[frame.source_record_id.isin(chosen_ids)].copy()
    f['population_band'] = pd.cut(pd.to_numeric(f.population, errors='coerce'), [-1, 0, 99, 999, 9999, float('inf')], labels=['unknown_or_zero', '1_99', '100_999', '1000_9999', '10000_plus'])
    keep = ['source_record_id', 'raw_region', 'settlement_name', 'settlement_type', 'raw_mun_upper', 'raw_mun_lower', 'population', 'provider_general_fias_id', 'provider_oktmo_equals_source_oktmo_exact_digits', 'geo_named_code_region_admin_match', 'class_named_code_region_admin_match', 'historical_same_region_homonym_count', 'candidate_rule_resolves_historical_regional_homonym', 'candidate_rule_union', 'residual_bucket']
    return f[keep].sort_values(['residual_bucket', 'population', 'source_record_id'], kind='mergesort')


def fixed_sample_ids(frame: pd.DataFrame, n_per_stratum: int = 12, salt: str = 'coord-rule-v1') -> set[str]:
    f = frame.copy()
    f['population_band'] = pd.cut(pd.to_numeric(f.population, errors='coerce'), [-1, 0, 99, 999, 9999, float('inf')], labels=['unknown_or_zero', '1_99', '100_999', '1000_9999', '10000_plus'])
    f['sample_key'] = f.source_record_id.map(lambda x: hashlib.sha256((salt + '|' + str(x)).encode()).hexdigest())
    f = f.sort_values('sample_key', kind='mergesort')
    chosen = f.groupby(['residual_bucket', 'population_band'], observed=True, sort=True).head(n_per_stratum)
    return set(chosen.source_record_id.astype(str))


def geo_name_typed_2011(name_raw: object, type_raw: object) -> str:
    """Strip only a recognized, matching type prefix at the start of a raw name."""
    name = '' if name_raw is None or pd.isna(name_raw) else str(name_raw).strip()
    raw_type = '' if type_raw is None or pd.isna(type_raw) else str(type_raw).strip().casefold()
    expected = GEO_TYPE_2011.get(raw_type)
    if not expected or not name:
        return name
    if name.casefold().startswith(raw_type + ' '):
        return name[len(raw_type):].strip()
    return name


def strict_code_text(value: object) -> tuple[str, str]:
    """Keep raw separately; normalize only digit strings plus a `.0+` serialization suffix."""
    if value is None or pd.isna(value):
        return '', 'missing'
    raw = str(value)
    if raw != raw.strip():
        return '', 'whitespace_present_invalid_code'
    if re.fullmatch(r'[0-9]+', raw):
        return raw, 'native_digits'
    match = re.fullmatch(r'([0-9]+)\.0+', raw)
    if match:
        return match.group(1), 'provider_integer_looking_dot_zero_serialization_normalized'
    return '', 'invalid_or_nonliteral_code'


def haversine_columns(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> np.ndarray:
    values = np.column_stack([*(pd.to_numeric(x, errors='coerce').to_numpy(dtype=float) for x in (lat1, lon1, lat2, lon2))])
    valid = (np.isfinite(values).all(axis=1) & (np.abs(values[:, 0]) <= 90) & (np.abs(values[:, 2]) <= 90)
             & (np.abs(values[:, 1]) <= 180) & (np.abs(values[:, 3]) <= 180))
    result = np.full(len(values), np.nan)
    if valid.any():
        x = np.radians(values[valid])
        dlat, dlon = x[:, 2] - x[:, 0], x[:, 3] - x[:, 1]
        h = np.sin(dlat / 2) ** 2 + np.cos(x[:, 0]) * np.cos(x[:, 2]) * np.sin(dlon / 2) ** 2
        result[valid] = 2 * 6371.0088 * np.arcsin(np.sqrt(np.minimum(1, h)))
    return result


def historical_tables_v2(geo_path: Path, class_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    geo = pd.read_parquet(geo_path, columns=[
        'historical_okato', 'name_raw', 'settlement_type_raw', 'is_deleted', 'longitude_from_long',
        'latitude_from_lat', 'source_sha256',
    ])
    cls = pd.read_parquet(class_path, columns=[
        'historical_okato', 'name', 'status', 'name_full', 'is_settlement_raw',
        'source_sha256', 'source_snapshot_version',
    ])
    cls['historical_okato'] = cls.historical_okato.astype('string')
    geo['historical_okato'] = geo.historical_okato.astype('string')
    cls['historical_region_name'] = cls.name_full.where(cls.historical_okato.str.fullmatch(r'\d{2}000000', na=False))
    region_rows = cls[cls.historical_okato.str.fullmatch(r'\d{2}000000', na=False)][['historical_okato', 'name_full']].copy()
    region_rows['region_code2'] = region_rows.historical_okato.str[:2]
    region_rows = region_rows.rename(columns={'name_full': 'classifier_region_name'}).drop(columns='historical_okato')
    cls['region_code2'] = cls.historical_okato.str[:2]
    cls = cls.merge(region_rows, on='region_code2', how='left', validate='many_to_one')
    cls['historical_region_name'] = cls['classifier_region_name']
    cls['historic_name'] = cls.name.fillna('').astype(str)
    cls['historic_type'] = cls.status.fillna('').astype(str)
    # Code hierarchy: first 5 digits plus 000 is the enclosing classifier admin row.
    cls['admin_parent_code'] = cls.historical_okato.str[:5] + '000'
    admin = cls[['historical_okato', 'name_full']].drop_duplicates('historical_okato').rename(columns={'historical_okato': 'admin_parent_code', 'name_full': 'historical_admin_parent_name'})
    cls = cls.merge(admin, on='admin_parent_code', how='left', validate='many_to_one')
    geo['historic_name'] = [geo_name_typed_2011(n, t) for n, t in zip(geo.name_raw, geo.settlement_type_raw)]
    geo['historic_type'] = geo.settlement_type_raw.fillna('').astype(str).str.strip().str.casefold().map(GEO_TYPE_2011).fillna('')
    geo['region_code2'] = geo.historical_okato.str[:2]
    geo = geo.merge(region_rows.rename(columns={'classifier_region_name': 'historical_region_name'}), on='region_code2', how='left', validate='many_to_one')
    geo['admin_parent_code'] = geo.historical_okato.str[:5] + '000'
    geo = geo.merge(admin, on='admin_parent_code', how='left', validate='many_to_one')
    geo['geo_latitude'] = pd.to_numeric(geo.latitude_from_lat, errors='coerce')
    geo['geo_longitude'] = pd.to_numeric(geo.longitude_from_long, errors='coerce')
    geo['geo_code_row_count'] = geo.groupby('historical_okato').historical_okato.transform('size')
    cls['classifier_code_row_count'] = cls.groupby('historical_okato').historical_okato.transform('size')
    return geo, cls


def build_v2(screen_path: Path = SCREEN_DEFAULT, uses_path: Path = USES_DEFAULT,
             geo_path: Path = GEO2011_DEFAULT, class_path: Path = CLASS2009_DEFAULT,
             historical_context_path: Path = HISTORICAL_CONTEXT_DEFAULT,
             historical_context_receipt_path: Path = HISTORICAL_CONTEXT_RECEIPT_DEFAULT,
             v1_receipt_path: Path = V1_RECEIPT_DEFAULT, output: Path = OUT_V2_DEFAULT,
             rule_version: str = 'v2') -> dict[str, object]:
    if rule_version not in {'v2', 'v3', 'v4'}:
        raise ValueError('rule_version must be v2, v3, or v4')
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'{rule_version} output is immutable and already populated: {output}')
    output.mkdir(parents=True, exist_ok=True)
    screen = pd.read_parquet(screen_path, columns=V2_SCREEN_COLUMNS)
    screen = screen[screen.census_year.eq(2021) & screen.source_object_is_naselenniy_punkt.fillna(False)].copy()
    uses = pd.read_parquet(uses_path, columns=['target_source_record_id', 'target_year'])
    accepted = set(uses.loc[uses.target_year.eq(2021), 'target_source_record_id'].astype(str))
    screen['source_okato_text'] = screen.raw_okato_dadata.map(lambda x: strict_code_text(x)[0])
    screen['source_okato_serialization'] = screen.raw_okato_dadata.map(lambda x: strict_code_text(x)[1])
    screen['source_okato_dot_zero_serialization'] = screen.source_okato_serialization.eq('provider_integer_looking_dot_zero_serialization_normalized')
    rem = screen[~screen.source_record_id.astype(str).isin(accepted)].copy()
    geo, cls = historical_tables_v2(geo_path, class_path)
    historic_context = pd.read_parquet(historical_context_path, columns=[
        'historical_okato', 'historical_point_modern_region', 'historical_key_region_name_type_count',
    ])
    historic_context['historical_okato'] = historic_context.historical_okato.astype('string')
    geo_count = geo.groupby('historical_okato').size().rename('geo_code_count')
    cls_count = cls.groupby('historical_okato').size().rename('classifier_code_count')
    geo_u = geo.drop_duplicates('historical_okato', keep=False).copy()
    cls_u = cls.drop_duplicates('historical_okato', keep=False).copy()
    geo_cols = ['historical_okato', 'historic_name', 'historic_type', 'historical_region_name', 'historical_admin_parent_name', 'is_deleted', 'geo_latitude', 'geo_longitude', 'source_sha256']
    cls_cols = ['historical_okato', 'historic_name', 'historic_type', 'historical_region_name', 'historical_admin_parent_name', 'is_settlement_raw', 'source_sha256', 'source_snapshot_version']
    geo_right = geo_u[geo_cols].rename(columns={'historical_okato': 'source_okato_text', **{c: (c if c.startswith('geo_') else f'geo_{c}') for c in geo_cols if c != 'historical_okato'}})
    class_right = cls_u[cls_cols].rename(columns={'historical_okato': 'source_okato_text', **{c: f'class_{c}' for c in cls_cols if c != 'historical_okato'}})
    hist = rem.merge(geo_right, on='source_okato_text', how='left', validate='many_to_one')
    hist = hist.merge(class_right, on='source_okato_text', how='left', validate='many_to_one')
    hist = hist.merge(geo_count, left_on='source_okato_text', right_index=True, how='left', validate='many_to_one')
    hist = hist.merge(cls_count, left_on='source_okato_text', right_index=True, how='left', validate='many_to_one')
    context_columns = historic_context.rename(columns={
        'historical_okato': 'source_okato_text',
        'historical_point_modern_region': 'historic_point_modern_region_from_cached_spatial_screen',
        'historical_key_region_name_type_count': 'cached_historical_key_region_name_type_count',
    })
    hist = hist.merge(context_columns, on='source_okato_text', how='left', validate='many_to_one')
    # Keep separate source witnesses and explicitly flag any disagreement.
    for prefix in ('geo', 'class'):
        hist[f'{prefix}_name_exact'] = hist.settlement_name.map(norm).eq(hist[f'{prefix}_historic_name'].map(norm))
        hist[f'{prefix}_type_exact'] = hist.settlement_type.map(type_norm).eq(hist[f'{prefix}_historic_type'].map(type_norm))
        hist[f'{prefix}_region_exact'] = hist.raw_region.map(norm).eq(hist[f'{prefix}_historical_region_name'].map(norm))
    hist['classifier_admin_exact'] = hist.raw_mun_upper.map(admin_norm).eq(hist.class_historical_admin_parent_name.map(admin_norm))
    hist['historical_sources_named_region_admin_concordant'] = (
        hist.geo_name_exact & hist.geo_type_exact & hist.geo_region_exact
        & hist.class_name_exact & hist.class_type_exact & hist.class_region_exact & hist.classifier_admin_exact
    )
    hist['historical_sources_conflict'] = (
        hist.geo_code_count.notna() & hist.classifier_code_count.notna()
        & ~hist.historical_sources_named_region_admin_concordant
    )
    hist['geo_historical_point_valid'] = hist.geo_latitude.between(-90, 90) & hist.geo_longitude.between(-180, 180)
    hist['geo_named_code_region_admin_match'] = hist.geo_code_count.eq(1) & hist.geo_name_exact & hist.geo_type_exact & hist.geo_region_exact & ~hist.geo_is_deleted.astype('boolean').fillna(True).astype(bool)
    hist['class_named_code_region_admin_match'] = hist.classifier_code_count.eq(1) & hist.class_name_exact & hist.class_type_exact & hist.class_region_exact & hist.classifier_admin_exact & hist.class_is_settlement_raw.astype(str).str.casefold().eq('t')
    hist['provider_own_fias_id_present'] = hist.raw_settlement_fias_id_dadata.fillna('').astype(str).str.strip().ne('')
    hist['provider_own_fias_id_unique'] = hist.provider_settlement_fias_duplicate_count.eq(1)
    hist['provider_general_fias_object_valid'] = hist.provider_general_fias_id.fillna('').astype(str).ne('') & hist.provider_fias_level.isin(['4', '6']) & hist.provider_general_fias_duplicate_count.eq(1)
    hist['provider_point_unique'] = hist.provider_coordinate_duplicate_count.eq(1)
    hist['provider_id_consistent'] = hist.gate_provider_secondary_settlement_id_not_contradictory.fillna(False).astype(bool)
    hist['provider_name_type_exact'] = hist.provider_name_exact_selected_name.fillna(False).astype(bool) & hist.provider_type_exact_selected_type.fillna(False).astype(bool)
    hist['no_coordinate_conflict'] = ~hist.baseline_provider_coordinate_conflict.fillna(False).astype(bool)
    hist['both_historical_code_rows_unique'] = hist.geo_code_count.eq(1) & hist.classifier_code_count.eq(1)
    hist['both_historical_source_names_types_regions_exact'] = hist.geo_name_exact & hist.geo_type_exact & hist.geo_region_exact & hist.class_name_exact & hist.class_type_exact & hist.class_region_exact
    hist['geo_and_provider_expected_region'] = (
        hist.historic_point_modern_region_from_cached_spatial_screen.map(norm).eq(hist.region_norm.map(norm))
    )
    hist['geo_provider_distance_km'] = haversine_columns(hist.geo_latitude, hist.geo_longitude, hist.provider_latitude, hist.provider_longitude)
    hist['geo_provider_distance_le_1km'] = pd.Series(hist.geo_provider_distance_km, index=hist.index).le(1.0)
    gates = {
        'physical_nonaggregate_source': hist.source_object_is_naselenniy_punkt.fillna(False).astype(bool) & ~hist.source_is_aggregate_scope.fillna(True).astype(bool),
        'provider_own_and_general_fias_unique_valid': hist.provider_own_fias_id_present & hist.provider_own_fias_id_unique & hist.provider_general_fias_object_valid,
        'provider_secondary_id_consistent': hist.provider_id_consistent,
        'provider_exact_name_and_type': hist.provider_name_type_exact,
        'provider_point_valid_and_unique': hist.provider_point_valid_wgs84.fillna(False).astype(bool) & hist.provider_point_in_coarse_russia_envelope.fillna(False).astype(bool) & hist.provider_point_unique,
        'no_known_coordinate_conflict': hist.no_coordinate_conflict,
        'both_historical_code_rows_unique': hist.both_historical_code_rows_unique,
        'both_2009_and_2011_named_type_region_witnesses_exact': hist.both_historical_source_names_types_regions_exact,
        'classifier_parent_admin_matches_selected_upper_admin': hist.classifier_admin_exact,
        'historical_geo_point_valid': hist.geo_historical_point_valid,
        'historical_geo_point_matches_expected_region': hist.geo_and_provider_expected_region,
        'historical_geo_provider_points_within_1km': hist.geo_provider_distance_le_1km,
    }
    for name, values in gates.items():
        hist[f'gate_{rule_version}_{name}'] = values.fillna(False).astype(bool)
    candidate_rule_column = f'candidate_rule_{rule_version}_both_history_plus_admin_geo_point'
    hist[candidate_rule_column] = hist[[f'gate_{rule_version}_{k}' for k in gates]].all(axis=1)
    hist['candidate_only_no_coordinate_admission'] = True
    hist['external_fias_binding_admission'] = False
    hist['coordinate_admission'] = False
    hist['residual_bucket_v2'] = 'other_hold_or_no_strong_rule'
    hist.loc[~hist.provider_point_valid_wgs84.fillna(False), 'residual_bucket_v2'] = 'provider_point_missing_or_invalid'
    hist.loc[~hist.provider_own_fias_id_unique | ~hist.provider_general_fias_id.notna(), 'residual_bucket_v2'] = 'provider_fias_id_missing_or_nonunique'
    hist.loc[~hist.provider_point_unique, 'residual_bucket_v2'] = 'competing_or_nonunique_provider_point'
    hist.loc[~hist.no_coordinate_conflict, 'residual_bucket_v2'] = 'known_coordinate_conflict'
    hist.loc[hist.historical_sources_conflict, 'residual_bucket_v2'] = 'matched_historical_code_source_contradiction'
    hist.loc[hist.geo_code_count.eq(1) & hist.classifier_code_count.eq(1) & ~hist.classifier_admin_exact, 'residual_bucket_v2'] = 'classifier_admin_context_mismatch'
    hist.loc[hist.geo_code_count.eq(1) & hist.classifier_code_count.eq(1) & hist.geo_provider_distance_km.gt(1), 'residual_bucket_v2'] = 'historical_geo_point_over_1km_from_provider'
    hist.loc[hist[candidate_rule_column], 'residual_bucket_v2'] = f'candidate_{rule_version}_both_history_admin_geo_point'
    candidate_path = output / f'coordinate_rule_{rule_version}_candidates.parquet'
    sample_path = output / 'fixed_stratified_sample.csv'
    candidate_cols = [
        'source_record_id', 'source_name_raw', 'settlement_name', 'settlement_type', 'raw_region',
        'raw_mun_upper', 'raw_mun_lower', 'population', 'raw_okato_dadata', 'source_okato_text',
        'source_okato_serialization', 'provider_settlement_fias_id', 'provider_settlement_fias_duplicate_count',
        'provider_general_fias_id', 'provider_general_fias_duplicate_count', 'provider_fias_level',
        'provider_settlement_name', 'provider_settlement_type_full', 'provider_latitude', 'provider_longitude',
        'geo_historic_name', 'geo_historic_type', 'geo_historical_region_name', 'geo_source_sha256', 'geo_is_deleted',
        'geo_latitude', 'geo_longitude', 'class_historic_name', 'class_historic_type',
        'class_historical_region_name', 'class_historical_admin_parent_name', 'class_source_sha256', 'class_is_settlement_raw', 'geo_provider_distance_km',
        'geo_and_provider_expected_region', 'historical_sources_named_region_admin_concordant',
        candidate_rule_column, 'candidate_only_no_coordinate_admission',
        'external_fias_binding_admission', 'coordinate_admission',
    ]
    candidates = hist[hist[candidate_rule_column]]
    candidates[candidate_cols].to_parquet(candidate_path, index=False)
    sample_input = hist.copy()
    sample_input['residual_bucket'] = sample_input.residual_bucket_v2
    sample_ids = fixed_sample_ids(sample_input, salt=f'coord-rule-{rule_version}')
    sample_columns = [
        'source_record_id', 'raw_region', 'settlement_name', 'settlement_type', 'raw_mun_upper', 'raw_mun_lower', 'population',
        'source_okato_text', 'source_okato_serialization', 'provider_general_fias_id', 'provider_settlement_fias_id',
        'provider_settlement_fias_duplicate_count', 'provider_general_fias_duplicate_count', 'provider_coordinate_duplicate_count',
        'geo_historic_name', 'geo_historic_type', 'geo_source_sha256', 'geo_latitude', 'geo_longitude',
        'class_historic_name', 'class_historic_type', 'class_historical_admin_parent_name', 'class_source_sha256',
        'geo_provider_distance_km', 'geo_and_provider_expected_region', 'historical_sources_conflict',
        candidate_rule_column, 'residual_bucket_v2',
    ]
    sample_path_rows = hist[hist.source_record_id.astype(str).isin(sample_ids)][sample_columns].sort_values(['residual_bucket_v2', 'population', 'source_record_id'], kind='mergesort')
    sample_path_rows.to_csv(sample_path, index=False)
    attrition = []
    mask = pd.Series(True, index=hist.index)
    for name, values in gates.items():
        before = int(mask.sum())
        mask &= values.fillna(False).astype(bool)
        attrition.append({'gate': name, 'remaining_rows': int(mask.sum()), 'remaining_population': int(pd.to_numeric(hist.loc[mask, 'population'], errors='coerce').fillna(0).sum()), 'rejected_at_gate_rows': before - int(mask.sum())})
    inputs = [screen_path, uses_path, geo_path, class_path, historical_context_path, historical_context_receipt_path, v1_receipt_path]
    context_receipt = json.loads(historical_context_receipt_path.read_text(encoding='utf-8'))
    expected_context_hash = context_receipt.get('outputs', {}).get('all_historical_object_context.parquet')
    if expected_context_hash != sha_file(historical_context_path):
        raise ValueError('cached historical spatial context does not match its frozen receipt')
    report = {
        'status': f'candidate_{rule_version}_diagnostic_only_no_coordinate_or_fias_binding_admission',
        'rule_version': rule_version,
        'v1_run_receipt_sha256_pinned': sha_file(v1_receipt_path),
        'inputs': {str(p): {'sha256': sha_file(p), 'bytes': p.stat().st_size} for p in inputs},
        'scope': 'Remaining R2-selected 2021 physical NP rows after exact target ID subtraction of accepted point uses. Population is recorded source population only.',
        'remaining_rows': len(hist), 'remaining_recorded_population': int(pd.to_numeric(hist.population, errors='coerce').fillna(0).sum()),
        'accepted_2021_target_ids_subtracted': len(accepted),
        'provider_okato_serialization_counts': weighted_table(hist.rename(columns={'source_okato_serialization': 'bucket'}), 'bucket'),
        f'{rule_version}_candidate_rows': int(hist[candidate_rule_column].sum()),
        f'{rule_version}_candidate_population': int(hist.loc[hist[candidate_rule_column], 'population'].sum()),
        'population_weighted_residual_breakdown': weighted_table(hist.rename(columns={'residual_bucket_v2': 'bucket'}), 'bucket'),
        'gate_attrition_ordered': attrition,
        'independent_gate_failure_counts': {name: {'rows': int((~values.fillna(False).astype(bool)).sum()), 'population': int(hist.loc[~values.fillna(False).astype(bool), 'population'].sum())} for name, values in gates.items()},
        'matched_source_contradictions': {'rows': int(hist.historical_sources_conflict.sum()), 'population': int(hist.loc[hist.historical_sources_conflict, 'population'].sum())},
        'candidate_definition': [
            '2021 physical nonaggregate NP source row with exact provider own and general FIAS IDs; both IDs unique at their respective provider duplicate counts, level 4/6, and secondary ID noncontradictory',
            'provider full own name/type exact; valid point, unique point, and no known hard coordinate conflict',
            'compare provider OKATO after removing only a literal .0+ suffix from digit-only integer-looking strings; raw strings are retained, width and leading zeroes are unchanged, and native OKTMO is untouched',
            'the exact same OKATO code is unique and active in both raw 2011 GeoKladr and the 2009 classifier; both independently match selected name/type/region exactly',
            'the 2009 classifier code-derived parent label matches selected raw_mun_upper exactly after removal of the census wrapper word municipal',
            'GeoKladr 2011 point is valid and falls in the selected expected ADM1 region according to the pinned historical spatial screen; provider point is within 1 km of it',
            'candidate only; coordinate admission and external FIAS binding admission are false',
        ],
        'name_prefix_rule': 'GeoKladr 2011 names remove a prefix only when it is an anchored recognized abbreviation equal to settlement_type_raw. Unprefixed names such as Великие Луки are unchanged.',
        'provider_okato_normalization': 'This is comparison-only normalization for provider OKATO raw text matching digit-only historical codes: accept [0-9]+ or [0-9]+\\.0+ and strip only the terminal .0+; preserve raw_okato_dadata in all output rows. Never pad, parse as integer, or normalize native OKTMO.',
        'normalization_policy_basis': 'Source-specific historical provider OKATO rule in research_rebuild/mass_linkage/historical_named_points.py::numeric_provider_code_equal; v3 narrows its comparison to exact digit-string content and width, with no integer cast or zero padding.',
        'context_and_date_limit': 'The classifier parent is a raw code-hierarchy label, not an asserted validity-dated municipality. Provider parent-chain fields are unavailable and are not inferred. Expected-region status is inherited from the pinned cached historical spatial screen, whose receipt includes geometry and region inputs.',
        'historical_spatial_context_receipt_sha256': sha_file(historical_context_receipt_path),
        'source_coordinate_and_fias_binding_separate': True,
        'outputs': {},
    }
    report_path = output / f'coordinate_rule_{rule_version}_report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md = [f'# 2021 physical settlement coordinate residual — {rule_version}', '',
          'Candidate diagnostic only. No coordinate or external FIAS binding is admitted.', '',
          f"Residual: {len(hist):,} rows / {report['remaining_recorded_population']:,} recorded population. {rule_version.upper()} strict candidate cohort: {report[f'{rule_version}_candidate_rows']:,} / {report[f'{rule_version}_candidate_population']:,}.", '',
          f'{rule_version.upper()} requires AND agreement from raw GeoKladr 2011 and the 2009 classifier on the same exact OKATO named/type/region row, the classifier code-derived parent exactly matching census upper admin, a valid GeoKladr point in the expected ADM1 region according to the pinned cached spatial screen, and a provider point within 1 km. Provider own and general FIAS objects/IDs and point uniqueness are screened separately.', '',
          '## Ordered gate attrition', '', '| Gate applied | Rows remaining | Population remaining | Rows rejected at gate |', '|---|---:|---:|---:|']
    md += [f"| {r['gate']} | {r['remaining_rows']:,} | {r['remaining_population']:,} | {r['rejected_at_gate_rows']:,} |" for r in attrition]
    md += ['', '## Population weighted residual buckets', '', '| Primary bucket | Rows | Population |', '|---|---:|---:|']
    md += [f"| {r['group']} | {r['rows']:,} | {r['population']:,} |" for r in report['population_weighted_residual_breakdown']]
    md += ['', 'Exact name prefixes in GeoKladr are removed only when an anchored recognized type abbreviation matches the row type. For provider OKATO comparison only, a literal `.0+` suffix is removed from an otherwise digit-only string. The original raw string is retained, and no leading zeroes or code digits are changed. Native OKTMO is untouched.', '',
          'The provider source has no returned parent chain. The classifier parent is interpreted as an OKATO hierarchy label and compared with source admin context; no validity-dated municipality claim is made. Coordinate source points and external provider-ID binding remain separate claims.', '',
          f"Fixed deterministic SHA256-stratified sample: {len(sample_path_rows):,} rows, SHA256 salt `coord-rule-{rule_version}` with first 12 per residual bucket × population band. Candidate parquet: `coordinate_rule_{rule_version}_candidates.parquet`. Input and output hashes: `run_receipt.json`.", '']
    md_path = output / f'coordinate_rule_{rule_version}_report.md'
    md_path.write_text('\n'.join(md), encoding='utf-8')
    report['outputs'] = {
        str(candidate_path): {'rows': len(candidates), 'sha256': sha_file(candidate_path)},
        str(sample_path): {'rows': len(sample_path_rows), 'sha256': sha_file(sample_path)},
        str(md_path): {'sha256': sha_file(md_path)},
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    receipt = {
        'status': report['status'], 'v1_run_receipt_sha256_pinned': report['v1_run_receipt_sha256_pinned'],
        'report_json_sha256': sha_file(report_path), 'report_markdown_sha256': sha_file(md_path),
        'candidate_sha256': sha_file(candidate_path), 'sample_sha256': sha_file(sample_path),
        'input_sha256': {str(p): sha_file(p) for p in inputs},
    }
    (output / 'run_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def build(screen_path: Path = SCREEN_DEFAULT, uses_path: Path = USES_DEFAULT,
          geo_path: Path = GEO2011_DEFAULT, class_path: Path = CLASS2009_DEFAULT,
          output: Path = OUT_DEFAULT) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    screen = pd.read_parquet(screen_path, columns=SCREEN_COLUMNS)
    screen = screen[screen.census_year.eq(2021) & screen.source_object_is_naselenniy_punkt.fillna(False)].copy()
    uses = pd.read_parquet(uses_path, columns=['target_source_record_id', 'target_year'])
    accepted = set(uses.loc[uses.target_year.eq(2021), 'target_source_record_id'].astype(str))
    screen['source_oktmo_key'] = screen.raw_oktmo.map(code_text)
    code_counts = screen.loc[screen.source_oktmo_key.ne('')].groupby('source_oktmo_key').size()
    screen['source_oktmo_selected_np_count'] = screen.source_oktmo_key.map(code_counts).fillna(0).astype('int64')
    remaining = screen[~screen.source_record_id.astype(str).isin(accepted)].copy()
    geo, cls = historical_tables(geo_path, class_path)
    joined = classify(enrich_historical_candidates(remaining, geo, cls))
    # Compact candidate-only evidence table and a fixed, population-stratified sample.
    candidate_path = output / 'coordinate_rule_candidates.parquet'
    sample_path = output / 'fixed_stratified_sample.csv'
    joined[joined.candidate_rule_union].to_parquet(candidate_path, index=False)
    fixed_sample(joined).to_csv(sample_path, index=False)
    report = {
        'status': 'candidate_diagnostic_only_no_coordinate_or_fias_binding_admission',
        'inputs': {str(p): {'sha256': sha_file(p), 'bytes': p.stat().st_size} for p in [screen_path, uses_path, geo_path, class_path]},
        'population_scope_note': 'Only R2-selected 2021 physical naselenny punkt rows not already in accepted_final_v1 point uses; population is reported as recorded and never allocated.',
        'remaining_rows': len(joined),
        'remaining_recorded_population': int(pd.to_numeric(joined.population, errors='coerce').fillna(0).sum()),
        'accepted_2021_target_ids_subtracted': len(accepted),
        'residual_by_bucket': weighted_table(joined, 'residual_bucket'),
        'rule_totals': {
            'existing_exact_named_provider_fias_point_candidate': {
                'rows': int(joined.candidate_family_exact_named_physical_np_fias_point.fillna(False).sum()),
                'population': int(joined.loc[joined.candidate_family_exact_named_physical_np_fias_point.fillna(False), 'population'].sum()),
            },
            'proposed_current_exact_oktmo': {
                'rows': int(joined.candidate_rule_current_exact_oktmo.sum()),
                'population': int(joined.loc[joined.candidate_rule_current_exact_oktmo, 'population'].sum()),
            },
            'proposed_historical_exact_named_okato_region_and_admin': {
                'rows': int(joined.candidate_rule_historical_exact_named_okato_region_admin.sum()),
                'population': int(joined.loc[joined.candidate_rule_historical_exact_named_okato_region_admin, 'population'].sum()),
            },
            'proposed_union_overlap_deduplicated': {
                'rows': int(joined.candidate_rule_union.sum()),
                'population': int(joined.loc[joined.candidate_rule_union, 'population'].sum()),
            },
            'historical_same_region_homonyms_resolved_by_exact_code_and_admin': {
                'rows': int(joined.candidate_rule_resolves_historical_regional_homonym.sum()),
                'population': int(joined.loc[joined.candidate_rule_resolves_historical_regional_homonym, 'population'].sum()),
            },
            'exact_current_source_provider_oktmo_any_residual_row': {
                'rows': int(joined.provider_oktmo_equals_source_oktmo_exact_digits.sum()),
                'population': int(joined.loc[joined.provider_oktmo_equals_source_oktmo_exact_digits, 'population'].sum()),
            },
        },
        'relationship_to_existing_candidate_family': {
            'proposed_union_rows_already_in_existing_exact_named_family': int((joined.candidate_rule_union & joined.candidate_family_exact_named_physical_np_fias_point.fillna(False)).sum()),
            'proposed_union_population_already_in_existing_exact_named_family': int(joined.loc[joined.candidate_rule_union & joined.candidate_family_exact_named_physical_np_fias_point.fillna(False), 'population'].sum()),
            'proposed_union_rows_added_beyond_existing_family': int((joined.candidate_rule_union & ~joined.candidate_family_exact_named_physical_np_fias_point.fillna(False)).sum()),
            'proposed_union_population_added_beyond_existing_family': int(joined.loc[joined.candidate_rule_union & ~joined.candidate_family_exact_named_physical_np_fias_point.fillna(False), 'population'].sum()),
        },
        'hard_gate_counts': {
            c: {'failed_rows': int((~joined[c].fillna(False).astype(bool)).sum()), 'failed_population': int(joined.loc[~joined[c].fillna(False).astype(bool), 'population'].sum())}
            for c in ['gate_provider_named_physical_fias_point_core', 'gate_current_exact_code_unique', 'gate_exact_historical_named_okato_region_and_admin']
        },
        'proposal_gates': [
            'selected 2021 physical NP; population scope is nonaggregate',
            'DaData result has a level 4/6 FIAS object, exact selected name and full type (only ё/е and pgt/poselok alias normalization)',
            'valid WGS84 point inside broad Russia envelope; no prior hard coordinate conflict',
            'unique FIAS object and unique provider point within selected 2021 rows; secondary settlement ID does not contradict general FIAS ID',
            'PLUS either unique exact source/provider current OKTMO digits (same width, no padding), OR unique active historical OKATO row whose name/type/region and OKATO-code-derived administrative parent exactly match selected fields',
            'candidate-only coordinate claim; external FIAS binding and admission remain false',
        ],
        'known_context_limit': '2021 provider payload has no returned parent chain. Historical OKATO admin context is an exact join from the source code to the 2009 classifier parent code/name and selected census upper-admin label; no parent properties are invented for DaData.',
        'source_coordinate_and_fias_binding_separate': True,
        'artifacts': {
            str(candidate_path): {'rows': int(joined.candidate_rule_union.sum()), 'sha256': sha_file(candidate_path)},
            str(sample_path): {'rows': len(fixed_sample(joined)), 'sha256': sha_file(sample_path), 'sampling': 'SHA256(coord-rule-v1|source_record_id), first 12 per residual bucket × recorded-population band'},
        },
    }
    report_path = output / 'coordinate_rule_report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md = [
        '# 2021 physical settlement coordinate residual', '',
        'Candidate diagnostic only. No coordinate or external FIAS binding is admitted by this run.', '',
        f"Remaining: {report['remaining_rows']:,} selected physical settlements, {report['remaining_recorded_population']:,} recorded population. Accepted 2021 point uses subtracted: {report['accepted_2021_target_ids_subtracted']:,} target IDs.", '',
        '## Population weighted residual buckets', '',
        '| Primary bucket | Rows | Recorded population |', '|---|---:|---:|',
    ]
    md += [f"| {r['group']} | {r['rows']:,} | {r['population']:,} |" for r in report['residual_by_bucket']]
    md += ['', '## Proposed strong rule cohort', '',
        'The strict historical route requires a unique active historical OKATO row, exact selected locality name and type, exact region label, and exact OKATO-derived upper administrative parent. The provider must also return a unique level 4/6 FIAS settlement object and unique valid point with exact name/type; known coordinate conflicts and contradictory secondary IDs hold.', '',
        f"This yields {report['rule_totals']['proposed_historical_exact_named_okato_region_and_admin']['rows']:,} review candidates covering {report['rule_totals']['proposed_historical_exact_named_okato_region_and_admin']['population']:,} population. Of these, {report['rule_totals']['historical_same_region_homonyms_resolved_by_exact_code_and_admin']['rows']:,} rows ({report['rule_totals']['historical_same_region_homonyms_resolved_by_exact_code_and_admin']['population']:,} population) have a same-name/type historical regional homonym resolved by exact code and admin context.", '',
        f"Exact current source/provider OKTMO matches occur on {report['rule_totals']['exact_current_source_provider_oktmo_any_residual_row']['rows']:,} rows, but none pass the full named FIAS point core. The historical cohort is already inside the existing exact-name candidate family; added rows beyond that family: {report['relationship_to_existing_candidate_family']['proposed_union_rows_added_beyond_existing_family']:,}.", '',
        '## Review assets and limits', '',
        f"Fixed SHA256-stratified sample: {len(fixed_sample(joined)):,} rows in `fixed_stratified_sample.csv`. The candidate rows are in `coordinate_rule_candidates.parquet`; hashes and frozen input receipts are in `run_receipt.json`.", '',
        'The 2021 provider payload has no returned parent chain. The historical admin comparison uses a code-derived 2009 classifier parent and the selected census upper-admin field; it does not assert any DaData parent property. Coordinate source points and FIAS binding are separate claims. Historical row reuse still needs independent review.', '',
    ]
    md_path = output / 'coordinate_rule_report.md'
    md_path.write_text('\n'.join(md), encoding='utf-8')
    receipt_path = output / 'run_receipt.json'
    receipt = {'status': report['status'], 'report_sha256': sha_file(report_path), 'markdown_sha256': sha_file(md_path), 'candidate_sha256': sha_file(candidate_path), 'sample_sha256': sha_file(sample_path), 'input_sha256': {str(p): sha_file(p) for p in [screen_path, uses_path, geo_path, class_path]}}
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', choices=['v1', 'v2', 'v3', 'v4'], default='v1')
    p.add_argument('--screen', type=Path, default=SCREEN_DEFAULT)
    p.add_argument('--uses', type=Path, default=USES_DEFAULT)
    p.add_argument('--geo2011', type=Path, default=GEO2011_DEFAULT)
    p.add_argument('--classifier2009', type=Path, default=CLASS2009_DEFAULT)
    p.add_argument('--historical-context', type=Path, default=HISTORICAL_CONTEXT_DEFAULT)
    p.add_argument('--historical-context-receipt', type=Path, default=HISTORICAL_CONTEXT_RECEIPT_DEFAULT)
    p.add_argument('--v1-receipt', type=Path, default=V1_RECEIPT_DEFAULT)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.version in {'v2', 'v3', 'v4'}:
        output_default = {'v2': OUT_V2_DEFAULT, 'v3': OUT_V3_DEFAULT, 'v4': OUT_V4_DEFAULT}[args.version]
        out = build_v2(args.screen, args.uses, args.geo2011, args.classifier2009, args.historical_context,
                       args.historical_context_receipt, args.v1_receipt, args.output or output_default, args.version)
    else:
        out = build(args.screen, args.uses, args.geo2011, args.classifier2009, args.output or OUT_DEFAULT)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
