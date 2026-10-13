"""Independent raw-file verification of the 2011 GeoKLADR/OKATO DBF snapshot.

The verifier reads DBF bytes directly and opens the preserved legacy DuckDB in
read-only mode. It makes no census observations or historical-boundary claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb


RAW_RELATIVE_PATH = "data/raw/historical_geography/geokladr_okato_2011/okato.dbf"
DBF_EXPECTED_SHA256 = "d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650"
DBF_EXPECTED_RECORDS = 151875
DBF_EXPECTED_HEADER_LENGTH = 705
DBF_EXPECTED_RECORD_LENGTH = 395
LEGACY_TABLE = "historical_geokladr_coordinates_2011"
LEGACY_DB_EXPECTED_SHA256 = "26a2fe5b2ce05119d919a196beb57cd655a49ffffb0ff8f194762aa78e6b5b64"

FIELD_SPECS = {
    "TER": ("C", 2), "KOD1": ("C", 3), "KOD2": ("C", 3), "KOD3": ("C", 3),
    "NAME1": ("C", 160), "SCOKATO": ("C", 25), "KLADRCODE": ("C", 13),
    "DATA_UPD": ("C", 10), "OKTMO": ("C", 8), "LONG": ("N", 16), "LAT": ("N", 16),
    "STATUS": ("N", 20), "POPULATION": ("N", 13),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest_sha256(manifest_path: Path, relative_path: str) -> str:
    path = str(Path(manifest_path).resolve(strict=True)).replace("'", "''")
    conn = duckdb.connect()
    try:
        row = conn.execute(
            f"SELECT sha256 FROM read_parquet('{path}') WHERE path = ? LIMIT 1", [relative_path]
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        raise ValueError(f"input manifest has no SHA-256 for {relative_path}")
    return str(row[0])


def parse_dbf_header(header: bytes) -> tuple[int, int, int, list[dict[str, Any]]]:
    if len(header) < 33:
        raise ValueError("DBF header is truncated")
    record_count = int.from_bytes(header[4:8], "little")
    header_length = int.from_bytes(header[8:10], "little")
    record_length = int.from_bytes(header[10:12], "little")
    fields: list[dict[str, Any]] = []
    offset = 1  # byte zero of each record is the deletion marker
    for pos in range(32, header_length, 32):
        if header[pos] == 0x0D:
            break
        if pos + 32 > len(header):
            raise ValueError("DBF field descriptor is truncated")
        descriptor = header[pos:pos + 32]
        name_bytes = descriptor[:11].split(b"\0", 1)[0]
        name = name_bytes.decode("ascii")
        field_type = chr(descriptor[11])
        width = descriptor[16]
        decimals = descriptor[17]
        fields.append({"name": name, "type": field_type, "width": width,
                       "decimals": decimals, "offset": offset})
        offset += width
    if offset != record_length:
        raise ValueError(f"DBF field widths total {offset}, record length is {record_length}")
    missing = set(FIELD_SPECS) - {f["name"] for f in fields}
    if missing:
        raise ValueError(f"DBF is missing expected fields: {sorted(missing)}")
    for field in fields:
        if field["name"] in FIELD_SPECS:
            expected_type, expected_width = FIELD_SPECS[field["name"]]
            if (field["type"], field["width"]) != (expected_type, expected_width):
                raise ValueError(f"unexpected DBF descriptor for {field['name']}: {field}")
    return record_count, header_length, record_length, fields


def _value(raw: bytes, field_type: str) -> Any:
    text = raw.decode("cp1251")
    stripped = text.strip()
    if not stripped:
        return None
    if field_type in {"N", "F"}:
        return float(stripped)
    return stripped


def parse_dbf_records(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source = Path(path).resolve(strict=True)
    with source.open("rb") as stream:
        header_prefix = stream.read(32)
        header_length = int.from_bytes(header_prefix[8:10], "little")
        stream.seek(0)
        header = stream.read(header_length)
        count, header_length, record_length, fields = parse_dbf_header(header)
        records: list[dict[str, Any]] = []
        for record_no in range(1, count + 1):
            byte_offset = header_length + (record_no - 1) * record_length
            stream.seek(byte_offset)
            raw_record = stream.read(record_length)
            if len(raw_record) != record_length:
                raise ValueError(f"truncated DBF record {record_no}")
            delete_byte = raw_record[0:1]
            if delete_byte not in {b" ", b"*"}:
                raise ValueError(f"invalid deletion marker {delete_byte!r} at record {record_no}")
            parsed: dict[str, Any] = {
                "record_number_1based": record_no,
                "record_byte_offset_0based": byte_offset,
                "deleted_marker_raw": delete_byte.decode("ascii"),
                "is_deleted": delete_byte == b"*",
            }
            for field in fields:
                name, field_type, width, offset = field["name"], field["type"], field["width"], field["offset"]
                raw = raw_record[offset:offset + width]
                if name in FIELD_SPECS:
                    raw_text = raw.decode("cp1251")
                    parsed[f"{name.lower()}_raw_text"] = raw_text
                    parsed[f"{name.lower()}_value"] = _value(raw, field_type)
                elif name == "KOD1" or name == "KOD2" or name == "KOD3" or name == "TER":
                    parsed[f"{name.lower()}_raw_text"] = raw.decode("cp1251")
                    parsed[f"{name.lower()}_value"] = _value(raw, field_type)
            parts = [parsed[f"{name.lower()}_value"] for name in ("TER", "KOD1", "KOD2", "KOD3")]
            parsed["historical_okato"] = "".join(str(part) for part in parts) if all(part is not None for part in parts) else None
            parsed["name_raw"] = parsed["name1_value"]
            parsed["settlement_type_raw"] = parsed["scokato_value"]
            parsed["kladr"] = parsed["kladrcode_value"]
            parsed["oktmo_2011_raw"] = parsed["oktmo_value"]
            parsed["source_updated_at"] = parsed["data_upd_value"]
            # DBF LONG is longitude and LAT is latitude. Keep them independent.
            parsed["longitude_from_long"] = parsed["long_value"]
            parsed["latitude_from_lat"] = parsed["lat_value"]
            parsed["source_status_value"] = parsed["status_value"]
            parsed["population_dbf_value_not_for_census_use"] = parsed["population_value"]
            records.append(parsed)
    actual_bytes = source.stat().st_size
    if header_length + count * record_length > actual_bytes:
        raise ValueError("DBF declared record area exceeds file size")
    meta = {"path": str(source), "size_bytes": actual_bytes, "record_count": count,
            "header_length": header_length, "record_length": record_length,
            "fields": fields, "trailing_bytes": actual_bytes - (header_length + count * record_length)}
    return meta, records


def _equal_raw_to_legacy(raw_value: Any, legacy_value: Any) -> bool:
    # Empty DBF fields are represented as None; empty is not zero.
    if raw_value is None or legacy_value is None:
        return raw_value is None and legacy_value is None
    return raw_value == legacy_value


def verify_snapshot(dbf_path: Path, manifest_path: Path, legacy_db_path: Path,
                    output_dir: Path, expected_legacy_sha: str = LEGACY_DB_EXPECTED_SHA256) -> dict[str, Any]:
    dbf_path = Path(dbf_path).resolve(strict=True)
    legacy_db_path = Path(legacy_db_path).resolve(strict=True)
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"verification output directory is not empty: {output_dir}")
    expected_manifest_sha = read_manifest_sha256(manifest_path, RAW_RELATIVE_PATH)
    raw_sha = sha256_file(dbf_path)
    if raw_sha != expected_manifest_sha:
        raise ValueError(f"DBF SHA differs from input manifest: expected {expected_manifest_sha}, got {raw_sha}")
    if raw_sha != DBF_EXPECTED_SHA256:
        raise ValueError(f"DBF SHA differs from frozen published snapshot: {DBF_EXPECTED_SHA256}")
    legacy_sha = sha256_file(legacy_db_path)
    if legacy_sha != expected_legacy_sha:
        raise ValueError(f"legacy database SHA mismatch: expected {expected_legacy_sha}, got {legacy_sha}")

    meta, raw_records = parse_dbf_records(dbf_path)
    if (meta["record_count"], meta["header_length"], meta["record_length"]) != (
            DBF_EXPECTED_RECORDS, DBF_EXPECTED_HEADER_LENGTH, DBF_EXPECTED_RECORD_LENGTH):
        raise ValueError(f"DBF layout differs from pinned snapshot: {meta}")
    raw_rows = []
    for row in raw_records:
        raw_rows.append({
            "historical_okato": row["historical_okato"], "record_number_1based": row["record_number_1based"],
            "record_byte_offset_0based": row["record_byte_offset_0based"],
            "deleted_marker_raw": row["deleted_marker_raw"], "is_deleted": row["is_deleted"],
            "ter_raw_text": row["ter_raw_text"], "kod1_raw_text": row["kod1_raw_text"],
            "kod2_raw_text": row["kod2_raw_text"], "kod3_raw_text": row["kod3_raw_text"],
            "name1_raw_text": row["name1_raw_text"], "name_raw": row["name_raw"],
            "scokato_raw_text": row["scokato_raw_text"], "settlement_type_raw": row["settlement_type_raw"],
            "kladrcode_raw_text": row["kladrcode_raw_text"], "kladr": row["kladr"],
            "oktmo_raw_text": row["oktmo_raw_text"], "oktmo_2011_raw": row["oktmo_2011_raw"],
            "data_upd_raw_text": row["data_upd_raw_text"], "source_updated_at": row["source_updated_at"],
            "long_raw_text": row["long_raw_text"], "longitude_from_long": row["longitude_from_long"],
            "lat_raw_text": row["lat_raw_text"], "latitude_from_lat": row["latitude_from_lat"],
            "status_raw_text": row["status_raw_text"], "source_status_value": row["source_status_value"],
            "population_raw_text_not_for_census_use": row["population_raw_text"],
            "population_dbf_value_not_for_census_use": row["population_dbf_value_not_for_census_use"],
            "source_sha256": raw_sha,
        })

    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    raw_df = pd.DataFrame.from_records(raw_rows)
    conn = duckdb.connect(str(legacy_db_path), read_only=True)
    try:
        schema = conn.execute(f"DESCRIBE {LEGACY_TABLE}").fetchall()
        if not schema:
            raise ValueError(f"missing frozen legacy table {LEGACY_TABLE}")
        legacy_count = int(conn.execute(f"SELECT count(*) FROM {LEGACY_TABLE}").fetchone()[0])
        legacy_columns = [row[0] for row in schema]
        required = {"historical_okato", "name_raw", "settlement_type_raw", "kladr", "oktmo_2011_raw",
                    "source_updated_at", "source_status", "latitude", "longitude"}
        if not required.issubset(legacy_columns):
            raise ValueError(f"legacy table missing expected fields: {sorted(required - set(legacy_columns))}")
        conn.register("raw_dbf", raw_df)
        raw_count = len(raw_rows)
        duplicate_raw = conn.execute("SELECT count(*) FROM (SELECT historical_okato FROM raw_dbf GROUP BY 1 HAVING count(*)>1)").fetchone()[0]
        duplicate_legacy = conn.execute(f"SELECT count(*) FROM (SELECT historical_okato FROM {LEGACY_TABLE} GROUP BY 1 HAVING count(*)>1)").fetchone()[0]
        joined = conn.execute(f"""
            SELECT r.historical_okato, r.record_number_1based, r.record_byte_offset_0based,
                   r.deleted_marker_raw, r.is_deleted,
                   r.name_raw AS raw_name, l.name_raw AS legacy_name,
                   r.settlement_type_raw AS raw_type, l.settlement_type_raw AS legacy_type,
                   r.kladr AS raw_kladr, l.kladr AS legacy_kladr,
                   r.oktmo_2011_raw AS raw_oktmo, l.oktmo_2011_raw AS legacy_oktmo,
                   r.source_updated_at AS raw_updated, l.source_updated_at AS legacy_updated,
                   r.longitude_from_long AS raw_longitude_from_long, l.longitude AS legacy_longitude,
                   r.latitude_from_lat AS raw_latitude_from_lat, l.latitude AS legacy_latitude,
                   r.source_status_value AS raw_status, l.source_status AS legacy_status
            FROM raw_dbf r FULL OUTER JOIN {LEGACY_TABLE} l USING (historical_okato)
        """).fetchall()
    finally:
        conn.close()

    # The compact row-level file is an extraction receipt, not a place-linked dataset.
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed_path = output_dir / "geokladr_okato_2011_raw_parsed.parquet"
    table = pa.Table.from_pandas(raw_df, preserve_index=False)
    pq.write_table(table, parsed_path, compression="zstd")

    field_mismatches = {key: 0 for key in ["name", "type", "kladr", "oktmo", "updated_at", "longitude", "latitude", "status"]}
    unmatched_raw = unmatched_legacy = 0
    deleted_count = sum(row["is_deleted"] for row in raw_rows)
    raw_empty_vs_legacy_null: dict[str, int] = {"kladr": 0, "oktmo": 0}
    for row in joined:
        (code, record_no, byte_offset, deleted, is_deleted,
         raw_name, legacy_name, raw_type, legacy_type, raw_kladr, legacy_kladr,
         raw_oktmo, legacy_oktmo, raw_updated, legacy_updated,
         raw_lon, legacy_lon, raw_lat, legacy_lat, raw_status, legacy_status) = row
        if code is None:
            unmatched_legacy += 1
            continue
        if record_no is None:
            unmatched_raw += 1
            continue
        for key, raw_value, legacy_value in [
            ("name", raw_name, legacy_name), ("type", raw_type, legacy_type),
            ("kladr", raw_kladr, legacy_kladr), ("oktmo", raw_oktmo, legacy_oktmo),
            ("updated_at", raw_updated, legacy_updated), ("longitude", raw_lon, legacy_lon),
            ("latitude", raw_lat, legacy_lat), ("status", raw_status, legacy_status),
        ]:
            if not _equal_raw_to_legacy(raw_value, legacy_value):
                field_mismatches[key] += 1
            if key in raw_empty_vs_legacy_null and raw_value is None and legacy_value is None:
                raw_empty_vs_legacy_null[key] += 1

    total_matches = len(joined) - unmatched_raw - unmatched_legacy
    receipt = {
        "verification_version": "geokladr-okato-2011-raw-vs-legacy-r1",
        "status": "PASS" if (raw_count == legacy_count == DBF_EXPECTED_RECORDS and not unmatched_raw
                               and not unmatched_legacy and not any(field_mismatches.values())
                               and duplicate_raw == 0 and duplicate_legacy == 0) else "PARTIAL",
        "raw_source": {**meta, "sha256": raw_sha, "sha256_input_manifest": expected_manifest_sha,
                       "sha256_expected_pinned": DBF_EXPECTED_SHA256},
        "legacy_database": {"path": str(legacy_db_path), "sha256": legacy_sha,
                            "sha256_expected_pinned": expected_legacy_sha,
                            "table": LEGACY_TABLE, "record_count": legacy_count,
                            "columns": legacy_columns},
        "comparison": {"raw_records": raw_count, "legacy_records": legacy_count,
                       "full_outer_join_rows": len(joined), "exact_code_matches": total_matches,
                       "raw_unmatched_codes": unmatched_raw, "legacy_unmatched_codes": unmatched_legacy,
                       "duplicate_raw_code_groups": int(duplicate_raw),
                       "duplicate_legacy_code_groups": int(duplicate_legacy),
                       "field_mismatches": field_mismatches,
                       "empty_raw_equals_legacy_null_counts": raw_empty_vs_legacy_null,
                       "deleted_record_count": int(deleted_count),
                       "deleted_markers_preserved_in_export": True,
                       "coordinates_checked_without_crossing_fields": {
                           "DBF_LONG_vs_legacy_longitude": field_mismatches["longitude"],
                           "DBF_LAT_vs_legacy_latitude": field_mismatches["latitude"],
                       }},
        "status_distribution_legacy": {str(k): int(v) for k, v in _status_counts(legacy_db_path).items()},
        "raw_source_updated_at_distribution": dict(sorted(Counter(row["source_updated_at"] for row in raw_records).items())),
        "verifier_sha256": sha256_file(Path(__file__)),
        "interpretation": "This verifies a dated OKATO/GeoKLADR snapshot only. OKTMO values are retained as 2011 raw administrative codes, not legal place events or modern settlement identifiers. No population value is joined to census observations; STATUS semantics remain unknown.",
        "output": {"path": str(parsed_path), "rows": raw_count,
                   "size_bytes": parsed_path.stat().st_size, "sha256": sha256_file(parsed_path)},
    }
    receipt_path = output_dir / "verification_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    receipt["receipt_sha256"] = sha256_file(receipt_path)
    return receipt


def _status_counts(db_path: Path) -> dict[Any, int]:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        return dict(conn.execute(f"SELECT source_status,count(*) FROM {LEGACY_TABLE} GROUP BY 1 ORDER BY 1").fetchall())
    finally:
        conn.close()


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--legacy-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = verify_snapshot(args.raw_root / RAW_RELATIVE_PATH, args.manifest, args.legacy_db, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
