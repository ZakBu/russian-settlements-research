from __future__ import annotations

import json

import pandas as pd
import pytest

from research_rebuild.mass_linkage import apply_reviewed_crimea2014_supplemental as app


def _synthetic_rows():
    reviewed = []
    current = []
    points = []
    cells = {}
    for i in range(22):
        source_id = f"2014:Qsource:pub-01-03:{100+i}"
        current_id = f"2021:current:{i}"
        city = i < 3
        dash = i >= 11
        caption = f"город Поселение {i}" if city else f"село Поселение {i}"
        name = f"Поселение {i}"
        pop_raw = "-" if dash else "25"
        family = "three_city_event_scoped" if city else "direct19"
        if city:
            witness = {"accepted_carrier_latitude": 44.0 + i / 1000,
                       "accepted_carrier_longitude": 34.0 + i / 1000,
                       "current_2021_raw_source_name": caption,
                       "current_2021_raw_object_level": "Населенный пункт",
                       "current_2021_raw_population": "25"}
            review = {"observation": witness, "edge": {"event_scope_review": "ancient-event-scoped"}}
            identity_review = "eligible_physical_city_continuity_2014_to_2021"
            pop_status = "literal_official_workbook_cell"
        else:
            witness = {"accepted_current_latitude": 44.0 + i / 1000,
                       "accepted_current_longitude": 34.0 + i / 1000,
                       "raw_object_name": caption,
                       "raw_object_level": "Населенный пункт",
                       "raw_population": "25"}
            review = {"row": witness, "eligible_key": {}}
            identity_review = "eligible_identity_corridor_only"
            pop_status = "missing_source_dash_no_observation" if dash else "literal_integer_in_official_2014_source"
        reviewed.append({
            "source_record_id": source_id, "current_source_record_id": current_id,
            "year": 2014, "place_name": name, "source_caption": caption,
            "source_type": "город" if city else "село", "source_region": "Республика Крым",
            "source_row": str(100+i), "source_sheet": "pub-01-03",
            "source_population_raw": pop_raw, "source_population_value": "" if dash else "25",
            "source_population_status": pop_status, "event_scope_review": "ancient-event-scoped" if city else "",
            "identity_review": identity_review, "current_native_OKTMO_literal": f"357000000{i:02d}",
            "current_2021_population_context": "25", "review_json": json.dumps(review),
            "row_family": family,
        })
        current.append({
            "record_type": "census", "observation_year": 2021, "source_record_id": current_id,
            "entity_id": f"settlement:{i}", "entity_category": "settlement",
            "settlement_name": name, "settlement_type": "город" if city else "село",
            "region_raw": "Республика Крым", "population_value": 25,
            "source_native_id": f"357000000{i:02d}",
        })
        points.append({
            "target_source_record_id": current_id, "latitude": 44.0+i/1000, "longitude": 34.0+i/1000,
            "coordinate_admission_status": "reviewed_rule_accepted", "coordinate_source": "tochno_dadata",
            "coordinate_provider": "tochno_dadata", "coordinate_provider_id": f"provider:{i}",
            "coordinate_provenance": "accepted graph7 point", "point_origin_file": f"origin-{i}.parquet",
            "point_origin_sha256": f"{i+1:064x}", "point_origin_locator": f"parquet_row_1based={i+1}",
            "point_origin_kind": "tochno_2021_dadata_raw_parquet_point",
        })
        cells[source_id] = [caption, "-" if dash else 25, "-" if dash else 12,
                            "-" if dash else 13, "-" if dash else 48]
    return (pd.DataFrame(reviewed), cells, pd.DataFrame(current), pd.DataFrame(points))


def test_literal_dash_is_missing_and_separate_presence_row():
    assert app.literal_integer("-") is None
    assert app.literal_integer("—") is None
    assert app.literal_integer("0") == 0
    reviewed, cells, current, points = _synthetic_rows()
    obs, presence, edges, point_uses = app.create_supplement_rows(reviewed, cells, current, points)
    assert len(obs) == 3
    assert len(presence) == 19
    assert int(presence.population_value.notna().sum()) == 8
    assert int(presence.population_value.isna().sum()) == 11
    assert presence.loc[presence.population_value.isna(), "population_raw"].eq("-").all()
    assert set(presence.record_type) == {"scoped_official_place_presence"}
    assert len(edges) == len(point_uses) == 22
    assert edges.strict_Russian_2002_2010_2021_chain_eligible.eq(False).all()
    assert point_uses.direct_historical_coordinate_measurement.eq(False).all()
    assert obs.latitude.notna().all() and presence.latitude.notna().all()
    assert obs.longitude.notna().all() and presence.longitude.notna().all()
    assert obs.point_origin_sha256.notna().all() and presence.point_origin_sha256.notna().all()
    assert obs.historical_provider_binding_asserted.eq(False).all()
    assert presence.historical_provider_binding_asserted.eq(False).all()
    assert presence.loc[presence.population_value.isna(), "population_raw"].eq("-").all()
    assert presence.loc[presence.population_value.notna(), "population_value"].astype(int).eq(25).all()


def test_population_literal_mismatch_is_rejected():
    reviewed, cells, current, points = _synthetic_rows()
    first_id = reviewed.iloc[0].source_record_id
    cells[first_id] = [cells[first_id][0], 26, 12, 13, 48]
    with pytest.raises(ValueError, match="reviewed population differs"):
        app.create_supplement_rows(reviewed, cells, current, points)


def test_wrong_carrier_or_coordinate_origin_is_rejected():
    reviewed, _, current, points = _synthetic_rows()
    bad = points.copy()
    bad.loc[0, "target_source_record_id"] = "2021:wrong"
    with pytest.raises(ValueError, match="missing accepted current point carriers"):
        app.validate_current_carriers(reviewed, current, bad)

    bad = points.copy()
    bad.loc[0, "latitude"] = 1.0
    with pytest.raises(ValueError, match="reviewed coordinate does not match"):
        app.validate_current_carriers(reviewed, current, bad)


def test_wrong_current_population_or_code_is_rejected():
    reviewed, _, current, points = _synthetic_rows()
    bad = current.copy()
    bad.loc[0, "population_value"] = 999
    with pytest.raises(ValueError, match="reviewed current population context differs"):
        app.validate_current_carriers(reviewed, bad, points)

    bad = current.copy()
    bad.loc[0, "source_native_id"] = "wrong"
    with pytest.raises(ValueError, match="native code differs"):
        app.validate_current_carriers(reviewed, bad, points)


def test_source_hash_mismatch_is_rejected(tmp_path):
    path = tmp_path / "source.bin"
    path.write_bytes(b"frozen-source")
    with pytest.raises(ValueError, match="source workbook hash mismatch"):
        app.verify_hash(path, "0" * 64, "source workbook")


def test_duplicate_publication_row_is_rejected_even_under_a_different_observation_id(tmp_path):
    base = tmp_path / "base.parquet"
    pd.DataFrame([{
        "observation_id": "official2014:other-prefix",
        "source_record_id": "2014:Qsource:pub-01-03:123",
        "source_publication_row_id": "2014:Qsource:pub-01-03:123",
    }]).to_parquet(base, index=False)
    with pytest.raises(ValueError, match="publisher row IDs already exist"):
        app.ensure_no_observation_collisions(base, ["official2014presence:2014:Qsource:pub-01-03:123"],
                                             ["2014:Qsource:pub-01-03:123"])


def test_staged_parquet_frame_preserves_nullable_population_and_boolean_types():
    frame = pd.DataFrame({
        "observation_year": [2014, 2014],
        "population_value": [4164, None],
        "population_raw": ["4,164", "—"],
        "historical_provider_binding_asserted": [False, False],
        "latitude": [44.1, 44.2],
    })
    typed = app.typed_staged_frame(frame)
    assert str(typed.observation_year.dtype) == "Int16"
    assert str(typed.population_value.dtype) == "Int64"
    assert str(typed.historical_provider_binding_asserted.dtype) == "boolean"
    assert typed.population_value.iloc[0] == 4164
    assert pd.isna(typed.population_value.iloc[1])
    assert typed.population_raw.tolist() == ["4,164", "—"]
    assert typed.latitude.tolist() == [44.1, 44.2]
