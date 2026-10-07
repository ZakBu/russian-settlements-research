"""Resolve regional homonyms using explicit source county names and accepted points."""
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from current_chain_state_20261007 import State, normalize, distance_km, sha

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / "research_rebuild/evidence"
OUT = E / "unique_county_name_bridge_20261007"
EXTRA_EDGES = [E / "refreshed_name_point_bridge_20261007/accepted_identity_edge_delta.csv", E / "large_missing_year_batch_20261007/accepted_identity_edge_delta.csv"]
EXTRA_POINTS = [E / "accepted_chain_point_transfer_20261007/accepted_point_use_delta.csv", E / "refreshed_name_point_bridge_20261007/accepted_point_use_delta.csv", E / "large_missing_year_application_20261007/accepted_point_use_delta.csv"]


def county_key(value):
    text = normalize(value)
    text = re.sub(r"\b(муниципальн(?:ый|ого|ое|ая)|городск(?:ой|ого|ое)|район(?:а)?|округ(?:а)?|город(?:а)?|р\s*н)\b", " ", text)
    return " ".join(re.sub(r"[^а-яa-z0-9]+", " ", text).split())


def main():
    state = State()
    state.add_deltas(EXTRA_EDGES, EXTRA_POINTS)
    baseline = state.metrics()
    obs = state.obs[state.obs.is_additive_settlement_record.fillna(False) & ~state.obs.region_norm.isin(["москва", "санкт петербург", "севастополь"])].copy()
    obs = obs[~obs.settlement_name.fillna("").str.contains(r"\(часть", regex=True)]
    obs["n"] = obs.name_norm.map(normalize)
    obs["t"] = obs.type_norm.map(normalize)
    obs["r"] = obs.region_norm.map(normalize)
    obs["d"] = obs.district_raw.map(county_key)
    obs = obs[obs.n.ne("") & obs.t.ne("") & obs.d.str.len().ge(3)]
    obs["unique"] = obs.groupby(["census_year", "n", "t", "r", "d"]).source_record_id.transform("size").eq(1)
    unique = obs[obs.unique]
    edges, points, holds = [], [], []
    outcomes = Counter()
    collision_counts = Counter((int(state.by_id.loc[sid, "census_year"]), p["latitude"], p["longitude"]) for sid, p in state.point_rows.items())
    ledger_hashes = {}
    for ya, yb in ((2002, 2010), (2010, 2021), (2002, 2021)):
        pairs = unique[unique.census_year.eq(ya)].merge(unique[unique.census_year.eq(yb)], on=["n", "t", "r", "d"], suffixes=("_a", "_b")).sort_values(["population_a", "population_b"], ascending=False)
        for row in pairs.to_dict("records"):
            aid, bid = row["source_record_id_a"], row["source_record_id_b"]
            ra, rb = state.uf.find(aid), state.uf.find(bid)
            if ra == rb:
                outcomes["already_connected"] += 1
                continue
            ap, bp = state.point_rows.get(aid), state.point_rows.get(bid)
            if ap is None and bp is None:
                outcomes["no_accepted_point"] += 1
                continue
            reasons = []
            if state.years[ra] & state.years[rb]:
                reasons.append("same_year_graph_conflict")
            if aid in state.conflicting_point_targets or bid in state.conflicting_point_targets:
                reasons.append("accepted_point_alternatives_conflict")
            distance = None
            if ap is not None and bp is not None:
                distance = distance_km((ap["latitude"], ap["longitude"]), (bp["latitude"], bp["longitude"]))
                if distance > 5:
                    reasons.append("accepted_points_over_5km")
            for sid, p, yr in ((aid, ap, ya), (bid, bp, yb)):
                if p is not None and collision_counts[(yr, p["latitude"], p["longitude"])] > 1:
                    reasons.append("point_shared_by_other_same_year_record")
            donor = bp if bp is not None else ap
            for side in ("a", "b"):
                lat, lon = row["latitude_"+side], row["longitude_"+side]
                if pd.notna(lat) and pd.notna(lon) and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180 and (float(lat), float(lon)) != (0, 0):
                    if distance_km((float(lat), float(lon)), (donor["latitude"], donor["longitude"])) > 5:
                        reasons.append("existing_coordinate_candidate_conflict")
            if reasons:
                holds.append({"from_source_record_id": aid, "to_source_record_id": bid, "name_norm": row["n"], "county_key": row["d"], "reason": ";".join(sorted(set(reasons)))})
                outcomes["held"] += 1
                continue
            state.union(aid, bid)
            outcomes["accepted_new_edge"] += 1
            pa, pb = row["population_a"], row["population_b"]
            ratio = max(pa, pb)/min(pa, pb) if pd.notna(pa) and pd.notna(pb) and min(pa, pb) > 0 else None
            edges.append({"from_source_record_id": aid, "from_year": ya, "to_source_record_id": bid, "to_year": yb, "relation": "same_place", "decision_status": "checked_rule_accepted", "name_norm": row["n"], "type_norm": row["t"], "region_norm": row["r"], "county_key": row["d"], "from_district_raw": row["district_raw_a"], "to_district_raw": row["district_raw_b"], "distance_km_if_both_points": distance, "population_ratio_max_over_min": ratio, "population_comparability": "not_asserted_outlier_scope_review" if ratio is not None and ratio > 2 else "not_asserted", "admission_rule": "unique_exact_name_type_region_explicit_county_with_accepted_point_v1"})
            ledger = Path(donor["point_ledger_path"])
            if ledger != OUT / "accepted_point_use_delta.csv":
                if str(ledger) not in ledger_hashes:
                    ledger_hashes[str(ledger)] = sha(ledger)
                origin_path, origin_sha, origin_locator = str(ledger), ledger_hashes[str(ledger)], "target_source_record_id="+donor["target_source_record_id"]
            else:
                origin_path, origin_sha, origin_locator = donor["coordinate_origin_ledger"], donor["coordinate_origin_ledger_sha256"], donor["coordinate_origin_ledger_locator"]
            for sid in (aid, bid):
                if sid in state.point_rows:
                    continue
                point = {"target_source_record_id": sid, "target_year": int(state.by_id.loc[sid,"census_year"]), "latitude": donor["latitude"], "longitude": donor["longitude"], "coordinate_source_record_id": donor["target_source_record_id"], "coordinate_admission_status": "reviewed_extension_rule_accepted", "coordinate_origin_ledger": origin_path, "coordinate_origin_ledger_sha256": origin_sha, "coordinate_origin_ledger_locator": origin_locator, "admission_rule": "representative_point_continuity_over_accepted_county_name_identity", "direct_historical_coordinate_measurement": False, "native_code_binding_asserted": False, "boundary_comparability_asserted": False, "point_ledger_path": str(OUT / "accepted_point_use_delta.csv")}
                state.point_rows[sid] = point
                collision_counts[(point["target_year"], point["latitude"], point["longitude"])] += 1
                points.append(point)
    OUT.mkdir(parents=True, exist_ok=True)
    edge_cols = ["from_source_record_id", "from_year", "to_source_record_id", "to_year", "relation", "decision_status", "name_norm", "type_norm", "region_norm", "county_key", "from_district_raw", "to_district_raw", "distance_km_if_both_points", "population_ratio_max_over_min", "population_comparability", "admission_rule"]
    point_cols = ["target_source_record_id", "target_year", "latitude", "longitude", "coordinate_source_record_id", "coordinate_admission_status", "coordinate_origin_ledger", "coordinate_origin_ledger_sha256", "coordinate_origin_ledger_locator", "admission_rule", "direct_historical_coordinate_measurement", "native_code_binding_asserted", "boundary_comparability_asserted", "point_ledger_path"]
    pd.DataFrame(edges, columns=edge_cols).to_csv(OUT / "accepted_identity_edge_delta.csv", index=False)
    pd.DataFrame(points, columns=point_cols).to_csv(OUT / "accepted_point_use_delta.csv", index=False)
    pd.DataFrame(holds, columns=["from_source_record_id", "to_source_record_id", "name_norm", "county_key", "reason"]).to_csv(OUT / "held_pairs.csv", index=False)
    after = state.metrics()
    receipt = {"status": "applied_explicit_county_homonym_resolution_rule", "new_identity_edges": len(edges), "new_point_uses": len(points), "outcomes": dict(outcomes), "baseline": baseline, "after": after, "full_chain_population_gain": {y: after[y]["covered_population"]-baseline[y]["covered_population"] for y in baseline}, "inputs": {str(p): sha(p) for p in state.inputs}, "source_population_values_modified": False, "population_boundary_comparability_asserted": False, "outputs": {p.name: sha(p) for p in OUT.glob("*.csv")}}
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    (OUT / "README.md").write_text("# Омонимы: одинаковые имя, тип, регион и явный район\n\nПринятие требует одного исходного НП с этим ключом в каждом году. Район берётся из поля источника, не из догадки по населению или порядку строк. Нормализация убирает только обозначения административного уровня; изменение топонима района не скрывается. Есть принятая точка хотя бы одного конца. При двух точках расстояние до 5 км. Общие точки разных объектов, противоречащие кандидаты и повтор года в графе удерживаются. Перенос точки обозначен как пространственная преемственность, границы и численность не объявляются сопоставимыми.\n")
    print(json.dumps({k: receipt[k] for k in ("new_identity_edges", "new_point_uses", "full_chain_population_gain", "after")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
