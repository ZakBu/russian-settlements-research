#!/usr/bin/env python3
"""Verify downloaded GitHub release assets against their published manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(manifest_path: Path, asset_dir: Path, selected_names: list[str] | None = None) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("assets")
    if not isinstance(entries, list) or not entries:
        raise ValueError("asset manifest must contain a nonempty assets list")
    by_name = {item.get("name"): item for item in entries if isinstance(item, dict)}
    if selected_names:
        unknown = sorted(set(selected_names) - set(by_name))
        if unknown:
            raise ValueError(f"requested assets are not listed in the manifest: {unknown}")
        entries = [by_name[name] for name in selected_names]
    for item in entries:
        name, expected_hash, expected_bytes = item.get("name"), item.get("sha256"), item.get("bytes")
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError(f"unsafe or missing asset filename: {name!r}")
        path = asset_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"release asset is missing: {path}")
        actual_bytes, actual_hash = path.stat().st_size, sha256(path)
        if actual_bytes != expected_bytes or actual_hash != expected_hash:
            raise ValueError(
                f"release asset verification failed for {name}: "
                f"expected {expected_bytes} bytes sha256={expected_hash}; "
                f"got {actual_bytes} bytes sha256={actual_hash}"
            )
        print(f"verified {name}: {actual_bytes} bytes sha256={actual_hash}")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--asset", action="append", dest="assets",
                        help="verify only this manifest-listed asset; may be repeated")
    args = parser.parse_args()
    count = verify(args.manifest, args.asset_dir, args.assets)
    print(f"verified {count} release assets")


if __name__ == "__main__":
    main()
