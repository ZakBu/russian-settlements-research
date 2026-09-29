"""Fresh-source extraction and assembly of Karelia's 2010 800-locality slice.

This command always rereads the supplied primary DOCX and the original Tom 1
PDF. It does not consume generated observation CSV/Parquet caches. The source
extractors' complete ledgers and their independently published controls are
retained under the chosen output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_DOCX = HERE.parent / "evidence/ingestion/sources/karelia_2010_rural_settlements.docx"
DEFAULT_PDF = HERE.parents[1] / "data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf"
TABLE5_MODULE = HERE.parents[1] / "research_audit/extract_official_2010_reference.py"
LOCATOR_CONTRACT = HERE / "source_locator_contract_karelia_2010_r5.json"
EXTRACTION_VERSION = "karelia-2010-fresh-primary-r5"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_frame_sha256(frame: pd.DataFrame) -> str:
    """Hash ordered typed table content, excluding Parquet writer metadata."""
    rows = []
    for row in frame.itertuples(index=False, name=None):
        typed = []
        for value in row:
            if pd.isna(value):
                typed.append(None)
                continue
            if hasattr(value, "item"):
                value = value.item()
            typed.append({"type": type(value).__name__, "value": value})
        rows.append(typed)
    payload = {"columns": [{"name": name, "dtype": str(dtype)}
                           for name, dtype in zip(frame.columns, frame.dtypes)], "rows": rows}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build(docx: Path, pdf: Path, output: Path) -> dict:
    docx, pdf, output = docx.resolve(), pdf.resolve(), output.resolve()
    if not docx.is_file() or not pdf.is_file():
        raise FileNotFoundError("Both primary DOCX and original Table 5 PDF must exist")
    if not LOCATOR_CONTRACT.is_file():
        raise FileNotFoundError(f"Required source locator contract is missing: {LOCATOR_CONTRACT}")
    locator_contract = json.loads(LOCATOR_CONTRACT.read_text(encoding="utf-8"))
    try:
        docx_label = locator_contract["locators"]["rural_docx"]
        pdf_label = locator_contract["locators"]["urban_table5_pdf"]
        docx_expected = locator_contract["expected_inputs"]["rural_docx"]
        pdf_expected = locator_contract["expected_inputs"]["urban_table5_pdf"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Source locator contract must define rural_docx and urban_table5_pdf") from exc
    if not all(isinstance(label, str) and label.strip() and not Path(label).is_absolute()
               for label in (docx_label, pdf_label)):
        raise ValueError("Source locator contract labels must be nonempty logical relative locators")
    # Provenance gate must run before any parser can interpret a different PDF
    # as Table 5 under the contracted source ID.
    for label, path, expected in ((docx_label, docx, docx_expected),
                                  (pdf_label, pdf, pdf_expected)):
        actual_sha, actual_bytes = sha256(path), path.stat().st_size
        if actual_sha != expected.get("sha256") or actual_bytes != expected.get("bytes"):
            raise ValueError(
                f"Source provenance mismatch before extraction for {label}: "
                f"expected sha256={expected.get('sha256')} bytes={expected.get('bytes')}; "
                f"got sha256={actual_sha} bytes={actual_bytes}"
            )
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"Output root must be empty to prevent mixing runs: {output}")

    # Re-extract from both original sources into this run's output directory.
    from extract_karelia_rural_2010_docx import extract as extract_rural
    rural_dir = output / "rural_source_extraction"
    extract_rural(docx, rural_dir, source_label=docx_label)
    rural = pd.read_csv(rural_dir / "karelia_2010_rural_official_observations.csv")

    spec = importlib.util.spec_from_file_location("table5_fresh_extractor", TABLE5_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Table 5 source extractor: {TABLE5_MODULE}")
    table5 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(table5)
    table5_dir = output / "table5_source_extraction"
    ref = table5.extract(pdf=pdf, output=table5_dir)
    urban_ref = ref[
        ref.region_key.eq("карелия")
        & ref.reference_status.eq("extracted_reference")
        & ref.row_kind.eq("settlement")
        & ref.settlement_type.isin(["город", "пгт"])
    ].copy()
    if len(urban_ref) != 24:
        raise AssertionError(f"Expected 24 direct urban/pgt Table 5 rows; got {len(urban_ref)}")

    urban = pd.DataFrame({
        "source_record_id": urban_ref.reference_id,
        "census_year": 2010,
        "population_scope": "permanent_residents_at_2010_census",
        "region_raw": "Республика Карелия",
        "region_norm": "карелия",
        "settlement_name": urban_ref.settlement_name,
        "settlement_name_norm": urban_ref.name_key,
        "settlement_type": urban_ref.settlement_type,
        "settlement_type_norm": urban_ref.type_key,
        "district_context_raw": urban_ref.district_raw,
        "municipality_context_raw": None,
        "population": urban_ref.population.astype(int),
        "men": urban_ref.men.astype(int),
        "women": urban_ref.women.astype(int),
        "source_population_raw": urban_ref.label_raw,
        "source_path": pdf_label,
        "source_sha256": sha256(pdf),
        "source_locator": urban_ref.apply(
            lambda r: f"pdf_page[{int(r.pdf_page)}].text_line[{int(r.text_line_start)}:{int(r.text_line_end)}]", axis=1
        ),
        "source_table_index_zero_based": None,
        "source_table_row_index_zero_based": None,
        "source_role": "official_rosstat_volume_1_table_5_urban",
        "source_integrity_status": "fresh_raw_pdf_extraction",
        "source_population_reference": urban_ref.reference_id,
        "coordinate_source": None,
        "latitude": None,
        "longitude": None,
    })
    rural = rural.rename(columns={
        "settlement_name_raw": "settlement_name",
        "settlement_name_norm": "settlement_name_norm",
        "settlement_type_raw": "settlement_type",
        "settlement_type_norm": "settlement_type_norm",
    })
    rural["source_role"] = "official_regional_census_rural"
    rural["source_integrity_status"] = "fresh_raw_docx_extraction_TLS_verification_pending"
    rural["source_population_raw"] = rural.population_raw_cell
    rural["source_population_reference"] = rural.source_record_id
    rural["coordinate_source"] = None
    rural["latitude"] = None
    rural["longitude"] = None

    columns = list(urban.columns)
    canonical = pd.concat([urban, rural[columns]], ignore_index=True)
    canonical["population_identity_status"] = "source observation; do not infer place identity from name alone"
    canonical["selection_status"] = "fresh source extraction; primary-value candidate pending source review"
    canonical["extraction_version"] = EXTRACTION_VERSION
    if len(canonical) != 800:
        raise AssertionError(f"Expected 800 source observations; got {len(canonical)}")
    for role, count, population in (
        ("official_rosstat_volume_1_table_5_urban", 24, 502217),
        ("official_regional_census_rural", 776, 141331),
    ):
        part = canonical[canonical.source_role.eq(role)]
        if len(part) != count or int(part.population.sum()) != population:
            raise AssertionError(f"{role}: rows={len(part)}, population={part.population.sum()}")
    if int(canonical.population.sum()) != 643548:
        raise AssertionError("The source-derived components do not sum to 643,548")
    if not (canonical.population == canonical.men + canonical.women).all():
        raise AssertionError("Found a fresh source row where population != men + women")
    if canonical.source_record_id.duplicated().any():
        raise AssertionError("Source-native record IDs must be unique in the assembled snapshot")

    canonical.to_csv(output / "karelia_2010_fresh_primary_observations.csv", index=False)
    canonical.to_parquet(output / "karelia_2010_fresh_primary_observations.parquet", index=False)
    summary = {
        "status": "fresh_primary_source_extraction; reviewable candidate",
        "extraction_version": EXTRACTION_VERSION,
        "source_independent_of_generated_row_cache": True,
        "docx_source": {"path": docx_label, "sha256": sha256(docx), "bytes": docx.stat().st_size},
        "pdf_source": {"path": pdf_label, "sha256": sha256(pdf), "bytes": pdf.stat().st_size},
        "observation_rows": len(canonical),
        "urban_table5_rows": len(urban), "urban_population": int(urban.population.sum()),
        "rural_docx_rows": len(rural), "rural_population": int(rural.population.sum()),
        "combined_population": int(canonical.population.sum()),
        "zero_population_rural_rows": int((rural.population == 0).sum()),
        "rural_source_facts": json.loads((rural_dir / "karelia_2010_rural_docx_source_facts.json").read_text()),
        "table5_extraction_summary": {
            "parsed_records": len(ref), "regions": int(ref.region_raw.nunique()),
            "all_text_lines_retained_once": True,
            "urban_record_ids": urban.source_record_id.tolist(),
            "urban_source_population": int(urban.population.sum()),
        },
        "limitations": [
            "DOCX retrieval initially had a TLS certificate-chain verification failure; transport caveat remains in the receipt.",
            "PDF urban extraction uses the audited Table 5 line parser rerun against the original PDF; it is not a separately authored parser implementation.",
            "This is source/population selection evidence, not proof of inter-census place identity.",
        ],
    }
    (output / "karelia_2010_fresh_primary_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    code_paths = [HERE / "extract_karelia_rural_2010_docx.py", TABLE5_MODULE,
                  Path(__file__).resolve(), LOCATOR_CONTRACT]
    code = [{"path": p.relative_to(HERE.parents[1]).as_posix(), "sha256": sha256(p), "bytes": p.stat().st_size}
            for p in code_paths]
    generated = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in {"run_receipt.json", "run_receipt.json.sha256"}:
            generated.append({"path": path.relative_to(output).as_posix(),
                              "sha256": sha256(path), "bytes": path.stat().st_size})
    receipt = {
        "receipt_version": "fresh-source-run-v1",
        "status": "complete",
        "extraction_version": EXTRACTION_VERSION,
        "source_locator_contract": {
            "path": LOCATOR_CONTRACT.relative_to(HERE.parents[1]).as_posix(),
            "sha256": sha256(LOCATOR_CONTRACT),
            "contract_version": locator_contract["contract_version"],
        },
        "input_sources": [
            {"logical_locator": docx_label, "physical_path": docx.as_posix(), "sha256": sha256(docx), "bytes": docx.stat().st_size},
            {"logical_locator": pdf_label, "physical_path": pdf.as_posix(), "sha256": sha256(pdf), "bytes": pdf.stat().st_size},
        ],
        "extractor_code": code,
        "outputs": generated,
        "canonical_parquet_content_sha256": canonical_frame_sha256(canonical),
        "output_row_count": len(canonical),
        "output_population": int(canonical.population.sum()),
        "runtime": {"python": __import__("sys").version.split()[0], "pandas": pd.__version__},
        "reproducibility_note": "Compare canonical_parquet_content_sha256 for typed values/row order and outputs[].sha256 for exact file bytes.",
    }
    receipt_path = output / "run_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt_hash = sha256(receipt_path)
    receipt_path.with_suffix(".json.sha256").write_text(f"{receipt_hash}  {receipt_path.name}\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-docx", type=Path, required=True)
    parser.add_argument("--source-pdf", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source_docx, args.source_pdf, args.output_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
