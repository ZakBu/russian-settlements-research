"""Finalize hash-pinned modern point admissions after independent rule review.

This consumes immutable candidate staging and the frozen independent review. It
keeps the reviewed R5b assertions intact, admits only reviewed 2021 rules, and
does not turn candidate point propagation into historical coordinate evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .coordinate_rules import valid_wgs84

STAGING = Path('/workspace/settlements-work/coordinates/admission_staging_v1')
REVIEW_DIR = Path('/workspace/settlements-work/coordinates/independent_review_v1')
OUTPUT = Path('/workspace/settlements-work/coordinates/accepted_modern_v1')
STAGING_MANIFEST_SHA256 = '8c0e5da620f428ebeb4cdcb599a8f4f9b57c33cb8fd7985c132584890387f5c2'
REVIEW_JSON_SHA256 = 'f8081527bd7d555ffe91069f2f4ec1af0459cf112a80befbe5d27587869f8726'
REVIEW_NOTES_SHA256 = 'e8cf2e38230083250ef4e8a395e3db8d957fc4f47994824eb74da34f0c2a8576'

PROVIDER_FAMILY = 'A_rural_exact_code_and_own_name_type'
CITY_C = 'C_wikidata_physical_source_city_point'
CITY_A = 'A_urban_level4_physical_code_name_point_in_region'
WIKI_EVIDENCE_FAMILY = 'wikimedia_wikidata_one_evidence_family'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    try:
        x = json.loads(value) if isinstance(value, str) else value
        return x if isinstance(x, list) else []
    except (ValueError, TypeError):
        return []


def _text(value: Any) -> str:
    return '' if value is None or pd.isna(value) else str(value).strip()


def _point_key(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        a, b = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(a) or not math.isfinite(b) or not valid_wgs84(a, b):
        return None
    return round(a, 7), round(b, 7)


def _family_sources(proposals: pd.DataFrame, family: str) -> set[str]:
    return {
        str(r.source_record_id)
        for r in proposals.itertuples(index=False)
        if family in _json_list(r.candidate_families_json)
    }


def _make_review_point_rows(
    proposals: pd.DataFrame,
    evidence: pd.DataFrame,
    baseline: pd.DataFrame,
    review: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Apply reviewed holds and family precedence to unique target source rows."""
    pby = {str(r.source_record_id): r._asdict() for r in proposals.itertuples(index=False)}
    baseline_by = {str(r.target_source_record_id): r._asdict() for r in baseline.itertuples(index=False)}
    # Baseline remains a direct frozen assertion, including the 48 historical uses.
    output: dict[str, dict[str, Any]] = {}
    for sid, r in baseline_by.items():
        if _point_key(r.get('latitude'), r.get('longitude')) is None:
            raise ValueError(f'bad frozen baseline coordinate for {sid}')
        output[sid] = {
            'target_source_record_id': sid,
            'target_year': int(r['target_year']),
            'latitude': float(r['latitude']), 'longitude': float(r['longitude']),
            'coordinate_quality': _text(r.get('coordinate_quality')),
            'coordinate_source': _text(r.get('coordinate_source')),
            'coordinate_source_record_id': _text(r.get('coordinate_source_record_id')),
            'coordinate_provider': _text(r.get('coordinate_source')),
            'coordinate_provider_id': '',
            'source_name': '', 'source_type': '', 'source_region': '',
            'source_file': '', 'source_row': None, 'source_sha256': '',
            'source_locator': _text(r.get('evidence_uri')),
            'coordinate_provenance': 'frozen_r5b_direct_reviewed_assertion_preserved_byte_identically_in_source_csv',
            'admission_rule': _text(r.get('decision_rule')),
            'provider_binding_status': 'frozen_reviewed_baseline_claim; no new provider binding inferred',
            'provider_fias_binding_status': 'not_reinterpreted_from_frozen_baseline',
            'coordinate_admission_status': 'frozen_r5b_reviewed_baseline_preserved',
            'coordinate_measurement_date_unknown': True,
            'boundary_comparability_asserted': False,
        }

    target_rows = proposals.loc[proposals.target_year.eq(2021)].copy()
    if target_rows.source_record_id.astype(str).duplicated().any():
        raise ValueError('staging proposals are not unique by source_record_id')
    proposal_sources = set(target_rows.source_record_id.astype(str))
    if not proposal_sources <= set(pby):
        raise ValueError('internal proposal index mismatch')

    city_review = review['verdict']
    c_sources = _family_sources(target_rows, CITY_C)
    a_city_sources = _family_sources(target_rows, CITY_A)
    provider_sources = _family_sources(target_rows, PROVIDER_FAMILY)
    if len(provider_sources) != city_review['A_rural_exact_code_plus_own_name_type']['candidate_rows']:
        raise ValueError('A-rural source count does not match reviewed count')
    if len(c_sources) != city_review[CITY_C]['candidate_source_rows']:
        raise ValueError('C city source count does not match reviewed count')
    if len(a_city_sources) != city_review[CITY_A]['candidate_source_rows']:
        raise ValueError('A-city source count does not match reviewed count')

    held_multi = {str(h['source_record_id']) for h in review['targeted_holds']['multiple_p625']}
    unresolved_conflicts = {
        str(h['source_record_id']) for h in review['targeted_holds']['known_city_coordinate_conflicts']
        if str(h.get('interpretation', '')).startswith('hold_')
    }
    # The six-item review list includes Langepas, whose alternative claims fail the
    # exact-label point gate. Only rows with multiple eligible point records count.
    wiki = evidence.loc[evidence.coordinate_provider_family.eq(WIKI_EVIDENCE_FAMILY)].copy()
    wiki['source_record_id'] = wiki.source_record_id.astype(str)
    wiki_by: dict[str, list[dict[str, Any]]] = {}
    for r in wiki.to_dict('records'):
        if r['source_record_id'] in c_sources | a_city_sources:
            wiki_by.setdefault(r['source_record_id'], []).append(r)
    distinct_wiki_points = {
        sid: {_point_key(r.get('latitude'), r.get('longitude')) for r in rows} - {None}
        for sid, rows in wiki_by.items()
    }
    multi_ids = {sid for sid, points in distinct_wiki_points.items() if len(points) > 1}
    if multi_ids != (held_multi & (c_sources | a_city_sources)):
        raise ValueError('reviewed multiple-P625 holds do not match staged eligible point rows')
    c_eligible = c_sources - multi_ids - unresolved_conflicts
    a_eligible = a_city_sources - multi_ids
    if len(c_eligible) != city_review[CITY_C]['eligible_after_known_holds']:
        raise ValueError('C city post-hold count does not match review')
    if len(a_eligible) != city_review[CITY_A]['eligible_after_known_holds']:
        raise ValueError('A-city post-hold count does not match review')

    admitted_by_family = {'baseline': 0, 'wikidata_C_city': 0, 'dadata_A_rural': 0}
    # Wiki city points take precedence over overlapping A-city presentation of
    # the same QID/P625 point. Any frozen assertion has precedence over both.
    accepted_city = c_eligible
    for sid in sorted(accepted_city):
        if sid in baseline_by:
            continue
        rows = wiki_by.get(sid, [])
        points = distinct_wiki_points.get(sid, set())
        if len(points) != 1 or not rows:
            raise ValueError(f'eligible city point missing or ambiguous for {sid}')
        point = next(iter(points))
        # Keep every QID/evidence locator that supports this single coordinate.
        supporting = [r for r in rows if _point_key(r.get('latitude'), r.get('longitude')) == point]
        source = pby[sid]
        first = supporting[0]
        output[sid] = _modern_row(source, first, point, CITY_C,
            'Wikidata P625 representative point; physical P31/P279, exact code/name and ADM1 checked; no boundary claim',
            'independently_reviewed_wikidata_qid_and_p625_point_claim',
            'Wikidata QID binding reviewed; FIAS binding not implied by coordinate admission')
        output[sid]['source_locator'] = json.dumps(sorted({_text(x.get('coordinate_source_locator')) for x in supporting if _text(x.get('coordinate_source_locator'))}), ensure_ascii=False)
        admitted_by_family['wikidata_C_city'] += 1

    # Rural DaData point use: reviewed exact source/provider code, own name/type,
    # physical settlement and unique provider point. The QID city rule wins above.
    provider_evidence = evidence.loc[evidence.coordinate_provider_family.eq('tochno_dadata')].copy()
    provider_evidence['source_record_id'] = provider_evidence.source_record_id.astype(str)
    provider_by = {str(k): g.to_dict('records') for k, g in provider_evidence.groupby('source_record_id', sort=False)}
    for sid in sorted(provider_sources):
        if sid in output:
            continue
        rows = provider_by.get(sid, [])
        points = {_point_key(r.get('latitude'), r.get('longitude')) for r in rows} - {None}
        if len(points) != 1 or not rows:
            raise ValueError(f'eligible rural point missing or ambiguous for {sid}')
        source = pby[sid]
        first = rows[0]
        output[sid] = _modern_row(source, first, next(iter(points)), PROVIDER_FAMILY,
            'DaData via Tochno 2021 source-row representative point; exact source/provider OKTMO, own name/type and FIAS level 6 checked; query receipt/date unavailable',
            'reviewed_exact_source_provider_code_name_type_point_rule_A_rural',
            'coordinate point rule accepted; FIAS level-6 ID binding is a separate reviewed claim')
        admitted_by_family['dadata_A_rural'] += 1

    admitted_by_family['baseline'] = len(baseline_by)
    result = list(output.values())
    if len({r['target_source_record_id'] for r in result}) != len(result):
        raise ValueError('final output has duplicate target source record IDs')
    for r in result:
        if _point_key(r.get('latitude'), r.get('longitude')) is None:
            raise ValueError(f'final output contains invalid point for {r.get("target_source_record_id")}')
    return result, {
        'staged_2021_source_rows': len(target_rows),
        'A_rural_review_eligible_sources': len(provider_sources),
        'B_strict_subset_of_A_sources': city_review["B_strict_name_plus_external_context"]['candidate_rows'],
        'C_city_review_eligible_sources': len(c_eligible),
        'A_city_review_eligible_sources': len(a_eligible),
        'C_A_city_source_overlap': len(c_sources & a_city_sources),
        'baseline_source_id_overlap_with_modern_candidates': len(set(baseline_by) & proposal_sources),
        'baseline_2021_source_id_overlap_with_city_candidates': len(set(baseline_by) & c_sources),
        'unresolved_city_coordinate_holds': len(unresolved_conflicts),
        'multiple_eligible_p625_holds': len(multi_ids),
        'accepted_uses_by_rule_in_final_output': admitted_by_family,
        'accepted_point_uses': len(result),
        'accepted_2021_point_uses': sum(int(r['target_year']) == 2021 for r in result),
        'accepted_historical_frozen_baseline_uses': sum(int(r['target_year']) in (2002, 2010) for r in result),
        'retrospective_candidate_propagations_admitted': 0,
    }


def _modern_row(source: dict[str, Any], evidence: dict[str, Any], point: tuple[float, float],
                rule: str, provenance: str, binding: str, fias_binding: str) -> dict[str, Any]:
    family = _text(evidence.get('coordinate_provider_family'))
    return {
        'target_source_record_id': _text(source.get('target_source_record_id')),
        'target_year': int(source['target_year']), 'latitude': point[0], 'longitude': point[1],
        'coordinate_quality': 'reviewed modern representative point',
        'coordinate_source': _text(evidence.get('coordinate_provider')),
        'coordinate_source_record_id': _text(evidence.get('coordinate_source_record_id')),
        'coordinate_provider': _text(evidence.get('coordinate_provider')),
        'coordinate_provider_family': family,
        'coordinate_provider_id': _text(evidence.get('coordinate_provider_id')),
        'provider_general_fias_id': _text(evidence.get('provider_general_fias_id')),
        'settlement_provider_id': _text(evidence.get('settlement_provider_id')),
        'source_name': _text(source.get('source_name')), 'source_type': _text(source.get('source_type')),
        'source_region': _text(source.get('source_region')),
        'source_file': _text(source.get('source_file')), 'source_row': source.get('source_row'),
        'source_sha256': _text(source.get('source_sha256')),
        'source_locator': _text(evidence.get('coordinate_source_locator')),
        'source_oktmo_raw': _text(source.get('source_oktmo_raw')),
        'source_okato_raw': _text(source.get('source_okato_raw')),
        'coordinate_provenance': provenance, 'admission_rule': rule,
        'provider_binding_status': binding, 'provider_fias_binding_status': fias_binding,
        'coordinate_admission_status': 'reviewed_rule_accepted',
        'coordinate_measurement_date_unknown': True,
        'provider_query_receipt_missing': family == 'tochno_dadata',
        'boundary_comparability_asserted': False,
        'coordinate_uncertainty_flags_json': _text(source.get('coordinate_uncertainty_flags_json')),
    }


def finalize(staging: Path = STAGING, review_dir: Path = REVIEW_DIR, output: Path = OUTPUT) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f'immutable output already exists: {output}')
    manifest_path = staging / 'manifest.json'
    review_path = review_dir / 'review.json'
    notes_path = review_dir / 'notes.md'
    if sha256(manifest_path) != STAGING_MANIFEST_SHA256:
        raise ValueError('staging manifest hash mismatch')
    if sha256(review_path) != REVIEW_JSON_SHA256 or sha256(notes_path) != REVIEW_NOTES_SHA256:
        raise ValueError('independent review hash mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    review = json.loads(review_path.read_text(encoding='utf-8'))
    if review.get('status') != 'checked_rule_accepted_with_narrow_row_specific_holds':
        raise ValueError('independent review is not an accepted coordinate-family review')
    for family in ('A_rural_exact_code_plus_own_name_type', 'B_strict_name_plus_external_context', CITY_C, CITY_A):
        decision = review['verdict'][family]['decision']
        if not decision.startswith('checked_rule_accepted'):
            raise ValueError(f'review did not accept {family}')
    for name in ('coordinate_proposals.parquet', 'coordinate_point_evidence.parquet', 'frozen_r5b_coordinate_assertions.parquet', 'frozen_r5b_coordinate_admissions.csv'):
        item = manifest['outputs'][name]
        p = staging / name
        if sha256(p) != item['sha256']:
            raise ValueError(f'staging input hash mismatch: {name}')
    baseline_csv = staging / 'frozen_r5b_coordinate_admissions.csv'
    baseline = pd.read_csv(baseline_csv)
    if len(baseline) != 81 or baseline.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('frozen R5b baseline must contain 81 unique source uses')
    proposals = pd.read_parquet(staging / 'coordinate_proposals.parquet')
    evidence = pd.read_parquet(staging / 'coordinate_point_evidence.parquet')
    rows, metrics = _make_review_point_rows(proposals, evidence, baseline, review)
    frame = pd.DataFrame(rows).sort_values(['target_year', 'target_source_record_id'], kind='stable').reset_index(drop=True)
    output.mkdir(parents=True, exist_ok=False)
    parquet = output / 'accepted_point_uses.parquet'
    frame.to_parquet(parquet, index=False)
    receipt = {
        'status': 'reviewed_modern_point_uses_finalized_with_frozen_baseline',
        'run_version': 'accepted_modern_coordinates_v1',
        'implementation_sha256': sha256(Path(__file__)),
        'staging_manifest': {'path': str(manifest_path), 'sha256': sha256(manifest_path)},
        'independent_review': {'review_id': review['review_id'], 'review_json': str(review_path), 'review_json_sha256': sha256(review_path), 'notes': str(notes_path), 'notes_sha256': sha256(notes_path)},
        'source_input_hashes': {name: manifest['outputs'][name]['sha256'] for name in ('coordinate_proposals.parquet', 'coordinate_point_evidence.parquet', 'frozen_r5b_coordinate_assertions.parquet', 'frozen_r5b_coordinate_admissions.csv')},
        'admission_policy': {
            'precedence': ['frozen_r5b_individual_assertion', 'reviewed_physical_wikidata_city_point', 'reviewed_exact_provider_rural_point'],
            'A_rural': 'accept reviewed 96,342 row rule; provider FIAS binding remains a distinct claim; query receipt and measurement date unavailable',
            'B_strict': 'reviewed subset of A rural; no extra coordinate family or source rows',
            'C_city': 'accept 903 eligible rows; hold five multiple-P625 rows and unresolved Mezhgorye/Ust-Kut coordinate choices',
            'A_city': '654 eligible rows overlap C city and do not create a second point use',
            'city_old_provider_distance_flags': '11 GeoKLADR-corroborated flags are resolved per review; only two unresolved rows held',
            'mixed_P31': 'physical P31/P279 path qualifies despite co-occurring administrative P31 class',
            'provider_identifier_binding': 'separate from coordinate correctness; Wikidata QID never treated as FIAS ID',
            'baseline': '81 frozen assertions preserved as individual uses from immutable source CSV',
            'retrospective_propagation': 'not admitted; candidate temporal-continuity propagation remains pending separate review',
            'scope': 'representative points only; no aggregate points, city footprints, or boundary equivalence claims',
        },
        'metrics': metrics,
        'output': {'path': str(parquet), 'sha256': sha256(parquet), 'rows': len(frame), 'columns': list(frame.columns)},
    }
    receipt_path = output / 'acceptance_receipt.json'
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staging', type=Path, default=STAGING)
    parser.add_argument('--review-dir', type=Path, default=REVIEW_DIR)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    print(json.dumps(finalize(args.staging, args.review_dir, args.output), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
