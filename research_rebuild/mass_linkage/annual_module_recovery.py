"""Recover population assertions directly from frozen Russian Wikipedia Lua modules.

The extractor treats a Lua numeric table key as a module key, never as a
settlement identity. It retains raw source text and source file hashes so the
observations can be reviewed independently of inherited place bindings.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

RAW_DIR = Path("/workspace/settlements-raw/data/raw/wikipedia_statistical")
OUTPUT_DIR = Path("/workspace/settlements-work/sources/annual_module_recovery")
CANDIDATE_PATH = Path("/workspace/settlements-work/sources/legacy_inventory/wikipedia_statistical_module_candidates.parquet")
VERSION = "raw-wikipedia-statistical-lua-recovery-r1"
ROW_RE = re.compile(r'^\s*\{\s*(\d{1,4})\s*,\s*([+-]?\d+(?:\.\d+)?)\s*,\s*(["\'])(.*?)\3\s*\}\s*,?\s*(?:--.*)?$', re.S)
QID_TABLE_RE = re.compile(r'^\s*\[(\d+)\]\s*=\s*\{\s*--\s*(.*?)\s*$', re.M)
SOURCE_ENTRY_RE = re.compile(r"^\s*\['((?:\\.|[^'])*)'\]\s*=\s*\{", re.M)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _lua_string(text: str) -> str:
    """Decode the ordinary escaped single/double quoted Lua strings in these files."""
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        # Lua supports these common escapes; unknown escapes retain their slash.
        body = text[1:-1]
        return re.sub(r"\\([\\\"'])", r"\1", body).replace(r"\n", "\n").replace(r"\t", "\t")


def _table_end(source: str, opening: int) -> int:
    """Return matching '}' for a Lua table, respecting quoted strings/comments."""
    depth, i, quote = 0, opening, None
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "-" and i + 1 < len(source) and source[i + 1] == "-":
            # Lua long comments are rare here; line comments are sufficient for the
            # frozen modules' data tables and avoid treating braces in comments as syntax.
            end = source.find("\n", i + 2)
            i = len(source) if end < 0 else end
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"unclosed Lua table at character {opening}")


def _source_refs(source: str) -> dict[str, dict[str, Any]]:
    marker = "['Источники']"
    start = source.find(marker)
    if start < 0:
        return {}
    opening = source.find("{", start)
    end = _table_end(source, opening)
    body = source[opening + 1:end]
    line_base = source.count("\n", 0, opening + 1)
    found: dict[str, dict[str, Any]] = {}
    for m in SOURCE_ENTRY_RE.finditer(body):
        key = _lua_string("'" + m.group(1) + "'")
        item_open = body.find("{", m.start())
        item_end = _table_end(body, item_open)
        literals = re.findall(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", body[item_open + 1:item_end])
        values = [_lua_string(x) for x in literals]
        found[key] = {
            "source_key": key,
            "source_text_raw": values[0] if values else None,
            "source_date_note_raw": values[1] if len(values) > 1 else None,
            # The regex's leading whitespace can consume the previous newline.
            # Locate the dictionary key itself, rather than the match boundary.
            "source_locator": f"line:{line_base + body.count(chr(10), 0, m.start(1)) + 1}",
        }
    return found


def recover_module(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse one module, returning source-level population rows and file receipt."""
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    decoded = gzip.decompress(raw).decode("utf-8-sig", errors="replace")
    module_code = path.name.removesuffix(".lua.gz")
    sources = _source_refs(decoded)
    rows: list[dict[str, Any]] = []
    for match in QID_TABLE_RE.finditer(decoded):
        module_key, title = match.group(1), match.group(2).strip()
        opening = decoded.find("{", match.start())
        closing = _table_end(decoded, opening)
        block = decoded[opening + 1:closing]
        base_line = decoded.count("\n", 0, opening + 1)
        for line_no, line in enumerate(block.splitlines(), start=base_line + 1):
            m = ROW_RE.match(line)
            if not m:
                continue
            year = int(m.group(1))
            raw_value = m.group(2)
            value = int(raw_value) if "." not in raw_value else float(raw_value)
            source_key = _lua_string(m.group(3) + m.group(4) + m.group(3))
            source = sources.get(source_key)
            rows.append({
                "module_code": module_code,
                "module_key_raw": module_key,
                "entry_title_comment_raw": title,
                "observation_year": year,
                "population_value_raw": raw_value,
                "population_value": value,
                "source_key_raw": source_key,
                # The Lua third tuple field is sometimes a source-dictionary key and
                # sometimes the literal citation itself. Preserve both cases.
                "source_text_raw": source.get("source_text_raw") if source else (source_key or None),
                "source_reference_kind": ("keyed_source_dictionary_entry" if source else
                                           "empty_source_field" if not source_key else
                                           "inline_source_text" if not re.fullmatch(r"\d{3,4}[A-Z]{1,3}", source_key) else
                                           "unresolved_source_key"),
                "source_date_note_raw": source.get("source_date_note_raw") if source else None,
                "source_locator": source.get("source_locator") if source else None,
                "module_locator": f"line:{line_no}",
                "module_sha256": digest,
                "population_scope": "as_asserted_by_wikipedia_statistical_module; object scope not independently certified",
                "source_class": "Wikipedia secondary/transcribed assertion; referenced work retained, source not fetched/verified",
                "exact_population_status": "unknown",
            })
    receipt = {
        "module_code": module_code,
        "path": str(path),
        "compressed_bytes": len(raw),
        "sha256": digest,
        "decompressed_utf8_bytes": len(decoded.encode("utf-8")),
        "source_reference_count": len(sources),
        "recovered_assertion_count": len(rows),
        "article_title": None,
        "revision_id": None,
        "metadata_note": "Frozen raw file has no embedded retrieval timestamp or revision id; neither is inferred from source dates.",
    }
    return rows, receipt


def _write_jsonl_gz(path: Path, records: Iterable[dict[str, Any]]) -> int:
    n = 0
    with gzip.open(path, "wt", encoding="utf-8", newline="\n", compresslevel=6) as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    return n


def _reconcile_candidates(rows: list[dict[str, Any]], candidate_path: Path) -> dict[str, Any]:
    """Compare literal year/value cells by module:key; do not carry candidate place IDs."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to reconcile the supplied candidate Parquet") from exc
    table = pq.read_table(candidate_path, columns=["observation_year", "population", "source_record_id"])
    raw_index: dict[tuple[str, str, int], list[Any]] = defaultdict(list)
    for row in rows:
        raw_index[(row["module_code"], row["module_key_raw"], row["observation_year"])].append(row["population_value"])
    matched = equal = missing = conflict = repeated = 0
    for batch in table.to_batches(max_chunksize=50000):
        data = batch.to_pydict()
        for year, value, record_id in zip(data["observation_year"], data["population"], data["source_record_id"]):
            try:
                module, key = record_id.split(":", 1)
            except (AttributeError, ValueError):
                missing += 1
                continue
            candidates = raw_index.get((module, key, int(year)), [])
            if not candidates:
                missing += 1
                continue
            matched += 1
            if len(candidates) > 1:
                repeated += 1
            vals = {float(x) for x in candidates}
            if float(value) in vals:
                equal += 1
            else:
                conflict += 1
    return {
        "candidate_path": str(candidate_path),
        "candidate_row_count": int(table.num_rows),
        "module_key_year_rows_matched": matched,
        "matched_rows_with_exact_value_equal_to_raw_cell": equal,
        "matched_candidate_rows_with_repeated_raw_module_key_year": repeated,
        "matched_rows_with_value_conflict": conflict,
        "candidate_rows_without_raw_module_key_year": missing,
        "binding_use": "candidate settlement_id and inherited place binding deliberately excluded; this is value-cell reconciliation only",
    }


def run(raw_dir: Path = RAW_DIR, output_dir: Path = OUTPUT_DIR,
        candidate_path: Path | None = CANDIDATE_PATH) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in raw_dir.glob("*.lua.gz") if not p.name.startswith("._"))
    if len(files) != 88:
        raise ValueError(f"expected 88 non-AppleDouble frozen modules, found {len(files)}")
    all_rows: list[dict[str, Any]] = []
    modules = []
    for path in files:
        rows, receipt = recover_module(path)
        all_rows.extend(rows)
        modules.append(receipt)
    # Row-level conflicts are reported without choosing a winner or merging records.
    years_by_key: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        years_by_key[(row["module_code"], row["module_key_raw"], row["observation_year"])].append(row)
    repeated = [
        {"module_code": k[0], "module_key_raw": k[1], "observation_year": k[2],
         "assertion_count": len(v), "distinct_values": sorted({r["population_value"] for r in v}),
         "locators": [r["module_locator"] for r in v]}
        for k, v in years_by_key.items() if len(v) > 1
    ]
    conflict_rows = [x for x in repeated if len(x["distinct_values"]) > 1]
    repeated_path = output_dir / "repeated_year_assertions.jsonl.gz"
    _write_jsonl_gz(repeated_path, repeated)
    observation_path = output_dir / "raw_population_assertions.parquet"
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to write compact columnar recovered assertions") from exc
    pq.write_table(pa.Table.from_pylist(all_rows), observation_path, compression="zstd")
    reconciliation = _reconcile_candidates(all_rows, candidate_path) if candidate_path and candidate_path.exists() else None
    source_kind_counts = dict(Counter(r["source_reference_kind"] for r in all_rows))
    source_unresolved = [r for r in all_rows if r["source_reference_kind"] == "unresolved_source_key"]
    unresolved_path = output_dir / "unresolved_source_keys.jsonl.gz"
    _write_jsonl_gz(unresolved_path, source_unresolved)
    manifest = {
        "recovery_version": VERSION,
        "input_directory": str(raw_dir),
        "source_file_count": len(files),
        "module_receipts": modules,
        "physically_verified_assertion_count": len(all_rows),
        "module_key_count": len({(r['module_code'], r['module_key_raw']) for r in all_rows}),
        "year_min": min((r["observation_year"] for r in all_rows), default=None),
        "year_max": max((r["observation_year"] for r in all_rows), default=None),
        "distinct_observed_year_count": len({r["observation_year"] for r in all_rows}),
        "repeated_module_key_year_count": len(repeated),
        "conflicting_value_module_key_year_count": len(conflict_rows),
        "source_reference_kind_counts": source_kind_counts,
        "unresolved_source_key_count": len(source_unresolved),
        "candidate_reconciliation": reconciliation,
        "outputs": {
            "raw_population_assertions": {"path": str(observation_path), "sha256": sha256_file(observation_path), "format": "Parquet/Zstandard"},
            "repeated_year_assertions": {"path": str(repeated_path), "sha256": sha256_file(repeated_path), "format": "JSONL/Gzip"},
            "unresolved_source_keys": {"path": str(unresolved_path), "sha256": sha256_file(unresolved_path), "format": "JSONL/Gzip"},
        },
        "identity_and_quality_limits": [
            "Raw numeric table keys are treated only as module array keys; names in comments, region-module membership and count equality do not establish an accepted settlement identity.",
            "All module values are preserved as secondary Wikipedia assertions with referenced source text; the cited primary works were not fetched or independently checked.",
            "Object level, census/statistical scope, territorial boundary precision, rounding/protection, and exactness are unknown unless an individual cited source establishes them.",
            "Source date notes are retained as written; retrieval dates and raw-module revision IDs are unavailable and are not inferred.",
            "No population zeros, missing-year values, interpolation or municipal aggregate allocations are generated.",
        ],
        "possible_place_bindings": {
            "accepted_count": 0,
            "reason": "This extraction found no independently verified settlement binding. Candidate file IDs are used only to reconcile module-key/year/value cells and are excluded from place identity.",
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--candidate-path", type=Path, default=CANDIDATE_PATH)
    args = parser.parse_args()
    print(json.dumps(run(args.raw_dir, args.output_dir, args.candidate_path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
