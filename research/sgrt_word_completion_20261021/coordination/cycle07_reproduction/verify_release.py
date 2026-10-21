"""Read-only byte verification of the final research bundle; no scientific rerun."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve() if args.root else next(
        p for p in Path(__file__).resolve().parents
        if (p / "transport").is_dir() and (p / "model").is_dir()
    )
    manifest = json.loads(args.manifest.read_text())
    errors, seen, cache = [], set(), {}
    for item in manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append({"path": str(relative), "error": "invalid relative path"})
            continue
        if str(relative) in seen:
            errors.append({"path": str(relative), "error": "duplicate manifest entry"})
            continue
        seen.add(str(relative))
        path = root / relative
        if not path.is_file():
            errors.append({"path": str(relative), "error": "missing file"})
            continue
        if path.stat().st_size != item["bytes"]:
            errors.append({"path": str(relative), "error": "size differs"})
            continue
        resolved = path.resolve()
        if resolved not in cache:
            cache[resolved] = digest(path)
        if cache[resolved] != item["sha256"]:
            errors.append({"path": str(relative), "error": "SHA256 differs"})
    result = {
        "status": "PASS" if not errors else "FAIL",
        "manifest_sha256": digest(args.manifest),
        "files_checked": len(seen),
        "distinct_file_targets_hashed": len(cache),
        "errors": errors,
        "scope": "Saved bytes only; not a new scientific validation or model rerun.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
