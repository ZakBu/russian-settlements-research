"""Stage two unblocked stable-city historical rows on accepted modern city points.

This bounded candidate application retains the failed-distance historical named
point as an unused alternative and carries the exact accepted 2021 carrier point
through an accepted same-place graph path. It never admits coordinates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

import pandas as pd

from .propagate_accepted_points import STATUS_OK

ROOT = Path('/workspace')
CONT = ROOT / 'settlements-work/continuation_20261003'
DEFAULT_CASES = CONT / 'next_loop_residual_diagnostic_v1/historical_city_distance_only_cases.csv'
DEFAULT_H_LEDGER = CONT / 'historical_city_application_v2/gate_ledger.parquet'
DEFAULT_SELECTED = ROOT / 'settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet'
DEFAULT_SELECTED_CURRENT = CONT / 'primary_population_application_v1/selected_observations.parquet'
DEFAULT_EVIDENCE = ROOT / 'settlements-work/candidates/optimized_run/source_evidence.parquet'
DEFAULT_GRAPH = ROOT / 'settlements-work/identity/accepted_historical_v2/accepted_identity_edges.parquet'
DEFAULT_BLOCKED = CONT / 'blocked_point_reuse_targets_v1.json'
DEFAULT_PRIOR_HOLDS = ROOT / 'settlements-work/coordinates/accepted_final_v1/additional_legacy_point_conflict_holds.parquet'
DEFAULT_RAW_2021_SOURCE = ROOT / 'settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
RAW_2021_SOURCE_SHA256 = '86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14'
POINT_CHOICE_REVIEW_SHA256 = 'c8791e211f0d1c7b337e566714e221085aff0ca3ad643a0168a472a37ca6733e'
POINT_CHOICE_REVIEW_ID = 'legacy_city_point_choice_review_v1_20261003'
EXPECTED_HOLD = ['historical_to_accepted_modern_point_exceeds_1km']
RECEIVING_EVENT_TYPES = {'absorbed', 'absorbed_into_city', 'merged_into_city'}

SELECTED_COLUMNS = [
    'source_record_id', 'census_year', 'settlement_name', 'settlement_type',
    'source_name_raw', 'source_file', 'source_sheet', 'source_row', 'source_sha256',
    'source_locator', 'source_native_id', 'population', 'population_scope',
    'population_value_quality', 'is_additive_settlement_record', 'entity_grain_status',
    'region_raw', 'region_norm', 'okato', 'oktmo',
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def txt(value) -> str:
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()


def num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def norm(value) -> str:
    return ' '.join(txt(value).casefold().replace('ё', 'е').split())


def read_blocked(path: Path) -> set[str]:
    value = json.loads(Path(path).read_text())
    if isinstance(value, dict):
        value = value.get('blocked_target_source_record_ids', [])
    if not isinstance(value, list):
        raise ValueError('blocked-target JSON needs a list of exact source IDs')
    return {txt(item) for item in value if txt(item)}


def exact_gate_hold(value) -> list[str]:
    try:
        reasons = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return []
    return reasons if isinstance(reasons, list) else []


def load_evidence(path: Path, ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    frame = pd.read_parquet(path, columns=['source_record_id', 'source_evidence_json'],
                            filters=[('source_record_id', 'in', sorted(ids))])
    out = {}
    for row in frame.itertuples(index=False):
        rid = txt(row.source_record_id)
        if rid in out:
            raise ValueError(f'duplicate source evidence for {rid}')
        out[rid] = json.loads(row.source_evidence_json)
    return out


def evidence_holds(value: dict | None, expected_year: int) -> list[str]:
    if not value:
        return ['source_evidence_missing']
    reasons = []
    if int(value.get('census_year', -1)) != expected_year:
        reasons.append('source_evidence_year_mismatch')
    if value.get('legacy_identity_conflict'):
        reasons.append('legacy_identity_conflict')
    if value.get('legacy_same_year_collision'):
        reasons.append('legacy_same_year_collision')
    if value.get('is_federal_aggregate'):
        reasons.append('source_is_federal_aggregate')
    if value.get('is_additive_settlement_record') is not True:
        reasons.append('source_not_confirmed_additive_physical_row')
    if norm(value.get('settlement_type')) != 'город':
        reasons.append('source_not_atomic_city')
    if not norm(value.get('settlement_name')) or not norm(value.get('region_norm')):
        reasons.append('source_name_or_region_missing')
    if value.get('legacy_entity_year_record_count') not in (None, 1):
        reasons.append('source_entity_year_not_unique')
    return reasons


def event_holds(value) -> list[str]:
    try:
        roles = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return ['lineage_event_roles_malformed']
    if not isinstance(roles, list):
        return ['lineage_event_roles_malformed']
    reasons = []
    for role in roles:
        allowed_receiver = (
            role.get('point_veto') is False
            and role.get('event_type') in RECEIVING_EVENT_TYPES
            and role.get('native_code_roles') == ['to_settlement_id_legacy_candidate']
        )
        if not allowed_receiver:
            reasons.append('lineage_event_role_not_safe_for_representative_point_reuse')
            break
    return reasons


def verify_carrier_origin(carrier: dict, hash_cache: dict[str, str]) -> list[str]:
    """Check stored carrier source assets once per filename, preserving each row hash."""
    reasons = []
    has_verified_asset = False
    for file_field, hash_field in (
        ('point_origin_file', 'point_origin_sha256'),
        ('point_claim_artifact_file', 'point_claim_artifact_sha256'),
    ):
        filename, expected = txt(carrier.get(file_field)), txt(carrier.get(hash_field))
        if not filename and not expected:
            continue
        if not filename or not expected:
            reasons.append('carrier_origin_file_or_hash_missing')
            continue
        if filename not in hash_cache:
            p = Path(filename)
            hash_cache[filename] = sha(p) if p.is_file() else '__MISSING__'
        if hash_cache[filename] == '__MISSING__' or hash_cache[filename] != expected:
            reasons.append('carrier_origin_asset_hash_mismatch')
        else:
            has_verified_asset = True
    if not has_verified_asset:
        reasons.append('carrier_has_no_hash_verified_point_origin_or_claim_asset')
    if not txt(carrier.get('point_origin_locator')):
        reasons.append('carrier_point_origin_locator_missing')
    if not txt(carrier.get('point_origin_kind')):
        reasons.append('carrier_point_origin_kind_missing')
    if not txt(carrier.get('coordinate_provenance')):
        reasons.append('carrier_coordinate_provenance_missing')
    lat, lon = num(carrier.get('latitude')), num(carrier.get('longitude'))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        reasons.append('carrier_point_invalid')
    return reasons


def validate_path(target_id: str, carrier_id: str, decision_ids: list[str],
                  edge_by_id: dict[str, dict]) -> list[str]:
    if not decision_ids:
        return ['accepted_identity_path_missing']
    current = target_id
    reasons = []
    for decision_id in decision_ids:
        edge = edge_by_id.get(decision_id)
        if not edge:
            reasons.append('accepted_identity_path_edge_missing')
            break
        if edge['relation'] != 'same_place' or edge['decision_status'] not in STATUS_OK:
            reasons.append('identity_path_has_unaccepted_or_non_same_place_edge')
            break
        left, right = txt(edge['from_source_record_id']), txt(edge['to_source_record_id'])
        if current == left:
            current = right
        elif current == right:
            current = left
        else:
            reasons.append('identity_path_edges_do_not_chain_from_exact_target')
            break
    if current != carrier_id:
        reasons.append('identity_path_does_not_end_at_exact_carrier')
    return reasons


def load_point_choice_approvals(review_path: Path | None, cases_by_id: dict[str, dict],
                                carriers: dict[str, dict], inputs: dict[str, Path],
                                blocked_ids: set[str], expected_sha256: str) -> tuple[dict, dict]:
    """Load only the pinned independent review, matching every approved carrier to base."""
    if review_path is None:
        return {}, {}
    review_path = Path(review_path)
    review_sha = sha(review_path)
    if review_sha != expected_sha256:
        raise ValueError('point-choice review JSON SHA-256 does not match its pinned approval')
    review_dir = review_path.parent
    row_path = review_dir / 'row_level_point_choice_review.csv'
    receipt_path = review_dir / 'receipt.json'
    if not row_path.is_file() or not receipt_path.is_file():
        raise FileNotFoundError('point-choice review row-level CSV or receipt is missing')
    review = json.loads(review_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if review.get('review_id') != POINT_CHOICE_REVIEW_ID:
        raise ValueError('unexpected point-choice review ID')
    if 'APPROVE_BOUNDED_MODERN_POINT_REUSE' not in txt(review.get('decision')):
        raise ValueError('point-choice review does not approve bounded modern point reuse')
    approved = review.get('approved_for_bounded_modern_point_reuse_ids')
    if not isinstance(approved, list) or len(approved) != 12 or len(set(approved)) != 12:
        raise ValueError('pinned point-choice review does not contain its exact 12 approved IDs')
    if review.get('target_count') != 12 or review.get('remaining_hold_ids') != []:
        raise ValueError('point-choice review scope or hold register changed')
    if not set(approved).issubset(cases_by_id):
        raise ValueError('point-choice approval includes targets outside the bounded case cohort')
    if not set(approved).issubset(blocked_ids):
        raise ValueError('point-choice approval does not correspond exclusively to blocked targets')
    receipt_files = receipt.get('files', {})
    if receipt.get('review_id') != POINT_CHOICE_REVIEW_ID or receipt.get('target_count') != 12 or receipt.get('approved_count') != 12 or receipt.get('held_count') != 0:
        raise ValueError('point-choice review receipt scope does not match approved review')
    if receipt_files.get('review.json') != review_sha:
        raise ValueError('point-choice review receipt does not pin supplied review JSON')
    row_sha = sha(row_path)
    if receipt_files.get('row_level_point_choice_review.csv') != row_sha:
        raise ValueError('point-choice review receipt does not pin row-level approval evidence')

    # The independent review used the earlier accepted-point table; require every
    # approved carrier's raw point claim to match the caller's current accepted base.
    frozen = review.get('frozen_input_sha256', {})
    for key, name in (
        ('/workspace/settlements-work/continuation_20261003/next_loop_residual_diagnostic_v1/historical_city_distance_only_cases.csv', 'distance_only_cases'),
        ('/workspace/settlements-work/identity/accepted_historical_v2/accepted_identity_edges.parquet', 'accepted_graph_R2'),
        ('/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet', 'selected_R2'),
        ('/workspace/settlements-work/coordinates/accepted_final_v1/additional_legacy_point_conflict_holds.parquet', 'prior_point_conflict_holds'),
    ):
        if frozen.get(key) != sha(inputs[name]):
            raise ValueError(f'point-choice review frozen evidence changed: {key}')

    review_rows = pd.read_csv(row_path, dtype='string').fillna('')
    if review_rows.target_source_record_id.duplicated().any():
        raise ValueError('point-choice review contains duplicate target rows')
    row_by_id = {txt(row.target_source_record_id): row._asdict()
                 for row in review_rows.itertuples(index=False)}
    if set(row_by_id) != set(approved):
        raise ValueError('point-choice row-level evidence does not equal the approved ID list')
    for target_id in approved:
        row = row_by_id[target_id]
        case = cases_by_id[target_id]
        carrier_id = txt(case.get('carrier_source_record_id'))
        carrier = carriers.get(carrier_id)
        if carrier is None:
            raise ValueError(f'approved target carrier missing from current accepted base: {target_id}')
        if row.get('point_choice') != 'APPROVE_BOUNDED_MODERN_POINT_REUSE':
            raise ValueError(f'row-level point-choice approval missing: {target_id}')
        if row.get('legacy_hold_is_same_claim_as_current_carrier') != 'True':
            raise ValueError(f'point-choice review does not identify exact carrier claim: {target_id}')
        if txt(row.get('modern_carrier_source_record_id')) != carrier_id:
            raise ValueError(f'point-choice carrier ID mismatch: {target_id}')
        if (num(row.get('accepted_point_latitude')) != num(carrier.get('latitude'))
                or num(row.get('accepted_point_longitude')) != num(carrier.get('longitude'))):
            raise ValueError(f'current accepted carrier coordinates differ from reviewed point: {target_id}')
        if txt(row.get('accepted_point_origin_kind')) != txt(carrier.get('point_origin_kind')):
            raise ValueError(f'current accepted carrier origin kind differs from review: {target_id}')
        if txt(row.get('accepted_point_qid')) != txt(carrier.get('coordinate_provider_id')):
            raise ValueError(f'current accepted carrier provider ID differs from review: {target_id}')
        for reviewed, current, label in (
            ('accepted_point_claim_raw_file', 'point_origin_file', 'origin filename'),
            ('accepted_point_claim_sha256', 'point_origin_sha256', 'origin hash'),
            ('accepted_point_claim_raw_locator', 'point_origin_locator', 'origin locator'),
        ):
            if txt(row.get(reviewed)) != txt(carrier.get(current)):
                raise ValueError(f'current accepted carrier {label} differs from review: {target_id}')
        if txt(carrier.get('coordinate_source')).lower() not in {'wikidata_p625', 'wikidata p625'}:
            raise ValueError(f'approved target no longer maps to reviewed P625 carrier: {target_id}')
    return row_by_id, {'review_id': POINT_CHOICE_REVIEW_ID, 'review_sha256': review_sha,
                       'row_level_sha256': row_sha, 'review_path': str(review_path),
                       'row_level_path': str(row_path), 'approved_ids': approved}


def recovered_frozen_source_origin(carrier: dict, raw_row: dict, frozen_row: dict,
                                   raw_path: Path, raw_sha256: str) -> dict:
    """Recover only the raw-row locator for the already frozen Voronezh point."""
    carrier_id = txt(carrier.get('target_source_record_id'))
    if raw_sha256 != RAW_2021_SOURCE_SHA256:
        raise ValueError('raw 2021 source parquet hash differs from reviewed asset')
    if txt(carrier.get('point_origin_kind')) != 'reviewed_frozen_assertion':
        raise ValueError('carrier is not the frozen reviewed assertion requiring origin recovery')
    suffix = re.search(r':parquet:(\d+)$', carrier_id)
    if suffix is None:
        raise ValueError('carrier ID does not encode its exact raw parquet row')
    source_row = int(suffix.group(1))
    stored_source_row = num(carrier.get('source_row'))
    if stored_source_row is not None and stored_source_row != source_row:
        raise ValueError('carrier stored row locator conflicts with exact carrier ID')
    if txt(frozen_row.get('target_source_record_id')) != carrier_id:
        raise ValueError('frozen claim row target does not equal exact current carrier ID')
    if txt(frozen_row.get('coordinate_source_record_id')) != carrier_id:
        raise ValueError('frozen claim row source does not equal exact current carrier ID')
    if txt(frozen_row.get('coordinate_kind')) != 'direct_source_row_representative_point':
        raise ValueError('frozen claim is not the reviewed direct source-row point')
    if int(float(txt(frozen_row.get('target_year')))) != 2021:
        raise ValueError('frozen claim row is not the 2021 carrier')

    raw_lat, raw_lon = num(raw_row.get('latitude_dadata')), num(raw_row.get('longitude_dadata'))
    frozen_lat, frozen_lon = num(frozen_row.get('latitude')), num(frozen_row.get('longitude'))
    carrier_lat, carrier_lon = num(carrier.get('latitude')), num(carrier.get('longitude'))
    if None in (raw_lat, raw_lon, frozen_lat, frozen_lon, carrier_lat, carrier_lon):
        raise ValueError('raw, frozen or accepted point coordinate is missing')
    if not (raw_lat == frozen_lat == carrier_lat and raw_lon == frozen_lon == carrier_lon):
        raise ValueError('raw, frozen and current accepted carrier coordinates differ')
    if txt(carrier.get('coordinate_admission_status')) != 'frozen_r5b_reviewed_baseline_preserved':
        raise ValueError('carrier is not the expected frozen reviewed baseline point')
    frozen_claim_file = txt(carrier.get('point_claim_artifact_file'))
    frozen_claim_sha = txt(carrier.get('point_claim_artifact_sha256'))
    if not frozen_claim_file or not frozen_claim_sha:
        raise ValueError('frozen claim artifact path or hash is missing')
    locator = (f'source_record_id={carrier_id};parquet_row_1based={int(source_row)};'
               'fields=latitude_dadata,longitude_dadata;'
               f'lat_raw={raw_row.get("latitude_dadata")};lon_raw={raw_row.get("longitude_dadata")};'
               f'settlement_raw={raw_row.get("settlement")};region_raw={raw_row.get("region")}')
    return {
        'point_origin_file': str(raw_path),
        'point_origin_sha256': raw_sha256,
        'point_origin_locator': locator,
        'point_origin_kind': 'retrospective_continuity_from_raw2021_coordinate_previously_frozen_reviewed_assertion',
        'point_claim_artifact_file': frozen_claim_file,
        'point_claim_artifact_sha256': frozen_claim_sha,
        'supporting_carrier_point_origin_file': txt(carrier.get('point_origin_file')),
        'supporting_carrier_point_origin_sha256': txt(carrier.get('point_origin_sha256')),
        'supporting_carrier_point_origin_locator': txt(carrier.get('point_origin_locator')),
        'supporting_carrier_point_origin_kind': txt(carrier.get('point_origin_kind')),
        'supporting_carrier_point_claim_artifact_file': frozen_claim_file,
        'supporting_carrier_point_claim_artifact_sha256': frozen_claim_sha,
        'frozen_reviewed_claim_kind': txt(frozen_row.get('coordinate_kind')),
        'frozen_reviewed_claim_coordinate_source_record_id': txt(frozen_row.get('coordinate_source_record_id')),
        'frozen_reviewed_claim_locator': txt(carrier.get('point_origin_locator')),
        'frozen_reviewed_claim_latitude': frozen_lat,
        'frozen_reviewed_claim_longitude': frozen_lon,
    }


def component_index(graph: pd.DataFrame):
    adjacency: dict[str, list[str]] = defaultdict(list)
    year_by_node: dict[str, int] = {}
    edge_by_id = {}
    for edge in graph.itertuples(index=False):
        decision_id = txt(edge.decision_id)
        record = edge._asdict()
        if decision_id in edge_by_id:
            raise ValueError(f'duplicate graph decision ID {decision_id}')
        edge_by_id[decision_id] = record
        left, right = txt(edge.from_source_record_id), txt(edge.to_source_record_id)
        year_left, year_right = int(edge.from_year), int(edge.to_year)
        if (left in year_by_node and year_by_node[left] != year_left) or (
                right in year_by_node and year_by_node[right] != year_right):
            raise ValueError('graph node has conflicting year labels')
        year_by_node[left], year_by_node[right] = year_left, year_right
        if edge.relation == 'same_place' and edge.decision_status in STATUS_OK:
            adjacency[left].append(right)
            adjacency[right].append(left)
    components = {}
    for root in sorted(adjacency):
        if root in components:
            continue
        nodes = set([root]); queue = deque([root])
        while queue:
            node = queue.popleft()
            for neighbor in adjacency[node]:
                if neighbor not in nodes:
                    nodes.add(neighbor); queue.append(neighbor)
        component_id = min(nodes)
        for node in nodes:
            components[node] = component_id
    nodes_by_component: dict[str, set[str]] = defaultdict(set)
    for node, component_id in components.items():
        nodes_by_component[component_id].add(node)
    return adjacency, year_by_node, components, nodes_by_component, edge_by_id


def apply_carrier_point(target, target_evidence: dict, carrier: dict,
                        carrier_id: str, path_ids: list[str], case: dict,
                        lineage_roles_json: str) -> dict:
    row = dict(carrier)
    target_year = int(target['census_year'])
    population_quality = target_evidence.get('population_value_quality')
    row.update({
        'target_source_record_id': txt(target['source_record_id']),
        'target_year': target_year,
        'source_name': target_evidence.get('settlement_name'),
        'source_type': target_evidence.get('settlement_type'),
        'source_region': target_evidence.get('region_norm'),
        'source_file': target_evidence.get('source_file'),
        'source_row': target_evidence.get('source_row'),
        'source_sha256': target_evidence.get('source_sha256'),
        'source_locator': target_evidence.get('source_locator'),
        'source_okato_raw': target_evidence.get('okato'),
        'source_oktmo_raw': target_evidence.get('oktmo'),
        'target_population': target_evidence.get('population'),
        'target_population_scope': target_evidence.get('population_scope'),
        'target_population_value_quality': population_quality,
        'target_source_record_json': json.dumps(target, ensure_ascii=False, default=str, sort_keys=True),
        'target_source_evidence_json': json.dumps(target_evidence, ensure_ascii=False, sort_keys=True),
        'supporting_carrier_source_record_id': carrier_id,
        'supporting_carrier_admission_rule': carrier.get('admission_rule'),
        'supporting_carrier_coordinate_quality': carrier.get('coordinate_quality'),
        'supporting_carrier_coordinate_provenance': carrier.get('coordinate_provenance'),
        'supporting_carrier_provider_fias_binding_status': carrier.get('provider_fias_binding_status'),
        'admission_rule': 'stable_city_retrospective_accepted_2021_representative_point_reuse_v1',
        'coordinate_quality': 'accepted_2021_city_representative_point_reused_retrospectively',
        'coordinate_admission_status': 'staged_candidate_pending_root_review',
        'application_gate_status': 'passed_stable_city_reuse_gates_pending_root_review',
        'admission_allowed': False,
        'provider_binding_status': 'not_asserted_for_historical_target_by_representative_point_reuse',
        'provider_fias_binding_status': 'not_asserted_for_historical_target_by_representative_point_reuse',
        'coordinate_provenance': (
            'Exact accepted 2021 city carrier representative point reused retrospectively through '
            'the accepted same_place graph path; historical named GeoKladr 2011 point is retained '
            'as an unused alternative because its corroborating distance exceeds 1 km; no '
            'historical measurement, boundary comparability, or population-scope equivalence claimed.'
        ),
        'coordinate_measurement_date_unknown': True,
        'boundary_comparability_asserted': False,
        'population_scope_comparability_asserted': False,
        'direct_historical_coordinate_measurement': False,
        'application_inference_kind': 'stable_city_retrospective_representative_point_from_accepted_2021_city_carrier',
        'coordinate_application_family': 'stable_city_modern_carrier_point_reuse',
        'review_id': 'pending_independent_root_review_stable_city_reuse',
        'inference_modern_point_use_target_source_record_id': carrier_id,
        'inference_identity_path_decision_ids_json': json.dumps(path_ids),
        'inference_identity_path_from_source_record_id': txt(target['source_record_id']),
        'inference_identity_path_to_source_record_id': carrier_id,
        'inference_identity_path_edge_count': len(path_ids),
        'historical_named_point_candidate_status': 'held_distance_only_not_applied',
        'historical_named_point_candidate_hold_reason': EXPECTED_HOLD[0],
        'historical_named_point_to_carrier_distance_km_not_used': num(case.get('point_distance_km')),
        'historical_named_point_target_source_record_id': txt(target['source_record_id']),
        'lineage_event_roles_json': lineage_roles_json,
        'inference_coordinate_origin_carrier_target_source_record_id': carrier_id,
    })
    return row


def stage(base_path: Path, output_path: Path, *, cases_path: Path = DEFAULT_CASES,
          h_ledger_path: Path = DEFAULT_H_LEDGER, selected_path: Path = DEFAULT_SELECTED,
          selected_current_path: Path = DEFAULT_SELECTED_CURRENT,
          evidence_path: Path = DEFAULT_EVIDENCE, graph_path: Path = DEFAULT_GRAPH,
          blocked_path: Path = DEFAULT_BLOCKED,
          prior_holds_path: Path = DEFAULT_PRIOR_HOLDS,
          point_choice_review_path: Path | None = None,
          expected_review_sha256: str = POINT_CHOICE_REVIEW_SHA256) -> dict:
    inputs = {
        'base_accepted_points': Path(base_path), 'distance_only_cases': Path(cases_path),
        'historical_city_gate_ledger': Path(h_ledger_path), 'selected_R2': Path(selected_path),
        'selected_current_primary_application': Path(selected_current_path),
        'source_evidence_R2': Path(evidence_path), 'accepted_graph_R2': Path(graph_path),
        'blocked_targets': Path(blocked_path), 'prior_point_conflict_holds': Path(prior_holds_path),
    }
    for name, path in inputs.items():
        if not path.is_file():
            raise FileNotFoundError(f'{name} input missing: {path}')
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(f'new immutable output path required: {output_path}')

    cases = pd.read_csv(inputs['distance_only_cases'], dtype='string')
    if cases.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('distance-only case IDs must be unique')
    case_by_id = {txt(row.target_source_record_id): row._asdict() for row in cases.itertuples(index=False)}
    target_ids = set(case_by_id)
    h_ledger = pd.read_parquet(inputs['historical_city_gate_ledger'])
    h_rows = h_ledger[h_ledger.target_source_record_id.astype(str).isin(target_ids)]
    if h_rows.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('historical gate ledger has duplicate target IDs')
    h_by_id = {txt(row.target_source_record_id): row._asdict() for row in h_rows.itertuples(index=False)}

    base = pd.read_parquet(inputs['base_accepted_points'])
    if base.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('base point-use source IDs must be unique')
    base_by_id = {txt(row.target_source_record_id): row._asdict() for row in base.itertuples(index=False)}
    carrier_ids = {txt(case.get('carrier_source_record_id')) for case in case_by_id.values()}
    carriers = {rid: base_by_id[rid] for rid in carrier_ids if rid in base_by_id
                and int(base_by_id[rid]['target_year']) == 2021}
    if not carriers:
        raise ValueError('no exact accepted 2021 carrier rows found in base')

    selected = pd.read_parquet(inputs['selected_R2'], columns=SELECTED_COLUMNS)
    selected['source_record_id'] = selected.source_record_id.astype('string').str.strip()
    if selected.source_record_id.duplicated().any():
        raise ValueError('selected R2 source IDs must be unique')
    selected_by_id = {txt(row.source_record_id): row._asdict() for row in selected.itertuples(index=False)}
    selected_current = pd.read_parquet(inputs['selected_current_primary_application'],
                                       columns=SELECTED_COLUMNS)
    selected_current['source_record_id'] = selected_current.source_record_id.astype('string').str.strip()
    if selected_current.source_record_id.duplicated().any():
        raise ValueError('current primary selected source IDs must be unique')
    selected_current_by_id = {txt(row.source_record_id): row._asdict()
                              for row in selected_current.itertuples(index=False)}
    needed_evidence = target_ids | carrier_ids
    evidence_by_id = load_evidence(inputs['source_evidence_R2'], needed_evidence)
    graph = pd.read_parquet(inputs['accepted_graph_R2'])
    _, year_by_node, component_of, nodes_by_component, edge_by_id = component_index(graph)
    blocked = read_blocked(inputs['blocked_targets'])
    prior = pd.read_parquet(inputs['prior_point_conflict_holds'])
    prior_blocked = {txt(value) for value in prior.target_source_record_id if txt(value)}
    blocked |= prior_blocked
    point_review_rows, point_review_pin = load_point_choice_approvals(
        point_choice_review_path, case_by_id, carriers, inputs, blocked, expected_review_sha256
    )
    raw_source_path = DEFAULT_RAW_2021_SOURCE
    raw_source_sha = None
    raw_rows_by_carrier = {}
    frozen_rows_by_carrier = {}
    raw_recovery_errors = {}
    if point_choice_review_path is not None:
        review_json_path = Path(point_choice_review_path)
        inputs['point_choice_review_json'] = review_json_path
        inputs['point_choice_review_rows'] = review_json_path.parent / 'row_level_point_choice_review.csv'
        inputs['point_choice_review_receipt'] = review_json_path.parent / 'receipt.json'
        inputs['raw_2021_carrier_source'] = raw_source_path
        # Only the frozen reviewed assertion carrier needs this provenance recovery.
        frozen_carriers = {rid: carrier for rid, carrier in carriers.items()
                           if txt(carrier.get('point_origin_kind')) == 'reviewed_frozen_assertion'}
        if frozen_carriers:
            if not raw_source_path.is_file():
                raw_recovery_errors.update({rid: 'raw_2021_carrier_source_missing' for rid in frozen_carriers})
            else:
                raw_source_sha = sha(raw_source_path)
                if raw_source_sha == RAW_2021_SOURCE_SHA256:
                    raw_data = pd.read_parquet(raw_source_path, columns=[
                        'settlement', 'region', 'latitude_dadata', 'longitude_dadata'
                    ])
                    for rid, carrier in frozen_carriers.items():
                        suffix = re.search(r':parquet:(\d+)$', rid)
                        row_number = int(suffix.group(1)) if suffix else None
                        stored_source_row = num(carrier.get('source_row'))
                        if row_number is None or (stored_source_row is not None and stored_source_row != row_number):
                            raw_recovery_errors[rid] = 'raw_source_row_locator_missing_or_invalid'
                            continue
                        offset = int(row_number) - 1
                        if offset >= len(raw_data):
                            raw_recovery_errors[rid] = 'raw_source_row_locator_out_of_range'
                            continue
                        raw_rows_by_carrier[rid] = raw_data.iloc[offset].to_dict()
                        claim_file = txt(carrier.get('point_claim_artifact_file'))
                        try:
                            frozen_data = pd.read_csv(claim_file, dtype='string')
                            frozen_match = frozen_data[
                                frozen_data.target_source_record_id.astype(str).eq(rid)
                            ]
                            if len(frozen_match) != 1:
                                raw_recovery_errors[rid] = 'frozen_review_claim_row_not_unique'
                            else:
                                frozen_rows_by_carrier[rid] = frozen_match.iloc[0].to_dict()
                        except Exception:
                            raw_recovery_errors[rid] = 'frozen_review_claim_file_unreadable'
                else:
                    raw_recovery_errors.update({rid: 'raw_2021_carrier_source_hash_mismatch'
                                                for rid in frozen_carriers})
    origin_hash_cache: dict[str, str] = {}

    proposed, held = [], []
    gate_rows = []
    for target_id, case in case_by_id.items():
        hrow = h_by_id.get(target_id)
        reasons = []
        if hrow is None:
            reasons.append('historical_distance_gate_row_missing')
        else:
            actual_reasons = exact_gate_hold(hrow.get('hold_reasons_json'))
            if actual_reasons != EXPECTED_HOLD:
                reasons.append('historical_gate_ledger_not_exact_distance_only_hold')
            if bool(hrow.get('gate_passed')):
                reasons.append('historical_gate_ledger_unexpectedly_passed')
        if exact_gate_hold(case.get('hold_reasons_json')) != EXPECTED_HOLD:
            reasons.append('distance_diagnostic_not_exact_expected_hold')
        review_row = point_review_rows.get(target_id)
        explicitly_approved_override = review_row is not None
        if target_id in blocked and not explicitly_approved_override:
            reasons.append('explicit_or_prior_actual_point_conflict_block')

        target = selected_by_id.get(target_id)
        if target is None:
            reasons.append('exact_target_missing_from_selected_R2')
        else:
            target_year = int(target['census_year'])
            if target_year not in {2002, 2010}:
                reasons.append('target_year_outside_2002_2010_scope')
            if target_id in base_by_id:
                reasons.append('target_already_has_a_base_point_use')
            primary_target = selected_current_by_id.get(target_id)
            if primary_target is None:
                reasons.append('exact_target_missing_from_current_primary_selected_source')
            else:
                for field in ('census_year', 'settlement_name', 'settlement_type',
                              'source_file', 'source_row', 'population', 'population_value_quality'):
                    if norm(primary_target.get(field)) != norm(target.get(field)):
                        reasons.append('current_primary_selected_target_changed_' + field)
        target_evidence = evidence_by_id.get(target_id)
        if target is not None:
            reasons.extend(evidence_holds(target_evidence, int(target['census_year'])))

        carrier_id = txt(case.get('carrier_source_record_id'))
        carrier = carriers.get(carrier_id)
        if carrier is None:
            reasons.append('exact_accepted_2021_carrier_missing_from_base')
        carrier_evidence = evidence_by_id.get(carrier_id)
        if carrier is not None:
            reasons.extend(evidence_holds(carrier_evidence, 2021))
            reasons.extend(verify_carrier_origin(carrier, origin_hash_cache))
            if carrier.get('coordinate_admission_status') not in {
                'reviewed_rule_accepted', 'frozen_r5b_reviewed_baseline_preserved',
                'accepted', 'accepted_current_point_rule', 'reviewed_rule_accepted_current',
            }:
                reasons.append('carrier_not_an_accepted_point_use')
        origin_recovery = None
        if (carrier is not None and point_choice_review_path is not None
                and txt(carrier.get('point_origin_kind')) == 'reviewed_frozen_assertion'):
            if carrier_id in raw_recovery_errors:
                reasons.append('frozen_current_coordinate_origin_recovery_failed_' + raw_recovery_errors[carrier_id])
            else:
                try:
                    origin_recovery = recovered_frozen_source_origin(
                        carrier, raw_rows_by_carrier[carrier_id], frozen_rows_by_carrier[carrier_id],
                        raw_source_path, raw_source_sha or ''
                    )
                except (KeyError, TypeError, ValueError) as error:
                    reasons.append('frozen_current_coordinate_origin_recovery_failed_' + str(error).replace(' ', '_'))
        if target is not None and target_evidence and carrier_evidence:
            for label, left, right in (
                ('name', target_evidence.get('settlement_name'), carrier_evidence.get('settlement_name')),
                ('type', target_evidence.get('settlement_type'), carrier_evidence.get('settlement_type')),
                ('region', target_evidence.get('region_norm'), carrier_evidence.get('region_norm')),
            ):
                if norm(left) != norm(right):
                    reasons.append('target_carrier_exact_' + label + '_mismatch')

        path_ids = []
        try:
            path_ids = json.loads(hrow.get('identity_path_decision_ids_json', '[]')) if hrow else []
        except (TypeError, json.JSONDecodeError):
            reasons.append('historical_identity_path_json_malformed')
        if not isinstance(path_ids, list):
            reasons.append('historical_identity_path_not_list')
            path_ids = []
        if carrier is not None:
            reasons.extend(validate_path(target_id, carrier_id, path_ids, edge_by_id))
            target_component = component_of.get(target_id)
            if target_component is None or target_component != component_of.get(carrier_id):
                reasons.append('target_carrier_not_in_same_accepted_graph_component')
            else:
                component_nodes = nodes_by_component[target_component]
                years = Counter(year_by_node[node] for node in component_nodes)
                if any(count > 1 for count in years.values()):
                    reasons.append('accepted_same_place_component_has_same_year_collision')
                component_carriers = [node for node in component_nodes
                                      if year_by_node.get(node) == 2021 and node in carriers]
                if component_carriers != [carrier_id]:
                    reasons.append('component_does_not_have_exactly_one_delta_city_carrier')

        try:
            roles_json = hrow.get('lineage_event_roles_json', '[]') if hrow else '[]'
            reasons.extend(event_holds(roles_json))
        except AttributeError:
            reasons.append('lineage_event_roles_missing')

        distance = num(case.get('point_distance_km'))
        if distance is None or distance <= 1.0:
            reasons.append('historical_alternative_not_documented_as_over_1km')
        if case.get('carrier_point_accepted_current') not in (True, 'True', 'true', '1'):
            reasons.append('diagnostic_does_not_assert_accepted_current_carrier_point')

        # Collision protection applies to all base point uses and to the proposal set.
        if target is not None and carrier is not None:
            point_key = (int(target['census_year']), num(carrier.get('latitude')), num(carrier.get('longitude')))
            if None in point_key[1:]:
                reasons.append('carrier_point_invalid_for_target_year')
            else:
                collisions = base[(base.target_year.astype(int).eq(point_key[0]))
                                  & base.latitude.astype(float).eq(point_key[1])
                                  & base.longitude.astype(float).eq(point_key[2])
                                  & base.target_source_record_id.astype(str).ne(target_id)]
                if len(collisions):
                    reasons.append('same_year_exact_coordinate_collision_with_base_use')

        reasons = list(dict.fromkeys(reasons))
        record = {
            'target_source_record_id': target_id,
            'target_year': int(target['census_year']) if target else int(case.get('year')),
            'settlement_name': target_evidence.get('settlement_name') if target_evidence else case.get('settlement_name'),
            'population': target_evidence.get('population') if target_evidence else case.get('population'),
            'population_value_quality': target_evidence.get('population_value_quality') if target_evidence else None,
            'carrier_source_record_id': carrier_id,
            'historical_named_point_distance_km': distance,
            'historical_named_point_hold_reason': EXPECTED_HOLD[0],
            'identity_path_decision_ids_json': json.dumps(path_ids),
            'lineage_event_roles_json': txt(roles_json),
            'blocked_by_prior_point_conflict': target_id in blocked,
            'blocked_conflict_resolution_approved': explicitly_approved_override,
            'frozen_current_coordinate_origin_recovered': origin_recovery is not None,
            'point_choice_review_id': point_review_pin.get('review_id') if explicitly_approved_override else None,
            'point_choice_review_sha256': point_review_pin.get('review_sha256') if explicitly_approved_override else None,
            'point_choice_review_resolution': txt(review_row.get('point_choice_reason')) if review_row else None,
            'gate_passed': not reasons,
            'hold_reasons_json': json.dumps(reasons, ensure_ascii=False),
        }
        gate_rows.append(record)
        if reasons:
            held.append(record)
            continue
        proposal = apply_carrier_point(target, target_evidence, carrier, carrier_id,
                                       path_ids, case, txt(roles_json))
        if review_row:
            proposal.update({
                'point_choice_review_id': point_review_pin['review_id'],
                'point_choice_review_sha256': point_review_pin['review_sha256'],
                'point_choice_review_row_level_sha256': point_review_pin['row_level_sha256'],
                'point_choice_review_decision': 'APPROVE_BOUNDED_MODERN_POINT_REUSE',
                'point_choice_review_resolution': txt(review_row.get('point_choice_reason')),
                'blocked_conflict_resolution_approved': True,
                'blocked_conflict_resolution_rationale': (
                    'Independent point-choice review found this historical target reuses the exact '
                    'already accepted current city P625 carrier point; the reviewed origin file, '
                    'SHA-256, locator, provider QID, coordinates, target ID and carrier ID match '
                    'the supplied current accepted base. Only the explicit prior point-conflict '
                    'block is resolved; all other source, graph, event, origin and collision gates remain.'
                ),
            })
        if origin_recovery:
            proposal.update(origin_recovery)
            proposal['coordinate_provenance'] += (
                ' Origin recovery reopens the exact 2021 raw source row underlying the previously '
                'frozen reviewed assertion; identical coordinates are confirmed, with no measurement '
                'date assigned and no new geocoding or provider/FIAS binding inferred.'
            )
        proposed.append(proposal)

    # Hold every exact same-year duplicate among proposed rows; do not choose a winner.
    collision_groups: dict[tuple[int, float, float], list[int]] = defaultdict(list)
    for index, row in enumerate(proposed):
        collision_groups[(int(row['target_year']), float(row['latitude']),
                          float(row['longitude']))].append(index)
    collision_indexes = {index for indexes in collision_groups.values() if len(indexes) > 1
                         for index in indexes}
    if collision_indexes:
        for index in sorted(collision_indexes):
            row = proposed[index]
            hold = {'target_source_record_id': row['target_source_record_id'],
                    'target_year': row['target_year'],
                    'carrier_source_record_id': row['supporting_carrier_source_record_id'],
                    'hold_reasons_json': json.dumps(['same_year_exact_coordinate_collision_among_candidates'])}
            held.append(hold)
            for gate in gate_rows:
                if gate['target_source_record_id'] == row['target_source_record_id']:
                    gate['gate_passed'] = False
                    gate['hold_reasons_json'] = hold['hold_reasons_json']
                    break
        proposed = [row for index, row in enumerate(proposed) if index not in collision_indexes]

    output_path.mkdir(parents=True)
    staged_path = output_path / 'staged_point_uses.parquet'
    held_path = output_path / 'held_targets.parquet'
    ledger_path = output_path / 'gate_ledger.parquet'
    staged_frame = pd.DataFrame(proposed)
    held_frame = pd.DataFrame(held)
    gate_frame = pd.DataFrame(gate_rows)
    staged_frame.to_parquet(staged_path, index=False)
    held_frame.to_parquet(held_path, index=False)
    gate_frame.to_parquet(ledger_path, index=False)
    receipt = {
        'status': 'stable_city_modern_point_reuse_staged_pending_independent_review',
        'input_hashes': {key: {'path': str(path), 'sha256': sha(path) if path.is_file() else None}
                         for key, path in inputs.items()},
        'input_case_rows': int(len(cases)),
        'exact_H_distance_only_rows': int(sum(exact_gate_hold(h_by_id.get(rid, {}).get('hold_reasons_json')) == EXPECTED_HOLD for rid in target_ids)),
        'base_accepted_point_rows': int(len(base)),
        'target_rows': int(len(gate_frame)),
        'blocked_target_rows': int(gate_frame.blocked_by_prior_point_conflict.sum()) if len(gate_frame) else 0,
        'independently_approved_block_resolution_rows': int(gate_frame.blocked_conflict_resolution_approved.sum()) if len(gate_frame) else 0,
        'staged_rows': int(len(staged_frame)),
        'held_rows': int(len(held_frame)),
        'staged_population_by_year': staged_frame.groupby('target_year').target_population.sum().to_dict() if len(staged_frame) else {},
        'held_reasons': dict(Counter(reason for val in held_frame.get('hold_reasons_json', [])
                                     for reason in json.loads(val))) if len(held_frame) else {},
        'staged_admission_allowed_all_false': bool(len(staged_frame) == 0 or not staged_frame.admission_allowed.any()),
        'historical_GeoKladr_alternative_applied': False,
        'point_origin_source': 'copied byte-for-byte from exact accepted 2021 carrier row',
        'point_choice_review': point_review_pin if point_choice_review_path is not None else None,
        'outputs': {p.name: {'path': str(p), 'rows': int(len(pd.read_parquet(p))), 'sha256': sha(p)}
                    for p in (staged_path, held_path, ledger_path)},
        'limits': [
            'Candidate staging only; admission is false pending independent review.',
            'The failed-distance GeoKladr point is retained only as a rejected alternative and is not applied.',
            'Modern representative point reuse does not assert a historical measurement date or point location.',
            'Boundary and population-scope comparability remain unasserted; source population and quality remain as reported.',
            'Prior actual point-conflict targets and all explicit blocked IDs remain held.',
        ],
    }
    receipt_path = output_path / 'receipt.json'
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True,
                        help='frozen accepted_current_city_delta_v1 point uses')
    parser.add_argument('--output', type=Path, required=True,
                        help='new immutable candidate output directory')
    parser.add_argument('--point-choice-review', type=Path,
                        help='optional pinned independent point-choice review JSON')
    args = parser.parse_args()
    print(json.dumps(stage(args.base, args.output,
                           point_choice_review_path=args.point_choice_review),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
