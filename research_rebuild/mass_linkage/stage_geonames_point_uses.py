#!/usr/bin/env python3
"""Stage the independently reviewed conditional 2021 GeoNames point cohort.

This creates pending point-use rows only. It does not admit coordinates, bind a
GeoNames identifier to a census/FIAS identifier, add identity edges, or
propagate points to earlier years.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from .apply_coordinate_extensions import base_use


ROOT = Path('/workspace')
COHORT = ROOT / 'settlements-work/continuation_20261003/geonames_named_point_rule_review_v1/conditional_point_use_candidates.parquet'
REVIEW = ROOT / 'settlements-work/continuation_20261003/geonames_named_point_rule_review_v1/review.json'
REVIEW_RECEIPT = ROOT / 'settlements-work/continuation_20261003/geonames_named_point_rule_review_v1/receipt.json'
BASE_POINTS = ROOT / 'settlements-work/continuation_20261003/accepted_after_podlipkovsky_hold_v1/accepted_point_uses.parquet'
GEONAMES_ZIP = ROOT / 'settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip'
RAW_MEMBER = 'RU.txt'

RULE = 'conditional_named_geonames_representative_point_v1'
PROVENANCE = 'GeoNames RU named-place source point; current snapshot coordinates, measurement date unknown'


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _num(value: Any, name: str) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid raw GeoNames {name}: {value!r}') from exc
    if not math.isfinite(number):
        raise ValueError(f'Non-finite raw GeoNames {name}: {value!r}')
    return number


def _canonical_locator(line_number: int, geonameid: str) -> str:
    return f'RU.txt:line={line_number};geonameid={geonameid}'


def _raw_membership_check(cohort: pd.DataFrame, zip_path: Path, expected_member_sha: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Read the complete cached member once and validate every candidate line."""
    if sha256(zip_path) == '':  # pragma: no cover - sha256 always returns text
        raise ValueError('Unable to hash GeoNames zip')
    by_line: dict[int, dict[str, Any]] = {}
    for row in cohort.itertuples(index=False):
        locator = str(row.geonames_record_locator)
        prefix = 'RU.txt:'
        if not locator.startswith(prefix):
            raise ValueError(f'Unexpected GeoNames locator: {locator}')
        line_number = int(locator[len(prefix):])
        if line_number <= 0 or line_number in by_line:
            raise ValueError(f'Duplicate or invalid RU.txt line: {line_number}')
        if int(row.source_line_1based) != line_number:
            raise ValueError(f'Candidate line/locator disagreement: {row.source_record_id}')
        by_line[line_number] = row._asdict()

    found: dict[str, dict[str, Any]] = {}
    member_digest = hashlib.sha256()
    member_rows = 0
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if names.count(RAW_MEMBER) != 1:
            raise ValueError(f'Expected exactly one {RAW_MEMBER} member; got {names.count(RAW_MEMBER)}')
        with archive.open(RAW_MEMBER, 'r') as stream:
            for line_number, raw_line in enumerate(stream, 1):
                member_rows = line_number
                member_digest.update(raw_line)
                candidate = by_line.get(line_number)
                if candidate is None:
                    continue
                try:
                    text = raw_line.decode('utf-8').rstrip('\r\n')
                except UnicodeDecodeError as exc:
                    raise ValueError(f'Invalid UTF-8 at {RAW_MEMBER}:{line_number}') from exc
                fields = text.split('\t')
                if len(fields) != 19:
                    raise ValueError(f'Unexpected GeoNames row width at {RAW_MEMBER}:{line_number}: {len(fields)}')
                (geonameid, name, ascii_name, alternates, lat_raw, lon_raw, feature_class,
                 feature_code, country_code, cc2, admin1, admin2, admin3, admin4,
                 population, elevation, dem, timezone, modified) = fields
                expected_id = str(candidate['geonameid'])
                alias = str(candidate['geonames_alias_raw'])
                comparisons = {
                    'geonameid': (geonameid, expected_id),
                    'name': (name, str(candidate['geonames_name_raw'])),
                    'latitude': (lat_raw, str(candidate['geonames_latitude'])),
                    'longitude': (lon_raw, str(candidate['geonames_longitude'])),
                    'feature_class': (feature_class, str(candidate['feature_class'])),
                    'feature_code': (feature_code, str(candidate['feature_code'])),
                    'country_code': (country_code, str(candidate['country_code'])),
                    'admin1': (admin1, str(candidate['admin1'])),
                    'admin2': (admin2, str(candidate['admin2'])),
                    'modification_date': (modified, str(candidate['modification_date'])),
                }
                for field, (actual, expected) in comparisons.items():
                    if actual != expected:
                        raise ValueError(f'Raw GeoNames {field} mismatch at {RAW_MEMBER}:{line_number}: {actual!r} != {expected!r}')
                if alias not in alternates.split(','):
                    raise ValueError(f'Candidate alias is not a literal RU.txt alternate name at {RAW_MEMBER}:{line_number}: {alias!r}')
                if feature_class != 'P' or not feature_code.startswith('PPL') or country_code != 'RU':
                    raise ValueError(f'Candidate is outside the reviewed Russian physical PPL family at {RAW_MEMBER}:{line_number}')
                latitude, longitude = _num(lat_raw, 'latitude'), _num(lon_raw, 'longitude')
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError(f'Raw GeoNames coordinates outside WGS84 at {RAW_MEMBER}:{line_number}')
                if geonameid in found:
                    raise ValueError(f'Duplicate GeoNames ID among candidate lines: {geonameid}')
                found[geonameid] = {
                    'source_line_1based': line_number,
                    'geonameid': geonameid,
                    'name': name,
                    'ascii_name': ascii_name,
                    'alternatenames': alternates,
                    'latitude_raw': lat_raw,
                    'longitude_raw': lon_raw,
                    'feature_class': feature_class,
                    'feature_code': feature_code,
                    'country_code': country_code,
                    'admin1': admin1,
                    'admin2': admin2,
                    'modification_date': modified,
                    'literal_alias_present': True,
                    'raw_member_line_sha256': hashlib.sha256(raw_line).hexdigest(),
                    'raw_member_line': text,
                }
    actual_member_sha = member_digest.hexdigest()
    if actual_member_sha != expected_member_sha:
        raise ValueError(f'RU.txt member SHA mismatch: {actual_member_sha}')
    if member_rows != 412729:
        raise ValueError(f'Unexpected RU.txt row count: {member_rows}')
    if len(found) != len(cohort):
        missing = sorted(set(cohort.geonameid.astype(str)) - set(found))
        raise ValueError(f'Not all candidate source rows were reopened; missing IDs: {missing[:10]}')
    return found, {'member_sha256': actual_member_sha, 'member_rows': member_rows,
                   'candidate_lines_reopened': len(found)}


def stage(output: Path, candidates: Path = COHORT, review_path: Path = REVIEW,
          review_receipt_path: Path = REVIEW_RECEIPT, base_points_path: Path = BASE_POINTS,
          geonames_zip_path: Path = GEONAMES_ZIP) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError('New immutable output directory required')
    for path in (candidates, review_path, review_receipt_path, base_points_path, geonames_zip_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    review = json.loads(review_path.read_text(encoding='utf-8'))
    review_receipt = json.loads(review_receipt_path.read_text(encoding='utf-8'))
    if review.get('verdict') != 'CONDITIONAL_2021_POINT_USE_CANDIDATES_FOR_INDEPENDENT_REVIEW; NO_ADMISSION':
        raise ValueError('Frozen conditional candidate-only review status changed')
    if review_receipt.get('status') != 'independent_candidate_only_review_no_admissions':
        raise ValueError('Frozen review receipt status changed')
    if sha256(review_path) != review_receipt.get('review_sha256'):
        raise ValueError('Frozen review JSON hash differs from receipt')
    if sha256(candidates) != review_receipt.get('outputs', {}).get('conditional_point_use_candidates.parquet'):
        raise ValueError('Conditional candidate table differs from the frozen review receipt')
    if len(pd.read_parquet(candidates, columns=['source_record_id'])) != 9044:
        raise ValueError('Conditional candidate row count changed')

    input_paths = {str(path): sha256(path) for path in
                   (candidates, review_path, review_receipt_path, base_points_path, geonames_zip_path)}
    for path, expected in review.get('inputs_sha256', {}).items():
        if Path(path).is_file() and sha256(path) != expected:
            raise ValueError(f'Frozen review input changed: {path}')
    expected_zip_sha = review['inputs_sha256'][str(geonames_zip_path)]
    if input_paths[str(geonames_zip_path)] != expected_zip_sha:
        raise ValueError('GeoNames source zip SHA differs from the independent review')
    expected_base_sha = 'c65441e973c59bd6421327624b4a1b587f7860581ed28083d4259719bf53a3b9'
    if input_paths[str(base_points_path)] != expected_base_sha:
        raise ValueError('Accepted base point ledger differs from the assigned checkpoint')

    cohort = pd.read_parquet(candidates)
    if len(cohort) != 9044 or cohort.source_record_id.duplicated().any():
        raise ValueError('Candidate source IDs are not the exact unique conditional cohort')
    if cohort.geonameid.astype(str).duplicated().any() or cohort.geonames_record_locator.duplicated().any():
        raise ValueError('GeoNames IDs or raw RU.txt locators are duplicated in the candidate cohort')
    if not cohort.census_year.eq(2021).all() or not cohort.proposed_candidate_gate_pass.all():
        raise ValueError('Conditional candidate year or reviewed gate changed')
    false_claims = ['candidate_only', 'admission_allowed', 'source_lineage_independence_proven',
                    'geonames_alias_current_date_proven', 'coordinate_measurement_at_census_date_proven',
                    'point_admitted', 'identity_edge_admitted', 'historical_propagation_allowed',
                    'population_or_boundary_reviewed', 'upstream_independent_lineage_proven',
                    'geonames_alias_language_or_validity_date_proven',
                    'census_date_point_measurement_proven', 'fias_identifier_binding_claimed']
    if not cohort.candidate_only.all():
        raise ValueError('Expected the frozen candidate-only flag on every row')
    for name in false_claims[1:]:
        if name in cohort and cohort[name].fillna(False).astype(bool).any():
            raise ValueError(f'Frozen candidates assert forbidden admission/lineage claim: {name}')

    base_targets = set(pd.read_parquet(base_points_path, columns=['target_source_record_id']).target_source_record_id.astype(str))
    candidate_targets = set(cohort.source_record_id.astype(str))
    overlap = sorted(candidate_targets & base_targets)
    if overlap:
        raise ValueError(f'Conditional candidates already have accepted points in the base ledger: {overlap[:10]}')

    member_sha = review['geonames_point_source_binding']['ru_txt_member_sha256']
    raw_by_id, raw_summary = _raw_membership_check(cohort, geonames_zip_path, member_sha)
    zip_sha = input_paths[str(geonames_zip_path)]
    point_rows: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []
    raw_by_source_id = {str(r.geonameid): raw_by_id[str(r.geonameid)] for r in cohort.itertuples(index=False)}
    for row in cohort.itertuples(index=False):
        r = row._asdict()
        raw = raw_by_source_id[str(row.geonameid)]
        line_number = int(raw['source_line_1based'])
        geonameid = str(raw['geonameid'])
        locator = _canonical_locator(line_number, geonameid)
        coordinate_locator = json.dumps({
            'archive_member': RAW_MEMBER,
            'archive_member_sha256': member_sha,
            'archive_sha256': zip_sha,
            'source_line_1based': line_number,
            'geonameid': geonameid,
            'raw_member_line_sha256': raw['raw_member_line_sha256'],
        }, ensure_ascii=False, sort_keys=True)
        latitude = _num(raw['latitude_raw'], 'latitude')
        longitude = _num(raw['longitude_raw'], 'longitude')
        use = base_use(
            str(row.source_record_id), 2021, latitude, longitude,
            f'GeoNames:geonameid:{geonameid}', raw['name'], raw['feature_code'],
            str(row.admin1_raw_alias), str(geonames_zip_path), line_number, zip_sha,
            locator, PROVENANCE, RULE,
            {
                'coordinate_quality': 'staged_conditional_geonames_point_not_admitted',
                'coordinate_provider_family': 'geonames',
                'coordinate_provider': 'GeoNames RU dump 2026-09-07',
                'coordinate_provider_id': geonameid,
                'provider_binding_status': 'GeoNames geonameid identifies only the external gazetteer row; census identifier binding is unassessed',
                'provider_fias_binding_status': 'not_assessed; no legal FIAS binding claimed',
                'coordinate_source_file': str(geonames_zip_path),
                'coordinate_source_sha256': zip_sha,
                'coordinate_source_locator': coordinate_locator,
                'coordinate_source_origin': 'GeoNames RU.txt named-place record',
                'coordinate_source_record_id': f'GeoNames:geonameid:{geonameid}',
                'coordinate_source_input_artifact_sha256': zip_sha,
                'coordinate_source_date': None,
                'coordinate_source_latitude_raw': raw['latitude_raw'],
                'coordinate_source_longitude_raw': raw['longitude_raw'],
                'coordinate_measurement_date_unknown': True,
                'coordinate_admission_status': 'staged_candidate_pending_root_review',
                'coordinate_application_family': 'GN_current_2021_named_place_point',
                'application_inference_kind': 'current_2021_named_point_representative_location_candidate',
                'application_gate_status': 'exact_frozen_conditional_candidate_and_RU_txt_source_row_reopened',
                'admission_allowed': False,
                'coordinate_admitted': False,
                'point_admitted': False,
                'identity_edge_admitted': False,
                'historical_propagation_allowed': False,
                'population_scope_comparability_asserted': False,
                'boundary_comparability_asserted': False,
                'direct_historical_coordinate_measurement': False,
                'source_lineage_independence_proven': False,
                'upstream_independent_lineage_proven': False,
                'geonames_alias_language_or_validity_date_proven': False,
                'geonames_alias_current_date_proven': False,
                'census_date_point_measurement_proven': False,
                'fias_identifier_binding_claimed': False,
                'geonames_source_file': str(geonames_zip_path),
                'geonames_source_sha256': zip_sha,
                'geonames_ru_member_sha256': member_sha,
                'geonames_geonameid': geonameid,
                'geonames_record_locator': f'{RAW_MEMBER}:{line_number}',
                'geonames_source_name_raw': raw['name'],
                'geonames_ascii_name_raw': raw['ascii_name'],
                'geonames_alias_raw': str(row.geonames_alias_raw),
                'geonames_alias_literal_in_raw_member': True,
                'geonames_feature_class': raw['feature_class'],
                'geonames_feature_code': raw['feature_code'],
                'geonames_country_code': raw['country_code'],
                'geonames_admin1_raw': raw['admin1'],
                'geonames_admin2_raw': raw['admin2'],
                'geonames_admin1_alias_source': str(row.admin1_raw_alias),
                'geonames_modification_date_raw': raw['modification_date'],
                'geonames_raw_line_sha256': raw['raw_member_line_sha256'],
                'point_origin_file': str(geonames_zip_path),
                'point_origin_sha256': zip_sha,
                'point_origin_locator': locator,
                'point_origin_kind': 'geonames_ru_txt_named_place_point',
                'point_claim_artifact_file': str(candidates),
                'point_claim_artifact_sha256': sha256(candidates),
                'coordinate_application_review_sha256': sha256(review_path),
                'coordinate_uncertainty_flags_json': json.dumps([
                    'GeoNames alias validity date unavailable',
                    'upstream coordinate lineage unknown',
                    'point measurement date unknown',
                    'provider point distance is a concordance screen, not independent measurement evidence',
                ], ensure_ascii=False),
                'target_source_name_raw': str(row.source_name_raw),
                'target_source_record_json': json.dumps({
                    'source_record_id': str(row.source_record_id),
                    'source_name_raw': str(row.source_name_raw),
                    'settlement_name': str(row.settlement_name),
                    'settlement_type': str(row.settlement_type),
                    'region_raw': str(row.region_raw),
                    'source_native_id': str(row.source_native_id),
                    'raw2021_locator': str(row.raw2021_locator),
                    'raw2021_source_sha256': str(row.raw2021_source_sha256),
                }, ensure_ascii=False, sort_keys=True),
                'lineage_event_roles_json': str(row.native_oktmo_event_hits_json),
                'geonames_conditional_rule_review_sha256': sha256(review_path),
                'geonames_conditional_rule_receipt_sha256': sha256(review_receipt_path),
            },
        )
        point_rows.append(use)
        ledger_rows.append({
            'target_source_record_id': str(row.source_record_id),
            'target_year': 2021,
            'population_context': int(row.population),
            'candidate_rule': RULE,
            'candidate_only': True,
            'admission_allowed': False,
            'point_admitted': False,
            'identity_edge_admitted': False,
            'historical_propagation_allowed': False,
            'already_in_accepted_identity_graph': bool(row.already_in_accepted_identity_graph),
            'geonameid': geonameid,
            'source_line_1based': line_number,
            'canonical_point_origin_locator': locator,
            'zip_sha256': zip_sha,
            'ru_txt_member_sha256': member_sha,
            'raw_member_line_sha256': raw['raw_member_line_sha256'],
            'raw_member_line': raw['raw_member_line'],
            'raw_alias_literal_match': True,
            'raw_latitude': raw['latitude_raw'],
            'raw_longitude': raw['longitude_raw'],
            'stored_latitude_from_raw_geonames': latitude,
            'stored_longitude_from_raw_geonames': longitude,
            'provider_latitude_for_concordance_only': float(row.provider_latitude),
            'provider_longitude_for_concordance_only': float(row.provider_longitude),
            'provider_to_geonames_distance_km_concordance_only': float(row.provider_to_geonames_km),
            'raw_source_row_all_checks_pass': bool(row.raw_source_row_all_checks_pass),
            'geonames_expected_region_status': str(row.geonames_expected_region_status),
            'provider_expected_region_status': str(row.provider_expected_region_status),
            'provider_fias_and_coordinate_ids_unique': bool(row.provider_fias_and_coordinate_ids_unique),
            'no_cached_baseline_coordinate_conflict': bool(row.no_cached_baseline_coordinate_conflict),
            'no_cached_p625_over_5km_conflict_screen': bool(row.no_cached_p625_over_5km_conflict_screen),
            'no_exact_native_oktmo_event': bool(row.no_exact_native_oktmo_event),
            'candidate_hold_reasons_json': str(row.candidate_hold_reasons_json),
            'source_lineage_independence_proven': False,
            'alias_validity_or_language_proven': False,
            'measurement_at_census_date_proven': False,
            'population_scope_or_boundary_comparability_asserted': False,
            'raw_source_row_reopened_and_verified': True,
        })

    point_uses = pd.DataFrame(point_rows)
    gate_ledger = pd.DataFrame(ledger_rows)
    if len(point_uses) != 9044 or len(gate_ledger) != 9044:
        raise ValueError('Stage did not preserve the exact 9,044-row conditional cohort')
    if point_uses.target_source_record_id.duplicated().any():
        raise ValueError('Duplicate target IDs in staged point uses')
    if not point_uses.coordinate_admission_status.eq('staged_candidate_pending_root_review').all():
        raise ValueError('Unexpected point admission status')
    if point_uses.admission_allowed.any() or point_uses.coordinate_admitted.any() or point_uses.point_admitted.any():
        raise ValueError('Staged point uses unexpectedly claim admission')
    expected_latitudes = cohort.set_index('source_record_id').loc[
        point_uses.target_source_record_id, 'geonames_latitude'].astype(str).astype(float).to_numpy()
    expected_longitudes = cohort.set_index('source_record_id').loc[
        point_uses.target_source_record_id, 'geonames_longitude'].astype(str).astype(float).to_numpy()
    if not point_uses.latitude.eq(expected_latitudes).all():
        raise ValueError('Stored latitude differs from exact raw GeoNames coordinate')
    if not point_uses.longitude.eq(expected_longitudes).all():
        raise ValueError('Stored longitude differs from exact raw GeoNames coordinate')

    output.mkdir(parents=True)
    point_path = output / 'staged_point_uses.parquet'
    ledger_path = output / 'gate_ledger.parquet'
    point_uses.to_parquet(point_path, index=False)
    gate_ledger.to_parquet(ledger_path, index=False)
    receipt = {
        'artifact': 'geonames_point_use_stage_v1',
        'status': 'candidate_only_pending_independent_application_review',
        'candidate_rule': RULE,
        'staged_rows': len(point_uses),
        'staged_population_context': int(cohort.population.sum()),
        'coordinate_use_admissions': 0,
        'identity_edge_admissions': 0,
        'historical_propagations': 0,
        'accepted_base_point_rows': len(base_targets),
        'base_target_overlap': 0,
        'geonames_raw_lines_reopened': raw_summary['candidate_lines_reopened'],
        'geonames_member_rows_read': raw_summary['member_rows'],
        'builder_sha256': sha256(Path(__file__)),
        'inputs': input_paths,
        'pins': {
            'conditional_review_sha256': sha256(review_path),
            'conditional_review_receipt_sha256': sha256(review_receipt_path),
            'conditional_candidate_table_sha256': sha256(candidates),
            'conditional_rule_reviewed_candidate_sha256': review_receipt['outputs']['conditional_point_use_candidates.parquet'],
            'geonames_zip_sha256': zip_sha,
            'geonames_ru_member_sha256': raw_summary['member_sha256'],
        },
        'outputs': {
            point_path.name: sha256(point_path),
            ledger_path.name: sha256(ledger_path),
        },
        'limits': [
            'Rows are 2021-only pending point-use candidates; no coordinates are admitted by this stage.',
            'Stored coordinates are the raw GeoNames named-place coordinates, not the provider coordinates; provider coordinates are only retained as concordance context.',
            'GeoNames geonameid identifies the external gazetteer row only; census identifier and legal FIAS binding are unassessed.',
            'Alias validity date, upstream coordinate lineage, and point measurement date are unknown.',
            'No identity edge, historical propagation, population comparability, or boundary comparability is asserted.',
            'The preserved source README specifies GeoNames CC BY 4.0; this stage makes no project-wide license conclusion.',
        ],
    }
    receipt_path = output / 'receipt.json'
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--candidates', type=Path, default=COHORT)
    parser.add_argument('--review', type=Path, default=REVIEW)
    parser.add_argument('--review-receipt', type=Path, default=REVIEW_RECEIPT)
    parser.add_argument('--base-points', type=Path, default=BASE_POINTS)
    parser.add_argument('--geonames-zip', type=Path, default=GEONAMES_ZIP)
    args = parser.parse_args()
    print(json.dumps(stage(args.output, args.candidates, args.review, args.review_receipt,
                           args.base_points, args.geonames_zip), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
