"""Replay independently reviewed same-census publication bindings onto R2 edges.

This migration changes only selected 2010 source-row endpoints. It preserves the
original same_place decision IDs, edge evidence, and source endpoint history;
it does not create or upgrade any cross-census identity decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

REVIEW_REL = Path(
    "research_rebuild/evidence/reviews/"
    "national_source_selection_r2_publication_binding_review_r1_20260930/review.json"
)
R2_REL = Path(
    "research_rebuild/evidence/releases/"
    "national_source_selection_r2_regional_2010_20260930"
)
R5B_REL = Path(
    "research_rebuild/evidence/releases/"
    "national_reviewed_admissions_r5b_yearbook_20260930"
)
EXPECTED_BINDINGS = 50
EXPECTED_EDGES = 54
EXPECTED_COORDINATE_CLAIMS = 81
EXPECTED_REVIEW_ID = "national_source_selection_r2_publication_binding_review_r1_20260930"
EXPECTED_R2_MANIFEST_SHA256 = "19beeaaf0caab6dbb79c04046b43abc6fcc0884ff6c37668406344643ab9630f"
EXPECTED_R5B_MANIFEST_SHA256 = "0bf4c442df7e1e3a0c9148c08c7cde2f43235ebde6ca608b762891d8ee26093c"
EXPECTED_REVIEW_JSON_SHA256 = "d752719a701d920f573ae3e8009fb88217f1133a121774cdc534bc7244362361"


class MigrationError(ValueError):
    """Raised when source, review, or graph invariants fail closed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_manifest_pins(manifest_path: Path, expected_manifest_sha: str,
                          root: Path, *, label: str) -> dict[str, Any]:
    if _sha256(manifest_path) != expected_manifest_sha:
        raise MigrationError(f"{label} release manifest hash does not match the pinned release")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relpath, record in manifest.get("outputs", {}).items():
        path = manifest_path.parent / relpath
        if not path.is_file() or _sha256(path) != record.get("sha256"):
            raise MigrationError(f"{label} release output is missing or changed: {relpath}")
    for relpath, record in manifest.get("verified_inputs", {}).items():
        path = root / relpath
        expected_hash = record.get("sha256") if isinstance(record, dict) else record
        if path.is_file() and _sha256(path) != expected_hash:
            raise MigrationError(f"{label} pinned input changed: {relpath}")
    return manifest


def _binding_id(review_id: str, old_id: str, new_id: str) -> str:
    payload = "\0".join((review_id, old_id, new_id)).encode("utf-8")
    return "PUBLISHED-BINDING-R2-" + hashlib.sha256(payload).hexdigest()[:24]


def _load_selected(selected: pd.DataFrame) -> pd.DataFrame:
    required = {"source_record_id", "census_year", "population"}
    missing = required - set(selected.columns)
    if missing:
        raise MigrationError(f"selected observations missing columns: {sorted(missing)}")
    result = selected.copy()
    if result.source_record_id.isna().any() or result.source_record_id.astype("string").str.strip().eq("").any():
        raise MigrationError("selected source_record_id contains null or blank values")
    result["source_record_id"] = result.source_record_id.astype(str)
    if result.source_record_id.duplicated().any():
        raise MigrationError("selected source_record_id values are not unique")
    result["census_year"] = pd.to_numeric(result.census_year, errors="raise").astype(int)
    return result


def _validate_review(review: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
    review_id = str(review.get("review_id", ""))
    if review_id != EXPECTED_REVIEW_ID:
        raise MigrationError(f"unexpected publication-binding review ID: {review_id!r}")
    if not str(review.get("verdict", "")).startswith("PASS: accept 50 unique 2010 publication bindings"):
        raise MigrationError("publication-binding review does not carry its accepted verdict")
    summary = review.get("binding_summary") or {}
    expected_summary = {
        "packet_rows": EXPECTED_EDGES,
        "unique_displaced_2010_endpoints": EXPECTED_BINDINGS,
        "unique_replacement_2010_endpoints": EXPECTED_BINDINGS,
        "accepted_bindings": EXPECTED_BINDINGS,
        "held": 0,
        "affected_identity_edges": EXPECTED_EDGES,
    }
    for field, expected in expected_summary.items():
        if int(summary.get(field, -1)) != expected:
            raise MigrationError(f"review {field}={summary.get(field)!r}; expected {expected}")
    bindings = review.get("binding_reviews")
    dispositions = review.get("edge_dispositions")
    if not isinstance(bindings, list) or len(bindings) != EXPECTED_BINDINGS:
        raise MigrationError("review must contain exactly 50 binding review rows")
    if not isinstance(dispositions, list) or len(dispositions) != EXPECTED_EDGES:
        raise MigrationError("review must contain exactly 54 affected edge dispositions")

    old_ids: set[str] = set()
    new_ids: set[str] = set()
    edge_ids: set[str] = set()
    for binding in bindings:
        old_id = str(binding.get("old_2010_source_record_id", ""))
        new_id = str(binding.get("replacement_2010_source_record_id", ""))
        if not old_id or not new_id or old_id == new_id:
            raise MigrationError("review binding has missing or identical old/new endpoint IDs")
        if binding.get("verdict") != "accept_publication_binding":
            raise MigrationError(f"binding {old_id!r} is not accepted by review")
        if binding.get("component") not in {"murmansk", "kaliningrad", "arkhangelsk_nao"}:
            raise MigrationError(f"binding {old_id!r} has an unexpected component")
        if binding.get("reason", "").find("same-census publication equivalence only") < 0:
            raise MigrationError(f"binding {old_id!r} lacks the limited publication-equivalence scope")
        if binding.get("identity_decision") not in (None, "preserved unchanged"):
            raise MigrationError(f"binding {old_id!r} changes identity-decision semantics")
        if old_id in old_ids or new_id in new_ids:
            raise MigrationError("review bindings are not one-to-one")
        old_ids.add(old_id)
        new_ids.add(new_id)
        affected = binding.get("affected_identity_edge_ids")
        if not isinstance(affected, list) or not affected:
            raise MigrationError(f"binding {old_id!r} has no affected identity edge IDs")
        if int(binding.get("affected_edge_count", -1)) != len(affected):
            raise MigrationError(f"binding {old_id!r} affected edge count does not match its ID list")
        if edge_ids.intersection(map(str, affected)):
            raise MigrationError("review assigns an affected identity edge to multiple bindings")
        edge_ids.update(map(str, affected))

    disposition_ids: set[str] = set()
    disposition_pairs: dict[str, tuple[str, str]] = {}
    for disposition in dispositions:
        edge_id = str(disposition.get("affected_identity_edge_id", ""))
        old_id = str(disposition.get("displaced_2010_source_record_id", ""))
        new_id = str(disposition.get("replacement_2010_source_record_id", ""))
        if not edge_id or edge_id in disposition_ids:
            raise MigrationError("review edge dispositions contain a missing or duplicate edge ID")
        if disposition.get("binding_verdict") != "accept_publication_binding":
            raise MigrationError(f"edge disposition {edge_id!r} is not accepted")
        if disposition.get("effect") != "eligible_to_restore_original_same_place_edge_endpoint":
            raise MigrationError(f"edge disposition {edge_id!r} has a wrong-kind effect")
        if disposition.get("identity_decision") != "preserved unchanged":
            raise MigrationError(f"edge disposition {edge_id!r} changes same_place decision semantics")
        if old_id not in old_ids or new_id not in new_ids:
            raise MigrationError(f"edge disposition {edge_id!r} references an unreviewed binding")
        disposition_ids.add(edge_id)
        disposition_pairs[edge_id] = (old_id, new_id)
    if edge_ids != disposition_ids:
        raise MigrationError("binding rows and edge dispositions do not cover the same exact edge IDs")
    binding_pairs = {
        str(b["old_2010_source_record_id"]): str(b["replacement_2010_source_record_id"])
        for b in bindings
    }
    if any(binding_pairs[old] != new for old, new in disposition_pairs.values()):
        raise MigrationError("edge dispositions disagree with reviewed old/new binding pairs")
    return review_id, str(review.get("upstream_manifest_sha256", "")), bindings, dispositions


def _assert_component_year_invariant(edges: pd.DataFrame, selected: pd.DataFrame) -> dict[str, int]:
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        if parent[item] != item:
            parent[item] = find(parent[item])
        return parent[item]

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for row in edges.itertuples(index=False):
        union(str(row.from_source_record_id), str(row.to_source_record_id))
    node_ids = set(edges.from_source_record_id.astype(str)) | set(edges.to_source_record_id.astype(str))
    metadata = selected[selected.source_record_id.isin(node_ids)][["source_record_id", "census_year"]].copy()
    if set(metadata.source_record_id.astype(str)) != node_ids:
        raise MigrationError("migrated graph contains an endpoint absent from current selected observations")
    metadata["component"] = metadata.source_record_id.map(find)
    counts = metadata.groupby(["component", "census_year"], dropna=False).source_record_id.nunique()
    if counts.gt(1).any():
        raise MigrationError("migrated same_place component contains multiple selected observations in one census year")
    years = metadata.groupby("component").census_year.agg(lambda values: set(map(int, values)))
    full = years.map(lambda values: values == {2002, 2010, 2021})
    return {
        "vertices": len(node_ids),
        "components": int(years.size),
        "full_2002_2010_2021_components": int(full.sum()),
        "same_year_component_collisions": 0,
    }


def _assert_source_rows_unchanged(projected: pd.DataFrame, source: pd.DataFrame, *, label: str) -> None:
    if "decision_id" not in projected or "decision_id" not in source:
        raise MigrationError(f"{label} is missing decision_id")
    if projected.decision_id.astype(str).duplicated().any() or source.decision_id.astype(str).duplicated().any():
        raise MigrationError(f"{label} has duplicate decision IDs")
    if set(projected.decision_id.astype(str)) != set(source.decision_id.astype(str)):
        raise MigrationError(f"{label} projection IDs do not match the R5b source ledger")
    columns = list(source.columns)
    if not set(columns) <= set(projected.columns):
        raise MigrationError(f"{label} projection is missing source ledger columns")
    left = projected[columns].copy()
    right = source[columns].copy()
    left["decision_id"] = left.decision_id.astype(str)
    right["decision_id"] = right.decision_id.astype(str)
    left = left.sort_values("decision_id", kind="stable").reset_index(drop=True)
    right = right.sort_values("decision_id", kind="stable").reset_index(drop=True)
    for column in columns:
        if left[column].fillna("").astype(str).tolist() != right[column].fillna("").astype(str).tolist():
            raise MigrationError(f"{label} source values differ from the pinned R5b ledger in {column}")


def migrate_records(
    edges: pd.DataFrame,
    points: pd.DataFrame,
    selected: pd.DataFrame,
    review: dict[str, Any],
    *,
    enforce_production_counts: bool = False,
    source_edges: pd.DataFrame | None = None,
    source_points: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Validate and replay reviewed bindings; safe to test with synthetic frames."""
    review_id, review_manifest_sha, bindings, dispositions = _validate_review(review)
    selected = _load_selected(selected)
    selected_ids = set(selected.source_record_id)
    year_by_id = selected.set_index("source_record_id").census_year.to_dict()
    if source_edges is not None:
        _assert_source_rows_unchanged(edges, source_edges, label="identity edge")
    if source_points is not None:
        _assert_source_rows_unchanged(points, source_points, label="coordinate claim")

    required_edge_cols = {
        "decision_id", "relation", "from_source_record_id", "from_year",
        "to_source_record_id", "to_year", "decision_status", "selection_projection_status",
    }
    missing = required_edge_cols - set(edges.columns)
    if missing:
        raise MigrationError(f"identity edge projection missing columns: {sorted(missing)}")
    if edges.decision_id.astype(str).duplicated().any():
        raise MigrationError("identity edge decision IDs are not unique")
    if set(edges.relation.astype(str)) != {"same_place"}:
        raise MigrationError("projection contains an event or non-same_place relation; migration is same_place-only")
    statuses = edges.selection_projection_status.astype(str).value_counts().to_dict()
    if statuses != {"active_endpoints_selected": len(edges) - EXPECTED_EDGES,
                    "held_endpoint_not_selected_pending_publication_binding": EXPECTED_EDGES}:
        raise MigrationError(f"unexpected R2 edge projection statuses: {statuses}")
    if enforce_production_counts and (len(edges) != 1162 or len(bindings) != EXPECTED_BINDINGS):
        raise MigrationError("production migration requires the pinned 1,162-edge/50-binding release")

    if points.empty or "selection_projection_status" not in points:
        raise MigrationError("coordinate projection missing or malformed")
    if len(points) != EXPECTED_COORDINATE_CLAIMS or not points.selection_projection_status.eq("active_endpoints_selected").all():
        raise MigrationError("expected all 81 existing coordinate claims to remain active")
    point_endpoint_cols = [c for c in ("target_source_record_id", "coordinate_source_record_id") if c in points]
    if not point_endpoint_cols:
        raise MigrationError("coordinate projection has no observation endpoint columns")
    for column in point_endpoint_cols:
        if not set(points[column].dropna().astype(str)) <= selected_ids:
            raise MigrationError(f"coordinate endpoint {column} is absent from current selected observations")

    binding_by_old = {str(b["old_2010_source_record_id"]): b for b in bindings}
    disposition_by_edge = {str(d["affected_identity_edge_id"]): d for d in dispositions}
    held = edges[edges.selection_projection_status.eq("held_endpoint_not_selected_pending_publication_binding")]
    if set(held.decision_id.astype(str)) != set(disposition_by_edge):
        raise MigrationError("held projection edge IDs differ from the 54 reviewed edge dispositions")

    out = edges.copy()
    out["original_from_source_record_id"] = out.from_source_record_id.astype(str)
    out["original_to_source_record_id"] = out.to_source_record_id.astype(str)
    out["migration_publication_binding_from"] = ""
    out["migration_publication_binding_to"] = ""
    out["pre_migration_selection_projection_status"] = out.selection_projection_status.astype(str)
    out["migration_scope"] = ""

    reviewed_binding_rows: list[dict[str, Any]] = []
    review_entry_id_by_pair: dict[tuple[str, str], str] = {}
    binding_id_by_old: dict[str, str] = {}
    for b in bindings:
        old_id = str(b["old_2010_source_record_id"])
        new_id = str(b["replacement_2010_source_record_id"])
        if old_id in selected_ids:
            raise MigrationError(f"displaced source endpoint is unexpectedly current-selected: {old_id}")
        if new_id not in selected_ids:
            raise MigrationError(f"reviewed replacement endpoint is absent from current selected observations: {new_id}")
        if int(year_by_id[new_id]) != 2010:
            raise MigrationError(f"replacement endpoint is not a selected 2010 observation: {new_id}")
        binding_id = _binding_id(review_id, old_id, new_id)
        binding_id_by_old[old_id] = binding_id
        review_entry_id = "R2-REVIEW-ENTRY-" + hashlib.sha256((old_id + "\0" + new_id).encode()).hexdigest()[:24]
        review_entry_id_by_pair[(old_id, new_id)] = review_entry_id
        reviewed_binding_rows.append({
            "publication_binding_id": binding_id,
            "review_entry_id": review_entry_id,
            "review_id": review_id,
            "upstream_release_manifest_sha256": review_manifest_sha,
            "old_2010_source_record_id": old_id,
            "replacement_2010_source_record_id": new_id,
            "old_source_sha256": (b.get("old_source") or {}).get("sha256"),
            "old_source_locator": (b.get("old_source") or {}).get("locator"),
            "replacement_source_sha256": (b.get("replacement_source") or {}).get("sha256"),
            "replacement_source_locator": (b.get("replacement_source") or {}).get("locator"),
            "component": b.get("component"),
            "affected_identity_edge_ids": json.dumps(b["affected_identity_edge_ids"], ensure_ascii=False, separators=(",", ":")),
            "affected_edge_count": int(b["affected_edge_count"]),
            "verdict": b["verdict"],
            "effect": "same_census_publication_equivalence_only",
            "identity_decision": "preserved unchanged",
            "reason": b.get("reason", ""),
        })

    rows_by_id = out.set_index(out.decision_id.astype(str), drop=False)
    for edge_id, d in disposition_by_edge.items():
        if edge_id not in rows_by_id.index:
            raise MigrationError(f"reviewed held edge is absent from projection: {edge_id}")
        row = rows_by_id.loc[edge_id]
        if isinstance(row, pd.DataFrame):
            raise MigrationError(f"duplicate projected edge ID: {edge_id}")
        if str(row.relation) != "same_place":
            raise MigrationError(f"review edge {edge_id} is not a same_place relation")
        if str(row.selection_projection_status) != "held_endpoint_not_selected_pending_publication_binding":
            raise MigrationError(f"review edge {edge_id} is not held for endpoint migration")
        old_id = str(d["displaced_2010_source_record_id"])
        new_id = str(d["replacement_2010_source_record_id"])
        binding = binding_by_old.get(old_id)
        if not binding or str(binding["replacement_2010_source_record_id"]) != new_id:
            raise MigrationError(f"review edge {edge_id} has no exact accepted old/new pair")
        from_id, to_id = str(row.from_source_record_id), str(row.to_source_record_id)
        from_year, to_year = int(row.from_year), int(row.to_year)
        if from_id == old_id and from_year == 2010:
            endpoint_column, binding_column = "from_source_record_id", "migration_publication_binding_from"
        elif to_id == old_id and to_year == 2010:
            endpoint_column, binding_column = "to_source_record_id", "migration_publication_binding_to"
        else:
            raise MigrationError(f"review edge {edge_id} does not contain its displaced 2010 endpoint")
        if int((from_id == old_id) + (to_id == old_id)) != 1:
            raise MigrationError(f"review edge {edge_id} has ambiguous displaced endpoint")
        out.loc[out.decision_id.astype(str).eq(edge_id), endpoint_column] = new_id
        out.loc[out.decision_id.astype(str).eq(edge_id), binding_column] = binding_id_by_old[old_id]
        out.loc[out.decision_id.astype(str).eq(edge_id), "selection_projection_status"] = "active_after_reviewed_publication_binding_migration"
        out.loc[out.decision_id.astype(str).eq(edge_id), "migration_scope"] = "endpoint publication equivalence; same_place identity evidence and decision unchanged"

    if set(out.decision_id.astype(str)) != set(edges.decision_id.astype(str)):
        raise MigrationError("migration changed the identity-decision ID set")
    if out.decision_id.astype(str).duplicated().any():
        raise MigrationError("migration created duplicate identity-decision IDs")
    if set(out.selection_projection_status.astype(str)) != {"active_endpoints_selected", "active_after_reviewed_publication_binding_migration"}:
        raise MigrationError("some identity edges remain non-active after reviewed endpoint migration")
    for column in ("from_source_record_id", "to_source_record_id"):
        if not set(out[column].astype(str)) <= selected_ids:
            raise MigrationError(f"migrated edge endpoint column {column} contains a dangling/nonselected ID")
    for row in out.itertuples(index=False):
        if int(year_by_id[str(row.from_source_record_id)]) != int(row.from_year):
            raise MigrationError(f"from endpoint year mismatch for {row.decision_id}")
        if int(year_by_id[str(row.to_source_record_id)]) != int(row.to_year):
            raise MigrationError(f"to endpoint year mismatch for {row.decision_id}")
    if out.from_year.astype(int).equals(edges.from_year.astype(int)) is False or out.to_year.astype(int).equals(edges.to_year.astype(int)) is False:
        raise MigrationError("migration changed edge census-year fields")

    existing_binding_ids: set[str] = set()
    for column in ("endpoint_publication_binding_from", "endpoint_publication_binding_to"):
        if column in out:
            existing_binding_ids |= set(out[column].dropna().astype(str)) - {""}
    created_binding_ids = set(binding_id_by_old.values())
    if existing_binding_ids & created_binding_ids:
        raise MigrationError("generated publication binding IDs collide with existing endpoint bindings")

    graph_summary = _assert_component_year_invariant(out, selected)
    if len(reviewed_binding_rows) != EXPECTED_BINDINGS:
        raise MigrationError("migration did not emit exactly 50 approved publication bindings")
    if int(out.selection_projection_status.eq("active_after_reviewed_publication_binding_migration").sum()) != EXPECTED_EDGES:
        raise MigrationError("migration did not restore exactly the 54 reviewed held edges")
    audit = {
        "status": "reviewed_publication_binding_migration_built_pending_independent_graph_review",
        "review_id": review_id,
        "upstream_release_manifest_sha256": review_manifest_sha,
        "migration_scope": "remap exact displaced 2010 publication-row endpoints only; preserve same_place decision IDs and identity evidence",
        "counts": {
            "input_edges": int(len(edges)),
            "active_before": int(edges.selection_projection_status.eq("active_endpoints_selected").sum()),
            "held_before": int(held.shape[0]),
            "approved_unique_publication_bindings": int(len(reviewed_binding_rows)),
            "migrated_identity_edges": int(out.selection_projection_status.eq("active_after_reviewed_publication_binding_migration").sum()),
            "active_edges_after": int(out.selection_projection_status.isin(["active_endpoints_selected", "active_after_reviewed_publication_binding_migration"]).sum()),
            "identity_decision_ids_preserved": True,
            "coordinate_claims_input": int(len(points)),
            "coordinate_claims_changed": 0,
        },
        "graph_invariants": graph_summary,
    }
    return pd.DataFrame(reviewed_binding_rows), out, audit


def build(data_root: Path, output_root: Path) -> dict[str, Any]:
    data_root = data_root.resolve()
    output_root = output_root.resolve()
    r2 = data_root / R2_REL
    r5b = data_root / R5B_REL
    repository_root = Path(__file__).resolve().parents[2]
    try:
        output_root.relative_to(repository_root)
    except ValueError:
        pass
    else:
        raise MigrationError("output directory must be outside the Git repository")
    review_path = data_root / REVIEW_REL
    inputs = {
        "selected_observations": r2 / "selected_observations.parquet",
        "identity_edge_projection": r2 / "identity_edge_selection_projection.csv",
        "coordinate_claim_projection": r2 / "coordinate_claim_selection_projection.csv",
        "review": review_path,
        "review_sha256_sidecar": review_path.with_suffix(".json.sha256"),
        "r2_release_manifest": r2 / "release_manifest.json",
        "r5b_release_manifest": r5b / "release_manifest.json",
        "r5b_identity_edges": r5b / "identity_edges_accepted.csv",
        "r5b_coordinate_claims": r5b / "coordinate_admissions.csv",
    }
    for label, path in inputs.items():
        if not path.is_file():
            raise FileNotFoundError(f"required {label} input not found: {path}")
    r2_manifest = _verify_manifest_pins(inputs["r2_release_manifest"], EXPECTED_R2_MANIFEST_SHA256,
                                        data_root, label="R2")
    r5b_manifest = _verify_manifest_pins(inputs["r5b_release_manifest"], EXPECTED_R5B_MANIFEST_SHA256,
                                         data_root, label="R5b")
    review_sidecar = inputs["review_sha256_sidecar"].read_text(encoding="utf-8").split()
    actual_review_sha = _sha256(inputs["review"])
    if not review_sidecar or review_sidecar[0] != actual_review_sha or actual_review_sha != EXPECTED_REVIEW_JSON_SHA256:
        raise MigrationError("publication-binding review JSON does not match its SHA-256 sidecar")
    if r5b_manifest.get("release_id") != R5B_REL.name or r2_manifest.get("release_id") != R2_REL.name:
        raise MigrationError("release manifest IDs do not match the expected R2/R5b assets")
    if r2_manifest.get("verified_inputs", {}).get(str((R5B_REL / "release_manifest.json").as_posix()), {}).get("sha256") != EXPECTED_R5B_MANIFEST_SHA256:
        raise MigrationError("R2 manifest does not bind the pinned R5b release manifest")
    selected = pd.read_parquet(inputs["selected_observations"])
    edges = pd.read_csv(inputs["identity_edge_projection"], dtype={
        "decision_id": "string", "from_source_record_id": "string", "to_source_record_id": "string",
        "relation": "string", "selection_projection_status": "string",
    })
    points = pd.read_csv(inputs["coordinate_claim_projection"], dtype={
        "target_source_record_id": "string", "coordinate_source_record_id": "string",
        "selection_projection_status": "string",
    })
    source_edges = pd.read_csv(inputs["r5b_identity_edges"], dtype={
        "decision_id": "string", "from_source_record_id": "string", "to_source_record_id": "string",
        "relation": "string",
    })
    source_points = pd.read_csv(inputs["r5b_coordinate_claims"], dtype={
        "decision_id": "string", "target_source_record_id": "string", "coordinate_source_record_id": "string",
    })
    review = json.loads(inputs["review"].read_text(encoding="utf-8"))
    binding_frame, migrated_edges, audit = migrate_records(
        edges, points, selected, review, enforce_production_counts=True,
        source_edges=source_edges, source_points=source_points,
    )
    binding_frame["review_json_sha256"] = actual_review_sha
    if output_root.exists():
        raise FileExistsError(f"immutable migration output already exists: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    binding_path = staging / "reviewed_publication_bindings.csv"
    edge_path = staging / "migrated_identity_edges.csv"
    audit_path = staging / "migration_audit.json"
    try:
        binding_frame.to_csv(binding_path, index=False)
        migrated_edges.to_csv(edge_path, index=False)
        audit["inputs"] = {
        label: {
            "path": path.relative_to(data_root).as_posix(),
            "input_root_role": "data_root",
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for label, path in inputs.items()
        }
        builder_path = Path(__file__).resolve()
        audit["builder"] = {
            "path": builder_path.relative_to(repository_root).as_posix(),
            "input_root_role": "git_checkout",
            "sha256": _sha256(builder_path),
            "bytes": builder_path.stat().st_size,
        }
        audit["outputs"] = {
            binding_path.name: {"sha256": _sha256(binding_path), "bytes": binding_path.stat().st_size, "rows": len(binding_frame)},
            edge_path.name: {"sha256": _sha256(edge_path), "bytes": edge_path.stat().st_size, "rows": len(migrated_edges)},
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
    parser.add_argument("--data-root", type=Path, required=True, help="Root containing research_rebuild/evidence inputs")
    parser.add_argument("--output-root", type=Path, required=True, help="New output directory outside the repository")
    args = parser.parse_args(argv)
    try:
        audit = build(args.data_root, args.output_root)
    except (FileNotFoundError, FileExistsError, MigrationError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": audit["status"], "counts": audit["counts"], "graph_invariants": audit["graph_invariants"], "output_root": str(args.output_root.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
