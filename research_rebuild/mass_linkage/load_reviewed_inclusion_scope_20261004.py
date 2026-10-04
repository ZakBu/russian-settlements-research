"""Load the reviewed, secondary-only historical inclusion references.

This module deliberately has no connection to the canonical build or ledger. It
verifies the frozen handoff bundle, then returns references to selected rows and
accepted point rows supplied by the caller. Nothing here adds a census row.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping

from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES


DEFAULT_FOLDER = Path(
    "/workspace/settlements-work/continuation_20261004/root/"
    "accepted_large_inclusion6_scope_preparation"
)
_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any, field: str) -> bool:
    s = _text(value).lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise ValueError(f"invalid boolean {field}={value!r}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _verify_pins(folder: Path) -> dict[str, str]:
    receipt_path = folder / "handoff_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    pins = dict(receipt.get("main_scope_outputs_sha256", {}))
    pins.update(receipt.get("zheleznodorozhny_supplement_files_sha256", {}))
    if not pins:
        raise ValueError("handoff receipt has no frozen output hash pins")
    for relpath, expected in pins.items():
        path = folder / relpath
        if not path.is_file():
            raise ValueError(f"pinned handoff file is missing: {relpath}")
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"handoff hash mismatch for {relpath}: {actual} != {expected}")
    main_receipt_hash = _text(receipt.get("main_scope_receipt_sha256"))
    build_receipt_hash = pins.get("build_receipt.json")
    if not main_receipt_hash or main_receipt_hash != build_receipt_hash:
        raise ValueError("main scope build receipt is not bound by the handoff receipt")
    return pins


def _field(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        if name in row and row[name] is not None:
            return _text(row[name])
    return ""


def _canonical_tuple(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    source_id = _field(row, "source_record_id", "source_id")
    year = _field(row, "census_year", "source_year", "year", "year_value")
    population = _field(row, "population", "population_value", "population_raw", "source_population")
    typ = _field(row, "type_raw", "settlement_type", "source_type", "type", "source_type_publisher")
    if not all((source_id, year, population, typ)):
        raise ValueError(f"canonical row lacks source ID/year/population/type tuple: {row!r}")
    return source_id, str(int(float(year))), str(int(float(population))), typ.casefold()


def _get_canonical(rows: Mapping[str, Mapping[str, Any]], source_id: str,
                   expected_year: str, expected_population: str,
                   expected_type: str | None = None) -> Mapping[str, Any]:
    try:
        row = rows[source_id]
    except KeyError as e:
        raise ValueError(f"selected canonical row missing: {source_id}") from e
    sid, year, pop, typ = _canonical_tuple(row)
    if sid != source_id or year != str(int(expected_year)) or pop != str(int(expected_population)):
        raise ValueError(f"selected row tuple mismatch for {source_id}: {(sid, year, pop)}")
    if expected_type is not None and typ != expected_type.casefold():
        raise ValueError(f"selected row type mismatch for {source_id}: {typ!r} != {expected_type!r}")
    _validate_physical_settlement(row, source_id)
    return row


def _validate_physical_settlement(row: Mapping[str, Any], source_id: str) -> None:
    if not _bool(row.get("is_additive_settlement_record"), "is_additive_settlement_record"):
        raise ValueError(f"canonical source is not an additive physical settlement: {source_id}")
    scope = _field(row, "population_scope").casefold().replace("_", " ")
    # Frozen selected_observations encodes this as "settlement"; the longer
    # spelling is accepted by narrow adapters that expose the semantic label.
    if scope not in {"settlement", "physical settlement"}:
        raise ValueError(f"canonical source is not physical-settlement grain: {source_id} ({scope})")
    aggregate_value = row.get("is_federal_aggregate")
    if aggregate_value is not None and _bool(aggregate_value, "is_federal_aggregate"):
        raise ValueError(f"canonical source is a federal aggregate: {source_id}")


def _index_unique(rows: list[dict[str, str]], key: str, label: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        value = _field(row, key)
        if not value:
            raise ValueError(f"missing {label} ID in {key}")
        if value in result:
            raise ValueError(f"duplicate {label} ID: {value}")
        result[value] = row
    return result


def _number(value: Any, field: str) -> float:
    try:
        number = float(_text(value))
    except (TypeError, ValueError) as e:
        raise ValueError(f"invalid coordinate {field}={value!r}") from e
    if not math.isfinite(number):
        raise ValueError(f"invalid coordinate {field}={value!r}")
    return number


def _coordinates(row: Mapping[str, Any]) -> tuple[float, float]:
    return (_number(_field(row, "latitude", "latitude_dd", "point_latitude"), "latitude"),
            _number(_field(row, "longitude", "longitude_dd", "point_longitude"), "longitude"))


def _validate_geonames_point(point: Mapping[str, Any], point_id: str,
                             seen_geonames: set[str], origin_cache: dict[Path, dict[str, tuple[tuple[float, float], str, str]]]) -> None:
    origin = Path(_field(point, "point_origin_file", "origin_file", "coordinate_source"))
    expected_hash = _field(point, "point_origin_sha256", "origin_sha256", "coordinate_source_sha256")
    locator = _field(point, "point_origin_locator", "origin_locator", "coordinate_source_locator")
    if not origin.is_file() or not expected_hash or _sha256(origin) != expected_hash:
        raise ValueError(f"point origin missing or hash-invalid for {point_id}")
    m = re.search(r"(?:^|/)RU\.txt:line=(\d+);geonameid=(\d+)(?:$|;)", locator)
    if not m:
        raise ValueError(f"point origin locator has no exact RU.txt line and GeoNames ID for {point_id}")
    line_number, geoname_id = int(m.group(1)), m.group(2)
    expected_coords = _coordinates(point)
    expected_line_hash = _field(point, "point_origin_line_sha256", "origin_line_sha256")
    if not expected_line_hash:
        raise ValueError(f"point origin line hash is missing for {point_id}")
    if geoname_id in seen_geonames:
        raise ValueError(f"duplicate GeoNames origin ID: {geoname_id}")
    seen_geonames.add(geoname_id)
    if origin not in origin_cache:
        found: dict[str, tuple[tuple[float, float], str, str]] = {}
        try:
            with zipfile.ZipFile(origin) as zf:
                member = next((n for n in zf.namelist() if n.endswith("RU.txt")), None)
                if member is None:
                    raise ValueError("GeoNames archive lacks RU.txt")
                with zf.open(member) as raw:
                    for lineno, line in enumerate(raw, start=1):
                        cols = line.decode("utf-8").rstrip("\r\n").split("\t")
                        if len(cols) > 8 and cols[0].isdigit():
                            try:
                                coords = (_number(cols[4], "GeoNames latitude"),
                                          _number(cols[5], "GeoNames longitude"))
                            except ValueError:
                                continue
                            found[cols[0]] = (coords, hashlib.sha256(line).hexdigest(),
                                              "\t".join((str(lineno), cols[1].strip(), cols[6], cols[7], cols[8])))
        except (zipfile.BadZipFile, OSError) as e:
            raise ValueError(f"cannot validate named-place origin {origin}") from e
        origin_cache[origin] = found
    if geoname_id not in origin_cache[origin]:
        raise ValueError(f"GeoNames origin is not a typed named place for {point_id}")
    coords, line_hash, line_meta = origin_cache[origin][geoname_id]
    if line_number != int(line_meta.split("\t", 1)[0]):
        raise ValueError(f"GeoNames line locator mismatch for {point_id}")
    if line_hash != expected_line_hash:
        raise ValueError(f"GeoNames source line hash mismatch for {point_id}")
    if coords != expected_coords:
        raise ValueError(f"GeoNames source coordinates differ from chosen point for {point_id}")
    _, name, feature_class, feature_code, country = line_meta.split("\t")
    if feature_class != "P" or not name or country != "RU":
        raise ValueError(f"GeoNames source row is not a named RU P feature for {point_id}")
    declared_provider_id = _field(point, "provider_feature_id", "geonames_geonameid")
    if declared_provider_id and declared_provider_id != geoname_id:
        raise ValueError(f"GeoNames provider ID differs from chosen origin ID for {point_id}")
    declared_member = _field(point, "point_origin_member", "origin_member")
    if declared_member and declared_member != "RU.txt":
        raise ValueError(f"unexpected GeoNames point member for {point_id}: {declared_member}")


def load_scoped_inclusion_references(
    folder: str | Path,
    selected_rows_by_id: Mapping[str, Mapping[str, Any]],
    point_rows_by_id: Mapping[str, Mapping[str, Any]],
    *, include_zheleznodorozhny: bool = False,
) -> list[dict[str, Any]]:
    """Return validated secondary inclusion references; never create observations.

    The caller must explicitly set ``include_zheleznodorozhny=True`` after root
    adoption. Canonical rows are matched by exact source ID, census year,
    population, and settlement type. ``point_rows_by_id`` is keyed by exact
    historical source ID (preferred), with point_use_id accepted for adapters.
    """
    folder = Path(folder)
    _verify_pins(folder)  # Verify every handoff file before reading selected rows.
    obs = _read_csv(folder / "scoped_inclusion_observations.csv")
    hooks = _index_unique(_read_csv(folder / "old_source_union_hooks.csv"), "source_record_id", "old-source hook")
    edges = _index_unique(_read_csv(folder / "secondary_inclusion_edges.csv"), "from_observation_id", "inclusion edge")
    point_uses = _index_unique(_read_csv(folder / "scoped_point_uses.csv"), "point_use_id", "point use")
    receivers = _index_unique(_read_csv(folder / "current_receiver_contexts.csv"), "source_record_id", "current receiver")
    all_records: list[tuple[dict[str, str], str, str, str, str]] = []
    for r in obs:
        if r["scope_status"] != "eligible_secondary_reported_inclusion_context_only":
            raise ValueError(f"unexpected main scope status for {r['source_record_id']}")
        all_records.append((r, r["old_parent_city_proper_source_record_id"],
                            r["old_parent_city_proper_population"], "main", ""))
    zfolder = folder / "zheleznodorozhny_secondary_context_supplement"
    if include_zheleznodorozhny:
        zobs = _read_csv(zfolder / "zheleznodorozhny_observations.csv")
        zhooks = _index_unique(_read_csv(zfolder / "zheleznodorozhny_old_city_proper_union_hooks.csv"),
                               "old_child_source_record_id", "Zheleznodorozhny old-parent hook")
        for r in zobs:
            if r["secondary_reported_context_only"].lower() != "true":
                raise ValueError("Zheleznodorozhny row is not marked secondary-only")
            h = zhooks[r["source_record_id"]]
            all_records.append((r, h["old_city_proper_parent_source_record_id"],
                                h["old_city_proper_population"], "zheleznodorozhny", ""))

    result: list[dict[str, Any]] = []
    seen_source: set[str] = set()
    seen_geonames: set[str] = set()
    seen_point_uses: set[str] = set()
    origin_cache: dict[Path, set[str]] = {}
    zrefs: dict[str, dict[str, str]] = {}
    if include_zheleznodorozhny:
        zrefs = _index_unique(_read_csv(zfolder / "zheleznodorozhny_existing_point_references.csv"),
                              "source_record_id", "Zheleznodorozhny point reference")
    for r, parent_id, parent_pop, scope, _ in all_records:
        source_id = _field(r, "source_record_id")
        if source_id in seen_source:
            raise ValueError(f"duplicate inclusion source ID: {source_id}")
        seen_source.add(source_id)
        year = _field(r, "source_year", "year")
        pop = _field(r, "population")
        typ = _field(r, "selected_source_type", "source_type_publisher", "source_type")
        _get_canonical(selected_rows_by_id, source_id, year, pop, typ)
        parent = _get_canonical(selected_rows_by_id, parent_id, year, parent_pop)
        # Parent must be an explicitly city-proper row, not an aggregate.
        parent_type = _canonical_tuple(parent)[3]
        if parent_type not in {"город", "city", "г"}:
            raise ValueError(f"old-year union target is not city proper: {parent_id} ({parent_type})")
        if scope == "main":
            hook = hooks[source_id]
            if hook["source_row_already_present_in_primary"].lower() != "true":
                raise ValueError(f"main inclusion row is not already selected: {source_id}")
            point_id = r["point_use_id"]
            point_ref = point_uses[point_id]
            receiver_id = r["current_receiver_source_record_id"]
            edge = edges[r["observation_id"]]
            if edge["current_receiver_source_record_id"] != receiver_id:
                raise ValueError(f"edge receiver mismatch for {source_id}")
            receiver = receivers[receiver_id]
            receiver_pop = receiver["population_context_only"]
            receiver_year = receiver["year"]
            if receiver_year != "2021" or receiver["population_is_child_value"].lower() != "false":
                raise ValueError(f"invalid current parent receiver context for {source_id}")
            if _field(receiver, "source_record_id") != receiver_id:
                raise ValueError(f"receiver source ID mismatch for {source_id}")
            _get_canonical(selected_rows_by_id, receiver_id, receiver_year, receiver_pop,
                           _field(receiver, "type"))
            if point_id not in seen_point_uses:
                _validate_geonames_point(point_ref, point_id, seen_geonames, origin_cache)
                seen_point_uses.add(point_id)
            # Accepted point ledgers are ordinarily keyed by target source ID;
            # accept point_use_id keys too for narrow in-memory adapters.
            point = point_rows_by_id.get(source_id) or point_rows_by_id.get(point_id)
            if point is None:
                raise ValueError(f"accepted point row missing: {point_id}")
            if _field(point, "coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES:
                raise ValueError(f"point row is not accepted by the canonical status set: {source_id}")
            point_source_id = _field(point, "target_source_record_id", "source_record_id", "point_use_id")
            if point_source_id and point_source_id not in {source_id, point_id}:
                raise ValueError(f"accepted point row belongs to another source: {source_id}")
            expected_coords = _coordinates(point_ref)
            actual_coords = _coordinates(point)
            if expected_coords != actual_coords:
                raise ValueError(f"accepted point coordinates mismatch for {point_id}")
            for field in ("national_additive", "ordinary_NP3_admission", "same_place_graph_identity_claimed",
                          "current_child_population_asserted", "parent_population_transfer_asserted"):
                if field in r and _bool(r[field], field):
                    raise ValueError(f"secondary context asserts prohibited {field}: {source_id}")
            if _field(point_ref, "measurement_date").casefold() not in {"unknown", ""}:
                raise ValueError(f"scoped point asserts a measurement date: {point_id}")
            if _bool(point_ref.get("direct_historical_coordinate_measurement", "False"),
                     "direct_historical_coordinate_measurement"):
                raise ValueError(f"scoped point claims a historical census-date measurement: {point_id}")
            if _text(r.get("population_raw")) != pop:
                raise ValueError(f"raw source population differs from normalized value: {source_id}")
            if hook["existing_primary_row_source_id"] != source_id or \
                    hook["existing_primary_row_population"] != pop:
                raise ValueError(f"old-source hook does not match selected row: {source_id}")
            if hook["strict_no_double_count_status"] != \
                    "old source row already in primary; sidecar contributes zero national count":
                raise ValueError(f"unexpected double-count hook for {source_id}")
        else:
            z = zrefs[source_id]
            point_id = ""
            receiver_id = r["receiver_source_record_id"]
            receiver_pop = r["current_receiver_population_context_only"]
            receiver_year = "2021"
            if z["coordinate_admission_status"] not in ACCEPTED_COORDINATE_STATUSES:
                raise ValueError(f"Zheleznodorozhny point reference not accepted: {source_id}")
            origin_path = Path(z["point_origin_file"])
            if not origin_path.is_file() or _sha256(origin_path) != z["point_origin_sha256"]:
                raise ValueError(f"existing Zheleznodorozhny point origin hash-invalid: {source_id}")
            point = point_rows_by_id.get(source_id)
            if point is None:
                raise ValueError(f"existing Zheleznodorozhny accepted point missing by exact source ID: {source_id}")
            if _field(point, "coordinate_admission_status") not in ACCEPTED_COORDINATE_STATUSES:
                raise ValueError(f"Zheleznodorozhny point row is not canonically accepted: {source_id}")
            if _field(point, "target_source_record_id", "source_record_id") != source_id:
                raise ValueError(f"Zheleznodorozhny point row belongs to another source: {source_id}")
            if _coordinates(point) != _coordinates(z):
                raise ValueError(f"existing Zheleznodorozhny accepted coordinates mismatch: {source_id}")
            for field in ("national_additive", "ordinary_NP3_admission", "same_place_graph_edge",
                          "current_child_population_asserted", "population_transfer_asserted"):
                if field in r and _bool(r[field], field):
                    raise ValueError(f"secondary context asserts prohibited {field}: {source_id}")
            if _field(r, "selected_primary_source_exists") and \
                    not _bool(r["selected_primary_source_exists"], "selected_primary_source_exists"):
                raise ValueError(f"Zheleznodorozhny source is not in selected primary rows: {source_id}")
        # Validate all three canonical tuples, including the 2021 receiver.
        receiver_row = selected_rows_by_id.get(receiver_id)
        if receiver_row is None:
            raise ValueError(f"selected canonical row missing: {receiver_id}")
        _get_canonical(selected_rows_by_id, receiver_id, receiver_year, receiver_pop,
                       _field(receiver_row, "type_raw", "settlement_type", "source_type", "type"))
        result.append({
            "source_record_id": source_id,
            "year": int(year),
            "population": int(pop),
            "source_type": typ,
            "old_same_year_city_proper_source_record_id": parent_id,
            "current_2021_receiver_source_record_id": receiver_id,
            "current_receiver_population_context_only": int(receiver_pop),
            "evidence_pins": {"handoff_receipt_sha256": _sha256(folder / "handoff_receipt.json"),
                              "source_file": _field(r, "source_file", "source_file_path"),
                              "source_sha256": _field(r, "source_sha256", "source_file_sha256"),
                              "source_locator": _field(r, "source_locator")},
            "status": "secondary_reported_inclusion_context_only",
            "scope": scope,
            "point_use_id": point_id or None,
            "point_row": point,
            "point_origin_reference": None if scope == "zheleznodorozhny" else {
                "file": point_ref["point_origin_file"], "sha256": point_ref["point_origin_sha256"],
                "locator": point_ref["point_origin_locator"],
                "historical_place_qid": point_ref["historical_place_qid"]},
            "population_additive": False,
            "ordinary_same_place_claim": False,
            "current_child_population_asserted": False,
        })
    return result


def apply_scoped_inclusion_reference(
    pop_by_source: Mapping[str, int], year: int, row: Mapping[str, Any], *,
    represented_current_receivers: set[str] | frozenset[str],
) -> dict[str, int]:
    """Union an already-selected old source row once into its existing series.

    For other years this is an identity copy. For the reference year, both the
    current receiver and old city-proper parent must already be represented.
    The historical source ID is inserted only if absent and must match exactly
    if present, preventing duplicate addition and parent/child aggregation.
    """
    out = dict(pop_by_source)
    old_year = int(row["year"])
    if int(year) != old_year:
        return out
    receiver_id = str(row["current_2021_receiver_source_record_id"])
    if receiver_id not in represented_current_receivers:
        raise ValueError(f"current receiver is not represented: {receiver_id}")
    parent_id = str(row["old_same_year_city_proper_source_record_id"])
    if parent_id not in out:
        raise ValueError(f"same-year city-proper parent is not represented: {parent_id}")
    source_id = str(row["source_record_id"])
    pop = int(row["population"])
    if source_id in out and int(out[source_id]) != pop:
        raise ValueError(f"existing old source population differs for {source_id}")
    out[source_id] = pop
    return out
