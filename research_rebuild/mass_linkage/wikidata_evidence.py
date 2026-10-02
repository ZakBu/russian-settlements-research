"""Reconstruct raw Wikidata code/point evidence for 2021 settlement observations.

This emits linkage candidates for independent review. It does not admit identity
or coordinates. P764 (OKTMO) and P721 (OKATO) can both have been copied from
one provider/source, so their agreement is not treated as independent proof.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from .coordinate_rules import haversine_km

PROPERTIES = ("P764", "P721", "P625", "P31", "P131", "P17")
CODE_PROPERTIES = {"P764": "oktmo", "P721": "okato"}
# Only these explicit type IDs are treated as known admin-only objects. Unknown
# P31 classes remain review-needed rather than silently passing a type gate.
ADMIN_ONLY_TYPE_QIDS = frozenset({
    "Q56061",  # administrative territorial entity
    "Q15642541",  # municipality
    "Q486972",  # human settlement (not admin-only; deliberately excluded)
}) - {"Q486972"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _entity_id(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return value.get("id") or (f"Q{value['numeric-id']}" if value.get("numeric-id") is not None else None)
    if isinstance(value, str):
        m = re.search(r"Q\d+", value)
        return m.group(0) if m else None
    return None


def normalize_code(value: Any) -> str | None:
    """Digits-only exact code normalization; never pads or truncates."""
    if value is None or isinstance(value, bool):
        return None
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".", 1)[0]
    if not re.fullmatch(r"\d+", s):
        return None
    return s


def _snak_value(snak: Mapping[str, Any]) -> Any:
    if snak.get("snaktype") != "value":
        return None
    return (snak.get("datavalue") or {}).get("value")


def _claim_value(prop: str, statement: Mapping[str, Any]) -> Any:
    value = _snak_value(statement.get("mainsnak") or {})
    if prop in {"P31", "P131", "P17"}:
        return _entity_id(value)
    return value


def _statement_row(qid: str, prop: str, statement: Mapping[str, Any], batch_path: str) -> dict[str, Any]:
    value = _claim_value(prop, statement)
    coord = value if prop == "P625" and isinstance(value, Mapping) else {}
    normalized = normalize_code(value) if prop in CODE_PROPERTIES else value
    if isinstance(normalized, (dict, list)):
        normalized = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "wikidata_qid": qid,
        "property": prop,
        "value_raw": json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if isinstance(value, (dict, list)) else value,
        "value_normalized": normalized,
        "statement_id": statement.get("id"),
        "rank": statement.get("rank", "normal"),
        "is_nondeprecated": statement.get("rank", "normal") != "deprecated",
        "latitude": coord.get("latitude"),
        "longitude": coord.get("longitude"),
        "precision": coord.get("precision"),
        "globe": coord.get("globe"),
        "qualifiers_json": json.dumps(statement.get("qualifiers", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "references_json": json.dumps(statement.get("references", []), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "source_file": batch_path,
    }


def _best_language(mapping: Mapping[str, Any], lang: str = "ru") -> str | None:
    item = mapping.get(lang)
    return item.get("value") if isinstance(item, Mapping) else None


def _entity_texts(entity: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    labels = entity.get("labels", {})
    aliases = entity.get("aliases", {})
    label = _best_language(labels, "ru")
    alias_values = [a.get("value") for a in aliases.get("ru", []) if a.get("value")]
    return label, sorted(set(alias_values))


def _name_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
    return " ".join(re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).split())


def _truthy_rows(paths: Iterable[Path], target_qids: set[str]) -> set[tuple[str, str, str]]:
    """Return observed (QID, property, normalized value) records for targets."""
    found: set[tuple[str, str, str]] = set()
    wanted = set(PROPERTIES)
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                qid = _entity_id(row.get("item"))
                prop = str(row.get("property", "")).rsplit("/", 1)[-1]
                if qid not in target_qids or prop not in wanted:
                    continue
                value = row.get("value")
                if prop in CODE_PROPERTIES:
                    norm = normalize_code(value)
                elif prop in {"P31", "P131", "P17"}:
                    norm = _entity_id(value)
                elif prop == "P625" and isinstance(value, Mapping):
                    norm = json.dumps(value, sort_keys=True, separators=(",", ":"))
                else:
                    norm = str(value)
                if norm is not None:
                    found.add((qid, prop, str(norm)))
    return found


def _valid_point(lat: Any, lon: Any, globe: Any) -> bool:
    try:
        return (
            globe == "http://www.wikidata.org/entity/Q2"
            and lat is not None and lon is not None
            and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
        )
    except (TypeError, ValueError):
        return False


def reconstruct(
    selected_observations: Path,
    entity_dir: Path,
    truthy_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    observation = pd.read_parquet(selected_observations)
    observation = observation.loc[observation["census_year"] == 2021].copy()
    observation["source_record_id"] = observation["source_record_id"].astype(str)
    observation["oktmo_norm"] = observation["oktmo"].map(normalize_code)
    observation["okato_norm"] = observation["okato"].map(normalize_code)

    entity_files = sorted(entity_dir.glob("batch*.json.gz"))
    entities: dict[str, dict[str, Any]] = {}
    claim_rows: list[dict[str, Any]] = []
    batch_receipts: dict[str, str] = {}
    for path in entity_files:
        batch = json.loads(gzip.open(path, "rt", encoding="utf-8").read())
        receipt = batch.get("retrieved_at_utc")
        batch_receipts[path.name] = receipt
        for qid, entity in batch.get("payload", {}).get("entities", {}).items():
            label, aliases = _entity_texts(entity)
            p31 = sorted({v for s in entity.get("claims", {}).get("P31", []) if s.get("rank", "normal") != "deprecated" if (v := _entity_id(_snak_value(s.get("mainsnak") or {})))})
            p131 = sorted({v for s in entity.get("claims", {}).get("P131", []) if s.get("rank", "normal") != "deprecated" if (v := _entity_id(_snak_value(s.get("mainsnak") or {})))})
            p17 = sorted({v for s in entity.get("claims", {}).get("P17", []) if s.get("rank", "normal") != "deprecated" if (v := _entity_id(_snak_value(s.get("mainsnak") or {})))})
            entities[qid] = {
                "wikidata_qid": qid,
                "label_ru": label,
                "aliases_ru_json": json.dumps(aliases, ensure_ascii=False),
                "description_ru": _best_language(entity.get("descriptions", {}), "ru"),
                "lastrevid": entity.get("lastrevid"),
                "modified": entity.get("modified"),
                "p31_qids_json": json.dumps(p31),
                "p131_qids_json": json.dumps(p131),
                "p17_qids_json": json.dumps(p17),
                "source_file": path.name,
                "api_retrieved_at_utc": receipt,
            }
            for prop in PROPERTIES:
                for statement in entity.get("claims", {}).get(prop, []):
                    claim_rows.append(_statement_row(qid, prop, statement, path.name))

    claims_df = pd.DataFrame(claim_rows)
    entities_df = pd.DataFrame(entities.values())
    claims_df.to_parquet(output_dir / "claims.parquet", index=False)
    entities_df.to_parquet(output_dir / "entities.parquet", index=False)

    code_qids: dict[tuple[str, str], set[str]] = defaultdict(set)
    qid_codes: dict[tuple[str, str], set[str]] = defaultdict(set)
    qid_code_claim_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in claim_rows:
        if row["property"] not in CODE_PROPERTIES or not row["is_nondeprecated"]:
            continue
        value = row["value_normalized"]
        if value:
            qid = row["wikidata_qid"]
            code_qids[(row["property"], str(value))].add(qid)
            qid_codes[(qid, row["property"])].add(str(value))
            qid_code_claim_counts[(qid, row["property"], str(value))] += 1

    source_by_oktmo: dict[str, list[int]] = defaultdict(list)
    source_by_okato: dict[str, list[int]] = defaultdict(list)
    for ix, row in observation.iterrows():
        if row["oktmo_norm"]:
            source_by_oktmo[row["oktmo_norm"]].append(ix)
        if row["okato_norm"]:
            source_by_okato[row["okato_norm"]].append(ix)

    # Truthy cache corroboration is a separate raw dump; it lacks statement
    # qualifiers/references. Keep only QIDs potentially matched by exact codes.
    candidate_qids = set()
    for code, indexes in source_by_oktmo.items():
        candidate_qids.update(code_qids.get(("P764", code), set()))
    for code, indexes in source_by_okato.items():
        candidate_qids.update(code_qids.get(("P721", code), set()))
    truthy_files = sorted(truthy_dir.glob("batch*.jsonl.gz"))
    truthy = _truthy_rows(truthy_files, candidate_qids)

    points_by_qid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in claim_rows:
        if row["property"] == "P625" and row["is_nondeprecated"]:
            row = dict(row)
            row["wgs84_valid"] = _valid_point(row["latitude"], row["longitude"], row["globe"])
            points_by_qid[row["wikidata_qid"]].append(row)

    bindings = []
    for ix, source in observation.iterrows():
        oktmo, okato = source["oktmo_norm"], source["okato_norm"]
        if not oktmo:
            continue
        qids = set(code_qids.get(("P764", oktmo), set()))
        if not qids:
            continue
        source_okato_observed = bool(okato)
        okato_qids = code_qids.get(("P721", okato), set()) if okato else set()
        for qid in sorted(qids):
            entity = entities[qid]
            types = set(json.loads(entity["p31_qids_json"]))
            same_qid_okato = bool(okato and qid in okato_qids)
            code_competition = len(code_qids[("P764", oktmo)]) > 1
            source_code_duplicate = len(source_by_oktmo[oktmo]) > 1
            object_admin_only = bool(types & ADMIN_ONLY_TYPE_QIDS)
            aliases = json.loads(entity["aliases_ru_json"])
            source_name = source.get("settlement_name") or source.get("source_name_raw")
            name_match = "exact_label" if _name_key(source_name) and _name_key(source_name) == _name_key(entity["label_ru"]) else (
                "exact_alias" if _name_key(source_name) and any(_name_key(source_name) == _name_key(alias) for alias in aliases) else "unmatched_or_missing"
            )
            point_rows = points_by_qid.get(qid, [])
            valid_points = [p for p in point_rows if p.get("wgs84_valid")]
            source_lat = source.get("latitude")
            source_lon = source.get("longitude")
            distances = [haversine_km(source_lat, source_lon, p["latitude"], p["longitude"]) for p in valid_points]
            distances = [d for d in distances if d is not None]
            source_okato_competitors = sorted(okato_qids - {qid})
            qid_other_oktmo = sorted(qid_codes.get((qid, "P764"), set()) - {oktmo})
            qid_other_okato = sorted(qid_codes.get((qid, "P721"), set()) - ({okato} if okato else set()))
            bindings.append({
                "source_record_id": source["source_record_id"],
                "census_year": 2021,
                "source_oktmo_raw": source.get("oktmo"),
                "source_oktmo_normalized": oktmo,
                "source_oktmo_length": len(oktmo),
                "source_oktmo_normalization": "digits_only_exact_no_padding_or_truncation",
                "source_okato_raw": source.get("okato"),
                "source_okato_normalized": okato,
                "source_settlement_name": source_name,
                "source_settlement_type": source.get("settlement_type"),
                "source_region": source.get("region_raw"),
                "source_district": source.get("district_raw"),
                "source_municipality": source.get("municipality_raw"),
                "wikidata_qid": qid,
                "provider_p764_oktmo_claim_count": qid_code_claim_counts[(qid, "P764", oktmo)],
                "provider_p721_okato_match_same_qid": same_qid_okato,
                "provider_okato_claim_qid_count": len(okato_qids) if okato else 0,
                "identifier_sources_independent": False,
                "identifier_independence_status": "not_established_both_census_provider_values_may_share_lineage" if same_qid_okato else "not_applicable_or_not_matching",
                "exact_p764_truthy_cache_match": (qid, "P764", oktmo) in truthy,
                "exact_p721_truthy_cache_match": bool(okato and (qid, "P721", okato) in truthy),
                "wikidata_label_ru": entity["label_ru"],
                "wikidata_aliases_ru_json": entity["aliases_ru_json"],
                "name_comparison": name_match,
                "wikidata_description_ru": entity["description_ru"],
                "wikidata_p31_qids_json": entity["p31_qids_json"],
                "wikidata_p31_ru_labels_json": json.dumps([entities[t]["label_ru"] for t in types if t in entities], ensure_ascii=False),
                "wikidata_p131_qids_json": entity["p131_qids_json"],
                "wikidata_p131_ru_labels_json": json.dumps([entities[t]["label_ru"] for t in json.loads(entity["p131_qids_json"]) if t in entities], ensure_ascii=False),
                "wikidata_p17_qids_json": entity["p17_qids_json"],
                "wikidata_p17_is_russia": "Q159" in json.loads(entity["p17_qids_json"]),
                "known_admin_only_type": object_admin_only,
                "p625_statement_count_nondeprecated": len(point_rows),
                "p625_valid_wgs84_point_count": len(valid_points),
                "source_latitude": source_lat,
                "source_longitude": source_lon,
                "minimum_p625_to_source_point_distance_km": min(distances) if distances else None,
                "p625_within_0_5km_source_point_screen": bool(distances and min(distances) <= 0.5),
                "p625_points_json": json.dumps([{"statement_id": p["statement_id"], "latitude": p["latitude"], "longitude": p["longitude"], "precision": p["precision"], "globe": p["globe"], "rank": p["rank"], "references_json": p["references_json"], "source_file": p["source_file"]} for p in point_rows], ensure_ascii=False, sort_keys=True),
                "competing_qids_for_p764_code": code_competition,
                "competing_qids_for_source_p721_code_json": json.dumps(source_okato_competitors),
                "qid_has_other_nondeprecated_p764_values_json": json.dumps(qid_other_oktmo),
                "qid_has_other_nondeprecated_p721_values_json": json.dumps(qid_other_okato),
                "duplicate_source_observations_for_oktmo": source_code_duplicate,
                "source_okato_present": source_okato_observed,
                "identity_decision": "candidate_only_no_acceptance",
                "coordinate_decision": "candidate_only_no_acceptance",
                "review_flags_json": json.dumps([flag for flag, yes in [
                    ("competing_qids_for_p764_code", code_competition),
                    ("duplicate_source_observations_for_oktmo", source_code_duplicate),
                    ("known_admin_only_type", object_admin_only),
                    ("name_not_exact_label_or_alias", name_match == "unmatched_or_missing"),
                    ("wikidata_p17_not_explicit_russia", "Q159" not in json.loads(entity["p17_qids_json"])),
                    ("qid_has_multiple_p625_points", len(point_rows) > 1),
                    ("p625_not_within_0_5km_source_point_screen", not (distances and min(distances) <= 0.5)),
                    ("source_p721_matches_other_qid", bool(source_okato_competitors)),
                    ("qid_has_other_oktmo_values", bool(qid_other_oktmo)),
                    ("qid_has_other_okato_values", bool(qid_other_okato)),
                    ("no_nondeprecated_p625_point", not point_rows),
                    ("no_valid_wgs84_p625_point", bool(point_rows) and not valid_points),
                    ("label_admin_or_type_requires_human_context_review", True),
                ] if yes]),
                "coordinate_provider_id": qid,
                "coordinate_source_record_id": f"wikidata:{qid}",
                "coordinate_provider": "Wikidata P625",
            })
    bindings_df = pd.DataFrame(bindings)
    bindings_df.to_parquet(output_dir / "point_bindings.parquet", index=False)

    counts = {
        "source_2021_rows": int(len(observation)),
        "source_rows_with_exact_11_digit_oktmo": int(observation["oktmo_norm"].map(lambda x: bool(x and len(x) == 11)).sum()),
        "source_rows_short_or_other_length_oktmo": int(observation["oktmo_norm"].map(lambda x: bool(x and len(x) != 11)).sum()),
        "source_oktmo_code_length_frequency": {str(k): int(v) for k, v in observation["oktmo_norm"].dropna().map(len).value_counts().sort_index().items()},
        "source_rows_with_okato": int(observation["okato_norm"].notna().sum()),
        "unique_entities_cached": int(len(entities_df)),
        "claim_statements_exported": int(len(claims_df)),
        "candidate_bindings": int(len(bindings_df)),
        "candidate_bindings_same_qid_okato_match": int(bindings_df.get("provider_p721_okato_match_same_qid", pd.Series(dtype=bool)).sum()),
        "candidate_bindings_competing_p764_qids": int(bindings_df.get("competing_qids_for_p764_code", pd.Series(dtype=bool)).sum()),
        "candidate_bindings_known_admin_only": int(bindings_df.get("known_admin_only_type", pd.Series(dtype=bool)).sum()),
        "candidate_bindings_with_any_valid_p625": int(bindings_df.get("p625_valid_wgs84_point_count", pd.Series(dtype=int)).gt(0).sum()),
        "candidate_bindings_name_exact_label_or_alias": int(bindings_df.get("name_comparison", pd.Series(dtype=str)).isin(["exact_label", "exact_alias"]).sum()),
        "candidate_bindings_within_0_5km_source_point_screen": int(bindings_df.get("p625_within_0_5km_source_point_screen", pd.Series(dtype=bool)).sum()),
    }
    # Diagnostic only: count how many 10-digit source strings would gain a
    # P764 candidate by adding one leading zero. Never use this transformation
    # for binding absent a fixed-width external classifier and source proof.
    leftpad_diagnostic = Counter()
    for code in source_by_oktmo:
        if len(code) == 10:
            qids = code_qids.get(("P764", "0" + code), set())
            leftpad_diagnostic["unique_qid"] += int(len(qids) == 1)
            leftpad_diagnostic["competing_qids"] += int(len(qids) > 1)
            leftpad_diagnostic["no_qid"] += int(not qids)
    counts["unapplied_left_zero_diagnostic_distinct_10digit_codes"] = {k: int(v) for k, v in leftpad_diagnostic.items()}
    manifest = {
        "method": "exact nondeprecated Wikidata P764/P721 statement join to 2021 selected R2 source codes; candidates only",
        "selected_observations_file": str(selected_observations),
        "selected_observations_sha256": _sha256(selected_observations),
        "source_file_values": sorted(str(x) for x in observation.get("source_file", pd.Series(dtype=str)).dropna().unique()),
        "source_archive_evidence": ([
            {"path": "/workspace/settlements-raw/data/raw/2021/tochno_2021.zip",
             "sha256": _sha256(Path("/workspace/settlements-raw/data/raw/2021/tochno_2021.zip"))}
        ] if Path("/workspace/settlements-raw/data/raw/2021/tochno_2021.zip").is_file() else []),
        "source_code_storage_diagnostic": {
            "oktmo_column_in_original_tochno_parquet": "string",
            "original_source_contains_10_digit_values_without_leading_zero": True,
            "interpretation": "No numeric-serialization loss is demonstrated in this frozen raw artifact; source-schema fixed-width validation against an authoritative OKTMO classifier is still required before any repair.",
        },
        "entity_cache_directory": str(entity_dir),
        "entity_cache_files": [{"path": p.name, "sha256": _sha256(p), "api_retrieved_at_utc": batch_receipts.get(p.name)} for p in entity_files],
        "truthy_cache_directory": str(truthy_dir),
        "truthy_cache_files": [{"path": p.name, "sha256": _sha256(p)} for p in truthy_files],
        "truthy_claims_used_for_properties": list(PROPERTIES),
        "property_meanings": {"P764": "OKTMO", "P721": "OKATO", "P625": "coordinate location", "P31": "instance of", "P131": "located in administrative entity", "P17": "country"},
        "limitations": [
            "P764 and P721 may share a provider/source lineage; co-occurrence is not independent proof.",
            "Truthies cache records have no statement references or qualifiers; entity API statements are the claim-level evidence.",
            "No coordinate point or QID is admitted as identity; nearest-point matching is not used.",
            "OKTMO values are matched exactly at their preserved source width; no universal length gate, padding or truncation is applied.",
            "A leading-zero diagnostic is emitted for 10-digit strings but never used for binding without external fixed-width classifier validation.",
            "The 2021 raw source stores OKTMO as string; a 10-digit raw value alone does not prove that a leading zero was lost.",
            "Wikidata label, aliases, type, P131 and point are retained for review, not treated as sufficient alone.",
            "The raw source cache is a captured snapshot and may be incomplete or stale relative to current Wikidata.",
        ],
        "counts": counts,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected", type=Path, default=Path("/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet"))
    parser.add_argument("--entity-dir", type=Path, default=Path("/workspace/settlements-raw/data/raw/wikidata_entities_full"))
    parser.add_argument("--truthy-dir", type=Path, default=Path("/workspace/settlements-raw/data/raw/wikidata_truthy_claims"))
    parser.add_argument("--output", type=Path, default=Path("/workspace/settlements-work/wikidata"))
    args = parser.parse_args()
    print(json.dumps(reconstruct(args.selected, args.entity_dir, args.truthy_dir, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
