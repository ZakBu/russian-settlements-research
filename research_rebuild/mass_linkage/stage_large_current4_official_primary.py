#!/usr/bin/env python3
"""Stage root-approved official Rosstat assertions for four large settlements.

The utility consumes the frozen independent review and same-census mapping
packets, replays their seven official source rows, attaches accepted modern
point context, and writes a separate integration layer. It does not mutate the
selected census frame, accepted graph, or long table.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import fitz
import pandas as pd
import xlrd

ROOT = Path("/workspace/settlements-work/continuation_20261004/independent_review")
OUT_DEFAULT = ROOT / "large_current4_official_primary_staged_v2"
EDGE_REVIEW = ROOT / "large_current4_official_rosstat_correction_review"
MAPPING_REVIEW = ROOT / "large_current4_same_census_source_mapping"

PINS = {
    "edge_receipt": (EDGE_REVIEW / "review_receipt.json", "d6245c021fcd7c71ce255b8a858ecca0a274f8d85633067a543d8ac027db77a1"),
    "edge_rows": (EDGE_REVIEW / "independently_reviewed_corridor_edges.csv", "18c2d6e73951eb23392fd048638583719b79764ec94f61f2c18690452980b491"),
    "source_row_replay": (EDGE_REVIEW / "official_source_row_replay.csv", "aba5f4a4778d3918b95e14ecf8bcf9f42b1d55017dbd4cc1c2c44ec3f99fc784"),
    "point_context": (EDGE_REVIEW / "current_point_and_source_context.csv", "f62bc208923cf779bfeea3107b1000f3ec26f1bd38d9962f8a0946e07d1bb549"),
    "mapping_receipt": (MAPPING_REVIEW / "mapping_receipt.json", "d2470e6a563f66163c4ab3eb368853f7d4c58b9d1eddc75f8ef0416b9f4a18f6"),
    "mapping_rows": (MAPPING_REVIEW / "official_to_selected_source_mapping.csv", "d1613388a6af1ee73700b8bf8c59b3b8d1cf8a4b6fdac6d9dfba62836db92818"),
    "mapping_source_replay": (MAPPING_REVIEW / "source_row_replay.json", "d640017fdb3a1c3f0198241e82c11af1b21fcee8cd79b1b605660492ab26c892"),
    "selected": (Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet"), "4ff918ae07715e98a37aa5dc77546f3d7b7ac9c241c7c01a041c8f72a6f8c657"),
    "base_long": (Path("/workspace/settlements-work/continuation_20261004/root/scoped2014_applied/seventh_long_with_scoped2014.parquet"), "be04c25f2cdcc1614e2c17865ca8a96593e4308f36ad344281062c37c7bd6360"),
    "point_ledger": (Path("/workspace/settlements-work/continuation_20261004/accepted_mass_seventh_reviewed/accepted_point_uses.parquet"), "2215702e772417bb512da8c0a6c0d31ad9783c6a5345d4c0bbfe18403e11ad22"),
    "official_2002": (Path("/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls"), "745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3"),
    "official_2010": (Path("/workspace/settlements-raw/data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf"), "42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3"),
    "kush_parts": (Path("/workspace/settlements-raw/data/raw/2002/036_81b258bc42_02c_Krasnodarski-krai.xls"), "9588f5aa5f8de40a290739a880e624a6d34ea566377b9a7f4df1674f1cf99121"),
}

EXPECTED_NEW_OBSERVATIONS = {
    "ROSSTAT2002:T4:01-04:r4338",  # Kushchevskaya whole locality
    "ROSSTAT2010:T5:p33:l120",     # Vlasikha
    "ROSSTAT2002:T4:01-04:r1212",  # Kalininets
    "ROSSTAT2010:T5:p36:l82",      # Kalininets
    "ROSSTAT2010:T5:p199:l277",    # Trudovoe
}
SOURCE_TYPE_RAW = {
    ("Кущевская", 2002): "ст-ца", ("Кущевская", 2010): "станица",
    ("Власиха", 2010): "пгт", ("Калининец", 2002): "п.",
    ("Калининец", 2010): "пгт", ("Трудовое", 2002): "пгт",
    ("Трудовое", 2010): "поселок",
}
CURRENT_IDS = {
    "Кущевская": "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:45656",
    "Власиха": "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:70219",
    "Калининец": "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:68255",
    "Трудовое": "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:100072",
}
ALIAS_IDS = {
    "ROSSTAT2010:T5:p79:l76": "ROSSTAT2010:T5:p79:l18",
    "ROSSTAT2002:T4:01-04:r9927": "2002:1_TOM_01_04.xls:0:9927",
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
    hashes: dict[str, str] = {}
    for name, (path, expected) in PINS.items():
        need(path.is_file(), f"missing pinned {name}: {path}")
        actual = sha256(path)
        need(actual == expected, f"pinned {name} hash mismatch: {actual}")
        hashes[name] = actual
    edge_receipt = json.loads(PINS["edge_receipt"][0].read_text(encoding="utf-8"))
    need(edge_receipt.get("status") == "independent_official_four_large_source_review_complete_candidate_only",
         "independent edge review status changed")
    need(edge_receipt.get("independently_supported_candidate_edge_rows") == 7 and
         edge_receipt.get("identity_or_population_admissions") == 0,
         "independent edge review counts changed")
    mapping_receipt = json.loads(PINS["mapping_receipt"][0].read_text(encoding="utf-8"))
    need(mapping_receipt.get("status") == "independent_same_census_source_mapping_complete_candidate_only",
         "same-census mapping review status changed")
    need(mapping_receipt.get("mapping_rows") == 7 and mapping_receipt.get("same_census_partition_relations") == 1 and
         mapping_receipt.get("same_year_identity_merges") == 0,
         "same-census source mapping counts changed")
    return hashes


def replay_official_rows(rows: pd.DataFrame) -> None:
    """Reopen all 3 Table4 and 4 Table5 literals against the pinned official files."""
    xls_rows = rows[rows.year.eq("2002")]
    pdf_rows = rows[rows.year.eq("2010")]
    need(len(xls_rows) == 3 and len(pdf_rows) == 4, "expected 3 official 2002 and 4 official 2010 replay rows")
    wb = xlrd.open_workbook(str(PINS["official_2002"][0]), on_demand=True)
    try:
        sheet = wb.sheet_by_name("01-04")
        for r in xls_rows.to_dict("records"):
            rownum = int(r["raw_check"].split("row=")[1].split(";")[0])
            vals = sheet.row_values(rownum - 1)
            label = str(vals[0]).strip()
            expected = (r["literal_label"].strip(), int(r["population"]), int(r["men"]), int(r["women"]))
            actual = (label, int(vals[1]), int(vals[2]), int(vals[3]))
            need(actual == expected, f"official Table4 raw row changed at {r['source_record_id']}: {actual}")
    finally:
        wb.release_resources()
    doc = fitz.open(str(PINS["official_2010"][0]))
    try:
        for r in pdf_rows.to_dict("records"):
            match = re.search(r"pdf_page=(\d+)", r["raw_check"])
            need(match, f"missing Table5 page locator: {r['source_record_id']}")
            page_no = int(match.group(1))
            text = " ".join(doc[page_no - 1].get_text().split())
            label = " ".join(r["literal_label"].split())
            pattern = re.escape(label) + r"\s+(\d+)\s+(\d+)\s+(\d+)"
            found = list(re.finditer(pattern, text))
            need(len(found) == 1, f"official Table5 row is absent or ambiguous at {r['source_record_id']}")
            actual = tuple(int(x) for x in found[0].groups())
            expected = (int(r["population"]), int(r["men"]), int(r["women"]))
            need(actual == expected, f"official Table5 counts changed at {r['source_record_id']}: {actual}")
    finally:
        doc.close()


def replay_kush_partition() -> dict[str, Any]:
    path = PINS["kush_parts"][0]
    wb = xlrd.open_workbook(str(path), on_demand=True)
    try:
        sh = wb.sheet_by_name("11")
        parts = []
        for rownum, name, value in ((1276, "станица Кущевская (часть 1)", 22680),
                                    (1332, "станица Кущевская (часть 2)", 6853)):
            vals = sh.row_values(rownum - 1)
            need(str(vals[1]).strip() == name and int(vals[2]) == value,
                 f"Kushchevskaya partition source row changed at sheet 11 row {rownum}")
            parts.append({"source_record_id": f"2002:{path.name}:11:{rownum}", "source_year": 2002,
                          "source_sheet": "11", "source_row": rownum, "source_label_raw": vals[1],
                          "population_value": value, "source_path": str(path), "source_sha256": PINS["kush_parts"][1]})
        need(sum(p["population_value"] for p in parts) == 29533, "Kushchevskaya partition projection no longer equals official whole")
        return {"policy_id": "kushchevskaya_2002_exclusive_partition_projection_v1",
                "parent_source_record_id": "ROSSTAT2002:T4:01-04:r4338", "parent_population_value": 29533,
                "parent_population_role": "official_whole_place_count_used_once",
                "child_parts": parts, "child_parts_counted_in_addition_to_parent": False,
                "child_parts_identity_merged": False,
                "projection_relation": "exclusive same-census parts sum to the official whole; parts are not additional settlement counts"}
    finally:
        wb.release_resources()


def typed(df: pd.DataFrame, ints: tuple[str, ...], bools: tuple[str, ...], floats: tuple[str, ...] = ()) -> pd.DataFrame:
    out = df.copy()
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


def build_layer() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    edge_rows = read_csv(PINS["edge_rows"][0])
    replay = read_csv(PINS["source_row_replay"][0])
    mappings = read_csv(PINS["mapping_rows"][0])
    point_ctx = read_csv(PINS["point_context"][0])
    need(len(edge_rows) == 7 and len(replay) == 7 and len(mappings) == 7 and len(point_ctx) == 4,
         "reviewed vectors changed from expected 7/7/7/4 rows")
    need(set(edge_rows.review_status) == {"independently_supported_scoped_source_continuity_candidate"},
         "edge review statuses are mixed or unsupported")
    need(not edge_rows.historical_coordinate_measurement_claimed.str.lower().eq("true").any() and
         not edge_rows.population_boundary_comparability.str.lower().eq("true").any(),
         "review packet makes an out-of-scope coordinate or boundary claim")
    need(set(r for r in replay.source_record_id) == set(edge_rows.from_source_record_id) |
         set(mappings.candidate_from_id), "official source replay row universe differs from mapping packet")
    replay_official_rows(replay)
    partition = replay_kush_partition()

    # Selected 2021 source rows, accepted point origins, and stable graph7 entity IDs.
    ids = list(CURRENT_IDS.values())
    con = __import__("duckdb").connect(":memory:")
    con.execute("SET memory_limit='512MB'")
    con.execute("SET threads=1")
    selected = con.execute("SELECT census_year,source_record_id,settlement_name,settlement_type,region_raw,population,source_native_id FROM read_parquet(?) WHERE census_year=2021 AND source_record_id IN (SELECT unnest(?))", [str(PINS["selected"][0]), ids]).fetchdf()
    base = con.execute("SELECT observation_year,record_type,source_record_id,entity_id,settlement_name,settlement_type,region_raw,population_value,source_native_id FROM read_parquet(?) WHERE record_type='census' AND observation_year=2021 AND source_record_id IN (SELECT unnest(?))", [str(PINS["base_long"][0]), ids]).fetchdf()
    point = con.execute("SELECT target_source_record_id,target_year,latitude,longitude,coordinate_source,coordinate_provider,coordinate_provider_id,coordinate_provenance,coordinate_admission_status,point_origin_file,point_origin_sha256,point_origin_locator,point_origin_kind FROM read_parquet(?) WHERE regexp_replace(target_year,'\\.0$','')='2021' AND target_source_record_id IN (SELECT unnest(?))", [str(PINS["point_ledger"][0]), ids]).fetchdf()
    con.close()
    need(len(selected) == len(base) == len(point) == 4, "current 2021 selected/base/point carrier map is incomplete")
    sel = selected.set_index("source_record_id", drop=False)
    bmap = base.set_index("source_record_id", drop=False)
    pmap = point.set_index("target_source_record_id", drop=False)
    reviewed_point = point_ctx.set_index("target_source_record_id", drop=False)
    for place, sid in CURRENT_IDS.items():
        need(sid in sel.index and sid in bmap.index and sid in pmap.index and sid in reviewed_point.index,
             f"current target missing for {place}")
        s, b, p, c = sel.loc[sid], bmap.loc[sid], pmap.loc[sid], reviewed_point.loc[sid]
        need(str(s.settlement_name) == place == str(b.settlement_name) == str(c.place), f"current target name mismatch for {place}")
        need(str(b.entity_id).startswith("settlement:"), f"missing current carrier entity ID for {place}")
        need(math.isclose(float(p.latitude), float(c.latitude), abs_tol=1e-10) and
             math.isclose(float(p.longitude), float(c.longitude), abs_tol=1e-10),
             f"accepted point coordinates differ from independent reviewed context for {place}")
        for field in ("point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind"):
            need(str(getattr(p, field)) == str(c[field]), f"accepted point origin {field} differs for {place}")
        origin = Path(str(p.point_origin_file))
        need(origin.is_file() and sha256(origin) == str(p.point_origin_sha256), f"accepted point origin hash does not replay for {place}")
        need(str(p.coordinate_admission_status) in {"reviewed_rule_accepted", "reviewed_extension_rule_accepted"},
             f"point not accepted for {place}")

    replay_map = replay.set_index("source_record_id", drop=False)
    obs_rows: list[dict[str, Any]] = []
    for source_id in sorted(EXPECTED_NEW_OBSERVATIONS):
        r = replay_map.loc[source_id]
        place = str(r.place)
        current_id = CURRENT_IDS[place]
        s, b, p = sel.loc[current_id], bmap.loc[current_id], pmap.loc[current_id]
        year = int(r.year)
        label = str(r.literal_label)
        population, male, female = (int(r[x]) for x in ("population", "men", "women"))
        need(male + female == population, f"official sex totals do not sum at {source_id}")
        obs_rows.append({
            "observation_id": f"official_primary:{source_id}", "record_type": "census",
            "record_layer": "root_approved_official_primary_source_assertion",
            "source_record_id": source_id, "source_publication_row_id": source_id,
            "entity_id": str(b.entity_id), "associated_census_entity_id": str(b.entity_id),
            "current_place_entity_id": str(b.entity_id), "current_2021_source_record_id": current_id,
            "current_2021_source_native_id": str(s.source_native_id), "current_2021_population_context": int(s.population),
            "settlement_name": place, "source_name_raw": label,
            "source_type_raw": SOURCE_TYPE_RAW[(place, year)],
            "settlement_type": {"Кущевская": "станица", "Власиха": "пгт", "Калининец": "п." if year == 2002 else "пгт", "Трудовое": "поселок"}[place],
            "region_raw": str(s.region_raw), "observation_year": year,
            "observation_date": None, "observation_date_precision": "census_year_only_exact_date_unknown",
            "reference_date_basis": "official_Rosstat_census_table_year", "actual_census_date_claimed": False,
            "population_value": population, "population_raw": str(r.population),
            "population_male": male, "population_male_raw": str(r.men),
            "population_female": female, "population_female_raw": str(r.women),
            "population_unit": "persons", "population_value_quality": "official_Rosstat_T4_T5_literal_row_replayed",
            "population_quality_status": "official_primary_source_assertion; alternate selected values retained separately",
            "selected_as_canonical_source_value": False,
            "source_sheet": "01-04" if year == 2002 else None,
            "source_page": int(re.search(r"pdf_page=(\d+)", str(r.raw_check)).group(1)) if year == 2010 else None,
            "source_row": int(re.search(r"row=(\d+)", str(r.raw_check)).group(1)) if year == 2002 else None,
            "source_path": str(PINS["official_2002"][0] if year == 2002 else PINS["official_2010"][0]),
            "source_sha256": str(r.source_file_sha256), "source_raw_locator": str(r.raw_check),
            "source_review_receipt_sha256": PINS["edge_receipt"][1],
            "source_item_title": "Rosstat official Table 4 (2002) / Table 5 (2010)",
            "primary_source_preference_status": "root_approved_primary_source_assertion; no selected-frame mutation",
            "alternate_selected_population_preserved": True,
            "alternate_source_relation": "same census year, same scoped physical place; distinct source assertion, not a new settlement",
            "source_mapping_status": "see same_census_source_mappings layer",
            "latitude": float(p.latitude), "longitude": float(p.longitude),
            "coordinate_quality": "accepted_current_2021_representative_point_context_only",
            "coordinate_admission_status": str(p.coordinate_admission_status),
            "coordinate_temporal_basis": "modern_2021_representative_point_used_for_scoped_physical_continuity; historical measurement date unknown",
            "coordinate_measurement_date_unknown": True, "direct_historical_coordinate_measurement": False,
            "coordinate_source": str(p.coordinate_source), "coordinate_provider": str(p.coordinate_provider),
            "coordinate_provider_id_context_only": str(p.coordinate_provider_id),
            "coordinate_provenance": str(p.coordinate_provenance),
            "coordinate_carrier_target_source_record_id": current_id,
            "point_origin_file": str(p.point_origin_file), "point_origin_sha256": str(p.point_origin_sha256),
            "point_origin_locator": str(p.point_origin_locator), "point_origin_kind": str(p.point_origin_kind),
            "historical_provider_binding_asserted": False, "historical_coordinate_asserted": False,
            "qid_context": str(edge_rows.loc[edge_rows.place.eq(place), "current_QID_context"].iloc[0]),
            "qid_native_identifier_binding_asserted": False,
            "native_historical_OKATO_binding_asserted": False, "native_historical_OKTMO_binding_asserted": False,
            "population_scope": "one official Rosstat locality row; historic administrative boundary comparability unknown",
            "population_boundary_comparability_to_2021": False,
            "population_scope_comparability_asserted": False,
            "boundary_comparability_asserted": False,
            "legal_status_effective_date": None, "legal_status_date_claimed": False,
            "identity_admission_status": "root_approved_scoped_physical_continuity",
            "strict_national_2002_2010_2021_chain_claimed": False,
            "review_status": "independent_source_row_reviewed_and_root_approved",
            "root_decision_reference": "2026-10-04 root approval of five official primary assertions, seven scoped continuity links and same-census mapping/projection rules",
        })
    obs = pd.DataFrame(obs_rows)
    need(len(obs) == 5 and set(obs.source_record_id) == EXPECTED_NEW_OBSERVATIONS, "official observation vector mismatch")

    links = edge_rows.copy()
    links["independent_review_packet_status"] = links["admission_status"]
    links["edge_id"] = [f"official-primary-continuity:{i+1:02d}" for i in range(len(links))]
    links["relation"] = "scoped_same_named_physical_place_continuity"
    links["admission_status"] = "root_approved_scoped_physical_continuity_for_integration"
    links["decision_status"] = "root_approved_scoped_physical_continuity"
    links["review_status"] = "independent_review_complete_and_root_approved"
    links["legal_effective_date"] = None
    links["legal_effective_date_status"] = "unknown_not_asserted"
    links["population_boundary_comparability_asserted"] = False
    links["historical_coordinate_asserted"] = False
    links["historical_provider_binding_asserted"] = False
    links["qid_binding_asserted"] = False
    links["canonical_selected_graph_mutated"] = False
    links["strict_national_chain_claimed"] = False
    links["root_decision_reference"] = "2026-10-04 root approval of seven scoped physical continuity links"
    need(len(links) == 7 and links.independent_review_packet_status.eq("candidate only; not applied").all(),
         "reviewed link vector no longer matches original candidate-only bytes")

    mappings["mapping_id"] = [f"same-census-source-map:{i+1:02d}" for i in range(len(mappings))]
    mappings["application_status"] = "root_approved_scoped_source_mapping"
    mappings["identity_merge_performed"] = False
    mappings["population_replacement_performed"] = False
    mappings["graph_mutation_performed"] = False
    mappings["root_decision_reference"] = "2026-10-04 root approval of exact source aliases and same-census alternatives"
    need(len(mappings) == 7 and not mappings.source_relation_type.str.contains("partition", case=False).any(),
         "same-census mapping vector changed")

    points = point_ctx.copy()
    points["point_use_id"] = [f"current-point-context:{i+1:02d}" for i in range(len(points))]
    points["target_year"] = 2021
    points["point_use_status"] = "accepted_modern_representative_point_context_for_scoped_physical_continuity"
    points["historical_measurement_claimed"] = False
    points["historical_provider_binding_asserted"] = False
    points["boundary_comparability_asserted"] = False
    points["root_decision_reference"] = "2026-10-04 root approval of four actual accepted current point uses"
    projection = pd.DataFrame([{
        "policy_id": partition["policy_id"], "parent_source_record_id": partition["parent_source_record_id"],
        "parent_population_value": partition["parent_population_value"], "child_source_record_id": child["source_record_id"],
        "child_population_value": child["population_value"], "child_source_label_raw": child["source_label_raw"],
        "source_year": child["source_year"], "source_sheet": child["source_sheet"], "source_row": child["source_row"],
        "child_counted_in_addition_to_parent": False, "child_identity_merged": False,
        "projection_relation": partition["projection_relation"],
    } for child in partition["child_parts"]])
    return (typed(obs, ("observation_year", "population_value", "population_male", "population_female", "current_2021_population_context", "source_row", "source_page"), ("actual_census_date_claimed", "selected_as_canonical_source_value", "alternate_selected_population_preserved", "coordinate_measurement_date_unknown", "direct_historical_coordinate_measurement", "historical_provider_binding_asserted", "historical_coordinate_asserted", "qid_native_identifier_binding_asserted", "native_historical_OKATO_binding_asserted", "native_historical_OKTMO_binding_asserted", "population_boundary_comparability_to_2021", "population_scope_comparability_asserted", "boundary_comparability_asserted", "legal_status_date_claimed", "strict_national_2002_2010_2021_chain_claimed"), ("latitude", "longitude")),
            typed(links, ("from_year", "to_year"), ("population_boundary_comparability_asserted", "historical_coordinate_asserted", "historical_provider_binding_asserted", "qid_binding_asserted", "canonical_selected_graph_mutated", "strict_national_chain_claimed")),
            typed(mappings, ("candidate_from_year", "candidate_to_year"), ("identity_merge_performed", "population_replacement_performed", "graph_mutation_performed")),
            typed(points, ("target_year",), ("measurement_date_unknown", "boundary_comparability_asserted", "historical_measurement_claimed", "historical_provider_binding_asserted"), ("latitude", "longitude")),
            typed(projection, ("parent_population_value", "child_population_value", "source_year", "source_row"), ("child_counted_in_addition_to_parent", "child_identity_merged")), partition)


def write_layer(out: Path, input_manifest: dict[str, Any], input_hashes: dict[str, str], layer: tuple[pd.DataFrame, ...], partition: dict[str, Any]) -> dict[str, Any]:
    need(not out.exists(), f"refusing to overwrite existing output directory: {out}")
    out.mkdir(parents=True)
    names = ("official_primary_observations", "scoped_continuity_links", "same_census_source_mappings", "accepted_current_point_uses", "same_census_projection_policy")
    pins: dict[str, Any] = {}
    for name, frame in zip(names, layer):
        for ext in ("csv", "parquet"):
            path = out / f"{name}.{ext}"
            if ext == "csv":
                frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
            else:
                frame.to_parquet(path, index=False)
            pins[f"{name}_{ext}"] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size, "rows": len(frame)}
    manifest_path = out / "application_input_manifest.json"
    manifest_path.write_text(json.dumps(input_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pins["application_input_manifest"] = {"path": str(manifest_path), "sha256": sha256(manifest_path), "bytes": manifest_path.stat().st_size}
    policy_path = out / "kushchevskaya_partition_projection.json"
    policy_path.write_text(json.dumps(partition, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pins["kushchevskaya_partition_projection_json"] = {"path": str(policy_path), "sha256": sha256(policy_path), "bytes": policy_path.stat().st_size}
    receipt = {
        "status": "root_approved_official_primary_source_assertion_layer_staged_for_integration",
        "root_decision_reference": "2026-10-04 root approval: five official primary source assertions, seven scoped physical continuity links, seven same-census mappings and one exclusive partition projection",
        "official_primary_observation_rows": len(layer[0]), "scoped_continuity_link_rows": len(layer[1]),
        "same_census_mapping_rows": len(layer[2]), "accepted_current_point_use_rows": len(layer[3]),
        "partition_policy_rows": len(layer[4]),
        "official_population_values": {str(r.source_record_id): int(r.population_value) for r in layer[0].itertuples(index=False)},
        "hypothetical_2010_primary_display": {
            "official_values": {"Власиха": 26359, "Калининец": 21774, "Трудовое": 18522},
            "preserved_protected_alternate_values": {"Власиха": 25394, "Калининец": 16336, "Трудовое": 18495},
            "official_sum": 66655, "protected_alternate_sum": 60225,
            "hypothetical_display_delta": 6430,
            "selection_applied": False,
        },
        "source_counts_replaced_or_changed": False, "selected_population_frame_mutated": False,
        "accepted_graph_mutated": False, "long_table_appended": False,
        "historical_provider_binding_asserted": False, "historical_coordinates_asserted": False,
        "boundary_comparability_asserted": False, "strict_full_chain_gain_claimed": False,
        "kalinin_current_qid_P764_P721_mismatch_used": False,
        "kalinin_QID_binding_status": "unresolved; current QID context only",
        "vlasikha_moscow_2002_observation_created": False,
        "kushchevskaya_part_rows_counted_in_addition_to_official_whole": False,
        "source_row_aliases_counted_as_new_observations": 0,
        "input_manifest_sha256": sha256(manifest_path), "input_hashes": input_hashes,
        "outputs": pins,
        "limitations": "Official source observations preserve publication values and alternatives. Physical continuity links are scoped; legal status dates and historic boundary comparability remain unknown. Current accepted points are modern context only.",
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
    input_hashes = verify_inputs()
    layer = build_layer()
    summary = {"status": "validated_root_approved_official_primary_layer_not_appended", "official_primary_observation_rows": len(layer[0]),
               "scoped_continuity_link_rows": len(layer[1]), "same_census_mapping_rows": len(layer[2]),
               "accepted_current_point_use_rows": len(layer[3]), "partition_policy_rows": len(layer[4]),
               "official_population_sum_not_a_trajectory_metric": int(layer[0].population_value.sum()),
               "strict_full_chain_gain_claimed": False, "selected_population_graph_or_long_mutated": False}
    if args.write_staged:
        application_manifest = {"status": "frozen_application_inputs", "inputs": {
            name: {"path": str(path), "sha256": expected} for name, (path, expected) in PINS.items()},
            "official_assertion_rows": sorted(EXPECTED_NEW_OBSERVATIONS),
            "current_carriers": CURRENT_IDS,
            "producer_code": {"path": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve())},
            "producer_tests": {"path": str(Path(__file__).parent / "tests/test_stage_large_current4_official_primary.py"),
                               "sha256": sha256(Path(__file__).parent / "tests/test_stage_large_current4_official_primary.py")},
            "note": "No selected population, canonical graph, or long-table mutation is part of this staging utility."}
        receipt = write_layer(args.out_dir, application_manifest, input_hashes, layer, layer[5])
        summary["output_dir"] = str(args.out_dir)
        summary["application_receipt_sha256"] = receipt["receipt_file_sha256"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
