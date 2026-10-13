#!/usr/bin/env python3
"""Add the approved Kuschchevskaya chain using its exclusive 2002 whole-row mapping."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/kushchevskaya_partition_chain_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/vlasikha_two_year_path_20261005/event_aware_coverage.json"
APPROVAL = ROOT / "research_rebuild/evidence/mass_joint_20261004/ninth_reviewed_and_scoped_history/official3/application_receipt.json"
PROJECTION = ROOT / "research_rebuild/evidence/mass_joint_20261004/reviewed_increments_after_eighth/independent_review/large_current4_official_primary_staged_v2/same_census_projection_policy.csv"
OUT = EVIDENCE / "event_aware_coverage.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {2002: 29533, 2010: 28362, 2021: 30375}
    got = {int(r["year"]): int(r["population_used"]) for r in rows}
    if len(rows) != 3 or got != expected:
        raise ValueError(f"unexpected Kuschchevskaya series: {got}")
    row_2002 = next(r for r in rows if int(r["year"]) == 2002)
    part_sum = int(row_2002["partition_part_1_population"]) + int(row_2002["partition_part_2_population"])
    if part_sum != 29533:
        raise ValueError("exclusive 2002 part rows must sum exactly to the official whole row")
    if any(r["scoped_chain_status"] != "root_approved_scoped_physical_continuity" for r in rows):
        raise ValueError("scoped continuity approval guard failed")
    if any(r["ordinary_identity_graph_mutated"] != "False" or r["historical_coordinate_measurement"] != "False" for r in rows):
        raise ValueError("scope guard failed")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds one root-approved Kuschchevskaya 2002–2010–2021 physical-place path. The 2002 whole-row observation is an exclusive alternative to two selected same-census parts whose populations sum exactly to 29,533; it replaces them in the spatial representation and is never counted on top of them.",
        "series": rows,
        "by_year": {},
        "guardrails": {
            "ordinary_identity_graph_mutated": False,
            "2002_whole_and_parts_added_together": False,
            "historical_coordinate_measurement_asserted": False,
            "historical_provider_binding_asserted": False,
            "population_boundary_comparability_asserted": False,
            "receiver_population_added": False,
        },
        "approval_source": str(APPROVAL.relative_to(ROOT)),
        "exclusive_projection_source": str(PROJECTION.relative_to(ROOT)),
        "approval_status": "root-approved scoped physical continuity; exclusive part-to-whole source projection retained",
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
            "kushchevskaya_population_added": add,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "population_source_status": row["population_source_status"],
            "note": "One official whole-row population is used; same-census components are an exclusive partition, not additions. Current OKTMO appears only for 2021." if year == 2002 else "The accepted path uses the official named locality row; boundaries and population comparability remain unknown.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (EVIDENCE / "manifest.json").write_text(json.dumps({
        "series_sha256": sha256(SERIES),
        "base_coverage_sha256": sha256(BASE),
        "approval_receipt_sha256": sha256(APPROVAL),
        "exclusive_projection_policy_sha256": sha256(PROJECTION),
        "output_sha256": sha256(OUT),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
