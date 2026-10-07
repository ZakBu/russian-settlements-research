"""Build complete three-census whole-place series without merging same-year parts."""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from current_chain_state_20261007 import State, normalize, sha

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "research_rebuild/evidence/numbered_partition_source_review_20261007"
OUT = ROOT / "research_rebuild/evidence/complete_numbered_partition_batch_20261007"
PART = re.compile(r"\s*\(часть\s*(\d+)\)\s*$", re.I)


def validate_members(group, reviewed_members, reviewed_groups):
    """A complete selected part set must be the complete set in its source scan."""
    if len(group) == 1 and not PART.search(str(group.iloc[0].settlement_name)):
        return False
    parsed = [PART.search(str(n)) for n in group.settlement_name]
    if any(m is None for m in parsed):
        raise ValueError("Competing whole-name homonyms require district disambiguation")
    numbers = sorted(int(m.group(1)) for m in parsed)
    if numbers != list(range(1, len(group)+1)) or len(group) < 2:
        raise ValueError("Incomplete or duplicated selected numbered parts")
    ids = set(group.source_record_id)
    evidence = reviewed_members[reviewed_members.source_record_id.isin(ids)]
    if set(evidence.source_record_id) != ids or evidence.source_record_id.duplicated().any():
        raise ValueError("Partition lacks distinct reviewed source rows")
    for r in group.itertuples(index=False):
        e = evidence[evidence.source_record_id.eq(r.source_record_id)].iloc[0]
        if int(e.selected_population) != int(r.population):
            raise ValueError("A component population changed")
    report = reviewed_groups[(reviewed_groups.year == int(group.iloc[0].census_year)) & reviewed_groups.region.eq(group.iloc[0].region_norm) & reviewed_groups.base_name.map(normalize).eq(normalize(PART.sub("", group.iloc[0].settlement_name)))]
    if len(report) != 1 or str(report.iloc[0].origin_workbook_parts) != ";".join(map(str, numbers)):
        raise ValueError("Source scan does not establish the selected complete numbered set")
    if int(report.iloc[0].selected_part_count) != len(group) or int(report.iloc[0].selected_part_sum) != int(group.population.sum()):
        raise ValueError("Review group differs from selected members")
    if int(group.iloc[0].census_year) == 2002 and int(report.iloc[0].official_candidates_equal_sum) != 1:
        raise ValueError("2002 whole population control not uniquely demonstrated")
    return True


def main():
    state = State()
    reviewed_members = pd.read_csv(REVIEW / "selected_partition_source_rows.csv", keep_default_na=False)
    reviewed_groups = pd.read_csv(REVIEW / "partition_groups.csv", keep_default_na=False)
    source_hashes = {}
    for row in reviewed_members.to_dict("records"):
        path = Path("/workspace/settlements-raw") / row["source_file"]
        if str(path) not in source_hashes:
            source_hashes[str(path)] = sha(path)
        if source_hashes[str(path)] != row["origin_workbook_sha256"]:
            raise ValueError("Reviewed member source bytes changed")
    official_controls = pd.read_csv(REVIEW / "complete_2002_groups_exact_official_whole.csv", keep_default_na=False)
    for path, expected in official_controls[["official_whole_source", "official_whole_source_sha256"]].drop_duplicates().itertuples(index=False, name=None):
        if sha(Path(path)) != expected:
            raise ValueError("Official whole control bytes changed")
    obs = state.obs.copy()
    obs["base"] = obs.settlement_name.map(lambda n: PART.sub("", str(n)))
    obs["base_norm"] = obs.base.map(normalize)
    partition_keys = obs[obs.settlement_name.str.contains(r"\(часть\s*\d+\)", na=False)][["base_norm", "region_norm", "settlement_type"]].drop_duplicates()
    rows, members, holds = [], [], []
    for base, region, typ in sorted(partition_keys.itertuples(index=False, name=None)):
        group = obs[obs.base_norm.eq(base) & obs.region_norm.eq(region) & obs.settlement_type.eq(typ)]
        try:
            if set(group.census_year) != {2002, 2010, 2021}:
                raise ValueError("Not all three census years are observed")
            if not group.is_additive_settlement_record.fillna(False).all():
                raise ValueError("Nonadditive member")
            years = []
            for year, g in group.groupby("census_year"):
                is_partition = validate_members(g, reviewed_members, reviewed_groups)
                years.append((int(year), g, is_partition))
            current = next(g for y, g, _ in years if y == 2021)
            if len(current) != 1:
                # Existing Novaya Usman whole-union rule owns its 2021 two-part
                # point; do not treat a member point as a new whole-place claim.
                raise ValueError("2021 whole-point binding needs the existing separate union artifact")
            sid = current.iloc[0].source_record_id
            if sid not in state.point_rows or sid in state.conflicting_point_targets:
                raise ValueError("No unambiguous accepted current whole-place point")
            point = state.point_rows[sid]
            ledger = Path(point["point_ledger_path"])
            place_id = "complete_partition:" + hashlib.sha256((region+"|"+typ+"|"+base).encode()).hexdigest()[:20]
            for year, g, partition in years:
                g = g.sort_values("source_record_id")
                ids = g.source_record_id.tolist()
                row = {"place_id": place_id, "place": current.iloc[0].settlement_name,
                    "region_norm": region, "settlement_type": typ, "year": year,
                    "population": int(g.population.sum()),
                    "member_source_record_ids_json": json.dumps(ids, ensure_ascii=False),
                    "member_populations_json": json.dumps([int(x) for x in g.population]),
                    "member_population_quality_json": json.dumps(g.population_value_quality.tolist(), ensure_ascii=False),
                    "member_source_provenance_json": json.dumps([{
                        "source_record_id": r["source_record_id"],
                        "source_file": r["source_file"],
                        "source_path": str(Path("/workspace/settlements-raw") / r["source_file"]),
                        "source_sha256": source_hashes.setdefault(str(Path("/workspace/settlements-raw") / r["source_file"]), sha(Path("/workspace/settlements-raw") / r["source_file"])),
                        "source_locator": r["source_record_id"],
                    } for r in g.to_dict("records")], ensure_ascii=False),
                    "population_is_derived_sum": partition,
                    "projection_status": "accepted_complete_publisher_partition" if partition else "selected_whole_locality_observation",
                    "latitude": point["latitude"], "longitude": point["longitude"],
                    "point_ledger_path": str(ledger), "point_ledger_sha256": sha(ledger),
                    "point_ledger_locator": "target_source_record_id="+sid,
                    "point_scope": "whole locality; no individual part coordinate admitted",
                    "individual_part_coordinates_admitted": False,
                    "direct_historical_coordinate_measurement": False,
                    "retrospective_point_use_is_continuity_inference": year != 2021,
                    "population_boundary_comparability_asserted": False,
                    "modern_boundary_harmonized": False,
                    "oktmo_native_current": str(current.iloc[0].oktmo) if pd.notna(current.iloc[0].oktmo) else "",
                    "oktmo_current_year": 2021, "oktmo_history_status": "not_reconstructed",
                }
                rows.append(row)
                for r in g.to_dict("records"):
                    members.append({"place_id": place_id, "source_record_id": r["source_record_id"], "year": year, "population": int(r["population"]), "coordinate_scope": "complete_whole_locality_projection" if partition else "whole_locality", "ordinary_same_place_graph_mutated": False})
        except ValueError as e:
            holds.append({"base_name": base, "region_norm": region, "settlement_type": typ, "reason": str(e)})
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "accepted_three_census_whole_place_series.csv", index=False)
    pd.DataFrame(members).to_csv(OUT / "accepted_exclusive_member_projection.csv", index=False)
    pd.DataFrame(holds).to_csv(OUT / "held_groups.csv", index=False)
    covered_ids = {r["source_record_id"] for r in members}
    if len(covered_ids) != len(members):
        raise ValueError("A source member was assigned to more than one place")
    baseline, after = state.metrics(), state.metrics(extra_covered_ids=covered_ids)
    receipt = {"status": "applied_complete_selected_numbered_partition_three_census_series", "places": len(rows)//3, "series_rows": len(rows), "exclusive_source_member_rows": len(members), "baseline_ordinary_three_census": baseline, "after_ordinary_plus_complete_partitions": after,
        "population_gain": {y: after[y]["covered_population"]-baseline[y]["covered_population"] for y in baseline},
        "new_ordinary_same_place_edges": 0, "new_individual_part_point_uses": 0,
        "source_population_values_modified": False, "source_member_populations_counted_once": True,
        "boundary_comparability_asserted": False,
        "inputs": {str(p): sha(p) for p in state.inputs + list(REVIEW.glob("*.csv"))} | source_hashes,
        "limitations": ["Full observed publisher partitions, not modern-boundary reconstruction.", "Whole-locality coordinates do not locate the individual territorial parts.", "Protected 2010 values remain protected, including sums differing from official whole rows.", "Homonyms and incomplete part sets remain held; absence is not population zero."],
        "outputs": {p.name: sha(p) for p in OUT.glob("*.csv")}}
    (OUT / "application_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    (OUT / "README.md").write_text("# Полные группы частей: три переписи и общая точка НП\n\nГруппируются только полные пронумерованные части одного издательского перечня. Для 2002 проверяется точная сумма по официальной строке целого НП. Сохраняются все исходные строки и качество населения, включая защиту значений 2010. Полный ряд связывает целый НП; координата не приписывается отдельной части. В покрытии объединяется набор исходных ID: сумма целого не прибавляется второй раз. Одноимённые объекты и неполные группы удержаны.\n")
    print(json.dumps({k: receipt[k] for k in ("places", "exclusive_source_member_rows", "population_gain", "after_ordinary_plus_complete_partitions")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
