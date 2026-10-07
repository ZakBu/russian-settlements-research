"""Apply bounded source-context inference to orphan 2010 whole-locality rows."""
import json
import argparse
from collections import Counter
from pathlib import Path

import pandas as pd
import xlrd

from current_chain_state_20261007 import normalize, distance_km, sha
from apply_unique_county_name_bridge_20261007 import county_key
from working_state_20261007 import load, E

REVIEW = E / "bracketed_2010_county_bridge_20261007"
OUT = E / "bracketed_2010_county_application_20261007"
RAW = Path("/workspace/settlements-raw")


def main(candidate_path=None, output_path=None, stage=1, recovery_path=None, allow_type_change=False):
    out = Path(output_path) if output_path else OUT
    state = load(stage=stage)
    before = state.metrics()
    candidate_path = Path(candidate_path) if candidate_path else REVIEW / "usable_contextual_link_candidates.csv"
    candidates = pd.read_csv(candidate_path, keep_default_na=False)
    recovery = pd.read_csv(recovery_path, keep_default_na=False).set_index("target_2010_source_record_id").to_dict("index") if recovery_path else {}
    if candidates.target_2010_source_record_id.duplicated().any():
        raise ValueError("Repeated candidate target")
    edges, points, holds, checks = [], [], [], []
    books, hashes = {}, {}
    for r in candidates.to_dict("records"):
        sid, old, cur = (r[k] for k in ("target_2010_source_record_id", "2002_endpoint_source_record_id", "2021_endpoint_source_record_id"))
        rows = [state.by_id.loc[x] for x in (sid, old, cur)]
        target, oldrow, currow = rows
        if [int(x.census_year) for x in rows] != [2010, 2002, 2021]:
            raise ValueError("Candidate endpoint year mismatch")
        for field in (("settlement_name", "region_norm") if allow_type_change else ("settlement_name", "settlement_type", "region_norm")):
            if len({normalize(x[field]) for x in rows}) != 1:
                raise ValueError("Candidate name/type/region mismatch")
        county = r["inferred_county_key"]
        if any(county_key(x.district_raw) != county for x in (oldrow, currow)):
            raise ValueError("Historical/current counties disagree")
        if pd.notna(target.district_raw) or not all(bool(x.is_additive_settlement_record) for x in rows):
            raise ValueError("Not a district-null whole settlement target")
        if state.uf.find(old) != state.uf.find(cur) or state.years[state.uf.find(cur)] != {2002, 2021} or state.years[state.uf.find(sid)] != {2010}:
            holds.append({"source_record_id": sid, "reason": "no_new_unique_three_year_merge"})
            continue
        anchors = [state.by_id.loc[r[k+"_anchor_2010_id"]] for k in ("lower", "upper")]
        if len({normalize(x.name_norm) for x in anchors}) != 2:
            holds.append({"source_record_id": sid, "reason": "bracket_anchors_not_distinct_names"})
            continue
        path = RAW / str(target.source_file)
        recovered = recovery.get(sid)
        if not path.is_file() and recovered is None:
            holds.append({"source_record_id": sid, "reason": "source_order_workbook_not_staged"})
            continue
        if recovered is None and path not in books:
            books[path] = xlrd.open_workbook(str(path), on_demand=True)
            hashes[str(path)] = sha(path)
        sheet = books[path].sheet_by_name(str(r["target_2010_source_sheet"])) if recovered is None else None
        n = int(r["target_2010_source_row"])
        rownums = [int(r[k+"_anchor_source_row"]) for k in ("lower", "upper")]
        if not (0 < n-rownums[0] <= 20 and 0 < rownums[1]-n <= 20):
            raise ValueError("Source bracket row gaps violated")
        for side, anchor in zip(("lower", "upper"), anchors):
            current_anchor = state.by_id.loc[r[side+"_anchor_2021_id"]]
            if state.uf.find(anchor.source_record_id) != state.uf.find(current_anchor.source_record_id) or county_key(current_anchor.district_raw) != county:
                raise ValueError("Bracket is not an accepted same-county anchor")
            if anchor.source_file != target.source_file or anchor.region_norm != target.region_norm:
                raise ValueError("Bracket source/region mismatch")
        literal_ok = True
        for role, obs, number in (("lower", anchors[0], rownums[0]), ("target", target, n), ("upper", anchors[1], rownums[1])):
            if recovered is None:
                vals = sheet.row_values(number-1)
                row_literal = " | ".join(str(v) for v in vals if v != "")
                source_sha, source_artifact = hashes[str(path)], str(path)
                sheet_name = sheet.name
            else:
                for field in ("source_ledger_path", "source_manifest_path"):
                    artifact = Path(recovered[field])
                    expected = recovered[field.replace("_path", "_sha256")]
                    if str(artifact) not in hashes:
                        hashes[str(artifact)] = sha(artifact)
                    if hashes[str(artifact)] != expected:
                        raise ValueError("Recovered complete source ledger or manifest changed")
                if int(recovered[role+"_source_row_1based"]) != number or str(recovered[role+"_selected_raw_literal_exact_match"]).lower() != "true":
                    raise ValueError("Recovered physical source row disagrees")
                if target.source_file != recovered["source_file_selected"]:
                    raise ValueError("Recovered publisher file differs")
                if pd.notna(target.source_sha256) and target.source_sha256 != recovered["source_file_sha256"]:
                    raise ValueError("Recovered publisher hash differs")
                vals = [recovered[role+"_source_label_raw"]]
                row_literal = recovered[role+"_raw_cells"]
                source_sha, source_artifact = recovered["source_ledger_sha256"], recovered["source_ledger_path"]
                sheet_name = str(r["target_2010_source_sheet"])
            name = normalize(obs.settlement_name)
            # Literal row is inspected, never inferred from a simulated source index.
            okay = any(name in normalize(v) for v in vals if isinstance(v, str))
            checks.append({"target_source_record_id": sid, "role": role, "source_file": source_artifact, "source_sha256": source_sha, "source_sheet": sheet_name, "source_row_1based": number, "literal_name_found": okay, "row_literal": row_literal, "complete_published_cell_ledger_used":recovered is not None})
            literal_ok &= okay
        if not literal_ok:
            holds.append({"source_record_id": sid, "reason": "physical_source_row_name_disagrees"})
            continue
        donor = state.point_rows[cur]
        if any(x in state.conflicting_point_targets for x in (sid, old, cur)):
            holds.append({"source_record_id": sid, "reason": "conflicting_point_alternatives"})
            continue
        if any(x in state.point_rows and distance_km((state.point_rows[x]["latitude"], state.point_rows[x]["longitude"]), (donor["latitude"], donor["longitude"])) > 5 for x in (old, sid)):
            holds.append({"source_record_id": sid, "reason": "accepted_points_over_5km"})
            continue
        ledger = Path(donor["point_ledger_path"])
        hashes.setdefault(str(ledger), sha(ledger))
        state.union(sid, cur)
        edges.append({"from_source_record_id": sid, "to_source_record_id": cur, "from_year": 2010, "to_year": 2021, "relation": "same_place", "decision_status": "checked_rule_accepted", "admission_rule": "unique_county_name_from_two_sided_source_context_type_variants_v1" if allow_type_change else "unique_typed_county_name_from_two_sided_source_context_v1", "inferred_county_key": county, "county_inference_evidence": str(candidate_path), "county_inference_locator": "target_2010_source_record_id="+sid, "source_district_field_modified": False, "population_boundary_comparability_asserted": False, "independent_historical_points_asserted": False, "printed_type_variation_allowed":allow_type_change})
        for tid in (sid, old):
            if tid in state.point_rows:
                continue
            point = {"target_source_record_id": tid, "target_year": int(state.by_id.loc[tid,"census_year"]), "latitude": donor["latitude"], "longitude": donor["longitude"], "coordinate_source_record_id": cur, "coordinate_admission_status": "reviewed_extension_rule_accepted", "coordinate_origin_ledger": str(ledger), "coordinate_origin_ledger_sha256": hashes[str(ledger)], "coordinate_origin_ledger_locator": "target_source_record_id="+cur, "admission_rule": "representative_point_continuity_over_accepted_source_context_identity", "direct_historical_coordinate_measurement": False, "native_code_binding_asserted": False, "boundary_comparability_asserted": False}
            state.point_rows[tid] = dict(point, point_ledger_path=str(out/"accepted_point_use_delta.csv"))
            points.append(point)
    out.mkdir(parents=True, exist_ok=True)
    # Keep the originally published stage-1 CSV schema byte-replayable.
    # Later extensions add explicit source-ledger and printed-type fields.
    if stage == 1 and not recovery_path and not allow_type_change:
        for row in edges:
            row.pop("printed_type_variation_allowed", None)
        for row in checks:
            row.pop("complete_published_cell_ledger_used", None)
    pd.DataFrame(edges).to_csv(out/"accepted_identity_edge_delta.csv", index=False)
    pd.DataFrame(points).to_csv(out/"accepted_point_use_delta.csv", index=False)
    pd.DataFrame(holds, columns=["source_record_id", "reason"]).to_csv(out/"held_candidates.csv", index=False)
    pd.DataFrame(checks).to_csv(out/"literal_source_row_checks.csv.gz", index=False, compression={"method":"gzip","mtime":0})
    after = state.metrics()
    inputs = {str(p): sha(p) for p in state.inputs + [candidate_path, candidate_path.parent/"summary.json", candidate_path.parent/"sampled_bracket_source_checks.csv"]}
    inputs.update(hashes)
    if recovery_path:
        inputs[str(recovery_path)] = sha(Path(recovery_path))
    receipt = {"status":"applied_source_context_inference_rule", "stage":stage,"printed_type_variation_allowed":allow_type_change, "candidate_count":len(candidates), "new_edges":len(edges), "new_point_uses":len(points), "held_count":len(holds), "holds":dict(Counter(r["reason"] for r in holds)), "all_applied_bracket_literal_rows_checked":True, "baseline":before, "after":after, "population_gain":{y:after[y]["covered_population"]-before[y]["covered_population"] for y in before}, "source_population_values_modified":False, "source_district_field_modified":False, "boundary_comparability_asserted":False, "inputs_sha256":inputs, "outputs":{p.name:sha(p) for p in out.iterdir() if p.suffix in (".csv",".gz")}}
    (out/"application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    (out/"README.md").write_text("# Районный контекст строк 2010\n\nОднозначные целые НП между двумя уже связанными разноимёнными строками той же таблицы, не дальше 20 физических строк с каждой стороны. Оба якоря имеют один район в принятых 2021 цепочках, а у объекта район подтверждён в 2002 и 2021. 2002–2021 уже связаны, конкурирующие строки и события исключены при генерации. Исходный район 2010 не переписан: контекст — явный вывод. Проверены буквальные строки всех применённых скобок по исходной книге либо её полному закреплённому ячеечному журналу. Точки перенесены как пространственная преемственность; независимость старых координат, границы и точность защищённых чисел 2010 не заявлены. Разрешение различий напечатанного типа, если использовано, явно записано в receipt и рёбрах.\n")
    print(json.dumps({k:receipt[k] for k in ("new_edges","new_point_uses","holds","population_gain","after")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidates")
    parser.add_argument("--out")
    parser.add_argument("--stage",type=int,default=1)
    parser.add_argument("--source-recovery")
    parser.add_argument("--allow-type-change",action="store_true")
    args=parser.parse_args()
    main(args.candidates,args.out,args.stage,args.source_recovery,args.allow_type_change)
