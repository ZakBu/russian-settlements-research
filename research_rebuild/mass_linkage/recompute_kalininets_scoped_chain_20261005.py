#!/usr/bin/env python3
"""Add the already approved Kalininets physical-place chain to event-aware coverage."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/kalininets_scoped_chain_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/krasnodar_included_2002_localities_20261005/event_aware_coverage.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {2002: 23873, 2010: 21774, 2021: 25082}
    got = {int(r["year"]): int(r["population_used"]) for r in rows}
    if len(rows) != 3 or got != expected:
        raise ValueError(f"unexpected official three-year Kalininets series: {got}")
    if any(r["scoped_chain_status"] != "root_approved_scoped_physical_continuity" for r in rows):
        raise ValueError("scoped continuity approval guard failed")
    if any(r["ordinary_identity_graph_mutated"] != "False" or r["historical_coordinate_measurement"] != "False" for r in rows):
        raise ValueError("scope guard failed")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds one previously root-approved, three-year physical-place continuity chain for Kalininets to the separate event-aware point-plus-chain coverage metric. Kalininets is not a former Moscow city and is not included in Moscow; its own 2021 point is used retrospectively for the same named place.",
        "series": rows,
        "by_year": {},
        "guardrails": {
            "ordinary_identity_graph_mutated": False,
            "receiver_territory_population_added": False,
            "historical_coordinate_measurement_asserted": False,
            "historical_coordinate_provider_binding_asserted": False,
            "population_boundary_comparability_asserted": False,
            "2010_protected_alternate_16336_promoted": False,
            "2021_current_oktmo_history_inferred": False,
        },
        "approval_source": "research_rebuild/evidence/mass_joint_20261004/ninth_reviewed_and_scoped_history/official3/application_receipt.json",
        "approval_status": "applied_reviewed_official_primary_three_place_scoped_trajectories; nine observations, including these three Kalininets years; canonical selected frame and identity graph were not mutated",
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
            "kalininets_chain_population_added": add,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "population_source_status": row["population_source_status"],
            "note": "Kalininets is its own named locality in Naro-Fominsky; its current OKTMO 46750000056 is a 2021 code only. No merger into Moscow or boundary/population equivalence is inferred.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "series_sha256": sha256(SERIES),
        "base_coverage_sha256": sha256(BASE),
        "approval_receipt_sha256": sha256(ROOT / result["approval_source"]),
        "output_sha256": sha256(OUT),
        "source_population_rows": {
            "2002": {"record_id": rows[0]["source_record_id"], "sha256": rows[0]["source_sha256"], "locator": rows[0]["source_locator"]},
            "2010": {"record_id": rows[1]["source_record_id"], "sha256": rows[1]["source_sha256"], "locator": rows[1]["source_locator"]},
            "2021": {"record_id": rows[2]["source_record_id"], "sha256": rows[2]["source_sha256"], "locator": rows[2]["source_locator"]},
        },
    }
    (EVIDENCE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
