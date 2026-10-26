"""Fail-closed, evidence-pinned coordinate holds; never substitutes coordinates.

A hold concerns a census record's spatial use, not its existence or population.
The original reference remains immutable, including uncredited population rows.
"""
from __future__ import annotations

import argparse
import hashlib
import gzip
import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DEFAULT_HOLDS = REPO / "references/provenance/coordinate_holds_20261026.json"
REQUIRED_FIELDS = {"name", "settlement_type_2021", "region", "district", "lat", "lon"}


def _file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing or unsafe coordinate evidence: {relative}")
    return path


def _validate_evidence(evidence: dict, root: Path) -> None:
    raw = _file(root, evidence["raw_path"]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != evidence["sha256"] or len(raw) != evidence["bytes"]:
        raise ValueError(f"Coordinate evidence hash/size mismatch: {evidence['raw_path']}")
    metadata = json.loads(_file(root, evidence["metadata_path"]).read_text())
    if (metadata.get("http_status") != 200 or evidence.get("http_status") != 200
            or metadata.get("sha256") != digest or metadata.get("bytes") != len(raw)
            or metadata.get("url") != evidence["url"]):
        raise ValueError("Coordinate evidence HTTP metadata mismatch")
    if evidence.get("kind") == "nominatim_raw_response":
        candidates = json.loads(raw)
        fields = evidence["object_fields"]
        selected = [item for item in candidates
                    if item.get("osm_type") == fields["osm_type"]
                    and item.get("osm_id") == fields["osm_id"]]
        if len(selected) != 1:
            raise ValueError("Coordinate evidence object is missing or duplicated")
        obj = selected[0]
        if any(obj.get(key) != value for key, value in fields.items()):
            raise ValueError("Coordinate evidence object fingerprint mismatch")
        if any(obj.get("address", {}).get(key) != value
               for key, value in evidence["address_fields"].items()):
            raise ValueError("Coordinate evidence address fingerprint mismatch")
    text_bytes = gzip.decompress(raw) if evidence.get("compression") == "gzip" else raw
    if evidence.get("uncompressed_sha256") and hashlib.sha256(text_bytes).hexdigest() != evidence["uncompressed_sha256"]:
        raise ValueError("Coordinate evidence uncompressed HTTP body hash mismatch")
    for literal in evidence.get("required_text", []):
        if literal not in text_bytes.decode(evidence.get("encoding", "utf-8")):
            raise ValueError(f"Coordinate evidence text is missing: {literal}")


def load_coordinate_holds(path, reference: pd.DataFrame, *, repo_root=REPO) -> set[str]:
    """Validate every record/evidence before returning any spatially held IDs.

    ``reference_fields`` are literal fingerprints, not name matching rules.
    Population credit and analysis-origin flags never relax these checks.
    """
    document = json.loads(Path(path).read_text())
    if document.get("schema") != "sgrt.coordinate_holds.v1":
        raise ValueError("Unsupported coordinate holds schema")
    holds = set()
    for record in document["records"]:
        source_id = record["source_record_id"]
        if not isinstance(source_id, str) or not source_id or source_id in holds:
            raise ValueError("Missing or duplicate coordinate hold ID")
        expected = record["reference_fields"]
        if not REQUIRED_FIELDS.issubset(expected):
            raise ValueError("Incomplete coordinate reference fingerprint")
        rows = reference.loc[reference["source_record_id"].eq(source_id)]
        if len(rows) != 1:
            raise ValueError(f"Coordinate hold reference ID missing/duplicated: {source_id}")
        actual = rows.iloc[0]
        for key, value in expected.items():
            if key not in reference or pd.isna(actual[key]) or actual[key] != value:
                raise ValueError(f"Coordinate hold reference mismatch: {source_id}:{key}")
        if not record.get("reason") or not record.get("evidence"):
            raise ValueError("Coordinate hold requires reason and evidence")
        if not any(e.get("kind") == "nominatim_raw_response" for e in record["evidence"]):
            raise ValueError("Coordinate hold requires explicit mapped-place evidence")
        for evidence in record["evidence"]:
            _validate_evidence(evidence, Path(repo_root))
        holds.add(source_id)
    return holds


def apply_coordinate_holds(reference: pd.DataFrame, holds: set[str]) -> pd.DataFrame:
    """Return all original rows/fields plus a spatial hold flag, without relocation."""
    result = reference.copy()
    result["coordinate_location_held"] = result["source_record_id"].isin(holds)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--holds", type=Path, default=DEFAULT_HOLDS)
    parser.add_argument("--repo-root", type=Path, default=REPO)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.resolve() == args.reference.resolve():
        raise ValueError("Output must be a new file; reference is immutable")
    reference = pd.read_parquet(args.reference)
    holds = load_coordinate_holds(args.holds, reference, repo_root=args.repo_root)
    result = apply_coordinate_holds(reference, holds)
    pd.testing.assert_frame_equal(reference, result[reference.columns])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(args.output, index=False)
    print(json.dumps({"held_ids": sorted(holds), "rows_preserved": len(result),
                      "manifest_sha256": hashlib.sha256(args.holds.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
