"""Build reviewable candidate links from annual module entries to 2021 NP codes.

Module data remain source assertions. A link is a staged candidate based on the
raw module title comment, a cached canonical Russian Wikipedia article, a
Wikidata article URL/QID with explicit P764, and a unique 2021 settlement row.
It does not assert that historical populations describe the same physical site.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


RAW_ASSERTIONS = Path("/workspace/settlements-work/sources/annual_module_recovery/raw_population_assertions.parquet")
ARTICLE_CACHE_DIR = Path("/workspace/settlements-raw/data/raw/wikipedia_articles")
WIDE_BINDINGS = Path("/workspace/settlements-work/wikidata/wide_v5/wide_point_bindings.parquet")
CURRENT_SOURCE = Path("/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet")
OUTPUT_DIR = Path("/workspace/settlements-work/sources/annual_module_bindings_v1")
VERSION = "annual-module-title-p764-current-np-candidates-r1"

RAW_COLUMNS = [
    "module_code", "module_key_raw", "entry_title_comment_raw", "observation_year",
    "population_value_raw", "population_value", "source_key_raw", "source_text_raw",
    "source_reference_kind", "source_date_note_raw", "source_locator", "module_locator",
    "module_sha256", "population_scope", "source_class", "exact_population_status",
]
WIDE_COLUMNS = [
    "wikidata_qid", "wikidata_tsv_article_urls_json", "wikidata_tsv_ru_labels_json",
    "wikidata_tsv_exact_p764_value_raw", "wikidata_truthy_exact_p764_claims_json",
    "wikidata_truthy_exact_p764_match", "source_oktmo_exact_digits", "source_name",
    "source_type", "source_region", "source_population_scope", "wikidata_name_exact_label",
    "wikidata_tsv_matching_rows", "wikidata_tsv_line_numbers_json",
]
CURRENT_COLUMNS = [
    "census_year", "population_scope", "analysis_population_additive", "snapshot_record_type",
    "settlement_name", "settlement_type", "region_raw", "oktmo", "source_record_id",
    "source_file", "source_row", "source_native_id", "source_sha256", "source_locator",
]


def _canonical_title_from_url(url: str) -> str | None:
    try:
        path = urllib.parse.urlsplit(url).path
        if "/wiki/" not in path:
            return None
        return urllib.parse.unquote(path.rsplit("/wiki/", 1)[1]).replace("_", " ")
    except (TypeError, ValueError):
        return None


def _page_content(page: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    revisions = page.get("revisions") or []
    revision = revisions[0] if revisions else None
    if not revision:
        return None, ""
    slots = revision.get("slots") or {}
    main = slots.get("main") or {}
    content = main.get("content", revision.get("*", ""))
    return revision, content if isinstance(content, str) else ""


def _strip_wiki_markup(value: str) -> str:
    value = re.sub(r"\[\[([^]|]+)\|([^]]+)\]\]", r"\2", value)
    value = re.sub(r"\[\[([^]]+)\]\]", r"\1", value)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    value = value.replace("{{!}}", "|").replace("<br />", " ").replace("<br>", " ")
    return re.sub(r"\s+", " ", value).strip(" \t\r\n'\"")


def _template_region(content: str) -> str | None:
    match = re.search(r"^\s*\|\s*регион\s*=\s*(.*?)\s*$", content, re.I | re.M)
    return _strip_wiki_markup(match.group(1)) if match else None


def _article_record(title: str, page: dict[str, Any], retrieved: str,
                    cache_path: str, line_number: int) -> dict[str, Any]:
    revision, content = _page_content(page)
    return {
        "canonical_title": title,
        "pageid": page.get("pageid"),
        "revision_id": revision.get("revid") if revision else None,
        "revision_timestamp": revision.get("timestamp") if revision else None,
        "revision_sha1": revision.get("sha1") if revision else None,
        "retrieved_at_utc": retrieved,
        "api_cache_path": cache_path,
        "api_cache_line": line_number,
        "is_np_russia_template": bool(re.search(r"\{\{\s*НП\+Россия\b", content, re.I)),
        "article_region_raw": _template_region(content),
        "article_content_present": bool(content),
    }


def load_raw_article_cache(cache_dir: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    paths = sorted(p for p in cache_dir.glob("*.json.gz") if not p.name.startswith("._"))
    page_count = 0
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    packet = json.loads(line)
                except json.JSONDecodeError:
                    continue
                retrieved = packet.get("retrieved_at_utc")
                pages = packet.get("payload", {}).get("query", {}).get("pages", [])
                for page in pages:
                    title = page.get("title")
                    if not title or page.get("missing") is not None:
                        continue
                    index[title].append(_article_record(title, page, retrieved, str(path), line_number))
                    page_count += 1
    return index, {"api_cache_directory": str(cache_dir), "api_cache_file_count": len(paths),
                   "api_cached_page_occurrence_count": page_count,
                   "distinct_canonical_title_count": len(index)}


def _p764_exact(row: dict[str, Any], code: str) -> bool:
    tsv = row.get("wikidata_tsv_exact_p764_value_raw")
    if str(tsv or "").strip() != code or not row.get("wikidata_truthy_exact_p764_match"):
        return False
    try:
        claims = json.loads(row.get("wikidata_truthy_exact_p764_claims_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    return any(str(c.get("value_exact_digits", "")).strip() == code for c in claims)


def _exact_title_entry(title: str, canonical_title: str) -> bool:
    """Raw module comment must exactly equal the API's canonical Russian title."""
    return bool(title) and title == canonical_title


def _annual_group_status(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Return linked, conflict-held, duplicate-held, or exact-deduplicated assertions."""
    signatures: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sig = (row["population_value_raw"], row["source_key_raw"], row["source_text_raw"],
               row["source_date_note_raw"])
        signatures[sig].append(row)
    values = {r["population_value_raw"] for r in rows}
    if len(values) > 1:
        return "held_conflicting_values", rows
    if len(signatures) > 1:
        return "held_duplicate_year_citations", rows
    if len(rows) > 1:
        row = dict(rows[0])
        row["module_locators_all"] = json.dumps(sorted(r["module_locator"] for r in rows), ensure_ascii=False)
        row["raw_duplicate_count"] = len(rows)
        row["duplicate_treatment"] = "exact_duplicate_citation_collapsed_in_binding; all raw rows remain in source parquet"
        return "exact_duplicate_collapsed", [row]
    return "linked_named_series", rows


def _module_entries(raw_rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str, int], list[dict[str, Any]]]]:
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    years: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        key = row["module_code"], row["module_key_raw"]
        entry = entries.setdefault(key, {"module_code": key[0], "module_key_raw": key[1],
                                         "title_comments": set(), "raw_row_count": 0,
                                         "observed_years": set(), "module_sha256": set()})
        entry["title_comments"].add(row["entry_title_comment_raw"])
        entry["raw_row_count"] += 1
        entry["observed_years"].add(row["observation_year"])
        entry["module_sha256"].add(row["module_sha256"])
        years[(key[0], key[1], row["observation_year"])].append(row)
    for entry in entries.values():
        entry["entry_title_comment_raw"] = next(iter(entry["title_comments"])) if len(entry["title_comments"]) == 1 else None
        entry["title_comment_count"] = len(entry["title_comments"])
        entry["observed_years"] = sorted(entry["observed_years"])
        entry["module_sha256_values"] = sorted(entry["module_sha256"])
    return entries, years


def _build_wide_title_index(wide_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in wide_rows:
        try:
            urls = json.loads(row.get("wikidata_tsv_article_urls_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        titles = {_canonical_title_from_url(url) for url in urls}
        for title in titles - {None}:
            item = dict(row)
            item["matched_article_title_from_url"] = title
            indexed[title].append(item)
    return indexed


def evaluate_entry(entry: dict[str, Any], article_records: list[dict[str, Any]],
                   wide_rows: list[dict[str, Any]], current_rows_by_code: dict[str, list[dict[str, Any]]]) -> tuple[str, str, dict[str, Any] | None]:
    """Return (status, blocker, candidate record) without consulting legacy IDs."""
    title = entry.get("entry_title_comment_raw")
    if entry["title_comment_count"] != 1 or not title:
        return "held", "module_title_comment_not_unique", None
    records = article_records
    if not records:
        return "held", "no_exact_raw_api_canonical_title", None
    pageids = {r["pageid"] for r in records if r["pageid"] is not None}
    if len(pageids) != 1:
        return "held", "raw_api_title_has_multiple_pageids", None
    # Keep the last captured page revision as the current article snapshot, with
    # all cache references retained in a compact JSON field.
    chosen = max(records, key=lambda r: (r.get("retrieved_at_utc") or "", r.get("revision_id") or 0))
    versions = {(r.get("revision_id"), r.get("revision_sha1")) for r in records}
    if not chosen["is_np_russia_template"]:
        return "held", "raw_api_article_lacks_np_russia_template_or_is_aggregate", None
    if not wide_rows:
        return "held", "no_exact_wikidata_russian_article_url", None

    signatures: dict[tuple[Any, ...], dict[str, Any]] = {}
    direct_rows = []
    for wide in wide_rows:
        qid, code = wide.get("wikidata_qid"), wide.get("source_oktmo_exact_digits")
        if not qid or not code or wide.get("source_population_scope") != "settlement":
            continue
        if not _p764_exact(wide, str(code)):
            continue
        # The raw RU label and exact label flag are separate evidence; require an
        # actual matching source label to avoid relying on the bool alone.
        try:
            labels = json.loads(wide.get("wikidata_tsv_ru_labels_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            labels = []
        if not wide.get("wikidata_name_exact_label") or wide.get("source_name") not in labels:
            continue
        direct_rows.append(wide)
    if not direct_rows:
        return "held", "no_explicit_p764_settlement_code_and_exact_ru_label", None
    signatures = {
        (r["wikidata_qid"], str(r["source_oktmo_exact_digits"]), r["source_name"], r["source_type"], r["source_region"]): r
        for r in direct_rows
    }
    qids = {s[0] for s in signatures}
    codes = {s[1] for s in signatures}
    if len(qids) != 1 or len(codes) != 1 or len(signatures) != 1:
        return "held", "wikidata_article_title_or_p764_metadata_ambiguous", None
    qid, code, wide_name, wide_type, wide_region = next(iter(signatures))
    source_rows = current_rows_by_code.get(code, [])
    if len(source_rows) != 1:
        return "held", "current_2021_source_code_not_unique", None
    source = source_rows[0]
    if (source.get("settlement_name"), source.get("settlement_type"), source.get("region_raw")) != (wide_name, wide_type, wide_region):
        return "held", "current_2021_source_name_type_region_conflict", None
    if chosen.get("article_region_raw") and chosen["article_region_raw"] != wide_region:
        return "held", "cached_article_region_conflicts_with_current_source", None
    candidate = {
        "candidate_id": f"{entry['module_code']}:{entry['module_key_raw']}",
        "module_code": entry["module_code"], "module_key_raw": entry["module_key_raw"],
        "module_key_interpretation": "opaque Lua array key; not QID or OKTMO",
        "module_title_comment_raw": title,
        "article_canonical_title": title,
        "article_pageid": chosen["pageid"],
        "article_revision_id": chosen["revision_id"],
        "article_revision_timestamp": chosen["revision_timestamp"],
        "article_revision_sha1": chosen["revision_sha1"],
        "article_retrieved_at_utc": chosen["retrieved_at_utc"],
        "article_cache_path": chosen["api_cache_path"],
        "article_cache_line": chosen["api_cache_line"],
        "article_is_np_russia_template": chosen["is_np_russia_template"],
        "article_cached_revision_count": len(versions),
        "article_cache_references_json": json.dumps([{"path": r["api_cache_path"], "line": r["api_cache_line"], "revision_id": r["revision_id"], "retrieved_at_utc": r["retrieved_at_utc"]} for r in records], ensure_ascii=False),
        "article_region_raw": chosen["article_region_raw"],
        "wikidata_qid": qid,
        "wikidata_article_url_title_raw": title,
        "wikidata_tsv_article_urls_json": next(iter(signatures.values()))["wikidata_tsv_article_urls_json"],
        "wikidata_tsv_exact_p764_value_raw": next(iter(signatures.values()))["wikidata_tsv_exact_p764_value_raw"],
        "wikidata_truthy_exact_p764_claims_json": next(iter(signatures.values()))["wikidata_truthy_exact_p764_claims_json"],
        "wikidata_tsv_ru_labels_json": next(iter(signatures.values()))["wikidata_tsv_ru_labels_json"],
        "wikidata_tsv_matching_rows": next(iter(signatures.values()))["wikidata_tsv_matching_rows"],
        "wikidata_tsv_line_numbers_json": next(iter(signatures.values()))["wikidata_tsv_line_numbers_json"],
        "current_source_oktmo_raw": source.get("oktmo"),
        "current_source_oktmo_exact_digits": code,
        "current_source_name": source.get("settlement_name"),
        "current_source_type": source.get("settlement_type"),
        "current_source_region": source.get("region_raw"),
        "current_source_population_scope": "settlement",
        "current_source_record_id": source.get("source_record_id"),
        "current_source_file": source.get("source_file"),
        "current_source_row": source.get("source_row"),
        "current_source_native_id": source.get("source_native_id"),
        "current_source_sha256": source.get("source_sha256"),
        "current_source_locator": source.get("source_locator"),
        "raw_module_sha256_values_json": json.dumps(entry["module_sha256_values"]),
        "annual_raw_row_count": entry["raw_row_count"],
        "observed_year_count": len(entry["observed_years"]),
        "observed_year_min": min(entry["observed_years"]),
        "observed_year_max": max(entry["observed_years"]),
        "observed_years_json": json.dumps(entry["observed_years"]),
        "candidate_status": "possible_strong_module_entry_to_current_np_code; pending independent review",
        "identity_chain_scope": "source_named_history_series",
        "physical_site_continuity_status": "unverified; no same-physical-place claim is made for historical years",
        "population_admission": False,
        "place_identity_admission": False,
    }
    return "candidate", "", candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(raw_assertions: Path = RAW_ASSERTIONS, article_cache_dir: Path = ARTICLE_CACHE_DIR,
        wide_path: Path = WIDE_BINDINGS, current_source_path: Path = CURRENT_SOURCE,
        output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_rows = pq.read_table(raw_assertions, columns=RAW_COLUMNS).to_pylist()
    entries, years = _module_entries(raw_rows)
    article_index, article_receipt = load_raw_article_cache(article_cache_dir)
    wide_table = pq.read_table(wide_path, columns=WIDE_COLUMNS)
    wide_title_index = _build_wide_title_index(wide_table.to_pylist())
    current_table = pq.read_table(current_source_path, columns=CURRENT_COLUMNS)
    current_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in current_table.to_pylist():
        if (row["census_year"] == 2021 and row["population_scope"] == "settlement"
                and row["analysis_population_additive"] is True
                and row["snapshot_record_type"] == "settlement_observation"
                and row["oktmo"] is not None):
            current_by_code[str(row["oktmo"])].append(row)

    decisions: list[dict[str, Any]] = []
    provisional: list[dict[str, Any]] = []
    statuses = Counter()
    for key, entry in sorted(entries.items()):
        title = entry.get("entry_title_comment_raw")
        status, reason, candidate = evaluate_entry(
            entry, article_index.get(title, []) if title else [],
            wide_title_index.get(title, []) if title else [], current_by_code)
        statuses[reason or status] += 1
        if candidate:
            provisional.append(candidate)
        decisions.append({
            "module_code": key[0], "module_key_raw": key[1],
            "module_title_comment_raw": title,
            "module_key_interpretation": "opaque Lua array key; not QID or OKTMO",
            "decision_status": status, "blocker_code": reason,
            "raw_row_count": entry["raw_row_count"],
            "observed_year_count": len(entry["observed_years"]),
            "observed_year_min": min(entry["observed_years"]),
            "observed_year_max": max(entry["observed_years"]),
            "observed_years_json": json.dumps(entry["observed_years"]),
        })
    # A title or current code resolving from multiple entries is held at the group
    # level. Never pick one based on population equality or key order.
    by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in provisional:
        by_title[row["module_title_comment_raw"]].append(row)
        by_code[row["current_source_oktmo_exact_digits"]].append(row)
    duplicate_ids: dict[str, str] = {}
    for group in by_title.values():
        if len(group) > 1:
            for row in group:
                duplicate_ids[row["candidate_id"]] = "duplicate_module_entry_title"
    for group in by_code.values():
        if len(group) > 1:
            for row in group:
                duplicate_ids[row["candidate_id"]] = "duplicate_module_entries_for_current_code"
    candidate_by_id = {}
    candidates = []
    for row in provisional:
        if row["candidate_id"] in duplicate_ids:
            row["candidate_status"] = "held_duplicate_entry_or_code"
            row["place_identity_admission"] = False
            for d in decisions:
                if d["module_code"] == row["module_code"] and d["module_key_raw"] == row["module_key_raw"]:
                    d["decision_status"] = "held"
                    d["blocker_code"] = duplicate_ids[row["candidate_id"]]
        else:
            row["candidate_status"] = "possible_strong_module_entry_to_current_np_code; pending independent review"
            candidate_by_id[row["candidate_id"]] = row
            candidates.append(row)

    # Retain all raw assertions for candidate entries. Exact duplicate citation
    # rows collapse to one binding record with every source locator preserved;
    # conflicting and multi-citation same-year groups are held.
    annual: list[dict[str, Any]] = []
    held_annual: list[dict[str, Any]] = []
    duplicate_handling = Counter()
    for (module, key, year), group in years.items():
        binding = candidate_by_id.get(f"{module}:{key}")
        if not binding:
            continue
        group_status, collapsed = _annual_group_status(group)
        duplicate_handling[group_status] += 1
        for raw in collapsed:
            record = dict(raw)
            record.update({
                "candidate_id": binding["candidate_id"],
                "wikidata_qid": binding["wikidata_qid"],
                "current_source_oktmo_exact_digits": binding["current_source_oktmo_exact_digits"],
                "current_source_name": binding["current_source_name"],
                "current_source_type": binding["current_source_type"],
                "current_source_region": binding["current_source_region"],
                "assertion_link_status": group_status,
                "identity_chain_scope": "source_named_history_series",
                "physical_site_continuity_status": "unverified; no same-physical-place claim is made for historical years",
                "population_admission": False,
                "place_identity_admission": False,
            })
            (held_annual if group_status.startswith("held_") else annual).append(record)

    annual_block_count: Counter[tuple[str, str]] = Counter()
    for (module, key, _year), group in years.items():
        status, _ = _annual_group_status(group)
        if status.startswith("held_"):
            annual_block_count[(module, key)] += 1
    for row in candidates:
        row["held_annual_year_group_count"] = annual_block_count[(row["module_code"], row["module_key_raw"])]

    # Write candidate and held files separately for clean review.
    candidate_path = output_dir / "possible_module_entry_bindings.parquet"
    held_entries_path = output_dir / "held_module_entries.parquet"
    annual_path = output_dir / "annual_assertion_binding_candidates.parquet"
    annual_held_path = output_dir / "held_annual_assertion_bindings.parquet"
    pq.write_table(pa.Table.from_pylist(candidates), candidate_path, compression="zstd")
    held_decisions = [d for d in decisions if d["decision_status"] == "held"]
    pq.write_table(pa.Table.from_pylist(held_decisions), held_entries_path, compression="zstd")
    pq.write_table(pa.Table.from_pylist(annual), annual_path, compression="zstd")
    pq.write_table(pa.Table.from_pylist(held_annual), annual_held_path, compression="zstd")
    summary = {
        "binding_version": VERSION,
        "input_receipts": {
            "annual_raw_assertions": {"path": str(raw_assertions), "sha256": _sha256(raw_assertions), "row_count": len(raw_rows)},
            "wide_wikidata_bindings": {"path": str(wide_path), "sha256": _sha256(wide_path), "row_count": wide_table.num_rows},
            "selected_current_source": {"path": str(current_source_path), "sha256": _sha256(current_source_path), "row_count": current_table.num_rows},
            "raw_article_cache": article_receipt,
            "legacy_article_index_use": "not used; candidate generation is based on raw API page cache and wide raw Wikidata evidence",
        },
        "module_entry_count": len(entries),
        "provisional_entries_passing_pairwise_rule_before_global_collision_screen": len(provisional),
        "possible_strong_candidate_entry_count_after_collision_holds": len(candidates),
        "held_module_entry_count": len(held_decisions),
        "annual_candidate_link_count": len(annual),
        "held_annual_link_count": len(held_annual),
        "place_identity_admission_count": 0,
        "population_admission_count": 0,
        "annual_duplicate_treatment_counts": dict(duplicate_handling),
        "candidate_observed_year_coverage": {
            "min_year": min((r["observed_year_min"] for r in candidates), default=None),
            "max_year": max((r["observed_year_max"] for r in candidates), default=None),
            "distinct_year_values": len({y for r in candidates for y in json.loads(r["observed_years_json"])}),
            "link_scope": "candidate source_named_history_series; not physical-place continuity",
        },
        "pairwise_decision_reason_counts": dict(statuses),
        "held_reason_counts": dict(Counter(d["blocker_code"] for d in held_decisions)),
        "limitations": [
            "Numeric module keys are opaque Lua array keys, not QIDs or OKTMO codes.",
            "The legacy database article index/crosswalk was not used as admission evidence.",
            "Each candidate joins an exact raw module comment title to the canonical article title in a raw API response, a QID's exact Russian Wikipedia URL and explicit P764 value, and one current 2021 national-source settlement row with exact code, name, type, and region agreement.",
            "Candidates remain pending independent admission. The current source code and article mapping do not certify historical physical-site continuity.",
            "Historical annual values remain Wikipedia secondary assertions with unverified primary-source precision, population scope, and historical boundaries; no value is transferred into current census records.",
            "No zero, missing year, interpolation, or municipal aggregate allocation is generated.",
        ],
        "outputs": {
            p.name: {"path": str(p), "sha256": _sha256(p), "rows": pq.read_metadata(p).num_rows, "format": "Parquet/Zstandard"}
            for p in (candidate_path, held_entries_path, annual_path, annual_held_path)
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-assertions", type=Path, default=RAW_ASSERTIONS)
    parser.add_argument("--article-cache-dir", type=Path, default=ARTICLE_CACHE_DIR)
    parser.add_argument("--wide-bindings", type=Path, default=WIDE_BINDINGS)
    parser.add_argument("--current-source", type=Path, default=CURRENT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    print(json.dumps(run(args.raw_assertions, args.article_cache_dir, args.wide_bindings,
                         args.current_source, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
