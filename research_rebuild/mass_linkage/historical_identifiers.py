"""Build a read-only ledger of observed historical/current identifier claims.

Classifier revisions, source update times, source snapshot dates, and explicit
lineage-table event dates stay in separate fields. This module never assigns
validity intervals or admits a place binding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import json
import uuid
import pyarrow as pa
from pathlib import Path
from typing import Any, Iterable

import duckdb


EXPECTED_DATABASE_SHA256 = "26a2fe5b2ce05119d919a196beb57cd655a49ffffb0ff8f194762aa78e6b5b64"
REQUIRED_OUTPUT_ROOT = Path("/workspace/settlements-work/sources/historical_identifiers")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEDGER_COLUMNS = [
    "claim_id", "source_table", "source_record_id", "source_file", "source_sheet",
    "source_row", "source_field", "identifier_system", "raw_code",
    "normalized_exact_code", "normalization_status", "source_snapshot_version",
    "source_snapshot_date", "source_updated_at", "source_status_raw",
    "source_status_interpretation", "provider", "original_settlement_id",
    "candidate_settlement_id", "region_raw", "name_raw", "type_raw",
    "source_locator", "source_url", "source_sha256", "valid_from", "valid_to",
    "binding_status",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _q(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sql_text(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def normalize_exact_code(raw: Any) -> tuple[str | None, str]:
    """Remove only a spreadsheet-style trailing .0; never pad or truncate."""
    if raw is None:
        return None, "missing"
    text = str(raw).strip()
    if not text:
        return None, "missing"
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if re.fullmatch(r"\d+", text):
        return text, "digits_only_exact"
    return None, "not_digits_only_preserved_raw"


def _manifest_hashes(conn: duckdb.DuckDBPyConnection, manifest_path: Path) -> dict[str, str]:
    path = str(Path(manifest_path).resolve(strict=True))
    if Path(path).suffix.casefold() == ".csv":
        source = f"read_csv_auto({_sql_text(path)}, all_varchar=true)"
    else:
        source = f"read_parquet({_sql_text(path)})"
    cols = {r[0] for r in conn.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()}
    if not {"path", "sha256"} <= cols:
        raise ValueError("input manifest must have path and sha256 columns")
    return {str(p): str(s) for p, s in conn.execute(
        f"SELECT path, sha256 FROM {source} WHERE path IS NOT NULL AND sha256 IS NOT NULL"
    ).fetchall()}


def _source_hash(hashes: dict[str, str], *paths: str) -> str | None:
    for path in paths:
        if path in hashes:
            return hashes[path]
    return None


def _rows(conn: duckdb.DuckDBPyConnection, query: str) -> Iterable[dict[str, Any]]:
    cursor = conn.execute(query)
    names = [d[0] for d in cursor.description]
    for values in cursor.fetchall():
        yield dict(zip(names, values))


def _claim_row(**values: Any) -> dict[str, Any]:
    row = {name: None for name in LEDGER_COLUMNS}
    row.update(values)
    row.setdefault("valid_from", None)
    row.setdefault("valid_to", None)
    if row.get("binding_status") is None:
        row["binding_status"] = "source_claim_only_not_identity_accepted"
    if row["identifier_system"] == "FIAS":
        try:
            code = str(uuid.UUID(str(row["raw_code"]).strip()))
            state = "valid_uuid_canonical_case_and_hyphens"
        except (ValueError, AttributeError):
            code, state = None, "invalid_uuid_preserved_raw"
    else:
        code, state = normalize_exact_code(row["raw_code"])
    row["normalized_exact_code"] = code
    row["normalization_status"] = state
    return row


def _build_claims(conn: duckdb.DuckDBPyConnection, hashes: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    hash_2009 = _source_hash(hashes,
        "data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql")
    for rec in _rows(conn, "SELECT * FROM main.historical_okato_142_2009"):
        rows.append(_claim_row(
            claim_id=f"okato142-2009:{rec['historical_okato']}:{rec['classifier_occurrence']}",
            source_table="historical_okato_142_2009", source_file="data/raw/historical_classifiers/okato_142_2009/dump-142_2009.sql",
            source_field="historical_okato", identifier_system="OKATO",
            raw_code=rec["historical_okato"], source_snapshot_version=rec["snapshot_revision"],
            source_status_raw=rec["status"], provider="historical OKATO classifier snapshot",
            candidate_settlement_id=rec["candidate_settlement_id"], region_raw=rec["historical_region_raw"],
            name_raw=rec["name_raw"], type_raw=rec["status"],
            source_locator=f"classifier_occurrence={rec['classifier_occurrence']};group_size={rec['classifier_group_size']}",
            source_url=rec["snapshot_url"], source_sha256=hash_2009,
        ))

    hash_2011 = _source_hash(hashes,
        "data/raw/historical_geography/geokladr_okato_2011/okato.dbf")
    for rec in _rows(conn, "SELECT * FROM main.historical_geokladr_coordinates_2011"):
        common = dict(
            source_table="historical_geokladr_coordinates_2011",
            source_file="data/raw/historical_geography/geokladr_okato_2011/okato.dbf",
            source_snapshot_version="GeoKLADR/OKATO DBF snapshot",
            source_snapshot_date=rec["source_snapshot_date"], source_updated_at=rec["source_updated_at"],
            source_status_raw=rec["source_status"],
            source_status_interpretation="unknown_source_status_code; no mapping inferred",
            provider="GeoKLADR/OKATO archived DBF",
            region_raw=None, name_raw=rec["name_raw"], type_raw=rec["settlement_type_raw"],
            source_locator=f"historical_okato={rec['historical_okato']};kladr={rec['kladr']}",
            source_url=rec["source_archive_url"], source_sha256=hash_2011,
        )
        for field, system in (("historical_okato", "OKATO"), ("kladr", "KLADR"), ("oktmo_2011_raw", "OKTMO")):
            raw = rec[field]
            if raw is None:
                continue
            rows.append(_claim_row(
                claim_id=f"geokladr2011:{rec['historical_okato']}:{field}:{raw}",
                source_field=field, identifier_system=system, raw_code=raw,
                original_settlement_id=None, candidate_settlement_id=None, **common,
            ))

    hash_2021 = _source_hash(hashes,
        "data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet")
    fields = [
        ("oktmo", "OKTMO", "source_native"), ("okato", "OKATO", "source_native"),
        ("settlement_fias_id_dadata", "FIAS", "DaData"), ("fias_id_dadata", "FIAS", "DaData"),
        ("oktmo_dadata", "OKTMO", "DaData"), ("okato_dadata", "OKATO", "DaData"),
    ]
    for rec in _rows(conn, "SELECT * FROM main.administrative_identifiers_2021"):
        version = None
        if rec["source_record_id"]:
            match = re.search(r"_v(\d{8})\.parquet", str(rec["source_record_id"]))
            version = match.group(1) if match else None
        common = dict(
            source_table="administrative_identifiers_2021",
            source_file="data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet",
            source_snapshot_version=version or "filename_version_unparsed",
            original_settlement_id=rec["settlement_id"], candidate_settlement_id=rec["settlement_id"],
            source_record_id=rec["source_record_id"], name_raw=None, type_raw=rec["fias_level_dadata"],
            source_locator=rec["source_record_id"], source_url=rec["source_dataset_url"],
            source_sha256=hash_2021,
            source_status_raw=("okato_parent_or_aggregate_risk=" + str(rec["okato_parent_or_aggregate_risk"]) +
                               ";wikidata_identifier_conflict=" + str(rec["wikidata_identifier_conflict"])),
            source_status_interpretation="table_quality_flags_preserved_as_raw_labels",
        )
        for field, system, provider in fields:
            raw = rec[field]
            if raw is None:
                continue
            rows.append(_claim_row(
                claim_id=f"2021:{rec['source_record_id']}:{field}:{raw}", source_field=field,
                identifier_system=system, raw_code=raw, provider=("DaData as carried by Tochno" if provider == "DaData" else "Tochno source-native field"), **common,
            ))
    return rows


def build_identifier_inventory(database_path: Path, expected_sha256: str,
                               manifest_path: Path) -> dict[str, Any]:
    """Inspect source tables read-only and prepare candidate claims/events."""
    from .legacy_inventory import verify_database

    db_receipt = verify_database(Path(database_path), expected_sha256)
    conn = duckdb.connect(db_receipt["path"], read_only=True)
    try:
        hashes = _manifest_hashes(conn, manifest_path)
        claim_rows = _build_claims(conn, hashes)
        counts = {}
        for table in ("historical_okato_142_2009", "historical_geokladr_coordinates_2011",
                      "administrative_identifiers_2021", "census_lineage_events"):
            counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM main.{_q(table)}").fetchone()[0])
        row_fields = {}
        for year in (2002, 2010):
            row_fields[str(year)] = conn.execute(
                "SELECT COUNT(*) total, COUNT(okato) okato_nonnull, COUNT(oktmo) oktmo_nonnull, "
                "COUNT(fias_id) fias_nonnull, COUNT(source_native_id) native_row_id_nonnull "
                "FROM main.census_source_rows WHERE census_year = ?", [year],
            ).fetchone()
        events = []
        for rec in _rows(conn, "SELECT * FROM main.census_lineage_events ORDER BY event_id"):
            events.append({
                "event_id": rec["event_id"], "event_type": rec["event_type"],
                "source_asserted_effective_date": rec["effective_date"],
                "date_role": "legacy_lineage_table_effective_date_assertion_not_independently_verified_here",
                "valid_from": None, "valid_to": None,
                "from_settlement_id_legacy_candidate": rec["from_settlement_id"],
                "to_settlement_id_legacy_candidate": rec["to_settlement_id"],
                "evidence_url": rec["evidence_url"], "note_raw": rec["note"],
                "relation_source": rec["relation_source"],
            })
        return {
            "inventory_version": "historical-identifier-candidates-r1",
            "database": db_receipt, "database_read_only": True,
            "manifest_path": str(Path(manifest_path).resolve(strict=True)),
            "table_row_counts": counts,
            "census_source_row_code_field_counts": {
                year: {"rows": int(total), "okato_nonnull": int(okato), "oktmo_nonnull": int(oktmo),
                       "fias_nonnull": int(fias), "source_native_row_id_nonnull": int(native)}
                for year, (total, okato, oktmo, fias, native) in row_fields.items()
            },
            "claim_count": len(claim_rows), "claims": claim_rows, "lineage_events": events,
            "interpretation": {
                "code_claims": "Observed identifiers with source version and locators; comparisons are not legal change events or proof of same-place identity.",
                "dates": "Source snapshot/update/version dates describe the cited artifact only. valid_from and valid_to remain null.",
                "2011_source_status": "Raw DBF status codes are retained; no available dictionary established their meaning, so every code stays unmapped.",
                "2002_2010_workbook_codes": "Processed census_source_rows has no non-null OKATO/OKTMO/FIAS fields; source_native_id is only a workbook row identifier. No fuzzy classifier-code join is performed.",
            },
        }
    finally:
        conn.close()


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    # DuckDB handles Parquet output directly and keeps the source DB read-only.
    conn = duckdb.connect()
    try:
        table = pa.Table.from_pylist([{k: (None if v is None else str(v)) for k,v in row.items()} for row in rows])
        conn.register("ledger_rows", table)
        columns = ", ".join(_q(c) for c in LEDGER_COLUMNS)
        target = str(path).replace("'", "''")
        conn.execute(f"COPY (SELECT {columns} FROM ledger_rows) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        conn.close()


def write_identifier_inventory(database_path: Path, expected_sha256: str,
                               manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    out = Path(output_dir).expanduser().resolve()
    try:
        out.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("identifier outputs must stay outside the Git checkout")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    report = build_identifier_inventory(database_path, expected_sha256, manifest_path)
    claims = report.pop("claims")
    events = report.pop("lineage_events")
    parquet_path = out / "identifier_claim_candidates.parquet"
    _write_parquet(claims, parquet_path)
    events_path = out / "lineage_event_candidates.json"
    events_path.write_text(json.dumps(events, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    schema_path = out / "schema_and_date_semantics.json"
    schema = {
        "ledger_columns": LEDGER_COLUMNS,
        "identifier_claim_rows": len(claims), "lineage_event_rows": len(events),
        "semantics": report["interpretation"],
        "source_dates": {
            "snapshot_date": "source artifact date; no assertion of legal validity",
            "source_updated_at": "source DBF field preserved verbatim; no assertion of legal validity",
            "source_snapshot_version": "classifier or input filename revision label",
            "source_asserted_effective_date": "explicit legacy event-table text; needs source-level verification before legal interpretation",
            "valid_from/valid_to": "unknown/null until explicit authoritative validity evidence is recorded",
        },
        "source_status_codes_2011": {"0": "unmapped", "2": "unmapped", "3": "unmapped"},
    }
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["builder_sha256"] = sha256_file(Path(__file__))
    report["outputs"] = {
        "claims": {"path": str(parquet_path), "rows": len(claims), "bytes": parquet_path.stat().st_size,
                   "sha256": sha256_file(parquet_path)},
        "events": {"path": str(events_path), "rows": len(events), "bytes": events_path.stat().st_size,
                   "sha256": sha256_file(events_path)},
        "schema": {"path": str(schema_path), "bytes": schema_path.stat().st_size,
                   "sha256": sha256_file(schema_path)},
    }
    report_path = out / "inventory_receipt.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output_dir": str(out), "claim_count": len(claims), "event_count": len(events),
            "receipt_path": str(report_path), "receipt_sha256": sha256_file(report_path)}


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=EXPECTED_DATABASE_SHA256)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=REQUIRED_OUTPUT_ROOT)
    args = parser.parse_args()
    print(json.dumps(write_identifier_inventory(args.database, args.expected_sha256,
                                                args.manifest, args.output_dir), indent=2))


if __name__ == "__main__":
    _main()
