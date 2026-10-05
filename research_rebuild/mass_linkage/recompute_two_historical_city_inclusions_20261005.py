#!/usr/bin/env python3
"""Add two already accepted historical city-inclusion references, without receiver totals."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/two_historical_city_inclusions_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/dygulybgey_event_path_20261005/event_aware_coverage.json"
APPROVAL = ROOT / "research_rebuild/evidence/mass_joint_20261004/graph16_skhodnya_nikolskoe_inclusion2/application_receipt.json"
REFS = ROOT / "research_rebuild/evidence/mass_joint_20261004/graph16_skhodnya_nikolskoe_inclusion2/accepted_scoped_inclusion_references.json"
POINTS = ROOT / "research_rebuild/evidence/mass_joint_20261004/graph16_skhodnya_nikolskoe_inclusion2/accepted_scoped_point_uses.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {"Сходня": 19119, "Никольско-Архангельский": 18637}
    got = {r["place"]: int(r["population_used"]) for r in rows}
    if len(rows) != 2 or got != expected:
        raise ValueError(f"unexpected historical inclusion records: {got}")
    ref_rows = json.loads(REFS.read_text(encoding="utf-8"))
    point_rows = json.loads(POINTS.read_text(encoding="utf-8"))
    ref_ids = {r["source_record_id"] for r in ref_rows}
    point_by_case = {r["case"]: r for r in point_rows}
    if {r["source_record_id"] for r in rows} != ref_ids:
        raise ValueError("historical source rows diverge from approved inclusion references")
    if {r["place"] for r in rows} != set(point_by_case):
        raise ValueError("each inclusion must have its reviewed scoped point context")
    if any(r["event_status"] != "secondary_reported_inclusion_context_only" for r in rows):
        raise ValueError("secondary-only event status must remain visible")
    if any(r["receiver_population_added"] != "False" or r["ordinary_identity_graph_mutated"] != "False" for r in rows):
        raise ValueError("receiver-total or canonical-graph guard failed")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds two distinct 2002 historical city observations to their own accepted secondary-reported inclusion locations. Reported receivers are Khimki and Balashikha; receiver totals are context only. Legal event dates and implementation were not independently verified.",
        "places": rows,
        "by_year": {},
        "guardrails": {
            "receiver_city_population_added": False,
            "2010_or_2021_child_rows_invented": False,
            "ordinary_identity_graph_mutated": False,
            "legal_event_independently_verified": False,
            "historical_coordinate_measurement_asserted": False,
            "population_boundary_comparability_asserted": False,
        },
        "approval_source": str(APPROVAL.relative_to(ROOT)),
        "approval_status": json.loads(APPROVAL.read_text(encoding="utf-8"))["status"],
    }
    for year in (2002, 2010, 2021):
        b = base["by_year"][str(year)]
        add = sum(int(r["population_used"]) for r in rows if int(r["year"]) == year)
        den = int(b["denominator"])
        num = int(b["event_aware_population"]) + add
        result["by_year"][str(year)] = {
            "denominator": den,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "historical_city_inclusion_population_added": add,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "note": "Adds 2002 historical-city observations only; no child locality observations exist in this accepted scope after the reported inclusion." if year == 2002 else "No separate historical locality count is available here; current receiver totals remain context only.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "manifest.json").write_text(json.dumps({
        "series_sha256": sha256(SERIES),
        "base_coverage_sha256": sha256(BASE),
        "approval_receipt_sha256": sha256(APPROVAL),
        "accepted_reference_rows_sha256": sha256(REFS),
        "accepted_point_uses_sha256": sha256(POINTS),
        "output_sha256": sha256(OUT),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
