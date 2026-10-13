"""Recover already parsed official annual observations without inventing precision.

This adds published January-1 estimates for 2022–2024, not exact census counts.
The 163 previously reviewed city-row bindings are reused; nine exceptional rows
remain unbound. Coordinates and population comparability are not admitted here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

SOURCE_REL = Path("research_rebuild/evidence/discovery/yearbook_table49_2010_2021_candidates_r2_20260930")
R5_REL = Path("research_rebuild/evidence/releases/national_reviewed_admissions_r5b_yearbook_20260930")
PDF_REL = Path("research_rebuild/evidence/discovery/official_sources_2010_2021_r2_yearbook/raw/rosstat_russian_statistical_yearbook_2024.pdf")
PDF_SHA = "bac43b438869d7b11ca595acd121726833d2bf2e54004351db825cade4c29da7"
ROWS_SHA = "43d97c7d655c7e48d23d742191a063b92e56892431c38604bad8e8951ed77688"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def poppler_annual_triplets(text: str) -> list[tuple[str, str, str]]:
    """Read the three final numeric columns using a second PDF text engine."""
    result = []
    for line in text.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) not in (6, 8) or not re.search(r"[А-Яа-яЁё]", parts[0]):
            continue
        if all(re.fullmatch(r"(?:\d[\d ]*|…)", x) for x in parts[1:-1]):
            result.append(tuple(parts[-4:-1]))
    return result


def observations(rows: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    if not rows.row_id.is_unique or not pairs.row_id.is_unique:
        raise ValueError("duplicate source rows or city bindings")
    bindings = pairs.set_index("row_id")
    output = []
    for row in rows.to_dict("records"):
        binding = bindings.loc[row["row_id"]] if row["row_id"] in bindings.index else None
        for year in (2022, 2023, 2024):
            raw = row[f"{year}_raw"]
            if not re.fullmatch(r"\d[\d ]*", raw):
                raise ValueError(f"unexpected annual value: {row['row_id']}:{year}:{raw}")
            value = int(raw.replace(" ", ""))
            output.append({
                "source_record_id": f"{row['row_id']}:annual:{year}",
                "source_publication_row_id": row["row_id"],
                "observation_year": year, "reference_date": f"{year}-01-01",
                "population_raw": raw, "population_reported_thousand": value,
                "population_reported_scaled_persons": value * 1000,
                "population_unit_multiplier": 1000,
                "population_value_quality": "official_annual_estimate_rounded_to_thousands",
                "rounding_convention": "unspecified_in_publication; no exact population or assumed error interval",
                "settlement_name_raw": row["raw_russian_label"],
                "settlement_name": row["normalized_city_label"],
                "region_qualifier_raw": row["explicit_region_qualifier_raw"],
                "source_pdf_page": int(row["data_line_page_1based"]),
                "source_line": int(row["data_line_1based"]),
                "source_sha256": PDF_SHA, "source_path": PDF_REL.as_posix(),
                "source_table": "4.9", "source_publication": "Российский статистический ежегодник 2024",
                "source_footnote_markers": row["footnote_markers"],
                "source_raw_line": row["raw_table_line"],
                "target_2021_source_record_id": binding["2021_source_record_id"] if binding is not None else None,
                "census_row_binding_basis": "reuse_prior_R5b_reviewed_publication_row_binding" if binding is not None else "exception_not_bound",
                "annual_identity_status": "candidate_repeated_named_city_in_same_official_series_pending_rule_review" if binding is not None else "unresolved_exception",
                "coordinate_status": "not_admitted_by_this_builder",
                "population_comparability": "year_specific_scope_no_boundary_harmonization",
                "is_national_population_denominator": False,
            })
    return pd.DataFrame(output)


def build(data_root: Path, selected_path: Path, output_root: Path) -> dict:
    repo = Path(__file__).resolve().parents[2]
    if output_root.resolve().is_relative_to(repo):
        raise ValueError("large output must be outside Git")
    if output_root.exists():
        raise FileExistsError(output_root)
    source = data_root / SOURCE_REL
    pdf = data_root / PDF_REL
    row_path = source / "table49_source_rows.csv"
    if sha(pdf) != PDF_SHA or sha(row_path) != ROWS_SHA:
        raise ValueError("published source bytes differ from pinned inputs")
    r5 = data_root / R5_REL
    manifest = json.loads((r5 / "release_manifest.json").read_text())
    pair_path = r5 / "accepted_and_deduplicated_yearbook_pairs.csv"
    # R5b stores its outputs under relative paths; pin using the release entry.
    entries = manifest.get("outputs", {})
    matches = [entry for name, entry in entries.items() if name.endswith(pair_path.name)]
    if len(matches) != 1 or sha(pair_path) != matches[0]["sha256"]:
        raise ValueError("reviewed city-row bindings fail release hash check")
    rows = pd.read_csv(row_path, dtype=str).fillna("")
    pairs = pd.read_csv(pair_path, dtype=str).fillna("")
    if len(rows) != 172 or len(pairs) != 163:
        raise ValueError("unexpected published row/binding counts")
    poppler = subprocess.run(["pdftotext", "-f", "91", "-l", "93", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    if "за остальные годы – оценка на 1 января соответствующего года" not in poppler:
        raise ValueError("annual reference-date footnote not independently recovered")
    expected = list(zip(rows["2022_raw"], rows["2023_raw"], rows["2024_raw"]))
    if poppler_annual_triplets(poppler) != expected:
        raise ValueError("annual columns do not agree with independent Poppler extraction")
    selected = pd.read_parquet(selected_path, columns=["source_record_id", "census_year", "population_scope"]).set_index("source_record_id")
    if not selected.index.is_unique:
        raise ValueError("duplicate selected observation IDs")
    for sid in pairs["2021_source_record_id"]:
        if sid not in selected.index or int(selected.loc[sid, "census_year"]) != 2021:
            raise ValueError("reviewed 2021 endpoint is not selected")
    result = observations(rows, pairs)
    result["target_population_scope"] = result.target_2021_source_record_id.map(selected.population_scope)
    output_root.mkdir(parents=True)
    path = output_root / "annual_observations.parquet"
    result.to_parquet(path, index=False)
    (output_root / "independent_poppler_pages_91_93.txt").write_text(poppler)
    receipt = {
        "status": "official_annual_population_observations_extracted_identity_candidates_only",
        "source_rows": len(rows), "annual_observations": len(result),
        "years": [2022, 2023, 2024], "bound_prior_reviewed_city_rows": len(pairs),
        "unresolved_city_rows": len(rows) - len(pairs),
        "all_516_annual_cells_agree_with_independent_Poppler_extraction": True,
        "reference_date": "January 1 per source footnote1", "population_unit": "thousand persons",
        "national_denominator": False, "new_coordinate_admissions": 0,
        "inputs": {"pdf": {"path": PDF_REL.as_posix(), "sha256": PDF_SHA}, "source_rows": {"path": (SOURCE_REL / row_path.name).as_posix(), "sha256": ROWS_SHA}, "reviewed_bindings": {"path": (R5_REL / pair_path.name).as_posix(), "sha256": sha(pair_path)}, "selected_observations": {"sha256": sha(selected_path)}},
        "outputs": {path.name: {"sha256": sha(path), "rows": len(result)}},
        "builder_sha256": sha(Path(__file__)),
        "limitations": ["Annual counts are rounded estimates, not exact census populations.", "Only listed >=100k cities; no national annual settlement denominator.", "Retain year-specific boundaries and census-to-estimate methodological differences.", "Identity continuation and spatial reuse await an independently checked rule."],
    }
    (output_root / "manifest.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    report = build(args.data_root, args.selected, args.output_root)
    print(json.dumps({k: report[k] for k in ("status", "annual_observations", "years", "bound_prior_reviewed_city_rows", "unresolved_city_rows")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
