"""Build a bounded, provenance-preserving settlement identity candidate ledger.

This module proposes exact-key candidates only. No result is an admission. It
uses the normalized fields already present in the selected source rows and does
not repair or infer historical administrative identifiers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import gzip
import json
from collections import defaultdict
from pathlib import Path
import tempfile
from typing import Any, Iterable

import pandas as pd

SEED_LOCKED = "20261002"
SAMPLE_PER_STRATUM = 3
YEAR_PAIRS = ((2002, 2010), (2010, 2021), (2002, 2021))
FAMILY_KEYS: dict[str, tuple[str, ...]] = {
    "region_name_type": ("region_norm", "name_norm", "type_norm"),
    "region_district_name_type": ("region_norm", "district_norm", "name_norm", "type_norm"),
    # Restrict to the existing urban type enum, then allow a type change while
    # still requiring a unique region+name key within each census year.
    "urban_region_name": ("region_norm", "name_norm"),
}
URBAN_TYPE_ENUM = frozenset({"город", "пгт", "поселок городского типа"})
AGGREGATE_SCOPES = frozenset({
    "federal_city_region", "municipality", "municipal_aggregate", "region",
    "administrative_area", "territorial_aggregate",
})
LEGACY_EVIDENCE_COLUMNS = (
    "matched_to_source_record_id", "match_method", "match_score", "accepted", "quality_flag",
    "entity_year_record_count", "verified_successor_settlement_id", "identity_status",
    "identity_reasons", "identity_certified", "federal_city_region_scope", "is_territorial_aggregate",
    "population", "population_scope", "source_file", "source_sheet", "source_row",
    "source_name_raw", "settlement_name", "settlement_type", "region_raw", "district_raw",
    "municipality_raw", "source_native_id", "settlement_id",
)
PROVENANCE_FIELDS = (
    "source_record_id", "census_year", "source_file", "source_path", "source_sheet", "source_row",
    "source_native_id", "source_sha256", "source_locator", "extraction_version", "source_selection_component",
    "source_name_raw", "settlement_name", "settlement_type", "region_raw", "district_raw",
    "municipality_raw", "region_norm", "district_norm", "name_norm", "type_norm", "okato", "oktmo",
    "fias_id", "source_population_raw", "population", "population_value_quality", "population_scope",
    "is_additive_settlement_record", "entity_grain_status", "legacy_source_file", "legacy_source_sheet",
    "legacy_source_row", "legacy_source_name_raw", "legacy_settlement_name", "legacy_settlement_type",
    "legacy_region_raw", "legacy_district_raw", "legacy_municipality_raw", "legacy_matched_to_source_record_id",
    "legacy_match_method", "legacy_match_score", "legacy_accepted", "legacy_quality_flag",
    "legacy_entity_year_record_count", "legacy_identity_status", "legacy_identity_reasons",
    "legacy_identity_certified", "legacy_verified_successor_settlement_id", "legacy_population",
    "legacy_population_scope",
)
SELECTED_INPUT_COLUMNS = tuple(dict.fromkeys(
    [
        "source_record_id", "census_year", "source_file", "source_path", "source_sheet", "source_row",
        "source_native_id", "source_sha256", "source_locator", "extraction_version",
        "source_selection_component", "source_name_raw", "settlement_name", "settlement_type",
        "region_raw", "district_raw", "municipality_raw", "region_norm", "district_norm",
        "name_norm", "type_norm", "okato", "oktmo", "fias_id", "source_population_raw",
        "population", "population_value_quality", "population_scope",
        "is_additive_settlement_record", "analysis_population_additive", "entity_grain_status",
    ]
))


class CandidateError(ValueError):
    pass


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _safe(value: Any) -> Any:
    if _missing(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def _text(value: Any) -> str:
    return "" if _missing(value) else str(value)


def _complete(value: Any) -> bool:
    return not _missing(value) and bool(str(value).strip())


def _bool(value: Any) -> bool:
    if _missing(value):
        return False
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes", "да"}
    return bool(value)


def _population(value: Any) -> int | None:
    if _missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not number.is_integer():
        return None
    return int(number)


def _hash_id(prefix: str, *parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return prefix + hashlib.sha256(payload).hexdigest()[:24]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _source_rows(selected: pd.DataFrame, legacy_quality: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[int, dict[str, int]]]:
    required = {"source_record_id", "census_year", "settlement_name", "settlement_type", "region_norm", "name_norm", "type_norm", "population"}
    missing = required - set(selected.columns)
    if missing:
        raise CandidateError(f"selected source layer missing required columns: {sorted(missing)}")
    if selected.source_record_id.isna().any() or selected.source_record_id.astype("string").str.strip().eq("").any():
        raise CandidateError("selected source_record_id contains null or blank values")
    if selected.source_record_id.astype("string").duplicated().any():
        raise CandidateError("selected source_record_id is not unique")
    selected_years = pd.to_numeric(selected.census_year, errors="raise").astype(int)
    if not set(selected_years).issubset({2002, 2010, 2021}):
        raise CandidateError("selected source layer has an unexpected census year")

    legacy = legacy_quality
    if "source_record_id" not in legacy:
        raise CandidateError("legacy quality layer has no source_record_id")
    if legacy.source_record_id.isna().any() or legacy.source_record_id.astype("string").str.strip().eq("").any():
        raise CandidateError("legacy quality source_record_id contains null or blank values")
    legacy_ids = legacy.source_record_id.astype("string")
    if legacy_ids.duplicated().any():
        raise CandidateError("legacy quality layer has duplicate source_record_id values")
    legacy_columns = [column for column in LEGACY_EVIDENCE_COLUMNS if column in legacy.columns]
    legacy_records: dict[str, dict[str, Any]] = {}
    for raw in legacy[["source_record_id", *legacy_columns]].itertuples(index=False, name=None):
        legacy_records[str(raw[0])] = dict(zip(legacy_columns, raw[1:]))

    blank_counts = {year: {family: 0 for family in FAMILY_KEYS} for year in (2002, 2010, 2021)}
    rows: list[dict[str, Any]] = []
    current_columns = (
        "source_record_id", "census_year", "source_file", "source_path", "source_sheet", "source_row",
        "source_native_id", "source_sha256", "source_locator", "extraction_version",
        "source_selection_component", "source_name_raw", "settlement_name", "settlement_type",
        "region_raw", "district_raw", "municipality_raw", "region_norm", "district_norm",
        "name_norm", "type_norm", "okato", "oktmo", "fias_id", "source_population_raw",
        "population", "population_value_quality", "population_scope",
        "is_additive_settlement_record", "analysis_population_additive", "entity_grain_status",
    )
    for raw in selected.itertuples(index=False, name=None):
        raw = dict(zip(selected.columns, raw))
        sid = str(raw["source_record_id"])
        lrow = legacy_records.get(sid)
        item = {key: _safe(raw.get(key)) for key in current_columns}
        item["source_record_id"] = sid
        item["census_year"] = int(raw["census_year"])
        item["legacy_quality_join_status"] = "matched_by_exact_source_record_id" if lrow else "no_exact_legacy_source_record_id"
        for column in LEGACY_EVIDENCE_COLUMNS:
            name = f"legacy_{column}"
            item[name] = _safe((lrow or {}).get(column))
        item["current_population"] = _population(raw.get("population"))
        item["legacy_population"] = _population((lrow or {}).get("population"))
        item["is_federal_aggregate"] = (
            _text(raw.get("population_scope")).casefold() in AGGREGATE_SCOPES
            or _bool(raw.get("is_territorial_aggregate"))
            or _bool((lrow or {}).get("is_territorial_aggregate"))
            or _bool((lrow or {}).get("federal_city_region_scope"))
        )
        item["grain_explicit"] = _complete(raw.get("entity_grain_status"))
        item["grain_review_flag"] = (
            "federal_aggregate_hard_block" if item["is_federal_aggregate"]
            else "grain_explicit" if item["grain_explicit"]
            else "grain_unresolved_or_not_recorded"
        )
        quality = _text(raw.get("population_value_quality")).casefold()
        legacy_quality_flag = _text((lrow or {}).get("quality_flag")).casefold()
        item["population_confidentiality_perturbed"] = "confidential" in quality or "perturb" in quality
        item["legacy_population_confidentiality_perturbed"] = "confidential" in legacy_quality_flag or "perturb" in legacy_quality_flag
        identity_status = _text((lrow or {}).get("identity_status")).casefold()
        quality_flag = legacy_quality_flag
        item["legacy_identity_conflict"] = (
            identity_status in {"quarantined", "conflict", "rejected"}
            or "admin_mismatch" in quality_flag
            or "entity_year_collision" in quality_flag
        )
        item["legacy_same_year_collision"] = (
            (_population((lrow or {}).get("entity_year_record_count")) or 0) > 1
            or "entity_year_collision" in quality_flag
        )
        item["legacy_ordinal_route_present"] = "ordinal" in _text((lrow or {}).get("match_method")).casefold()
        item["legacy_route_is_acceptance_signal"] = False
        for family, keys in FAMILY_KEYS.items():
            if not all(_complete(raw.get(key)) for key in keys):
                blank_counts[item["census_year"]][family] += 1
        rows.append(item)
    return rows, blank_counts


def _endpoint(item: dict[str, Any]) -> dict[str, Any]:
    result = {field: _safe(item.get(field)) for field in PROVENANCE_FIELDS}
    result.update({
        "legacy_quality_join_status": item["legacy_quality_join_status"],
        "is_federal_aggregate": item["is_federal_aggregate"],
        "grain_explicit": item["grain_explicit"],
        "grain_review_flag": item["grain_review_flag"],
        "population_confidentiality_perturbed": item["population_confidentiality_perturbed"],
        "legacy_population_confidentiality_perturbed": item["legacy_population_confidentiality_perturbed"],
        "legacy_identity_conflict": item["legacy_identity_conflict"],
        "legacy_same_year_collision": item["legacy_same_year_collision"],
        "legacy_ordinal_route_present": item["legacy_ordinal_route_present"],
        "legacy_route_is_acceptance_signal": False,
    })
    return result


def _family_applies(item: dict[str, Any], family: str) -> bool:
    if family != "urban_region_name":
        return True
    return _text(item.get("type_norm")) in URBAN_TYPE_ENUM


def _risk_class(from_items: list[dict[str, Any]], to_items: list[dict[str, Any]], *, region_mismatch: bool = False) -> str:
    values = from_items + to_items
    if any(v["is_federal_aggregate"] for v in values):
        return "aggregate_block"
    if any(v["legacy_identity_conflict"] or v["legacy_same_year_collision"] for v in values):
        return "legacy_identity_or_collision_risk"
    if region_mismatch:
        return "cross_region_or_admin_change"
    if any(not _complete(v.get("district_norm")) for v in values):
        return "district_context_missing"
    return "same_region_low_flag_count"


def _population_band(values: Iterable[int | None]) -> str:
    known = [int(v) for v in values if v is not None]
    if not known:
        return "unknown"
    maximum = max(known)
    if maximum < 1000:
        return "under_1k"
    if maximum < 10000:
        return "1k_to_9k"
    if maximum < 100000:
        return "10k_to_99k"
    return "100k_plus"


def _region_stratum(from_regions_json: str, to_regions_json: str) -> str:
    return "same_region" if from_regions_json == to_regions_json else "cross_or_competing_regions"


def _key_map(rows: list[dict[str, Any]], family: str, keys: tuple[str, ...], year: int) -> tuple[dict[tuple[str, ...], list[dict[str, Any]]], int]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    blank = 0
    for item in rows:
        if item["census_year"] != year or not _family_applies(item, family):
            continue
        values = tuple(_text(item.get(key)) for key in keys)
        if not all(_complete(value) for value in values):
            blank += 1
            continue
        groups.setdefault(values, []).append(item)
    return groups, blank


def _group_row(
    family: str,
    candidate_kind: str,
    year_from: int,
    year_to: int,
    key_fields: tuple[str, ...],
    key_values: tuple[str, ...],
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    flags: list[str] | None = None,
    direction: str = "cross_year",
    include_endpoint_evidence: bool = True,
) -> dict[str, Any]:
    left_ids = sorted(v["source_record_id"] for v in left)
    right_ids = sorted(v["source_record_id"] for v in right)
    left_regions = sorted({_text(v.get("region_norm")) for v in left if _complete(v.get("region_norm"))})
    right_regions = sorted({_text(v.get("region_norm")) for v in right if _complete(v.get("region_norm"))})
    region_mismatch = bool(left_regions and right_regions and set(left_regions).isdisjoint(right_regions))
    key_json = _json(dict(zip(key_fields, key_values)))
    key_hash = hashlib.sha256(key_json.encode("utf-8")).hexdigest()[:20]
    source_members = left + right
    all_flags = set(flags or [])
    if any(v["is_federal_aggregate"] for v in source_members):
        all_flags.add("federal_aggregate_hard_block")
    if any(v["legacy_identity_conflict"] for v in source_members):
        all_flags.add("legacy_identity_conflict_present")
    if any(v["legacy_same_year_collision"] for v in source_members):
        all_flags.add("legacy_same_year_collision_present")
    if any(not v["grain_explicit"] for v in source_members):
        all_flags.add("grain_unresolved_or_not_explicit")
    if any(v["legacy_ordinal_route_present"] for v in source_members):
        all_flags.add("legacy_ordinal_route_preserved_not_used_for_admission")
    types_from = sorted({_text(v.get("type_norm")) for v in left if _complete(v.get("type_norm"))})
    types_to = sorted({_text(v.get("type_norm")) for v in right if _complete(v.get("type_norm"))})
    if types_from and types_to and set(types_from).isdisjoint(types_to):
        all_flags.add("type_change_or_type_mismatch")
    if region_mismatch:
        all_flags.add("region_mismatch_or_administrative_change")
    pop_from = [_population(v.get("current_population")) for v in left]
    pop_to = [_population(v.get("current_population")) for v in right]
    candidate_id = _hash_id(
        "CAND-", family, str(year_from), str(year_to), candidate_kind, key_json,
        _json(left_ids), _json(right_ids), direction,
    )
    result = {
        "candidate_id": candidate_id,
        "candidate_family": family,
        "candidate_kind": candidate_kind,
        "year_from": year_from,
        "year_to": year_to,
        "year_pair": f"{year_from}-{year_to}",
        "direction": direction,
        "key_fields": _json(list(key_fields)),
        "key_values": key_json,
        "key_hash": key_hash,
        "from_source_record_id": left_ids[0] if len(left_ids) == 1 else None,
        "to_source_record_id": right_ids[0] if len(right_ids) == 1 else None,
        "from_candidate_ids_json": _json(left_ids),
        "to_candidate_ids_json": _json(right_ids),
        "from_candidate_count": len(left),
        "to_candidate_count": len(right),
        "potential_cartesian_pair_count_not_materialized": len(left) * len(right),
        "from_known_population": sum(v for v in pop_from if v is not None),
        "to_known_population": sum(v for v in pop_to if v is not None),
        "from_unknown_population_rows": sum(v is None for v in pop_from),
        "to_unknown_population_rows": sum(v is None for v in pop_to),
        "from_population_band": _population_band(pop_from),
        "to_population_band": _population_band(pop_to),
        "population_band": _population_band(pop_from + pop_to),
        "from_regions_json": _json(left_regions),
        "to_regions_json": _json(right_regions),
        "region_risk_class": _risk_class(
            left, right,
            region_mismatch=region_mismatch or "region_mismatch_or_administrative_change" in all_flags,
        ),
        "region_mismatch": region_mismatch,
        "type_change_or_mismatch": "type_change_or_type_mismatch" in all_flags,
        "within_year_key_collision": len(left) > 1 or len(right) > 1,
        "federal_aggregate_block": any(v["is_federal_aggregate"] for v in source_members),
        "grain_explicit_all_endpoints": all(v["grain_explicit"] for v in source_members),
        "legacy_identity_conflict_present": any(v["legacy_identity_conflict"] for v in source_members),
        "legacy_same_year_collision_present": any(v["legacy_same_year_collision"] for v in source_members),
        "legacy_ordinal_route_present_not_acceptance_signal": any(v["legacy_ordinal_route_present"] for v in source_members),
        "source_population_quality_from_json": _json(sorted({_text(v.get("population_value_quality")) for v in left})),
        "source_population_quality_to_json": _json(sorted({_text(v.get("population_value_quality")) for v in right})),
        "confidentiality_perturbation_present": any(v["population_confidentiality_perturbed"] or v["legacy_population_confidentiality_perturbed"] for v in source_members),
        "ambiguity_flags_json": _json(sorted(all_flags)),
        "admission_status": "candidate_only_no_admission",
        "candidate_method_note": "exact pre-existing normalized fields only; identifiers and legacy route are preserved, never silently repaired or used as proof",
    }
    if include_endpoint_evidence:
        result["from_endpoint_evidence_json"] = _json([_endpoint(v) for v in sorted(left, key=lambda x: x["source_record_id"])])
        result["to_endpoint_evidence_json"] = _json([_endpoint(v) for v in sorted(right, key=lambda x: x["source_record_id"])])
    return result


def _iter_same_key_candidates(rows: list[dict[str, Any]], include_endpoint_evidence: bool = True):
    for family, keys in FAMILY_KEYS.items():
        maps = {year: _key_map(rows, family, keys, year)[0] for year in (2002, 2010, 2021)}
        for year_from, year_to in YEAR_PAIRS:
            from_map, to_map = maps[year_from], maps[year_to]
            for key in sorted(set(from_map).intersection(to_map)):
                left, right = from_map[key], to_map[key]
                kind = "unique_exact_key_pair" if len(left) == len(right) == 1 else "ambiguous_competing_key_group"
                yield _group_row(family, kind, year_from, year_to, keys, key, left, right,
                                 include_endpoint_evidence=include_endpoint_evidence)
        # Release a family's key maps before building the next candidate family.
        del maps


def _iter_change_screens(rows: list[dict[str, Any]], include_endpoint_evidence: bool = True):
    screen_configs = (
        ("region_mismatch_screen", ("name_norm", "type_norm"), "region_mismatch"),
        ("type_transition_screen", ("region_norm", "name_norm"), "type_change"),
    )
    for family, keys, screen in screen_configs:
        maps_by_year: dict[int, dict[tuple[str, ...], list[dict[str, Any]]]] = {}
        for year in (2002, 2010, 2021):
            groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
            for item in rows:
                if item["census_year"] != year or (family == "type_transition_screen" and not _family_applies(item, "urban_region_name")):
                    continue
                vals = tuple(_text(item.get(key)) for key in keys)
                if not all(_complete(val) for val in vals):
                    continue
                groups.setdefault(vals, []).append(item)
            maps_by_year[year] = groups
        for year_from, year_to in YEAR_PAIRS:
            a, b = maps_by_year[year_from], maps_by_year[year_to]
            for key in sorted(set(a).intersection(b)):
                left, right = a[key], b[key]
                regions_from = {_text(v.get("region_norm")) for v in left if _complete(v.get("region_norm"))}
                regions_to = {_text(v.get("region_norm")) for v in right if _complete(v.get("region_norm"))}
                types_from = {_text(v.get("type_norm")) for v in left if _complete(v.get("type_norm"))}
                types_to = {_text(v.get("type_norm")) for v in right if _complete(v.get("type_norm"))}
                if screen == "region_mismatch" and regions_from == regions_to:
                    if len(left) == len(right) == 1 and next(iter(regions_from), None) == next(iter(regions_to), None):
                        continue
                    if not (regions_from != regions_to or len(regions_from) > 1 or len(regions_to) > 1):
                        continue
                if screen == "type_change" and types_from == types_to:
                    if len(left) == len(right) == 1 and next(iter(types_from), None) == next(iter(types_to), None):
                        continue
                    if not (types_from != types_to or len(types_from) > 1 or len(types_to) > 1):
                        continue
                flags = ["screen_only_no_candidate_admission", "region_mismatch_or_administrative_change" if screen == "region_mismatch" else "type_change_or_type_mismatch"]
                yield _group_row(family, f"{screen}_screen_group", year_from, year_to, keys, key, left, right,
                                 flags=flags, include_endpoint_evidence=include_endpoint_evidence)


def _iter_ledger_rows(rows: list[dict[str, Any]], include_endpoint_evidence: bool = True):
    yield from _iter_same_key_candidates(rows, include_endpoint_evidence)
    yield from _iter_change_screens(rows, include_endpoint_evidence)


def _sample(ledger: pd.DataFrame, max_per_stratum: int = SAMPLE_PER_STRATUM) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame(columns=["candidate_id", "sample_stratum", "sample_rank", "seed_locked"])
    sample_rows = []
    work = ledger.copy()
    work["region_stratum"] = [
        _region_stratum(a, b) for a, b in zip(work.from_regions_json, work.to_regions_json)
    ]
    strata = ["candidate_family", "year_pair", "population_band", "region_risk_class", "region_stratum"]
    for values, group in work.groupby(strata, dropna=False, sort=True):
        ranked = group.assign(_rank=group.candidate_id.map(
            lambda candidate_id: hashlib.sha256(f"{SEED_LOCKED}\0{candidate_id}".encode()).hexdigest()
        )).sort_values(["_rank", "candidate_id"], kind="stable").head(max_per_stratum)
        for rank, row in enumerate(ranked.itertuples(index=False), start=1):
            sample_rows.append({
                "candidate_id": row.candidate_id,
                "candidate_family": row.candidate_family,
                "year_pair": row.year_pair,
                "population_band": row.population_band,
                "region_risk_class": row.region_risk_class,
                "region_stratum": row.region_stratum,
                "candidate_kind": row.candidate_kind,
                "sample_rank": rank,
                "sample_stratum": _json(dict(zip(strata, values if isinstance(values, tuple) else (values,)))),
                "seed_locked": SEED_LOCKED,
                "review_unit": "pair" if row.candidate_kind == "unique_exact_key_pair" else "candidate_key_group",
                "precision_interpretation": "fixed deterministic review sample; not a national probability estimate",
            })
    return pd.DataFrame(sample_rows).sort_values(["candidate_family", "year_pair", "sample_stratum", "sample_rank"], kind="stable").reset_index(drop=True)


def build_candidate_ledger(selected: pd.DataFrame, legacy_quality: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    rows, blank_counts = _source_rows(selected, legacy_quality)
    raw_records = []
    for family, keys in FAMILY_KEYS.items():
        for year in (2002, 2010, 2021):
            blank = sum(1 for item in rows if item["census_year"] == year and _family_applies(item, family) and not all(_complete(item.get(key)) for key in keys))
            raw_records.append({"candidate_family": family, "year": year, "source_rows": sum(1 for v in rows if v["census_year"] == year and _family_applies(v, family)), "blank_or_missing_key_rows_not_joined": blank})
    ledger_rows = list(_iter_ledger_rows(rows))
    ledger = pd.DataFrame(ledger_rows)
    if ledger.empty:
        raise CandidateError("candidate ledger unexpectedly empty")
    if ledger.candidate_id.duplicated().any():
        raise CandidateError("stable candidate ID collision")
    if not ledger.admission_status.eq("candidate_only_no_admission").all():
        raise CandidateError("candidate builder emitted a non-candidate admission status")
    sample = _sample(ledger)

    summaries = []
    for (family, year_pair), group in ledger.groupby(["candidate_family", "year_pair"], sort=True):
        exact = group[group.candidate_kind.eq("unique_exact_key_pair")]
        ambiguous = group[group.candidate_kind.eq("ambiguous_competing_key_group")]
        summaries.append({
            "candidate_family": family,
            "year_pair": year_pair,
            "unique_exact_key_candidate_pairs": int(len(exact)),
            "ambiguous_competing_key_groups": int(len(ambiguous)),
            "change_screen_groups": int(group.candidate_kind.str.endswith("_screen_group").sum()),
            "aggregate_blocked_unique_pairs": int(exact.federal_aggregate_block.sum()),
            "legacy_conflict_unique_pairs": int(exact.legacy_identity_conflict_present.sum()),
            "legacy_collision_unique_pairs": int(exact.legacy_same_year_collision_present.sum()),
            "known_population_mass_from_unique_pairs": int(exact.from_known_population.sum()),
            "known_population_mass_to_unique_pairs": int(exact.to_known_population.sum()),
            "unknown_population_endpoint_rows_from_unique_pairs": int(exact.from_unknown_population_rows.sum()),
            "unknown_population_endpoint_rows_to_unique_pairs": int(exact.to_unknown_population_rows.sum()),
            "ambiguous_endpoint_records_from": int(ambiguous.from_candidate_count.sum()),
            "ambiguous_endpoint_records_to": int(ambiguous.to_candidate_count.sum()),
            "ambiguous_known_population_from": int(ambiguous.from_known_population.sum()),
            "ambiguous_known_population_to": int(ambiguous.to_known_population.sum()),
            "admission_status": "candidate_only_no_admission",
        })
    audit = {
        "status": "candidate_ledger_only_no_admissions",
        "rule_version": "exact_existing_normalized_keys_v1",
        "seed_locked": SEED_LOCKED,
        "stratified_sample_cap_per_family_year_pair_population_band_region_risk_stratum": SAMPLE_PER_STRATUM,
        "sample_note": "Seed-hash ranking is deterministic and fixed; sample is for case review planning, not national accuracy estimation.",
        "year_pairs": [f"{a}-{b}" for a, b in YEAR_PAIRS],
        "families": {family: list(keys) for family, keys in FAMILY_KEYS.items()},
        "urban_type_enum": sorted(URBAN_TYPE_ENUM),
        "population_mass_note": "Known endpoint masses are separate by census year and candidate family; unknown counts remain explicit. Do not sum across candidate families or across year endpoints.",
        "identifier_note": "OKATO/OKTMO/FIAS values and raw source labels are preserved in endpoint evidence and are not silently corrected or used as matching keys.",
        "legacy_route_note": "Legacy ordinal/match method, accepted flag and identity flags are preserved as risk context only; none is an acceptance signal.",
        "count_note": "Ambiguity groups summarize key collisions linearly; potential Cartesian pair counts are reported but never materialized.",
        "candidate_count_not_additive_across_families": True,
        "source_key_completeness": raw_records,
        "candidate_summary": summaries,
        "counts": {
            "candidate_ledger_rows": int(len(ledger)),
            "unique_exact_key_pair_rows": int(ledger.candidate_kind.eq("unique_exact_key_pair").sum()),
            "ambiguous_competing_key_groups": int(ledger.candidate_kind.eq("ambiguous_competing_key_group").sum()),
            "region_mismatch_screen_groups": int(ledger.candidate_kind.eq("region_mismatch_screen_group").sum()),
            "type_transition_screen_groups": int(ledger.candidate_kind.eq("type_change_screen_group").sum()),
            "stratified_review_sample_rows": int(len(sample)),
            "admissions_created": 0,
        },
    }
    return ledger, sample, audit


def _review_sample_row(row: dict[str, Any], rank: str, sample_rank: int) -> dict[str, Any]:
    regions = _region_stratum(row["from_regions_json"], row["to_regions_json"])
    strata = {
        "candidate_family": row["candidate_family"],
        "year_pair": row["year_pair"],
        "population_band": row["population_band"],
        "region_risk_class": row["region_risk_class"],
        "region_stratum": regions,
    }
    return {
        "candidate_id": row["candidate_id"],
        "candidate_family": row["candidate_family"],
        "year_pair": row["year_pair"],
        "population_band": row["population_band"],
        "region_risk_class": row["region_risk_class"],
        "region_stratum": regions,
        "candidate_kind": row["candidate_kind"],
        "sample_rank": sample_rank,
        "sample_stratum": _json(strata),
        "sample_hash_rank": rank,
        "seed_locked": SEED_LOCKED,
        "review_unit": "pair" if row["candidate_kind"] == "unique_exact_key_pair" else "candidate_key_group",
        "precision_interpretation": "fixed deterministic review sample; not a national probability estimate",
    }


def _write_streaming_ledger(rows: list[dict[str, Any]], ledger_path: Path, sample_path: Path) -> dict[str, Any]:
    summaries: dict[tuple[str, str], dict[str, Any]] = {}
    candidate_kind_counts: dict[str, int] = defaultdict(int)
    sample_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_limit = SAMPLE_PER_STRATUM
    fieldnames: list[str] | None = None
    row_count = 0
    with gzip.open(ledger_path, "wt", encoding="utf-8", newline="", compresslevel=6) as output:
        writer = None
        for row in _iter_ledger_rows(rows, include_endpoint_evidence=False):
            if fieldnames is None:
                # Endpoint attributes are published once in source_evidence.csv;
                # candidate rows carry source IDs as stable foreign keys.
                fieldnames = [key for key in row if key not in {"from_endpoint_evidence_json", "to_endpoint_evidence_json"}]
                writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="raise")
                writer.writeheader()
            assert writer is not None
            writer.writerow({key: value for key, value in row.items() if key in fieldnames})
            row_count += 1
            kind = row["candidate_kind"]
            family_pair = (row["candidate_family"], row["year_pair"])
            metrics = summaries.setdefault(family_pair, {
                "candidate_family": family_pair[0], "year_pair": family_pair[1],
                "unique_exact_key_candidate_pairs": 0, "ambiguous_competing_key_groups": 0,
                "change_screen_groups": 0, "aggregate_blocked_unique_pairs": 0,
                "legacy_conflict_unique_pairs": 0, "legacy_collision_unique_pairs": 0,
                "known_population_mass_from_unique_pairs": 0, "known_population_mass_to_unique_pairs": 0,
                "unknown_population_endpoint_rows_from_unique_pairs": 0,
                "unknown_population_endpoint_rows_to_unique_pairs": 0,
                "ambiguous_endpoint_records_from": 0, "ambiguous_endpoint_records_to": 0,
                "ambiguous_known_population_from": 0, "ambiguous_known_population_to": 0,
                "admission_status": "candidate_only_no_admission",
            })
            candidate_kind_counts[kind] += 1
            if kind == "unique_exact_key_pair":
                metrics["unique_exact_key_candidate_pairs"] += 1
                metrics["aggregate_blocked_unique_pairs"] += int(row["federal_aggregate_block"])
                metrics["legacy_conflict_unique_pairs"] += int(row["legacy_identity_conflict_present"])
                metrics["legacy_collision_unique_pairs"] += int(row["legacy_same_year_collision_present"])
                metrics["known_population_mass_from_unique_pairs"] += int(row["from_known_population"])
                metrics["known_population_mass_to_unique_pairs"] += int(row["to_known_population"])
                metrics["unknown_population_endpoint_rows_from_unique_pairs"] += int(row["from_unknown_population_rows"])
                metrics["unknown_population_endpoint_rows_to_unique_pairs"] += int(row["to_unknown_population_rows"])
            elif kind == "ambiguous_competing_key_group":
                metrics["ambiguous_competing_key_groups"] += 1
                metrics["ambiguous_endpoint_records_from"] += int(row["from_candidate_count"])
                metrics["ambiguous_endpoint_records_to"] += int(row["to_candidate_count"])
                metrics["ambiguous_known_population_from"] += int(row["from_known_population"])
                metrics["ambiguous_known_population_to"] += int(row["to_known_population"])
            elif kind.endswith("_screen_group"):
                metrics["change_screen_groups"] += 1

            region_stratum = _region_stratum(row["from_regions_json"], row["to_regions_json"])
            strata = (row["candidate_family"], row["year_pair"], row["population_band"], row["region_risk_class"], region_stratum)
            stratum_id = _json(strata)
            rank = hashlib.sha256(f"{SEED_LOCKED}\0{row['candidate_id']}".encode()).hexdigest()
            bucket = sample_buckets[stratum_id]
            existing = {item["candidate_id"]: item for item in bucket}
            existing[row["candidate_id"]] = _review_sample_row(row, rank, 0)
            ordered = sorted(existing.values(), key=lambda item: (item["sample_hash_rank"], item["candidate_id"]))[:sample_limit]
            for sample_rank, item in enumerate(ordered, start=1):
                item["sample_rank"] = sample_rank
            sample_buckets[stratum_id] = ordered
    if row_count == 0 or fieldnames is None:
        raise CandidateError("candidate ledger unexpectedly empty")

    samples = [item for bucket in sample_buckets.values() for item in bucket]
    samples.sort(key=lambda item: (item["candidate_family"], item["year_pair"], item["sample_stratum"], item["sample_rank"]))
    with sample_path.open("w", encoding="utf-8", newline="") as output:
        sample_fields = list(samples[0]) if samples else ["candidate_id", "sample_stratum"]
        writer = csv.DictWriter(output, fieldnames=sample_fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(samples)
    return {
        "summary": [summaries[key] for key in sorted(summaries)],
        "kind_counts": dict(sorted(candidate_kind_counts.items())),
        "candidate_ledger_rows": row_count,
        "sample_rows": len(samples),
        "sample_strata": len(sample_buckets),
    }


def _write_source_evidence(rows: list[dict[str, Any]], path: Path) -> int:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise CandidateError("pyarrow is required to write the compact source evidence index") from exc
    schema = pa.schema([
        ("source_record_id", pa.string()),
        ("census_year", pa.int16()),
        ("source_evidence_json", pa.string()),
    ])
    count = 0
    with pq.ParquetWriter(path, schema=schema, compression="zstd", version="2.6") as writer:
        for start in range(0, len(rows), 5000):
            chunk = rows[start:start + 5000]
            batch = pa.Table.from_pydict({
                "source_record_id": [item["source_record_id"] for item in chunk],
                "census_year": [item["census_year"] for item in chunk],
                "source_evidence_json": [_json(_endpoint(item)) for item in chunk],
            }, schema=schema)
            writer.write_table(batch, row_group_size=5000)
            count += len(chunk)
    return count


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(selected_parquet: Path, legacy_quality_parquet: Path, output_root: Path) -> dict[str, Any]:
    selected_parquet = selected_parquet.resolve()
    legacy_quality_parquet = legacy_quality_parquet.resolve()
    output_root = output_root.resolve()
    repository_root = Path(__file__).resolve().parents[2]
    try:
        output_root.relative_to(repository_root)
    except ValueError:
        pass
    else:
        raise CandidateError("output directory must be outside the Git repository")
    for label, path in (("selected parquet", selected_parquet), ("legacy quality parquet", legacy_quality_parquet)):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
    if output_root.exists():
        raise FileExistsError(f"immutable candidate output already exists: {output_root}")
    selected = pd.read_parquet(selected_parquet, columns=list(SELECTED_INPUT_COLUMNS))
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise CandidateError("pyarrow is required to inspect legacy parquet columns") from exc
    available_legacy_columns = set(pq.ParquetFile(legacy_quality_parquet).schema.names)
    if "source_record_id" not in available_legacy_columns:
        raise CandidateError("legacy quality parquet has no source_record_id")
    legacy_columns = [column for column in dict.fromkeys(["source_record_id", *LEGACY_EVIDENCE_COLUMNS])
                      if column in available_legacy_columns]
    legacy = pd.read_parquet(legacy_quality_parquet, columns=legacy_columns)
    rows, blank_counts = _source_rows(selected, legacy)
    selected_year_counts = selected.census_year.value_counts().to_dict()
    legacy_join_counts = pd.Series([r["legacy_quality_join_status"] for r in rows]).value_counts().to_dict()
    del selected, legacy
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    ledger_path = staging / "pair_candidates.csv.gz"
    sample_path = staging / "stratified_review_sample.csv"
    evidence_path = staging / "source_evidence.parquet"
    audit_path = staging / "candidate_audit.json"
    try:
        evidence_rows = _write_source_evidence(rows, evidence_path)
        streamed = _write_streaming_ledger(rows, ledger_path, sample_path)
        source_key_completeness = []
        for family in FAMILY_KEYS:
            for year in (2002, 2010, 2021):
                source_row_count = sum(1 for item in rows if item["census_year"] == year and _family_applies(item, family))
                source_key_completeness.append({
                    "candidate_family": family,
                    "year": year,
                    "source_rows": source_row_count,
                    "blank_or_missing_key_rows_not_joined": int(blank_counts[year][family]),
                })
        kind_counts = streamed["kind_counts"]
        audit = {
            "status": "candidate_ledger_only_no_admissions",
            "rule_version": "exact_existing_normalized_keys_v1",
            "seed_locked": SEED_LOCKED,
            "stratified_sample_cap_per_family_year_pair_population_band_region_risk_and_region_relationship": SAMPLE_PER_STRATUM,
            "sample_note": "Seed-hash ranking is deterministic and fixed; sample is for case review planning, not national accuracy estimation.",
            "year_pairs": [f"{a}-{b}" for a, b in YEAR_PAIRS],
            "families": {family: list(keys) for family, keys in FAMILY_KEYS.items()},
            "urban_type_enum": sorted(URBAN_TYPE_ENUM),
            "population_mass_note": "Known endpoint masses are separate by census year and candidate family; unknown counts remain explicit. Do not sum across candidate families or across year endpoints.",
            "identifier_note": "OKATO/OKTMO/FIAS values and raw source labels are preserved in endpoint evidence and are not silently corrected or used as matching keys.",
            "legacy_route_note": "Legacy ordinal/match method, accepted flag and identity flags are preserved as risk context only; none is an acceptance signal.",
            "count_note": "Ambiguity groups summarize key collisions linearly; potential Cartesian pair counts are reported but never materialized.",
            "candidate_count_not_additive_across_families": True,
            "source_evidence_note": "Raw source labels, identifiers, provenance and legacy context are stored once per source_record_id in compressed source_evidence.parquet; pair ledger endpoints reference these IDs.",
            "source_key_completeness": source_key_completeness,
            "candidate_summary": streamed["summary"],
            "legacy_quality_join_counts": {str(k): int(v) for k, v in legacy_join_counts.items()},
            "selected_row_counts_by_year": {str(k): int(v) for k, v in selected_year_counts.items()},
            "counts": {
                "candidate_ledger_rows": streamed["candidate_ledger_rows"],
                "unique_exact_key_pair_rows": kind_counts.get("unique_exact_key_pair", 0),
                "ambiguous_competing_key_groups": kind_counts.get("ambiguous_competing_key_group", 0),
                "region_mismatch_screen_groups": kind_counts.get("region_mismatch_screen_group", 0),
                "type_transition_screen_groups": kind_counts.get("type_change_screen_group", 0),
                "stratified_review_sample_rows": streamed["sample_rows"],
                "stratified_review_sample_strata": streamed["sample_strata"],
                "source_evidence_rows": evidence_rows,
                "admissions_created": 0,
            },
        }
        audit["input_roots"] = {
            "selected_parquet_root": {"input_root_role": "selected_input_root", "path": "."},
            "legacy_quality_parquet_root": {"input_root_role": "legacy_quality_input_root", "path": "."},
        }
        audit["inputs"] = {
            "selected_parquet": {"path": selected_parquet.name, "input_root_role": "selected_parquet_root", "sha256": _sha(selected_parquet), "bytes": selected_parquet.stat().st_size},
            "legacy_quality_parquet": {"path": legacy_quality_parquet.name, "input_root_role": "legacy_quality_parquet_root", "sha256": _sha(legacy_quality_parquet), "bytes": legacy_quality_parquet.stat().st_size},
        }
        builder_path = Path(__file__).resolve()
        audit["builder"] = {"path": builder_path.relative_to(repository_root).as_posix(), "input_root_role": "git_checkout", "sha256": _sha(builder_path), "bytes": builder_path.stat().st_size}
        audit["outputs"] = {
            ledger_path.name: {"sha256": _sha(ledger_path), "bytes": ledger_path.stat().st_size, "rows": streamed["candidate_ledger_rows"]},
            sample_path.name: {"sha256": _sha(sample_path), "bytes": sample_path.stat().st_size, "rows": streamed["sample_rows"]},
            evidence_path.name: {"sha256": _sha(evidence_path), "bytes": evidence_path.stat().st_size, "rows": evidence_rows},
        }
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.rename(output_root)
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-parquet", type=Path, required=True)
    parser.add_argument("--legacy-quality-parquet", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        audit = build(args.selected_parquet, args.legacy_quality_parquet, args.output_root)
    except (CandidateError, FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": audit["status"], "counts": audit["counts"], "output_root": str(args.output_root.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
