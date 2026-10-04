#!/usr/bin/env python3
"""Stage 27 official Ukrainian 2001 present-population source assertions.

Rows remain unbound source observations. The existing scoped 2014-to-2021
associations and current accepted points are supplied as separate context; this
utility creates no 2001 identity edge or historical coordinate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import xlrd

REVIEW = Path("/workspace/settlements-work/continuation_20261004/independent_review/ukraine2001_27_primary_review")
OUT_DEFAULT = Path("/workspace/settlements-work/continuation_20261004/independent_review/ukraine2001_crimea_primary_staged_v2")
WORKBOOK = Path("/workspace/settlements-work/continuation_20261004/federal_and_history/crimea_2001_source_claim_review_20261004/official_tls_source/extracted/5.xls")
PREFACE = Path("/workspace/settlements-work/continuation_20261004/federal_and_history/ukraine_2001_official_archive_inspection/doc_text/Передмова 1.txt")
BASE_LONG = Path("/workspace/settlements-work/continuation_20261004/root/scoped2014_applied/seventh_long_with_scoped2014.parquet")
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
CURRENT_RAW = Path("/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet")
POINT_LEDGER = Path("/workspace/settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/accepted_point_uses.parquet")

PINS = {
    "review_receipt": (REVIEW / "review_receipt.json", "7c32557cb5af6b2eeaaae4b00589a61d4035c392d85ae465b3c8ee95ae23f806"),
    "observations": (REVIEW / "eligible_2001_official_observations.csv", "4eb8f0ac200f63d2916b269e023f592e08b61f020042581787a2a42dbd8526e8"),
    "subject_contexts": (REVIEW / "candidate_2001_observation_subject_contexts.csv", "3123b74ab742afc7f01919927959be396b924096d4e9a545859bb31ee46c220b"),
    "point_contexts": (REVIEW / "candidate_2001_current_point_context_uses.csv", "8940826082945832c05a61d6378b53335c23f28ff6ae81376a1f2758955a5560"),
    "review_code": (REVIEW / "review_ukraine2001_27.py", "1415bf113a4d899a32a141b8888eaa023e8b66f645a3541bfaaa9b96f1fec637"),
    "source_workbook": (WORKBOOK, "5088ed43450aff371eb8b7382222d3c08ebc591e676368f5e00a76ffa4a56b33"),
    "preface": (PREFACE, "6f2a5380e62b44898741de218f49f7017b91cff96145f6ea24e35bd8b56ab3f1"),
    "preface_doc": (Path("/workspace/settlements-work/continuation_20261004/federal_and_history/crimea_2001_source_claim_review_20261004/official_tls_source/extracted/Передмова 1.doc"), "a69b56680c5d605c30dc241f879b41139e38312ccb419e6ad12373c424fcfcd6"),
    "archive_receipt": (Path("/workspace/settlements-work/continuation_20261004/federal_and_history/ukraine_2001_official_archive_inspection/receipt.json"), "9214cfc4a0d018014357d155fd357d577873a49ef53e1bb9e05e37c3d61089c8"),
    "current_raw": (CURRENT_RAW, "86c197cd522e0b63669e9c6e7f43fd3d82b3704c6a126c800a9968ecd16cae14"),
    "selected": (SELECTED, "4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657"),
    "base_long": (BASE_LONG, "be04c25f2cdcc1614e2c17865ca8a96593e4308f36ad344281062c37c7bd6360"),
    "point_ledger": (POINT_LEDGER, "2215702e772417bb512da8c0a6c0d31ad9783c6a5345d4c0bbfe18403e11ad22"),
    "2014_edges": (Path("/workspace/settlements-work/continuation_20261004/independent_review/crimea2014_scoped/eligible_2014_to_2021_identity_edges.csv"), "268f7f9e7958a34e63cac1816bb53cfed965cf2eeda4c002db97a9060a38706e"),
    "2014_points": (Path("/workspace/settlements-work/continuation_20261004/independent_review/crimea2014_scoped/eligible_2014_retrospective_point_uses.csv"), "b1f8aeb1e13613659234862ef17c59fb0d943610050cb1339356e3997451fb0e"),
}


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", engine="python")


def verify_inputs() -> dict[str, str]:
    hashes = {}
    for name, (path, expected) in PINS.items():
        need(path.is_file(), f"missing input {name}: {path}")
        actual = sha256(path)
        need(actual == expected, f"input hash mismatch for {name}: {actual}")
        hashes[name] = actual
    receipt = json.loads(PINS["review_receipt"][0].read_text(encoding="utf-8"))
    need(receipt.get("candidate_only_no_application") is True and receipt.get("independently_verified_source_rows") == 27,
         "independent 27-row review receipt changed")
    need(receipt.get("candidate_population_total") == 845627 and receipt.get("strict_Russian_2002_2010_2021_gain") == 0,
         "independent review totals changed")
    return hashes


def replay_workbook(observations: pd.DataFrame) -> None:
    book = xlrd.open_workbook(str(WORKBOOK), on_demand=True)
    try:
        need("АРК" in book.sheet_names(), "Ukraine 2001 Table5 worksheet missing")
        sheet = book.sheet_by_name("АРК")
        need("Кількість наявного населення" in str(sheet.cell_value(0, 0)) and int(sheet.cell_value(3, 3)) == 2001,
             "workbook title/header no longer identifies 2001 present-population")
        need(sheet.ncols == 7, "unexpected 2001 Table5 layout")
        preface = PREFACE.read_text(encoding="utf-8-sig").lower()
        need("станом на 5 грудня 2001 року" in preface and "наявне населення" in preface,
             "official preface does not support 2001-12-05 present-population description")
        seen: set[int] = set()
        for r in observations.to_dict("records"):
            row_no = int(r["official_row_1based"])
            need(row_no not in seen, f"duplicate Table5 source row locator {row_no}")
            seen.add(row_no)
            raw_label = str(sheet.cell_value(row_no - 1, 0))
            raw_population = sheet.cell_value(row_no - 1, 3)
            need(raw_label.strip() == str(r["official_row_label_raw"]).strip(), f"raw Table5 label mismatch at row {row_no}")
            need(int(raw_population) == int(r["population_raw_table5"]), f"raw Table5 population mismatch at row {row_no}")
            need(r["population_measure"] == "present_population" and r["official_census_reference_date"] == "2001-12-05",
                 f"unexpected measure/date status at row {row_no}")
            need(str(r["source_has_native_locality_code"]).lower() == "false" and
                 str(r["table_sex_disaggregation_published"]).lower() == "false",
                 f"source identifier/sex scope changed at row {row_no}")
            need(str(r["P585_literal"]) == "+2001-00-00T00:00:00Z" and str(r["P585_precision"]) == "9",
                 f"P585 date precision was changed at row {row_no}")
        need(len(seen) == 27, "expected 27 unique official source rows")
    finally:
        book.release_resources()


def typed(frame: pd.DataFrame, ints: tuple[str, ...] = (), bools: tuple[str, ...] = (), floats: tuple[str, ...] = ()) -> pd.DataFrame:
    out = frame.copy()
    for col in ints:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    for col in bools:
        if col in out:
            if out[col].dtype == object:
                out[col] = out[col].map({"True": True, "False": False, "true": True, "false": False,
                                         True: True, False: False, "": pd.NA})
            out[col] = out[col].astype("boolean")
    for col in floats:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Float64")
    return out


def build_layer() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    source_obs = read_csv(PINS["observations"][0])
    subject = read_csv(PINS["subject_contexts"][0])
    point_context = read_csv(PINS["point_contexts"][0])
    edge2014 = read_csv(PINS["2014_edges"][0])
    point2014 = read_csv(PINS["2014_points"][0])
    need(len(source_obs) == len(subject) == len(point_context) == 27, "reviewed 27-row vectors changed")
    need(source_obs.historical_source_candidate_key.is_unique and subject.historical_2001_candidate_key.is_unique and
         point_context.current_source_record_id_2021.is_unique, "27-row keys are duplicated")
    replay_workbook(source_obs)
    need(source_obs.population_raw_table5.astype(int).sum() == 845627, "2001 official population sum changed")
    need((source_obs.official_row_type == "city").sum() == 11 and (source_obs.official_row_type == "urban_type_settlement").sum() == 16,
         "urban locality type split changed")
    need(not source_obs.unresolved_successor_or_merger_event_hold.str.lower().eq("true").any(),
         "source cohort contains a new successor/merger event hold")
    need(not source_obs.identity_admitted.str.lower().eq("true").any() and
         not source_obs.historical_coordinates_admitted.str.lower().eq("true").any(),
         "source review unexpectedly admitted 2001 identity/coordinates")

    keymap = subject.set_index("historical_2001_candidate_key", drop=False)
    points_by_source = point_context.set_index("current_source_record_id_2021", drop=False)
    need({"from_source_record_id", "to_source_record_id", "source_population", "review_status"} <= set(edge2014.columns),
         "2014-to-2021 reviewed mapping packet schema changed")
    edge14_map = edge2014.set_index("from_source_record_id", drop=False)
    point14_map = point2014.set_index("target_source_record_id", drop=False)
    # Source keys carry the 2014 endpoint in their `2001 -> 2014 -> 2021` trace.
    parsed = []
    for r in source_obs.to_dict("records"):
        pieces = str(r["historical_source_candidate_key"]).split(" -> ")
        need(len(pieces) == 3, "candidate trajectory key no longer has 2001/2014/2021 endpoints")
        source_id, intermediate_2014_id, current_id = pieces
        subj = keymap.loc[r["historical_source_candidate_key"]]
        need(str(subj.current_2021_source_record_id) == current_id and
             str(subj.intervening_2014_source_record_id) == intermediate_2014_id,
             f"subject context endpoints disagree for {source_id}")
        need(str(r["current_source_record_id_2021"]) == current_id,
             f"official observation and current row disagree for {source_id}")
        need(str(r["current_qid_context"]) == str(subj.source_row_to_wikidata_subject_qid),
             f"source subject context disagrees for {source_id}")
        parsed.append({**r, "source_record_id": source_id, "intervening_2014_source_record_id": intermediate_2014_id,
                       "current_id": current_id, "subject_context": subj.to_dict()})
    parsed_df = pd.DataFrame(parsed)

    # Re-open current records, existing 2014 source observations, and the accepted current point carrier.
    ids = sorted(parsed_df.current_id.astype(str).unique())
    ids14 = sorted(parsed_df.intervening_2014_source_record_id.astype(str).unique())
    con = duckdb.connect(":memory:")
    con.execute("SET memory_limit='512MB'")
    con.execute("SET threads=1")
    current = con.execute("SELECT census_year,source_record_id,settlement_name,settlement_type,region_raw,population,source_native_id FROM read_parquet(?) WHERE census_year=2021 AND source_record_id IN (SELECT unnest(?))", [str(SELECTED), ids]).fetchdf()
    current_raw = con.execute("WITH x AS (SELECT row_number() OVER() AS row_number,object_level,object_name,oktmo,region,population,latitude_dadata,longitude_dadata FROM read_parquet(?)) SELECT * FROM x WHERE row_number IN (SELECT unnest(?))", [str(CURRENT_RAW), sorted(int(x.rsplit(":",1)[1]) for x in ids)]).fetchdf()
    baseline = con.execute("SELECT observation_id,record_type,entity_id,associated_census_entity_id,association_status,spatial_identity_status,identity_quality,observation_year,source_record_id,settlement_name,settlement_type,region_raw,population_value,latitude,longitude,coordinate_admission_status,historical_identity_admitted,population_scope_comparability_asserted,boundary_comparability_asserted FROM read_parquet(?) WHERE source_record_id IN (SELECT unnest(?))", [str(BASE_LONG), ids + ids14]).fetchdf()
    point_ledger = con.execute("SELECT target_source_record_id,target_year,latitude,longitude,coordinate_source,coordinate_provider,coordinate_provider_id,coordinate_provenance,coordinate_admission_status,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind FROM read_parquet(?) WHERE regexp_replace(target_year,'\\.0$','')='2021' AND target_source_record_id IN (SELECT unnest(?))", [str(POINT_LEDGER), ids]).fetchdf()
    con.close()
    need(len(current) == len(ids) == len(current_raw) == len(point_ledger), "current selected/raw/point vectors are incomplete")
    curmap = current.set_index("source_record_id", drop=False)
    rawmap = current_raw.set_index("row_number", drop=False)
    base_map = baseline.set_index("source_record_id", drop=False)
    point_map = point_ledger.set_index("target_source_record_id", drop=False)
    observations: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    point_uses: list[dict[str, Any]] = []
    origin_hashes: dict[str, str] = {}
    for r in parsed:
        sid, mid, cid = r["source_record_id"], r["intervening_2014_source_record_id"], r["current_id"]
        s, b14, b21, p = curmap.loc[cid], base_map.loc[mid], base_map.loc[cid], point_map.loc[cid]
        point_review = points_by_source.loc[cid]
        need(str(s.region_raw) == str(r["current_2021_raw_source_region"]), f"current source region changed for {cid}")
        need(str(s.source_native_id) == str(r["current_native_OKTMO_2021_only"]), f"2021 native OKTMO context changed for {cid}")
        need(str(b21.entity_id).startswith("settlement:"), f"current census carrier entity ID is missing for {cid}")
        need(str(b14.associated_census_entity_id) == str(b21.entity_id) and
             str(b14.association_status) == "reviewed_scoped_same_place_to_2021" and
             str(b14.historical_identity_admitted).lower() == "true",
             f"existing 2014-to-2021 scoped association is missing or changed for {mid}")
        need(mid in edge14_map.index and mid in point14_map.index,
             f"independently reviewed 2014 endpoint/point candidate is missing for {mid}")
        e14, p14 = edge14_map.loc[mid], point14_map.loc[mid]
        need(str(e14.to_source_record_id) == cid and
             str(e14.review_status) == "independently_eligible_for_scoped_application_candidate_only" and
             int(float(e14.source_population)) == int(b14.population_value),
             f"2014 reviewed source edge does not match baseline for {mid}")
        need(str(p14.source_2021_carrier_target_source_record_id) == cid and
             str(p14.coordinate_use_review_status) == "independently_eligible_for_scoped_application_candidate_only",
             f"2014 point candidate does not map to the same current carrier for {mid}")
        need(str(r["2014_to_2021_edge_status"]) == "independently_eligible_for_scoped_application_candidate_only" and
             str(r["identity_admitted"]).lower() == "false",
             f"2001-to-2014/2021 identity scope changed for {sid}")
        rawnum = int(cid.rsplit(":", 1)[1])
        raw = rawmap.loc[rawnum]
        need(str(raw.object_name).strip() == str(r["current_2021_raw_source_name"]).strip() and
             str(raw.object_level) == str(r["current_2021_raw_source_object_level"]) and
             str(raw.region) == str(r["current_2021_raw_source_region"]) and str(raw.oktmo) == str(r["current_native_OKTMO_2021_only"]),
             f"current raw publisher row changed for {cid}")
        need(int(raw.population) == int(float(r["current_2021_source_population"])), f"current raw population changed for {cid}")
        need(math.isclose(float(p.latitude), float(point_review.point_latitude_current_representative), abs_tol=1e-10) and
             math.isclose(float(p.longitude), float(point_review.point_longitude_current_representative), abs_tol=1e-10),
             f"current accepted point differs from reviewed carrier for {cid}")
        need(str(p.coordinate_admission_status) in {"reviewed_rule_accepted", "reviewed_extension_rule_accepted"},
             f"current point is not accepted for {cid}")
        origin = Path(str(p.point_origin_file))
        need(origin.is_file(), f"current point origin is missing for {cid}")
        if str(origin) not in origin_hashes:
            origin_hashes[str(origin)] = sha256(origin)
        need(origin_hashes[str(origin)] == str(p.point_origin_sha256) == str(point_review.point_origin_sha256),
             f"current point origin hash mismatch for {cid}")

        source_id = str(r["source_record_id"])
        source_name = str(r["official_row_label_raw"])
        population = int(r["population_raw_table5"])
        observations.append({
            "observation_id": f"ukraine2001_official_source:{source_id}", "record_type": "historical_source_observation",
            "record_scope": "primary_official_source_assertion_not_identity_bound",
            "source_record_id": source_id, "source_publication_row_id": source_id,
            "historical_source_candidate_key": r["historical_source_candidate_key"],
            "entity_id": None, "associated_census_entity_id": None,
            "association_status": "source_row_only_current_subject_is_context",
            "identity_admission_status": "not_admitted",
            "source_name_raw": source_name, "settlement_name": source_name.strip().split(maxsplit=1)[-1],
            "source_type": r["official_row_type"], "source_admin_parent_raw": r["source_admin_parent_row_raw"],
            "source_grouping_raw": r["source_grouping_row_raw"],
            "observation_year": 2001, "reference_date": "2001-12-05",
            "reference_date_source": "official collection preface: enumerated at midnight 4/5 December 2001",
            "reference_date_basis": "official_census_reference_date", "observation_date_precision": "day_source_preface; Wikidata P585 remains year precision 9",
            "actual_census_date_claimed": True, "population_measure": "present_population",
            "population_unit": "persons", "population_value": population, "population_raw": str(r["population_raw_table5"]),
            "population_source_claim_P1082_raw": str(r["population_raw_P1082"]),
            "population_assertion_admitted": True, "population_to_current_entity_binding_admitted": False,
            "population_value_quality": "Ukraine_2001_official_Table5_row_replayed; present_population",
            "source_sheet": r["official_sheet"], "source_row": int(r["official_row_1based"]),
            "source_row_label_literal": source_name, "source_file": str(WORKBOOK),
            "source_sha256": str(r["official_workbook_sha256"]),
            "source_has_native_locality_code": False, "native_2001_OKTMO_raw": None,
            "native_2001_code_binding_asserted": False,
            "table_sex_disaggregation_published": False, "population_male": None, "population_female": None,
            "current_QID_context_only": str(r["current_qid_context"]),
            "current_QID_binding_scope": "reviewed_2021_current_source_to_QID_only; not a 2001 identity binding",
            "P1082_statement_guid": str(r["actual_P1082_statement_guid"]), "P1082_rank": str(r["P1082_rank"]),
            "P1082_literal_date": str(r["P585_literal"]), "P1082_date_precision": int(r["P585_precision"]),
            "P1082_statement_sha256": str(r["P1082_statement_sha256"]),
            "P1082_matches_official_source_count": True,
            "intervening_2014_source_record_id_context_only": mid,
            "current_2021_source_record_id_context_only": cid,
            "historical_coordinates_asserted": False,
            "population_boundary_comparability_asserted": False,
            "strict_Russian_2002_2010_2021_chain": False,
            "event_scope_note": "P571 establishment-date-only context is not used as identity; successor/merger holds excluded upstream",
            "review_status": "root_approved_official_primary_source_observation; 2001 identity remains unadmitted",
            "root_decision_reference": "2026-10-04 root approval of 27 Ukraine 2001 official source assertions; 2014-to-2021 existing scoped map only",
        })
        mappings.append({
            "mapping_id": f"existing-2014-current-map:{len(mappings)+1:02d}",
            "from_source_record_id": mid, "from_year": 2014,
            "to_source_record_id": cid, "to_year": 2021,
            "relation": "existing_scoped_2014_to_2021_same_place_association",
            "mapping_status": "already_present_in_frozen_long_baseline_not_newly_admitted",
            "baseline_2014_observation_id": str(b14.observation_id),
            "baseline_entity_id": str(b14.entity_id),
            "baseline_association_status": str(b14.association_status),
            "baseline_spatial_identity_status": str(b14.spatial_identity_status),
            "baseline_historical_identity_admitted": bool(b14.historical_identity_admitted),
            "year_2014_population_context": int(b14.population_value),
            "year_2021_population_context": int(s.population),
            "2014_independent_edge_packet_status": str(e14.review_status),
            "2014_point_packet_status": str(p14.coordinate_use_review_status),
            "population_boundary_comparability_asserted": False,
            "strict_national_2002_2010_2021_chain": False,
            "input_2001_candidate_key": r["historical_source_candidate_key"],
            "does_not_admit_2001_identity": True,
        })
        paths.append({
            "path_id": f"ukraine-crimea-time-context:{len(paths)+1:02d}",
            "observation_2001_source_record_id": source_id,
            "population_2001_source_value": population,
            "population_2001_identity_status": "official source observation admitted; place identity unbound",
            "observation_2014_source_record_id": mid,
            "population_2014_existing_baseline_value": int(b14.population_value),
            "identity_2014_to_2021_status": "existing scoped same-place association in frozen baseline",
            "current_2021_source_record_id": cid,
            "population_2021_selected_value": int(s.population),
            "current_entity_id_for_2014_2021_only": str(b21.entity_id),
            "current_point_use_id": f"ukraine-crimea-current-point:{len(point_uses)+1:02d}",
            "path_status": "2001 source value plus existing 2014-to-2021 path; no 2001-to-2014/2021 continuity assertion",
            "population_boundary_comparability_asserted": False,
            "three_year_same_place_chain_admitted": False,
        })
        point_uses.append({
            "point_use_id": f"ukraine-crimea-current-point:{len(point_uses)+1:02d}",
            "target_source_record_id": cid, "target_year": 2021,
            "current_qid_context_only": str(r["current_qid_context"]),
            "latitude": float(p.latitude), "longitude": float(p.longitude),
            "point_status": str(p.coordinate_admission_status),
            "point_role": "accepted_current_2021_representative_point_context_only",
            "coordinate_measurement_date_unknown": True,
            "historical_2001_coordinate_use_claimed": False,
            "coordinate_provider": str(p.coordinate_provider), "coordinate_provider_id": str(p.coordinate_provider_id),
            "coordinate_source": str(p.coordinate_source), "coordinate_provenance": str(p.coordinate_provenance),
            "point_origin_file": str(p.point_origin_file), "point_origin_sha256": str(p.point_origin_sha256),
            "point_origin_locator": str(p.point_origin_locator), "point_origin_kind": str(p.point_origin_kind),
            "point_origin_raw_rehashed": True,
            "boundary_comparability_asserted": False,
        })

    obs_df = typed(pd.DataFrame(observations), ints=("observation_year", "source_row", "population_value", "P1082_date_precision"),
                   bools=("actual_census_date_claimed", "population_assertion_admitted", "population_to_current_entity_binding_admitted", "source_has_native_locality_code", "native_2001_code_binding_asserted", "table_sex_disaggregation_published", "P1082_matches_official_source_count", "historical_coordinates_asserted", "population_boundary_comparability_asserted", "strict_Russian_2002_2010_2021_chain"))
    map_df = typed(pd.DataFrame(mappings), ints=("from_year", "to_year", "year_2014_population_context", "year_2021_population_context"), bools=("baseline_historical_identity_admitted", "population_boundary_comparability_asserted", "strict_national_2002_2010_2021_chain", "does_not_admit_2001_identity"))
    path_df = typed(pd.DataFrame(paths), ints=("population_2001_source_value", "population_2014_existing_baseline_value", "population_2021_selected_value"), bools=("population_boundary_comparability_asserted", "three_year_same_place_chain_admitted"))
    point_df = typed(pd.DataFrame(point_uses), ints=("target_year",), bools=("coordinate_measurement_date_unknown", "historical_2001_coordinate_use_claimed", "point_origin_raw_rehashed", "boundary_comparability_asserted"), floats=("latitude", "longitude"))
    need(len(obs_df) == len(map_df) == len(path_df) == len(point_df) == 27, "staged 27-row vectors changed")
    need(int(obs_df.population_value.sum()) == 845627, "staged 2001 official total changed")
    return obs_df, map_df, path_df, point_df, {"origins_rehashed": origin_hashes}


def write_layer(out: Path, inputs: dict[str, str], layer: tuple[pd.DataFrame, ...], origin_hashes: dict[str, str]) -> dict[str, Any]:
    need(not out.exists(), f"refusing to overwrite staged output: {out}")
    out.mkdir(parents=True)
    names = ("official_2001_source_observations", "existing_2014_to_2021_mappings", "available_year_context_paths", "current_2021_point_context_uses")
    outputs = {}
    for name, frame in zip(names, layer):
        for ext in ("csv", "parquet"):
            path = out / f"{name}.{ext}"
            frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL) if ext == "csv" else frame.to_parquet(path, index=False)
            outputs[f"{name}_{ext}"] = {"path": str(path), "sha256": sha256(path), "rows": len(frame), "bytes": path.stat().st_size}
    test_path = Path(__file__).parent / "tests/test_stage_ukraine2001_crimea_primary_layer.py"
    manifest = {"status": "frozen_ukraine2001_application_inputs", "inputs": {n: {"path": str(p), "sha256": h} for n, (p, h) in PINS.items()},
                "producer_code": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
                "producer_tests": {"path": str(test_path.resolve()), "sha256": sha256(test_path)},
                "point_origin_hashes_replayed": origin_hashes}
    mp = out / "application_input_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs["application_input_manifest"] = {"path": str(mp), "sha256": sha256(mp), "bytes": mp.stat().st_size}
    receipt = {
        "status": "root_approved_ukraine_2001_primary_source_assertions_staged_unbound",
        "root_decision_reference": "2026-10-04 root approval of 27 official Ukraine 2001 primary source assertions with only the already admitted 2014-to-2021 context",
        "official_2001_source_observations": len(layer[0]), "official_present_population_total": int(layer[0].population_value.sum()),
        "source_type_counts": layer[0].source_type.value_counts().to_dict(),
        "available_source_value_rows_by_year": {"2001": len(layer[0]), "2014": len(layer[1]), "2021": len(layer[1])},
        "observed_population_value_sums_context_only": {
            "2001_official_present_population": int(layer[0].population_value.sum()),
            "2014_existing_scoped_source_rows": int(layer[2].population_2014_existing_baseline_value.sum()),
            "2021_selected_source_rows": int(layer[2].population_2021_selected_value.sum()),
            "cross_year_sum_or_comparison_claimed": False,
        },
        "current_source_QID_bindings_to_2001": 0, "2001_identity_edges_created": 0,
        "existing_2014_to_2021_context_mappings": len(layer[1]), "new_2014_to_2021_edges_created": 0,
        "available_year_context_rows": len(layer[2]), "current_2021_point_context_uses": len(layer[3]),
        "current_point_provider_counts": layer[3].coordinate_provider.value_counts().to_dict(),
        "historical_2001_coordinates_asserted": False, "native_2001_code_binding_asserted": False,
        "population_boundary_comparability_asserted": False, "strict_Russian_2002_2010_2021_gain": 0,
        "permanent_population_or_village_allocation_included": False, "table_sex_counts_invented": False,
        "p571_establishment_flags_promoted_to_identity": 0, "successor_or_merge_flags_promoted": 0,
        "selected_frame_or_canonical_graph_mutated": False, "long_table_appended": False,
        "input_hashes": inputs, "outputs": outputs,
        "limitations": "2001 source rows are locator-derived and have no native locality codes. The current QID/native OKTMO are 2021-only context. Existing 2014-to-2021 baseline associations remain scoped to those years; 2001-to-2014/2021 identity and population boundary comparability are not asserted.",
    }
    rp = out / "application_receipt.json"
    rp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt["receipt_file_sha256"] = sha256(rp)
    return receipt


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--write-staged", action="store_true")
    args = ap.parse_args()
    hashes = verify_inputs()
    observations, mappings, paths, points, auxiliary = build_layer()
    result = {"status": "validated_ukraine2001_primary_source_layer_unbound_not_appended", "official_source_rows": len(observations),
              "official_present_population_total": int(observations.population_value.sum()),
              "2014_to_2021_existing_mappings": len(mappings), "available_year_context_paths": len(paths),
              "current_point_context_uses": len(points), "identity_2001_admitted": False,
              "strict_Russian_2002_2010_2021_gain": 0, "selected_graph_or_long_mutated": False}
    if args.write_staged:
        receipt = write_layer(args.out_dir, hashes, (observations, mappings, paths, points), auxiliary["origins_rehashed"])
        result.update(output_dir=str(args.out_dir), application_receipt_sha256=receipt["receipt_file_sha256"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
