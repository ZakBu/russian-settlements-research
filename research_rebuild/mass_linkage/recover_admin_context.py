"""Recover one documented 2010 workbook's inherited district context.

Only exact R2 source_file/sheet/one-based-row matches with equal raw label and
population are emitted. The output is a reviewable context assertion, never a
population edit or a settlement identity admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import duckdb


SOURCE_FILE = "data/raw/2010/001_723371ec84_1._20NW_2010.xls"
SOURCE_SHEET = "NW"
SOURCE_HEADER_ROW = 4
SOURCE_FIRST_DATA_ROW = 6
REGION_COL = 2  # C, explicit on each settlement row in this workbook family
DISTRICT_COL = 3  # D, populated at block start and inherited within region
NAME_COL = 4  # E
POPULATION_COL = 5  # F
EXPECTED_HEADERS = {REGION_COL: "субъ2", DISTRICT_COL: "район", NAME_COL: "н.п.", POPULATION_COL: "всего"}
QUALITY = "confidentiality_perturbed_within_ten"
NORMALIZATION_VERSION = "nfkc-casefold-collapse-space-yo-e-context-strip-and-region-suffix-r1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path("/workspace/settlements-work/sources/admin_context_recovery")
NATIONAL_OUTPUT_ROOT = Path("/workspace/settlements-work/sources/admin_context_recovery_national_approved_subset")

OUTPUT_COLUMNS = [
    "assertion_id", "source_record_id", "assertion_status", "assertion_rule", "source_file", "source_sha256",
    "source_sheet", "source_row_1based", "source_row_ordinal_raw", "source_name_raw",
    "selected_name_raw", "source_label_matches_exact_normalized", "source_population_raw",
    "selected_population", "source_population_matches_exact", "source_region_raw",
    "source_region_normalized", "target_region_normalized", "source_region_matches_selected",
    "normalization_version", "source_explicit_district_raw",
    "source_context_kind", "recovered_district_raw",
    "recovered_district_normalized", "recovered_district_from_row_1based", "current_district_raw",
    "current_district_matches_source_context", "legacy_settlement_id_candidate",
    "population_value_quality", "identity_status", "valid_from", "valid_to",
]

# Layout profiles were read from the source worksheet headers and checked against
# row-level source labels/population. Unlisted workbooks remain out of scope.
# Columns are zero-based; headers are one-based worksheet rows.
SHEET_PROFILES: dict[str, dict[str, Any]] = {
    "data/raw/2010/001_723371ec84_1._20NW_2010.xls": {
        "sheet": "NW", "header_row": 4, "first_data_row": 6,
        "region_col": 2, "district_cols": [3], "name_cols": [4], "population_col": 5,
        "headers": {2: "субъ2", 3: "район", 4: "н.п.", 5: "всего"},
    },
    "data/raw/2010/002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls": {
        "sheet": "СК", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3, 4], "name_cols": [5], "population_col": 6,
        "headers": {2: "суб", 3: "р-н", 4: "р-н", 5: "н.п.", 6: "total"},
    },
    "data/raw/2010/003_eb441570b1_11._20Урал_ФО_2010.xls": {
        "sheet": "Урал", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3], "name_cols": [4], "population_col": 7,
        "headers": {2: "субъ2", 3: "район", 4: "н.п., полное название", 7: "всего"},
    },
    "data/raw/2010/004_486e984bdc_12._20Астр_Волгог_Ростов.xls": {
        "sheet": "Южный", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3, 4], "name_cols": [5, 6], "population_col": 7,
        "headers": {2: "субъекты", 3: "район", 4: "район", 7: "total"},
    },
    "data/raw/2010/005_888282bccc_13._20Краснодарский_край_2010.xls": {
        "sheet": "КК", "header_row": 4, "first_data_row": 7,
        "region_constant_cell": [2, 0], "district_cols": [1, 2], "name_cols": [3], "population_col": 4,
        "headers": {1: "район", 2: "район"},
    },
    "data/raw/2010/006_9b114a55c0_14._20Адыгея.xls": {
        "sheet": "адыг", "header_row": 4, "first_data_row": 7,
        "region_col": 1, "district_cols": [2], "name_cols": [3], "population_col": 4,
        "headers": {1: "субъекты", 2: "район", 4: "total"},
    },
    "data/raw/2010/007_27e8a60d91_15._20Kalmykia.xls": {
        "sheet": "калмыкия", "header_row": 4, "first_data_row": 7,
        "region_constant_cell": [2, 2], "district_cols": [1], "name_cols": [2], "population_col": 3,
        "headers": {1: "район"},
    },
    "data/raw/2010/008_342f3c208b_16._20Сиб_ФО_2010.xls": {
        "sheet": "Sib", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3], "name_cols": [4], "population_col": 5,
        "headers": {2: "субъ", 3: "район", 5: "всего"},
    },
    "data/raw/2010/009_81f8a0e73c_17._20ДВ_ФО_2010.xls": {
        "sheet": "ДВ", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3], "name_cols": [4], "population_col": 5,
        "headers": {2: "субъ", 3: "район", 4: "нп", 5: "всего"},
    },
    "data/raw/2010/012_5c339c0d0e_4._20Vologod_pskov_2010.xls": {
        "sheet": "Data Sheet", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3], "name_cols": [4], "population_col": 5,
        "headers": {2: "суб2", 3: "район"},
    },
    "data/raw/2010/014_5ca759eea0_5._20Nizheg_Kirov_202010.xls": {
        "sheet": "Data Sheet", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3], "name_cols": [4], "population_col": 5,
        "headers": {2: "обл", 3: "район", 4: "н.п.", 5: "total"},
    },
    "data/raw/2010/016_802d308e41_8._20Or_Penz_Perm_Samar_Saratov_Uly_2010.xls": {
        "sheet": "!!!", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3], "name_cols": [5], "population_col": 6,
        "headers": {2: "субъ", 3: "р-н", 6: "всего исходно"},
    },
    "data/raw/2010/017_68e0e4537e_9._20Basq_Mari_Mord_Tatar_Udm_Chuv_2010.xls": {
        "sheet": "!!!", "header_row": 4, "first_data_row": 7,
        "region_col": 2, "district_cols": [3], "name_cols": [5], "population_col": 6,
        "headers": {1: "субъ", 3: "район", 5: "нп", 6: "total"},
        "region_cell_requires_selected_region_match": True,
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
    return " ".join(text.split())


def _context_norm(value: Any) -> str:
    text = _norm(value).strip(" .,:;–—-\t")
    text = re.sub(r"(?:\s+|^)(?:район|р-н|р\.?\s*н\.?|district)$", "", text).strip(" .,:;–—-")
    return " ".join(text.split())


def _cell(sheet: Any, row: int, col: int) -> Any:
    if row >= sheet.nrows or col >= sheet.ncols:
        return None
    value = sheet.cell_value(row, col)
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _nonblank(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in {"", "-", "--", "–", "—"}
    return True


def _population_int(value: Any) -> int | None:
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


def _is_summary_or_header(name: Any) -> bool:
    text = _norm(name).strip(" .,:;–—-")
    if not text:
        return True
    return bool(
        re.match(r"^(?:(?:по\s+)?(?:всего|итого|справочно|население|район|область|субъект))(?:\b|$)", text)
        or re.search(r"\s+(?:район|округ)$", text)
    )


def _manifest_file_hash(manifest: Path, relpath: str) -> str:
    conn = duckdb.connect()
    try:
        path = str(manifest.resolve(strict=True))
        source = f"read_csv_auto('{path.replace(chr(39), chr(39)*2)}', all_varchar=true)" if manifest.suffix.casefold() == ".csv" else f"read_parquet('{path.replace(chr(39), chr(39)*2)}')"
        result = conn.execute(f"SELECT sha256 FROM {source} WHERE path = ? LIMIT 1", [relpath]).fetchone()
    finally:
        conn.close()
    if not result or not result[0]:
        raise ValueError(f"input manifest has no SHA-256 for {relpath}")
    return str(result[0])


def _check_source_headers(sheet: Any) -> dict[str, Any]:
    header_index = SOURCE_HEADER_ROW - 1
    actual = {col: _norm(_cell(sheet, header_index, col)) for col in EXPECTED_HEADERS}
    expected = {col: _norm(value) for col, value in EXPECTED_HEADERS.items()}
    if actual != expected:
        raise ValueError(f"source sheet structure does not match the audited NW layout: {actual}")
    return {str(col): {"header_raw": _cell(sheet, header_index, col), "role": role}
            for col, role in ((REGION_COL, "region"), (DISTRICT_COL, "district"),
                              (NAME_COL, "settlement_name"), (POPULATION_COL, "population"))}


def recover_admin_context(selection_path: Path, raw_root: Path, manifest_path: Path) -> dict[str, Any]:
    """Return verified rows and diagnostics for the NW workbook only."""
    try:
        import xlrd  # lazy dependency: only required when reproducing XLS recovery
    except ImportError as exc:
        raise RuntimeError("xlrd is required to read the archived XLS source") from exc

    selection_path = Path(selection_path).resolve(strict=True)
    raw_root = Path(raw_root).resolve(strict=True)
    manifest_path = Path(manifest_path).resolve(strict=True)
    selection_sha = sha256_file(selection_path)
    source_path = (raw_root / SOURCE_FILE).resolve(strict=True)
    if not source_path.is_relative_to(raw_root):
        raise ValueError("source path escapes raw_root")
    expected_source_sha = _manifest_file_hash(manifest_path, SOURCE_FILE)
    actual_source_sha = sha256_file(source_path)
    if actual_source_sha != expected_source_sha:
        raise ValueError(f"source workbook hash mismatch: expected {expected_source_sha}, got {actual_source_sha}")

    conn = duckdb.connect()
    try:
        selected = conn.execute(
            "SELECT source_record_id, source_file, source_sheet, source_row, source_native_id, "
            "source_name_raw, district_raw, region_raw, population, population_value_quality, settlement_id "
            "FROM read_parquet(?) WHERE census_year = 2010 AND source_file = ? AND source_sheet = ? "
            "AND population_value_quality = ? ORDER BY source_row",
            [str(selection_path), SOURCE_FILE, SOURCE_SHEET, QUALITY],
        ).fetchall()
        total_protected = int(conn.execute(
            "SELECT COUNT(*) FROM read_parquet(?) WHERE census_year=2010 "
            "AND population_value_quality=?", [str(selection_path), QUALITY]
        ).fetchone()[0])
        all_2010 = int(conn.execute(
            "SELECT COUNT(*) FROM read_parquet(?) WHERE census_year=2010", [str(selection_path)]
        ).fetchone()[0])
    finally:
        conn.close()

    if not selected:
        raise ValueError("the pinned selection contains no protected observations for the audited workbook")
    book = xlrd.open_workbook(str(source_path), on_demand=True)
    try:
        if SOURCE_SHEET not in book.sheet_names():
            raise ValueError(f"source sheet {SOURCE_SHEET!r} not found")
        sheet = book.sheet_by_name(SOURCE_SHEET)
        header_map = _check_source_headers(sheet)
        selected_by_row = {int(row[3]): row for row in selected}
        state_region_raw: str | None = None
        state_region_norm: str | None = None
        state_district_raw: str | None = None
        state_district_norm: str | None = None
        district_start_row: int | None = None
        assertions: list[dict[str, Any]] = []
        diagnostics = {
            "selected_protected_rows": len(selected), "raw_rows_addressed": 0,
            "source_label_mismatch": 0, "source_population_mismatch": 0,
            "missing_explicit_region": 0, "missing_context_district": 0,
            "current_district_nonblank": 0, "current_district_matches_explicit": 0,
            "current_district_conflict": 0, "recovered_blank_district": 0,
            "already_filled_explicit_district": 0,
        }
        for row_zero in range(SOURCE_FIRST_DATA_ROW - 1, sheet.nrows):
            row_1 = row_zero + 1
            region_raw = _cell(sheet, row_zero, REGION_COL)
            district_raw = _cell(sheet, row_zero, DISTRICT_COL)
            name_raw = _cell(sheet, row_zero, NAME_COL)
            pop_raw = _cell(sheet, row_zero, POPULATION_COL)
            region_norm = _context_norm(region_raw)
            if not region_norm:
                state_region_raw = state_region_norm = state_district_raw = state_district_norm = None
                district_start_row = None
                continue
            if region_norm != state_region_norm:
                state_region_raw, state_region_norm = str(region_raw), region_norm
                state_district_raw = state_district_norm = None
                district_start_row = None

            pop_int = _population_int(pop_raw)
            settlement_row = _nonblank(name_raw) and not _is_summary_or_header(name_raw) and pop_int is not None
            if not settlement_row:
                # Spacers, headers and summaries terminate context inheritance.
                state_district_raw = state_district_norm = None
                district_start_row = None
                continue

            if _nonblank(district_raw):
                state_district_raw = str(district_raw)
                state_district_norm = _context_norm(district_raw)
                district_start_row = row_1

            target = selected_by_row.get(row_1)
            if target is None:
                continue
            diagnostics["raw_rows_addressed"] += 1
            (source_record_id, source_file, source_sheet, source_row, source_native_id,
             selected_name, current_district, selected_region, selected_population,
             quality, settlement_id) = target
            label_ok = _norm(name_raw) == _norm(selected_name)
            pop_ok = pop_int == int(selected_population) if selected_population is not None else False
            if not label_ok:
                diagnostics["source_label_mismatch"] += 1
            if not pop_ok:
                diagnostics["source_population_mismatch"] += 1
            if not state_region_norm:
                diagnostics["missing_explicit_region"] += 1
            if not state_district_norm:
                diagnostics["missing_context_district"] += 1
            if _nonblank(current_district):
                diagnostics["current_district_nonblank"] += 1
                if _context_norm(current_district) == state_district_norm:
                    diagnostics["current_district_matches_explicit"] += 1
                else:
                    diagnostics["current_district_conflict"] += 1
            if not label_ok or not pop_ok or not state_region_norm or not state_district_norm:
                continue
            if _nonblank(current_district) and _context_norm(current_district) != state_district_norm:
                continue
            assertion_type = "district_context_confirmed_from_explicit_source_cell" if _nonblank(district_raw) else "district_context_inherited_within_explicit_region_block"
            if _nonblank(current_district):
                diagnostics["already_filled_explicit_district"] += 1
            else:
                diagnostics["recovered_blank_district"] += 1
            assertions.append({
                "assertion_id": f"{source_record_id}:district-context",
                "assertion_status": "source_context_assertion_pending_review",
                "assertion_rule": assertion_type,
                "source_file": source_file, "source_sha256": actual_source_sha,
                "source_sheet": source_sheet, "source_row_1based": int(source_row),
                "source_row_ordinal_raw": source_native_id,
                "source_name_raw": str(name_raw), "selected_name_raw": str(selected_name),
                "source_label_matches_exact_normalized": label_ok,
                "source_population_raw": str(pop_raw), "selected_population": int(selected_population),
                "source_population_matches_exact": pop_ok,
                "source_region_raw": str(region_raw), "source_region_normalized": state_region_norm,
                "source_explicit_district_raw": str(district_raw) if _nonblank(district_raw) else None,
                "recovered_district_raw": state_district_raw,
                "recovered_district_normalized": state_district_norm,
                "recovered_district_from_row_1based": district_start_row,
                "current_district_raw": str(current_district) if _nonblank(current_district) else None,
                "current_district_matches_source_context": (
                    _context_norm(current_district) == state_district_norm if _nonblank(current_district) else None
                ),
                "legacy_settlement_id_candidate": settlement_id,
                "population_value_quality": quality,
                "identity_status": "not_evaluated_not_admitted_by_context_recovery",
                "valid_from": None, "valid_to": None,
            })
        unaddressed = set(selected_by_row) - {r["source_row_1based"] for r in assertions}
        diagnostics["selected_rows_without_assertion"] = len(unaddressed)
        diagnostics["selected_rows_not_encountered_as_settlement_rows"] = len(selected_by_row) - diagnostics["raw_rows_addressed"]
        return {
            "recovery_version": "r2-2010-nw-admin-context-r1",
            "selected_file": str(selection_path), "selected_sha256": selection_sha,
            "raw_root": str(raw_root), "manifest_path": str(manifest_path),
            "source_file": SOURCE_FILE, "source_sha256_expected": expected_source_sha,
            "source_sha256_actual": actual_source_sha, "source_sheet": SOURCE_SHEET,
            "source_header_row_1based": SOURCE_HEADER_ROW,
            "source_first_data_row_1based": SOURCE_FIRST_DATA_ROW,
            "source_columns": header_map,
            "scope": {"census_year": 2010, "population_value_quality": QUALITY,
                      "one_source_file_and_sheet_only": True, "all_2010_selected_rows": all_2010,
                      "protected_rows_nationally": total_protected,
                      "protected_rows_in_audited_sheet": len(selected)},
            "diagnostics": diagnostics, "assertions": assertions,
            "interpretation": "Recovered district text is source hierarchy context only; it does not change protected population values, define census-date legal boundaries, or establish place identity.",
        }
    finally:
        book.unload_sheet(SOURCE_SHEET)
        book.release_resources()


def _region_norm(value: Any) -> str:
    text = _context_norm(value)
    return re.sub(
        r"(?:\s+|^)(?:область|обл\.?|край|республика|респ\.?|автономный округ|автономная область|федеральный округ|ао)$",
        "", text,
    ).strip()


def _usable_context(value: Any) -> bool:
    """Require an actual name rather than source placeholders such as ?? or !."""
    return _nonblank(value) and bool(re.search(r"[\w\u0400-\u04ff]", str(value), re.UNICODE))


def _context_kind(value: Any) -> str:
    if _context_norm(value) in {"владикавказ", "г.астрахань", "астрахань", "омск", "казань"}:
        return "urban_administrative_parent_unknown_scope"
    return "district_or_urban_administrative_parent_unclassified"


def _label_part(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() if value is not None else ""


def _profile_region(sheet: Any, row_zero: int, profile: dict[str, Any]) -> Any:
    if "region_col" in profile:
        return _cell(sheet, row_zero, profile["region_col"])
    rr, cc = profile["region_constant_cell"]
    return _cell(sheet, rr - 1, cc)


def _validate_profile(sheet: Any, profile: dict[str, Any]) -> dict[str, Any]:
    header_row = profile["header_row"] - 1
    actual: dict[str, Any] = {}
    for col, expected in profile.get("headers", {}).items():
        got = _cell(sheet, header_row, int(col))
        actual[str(col)] = got
        if _norm(got) != _norm(expected):
            raise ValueError(f"profile header mismatch at column {col + 1}: expected {expected!r}, got {got!r}")
    if "region_constant_cell" in profile:
        rr, cc = profile["region_constant_cell"]
        region_title = _cell(sheet, rr - 1, cc)
        if not _nonblank(region_title):
            raise ValueError("expected a nonblank explicit region title cell")
        actual["region_constant_cell"] = {"row_1based": rr, "column_1based": cc + 1,
                                          "value_raw": region_title}
    return {"header_row_1based": profile["header_row"], "headers_checked": actual,
            "region_source": (f"column_{profile['region_col'] + 1}_repeated_per_row" if "region_col" in profile else "explicit_sheet_region_title") ,
            "district_columns_1based": [c + 1 for c in profile["district_cols"]],
            "name_columns_1based": [c + 1 for c in profile["name_cols"]],
            "population_column_1based": profile["population_col"] + 1}


def recover_national_admin_context(selection_path: Path, raw_root: Path,
                                   manifest_path: Path) -> dict[str, Any]:
    """Recover context only for the individually profiled grouped 2010 sheets."""
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("xlrd is required to read archived XLS source files") from exc
    selection_path = Path(selection_path).resolve(strict=True)
    raw_root = Path(raw_root).resolve(strict=True)
    manifest_path = Path(manifest_path).resolve(strict=True)
    selection_sha = sha256_file(selection_path)
    conn = duckdb.connect()
    try:
        all_protected = int(conn.execute(
            "SELECT COUNT(*) FROM read_parquet(?) WHERE census_year=2010 AND population_value_quality=?",
            [str(selection_path), QUALITY],
        ).fetchone()[0])
        all_rows = conn.execute(
            "SELECT source_file, source_sheet, COUNT(*) AS row_count, "
            "COUNT(*) FILTER (WHERE district_raw IS NULL OR trim(district_raw)='') AS blank_district "
            "FROM read_parquet(?) WHERE census_year=2010 AND population_value_quality=? "
            "AND regexp_matches(source_file, '^data/raw/2010/0(0[1-9]|1[0-9])_') "
            "GROUP BY 1,2 ORDER BY 1,2",
            [str(selection_path), QUALITY],
        ).fetchall()
        records: dict[tuple[str, str], list[tuple[Any, ...]]] = {}
        for source_file in SHEET_PROFILES:
            profile = SHEET_PROFILES[source_file]
            source_rows = conn.execute(
                "SELECT source_record_id, source_file, source_sheet, source_row, source_native_id, "
                "source_name_raw, settlement_name, district_raw, region_raw, population, "
                "population_value_quality, settlement_id FROM read_parquet(?) "
                "WHERE census_year=2010 AND source_file=? AND source_sheet=? "
                "AND population_value_quality=? ORDER BY source_row",
                [str(selection_path), source_file, profile["sheet"], QUALITY],
            ).fetchall()
            if source_rows:
                records[(source_file, profile["sheet"])] = source_rows
    finally:
        conn.close()

    assertions: list[dict[str, Any]] = []
    file_reports: dict[str, Any] = {}
    source_hashes: dict[str, str] = {}
    boundary_events: list[dict[str, Any]] = []
    for (source_file, sheet_name), targets in records.items():
        profile = SHEET_PROFILES[source_file]
        path = (raw_root / source_file).resolve(strict=True)
        if not path.is_relative_to(raw_root):
            raise ValueError("source path escapes raw_root")
        expected_sha = _manifest_file_hash(manifest_path, source_file)
        actual_sha = sha256_file(path)
        if actual_sha != expected_sha:
            raise ValueError(f"source workbook hash mismatch for {source_file}: expected {expected_sha}, got {actual_sha}")
        source_hashes[source_file] = actual_sha
        book = xlrd.open_workbook(str(path), on_demand=True)
        try:
            if sheet_name not in book.sheet_names():
                raise ValueError(f"expected sheet {sheet_name!r} missing in {source_file}")
            sheet = book.sheet_by_name(sheet_name)
            profile_receipt = _validate_profile(sheet, profile)
            targets_by_row = {int(r[3]): r for r in targets}
            report = {
                "sheet": sheet_name, "source_sha256": actual_sha,
                "layout": profile_receipt, "selected_protected_rows": len(targets),
                "selected_blank_district_rows": sum(not _nonblank(r[7]) for r in targets),
                "raw_rows_addressed": 0, "exact_name_matches": 0,
                "exact_population_matches": 0, "name_mismatches": 0,
                "population_mismatches": 0, "region_matches_selected": 0,
                "region_mismatches_selected": 0, "missing_explicit_region_rows": 0,
                "blank_district_rows_with_context": 0, "blank_district_rows_without_context": 0,
                "already_filled_districts": 0, "already_filled_district_matches": 0,
                "already_filled_district_conflicts": 0, "ambiguous_district_rows": 0,
                "placeholder_context_rows": 0, "source_context_conflict_rows": [],
                "admin_parent_reset_markers": [], "admin_parent_context_comparisons": [],
                "region_change_count": 0, "empty_region_reset_count": 0,
                "invalid_row_reset_count": 0, "district_block_start_count": 0,
                "region_change_rows": [], "district_block_starts": [],
                "name_mismatch_samples": [], "region_mismatch_samples": [],
                "population_mismatch_samples": [], "current_district_conflict_samples": [],
                "blank_no_context_samples": [],
            }
            state_region_raw: str | None = None
            state_region_norm: str | None = None
            state_district_raw: str | None = None
            state_district_norm: str | None = None
            district_start_row: int | None = None
            pending_urban_parent: dict[str, Any] | None = None
            for row_zero in range(profile["first_data_row"] - 1, sheet.nrows):
                row_1 = row_zero + 1
                region_raw = _profile_region(sheet, row_zero, profile)
                region_norm = _region_norm(region_raw)
                if not region_norm:
                    if state_region_norm is not None or state_district_norm is not None:
                        report["empty_region_reset_count"] += 1
                        boundary_events.append({"source_file": source_file, "source_sheet": sheet_name,
                                                "source_row_1based": row_1, "kind": "empty_region_reset"})
                    state_region_raw = state_region_norm = state_district_raw = state_district_norm = None
                    district_start_row = None
                    pending_urban_parent = None
                    continue
                if region_norm != state_region_norm:
                    if state_region_norm is not None:
                        report["region_change_count"] += 1
                        event = {"source_file": source_file, "source_sheet": sheet_name,
                                 "source_row_1based": row_1, "kind": "region_change",
                                 "from_region_raw": state_region_raw, "to_region_raw": str(region_raw)}
                        report["region_change_rows"].append(event)
                        boundary_events.append(event)
                    state_region_raw, state_region_norm = str(region_raw), region_norm
                    state_district_raw = state_district_norm = None
                    district_start_row = None
                    pending_urban_parent = None

                name_parts = [_cell(sheet, row_zero, col) for col in profile["name_cols"]]
                source_name = " ".join(_label_part(value) for value in name_parts if _nonblank(value)).strip()
                source_population_raw = _cell(sheet, row_zero, profile["population_col"])
                source_population = _population_int(source_population_raw)
                is_data_row = bool(source_name and not _is_summary_or_header(source_name) and source_population is not None)
                district_values = [_cell(sheet, row_zero, col) for col in profile["district_cols"]]
                nonblank_districts = [str(v) for v in district_values if _nonblank(v)]
                if not is_data_row:
                    if (source_name and re.search(r"\s+(?:район|округ)$", _norm(source_name))
                            and nonblank_districts and all(_usable_context(v) for v in nonblank_districts)):
                        parent_norms = {_context_norm(v) for v in nonblank_districts}
                        if len(parent_norms) == 1:
                            pending_urban_parent = {
                                "source_context_raw": nonblank_districts[0],
                                "source_context_kind": "urban_administrative_parent_unknown_scope",
                                "source_marker_name_raw": source_name,
                                "source_marker_row_1based": row_1,
                                "district_columns_1based": [col + 1 for col in profile["district_cols"]],
                                "source_region_raw": str(region_raw),
                            }
                            report["admin_parent_reset_markers"].append(dict(pending_urban_parent))
                    elif nonblank_districts:
                        pending_urban_parent = None
                    state_district_raw = state_district_norm = None
                    district_start_row = None
                    report["invalid_row_reset_count"] += 1
                    continue

                if nonblank_districts:
                    pending_urban_parent = None
                district_norms = {_context_norm(v) for v in nonblank_districts}
                if len(district_norms) > 1:
                    state_district_raw = state_district_norm = None
                    district_start_row = None
                    report["ambiguous_district_rows"] += 1
                elif nonblank_districts:
                    new_district_raw = nonblank_districts[0]
                    new_district_norm = next(iter(district_norms))
                    if new_district_norm != state_district_norm:
                        report["district_block_start_count"] += 1
                        report["district_block_starts"].append({
                            "source_row_1based": row_1, "region_raw": str(region_raw),
                            "district_raw": new_district_raw,
                        })
                    if _usable_context(new_district_raw):
                        state_district_raw = new_district_raw
                        state_district_norm = new_district_norm
                        district_start_row = row_1
                    else:
                        state_district_raw = state_district_norm = None
                        district_start_row = None
                        report["placeholder_context_rows"] += 1

                target = targets_by_row.get(row_1)
                if target is None:
                    continue
                report["raw_rows_addressed"] += 1
                (source_record_id, _, _, source_row, source_native_id, source_name_raw,
                 selected_name, current_district, selected_region, selected_population,
                 quality, settlement_id) = target
                if pending_urban_parent and _nonblank(current_district):
                    if _context_norm(current_district) != _context_norm(pending_urban_parent["source_context_raw"]):
                        report["admin_parent_context_comparisons"].append({
                            **pending_urban_parent, "source_row_1based": row_1,
                            "source_record_id": source_record_id, "source_name_raw": source_name,
                            "current_district_raw": current_district,
                            "selected_region_raw": selected_region,
                            "source_population_raw": source_population_raw,
                            "selected_population": selected_population,
                            "comparison_status": "source_urban_parent_differs_from_current_R2_district",
                            "admission": "held_for_review",
                        })
                label_candidates = [("source_name_raw", source_name_raw), ("settlement_name", selected_name)]
                matched_label_field = next((field for field, value in label_candidates
                                            if _norm(source_name) == _norm(value)), None)
                name_ok = matched_label_field is not None
                population_ok = source_population == int(selected_population) if selected_population is not None else False
                # The source-region column controls inheritance/reset; assertions
                # require equality under deterministic normalization. Nested or
                # alternate names remain held for authoritative alias review.
                region_ok = (_region_norm(selected_region) == state_region_norm
                             if _nonblank(selected_region) else False)
                if name_ok:
                    report["exact_name_matches"] += 1
                else:
                    report["name_mismatches"] += 1
                    if len(report["name_mismatch_samples"]) < 20:
                        report["name_mismatch_samples"].append({
                            "source_row_1based": row_1, "source_record_id": source_record_id,
                            "source_name_raw": source_name, "selected_source_name_raw": source_name_raw,
                            "selected_settlement_name": selected_name,
                        })
                if population_ok:
                    report["exact_population_matches"] += 1
                else:
                    report["population_mismatches"] += 1
                    if len(report["population_mismatch_samples"]) < 20:
                        report["population_mismatch_samples"].append({
                            "source_row_1based": row_1, "source_record_id": source_record_id,
                            "source_population_raw": source_population_raw,
                            "selected_population": selected_population,
                        })
                if region_ok:
                    report["region_matches_selected"] += 1
                else:
                    report["region_mismatches_selected"] += 1
                    if len(report["region_mismatch_samples"]) < 20:
                        report["region_mismatch_samples"].append({
                            "source_row_1based": row_1, "source_record_id": source_record_id,
                            "source_region_raw": region_raw, "selected_region_raw": selected_region,
                        })
                if not state_region_norm:
                    report["missing_explicit_region_rows"] += 1
                if not _nonblank(current_district):
                    if state_district_norm:
                        report["blank_district_rows_with_context"] += 1
                    else:
                        report["blank_district_rows_without_context"] += 1
                        if len(report["blank_no_context_samples"]) < 20:
                            report["blank_no_context_samples"].append({
                                "source_row_1based": row_1, "source_record_id": source_record_id,
                                "region_raw": region_raw, "name_raw": source_name,
                            })
                else:
                    report["already_filled_districts"] += 1
                    if state_district_norm and _context_norm(current_district) == state_district_norm:
                        report["already_filled_district_matches"] += 1
                    else:
                        report["already_filled_district_conflicts"] += 1
                        report["source_context_conflict_rows"].append({
                            "source_row_1based": row_1, "source_record_id": source_record_id,
                            "source_name_raw": source_name,
                            "current_district_raw": current_district,
                            "source_context_raw": state_district_raw,
                            "source_context_from_row_1based": district_start_row,
                            "source_context_kind": _context_kind(state_district_raw) if state_district_raw else "unknown",
                            "district_columns_1based": [col + 1 for col in profile["district_cols"]],
                            "interpretation": "source hierarchy label differs from current R2 district; preserve as conflict, do not overwrite or admit",
                        })
                        if len(report["current_district_conflict_samples"]) < 20:
                            report["current_district_conflict_samples"].append({
                                "source_row_1based": row_1, "source_record_id": source_record_id,
                                "current_district_raw": current_district,
                                "source_context_district_raw": state_district_raw,
                            })
                if not (name_ok and population_ok and region_ok and state_region_norm and state_district_norm):
                    continue
                if _nonblank(current_district) and _context_norm(current_district) != state_district_norm:
                    continue
                assertion_type = (
                    "source_hierarchy_context_from_explicit_source_row" if nonblank_districts
                    else "source_hierarchy_context_inherited_within_same_explicit_region"
                )
                assertions.append({
                    "assertion_id": f"{source_record_id}:district-context",
                    "source_record_id": source_record_id,
                    "assertion_status": "source_context_assertion_pending_review",
                    "assertion_rule": assertion_type,
                    "source_file": source_file, "source_sha256": actual_sha,
                    "source_sheet": sheet_name, "source_row_1based": int(source_row),
                    "source_row_ordinal_raw": source_native_id,
                    "source_name_raw": source_name, "selected_name_raw": str(source_name_raw),
                    "source_label_matches_exact_normalized": name_ok,
                    "source_population_raw": str(source_population_raw), "selected_population": int(selected_population),
                    "source_population_matches_exact": population_ok,
                    "source_region_raw": str(region_raw), "source_region_normalized": state_region_norm,
                    "target_region_normalized": _region_norm(selected_region),
                    "source_region_matches_selected": region_ok,
                    "normalization_version": NORMALIZATION_VERSION,
                    "source_explicit_district_raw": " | ".join(nonblank_districts) if nonblank_districts else None,
                    "source_context_kind": _context_kind(state_district_raw),
                    "recovered_district_raw": state_district_raw,
                    "recovered_district_normalized": state_district_norm,
                    "recovered_district_from_row_1based": district_start_row,
                    "current_district_raw": str(current_district) if _nonblank(current_district) else None,
                    "current_district_matches_source_context": (
                        _context_norm(current_district) == state_district_norm if _nonblank(current_district) else None
                    ),
                    "legacy_settlement_id_candidate": settlement_id,
                    "population_value_quality": quality,
                    "identity_status": "not_evaluated_not_admitted_by_context_recovery",
                    "valid_from": None, "valid_to": None,
                })
            report["assertion_count"] = sum(r["source_file"] == source_file for r in assertions)
            report["unasserted_target_rows"] = report["selected_protected_rows"] - report["assertion_count"]
            file_reports[source_file] = report
        finally:
            book.unload_sheet(sheet_name)
            book.release_resources()

    profiled_rows = {(f, s): len(rs) for (f, s), rs in records.items()}
    source_inventory: dict[str, Any] = {}
    for source_file, sheet_name, count, blank in all_rows:
        source_file, sheet_name = str(source_file), str(sheet_name)
        if source_file in SHEET_PROFILES:
            disposition = "profiled_exact_rawrow_validation"
            source_sha = source_hashes[source_file]
            header_fields = file_reports[source_file]["layout"]["headers_checked"]
            district_header_cols = file_reports[source_file]["layout"]["district_columns_1based"]
        else:
            raw_path = (raw_root / source_file).resolve(strict=True)
            if not raw_path.is_relative_to(raw_root):
                raise ValueError("source path escapes raw_root")
            expected_sha = _manifest_file_hash(manifest_path, source_file)
            source_sha = sha256_file(raw_path)
            if source_sha != expected_sha:
                raise ValueError(f"source workbook hash mismatch for {source_file}")
            source_hashes[source_file] = source_sha
            import xlrd
            book = xlrd.open_workbook(str(raw_path), on_demand=True)
            try:
                if sheet_name not in book.sheet_names():
                    raise ValueError(f"source sheet {sheet_name!r} missing in {source_file}")
                sheet = book.sheet_by_name(sheet_name)
                header_fields = {}
                for row_i in range(min(8, sheet.nrows)):
                    cells = {str(col + 1): _cell(sheet, row_i, col)
                             for col in range(min(sheet.ncols, 16)) if _nonblank(_cell(sheet, row_i, col))}
                    if cells:
                        header_fields[str(row_i + 1)] = cells
                district_header_cols = sorted({
                    int(col) for row in header_fields.values() for col, value in row.items()
                    if re.search(r"район|р-н", _norm(value))
                })
            finally:
                book.unload_sheet(sheet_name)
                book.release_resources()
            if not district_header_cols and int(blank):
                disposition = "unresolved_no_district_column_in_first_eight_rows"
            elif int(blank) == 0:
                disposition = "district_field_present_or_not_needed_no_blank_rows"
            else:
                disposition = "unprofiled_layout_not_recovered"
        source_inventory[f"{source_file}::{sheet_name}"] = {
            "sheet": sheet_name, "protected_rows": int(count), "blank_current_district_rows": int(blank),
            "source_sha256": source_sha, "header_fields_first_eight_rows": header_fields,
            "district_header_columns_1based": district_header_cols, "disposition": disposition,
        }
    return {
        "recovery_version": "r2-2010-grouped-sheets-admin-context-r1",
        "normalization_version": NORMALIZATION_VERSION,
        "selected_file": str(selection_path), "selected_sha256": selection_sha,
        "raw_root": str(raw_root), "manifest_path": str(manifest_path),
        "scope": {"census_year": 2010, "population_value_quality": QUALITY,
                  "protected_rows_nationally": all_protected,
                  "grouped_workbook_protected_rows": sum(int(row[2]) for row in all_rows),
                  "profiled_protected_rows": sum(profiled_rows.values()),
                  "unprofiled_source_sheet_count": sum(1 for key in source_inventory
                                                        if key.split("::", 1)[0] not in SHEET_PROFILES)},
        "source_inventory": source_inventory, "profiled_sheets": file_reports,
        "assertions": assertions,
        "source_sha256_by_file": source_hashes,
        "diagnostics": {
            "assertion_rows": len(assertions),
            "rows_matching_exact_source_label_population_region_and_context": len(assertions),
            "blank_current_district_rows_with_source_context": sum(r["current_district_raw"] is None for r in assertions),
            "current_filled_districts_checked": sum(v["already_filled_districts"] for v in file_reports.values()),
            "current_filled_district_matches": sum(v["already_filled_district_matches"] for v in file_reports.values()),
            "current_filled_district_conflicts": sum(v["already_filled_district_conflicts"] for v in file_reports.values()),
            "source_label_mismatches": sum(v["name_mismatches"] for v in file_reports.values()),
            "source_population_mismatches": sum(v["population_mismatches"] for v in file_reports.values()),
            "selected_region_mismatches": sum(v["region_mismatches_selected"] for v in file_reports.values()),
            "blank_district_rows_without_source_context": sum(v["blank_district_rows_without_context"] for v in file_reports.values()),
            "rows_with_nonblank_but_unusable_source_context": sum(v["placeholder_context_rows"] for v in file_reports.values()),
            "urban_parent_reset_markers": sum(len(v["admin_parent_reset_markers"]) for v in file_reports.values()),
            "urban_parent_context_disagreement_rows": sum(len(v["admin_parent_context_comparisons"]) for v in file_reports.values()),
            "boundary_events": boundary_events,
        },
        "interpretation": "Source hierarchy-context assertions leave population and frozen R2 untouched. A source cell headed district may encode an urban administrative parent; conflicts with current R2 districts are preserved in diagnostics and excluded. Context does not define census-date legal boundaries or establish place identity.",
    }


def write_recovery(selection_path: Path, raw_root: Path, manifest_path: Path,
                   output_dir: Path = OUTPUT_ROOT) -> dict[str, Any]:
    out = Path(output_dir).expanduser().resolve()
    try:
        out.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("recovery outputs must stay outside the Git checkout")
    try:
        out.relative_to(OUTPUT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"recovery outputs must be under {OUTPUT_ROOT}") from exc
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    result = recover_admin_context(selection_path, raw_root, manifest_path)
    assertions = result.pop("assertions")
    claim_path = out / "admin_context_assertions.parquet"
    conn = duckdb.connect()
    try:
        import pandas as pd
        df = pd.DataFrame.from_records(assertions, columns=OUTPUT_COLUMNS)
        conn.register("assertions", df)
        cols = ", ".join(f'"{col}"' for col in OUTPUT_COLUMNS)
        conn.execute(f"COPY (SELECT {cols} FROM assertions) TO '{str(claim_path).replace(chr(39), chr(39)*2)}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        conn.close()
    result["output"] = {"path": str(claim_path), "rows": len(assertions), "bytes": claim_path.stat().st_size,
                        "sha256": sha256_file(claim_path)}
    result["code_sha256"] = sha256_file(Path(__file__))
    receipt_path = out / "recovery_receipt.json"
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["receipt_path"] = str(receipt_path)
    result["receipt_sha256"] = sha256_file(receipt_path)
    return result


def write_national_recovery(selection_path: Path, raw_root: Path, manifest_path: Path,
                            output_dir: Path = NATIONAL_OUTPUT_ROOT) -> dict[str, Any]:
    out = Path(output_dir).expanduser().resolve()
    try:
        out.relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("recovery outputs must stay outside the Git checkout")
    try:
        out.relative_to(NATIONAL_OUTPUT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"national recovery outputs must be under {NATIONAL_OUTPUT_ROOT}") from exc
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    result = recover_national_admin_context(selection_path, raw_root, manifest_path)
    assertions = result.pop("assertions")
    claim_path = out / "admin_context_assertions.parquet"
    conn = duckdb.connect()
    try:
        import pandas as pd
        df = pd.DataFrame.from_records(assertions, columns=OUTPUT_COLUMNS)
        conn.register("assertions", df)
        cols = ", ".join(f'"{col}"' for col in OUTPUT_COLUMNS)
        target = str(claim_path).replace("'", "''")
        conn.execute(f"COPY (SELECT {cols} FROM assertions) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        conn.close()
    result["output"] = {"path": str(claim_path), "rows": len(assertions), "bytes": claim_path.stat().st_size,
                        "sha256": sha256_file(claim_path)}
    result["code_sha256"] = sha256_file(Path(__file__))
    receipt_path = out / "recovery_receipt.json"
    receipt_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["receipt_path"] = str(receipt_path)
    result["receipt_sha256"] = sha256_file(receipt_path)
    return result


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=NATIONAL_OUTPUT_ROOT)
    args = parser.parse_args()
    result = write_national_recovery(args.selection, args.raw_root, args.manifest, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
