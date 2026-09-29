"""Build the reviewed national population-source selection release R1.

This release applies two separately reviewed source-grain corrections:
Moscow 2002 (aggregate parent replaced by five disjoint children) and
Karelia 2010 (legacy regional slice replaced by the corrected fresh R5 source).
It deliberately makes no identity or coordinate admissions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import pandas as pd

CODE_ROOT = Path(__file__).resolve().parents[2]
BASELINE = CODE_ROOT / "research_audit/output/audited_census_snapshots.parquet"
KARELIA_R5 = CODE_ROOT / "research_rebuild/evidence/ingestion/karelia_2010_fresh_source_reproduction_r5/karelia_2010_fresh_primary_observations.parquet"
R5_RECEIPT = KARELIA_R5.parent / "run_receipt.json"
R5_MANIFEST = CODE_ROOT / "research_rebuild/evidence/ingestion/source_manifest_karelia_r5_fresh.json"
MOSCOW_CHILDREN = CODE_ROOT / "research_rebuild/evidence/ingestion/2002_parent_child_scope_audit/rosstat_2002_typed_urban_components_by_parent.csv"
MOSCOW_REVIEW = CODE_ROOT / "research_rebuild/evidence/reviews/moscow_2002_parent_child_migration_review_r1_20260930.json"
MOSCOW_PROPOSAL = CODE_ROOT / "research_rebuild/evidence/releases/national_2002_parent_child_selection_proposal_r0_20260930/2002_parent_child_selection_proposal_manifest.json"
MOSCOW_PARENT_ID = "2002:1_TOM_01_04.xls:0:2154"
MOSCOW_LOGICAL_PARENT = "ROSSTAT2002:T1:T4:sheet01-04:excel_row02154"
R5_MANIFEST_SHA = "0988f9092c385b7aaa506bd2da6724bb6fb65593c1843a98ee0479158f06104e"
MOSCOW_REVIEW_SHA = "893959b9cb59e8e3c35a0aff0b072042e45359c4fbbb542bde474c5df4a30721"
MOSCOW_PROPOSAL_SHA = "b61dd7f9320a18c62c6ab7e555653bbbd45e6ec53cba8b7b44108845d4cc0aa8"
R5_CANONICAL_CONTENT_SHA = "551e4cef5653997045ef3710bc16f8fef1d8239f81f55a5819a521f91a5b250b"
EXTRA_COLUMNS = ["source_path", "source_sha256", "source_locator", "source_population_raw", "men", "women",
                 "extraction_version", "source_selection_component", "identity_admission", "coordinate_admission"]


def output_columns(template: pd.DataFrame) -> list[str]:
    return list(template.columns) + [c for c in EXTRA_COLUMNS if c not in template.columns]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_inputs() -> dict:
    expected = {
        BASELINE: "b42a1230519c8303079ce2465bb28d3c4af357ece5dbdd26e4f5de2c3de02c2b",
        R5_MANIFEST: R5_MANIFEST_SHA,
        MOSCOW_CHILDREN: "da7ca2fc853ddd46a8cd50ba05cc098f774989666e9cbef8afa30958fcde09b4",
        MOSCOW_REVIEW: MOSCOW_REVIEW_SHA,
        MOSCOW_PROPOSAL: MOSCOW_PROPOSAL_SHA,
    }
    checked = {}
    for path, digest in expected.items():
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"required reviewed input missing or changed: {path}")
        checked[str(path.relative_to(CODE_ROOT))] = {"sha256": digest, "bytes": path.stat().st_size}
    if not KARELIA_R5.is_file() or not R5_RECEIPT.is_file():
        raise FileNotFoundError("corrected R5 Karelia source output or run receipt is missing")
    receipt = json.loads(R5_RECEIPT.read_text(encoding="utf-8"))
    outrec = {x["path"]: x for x in receipt.get("outputs", [])}
    parquet_rec = outrec.get(KARELIA_R5.name)
    if receipt.get("status") != "complete" or receipt.get("extraction_version") != "karelia-2010-fresh-primary-r5":
        raise ValueError("R5 run receipt is not a completed corrected extraction")
    if not parquet_rec or parquet_rec.get("sha256") != sha(KARELIA_R5):
        raise ValueError("R5 Parquet binary does not match its run receipt")
    if receipt.get("canonical_parquet_content_sha256") != R5_CANONICAL_CONTENT_SHA:
        raise ValueError("R5 canonical typed content hash differs from the frozen source layer")
    checked[str(KARELIA_R5.relative_to(CODE_ROOT))] = {"sha256": sha(KARELIA_R5), "canonical_typed_content_sha256": R5_CANONICAL_CONTENT_SHA}
    checked[str(R5_RECEIPT.relative_to(CODE_ROOT))] = {"sha256": sha(R5_RECEIPT)}
    return checked


def make_moscow_rows(children: pd.DataFrame, template: pd.DataFrame) -> pd.DataFrame:
    m = children[children.parent_source_record_id.eq(MOSCOW_LOGICAL_PARENT)].copy()
    if len(m) != 5 or not m.disjoint_parent_sex_conservation_proven.astype(bool).all():
        raise ValueError("Moscow needs exactly five independently conserved typed children")
    if (int(m.population.sum()), int(m.men.sum()), int(m.women.sum())) != (10_382_754, 4_951_819, 5_430_935):
        raise ValueError("Moscow child P/M/F totals do not conserve the reviewed parent")
    rows = []
    for r in m.itertuples(index=False):
        is_city = str(r.settlement_type_raw).strip() == "г."
        name = str(r.label_raw).strip()
        if name.startswith("г."):
            name = name[2:].strip()
        elif name.startswith("пгт"):
            name = name[3:].strip()
        row = {c: pd.NA for c in template.columns}
        row.update({
            "source_record_id": r.source_record_id,
            "census_year": 2002,
            "source_file": "data/raw/2002_official_tom1/1_TOM_01_04.xls",
            "source_sheet": "01-04",
            "source_row": int(r.excel_row),
            "source_native_id": r.source_record_id,
            "source_name_raw": r.label_raw,
            "settlement_name": name,
            "settlement_type": "город" if is_city else "посёлок городского типа",
            "region_raw": "Москва",
            "district_raw": pd.NA,
            "municipality_raw": pd.NA,
            "population": int(r.population),
            "latitude": pd.NA,
            "longitude": pd.NA,
            "coordinate_source": pd.NA,
            "coverage_status": "reviewed_source_selection_no_identity_or_point_claim",
            "population_scope": "physical_settlement_city_only" if is_city else "physical_settlement_urban_type",
            "derivation_note": "Selected from source-disjoint child partition under independent Moscow 2002 migration review; no identity or coordinate carried forward.",
            "name_norm": " ".join(name.casefold().replace("ё", "е").split()),
            "type_norm": "город" if is_city else "поселок городского типа",
            "region_norm": "москва",
            "is_additive_settlement_record": True,
            "population_value_quality": "reviewed_primary_source_child_partition",
            "analysis_population_additive": True,
            "entity_grain_status": "atomic_physical_settlement",
            "recovered_official_city_record": True,
            "source_path": "data/raw/2002_official_tom1/1_TOM_01_04.xls",
            "source_sha256": "745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3",
            "source_locator": f"sheet 01-04, Excel row {int(r.excel_row)}",
            "source_population_raw": r.label_raw,
            "men": int(r.men), "women": int(r.women),
            "source_selection_component": "moscow_2002_parent_child_migration",
            "identity_admission": "none", "coordinate_admission": "none",
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=output_columns(template))


def map_r5_rows(r5: pd.DataFrame, template: pd.DataFrame) -> pd.DataFrame:
    if len(r5) != 800 or r5.source_record_id.duplicated().any() or int(r5.population.sum()) != 643_548:
        raise ValueError("R5 source layer failed row count, unique ID, or sum controls")
    rows = []
    for r in r5.itertuples(index=False):
        row = {c: pd.NA for c in template.columns}
        region = str(r.region_raw)
        name = str(r.settlement_name)
        typ = str(r.settlement_type)
        if pd.notna(r.source_table_row_index_zero_based):
            source_row_number = int(r.source_table_row_index_zero_based)
        else:
            match = re.search(r"text_line\[(\d+)", str(r.source_locator))
            if not match:
                raise ValueError(f"cannot derive numeric source row locator: {r.source_locator}")
            source_row_number = int(match.group(1))
        row.update({
            "source_record_id": r.source_record_id,
            "census_year": 2010,
            "source_file": r.source_path,
            "source_sheet": f"table={r.source_table_index_zero_based};row={r.source_table_row_index_zero_based}" if pd.notna(r.source_table_index_zero_based) else "DOCX rural tables",
            "source_row": source_row_number,
            "source_native_id": r.source_population_reference,
            "source_name_raw": r.source_population_raw,
            "settlement_name": name,
            "settlement_type": typ,
            "region_raw": region,
            "district_raw": r.district_context_raw,
            "municipality_raw": r.municipality_context_raw,
            "population": int(r.population),
            "latitude": pd.NA, "longitude": pd.NA, "coordinate_source": pd.NA,
            "coverage_status": "selected_primary_r5_source_no_identity_or_point_claim",
            "population_scope": r.population_scope,
            "name_norm": r.settlement_name_norm,
            "type_norm": r.settlement_type_norm,
            "region_norm": r.region_norm,
            "derivation_note": "Fresh corrected R5 primary extraction; source value selection is separate from identity matching.",
            "is_additive_settlement_record": True,
            "population_value_quality": "fresh_primary_r5_source",
            "analysis_population_additive": True,
            "entity_grain_status": "atomic_physical_settlement",
            "recovered_official_city_record": "urban" in str(r.source_role),
            "source_path": r.source_path,
            "source_sha256": r.source_sha256,
            "source_locator": r.source_locator,
            "source_population_raw": r.source_population_raw,
            "men": int(r.men) if pd.notna(r.men) else pd.NA,
            "women": int(r.women) if pd.notna(r.women) else pd.NA,
            "extraction_version": r.extraction_version,
            "source_selection_component": "karelia_2010_primary_r5",
            "identity_admission": "none", "coordinate_admission": "none",
        })
        rows.append(row)
    return pd.DataFrame(rows, columns=output_columns(template))


def build(output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"immutable output already exists: {output}")
    inputs = verify_inputs()
    baseline = pd.read_parquet(BASELINE)
    original = baseline.copy()
    children = pd.read_csv(MOSCOW_CHILDREN)
    r5 = pd.read_parquet(KARELIA_R5)
    # Exact legacy 2002 parent and whole Karelia 2010 region slices only.
    if int((baseline.source_record_id.astype(str) == MOSCOW_PARENT_ID).sum()) != 1:
        raise ValueError("legacy Moscow parent must occur exactly once in selected snapshot")
    k_mask = baseline.census_year.eq(2010) & baseline.region_raw.astype("string").str.casefold().str.contains("карелия", na=False)
    old_k = baseline[k_mask].copy()
    if len(old_k) != 799 or int(old_k.population.sum()) != 638_764:
        raise ValueError("legacy selected Karelia 2010 slice differs from reviewed R5 replacement precondition")
    moscow_rows = make_moscow_rows(children, baseline)
    r5_rows = map_r5_rows(r5, baseline)
    result = baseline.reindex(columns=output_columns(baseline))
    result = result[result.source_record_id.astype(str).ne(MOSCOW_PARENT_ID) & ~k_mask].copy()
    result = pd.concat([result, moscow_rows, r5_rows], ignore_index=True, sort=False)
    result = result.sort_values(["census_year", "source_record_id"], kind="stable", ignore_index=True)
    if result.source_record_id.astype(str).duplicated().any():
        raise ValueError("release selected source IDs are not globally unique")
    # Regression gate: exact ID-set changes by year, not only counts/sums.
    for year in (2002, 2010, 2021):
        before = set(original.loc[original.census_year.eq(year), "source_record_id"].astype(str))
        after = set(result.loc[result.census_year.eq(year), "source_record_id"].astype(str))
        if year == 2002:
            expected = before - {MOSCOW_PARENT_ID} | set(moscow_rows.source_record_id.astype(str))
        elif year == 2010:
            expected = before - set(old_k.source_record_id.astype(str)) | set(r5_rows.source_record_id.astype(str))
        else:
            expected = before
        if after != expected:
            raise ValueError(f"selected source ID set mismatch for {year}")
    totals = {}
    for year in (2002, 2010, 2021):
        b = original[original.census_year.eq(year)]
        a = result[result.census_year.eq(year)]
        totals[str(year)] = {"baseline_rows": len(b), "selected_rows": len(a),
            "row_delta": len(a)-len(b), "baseline_population": int(b.population.sum()),
            "selected_population": int(a.population.sum()), "population_delta": int(a.population.sum()-b.population.sum()),
            "selected_ids_sha256": hashlib.sha256("\n".join(sorted(a.source_record_id.astype(str))).encode()).hexdigest()}
    expected_deltas = {"2002": (4, 0), "2010": (1, 4784), "2021": (0, 0)}
    for y, vals in expected_deltas.items():
        if (totals[y]["row_delta"], totals[y]["population_delta"]) != vals:
            raise ValueError(f"unexpected year delta {y}: {totals[y]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    result_path = staging / "selected_observations.parquet"
    result.to_parquet(result_path, index=False)
    # Preserve parent exclusion as a decision row, never silently delete it.
    parent = original[original.source_record_id.astype(str).eq(MOSCOW_PARENT_ID)].copy()
    parent["release_disposition"] = "excluded_city_plus_subordinates_aggregate_replaced_by_reviewed_children"
    parent["decision_evidence"] = "research_rebuild/evidence/reviews/moscow_2002_parent_child_migration_review_r1_20260930.json"
    parent["identity_admission"] = "none"
    parent["coordinate_admission"] = "none"
    parent.to_csv(staging / "excluded_source_rows.csv", index=False)
    components = pd.DataFrame([
      {"component_id":"moscow_2002_parent_child_migration","census_year":2002,"operation":"replace_aggregate_parent_with_disjoint_children",
       "removed_rows":1,"added_rows":5,"row_delta":4,"removed_population":10_382_754,"added_population":10_382_754,"population_delta":0,
       "removed_source_record_ids":json.dumps([MOSCOW_PARENT_ID]),"added_source_record_ids":json.dumps(sorted(moscow_rows.source_record_id.astype(str))),
       "evidence_manifest_sha256":MOSCOW_REVIEW_SHA,"identity_or_coordinate_claims":"none"},
      {"component_id":"karelia_2010_primary_r5","census_year":2010,"operation":"replace_legacy_region_slice_with_corrected_primary_source_layer",
       "removed_rows":len(old_k),"added_rows":len(r5_rows),"row_delta":len(r5_rows)-len(old_k),"removed_population":int(old_k.population.sum()),"added_population":int(r5_rows.population.sum()),"population_delta":int(r5_rows.population.sum()-old_k.population.sum()),
       "removed_source_record_ids":json.dumps(sorted(old_k.source_record_id.astype(str))),"added_source_record_ids":json.dumps(sorted(r5_rows.source_record_id.astype(str))),
       "evidence_manifest_sha256":R5_MANIFEST_SHA,"identity_or_coordinate_claims":"none"},
    ])
    components.to_csv(staging / "component_ledger.csv", index=False)
    assertions = []
    for row in parent.itertuples(index=False):
        assertions.append({"component_id":"moscow_2002_parent_child_migration","census_year":2002,
          "source_record_id":row.source_record_id,"action":"retain_in_archive_exclude_from_selected_release",
          "population":int(row.population),"source_locator":f"{row.source_file}; sheet={row.source_sheet}; row={row.source_row}",
          "reason":"city-plus-subordinates aggregate replaced by independently reviewed disjoint children",
          "evidence_sha256":MOSCOW_REVIEW_SHA})
    for row in moscow_rows.itertuples(index=False):
        assertions.append({"component_id":"moscow_2002_parent_child_migration","census_year":2002,
          "source_record_id":row.source_record_id,"action":"select_for_release",
          "population":int(row.population),"source_locator":row.source_locator,
          "reason":"reviewed source-disjoint physical settlement child; no identity or point claim",
          "evidence_sha256":MOSCOW_REVIEW_SHA})
    for row in old_k.itertuples(index=False):
        assertions.append({"component_id":"karelia_2010_primary_r5","census_year":2010,
          "source_record_id":row.source_record_id,"action":"retain_as_superseded_selected_observation",
          "population":int(row.population),"source_locator":f"{row.source_file}; sheet={row.source_sheet}; row={row.source_row}",
          "reason":"legacy selected observation retained in baseline archive; replaced by corrected primary R5 source selection",
          "evidence_sha256":R5_MANIFEST_SHA})
    for row in r5_rows.itertuples(index=False):
        assertions.append({"component_id":"karelia_2010_primary_r5","census_year":2010,
          "source_record_id":row.source_record_id,"action":"select_for_release",
          "population":int(row.population),"source_locator":row.source_locator,
          "reason":"fresh corrected primary source observation; no identity or point claim",
          "evidence_sha256":R5_MANIFEST_SHA})
    pd.DataFrame(assertions).sort_values(["census_year","component_id","action","source_record_id"],kind="stable").to_csv(
        staging / "source_selection_assertions.csv", index=False)
    (staging / "annual_controls.json").write_text(json.dumps(totals, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    manifest = {"release_id":"national_source_selection_r1_20260930","release_status":"selection_only_no_new_identity_or_coordinate_admissions",
      "builder_sha256":sha(Path(__file__).resolve()),
      "baseline_snapshot":{"path":str(BASELINE.relative_to(CODE_ROOT)),"sha256":sha(BASELINE)},
      "verified_inputs":inputs,"components":[
        {"component_id":"moscow_2002_parent_child_migration","review_file":str(MOSCOW_REVIEW.relative_to(CODE_ROOT)),"review_sha256":MOSCOW_REVIEW_SHA,"proposal_manifest_sha256":MOSCOW_PROPOSAL_SHA,"child_source_ids":sorted(moscow_rows.source_record_id.astype(str))},
        {"component_id":"karelia_2010_primary_r5","source_manifest":str(R5_MANIFEST.relative_to(CODE_ROOT)),"source_manifest_sha256":R5_MANIFEST_SHA,"run_receipt_sha256":sha(R5_RECEIPT),"source_ids":sorted(r5.source_record_id.astype(str))}],
      "annual_controls":totals,"source_observations":len(result),"outputs":{}}
    for p in sorted(staging.iterdir()):
        if p.is_file(): manifest["outputs"][p.name]={"sha256":sha(p),"bytes":p.stat().st_size}
    (staging/"release_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if output.exists():
        shutil.rmtree(staging)
        raise FileExistsError(f"immutable output already exists: {output}")
    staging.rename(output)
    return manifest


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    m=build(args.output)
    print(json.dumps({"release_id":m["release_id"],"annual_controls":m["annual_controls"],"output":str(args.output.resolve())},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
