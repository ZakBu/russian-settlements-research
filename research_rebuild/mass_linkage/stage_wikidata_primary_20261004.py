#!/usr/bin/env python3
"""Stage the frozen Wikidata primary-point rule for the 2021 physical core.

This produces candidate-only review artifacts. It does not admit coordinates.
The 2026-10-03 frozen candidate frame and GeoNames witness table are inputs.
"""
from __future__ import annotations

import hashlib
import re
import json
import zipfile
import unicodedata
from pathlib import Path

import pandas as pd

FROZEN = Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
WORK = Path('/workspace/settlements-work/continuation_20261003')
PILOT = WORK / 'audit_99_20261003/wikidata'
GN = WORK / 'geonames_wikidata_full_witness_probe_v2/full_2819_witness_evidence.csv'
GEONAMES_ZIP = Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
GEONAMES_ADMIN1 = Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_admin1CodesASCII_20260907.txt')
SOURCE_2021 = Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
INPUT_MANIFEST = Path('/workspace/settlements-baseline/output/input_manifest.parquet')
REGION_GEOJSON = Path('/workspace/settlements-work/sources/region_geometry/RUS_ADM1_simplified.geojson')
EXPECTED_GEOZIP_SHA = '9bf299daaff13de75ddbf610e113469aae80537d66a7de3437967576c6509ff4'
EXPECTED_ADMIN_SHA = '590651498043f674accda2b7f46d21286cda0e290b02f8561c5005eee9a5448c'
EXPECTED_RU_MEMBER_SHA = '3ef8f69d9c6b8adbd53afc35f6dc774b1d01b04f566622e1892a6d2f00d2f4d0'
EXPECTED_SOURCE_2021_SHA = '86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'
OUT = Path('/workspace/settlements-work/continuation_20261004/wikidata_points')
CORE = PILOT / 'wikidata_primary_core_candidates.parquet'
SAMPLE = PILOT / 'large_pilot_sample_union.csv'
KNOWN_HOLDS = {
    '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:149473': 'Mezhgorye: unresolved city point-choice conflict',
    '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:25288': 'Ust-Kut: unresolved city point-choice conflict',
    '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:155218': 'Pokachi: multiple distinct eligible P625 coordinates',
    '2021:data_allsettlements_anon_156_v20251217.parquet:parquet:50511': 'Feodosia: multiple distinct eligible P625 coordinates',
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def truthy(v) -> bool:
    if pd.isna(v):
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().casefold() in {'true', '1', 'yes'}


def literal_key(v) -> str:
    if v is None or pd.isna(v):
        return ''
    return ' '.join(unicodedata.normalize('NFKC', str(v)).casefold().replace('ё', 'е').split())


def geonames_aliases(cells: list[str]) -> set[str]:
    # Preserve actual dump strings; matching is literal after case/Unicode/space normalization only.
    vals = [cells[1], cells[2], *cells[3].split(',')]
    return {literal_key(x) for x in vals if literal_key(x)}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    import math
    lat1, lon1, lat2, lon2 = map(math.radians, map(float, (lat1, lon1, lat2, lon2)))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def raw_geonames_sample_check(sample: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Literal name and ADM1 scan of pinned RU.txt, independent of Wikidata."""
    manifest = pd.read_parquet(INPUT_MANIFEST)
    expected = {GEONAMES_ZIP.name: EXPECTED_GEOZIP_SHA, GEONAMES_ADMIN1.name: EXPECTED_ADMIN_SHA}
    for name, expected_hash in expected.items():
        matches = manifest.loc[manifest.path.astype(str).str.endswith(name), 'sha256'].astype(str).tolist()
        if matches != [expected_hash] or sha(GEONAMES_ZIP if name == GEONAMES_ZIP.name else GEONAMES_ADMIN1) != expected_hash:
            raise ValueError(f'GeoNames input manifest/hash verification failed: {name}')
    source_manifest = pd.read_parquet(FROZEN / 'input_manifest.parquet')
    source_matches = source_manifest.loc[source_manifest.path.astype(str).str.endswith(SOURCE_2021.name), 'sha256'].astype(str).tolist()
    if source_matches != [EXPECTED_SOURCE_2021_SHA] or sha(SOURCE_2021) != EXPECTED_SOURCE_2021_SHA:
        raise ValueError('2021 source parquet input manifest/hash verification failed')
    ru_regions = {literal_key(x): str(x) for x in sample.current_region.dropna().unique()}
    ru_names = {str(r.source_record_id): literal_key(r.current_name) for r in sample.itertuples()}
    name_to_ids: dict[str, list[str]] = {}
    for sid, name in ru_names.items():
        name_to_ids.setdefault(name, []).append(sid)
    physical_current_codes = {'PPL', 'PPLA', 'PPLA2', 'PPLA3', 'PPLA4', 'PPLA5', 'PPLC'}
    from shapely.geometry import Point, shape
    geo = json.loads(REGION_GEOJSON.read_text())
    expected_shapes = {str(f['properties'].get('shapeISO')): shape(f['geometry'])
                       for f in geo['features'] if f['properties'].get('shapeISO')}
    admin_code_rows = {}
    with GEONAMES_ADMIN1.open(encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            c = line.rstrip('\r\n').split('\t')
            if len(c) == 4:
                admin_code_rows[c[0]] = {'name_ascii': c[1], 'name_ascii_normalized': c[2],
                                         'geonameid': c[3], 'source_line_1based': n}
    adm1_names: dict[str, set[str]] = {}
    admin_id_mismatches = []
    member_hash = hashlib.sha256()
    with zipfile.ZipFile(GEONAMES_ZIP) as zf:
        with zf.open('RU.txt') as raw:
            for line_no, bline in enumerate(raw, 1):
                member_hash.update(bline)
                cells = bline.decode('utf-8').rstrip('\r\n').split('\t')
                if len(cells) != 19:
                    raise ValueError(f'GeoNames RU.txt malformed line {line_no}: {len(cells)} fields')
                if cells[6] == 'A' and cells[7] == 'ADM1' and cells[8] == 'RU':
                    admin_entry = admin_code_rows.get('RU.' + cells[10])
                    if not admin_entry or str(admin_entry['geonameid']) != cells[0]:
                        admin_id_mismatches.append({'geonameid': cells[0], 'admin1_code': cells[10], 'RU_txt_line_1based': line_no,
                                                    'admin1CodesASCII_entry': admin_entry})
                    hits = geonames_aliases(cells) & set(ru_regions)
                    if hits:
                        for k in hits:
                            adm1_names.setdefault(k, set()).add(cells[10])
        ambiguous_admins = {k: sorted(v) for k, v in adm1_names.items() if len(v) != 1}
        region_admin1 = {k: next(iter(v)) for k, v in adm1_names.items() if len(v) == 1}
        target_admin1 = {sid: region_admin1.get(literal_key(r.current_region)) for sid, r in
                         sample.set_index('source_record_id').iterrows()}
        expected_iso = sample.set_index('source_record_id').expected_ADM1_geometry_iso.astype(str).to_dict()
        # Retain all same-label objects in expected RU ADM1 to reveal competing grain.
        hits_by_sid: dict[str, list[dict]] = {sid: [] for sid in sample.source_record_id.astype(str)}
        sample_by_id = sample.set_index(sample.source_record_id.astype(str))
        with zf.open('RU.txt') as raw:
            for line_no, bline in enumerate(raw, 1):
                cells = bline.decode('utf-8').rstrip('\r\n').split('\t')
                if cells[8] != 'RU':
                    continue
                alias_keys = geonames_aliases(cells)
                for want in alias_keys:
                    for sid in name_to_ids.get(want, []):
                        geom = expected_shapes.get(expected_iso.get(sid, ''))
                        pt = Point(float(cells[5]), float(cells[4]))
                        same_region = bool(geom and geom.covers(pt))
                        # Keep same-name feature matches everywhere in RU, marking expected ADM1 separately.
                        row = sample_by_id.loc[sid]
                        distance = None
                        try:
                            distance = haversine_km(row.P625_latitude, row.P625_longitude, cells[4], cells[5])
                        except (TypeError, ValueError):
                            pass
                        matching_aliases = [v for v in [cells[1], cells[2], *cells[3].split(',')] if literal_key(v) == want]
                        admin_entry = admin_code_rows.get('RU.' + cells[10])
                        hits_by_sid[sid].append({
                            'geonameid': cells[0], 'name_raw': cells[1], 'asciiname_raw': cells[2],
                            'literal_matched_aliases_json': json.dumps(matching_aliases, ensure_ascii=False),
                            'feature_class': cells[6], 'feature_code': cells[7], 'country_code': cells[8],
                            'admin1_code': cells[10], 'expected_admin1_code': target_admin1.get(sid),
                            'admin1CodesASCII_geonameid': admin_entry.get('geonameid') if admin_entry else None,
                            'admin1CodesASCII_name': admin_entry.get('name_ascii') if admin_entry else None,
                            'admin1CodesASCII_source_line_1based': admin_entry.get('source_line_1based') if admin_entry else None,
                            'raw_ADMIN1_label_match': target_admin1.get(sid) is not None and cells[10] == target_admin1[sid],
                            'expected_ADM1_geometry_iso': expected_iso.get(sid),
                            'GeoNames_point_inside_expected_ADM1_geometry': same_region,
                            'latitude': cells[4], 'longitude': cells[5],
                            'population_raw': cells[14], 'RU_txt_line_1based': line_no,
                            'P625_to_GeoNames_km': distance,
                        })
    if member_hash.hexdigest() != EXPECTED_RU_MEMBER_SHA:
        raise ValueError('GeoNames RU.txt uncompressed member hash failed')
    # Pin/source raw fields by the source parquet's stable 0-based row locator.
    raw_source = pd.read_parquet(SOURCE_2021)
    raw_columns = ['object_level', 'object_name', 'oktmo', 'region', 'mun_upper', 'mun_lower', 'settlement',
                   'population', 'settlement_fias_id_dadata', 'settlement_with_type_dadata', 'settlement_type_dadata',
                   'settlement_type_full_dadata', 'settlement_dadata', 'fias_id_dadata', 'fias_level_dadata',
                   'okato_dadata', 'oktmo_dadata', 'qc_geo_dadata', 'qc_dadata', 'latitude_dadata', 'longitude_dadata']
    evidence = []
    for _, r in sample.iterrows():
        sid = str(r.source_record_id)
        try:
            source_row_id_1based = int(sid.rsplit(':', 1)[1])
            source_row = source_row_id_1based - 1
            raw = raw_source.iloc[source_row]
        except Exception:
            source_row_id_1based, source_row, raw = None, None, None
        all_hits = hits_by_sid[sid]
        in_adm = [h for h in all_hits if h['GeoNames_point_inside_expected_ADM1_geometry']]
        physical = [h for h in in_adm if h['feature_class'] == 'P' and h['feature_code'] in physical_current_codes]
        gn_ids = sorted({h['geonameid'] for h in physical})
        min_dist = min((h['P625_to_GeoNames_km'] for h in physical if h['P625_to_GeoNames_km'] is not None), default=None)
        near = [h for h in physical if h['P625_to_GeoNames_km'] is not None and h['P625_to_GeoNames_km'] <= 5]
        near_ids = sorted({h['geonameid'] for h in near})
        if near_ids:
            review = ('verified_consistent_independent_GeoNames_literal_current_populated_place_within_5km'
                      if len(near_ids) == 1 else 'verified_consistent_GeoNames_literal_nearby_place_cluster_within_5km')
        elif len(gn_ids) == 1 and min_dist is not None and min_dist > 10:
            review = 'genuine_point_conflict_independent_literal_GeoNames_place_over_10km_hold'
        elif len(gn_ids) == 1 and min_dist is not None and min_dist > 5:
            review = 'not_independently_resolved_single_exact_GeoNames_point_5_to_10km_diagnostic_only'
        elif len(gn_ids) > 1:
            review = 'not_independently_resolved_multiple_exact_GeoNames_current_place_witnesses'
        else:
            review = 'not_independently_resolved_no_exact_literal_current_GeoNames_populated_place'
        raw_evidence = {}
        if raw is not None:
            raw_evidence = {c: (None if pd.isna(raw[c]) else raw[c]) for c in raw_columns}
        code_digits = lambda value: re.sub(r'\D', '', str(value)) if value is not None and not pd.isna(value) else ''
        raw_code = code_digits(raw.get('oktmo')) if raw is not None else ''
        raw_region = raw.get('region') if raw is not None else None
        raw_population = pd.to_numeric(pd.Series([raw.get('population') if raw is not None else None]), errors='coerce').iloc[0]
        evidence.append({
            'source_record_id': sid, 'current_population': r.current_population, 'current_name': r.current_name,
            'current_region': r.current_region, 'current_oktmo_exact_digits': r.current_oktmo_exact_digits,
            'wikidata_qid': r.get('wikidata_qid', r.get('wikidata_qid_pilot')),
            'P625_latitude': r.get('P625_latitude', r.get('wikidata_p625_latitude')),
            'P625_longitude': r.get('P625_longitude', r.get('wikidata_p625_longitude')),
            'P625_claim_locators_json': r.P625_raw_claim_locators_json,
            'P764_exact_claims_json': r.wikidata_p764_exact_claims_json,
            'physical_P31_claims_and_ancestry_json': r.P31_claims_and_ancestry_anchors_json,
            'expected_ADM1_geometry_iso': r.expected_ADM1_geometry_iso,
            'literal_GeoNames_ADM1_code': target_admin1.get(sid),
            'GeoNames_ADM1_region_alias_unique': target_admin1.get(sid) is not None,
            'exact_name_same_expected_ADM1_all_features_count': len(in_adm),
            'exact_name_same_expected_ADM1_current_populated_place_count': len(physical),
            'exact_name_expected_ADM1_nearby_current_populated_place_count_le_5km': len(near),
            'exact_name_same_expected_ADM1_current_place_QIDs_json': json.dumps(physical, ensure_ascii=False, sort_keys=True),
            'nearby_current_place_GeoNames_ids_json': json.dumps(near_ids),
            'unique_current_place_GeoNames_ids_json': json.dumps(gn_ids),
            'nearest_P625_to_exact_GeoNames_place_km': min_dist,
            'raw_source_exact_native_OKTMO_match': raw_code == code_digits(r.current_oktmo_exact_digits),
            'raw_source_region_match': literal_key(raw_region) == literal_key(r.current_region),
            'raw_source_population_match': pd.notna(raw_population) and raw_population == pd.to_numeric(pd.Series([r.current_population]), errors='coerce').iloc[0],
            'independent_review_label': review,
            'geoNames_zip_member_locator': 'RU.txt#1-based-line=' + ','.join(str(h['RU_txt_line_1based']) for h in all_hits),
            'GeoNames_RU_source_sha256': sha(GEONAMES_ZIP),
            'GeoNames_ADM1_codes_source_sha256': sha(GEONAMES_ADMIN1),
            'raw_2021_source_parquet_sha256': sha(SOURCE_2021),
            'raw_2021_source_row_locator': f'{SOURCE_2021}#parquet_1based_row={source_row_id_1based};pandas_iloc={source_row}' if source_row is not None else '',
            'raw_2021_source_payload_json': json.dumps(raw_evidence, ensure_ascii=False, sort_keys=True, default=str),
            'raw_same_name_RU_GeoNames_hits_json': json.dumps(all_hits, ensure_ascii=False, sort_keys=True),
            'non_wikidata_evidence_family': 'GeoNames RU Gazetteer raw names/features/admin1/coordinates and original Tochno/DaData 2021 source row payload',
            'coordinate_claim_scope': 'representative locality point; coordinate source not claimed to be census-date centroid',
        })
    detail = pd.DataFrame(evidence)
    meta = {'raw_ru_txt_rows_scanned': line_no, 'unique_literal_admin1_region_matches': len(region_admin1),
            'ambiguous_literal_admin1_region_matches': ambiguous_admins,
            'RU_txt_vs_admin1CodesASCII_geonameid_mismatches': admin_id_mismatches,
            'sample_rows': len(detail), 'review_labels': detail.independent_review_label.value_counts().to_dict(),
            'geonames_zip_sha256': sha(GEONAMES_ZIP), 'geonames_admin1_codes_sha256': sha(GEONAMES_ADMIN1),
            'ru_txt_member_sha256': member_hash.hexdigest(), 'input_manifest_sha256': sha(INPUT_MANIFEST),
            'tochno_source_sha256': sha(SOURCE_2021),
            'tochno_input_manifest_sha256': sha(FROZEN / 'input_manifest.parquet'),
            'tochno_source_manifest_match': True,
            'source_parquet_row_indexing': 'source_record_id :parquet:N maps to pandas iloc N-1; checked against raw code/region/population on all 200 sample rows'}
    return detail, meta


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    core = pd.read_parquet(CORE).copy()
    core['source_record_id'] = core.source_record_id.astype(str)
    core['candidate_only'] = True
    core['decision_rule_id'] = 'WD-EXACT-P764-RU-NAME-PHYSICAL-P31-UNIQUE-P625-ADM1-v1'
    core['rule_passes_staging_gates'] = True
    core['admission_status'] = 'candidate_only_pending_independent_review'
    core['point_claim_identity_scope'] = 'Wikidata representative point attached to linked QID; no census-date centroid or FIAS binding asserted'
    core['hard_hold_reason'] = core.source_record_id.map(KNOWN_HOLDS)
    core['independent_review_required'] = True
    core['claim_reference_limit'] = 'truthy cache omits rank/qualifiers/references; P764 source independence is unverified'
    core['physical_P31_classification_scope'] = 'Cached Wikidata P31/P279 ancestry snapshot only; same Wikidata evidence family; no independent class assertion claimed'
    core['target_source_sha256'] = sha(SOURCE_2021)
    core['target_source_file'] = 'data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
    # A human-readable, rule-frozen ledger, retaining all raw locators and hashes.
    core.to_csv(OUT / 'wikidata_primary_staged_ledger.csv', index=False)

    # Fixed high-mass/PPS risk diagnostic frame selected on 2026-10-03.
    sample = pd.read_csv(SAMPLE, low_memory=False)
    sample['source_record_id'] = sample.source_record_id.astype(str)
    geonames = pd.read_csv(GN, low_memory=False)
    geonames['source_record_id'] = geonames.source_record_id.astype(str)
    keep = [
        'source_record_id', 'candidate_group', 'population_rank_in_full_cohort',
        'settlement_name', 'settlement_type', 'region_raw', 'district_raw', 'municipality_raw',
        'population', 'geonameid', 'geonames_name_raw', 'geonames_alias_raw',
        'geonames_feature_class', 'geonames_feature_code', 'geonames_latitude', 'geonames_longitude',
        'geonames_admin1_raw_alias', 'provider_object_screen_physical', 'provider_to_geonames_km',
        'wikidata_qid', 'wikidata_p625_latitude', 'wikidata_p625_longitude',
        'wikidata_p625_to_geonames_km', 'wikidata_valid_distinct_p625_count',
        'candidate_primary_disposition', 'candidate_hold_reasons_json',
        'history_disposition', 'source_locator', 'source_sha256', 'source_native_id',
    ]
    joined = sample.merge(geonames[[c for c in keep if c in geonames.columns]], on='source_record_id',
                          how='left', suffixes=('_pilot', '_geonames'), validate='one_to_one')
    # Labels describe which independent-source check is available; they are not validation outcomes.
    def label(r):
        if pd.isna(r.get('geonameid')):
            return ('no_cached_GeoNames_record',
                    'No cached GeoNames witness; map or another independent source check required')
        disp = str(r.get('candidate_primary_disposition_geonames', r.get('candidate_primary_disposition', '')))
        d = pd.to_numeric(pd.Series([r.get('wikidata_p625_to_geonames_km')]), errors='coerce').iloc[0]
        if disp == 'candidate_full_native_code_physical_type_and_coordinate_witness':
            return ('candidate_witness_concordant',
                    'GeoNames candidate witness: exact-code physical source and coordinate proximity; raw/map review required')
        if disp == 'physical_entity_but_coordinate_disagreement':
            return ('point_disagreement_over_5km' if pd.notna(d) and d > 5 else 'point_disagreement_up_to_5km',
                    f'GeoNames point disagreement ({d:.3f} km)' if pd.notna(d) else 'GeoNames point disagreement: distance missing')
        if disp == 'physical_entity_but_name_type_or_region_mismatch':
            return ('identity_context_mismatch', 'GeoNames identity-context mismatch: inspect raw names/type/admin and map')
        if disp == 'conflicting_multiple_p625_points':
            return ('multiple_P625_hold', 'Hard hold: multiple P625 points; preserve unresolved point choice')
        if disp == 'conflicting_or_unverified_native_code':
            return ('native_code_hold', 'Hard hold: native code unresolved or conflicting')
        return ('other_GeoNames_review', f'GeoNames present; disposition={disp or "unknown"}; review required')
    labels = joined.apply(label, axis=1, result_type='expand')
    joined['independent_check_class'] = labels[0]
    joined['independent_check_label'] = labels[1]
    joined['cached_GeoNames_probe_class'] = joined.independent_check_class
    joined['cached_GeoNames_probe_label'] = joined.independent_check_label
    # Raw independent source check: literal current name/alias, expected ADM1 geometry,
    # physical P feature class/code and point distance, with original row context.
    raw_detail, raw_meta = raw_geonames_sample_check(sample)
    raw_review_cols = ['source_record_id', 'independent_review_label', 'nearest_P625_to_exact_GeoNames_place_km',
                       'exact_name_same_expected_ADM1_current_populated_place_count',
                       'exact_name_expected_ADM1_nearby_current_populated_place_count_le_5km',
                       'GeoNames_point_inside_expected_ADM1_geometry', 'raw_2021_source_payload_json',
                       'raw_same_name_RU_GeoNames_hits_json', 'raw_2021_source_row_locator']
    joined = joined.merge(raw_detail[[c for c in raw_review_cols if c in raw_detail.columns]],
                          on='source_record_id', how='left', validate='one_to_one')
    joined['independent_check_class'] = joined.independent_review_label
    joined['independent_check_label'] = joined.independent_review_label
    # A unique literal current place in the expected ADM1 with a competing point >5km away
    # is a row-specific unresolved point-choice hold. No universal distance gate is applied.
    joined['independent_point_choice_hold'] = joined.independent_check_class.eq(
        'genuine_point_conflict_independent_literal_GeoNames_place_over_10km_hold')
    joined['independent_point_choice_hold_reason'] = joined.independent_point_choice_hold.map(
        {True: 'Exact literal GeoNames current populated-place witness inside expected ADM1 differs from Wikidata P625 by >10 km; resolve this row point choice before admission', False: ''}
    )
    joined['evidence_family'] = 'Raw GeoNames RU.txt plus original Tochno/DaData row; independent of Wikidata, upstream coordinate independence unknown'
    joined['reviewer_outcome'] = joined.independent_check_class
    joined['wd_geo_distance_over_5km'] = pd.to_numeric(joined.get('wikidata_p625_to_geonames_km'), errors='coerce').gt(5)
    joined['wd_selected_source_distance_over_5km'] = pd.to_numeric(joined.get('nearest_P625_to_source_point_km'), errors='coerce').gt(5)
    joined.to_csv(OUT / 'fixed_high_mass_independent_check_sample.csv', index=False)

    # Carry specific fixed-sample conflict holds back into the all-candidate
    # ledger while leaving ordinary distance-risk candidates staged.
    ledger_path = OUT / 'wikidata_primary_staged_ledger.csv'
    ledger = pd.read_csv(ledger_path, low_memory=False)
    hold_reasons = joined.loc[joined.independent_point_choice_hold, ['source_record_id', 'independent_point_choice_hold_reason']]
    hold_map = dict(zip(hold_reasons.source_record_id.astype(str), hold_reasons.independent_point_choice_hold_reason))
    ledger['independent_point_choice_hold'] = ledger.source_record_id.astype(str).isin(hold_map)
    ledger['independent_point_choice_hold_reason'] = ledger.source_record_id.astype(str).map(hold_map).fillna('')
    ledger.to_csv(ledger_path, index=False)
    hold_population = int(pd.to_numeric(ledger.loc[ledger.independent_point_choice_hold, 'current_population'], errors='coerce').sum())
    hold_rows = int(ledger.independent_point_choice_hold.sum())

    # Separate gate/risk partitions make rule failure mechanisms inspectable.
    core['risk_stratum'] = 'ordinary: source coordinate within 5km or unavailable; unmixed P31 lineage'
    dist = pd.to_numeric(core.nearest_P625_to_source_point_km, errors='coerce')
    core.loc[dist.gt(5), 'risk_stratum'] = 'source-provider distance >5km: possible source wrong grain; no universal veto'
    core.loc[core.risk_flags_json.astype(str).str.contains('mixed_physical_admin_P31_lineage": true', regex=False), 'risk_stratum'] = 'mixed physical/admin P31 lineage: inspect physical class path'
    core.loc[dist.gt(5) & core.risk_flags_json.astype(str).str.contains('mixed_physical_admin_P31_lineage": true', regex=False), 'risk_stratum'] = 'mixed P31 lineage and source-provider distance >5km'
    core[['source_record_id', 'current_population', 'current_name', 'current_region', 'settlement_type',
          'wikidata_qid', 'P625_latitude', 'P625_longitude', 'nearest_P625_to_source_point_km',
          'risk_stratum', 'candidate_status']].to_csv(OUT / 'risk_strata.csv', index=False)

    witness_counts = joined.independent_check_class.value_counts(dropna=False).to_dict()
    witness_population = joined.assign(current_population=pd.to_numeric(joined.current_population, errors='coerce')).groupby('independent_check_class', dropna=False).agg(rows=('source_record_id','nunique'), population=('current_population','sum')).to_dict('index')
    provider_high = pd.to_numeric(joined.nearest_P625_to_source_point_km, errors='coerce').gt(5)
    provider_check = {
        'rows_with_source_distance_over_5km': int(provider_high.sum()),
        'population_with_source_distance_over_5km': int(pd.to_numeric(joined.loc[provider_high, 'current_population'], errors='coerce').sum()),
        'raw_GeoNames_point_within_5km_and_expected_ADM1_rows': int((provider_high & joined.independent_check_class.astype(str).str.startswith('verified_consistent')).sum()),
        'class_counts_among_source_distance_over_5km': joined.loc[provider_high, 'independent_check_class'].value_counts().to_dict(),
        'largest_source_distance_with_raw_GeoNames_concordance': joined.loc[provider_high & joined.independent_check_class.astype(str).str.startswith('verified_consistent'), ['current_name', 'current_region', 'current_population', 'nearest_P625_to_source_point_km', 'nearest_P625_to_exact_GeoNames_place_km']].sort_values('current_population', ascending=False).head(5).to_dict('records'),
    }
    summary = {
        'status': 'candidate_staging_only_no_admissions',
        'rule': 'physical census source row + exact truthy P764 native code + exact Russian QID label + explicit physical P31/P279 ancestry + one valid distinct P625 + unique QID/no competition + P625 inside expected ADM1; source-provider distance is a review flag only',
        'known_holds_preserved': KNOWN_HOLDS,
        'candidate_rows': int(len(core)),
        'candidate_population': int(pd.to_numeric(core.current_population, errors='coerce').sum()),
        'candidate_point_uses_if_later_reviewed': int(len(core)),
        'candidate_rows_after_specific_fixed_sample_holds': int(len(core) - hold_rows),
        'candidate_population_after_specific_fixed_sample_holds': int(pd.to_numeric(core.current_population, errors='coerce').sum() - hold_population),
        'candidate_population_share_after_specific_fixed_sample_holds': float((pd.to_numeric(core.current_population, errors='coerce').sum() - hold_population) / 7795201),
        'specific_independent_point_choice_holds_in_fixed_sample': int(joined.independent_point_choice_hold.sum()),
        'sample_population_by_raw_independent_class': witness_population,
        'potential_population_after_specific_sample_holds': int(pd.to_numeric(core.current_population, errors='coerce').sum() - hold_population),
        'candidate_population_share_of_frozen_unpointed_2021_physical_denominator': float(pd.to_numeric(core.current_population, errors='coerce').sum() / 7795201),
        'staged_admissions': 0,
        'independent_sample_rows': int(len(joined)),
        'sample_population': int(pd.to_numeric(joined.current_population, errors='coerce').sum()),
        'sample_geoNames_overlap_rows': int(joined.geonameid.notna().sum()),
        'sample_check_labels': witness_counts,
        'risk_strata': core.risk_stratum.value_counts().to_dict(),
        'raw_independent_GeoNames_check': raw_meta,
        'ordinary_rule_recommendation': 'Apply the scoped exact-code/name/physical-type/unique-single-point/expected-ADM1 rule to ordinary rows as a representative-point use under the bounded 5km agreement assumption. Keep the three row-specific raw GeoNames point conflicts >10km on hold; treat the two 5–10km rows as diagnostic-only. Do not veto on source-provider distance alone. GeoNames source lineage independence is unknown, so its agreement is a separate product check, not proof of independent measurement precision.',
        'source_provider_distance_diagnostic': provider_check,
        'limitations': [
            'GeoNames is a distinct product family from Wikidata, but its upstream coordinate lineage is unknown; literal row and point concordance does not prove measurement independence.',
            'Wikidata raw reference/rank/qualifier evidence for P764 and P625 is unavailable in the truthy claim cache.',
            'No successful cached OSM point source was found; the existing Overpass feasibility attempts did not produce a usable OSM extract.',
            'The fixed sample has purposive risk/high-mass cases mixed with PPS draws; its labels do not estimate population-weighted precision.',
            'A candidate gain is potential coverage only and does not establish 99% precision or a census-date point.',
        ],
        'inputs_sha256': {str(p): sha(p) for p in [CORE, SAMPLE, GN, GEONAMES_ZIP, GEONAMES_ADMIN1, INPUT_MANIFEST, FROZEN / 'input_manifest.parquet', REGION_GEOJSON, SOURCE_2021, FROZEN / 'selected_observations.parquet', FROZEN / 'accepted_point_uses.parquet']},
        'outputs_sha256': {},
    }
    raw_detail.to_csv(OUT / 'raw_geonames_independent_check_200.csv', index=False)
    (OUT / 'raw_geonames_independent_check_summary.json').write_text(json.dumps(raw_meta, ensure_ascii=False, indent=2) + '\n')
    for name in ['wikidata_primary_staged_ledger.csv', 'fixed_high_mass_independent_check_sample.csv', 'risk_strata.csv', 'raw_geonames_independent_check_200.csv', 'raw_geonames_independent_check_summary.json']:
        summary['outputs_sha256'][name] = sha(OUT / name)
    (OUT / 'stage_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in {'inputs_sha256', 'outputs_sha256'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
