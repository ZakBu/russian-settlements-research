#!/usr/bin/env python3
"""Export observed OKTMO snapshots without asserting identifier validity intervals.

The 2021 codes are exact lexical strings from selected 2021 population records. Raw
GeoKLADR-2011 codes, when carried in an accepted point ledger, are separate origin-place
context observations and are never interpreted as changes to a 2021 census identifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

ACCEPTED_POINT_STATUSES = {
    "reviewed_rule_accepted",
    "frozen_r5b_reviewed_baseline_preserved",
    "reviewed_extension_rule_accepted",
    "reviewed_case_accepted",
}
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "mass_joint_20261004.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _parse_point_target_year(value: Any, source_id: str) -> int:
    """Parse an integral census year without truncating fractional values."""
    raw = str(value).strip()
    match = re.fullmatch(r"(\d{4})(?:\.0+)?", raw)
    if not match:
        raise ValueError(f"accepted point target_year is not a finite integral year for {source_id}: {value!r}")
    year = int(match.group(1))
    if not 1800 <= year <= 2200:
        raise ValueError(f"accepted point target_year is outside the supported year domain for {source_id}: {value!r}")
    return year


def raw_string(value: Any, field: str) -> str | None:
    """Return an exact lexical source string, refusing numeric coercion/padding."""
    if _missing(value):
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a raw string to preserve lexical form; got {type(value).__name__}")
    return value


def code_role_2021(raw_code: str | None, population_scope: str | None) -> str:
    """Classify only the observed code's lexical form and explicit scope."""
    raw_code = raw_string(raw_code, "2021 native OKTMO")
    if raw_code is None:
        return "missing_native_OKTMO"
    if re.fullmatch(r"\d{11}", raw_code):
        return "lexical_length_11_NP_code"
    if re.fullmatch(r"\d{8}", raw_code):
        scope = (population_scope or "").casefold().replace("_", " ").replace("-", " ")
        explicit_federal_territory = any(marker in scope for marker in (
            "federal city", "federal territory", "city of federal significance",
            "федеральный город", "город федерального значения", "федеральная территория",
            "территория федерального города", "территория города федерального значения",
        ))
        if explicit_federal_territory:
            return "lexical_length_8_federal_territory_code_scope_explicit"
        return "format_unverified_length_8_scope_not_explicitly_federal"
    return "format_unverified_raw_literal_preserved"


def code_role_geo2011(raw_code: str | None) -> str:
    raw_code = raw_string(raw_code, "raw_geo_oktmo_2011")
    if raw_code is None:
        return "missing_raw_geo_2011_OKTMO"
    if re.fullmatch(r"\d{8}", raw_code):
        return "municipal_context_of_origin_place_length_8"
    return "format_unverified_raw_geo_2011_OKTMO_context"


def recover_geokladr_origin_rows(point_rows: pd.DataFrame, dbf_path: str | Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Replay exact pinned DBF record locators for accepted point origins.

    The result is contextual source data only. A recovered 2011 code is not a
    native-ID binding, a validity interval, or a claim that the point is correct.
    """
    path = Path(dbf_path).resolve()
    payload = path.read_bytes()
    file_sha = hashlib.sha256(payload).hexdigest()
    if not {"point_origin_file", "point_origin_sha256", "point_origin_locator"}.issubset(point_rows.columns):
        return {}
    locators: dict[str, tuple[int, int]] = {}
    loc_re = re.compile(r"(?:raw_dbf_record_number_1based|dbf_record_1based|record_number_1based)=(\d+);(?:byte_offset_0based|byte_offset|DBF_byte_offset_0based)=(\d+)(?:;(.*))?", re.IGNORECASE)
    resolved_path = str(path)
    for row in point_rows[["point_origin_file", "point_origin_sha256", "point_origin_locator"]].itertuples(index=False, name=None):
        raw_path, raw_sha, raw_locator = row
        if _missing(raw_path) or _missing(raw_sha) or _missing(raw_locator):
            continue
        try:
            same_path = Path(str(raw_path)).resolve() == path
        except (OSError, RuntimeError):
            same_path = False
        if not same_path or str(raw_sha) != file_sha:
            continue
        locator = str(raw_locator)
        match = loc_re.fullmatch(locator.strip())
        if not match:
            continue
        record_number, byte_offset = int(match.group(1)), int(match.group(2))
        locator_suffix = match.group(3) or ""
        code_match = re.search(r"(?:^|;)(?:OKATO2011_raw|OKATO)=(\d+)(?:;|$)", locator_suffix, re.IGNORECASE)
        locator_okato = code_match.group(1) if code_match else None
        locators[locator] = (record_number, byte_offset, locator_okato)
    if not locators:
        return {}

    if len(payload) < 32:
        raise ValueError(f"Pinned DBF is shorter than a header: {path}")
    record_count = struct.unpack_from("<I", payload, 4)[0]
    header_len, record_len = struct.unpack_from("<HH", payload, 8)
    fields: list[tuple[str, str, int, int]] = []
    pos = 32
    while pos < header_len and payload[pos] != 0x0D:
        name = payload[pos:pos + 11].split(b"\0", 1)[0].decode("ascii", "replace").strip()
        kind = chr(payload[pos + 11])
        width = payload[pos + 16]
        fields.append((name, kind, width, pos))
        pos += 32
    wanted = {"TER", "KOD1", "KOD2", "KOD3", "OKTMO", "DATA_UPD", "SCOKATO", "TYPE_NP", "NAME1", "STATUS", "LAT", "LONG", "KLADRCODE"}
    field_offsets: dict[str, tuple[int, int]] = {}
    offset_in_record = 1
    for name, _kind, width, _descriptor_pos in fields:
        if name in wanted:
            field_offsets[name] = (offset_in_record, width)
        offset_in_record += width
    requested_by_number: dict[int, list[tuple[str, int, str | None]]] = {}
    for locator, (number, byte_offset, locator_okato) in locators.items():
        requested_by_number.setdefault(number, []).append((locator, byte_offset, locator_okato))
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for number, locator_offsets in requested_by_number.items():
        if number < 1 or number > record_count:
            continue
        record = payload[header_len + (number - 1) * record_len:header_len + number * record_len]
        if len(record) != record_len or record[:1] == b"*":
            continue
        for locator, byte_offset, locator_okato in locator_offsets:
            expected_offset = header_len + (number - 1) * record_len
            if byte_offset != expected_offset:
                continue
            raw_fields = {}
            for name, (field_pos, width) in field_offsets.items():
                raw_fields[name] = record[field_pos:field_pos + width].decode("cp1251", "replace").strip() or None
            raw_okato_parts = [raw_fields.get(name) or "" for name in ("TER", "KOD1", "KOD2", "KOD3")]
            raw_okato = "".join(raw_okato_parts) or None
            if locator_okato is not None and raw_okato != locator_okato:
                continue
            raw_fields.update({
                "raw_geo_oktmo_2011": raw_fields.get("OKTMO"),
                "raw_geo_data_updated": raw_fields.get("DATA_UPD"),
                "raw_geo_okato_code": raw_okato,
                "raw_geo_record_number_1based": number,
                "raw_geo_byte_offset_0based": byte_offset,
                "raw_geo_origin_record_replay_status": "verified_exact_file_sha_and_dbf_record_offset",
                "raw_geo_origin_dbf_path": resolved_path,
                "raw_geo_origin_dbf_sha256": file_sha,
                "raw_geo_origin_locator": locator,
            })
            result[(resolved_path, file_sha, locator)] = raw_fields
    return result


def _source_version(snapshot_version: str) -> tuple[str, str | None]:
    raw = snapshot_version.strip()
    digits = raw[1:] if raw.startswith("v") else raw
    release_date = None
    if re.fullmatch(r"\d{8}", digits):
        release_date = f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return (raw if raw.startswith("v") else f"v{raw}", release_date)


def _year_column(columns: set[str]) -> str:
    for name in ("census_year", "observation_year", "year", "population_observation_year"):
        if name in columns:
            return name
    raise ValueError("Final core is missing a census-year column (census_year/year/population_observation_year)")


def _select_parquet(path: str | Path, required: list[str], optional: list[str] | None = None) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        available = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()}
        missing = set(required) - available
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
        cols = required + [x for x in (optional or []) if x in available and x not in required]
        projection = ",".join('"' + x.replace('"', '""') + '"' for x in cols)
        return con.execute(f"SELECT {projection} FROM read_parquet(?)", [str(path)]).df()
    finally:
        con.close()


def _core_entity_map(core: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    required = {"source_record_id", "entity_id"}
    if not required.issubset(core.columns):
        raise ValueError(f"Final core must contain {sorted(required)}")
    year_col = _year_column(set(core.columns))
    years = pd.to_numeric(core[year_col], errors="coerce")
    core = core.assign(_year=years)
    core = core[core._year.notna()].copy()
    # Final long cores also contain annual/Wikidata rows. Only census observations
    # define the source-record→settlement component map used by this export.
    if "record_type" in core.columns:
        core = core[core.record_type.astype(str).eq("census")].copy()
    source_entity: dict[str, str] = {}
    source_year: dict[str, str] = {}
    for _, row in core.iterrows():
        source_id = raw_string(row["source_record_id"], "source_record_id")
        entity_id = raw_string(row["entity_id"], "entity_id")
        year_value = str(int(row["_year"]))
        if not source_id or not entity_id:
            raise ValueError("Final core contains an empty source_record_id or entity_id")
        if source_id in source_entity and source_entity[source_id] != entity_id:
            raise ValueError(f"source_record_id maps to multiple final entities: {source_id}")
        source_entity[source_id] = entity_id
        source_year[source_id] = year_value
    return source_entity, source_year


def build_snapshot_rows(
    final_core: pd.DataFrame,
    population_rows: pd.DataFrame,
    point_rows: pd.DataFrame,
    *,
    snapshot_version: str = "v20251217",
    population_layer_sha256: str,
    accepted_points_sha256: str,
    final_core_sha256: str,
    origin_dbf_rows: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (2021 native-code rows, 2011 context rows, point context holds)."""
    entity_by_source, year_by_source = _core_entity_map(final_core)
    version, release_date = _source_version(snapshot_version)

    pop_required = {"source_record_id", "census_year", "oktmo", "source_native_id", "population", "source_file", "source_sheet", "source_row", "population_scope"}
    if not pop_required.issubset(population_rows.columns):
        raise ValueError(f"Population rows missing columns: {sorted(pop_required - set(population_rows.columns))}")
    pop = population_rows[pd.to_numeric(population_rows.census_year, errors="coerce").eq(2021)].copy()
    pop = pop[pop.source_record_id.astype(str).isin(entity_by_source)]
    if pop.source_record_id.astype(str).duplicated().any():
        raise ValueError("2021 population layer has duplicate source_record_id rows")
    if "source_sha256" in population_rows:
        hash_map = dict(zip(population_rows.source_record_id.astype(str), population_rows.source_sha256))
    else:
        hash_map = {}
    locator_map = dict(zip(population_rows.source_record_id.astype(str), population_rows.source_locator)) if "source_locator" in population_rows else {}

    native_records: list[dict[str, Any]] = []
    for row in pop.itertuples(index=False):
        source_id = str(row.source_record_id)
        # `oktmo` is the explicit native identifier field. Preserve it byte-for-byte as text.
        raw_code = raw_string(row.oktmo, "oktmo")
        native_id_raw = raw_string(row.source_native_id, "source_native_id")
        raw_file = raw_string(row.source_file, "source_file")
        raw_scope = raw_string(row.population_scope, "population_scope")
        raw_hash = raw_string(hash_map.get(source_id), "source_sha256")
        record_locator = raw_string(locator_map.get(source_id), "source_locator")
        if record_locator is None:
            record_locator = f"{raw_file}#{row.source_sheet}:row={row.source_row};source_record_id={source_id}"
        native_records.append({
            "entity_id": entity_by_source[source_id],
            "source_record_id": source_id,
            "identifier_namespace": "OKTMO",
            "identifier_raw": raw_code,
            "identifier_role": code_role_2021(raw_code, raw_scope),
            "identifier_binding_status": "native literal observed in selected 2021 population row; code validity not asserted",
            "identifier_observation_year": 2021,
            "linked_population_observation_year": 2021,
            "population_value": row.population,
            "population_scope": raw_scope,
            "source_native_id_raw": native_id_raw,
            "oktmo_vs_source_native_id_conflict": bool(raw_code is not None and native_id_raw is not None and raw_code != native_id_raw),
            "source_file": raw_file,
            "source_sheet": raw_string(row.source_sheet, "source_sheet"),
            "source_row": row.source_row,
            "source_locator": record_locator,
            "source_asset_sha256": raw_hash or population_layer_sha256,
            "source_asset_hash_basis": "source row source_sha256" if raw_hash else "selected population layer SHA-256; row-level source file hash unavailable",
            "population_layer_path": str(population_rows.attrs.get("source_path", "")) or None,
            "population_layer_sha256": population_layer_sha256,
            "source_license_notice": "SOURCES.md records the Tochno 2021 source as CC BY 4.0; preserve attribution and source version; this does not license merged source material.",
            "identifier_source_version": version,
            "identifier_source_release_date": None,
            "identifier_snapshot_version_date_token": release_date,
            "identifier_source_version_basis": "date-like token parsed from source version label only; not a verified publication/effective date or identifier validity date",
            "identifier_code_observed_date": None,
            "identifier_code_observed_date_basis": "not specified; observed only in this versioned source snapshot",
            "valid_from": None,
            "valid_to": None,
            "validity_status": "unknown_not_asserted",
            "point_snapshot_path": None,
            "point_snapshot_sha256": accepted_points_sha256,
            "final_core_path": str(final_core.attrs.get("source_path", "")) or None,
            "final_core_sha256": final_core_sha256,
            "entity_binding_basis": "final core source_record_id→entity_id mapping",
            "population_observation_locator": record_locator,
        })

    # Accepted point rows join to the final entity only through target_source_record_id.
    point_cols = set(point_rows.columns)
    needed = {"target_source_record_id", "target_year", "coordinate_admission_status"}
    if not needed.issubset(point_cols):
        raise ValueError(f"Accepted points missing columns: {sorted(needed - point_cols)}")
    all_statuses = set(point_rows.coordinate_admission_status.dropna().astype(str))
    unknown_statuses = all_statuses - ACCEPTED_POINT_STATUSES
    if point_rows.coordinate_admission_status.isna().any() or unknown_statuses:
        raise ValueError(f"accepted point input contains nonaccepted/unrecognized statuses: {sorted(unknown_statuses)}")
    accepted = point_rows.copy()
    accepted = accepted[accepted.target_source_record_id.astype(str).isin(entity_by_source)]
    if accepted.target_source_record_id.astype(str).duplicated().any():
        raise ValueError("Accepted point ledger has duplicate target_source_record_id rows")
    context_rows: list[dict[str, Any]] = []
    hold_rows: list[dict[str, Any]] = []
    for row in accepted.itertuples(index=False):
        source_id = str(row.target_source_record_id)
        authoritative_year = int(year_by_source[source_id])
        raw_point_target_year = getattr(row, "target_year", None)
        if raw_point_target_year is not None and not pd.isna(raw_point_target_year):
            point_target_year = _parse_point_target_year(raw_point_target_year, source_id)
            if point_target_year != authoritative_year:
                raise ValueError(
                    f"accepted point target_year disagrees with final-core census year for {source_id}: "
                    f"{point_target_year} != {authoritative_year}"
                )
        else:
            point_target_year = None
        raw_geo_code = raw_string(getattr(row, "raw_geo_oktmo_2011", None), "raw_geo_oktmo_2011") if "raw_geo_oktmo_2011" in point_cols else None
        raw_geo_okato = raw_string(getattr(row, "raw_geo_okato_code", None), "raw_geo_okato_code") if "raw_geo_okato_code" in point_cols else None
        data_updated = raw_string(getattr(row, "raw_geo_data_updated", None), "raw_geo_data_updated") if "raw_geo_data_updated" in point_cols else None
        origin_file = raw_string(getattr(row, "point_origin_file", None), "point_origin_file") if "point_origin_file" in point_cols else None
        origin_hash = raw_string(getattr(row, "point_origin_sha256", None), "point_origin_sha256") if "point_origin_sha256" in point_cols else None
        origin_locator = raw_string(getattr(row, "point_origin_locator", None), "point_origin_locator") if "point_origin_locator" in point_cols else None
        origin_record = None
        if origin_dbf_rows and origin_file and origin_hash and origin_locator:
            try:
                origin_key = (str(Path(origin_file).resolve()), origin_hash, origin_locator)
            except (OSError, RuntimeError):
                origin_key = (origin_file, origin_hash, origin_locator)
            origin_record = origin_dbf_rows.get(origin_key)
        if origin_record is not None:
            raw_geo_code = origin_record.get("raw_geo_oktmo_2011")
            raw_geo_okato = origin_record.get("raw_geo_okato_code")
            data_updated = origin_record.get("raw_geo_data_updated")
        if raw_geo_code is None and origin_record is None:
            hold_rows.append({
                "entity_id": entity_by_source[source_id],
                "target_source_record_id": source_id,
                "target_year": authoritative_year,
                "point_target_year_raw": point_target_year,
                "hold_reason": "accepted point row has no raw_geo_oktmo_2011 literal field/value; no code inferred",
                "point_origin_file": origin_file,
                "point_origin_sha256": origin_hash,
                "point_origin_locator": origin_locator,
                "source_version": "GeoKLADR 2011 field not observed",
            })
            continue
        role = code_role_geo2011(raw_geo_code)
        context_rows.append({
            "entity_id": entity_by_source[source_id],
            "target_source_record_id": source_id,
            "target_year": authoritative_year,
            "point_target_year_raw": point_target_year,
            "linked_population_observation_year": authoritative_year,
            "linked_point_target_source_record_ids_json": json.dumps([source_id], ensure_ascii=False),
            "linked_population_observation_years_json": json.dumps([authoritative_year]),
            "identifier_namespace": "OKTMO",
            "identifier_raw": raw_geo_code,
            "identifier_role": role,
            "identifier_binding_status": "accepted point origin contextual code; no native ID binding or code transition asserted",
            "source_version": "GeoKLADR 2011",
            "source_license_notice": "SOURCES.md says historical OKATO/GeoKLADR terms vary by source; no blanket redistribution license is inferred; preserve source-specific provenance and conditions.",
            "source_data_updated_raw": data_updated,
            "source_data_updated_basis": "raw GeoKLADR DATA_UPD field; retained literally and not treated as validity date",
            "raw_geo_record_replay_status": origin_record.get("raw_geo_origin_record_replay_status") if origin_record else "convenience_field_only_or_not_replayed",
            "raw_geo_record_number_1based": origin_record.get("raw_geo_record_number_1based") if origin_record else None,
            "raw_geo_byte_offset_0based": origin_record.get("raw_geo_byte_offset_0based") if origin_record else None,
            "raw_geo_origin_dbf_path": origin_record.get("raw_geo_origin_dbf_path") if origin_record else None,
            "raw_geo_origin_dbf_sha256": origin_record.get("raw_geo_origin_dbf_sha256") if origin_record else None,
            "raw_geo_origin_locator": origin_record.get("raw_geo_origin_locator") if origin_record else None,
            "raw_geo_ter_raw": origin_record.get("TER") if origin_record else None,
            "raw_geo_kod1_raw": origin_record.get("KOD1") if origin_record else None,
            "raw_geo_kod2_raw": origin_record.get("KOD2") if origin_record else None,
            "raw_geo_kod3_raw": origin_record.get("KOD3") if origin_record else None,
            "raw_geo_oktmo_2011_literal": raw_geo_code,
            "raw_geo_okato_2011_literal": raw_geo_okato,
            "raw_geo_name_raw": origin_record.get("NAME1") if origin_record else None,
            "raw_geo_type_scokato_raw": origin_record.get("SCOKATO") if origin_record else None,
            "raw_geo_type_np_raw_separate": origin_record.get("TYPE_NP") if origin_record else None,
            "raw_geo_status_raw": origin_record.get("STATUS") if origin_record else None,
            "raw_geo_kladr_code_raw": origin_record.get("KLADRCODE") if origin_record else None,
            "raw_geo_oktmo_empty_in_source": bool(origin_record is not None and raw_geo_code is None),
            "identifier_code_observed_date": None,
            "identifier_code_observed_date_basis": "source snapshot year is 2011; observation/validity date not established",
            "valid_from": None,
            "valid_to": None,
            "validity_status": "unknown_not_asserted",
            "related_okato_raw": raw_geo_okato,
            "point_origin_file": origin_file,
            "point_origin_sha256": origin_hash,
            "point_origin_locator": origin_locator,
            "point_origin_kind": raw_string(getattr(row, "point_origin_kind", None), "point_origin_kind") if "point_origin_kind" in point_cols else None,
            "point_record_admission_status": raw_string(row.coordinate_admission_status, "coordinate_admission_status"),
            "point_target_entity_join_basis": "accepted point target_source_record_id→final core entity_id; context only",
            "current_native_identifier_comparison": "not compared; 2011 municipal-context code is not a same-level 2021 native NP code",
            "accepted_point_ledger_path": str(point_rows.attrs.get("source_path", "")) or None,
            "accepted_point_ledger_sha256": accepted_points_sha256,
            "final_core_sha256": final_core_sha256,
        })

    native_df = pd.DataFrame(native_records)
    if not native_df.empty and native_df.duplicated(["entity_id", "identifier_observation_year"]).any():
        raise ValueError("final core maps multiple 2021 native code rows to one entity")
    context_df = pd.DataFrame(context_rows)
    holds_df = pd.DataFrame(hold_rows)
    # Deduplicate only when both origin-hash and locator evidence are present;
    # incomplete provenance must not collapse independent observations.
    if not context_df.empty:
        complete_origin = context_df.point_origin_sha256.notna() & context_df.point_origin_locator.notna()
        key = ["entity_id", "identifier_raw", "point_origin_sha256", "point_origin_locator"]
        complete_input = context_df[complete_origin].copy()
        if not complete_input.empty:
            grouped = []
            for _, group in complete_input.groupby(key, sort=True, dropna=False):
                first = group.iloc[0].to_dict()
                first["linked_point_target_source_record_ids_json"] = json.dumps(sorted(set(
                    target for value in group.linked_point_target_source_record_ids_json for target in json.loads(value))), ensure_ascii=False)
                first["linked_population_observation_years_json"] = json.dumps(sorted(set(
                    year for value in group.linked_population_observation_years_json for year in json.loads(value))), ensure_ascii=False)
                grouped.append(first)
            complete = pd.DataFrame(grouped)
        else:
            complete = complete_input
        incomplete = context_df[~complete_origin]
        context_df = pd.concat([complete, incomplete], ignore_index=True).sort_values(
            ["entity_id", "target_source_record_id"], kind="stable").reset_index(drop=True)
    return native_df, context_df, holds_df


def load_inputs(final_core_path: str | Path, population_layer_path: str | Path, accepted_points_path: str | Path):
    # Narrow projections keep this export independent of large classifier/source-evidence fields.
    core_raw = _select_parquet(final_core_path, ["entity_id", "source_record_id"], ["census_year", "observation_year", "year", "population_observation_year", "record_type"])
    core_raw.attrs["source_path"] = str(final_core_path)
    core = core_raw
    year_col = _year_column(set(core.columns))
    if "census_year" not in core and year_col != "census_year":
        core["census_year"] = core[year_col]
    pop_cols = ["source_record_id", "census_year", "oktmo", "source_native_id", "population", "source_file", "source_sheet", "source_row", "population_scope"]
    pop_optional = ["source_sha256", "source_locator", "source_path"]
    pop = _select_parquet(population_layer_path, pop_cols, pop_optional)
    pop.attrs["source_path"] = str(population_layer_path)
    point_cols = ["target_source_record_id", "target_year", "coordinate_admission_status"]
    point_optional = ["raw_geo_oktmo_2011", "raw_geo_data_updated", "raw_geo_okato_code", "point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind"]
    points = _select_parquet(accepted_points_path, point_cols, point_optional)
    points.attrs["source_path"] = str(accepted_points_path)
    return core, pop, points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-core", required=True, help="Final core table with entity_id/source_record_id/year")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--accepted-points", type=Path, help="Override configured accepted point ledger")
    parser.add_argument("--population-layer", type=Path, help="Override configured selected population layer")
    parser.add_argument("--snapshot-version", default="v20251217")
    parser.add_argument("--raw-geo-2011-dbf", type=Path, help="Pinned GeoKLADR okato.dbf used to replay exact accepted point-origin record locators")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    points_path = args.accepted_points or Path(config["working_point_uses"])
    population_path = args.population_layer or Path(config["working_population_layer"])
    final_core_path = Path(args.final_core)
    if not final_core_path.exists():
        parser.error(f"final core does not exist yet; export not run: {final_core_path}")
    for path in (args.config, points_path, population_path):
        if not Path(path).exists():
            parser.error(f"input path does not exist: {path}")
    core, population, points = load_inputs(final_core_path, population_path, points_path)
    core_sha, points_sha, population_sha = sha256_file(final_core_path), sha256_file(points_path), sha256_file(population_path)
    config_expected_point_sha = config.get("working_point_uses_sha256")
    if config_expected_point_sha and points_sha != config_expected_point_sha:
        parser.error(f"configured accepted point ledger hash mismatch: expected {config_expected_point_sha}, got {points_sha}")
    origin_dbf_rows = recover_geokladr_origin_rows(points, args.raw_geo_2011_dbf) if args.raw_geo_2011_dbf else None
    native, context, holds = build_snapshot_rows(
        core, population, points,
        snapshot_version=args.snapshot_version,
        population_layer_sha256=population_sha,
        accepted_points_sha256=points_sha,
        final_core_sha256=core_sha,
        origin_dbf_rows=origin_dbf_rows,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    native.to_parquet(args.output_dir / "2021_native_oktmo_snapshot.parquet", index=False)
    native.to_csv(args.output_dir / "2021_native_oktmo_snapshot.csv", index=False)
    context.to_parquet(args.output_dir / "geo_2011_point_origin_context.parquet", index=False)
    context.to_csv(args.output_dir / "geo_2011_point_origin_context.csv", index=False)
    holds.to_csv(args.output_dir / "geo_2011_point_origin_holds.csv", index=False)
    counts = {
        "native_2021_rows": len(native),
        "native_2021_distinct_entities": int(native.entity_id.nunique()) if not native.empty else 0,
        "native_2021_missing_code_rows": int(native.identifier_raw.isna().sum()) if not native.empty else 0,
        "native_2021_unverified_format_rows": int(native.identifier_role.str.startswith("format_unverified").sum()) if not native.empty else 0,
        "geo_2011_context_rows_after_provenance_dedup": len(context),
        "geo_2011_context_distinct_entities": int(context.entity_id.nunique()) if not context.empty else 0,
        "accepted_point_rows_without_raw_geo_2011_code": len(holds),
        "geo_2011_context_rows_with_missing_OKTMO_literal": int(context.identifier_raw.isna().sum()) if not context.empty else 0,
        "geo_2011_context_rows_recovered_from_pinned_origin_dbf": int(context.raw_geo_record_replay_status.eq("verified_exact_file_sha_and_dbf_record_offset").sum()) if not context.empty else 0,
        "code_validity_intervals_asserted": 0,
        "identifier_transitions_asserted": 0,
    }
    receipt = {
        "status": "observed_identifier_snapshot_export_complete",
        "interpretation": "Observed source snapshots only. 2021 native OKTMO literals are linked to 2021 population observations; source snapshot release/version does not establish code validity. GeoKLADR-2011 OKTMO values are a separate municipal-context observation attached through accepted point origin and target source record; they are not native-code bindings or identifier changes.",
        "inputs": {
            "final_core_path": str(final_core_path), "final_core_sha256": core_sha,
            "accepted_point_ledger_path": str(points_path), "accepted_point_ledger_sha256": points_sha,
            "population_layer_path": str(population_path), "population_layer_sha256": population_sha,
            "config_path": str(args.config), "config_sha256": sha256_file(args.config),
            "snapshot_version": args.snapshot_version,
            "raw_geo_2011_dbf_path": str(args.raw_geo_2011_dbf) if args.raw_geo_2011_dbf else None,
            "raw_geo_2011_dbf_sha256": sha256_file(args.raw_geo_2011_dbf) if args.raw_geo_2011_dbf else None,
            "accepted_point_statuses": sorted(ACCEPTED_POINT_STATUSES),
            "source_registry_path": str(Path(__file__).resolve().parents[2] / "SOURCES.md"),
            "source_registry_sha256": sha256_file(Path(__file__).resolve().parents[2] / "SOURCES.md"),
        },
        "counts": counts,
        "outputs": {
            name: sha256_file(args.output_dir / name)
            for name in ("2021_native_oktmo_snapshot.parquet", "2021_native_oktmo_snapshot.csv", "geo_2011_point_origin_context.parquet", "geo_2011_point_origin_context.csv", "geo_2011_point_origin_holds.csv")
        },
    }
    (args.output_dir / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
