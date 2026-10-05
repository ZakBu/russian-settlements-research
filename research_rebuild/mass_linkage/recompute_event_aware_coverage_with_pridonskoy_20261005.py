#!/usr/bin/env python3
"""Apply the official 2011 Pridonskoy-to-Voronezh inclusion to event coverage."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/pridonskoy_voronezh_inclusion_20261005"
BASE = ROOT / "research_rebuild/evidence/accepted_national_inclusions_20261005/event_aware_coverage.json"
SERIES = EVIDENCE / "accepted_series.csv"
OUT = EVIDENCE / "event_aware_coverage.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {"2002": (17133, "2002:1_TOM_01_04.xls:0:365"),
                "2010": (18300, "ROSSTAT2010:T5:p20:l21")}
    if len(rows) != 2 or {r["year"] for r in rows} != set(expected):
        raise ValueError("Expected exactly the 2002 and 2010 Pridonskoy observations")
    if any((int(r["population_used"]), r["source_record_id"]) != expected[r["year"]] for r in rows):
        raise ValueError("Population or source row changed")
    if any(r["receiver_population_added"] != "False" or r["ordinary_same_place_identity"] != "False" for r in rows):
        raise ValueError("Receiver-total or ordinary-identity guard failed")
    if len({(r["latitude"], r["longitude"]) for r in rows}) != 1:
        raise ValueError("The two years must share the accepted scoped point")

    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds only the two official pre-inclusion Pridonskoy observations at its own scoped representative point. Voronezh 2021 receiver totals are context only; no 2021 child population is invented.",
        "series": [{
            "place": r["place"], "year": int(r["year"]),
            "population": int(r["population_used"]),
            "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
            "source_record_id": r["source_record_id"],
            "source_file": r["source_file"], "source_sha256": r["source_sha256"],
            "source_locator": r["source_locator"],
            "population_source_quality": r["population_source_quality"],
            "point_provider": r["point_provider"],
            "point_source_sha256": r["point_source_sha256"],
            "point_source_locator": r["point_source_locator"],
            "coordinate_status": r["coordinate_status"],
            "receiver_city": r["receiver_city"],
            "receiver_2021_population_context_only": int(r["receiver_2021_population_context_only"]),
            "receiver_2021_oktmo_context_only": r["receiver_2021_oktmo_context_only"],
            "event_status": r["event_status"],
            "event_source_url": r["event_source_url"],
            "event_source_status": r["event_source_status"],
            "receiver_population_added": False,
            "ordinary_same_place_identity_asserted": False,
            "historical_coordinate_measurement_asserted": False,
            "population_boundary_comparability": "unknown"
        } for r in rows],
        "by_year": {},
        "guardrails": {
            "receiver_city_populations_added": False,
            "2021_child_observation_invented": False,
            "ordinary_identity_graph_mutated": False,
            "official_inclusion_law_saved": True,
            "historical_coordinate_measurement_asserted": False,
            "population_boundary_comparability_asserted": False
        }
    }
    for year in (2002, 2010, 2021):
        b = base["by_year"][str(year)]
        addition = sum(int(r["population_used"]) for r in rows if int(r["year"]) == year)
        denominator = int(b["denominator"])
        population = int(b["event_aware_population"]) + addition
        result["by_year"][str(year)] = {
            "denominator": denominator,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "pridonskoy_inclusion_population_added": addition,
            "event_aware_population": population,
            "event_aware_percent": 100 * population / denominator,
            "gap_to_99_percent": max(0, math.ceil(.99 * denominator) - population),
            "note": "No distinct Pridonskoy population is published for this year; Voronezh total is already represented and is not added again." if year == 2021 else "Official pre-inclusion Pridonskoy count is located at its own scoped representative point; total Voronezh population is not transferred."
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
