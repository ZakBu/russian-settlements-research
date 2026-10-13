"""Stage Wikipedia module counts as named-history series candidates.

This writer deliberately does not admit historical observations to a physical
settlement identity. Census comparisons are attached only as diagnostics and
preserve the official endpoint, scope and value-quality metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


BINDING_ROOT = Path("/workspace/settlements-work/sources/annual_module_bindings_v1")
SELECTED_SOURCE = Path("/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet")
ACCEPTED_GRAPH = Path("/workspace/settlements-work/identity/accepted_ordinary_v4/accepted_identity_edges.parquet")
OUTPUT_ROOT = Path("/workspace/settlements-work/sources/annual_module_series_staging_v1")
VERSION = "annual-module-named-history-staging-r1"
ACCEPTED_GRAPH_STATUSES = {
    "checked_rule_accepted", "checked_rule_accepted_redundant_graph_connectivity_effect",
    "accepted_rule_family_after_independent_sample_review", "case_specific_independent_review_accepted",
    "case_review_accepted", "independent_case_review_accepted", "accepted_case_specific",
}
ACTIVE_PROJECTIONS = {"active_endpoints_selected", "active_after_reviewed_publication_binding_migration"}
COMPARISON_YEARS = {1970, 1989, 2002, 2010, 2021}

SELECTED_COLUMNS = [
    "source_record_id", "census_year", "settlement_name", "settlement_type", "region_raw", "oktmo",
    "name_norm", "type_norm", "region_norm", "population", "population_scope",
    "analysis_population_additive", "snapshot_record_type", "population_value_quality",
    "source_population_raw", "coverage_status", "source_file", "source_sheet", "source_row",
    "source_native_id", "source_path", "source_sha256", "source_locator", "entity_grain_status", "population",
]
GRAPH_COLUMNS = [
    "decision_id", "relation", "from_source_record_id", "from_year", "to_source_record_id",
    "to_year", "decision_status", "decision_rule", "evidence_sha256", "selection_projection_status",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def official_comparison_class(module_value: int, official_value: int | None,
                              official_quality: str | None) -> tuple[str, str, int | None]:
    """Compare recorded numbers without deciding which source is correct."""
    if official_value is None:
        return "official_value_missing", "not_comparable", None
    difference = int(module_value) - int(official_value)
    if difference == 0:
        return "numeric_values_equal", "equal_recorded_values; scope/date/boundary still unverified", difference
    if official_quality == "confidentiality_perturbed_within_ten":
        return "numeric_values_differ_official_value_confidentiality_perturbed", "protected_value_difference_not_evidence_of_module_error", difference
    if official_quality in {"direct_published_census_value", "direct_official_city_value", "reviewed_primary_reported_value"}:
        return "numeric_values_differ_official_published_value", "difference_needs_scope/date/boundary/source review; no source replaced", difference
    return "numeric_values_differ_official_quality_unclassified", "quality or comparability unresolved; no source replaced", difference


def _accepted_graph_index(edges: list[dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, list[dict[str, Any]]], dict[str, str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    pair_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    node_year: dict[str, str] = {}
    for edge in edges:
        if (edge["relation"] != "same_place" or edge["decision_status"] not in ACCEPTED_GRAPH_STATUSES
                or edge["selection_projection_status"] not in ACTIVE_PROJECTIONS):
            continue
        a, b = edge["from_source_record_id"], edge["to_source_record_id"]
        if not a or not b:
            continue
        adjacency[a].add(b)
        adjacency[b].add(a)
        pair_edges["\0".join(sorted((a, b)))].append(edge)
        node_year.setdefault(a, str(edge["from_year"]))
        node_year.setdefault(b, str(edge["to_year"]))
    return adjacency, pair_edges, node_year


def _accepted_path(start: str, target: str, adjacency: dict[str, set[str]],
                   pair_edges: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]] | None:
    if start == target:
        return []
    queue = deque([start])
    previous: dict[str, str | None] = {start: None}
    while queue:
        node = queue.popleft()
        for neighbour in adjacency.get(node, ()):
            if neighbour in previous:
                continue
            previous[neighbour] = node
            if neighbour == target:
                queue.clear()
                break
            queue.append(neighbour)
    if target not in previous:
        return None
    route: list[tuple[str, str]] = []
    node = target
    while previous[node] is not None:
        parent = previous[node]
        route.append((parent, node))
        node = parent
    route.reverse()
    records: list[dict[str, Any]] = []
    for a, b in route:
        options = pair_edges["\0".join(sorted((a, b)))]
        edge = sorted(options, key=lambda x: (x["decision_status"], x["decision_id"]))[0]
        records.append({"decision_id": edge["decision_id"], "from_source_record_id": edge["from_source_record_id"],
                        "from_year": edge["from_year"], "to_source_record_id": edge["to_source_record_id"],
                        "to_year": edge["to_year"], "decision_status": edge["decision_status"],
                        "decision_rule": edge["decision_rule"], "evidence_sha256": edge["evidence_sha256"]})
    return records


def compare_module_assertion(assertion: dict[str, Any], candidate: dict[str, Any],
                             selected_by_id: dict[str, dict[str, Any]],
                             diagnostic_by_year_key: dict[tuple[int, str, str, str], list[dict[str, Any]]],
                             graph_adjacency: dict[str, set[str]],
                             graph_pair_edges: dict[str, list[dict[str, Any]]],
                             graph_node_year: dict[str, str], selected_years: set[int]) -> dict[str, Any]:
    year = int(assertion["observation_year"])
    result = {
        "census_comparison_status": "outside_comparison_scope",
        "census_comparison_basis": None,
        "census_comparison_source_record_id": None,
        "census_comparison_locator": None,
        "census_comparison_graph_path_json": None,
        "census_comparison_population": None,
        "census_comparison_population_quality": None,
        "census_comparison_population_scope": None,
        "census_comparison_source_file": None,
        "census_comparison_difference": None,
        "census_comparison_interpretation": None,
        "census_comparison_identity_admission": False,
    }
    if year not in COMPARISON_YEARS and year < 1990:
        return result
    if year not in selected_years:
        result["census_comparison_status"] = "selected_official_source_has_no_rows_for_this_year"
        result["census_comparison_basis"] = "no_official_comparator_available"
        result["census_comparison_interpretation"] = "no year, date, or population is inferred"
        return result

    chosen: dict[str, Any] | None = None
    basis: str | None = None
    path: list[dict[str, Any]] | None = None
    start = candidate["current_source_record_id"]
    if year == 2021:
        chosen = selected_by_id.get(start)
        basis = "same_current_2021_source_record_as_candidate_binding"
        path = []
    elif year in {2002, 2010}:
        connected_ids = []
        seen = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbour in graph_adjacency.get(node, ()):
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                queue.append(neighbour)
                if graph_node_year.get(neighbour) == str(year) and neighbour in selected_by_id:
                    connected_ids.append(neighbour)
        connected_ids = sorted(set(connected_ids))
        if len(connected_ids) == 1:
            chosen_id = connected_ids[0]
            chosen = selected_by_id[chosen_id]
            basis = "accepted_2021_identity_graph_same_place_endpoint"
            path = _accepted_path(start, chosen_id, graph_adjacency, graph_pair_edges)
        elif len(connected_ids) > 1:
            result["census_comparison_status"] = "accepted_identity_graph_has_multiple_same_year_endpoints"
            result["census_comparison_basis"] = "accepted_identity_graph_ambiguous"
            result["census_comparison_interpretation"] = "competing accepted graph endpoints retained; no numeric comparison selected"
            return result

    if chosen is None and year in {2002, 2010}:
        key = (year, candidate.get("current_name_norm", ""), candidate.get("current_type_norm", ""), candidate.get("current_region_norm", ""))
        possible = diagnostic_by_year_key.get(key, [])
        if len(possible) == 1:
            chosen = possible[0]
            basis = "diagnostic_exact_name_type_region_only"
        elif len(possible) > 1:
            result["census_comparison_status"] = "diagnostic_name_type_region_has_multiple_rows"
            result["census_comparison_basis"] = "diagnostic_only_ambiguous"
            result["census_comparison_interpretation"] = "normalized exact-text diagnostic has competing rows; not an identity link"
            return result
        else:
            result["census_comparison_status"] = "no_graph_or_unique_exact_text_diagnostic_endpoint"
            result["census_comparison_basis"] = "no_unique_comparator"
            result["census_comparison_interpretation"] = "no comparison endpoint selected; no value is inferred"
            return result
    if chosen is None:
        result["census_comparison_status"] = "candidate_2021_source_record_missing_from_selected_source"
        result["census_comparison_basis"] = basis
        result["census_comparison_interpretation"] = "candidate endpoint absent; no replacement or inference"
        return result

    quality = chosen.get("population_value_quality")
    official_value = chosen.get("population")
    compare_class, interpretation, difference = official_comparison_class(
        int(assertion["population_value"]), int(official_value) if official_value is not None else None, quality)
    result.update({
        "census_comparison_status": compare_class,
        "census_comparison_basis": basis,
        "census_comparison_source_record_id": chosen["source_record_id"],
        "census_comparison_locator": chosen.get("source_locator") or chosen.get("source_file"),
        "census_comparison_graph_path_json": json.dumps(path, ensure_ascii=False) if path is not None else None,
        "census_comparison_population": official_value,
        "census_comparison_population_quality": quality,
        "census_comparison_population_scope": chosen.get("population_scope"),
        "census_comparison_source_file": chosen.get("source_file"),
        "census_comparison_difference": difference,
        "census_comparison_interpretation": interpretation + "; identity links and comparisons do not certify census-date boundary equivalence",
        "census_comparison_identity_admission": False,
    })
    return result


def stage(binding_root: Path = BINDING_ROOT, selected_path: Path = SELECTED_SOURCE,
          graph_path: Path = ACCEPTED_GRAPH, output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(output_root)
    bindings_path = binding_root / "possible_module_entry_bindings.parquet"
    annual_path = binding_root / "annual_assertion_binding_candidates.parquet"
    held_path = binding_root / "held_annual_assertion_bindings.parquet"
    binding_manifest_path = binding_root / "manifest.json"
    binding_manifest = json.loads(binding_manifest_path.read_text(encoding="utf-8"))
    for path in (bindings_path, annual_path, held_path):
        if sha256_file(path) != binding_manifest["outputs"][path.name]["sha256"]:
            raise ValueError(f"module binding input changed: {path.name}")

    candidate_rows = pq.read_table(bindings_path).to_pylist()
    candidate_by_id = {r["candidate_id"]: r for r in candidate_rows}
    if len(candidate_by_id) != len(candidate_rows):
        raise ValueError("duplicate module entry candidate IDs")
    qids, codes = Counter(r["wikidata_qid"] for r in candidate_rows), Counter(r["current_source_oktmo_exact_digits"] for r in candidate_rows)
    if max(qids.values(), default=0) > 1 or max(codes.values(), default=0) > 1:
        raise ValueError("v1 possible bindings no longer have unique QID/code")
    for candidate in candidate_rows:
        if candidate["module_title_comment_raw"] != candidate["article_canonical_title"]:
            raise ValueError(f"module comment/API canonical title mismatch: {candidate['candidate_id']}")
        try:
            urls = json.loads(candidate["wikidata_tsv_article_urls_json"] or "[]")
            labels = json.loads(candidate["wikidata_tsv_ru_labels_json"] or "[]")
            claims = json.loads(candidate["wikidata_truthy_exact_p764_claims_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            raise ValueError(f"malformed Wikidata evidence JSON: {candidate['candidate_id']}")
        linked_titles = {urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/wiki/", 1)[-1]).replace("_", " ")
                         for url in urls if "/wiki/" in urllib.parse.urlsplit(url).path}
        qid = candidate["wikidata_qid"]
        code = candidate["current_source_oktmo_exact_digits"]
        if candidate["article_canonical_title"] not in linked_titles:
            raise ValueError(f"candidate lacks its exact Wikidata RU article URL: {candidate['candidate_id']}")
        if candidate["current_source_name"] not in labels:
            raise ValueError(f"candidate lacks the exact current-source RU label: {candidate['candidate_id']}")
        if candidate["wikidata_tsv_exact_p764_value_raw"] != code or not any(c.get("value_exact_digits") == code for c in claims):
            raise ValueError(f"candidate P764 evidence does not equal the current code: {candidate['candidate_id']}")
        if not qid or not candidate.get("article_revision_id"):
            raise ValueError(f"candidate lacks raw QID/article revision evidence: {candidate['candidate_id']}")
    annual_rows = pq.read_table(annual_path).to_pylist()
    held_rows = pq.read_table(held_path).to_pylist()
    if any(r["candidate_id"] not in candidate_by_id for r in annual_rows + held_rows):
        raise ValueError("annual assertion references a missing module entry candidate")
    if any("Wikipedia secondary" not in str(r.get("source_class", ""))
           or r.get("exact_population_status") != "unknown"
           or int(r["population_value_raw"]) != int(r["population_value"])
           for r in annual_rows + held_rows):
        raise ValueError("raw source class/value/precision invariants changed")
    if any(int(r["observation_year"]) > 2025 for r in annual_rows + held_rows):
        raise ValueError("future observation year is outside the frozen candidate maximum")

    source_table = pq.read_table(selected_path, columns=SELECTED_COLUMNS)
    selected_rows = source_table.to_pylist()
    selected_by_id: dict[str, dict[str, Any]] = {}
    for row in selected_rows:
        sid = row["source_record_id"]
        if sid:
            if sid in selected_by_id:
                raise ValueError(f"selected source_record_id is not unique: {sid}")
            selected_by_id[sid] = row
    diagnostic_by_year_key: dict[tuple[int, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    source_years = set()
    for row in selected_rows:
        year = int(row["census_year"])
        source_years.add(year)
        if (row.get("snapshot_record_type") == "settlement_observation"
                and row.get("population_scope") != "federal_city_region"
                and row.get("name_norm") and row.get("type_norm") and row.get("region_norm")):
            diagnostic_by_year_key[(year, row["name_norm"], row["type_norm"], row["region_norm"])].append(row)
    for candidate in candidate_rows:
        sid = candidate["current_source_record_id"]
        target = selected_by_id.get(sid)
        if not target or int(target["census_year"]) != 2021:
            raise ValueError(f"candidate lacks its unique selected 2021 source endpoint: {sid}")
        if (str(target.get("oktmo")) != candidate["current_source_oktmo_exact_digits"]
                or target.get("settlement_name") != candidate["current_source_name"]
                or target.get("settlement_type") != candidate["current_source_type"]
                or target.get("region_raw") != candidate["current_source_region"]):
            raise ValueError(f"candidate/current source evidence no longer agrees: {candidate['candidate_id']}")
        candidate["current_name_norm"] = target.get("name_norm") or ""
        candidate["current_type_norm"] = target.get("type_norm") or ""
        candidate["current_region_norm"] = target.get("region_norm") or ""

    graph_rows = pq.read_table(graph_path, columns=GRAPH_COLUMNS).to_pylist()
    graph_adjacency, graph_pair_edges, graph_node_year = _accepted_graph_index(graph_rows)
    staged_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    comparison_statuses = Counter()
    comparison_statuses_by_year = Counter()
    comparison_bases = Counter()
    comparison_qualities = Counter()
    source_kinds = Counter()
    assertion_scopes = Counter()
    assertion_source_classes = Counter()
    assertion_exactness = Counter()
    year_counts = Counter()
    for assertion in annual_rows:
        candidate = candidate_by_id[assertion["candidate_id"]]
        comparison = compare_module_assertion(assertion, candidate, selected_by_id,
                                              diagnostic_by_year_key, graph_adjacency,
                                              graph_pair_edges, graph_node_year, source_years)
        row = dict(assertion)
        row.update(comparison)
        row.update({
            "staging_status": "staged_source_named_history_series_candidate",
            "staging_version": VERSION,
            "identity_chain_scope": "source_named_history_series",
            "physical_site_continuity_status": "unverified; no automatic physical continuity from earliest year to 2025",
            "place_identity_admission": False,
            "population_admission": False,
            "official_population_replaced": False,
        })
        staged_rows.append(row)
        if int(assertion["observation_year"]) in COMPARISON_YEARS or int(assertion["observation_year"]) >= 1990:
            comparison_rows.append(row)
        comparison_statuses[comparison["census_comparison_status"]] += 1
        comparison_statuses_by_year[(int(assertion["observation_year"]), comparison["census_comparison_status"])] += 1
        comparison_bases[str(comparison["census_comparison_basis"])] += 1
        comparison_qualities[str(comparison["census_comparison_population_quality"])] += 1
        source_kinds[assertion["source_reference_kind"]] += 1
        assertion_scopes[str(assertion["population_scope"])] += 1
        assertion_source_classes[str(assertion["source_class"])] += 1
        assertion_exactness[str(assertion["exact_population_status"])] += 1
        year_counts[int(assertion["observation_year"])] += 1

    out = output_root
    out.mkdir(parents=True)
    for row in held_rows:
        row["staging_status"] = "held_conflicting_module_entry_year"
        row["identity_chain_scope"] = "source_named_history_series"
        row["physical_site_continuity_status"] = "unverified; held conflict is not resolved"
        row["place_identity_admission"] = False
        row["population_admission"] = False
        row["official_population_replaced"] = False
    artifact_frames = {
        "staged_annual_module_series.parquet": staged_rows,
        "census_comparisons_and_diagnostics.parquet": comparison_rows,
        "held_conflicting_annual_assertions.parquet": held_rows,
    }
    for name, rows in artifact_frames.items():
        pq.write_table(pa.Table.from_pylist(rows), out / name, compression="zstd")

    # The 2010 official source explicitly marks many values as privacy perturbed;
    # comparison differences are retained with their source quality field.
    report = {
        "staging_version": VERSION,
        "status": "staged_pending_separate_review",
        "rule": "candidate source_named_history_series; no physical-place continuity or population admission",
        "input_receipts": {
            "module_binding_manifest": {"path": str(binding_manifest_path), "sha256": sha256_file(binding_manifest_path)},
            "module_entry_bindings": {"path": str(bindings_path), "sha256": sha256_file(bindings_path), "rows": len(candidate_rows)},
            "annual_assertion_candidates": {"path": str(annual_path), "sha256": sha256_file(annual_path), "rows": len(annual_rows)},
            "held_annual_assertions": {"path": str(held_path), "sha256": sha256_file(held_path), "rows": len(held_rows)},
            "selected_official_observations": {"path": str(selected_path), "sha256": sha256_file(selected_path), "rows": source_table.num_rows, "years_present": sorted(source_years)},
            "accepted_identity_graph": {"path": str(graph_path), "sha256": sha256_file(graph_path), "rows": len(graph_rows), "same_place_active_edges_used": sum(1 for e in graph_rows if e["relation"] == "same_place" and e["decision_status"] in ACCEPTED_GRAPH_STATUSES and e["selection_projection_status"] in ACTIVE_PROJECTIONS)},
        },
        "candidate_entry_count": len(candidate_rows),
        "staged_annual_assertion_count": len(staged_rows),
        "held_conflicting_annual_assertion_count": len(held_rows),
        "place_identity_admission_count": 0,
        "population_admission_count": 0,
        "spatial_admission_count": 0,
        "observed_year_coverage": {
            "minimum": min(year_counts, default=None), "maximum": max(year_counts, default=None),
            "distinct_year_count": len(year_counts), "row_count_by_year": {str(y): year_counts[y] for y in sorted(year_counts)},
        },
        "source_reference_kind_counts": dict(source_kinds),
        "annual_assertion_provenance_and_scope": {
            "population_scope_counts": dict(assertion_scopes),
            "source_class_counts": dict(assertion_source_classes),
            "exact_population_status_counts": dict(assertion_exactness),
            "interpretation": "the module asserts its object scope; this pipeline does not independently certify the geographic unit, reference date, census/estimate status, or exactness",
        },
        "census_comparison_policy": {
            "same_years_requested": sorted(COMPARISON_YEARS),
            "accepted_graph_first_years": [2002, 2010],
            "current_endpoint_year": 2021,
            "diagnostic_fallback": "exact existing normalized name/type/region triple only; comparison-only, never an identity edge",
            "selected_source_years_unavailable": sorted(COMPARISON_YEARS - source_years),
            "other_annual_years_from_1990": "each receives an explicit no-same-year-selected-census status; no adjacent-year comparison is synthesized",
            "official_value_quality_counts": dict(comparison_qualities),
            "comparison_result_counts": dict(comparison_statuses),
            "comparison_result_counts_by_year": {f"{year}:{status}": count for (year, status), count in sorted(comparison_statuses_by_year.items())},
            "comparison_basis_counts": dict(comparison_bases),
            "2010_quality_caveat": "confidentiality_perturbed_within_ten values are called protected-value differences; mismatch is not treated as evidence that Wikipedia is wrong",
        },
        "known_exceptions_and_holds": [
            "RUS-AAA / Адыгея remains held as a region-level array without exact raw article-title evidence.",
            "Севастополь has an НП-Крым article template and no P17-based veto; its exact source row is federal_city_region scope, so it is not linked to a physical NP record.",
            "Германовский remains held: current 2021 source label differs from the article/comment label, the article uses Бывший НП, and the official source value is zero; no identity is inferred from a substring or zero.",
            "The duplicate Ононск module entries and three contradictory module-entry/year groups stay held.",
        ],
        "source_and_identity_limits": [
            "Annual values remain raw Wikipedia secondary assertions; underlying citations were not mass-fetched or independently verified.",
            "Citation blanks/unresolved references, census versus estimate status, reference-date alignment, population boundaries, and exactness remain unknown.",
            "Accepted graph edges inform only source-row comparison endpoints; their identity admission does not transfer that identity to the Wikipedia module series.",
            "No official value is replaced, no zero or missing year is inferred, and no interpolation or municipal aggregate allocation is generated.",
            "This staging contains no future observation year beyond 2025 and no blanket point reuse for old or changed places.",
        ],
        "outputs": {},
    }
    for name in artifact_frames:
        path = out / name
        report["outputs"][name] = {"path": str(path), "sha256": sha256_file(path), "rows": pq.read_metadata(path).num_rows, "format": "Parquet/Zstandard"}
    manifest_path = out / "staging_manifest.json"
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding-root", type=Path, default=BINDING_ROOT)
    parser.add_argument("--selected-source", type=Path, default=SELECTED_SOURCE)
    parser.add_argument("--accepted-graph", type=Path, default=ACCEPTED_GRAPH)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(stage(args.binding_root, args.selected_source, args.accepted_graph, args.output_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
