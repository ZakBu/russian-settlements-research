"""Correct dependency typing in the frozen national reviewed-admission R1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
R1 = ROOT / "research_rebuild/evidence/releases/national_reviewed_admissions_r1_20260930"
R6 = ROOT / "research_rebuild/evidence/inputs/karelia_r6_reviewed_claims_r1_20260930"
R1_MANIFEST_SHA = "4875e3b060fbc31e7b98af2bf938b1cd354c6008121d801a5eff53b30ab8e9a2"
R1_COORDINATES_SHA = "a0140c05fcfebc72748691fbd09c7f111b7b37f807b4e87bdc9daaf44a2cdbf9"
R6_BINDINGS_SHA = "c1998dc16f488f8a815f139b2c111b0787fbaa5087016ac6cac980ad6bfe1a16"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"immutable release already exists: {output}")
    manifest_path = R1 / "release_manifest.json"
    coord_path = R1 / "coordinate_admissions.csv"
    bindings_path = R6 / "published_record_bindings.csv"
    for p, expected in ((manifest_path, R1_MANIFEST_SHA), (coord_path, R1_COORDINATES_SHA),
                        (bindings_path, R6_BINDINGS_SHA)):
        if not p.is_file() or sha(p) != expected:
            raise ValueError(f"frozen correction input mismatch: {p}")
    parent = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hashes = {name: entry["sha256"] for name, entry in parent["outputs"].items()}
    for name, expected in source_hashes.items():
        p = R1 / name
        if not p.is_file() or sha(p) != expected:
            raise ValueError(f"R1 output changed before correction: {name}")

    points = pd.read_csv(coord_path)
    bindings = pd.read_csv(bindings_path)
    binding_ids = set(bindings.binding_decision_id.astype(str))
    identity_path = R1 / "identity_edges_accepted.csv"
    identity = pd.read_csv(identity_path)
    identity_ids = set(identity.decision_id.astype(str))

    def parse_ids(raw):
        if pd.isna(raw) or str(raw).strip() == "":
            return []
        value = json.loads(str(raw))
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"invalid dependency list: {raw}")
        return value

    pub_rows = 0
    for idx, row in points.iterrows():
        deps = parse_ids(row.depends_on_identity_decision_ids)
        pub = [x for x in deps if x in binding_ids or x.startswith("PUBLISHED-BINDING-")]
        identity_deps = [x for x in deps if x not in pub]
        # Fail closed on unknown IDs or incorrectly typed IDs instead of quietly
        # turning malformed references into nullable provenance.
        if any(x not in identity_ids for x in identity_deps):
            raise ValueError(f"unknown identity dependency for {row.decision_id}: {identity_deps}")
        if any(x not in binding_ids for x in pub):
            raise ValueError(f"unknown publication-binding dependency for {row.decision_id}: {pub}")
        if pub and int(row.target_year) != 2010:
            raise ValueError(f"same-census publication binding applied to non-2010 coordinate: {row.decision_id}")
        if len(pub) > 1:
            raise ValueError(f"coordinate claim has multiple publication-binding dependencies: {row.decision_id}")
        points.at[idx, "depends_on_identity_decision_ids"] = json.dumps(identity_deps, separators=(",", ":"))
        points.at[idx, "depends_on_publication_binding_ids"] = json.dumps(pub, separators=(",", ":"))
        points.at[idx, "published_record_binding_id"] = pub[0] if pub else row.published_record_binding_id
        pub_rows += len(pub)
    if pub_rows != 10:
        raise ValueError(f"expected ten coordinate publication-binding dependencies, got {pub_rows}")

    # Validate both dependency types as foreign keys after normalization.
    for row in points.itertuples(index=False):
        ids = parse_ids(row.depends_on_identity_decision_ids)
        pubs = parse_ids(row.depends_on_publication_binding_ids)
        if any(x not in identity_ids for x in ids):
            raise ValueError(f"identity dependency FK violation: {row.decision_id}")
        if any(x not in binding_ids for x in pubs):
            raise ValueError(f"publication dependency FK violation: {row.decision_id}")
        scalar = None if pd.isna(row.published_record_binding_id) else str(row.published_record_binding_id)
        if pubs != ([scalar] if scalar else []):
            raise ValueError(f"publication-binding scalar/list mismatch: {row.decision_id}")

    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    for name in source_hashes:
        if name == "coordinate_admissions.csv":
            continue
        shutil.copyfile(R1 / name, staging / name)
    points.to_csv(staging / "coordinate_admissions.csv", index=False)
    manifest = {
        **parent,
        "release_id": "national_reviewed_admissions_r2_20260930",
        "parent_release_id": parent["release_id"],
        "parent_release_manifest_sha256": R1_MANIFEST_SHA,
        "correction": {
            "kind": "dependency_type_and_foreign_key_fix",
            "reason": "Ten 2010 coordinate claims carried PUBLISHED-BINDING IDs in the identity-dependency list.",
            "change": "Publication bindings are now isolated in depends_on_publication_binding_ids and published_record_binding_id; depends_on_identity_decision_ids contains same_place decision IDs only.",
            "coordinate_decisions_changed": False,
            "identity_decisions_changed": False,
            "claims_with_publication_binding_dependency": pub_rows,
            "foreign_key_checks": {"identity_dependency_ids": "identity_edges_accepted.decision_id", "publication_binding_ids": "publication_bindings.binding_decision_id"},
            "revocation_semantics": "Revoking a same_place edge invalidates only claims that list that identity decision ID; revoking a publication binding invalidates only claims that list that binding ID. The two dependency types are not interchangeable.",
        },
        "outputs": {},
    }
    for p in sorted(staging.iterdir()):
        manifest["outputs"][p.name] = {"sha256": sha(p), "bytes": p.stat().st_size}
    manifest["builder_sha256"] = sha(Path(__file__).resolve())
    (staging / "release_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    staging.rename(output)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
