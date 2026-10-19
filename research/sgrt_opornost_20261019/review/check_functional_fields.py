"""Independent sampled replay of scenario fields, without importing GIS code.

Angular distances use atan2(norm(cross), dot) of unit vectors, independently
of the author's haversine implementation. This validates numerical outputs only.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

R = 6371.0088


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def table(path):
    return pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path)


def vec(frame):
    a = np.deg2rad(frame.lat.to_numpy(float))
    b = np.deg2rad(frame.lon.to_numpy(float))
    return np.c_[np.cos(a) * np.cos(b), np.cos(a) * np.sin(b), np.sin(a)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origins", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--fields", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sample", type=int, default=64)
    args = ap.parse_args()
    origins = table(args.origins)
    candidates = table(args.candidates)
    manifest = json.loads((args.fields / "manifest.json").read_text())
    assert sha(args.origins) == manifest["origins_sha256"]
    assert sha(args.candidates) == manifest["candidates_sha256"]
    # Deliberately cover candidate/local-option origins and zero-pop origins too.
    rng = np.random.default_rng(20261019)
    ix = set(rng.choice(len(origins), min(args.sample, len(origins)), replace=False).tolist())
    cmap = origins.entity_uid.astype(str).isin(candidates.entity_uid.astype(str))
    ix.update(origins.index[cmap][:8].tolist())
    if "population_2021" in origins:
        ix.update(origins.index[origins.population_2021.eq(0)][:8].tolist())
    sample = origins.loc[sorted(ix)].reset_index(drop=True)
    ids = sample.entity_uid.astype(str).tolist()
    all_checks = []
    comparisons = 0
    for item in manifest["outputs"]:
        path = args.fields / item["file"]
        assert sha(path) == item["sha256"]
        got = ds.dataset(path, format="parquet").to_table(filter=ds.field("entity_uid").isin(ids)).to_pandas()
        assert len(got) == len(sample) and got.entity_uid.is_unique
        got = got.set_index("entity_uid").loc[ids].reset_index()
        first = got.iloc[0]
        qname = first["function"]
        suppliers = candidates[candidates[qname] > 0].copy()
        cv = vec(suppliers)
        cq = suppliers[qname].to_numpy(float)
        cids = suppliers.entity_uid.astype(str).to_numpy()
        max_abs = 0.0
        for n, ov in enumerate(vec(sample)):
            distances = R * np.arctan2(np.linalg.norm(np.cross(cv, ov), axis=1), cv @ ov)
            scores = cq / float(first.q_ref) * np.power(1 + distances / float(first.d0_km), -float(first.beta))
            own = cids == ids[n]
            local = math.fsum(scores[own].tolist())
            ext = np.where(own, 0.0, scores)
            order = np.argsort(-ext, kind="stable")
            top = ext[order[0]] if len(ext) else 0.0
            second = ext[order[1]] if len(ext) > 1 else 0.0
            ext_sum = math.fsum(ext.tolist())
            den = 1 + local + ext_sum
            dominance = top / max(1, local, second)
            if top <= 0:
                status = "no_observed_external_supplier"
            elif top <= 1:
                status = "below_absolute_threshold"
            elif local >= top:
                status = "local_option_at_least_as_strong"
            elif dominance < float(first.margin_scenario):
                status = "contested"
            else:
                status = "scenario_dominant"
            row = got.iloc[n]
            expected = {"top_score": top, "second_score": second, "local_score": local,
                        "external_score_sum": ext_sum, "outside_weight": 1 / den,
                        "local_weight": local / den, "external_weight_sum": ext_sum / den,
                        "top_weight": top / den, "dominance_over_best_alternative": dominance}
            for col, value in expected.items():
                max_abs = max(max_abs, abs(float(row[col]) - value))
                assert np.isclose(float(row[col]), value, atol=1e-8, rtol=1e-10), (path, ids[n], col, row[col], value)
            assert row.status == status, (path, ids[n], row.status, status)
            assert bool(row.lose_observed_absolute_option_if_top_removed) == bool(top > 1 and second <= 1 and local <= 1)
            if top > 0:
                chosen = np.flatnonzero(cids == str(row.top_center_uid))
                assert len(chosen) == 1
                assert np.isclose(ext[chosen[0]], top, atol=1e-8, rtol=1e-10)
                assert np.isclose(float(row.top_distance_km), distances[chosen[0]], atol=1e-8, rtol=1e-10)
                assert str(row.top_center_uid) != ids[n]
            comparisons += len(expected) + 4
        all_checks.append({"file": item["file"], "n_sample_origins": len(sample),
                           "all_supplier_comparisons": len(sample) * len(suppliers),
                           "max_absolute_numerical_difference": max_abs, "status": "PASS"})
    result = {"status": "PASS_SAMPLED_NUMERICAL_REPLAY_ONLY", "origins_total": len(origins),
              "sample_size": len(sample), "checks_scalar": comparisons,
              "n_outputs": len(all_checks), "details": all_checks,
              "functional_existence_established_by_this_test": False,
              "outside_option_empirically_calibrated_by_this_test": False,
              "code_import_from_author": False,
              "method": "atan2 unit-vector spherical distance + independently implemented formula and status rules",
              "input_sha256": {"origins": sha(args.origins), "candidates": sha(args.candidates)}}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
