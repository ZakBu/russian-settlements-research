#!/usr/bin/env python3
"""Add accepted, secondary-reported Krasnodar inclusion paths to scoped coverage."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/krasnodar_included_2002_localities_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/moscow_oblast_absorbed_city_events_20261005/event_aware_coverage.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {"Калинино": 34152, "Пашковский": 43077}
    if {r["place"]: int(r["population"]) for r in rows} != expected or len(rows) != 2:
        raise ValueError("expected the two exact reviewed 2002 Krasnodar-area source rows")
    if any(r["event_status"] != "accepted_scoped_inclusion_with_limits" or r["ordinary_same_place_identity"] != "False" for r in rows):
        raise ValueError("scoped inclusion/no-ordinary-identity guard failed")
    if any(r["receiver_2021_population_added"] != "False" or r["population_boundary_comparability"] != "unknown" for r in rows):
        raise ValueError("receiver context or boundary-comparability guard failed")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds two accepted historical inclusion routes to Krasnodar to the separate event-aware spatial coverage measure; resolution text was consulted, exact effective date is unresolved.",
        "places": [{"place": r["place"], "year": int(r["year"]), "population": int(r["population"]), "receiver": r["receiver_2021_city"], "receiver_population_context_only": int(r["receiver_2021_population_context_only"]), "latitude": float(r["latitude"]), "longitude": float(r["longitude"]), "event_status": r["event_status"], "legal_event_date_status": r["event_period"], "legal_evidence_status": r["legal_event_evidence_status"], "legal_evidence_url": r["supplemental_legal_evidence_url"]} for r in rows],
        "by_year": {},
        "guardrails": {"2021_receiver_population_added": False, "resolution_text_consulted_via_Garant": True, "official_gazette_copy_preserved": False, "exact_effective_date_known": False, "ordinary_same_place_identity_asserted": False, "population_boundary_comparability_asserted": False, "canonical_graph_mutated": False},
    }
    for y in (2002, 2010, 2021):
        b = base["by_year"][str(y)]
        addition = sum(int(r["population"]) for r in rows if int(r["year"]) == y)
        den = int(b["denominator"]); num = int(b["event_aware_population"]) + addition
        result["by_year"][str(y)] = {"denominator": den, "prior_event_aware_population": int(b["event_aware_population"]), "Krasnodar_inclusion_population_added": addition, "event_aware_population": num, "event_aware_percent": 100*num/den, "gap_to_99_percent": max(0, math.ceil(.99*den)-num), "note": "Resolution text confirms the reported inclusion; exact effective date remains unknown; current city count is context only." if y == 2002 else "No selected locality value is available in this accepted scope for this year; no value is imputed."}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
