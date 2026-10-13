#!/usr/bin/env python3
"""Add the Leninsky-district Moskovskiy census rows before Moscow annexation."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/moskovskiy_leninsky_moscow_inclusion_20261005"
BASE = ROOT / "research_rebuild/evidence/kosaya_gora_tula_inclusion_20261005/event_aware_coverage.json"
SERIES = EVIDENCE / "accepted_series.csv"
OUT = EVIDENCE / "event_aware_coverage.json"


def main() -> None:
    with SERIES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {"2002": (15563, "2002:010_3e630cc803_02c_Moskovskaya-oblast.xls:Sheet1:2682"),
                "2010": (17366, "2010:pub-11-1-4.pdf:pdf_page_11:42")}
    if len(rows) != 2 or {r["year"] for r in rows} != set(expected):
        raise ValueError("Expected exactly the 2002 and 2010 Leninsky Moskovskiy records")
    if any((int(r["population_used"]), r["source_record_id"]) != expected[r["year"]] for r in rows):
        raise ValueError("Population/source record guard failed")
    if len({(r["latitude"], r["longitude"]) for r in rows}) != 1:
        raise ValueError("Both census rows must resolve to the same scoped historical place")
    if any(r["receiver_population_added"].strip() != "False" or r["ordinary_same_place_identity"].strip() != "False" for r in rows):
        raise ValueError("No-receiver-total / no-ordinary-identity guard failed")

    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds two official observations for the former Leninsky-district Moskovskiy settlement at its own representative point before its territory entered Moscow in 2012. Moscow 2021 territory total remains context only.",
        "series": [{
            "place": r["place"], "year": int(r["year"]),
            "population": int(r["population_used"]),
            "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
            "source_record_id": r["source_record_id"], "source_file": r["source_file"],
            "source_sha256": r["source_sha256"], "source_locator": r["source_locator"],
            "population_source_quality": r["population_source_quality"],
            "point_provider": r["point_provider"], "point_source_sha256": r["point_source_sha256"],
            "point_source_locator": r["point_source_locator"],
            "coordinate_status": r["coordinate_status"],
            "receiver_2021_federal_territory": "Москва",
            "receiver_2021_population_context_only": 13010112,
            "receiver_2021_source_record_id": "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:64748",
            "event_status": r["event_status"], "event_source_url": r["event_source_url"],
            "event_effective_date": "2012-07-01",
            "event_source_status": r["event_source_status"],
            "receiver_population_added": False,
            "ordinary_same_place_identity_asserted": False,
            "historical_coordinate_measurement_asserted": False,
            "population_boundary_comparability": "unknown"
        } for r in rows],
        "by_year": {},
        "guardrails": {
            "receiver_city_populations_added": False,
            "2021_child_locality_population_invented": False,
            "ordinary_identity_graph_mutated": False,
            "boundary_agreement_text_saved": True,
            "agreement_map_appendix_saved": False,
            "historical_coordinate_measurement_asserted": False,
            "population_boundary_comparability_asserted": False
        }
    }
    for year in (2002, 2010, 2021):
        b = base["by_year"][str(year)]
        addition = sum(int(r["population_used"]) for r in rows if int(r["year"]) == year)
        den = int(b["denominator"])
        num = int(b["event_aware_population"]) + addition
        result["by_year"][str(year)] = {
            "denominator": den,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "moskovskiy_inclusion_population_added": addition,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "note": "Historical Moskovskiy value is represented at its own point; no Moscow territory total is transferred." if year in (2002, 2010) else "No separately published Moskovskiy child count is selected for 2021; the Moscow territory total is already represented."
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
