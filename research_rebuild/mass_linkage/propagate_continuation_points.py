"""Stage reviewed graph-continuity point uses for explicit new 2021 carriers.

This is a parameterized candidate stage, not an admission step. It uses only
accepted same-place graph paths and accepted 2021 point rows whose source IDs
appear in a caller-supplied carrier delta. Historical source metadata and
modern point-origin metadata remain separate.
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

STATUS_OK = {
    'checked_rule_accepted',
    'checked_rule_accepted_redundant_graph_connectivity_effect',
    'accepted_rule_family_after_independent_sample_review',
    'case_specific_independent_review_accepted',
    'case_review_accepted',
    'independent_case_review_accepted',
    'accepted_case_specific',
}
POINT_ORIGIN_FIELDS = [
    'point_origin_file', 'point_origin_sha256', 'point_origin_locator', 'point_origin_kind',
    'point_claim_artifact_file', 'point_claim_artifact_sha256',
]
ACCEPTED_COLUMNS = [
    'target_source_record_id', 'target_year', 'latitude', 'longitude', 'coordinate_quality',
    'coordinate_source', 'coordinate_source_record_id', 'coordinate_provider',
    'coordinate_provider_id', 'coordinate_provenance', 'admission_rule',
    'provider_binding_status', 'provider_fias_binding_status', 'coordinate_admission_status',
    'coordinate_measurement_date_unknown', 'boundary_comparability_asserted',
    'coordinate_provider_family', 'provider_query_receipt_missing',
    'coordinate_uncertainty_flags_json', 'coordinate_application_family', 'review_id',
    'application_inference_kind', 'direct_historical_coordinate_measurement',
    'population_scope_comparability_asserted', 'coordinate_source_sha256',
    'coordinate_source_locator', 'coordinate_source_file', 'coordinate_source_origin',
    'coordinate_source_input_artifact_sha256', 'coordinate_source_date',
    'coordinate_source_latitude_raw', 'coordinate_source_longitude_raw',
    'inference_modern_point_use_target_source_record_id',
    'inference_identity_path_decision_ids_json', 'inference_identity_path_from_source_record_id',
    'inference_identity_path_to_source_record_id', 'inference_identity_path_edge_count',
    *POINT_ORIGIN_FIELDS,
]
EVIDENCE_COLUMNS = ['source_record_id', 'census_year', 'source_evidence_json']
SELECTED_COLUMNS = [
    'source_record_id', 'census_year', 'settlement_name', 'settlement_type',
    'source_name_raw', 'source_file', 'source_sheet', 'source_row', 'source_sha256',
    'source_locator', 'source_native_id', 'source_path', 'population', 'population_scope',
    'population_value_quality', 'is_additive_settlement_record', 'entity_grain_status',
    'region_raw', 'region_norm', 'district_raw', 'municipality_raw', 'okato', 'oktmo',
]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def txt(value) -> str:
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def valid_wgs84(lat, lon) -> bool:
    a, b = number(lat), number(lon)
    return a is not None and b is not None and -90 <= a <= 90 and -180 <= b <= 180


def accepted_same_place_edges(graph: pd.DataFrame) -> pd.DataFrame:
    return graph.loc[graph.relation.eq('same_place') & graph.decision_status.isin(STATUS_OK)].copy()


def event_codes(events: list[dict]) -> dict[str, list[dict]]:
    """Map literal native OKTMO values to source-event roles; never pad/repair."""
    out: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        date = txt(event.get('source_asserted_effective_date'))
        match = re.search(r'(?:19|20)\d{2}', date)
        year = int(match.group()) if match else None
        codes = []
        for key, value in event.items():
            if 'settlement_id' not in key or not value:
                continue
            code_match = re.fullmatch(r'RU-OKTMO-(\d+)', str(value))
            if code_match:
                codes.append(code_match.group(1))
        for code in set(codes):
            out[code].append({
                'event_id': txt(event.get('event_id')),
                'year': year,
                'event_type': txt(event.get('event_type')),
            })
    return out


def read_blocked_targets(path: Path) -> set[str]:
    """Read exact blocked IDs from parquet, CSV, JSON, or newline-delimited text."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.parquet':
        frame = pd.read_parquet(path)
        column = next((c for c in ('target_source_record_id', 'blocked_target_source_record_id',
                                   'source_record_id') if c in frame.columns), None)
        if column is None:
            raise ValueError('blocked-target parquet needs a source-record ID column')
        return {txt(x) for x in frame[column] if txt(x)}
    if suffix == '.csv':
        frame = pd.read_csv(path, dtype='string')
        column = next((c for c in ('target_source_record_id', 'blocked_target_source_record_id',
                                   'source_record_id') if c in frame.columns), None)
        if column is None:
            raise ValueError('blocked-target CSV needs a source-record ID column')
        return {txt(x) for x in frame[column] if txt(x)}
    if suffix == '.json':
        value = json.loads(path.read_text())
        if isinstance(value, dict):
            value = value.get('blocked_target_source_record_ids', value.get('target_source_record_ids', []))
        if not isinstance(value, list):
            raise ValueError('blocked-target JSON must contain a list of exact source-record IDs')
        return {txt(x) for x in value if txt(x)}
    return {line.strip() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')}


def load_source_evidence(path: Path, needed_ids: set[str]) -> dict[tuple[str, int], dict]:
    if not needed_ids:
        return {}
    frame = pd.read_parquet(path, columns=EVIDENCE_COLUMNS,
                            filters=[('source_record_id', 'in', sorted(needed_ids))])
    result = {}
    for row in frame.itertuples(index=False):
        key = (txt(row.source_record_id), int(row.census_year))
        if key in result:
            raise ValueError(f'duplicate exact source-evidence key: {key}')
        result[key] = json.loads(row.source_evidence_json)
    return result


def source_conflicts(evidence: dict | None) -> list[str]:
    if not evidence:
        return ['source_evidence_missing']
    reasons = []
    if evidence.get('legacy_identity_conflict'):
        reasons.append('legacy_identity_conflict')
    if evidence.get('legacy_same_year_collision'):
        reasons.append('legacy_same_year_collision')
    if evidence.get('is_federal_aggregate'):
        reasons.append('source_is_federal_aggregate')
    if evidence.get('is_additive_settlement_record') is not True:
        reasons.append('source_not_confirmed_additive_physical_row')
    if not txt(evidence.get('settlement_name')) or not txt(evidence.get('settlement_type')):
        reasons.append('source_name_or_type_missing')
    grain = txt(evidence.get('entity_grain_status')).lower()
    if grain and any(term in grain for term in ('aggregate', 'parent', 'shared_okato', 'municipal_total')):
        reasons.append('source_grain_aggregate_or_shared')
    return reasons


def stage_point_use(target, target_evidence, carrier, carrier_id, carrier_evidence,
                    path_decision_ids: list[str]) -> dict:
    """Copy carrier point-origin claims while restoring target source provenance."""
    row = carrier.copy()
    source = target_evidence or {}
    row.update({
        'target_source_record_id': txt(target.source_record_id),
        'target_year': int(target.census_year),
        'source_name': txt(source.get('settlement_name') or target.settlement_name),
        'target_source_name_raw': txt(source.get('source_name_raw') or target.source_name_raw),
        'source_type': txt(source.get('settlement_type') or target.settlement_type),
        'source_region': txt(source.get('region_norm') or target.region_norm),
        'source_file': txt(source.get('source_file') or target.source_file),
        'source_row': source.get('source_row', target.source_row),
        'source_sha256': txt(source.get('source_sha256') or target.source_sha256),
        'source_locator': txt(source.get('source_locator') or target.source_locator),
        'source_okato_raw': txt(source.get('okato') or target.okato),
        'source_oktmo_raw': txt(source.get('oktmo') or target.oktmo),
        'coordinate_admission_status': 'staged_candidate_pending_root_review',
        'application_gate_status': 'passed_graph_continuity_gates_pending_root_review',
        'admission_allowed': False,
        'coordinate_provenance': txt(carrier.get('coordinate_provenance')) +
            '; assigned to this historical source through accepted same_place graph continuity; no historical measurement claimed',
        'coordinate_measurement_date_unknown': True,
        'boundary_comparability_asserted': False,
        'population_scope_comparability_asserted': False,
        'direct_historical_coordinate_measurement': False,
        'application_inference_kind': 'retrospective_continuity_from_accepted_2021_point',
        'inference_modern_point_use_target_source_record_id': carrier_id,
        'inference_identity_path_decision_ids_json': json.dumps(path_decision_ids),
        'inference_identity_path_from_source_record_id': txt(target.source_record_id),
        'inference_identity_path_to_source_record_id': carrier_id,
        'inference_identity_path_edge_count': len(path_decision_ids),
        'coordinate_application_family': 'R_graph_accepted_2021_carrier_continuity',
        'review_id': 'pending_root_review_graph_continuity',
        'provider_fias_binding_status': 'not_asserted_for_historical_target_by_graph_continuity',
        'target_source_evidence_json': json.dumps(source, ensure_ascii=False, sort_keys=True),
    })
    # The carrier's exact point origin, coordinate source, IDs, hashes, and
    # original source-coordinate text remain untouched above.
    return row


def build(accepted_path: Path, carrier_delta_path: Path, graph_path: Path,
          selected_path: Path, evidence_path: Path, events_path: Path,
          blocked_targets_path: Path, output_path: Path) -> dict:
    paths = {
        'accepted': Path(accepted_path), 'carrier_delta': Path(carrier_delta_path),
        'graph': Path(graph_path), 'selected': Path(selected_path),
        'evidence': Path(evidence_path), 'events': Path(events_path),
        'blocked_targets': Path(blocked_targets_path),
    }
    for key, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f'{key} input not found: {path}')
    output_path = Path(output_path)
    if output_path.exists() and any(output_path.iterdir()):
        raise FileExistsError(f'output path is not empty: {output_path}')

    accepted = pd.read_parquet(paths['accepted'], columns=ACCEPTED_COLUMNS)
    if accepted.target_source_record_id.astype(str).duplicated().any():
        raise ValueError('accepted target_source_record_id values must be unique')
    accepted_ids = set(accepted.target_source_record_id.astype(str))
    accepted_by_id = {txt(row.target_source_record_id): row._asdict()
                      for row in accepted.itertuples(index=False)}
    carrier_delta = pd.read_parquet(paths['carrier_delta'])
    if 'target_source_record_id' not in carrier_delta.columns:
        raise ValueError('carrier delta must contain target_source_record_id')
    carrier_ids_series = carrier_delta.target_source_record_id.astype('string').fillna('').str.strip()
    if carrier_ids_series.eq('').any() or carrier_ids_series.duplicated().any():
        raise ValueError('carrier delta IDs must be nonblank and unique')
    carrier_ids = set(carrier_ids_series.astype(str))
    carriers = {rid: accepted_by_id[rid] for rid in carrier_ids if rid in accepted_by_id
                and int(accepted_by_id[rid]['target_year']) == 2021}

    selected = pd.read_parquet(paths['selected'], columns=SELECTED_COLUMNS)
    selected = selected[selected.census_year.isin([2002, 2010, 2021])].copy()
    if selected.source_record_id.astype(str).duplicated().any():
        raise ValueError('selected source_record_id values must be unique')
    selected_by_id = {txt(row.source_record_id): row for row in selected.itertuples(index=False)}
    missing = selected[selected.census_year.isin([2002, 2010])
                       & ~selected.source_record_id.astype(str).isin(accepted_ids)].copy()
    targets = {txt(x) for x in missing.source_record_id}
    evidence_by = load_source_evidence(paths['evidence'], targets | carrier_ids)
    events = json.loads(paths['events'].read_text())
    if not isinstance(events, list):
        raise ValueError('lineage-event input must be a JSON list')
    event_by_code = event_codes(events)
    blocked_ids = read_blocked_targets(paths['blocked_targets'])

    graph = pd.read_parquet(paths['graph'])
    edges = accepted_same_place_edges(graph)
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    year_by_node: dict[str, int] = {}
    edge_by_id: dict[str, dict] = {}
    for edge in edges.itertuples(index=False):
        a, b = txt(edge.from_source_record_id), txt(edge.to_source_record_id)
        ya, yb, did = int(edge.from_year), int(edge.to_year), txt(edge.decision_id)
        if ((a in year_by_node and year_by_node[a] != ya)
                or (b in year_by_node and year_by_node[b] != yb)):
            raise ValueError('accepted graph node has inconsistent year labels')
        year_by_node[a], year_by_node[b] = ya, yb
        if did in edge_by_id:
            raise ValueError(f'duplicate accepted graph decision ID: {did}')
        edge_by_id[did] = edge._asdict()
        adjacency[a].append((b, did)); adjacency[b].append((a, did))
    for node in adjacency:
        adjacency[node].sort(key=lambda x: (x[0], x[1]))

    component_of: dict[str, str] = {}
    parent: dict[str, str | None] = {}
    parent_edge: dict[str, str] = {}
    depth: dict[str, int] = {}
    component_nodes: dict[str, list[str]] = {}
    for root in sorted(adjacency):
        if root in component_of:
            continue
        component_id = root
        component_of[root] = component_id
        parent[root] = None; depth[root] = 0
        nodes = []; queue = deque([root])
        while queue:
            current = queue.popleft(); nodes.append(current)
            for neighbor, decision_id in adjacency[current]:
                if neighbor in component_of:
                    continue
                component_of[neighbor] = component_id
                parent[neighbor] = current
                parent_edge[neighbor] = decision_id
                depth[neighbor] = depth[current] + 1
                queue.append(neighbor)
        component_nodes[component_id] = nodes
    component_year_collision = {}
    component_carriers: dict[str, list[str]] = defaultdict(list)
    for component_id, nodes in component_nodes.items():
        counts = Counter(year_by_node[node] for node in nodes)
        component_year_collision[component_id] = sorted(y for y, count in counts.items() if count > 1)
        component_carriers[component_id] = sorted(
            node for node in nodes if year_by_node[node] == 2021 and node in carriers
        )

    def path_decisions(start: str, end: str) -> list[str]:
        left, right = start, end
        path_left, path_right = [], []
        while depth[left] > depth[right]:
            path_left.append(parent_edge[left]); left = parent[left]
        while depth[right] > depth[left]:
            path_right.append(parent_edge[right]); right = parent[right]
        while left != right:
            path_left.append(parent_edge[left]); path_right.append(parent_edge[right])
            left, right = parent[left], parent[right]
        return path_left + path_right[::-1]

    # Same-year exact point collision index across already accepted point uses.
    accepted_point_index: dict[tuple[int, float, float], list[str]] = defaultdict(list)
    for row in accepted.itertuples(index=False):
        lat, lon = number(row.latitude), number(row.longitude)
        if lat is not None and lon is not None:
            accepted_point_index[(int(row.target_year), lat, lon)].append(txt(row.target_source_record_id))

    proposals, holds = [], []
    # Many thousands of targets share the same immutable raw asset. Measure
    # its hash once per run, without caching acceptance across input versions.
    origin_hash_cache = {}
    for target in missing.itertuples(index=False):
        target_id, target_year = txt(target.source_record_id), int(target.census_year)
        reasons = []
        component = component_of.get(target_id)
        if target_id in blocked_ids:
            reasons.append('explicit_blocked_target_id')
        if component is None:
            reasons.append('target_not_in_accepted_same_place_graph')
            nodes = []
        else:
            nodes = component_nodes[component]
            if component_year_collision.get(component):
                reasons.append('accepted_graph_component_has_same_year_collision')
        target_evidence = evidence_by.get((target_id, target_year))
        reasons.extend(source_conflicts(target_evidence))
        target_identity = json.loads(json.dumps(target_evidence)) if target_evidence else {}
        # All selected and evidence values are source records; reject endpoint
        # year drift rather than silently identifying a similar row.
        if target_evidence and int(target_evidence.get('census_year', target_year)) != target_year:
            reasons.append('target_source_evidence_year_mismatch')

        candidate_carriers = component_carriers.get(component, []) if component else []
        if len(candidate_carriers) != 1:
            reasons.append('component_does_not_have_exactly_one_delta_accepted_2021_carrier')
        if reasons:
            holds.append({'target_source_record_id': target_id, 'target_year': target_year,
                          'component_id': component or '',
                          'hold_reasons_json': json.dumps(list(dict.fromkeys(reasons)), ensure_ascii=False)})
            continue

        carrier_id = candidate_carriers[0]
        carrier = carriers[carrier_id]
        carrier_evidence = evidence_by.get((carrier_id, 2021))
        reasons.extend(source_conflicts(carrier_evidence))
        if carrier_evidence and int(carrier_evidence.get('census_year', 2021)) != 2021:
            reasons.append('carrier_source_evidence_year_mismatch')
        if not any(txt(carrier.get(field)) for field in POINT_ORIGIN_FIELDS):
            reasons.append('accepted_2021_carrier_missing_canonical_point_origin')
        origin_paths = {}
        for file_field, hash_field in (('point_origin_file', 'point_origin_sha256'),
                                       ('point_claim_artifact_file', 'point_claim_artifact_sha256')):
            file_name, expected = txt(carrier.get(file_field)), txt(carrier.get(hash_field))
            if file_name:
                if not expected:
                    reasons.append('accepted_2021_carrier_origin_hash_missing')
                elif file_name not in origin_paths:
                    origin_paths[file_name] = expected
            elif expected:
                reasons.append('accepted_2021_carrier_origin_file_missing')
        for file_name, expected in origin_paths.items():
            origin_path = Path(file_name)
            if file_name not in origin_hash_cache:
                origin_hash_cache[file_name] = sha(origin_path) if origin_path.is_file() else None
            if origin_hash_cache[file_name] != expected:
                reasons.append('accepted_2021_carrier_origin_asset_hash_mismatch')
                break
        if not valid_wgs84(carrier.get('latitude'), carrier.get('longitude')):
            reasons.append('accepted_2021_carrier_point_invalid')

        native_oktmo = txt(getattr(selected_by_id.get(carrier_id), 'oktmo', None))
        for event in event_by_code.get(native_oktmo, []) if native_oktmo else []:
            event_year = event.get('year')
            if event_year is None or target_year <= int(event_year) <= 2021:
                reasons.append('exact_native_carrier_oktmo_lineage_event_' + (event['event_id'] or 'unnamed'))
        carrier_point_key = (target_year, number(carrier.get('latitude')), number(carrier.get('longitude')))
        point_collisions = [sid for sid in accepted_point_index.get(carrier_point_key, []) if sid != target_id]
        if point_collisions:
            reasons.append('same_year_exact_coordinate_collision_with_accepted_target')
        reasons = list(dict.fromkeys(reasons))
        if reasons:
            holds.append({'target_source_record_id': target_id, 'target_year': target_year,
                          'component_id': component, 'carrier_target_source_record_id': carrier_id,
                          'hold_reasons_json': json.dumps(reasons, ensure_ascii=False),
                          'same_year_collision_source_record_ids_json': json.dumps(point_collisions)})
            continue

        decisions = path_decisions(target_id, carrier_id)
        current = target_id
        for decision_id in decisions:
            edge = edge_by_id[decision_id]
            if current == txt(edge['from_source_record_id']):
                current = txt(edge['to_source_record_id'])
            elif current == txt(edge['to_source_record_id']):
                current = txt(edge['from_source_record_id'])
            else:
                raise AssertionError(f'nonchaining path for {target_id}')
        if current != carrier_id:
            raise AssertionError('accepted identity path did not terminate at exact carrier')
        proposals.append(stage_point_use(target, target_evidence, carrier, carrier_id,
                                         carrier_evidence, decisions))

    # Proposals may not collide with one another in the same target year.
    staged_collision_keys = defaultdict(list)
    for index, proposal in enumerate(proposals):
        key = (int(proposal['target_year']), number(proposal.get('latitude')),
               number(proposal.get('longitude')))
        staged_collision_keys[key].append(index)
    collision_indexes = {i for indexes in staged_collision_keys.values() if len(indexes) > 1 for i in indexes}
    if collision_indexes:
        for i in sorted(collision_indexes):
            proposal = proposals[i]
            holds.append({'target_source_record_id': proposal['target_source_record_id'],
                          'target_year': proposal['target_year'],
                          'carrier_target_source_record_id': proposal['inference_modern_point_use_target_source_record_id'],
                          'hold_reasons_json': json.dumps(['same_year_exact_coordinate_collision_among_staged_targets'])})
        proposals = [p for i, p in enumerate(proposals) if i not in collision_indexes]

    output_path.mkdir(parents=True, exist_ok=True)
    staged = pd.DataFrame(proposals)
    if staged.empty:
        staged = pd.DataFrame(columns=['target_source_record_id', 'target_year', 'latitude', 'longitude',
                                       'coordinate_source', 'coordinate_source_record_id',
                                       'admission_allowed', 'application_inference_kind'])
    held = pd.DataFrame(holds)
    if held.empty:
        held = pd.DataFrame(columns=['target_source_record_id', 'target_year', 'component_id',
                                     'carrier_target_source_record_id', 'hold_reasons_json'])
    staged_path = output_path / 'staged_point_uses.parquet'
    held_path = output_path / 'held_targets.parquet'
    staged.to_parquet(staged_path, index=False)
    held.to_parquet(held_path, index=False)
    receipt = {
        'status': 'continuation_graph_point_uses_staged_pending_root_review',
        'input_hashes': {key: {'path': str(path), 'sha256': sha(path)} for key, path in paths.items()},
        'accepted_rows': int(len(accepted)),
        'accepted_graph_rows': int(len(graph)),
        'accepted_same_place_edges_used': int(len(edges)),
        'explicit_carrier_delta_ids': int(len(carrier_ids)),
        'accepted_2021_carriers_in_delta': int(len(carriers)),
        'explicit_blocked_target_ids': int(len(blocked_ids)),
        'selected_missing_2002_2010_targets': int(len(missing)),
        'staged_rows': int(len(staged)),
        'held_rows': int(len(held)),
        'staged_by_year': staged.target_year.value_counts().to_dict() if len(staged) else {},
        'held_reasons': dict(Counter(reason for value in held.get('hold_reasons_json', [])
                                     for reason in json.loads(value))) if len(held) else {},
        'staged_admission_allowed_all_false': bool(len(staged) == 0 or not staged.admission_allowed.any()),
        'every_staged_origin_copied_from_exact_accepted_carrier': True,
        'every_staged_source_row_restored_from_exact_selected_evidence': True,
        'raw_origin_assets_hashed_once': origin_hash_cache,
        'outputs': {
            'staged_point_uses': {'path': str(staged_path), 'rows': int(len(staged)), 'sha256': sha(staged_path)},
            'held_targets': {'path': str(held_path), 'rows': int(len(held)), 'sha256': sha(held_path)},
        },
        'limits': [
            'This output is candidate staging only; it does not admit or publish coordinates.',
            'Modern representative-point reuse is a retrospective continuity inference, not a historical measurement.',
            'Measurement date, population boundary comparability, and population-scope equivalence remain unasserted.',
            'All blocked target IDs and exact-native event roles remain held.',
        ],
    }
    receipt_path = output_path / 'receipt.json'
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--accepted', required=True, type=Path)
    parser.add_argument('--carrier-delta', required=True, type=Path)
    parser.add_argument('--graph', required=True, type=Path)
    parser.add_argument('--selected', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--events', required=True, type=Path)
    parser.add_argument('--blocked-targets', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.accepted, args.carrier_delta, args.graph, args.selected,
                           args.evidence, args.events, args.blocked_targets, args.output),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
