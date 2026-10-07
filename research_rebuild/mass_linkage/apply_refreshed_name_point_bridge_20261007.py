"""Apply the existing unique-name/region rule using all current accepted points."""
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from current_chain_state_20261007 import State, distance_km, normalize, sha

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/refreshed_name_point_bridge_20261007"
TRANSFER = ROOT / "research_rebuild/evidence/accepted_chain_point_transfer_20261007/accepted_point_use_delta.csv"


def main():
    state = State()
    for row in pd.read_csv(TRANSFER, keep_default_na=False).to_dict("records"):
        row["point_ledger_path"] = str(TRANSFER)
        state.point_rows[row["target_source_record_id"]] = row
    state.inputs.append(TRANSFER)
    baseline = state.metrics()
    obs = state.obs[state.obs.is_additive_settlement_record.fillna(False)].copy()
    obs["n"] = obs.name_norm.map(normalize)
    obs["r"] = obs.region_norm.map(normalize)
    obs = obs[obs.n.ne("") & obs.r.ne("") & ~obs.settlement_name.fillna("").str.contains(r"\(часть", regex=True)]
    obs["unique"] = obs.groupby(["census_year", "n", "r"]).source_record_id.transform("size").eq(1)
    unique = obs[obs.unique]
    point_collisions = Counter((int(state.by_id.loc[sid, "census_year"]), p["latitude"], p["longitude"]) for sid, p in state.point_rows.items())
    edges, points, holds, outcomes = [], [], [], Counter()
    for ya, yb in ((2002, 2010), (2010, 2021), (2002, 2021)):
        a = unique[unique.census_year.eq(ya)]
        b = unique[unique.census_year.eq(yb)]
        pairs = a.merge(b, on=["n", "r"], suffixes=("_a", "_b"))
        pairs = pairs.sort_values(["population_a", "population_b"], ascending=False)
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
            if normalize(row["type_norm_a"]) != normalize(row["type_norm_b"]):
                reasons.append("type_change")
            if state.years[ra] & state.years[rb]:
                reasons.append("same_year_graph_collision")
            if aid in state.conflicting_point_targets or bid in state.conflicting_point_targets:
                reasons.append("conflicting_accepted_point_alternatives")
            for sid, p, year in ((aid, ap, ya), (bid, bp, yb)):
                if p is not None and point_collisions[(year, p["latitude"], p["longitude"])] > 1:
                    reasons.append("same_year_shared_coordinate")
            distance = None
            if ap is not None and bp is not None:
                distance = distance_km((ap["latitude"], ap["longitude"]), (bp["latitude"], bp["longitude"]))
                if distance > 5:
                    reasons.append("points_over_5km")
            donor, recipient = (ap, bid) if ap is not None else (bp, aid)
            old = state.by_id.loc[recipient]
            if pd.notna(old.latitude) and pd.notna(old.longitude) and -90 <= float(old.latitude) <= 90 and -180 <= float(old.longitude) <= 180 and (float(old.latitude), float(old.longitude)) != (0, 0):
                if distance_km((float(old.latitude), float(old.longitude)), (donor["latitude"], donor["longitude"])) > 5:
                    reasons.append("old_coordinate_candidate_conflict")
            if reasons:
                holds.append({"from_source_record_id": aid, "to_source_record_id": bid, "reason": ";".join(sorted(set(reasons)))})
                outcomes["held"] += 1
                continue
            state.union(aid, bid)
            outcomes["new_edge"] += 1
            pa, pb = row["population_a"], row["population_b"]
            ratio = max(pa, pb)/min(pa, pb) if pd.notna(pa) and pd.notna(pb) and min(pa, pb) > 0 else None
            edges.append({"from_source_record_id": aid, "from_year": ya, "to_source_record_id": bid, "to_year": yb, "relation": "same_place", "decision_status": "checked_rule_accepted", "name_norm": row["n"], "region_norm": row["r"], "distance_km_if_both_points": distance, "population_ratio_max_over_min": ratio, "population_comparability": "unknown_outlier_scope_review" if ratio is not None and ratio > 2 else "not_asserted", "admission_rule": "existing_unique_exact_name_region_rule_refreshed_all_accepted_points_same_type_v1"})
            if recipient not in state.point_rows:
                ledger = Path(donor["point_ledger_path"])
                point = {"target_source_record_id": recipient, "target_year": int(old.census_year), "latitude": donor["latitude"], "longitude": donor["longitude"], "coordinate_admission_status": "reviewed_extension_rule_accepted", "coordinate_source_record_id": donor["target_source_record_id"], "coordinate_origin_ledger": str(ledger), "coordinate_origin_ledger_sha256": sha(ledger) if ledger.exists() else "", "coordinate_origin_ledger_locator": "target_source_record_id=" + donor["target_source_record_id"], "admission_rule": "spatial_continuity_over_refreshed_unique_name_region_identity", "direct_historical_coordinate_measurement": False, "native_code_binding_asserted": False, "boundary_comparability_asserted": False, "point_ledger_path": str(OUT / "accepted_point_use_delta.csv")}
                # All new points retain a donor from an input ledger rather than
                # creating circular references to the batch being written.
                if ledger == OUT / "accepted_point_use_delta.csv":
                    point["coordinate_origin_ledger"] = donor["coordinate_origin_ledger"]
                    point["coordinate_origin_ledger_sha256"] = donor["coordinate_origin_ledger_sha256"]
                    point["coordinate_origin_ledger_locator"] = donor["coordinate_origin_ledger_locator"]
                state.point_rows[recipient] = point
                point_collisions[(int(old.census_year), point["latitude"], point["longitude"])] += 1
                points.append(point)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(edges, columns=["from_source_record_id", "from_year", "to_source_record_id", "to_year", "relation", "decision_status", "name_norm", "region_norm", "distance_km_if_both_points", "population_ratio_max_over_min", "population_comparability", "admission_rule"]).to_csv(OUT / "accepted_identity_edge_delta.csv", index=False)
    pd.DataFrame(points, columns=["target_source_record_id", "target_year", "latitude", "longitude", "coordinate_admission_status", "coordinate_source_record_id", "coordinate_origin_ledger", "coordinate_origin_ledger_sha256", "coordinate_origin_ledger_locator", "admission_rule", "direct_historical_coordinate_measurement", "native_code_binding_asserted", "boundary_comparability_asserted", "point_ledger_path"]).to_csv(OUT / "accepted_point_use_delta.csv", index=False)
    pd.DataFrame(holds, columns=["from_source_record_id", "to_source_record_id", "reason"]).to_csv(OUT / "held_pairs.csv", index=False)
    after = state.metrics()
    receipt = {"status": "applied_existing_unique_name_region_rule_on_refreshed_point_inventory", "outcomes": dict(outcomes), "new_edges": len(edges), "new_point_uses": len(points), "baseline": baseline, "after": after, "full_chain_population_gain": {y: after[y]["covered_population"]-baseline[y]["covered_population"] for y in baseline}, "inputs": {str(p): sha(p) for p in state.inputs}, "source_population_values_modified": False, "boundary_comparability_asserted": False, "outputs": {p.name: sha(p) for p in OUT.glob("*.csv")}}
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    (OUT / "README.md").write_text("# Повторное применение массового правила к новым принятым точкам\n\nИспользовано существующее правило уникального нормализованного имени и региона с дополнительным требованием одинакового типа. Учтены все принятые дельты точек, которые предыдущий SQL-запрос не включал. Для двух точек расстояние не превышает 5 км. Удерживаются конкурирующий год в графе, общие координаты разных объектов и конфликтующие старые координатные кандидаты. Популяционные выбросы отмечаются отдельно, исходные числа не изменяются.\n")
    print(json.dumps({k: receipt[k] for k in ("new_edges", "new_point_uses", "full_chain_population_gain", "after")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
