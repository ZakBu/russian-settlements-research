"""Apply conditionally reviewed ordinary identity rules to exact census keys.

Candidate generation and this application are separate. This module performs
source, grain, ambiguity, conflict, context and year-exclusive component
screens before it labels any new edge checked-rule accepted. It does not change
populations, coordinates, or dated boundary comparability.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd
import xlrd

from research_rebuild.mass_linkage.candidate_graph_checks import (
    Node, YearConstrainedUnionFind, _flag, _load_nodes, _sha,
)
from research_rebuild.mass_linkage.recover_admin_context import SHEET_PROFILES

RULE_VERSION = "conditional_exact_identity_rules_v1"
EXPECTED_REVIEW_SHA256 = "ca98c8e11c6d1005259e3218636e5575aec9613d270b18ef2e34ab2a328b8cff"
YEARS = (2002, 2010, 2021)
YEAR_PAIR_PRIORITY = {(2002, 2010): 0, (2010, 2021): 1, (2002, 2021): 2}
AGGREGATE_SCOPES = {
    "federal_city_region", "municipality", "municipal_aggregate", "region",
    "administrative_area", "territorial_aggregate",
}
CITY_TYPE = "город"
DEFAULT_ROOT = Path("/workspace")
DEFAULT_SELECTED = DEFAULT_ROOT / "settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet"
DEFAULT_EVIDENCE = DEFAULT_ROOT / "settlements-work/candidates/optimized_run/source_evidence.parquet"
DEFAULT_CANDIDATES = DEFAULT_ROOT / "settlements-work/candidates/optimized_run/pair_candidates.csv.gz"
DEFAULT_BASE_GRAPH = DEFAULT_ROOT / "settlements-work/migration-portable/migrated_identity_edges.csv"
DEFAULT_REVIEW = DEFAULT_ROOT / "settlements-work/candidates/independent_rule_review.json"
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config/mass_linkage_run_20261002.json"
DEFAULT_INPUT_MANIFEST = DEFAULT_ROOT / "settlements-baseline/output/input_manifest.parquet"
DEFAULT_RAW_ROOT = DEFAULT_ROOT / "settlements-raw"
DEFAULT_OUTPUT = DEFAULT_ROOT / "settlements-work/identity/ordinary_v4"
EXPECTED_ADMIN_REVIEW_SHA256 = "fa212e5c7dc010a5b40ca17e9508b5823c74ef95cad75b374625edbf29043d86"
DEFAULT_ADMIN_REVIEW = DEFAULT_ROOT / "settlements-work/sources/admin_context_review/review.json"


class ApplicationError(ValueError):
    pass


def _norm(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().casefold()


def _district_key(value: Any) -> str:
    """Reuse the existing reviewed administrative-key token normalization."""
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().replace("ё", "е")
    text = text.replace("–", "-").replace("—", "-").replace("'", "")
    text = re.sub(r"[\"«»()]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:.\t\n")
    text = re.sub(r"\b(?:муниципальный|городской|сельский|городское|сельское)\b", " ", text)
    text = re.sub(r"\b(?:район|округ|поселение|поселения|сп|гп)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _source_label_key(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", text).strip()


def _source_region_key(value: Any) -> str:
    text = _source_label_key(value)
    # Limited source-format normalization: remove a terminal federal-subject
    # descriptor; region aliases/abbreviations remain distinct and fail closed.
    text = re.sub(r"\s+(?:область|край|республика|автономная область|автономный округ)$", "", text)
    return text.strip()


def _raw_population(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = re.sub(r"[\s\u00a0]", "", str(value))
        if not re.fullmatch(r"[+-]?\d+", text):
            return None
        return int(text)
    return int(number) if number.is_integer() else None


def _verified_direct_context(meta: dict[str, Any], profile: dict[str, Any], values: list[Any],
                             constant_region: Any = None) -> tuple[list[str], str | None]:
    """Return same-row D values only when raw identity, population and region agree."""
    raw_names = [values[int(col)] if int(col) < len(values) else "" for col in profile.get("name_cols", [])]
    raw_label_key = _source_label_key(meta.get("source_name_raw"))
    if not raw_label_key:
        raw_label_key = _source_label_key(meta.get("settlement_name"))
    if not raw_label_key or not any(_source_label_key(value) == raw_label_key for value in raw_names):
        return [], "raw_label_mismatch"
    pop_col = profile.get("population_col")
    raw_pop = values[int(pop_col)] if pop_col is not None and int(pop_col) < len(values) else None
    selected_pop = _raw_population(meta.get("population"))
    if _raw_population(raw_pop) is None or _raw_population(raw_pop) != selected_pop:
        return [], "raw_population_mismatch"
    region_raw = constant_region
    if profile.get("region_col") is not None:
        col = int(profile["region_col"])
        region_raw = values[col] if col < len(values) else None
    selected_region = _source_region_key(meta.get("region_raw"))
    source_region = _source_region_key(region_raw)
    if not source_region or not selected_region or source_region != selected_region:
        return [], "raw_region_mismatch"
    explicit = []
    for col in profile["district_cols"]:
        cell = values[int(col)] if int(col) < len(values) else ""
        if cell is not None and str(cell).strip():
            explicit.append(str(cell).strip())
    return explicit, None


def _json(value: Any) -> str:
    def clean(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(k): clean(v) for k, v in item.items()}
        if isinstance(item, (list, tuple, set)):
            return [clean(v) for v in item]
        try:
            if pd.isna(item):
                return None
        except (TypeError, ValueError):
            pass
        if hasattr(item, "item"):
            try:
                return item.item()
            except (ValueError, AttributeError):
                pass
        return item
    return json.dumps(clean(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _require_origin(meta: dict[str, Any]) -> bool:
    row = meta.get("source_row")
    has_row = row is not None and not pd.isna(row) and str(row).strip() != ""
    return bool(_norm(meta.get("source_file")) and _norm(meta.get("source_sha256"))
                and _norm(meta.get("source_sheet"))
                and (has_row or _norm(meta.get("source_locator"))))


def _traceable_district(node: Node, meta: dict[str, Any], key_district: str) -> bool:
    """Confirm a key's parent value has a row/source locator; no boundary claim."""
    if not key_district or not _require_origin(meta):
        return False
    if node.census_year == 2021:
        # Tochno mun_upper is current parent context, used only as a matching
        # feature. It is explicitly not evidence of a historical district.
        context = _district_key(node.district_raw) or _district_key(node.municipality_raw)
        return bool(context and context == key_district)
    if node.census_year == 2010:
        # In the present R2 projection, most 2010 district values are absent
        # and some historical extraction families may have carried a prior
        # worksheet group value. Only the independently source-reviewed R5
        # parent context is eligible until row-cell provenance is reviewed.
        if node.source_selection_component == "karelia_2010_primary_r5":
            return _district_key(node.district_raw) == key_district
        direct_values = meta.get("raw_explicit_district_values", [])
        return any(_district_key(value) == key_district for value in direct_values)
    return bool(_district_key(node.district_raw) == key_district)


def _screen_candidate_pair(
    pair: dict[str, Any], nodes: dict[str, Node], endpoint_meta: dict[str, dict[str, Any]],
    ambiguous_ids_by_family: dict[str, set[str]], competing_families: set[str],
) -> tuple[str | None, list[str]]:
    """Return a rule name only after local screens pass; blockers stay explicit."""
    left, right = pair["from_id"], pair["to_id"]
    a, b = nodes[left], nodes[right]
    ma, mb = endpoint_meta[left], endpoint_meta[right]
    reasons: list[str] = []
    fam = pair["families"]
    kv_by_family = pair["key_values_by_family"]
    kv = next(iter(kv_by_family.values()))

    has_district_rule = "region_district_name_type" in fam
    has_city_rule = ("region_name_type" in fam and _norm(a.type_norm) == CITY_TYPE
                     and _norm(b.type_norm) == CITY_TYPE)
    district_kv = kv_by_family.get("region_district_name_type", {})
    district_applicable = (has_district_rule
                           and _district_key(district_kv.get("district_norm")) == _district_key(a.district_norm)
                           and _district_key(district_kv.get("district_norm")) == _district_key(b.district_norm)
                           and _traceable_district(a, ma, _district_key(district_kv.get("district_norm")))
                           and _traceable_district(b, mb, _district_key(district_kv.get("district_norm"))))
    if district_applicable and (left in ambiguous_ids_by_family.get("region_district_name_type", set())
                                or right in ambiguous_ids_by_family.get("region_district_name_type", set())):
        reasons.append("district_key_ambiguous_competing_group")
    if has_city_rule and not district_applicable and (left in ambiguous_ids_by_family.get("region_name_type", set())
                                                       or right in ambiguous_ids_by_family.get("region_name_type", set())):
        reasons.append("region_name_type_ambiguous_competing_group")
    if ((district_applicable and "region_district_name_type" in competing_families)
            or (has_city_rule and not district_applicable and "region_name_type" in competing_families)):
        reasons.append("competing_endpoint_alternative_within_applicable_key_family")
    if pair["federal_aggregate_block"] or a.aggregate or b.aggregate:
        reasons.append("aggregate_or_nonsettlement_scope")
    if pair["legacy_identity_conflict_present"] or pair["legacy_same_year_collision_present"] or a.legacy_identity_conflict or b.legacy_identity_conflict or a.legacy_same_year_collision or b.legacy_same_year_collision:
        reasons.append("unresolved_legacy_identity_or_same_year_flag")
    if pair["region_mismatch"] or _norm(a.region_norm) != _norm(b.region_norm) or not _norm(a.region_norm):
        reasons.append("region_mismatch_or_missing")
    if pair["type_change_or_mismatch"] or not _norm(a.type_norm) or _norm(a.type_norm) != _norm(b.type_norm):
        reasons.append("type_mismatch_or_missing")
    if not _norm(ma.get("name_norm")) or _norm(ma.get("name_norm")) != _norm(mb.get("name_norm")):
        reasons.append("normalized_name_mismatch_or_missing")
    if _norm(a.entity_grain_status) == "named_locality_type_unresolved" or _norm(b.entity_grain_status) == "named_locality_type_unresolved":
        reasons.append("named_locality_grain_unresolved")
    if _norm(ma.get("population_scope")) in AGGREGATE_SCOPES or _norm(mb.get("population_scope")) in AGGREGATE_SCOPES:
        reasons.append("aggregate_population_scope")
    if not _flag(ma.get("is_additive_settlement_record")) or not _flag(mb.get("is_additive_settlement_record")):
        reasons.append("not_selected_as_additive_settlement_record")
    if not _require_origin(ma) or not _require_origin(mb):
        reasons.append("source_origin_or_row_locator_not_traceable")

    # The exact-key payload itself must still agree with the selected records.
    if _norm(kv.get("region_norm")) != _norm(a.region_norm) or _norm(kv.get("region_norm")) != _norm(b.region_norm):
        reasons.append("candidate_region_key_disagrees_with_current_source")
    if _norm(kv.get("type_norm")) != _norm(a.type_norm) or _norm(kv.get("type_norm")) != _norm(b.type_norm):
        reasons.append("candidate_type_key_disagrees_with_current_source")
    if _norm(kv.get("name_norm")) != _norm(ma.get("name_norm")) or _norm(kv.get("name_norm")) != _norm(mb.get("name_norm")):
        reasons.append("candidate_name_key_disagrees_with_current_source")

    district_ok = district_applicable

    if reasons:
        return None, sorted(set(reasons))
    if district_ok:
        return "exact_region_district_name_type_with_traceable_context", []
    if has_city_rule:
        return "unique_exact_region_city_name_type", []
    return None, ["no_scoped_rule_applies_or_parent_context_untraceable"]


def _load_candidate_pairs(path: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, set[str]]]:
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    ambiguous_ids: dict[str, set[str]] = defaultdict(set)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "candidate_id", "candidate_family", "candidate_kind", "year_from", "year_to",
            "from_source_record_id", "to_source_record_id", "from_candidate_count",
            "to_candidate_count", "key_values", "federal_aggregate_block",
            "legacy_identity_conflict_present", "legacy_same_year_collision_present",
            "legacy_ordinal_route_present_not_acceptance_signal", "region_mismatch", "type_change_or_mismatch",
        }
        if not required.issubset(reader.fieldnames or []):
            raise ApplicationError(f"candidate ledger missing fields: {sorted(required-set(reader.fieldnames or []))}")
        for row in reader:
            family = row["candidate_family"]
            if family not in {"region_district_name_type", "region_name_type"}:
                continue
            left, right = row["from_source_record_id"], row["to_source_record_id"]
            if row["candidate_kind"] == "ambiguous_competing_key_group":
                for field in ("from_candidate_ids_json", "to_candidate_ids_json"):
                    try:
                        ambiguous_ids[family].update(json.loads(row.get(field) or "[]"))
                    except json.JSONDecodeError as exc:
                        raise ApplicationError(f"invalid ambiguous endpoint list {row['candidate_id']}") from exc
                continue
            if row["candidate_kind"] != "unique_exact_key_pair":
                continue
            if not left or not right:
                raise ApplicationError(f"unique candidate has blank endpoint: {row['candidate_id']}")
            try:
                kv = json.loads(row["key_values"])
            except json.JSONDecodeError as exc:
                raise ApplicationError(f"invalid key payload {row['candidate_id']}") from exc
            key = (left, right)
            item = pairs.setdefault(key, {
                "from_id": left, "to_id": right, "year_from": int(row["year_from"]),
                "year_to": int(row["year_to"]), "candidate_ids": set(), "families": set(),
                "key_values_by_family": {}, "candidate_unique": True,
                "federal_aggregate_block": False, "legacy_identity_conflict_present": False,
                "legacy_same_year_collision_present": False, "region_mismatch": False,
                "legacy_ordinal_route_present_not_acceptance_signal": False, "type_change_or_mismatch": False,
            })
            if (item["year_from"], item["year_to"]) != (int(row["year_from"]), int(row["year_to"])):
                raise ApplicationError("endpoint pair is duplicated with inconsistent census years")
            item["candidate_ids"].add(row["candidate_id"])
            item["families"].add(family)
            if family in item["key_values_by_family"] and item["key_values_by_family"][family] != kv:
                raise ApplicationError(f"candidate family has conflicting keys for endpoint pair: {left} / {right}")
            item["key_values_by_family"][family] = kv
            item["federal_aggregate_block"] |= _flag(row["federal_aggregate_block"])
            item["legacy_identity_conflict_present"] |= _flag(row["legacy_identity_conflict_present"])
            item["legacy_same_year_collision_present"] |= _flag(row["legacy_same_year_collision_present"])
            item["legacy_ordinal_route_present_not_acceptance_signal"] |= _flag(row["legacy_ordinal_route_present_not_acceptance_signal"])
            item["region_mismatch"] |= _flag(row["region_mismatch"])
            item["type_change_or_mismatch"] |= _flag(row["type_change_or_mismatch"])
            item["candidate_unique"] &= (int(row["from_candidate_count"]) == 1 and int(row["to_candidate_count"]) == 1)
    return pairs, dict(ambiguous_ids)


def _validate_review_pins(review: dict[str, Any], review_path: Path, candidate_path: Path,
                          evidence_path: Path) -> set[str]:
    """Bind the conditional decision to the reviewed deterministic artifacts."""
    review_root = review_path.parent.parent
    expected_inputs = review.get("inputs", {})
    checked = set()
    for key, path, expected in (
        ("audit", review_root / expected_inputs.get("audit", ""), expected_inputs.get("audit_sha256")),
        ("stratified_review_sample", review_root / expected_inputs.get("stratified_review_sample", ""), expected_inputs.get("sample_sha256")),
        ("source_evidence", review_root / expected_inputs.get("source_evidence", ""), expected_inputs.get("source_evidence_sha256")),
        ("pair_ledger", review_root / expected_inputs.get("pair_ledger", ""), expected_inputs.get("pair_ledger_sha256")),
    ):
        if not path.is_file() or not expected or _sha(path) != expected:
            raise ApplicationError(f"review-pinned {key} input missing or changed: {path}")
        checked.add(key)
    builder = expected_inputs.get("builder", {})
    builder_path = Path(__file__).resolve().parents[2] / builder.get("path", "")
    if not builder.get("sha256") or not builder_path.is_file() or _sha(builder_path) != builder["sha256"]:
        raise ApplicationError("candidate builder differs from the builder pinned by the conditional review")
    checked.add("candidate_builder")
    return checked


def _pair_competitors(pairs: dict[tuple[str, str], dict[str, Any]], nodes: dict[str, Node]) -> dict[tuple[str, str], set[str]]:
    by_endpoint: dict[tuple[str, int, int, str], set[str]] = defaultdict(set)
    for (left, right), values in pairs.items():
        for family in values["families"]:
            by_endpoint[(left, values["year_from"], values["year_to"], family)].add(right)
            by_endpoint[(right, values["year_to"], values["year_from"], family)].add(left)
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    for pair, values in pairs.items():
        for family in values["families"]:
            if (len(by_endpoint[(pair[0], values["year_from"], values["year_to"], family)]) > 1
                    or len(by_endpoint[(pair[1], values["year_to"], values["year_from"], family)]) > 1):
                out[pair].add(family)
    return dict(out)


def _metadata(selected_path: Path, endpoint_ids: set[str], manifest_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    cols = ["source_record_id", "census_year", "name_norm", "is_additive_settlement_record", "population_scope",
            "source_file", "source_sha256", "source_sheet", "source_row", "source_locator",
            "source_name_raw", "settlement_name", "settlement_type", "region_raw", "district_raw", "source_path",
            "municipality_raw", "population_value_quality", "source_selection_component", "population"]
    selected = pd.read_parquet(selected_path, columns=cols)
    selected = selected[selected.source_record_id.astype(str).isin(endpoint_ids)]
    if selected.source_record_id.astype(str).duplicated().any():
        raise ApplicationError("selected projection has duplicate source_record_id")
    manifest = pd.read_parquet(manifest_path, columns=["path", "bytes", "sha256"])
    manifest_map: dict[str, dict[str, Any]] = {}
    for row in manifest.to_dict("records"):
        rel = str(row["path"]).replace("\\", "/")
        val = {"bytes": int(row["bytes"]), "sha256": str(row["sha256"])}
        if rel in manifest_map and manifest_map[rel] != val:
            raise ApplicationError(f"input manifest has conflicting exact-path entries: {rel}")
        manifest_map[rel] = val
    result = {}
    source_inputs: dict[str, dict[str, Any]] = {}
    for row in selected.to_dict("records"):
        sid = str(row["source_record_id"])
        def raw_path(value: Any) -> str:
            return "" if value is None or pd.isna(value) else str(value).replace("\\", "/")
        rels = [raw_path(row.get("source_file")), raw_path(row.get("source_path"))]
        rels = [rel for rel in rels if rel]
        found = next((rel for rel in rels if rel in manifest_map), None)
        selected_hash = row.get("source_sha256")
        if pd.isna(selected_hash) if selected_hash is not None else True:
            if not found:
                raise ApplicationError(f"source hash missing and no exact-path manifest bind for {sid}: {rels}")
            selected_hash = manifest_map[found]["sha256"]
        elif found and str(selected_hash) != manifest_map[found]["sha256"]:
            raise ApplicationError(f"selected source hash disagrees with exact-path input manifest for {sid}")
        if not found:
            source_inputs.setdefault(rels[0], {"sha256": str(selected_hash), "bytes": None,
                                               "binding": "selected_projection_source_sha256"})
        else:
            source_inputs.setdefault(found, {**manifest_map[found], "binding": "exact_input_manifest_path"})
        row["source_sha256"] = str(selected_hash)
        result[sid] = row
    if set(result) != endpoint_ids:
        raise ApplicationError(f"candidate endpoints absent from selected projection: {len(endpoint_ids-set(result))}")
    return result, source_inputs


def _read_explicit_2010_district_cells(endpoint_meta: dict[str, dict[str, Any]], raw_root: Path,
                                       source_manifest_binds: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Read direct source rows only, verifying label/population/region before context use."""
    by_file: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for sid, meta in endpoint_meta.items():
        if int(meta.get("census_year") or 0) != 2010:
            continue
        if meta.get("source_selection_component") == "karelia_2010_primary_r5":
            continue
        source_file = str(meta.get("source_file") or "").replace("\\", "/")
        if source_file in SHEET_PROFILES:
            by_file[source_file].append((sid, meta))
    counts = Counter()
    raw_root = raw_root.resolve()
    for source_file, records in by_file.items():
        profile = SHEET_PROFILES[source_file]
        candidate_path = (raw_root / source_file).resolve()
        try:
            candidate_path.relative_to(raw_root)
        except ValueError as exc:
            raise ApplicationError(f"source path escapes raw root: {source_file}") from exc
        if not candidate_path.is_file():
            raise ApplicationError(f"raw source workbook required for exact district-cell check is missing: {candidate_path}")
        expected = source_manifest_binds.get(source_file, {}).get("sha256")
        if not expected or _sha(candidate_path) != expected:
            raise ApplicationError(f"raw source workbook differs from its exact input-manifest binding: {source_file}")
        book = xlrd.open_workbook(str(candidate_path), on_demand=True)
        if profile["sheet"] not in book.sheet_names():
            raise ApplicationError(f"source sheet from checked profile is absent: {source_file}:{profile['sheet']}")
        sheet = book.sheet_by_name(profile["sheet"])
        header_index = int(profile["header_row"]) - 1
        header_values = sheet.row_values(header_index)
        for col, expected_header in profile.get("headers", {}).items():
            got = header_values[int(col)] if int(col) < len(header_values) else ""
            if _norm(got) != _norm(expected_header):
                raise ApplicationError(f"raw district-cell profile header changed: {source_file} col {int(col)+1}")
        constant_region = None
        if profile.get("region_constant_cell"):
            r, c = profile["region_constant_cell"]
            constant_region = sheet.cell_value(int(r), int(c)) if int(r) < sheet.nrows and int(c) < sheet.ncols else None
        for sid, meta in records:
            meta["raw_explicit_district_values"] = []
            meta["direct_source_row_context_verified"] = False
            row_number = meta.get("source_row")
            if row_number is None or pd.isna(row_number):
                counts["source_row_missing"] += 1
                continue
            row_index = int(float(row_number)) - 1
            if row_index < int(profile["first_data_row"]) - 1 or row_index >= sheet.nrows:
                counts["source_row_outside_profile_data"] += 1
                continue
            values = sheet.row_values(row_index)
            counts["rows_checked"] += 1
            # Verify the selected observation points at this exact raw row. Any
            # mismatch leaves its source parent context unavailable to the rule.
            explicit, validation_error = _verified_direct_context(meta, profile, values, constant_region)
            if validation_error:
                counts[validation_error + "_held"] += 1
                continue
            counts["direct_source_rows_label_population_region_verified"] += 1
            if explicit:
                meta["raw_explicit_district_values"] = explicit
                meta["direct_source_row_context_verified"] = True
                counts["rows_with_nonblank_exact_district_cell"] += 1
            else:
                counts["rows_with_blank_district_cell_held"] += 1
        book.release_resources()
    counts["profiled_source_files_read"] = len(by_file)
    return dict(counts)


def _base_graph(path: Path, nodes: dict[str, Node]) -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    base = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"relation", "from_source_record_id", "from_year", "to_source_record_id", "to_year", "decision_status"}
    if not required.issubset(base.columns) or len(base) != 1162:
        raise ApplicationError("migration baseline must contain exactly 1162 identity edges with expected schema")
    if base.from_source_record_id.eq(base.to_source_record_id).any() or not base.relation.eq("same_place").all():
        raise ApplicationError("migration baseline includes invalid/non-identity relations")
    edges = []
    for row in base.to_dict("records"):
        left, right = row["from_source_record_id"], row["to_source_record_id"]
        if left not in nodes or right not in nodes:
            raise ApplicationError(f"baseline edge endpoint absent from selected rows: {left} / {right}")
        if nodes[left].census_year != int(row["from_year"]) or nodes[right].census_year != int(row["to_year"]):
            raise ApplicationError("baseline edge year differs from current selected endpoint year")
        edges.append((left, right))
    if len(set(edges)) != len(edges):
        raise ApplicationError("migration baseline contains duplicate endpoint pairs")
    return base.to_dict("records"), edges


def _candidate_graph_outcome(key: tuple[str, str], graph: YearConstrainedUnionFind,
                             baseline_pairs: set[tuple[str, str]]) -> tuple[str, tuple[int, ...], str]:
    """Keep prior endpoint decisions as corroboration; admit distinct redundant pairs."""
    if key in baseline_pairs:
        return "corroborates_reviewed_baseline_pair", (), "existing_baseline_pair_no_new_edge"
    status, overlap, _, _ = graph.add_edge(*key)
    if status == "blocked_same_year_component_collision":
        return status, tuple(overlap), "blocked_same_year_component_collision"
    if status == "already_connected":
        return status, tuple(overlap), "redundant_graph_connectivity_effect"
    return status, tuple(overlap), "added_distinct_pair"


def _component_rows(graph: YearConstrainedUnionFind, nodes: dict[str, Node]) -> list[dict[str, Any]]:
    rows = []
    for _, members, years in graph.component_summaries():
        if len(members) <= 1:
            continue
        members = sorted(members)
        pop_by_year = {}
        count_by_year = {}
        for year in YEARS:
            ids = [sid for sid in members if nodes[sid].census_year == year]
            count_by_year[str(year)] = len(ids)
            pop_by_year[str(year)] = sum(nodes[sid].population for sid in ids if nodes[sid].population is not None)
        compid = "CMP-" + hashlib.sha256("\0".join(members).encode()).hexdigest()[:24]
        full = all(count_by_year[str(year)] == 1 for year in YEARS)
        rows.append({"component_id": compid, "member_source_record_ids_json": _json(members),
                     "rows_by_year_json": _json(count_by_year), "known_population_by_year_json": _json(pop_by_year),
                     "full_2002_2010_2021_chain": full, "distinct_year_count": len(years)})
    return sorted(rows, key=lambda row: row["component_id"])


def _metrics(component_rows: list[dict[str, Any]], nodes: dict[str, Node], selected: pd.DataFrame,
             official_controls: dict[str, int], label: str) -> list[dict[str, Any]]:
    linked: dict[int, set[str]] = {year: set() for year in YEARS}
    chains: dict[int, set[str]] = {year: set() for year in YEARS}
    for row in component_rows:
        members = json.loads(row["member_source_record_ids_json"])
        for sid in members:
            year = nodes[sid].census_year
            linked[year].add(sid)
            if row["full_2002_2010_2021_chain"]:
                chains[year].add(sid)
    summary = selected.groupby("census_year").agg(
        selected_rows=("source_record_id", "size"), known_population=("population", "sum"),
        unknown_population_rows=("population", lambda s: int(s.isna().sum())),
    )
    result = []
    for year in YEARS:
        selected_rows = int(summary.loc[year, "selected_rows"])
        known_pop = int(summary.loc[year, "known_population"])
        ids, chain_ids = linked[year], chains[year]
        linked_known = sum(nodes[sid].population for sid in ids if nodes[sid].population is not None)
        chain_known = sum(nodes[sid].population for sid in chain_ids if nodes[sid].population is not None)
        result.append({
            "graph_stage": label, "census_year": year, "selected_rows": selected_rows,
            "selected_known_population": known_pop, "selected_unknown_population_rows": int(summary.loc[year, "unknown_population_rows"]),
            "official_control_population_from_config": int(official_controls[str(year)]),
            "official_control_status": "preserved_run_config_control_pending_primary_source_reverification",
            "linked_any_census_rows": len(ids), "linked_any_census_known_population": linked_known,
            "linked_any_rows_fraction_of_selected": len(ids)/selected_rows if selected_rows else 0,
            "linked_any_known_population_fraction_of_selected_known": linked_known/known_pop if known_pop else 0,
            "linked_any_known_population_fraction_of_official_control": linked_known/int(official_controls[str(year)]),
            "full_chain_rows": len(chain_ids), "full_chain_known_population": chain_known,
            "full_chain_rows_fraction_of_selected": len(chain_ids)/selected_rows if selected_rows else 0,
            "full_chain_known_population_fraction_of_selected_known": chain_known/known_pop if known_pop else 0,
            "full_chain_known_population_fraction_of_official_control": chain_known/int(official_controls[str(year)]),
        })
    return result


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None, compressed: bool = False) -> None:
    if not rows and not fields:
        raise ApplicationError(f"output has no schema: {path.name}")
    fields = fields or list(rows[0])
    opener = gzip.open if compressed else open
    mode = "wt" if compressed else "w"
    with opener(path, mode, encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build(selected_path: Path = DEFAULT_SELECTED, evidence_path: Path = DEFAULT_EVIDENCE,
          candidate_path: Path = DEFAULT_CANDIDATES, base_graph_path: Path = DEFAULT_BASE_GRAPH,
          review_path: Path = DEFAULT_REVIEW, config_path: Path = DEFAULT_CONFIG,
          manifest_path: Path = DEFAULT_INPUT_MANIFEST,
          raw_root: Path = DEFAULT_RAW_ROOT, admin_review_path: Path = DEFAULT_ADMIN_REVIEW,
          output_root: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    paths = [selected_path, evidence_path, candidate_path, base_graph_path, review_path, config_path, manifest_path, admin_review_path]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    review_sha = _sha(review_path)
    if review_sha != EXPECTED_REVIEW_SHA256:
        raise ApplicationError(f"conditional review hash mismatch: {review_sha}")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("status") != "conditional_scoped_pass_for_strong_ordinary_rules":
        raise ApplicationError("conditional review status does not authorize scoped rule application")
    review_pin_checks = _validate_review_pins(review, review_path, candidate_path, evidence_path)
    admin_review_sha = _sha(admin_review_path)
    if admin_review_sha != EXPECTED_ADMIN_REVIEW_SHA256:
        raise ApplicationError(f"frozen 2010 admin-context review hash mismatch: {admin_review_sha}")
    admin_review = json.loads(admin_review_path.read_text(encoding="utf-8"))
    if admin_review.get("review_status") != "reject_current_bulk_recovery_ifcarryoverunsupported":
        raise ApplicationError("frozen admin-context review status changed")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    official_controls = {str(k): int(v) for k, v in config["population_controls_from_preserved_audit"].items()}
    if set(official_controls) != {str(y) for y in YEARS}:
        raise ApplicationError("run configuration lacks an official population control for every census year")

    nodes, selected = _load_nodes(selected_path, evidence_path)
    base_records, base_edges = _base_graph(base_graph_path, nodes)
    pairs, ambiguous_ids_by_family = _load_candidate_pairs(candidate_path)
    ledger_candidate_ids = {candidate_id for pair in pairs.values() for candidate_id in pair["candidate_ids"]}
    reviewed_sample_ids = set(review.get("fixed_sample", {}).get("candidate_ids", []))
    if not reviewed_sample_ids or not reviewed_sample_ids.issubset(ledger_candidate_ids):
        raise ApplicationError("fixed reviewed candidate sample is not present in the pinned candidate ledger")
    endpoint_ids = {sid for pair in pairs for sid in pair}
    endpoint_meta, source_manifest_binds = _metadata(selected_path, endpoint_ids, manifest_path)
    raw_context_check_counts = _read_explicit_2010_district_cells(endpoint_meta, raw_root, source_manifest_binds)
    competing_pairs = _pair_competitors(pairs, nodes)

    screened = []
    screened_index: dict[tuple[str, str], int] = {}
    candidate_edges = []
    reasons_count: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    candidate_nodes = {sid for pair in pairs for sid in pair}
    for key, pair in pairs.items():
        left, right = key
        blockers = []
        if not pair["candidate_unique"]:
            blockers.append("candidate_key_not_one_to_one_unique")
        rule, reasons = _screen_candidate_pair(pair, nodes, endpoint_meta, ambiguous_ids_by_family,
                                               competing_pairs.get(key, set()))
        blockers.extend(reasons)
        if blockers:
            status = "held_screen_failed"
            for reason in set(blockers):
                reasons_count[reason] += 1
        else:
            status = "screen_pass_pending_graph_constraint"
            candidate_edges.append((key, rule or ""))
        screened.append({
            "from_source_record_id": left, "to_source_record_id": right,
            "from_year": pair["year_from"], "to_year": pair["year_to"],
            "candidate_ids_json": _json(sorted(pair["candidate_ids"])),
            "candidate_families_json": _json(sorted(pair["families"])),
            "exact_key_values_by_family_json": _json(pair["key_values_by_family"]),
            "rule_applied": rule or "", "application_status": status,
            "blocking_reasons_json": _json(sorted(set(blockers))),
        })
        screened_index[key] = len(screened) - 1

    graph = YearConstrainedUnionFind(nodes)
    graph.initialize_edges(base_edges)
    baseline_pair_set = set(base_edges)
    base_components = _component_rows(graph, nodes)
    base_metrics = _metrics(base_components, nodes, selected, official_controls, "migration_baseline_1162")

    candidate_edges.sort(key=lambda item: (
        0 if item[1] == "exact_region_district_name_type_with_traceable_context" else 1,
        YEAR_PAIR_PRIORITY[(pairs[item[0]]["year_from"], pairs[item[0]]["year_to"])],
        item[0][0], item[0][1],
    ))
    newly_accepted = []
    accepted_pair_set = set()
    baseline_pair_corroborations = 0
    redundant_graph_effect_pairs = 0
    for key, rule in candidate_edges:
        pair = pairs[key]
        left, right = key
        status, overlap, graph_effect = _candidate_graph_outcome(key, graph, baseline_pair_set)
        if status == "corroborates_reviewed_baseline_pair":
            baseline_pair_corroborations += 1
            row = screened[screened_index[key]]
            row["application_status"] = status
            row["graph_connectivity_effect"] = graph_effect
            row["blocking_reasons_json"] = _json([])
            continue
        if status == "blocked_same_year_component_collision":
            reasons_count["same_year_component_collision_in_accepted_graph"] += 1
            record_status = "held_same_year_component_collision"
            reason_list = ["same_year_component_collision:" + _json(overlap)]
        else:
            record_status = "checked_rule_accepted_pending_independent_application_verification"
            if graph_effect == "redundant_graph_connectivity_effect":
                record_status = "checked_rule_accepted_redundant_graph_connectivity_effect_pending_independent_application_verification"
                redundant_graph_effect_pairs += 1
            reason_list = []
            accepted_pair_set.add(key)
            rule_counts[rule] += 1
            edge_id = "RULE-" + hashlib.sha256((rule + "\0" + left + "\0" + right).encode()).hexdigest()[:24]
            a, b = nodes[left], nodes[right]
            ma, mb = endpoint_meta[left], endpoint_meta[right]
            newly_accepted.append({
                "decision_id": edge_id, "relation": "same_place", "from_source_record_id": left,
                "from_year": pair["year_from"], "to_source_record_id": right, "to_year": pair["year_to"],
                "decision_class": "checked_rule", "decision_status": record_status,
                "decision_rule": RULE_VERSION + ":" + rule, "review_id": review["review_id"],
                "review_sha256": review_sha, "candidate_ids_json": _json(sorted(pair["candidate_ids"])),
                "candidate_families_json": _json(sorted(pair["families"])),
                "legacy_ordinal_route_present_not_acceptance_signal": pair["legacy_ordinal_route_present_not_acceptance_signal"],
                "key_values_by_family_json": _json(pair["key_values_by_family"]),
                "from_source_origin_json": _json({k: ma.get(k) for k in ("source_file","source_sha256","source_sheet","source_row","source_locator","source_name_raw","settlement_name","settlement_type","region_raw","district_raw","raw_explicit_district_values","municipality_raw","population_value_quality")}),
                "to_source_origin_json": _json({k: mb.get(k) for k in ("source_file","source_sha256","source_sheet","source_row","source_locator","source_name_raw","settlement_name","settlement_type","region_raw","district_raw","raw_explicit_district_values","municipality_raw","population_value_quality")}),
                "from_context_class": a.district_lineage_class,
                "to_context_class": b.district_lineage_class,
                "context_interpretation": "matching feature only; 2021 mun_upper is current context, not historical-boundary evidence",
                "population_scope_interpretation": "identity only; populations remain year-specific; comparability not inferred",
                "coordinate_admission_changed": False,
                "graph_add_status": status,
                "graph_connectivity_effect": graph_effect,
            })
        row = screened[screened_index[key]]
        row["application_status"] = record_status
        row["graph_connectivity_effect"] = graph_effect
        row["blocking_reasons_json"] = _json(reason_list)

    final_components = _component_rows(graph, nodes)
    metrics = base_metrics + _metrics(final_components, nodes, selected, official_controls, "ordinary_rules_applied")

    output_root = output_root.resolve()
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise ApplicationError("output directory must be outside the Git repository")
    if output_root.exists():
        raise FileExistsError(f"immutable identity-rule output already exists: {output_root}")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=output_root.parent))
    try:
        shutil.copyfile(base_graph_path, staging / "reviewed_baseline_identity_edges.csv")
        _write_csv(staging / "rule_accepted_edges.csv", newly_accepted,
                   fields=list(newly_accepted[0]) if newly_accepted else ["decision_id","relation","decision_status"])
        _write_csv(staging / "screened_candidate_pairs.csv.gz", screened,
                   fields=list(dict.fromkeys(list(screened[0]) + ["graph_connectivity_effect"])) if screened else ["from_source_record_id","to_source_record_id","application_status","graph_connectivity_effect"], compressed=True)
        _write_csv(staging / "linked_components.csv", final_components,
                   fields=list(final_components[0]) if final_components else ["component_id","member_source_record_ids_json"])
        _write_csv(staging / "coverage_by_year.csv", metrics)
        code_path = Path(__file__).resolve()
        audit = {
            "status": "staged_rule_application_pending_independent_application_verification",
            "rule_version": RULE_VERSION,
            "review": {"review_id": review["review_id"], "status": review["status"], "sha256": review_sha,
                       "fixed_sample_rows": review.get("fixed_sample", {}).get("rural_count", 0)+review.get("fixed_sample", {}).get("urban_count", 0),
                "national_precision_claim": False},
            "interpretation": [
                "Rule admissions identify a same-place relation only; dated populations and boundary comparability remain separate.",
                "2021 mun_upper is current administrative context used as a matching feature, never asserted as a historical boundary.",
                "Unknown populations remain null; no population or coordinate values were changed.",
                "The 1162 migrated reviewed identity edges are preserved byte-for-byte as a separate baseline file.",
            ],
            "counts": {
                "selected_source_rows": len(selected), "candidate_endpoint_pairs_deduplicated_across_families": len(pairs),
                "ambiguous_endpoint_ids_by_family": {family: len(ids) for family, ids in ambiguous_ids_by_family.items()},
                "unique_pairs_with_candidate_alternatives": len(competing_pairs),
                "screen_passed_pairs_before_graph_constraint": len(candidate_edges),
                "new_checked_rule_edges": len(newly_accepted),
                "candidate_pairs_corroborating_baseline_pair_without_new_edge": baseline_pair_corroborations,
                "distinct_pair_acceptances_with_redundant_graph_connectivity_effect": redundant_graph_effect_pairs,
                "rule_counts": dict(rule_counts), "blocker_counts": dict(reasons_count),
                "baseline_identity_edges": len(base_records), "baseline_components": len(base_components),
                "ordinary_graph_components": len(final_components),
                "baseline_full_chains": sum(bool(r["full_2002_2010_2021_chain"]) for r in base_components),
                "ordinary_full_chains": sum(bool(r["full_2002_2010_2021_chain"]) for r in final_components),
                "coordinate_admissions_changed": 0,
                "review_pinned_candidate_sample_ids": len(reviewed_sample_ids),
                "conditional_review_inputs_hash_verified": sorted(review_pin_checks),
            },
            "inputs": {p.name: {"path": p.name, "root_role": role, "sha256": _sha(p), "bytes": p.stat().st_size}
                       for p, role in ((selected_path,"selected_data_root"),(evidence_path,"candidate_output_root"),
                           (candidate_path,"candidate_output_root"),(base_graph_path,"migration_output_root"),
                           (review_path,"candidate_review_root"),(config_path,"git_checkout"),
                           (manifest_path,"baseline_input_manifest_root"))},
            "source_manifest_bindings": {"source_files": len(source_manifest_binds),
                                         "bindings": source_manifest_binds,
                                         "lookup_policy": "exact relative path only; no basename fallback"},
            "frozen_admin_context_review": {"path": str(admin_review_path), "sha256": admin_review_sha,
                "status": admin_review["review_status"], "use": "direct same-row context only after exact source label, population, region, profile headers and SHA checks; no carry-forward"},
            "2010_direct_row_context_check": {
                "profile_source": "research_rebuild/mass_linkage/recover_admin_context.py:SHEET_PROFILES",
                "row_cell_only": True, "fill_forward_or_recovered_assertions_used": False,
                "counts": raw_context_check_counts,
            },
            "builder": {"path": code_path.relative_to(repo_root).as_posix(), "sha256": _sha(code_path), "bytes": code_path.stat().st_size},
            "outputs": {},
        }
        for p in sorted(staging.iterdir()):
            if p.is_file():
                audit["outputs"][p.name] = {"sha256": _sha(p), "bytes": p.stat().st_size}
        (staging / "application_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        staging.rename(output_root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-parquet", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--source-evidence-parquet", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--candidate-ledger", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--base-identity-edges", type=Path, default=DEFAULT_BASE_GRAPH)
    parser.add_argument("--conditional-review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--run-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_INPUT_MANIFEST)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--admin-context-review", type=Path, default=DEFAULT_ADMIN_REVIEW)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    audit = build(args.selected_parquet, args.source_evidence_parquet, args.candidate_ledger,
                  args.base_identity_edges, args.conditional_review, args.run_config,
                  args.source_manifest, args.raw_root, args.admin_context_review, args.output_root)
    print(json.dumps({"status": audit["status"], "counts": audit["counts"], "output_root": str(args.output_root.resolve())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
