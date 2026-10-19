#!/usr/bin/env python3
"""Build deterministic, audited delivery archives without transient files."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
WORKSPACE = REPO.parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def result_files() -> list[tuple[Path, str]]:
    selected: dict[str, Path] = {}

    def add(path: Path, arc: str | None = None) -> None:
        if path.is_file() and ".tmp" not in path.name and not path.name.startswith("."):
            selected[arc or f"research/sgrt_recovered_20261019/{path.relative_to(ROOT)}"] = path

    # Code, logs, registries, documentation and compact result tables.
    for path in ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or "maps" in path.relative_to(ROOT).parts:
            continue
        if path.name in {"SGRT_RESEARCH_REPORT.pdf", "report_body.tmp.pdf"}:
            continue
        if path.suffix.lower() in {".py", ".md", ".json", ".yaml", ".yml", ".txt"} or path.name == "requirements.txt":
            add(path)
        elif path.suffix.lower() in {".csv", ".gz", ".parquet"} and path.stat().st_size <= 5_000_000:
            add(path)

    # Core machine-readable outputs, including tables larger than the compact threshold.
    keep = [
        "data/panel.parquet",
        "data/municipality_bridge.parquet",
        "model/nearest_membership.parquet",
        "model/dynamic2021_membership.parquet",
        "agriculture/zone_crop_context.parquet",
        "agriculture/settlement_municipality_zone.parquet",
        "rfsd/primary2010/financial_observations.parquet",
        "rfsd/primary2010/sector_sensitivity.parquet",
        "rfsd/primary2010/center_economic_witness.parquet",
        "rfsd/primary2010/functional/sector_profiles.parquet",
        "rfsd/primary2010/functional/functional_types.csv",
        "rfsd/threshold_sensitivity/threshold_classifications.csv.gz",
        "rfsd/reference2002_complete/localfirst_financial.parquet",
        "rfsd/reference2002_complete/localfirst_sectors.parquet",
        "rfsd/reference2002_complete/zone_financial.parquet",
        "rfsd/reference2002_complete/zone_sectors.parquet",
        "statistics/independent_point_covariates.parquet",
        "validation/paired_noncenters.parquet",
        "supervision/final_typology/sgrt_dynamic_functional_typology.parquet",
        "published/sgrt_dynamic_functional_typology.csv.gz",
    ]
    for rel in keep:
        add(ROOT / rel)

    # Exact frozen inputs needed for the local core replay.
    inputs = [
        (REPO / "publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz", "inputs/publication/stage71/ordinary_full3_with_primary_population_sources.csv.gz"),
        (REPO / "publication/stage71/accepted_common_federal_territory_axis.csv", "inputs/publication/stage71/accepted_common_federal_territory_axis.csv"),
        (REPO / "research_rebuild/evidence/tochno_enrichment_application_20261013/native_np_municipality_bridge.csv.gz", "inputs/research_rebuild/native_np_municipality_bridge.csv.gz"),
        (REPO / "research_rebuild/evidence/historical_sources_integration_20261014/population_1989_selected_long.parquet", "inputs/research_rebuild/population_1989_selected_long.parquet"),
        (WORKSPACE / "recovery_inputs/columnar/agriculture.parquet", "inputs/recovery_inputs/columnar/agriculture.parquet"),
        (WORKSPACE / "recovery_inputs/columnar/manifest.json", "inputs/recovery_inputs/columnar/manifest.json"),
        (WORKSPACE / "recovery_inputs/enrichment/rfsd_2016_selected.parquet", "inputs/recovery_inputs/enrichment/rfsd_2016_selected.parquet"),
        (WORKSPACE / "recovery_inputs/enrichment/rfsd_2021_selected.parquet", "inputs/recovery_inputs/enrichment/rfsd_2021_selected.parquet"),
        (WORKSPACE / "recovery_inputs/enrichment/rfsd_2016_schema.json", "inputs/recovery_inputs/enrichment/rfsd_2016_schema.json"),
        (WORKSPACE / "recovery_inputs/enrichment/rfsd_2021_schema.json", "inputs/recovery_inputs/enrichment/rfsd_2021_schema.json"),
        (WORKSPACE / "recovery_inputs/enrichment/source_manifest.json", "inputs/recovery_inputs/enrichment/source_manifest.json"),
        (WORKSPACE / "recovery_inputs/enrichment/world.geojson", "inputs/recovery_inputs/enrichment/world.geojson"),
    ]
    for path, arc in inputs:
        add(path, arc)
    return sorted(((p, arc) for arc, p in selected.items()), key=lambda x: x[1])


def map_files() -> list[tuple[Path, str]]:
    maps = ROOT / "maps"
    files: list[tuple[Path, str]] = []
    for path in sorted(maps.iterdir()):
        if path.name == "SGRT_MAP_ATLAS.pdf" or ".tmp" in path.name or path.name.startswith("."):
            continue
        if path.suffix.lower() in {".png", ".svg", ".pdf", ".json", ".py", ".md"}:
            files.append((path, f"maps/{path.name}"))
    return files


def make_zip(path: Path, files: list[tuple[Path, str]], kind: str) -> dict:
    manifest = {
        "archive_kind": kind,
        "created_utc": "2026-10-19T10:00:00Z",
        "files": [{"path": arc, "bytes": p.stat().st_size, "sha256": sha256(p)} for p, arc in files],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for src, arc in files:
            z.write(src, arc)
        z.writestr("PACKAGE_MANIFEST.json", manifest_bytes)
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f"CRC failure: {bad}")
        stored = json.loads(z.read("PACKAGE_MANIFEST.json"))
        if len(stored["files"]) != len(files):
            raise RuntimeError("manifest member count mismatch")
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path), "members": len(files) + 1}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report = ROOT / "report/SGRT_RESEARCH_REPORT.pdf"
    atlas = ROOT / "maps/SGRT_MAP_ATLAS.pdf"
    shutil.copy2(report, args.out / report.name)
    shutil.copy2(atlas, args.out / atlas.name)
    records = [
        {"path": report.name, "bytes": report.stat().st_size, "sha256": sha256(report), "pages": 28},
        {"path": atlas.name, "bytes": atlas.stat().st_size, "sha256": sha256(atlas), "pages": 12},
        make_zip(args.out / "SGRT_RESULTS.zip", result_files(), "results_code_and_frozen_inputs"),
        make_zip(args.out / "SGRT_MAPS.zip", map_files(), "map_sources_and_all_formats"),
    ]
    checks = {"created_utc": "2026-10-19T10:00:00Z", "artifacts": records, "status": "PASS"}
    (args.out / "CHECKSUMS.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
