"""Independent DFS and exact-column check of the reviewed publication migration.

This verifier deliberately does not import the migration builder. Its receipt
admits only the 54 endpoint transfers already supported by the pinned review;
it adds neither identity evidence nor coordinate admissions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(data_root: Path, migration_root: Path) -> dict:
    audit_path = migration_root / "migration_audit.json"
    audit = json.loads(audit_path.read_text())
    for entry in audit["inputs"].values():
        path = data_root / entry["path"]
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"input changed: {entry['path']}")
    for name, entry in audit["outputs"].items():
        path = migration_root / name
        if path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            raise ValueError(f"output changed: {name}")
    builder = Path(__file__).resolve().parents[2] / audit["builder"]["path"]
    if digest(builder) != audit["builder"]["sha256"]:
        raise ValueError("builder code changed since build")
    inputs = audit["inputs"]
    old = pd.read_csv(data_root / inputs["identity_edge_projection"]["path"], dtype=str).fillna("")
    new = pd.read_csv(migration_root / "migrated_identity_edges.csv", dtype=str).fillna("")
    original = pd.read_csv(data_root / inputs["r5b_identity_edges"]["path"], dtype=str).fillna("")
    if len(new) != 1162 or not new.decision_id.is_unique:
        raise ValueError("edge count or unique decision IDs changed")
    old = old.set_index("decision_id")
    new = new.set_index("decision_id").loc[old.index]
    original = original.set_index("decision_id").loc[old.index]
    mutable = {"from_source_record_id", "to_source_record_id", "selection_projection_status"}
    for col in old.columns.difference(list(mutable)):
        if not old[col].equals(new[col]):
            raise ValueError(f"nonendpoint projection column changed: {col}")
    for col in original.columns.difference(list(mutable)):
        if not original[col].equals(new[col]):
            raise ValueError(f"original identity evidence changed: {col}")
    changed = old.from_source_record_id.ne(new.from_source_record_id) | old.to_source_record_id.ne(new.to_source_record_id)
    if int(changed.sum()) != 54 or not old.loc[changed, "selection_projection_status"].str.startswith("held_").all():
        raise ValueError("migration changed edges outside held set")
    review = json.loads((data_root / inputs["review"]["path"]).read_text())
    selected = pd.read_parquet(data_root / inputs["selected_observations"]["path"]).set_index("source_record_id")
    transfers = {}
    representation_variations = []
    for binding in review["binding_reviews"]:
        if binding["verdict"] != "accept_publication_binding":
            raise ValueError("unaccepted binding")
        old_id, new_id = binding["old_2010_source_record_id"], binding["replacement_2010_source_record_id"]
        transfers[old_id] = new_id
        row = selected.loc[new_id]
        if int(row.census_year) != 2010:
            raise ValueError("publication migration is not within 2010")
        expected = binding["replacement_source"]
        for field, review_field in {"name_norm": "name", "type_norm": "type", "region_norm": "region", "population": "population_2010", "source_sha256": "sha256"}.items():
            if review_field not in expected or pd.isna(expected[review_field]):
                raise ValueError(f"review missing required replacement field: {new_id}:{review_field}")
            value = row[field]
            if field == "population":
                ok = pd.notna(value) and int(value) == int(expected[review_field])
            else:
                ok = value == expected[review_field]
                if field == "name_norm" and row.type_norm == "город" and isinstance(value, str) and value.startswith("г. "):
                    ok = value[3:] == expected[review_field]
                    if ok:
                        representation_variations.append({"source_record_id": new_id, "field": field, "selected_value": value, "review_value": expected[review_field], "rule": "remove separate literal city abbreviation г. with following space; not a word-prefix filter"})
            if not ok:
                raise ValueError(f"replacement row differs from review: {new_id}:{field}")
    if len(transfers) != 50 or len(set(transfers.values())) != 50:
        raise ValueError("publication bindings are not 50 one-to-one transfers")
    for endpoint in ("from_source_record_id", "to_source_record_id"):
        expected = old[endpoint].map(lambda sid: transfers.get(sid, sid))
        if not expected.equals(new[endpoint]):
            raise ValueError("endpoint differs from independently reviewed mapping")
    adjacency = defaultdict(set)
    for edge in new.itertuples():
        if edge.relation != "same_place":
            raise ValueError("event relation in same-place graph")
        a, b = edge.from_source_record_id, edge.to_source_record_id
        if a not in selected.index or b not in selected.index:
            raise ValueError("unselected endpoint")
        if int(selected.loc[a, "census_year"]) != int(edge.from_year) or int(selected.loc[b, "census_year"]) != int(edge.to_year):
            raise ValueError("edge year mismatch")
        adjacency[a].add(b)
        adjacency[b].add(a)
    visited, components, full_ids = set(), [], set()
    for start in sorted(adjacency):
        if start in visited:
            continue
        stack, component = [start], set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency[node] - component)
        years = selected.loc[list(component), "census_year"].astype(int).tolist()
        if len(years) != len(set(years)):
            raise ValueError("two observations of one year in one place component")
        if set(years) == {2002, 2010, 2021}:
            full_ids.update(component)
        visited.update(component)
        components.append(component)
    point_projection = pd.read_csv(data_root / inputs["coordinate_claim_projection"]["path"], dtype=str).fillna("")
    source_points = pd.read_csv(data_root / inputs["r5b_coordinate_claims"]["path"], dtype=str).fillna("")
    if len(point_projection) != 81 or not point_projection.selection_projection_status.eq("active_endpoints_selected").all():
        raise ValueError("coordinate projection changed")
    if not source_points.equals(point_projection[source_points.columns]):
        raise ValueError("original coordinate columns changed")
    coverage = {}
    for year, rows in selected.groupby("census_year"):
        linked, chained = rows.index.isin(visited), rows.index.isin(full_ids)
        denominator = int(rows.population.sum())
        coverage[str(int(year))] = {
            "selected_rows": len(rows), "selected_known_population": denominator,
            "linked_rows": int(linked.sum()), "linked_population": int(rows.loc[linked, "population"].sum()),
            "full_chain_rows": int(chained.sum()), "full_chain_population": int(rows.loc[chained, "population"].sum()),
            "linked_population_fraction": float(rows.loc[linked, "population"].sum() / denominator),
            "linked_record_fraction": float(linked.mean()),
            "full_chain_population_fraction": float(rows.loc[chained, "population"].sum() / denominator),
            "full_chain_record_fraction": float(chained.mean()),
        }
    return {
        "status": "accepted_reviewed_publication_endpoint_migration",
        "scope": "50 same-census publication bindings; 54 existing identity edges restored; no new identity or coordinate evidence",
        "migration_audit_sha256": digest(audit_path),
        "outputs": audit["outputs"], "inputs": inputs,
        "independent_verifier": {"path": "research_rebuild/mass_linkage/validate_migration.py", "sha256": digest(Path(__file__))},
        "graph": {"edges": len(new), "changed_edges": int(changed.sum()), "vertices": len(visited), "components": len(components), "full_chains": len(full_ids) // 3, "same_year_collisions": 0},
        "coordinate_claims_changed": 0, "coverage": coverage,
        "replacement_fields_checked": ["name", "type", "region", "population_2010", "source_sha256"],
        "representation_variations": representation_variations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--migration-root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError(args.receipt)
    receipt = validate(args.data_root, args.migration_root)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "graph": receipt["graph"]}))


if __name__ == "__main__":
    main()
