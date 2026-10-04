#!/usr/bin/env python3
"""Append hash-pinned current-subject point context to an existing long display Parquet.

This adapter never rebuilds the long table and never changes source, population,
identity, or historical-coordinate fields. It joins the reviewed 309 statement
uses by exact Wikidata statement GUID and adds only ``current_subject_context_*``
columns. Runtime paths and hashes must be supplied explicitly by the caller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

TRUSTED_CONTEXT_CSV_SHA256 = "0130842ddaeb6f044f7715c21904b24503b5cfe0895efde82aad9df611a27e95"
TRUSTED_CONTEXT_RECEIPT_SHA256 = "e706d5bf518df8f41d52b27887bfdae2d9328a345aad4a631a7d04a269f2caed"
TRUSTED_POINT_LEDGER_SHA256 = "2215702e772417bb512da8c0a6c0d31ad9783c6a5345d4c0bbfe18403e11ad22"
TRUSTED_IDENTITY_GRAPH_SHA256 = "18bf1edd259808c9e881ac11fa40be26c88be4fb27e1ac735c59e083d6dcd312"
TRUSTED_REVIEW_STATUS = "candidate_only_current_subject_point_context_adapter_no_population_or_historical_point_admission"
EXPECTED_CONTEXT_ROWS = 309

# These are deliberately a separate, narrow namespace. Existing historical
# coordinates, population admission, identity, and point-ledger fields stay intact.
CONTEXT_TYPES = {
    "current_subject_context_status": "VARCHAR",
    "current_subject_context_kind": "VARCHAR",
    "current_subject_context_statement_guid": "VARCHAR",
    "current_subject_context_qid": "VARCHAR",
    "current_subject_context_current_source_record_id": "VARCHAR",
    "current_subject_context_current_entity_id": "VARCHAR",
    "current_subject_context_latitude": "DOUBLE",
    "current_subject_context_longitude": "DOUBLE",
    "current_subject_context_point_snapshot_year": "SMALLINT",
    "current_subject_context_point_admission_status": "VARCHAR",
    "current_subject_context_coordinate_source": "VARCHAR",
    "current_subject_context_source_provenance": "VARCHAR",
    "current_subject_context_origin_file": "VARCHAR",
    "current_subject_context_origin_sha256": "VARCHAR",
    "current_subject_context_origin_locator": "VARCHAR",
    "current_subject_context_origin_kind": "VARCHAR",
    "current_subject_context_temporal_relation": "VARCHAR",
    "current_subject_context_point_context_is_at_statement_date": "BOOLEAN",
    "current_subject_context_quality_status": "VARCHAR",
    "current_subject_context_rule": "VARCHAR",
    "current_subject_context_review_receipt_sha256": "VARCHAR",
    "current_subject_context_review_csv_sha256": "VARCHAR",
}

CSV_TO_OUTPUT = {
    "statement_guid": "current_subject_context_statement_guid",
    "qid": "current_subject_context_qid",
    "current_source_record_id": "current_subject_context_current_source_record_id",
    "current_entity_id": "current_subject_context_current_entity_id",
    "current_point_latitude": "current_subject_context_latitude",
    "current_point_longitude": "current_subject_context_longitude",
    "current_point_target_year": "current_subject_context_point_snapshot_year",
    "current_point_status": "current_subject_context_point_admission_status",
    "current_point_coordinate_source": "current_subject_context_coordinate_source",
    "current_point_coordinate_provenance": "current_subject_context_source_provenance",
    "current_point_origin_file": "current_subject_context_origin_file",
    "current_point_origin_sha256": "current_subject_context_origin_sha256",
    "current_point_origin_locator": "current_subject_context_origin_locator",
    "current_point_origin_kind": "current_subject_context_origin_kind",
    "point_context_vs_statement_year": "current_subject_context_temporal_relation",
}
REQUIRED_CSV_COLUMNS = set(CSV_TO_OUTPUT) | {
    "context_use_id", "observation_id", "observation_year", "P1082_value_raw",
    "current_subject_point_context_status", "historical_identity_admitted",
    "historical_coordinate_asserted", "history_population_admitted",
    "boundary_comparability_asserted", "quantitative_year_eligible_preserved",
}
REQUIRED_LONG_COLUMNS = {
    "observation_id", "record_type", "wikidata_statement_id", "current_wikidata_qid",
    "current_source_record_id", "current_place_entity_id", "observation_year",
    "population_value_raw_for_secondary_display", "history_population_admitted",
    "historical_identity_admitted", "historical_coordinate_asserted",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _receipt_check(receipt_path: Path, receipt_sha256: str, csv_sha256: str) -> dict[str, Any]:
    actual = sha256_file(receipt_path)
    if actual != receipt_sha256 or actual != TRUSTED_CONTEXT_RECEIPT_SHA256:
        raise ValueError(f"Context review receipt hash mismatch: {actual}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != TRUSTED_REVIEW_STATUS:
        raise ValueError(f"Unexpected context review status: {receipt.get('status')!r}")
    if receipt.get("result_counts", {}).get("eligible_current_subject_context_uses") != EXPECTED_CONTEXT_ROWS:
        raise ValueError("Review receipt does not pin 309 eligible current-subject context uses")
    if receipt.get("result_counts", {}).get("held_current_subject_context_uses") != 0:
        raise ValueError("Review receipt records held rows; expected the approved 309-row eligible adapter")
    if receipt.get("active_seventh_graph", {}).get("sha256") != TRUSTED_IDENTITY_GRAPH_SHA256:
        raise ValueError("Review receipt uses an unexpected seventh graph")
    if receipt.get("active_seventh_points", {}).get("sha256") != TRUSTED_POINT_LEDGER_SHA256:
        raise ValueError("Review receipt uses an unexpected seventh point ledger")
    if receipt.get("outputs", {}).get("current_subject_context_eligible.csv", {}).get("sha256") != csv_sha256:
        raise ValueError("Eligible CSV hash does not agree with the review receipt")
    return receipt


def _load_review(connection: duckdb.DuckDBPyConnection, csv_path: Path, receipt_path: Path, csv_sha256: str, receipt_sha256: str) -> None:
    if sha256_file(csv_path) != csv_sha256 or csv_sha256 != TRUSTED_CONTEXT_CSV_SHA256:
        raise ValueError("Current-subject context CSV hash does not match the reviewed eligible list")
    csv_columns = {row[0] for row in connection.execute("DESCRIBE SELECT * FROM read_csv(?, all_varchar=true)", [str(csv_path)]).fetchall()}
    missing = REQUIRED_CSV_COLUMNS - csv_columns
    if missing:
        raise ValueError(f"Reviewed CSV is missing columns: {sorted(missing)}")
    # The receipt is opened after its exact hash is checked. It is also pinned in
    # every appended row so the in-table context has an auditable review chain.
    _receipt_check(receipt_path, receipt_sha256, csv_sha256)
    casts = []
    for source, target in CSV_TO_OUTPUT.items():
        typ = CONTEXT_TYPES[target]
        if typ == "DOUBLE":
            expr = f"try_cast({quote_identifier(source)} AS DOUBLE)"
        elif typ == "SMALLINT":
            expr = f"try_cast({quote_identifier(source)} AS SMALLINT)"
        else:
            expr = f"cast({quote_identifier(source)} AS VARCHAR)"
        casts.append(f"{expr} AS {quote_identifier(target)}")
    casts.extend([
        f"try_cast({quote_identifier('observation_year')} AS INTEGER) AS _review_observation_year",
        f"cast({quote_identifier('P1082_value_raw')} AS VARCHAR) AS _review_P1082_value_raw",
        f"try_cast({quote_identifier('historical_identity_admitted')} AS BOOLEAN) AS _review_historical_identity_admitted",
        f"try_cast({quote_identifier('historical_coordinate_asserted')} AS BOOLEAN) AS _review_historical_coordinate_asserted",
        f"try_cast({quote_identifier('history_population_admitted')} AS BOOLEAN) AS _review_history_population_admitted",
        f"try_cast({quote_identifier('boundary_comparability_asserted')} AS BOOLEAN) AS _review_boundary_comparability_asserted",
        f"try_cast({quote_identifier('quantitative_year_eligible_preserved')} AS BOOLEAN) AS _review_quantitative_year_eligible",
        "'eligible_current_subject_point_context'::VARCHAR AS current_subject_context_status",
        "'accepted_2021_selected_source_point_context'::VARCHAR AS current_subject_context_kind",
        "FALSE::BOOLEAN AS current_subject_context_point_context_is_at_statement_date",
        "'accepted current point status and raw source origin path/hash/locator; measurement date unknown; not a historical coordinate'::VARCHAR AS current_subject_context_quality_status",
        "'current_subject_point_context_309_verified_v3; exact P1082 GUID + current physical-source binding + seventh entity + accepted 2021 point; no event or competing-P625 hold'::VARCHAR AS current_subject_context_rule",
        f"'{receipt_sha256}'::VARCHAR AS current_subject_context_review_receipt_sha256",
        f"'{csv_sha256}'::VARCHAR AS current_subject_context_review_csv_sha256",
    ])
    context_sql = ",\n      ".join(casts)
    connection.execute(
        f"CREATE TEMP TABLE review_context AS SELECT {context_sql} FROM read_csv(?, all_varchar=true)",
        [str(csv_path)],
    )


def _source_schema(connection: duckdb.DuckDBPyConnection, input_path: Path) -> list[tuple[str, str]]:
    desc = connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(input_path)]).fetchall()
    columns = [(row[0], row[1]) for row in desc]
    names = {name for name, _ in columns}
    missing = REQUIRED_LONG_COLUMNS - names
    if missing:
        raise ValueError(f"Full long Parquet is missing required columns: {sorted(missing)}")
    conflicts = set(CONTEXT_TYPES) & names
    if conflicts:
        raise ValueError(f"Input already contains context adapter columns; refusing overwrite: {sorted(conflicts)}")
    return columns


def _validate_inputs(connection: duckdb.DuckDBPyConnection, input_path: Path, expected_context_rows: int) -> tuple[list[tuple[str, str]], int]:
    columns = _source_schema(connection, input_path)
    # A full wide TEMP TABLE plus ORDER BY spilled several GiB for 865k rows.
    # Keep the immutable Parquet as a view and project only requested fields.
    # Observation IDs preserve row identity; physical output row order is not
    # an evidentiary property and is intentionally not asserted.
    connection.read_parquet(str(input_path)).create_view("source_long")
    source_rows = connection.execute("SELECT count(*) FROM source_long").fetchone()[0]
    if source_rows < expected_context_rows:
        raise ValueError("Long input has fewer rows than the reviewed context list")
    duplicate_observations = connection.execute("SELECT count(*) FROM (SELECT observation_id FROM source_long GROUP BY observation_id HAVING count(*)<>1)").fetchone()[0]
    if duplicate_observations:
        raise ValueError(f"Long input observation_id is not unique; duplicate groups={duplicate_observations}")
    duplicate_guids = connection.execute("SELECT count(*) FROM (SELECT wikidata_statement_id FROM source_long WHERE wikidata_statement_id IS NOT NULL GROUP BY wikidata_statement_id HAVING count(*)<>1)").fetchone()[0]
    if duplicate_guids:
        raise ValueError(f"Long input statement GUID is not unique; duplicate groups={duplicate_guids}")
    review_rows = connection.execute("SELECT count(*) FROM review_context").fetchone()[0]
    if review_rows != expected_context_rows:
        raise ValueError(f"Reviewed context row count {review_rows}, expected {expected_context_rows}")
    duplicate_review_guids = connection.execute("SELECT count(*) FROM (SELECT current_subject_context_statement_guid FROM review_context GROUP BY 1 HAVING count(*)<>1)").fetchone()[0]
    if duplicate_review_guids:
        raise ValueError(f"Reviewed statement GUID is not unique; duplicate groups={duplicate_review_guids}")
    malformed = connection.execute("""
      SELECT count(*) FROM review_context
      WHERE current_subject_context_statement_guid IS NULL OR current_subject_context_statement_guid=''
         OR current_subject_context_qid IS NULL OR current_subject_context_current_source_record_id IS NULL
         OR current_subject_context_current_entity_id IS NULL
         OR current_subject_context_latitude IS NULL OR current_subject_context_longitude IS NULL
         OR current_subject_context_point_snapshot_year IS DISTINCT FROM 2021
         OR current_subject_context_latitude NOT BETWEEN -90 AND 90
         OR current_subject_context_longitude NOT BETWEEN -180 AND 180
         OR current_subject_context_status<>'eligible_current_subject_point_context'
         OR current_subject_context_point_admission_status NOT IN ('reviewed_rule_accepted','reviewed_extension_rule_accepted','reviewed_case_accepted','frozen_r5b_reviewed_baseline_preserved')
         OR current_subject_context_review_receipt_sha256 IS NULL
         OR current_subject_context_review_csv_sha256 IS NULL
    """).fetchone()[0]
    if malformed:
        raise ValueError(f"Reviewed current context list has {malformed} malformed or nonaccepted rows")
    unmatched = connection.execute("""
      SELECT count(*) FROM review_context c LEFT JOIN source_long l
        ON c.current_subject_context_statement_guid=l.wikidata_statement_id
      WHERE l.wikidata_statement_id IS NULL
    """).fetchone()[0]
    if unmatched:
        raise ValueError(f"{unmatched} reviewed statement GUIDs do not match the full long input")
    mismatch = connection.execute("""
      SELECT count(*) FROM review_context c JOIN source_long l
        ON c.current_subject_context_statement_guid=l.wikidata_statement_id
      WHERE l.record_type<>'wiki_literal_series'
         OR l.current_wikidata_qid IS DISTINCT FROM c.current_subject_context_qid
         OR l.current_source_record_id IS DISTINCT FROM c.current_subject_context_current_source_record_id
         OR l.current_place_entity_id IS DISTINCT FROM c.current_subject_context_current_entity_id
         OR try_cast(l.observation_year AS INTEGER) IS DISTINCT FROM c._review_observation_year
         OR l.population_value_raw_for_secondary_display IS DISTINCT FROM c._review_P1082_value_raw
         OR l.historical_identity_admitted IS DISTINCT FROM FALSE
         OR l.historical_coordinate_asserted IS DISTINCT FROM FALSE
         OR l.history_population_admitted IS DISTINCT FROM FALSE
         OR c._review_historical_identity_admitted IS DISTINCT FROM FALSE
         OR c._review_historical_coordinate_asserted IS DISTINCT FROM FALSE
         OR c._review_history_population_admitted IS DISTINCT FROM FALSE
         OR c._review_boundary_comparability_asserted IS DISTINCT FROM FALSE
         OR c._review_quantitative_year_eligible IS DISTINCT FROM FALSE
    """).fetchone()[0]
    if mismatch:
        raise ValueError(f"{mismatch} context rows mismatch source GUID/QID/year/value/entity or admission-preservation gates")
    matched = connection.execute("""
      SELECT count(*) FROM source_long l JOIN review_context c
        ON l.wikidata_statement_id=c.current_subject_context_statement_guid
    """).fetchone()[0]
    if matched != expected_context_rows:
        raise ValueError(f"Expected {expected_context_rows} unique joined GUIDs, found {matched}")
    return columns, source_rows


def build_display_adapter(
    input_long: Path,
    context_csv: Path,
    output: Path,
    *,
    review_receipt_path: Path,
    context_csv_sha256: str,
    context_receipt_sha256: str,
    expected_context_rows: int = EXPECTED_CONTEXT_ROWS,
    expected_input_rows: int | None = None,
    memory_limit: str = "1GB",
) -> dict[str, Any]:
    """Join a validated review CSV to a full long table without altering source fields."""
    for path in (input_long, context_csv, review_receipt_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    input_sha = sha256_file(input_long)
    csv_sha = sha256_file(context_csv)
    receipt_sha = sha256_file(review_receipt_path)
    if csv_sha != context_csv_sha256 or csv_sha != TRUSTED_CONTEXT_CSV_SHA256:
        raise ValueError("Context CSV SHA-256 does not match the approved 309-row adapter")
    if receipt_sha != context_receipt_sha256 or receipt_sha != TRUSTED_CONTEXT_RECEIPT_SHA256:
        raise ValueError("Context receipt SHA-256 does not match the approved 309-row review")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite output: {output}")
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    if receipt_path.exists():
        raise FileExistsError(f"Refusing to overwrite receipt: {receipt_path}")
    staging = output.with_name(output.name + ".staging.parquet")
    if staging.exists():
        raise FileExistsError(f"Refusing to reuse staging path: {staging}")
    output.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(config={"threads": 1, "memory_limit": memory_limit, "preserve_insertion_order": False})
    try:
        _load_review(connection, context_csv, review_receipt_path, csv_sha, receipt_sha)
        original_columns, source_rows = _validate_inputs(connection, input_long, expected_context_rows)
        if expected_input_rows is not None and source_rows != expected_input_rows:
            raise ValueError(f"Input long row count mismatch: {source_rows} != {expected_input_rows}")
        original_names = [name for name, _ in original_columns]
        projection = ",\n          ".join(f"s.{quote_identifier(name)}" for name in original_names)
        additions = []
        for name, typ in CONTEXT_TYPES.items():
            additions.append(f"c.{quote_identifier(name)} AS {quote_identifier(name)}")
        select_sql = ",\n          ".join([projection, *additions])
        # Stream the source and small hash-joined context without sorting wide rows.
        connection.execute(
            f"COPY (SELECT {select_sql} FROM source_long s LEFT JOIN review_context c "
            f"ON s.wikidata_statement_id=c.current_subject_context_statement_guid "
            f") TO ? (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 16384)",
            [str(staging)],
        )
        output_rows = connection.execute("SELECT count(*) FROM read_parquet(?)", [str(staging)]).fetchone()[0]
        if output_rows != source_rows:
            raise ValueError(f"Output row count changed: {source_rows} -> {output_rows}")
        output_schema = connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(staging)]).fetchall()
        output_names = [r[0] for r in output_schema]
        if output_names[:len(original_names)] != original_names:
            raise ValueError("Original column order/schema changed in output")
        if output_names[len(original_names):] != list(CONTEXT_TYPES):
            raise ValueError("Unexpected context columns/order in output")
        type_by_name = {r[0]: r[1].upper() for r in output_schema}
        for name, expected_type in CONTEXT_TYPES.items():
            if type_by_name[name] != expected_type:
                raise ValueError(f"Context column {name} has type {type_by_name[name]}, expected {expected_type}")
        output_guid_matches = connection.execute("""
          SELECT count(*) FROM read_parquet(?) WHERE current_subject_context_status='eligible_current_subject_point_context'
        """, [str(staging)]).fetchone()[0]
        if output_guid_matches != expected_context_rows:
            raise ValueError(f"Expected {expected_context_rows} displayed contexts, found {output_guid_matches}")
        unexpected_admission = connection.execute("""
          SELECT count(*) FROM read_parquet(?)
          WHERE current_subject_context_status='eligible_current_subject_point_context'
            AND (historical_identity_admitted IS DISTINCT FROM FALSE
              OR historical_coordinate_asserted IS DISTINCT FROM FALSE
              OR history_population_admitted IS DISTINCT FROM FALSE)
        """, [str(staging)]).fetchone()[0]
        if unexpected_admission:
            raise ValueError("Adapter altered or encountered non-false historical/census admission flags")
        unmatched_additions = connection.execute("""
          SELECT count(*) FROM read_parquet(?)
          WHERE current_subject_context_status IS NULL
            AND (current_subject_context_statement_guid IS NOT NULL OR current_subject_context_latitude IS NOT NULL
              OR current_subject_context_longitude IS NOT NULL OR current_subject_context_review_receipt_sha256 IS NOT NULL)
        """, [str(staging)]).fetchone()[0]
        if unmatched_additions:
            raise ValueError("Unmatched rows received context values")
        os.replace(staging, output)
        receipt = {
            "status": "current_subject_point_context_display_adapter_written_no_identity_population_or_historical_point_admission",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "adapter_script_path": str(Path(__file__).resolve()),
            "adapter_script_sha256": sha256_file(Path(__file__).resolve()),
            "input_long": {"path": str(input_long.resolve()), "sha256": input_sha, "rows": source_rows, "columns": len(original_names)},
            "reviewed_context_csv": {"path": str(context_csv.resolve()), "sha256": csv_sha, "rows": expected_context_rows},
            "review_receipt": {"path": str(review_receipt_path.resolve()), "sha256": receipt_sha},
            "trusted_review_pins": {"graph_sha256": TRUSTED_IDENTITY_GRAPH_SHA256, "point_ledger_sha256": TRUSTED_POINT_LEDGER_SHA256},
            "output": {"path": str(output.resolve()), "sha256": sha256_file(output), "bytes": output.stat().st_size, "rows": output_rows, "columns": len(output_names)},
            "matched_context_rows": output_guid_matches,
            "unmatched_long_rows_with_null_context": output_rows - output_guid_matches,
            "original_columns_projected_directly_and_in_original_order": original_names,
            "new_columns": list(CONTEXT_TYPES),
            "all_existing_values_preserved_by_direct_projection": True,
            "physical_row_order_asserted": False,
            "historical_identity_coordinate_population_admissions_changed": False,
            "current_context_temporal_scope": "2021 selected-source point context only; not assigned to the dated P1082 observation and not a historical coordinate measurement",
            "no_census_metrics_or_population_values_changed": True,
        }
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt["output_receipt"] = {"path": str(receipt_path.resolve()), "sha256": sha256_file(receipt_path)}
        return receipt
    except Exception:
        if staging.exists():
            staging.unlink()
        raise
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-long", type=Path, required=True)
    parser.add_argument("--input-long-sha256", required=True)
    parser.add_argument("--context-csv", type=Path, required=True)
    parser.add_argument("--context-csv-sha256", required=True)
    parser.add_argument("--review-receipt", type=Path, required=True)
    parser.add_argument("--review-receipt-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-input-rows", type=int)
    parser.add_argument("--memory-limit", default="1GB")
    args = parser.parse_args()
    actual_long_sha = sha256_file(args.input_long)
    if actual_long_sha != args.input_long_sha256:
        raise ValueError(f"Full long input hash mismatch: expected {args.input_long_sha256}, found {actual_long_sha}")
    result = build_display_adapter(
        args.input_long, args.context_csv, args.output,
        review_receipt_path=args.review_receipt,
        context_csv_sha256=args.context_csv_sha256,
        context_receipt_sha256=args.review_receipt_sha256,
        expected_input_rows=args.expected_input_rows,
        memory_limit=args.memory_limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
