#!/usr/bin/env python3
"""Add the 2002 Kosaya Gora record before its official inclusion in Tula."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence/kosaya_gora_tula_inclusion_20261005"
BASE = ROOT / "research_rebuild/evidence/pridonskoy_voronezh_inclusion_20261005/event_aware_coverage.json"
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
    if len(rows) != 1 or rows[0]["year"] != "2002" or int(rows[0]["population_used"]) != 18131:
        raise ValueError("Expected exactly the official 2002 Kosaya Gora row (18,131)")
    r = rows[0]
    if r["source_record_id"] != "2002:1_TOM_01_04.xls:0:1949":
        raise ValueError("Source record id changed")
    if r["receiver_population_added"] != "False" or r["ordinary_same_place_identity"] != "False":
        raise ValueError("Receiver population or ordinary identity guard failed")
    base = json.loads(BASE.read_text(encoding="utf-8"))
    result = {
        "scope": "Adds the official separate 2002 Kosaya Gora settlement record at its own scoped point before the 2005 inclusion into Tula. Tula receiver totals for 2010 and 2021 are context only.",
        "series": [{
            "place": r["place"], "year": 2002,
            "population": int(r["population_used"]),
            "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
            "source_record_id": r["source_record_id"],
            "source_file": r["source_file"], "source_sha256": r["source_sha256"],
            "source_locator": r["source_locator"],
            "point_provider": r["point_provider"], "point_source_sha256": r["point_source_sha256"],
            "point_source_locator": r["point_source_locator"],
            "coordinate_status": r["coordinate_status"],
            "receiver_city": "Тула", "receiver_2010_population_context_only": 501169,
            "receiver_2021_population_context_only": 473622,
            "receiver_2021_oktmo_context_only": "70701000001",
            "event_status": "official_law_inclusion; exact effective date not established",
            "event_source_url": "https://base.garant.ru/30313721/",
            "event_source_law": "Tula Oblast Law No. 594-ZTO dated 2005-07-06",
            "receiver_population_added": False,
            "ordinary_same_place_identity_asserted": False,
            "historical_coordinate_measurement_asserted": False,
            "population_boundary_comparability": "unknown"
        }],
        "by_year": {},
        "guardrails": {
            "receiver_city_populations_added": False,
            "separate_2010_or_2021_kosaya_gora_observation_invented": False,
            "ordinary_identity_graph_mutated": False,
            "official_inclusion_law_saved": True,
            "historical_coordinate_measurement_asserted": False,
            "population_boundary_comparability_asserted": False
        }
    }
    for year in (2002, 2010, 2021):
        b = base["by_year"][str(year)]
        addition = 18131 if year == 2002 else 0
        den = int(b["denominator"])
        num = int(b["event_aware_population"]) + addition
        result["by_year"][str(year)] = {
            "denominator": den,
            "prior_event_aware_population": int(b["event_aware_population"]),
            "kosaya_gora_inclusion_population_added": addition,
            "event_aware_population": num,
            "event_aware_percent": 100 * num / den,
            "gap_to_99_percent": max(0, math.ceil(.99 * den) - num),
            "note": "Separate official 2002 record at its own retrospective point; Tula receiver is not added." if year == 2002 else "No distinct Kosaya Gora population is available in this scope; already represented Tula receiver total is not added again."
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["by_year"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
