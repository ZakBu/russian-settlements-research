#!/usr/bin/env python3
"""Apply the accepted Dygulybgey village trajectory to event-aware coverage."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/dygulybgey_event_path_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/kushchevskaya_partition_chain_20261005/event_aware_coverage.json"
APPROVED = ROOT / "research_rebuild/evidence/mass_joint_20261004/graph14_inclusion_scope_and_controls/accepted_dygulybgey_event_aware_scope__accepted_scoped_trajectory.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {2002: 20355, 2010: 20228, 2021: 20852}
    got = {int(r["year"]): int(r["population_used"]) for r in rows}
    if len(rows) != 3 or got != expected:
        raise ValueError(f"unexpected Dygulybgey trajectory: {got}")
    approved = json.loads(APPROVED.read_text(encoding="utf-8"))
    approved_ids = {o["source_record_id"] for o in approved["observations"]}
    if {r["source_record_id"] for r in rows} != approved_ids:
        raise ValueError("selected source observations diverge from the accepted trajectory")
    if any(o["decision_status"] != "accepted_event_aware_physical_village_trajectory" or o["ordinary_NP3"] for o in approved["observations"]):
        raise ValueError("event-aware/no ordinary-NP3 scope guard failed")
    if any(r["ordinary_identity_graph_mutated"] != "False" or r["historical_coordinate_measurement"] != "False" for r in rows):
        raise ValueError("scope guard failed")
    if any(r["year"] == "2010" and r["population_value_quality"] != "secondary_confidentiality_protected_value_exact_scope_unverified" for r in rows):
        raise ValueError("2010 population quality tag must be retained")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds the previously accepted separate physical-village path for the 2002 spelling Дугулубгей and 2010/2021 spelling Дыгулыбгей. The reported Baksan incorporation/restoration remains secondary historical context with exact legal scope/date unverified; the Baksan city totals and identifier are not attached to this village.",
        "series": rows,
        "by_year": {},
        "guardrails": {
            "ordinary_identity_graph_mutated": False,
            "baksan_city_population_added": False,
            "historical_coordinate_measurement_asserted": False,
            "historical_provider_binding_asserted": False,
            "population_boundary_comparability_asserted": False,
            "2010_protected_value_relabelled_primary": False,
            "exact_incorporation_or_restoration_date_asserted": False,
        },
        "approval_source": str(APPROVED.relative_to(ROOT)),
        "approval_status": approved["status"],
    }
    for year in (2002, 2010, 2021):
        b = base["by_year"][str(year)]
        row = next(r for r in rows if int(r["year"]) == year)
        den = int(b["denominator"])
        add = int(row["population_used"])
        num = int(b["event_aware_population"]) + add
        result["by_year"][str(year)] = {
            "denominator": den,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "dygulybgey_event_path_population_added": add,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "population_source_status": row["population_value_quality"],
            "note": "Distinct village trajectory and accepted modern village point; Baksan city proper/urban-okrug totals and legacy Baksan city code are excluded. Legal event dates and boundary comparability remain unresolved.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "manifest.json").write_text(json.dumps({
        "series_sha256": sha256(SERIES),
        "base_coverage_sha256": sha256(BASE),
        "accepted_trajectory_sha256": sha256(APPROVED),
        "output_sha256": sha256(OUT),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
