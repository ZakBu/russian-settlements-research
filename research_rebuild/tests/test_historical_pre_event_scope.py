import hashlib
import json

import pandas as pd
import pytest

from research_rebuild.mass_linkage.apply_reviewed_mass_extensions_20261004 import (
    load_historical_pre_event_scopes,
    validate_historical_pre_event_pairs,
)


def scope_fixture(tmp_path):
    def asset(name):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(name.encode())
        return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}

    pubs = {"old02": asset("data/raw/02.xls"), "old10": asset("data/raw/10.pdf")}
    origin = asset("raw/point.dbf")
    observations = [{"source_record_id": sid, "observation_year": year,
                     "population_value": pop, "settlement_name": "Former city",
                     "source_path": path}
                    for sid, year, pop, path in [("old02", 2002, 100, "data/raw/02.xls"),
                                                ("old10", 2010, 110, "data/raw/10.pdf")]]
    review = {
        "status": "independent_pre_event_review_complete_candidate_only",
        "decision": {"2002_to_2010_same_place_pair": "supported_for_scoped_root_review",
                     "2011_point_use_for_2002_and_2010": "supported_as_separate_spatial_continuity_candidate"},
        "approved_scope_candidate": {"from_source_record_id": "old02", "to_source_record_id": "old10",
                                     "exact_source_hashes": {k: v["sha256"] for k, v in pubs.items()}},
        "published_city_observations": observations,
        "successor_event": {"event_candidate": {"legacy_asserted_year": "2015"}},
        "input_pins": {"GeoKLADR_DBf": origin},
        "historical_city_identity_and_point": {"2011_GeoKLADR": {
            "is_deleted": False, "type_raw": "г", "latitude": 55.0, "longitude": 38.0}},
    }
    receipt = tmp_path / "review.json"
    receipt.write_text(json.dumps(review))
    manifest = {"historical_pre_event_exceptions": [{
        "review_receipt": {"path": str(receipt), "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()},
        "published_sources": pubs}]}
    selected = pd.DataFrame([{"source_record_id": r["source_record_id"],
                              "census_year": r["observation_year"], "population": r["population_value"],
                              "settlement_type": "город", "settlement_name": "Former city",
                              "source_sha256": None, "source_file": r["source_path"]}
                             for r in observations])
    return manifest, selected


def test_exact_pre_event_pair_support_does_not_grant_successor_identity(tmp_path):
    manifest, selected = scope_fixture(tmp_path)
    scopes, pairs, pins = load_historical_pre_event_scopes(manifest, selected)
    assert set(scopes) == {"old02", "old10"}
    assert pairs == {("old02", "old10")}
    assert pins[0]["source_record_ids"] == ["old02", "old10"]
    validate_historical_pre_event_pairs(pd.DataFrame([{
        "from_source_record_id": "old02", "to_source_record_id": "old10"}]), scopes, pairs)
    with pytest.raises(ValueError, match="successor identity"):
        validate_historical_pre_event_pairs(pd.DataFrame([{
            "from_source_record_id": "old10", "to_source_record_id": "parent21"}]), scopes, pairs)


@pytest.mark.parametrize("column,value,message", [
    ("census_year", 2021, "precede"),
    ("population", 999, "population changed"),
    ("source_file", "data/raw/other.xls", "source path"),
    ("settlement_type", "municipality", "name/type"),
])
def test_pre_event_exception_refuses_newer_or_changed_observation(tmp_path, column, value, message):
    manifest, selected = scope_fixture(tmp_path)
    selected.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        load_historical_pre_event_scopes(manifest, selected)
