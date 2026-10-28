"""Freeze exact public inputs and evaluation points for a bounded field pilot.

The circles select evaluation locations, not sources, catchments or service
boundaries. Sources are all current ordinary spatial records in the accepted
national reference. Population and road missingness remain explicit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.research_data import archive_member
TRANSPORT = "research/sgrt_word_completion_20261021/transport/cycle06_network2021_access_v2/"
REFERENCE = "sgrt/zero20261025/context/analysis_reference.parquet"
ENDPOINTS = "sgrt/identity20261026/routes/endpoint_network_quality.parquet"
GRAPH_SHA256 = "a6713a186f07d76193b0fc494bc35a3b5a9a8148744fda691487a461d8b6a366"
PREFIX = "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:"
PILOTS = (
    ("saratov_engels", PREFIX + "118372", "Саратов — Энгельс"),
    ("uchaly", PREFIX + "148722", "Учалы: город и соседние сёла"),
    ("ustye", PREFIX + "12160", "Устье: Усть-Кубинский район"),
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def catalog_source(catalog: Path, relative: str) -> dict:
    cat = json.loads(catalog.read_text())
    row = next(r for r in cat["files"] if r["path"] == relative)
    obj = cat["objects"][row["blob"]]
    tag = cat.get("release_tag")
    asset = row.get("asset", obj.get("asset"))
    url = obj.get("url")
    if not url and tag and asset:
        url = f"https://github.com/ZakBu/russian-settlements-research/releases/download/{tag}/{asset}"
    return {
        "catalog": str(catalog.relative_to(REPO)),
        "path": relative,
        "sha256": obj["sha256"],
        "bytes": row["bytes"],
        "release_tag": tag,
        "url": url,
        "archive_member": archive_member(obj, row["blob"]),
    }


def haversine(lat, lon, centre_lat, centre_lon):
    lat, lon = np.radians(lat), np.radians(lon)
    centre_lat, centre_lon = np.radians([centre_lat, centre_lon])
    a = np.sin((lat - centre_lat) / 2) ** 2
    a += np.cos(lat) * np.cos(centre_lat) * np.sin((lon - centre_lon) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def prepare(reference: pd.DataFrame, endpoints: pd.DataFrame):
    """One row per current ordinary spatial identity, without population filtering."""
    cols = ["root", "source_record_id", "name", "region", "district", "lat", "lon",
            "population_2021", "credit_2021", "budget_population_credit",
            "ordinary_spatial_2021", "analysis_origin", "population_role"]
    current = reference.loc[
        reference.ordinary_spatial_2021.eq(True)
        & reference.accepted_point_present.eq(True)
        & reference.source_record_id.notna(), cols].copy()
    if current.source_record_id.duplicated().any():
        raise ValueError("Current reference IDs are not unique")
    if endpoints.source_record_id.duplicated().any():
        raise ValueError("Road endpoint IDs are not unique")
    keep = ["source_record_id", "road_node_index", "snap_km", "road_endpoint_accepted",
            "verified_component_id", "verified_component_node_count"]
    current = current.merge(endpoints[keep], on="source_record_id", how="left", validate="one_to_one")
    known = (current.credit_2021.eq(True) & current.budget_population_credit.eq(True)
             & current.population_2021.notna() & np.isfinite(current.population_2021)
             & current.population_2021.ge(0))
    published = current.population_2021.notna() & np.isfinite(current.population_2021) & current.population_2021.ge(0)
    current["population_data_status"] = np.where(published, "published_nonnegative_value", "missing_or_invalid_value")
    current["mass_status"] = "unknown_or_invalid_population"
    current.loc[published, "mass_status"] = "published_value_not_credited"
    current.loc[known & current.population_2021.eq(0), "mass_status"] = "credited_known_zero"
    current.loc[known & current.population_2021.gt(0), "mass_status"] = "credited_known_positive"
    current["mass_2021"] = current.population_2021.where(known)
    accepted = (current.road_endpoint_accepted.eq(True) & current.road_node_index.notna()
                & current.snap_km.notna() & current.snap_km.between(0, 10))
    current["road_status"] = np.where(accepted, "accepted_current_endpoint", "unaccepted_or_missing_endpoint")
    current["routable"] = accepted
    current["connector_minutes"] = current.snap_km * 4  # explicit inherited 15 km/h scenario
    return current.sort_values("source_record_id").reset_index(drop=True)


def build(input_root: Path, output: Path, radius_km=30., core_km=20.):
    output.mkdir(parents=True, exist_ok=True)
    sources = [catalog_source(REPO / "data/zero_catalog_20261025.json", REFERENCE),
               catalog_source(REPO / "data/identity_catalog_20261026.json", ENDPOINTS)]
    for n in range(3):
        sources.append(catalog_source(REPO / "data/catalog.json",
                                      TRANSPORT + f"graph_npz_parts/part_{n:03d}.bin"))
    for item in sources:
        path = input_root / item["path"]
        if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
            raise ValueError("Source differs from immutable catalog: " + item["path"])
    h = hashlib.sha256()
    for n in range(3):
        with (input_root / TRANSPORT / f"graph_npz_parts/part_{n:03d}.bin").open("rb") as f:
            for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                h.update(block)
    if h.hexdigest() != GRAPH_SHA256:
        raise ValueError("Joined graph differs")
    ref = pd.read_parquet(input_root / REFERENCE)
    nodes = prepare(ref, pd.read_parquet(input_root / ENDPOINTS))
    nodes.to_parquet(output / "sourceweights.parquet", index=False, compression="zstd")
    evaluations, diagnostics = [], []
    for pilot, anchor_id, label in PILOTS:
        anchor = nodes.loc[nodes.source_record_id.eq(anchor_id)]
        if len(anchor) != 1:
            raise ValueError("Anchor identity is absent or ambiguous")
        a = anchor.iloc[0]
        distance = haversine(nodes.lat.to_numpy(), nodes.lon.to_numpy(), a.lat, a.lon)
        selected = nodes.loc[distance <= radius_km].copy()
        selected["pilot"] = pilot
        selected["pilot_label"] = label
        selected["anchor_id"] = anchor_id
        selected["distance_to_anchor_km"] = distance[distance <= radius_km]
        selected["evaluation_core"] = selected.distance_to_anchor_km.le(core_km)
        selected["evaluation_eligible"] = selected.routable
        evaluations.append(selected)
        diagnostics.append({"pilot": pilot, "anchor_id": anchor_id, "anchor_name": a["name"],
            "anchor_region": a.region, "anchor_population_2021": a.population_2021,
            "records_in_evaluation_window": len(selected),
            "routable_evaluation_records": int(selected.routable.sum()),
            "routable_core_records": int((selected.routable & selected.evaluation_core).sum()),
            "mass_statuses": selected.mass_status.value_counts().to_dict(),
            "unroutable_known_positive_records": int((~selected.routable & selected.mass_status.eq("credited_known_positive")).sum()),
            "uncredited_published_population_sum_not_added": float(selected.loc[selected.mass_status.eq("published_value_not_credited"), "population_2021"].sum())})
    evaluation = pd.concat(evaluations, ignore_index=True)
    evaluation.to_csv(output / "evaluation.csv", index=False)
    evaluation.to_parquet(output / "evaluation.parquet", index=False, compression="zstd")
    current = ref.loc[ref.source_record_id.notna()].copy()
    outside = current.loc[~current.source_record_id.isin(nodes.source_record_id)]
    outside_ordinary = outside.loc[outside.population_role.eq("ordinary_settlement_record")]
    contexts = outside.loc[outside.population_role.ne("ordinary_settlement_record")]
    uncredited = nodes.loc[nodes.mass_status.eq("published_value_not_credited")]
    population_ledger = {
        "current_reference_records": len(current),
        "ordinary_spatial_records": len(nodes),
        "ordinary_spatial_uncredited_published_positive_records": int((uncredited.population_2021.gt(0)).sum()),
        "ordinary_spatial_uncredited_published_zero_records": int((uncredited.population_2021.eq(0)).sum()),
        "ordinary_spatial_uncredited_published_sum_not_added": float(uncredited.population_2021.sum()),
        "ordinary_spatial_missing_or_invalid_population_records": int(nodes.population_data_status.eq("missing_or_invalid_value").sum()),
        "ordinary_nonspatial_current_records": len(outside_ordinary),
        "ordinary_nonspatial_published_population_sum_not_added": float(outside_ordinary.population_2021.sum()),
        "ordinary_nonspatial_credited_records": int(outside_ordinary.credit_2021.eq(True).sum()),
        "ordinary_nonspatial_credited_population_sum_not_added": float(outside_ordinary.loc[outside_ordinary.credit_2021.eq(True), "population_2021"].sum()),
        "nonadditive_federal_context_records_not_added": len(contexts),
        "nonadditive_federal_context_raw_sum_not_an_additive_total": float(contexts.population_2021.sum()),
        "uncredited_scope": "Published but not accepted as additive population credit; this is neither a missing source value nor a zero. No claim that all such rows are duplicates.",
        "conservative_excluded_published_raw_sum_upper_bound_may_double_count": float(uncredited.population_2021.sum() + outside.population_2021.sum()),
        "excluded_mass_bound_scope": "Envelope over excluded published values in this reference only, allowing intentional double count. Not an asserted upper bound on true Russian population, unknown data errors or unrecorded settlements. Never add it as an estimated population total.",
    }
    result = {"schema": "sgrt.field_pilot.inputs.v1", "source_files": sources,
        "graph_sha256": GRAPH_SHA256, "graph_cost_unit": "modelled_minutes",
        "graph_directed": True, "graph_epoch": "2021-01-01T21:42:03Z",
        "connector_scenario_kmh": 15, "maximum_inherited_snap_km": 10,
        "graph_scope": "full_national_graph_not_induced_window",
        "evaluation_circle_km": radius_km, "evaluation_core_circle_km": core_km,
        "circle_scope": "evaluation_locations_only_not_mass_sources_or_catchments",
        "national_current_ordinary_spatial_records": len(nodes),
        "national_mass_statuses": nodes.mass_status.value_counts().to_dict(),
        "population_accounting": population_ledger,
        "national_routable_records": int(nodes.routable.sum()),
        "national_known_positive_mass": float(nodes.mass_2021.sum()),
        "national_known_positive_mass_without_accepted_endpoint": float(nodes.loc[~nodes.routable, "mass_2021"].sum()),
        "pilots": diagnostics,
        "excluded_nonadditive_contexts": ref.loc[ref.population_role.ne("ordinary_settlement_record") & ref.source_record_id.notna(), ["source_record_id", "name", "population_role", "population_2021"]].to_dict("records"),
        "uncredited_examples": uncredited.nlargest(10, "population_2021")[["source_record_id", "name", "region", "population_2021", "credit_2021"]].to_dict("records"),
        "population_missingness": "Published uncredited values remain distinct from unknown population and from known zero. The current source frame has no unknown numeric population values; its uncredited published values have mass_2021=NULL because additive credit is not established.",
        "uncomputed_road_pairs": "Outside a finite search limit is censored, not disconnected. Unaccepted endpoints are unknown, not isolated.",
        "evaluation": {"csv": "evaluation.csv", "parquet": "evaluation.parquet"},
        "source_weights": "sourceweights.parquet"}
    (output / "input_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--radius-km", type=float, default=30.)
    ap.add_argument("--core-km", type=float, default=20.)
    a = ap.parse_args()
    if not 0 < a.core_km < a.radius_km:
        ap.error("Require 0 < core-km < radius-km")
    result = build(a.input_root, a.output, a.radius_km, a.core_km)
    print(json.dumps({k: v for k, v in result.items() if k not in {"source_files", "excluded_nonadditive_contexts"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
