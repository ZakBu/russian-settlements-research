#!/usr/bin/env python3
"""Apply one shared locality anchor to census rows split across rural OKTMO units."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import duckdb
import pandas as pd
from build_long_table import ACCEPTED_COORDINATE_STATUSES, ACCEPTED_EDGE_STATUSES, UnionFind

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/shared_locality_point_novaya_usman_20261005"
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
EDGES = Path("/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet")
POINTS = Path("/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet")
RAW_2021 = Path("/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet")
WD_OKTMO = Path("/workspace/settlements-raw/data/raw/wikimedia/wikidata_oktmo_entities.tsv")
FIAS = "d479d838-44a8-4c60-9044-83caa34308e4"
COORD = (51.6440564, 39.4129162)
PARTS = {
    1: {
        2002: "2002:004_f58b08b4f6_02c_Voronezhskaja.xls:Sheet1:1184",
        2010: "2010:013_f60b2d2bcf_5._20Belg_Bryan_Vlad_Voron_Ivanov_Kalug_20L1_ethn_2010.xls:Data Sheet:7530",
        2021: "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:14878",
    },
    2: {
        2002: "2002:004_f58b08b4f6_02c_Voronezhskaja.xls:Sheet1:1190",
        2010: "2010:013_f60b2d2bcf_5._20Belg_Bryan_Vlad_Voron_Ivanov_Kalug_20L1_ethn_2010.xls:Data Sheet:7535",
        2021: "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:14880",
    },
}
STATUSES = sorted(ACCEPTED_COORDINATE_STATUSES)


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main() -> None:
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    selected = con.execute(
        "select source_record_id,census_year,settlement_name,settlement_type,region_norm,district_norm,population,"
        "fias_id,oktmo,source_file,source_row,source_sha256,source_path,source_locator,is_additive_settlement_record "
        "from read_parquet(?)",
        [str(SELECTED)],
    ).fetchdf().set_index("source_record_id", drop=False)
    ids = [sid for part in PARTS.values() for sid in part.values()]
    rows = selected.loc[ids]
    if len(rows) != 6 or rows.source_record_id.duplicated().any():
        raise RuntimeError("selected part endpoints missing or repeated")
    if set(rows.census_year.astype(int)) != {2002, 2010, 2021} or len(rows[rows.census_year.eq(2002)]) != 2:
        raise RuntimeError("unexpected census-year structure")
    for row in rows.itertuples(index=False):
        if not bool(row.is_additive_settlement_record) or row.settlement_type != "село" or row.region_norm != "воронежская":
            raise RuntimeError(f"unexpected census grain/type/region: {row.source_record_id}")
        if f"(часть " not in row.settlement_name:
            raise RuntimeError(f"missing explicit part label: {row.source_record_id}")
    if not (rows.settlement_name.str.replace(r" \(часть [12]\)$", "", regex=True).nunique() == 1):
        raise RuntimeError("parts do not share one base settlement name")

    # Build the accepted graph plus recorded deltas and require each same-part chain.
    uf = UnionFind(selected.index.astype(str))
    for a, b in con.execute(
        "select from_source_record_id,to_source_record_id from read_parquet(?) "
        "where relation='same_place' and decision_status in (select unnest(?))",
        [str(EDGES), sorted(ACCEPTED_EDGE_STATUSES)],
    ).fetchall():
        uf.union(str(a), str(b))
    delta_paths = [
        (ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/accepted_identity_edge_delta.csv", "from_id", "to_id"),
        (ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/top60_identity_edge_delta.csv", "from_id", "to_id"),
        (ROOT / "research_rebuild/evidence/top100_classifier_bridge_20261005/accepted_classifier_bridge_delta.csv", "source_record_id_old", "source_record_id_current"),
        (ROOT / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005/accepted_identity_edge_delta.csv", "from_source_record_id", "to_source_record_id"),
    ]
    for path, left, right in delta_paths:
        df = pd.read_csv(path)
        for a, b in df[[left, right]].itertuples(index=False, name=None):
            uf.union(str(a), str(b))
    for part, chain in PARTS.items():
        roots = {uf.find(sid) for sid in chain.values()}
        if len(roots) != 1:
            raise RuntimeError(f"part {part} is not already one accepted component")
        root = next(iter(roots))
        members = selected[selected.source_record_id.map(lambda sid: uf.find(str(sid)) == root)]
        year_counts = members.census_year.astype(int).value_counts().to_dict()
        if year_counts != {2002: 1, 2010: 1, 2021: 1}:
            raise RuntimeError(f"part {part} component is not a one-row-per-year full chain: {year_counts}")

    # Verify both 2021 source rows directly in the exact cached source and shared FIAS.
    raw = con.execute(
        "select object_name,oktmo,region,mun_upper,mun_lower,settlement,population,settlement_fias_id_dadata,"
        "settlement_dadata,fias_id_dadata,fias_level_dadata,okato_dadata,oktmo_dadata,qc_geo_dadata,qc_dadata,"
        "latitude_dadata,longitude_dadata from read_parquet(?) where settlement_fias_id_dadata=? order by oktmo",
        [str(RAW_2021), FIAS],
    ).fetchdf()
    if len(raw) != 2 or set(raw.oktmo.astype(str)) != {"20625491101", "20625492101"}:
        raise RuntimeError("the shared-FIAS raw source group changed")
    if raw.settlement_dadata.nunique() != 1 or raw.settlement_dadata.iloc[0] != "Новая Усмань" or raw.fias_id_dadata.nunique() != 1:
        raise RuntimeError("shared FIAS parent-name conditions changed")
    if not (raw.latitude_dadata.map(lambda v: math.isclose(float(v), COORD[0], abs_tol=1e-7)).all() and raw.longitude_dadata.map(lambda v: math.isclose(float(v), COORD[1], abs_tol=1e-7)).all()):
        raise RuntimeError("shared point coordinates changed")
    if set(raw.qc_geo_dadata.astype(int)) != {3} or set(raw.qc_dadata.astype(int)) != {1} or raw.fias_level_dadata.astype(str).nunique() != 1 or raw.fias_level_dadata.iloc[0] != "6":
        raise RuntimeError("DaData point quality/level changed")

    # Wikidata independently names the parent locality and provides a point/code.
    lines = [line for line in WD_OKTMO.read_text(encoding="utf-8").splitlines() if "Q2003465" in line]
    if not lines:
        raise RuntimeError("local Wikidata row for Q2003465 missing")
    qid_fields = lines[0].split("\t")
    if not ("20625491101" in lines[0] and "Новая Усмань" in lines[0] and "POINT(39.410278 51.643889)" in lines[0]):
        raise RuntimeError("cached Wikidata parent record changed")
    qlat, qlon = 51.643889, 39.410278
    distance_km = 2 * 6371 * math.asin(math.sqrt(math.sin(math.radians(COORD[0] - qlat) / 2) ** 2 + math.cos(math.radians(COORD[0])) * math.cos(math.radians(qlat)) * math.sin(math.radians(COORD[1] - qlon) / 2) ** 2))
    if distance_km > 0.25:
        raise RuntimeError("independent QID point farther than 250m")

    existing = con.execute(
        "select target_source_record_id,target_year,latitude,longitude from read_parquet(?) "
        "where coordinate_admission_status in (select unnest(?))",
        [str(POINTS), STATUSES],
    ).fetchdf()
    for path in [
        ROOT / "research_rebuild/evidence/top60_and_proximity_review_20261005/simple_rule_application/top60_point_use_delta.csv",
        ROOT / "research_rebuild/evidence/top100_classifier_bridge_20261005/old_point_use_delta.csv",
        ROOT / "research_rebuild/evidence/historical_urban_code_residual_20261005/accepted_point_use_delta.csv",
        ROOT / "research_rebuild/evidence/historical_classifier_bridge_batch_20261005/accepted_retrospective_point_use_delta.csv",
    ]:
        x = pd.read_csv(path)
        lat_col = "latitude" if "latitude" in x.columns else "carrier_latitude"
        lon_col = "longitude" if "longitude" in x.columns else "carrier_longitude"
        existing = pd.concat([existing, x[["target_source_record_id", "target_year", lat_col, lon_col]].rename(columns={lat_col: "latitude", lon_col: "longitude"})], ignore_index=True)
    if set(ids) & set(existing.target_source_record_id.astype(str)):
        raise RuntimeError("one or more endpoints already have an accepted point use")
    key = (round(COORD[0], 7), round(COORD[1], 7))
    outside = existing[
        (existing.target_year.astype(str).str.replace(r"\.0$", "", regex=True).isin(["2002", "2010", "2021"]))
        & (existing.latitude.round(7) == key[0]) & (existing.longitude.round(7) == key[1])
    ]
    if len(outside):
        raise RuntimeError("the shared locality anchor is already used by an unrelated accepted endpoint")

    result = []
    for part, chain in PARTS.items():
        for year, sid in chain.items():
            r = selected.loc[sid]
            result.append({
                "target_source_record_id": sid, "target_year": year,
                "target_name": r.settlement_name, "base_locality_name": "Новая Усмань",
                "target_type": r.settlement_type, "target_region": r.region_norm,
                "target_population": int(r.population), "latitude": COORD[0], "longitude": COORD[1],
                "shared_locality_id": f"shared_fias_parent:{FIAS}", "shared_part_number": part,
                "shared_parent_fias_id": FIAS, "distinct_part_oktmo_2021": str(raw.loc[raw.object_name.str.contains(f"часть {part}"), "oktmo"].iloc[0]) if year == 2021 else None,
                "anchor_source": "Tochno 2021 DaData FIAS level 6 parent locality point",
                "anchor_source_file": str(RAW_2021), "anchor_source_sha256": sha(RAW_2021),
                "anchor_source_record_id_part1": PARTS[1][2021], "anchor_source_record_id_part2": PARTS[2][2021],
                "anchor_fias_id": FIAS, "anchor_fias_level": 6, "anchor_qc_geo": 3, "anchor_qc_dadata": 1,
                "independent_wikidata_qid": "Q2003465", "wikidata_qid_typed_code_binds_to_part": 1,
                "wikidata_point_distance_m": distance_km * 1000,
                "coordinate_admission_status": "reviewed_case_accepted",
                "coordinate_application_family": "shared_parent_locality_point_for_split_oktmo_census_rows_20261005",
                "point_is_parent_locality_anchor": True, "same_coordinate_allowed_reason": "two census rows are explicitly labeled parts of the same settlement; both source rows share the same FIAS level-6 locality ID and exact parent locality/coordinate",
                "measurement_date_unknown": False if year == 2021 else True,
                "provider_identifier_binding_asserted": False,
                "population_value_changed": False, "population_boundary_comparability_asserted": False,
                "identity_chain_preexisting": True,
            })
    pd.DataFrame(result).to_csv(OUT / "accepted_shared_locality_point_uses.csv", index=False)
    summary = {
        "status": "accepted_shared_parent_locality_anchor_for_two_split_rows_per_census",
        "records": 6,
        "records_by_year": {str(y): 2 for y in [2002, 2010, 2021]},
        "population_covered_by_year": {str(y): int(rows.loc[rows.census_year.eq(y), "population"].sum()) for y in [2002, 2010, 2021]},
        "one_locality_two_record_parts": True,
        "shared_coordinate_allowed": True,
        "reason": "The 2021 primary selected source lists parts 1 and 2 as one base locality, with identical FIAS level-6 ID/name and exact same coordinate; distinct OKTMO units partition population rows. A local Wikidata item independently represents the parent locality with matching part-1 OKTMO and a point 0.183 km away. Existing accepted graph already gives each part its own 2002-2010-2021 chain.",
        "within_year_other_endpoint_coordinate_collision": 0,
        "identity_edges_added": 0,
        "population_values_modified": False,
        "population_boundary_comparability_asserted": False,
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in [SELECTED, EDGES, POINTS, RAW_2021, WD_OKTMO] + [p for p, _, _ in delta_paths]},
        "limitations": ["The coordinate locates the shared parent settlement; it does not locate the separate municipal parts within that settlement.", "Wikidata's OKTMO matches part 1 only; part 2's coordinate inheritance is supported by the shared FIAS parent record, not by a direct Wikidata code binding.", "No census population values or boundaries are claimed comparable because of this point assignment."],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Общий координатный якорь для двух частей Новой Усмани\n\n"
        "Две строки 2021 года явно названы частями одного села и имеют разные ОКТМО, но одинаковые parent-name, FIAS level-6 ID, DaData point и тип села. Локальный Wikidata Q2003465 подтверждает базовое село и ОКТМО части 1; его точка находится в 183 м. Отдельная часть 2 не объявляется кодово связанной с QID: её положение представлено тем же parent-locality anchor только потому, что исходная переписная таблица обеих частей прямо связывает их с одним FIAS locality ID/координатой.\n\n"
        "Обе части уже имеют независимые accepted 2002–2010–2021 identity chains. Поэтому один и тот же anchor записан для соответствующих шести годовых endpoint-строк с явным `shared_locality_id`; повтор координаты здесь означает одно физическое село, разделённое на два муниципальных учётных ряда, а не два coincident NP. Население и границы не менялись и не объявляются сопоставимыми. Сводка, локаторы и hashes: `summary.json` и CSV.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    main()
