"""Bounded compatibility checks for exact-key census identity candidates.

This tool constructs conflict-free proposal graphs for two candidate families.
It does not admit identity edges. In particular, the 2021 Tochno ``mun_upper``
parent field is retained as undated administrative context, not projected back
as historical district evidence.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

YEARS = (2002, 2010, 2021)
YEAR_PAIR_PRIORITY = {(2002, 2010): 0, (2010, 2021): 1, (2002, 2021): 2}
URBAN_TYPE_ENUM = frozenset({"город", "пгт", "поселок городского типа"})
AGGREGATE_SCOPES = frozenset({
    "federal_city_region", "municipality", "municipal_aggregate", "region",
    "administrative_area", "territorial_aggregate",
})
SELECTED_COLUMNS = (
    "source_record_id", "census_year", "source_file", "source_path", "source_sheet",
    "source_row", "source_native_id", "source_sha256", "source_locator",
    "source_selection_component", "region_raw", "district_raw", "municipality_raw",
    "region_norm", "district_norm", "municipality_norm", "type_norm", "population",
    "population_value_quality", "population_scope", "entity_grain_status",
)
CANDIDATE_COLUMNS = (
    "candidate_id", "candidate_family", "candidate_kind", "year_from", "year_to",
    "from_source_record_id", "to_source_record_id", "federal_aggregate_block",
    "legacy_identity_conflict_present", "legacy_same_year_collision_present",
    "potential_cartesian_pair_count_not_materialized", "admission_status",
)


class GraphCheckError(ValueError):
    pass


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def _text(value: Any) -> str:
    return "" if _is_missing(value) else str(value).strip()


def _flag(value: Any) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, str):
        return value.casefold().strip() in {"true", "1", "yes", "да"}
    return bool(value)


def _population(value: Any) -> int | None:
    if _is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def district_lineage_class(year: int, source_file: Any, source_path: Any,
                           source_selection_component: Any, district_raw: Any) -> str:
    """Classify recorded origin without assigning a historical effective date."""
    if not _text(district_raw):
        return "district_value_missing"
    source = (_text(source_path) or _text(source_file)).replace("\\", "/").casefold()
    component = _text(source_selection_component).casefold()
    if year == 2021 and ("2021_tochno" in source or "allsettlements_anon" in source):
        return "tochno_mun_upper_parent_raw_but_census_date_unestablished"
    if year == 2002 and "/2002/" in f"/{source}/":
        return "2002_source_row_district_heading_or_parent"
    if year == 2010 and component == "karelia_2010_primary_r5":
        return "reviewed_2010_karelia_primary_document_parent_context"
    if year == 2010 and component == "national_2010_regional_primary_r2":
        return "reviewed_2010_primary_publication_parent_context"
    if year == 2010 and "/2010/" in f"/{source}/":
        return "2010_source_row_district_context"
    return "source_parent_origin_requires_review"


@dataclass(frozen=True)
class Node:
    source_record_id: str
    census_year: int
    population: int | None
    population_scope: str
    aggregate: bool
    legacy_identity_conflict: bool
    legacy_same_year_collision: bool
    type_norm: str
    region_norm: str
    district_norm: str
    district_raw: str
    municipality_raw: str
    municipality_norm: str
    district_lineage_class: str
    source_file: str
    source_path: str
    source_sheet: str
    source_row: str
    source_native_id: str
    source_sha256: str
    source_locator: str
    source_selection_component: str
    entity_grain_status: str
    population_value_quality: str

    def lineage_evidence(self) -> dict[str, Any]:
        return {
            "source_record_id": self.source_record_id,
            "census_year": self.census_year,
            "district_norm": self.district_norm or None,
            "district_raw": self.district_raw or None,
            "municipality_norm": self.municipality_norm or None,
            "municipality_raw": self.municipality_raw or None,
            "district_lineage_class": self.district_lineage_class,
            "source_file": self.source_file or None,
            "source_path": self.source_path or None,
            "source_sheet": self.source_sheet or None,
            "source_row": self.source_row or None,
            "source_native_id": self.source_native_id or None,
            "source_sha256": self.source_sha256 or None,
            "source_locator": self.source_locator or None,
            "source_selection_component": self.source_selection_component or None,
            "entity_grain_status": self.entity_grain_status or None,
        }


@dataclass(frozen=True)
class ProposalEdge:
    edge_id: str
    year_from: int
    year_to: int
    from_id: str
    to_id: str
    candidate_ids: tuple[str, ...]
    candidate_families: tuple[str, ...]
    from_node: Node
    to_node: Node


class YearConstrainedUnionFind:
    """Union-find that refuses a component merge if any census year overlaps."""

    def __init__(self, nodes: dict[str, Node]):
        self.nodes = nodes
        self.parent: dict[str, str] = {}
        self.year_counts: dict[str, Counter[int]] = {}
        self.size: dict[str, int] = {}
        self.selected_touched: set[str] = set()

    def find(self, item: str) -> str:
        if item not in self.parent:
            if item not in self.nodes:
                raise GraphCheckError(f"edge endpoint is absent from selected source rows: {item}")
            self.parent[item] = item
            self.year_counts[item] = Counter({self.nodes[item].census_year: 1})
            self.size[item] = 1
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while item != root:
            next_item = self.parent[item]
            self.parent[item] = root
            item = next_item
        return root

    def add_edge(self, left: str, right: str) -> tuple[str, tuple[int, ...], str, str]:
        root_left, root_right = self.find(left), self.find(right)
        if root_left == root_right:
            self.selected_touched.update((left, right))
            return "already_connected", (), root_left, root_right
        overlap = tuple(sorted(set(self.year_counts[root_left]) & set(self.year_counts[root_right])))
        if overlap:
            return "blocked_same_year_component_collision", overlap, root_left, root_right
        # Stable representative independent of input order after priority sort.
        root, child = sorted((root_left, root_right))
        self.parent[child] = root
        self.year_counts[root].update(self.year_counts.pop(child))
        self.size[root] += self.size.pop(child)
        self.selected_touched.update((left, right))
        return "proposed_component_merge", (), root, child

    def initialize_edges(self, edges: Iterable[tuple[str, str]]) -> None:
        for left, right in edges:
            status, overlap, _, _ = self.add_edge(left, right)
            if status == "blocked_same_year_component_collision":
                raise GraphCheckError(f"accepted graph has same-year collision {left} - {right}: {overlap}")

    def component_summaries(self) -> list[tuple[str, list[str], Counter[int]]]:
        members: dict[str, list[str]] = defaultdict(list)
        for item in tuple(self.parent):
            members[self.find(item)].append(item)
        return [(root, values, Counter(self.year_counts[root])) for root, values in members.items()]


def _load_nodes(selected_path: Path, source_evidence_path: Path) -> tuple[dict[str, Node], pd.DataFrame]:
    selected = pd.read_parquet(selected_path, columns=list(SELECTED_COLUMNS))
    if selected.source_record_id.isna().any() or selected.source_record_id.astype("string").str.strip().eq("").any():
        raise GraphCheckError("selected source_record_id contains null or blank IDs")
    selected["source_record_id"] = selected.source_record_id.astype(str)
    selected["census_year"] = pd.to_numeric(selected.census_year, errors="raise").astype(int)
    if selected.source_record_id.duplicated().any():
        raise GraphCheckError("selected source_record_id is not unique")
    evidence = pd.read_parquet(source_evidence_path, columns=["source_record_id", "source_evidence_json"])
    if evidence.source_record_id.astype(str).duplicated().any():
        raise GraphCheckError("source evidence has duplicate source_record_id values")
    legacy_flags: dict[str, tuple[bool, bool, bool]] = {}
    for sid, blob in zip(evidence.source_record_id.astype(str), evidence.source_evidence_json.astype(str)):
        raw = json.loads(blob)
        legacy_flags[sid] = (
            _flag(raw.get("legacy_identity_conflict")),
            _flag(raw.get("legacy_same_year_collision")),
            _flag(raw.get("is_federal_aggregate")),
        )
    if set(legacy_flags) != set(selected.source_record_id):
        raise GraphCheckError("source evidence IDs do not exactly equal selected source IDs")
    del evidence

    nodes: dict[str, Node] = {}
    positions = {name: index for index, name in enumerate(selected.columns)}
    for values in selected.itertuples(index=False, name=None):
        sid = str(values[positions["source_record_id"]])
        year = int(values[positions["census_year"]])
        legacy_conflict, legacy_collision, evidence_aggregate = legacy_flags[sid]
        val = lambda name: values[positions[name]] if name in positions else None
        scope = _text(val("population_scope")).casefold()
        source_file, source_path = _text(val("source_file")), _text(val("source_path"))
        district_raw = _text(val("district_raw"))
        nodes[sid] = Node(
            source_record_id=sid,
            census_year=year,
            population=_population(val("population")),
            population_scope=scope,
            aggregate=(scope in AGGREGATE_SCOPES or evidence_aggregate),
            legacy_identity_conflict=legacy_conflict,
            legacy_same_year_collision=legacy_collision,
            type_norm=_text(val("type_norm")),
            region_norm=_text(val("region_norm")),
            district_norm=_text(val("district_norm")),
            district_raw=district_raw,
            municipality_raw=_text(val("municipality_raw")),
            municipality_norm=_text(val("municipality_norm")),
            district_lineage_class=district_lineage_class(year, source_file, source_path,
                val("source_selection_component"), district_raw),
            source_file=source_file, source_path=source_path,
            source_sheet=_text(val("source_sheet")), source_row=_text(val("source_row")),
            source_native_id=_text(val("source_native_id")), source_sha256=_text(val("source_sha256")),
            source_locator=_text(val("source_locator")),
            source_selection_component=_text(val("source_selection_component")),
            entity_grain_status=_text(val("entity_grain_status")),
            population_value_quality=_text(val("population_value_quality")),
        )
    compact_selected = selected[["source_record_id", "census_year", "population"]].copy()
    return nodes, compact_selected


def _read_candidates(path: Path, nodes: dict[str, Node]) -> dict[tuple[str, str], dict[str, Any]]:
    required = set(CANDIDATE_COLUMNS)
    pair_map: dict[tuple[str, str], dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or []):
            raise GraphCheckError(f"candidate ledger lacks required columns: {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            if row["candidate_kind"] != "unique_exact_key_pair":
                continue
            family = row["candidate_family"]
            if family not in {"region_district_name_type", "region_name_type"}:
                continue
            left, right = row["from_source_record_id"], row["to_source_record_id"]
            if not left or not right:
                raise GraphCheckError(f"unique candidate has blank endpoint ID: {row['candidate_id']}")
            if left not in nodes or right not in nodes:
                raise GraphCheckError(f"candidate endpoint not in selected rows: {row['candidate_id']}")
            years = int(row["year_from"]), int(row["year_to"])
            if (nodes[left].census_year, nodes[right].census_year) != years:
                raise GraphCheckError(f"candidate endpoint year disagrees with candidate ledger: {row['candidate_id']}")
            key = (left, right)
            item = pair_map.setdefault(key, {
                "year_from": years[0], "year_to": years[1], "candidate_ids": set(),
                "candidate_families": set(), "federal_aggregate_block": False,
                "legacy_identity_conflict_present": False, "legacy_same_year_collision_present": False,
            })
            if (item["year_from"], item["year_to"]) != years:
                raise GraphCheckError("same directed endpoint pair appears with different years")
            item["candidate_ids"].add(row["candidate_id"])
            item["candidate_families"].add(family)
            item["federal_aggregate_block"] |= _flag(row["federal_aggregate_block"])
            item["legacy_identity_conflict_present"] |= _flag(row["legacy_identity_conflict_present"])
            item["legacy_same_year_collision_present"] |= _flag(row["legacy_same_year_collision_present"])
    return pair_map


def _read_ambiguous_key_groups(path: Path) -> list[dict[str, Any]]:
    fields = (
        "candidate_id", "candidate_family", "year_pair", "key_fields", "key_values", "key_hash",
        "from_candidate_count", "to_candidate_count", "from_candidate_ids_json", "to_candidate_ids_json",
        "potential_cartesian_pair_count_not_materialized", "from_known_population", "to_known_population",
        "from_unknown_population_rows", "to_unknown_population_rows", "from_regions_json", "to_regions_json",
        "region_risk_class", "federal_aggregate_block", "legacy_identity_conflict_present",
        "legacy_same_year_collision_present", "ambiguity_flags_json",
    )
    out = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row["candidate_kind"] != "ambiguous_competing_key_group"
                    or row["candidate_family"] not in {"region_district_name_type", "region_name_type"}):
                continue
            item = {name: row.get(name, "") for name in fields}
            item.update({
                "candidate_kind": "ambiguous_competing_key_group",
                "admission_status": "candidate_only_no_admission",
                "cartesian_expansion_performed": False,
                "review_unit": "candidate_key_group_endpoint_alternatives_not_individual_pairs",
            })
            out.append(item)
    return out


def _proposal_edge(pair: tuple[str, str], values: dict[str, Any], nodes: dict[str, Node]) -> ProposalEdge:
    left, right = pair
    candidate_ids = tuple(sorted(values["candidate_ids"]))
    payload = "\0".join([str(values["year_from"]), str(values["year_to"]), left, right])
    edge_id = "GCP-" + hashlib.sha256(payload.encode()).hexdigest()[:24]
    return ProposalEdge(edge_id, values["year_from"], values["year_to"], left, right,
        candidate_ids, tuple(sorted(values["candidate_families"])), nodes[left], nodes[right])


def _candidate_blockers(edge: ProposalEdge) -> list[str]:
    flags = []
    for node in (edge.from_node, edge.to_node):
        if node.aggregate:
            flags.append("federal_or_admin_aggregate_scope")
        if node.legacy_identity_conflict:
            flags.append("legacy_identity_conflict")
        if node.legacy_same_year_collision:
            flags.append("legacy_same_year_collision")
        if not node.type_norm or node.entity_grain_status == "named_locality_type_unresolved":
            flags.append("grain_unresolved_or_not_atomic")
    if edge.from_node.aggregate or edge.to_node.aggregate:
        flags.append("candidate_ledger_aggregate_block")
    return sorted(set(flags))


def _candidate_scenarios(pair_map: dict[tuple[str, str], dict[str, Any]], nodes: dict[str, Node]) -> dict[str, list[ProposalEdge]]:
    scenarios: dict[str, list[ProposalEdge]] = {"strict_region_district_name_type": [], "urban_region_name_type": []}
    for pair, values in pair_map.items():
        edge = _proposal_edge(pair, values, nodes)
        if "region_district_name_type" in edge.candidate_families:
            scenarios["strict_region_district_name_type"].append(edge)
        if ("region_name_type" in edge.candidate_families
                and edge.from_node.type_norm in URBAN_TYPE_ENUM
                and edge.to_node.type_norm in URBAN_TYPE_ENUM):
            scenarios["urban_region_name_type"].append(edge)
    for edges in scenarios.values():
        edges.sort(key=lambda e: (YEAR_PAIR_PRIORITY[(e.year_from, e.year_to)], e.from_id, e.to_id, e.edge_id))
    return scenarios


def _run_scenario(name: str, edges: list[ProposalEdge], nodes: dict[str, Node],
                  base_edges: list[tuple[str, str]], selected: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    graph = YearConstrainedUnionFind(nodes)
    graph.initialize_edges(base_edges)
    baseline_summaries = graph.component_summaries()
    baseline_components = [members for _, members, _ in baseline_summaries if len(members) > 1]
    edge_counts: Counter[str] = Counter()
    conflict_rows: list[dict[str, Any]] = []
    for edge in edges:
        blockers = _candidate_blockers(edge)
        if blockers:
            status = "blocked_source_quality_or_grain"
            overlaps: tuple[int, ...] = ()
            root_left = root_right = ""
        else:
            status, overlaps, root_left, root_right = graph.add_edge(edge.from_id, edge.to_id)
        edge_counts[status] += 1
        result = {
                "scenario": name, "edge_id": edge.edge_id,
                "candidate_ids_json": _json(edge.candidate_ids),
                "candidate_families_json": _json(edge.candidate_families),
                "from_source_record_id": edge.from_id, "from_year": edge.year_from,
                "to_source_record_id": edge.to_id, "to_year": edge.year_to,
                "compatibility_status": status,
                "blocking_flags_json": _json(blockers),
                "same_year_overlap_json": _json(overlaps),
                "from_component_representative": root_left,
                "to_component_representative": root_right,
                "from_district_lineage_json": _json(edge.from_node.lineage_evidence()),
                "to_district_lineage_json": _json(edge.to_node.lineage_evidence()),
                "decision_status": "candidate_only_no_admission",
        }
        if status != "proposed_component_merge":
            conflict_rows.append(result)

    summaries = graph.component_summaries()
    linked = [(root, members, years) for root, members, years in summaries if len(members) > 1]
    full = [(root, members, years) for root, members, years in linked
            if all(years.get(year, 0) == 1 for year in YEARS) and len(years) == 3]
    baseline_linked_ids = {sid for members in baseline_components for sid in members}
    proposed_linked_ids = {sid for _, members, _ in linked for sid in members}
    full_ids = {sid for _, members, _ in full for sid in members}
    base_full = {sid for _, members, years in baseline_summaries
                 if len(members) > 1 and len(years) == 3 and all(years.get(y, 0) == 1 for y in YEARS)
                 for sid in members}
    by_year = []
    selected_counts = selected.census_year.value_counts().to_dict()
    for year in YEARS:
        year_ids = {sid for sid in proposed_linked_ids if nodes[sid].census_year == year}
        base_ids = {sid for sid in baseline_linked_ids if nodes[sid].census_year == year}
        full_year_ids = {sid for sid in full_ids if nodes[sid].census_year == year}
        known = lambda ids: sum(nodes[sid].population for sid in ids if nodes[sid].population is not None)
        unknown = lambda ids: sum(nodes[sid].population is None for sid in ids)
        base_pop = known(base_ids)
        proposed_pop = known(year_ids)
        by_year.append({
            "scenario": name, "census_year": year,
            "selected_rows": int(selected_counts.get(year, 0)),
            "baseline_linked_rows": len(base_ids), "baseline_known_population": base_pop,
            "baseline_unknown_population_rows": unknown(base_ids),
            "proposed_linked_rows": len(year_ids), "proposed_known_population": proposed_pop,
            "proposed_unknown_population_rows": unknown(year_ids),
            "incremental_linked_rows_vs_baseline": len(year_ids - base_ids),
            "incremental_known_population_vs_baseline": known(year_ids - base_ids),
            "full_chain_rows": len(full_year_ids), "full_chain_known_population": known(full_year_ids),
            "full_chain_unknown_population_rows": unknown(full_year_ids),
            "proposed_linked_record_fraction": len(year_ids) / int(selected_counts.get(year, 1)),
            "proposed_full_chain_record_fraction": len(full_year_ids) / int(selected_counts.get(year, 1)),
        })
    summary = {
        "scenario": name,
        "status": "conflict_free_candidate_graph_no_admissions",
        "baseline_accepted_edges": len(base_edges),
        "baseline_components": len(baseline_summaries),
        "baseline_linked_components": len(baseline_components),
        "baseline_full_chain_components": len([1 for _, m, y in baseline_summaries
            if len(m) > 1 and len(y) == 3 and all(y.get(t, 0) == 1 for t in YEARS)]),
        "distinct_candidate_pairs_after_cross_family_dedup": len(edges),
        "source_or_grain_blocked_edges": edge_counts["blocked_source_quality_or_grain"],
        "candidate_edges_compatible_and_proposed": edge_counts["proposed_component_merge"],
        "candidate_edges_redundant_to_existing_or_prior_proposal": edge_counts["already_connected"],
        "candidate_edges_blocked_by_same_year_overlap": edge_counts["blocked_same_year_component_collision"],
        "proposed_components": len(summaries),
        "proposed_linked_components": len(linked),
        "proposed_full_chain_components": len(full),
        "proposed_full_chain_rows_all_years": len(full_ids),
        "baseline_full_chain_rows_all_years": len(base_full),
        "same_year_collision_components": 0,
        "admissions_created": 0,
        "population_note": "Known selected-row population is summed once per census year within this scenario; unknown values remain explicit. Do not sum across scenarios.",
        "maximality_note": "Deterministic maximal greedy extension, prioritizing adjacent census transitions; not a proof of globally maximum edge count.",
    }
    return {"summary": summary, "by_year": by_year}, conflict_rows


def _district_summaries(nodes: dict[str, Node], pair_map: dict[tuple[str, str], dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    counts: Counter[tuple[int, str, bool, bool]] = Counter()
    for node in nodes.values():
        counts[(node.census_year, node.district_lineage_class, bool(node.district_raw),
                bool(node.district_raw and node.municipality_raw and node.district_raw.casefold() == node.municipality_raw.casefold()))] += 1
    source_summary = []
    for (year, lineage, raw_present, raw_equals_municipality), n in sorted(counts.items()):
        source_summary.append({
            "census_year": year, "district_lineage_class": lineage,
            "district_raw_present": raw_present, "district_raw_exactly_equals_municipality_raw": raw_equals_municipality,
            "selected_rows": n,
        })
    pair_counts: Counter[tuple[int, int, str, str]] = Counter()
    for (left, right), values in pair_map.items():
        if "region_district_name_type" not in values["candidate_families"]:
            continue
        a, b = nodes[left], nodes[right]
        pair_counts[(a.census_year, b.census_year, a.district_lineage_class, b.district_lineage_class)] += 1
    pair_summary = [
        {"year_from": a, "year_to": b, "from_district_lineage_class": c,
         "to_district_lineage_class": d, "unique_exact_district_candidate_pairs": n,
         "historical_date_interpretation": "source contexts are not equivalent dated district identity unless independently confirmed"}
        for (a, b, c, d), n in sorted(pair_counts.items())
    ]
    return source_summary, pair_summary


def _alternative_groups(scenario_name: str, edges: list[ProposalEdge]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, int], list[ProposalEdge]] = defaultdict(list)
    for edge in edges:
        groups[(edge.from_id, edge.year_from, edge.year_to)].append(edge)
        groups[(edge.to_id, edge.year_to, edge.year_from)].append(edge)
    out = []
    for (shared_id, shared_year, other_year), alternatives in sorted(groups.items()):
        counterparts = sorted({edge.to_id if edge.from_id == shared_id else edge.from_id for edge in alternatives})
        if len(counterparts) <= 1:
            continue
        out.append({
            "scenario": scenario_name, "shared_source_record_id": shared_id,
            "shared_year": shared_year, "alternative_year": other_year,
            "counterpart_source_record_ids_json": _json(counterparts),
            "candidate_edge_ids_json": _json(sorted(edge.edge_id for edge in alternatives)),
            "candidate_id_sets_json": _json([edge.candidate_ids for edge in sorted(alternatives, key=lambda e: e.edge_id)]),
            "candidate_family_sets_json": _json([edge.candidate_families for edge in sorted(alternatives, key=lambda e: e.edge_id)]),
            "alternative_count": len(counterparts),
            "interpretation": "competing exact-key counterparts; do not select by order, name, type, legacy ID or population alone",
        })
    return out


def build_checks(selected_parquet: Path, source_evidence_parquet: Path, candidate_ledger_path: Path,
                 accepted_edges_path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    nodes, selected = _load_nodes(selected_parquet, source_evidence_parquet)
    pair_map = _read_candidates(candidate_ledger_path, nodes)
    accepted = pd.read_csv(accepted_edges_path, dtype={
        "from_source_record_id": "string", "to_source_record_id": "string",
        "decision_id": "string", "relation": "string", "decision_status": "string",
    })
    required = {"from_source_record_id", "to_source_record_id", "from_year", "to_year", "relation", "decision_status"}
    if not required.issubset(accepted.columns):
        raise GraphCheckError(f"accepted identity edges missing columns: {sorted(required - set(accepted.columns))}")
    if len(accepted) != 1162 or not accepted.relation.eq("same_place").all():
        raise GraphCheckError("accepted graph is not the expected 1162 same_place edges")
    if not accepted.decision_status.astype(str).str.contains("accepted", case=False).all():
        raise GraphCheckError("accepted graph includes a non-accepted decision status")
    base_edges: list[tuple[str, str]] = []
    for row in accepted.itertuples(index=False):
        left, right = str(row.from_source_record_id), str(row.to_source_record_id)
        if left not in nodes or right not in nodes:
            raise GraphCheckError(f"accepted edge endpoint is not current selected: {left} / {right}")
        if nodes[left].census_year != int(row.from_year) or nodes[right].census_year != int(row.to_year):
            raise GraphCheckError(f"accepted edge years disagree with selected rows: {left} / {right}")
        base_edges.append((left, right))
    if len(set(base_edges)) != len(base_edges):
        raise GraphCheckError("accepted graph has duplicate endpoint pairs")

    scenarios = _candidate_scenarios(pair_map, nodes)
    summary_rows, conflict_rows, alternative_rows = [], [], []
    for name, edges in scenarios.items():
        run, conflicts = _run_scenario(name, edges, nodes, base_edges, selected)
        summary_rows.append(run["summary"])
        summary_rows.extend(run["by_year"])
        conflict_rows.extend(conflicts)
        alternative_rows.extend(_alternative_groups(name, edges))
    source_lineage, pair_lineage = _district_summaries(nodes, pair_map)
    ambiguous_groups = _read_ambiguous_key_groups(candidate_ledger_path)
    ambiguous_summary: Counter[tuple[str, str]] = Counter()
    ambiguous_cartesian_potential: Counter[tuple[str, str]] = Counter()
    for group in ambiguous_groups:
        key = (group["candidate_family"], group["year_pair"])
        ambiguous_summary[key] += 1
        ambiguous_cartesian_potential[key] += int(group["potential_cartesian_pair_count_not_materialized"] or 0)
    base_check = YearConstrainedUnionFind(nodes)
    base_check.initialize_edges(base_edges)
    base_components = base_check.component_summaries()
    audit = {
        "status": "candidate_graph_compatibility_checks_no_admissions",
        "rule_version": "year_exclusive_component_union_v1",
        "candidate_ledger": {"unique_endpoint_pairs_after_cross_family_dedup": len(pair_map)},
        "accepted_graph": {
            "input_edges": len(base_edges), "components": len(base_components),
            "same_year_collisions": 0,
            "source": "accepted/migrated identity graph supplied by caller; copied as a fixed baseline only",
        },
        "candidate_families": {
            "strict_region_district_name_type": "unique exact region_norm + district_norm + name_norm + type_norm candidate rows; aggregates and legacy hard conflicts block the proposal graph",
            "urban_region_name_type": "unique exact region_norm + name_norm + type_norm rows restricted to existing urban type enum; aggregates and legacy hard conflicts block the proposal graph",
        },
        "graph_note": "Candidate relations are hypothetical compatibility proposals only. No identity or coordinate admissions are created.",
        "lineage_note": "For 2021, district_raw originates from the ToChno source field mun_upper in the archived extraction code; it is recorded as undated administrative context relative to census date. It is not silently copied backward as historical district identity. Current R2 has district_raw blank on many 2010 rows; this records selection-layer missingness, not proof that a grouped historical publication lacked district headings. Raw workbook block-header recovery is separately reviewed before any fill-forward.",
        "full_chain_note": "A full chain is a connected component with exactly one selected observation from each of 2002, 2010, 2021; every component merge is rejected if it would add a second observation from any census year.",
        "population_note": "Unknown populations remain unknown and are not treated as zero. Scenario totals are separate and must not be summed across candidate families.",
        "summary_rows": summary_rows,
        "district_lineage_source_rows": source_lineage,
        "district_candidate_pair_lineage": pair_lineage,
        "ambiguous_candidate_key_group_counts": [
            {"candidate_family": family, "year_pair": pair, "ambiguous_key_groups": count,
             "potential_cartesian_pairs_not_materialized": ambiguous_cartesian_potential[(family, pair)]}
            for (family, pair), count in sorted(ambiguous_summary.items())
        ],
        "cross_family_duplicate_endpoint_pairs": sum(len(v["candidate_families"]) > 1 for v in pair_map.values()),
        "counts": {
            "candidate_conflict_rows": len(conflict_rows),
            "candidate_alternative_groups_from_unique_edges": len(alternative_rows),
            "ambiguous_candidate_key_groups": len(ambiguous_groups),
            "proposed_scenarios": len(scenarios),
            "admissions_created": 0,
        },
    }
    tables = {
        "candidate_graph_conflicts.csv.gz": conflict_rows,
        "candidate_alternative_groups.csv": alternative_rows,
        "ambiguous_candidate_key_groups.csv.gz": ambiguous_groups,
    }
    return audit, tables


def _write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        empty_fields = {
            "candidate_graph_conflicts.csv.gz": ["scenario", "edge_id", "compatibility_status", "blocking_flags_json"],
            "candidate_alternative_groups.csv": ["scenario", "shared_source_record_id", "alternative_count"],
            "ambiguous_candidate_key_groups.csv.gz": ["candidate_id", "candidate_family", "year_pair", "from_candidate_ids_json", "to_candidate_ids_json", "potential_cartesian_pair_count_not_materialized"],
        }.get(path.name, ["status"])
        opener = gzip.open if path.suffix == ".gz" else open
        mode = "wt" if path.suffix == ".gz" else "w"
        with opener(path, mode, encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerow(empty_fields)
        return
    fields = list(rows[0])
    opener = gzip.open if path.suffix == ".gz" else open
    mode = "wt" if path.suffix == ".gz" else "w"
    with opener(path, mode, encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build(selected_parquet: Path, source_evidence_parquet: Path, candidate_ledger_path: Path,
          accepted_edges_path: Path, output_root: Path) -> dict[str, Any]:
    selected_parquet, source_evidence_parquet = selected_parquet.resolve(), source_evidence_parquet.resolve()
    candidate_ledger_path, accepted_edges_path = candidate_ledger_path.resolve(), accepted_edges_path.resolve()
    output_root = output_root.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise GraphCheckError("output directory must be outside the Git repository")
    if output_root.exists():
        raise FileExistsError(f"immutable graph-check output already exists: {output_root}")
    for label, path in (("selected parquet", selected_parquet), ("source evidence parquet", source_evidence_parquet),
                        ("candidate ledger", candidate_ledger_path), ("accepted graph", accepted_edges_path)):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
    audit, tables = build_checks(selected_parquet, source_evidence_parquet, candidate_ledger_path, accepted_edges_path)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    try:
        for name, rows in tables.items():
            _write_table(staging / name, rows)
        audit_path = staging / "graph_check_audit.json"
        audit["inputs"] = {
            "selected_parquet": {"path": selected_parquet.name, "input_root_role": "selected_parquet_root", "sha256": _sha(selected_parquet), "bytes": selected_parquet.stat().st_size},
            "source_evidence_parquet": {"path": source_evidence_parquet.name, "input_root_role": "candidate_output_root", "sha256": _sha(source_evidence_parquet), "bytes": source_evidence_parquet.stat().st_size},
            "candidate_ledger": {"path": candidate_ledger_path.name, "input_root_role": "candidate_output_root", "sha256": _sha(candidate_ledger_path), "bytes": candidate_ledger_path.stat().st_size},
            "accepted_edges": {"path": accepted_edges_path.name, "input_root_role": "migrated_graph_root", "sha256": _sha(accepted_edges_path), "bytes": accepted_edges_path.stat().st_size},
        }
        builder_path = Path(__file__).resolve()
        audit["builder"] = {"path": builder_path.relative_to(repo_root).as_posix(), "sha256": _sha(builder_path), "bytes": builder_path.stat().st_size}
        audit["outputs"] = {
            name: {"sha256": _sha(staging / name), "bytes": (staging / name).stat().st_size, "rows": len(rows)}
            for name, rows in tables.items()
        }
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.rename(output_root)
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-parquet", type=Path, required=True)
    parser.add_argument("--source-evidence-parquet", type=Path, required=True)
    parser.add_argument("--candidate-ledger", type=Path, required=True)
    parser.add_argument("--accepted-edges", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        audit = build(args.selected_parquet, args.source_evidence_parquet, args.candidate_ledger,
                      args.accepted_edges, args.output_root)
    except (GraphCheckError, FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": audit["status"], "counts": audit["counts"], "output_root": str(args.output_root.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
