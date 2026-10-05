#!/usr/bin/env python3
"""Recalculate the Moscow-expansion event-aware series contribution.

This is a separate spatial/event overlay. It does not mutate census rows,
ordinary identity edges, or official census totals.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/moscow_2012_two_city_event_aware_20261005"
SERIES = EVIDENCE / "accepted_series.csv"
BASE = ROOT / "research_rebuild/evidence/federal_territory_spatial_overlay_20261005/coverage_overlay.json"
OUT = EVIDENCE / "event_aware_coverage.json"


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {
        ("Троицк", 2002): 32653, ("Троицк", 2010): 39873, ("Троицк", 2021): 65043,
        ("Щербинка", 2002): 28043, ("Щербинка", 2010): 32450, ("Щербинка", 2021): 56531,
    }
    if len(rows) != len(expected):
        raise ValueError(f"expected six city-year observations, found {len(rows)}")
    got = {(r["place"], int(r["observation_year"])): int(r["population"]) for r in rows}
    if got != expected:
        raise ValueError(f"series population signature changed: {got}")
    if any(r["event_date"] != "2012-07-01" or r["event_relation"] != "included_into_Moscow_territory" for r in rows):
        raise ValueError("territorial event scope/date changed")
    if any(r["chain_status"] != "accepted_scoped_physical_continuity" for r in rows):
        raise ValueError("unaccepted/ordinary identity status in this event layer")
    for r in rows:
        if not r["coordinate_latitude"] or not r["coordinate_longitude"] or r["coordinate_status"] != "accepted_scoped_representative_point_retrospective" or r["coordinate_is_census_measurement"] != "false":
            raise ValueError(f"coordinate guard failed for {r['place']} {r['year']}")
    secondary = [r for r in rows if int(r["observation_year"]) == 2021]
    if any(r["population_source_status"] != "secondary_wikidata_claim_only" or r["national_2021_additive"] != "false" for r in secondary):
        raise ValueError("2021 secondary values must remain nonadditive")
    if any(r["native_2021_binding"] != "false" or r["population_boundary_comparability"] != "unknown" for r in rows):
        raise ValueError("do not assert a census-row binding or population comparability")

    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Event-aware spatial series for two former Moscow Oblast cities included in Moscow on 2012-07-01; physical continuity and territory membership are separate from census-row identity and population-boundary comparability.",
        "input_base_scope": base["scope"],
        "cities": {},
        "by_year": {},
        "guardrails": {
            "ordinary_identity_graph_mutated": False,
            "official_population_rows_mutated": False,
            "national_census_controls_mutated": False,
            "2021_Wikidata_values_added_to_national_totals": False,
            "population_boundary_comparability_asserted": False,
            "geographic_event": "Moscow territory expanded; these two city territories were transferred, without claiming the entirety of Moscow's later territory is represented by these city rows.",
        },
    }
    for place in ("Троицк", "Щербинка"):
        pr = [r for r in rows if r["place"] == place]
        result["cities"][place] = {
            "observations": [
                {"year": int(r["observation_year"]), "population": int(r["population"]), "population_source_status": r["population_source_status"], "source_record_id": r["source_record_id"] or None}
                for r in pr
            ],
            "coordinate": {"latitude": float(pr[0]["coordinate_latitude"]), "longitude": float(pr[0]["coordinate_longitude"]), "status": "accepted scoped representative point; retrospective use, not census-date measurement"},
            "territorial_event": {"date": "2012-07-01", "relation": "included into federal city of Moscow", "post_event_current_oktmo": pr[0]["current_oktmo"], "oktmo_grain": "current intracity municipal district; not a historical locality code"},
        }
    for y in (2002, 2010, 2021):
        b = base["by_year"][str(y)]
        den = int(b.get("available_three_census_chain_denominator", b["official_control"]))
        baseline = int(b["spatial_point_plus_full_chain_population"])
        addon = sum(int(r["population"]) for r in rows if int(r["observation_year"]) == y and r["population_source_status"] == "official_selected_census_observation")
        numerator = baseline + addon
        result["by_year"][str(y)] = {
            "denominator": den,
            "baseline_federal_territory_plus_ordinary_full_chain_population": baseline,
            "baseline_percent": 100 * baseline / den,
            "eligible_old_city_observation_population_added_via_accepted_scoped_event_path": addon,
            "event_aware_population": numerator,
            "event_aware_percent": 100 * numerator / den,
            "gap_to_99_percent": max(0, math.ceil(0.99 * den) - numerator),
            "official_census_control": int(b["official_control"]),
            "note": "2021 leaves the numerator unchanged: city-level P1082 claims are secondary and already lie within the official Moscow territory total.",
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
