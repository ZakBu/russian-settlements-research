"""Extract the historical census comparison cells in Rosstat Table 4.9.

These are published rounded city-series comparisons attached to already reviewed
2021 publication rows. They are supplementary source observations; this builder
does not create census records, denominators, identity decisions, or coordinates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

SOURCE_REL = Path("research_rebuild/evidence/discovery/yearbook_table49_2010_2021_candidates_r2_20260930")
PDF_REL = Path("research_rebuild/evidence/discovery/official_sources_2010_2021_r2_yearbook/raw/rosstat_russian_statistical_yearbook_2024.pdf")
PDF_SHA = "bac43b438869d7b11ca595acd121726833d2bf2e54004351db825cade4c29da7"
ROWS_SHA = "43d97c7d655c7e48d23d742191a063b92e56892431c38604bad8e8951ed77688"
YEARS = (2002, 2010, 2021)
DATE_INFO = {
    2002: ("2002-10-09", "source_footnote"),
    2010: ("2010-10-14", "source_footnote"),
    2021: ("2021-10-01", "source_footnote"),
}
NUMBER = re.compile(r"\d[\d ]*")
CELL = re.compile(r"(?:\d[\d ]*|…|\.\.\.|—|–|-)?")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _header_columns(text: str) -> dict[int, dict[int, tuple[int, int]]]:
    """Get fixed-width year cell spans from each page's repeated table header."""
    headers: dict[int, dict[int, tuple[int, int]]] = {}
    page = 0
    for line in text.splitlines():
        if "\f" in line:
            page += line.count("\f")
        matches = list(re.finditer(r"\b(?:2002|2010|2021|2022|2023|2024)\b", line))
        years = [int(m.group()) for m in matches]
        if all(y in years for y in (2002, 2010, 2021)):
            starts = [m.start() for m in matches]
            spans = {}
            for i, m in enumerate(matches):
                if int(m.group()) not in YEARS:
                    continue
                left = 0 if i == 0 else (starts[i - 1] + m.start()) // 2
                right = len(line) if i + 1 == len(matches) else (m.end() + starts[i + 1]) // 2
                spans[int(m.group())] = (left, right)
            headers[page] = spans
    return headers


def poppler_historical_rows(text: str) -> list[tuple[str, str, str]]:
    """Extract 2002/2010/2021 cells by header-aligned columns, retaining unknowns."""
    headers = _header_columns(text)
    if not headers:
        raise ValueError("Poppler text has no Table 4.9 historical year headers")
    rows = []
    page = 0
    for line in text.splitlines():
        if "\f" in line:
            page += line.count("\f")
        spans = headers.get(page)
        if not spans:
            continue
        # The Latin publication label is the rightmost text on each data line;
        # it also captures continuation rows whose Russian qualifier wraps.
        if not re.search(r"[A-Za-zА-Яа-яЁё]", line[max(x[1] for x in spans.values()):]):
            continue
        cells = tuple(line[spans[y][0]:spans[y][1]].strip() for y in YEARS)
        if all(CELL.fullmatch(cell) for cell in cells):
            rows.append(cells)
    return rows


def _cell_values(raw: str) -> tuple[int | None, int | None, str]:
    token = raw.strip()
    if not token:
        return None, None, "blank"
    if token in ("…", "...", "—", "–", "-"):
        kind = "ellipsis" if token in ("…", "...") else "dash"
        return None, None, kind
    if not NUMBER.fullmatch(token):
        raise ValueError(f"unexpected historical population cell: {raw!r}")
    thousand = int(token.replace(" ", ""))
    return thousand, thousand * 1000, "numeric_published_thousands"


def observations(rows: pd.DataFrame, accepted: pd.DataFrame) -> pd.DataFrame:
    if not rows.row_id.is_unique:
        raise ValueError("duplicate source publication rows")
    required = {"source_publication_row_id", "target_2021_source_record_id", "target_population_scope"}
    if not required.issubset(accepted.columns):
        raise ValueError("accepted annual observations lack reusable 2021 publication-row bindings")
    # Every accepted annual year repeats the same explicit publication-row -> 2021 link.
    pairs = accepted[list(required)].drop_duplicates()
    if pairs.source_publication_row_id.duplicated().any():
        raise ValueError("ambiguous accepted publication-row binding")
    pairs = pairs.set_index("source_publication_row_id")
    output = []
    for row in rows.to_dict("records"):
        row_id = row["row_id"]
        if row_id not in pairs.index:
            raise ValueError(f"no accepted 2021 publication-row binding for {row_id}")
        binding = pairs.loc[row_id]
        for year in YEARS:
            raw = str(row[f"{year}_raw"] or "")
            value, scaled, kind = _cell_values(raw)
            date, date_basis = DATE_INFO[year]
            output.append({
                "source_record_id": f"{row_id}:historical_comparison:{year}",
                "source_publication_row_id": row_id,
                "record_type": "official_historical_comparison",
                "observation_year": year,
                "reference_date": date,
                "reference_date_basis": date_basis,
                "population_raw": raw,
                "population_reported_thousand": value,
                "population_reported_scaled_persons": scaled,
                "population_unit_multiplier": 1000,
                "population_value_quality": "official_census_comparison_rounded_to_thousands" if value is not None else f"official_census_comparison_unknown_{kind}",
                "population_missing_kind": "" if value is not None else kind,
                "settlement_name_raw": row["raw_russian_label"],
                "settlement_name": row["normalized_city_label"],
                "region_qualifier_raw": row["explicit_region_qualifier_raw"],
                "source_pdf_page": int(row["data_line_page_1based"]),
                "source_line": int(row["data_line_1based"]),
                "source_sha256": PDF_SHA,
                "source_path": PDF_REL.as_posix(),
                "source_table": "4.9",
                "source_publication": "Российский статистический ежегодник 2024",
                "source_footnote_markers": row["footnote_markers"],
                "source_raw_line": row["raw_table_line"],
                "target_2021_source_record_id": binding["target_2021_source_record_id"],
                "binding_quality": "accepted_2021_publication_row_link_reused_as_named_series_association",
                "identity_claim": "named_statistical_series_association_only_not_historical_physical_identity",
                "historical_source_scope": "year_specific_official_city_comparison; historical_boundary_and_scope_unknown",
                "canonical_census_record": False,
                "is_national_population_denominator": False,
                "coordinate_status": "not_admitted_by_this_builder",
            })
    return pd.DataFrame(output)


def _json_cell(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if isinstance(value, (int, float)) and float(value).is_integer():
        return int(value)
    return str(value).strip()


def inventory_sheets(raw_root: Path, sample_rows: int = 25) -> list[dict[str, Any]]:
    """Inventory only already-downloaded .xls schemas using top-of-sheet samples."""
    import xlrd

    candidates = []
    for folder in (raw_root / "2002", raw_root / "2010"):
        if folder.exists():
            candidates.extend(p for p in folder.glob("*.xls") if not p.name.startswith("._"))
    official_2002 = raw_root / "2002_official_tom1" / "1_TOM_01_04.xls"
    if official_2002.exists() and official_2002 not in candidates:
        candidates.append(official_2002)
    # Stable order and path uniqueness avoid Mac resource-fork sidecars.
    candidates = sorted(set(candidates), key=lambda p: p.as_posix())
    results = []
    for path in candidates:
        base = {"path": path.relative_to(raw_root.parents[1]).as_posix(), "sha256": sha(path), "byte_size": path.stat().st_size}
        try:
            book = xlrd.open_workbook(str(path), on_demand=True)
        except Exception as exc:  # inventory failures stay explicit
            results.append({**base, "workbook_status": "unreadable_xls", "error": f"{type(exc).__name__}: {exc}"})
            continue
        try:
            for sheet in book.sheets():
                sample = []
                for r in range(min(sample_rows, sheet.nrows)):
                    values = [_json_cell(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
                    while values and values[-1] is None:
                        values.pop()
                    if any(v is not None for v in values):
                        sample.append({"row_1based": r + 1, "cells": values})
                flattened = [str(v) for row in sample for v in row["cells"] if v is not None]
                year_labels = sorted({int(m.group()) for value in flattened for m in re.finditer(r"(?<!\d)(?:19\d{2}|20\d{2})(?!\d)", value) if 1900 <= int(m.group()) <= 2025})
                # Keep the literal first-25-row evidence, but only treat years
                # embedded in an explicit count/population header as column candidates.
                population_header_terms = ("числен", "населен", "population", "чел", "persons")
                population_header_rows = []
                population_year_headers = []
                for row in sample:
                    cells = [str(v) for v in row["cells"] if v is not None]
                    context = " ".join(cells).casefold()
                    if any(term in context for term in population_header_terms):
                        population_header_rows.append(row["row_1based"])
                        for value in cells:
                            for m in re.finditer(r"(?<!\d)(?:19\d{2}|20\d{2})(?!\d)", value):
                                if any(term in value.casefold() for term in population_header_terms):
                                    population_year_headers.append(int(m.group()))
                # Many tables put a single census year in a merged title cell
                # on row 1, then name the population column on row 2.
                top_header_text = " ".join(
                    str(v) for row in sample if row["row_1based"] <= 3 for v in row["cells"] if v is not None
                ).casefold()
                if any(term in top_header_text for term in population_header_terms):
                    for row in sample:
                        if row["row_1based"] > 3:
                            continue
                        for value in row["cells"]:
                            if value is None:
                                continue
                            value = str(value)
                            if re.fullmatch(r"(?:19|20)\d{2}", value.strip()):
                                population_year_headers.append(int(value.strip()))
                population_year_headers = sorted(set(population_year_headers))
                header_text = " ".join(flattened).casefold()
                population_markers = [term for term in ("населен", "числен", "population", "population size", "человек") if term in header_text]
                settlement_markers = [term for term in ("город", "населён", "населен", "посел", "settlement") if term in header_text]
                ethnic_markers = [term for term in ("национальн", "этничес", "доля", "per 100 000", "ethnic", "national composition") if term in header_text]
                source_folder_year = int(path.parent.name) if path.parent.name in ("2002", "2010") else None
                historical_comparator_years = [year for year in population_year_headers if source_folder_year and year < source_folder_year]
                eligible = bool(historical_comparator_years and population_markers)
                results.append({
                    **base,
                    "workbook_status": "readable_xls",
                    "sheet": sheet.name,
                    "sheet_index_0based": sheet.number,
                    "sheet_dimensions": {"rows": sheet.nrows, "columns": sheet.ncols},
                    "sample_rows_limit": sample_rows,
                    "sample_rows_nonempty": len(sample),
                    "possible_year_labels_in_first_sample": year_labels,
                    "population_count_year_labels_in_sample_headers": population_year_headers,
                    "possible_historical_comparator_years_in_sample_headers": historical_comparator_years,
                    "population_context_sample_row_numbers": population_header_rows,
                    "population_context_markers_in_sample": population_markers,
                    "settlement_context_markers_in_sample": settlement_markers,
                    "ethnic_or_share_context_markers_in_sample": ethnic_markers,
                    "candidate_gate": "possible_historical_population_comparison_column_needs_schema_review" if eligible else ("exclude_ethnic_or_share_context" if ethnic_markers else "no_additional_historical_population_year_in_sample_headers"),
                    "sample_first_rows": sample,
                })
        finally:
            book.release_resources()
    return results


def build_inventory(raw_root: Path, output_root: Path) -> dict:
    if output_root.exists():
        raise FileExistsError(output_root)
    entries = inventory_sheets(raw_root)
    output_root.mkdir(parents=True)
    json_path = output_root / "downloaded_raw_population_year_column_inventory.json"
    json_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
    flat = [{k: v for k, v in entry.items() if k != "sample_first_rows"} | {"sample_first_rows_json": json.dumps(entry.get("sample_first_rows", []), ensure_ascii=False)} for entry in entries]
    csv_path = output_root / "downloaded_raw_population_year_column_inventory.csv"
    pd.DataFrame(flat).to_csv(csv_path, index=False)
    possible = [e for e in entries if e.get("candidate_gate") == "possible_historical_population_comparison_column_needs_schema_review"]
    report = {
        "status": "bounded_readonly_inventory_of_already_downloaded_xls_samples",
        "inventory_rows": len(entries),
        "workbooks": len({e["path"] for e in entries}),
        "possible_population_year_column_sheets": len(possible),
        "candidate_year_labels": sorted({year for e in possible for year in e["possible_historical_comparator_years_in_sample_headers"]}),
        "requested_year_header_screen": [1979, 1989, *range(1991, 2026)],
        "requested_years_seen_as_additional_historical_comparator_headers": sorted(
            {year for e in possible for year in e.get("possible_historical_comparator_years_in_sample_headers", [])}
            & {1979, 1989, *range(1991, 2026)}
        ),
        "requested_years_not_seen_as_additional_historical_comparator_headers": sorted(
            {1979, 1989, *range(1991, 2026)}
            - {year for e in possible for year in e.get("possible_historical_comparator_years_in_sample_headers", [])}
        ),
        "sample_limit_per_sheet": 25,
        "source_mutations": 0,
        "new_downloads": 0,
        "mass_extraction": False,
        "identity_or_coordinate_decisions": 0,
        "outputs": {
            json_path.name: {"sha256": sha(json_path), "rows": len(entries)},
            csv_path.name: {"sha256": sha(csv_path), "rows": len(entries)},
        },
        "review_gate": "year labels are first-25-row header candidates only; no population assertion is verified without full schema review and an applicable parser",
    }
    (output_root / "inventory_receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def build(data_root: Path, accepted_path: Path, output_root: Path) -> dict:
    repo = Path(__file__).resolve().parents[2]
    if output_root.resolve().is_relative_to(repo):
        raise ValueError("large output must be outside Git")
    if output_root.exists():
        raise FileExistsError(output_root)
    row_path = data_root / SOURCE_REL / "table49_source_rows.csv"
    pdf = data_root / PDF_REL
    if sha(pdf) != PDF_SHA or sha(row_path) != ROWS_SHA:
        raise ValueError("published source bytes differ from pinned inputs")
    rows = pd.read_csv(row_path, dtype=str).fillna("")
    accepted = pd.read_parquet(accepted_path)
    if len(rows) != 172:
        raise ValueError("unexpected source publication row count")
    for year in YEARS:
        if f"{year}_raw" not in rows:
            raise ValueError(f"source rows lack the {year} published column")
    poppler = subprocess.run(["pdftotext", "-f", "91", "-l", "93", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    if "по переписи населения на 9 октября" not in poppler or "по переписи населения на 14 октября" not in poppler or "по переписи населения на 1 октября" not in poppler:
        raise ValueError("historical census reference-date footnotes missing from Poppler text")
    independent = poppler_historical_rows(poppler)
    expected = [tuple(str(row[f"{year}_raw"] or "").strip() for year in YEARS) for row in rows.to_dict("records")]
    if len(independent) != len(expected) or independent != expected:
        raise ValueError("historical columns do not agree with independent Poppler extraction")
    result = observations(rows, accepted)
    output_root.mkdir(parents=True)
    path = output_root / "official_historical_comparisons.parquet"
    result.to_parquet(path, index=False)
    (output_root / "independent_poppler_table49_pages_91_93.txt").write_text(poppler)
    manifest = {
        "status": "official_historical_comparison_observations_extracted_supplement_only",
        "source_publication_rows": len(rows),
        "historical_observations": len(result),
        "years": list(YEARS),
        "all_cells_agree_with_independent_Poppler_extraction": True,
        "unknown_cells": int(result.population_reported_thousand.isna().sum()),
        "reference_dates": {str(y): {"date": DATE_INFO[y][0], "basis": DATE_INFO[y][1]} for y in YEARS},
        "1989": {"status": "not_in_scope_no_column_in_pinned_Table_4_9_source_rows_or_PDF_table", "observations": 0},
        "accepted_2021_bindings_reused": int(result.source_publication_row_id.nunique()),
        "binding_semantics": "named statistical series association only for historical columns; not automatic historical physical identity",
        "national_denominator": False,
        "canonical_census_records_created": 0,
        "coordinate_admissions": 0,
        "inputs": {"pdf": {"path": PDF_REL.as_posix(), "sha256": PDF_SHA}, "source_rows": {"path": (SOURCE_REL / row_path.name).as_posix(), "sha256": ROWS_SHA}, "accepted_annual_bindings": {"path": str(accepted_path), "sha256": sha(accepted_path)}},
        "outputs": {path.name: {"sha256": sha(path), "rows": len(result)}},
        "builder_sha256": sha(Path(__file__)),
        "limitations": ["Values are rounded published comparison figures, not canonical exact census counts.", "No national denominator or national coverage claim.", "Historical boundary comparability and physical identity remain unknown.", "No population values were inferred from blanks, ellipses, or dashes.", "1989 is absent from this pinned source table and was not sourced elsewhere."],
    }
    (output_root / "receipt.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--accepted", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--inventory-raw-root", type=Path, help="Inventory already downloaded data/raw/2002 and data/raw/2010 .xls samples")
    args = parser.parse_args()
    if args.inventory_raw_root:
        report = build_inventory(args.inventory_raw_root, args.output_root)
    else:
        if args.data_root is None or args.accepted is None:
            parser.error("--data-root and --accepted are required unless --inventory-raw-root is provided")
        report = build(args.data_root, args.accepted, args.output_root)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
