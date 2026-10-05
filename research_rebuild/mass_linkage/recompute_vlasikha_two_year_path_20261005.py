#!/usr/bin/env python3
"""Count the approved Vlasikha 2010–2021 path without inventing a 2002 row."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/vlasikha_two_year_path_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/kalininets_scoped_chain_20261005/event_aware_coverage.json"
POINT_REVIEW = ROOT / "research_rebuild/evidence/mass_joint_20261004/reviewed_increments_after_eighth/independent_review/large_current4_official_primary_staged_v2/accepted_current_point_uses.csv"
YEAR_GAP_REVIEW = ROOT / "research_rebuild/evidence/mass_joint_20261004/reviewed_increments_after_eighth/independent_review/large_current4_same_census_source_mapping/mapping_review_context.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {2010: 26359, 2021: 28240}
    got = {int(r["year"]): int(r["population_used"]) for r in rows}
    if len(rows) != 2 or got != expected:
        raise ValueError(f"unexpected Vlasikha two-year observations: {got}")
    if any(r["scoped_chain_status"] != "root_approved_scoped_physical_continuity" for r in rows):
        raise ValueError("scoped continuity approval guard failed")
    if any(r["ordinary_identity_graph_mutated"] != "False" or r["historical_coordinate_measurement"] != "False" for r in rows):
        raise ValueError("scope guard failed")
    if any(r["year"] == "2002" for r in rows):
        raise ValueError("do not create an unsupported 2002 observation")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds Vlasikha's already root-approved 2010–2021 physical-place path to the event-aware measure that accepts connected observed census years. The official source review found no Moscow-region Vlasikha row in 2002; the missing year remains absent, not zero or imputed.",
        "series": rows,
        "by_year": {},
        "guardrails": {
            "ordinary_identity_graph_mutated": False,
            "2002_observation_created": False,
            "historical_coordinate_measurement_asserted": False,
            "historical_coordinate_provider_binding_asserted": False,
            "population_boundary_comparability_asserted": False,
            "2010_protected_alternate_25394_promoted": False,
        },
        "approval_source": "research_rebuild/evidence/mass_joint_20261004/ninth_reviewed_and_scoped_history/official3/application_receipt.json",
        "approval_status": "root-approved scoped 2010–2021 physical continuity; not a three-census full chain",
    }
    for year in (2002, 2010, 2021):
        b = base["by_year"][str(year)]
        row = next((r for r in rows if int(r["year"]) == year), None)
        den = int(b["denominator"])
        add = 0 if row is None else int(row["population_used"])
        num = int(b["event_aware_population"]) + add
        result["by_year"][str(year)] = {
            "denominator": den,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "vlasikha_two_year_path_population_added": add,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "population_source_status": None if row is None else row["population_source_status"],
            "note": "No Vlasikha observation is admitted for this census year." if row is None else "Vlasikha remains a separate ZATO locality in Moscow Oblast; current OKTMO is 46773000051; boundaries and population scope are not asserted comparable across years.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "manifest.json").write_text(json.dumps({
        "series_sha256": sha256(SERIES),
        "base_coverage_sha256": sha256(BASE),
        "approval_receipt_sha256": sha256(ROOT / result["approval_source"]),
        "accepted_point_review_sha256": sha256(POINT_REVIEW),
        "official_2002_gap_review_sha256": sha256(YEAR_GAP_REVIEW),
        "output_sha256": sha256(OUT),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
