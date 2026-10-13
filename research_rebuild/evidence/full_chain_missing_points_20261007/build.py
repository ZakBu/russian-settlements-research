#!/usr/bin/env python3
"""Rebuild the evidence delta for accepted full chains with no accepted point.

Run from any directory with the project Python dependencies installed:
    python research_rebuild/evidence/full_chain_missing_points_20261007/build.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research_rebuild/mass_linkage"))
from current_chain_state_20261007 import State, distance_km, normalize  # noqa: E402

OUT = Path(__file__).resolve().parent
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
TOCHNO = Path("/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet")
GEOKLADR_CACHE = Path("/workspace/settlements-work/sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet")
GEOKLADR_DB = Path("/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf")
CSV = OUT / "point_use_delta.csv"
RECEIPT = OUT / "application_receipt.json"

LOCALITY_TYPES = {
    "село", "деревня", "хутор", "поселок", "пгт", "поселок городского типа",
    "станица", "аул", "улус", "арбан", "аал", "слобода", "починок",
    "выселок", "выселки(ок)", "заимка", "местечко", "сельский поселок",
    "городской поселок",
}
FACILITY_NAME = re.compile(
    r"(?:^|\s)(?:\d+\s*км|километр|ж/д|железнодорож|станци\w*|разъезд\w*|"
    r"платформ\w*|будк\w*|пост\w*|казарм\w*|снт|садов\w* товариществ\w*|"
    r"улиц\w*|район\w*)(?:$|\s)", re.IGNORECASE,
)
GEOKLADR_PREFIX = re.compile(
    r"^(?:д|дер|с|сел|х|хут|п|пос|пгт|ст|стан|п\.ст|п\s*ст|ж/д\s*ст|жд\s*ст|рп|м|а|у)\s+"
)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def component_inventory(state: State):
    obs = state.obs.copy()
    obs["root"] = obs.source_record_id.map(state.uf.find)
    strict = []
    excluded = Counter()
    for root, group in obs.groupby("root", sort=True):
        years = state.years[state.uf.find(root)]
        if years != {2002, 2010, 2021}:
            continue
        if len(group) != 3 or set(group.census_year.astype(int)) != {2002, 2010, 2021}:
            excluded["not_one_selected_record_per_year"] += 1
            continue
        if any(sid in state.point_rows for sid in group.source_record_id):
            continue
        if any(len({normalize(value) for value in group[col]}) != 1 for col in ("settlement_name", "settlement_type", "region_norm")):
            excluded["name_type_or_region_changes"] += 1
            continue
        current = group[group.census_year.eq(2021)]
        if len(current) != 1:
            excluded["missing_or_duplicate_2021_row"] += 1
            continue
        strict.append((root, group, current.iloc[0]))
    return strict, excluded


def main() -> None:
    for path in (SELECTED, TOCHNO, GEOKLADR_CACHE, GEOKLADR_DB):
        if not path.is_file():
            raise FileNotFoundError(path)

    state = State()
    baseline = state.metrics()
    strict, exclusions = component_inventory(state)
    current_ids = {str(current.source_record_id) for _, _, current in strict}

    con = duckdb.connect(config={"threads": 1, "memory_limit": "1GB"})
    selected = con.execute(
        "SELECT source_record_id,settlement_name,settlement_type,region_raw,oktmo,okato,latitude,longitude "
        "FROM read_parquet(?) WHERE census_year=2021",
        [str(SELECTED)],
    ).fetchdf()
    selected.source_record_id = selected.source_record_id.astype(str)
    selected = selected[selected.source_record_id.isin(current_ids)].copy()

    # The provider-facing fields are checked directly. `object_name` alone is
    # not accepted as a proxy for the locality name returned by the provider.
    provider_rows = con.execute(
        "SELECT file_row_number,object_level,settlement_dadata,settlement_type_full_dadata,region,"
        "fias_level_dadata,qc_geo_dadata,oktmo,latitude_dadata,longitude_dadata "
        "FROM read_parquet(?,file_row_number=true) "
        "WHERE object_level='Населенный пункт' AND fias_level_dadata=6 AND qc_geo_dadata=3 "
        "AND latitude_dadata IS NOT NULL AND longitude_dadata IS NOT NULL",
        [str(TOCHNO)],
    ).fetchdf()
    provider_index = {}
    for _, row in provider_rows.iterrows():
        key = (
            normalize(row.settlement_dadata), normalize(row.settlement_type_full_dadata),
            normalize(row.region),
        )
        provider_index.setdefault(key, []).append(row)

    geokladr_rows = con.execute(
        "SELECT historical_okato,record_number_1based,record_byte_offset_0based,name_raw,"
        "settlement_type_raw,longitude_from_long,latitude_from_lat,source_sha256 "
        "FROM read_parquet(?) WHERE latitude_from_lat IS NOT NULL AND longitude_from_long IS NOT NULL "
        "AND NOT is_deleted",
        [str(GEOKLADR_CACHE)],
    ).fetchdf()
    geokladr_index = {}
    for _, row in geokladr_rows.iterrows():
        geokladr_index.setdefault(str(row.historical_okato), []).append(row)

    chosen = {}
    held = Counter()
    for root, group, current in strict:
        target = selected[selected.source_record_id.eq(str(current.source_record_id))]
        if len(target) != 1:
            held["selected_2021_record_not_unique"] += 1
            continue
        target = target.iloc[0]
        name = normalize(target.settlement_name)
        kind = normalize(target.settlement_type)
        region = normalize(target.region_raw)
        if kind not in LOCALITY_TYPES:
            held["nonlocality_or_nonpreferred_type"] += 1
            continue
        if FACILITY_NAME.search(name):
            held["transport_or_facility_name"] += 1
            continue

        if pd.notna(target.oktmo):
            key = (name, kind, region)
            candidates = provider_index.get(key, [])
            if len(candidates) == 1:
                candidate = candidates[0]
                if str(candidate.oktmo) != str(target.oktmo):
                    held["provider_exact_tuple_native_code_disagrees"] += 1
                else:
                    lat, lon = float(candidate.latitude_dadata), float(candidate.longitude_dadata)
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat, lon) == (0, 0):
                        held["provider_invalid_coordinate"] += 1
                    elif pd.notna(target.latitude) and pd.notna(target.longitude) and distance_km(
                        (lat, lon), (float(target.latitude), float(target.longitude))
                    ) > 0.05:
                        held["provider_coordinate_disagrees_with_selected_row"] += 1
                    else:
                        chosen[root] = {
                            "group": group, "current": current, "latitude": lat, "longitude": lon,
                            "source_kind": "tochno_2021_provider_exact", "source_path": str(TOCHNO),
                            "source_sha256": sha(TOCHNO),
                            "source_locator": (
                                f"file_row_number={int(candidate.file_row_number)} (0-based); "
                                f"settlement_dadata={candidate.settlement_dadata}; "
                                f"settlement_type_full_dadata={candidate.settlement_type_full_dadata}; "
                                f"region={candidate.region}; fias_level_dadata=6; qc_geo_dadata=3; "
                                f"oktmo={candidate.oktmo}"
                            ),
                        }
                        continue
            if len(candidates) > 1:
                held["provider_exact_name_type_region_not_unique"] += 1

        # GeoKLADR fallback requires a unique exact full OKATO and an exact
        # locality name after removing only the classifier type prefix.
        if pd.isna(target.okato):
            held["no_exact_provider_point_or_okato"] += 1
            continue
        candidates = geokladr_index.get(str(target.okato), [])
        candidates = [
            row for row in candidates
            if GEOKLADR_PREFIX.sub("", normalize(row.name_raw)) == name
        ]
        if len(candidates) != 1:
            held["geokladr_exact_name_okato_not_unique_or_absent"] += 1
            continue
        candidate = candidates[0]
        lat, lon = float(candidate.latitude_from_lat), float(candidate.longitude_from_long)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat, lon) == (0, 0):
            held["geokladr_invalid_coordinate"] += 1
            continue
        if pd.notna(target.latitude) and pd.notna(target.longitude):
            if distance_km((lat, lon), (float(target.latitude), float(target.longitude))) > 5:
                held["geokladr_disagrees_with_selected_coordinate_over_5km"] += 1
                continue
        chosen[root] = {
            "group": group, "current": current, "latitude": lat, "longitude": lon,
            "source_kind": "geokladr_2011_exact_okato_name", "source_path": str(GEOKLADR_DB),
            "source_sha256": str(candidate.source_sha256),
            "source_locator": (
                f"record_number_1based={int(candidate.record_number_1based)}; "
                f"record_byte_offset_0based={int(candidate.record_byte_offset_0based)}; "
                f"historical_okato={target.okato}; name_raw={candidate.name_raw}; "
                f"settlement_type_raw={candidate.settlement_type_raw}"
            ),
        }

    rows = []
    for root, item in chosen.items():
        group, current = item["group"], item["current"]
        direct = item["source_kind"] == "tochno_2021_provider_exact"
        for _, target in group.sort_values("census_year").iterrows():
            is_current = int(target.census_year) == 2021
            if direct:
                origin = (
                    "Direct Tochno/DaData source coordinates. Exact provider locality name, full type, "
                    "and region match the selected 2021 row; object_level=Населенный пункт, "
                    "fias_level_dadata=6, qc_geo_dadata=3, and OKTMO agrees."
                    if is_current else
                    "Spatial continuity inference from the exact 2021 provider point across an already "
                    "accepted full same_place chain with invariant name/type/region; no historic point measurement."
                )
            else:
                origin = (
                    "Direct GeoKLADR 2011 coordinates from a unique exact full-OKATO record whose locality "
                    "name matches after removing the classifier type prefix; no provider identifier binding."
                    if is_current else
                    "Spatial continuity inference from the unique exact-name GeoKLADR 2011 point across an "
                    "already accepted full same_place chain; no census-year point measurement."
                )
            rows.append({
                "target_source_record_id": str(target.source_record_id),
                "target_year": int(target.census_year),
                "latitude": item["latitude"], "longitude": item["longitude"],
                "source": item["source_path"], "source_sha256": item["source_sha256"],
                "source_locator": item["source_locator"],
                "coordinate_source_record_id": str(current.source_record_id),
                "coordinate_admission_status": "reviewed_extension_rule_accepted",
                "coordinate_quality": (
                    "source_geocoded_settlement_point_fias6_qc_geo3" if direct and is_current else
                    "geokladr_2011_unique_exact_okato_name_point" if is_current else
                    "representative_point_inherited_over_accepted_identity"
                ),
                "provider_binding_asserted": False,
                "coordinate_origin_kind": (
                    "direct_selected_2021_provider_exact" if direct and is_current else
                    "direct_geokladr_2011_source_row" if is_current else
                    "accepted_same_place_spatial_continuity_inference"
                ),
                "origin": origin,
            })

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("No eligible point uses were found")
    if frame.target_source_record_id.duplicated().any():
        raise RuntimeError("Duplicate point-use target")
    if not frame.provider_binding_asserted.eq(False).all():
        raise RuntimeError("Provider binding must remain unasserted")
    if not frame.latitude.between(-90, 90).all() or not frame.longitude.between(-180, 180).all():
        raise RuntimeError("Invalid coordinate in output")

    after = state.metrics(extra_point_ids=frame.target_source_record_id.astype(str).tolist())
    components_by_source = Counter(item["source_kind"] for item in chosen.values())
    source_by_component = {
        str(item["current"].source_record_id): item["source_kind"] for item in chosen.values()
    }
    population_by_year = {}
    for year in (2002, 2010, 2021):
        targets = frame[frame.target_year.eq(year)]
        population_by_year[str(year)] = {
            "point_uses_added": int(len(targets)),
            "population_point_uses_added": int(sum(
                state.by_id.loc[sid, "population"] for sid in targets.target_source_record_id
                if pd.notna(state.by_id.loc[sid, "population"])
            )),
        }

    frame.to_csv(CSV, index=False)
    graph_inputs = {
        str(path): {"sha256": sha(path), "bytes": path.stat().st_size}
        for path in state.inputs
    }
    other_inputs = {}
    for path in (SELECTED, TOCHNO, GEOKLADR_CACHE, GEOKLADR_DB):
        other_inputs[str(path)] = {"sha256": sha(path), "bytes": path.stat().st_size}
    receipt = {
        "status": "reproducibly_built_raw_points_for_existing_accepted_full_chains",
        "full_chain_components_without_any_accepted_point_at_start": len(strict),
        "components_with_point_uses_added": len(chosen),
        "point_uses_added": len(frame),
        "source_components": dict(components_by_source),
        "point_use_rows_by_origin_kind": dict(Counter(frame.coordinate_origin_kind)),
        "coverage_baseline": baseline,
        "coverage_after": after,
        "full_chain_population_gain_by_year": {
            year: after[year]["covered_population"] - baseline[year]["covered_population"]
            for year in baseline
        },
        "point_uses_by_year": population_by_year,
        "held_components_by_reason": dict(held),
        "preselection_exclusions": dict(exclusions),
        "rules": {
            "common": "Already accepted full same_place component, exactly one selected row per census year, unchanged settlement name/type/region across 2002/2010/2021, and no accepted point at start.",
            "tochno_2021": "Unique exact source-provider settlement_dadata, settlement_type_full_dadata and region match to selected row; object_level=Населенный пункт and fias_level_dadata=6 and qc_geo_dadata=3; source OKTMO must equal selected OKTMO; coordinates must agree with selected 2021 coordinates within 50 m when present.",
            "geokladr_2011": "Fallback only: unique exact full OKATO and exact locality name after removing a classifier type prefix; locality type allowed; selected coordinate, when present, must be within 5 km.",
            "continuity": "2021 source point is reused on earlier rows only as a spatial continuity inference over the already accepted identity; no historical point measurement or external provider identifier binding is asserted.",
        },
        "provider_binding_asserted": False,
        "graph_inputs": graph_inputs,
        "graph_composition": {
            "accepted_graph25_edges_path": str(state.inputs[1]),
            "accepted_graph25_point_uses_path": str(state.inputs[2]),
            "accepted_identity_edge_delta_paths": [str(path) for path in state.inputs[3:12]],
            "accepted_point_use_delta_paths": [str(path) for path in state.inputs[12:]],
            "accepted_identity_edge_delta_count": len(state.inputs[3:12]),
            "accepted_point_use_delta_count": len(state.inputs[12:]),
        },
        "source_inputs": other_inputs,
        "build_script_sha256": sha(Path(__file__)),
    }
    receipt["outputs"] = {CSV.name: sha(CSV)}
    RECEIPT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "components": len(chosen), "points": len(frame),
        "source_components": dict(components_by_source),
        "gains": receipt["full_chain_population_gain_by_year"],
        "coverage_after": {year: after[year]["coverage_percent"] for year in after},
        "held_components": dict(held),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
