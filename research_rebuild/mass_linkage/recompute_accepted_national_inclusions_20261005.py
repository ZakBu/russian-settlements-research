#!/usr/bin/env python3
"""Apply a previously reviewed batch of 2002 historical-city points and Somovo 2010."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/accepted_national_inclusions_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/two_historical_city_inclusions_20261005/event_aware_coverage.json"
SCOPE = ROOT / "research_rebuild/evidence/mass_joint_20261004/graph14_inclusion_scope_and_controls"
ABSORBED = SCOPE / "accepted_national_absorbed8_scope__accepted_scoped_inclusion_references.json"
ABSORBED_POINTS = SCOPE / "accepted_national_absorbed8_scope__accepted_scoped_point_uses.json"
SOMOVO = SCOPE / "accepted_somovo2010_selected_scope__accepted_scoped_inclusion_references.json"
SOMOVO_POINTS = SCOPE / "accepted_somovo2010_selected_scope__accepted_scoped_point_uses.json"
RECEIPT = SCOPE / "accepted_national_absorbed8_scope__application_receipt.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    old_rows = [r for r in rows if r["scope_year_group"] == "2002"]
    somovo_rows = [r for r in rows if r["scope_year_group"] == "2010_somovo"]
    if len(old_rows) != 8 or sum(int(r["population_used"]) for r in old_rows) != 117311:
        raise ValueError("must preserve exactly the eight approved 2002 rows and their reviewed total")
    if len(somovo_rows) != 1 or int(somovo_rows[0]["population_used"]) != 13605:
        raise ValueError("must include exactly the approved 2010 Somovo row")
    absorbed = json.loads(ABSORBED.read_text(encoding="utf-8"))
    absorbed_points = json.loads(ABSORBED_POINTS.read_text(encoding="utf-8"))
    somovo = json.loads(SOMOVO.read_text(encoding="utf-8"))
    somovo_points = json.loads(SOMOVO_POINTS.read_text(encoding="utf-8"))
    expected_ids = {r["source_record_id"] for r in absorbed}
    expected_ids |= {r["source_record_id"] for r in somovo}
    if {r["source_record_id"] for r in rows} != expected_ids:
        raise ValueError("series rows differ from the previously accepted source references")
    allowed_points = {r["point_use_id"] for r in absorbed_points + somovo_points}
    if {r["point_use_id"] for r in rows} != allowed_points:
        raise ValueError("series point uses differ from reviewed point-use rows")
    if any(r["event_status"] != "secondary_reported_inclusion_context_only" for r in rows):
        raise ValueError("secondary-reported event limit must remain visible")
    if any(r["receiver_population_added"] != "False" or r["ordinary_identity_graph_mutated"] != "False" for r in rows):
        raise ValueError("receiver population/canonical graph guard failed")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds eight accepted 2002 historical settlement observations and one accepted 2010 Somovo observation at their own scoped point contexts. Events are secondary-reported, exact legal dates are unresolved, and receiver city populations remain context only.",
        "series": rows,
        "by_year": {},
        "guardrails": {
            "receiver_city_populations_added": False,
            "2021_child_observations_invented": False,
            "ordinary_identity_graph_mutated": False,
            "legal_events_independently_verified": False,
            "historical_coordinate_measurements_asserted": False,
            "population_boundary_comparability_asserted": False,
            "2010_somovo_source_value_promoted_beyond_official_table_scope": False,
        },
        "approval_sources": [str(RECEIPT.relative_to(ROOT)), str(SCOPE.joinpath("accepted_somovo2010_selected_scope__application_receipt.json").relative_to(ROOT))],
    }
    for year in (2002, 2010, 2021):
        b = base["by_year"][str(year)]
        add = sum(int(r["population_used"]) for r in rows if int(r["year"]) == year)
        den = int(b["denominator"])
        num = int(b["event_aware_population"]) + add
        result["by_year"][str(year)] = {
            "denominator": den,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "accepted_historical_inclusion_population_added": add,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "note": "Adds old settlement observations at distinct historical points; current receiver totals are not transferred." if year in (2002, 2010) else "No separate child-locality value is added for this year; receiver city totals remain context only.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "manifest.json").write_text(json.dumps({
        "series_sha256": sha256(SERIES),
        "base_coverage_sha256": sha256(BASE),
        "absorbed8_references_sha256": sha256(ABSORBED),
        "absorbed8_points_sha256": sha256(ABSORBED_POINTS),
        "somovo_reference_sha256": sha256(SOMOVO),
        "somovo_points_sha256": sha256(SOMOVO_POINTS),
        "absorbed8_receipt_sha256": sha256(RECEIPT),
        "somovo_receipt_sha256": sha256(SCOPE / "accepted_somovo2010_selected_scope__application_receipt.json"),
        "output_sha256": sha256(OUT),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
