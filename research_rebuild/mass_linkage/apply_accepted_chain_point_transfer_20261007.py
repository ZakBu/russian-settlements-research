"""Reuse accepted locality points on already accepted, stable temporal identities."""
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from current_chain_state_20261007 import State, distance_km, normalize, sha

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research_rebuild/evidence/accepted_chain_point_transfer_20261007"


def main():
    state = State()
    baseline = state.metrics()
    eligible_roots = {state.uf.find(sid) for sid in state.obs.source_record_id if sid not in state.point_rows and len(state.years[state.uf.find(sid)]) > 1}
    rows, holds = [], []
    ledger_hashes = {}
    for root, group in state.obs[state.obs.root.isin(eligible_roots)].groupby("root", sort=True):
        anchors = [r for sid in group.source_record_id if (r := state.point_rows.get(sid)) is not None]
        if not anchors:
            continue
        anchors.sort(key=lambda r: (-int(state.by_id.loc[r["target_source_record_id"], "census_year"]), r["target_source_record_id"]))
        origin = anchors[0]
        anchor_id = origin["target_source_record_id"]
        source = state.by_id.loc[anchor_id]
        point = origin["latitude"], origin["longitude"]
        spread = max(distance_km(point, (r["latitude"], r["longitude"])) for r in anchors)
        for target in group.to_dict("records"):
            sid = target["source_record_id"]
            if sid in state.point_rows:
                continue
            reasons = []
            if any(r["target_source_record_id"] in state.conflicting_point_targets for r in anchors):
                reasons.append("accepted_target_has_conflicting_coordinate_alternatives")
            if not target["is_additive_settlement_record"]:
                reasons.append("not_additive_settlement")
            if target["population_scope"] not in (None, "settlement") and not pd.isna(target["population_scope"]):
                reasons.append("non_settlement_population_scope")
            if "(часть" in normalize(target["settlement_name"]):
                reasons.append("partition_requires_whole_projection")
            if any(normalize(target[k]) != normalize(source[k]) for k in ("settlement_name", "settlement_type", "region_norm")):
                reasons.append("name_type_region_change")
            if spread > 5:
                reasons.append("accepted_component_points_disagree_over_5km")
            if pd.notna(target["latitude"]) and pd.notna(target["longitude"]):
                candidate = float(target["latitude"]), float(target["longitude"])
                if -90 <= candidate[0] <= 90 and -180 <= candidate[1] <= 180 and candidate != (0, 0) and distance_km(candidate, point) > 5:
                    reasons.append("existing_coordinate_candidate_disagrees_over_5km")
            if reasons:
                holds.append({"source_record_id": sid, "year": target["census_year"], "population": target["population"], "reason": ";".join(reasons)})
                continue
            ledger = Path(origin["point_ledger_path"])
            ledger_hashes.setdefault(str(ledger), sha(ledger))
            rows.append({
                "target_source_record_id": sid, "target_year": int(target["census_year"]),
                "settlement_name": target["settlement_name"], "region_norm": target["region_norm"],
                "population": int(target["population"]) if pd.notna(target["population"]) else None,
                "latitude": point[0], "longitude": point[1],
                "coordinate_admission_status": "reviewed_extension_rule_accepted",
                "admission_rule": "already_accepted_same_place_identical_name_type_region_point_continuity_v1",
                "coordinate_quality": "representative_point_inherited_over_accepted_identity",
                "coordinate_source": "accepted point of another selected census record in the same accepted physical identity",
                "coordinate_source_record_id": anchor_id,
                "coordinate_origin_ledger": str(ledger), "coordinate_origin_ledger_sha256": ledger_hashes[str(ledger)],
                "coordinate_origin_ledger_locator": "target_source_record_id=" + anchor_id,
                "coordinate_origin_evidence_json": json.dumps({k: v for k, v in origin.items() if k.startswith("point_origin_") or k in ("source_sha256", "source_locator", "coordinate_provenance")}, ensure_ascii=False, default=str),
                "identity_component_root": root,
                "coordinate_measurement_date_unknown": True,
                "application_inference_kind": "spatial_continuity_over_previously_accepted_temporal_identity",
                "direct_historical_coordinate_measurement": False,
                "native_code_binding_asserted": False,
                "boundary_comparability_asserted": False,
                "population_values_modified": False,
            })
    OUT.mkdir(parents=True, exist_ok=True)
    delta = pd.DataFrame(rows)
    delta.to_csv(OUT / "accepted_point_use_delta.csv", index=False)
    pd.DataFrame(holds, columns=["source_record_id", "year", "population", "reason"]).to_csv(OUT / "held_targets.csv", index=False)
    after = state.metrics(extra_point_ids=[r["target_source_record_id"] for r in rows])
    receipt = {
        "status": "applied_accepted_identity_point_continuity_rule", "new_identity_edges": 0,
        "point_uses_added": len(rows), "point_targets_unique": len({r["target_source_record_id"] for r in rows}) == len(rows),
        "by_year": {str(y): {"point_uses_added": len(g), "population_point_uses_added": int(g.population.sum())} for y, g in delta.groupby("target_year")},
        "ordinary_three_census_baseline": baseline, "ordinary_three_census_after": after,
        "full_chain_population_gain": {y: after[y]["covered_population"]-baseline[y]["covered_population"] for y in baseline},
        "hold_reasons": dict(Counter(r["reason"] for r in holds)),
        "inputs": {str(p): sha(p) for p in state.inputs},
        "source_population_values_modified": False, "native_code_binding_asserted": False,
        "limitations": ["No new identity claim is made: the same_place graph was already accepted.", "A representative point is reused as spatial continuity, not a historical point measurement.", "Numbered parts, changes of name/type/region, inconsistent accepted points and conflicting old coordinate candidates are held.", "Source population quality and boundary comparability remain separate from coordinates."],
    }
    receipt["outputs"] = {p.name: sha(p) for p in OUT.glob("*.csv")}
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    (OUT / "README.md").write_text("# Перенос точки по уже принятой временной идентичности\n\nПакет добавляет точки к исходным переписным записям уже принятого графа. Требует неизменных названия, типа и региона, согласия принятых точек в пределах 5 км, отсутствия конфликта с прежним координатным кандидатом. Это вывод о пространственной преемственности. Коды внешнего поставщика не присваиваются новой исходной записи. Численность, идентичность и сопоставимость границ не меняются. Полные трёхлетние цепочки пересчитаны отдельно от двухлетних.\n")
    print(json.dumps({k:receipt[k] for k in ("point_uses_added", "by_year", "full_chain_population_gain", "ordinary_three_census_after")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
