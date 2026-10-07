"""Apply source-reviewed large-locality links and explicit representative-point reuse."""
import json
from pathlib import Path

import pandas as pd

from build_long_table import ACCEPTED_EDGE_STATUSES
from current_chain_state_20261007 import State, distance_km, sha

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/large_missing_year_application_20261007"
REVIEW = ROOT / "research_rebuild/evidence/large_missing_year_batch_20261007"


def main():
    state = State()
    baseline = state.metrics()
    edges = pd.read_csv(REVIEW / "accepted_identity_edge_delta.csv", keep_default_na=False)
    affected = set()
    source_hashes = {}
    for row in edges.to_dict("records"):
        if row["decision_status"] not in ACCEPTED_EDGE_STATUSES or row["relation"] != "same_place":
            raise ValueError("Unsupported identity decision status")
        for side in ("from", "to"):
            sid = row[side+"_source_record_id"]
            obs = state.by_id.loc[sid]
            if int(obs.census_year) != int(row[side+"_year"]) or int(obs.population) != int(row[side+"_population"]):
                raise ValueError("Reviewed endpoint year/population differs")
            if pd.notna(obs.source_sha256):
                if str(obs.source_sha256) != row[side+"_source_sha256"]:
                    raise ValueError("Reviewed source hash differs")
            else:
                source_path = Path("/workspace/settlements-raw") / str(obs.source_file)
                if not source_path.is_file():
                    raise ValueError("Missing source without a selected hash: " + str(source_path))
                source_hashes.setdefault(str(source_path), sha(source_path))
                if source_hashes[str(source_path)] != row[side+"_source_sha256"]:
                    raise ValueError("Actual reviewed source hash differs")
            if not obs.is_additive_settlement_record:
                raise ValueError("Reviewed endpoint is not an additive settlement")
            affected.add(sid)
        state.union(row["from_source_record_id"], row["to_source_record_id"])
    affected_roots = {state.uf.find(sid) for sid in affected}
    state.obs["root"] = state.obs.source_record_id.map(state.uf.find)
    points, holds = [], []
    ledger_hashes = {}
    for root, group in state.obs[state.obs.root.isin(affected_roots)].groupby("root", sort=True):
        anchors = [state.point_rows[sid] for sid in group.source_record_id if sid in state.point_rows]
        if not anchors:
            holds.extend({"source_record_id": sid, "reason": "no_accepted_point_in_reviewed_component"} for sid in group.source_record_id)
            continue
        anchors.sort(key=lambda p: -int(state.by_id.loc[p["target_source_record_id"], "census_year"]))
        anchor = anchors[0]
        coordinate = anchor["latitude"], anchor["longitude"]
        if any(p["target_source_record_id"] in state.conflicting_point_targets or distance_km(coordinate, (p["latitude"], p["longitude"])) > 5 for p in anchors):
            holds.extend({"source_record_id": sid, "reason": "inconsistent_component_points"} for sid in group.source_record_id if sid not in state.point_rows)
            continue
        ledger = Path(anchor["point_ledger_path"])
        ledger_hashes.setdefault(str(ledger), sha(ledger))
        for obs in group.itertuples(index=False):
            if obs.source_record_id in state.point_rows:
                continue
            if pd.notna(obs.latitude) and pd.notna(obs.longitude) and -90 <= float(obs.latitude) <= 90 and -180 <= float(obs.longitude) <= 180 and (float(obs.latitude), float(obs.longitude)) != (0, 0):
                if distance_km((float(obs.latitude), float(obs.longitude)), coordinate) > 5:
                    holds.append({"source_record_id": obs.source_record_id, "reason": "old_coordinate_candidate_conflict"})
                    continue
            points.append({"target_source_record_id": obs.source_record_id, "target_year": int(obs.census_year), "latitude": coordinate[0], "longitude": coordinate[1], "coordinate_admission_status": "reviewed_case_accepted", "coordinate_source_record_id": anchor["target_source_record_id"], "coordinate_origin_ledger": str(ledger), "coordinate_origin_ledger_sha256": ledger_hashes[str(ledger)], "coordinate_origin_ledger_locator": "target_source_record_id=" + anchor["target_source_record_id"], "admission_rule": "representative_point_continuity_over_source_reviewed_large_locality_identity", "direct_historical_coordinate_measurement": False, "native_code_binding_asserted": False, "boundary_comparability_asserted": False})
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(points).to_csv(OUT / "accepted_point_use_delta.csv", index=False)
    pd.DataFrame(holds, columns=["source_record_id", "reason"]).to_csv(OUT / "held_point_targets.csv", index=False)
    after = state.metrics(extra_point_ids=[r["target_source_record_id"] for r in points])
    receipt = {"status": "applied_source_reviewed_large_locality_identity_batch", "identity_edges_applied": len(edges), "reviewed_components": len(affected_roots), "point_uses_added": len(points), "baseline": baseline, "after": after,
        "full_chain_population_gain": {y: after[y]["covered_population"]-baseline[y]["covered_population"] for y in baseline},
        "source_population_values_modified": False, "population_boundary_comparability_asserted": False,
        "inputs": {str(p): sha(p) for p in state.inputs + list(REVIEW.iterdir()) if p.is_file()}, "outputs": {p.name: sha(p) for p in OUT.glob("*.csv")}}
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    (OUT / "README.md").write_text("# Применение крупного пакета межгодовых связей\n\nПрименены связи из соседнего source-reviewed пакета с проверкой каждого выбранного исходного ID, года, численности, SHA и отсутствия повторного года в компоненте. Точки целого НП перенесены по принятой идентичности, варианты названий подтверждены в исходном разборе. Исходные числа, включая защищённые 2010, не изменены; расхождения с официальными альтернативами сохранены в рецензии. Нет утверждения об неизменных границах.\n")
    print(json.dumps({k: receipt[k] for k in ("identity_edges_applied", "point_uses_added", "full_chain_population_gain", "after")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
