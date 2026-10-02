"""Apply the independently reviewed 2021→2022–2024 official city-series rule."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from .annual_yearbook import SOURCE_REL, sha

REVIEW_SHA = "f21d45d4ad0a40035a57167a65bc91faef843593855b39d0cd54b22fb9c699d1"
RULE = "official_named_city_series_2021_to_annual_2022_2024_v1"


def apply(data_root: Path, selected_path: Path, candidate_root: Path, review_path: Path, output_root: Path) -> dict:
    if output_root.exists():
        raise FileExistsError(output_root)
    if output_root.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError("outputs must be outside Git")
    if sha(review_path) != REVIEW_SHA:
        raise ValueError("independent rule-review bytes changed")
    review = json.loads(review_path.read_text())
    if review["status"] != "PASS_WITH_ENTITY_GRAIN_QUALIFIERS":
        raise ValueError("rule review is not accepted")
    pins = review["pinned_inputs"]
    bridge_path = data_root / SOURCE_REL / "bridge_candidates_2010_2021.csv"
    for path, key in [(bridge_path, "candidate_2010_2021_bridge_csv_sha256"), (selected_path, "selected_observations_r2_sha256"), (Path(__file__).with_name("annual_yearbook.py"), "annual_builder_sha256")]:
        if sha(path) != pins[key]:
            raise ValueError(f"reviewed input changed: {key}")
    manifest = json.loads((candidate_root / "manifest.json").read_text())
    population_path = candidate_root / "annual_observations.parquet"
    if sha(population_path) != manifest["outputs"][population_path.name]["sha256"]:
        raise ValueError("annual candidate table changed")
    candidates = pd.read_parquet(population_path)
    bridge = pd.read_csv(bridge_path, dtype=str).fillna("")
    selected = pd.read_parquet(selected_path).set_index("source_record_id")
    if not bridge.row_id.is_unique or not bridge["2021_source_record_id"].is_unique or not selected.index.is_unique:
        raise ValueError("competing city-series bindings")
    if len(candidates) != 516 or len(bridge) != 172 or not bridge["2021_match_count"].eq("1").all():
        raise ValueError("source series count or uniqueness changed")
    mapping = bridge.set_index("row_id")["2021_source_record_id"]
    candidates["target_2021_source_record_id"] = candidates.source_publication_row_id.map(mapping)
    if candidates.target_2021_source_record_id.isna().any():
        raise ValueError("annual source row lacks reviewed binding")
    for sid in mapping:
        if sid not in selected.index or int(selected.loc[sid, "census_year"]) != 2021:
            raise ValueError("2021 source endpoint is not selected")
    candidates["target_population_scope"] = candidates.target_2021_source_record_id.map(selected.population_scope)
    if not candidates.target_population_scope.isin(["settlement", "federal_city_region"]).all():
        raise ValueError("unexpected entity grain")
    aggregate = candidates.target_population_scope.eq("federal_city_region")
    if int(aggregate.sum()) != 9:
        raise ValueError("federal-city aggregates not preserved separately")
    candidates["annual_identity_status"] = "checked_rule_accepted"
    candidates["annual_identity_rule"] = RULE
    candidates["annual_identity_review_sha256"] = REVIEW_SHA
    candidates["census_row_binding_basis"] = "independently_reviewed_direct_2021_comparative_publication_row"
    edges = pd.DataFrame({
        "from_source_record_id": candidates.target_2021_source_record_id,
        "from_year": 2021,
        "to_source_record_id": candidates.source_record_id,
        "to_year": candidates.observation_year,
        "to_reference_date": candidates.reference_date,
        "relation": aggregate.map({True: "same_statistical_aggregate", False: "same_place"}),
        "entity_grain": candidates.target_population_scope,
        "decision_status": "checked_rule_accepted",
        "decision_rule": RULE,
        "evidence_publication_row_id": candidates.source_publication_row_id,
        "evidence_sha256": candidates.source_sha256,
        "review_sha256": REVIEW_SHA,
        "spatial_admission": False,
        "population_boundary_harmonized": False,
    })
    edges["decision_id"] = ["ANNUAL-ID-" + hashlib.sha256((a + "\0" + b).encode()).hexdigest()[:24] for a, b in zip(edges.from_source_record_id, edges.to_source_record_id)]
    if not edges.decision_id.is_unique or edges.duplicated(["from_source_record_id", "to_reference_date"]).any():
        raise ValueError("duplicate annual identity decision")
    output_root.mkdir(parents=True)
    paths = {"annual_observations_accepted.parquet": candidates, "annual_identity_edges.parquet": edges}
    for name, frame in paths.items():
        frame.to_parquet(output_root / name, index=False)
    receipt = {
        "status": "accepted_scoped_annual_identity_rule", "rule": RULE,
        "identity_edges": len(edges), "settlement_identity_edges": int((~aggregate).sum()), "aggregate_identity_edges": int(aggregate.sum()),
        "observed_years": [2022, 2023, 2024], "coordinate_admissions": 0,
        "census_2010_missing_cells_changed": 0, "population_precision": "published rounded thousand-person estimates",
        "boundary_harmonization": False, "national_annual_coverage_claim": False,
        "independent_review_sha256": REVIEW_SHA, "candidate_manifest_sha256": sha(candidate_root / "manifest.json"),
        "builder_sha256": sha(Path(__file__)),
        "outputs": {name: {"sha256": sha(output_root / name), "rows": len(frame)} for name, frame in paths.items()},
    }
    (output_root / "acceptance_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["data-root", "selected", "candidate-root", "review", "output-root"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = apply(args.data_root, args.selected, args.candidate_root, args.review, args.output_root)
    print(json.dumps({key: report[key] for key in ["status", "identity_edges", "settlement_identity_edges", "aggregate_identity_edges", "coordinate_admissions"]}))


if __name__ == "__main__":
    main()
