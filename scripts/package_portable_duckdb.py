#!/usr/bin/env python3
"""Package the pilot Parquet outputs in a self-contained DuckDB artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_scalar(value):
    if value is None or value is pd.NA:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {str(k): canonical_scalar(v) for k, v in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [canonical_scalar(v) for v in value]
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def typed_frame_sha256(frame: pd.DataFrame, arrow_schema) -> str:
    rows = []
    for row in frame.itertuples(index=False, name=None):
        typed = []
        for value in row:
            normalized = canonical_scalar(value)
            typed.append(None if normalized is None else {"type": type(value.item() if hasattr(value, "item") else value).__name__, "value": normalized})
        rows.append(typed)
    payload = {"columns": [{"name": name, "arrow_type": str(arrow_schema.field(name).type)} for name in frame.columns], "rows": rows}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def build(release_dir: Path, database_path: Path) -> dict:
    release_dir = release_dir.expanduser().resolve()
    database_path = database_path.expanduser().resolve()
    if not release_dir.is_dir():
        raise FileNotFoundError(f"pilot release directory does not exist: {release_dir}")
    manifest_path = release_dir / "release_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("pilot release_manifest.json is required")
    if database_path.exists():
        raise FileExistsError(f"portable database output already exists: {database_path}")
    parquet_files = sorted(release_dir.glob("*.parquet"))
    if not parquet_files:
        raise ValueError("pilot release contains no Parquet tables")
    database_path.parent.mkdir(parents=True, exist_ok=True)

    expected_hashes = json.loads(manifest_path.read_text(encoding="utf-8")).get("output_artifact_sha256", {})
    con = duckdb.connect(str(database_path))
    table_details = []
    try:
        for parquet_path in parquet_files:
            table_name = parquet_path.stem
            source_hash = sha256(parquet_path)
            if table_name in expected_hashes and source_hash != expected_hashes[table_name]:
                raise ValueError(f"Parquet hash differs from release manifest: {parquet_path.name}")
            source_frame = pd.read_parquet(parquet_path)
            source_schema = pq.read_schema(parquet_path)
            source_digest = typed_frame_sha256(source_frame, source_schema)
            quoted = quote_identifier(table_name)
            escaped_path = parquet_path.as_posix().replace("'", "''")
            con.execute(f"CREATE TABLE {quoted} AS SELECT * FROM read_parquet('{escaped_path}')")
            actual_frame = con.execute(f"SELECT * FROM {quoted}").fetchdf()
            actual_digest = typed_frame_sha256(actual_frame, source_schema)
            if len(actual_frame) != len(source_frame) or actual_digest != source_digest:
                raise ValueError(f"Materialized DuckDB table differs from source Parquet: {parquet_path.name}")
            schema = [{"name": field.name, "arrow_type": str(field.type)} for field in source_schema]
            table_details.append({"table": table_name, "parquet_file": parquet_path.name,
                "parquet_sha256": source_hash, "rows": len(source_frame),
                "typed_content_sha256": source_digest, "schema": schema})
        if "effective_coordinate_decisions" in {item["table"] for item in table_details}:
            con.execute('CREATE VIEW "admitted_coordinate_observations" AS SELECT * FROM "effective_coordinate_decisions" WHERE event_action=\'apply\'')
            if "selected_observations_for_release" in {item["table"] for item in table_details}:
                leaked = con.execute('SELECT count(*) FROM "admitted_coordinate_observations" d ANTI JOIN "selected_observations_for_release" s USING(observation_id)').fetchone()[0]
                if leaked:
                    raise ValueError(f"portable admitted-coordinate view has {leaked} unselected observation rows")
        views = con.execute("SELECT view_name, sql FROM duckdb_views() WHERE schema_name='main' AND internal=false ORDER BY view_name").fetchall()
        view_rows = len(views)
        table_rows = con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE'").fetchone()[0]
    finally:
        con.close()

    # Reopen only a copied .duckdb file from an unrelated working directory.
    # The copied file must contain tables, not views that depend on build paths.
    with tempfile.TemporaryDirectory(prefix="portable-duckdb-check-") as temp:
        isolated = Path(temp) / database_path.name
        shutil.copy2(database_path, isolated)
        con = duckdb.connect(str(isolated), read_only=True)
        try:
            definitions = con.execute("SELECT sql FROM duckdb_views() WHERE internal = false").fetchall()
            if any("read_parquet" in str(definition).lower() for (definition,) in definitions):
                raise ValueError("portable DuckDB has a view that reads external Parquet paths")
            copied_views = con.execute("SELECT view_name, sql FROM duckdb_views() WHERE schema_name='main' AND internal=false ORDER BY view_name").fetchall()
            if copied_views != views:
                raise ValueError("portable copied database view definitions differ from the packaged database")
            for item in table_details:
                frame = con.execute(f"SELECT * FROM {quote_identifier(item['table'])}").fetchdf()
                source_schema = pq.read_schema(release_dir / item["parquet_file"])
                if len(frame) != item["rows"] or typed_frame_sha256(frame, source_schema) != item["typed_content_sha256"]:
                    raise ValueError(f"portable copied database failed typed-content verification: {item['table']}")
            critical = {}
            if "selected_observations_for_release" in {item["table"] for item in table_details}:
                for row in con.execute('SELECT census_year, count(*), sum(population) FROM "selected_observations_for_release" GROUP BY census_year ORDER BY census_year').fetchall():
                    critical[str(int(row[0]))] = {"rows": int(row[1]), "population": int(row[2])}
            if "admitted_coordinate_observations" in [name[0] for name in con.execute("SELECT table_name FROM information_schema.views WHERE table_schema='main'").fetchall()]:
                admitted = con.execute('SELECT count(*), sum(s.population) FROM "admitted_coordinate_observations" d JOIN "selected_observations_for_release" s USING(observation_id)').fetchone()
                critical["admitted_coordinates"] = {"rows": int(admitted[0]), "population": int(admitted[1])}
        finally:
            con.close()

    manifest = {
        "artifact_type": "self-contained materialized DuckDB distribution",
        "source_release_manifest_sha256": sha256(manifest_path),
        "database_file": database_path.name,
        "database_sha256": sha256(database_path),
        "database_bytes": database_path.stat().st_size,
        "table_count": len(table_details),
        "view_count": int(view_rows),
        "views": [{"name": name, "sql": sql} for name, sql in views],
        "table_count_in_database": int(table_rows),
        "tables": table_details,
        "portable_copy_check": "passed: copied database reopened and every table's typed content hash matched with no external Parquet paths",
        "key_query_results": critical,
        "limitations": ["This is a materialized convenience database built from the release Parquet tables; the Parquet files and scientific release manifest remain the authoritative artifacts."]
    }
    output_manifest = database_path.with_suffix(".manifest.json")
    output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--database-path", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.release_dir, args.database_path)
    print(json.dumps({key: result[key] for key in (
        "database_file", "database_sha256", "database_bytes", "table_count", "view_count",
        "table_count_in_database", "portable_copy_check", "key_query_results"
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
