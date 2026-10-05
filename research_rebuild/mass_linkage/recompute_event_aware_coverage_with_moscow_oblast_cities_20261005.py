#!/usr/bin/env python3
"""Append three legal city-merger trajectories to the separate event metric."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/moscow_oblast_absorbed_city_events_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/norilsk_talnakh_kayerkan_series_20261005/event_aware_coverage.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {
        ("Железнодорожный", 2002): 103931, ("Железнодорожный", 2010): 131257,
        ("Климовск", 2002): 55644, ("Климовск", 2010): 56186,
        ("Юбилейный", 2002): 30837, ("Юбилейный", 2010): 33237,
    }
    got = {(r["place"], int(r["year"])): int(r["population"]) for r in rows}
    if got != expected:
        raise ValueError(f"unexpected event row signature: {got}")
    if any(r["coordinate_status"] != "reviewed_extension_rule_accepted" or r["ordinary_same_place_claim_to_receiver"] != "False" for r in rows):
        raise ValueError("point or no-ordinary-identity scope guard failed")
    if any(r["receiver_2021_population_added"] != "False" or r["population_boundary_comparability"] != "unknown" for r in rows):
        raise ValueError("parent receiver values must remain context-only")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Event-aware inclusion of three historical Moscow Oblast cities into their legally reported successor cities; old census counts and accepted points are shown as separate historic-place observations.",
        "successors": {
            place: {"recipient": rs[0]["recipient_city"], "law": rs[0]["event_law"], "event_period": rs[0]["event_period"], "2021_receiver_population_context_only": int(rs[0]["receiver_2021_population_context_only"]), "2021_receiver_OKTMO_context_only": rs[0]["receiver_2021_oktmo_context_only"]}
            for place in ("Железнодорожный", "Климовск", "Юбилейный")
            for rs in [[r for r in rows if r["place"] == place]]
        },
        "by_year": {},
        "guardrails": {
            "2021_receiver_populations_added": False,
            "historical_city_values_changed": False,
            "ordinary_identity_graph_mutated": False,
            "boundary_or_population_comparability_asserted": False,
            "territorial_event_link_is_not_same_place_identity": True,
        },
    }
    for y in (2002, 2010, 2021):
        b = base["by_year"][str(y)]
        add = sum(int(r["population"]) for r in rows if int(r["year"]) == y)
        den = int(b["denominator"])
        numerator = int(b["event_aware_population"]) + add
        result["by_year"][str(y)] = {
            "denominator": den,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "three_successor_city_event_population_added": add,
            "event_aware_population": numerator,
            "event_aware_percent": 100 * numerator / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - numerator),
            "note": "No 2021 child locality observations exist in this accepted input. Successor-city counts are context only and already represented in the census-year 2021 denominator/coverage layer." if y == 2021 else "Adds selected, separately observed old-city census populations along accepted scoped inclusion references; does not assign the successor-city population to the predecessor.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
