#!/usr/bin/env python3
"""Rebuild the source-corrected preliminary Karelia R6 pilot."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DOCX_REL = Path("evidence/ingestion/source/karelia_2010_rural_settlements.docx")
PDF_REL = Path("data/raw/2010_official_tom1/tom-1-chislennost-i-razmeshchenie-naseleniya.pdf")
RELEASE_NAME = "karelia-primary-source-corrected-final"


def run(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True,
                        help="root of the extracted private baseline release")
    parser.add_argument("--inputs-root", type=Path, required=True,
                        help="root of the extracted Karelia pilot input bundle")
    parser.add_argument("--output-root", type=Path, required=True,
                        help="new or empty writable directory for generated results")
    args = parser.parse_args()
    data_root = args.data_root.expanduser().resolve()
    inputs_root = args.inputs_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    docx = inputs_root / DOCX_REL
    pdf = data_root / PDF_REL
    if not docx.is_file() or not pdf.is_file():
        parser.error(f"missing primary source: expected {docx} and {pdf}")
    if output_root.exists() and any(output_root.iterdir()):
        parser.error(f"output root must be new or empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    parser_script = REPO / "research_rebuild/ingestion/build_karelia_2010_fresh_primary_r5.py"
    linkage_script = REPO / "research_rebuild/linkage/build_r6_source_corrected.py"
    run([sys.executable, str(parser_script), "--source-docx", str(docx),
         "--source-pdf", str(pdf), "--output-root", str(output_root / "ingestion")], cwd=Path("/"))
    common = [sys.executable, str(linkage_script), "--data-root", str(data_root),
              "--inputs-root", str(inputs_root), "--output-root", str(output_root),
              "--source-selection-version", "primary2010", "--scope", "karelia",
              "--release-name", RELEASE_NAME]
    run(common[:2] + ["--build"] + common[2:], cwd=Path("/"))
    run(common[:2] + ["--validate-only"] + common[2:], cwd=Path("/"))
    package_script = REPO / "scripts/package_portable_duckdb.py"
    run([sys.executable, str(package_script), "--release-dir",
         str(output_root / RELEASE_NAME), "--database-path",
         str(output_root / RELEASE_NAME / "linkage_review_portable.duckdb")], cwd=Path("/"))
    print(f"Verified pilot outputs: {output_root / RELEASE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
