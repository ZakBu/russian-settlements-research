#!/usr/bin/env python3
"""Add accepted Norilsk named-place trajectories to the separate event metric."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/norilsk_talnakh_kayerkan_series_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/moscow_2012_two_city_event_aware_20261005/event_aware_coverage.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 6 or {(r["place"], int(r["observation_year"])) for r in rows} != {
        (p, y) for p in ("Талнах", "Кайеркан") for y in (2002, 2010, 2021)
    }:
        raise ValueError("expected exactly two scoped places × three observed years")
    if any(r["typed_path_status"] != "accepted_scoped_typed_physical_place_relation" for r in rows):
        raise ValueError("unaccepted typed-scope trajectory")
    if any(r["point_status"] != "accepted_scoped_named_place_point_use" for r in rows):
        raise ValueError("unaccepted point use")
    for r in rows:
        y = int(r["observation_year"])
        if r["row_nationally_additive_in_selected_layer"] != ("true" if y == 2002 else "false"):
            raise ValueError("2002 additive versus 2010/2021 nested partition rule changed")
        if r["ordinary_NP_same_grain_identity"] != "false" or r["boundary_comparability"] != "unknown":
            raise ValueError("ordinary identity or boundary comparability was improperly asserted")

    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Additional typed-scope trajectories for Talnakh and Kayerkan, appended to the separate Moscow-expansion event-aware metric; no canonical graph or official total is changed.",
        "by_year": {},
        "places": {
            place: [{"year": int(r["observation_year"]), "population": int(r["population"]), "nationally_additive": r["row_nationally_additive_in_selected_layer"] == "true", "source_locator": r["source_locator"]} for r in rows if r["place"] == place]
            for place in ("Талнах", "Кайеркан")
        },
        "guardrails": {
            "2002_source_rows_are_selected_additive": True,
            "2010_2021_rows_are_official_but_nested_in_norilsk_selected_parent": True,
            "2010_2021_nested_population_added_to_national_numerator": False,
            "ordinary_same_grain_identity_asserted": False,
            "boundary_or_population_comparability_asserted": False,
            "current_OKTMO_binding": False,
            "canonical_identity_graph_mutated": False,
        },
    }
    for y in (2002, 2010, 2021):
        b = base["by_year"][str(y)]
        addition = sum(int(r["population"]) for r in rows if int(r["observation_year"]) == y and r["row_nationally_additive_in_selected_layer"] == "true")
        denominator = int(b["denominator"])
        numerator = int(b["event_aware_population"]) + addition
        result["by_year"][str(y)] = {
            "denominator": denominator,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "norilsk_typed_scope_population_added": addition,
            "event_aware_population": numerator,
            "event_aware_percent": 100 * numerator / denominator,
            "gap_to_99_percent": max(0, math.ceil(.99 * denominator) - numerator),
            "note": "2010/2021 district values are shown in the locality series but remain nested in the national Norilsk parent and add zero to the coverage numerator." if y != 2002 else "Adds the two selected additive 2002 named-city rows through accepted scoped place tracks.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
