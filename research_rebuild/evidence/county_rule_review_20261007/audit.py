"""Independent, read-only audit of the 2026-10-07 county bridge package."""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research_rebuild/mass_linkage"))
from apply_unique_county_name_bridge_20261007 import EXTRA_EDGES, EXTRA_POINTS, county_key
from current_chain_state_20261007 import State, distance_km, normalize
from build_long_table import ACCEPTED_COORDINATE_STATUSES

OUT = Path(__file__).resolve().parent
PACKAGE = ROOT / "research_rebuild/evidence/unique_county_name_bridge_20261007"
RAW = Path("/workspace/settlements-raw")
SELECTED = Path("/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet")
RAW_2021 = RAW / "data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def raw_row_text(frame: pd.DataFrame, row_number: int) -> str:
    return " ".join(str(v).strip() for v in frame.iloc[row_number - 1].to_list() if pd.notna(v))


def county_witness(frame: pd.DataFrame, row_number: int, key: str) -> tuple[str, str]:
    # The source books use a district heading or a district cell at the first
    # locality of a block; retain the literal text and source row for review.
    for idx in range(row_number - 1, max(-1, row_number - 1201), -1):
        for col, cell in enumerate(frame.iloc[idx, :min(8, frame.shape[1])]):
            if pd.isna(cell):
                continue
            literal = str(cell).strip()
            explicit_level = re.search(r"район|округ|город|улус|\bр[. -]?н\b", normalize(literal))
            bare_district_cell = col in (1, 2, 3) and county_key(literal) == key
            if key and ((explicit_level and key in county_key(literal)) or bare_district_cell):
                return str(idx + 1), literal
    return "", ""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    edge_file = PACKAGE / "accepted_identity_edge_delta.csv"
    point_file = PACKAGE / "accepted_point_use_delta.csv"
    edges = pd.read_csv(edge_file, dtype=str, keep_default_na=False)
    points = pd.read_csv(point_file, dtype=str, keep_default_na=False)
    receipt = json.loads((PACKAGE / "application_receipt.json").read_text())
    issues: list[dict] = []

    def issue(kind: str, sid: str, detail: str) -> None:
        issues.append({"kind": kind, "source_record_id": sid, "detail": detail})

    state = State()
    state.add_deltas(EXTRA_EDGES, EXTRA_POINTS)
    all_obs = state.obs.copy()
    all_obs["n"] = all_obs.name_norm.map(normalize)
    all_obs["t"] = all_obs.type_norm.map(normalize)
    all_obs["r"] = all_obs.region_norm.map(normalize)
    all_obs["d"] = all_obs.district_raw.map(county_key)
    allowed = all_obs.is_additive_settlement_record.fillna(False) & ~all_obs.settlement_name.fillna("").str.contains(r"\(часть", regex=True)
    key_count = all_obs[allowed].groupby(["census_year", "n", "t", "r", "d"], dropna=False).size()
    endpoint_ids = set(edges.from_source_record_id) | set(edges.to_source_record_id)
    c = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    selected_extra = c.execute(
        "SELECT source_record_id,source_sheet,source_row,source_name_raw,source_file,source_locator,"
        "snapshot_record_type,entity_grain_status,population_scope,population,oktmo,district_raw "
        "FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))",
        [str(SELECTED), sorted(endpoint_ids)],
    ).fetchdf().set_index("source_record_id")
    if len(selected_extra) != len(endpoint_ids):
        issue("endpoint_missing", "", f"distinct IDs={len(endpoint_ids)} selected rows={len(selected_extra)}")
    if len(edges) != 422 or len(points) != 422:
        issue("count", "", f"edges={len(edges)} points={len(points)}")
    if edges[["from_source_record_id", "to_source_record_id"]].duplicated().any():
        issue("duplicate_edge", "", "duplicate ordered endpoint pair")
    if points.target_source_record_id.duplicated().any():
        issue("duplicate_point_target", "", "more than one new point per target")

    for _, edge in edges.iterrows():
        aid, bid = edge.from_source_record_id, edge.to_source_record_id
        if aid not in state.by_id.index or bid not in state.by_id.index:
            issue("unknown_endpoint", f"{aid}|{bid}", "missing in selected"); continue
        for sid, year in ((aid, edge.from_year), (bid, edge.to_year)):
            row = state.by_id.loc[sid]
            if int(row.census_year) != int(year):
                issue("year_mismatch", sid, year)
            if not bool(row.is_additive_settlement_record) or row.settlement_name.find("(часть") >= 0:
                issue("grain_flag", sid, str(row.settlement_name))
            ex = selected_extra.loc[sid]
            if ex.snapshot_record_type != "settlement_observation" or ex.entity_grain_status not in (None, "settlement_shared_okato_review") and pd.notna(ex.entity_grain_status):
                issue("source_grain", sid, f"{ex.snapshot_record_type}|{ex.entity_grain_status}")
            if not isinstance(ex.district_raw, str) or len(ex.district_raw.strip()) < 3:
                issue("missing_raw_county", sid, str(ex.district_raw))
            actual = (normalize(row.name_norm), normalize(row.type_norm), normalize(row.region_norm), county_key(row.district_raw))
            recorded = (edge.name_norm, edge.type_norm, edge.region_norm, edge.county_key)
            if actual != recorded:
                issue("key_mismatch", sid, f"actual={actual} recorded={recorded}")
            if key_count.get((int(year), *recorded), 0) != 1:
                issue("nonunique_county_year_key", sid, f"count={key_count.get((int(year), *recorded), 0)}")
        if edge.from_district_raw != state.by_id.loc[aid].district_raw or edge.to_district_raw != state.by_id.loc[bid].district_raw:
            issue("district_literal_mismatch", f"{aid}|{bid}", "CSV differs from selected district_raw")
        if edge.relation != "same_place" or edge.decision_status != "checked_rule_accepted":
            issue("decision_status", f"{aid}|{bid}", f"{edge.relation}|{edge.decision_status}")

    point_by_target = points.set_index("target_source_record_id", drop=False)
    if set(points.target_source_record_id) - endpoint_ids:
        issue("point_target_outside_edges", "", str(sorted(set(points.target_source_record_id) - endpoint_ids)[:3]))
    hashes = {}
    for path_text, group in points.groupby("coordinate_origin_ledger"):
        path = Path(path_text)
        if not path.exists():
            for sid in group.target_source_record_id: issue("missing_origin_ledger", sid, path_text)
            continue
        hashes[path_text] = digest(path)
        for row in group.itertuples(index=False):
            if row.coordinate_origin_ledger_sha256 != hashes[path_text]:
                issue("origin_hash", row.target_source_record_id, path_text)
            if row.coordinate_origin_ledger_locator != "target_source_record_id=" + row.coordinate_source_record_id:
                issue("origin_locator", row.target_source_record_id, row.coordinate_origin_ledger_locator)
    donor_ids = sorted(set(points.coordinate_source_record_id))
    baseline = Path("/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_point_uses.parquet")
    baseline_rows = c.execute(
        "SELECT target_source_record_id,latitude,longitude,coordinate_admission_status FROM read_parquet(?) "
        "WHERE target_source_record_id IN (SELECT UNNEST(?))",
        [str(baseline), donor_ids],
    ).fetchdf()
    origin_rows = {str(sid): list(gr.to_dict("records")) for sid, gr in baseline_rows.groupby("target_source_record_id")}
    compressed = Path("/workspace/russian-settlements-research/research_rebuild/evidence/current_residual_ownlocality_points_20261005/accepted_point_use_delta.csv.gz")
    compressed_rows = pd.read_csv(compressed, dtype=str)
    for sid, gr in compressed_rows[compressed_rows.target_source_record_id.isin(donor_ids)].groupby("target_source_record_id"):
        origin_rows.setdefault(str(sid), []).extend(gr.to_dict("records"))
    for row in points.itertuples(index=False):
        sid, donor = row.target_source_record_id, row.coordinate_source_record_id
        if sid not in state.by_id.index or int(row.target_year) != int(state.by_id.loc[sid, "census_year"]):
            issue("point_target_year", sid, row.target_year)
        if donor not in state.point_rows:
            issue("donor_not_accepted", sid, donor); continue
        prior = state.point_rows[donor]
        if (float(row.latitude), float(row.longitude)) != (prior["latitude"], prior["longitude"]):
            issue("donor_coordinate", sid, donor)
        candidates = origin_rows.get(donor, [])
        if not any(x["coordinate_admission_status"] in ACCEPTED_COORDINATE_STATUSES and distance_km((float(row.latitude), float(row.longitude)), (float(x["latitude"]), float(x["longitude"]))) < 0.000001 for x in candidates):
            issue("origin_row_coordinate", sid, donor)
        if row.coordinate_admission_status != "reviewed_extension_rule_accepted" or row.direct_historical_coordinate_measurement != "False" or row.native_code_binding_asserted != "False":
            issue("point_status_or_claim", sid, row.coordinate_admission_status)

    # Replay in output order, including new points, to check collisions and
    # both-point distances against the complete predecessor state.
    occupied = Counter((int(state.by_id.loc[sid, "census_year"]), p["latitude"], p["longitude"]) for sid, p in state.point_rows.items())
    graph_unions = 0
    for edge in edges.itertuples(index=False):
        aid, bid = edge.from_source_record_id, edge.to_source_record_id
        ap, bp = state.point_rows.get(aid), state.point_rows.get(bid)
        if ap is None and bp is None: issue("no_accepted_donor", f"{aid}|{bid}", "both unpointed")
        if ap is not None and bp is not None:
            km = distance_km((ap["latitude"], ap["longitude"]), (bp["latitude"], bp["longitude"]))
            if km > 5 or abs(km - float(edge.distance_km_if_both_points)) > 1e-6:
                issue("both_point_distance", f"{aid}|{bid}", str(km))
        donor = bp if bp is not None else ap
        if donor is not None:
            for sid in (aid, bid):
                candidate = state.by_id.loc[sid]
                lat, lon = candidate.latitude, candidate.longitude
                if pd.notna(lat) and pd.notna(lon) and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180 and (float(lat), float(lon)) != (0, 0):
                    km = distance_km((float(lat), float(lon)), (donor["latitude"], donor["longitude"]))
                    if km > 5:
                        issue("selected_coordinate_candidate_conflict", sid, str(km))
        for sid, point in ((aid, ap), (bid, bp)):
            if point is not None and occupied[(int(state.by_id.loc[sid, "census_year"]), point["latitude"], point["longitude"])] > 1:
                issue("existing_point_collision", sid, "shared same-year coordinate")
        if state.years[state.uf.find(aid)] & state.years[state.uf.find(bid)]:
            issue("graph_year_collision", f"{aid}|{bid}", "same year in components")
        else:
            graph_unions += int(state.union(aid, bid))
        new_targets = [sid for sid in (aid, bid) if sid in point_by_target.index]
        if len(new_targets) != 1:
            issue("new_point_count_per_edge", f"{aid}|{bid}", str(new_targets))
        for sid in new_targets:
            point = point_by_target.loc[sid]
            lat, lon = float(point.latitude), float(point.longitude)
            year = int(state.by_id.loc[sid, "census_year"])
            if occupied[(year, lat, lon)] != 0:
                issue("new_point_collision", sid, f"{year}|{lat}|{lon}")
            occupied[(year, lat, lon)] += 1
            state.point_rows[sid] = {"latitude": lat, "longitude": lon}
    if graph_unions != len(edges):
        issue("union_count", "", f"{graph_unions}/{len(edges)}")

    # Raw 2021 publisher rows: this verifies district_raw is mun_upper,
    # census grain is a locality, and row IDs point to the stated source cells.
    current = selected_extra.loc[list(endpoint_ids)].copy()
    current["census_year"] = current.index.map(lambda sid: int(state.by_id.loc[sid, "census_year"]))
    current = current[current.census_year.eq(2021)].copy()
    current["rn"] = current.source_row.astype(int)
    raw_current = c.execute(
        "SELECT rn,object_level,settlement,mun_upper,population,oktmo FROM "
        "(SELECT row_number() OVER () rn,object_level,settlement,mun_upper,population,oktmo FROM read_parquet(?)) "
        "WHERE rn IN (SELECT UNNEST(?))",
        [str(RAW_2021), current.rn.tolist()],
    ).fetchdf().set_index("rn")
    for sid, r in current.iterrows():
        raw = raw_current.loc[int(r.rn)]
        if raw.object_level != "Населенный пункт" or raw.settlement != r.source_name_raw or raw.mun_upper != r.district_raw or int(raw.population) != int(r.population) or str(raw.oktmo) != str(r.oktmo):
            issue("raw_2021_row", sid, f"{raw.object_level}|{raw.settlement}|{raw.mun_upper}|{raw.population}|{raw.oktmo}")
    c.close()

    sample_indices = sorted(random.Random(20261007).sample(range(len(edges)), 40))
    maxpop = [max(float(state.by_id.loc[a, "population"]), float(state.by_id.loc[b, "population"])) for a, b in edges[["from_source_record_id", "to_source_record_id"]].itertuples(index=False, name=None)]
    top_indices = sorted(range(len(edges)), key=lambda i: (-maxpop[i], i))[:10]
    inspect_indices = set(sample_indices) | set(top_indices)
    source_rows = selected_extra.loc[list(endpoint_ids)].copy()
    source_rows["census_year"] = source_rows.index.map(lambda sid: int(state.by_id.loc[sid, "census_year"]))
    source_rows = source_rows[source_rows.census_year.lt(2021)]
    snippets = {}
    raw_workbook_sha256 = {}
    raw_county_witnesses = 0
    for (source_file, sheet), group in source_rows.groupby(["source_file", "source_sheet"]):
        path = RAW / source_file
        if not path.exists():
            for sid in group.index: issue("missing_raw_workbook", sid, str(path))
            continue
        raw_workbook_sha256[str(path)] = digest(path)
        book = pd.read_excel(path, sheet_name=sheet, header=None)
        for sid, r in group.iterrows():
            rn = int(r.source_row)
            if rn < 1 or rn > len(book):
                issue("raw_workbook_row_outside", sid, f"{path}|{sheet}|{rn}"); continue
            line = raw_row_text(book, rn)
            expected = normalize(r.source_name_raw)
            if expected not in normalize(line):
                issue("raw_workbook_name", sid, f"{path}|{sheet}|{rn}|{line[:150]}")
            snippets[sid] = f"{path}#{sheet}:row_1based={rn} | {line[:200]}"
            key = county_key(r.district_raw)
            witness_row, witness = county_witness(book, rn, key)
            if witness_row:
                raw_county_witnesses += 1
            else:
                issue("raw_county_witness_missing", sid, f"{path}|{sheet}|{rn}|{r.district_raw}")
            if sid in {x for i in inspect_indices for x in (edges.iloc[i].from_source_record_id, edges.iloc[i].to_source_record_id)}:
                snippets[sid] += f" | county_witness_row={witness_row} {witness[:110]}"

    def inspect_row(index: int, kind: str) -> dict:
        e = edges.iloc[index]
        a, b = e.from_source_record_id, e.to_source_record_id
        return {
            "set": kind, "csv_row_1based": index + 2,
            "from_source_record_id": a, "to_source_record_id": b,
            "from_name": str(state.by_id.loc[a, "settlement_name"]), "to_name": str(state.by_id.loc[b, "settlement_name"]),
            "from_population": state.by_id.loc[a, "population"], "to_population": state.by_id.loc[b, "population"],
            "name_norm": e.name_norm, "type_norm": e.type_norm, "region_norm": e.region_norm,
            "from_district_raw": e.from_district_raw, "to_district_raw": e.to_district_raw, "county_key": e.county_key,
            "from_source_row": snippets.get(a, f"{RAW_2021}#parquet_row_1based={int(selected_extra.loc[a,'source_row'])}"),
            "to_source_row": snippets.get(b, f"{RAW_2021}#parquet_row_1based={int(selected_extra.loc[b,'source_row'])}"),
            "from_point_before": a not in set(points.target_source_record_id),
            "to_point_before": b not in set(points.target_source_record_id),
            "population_ratio_max_over_min": e.population_ratio_max_over_min,
            "review_note": "",
        }
    pd.DataFrame([inspect_row(i, "seeded_random_40") for i in sample_indices]).to_csv(OUT / "sample40.csv", index=False)
    pd.DataFrame([inspect_row(i, "top_population_10_not_representative") for i in top_indices]).to_csv(OUT / "top10_population_risk.csv", index=False)
    pd.DataFrame(issues, columns=["kind", "source_record_id", "detail"]).to_csv(OUT / "issues.csv", index=False)
    summary = {
        "status": "independent_county_rule_audit", "seed": 20261007,
        "edges": len(edges), "new_points": len(points), "distinct_selected_endpoints": len(endpoint_ids),
        "both_accepted_point_pairs": int(edges.distance_km_if_both_points.ne("").sum()),
        "new_targets_with_selected_coordinate_candidates": int(sum(pd.notna(state.by_id.loc[sid, "latitude"]) and pd.notna(state.by_id.loc[sid, "longitude"]) for sid in points.target_source_record_id)),
        "population_ratio_gt2": int((pd.to_numeric(edges.population_ratio_max_over_min, errors="coerce") > 2).sum()),
        "population_ratio_undefined": int(edges.population_ratio_max_over_min.eq("").sum()),
        "special_entity_grain_flags": [
            {"source_record_id": sid, "entity_grain_status": str(row.entity_grain_status)}
            for sid, row in selected_extra.iterrows() if pd.notna(row.entity_grain_status)
        ],
        "sample40_csv_data_rows_1based": [i + 2 for i in sample_indices],
        "top10_csv_data_rows_1based": [i + 2 for i in top_indices],
        "top10_is_representative": False,
        "raw_2021_rows_rechecked": len(current), "raw_2002_2010_rows_rechecked": len(source_rows),
        "historical_raw_county_witnesses_found": raw_county_witnesses,
        "raw_source_sha256": {**raw_workbook_sha256, str(RAW_2021): digest(RAW_2021)},
        "new_component_unions_replayed": graph_unions,
        "origin_ledger_sha256": hashes,
        "origin_ledger_use_counts": points.coordinate_origin_ledger.value_counts().to_dict(),
        "issue_counts": dict(Counter(x["kind"] for x in issues)),
        "input_sha256": {str(edge_file): digest(edge_file), str(point_file): digest(point_file), str(SELECTED): digest(SELECTED)},
        "receipt_outputs_match": all(receipt["outputs"][p.name] == digest(p) for p in (edge_file, point_file)),
    }
    (OUT / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("edges", "distinct_selected_endpoints", "new_component_unions_replayed", "raw_2021_rows_rechecked", "raw_2002_2010_rows_rechecked", "issue_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
