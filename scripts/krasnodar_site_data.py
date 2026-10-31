#!/usr/bin/env python3
"""Download and verify the release-pinned Krasnodar frontend payload.

No routing or scientific recalculation runs during a website build. Generated
files go only to web/public/data/krasnodar and must never be committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 25 * 1024 * 1024
REQUIRED = {
    "manifest.json", "asset_manifest.json", "calculation_manifest.json",
    "statistics.json", "summary.json", "isochrone_bands.geojson",
    "isochrones_base.geojson", "isochrones_slow.geojson",
    "core_isochrones_base.geojson", "core_isochrones_slow.geojson",
    "core.geojson", "candidate_60.geojson", "candidate_60_slow.geojson",
    "places.geojson", "context.geojson", "settlement_access.csv",
    "candidate_roster.csv",
}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def valid_name(name: str) -> bool:
    return (bool(name) and name not in {".", ".."} and "/" not in name
            and "\\" not in name and ":" not in name
            and Path(name).suffix.lower() in {".json", ".geojson", ".csv", ".png"})


def verify_payload(directory: Path, expected_commit: str | None = None) -> dict:
    actual = {p.name for p in directory.iterdir() if p.is_file()}
    if not REQUIRED <= actual:
        raise ValueError(f"Krasnodar payload lacks required files: {sorted(REQUIRED - actual)}")
    manifest = json.loads((directory / "asset_manifest.json").read_text())
    files = manifest["files"]
    if set(files) != actual - {"asset_manifest.json"}:
        raise ValueError("Asset manifest must cover every payload file exactly once")
    for name, entry in files.items():
        if not valid_name(name):
            raise ValueError(f"Unsafe asset name: {name!r}")
        path = directory / name
        if path.stat().st_size != entry["bytes"] or sha(path) != entry["sha256"]:
            raise ValueError(f"Krasnodar asset checksum/size differs: {name}")
        if path.suffix in {".json", ".geojson"}:
            value = json.loads(path.read_text())
            if path.suffix == ".geojson" and value.get("type") not in {"FeatureCollection", "Feature"}:
                raise ValueError(f"Invalid GeoJSON document: {name}")
    app = json.loads((directory / "manifest.json").read_text())
    if manifest.get("sourceCommit") != app.get("sourceCommit"):
        raise ValueError("Application and asset manifests have different source commits")
    if expected_commit and app.get("sourceCommit") != expected_commit:
        raise ValueError("Payload source commit differs from pinned release catalog")
    references = [s["geometryUrl"] for s in app["studies"]]
    references += [app["candidate"]["geometryUrl"], app["candidate"]["robustGeometryUrl"]]
    references += [v["url"] for v in app["isochrones"]["variants"]]
    for name in references:
        if not valid_name(name) or name not in files:
            raise ValueError(f"Unverified application data reference: {name!r}")
    return app


def extract_verified(archive: Path, directory: Path, expected_commit: str | None = None) -> dict:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        names = [m.filename for m in members]
        if len(members) > 200 or len(set(names)) != len(names):
            raise ValueError("Duplicate or excessive ZIP members")
        if sum(m.file_size for m in members) > MAX_BYTES:
            raise ValueError("Krasnodar payload exceeds 25 MiB uncompressed")
        total = 0
        for member in members:
            mode = member.external_attr >> 16
            if (not valid_name(member.filename) or member.is_dir()
                    or stat.S_ISLNK(mode) or member.flag_bits & 1):
                raise ValueError(f"Unsafe ZIP member: {member.filename!r}")
            with bundle.open(member) as source, (directory / member.filename).open("wb") as target:
                while block := source.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_BYTES:
                        raise ValueError("Expanded payload exceeds 25 MiB")
                    target.write(block)
    return verify_payload(directory, expected_commit)


def build(catalog_path: Path | str = ROOT / "data/krasnodar_maps_catalog_20261031.json",
          output: Path | str = ROOT / "web/public/data/krasnodar",
          cache: Path | str = ROOT / ".research-cache/krasnodar-maps",
          offline: bool = False) -> dict:
    catalog = json.loads(Path(catalog_path).read_text())
    entry = catalog.get("files", {}).get("app") or catalog.get("app")
    if entry is None:
        entry = {"url": catalog["appUrl"], "sha256": catalog["appSha256"]}
    if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
        raise ValueError("A pinned SHA-256 is required for the application ZIP")
    if urlparse(entry["url"]).scheme != "https":
        raise ValueError("Release assets must use HTTPS")
    output, cache = Path(output), Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (entry["sha256"] + ".zip")
    if not archive.is_file() or sha(archive) != entry["sha256"]:
        if offline:
            raise ValueError("Offline Krasnodar ZIP is missing or differs from its pinned SHA-256")
        temporary = archive.with_suffix(".download")
        try:
            request = Request(entry["url"], headers={"User-Agent": "russian-settlements-research/1.0"})
            with urlopen(request, timeout=120) as response, temporary.open("wb") as target:
                downloaded = 0
                while block := response.read(1024 * 1024):
                    downloaded += len(block)
                    if downloaded > MAX_BYTES:
                        raise ValueError("Application ZIP download exceeds 25 MiB")
                    target.write(block)
            if sha(temporary) != entry["sha256"]:
                raise ValueError("Krasnodar application ZIP SHA-256 differs")
            os.replace(temporary, archive)
        finally:
            temporary.unlink(missing_ok=True)
    if "bytes" in entry and archive.stat().st_size != entry["bytes"]:
        raise ValueError("Krasnodar application ZIP byte count differs")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".krasnodar-", dir=output.parent) as temporary_dir:
        staging = Path(temporary_dir)
        app = extract_verified(archive, staging, catalog.get("sourceCommit"))
        if output.exists():
            shutil.rmtree(output)
        os.replace(staging, output)
    result = {"sourceCommit": app["sourceCommit"], "files": len(list(output.iterdir())), "output": str(output)}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data/krasnodar_maps_catalog_20261031.json")
    parser.add_argument("--output", type=Path, default=ROOT / "web/public/data/krasnodar")
    parser.add_argument("--cache", type=Path, default=ROOT / ".research-cache/krasnodar-maps")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    build(args.catalog, args.output, args.cache, offline=args.offline)
