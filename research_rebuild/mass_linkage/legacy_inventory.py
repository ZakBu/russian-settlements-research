"""Read-only inventory and controlled export helpers for the legacy DuckDB.

The file hash is checked before opening the database. Inventory is limited to
schema, counts, temporal fields, low-cardinality quality flags, and evidence
field completeness; it never changes the database. Optional exports require an
explicit table, column list, and output location outside the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import duckdb


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_EXPORT_ROOT = Path("/workspace/settlements-work/sources/legacy_inventory")
INVENTORY_VERSION = "legacy-duckdb-inventory-r1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_database(path: Path, expected_sha256: str) -> dict[str, Any]:
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise FileNotFoundError(path)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase 64-character SHA-256")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(f"legacy database hash mismatch: expected {expected_sha256}, got {actual}")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": actual}


def _ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_ident(schema)}.{_ident(table)}"


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9а-я]+", "_", name.casefold()).strip("_")


def _field_roles(name: str) -> list[str]:
    n = _norm(name)
    roles: list[str] = []
    non_value_population = re.search(r"quality|scope|additive|trusted|status|note|candidate|year|count|flag|cell", n)
    if re.search(r"population|pop(?:ulation)?|населен|числен", n) and not non_value_population:
        roles.append("population")
    if re.search(r"oktmo|okato|kladr|settlement_id|place_id|wikidata|qid|код", n):
        roles.append("identifier_or_code")
    if _is_temporal_field(name):
        roles.append("temporal")
    if re.search(r"source|provenance|reference|citation|evidence|url|uri|sha|hash|page|sheet|row|statement|revision|locator|ссыл|источник", n):
        roles.append("provenance")
    if re.search(r"quality|status|exact|protected|rounded|precision|confidential|perturb|точн|защит|округл|точност|качест|статус", n):
        roles.append("quality_or_precision_evidence")
    if n.endswith("_raw") or "raw_" in n or n in {"raw_value", "value_raw"}:
        roles.append("raw_value")
    if n.endswith("_normalized") or n.endswith("_parsed") or n in {"population", "year", "observation_year"}:
        roles.append("interpreted_value")
    return roles


def _quality_class(value: Any) -> str:
    text = str(value).casefold()
    if re.search(r"protect|confidential|perturb|privacy|защит|конфиденц|скрыт|возмущ", text):
        return "protected_or_perturbed"
    if re.search(r"round|rounded|округл|тыс\.?|approx|estimated|оценоч|приблиз", text):
        return "rounded_or_estimated"
    if re.search(r"exact|official|primary|direct|точн|официальн|прям", text):
        return "explicit_exact_or_official_label"
    if re.search(r"raw|cached|cache|сыр|кэш", text):
        return "raw_or_cached_label"
    return "unclassified_label"


def _is_year_field(name: str) -> bool:
    parts = _norm(name).split("_")
    if any(part in {"evidence", "text", "rule", "scope", "trusted", "status", "count", "flag", "note"} for part in parts):
        return False
    if parts and parts[0] == "is":
        return False
    if "year" in parts or "год" in parts:
        return True
    return False


def _is_temporal_field(name: str) -> bool:
    n = _norm(name)
    parts = set(n.split("_"))
    return _is_year_field(name) or bool(
        parts & {"date", "datetime", "дата", "time", "время", "effective", "modified", "timestamp"}
        or {"valid", "from"} <= parts
        or {"valid", "to"} <= parts
        or {"point", "in", "time"} <= parts
    )


def _year_field_inventory(conn: duckdb.DuckDBPyConnection, schema: str, table: str,
                          column: str) -> dict[str, Any]:
    field = _ident(column)
    source = _qualified(schema, table)
    value_expr = f"CAST({field} AS VARCHAR)"
    if _is_year_field(column):
        # Year-valued fields must be a year itself, not arbitrary text containing
        # a four-digit token (e.g. an evidence note or identifier).
        valid_expr = f"regexp_matches({value_expr}, '^[0-9]{{4}}([.]0+)?$')"
        year_expr = f"regexp_extract({value_expr}, '^([0-9]{{4}})', 1)"
    else:
        # Date/time columns may begin with YYYY-MM-DD or Wikidata's +YYYY-… form.
        valid_expr = f"regexp_matches({value_expr}, '^[+]?[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}')"
        year_expr = f"regexp_extract({value_expr}, '^[+]?([0-9]{{4}})-', 1)"
    rows = conn.execute(
        f"SELECT {year_expr} AS year_text, COUNT(*) AS row_count "
        f"FROM {source} WHERE {field} IS NOT NULL AND {valid_expr} "
        f"GROUP BY 1 ORDER BY 1"
    ).fetchall()
    missing = conn.execute(f"SELECT COUNT(*) FROM {source} WHERE {field} IS NULL").fetchone()[0]
    return {
        "field": column,
        "field_role": "year" if _is_year_field(column) else "date_or_time",
        "rows_with_valid_year_value": sum(int(row[1]) for row in rows),
        "null_rows": int(missing),
        "year_value_counts": {str(year): int(count) for year, count in rows},
        "interpretation": "A strictly formatted year/date is inventoried as recorded; it does not certify the population's reference date.",
    }


def _quality_values(conn: duckdb.DuckDBPyConnection, schema: str, table: str,
                    column: str, row_count: int, max_distinct: int = 64) -> dict[str, Any]:
    source, field = _qualified(schema, table), _ident(column)
    distinct = int(conn.execute(f"SELECT COUNT(DISTINCT CAST({field} AS VARCHAR)) FROM {source}").fetchone()[0])
    result: dict[str, Any] = {"field": column, "distinct_nonnull_values": distinct}
    if distinct <= max_distinct:
        values = conn.execute(
            f"SELECT CAST({field} AS VARCHAR), COUNT(*) FROM {source} "
            f"WHERE {field} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {max_distinct}"
        ).fetchall()
        result["value_counts"] = [
            {"value_raw": value, "row_count": int(count), "classification": _quality_class(value)}
            for value, count in values
        ]
    else:
        result["value_counts"] = None
    result["null_rows"] = int(row_count) - int(conn.execute(
        f"SELECT COUNT({field}) FROM {source}"
    ).fetchone()[0])
    return result


def inspect_legacy_database(path: Path, expected_sha256: str) -> dict[str, Any]:
    """Return a read-only table/schema inventory after enforcing the pinned hash."""
    receipt = verify_database(path, expected_sha256)
    conn = duckdb.connect(receipt["path"], read_only=True)
    try:
        tables = conn.execute(
            "SELECT table_schema, table_name, table_type FROM information_schema.tables "
            "WHERE table_schema NOT IN ('information_schema', 'pg_catalog') "
            "ORDER BY table_schema, table_name"
        ).fetchall()
        records = []
        for schema, table, table_type in tables:
            source = _qualified(schema, table)
            row_count = int(conn.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0])
            columns = conn.execute(
                "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                "WHERE table_schema = ? AND table_name = ? ORDER BY ordinal_position",
                [schema, table],
            ).fetchall()
            column_records = [
                {"name": name, "type": data_type, "nullable": nullable == "YES", "roles": _field_roles(name)}
                for name, data_type, nullable in columns
            ]
            role_columns = {role: [c["name"] for c in column_records if role in c["roles"]]
                            for role in ("population", "identifier_or_code", "temporal", "provenance",
                                         "quality_or_precision_evidence", "raw_value", "interpreted_value")}
            temporal_columns = [c["name"] for c in column_records if _is_temporal_field(c["name"])]
            quality_columns = [c["name"] for c in column_records if "quality_or_precision_evidence" in c["roles"]]
            candidate = bool(role_columns["population"] or role_columns["identifier_or_code"])
            year_inventory = [_year_field_inventory(conn, schema, table, col) for col in temporal_columns]
            quality_inventory = [_quality_values(conn, schema, table, col, row_count) for col in quality_columns]
            evidence_presence = {}
            for role in ("population", "identifier_or_code", "temporal", "provenance", "quality_or_precision_evidence"):
                evidence_presence[role] = {}
                for name in role_columns[role]:
                    field = _ident(name)
                    nonnull = int(conn.execute(f"SELECT COUNT({field}) FROM {source}").fetchone()[0])
                    evidence_presence[role][name] = {"nonnull_rows": nonnull, "null_rows": row_count - nonnull}
            records.append({
                "schema": schema, "table": table, "table_type": table_type, "row_count": row_count,
                "columns": column_records, "candidate_for_population_or_code_history": candidate,
                "field_role_columns": role_columns, "temporal_fields": year_inventory,
                "quality_or_precision_value_counts": quality_inventory,
                "evidence_field_presence": evidence_presence,
                "read_only_inventory_caveat": "Table-level labels and date tokens are candidate metadata, not certification of census scope, source exactness, or identity.",
            })
        return {
            "inventory_version": INVENTORY_VERSION,
            "database": receipt,
            "read_only": True,
            "table_count": len(records),
            "candidate_table_count": sum(r["candidate_for_population_or_code_history"] for r in records),
            "tables": records,
        }
    finally:
        conn.close()


def _check_external_output(path: Path) -> Path:
    output = Path(path).expanduser().resolve()
    try:
        output.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("legacy exports must stay outside the Git checkout")
    try:
        output.relative_to(REQUIRED_EXPORT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"legacy exports must be under {REQUIRED_EXPORT_ROOT}") from exc
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def export_selected_rows(path: Path, expected_sha256: str, schema: str, table: str,
                         columns: Sequence[str], output_path: Path,
                         equals: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Export explicitly named rows/columns to external Parquet; source DB stays read-only."""
    if not columns or len(set(columns)) != len(columns):
        raise ValueError("provide a nonempty, duplicate-free explicit column list")
    output = _check_external_output(output_path)
    receipt = verify_database(path, expected_sha256)
    conn = duckdb.connect(receipt["path"], read_only=True)
    try:
        available = {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = ? AND table_name = ?",
            [schema, table],
        ).fetchall()}
        requested = set(columns) | set((equals or {}).keys())
        missing = requested - available
        if missing:
            raise ValueError(f"columns missing from {schema}.{table}: {sorted(missing)}")
        predicates = []
        params: list[Any] = []
        for name, value in (equals or {}).items():
            predicates.append(f"{_ident(name)} = ?")
            params.append(value)
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        query = f"SELECT {', '.join(_ident(c) for c in columns)} FROM {_qualified(schema, table)}{where}"
        row_count = int(conn.execute(f"SELECT COUNT(*) FROM {_qualified(schema, table)}{where}", params).fetchone()[0])
        # DuckDB's COPY target is a string literal; double embedded apostrophes.
        target = str(output).replace("'", "''")
        conn.execute(f"COPY ({query}) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)", params)
    finally:
        conn.close()
    return {
        "database": receipt, "schema": schema, "table": table, "columns": list(columns),
        "equals": dict(equals or {}), "row_count": row_count, "output_path": str(output),
        "output_bytes": output.stat().st_size, "output_sha256": sha256_file(output),
        "source_values_preserved_without_interpretation": True,
    }


def write_inventory(path: Path, expected_sha256: str, output_path: Path) -> dict[str, Any]:
    output = _check_external_output(output_path)
    report = inspect_legacy_database(path, expected_sha256)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"output_path": str(output), "output_bytes": output.stat().st_size,
            "output_sha256": sha256_file(output), "table_count": report["table_count"],
            "candidate_table_count": report["candidate_table_count"]}


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output-json", type=Path, required=True,
                        help=f"must be outside checkout and under {REQUIRED_EXPORT_ROOT}")
    args = parser.parse_args()
    print(json.dumps(write_inventory(args.database, args.expected_sha256, args.output_json), indent=2))


if __name__ == "__main__":
    _main()
