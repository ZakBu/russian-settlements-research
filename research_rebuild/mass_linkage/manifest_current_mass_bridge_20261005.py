#!/usr/bin/env python3
"""Build a SHA-256 manifest for the October 5 mass-linkage run artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence"
OUT = EVIDENCE / "current_mass_bridge_manifest_20261005.json"
FOLDERS = [
    EVIDENCE / "exact_name_proximity_batch_20261005",
    EVIDENCE / "joint_residual_after_exact_name_proximity_20261005",
    EVIDENCE / "unique_name_region_coordinate_bridge_20261005",
    EVIDENCE / "joint_residual_after_unique_name_region_bridge_20261005",
    EVIDENCE / "current_available_year_path_20261005",
    EVIDENCE / "event_aware_path_union_20261005",
]
SCRIPTS = [
    ROOT / "research_rebuild/mass_linkage/apply_exact_name_proximity_batch_20261005.py",
    ROOT / "research_rebuild/mass_linkage/apply_unique_name_region_coordinate_bridge_20261005.py",
    ROOT / "research_rebuild/mass_linkage/report_joint_residual_after_exact_name_proximity_20261005.py",
    ROOT / "research_rebuild/mass_linkage/report_joint_residual_after_unique_name_region_bridge_20261005.py",
    ROOT / "research_rebuild/mass_linkage/measure_current_available_year_path_20261005.py",
    ROOT / "research_rebuild/mass_linkage/measure_event_aware_path_union_20261005.py",
    ROOT / "research_rebuild/mass_linkage/screen_extreme_population_ratios_20261005.py",
    ROOT / "research_rebuild/mass_linkage/manifest_current_mass_bridge_20261005.py",
]


def file_record(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size, "sha256": digest}


def main() -> None:
    outputs = []
    for folder in FOLDERS:
        outputs.extend(file_record(path) for path in sorted(folder.iterdir()) if path.is_file())
    scripts = [file_record(path) for path in SCRIPTS]
    manifest = {
        "status": "local_mass_linkage_and_current_coverage_checkpoint",
        "created_utc_date": "2026-10-05",
        "outputs": outputs,
        "reproduction_scripts": scripts,
        "note": "Input artifact hashes are recorded in each application or measurement receipt. Large selected, graph and point ledgers are external mounted files and are not included in this manifest.",
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"manifest_entries={len(outputs)} scripts={len(scripts)} path={OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
