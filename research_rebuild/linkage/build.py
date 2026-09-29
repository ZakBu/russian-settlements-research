"""Build reproducible identity and coordinate review layers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import sys
import tempfile

import duckdb
import numpy as np
import pandas as pd

CODE_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("SETTLEMENT_DATA_ROOT", CODE_ROOT)).expanduser().resolve()
INPUTS_ROOT = Path(os.environ.get("SETTLEMENT_INPUTS_ROOT", CODE_ROOT)).expanduser().resolve()
HERE = Path(__file__).resolve().parent
REBUILD = HERE.parent
OUT_ROOT = Path(os.environ.get("SETTLEMENT_OUTPUT_ROOT", REBUILD / "output")).expanduser().resolve()
_bundle_ingestion = INPUTS_ROOT / "evidence/ingestion"
_output_ingestion = OUT_ROOT / "ingestion"
INGESTION_ROOT = (_output_ingestion if _output_ingestion.exists() else
                  _bundle_ingestion if _bundle_ingestion.exists() else REBUILD / "evidence/ingestion")
REVIEW_ROOT = INPUTS_ROOT / "review_inputs" if (INPUTS_ROOT / "review_inputs").exists() else OUT_ROOT
OUT = OUT_ROOT
INPUT_VERIFICATION = {}
YEARS = (2002, 2010, 2021)
OFFICIAL_TOTALS = {2002: 145_166_731, 2010: 142_856_536, 2021: 147_182_123}
KARELIA_OFFICIAL_TOTALS = {2002: 716_281, 2010: 643_548, 2021: 533_121}
KARELIA_CONTROL_LOCATORS = {
    2002: "data/raw/2002_official_tom1/1_TOM_01_04.xls; source row 2305, columns A/B",
    2010: "Rosstat Vol. 1 Table 5; PDF page 54, lines 22-24 (printed page 53)",
    2021: "Rosstat 2021 Table 5 settlement rows; source_inventory and regional aggregate control",
}

sys.path.insert(0, str(HERE))
from core import (apply_decision_events, coordinate_claims, make_identity_candidates,
                  prepare_observations, rule_coordinate_decisions, stable_id,
                  reviewer_results_to_events, identity_components, component_lineage, normalize)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_primary_source_hash(frame: pd.DataFrame) -> str:
    """Hash ordered, typed table values using the frozen parser's canonical scheme."""
    rows = []
    for row in frame.itertuples(index=False, name=None):
        typed = []
        for value in row:
            if pd.isna(value):
                typed.append(None)
                continue
            if hasattr(value, "item"):
                value = value.item()
            typed.append({"type": type(value).__name__, "value": value})
        rows.append(typed)
    payload = {"columns": [{"name": name, "dtype": str(dtype)}
                           for name, dtype in zip(frame.columns, frame.dtypes)], "rows": rows}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_portable_inputs() -> dict:
    """Fail closed on the pinned source archive and declared supplemental assets."""
    source_manifest_path = CODE_ROOT / "research_rebuild/evidence/ingestion/source_manifest_karelia_r4_fresh.json"
    if not source_manifest_path.is_file() or sha256(source_manifest_path) != "77c0abc3730f505a3da3ce53bd5993536b99ba9b6928e5691a26aac2699ca8dd":
        raise ValueError("pinned R4 source manifest is missing or changed")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    required_roles = {"raw_primary_or_secondary_source", "preexisting_replay_or_reference_evidence"}
    checked = []
    for item in source_manifest:
        if item.get("role") not in required_roles:
            continue
        path = ROOT / item["path"]
        if not path.is_file() and item["path"].endswith("karelia_2010_rural_settlements.docx"):
            path = INPUTS_ROOT / "evidence/ingestion/source/karelia_2010_rural_settlements.docx"
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"baseline input missing or checksum/size mismatch: {item['path']}")
        checked.append(item["path"])
    fresh_manifest_path = CODE_ROOT / "research_rebuild/evidence/ingestion/source_manifest_karelia_r4b_fresh_final.json"
    if not fresh_manifest_path.is_file() or sha256(fresh_manifest_path) != "bdbf48f0a03648a42178e4b786554ea9e047849e75fa78aa239a1e23826021c0":
        raise ValueError("frozen R4b fresh extraction manifest is missing or changed")
    fresh_manifest = json.loads(fresh_manifest_path.read_text(encoding="utf-8"))
    for item in fresh_manifest["input_sources"]:
        path = (INPUTS_ROOT / "evidence/ingestion/source/karelia_2010_rural_settlements.docx"
                if item["role"] == "primary_regional_census_docx" else ROOT / item["path"])
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"R4b primary source missing or checksum/size mismatch: {item['path']}")
        checked.append(item["path"])
    for item in fresh_manifest["extractor_code"] + fresh_manifest["validation_tests"]:
        path = CODE_ROOT / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"R4b method/test code missing or checksum/size mismatch: {item['path']}")
        checked.append(item["path"])
    bundle_manifest_path = INPUTS_ROOT / "BUNDLE_MANIFEST.json"
    if not bundle_manifest_path.is_file():
        raise FileNotFoundError("supplemental input bundle lacks BUNDLE_MANIFEST.json")
    bundle = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
    for item in bundle.get("asset_files", []):
        path = INPUTS_ROOT / item["path"]
        if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError(f"supplemental input missing or checksum/size mismatch: {item['path']}")
        checked.append(item["path"])
    return {"baseline_source_manifest": artifact_path(source_manifest_path),
            "baseline_source_manifest_sha256": sha256(source_manifest_path),
            "fresh_source_manifest": artifact_path(fresh_manifest_path),
            "fresh_source_manifest_sha256": sha256(fresh_manifest_path),
            "supplemental_bundle_manifest": artifact_path(bundle_manifest_path),
            "supplemental_bundle_manifest_sha256": sha256(bundle_manifest_path),
            "verified_input_count": len(checked), "verified_input_paths": checked}


def artifact_path(path: Path) -> str:
    """Stable path relative to one of the declared portable build roots."""
    try:
        return "review_inputs/" + path.resolve().relative_to(REVIEW_ROOT.resolve()).as_posix()
    except ValueError:
        pass
    for root in (ROOT, INPUTS_ROOT, OUT_ROOT, CODE_ROOT):
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return path.name


def release_coordinate_decisions(effective: pd.DataFrame, selected_observation_ids: set[str]) -> pd.DataFrame:
    """Keep historical ledger events, but admit only selected source rows in a release."""
    if effective.empty:
        return effective.copy()
    active = effective[effective.decision_type.eq("coordinate_admission")
                       & effective.event_action.eq("apply")
                       & effective.observation_id.isin(selected_observation_ids)].copy()
    return active


def load_observations(scope: str = "mixed") -> tuple[pd.DataFrame, dict]:
    """Prefer parser rebuild after row-disposition reconciliation is available."""
    pilot_obs_path = INGESTION_ROOT / "observations_karelia.parquet"
    pilot_disp_path = INGESTION_ROOT / "source_dispositions_karelia.parquet"
    if pilot_obs_path.exists() and pilot_disp_path.exists():
        legacy_path = ROOT / "research_audit/output/audited_census_snapshots.parquet"
        pilot = pd.read_parquet(pilot_obs_path)
        dispositions = pd.read_parquet(pilot_disp_path)
        selected = dispositions[dispositions.snapshot_included.eq(True)]
        ids = set(selected.observation_source_record_id.dropna().astype(str))
        pilot.source_record_id = pilot.source_record_id.astype(str)
        pilot = pilot[pilot.source_record_id.isin(ids)].copy()
        if pilot.source_record_id.duplicated().any():
            raise ValueError("Karelia parser pilot duplicates an included source record")
        if scope == "karelia":
            return pilot, {
                "mode": "karelia_disposition_selected_pilot",
                "pilot_observations": artifact_path(pilot_obs_path),
                "pilot_observations_sha256": sha256(pilot_obs_path),
                "pilot_dispositions": artifact_path(pilot_disp_path),
                "pilot_dispositions_sha256": sha256(pilot_disp_path),
                "source_status": "Karelia additive observation rows selected by row-level dispositions; regional population control is still unresolved",
            }
        legacy = pd.read_parquet(legacy_path)
        legacy = legacy[legacy.census_year.isin(YEARS)].copy()
        legacy_region = legacy.region_raw.astype("string").str.contains("карелия", case=False, na=False)
        # Regional replay replaces the prior regional slice without changing
        # other regions. Source rows remain at their original grain.
        nonregional = legacy[~legacy_region]
        combined = pd.concat([nonregional, pilot], ignore_index=True, sort=False)
        if combined.source_record_id.duplicated().any():
            raise ValueError("mixed nationwide observations contain duplicate source_record_id")
        return combined, {
            "mode": "karelia_reconciled_pilot_plus_legacy_national_comparison",
            "pilot_observations": artifact_path(pilot_obs_path),
            "pilot_observations_sha256": sha256(pilot_obs_path),
            "pilot_dispositions": artifact_path(pilot_disp_path),
            "pilot_dispositions_sha256": sha256(pilot_disp_path),
            "national_comparison": artifact_path(legacy_path),
            "national_comparison_sha256": sha256(legacy_path),
            "source_status": "Karelia uses reconciled pilot dispositions; all other regions remain legacy comparison input, not production-certified",
        }
    ing = INGESTION_ROOT
    obs_path = ing / "observations.parquet"
    disp_path = ing / "source_dispositions.parquet"
    if obs_path.exists() and disp_path.exists():
        obs = pd.read_parquet(obs_path)
        disp = pd.read_parquet(disp_path)
        if "observation_source_record_id" not in disp:
            raise ValueError("source dispositions lack observation_source_record_id")
        if "row_status" not in disp:
            raise ValueError("source dispositions lack row_status")
        included = disp[disp.row_status.astype("string").isin(["included", "observation", "parsed", "selected"])]
        keep = set(included.observation_source_record_id.dropna().astype(str))
        obs["source_record_id"] = obs.source_record_id.astype(str)
        # A parsed observation counts only if the source-row disposition table
        # identifies it as an included census row. The input report discloses
        # all parser dispositions and any excluded rows.
        obs = obs[obs.source_record_id.isin(keep)].copy()
        if obs.source_record_id.duplicated().any():
            raise ValueError("parser observations are not unique by source_record_id")
        return obs, {"mode": "reconciled_parser_output", "path": artifact_path(obs_path),
                     "sha256": sha256(obs_path), "dispositions": artifact_path(disp_path),
                     "dispositions_sha256": sha256(disp_path), "source_status": "parser audit status read from ingestion summary"}
    legacy = ROOT / "research_audit/output/audited_census_snapshots.parquet"
    if not legacy.exists():
        raise FileNotFoundError("Neither reconciled ingestion nor audited legacy snapshot is available")
    obs = pd.read_parquet(legacy)
    obs = obs[obs.census_year.isin(YEARS)].copy()
    if scope == "karelia":
        obs = obs[obs.region_raw.astype("string").str.contains("карелия", case=False, na=False)].copy()
    return obs, {"mode": "baseline_audited_snapshot", "path": artifact_path(legacy),
                 "sha256": sha256(legacy),
                 "pilot_observations": artifact_path(legacy), "pilot_observations_sha256": sha256(legacy),
                 "source_status": "baseline audited snapshot, used only for unchanged 2002/2021 slice and pre-existing 2010 review nodes; fresh 2010 selection comes from R4 primary extraction"}


def load_karelia_observation_registry() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep prior and current parser observations; selection is a separate release map."""
    legacy_path = ROOT / "research_audit/output/audited_census_snapshots.parquet"
    pilot_path = INGESTION_ROOT / "observations_karelia.parquet"
    disp_path = INGESTION_ROOT / "source_dispositions_karelia.parquet"
    legacy = pd.read_parquet(legacy_path)
    legacy = legacy[legacy.region_raw.astype("string").str.contains("карелия", case=False, na=False)].copy()
    if not pilot_path.is_file() or not disp_path.is_file():
        # Portable R4 runner: preserve the full raw replay as immutable registry
        # history, while the audited snapshot alone determines selected rows.
        raw_path = ROOT / "research_audit/evidence/replayed_observations.parquet"
        if not raw_path.is_file():
            raise FileNotFoundError("portable registry requires the declared replayed_observations.parquet baseline")
        raw = pd.read_parquet(raw_path)
        raw = raw[raw.region_raw.astype("string").str.contains("карелия", case=False, na=False)].copy()
        expected_source_ids = set(legacy.source_record_id.astype(str)) | set(raw.source_record_id.astype(str))
        combined = pd.concat([legacy, raw], ignore_index=True, sort=False)
        for source_id, rows in combined[combined.source_record_id.astype(str).duplicated(keep=False)].groupby(combined.source_record_id.astype(str)):
            for field in ("census_year", "population", "settlement_name", "settlement_type"):
                if field in rows and rows[field].dropna().astype(str).nunique() > 1:
                    raise ValueError(f"baseline/raw immutable source observation disagreement {source_id}:{field}")
        combined = combined.drop_duplicates("source_record_id", keep="first").copy()
        if set(combined.source_record_id.astype(str)) != expected_source_ids:
            raise ValueError("portable registry lost or introduced a source ID while merging raw replay and selected snapshot")
        combined["observation_id"] = combined.source_record_id.map(lambda x: stable_id("OBS", x))
        selection_source = legacy.copy()
        selection_source["observation_id"] = selection_source.source_record_id.map(lambda x: stable_id("OBS", x))
        selection = selection_source[[c for c in ["source_record_id", "observation_id", "census_year", "source_file", "source_sha256", "source_sheet", "source_row", "source_native_id", "population"] if c in selection_source]].copy()
        selection["release_id"] = "karelia-case-review-r1"
        selection["selected_for_release"] = True
        selection["row_status"] = "selected_in_baseline_snapshot"
        return combined, selection
    pilot = pd.read_parquet(pilot_path)
    # Both source versions remain addressable. Identical source record keys may
    # occur in both; reject any silent value rewrite under a stable key.
    combined = pd.concat([legacy, pilot], ignore_index=True, sort=False)
    duplicate_ids = set(combined.loc[combined.source_record_id.astype(str).duplicated(keep=False), "source_record_id"].astype(str))
    for source_id in duplicate_ids:
        rows = combined[combined.source_record_id.astype(str).eq(source_id)]
        for field in ("census_year", "population", "settlement_name", "settlement_type"):
            values = set(rows[field].dropna().astype(str)) if field in rows else set()
            if len(values) > 1:
                raise ValueError(f"immutable observation conflict for {source_id}: {field}={values}")
    combined = combined.drop_duplicates("source_record_id", keep="first").copy()
    combined["observation_id"] = combined.source_record_id.map(lambda x: stable_id("OBS", x))
    disp = pd.read_parquet(disp_path)
    chosen = disp[disp.snapshot_included.eq(True)].copy()
    chosen = chosen[chosen.observation_source_record_id.notna()].copy()
    mapping = chosen[["observation_source_record_id", "census_year", "source_path", "source_sha256", "source_sheet", "source_row",
        "source_name_or_row_text", "source_population_parsed", "row_status", "disposition_reason"]].rename(columns={
            "observation_source_record_id": "source_record_id", "source_population_parsed": "selected_source_population"})
    mapping["observation_id"] = mapping.source_record_id.map(lambda x: stable_id("OBS", x))
    mapping["release_id"] = "karelia-case-review-r1"
    mapping["selected_for_release"] = True
    return combined, mapping


def load_primary_2010_observations() -> tuple[pd.DataFrame, dict]:
    """Validate and normalize the fresh, source-backed official 2010 extraction."""
    candidates = [OUT_ROOT / "ingestion/karelia_2010_fresh_primary_observations.parquet"]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError("fresh 2010 primary extraction is missing; run the fresh source parser into output-root/ingestion")
    frame = pd.read_parquet(path)
    if len(frame) != 800 or frame.source_record_id.duplicated().any() or not frame.census_year.eq(2010).all():
        raise ValueError("fresh 2010 source row identity/year checks failed")
    if int(frame.population.sum()) != 643_548:
        raise ValueError("fresh 2010 source sum does not match 643,548")
    urban = frame.source_role.eq("official_rosstat_volume_1_table_5_urban")
    rural = frame.source_role.eq("official_regional_census_rural")
    if int(urban.sum()) != 24 or int(rural.sum()) != 776:
        raise ValueError("fresh 2010 source must contain 24 urban and 776 rural rows")
    if int(frame.loc[urban, "population"].sum()) != 502_217 or int(frame.loc[rural, "population"].sum()) != 141_331:
        raise ValueError("fresh 2010 urban/rural subtotals do not match source controls")
    canonical_hash = canonical_primary_source_hash(frame)
    if canonical_hash != "be3c0bf3f1871923d91eec684a9fde2769b70ef40749510f6e79171c7e791524":
        raise ValueError(f"fresh 2010 canonical typed content hash mismatch: {canonical_hash}")
    receipt_path = OUT_ROOT / "ingestion/run_receipt.json"
    receipt_sidecar = receipt_path.with_suffix(".json.sha256")
    if not receipt_path.is_file() or not receipt_sidecar.is_file():
        raise FileNotFoundError("fresh extraction run_receipt.json and SHA-256 sidecar are required")
    receipt_sha = sha256(receipt_path)
    sidecar_sha_text = receipt_sidecar.read_text(encoding="utf-8").strip().split()[0]
    if sidecar_sha_text != receipt_sha:
        raise ValueError("fresh extraction run receipt does not match its SHA-256 sidecar")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_output = next((item for item in receipt.get("outputs", [])
                           if item.get("path") == path.name), None)
    if (receipt.get("status") != "complete" or receipt.get("canonical_parquet_content_sha256")
            != "311aab369179fec034ef0abee81740f8c76e029cb99c7ea3dc6f79e59f11ee83"
            or receipt.get("output_row_count") != 800 or receipt.get("output_population") != 643548
            or receipt_output is None or receipt_output.get("sha256") != sha256(path)
            or receipt_output.get("bytes") != path.stat().st_size):
        raise ValueError("fresh extraction receipt does not certify the required R4b source output")
    facts_candidates = [OUT_ROOT / "ingestion/rural_source_extraction/karelia_2010_rural_docx_source_facts.json",
                        OUT_ROOT / "ingestion/karelia_2010_rural_docx_source_facts.json",
                        INGESTION_ROOT / "karelia_2010_rural_docx_source_facts.json"]
    facts_path = next((p for p in facts_candidates if p.is_file()), None)
    facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path else {}
    manifest_path = CODE_ROOT / "research_rebuild/evidence/ingestion/source_manifest_karelia_r4b_fresh_final.json"
    if not manifest_path.is_file() or sha256(manifest_path) != "bdbf48f0a03648a42178e4b786554ea9e047849e75fa78aa239a1e23826021c0":
        raise ValueError("frozen R4b fresh source manifest is missing or fails its SHA-256 receipt")
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("canonical_table_content_sha256") != receipt.get("canonical_parquet_content_sha256"):
        raise ValueError("R4b parser receipt and frozen manifest disagree on canonical source content")
    if (facts.get("source_sha256") not in (None, "dcc79b64b15dc44d62f12868293f8f8dfa124c2d14b2f5f08167b9faefe06a59")
            or facts.get("extractor_code_sha256") != "2b33cb3618e8e4c03dfc3530386845c42b173d82ea1ffdeb5b15c2fb39897876"):
        raise ValueError("fresh DOCX facts differ from the source-verified extraction")
    ledger_candidates = [OUT_ROOT / "ingestion/rural_source_extraction/karelia_2010_rural_docx_source_rows.csv",
                        OUT_ROOT / "ingestion/karelia_2010_rural_docx_source_rows.csv",
                        INPUTS_ROOT / "evidence/ingestion/karelia_2010_rural_docx_source_rows.csv",
                        INGESTION_ROOT / "karelia_2010_rural_docx_source_rows.csv"]
    ledger_path = next((p for p in ledger_candidates if p.is_file()), None)
    if ledger_path is None:
        raise FileNotFoundError("corrected DOCX row-level extraction ledger is missing")
    ledger = pd.read_csv(ledger_path)
    if "source_locator" not in ledger or "row_disposition" not in ledger:
        raise ValueError("corrected DOCX ledger lacks source locator/disposition fields")
    ledger = ledger[ledger.row_disposition.eq("rural_locality_observation")]
    if len(ledger) != 776 or set(frame.loc[rural, "source_locator"].astype(str)) != set(ledger.source_locator.astype(str)):
        raise ValueError("fresh rural observations do not reconcile one-to-one to the corrected DOCX row ledger")
    road_rows = frame[frame.settlement_name.astype("string").str.contains("Дороги Кемь-Калевала", case=False, regex=False, na=False)]
    if len(road_rows) != 2 or set(pd.to_numeric(road_rows.population).astype(int)) != {4, 584} or not road_rows.settlement_name.str.contains(r"(?:6 км|14 км)", regex=True, case=False).all():
        raise ValueError("smartTag road names/values are missing from fresh DOCX output")
    allowed_paths = {"evidence/ingestion/source/karelia_2010_rural_settlements.docx",
                     "data/raw/2010_official_tom11/pub-11-1-4.pdf"}
    if set(frame.source_path.astype(str)) - allowed_paths:
        raise ValueError("fresh source observations contain an unpinned logical source locator")
    if "source_path" in frame:
        frame = frame.rename(columns={"source_path": "source_file"})
    if "source_population_raw" in frame:
        frame = frame.rename(columns={"source_population_raw": "source_name_raw"})
    elif "source_population_raw" not in frame and "source_name_raw" not in frame:
        frame["source_name_raw"] = frame.get("source_population_reference", frame.settlement_name)
    frame["source_record_id_upstream"] = frame.source_record_id.astype(str)
    frame["source_extraction_version"] = frame.source_role.map(
        lambda role: "karelia-rural-docx-xml-visible-text-v2" if role == "official_regional_census_rural" else "rosstat-volume1-table5-reference-v1")
    is_rural = frame.source_role.eq("official_regional_census_rural")
    frame.loc[is_rural, "source_record_id"] = frame.loc[is_rural].apply(
        lambda row: f"{row.source_record_id}:extractor=karelia-rural-docx-xml-visible-text-v2", axis=1)
    frame["source_sheet"] = frame.source_role
    frame["source_row"] = frame.source_locator
    frame["source_native_id"] = frame.source_population_reference
    frame["district_raw"] = frame.district_context_raw
    frame["municipality_raw"] = frame.municipality_context_raw
    frame["region_raw"] = frame.region_raw.fillna("Республика Карелия")
    frame["coordinate_quality"] = pd.NA
    frame["coverage_status"] = frame.source_role
    frame["extractor_id"] = frame.source_role.map(lambda role: "karelia-rural-docx-xml-visible-text-v2" if role == "official_regional_census_rural" else "rosstat-volume1-table5-reference-v1")
    frame["extractor_code_sha256"] = frame.source_role.map(lambda role: facts.get("extractor_code_sha256") if role == "official_regional_census_rural" else pd.NA)
    frame["coordinate_source"] = pd.NA
    frame["latitude"] = pd.NA
    frame["longitude"] = pd.NA
    frame["additive_snapshot_status"] = "selected_in_primary2010_release"
    frame["region_norm"] = "карелия"
    frame["district_norm"] = frame.district_raw
    frame["municipality_norm"] = frame.municipality_raw
    frame["derivation_note"] = frame.source_population_reference
    frame["selection_extractor_id"] = "karelia-primary-value-selection-v2"
    return frame, {
        "proposal_path": artifact_path(path), "proposal_sha256_binary": sha256(path),
        "proposal_sha256_canonical_typed_content": canonical_hash,
        "parser_canonical_pre_parquet_sha256": receipt["canonical_parquet_content_sha256"],
        "parser_run_receipt_path": artifact_path(receipt_path), "parser_run_receipt_sha256": receipt_sha,
        "source_manifest_path": artifact_path(manifest_path), "source_manifest_sha256": sha256(manifest_path),
        "source_docx_sha256": "dcc79b64b15dc44d62f12868293f8f8dfa124c2d14b2f5f08167b9faefe06a59",
        "extractor_version": "karelia-rural-docx-xml-visible-text-v2", "extractor_code_sha256": facts.get("extractor_code_sha256"),
        "extractor_config_sha256": facts.get("extractor_config_sha256"),
        "row_ledger_path": artifact_path(ledger_path), "row_ledger_sha256": sha256(ledger_path),
        "extraction_locality_rows": len(ledger), "primary_rows": len(frame),
        "primary_population": int(frame.population.sum()), "urban_rows": int(urban.sum()), "rural_rows": int(rural.sum()),
        "rural_transport_status": facts.get("download_transport_status"),
        "source_selection_version": "karelia-2010-primary-source-r4-fresh-v2",
    }


def load_superseded_primary_2010_v1() -> pd.DataFrame:
    """Retain the prior name-loss extraction as superseded, immutable evidence."""
    candidates = [INGESTION_ROOT / "karelia_2010_primary_value_selection_v1_name_loss_superseded.parquet",
                  INPUTS_ROOT / "evidence/ingestion/karelia_2010_primary_value_selection_v1_name_loss_superseded.parquet"]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None or sha256(path) != "723e20cf795dac2894c2e322d7d15faa59a1deb94bb88b7990a8761b538665f0":
        raise ValueError("superseded DOCX v1 artifact is missing or fails the pinned source bundle checksum")
    frame = pd.read_parquet(path)
    if len(frame) != 800 or frame.source_record_id.duplicated().any():
        raise ValueError("superseded DOCX v1 layer no longer has its original 800 unique rows")
    frame["source_record_id_upstream"] = frame.source_record_id.astype(str)
    frame["source_extraction_version"] = frame.source_role.map(
        lambda role: "karelia-rural-docx-python-docx-v1-name-loss" if role == "official_regional_census_rural" else "rosstat-volume1-table5-reference-v1")
    is_rural = frame.source_role.eq("official_regional_census_rural")
    frame.loc[is_rural, "source_record_id"] = frame.loc[is_rural].apply(
        lambda row: f"{row.source_record_id}:extractor=karelia-rural-docx-python-docx-v1-name-loss", axis=1)
    frame = frame[is_rural].copy()  # The unchanged Table 5 references have a stable, unversioned source identity.
    frame = frame.rename(columns={"source_path": "source_file", "source_population_raw": "source_name_raw"})
    frame["source_sheet"] = frame.source_role
    frame["source_row"] = frame.source_locator
    frame["source_native_id"] = frame.source_population_reference
    frame["district_raw"] = frame.district_context_raw
    frame["municipality_raw"] = frame.municipality_context_raw
    frame["coordinate_quality"] = pd.NA
    frame["coverage_status"] = frame.source_role
    frame["extractor_id"] = "karelia-rural-docx-python-docx-v1-name-loss"
    frame["extractor_code_sha256"] = pd.NA
    frame["coordinate_source"] = pd.NA
    frame["latitude"] = pd.NA
    frame["longitude"] = pd.NA
    frame["additive_snapshot_status"] = "superseded_extraction_preserved_not_selected"
    frame["region_norm"] = "карелия"
    frame["selection_extractor_id"] = "karelia-primary-value-selection-v1-superseded"
    frame["observation_supersession_status"] = "superseded_name_loss_smarttag_prefix"
    return frame


def primary_2010_selection_inputs(observations: pd.DataFrame, registry: pd.DataFrame,
                                 legacy_selection_map: pd.DataFrame, release_name: str
                                 ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Create the R4 selected slice, append-only observation versions and source-selection assertions."""
    v2, source_manifest = load_primary_2010_observations()
    v1 = load_superseded_primary_2010_v1()
    old_selected = observations[observations.census_year.eq(2010)].copy()
    new_selected = v2.copy()
    active = pd.concat([observations[~observations.census_year.eq(2010)], new_selected], ignore_index=True, sort=False)
    if "source_row" in active:
        active["source_row"] = active.source_row.astype("string")
    if active.source_record_id.duplicated().any():
        raise ValueError("selected R4 observation source IDs are not unique")
    if len(active) != 2_444 or active.census_year.value_counts().to_dict() != {2002: 799, 2010: 800, 2021: 845}:
        raise ValueError("R4 selected slice must be 799 (2002) + 800 (2010) + 845 (2021) observations")
    old_registry_ids = set(registry.source_record_id.astype(str))
    new_rows = pd.concat([v1, v2], ignore_index=True, sort=False)
    new_rows = new_rows[~new_rows.source_record_id.astype(str).isin(old_registry_ids)].copy()
    registry = pd.concat([registry, new_rows], ignore_index=True, sort=False)
    if "source_row" in registry:
        registry["source_row"] = registry.source_row.astype("string")
    if registry.source_record_id.duplicated().any():
        raise ValueError("append-only R4 registry contains duplicate extraction-version IDs")

    selection = legacy_selection_map.copy()
    selection = selection[selection.census_year.ne(2010)].copy()
    selection["selected_for_release"] = True
    selection["selection_version"] = "karelia-primary-selection-r4"
    selection["selection_reason"] = "Prior row-level source disposition retained; 2002/2021 slice unchanged from R3."
    prior_2010 = legacy_selection_map[legacy_selection_map.census_year.eq(2010)].copy()
    prior_2010["selected_for_release"] = False
    prior_2010["selection_version"] = "karelia-primary-selection-r4"
    prior_2010["selection_reason"] = "Preserved secondary/legacy observation; superseded in the 2010 release value layer by official primary Table 5 + regional rural publication."
    prior_2010["selection_status"] = "secondary_not_selected_for_r4"
    old_selection_assertions = prior_2010.copy()

    v1_selection = v1[["source_record_id", "source_record_id_upstream", "census_year", "source_file",
                       "source_sha256", "source_sheet", "source_row", "source_name_raw", "population",
                       "source_extraction_version"]].copy()
    v1_selection["observation_id"] = v1_selection.source_record_id.map(lambda x: stable_id("OBS", x))
    v1_selection["selected_for_release"] = False
    v1_selection["selection_version"] = "karelia-primary-selection-r4"
    v1_selection["selection_status"] = "superseded_extraction_not_selected"
    v1_selection["selection_reason"] = "Prior python-docx extraction dropped smartTag prefixes 6 км/14 км; immutable superseded version retained for lineage."
    v1_selection["release_id"] = release_name

    v2_selection = v2[["source_record_id", "source_record_id_upstream", "census_year", "source_file",
                       "source_sha256", "source_sheet", "source_row", "source_name_raw", "population",
                       "source_extraction_version", "selection_status"]].copy()
    v2_selection["observation_id"] = v2_selection.source_record_id.map(lambda x: stable_id("OBS", x))
    v2_selection["selected_for_release"] = True
    v2_selection["selection_version"] = "karelia-primary-selection-r4"
    v2_selection["selection_reason"] = "Official 2010 Table 5 urban rows and source-verified rural DOCX table 1.8 rows; value selection does not assert cross-source rural identity."
    v2_selection["release_id"] = release_name

    # Keep prior observation records addressable and explicitly mark selection outcome.
    old_selection_assertions["source_record_id_upstream"] = old_selection_assertions.source_record_id.astype(str)
    old_selection_assertions["source_extraction_version"] = "legacy-parser-observation"
    old_selection_assertions["selection_status"] = "secondary_not_selected_for_r4"
    old_selection_assertions["release_id"] = release_name
    source_selection = pd.concat([selection, old_selection_assertions, v1_selection, v2_selection], ignore_index=True, sort=False)
    if "source_row" in source_selection:
        source_selection["source_row"] = source_selection.source_row.astype("string")
    selected_for_release = pd.concat([selection, v2_selection], ignore_index=True, sort=False)
    if "source_row" in selected_for_release:
        selected_for_release["source_row"] = selected_for_release.source_row.astype("string")
    selected_for_release["release_id"] = release_name
    if len(source_selection) != 4_019 or len(v1_selection) != 776 or len(v2_selection) != 800:
        raise ValueError("R4 source-selection ledger has unexpected legacy/v1/v2 record counts")
    if source_selection.source_record_id.duplicated().any():
        raise ValueError("R4 source-selection assertions have duplicate versioned source record IDs")
    selected_assertion_ids = set(source_selection.loc[source_selection.selected_for_release.eq(True), "source_record_id"].astype(str))
    release_selection_ids = set(selected_for_release.loc[selected_for_release.selected_for_release.eq(True), "source_record_id"].astype(str))
    active_ids = set(active.source_record_id.astype(str))
    if selected_assertion_ids != release_selection_ids or active_ids != release_selection_ids or len(release_selection_ids) != 2_444:
        raise ValueError("R4 selected-set identity regression gate failed: selected observation IDs must match release rows exactly")
    expected_registry_ids = old_registry_ids | set(v1.source_record_id.astype(str)) | set(v2.source_record_id.astype(str))
    actual_registry_ids = set(registry.source_record_id.astype(str))
    if actual_registry_ids != expected_registry_ids or len(registry) != registry.source_record_id.nunique():
        raise ValueError("R4 append-only registry does not equal the unique union of baseline, superseded v1 and fresh v2 observation IDs")
    return active, registry, selected_for_release, source_selection, source_manifest


def primary_2010_published_record_bindings(primary_observations: pd.DataFrame, case_observations: pd.DataFrame,
                                           case_identity_events: pd.DataFrame, claims: pd.DataFrame,
                                           review_path: Path, release_name: str
                                           ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Bind reviewed old Table 1.4 city nodes to direct Table 5 rows without population double counting."""
    urban_new = primary_observations[
        primary_observations.census_year.eq(2010)
        & primary_observations.source_role.eq("official_rosstat_volume_1_table_5_urban")
    ].copy()
    old10 = case_observations[case_observations.census_year.eq(2010)].copy()
    obs_by_id = case_observations.set_index("observation_id", drop=False)
    primary_by_key = {}
    for _, row in urban_new.iterrows():
        key = (normalize(row.settlement_name), normalize(row.settlement_type))
        if key in primary_by_key:
            raise ValueError(f"duplicate direct Table 5 urban key in 2010 proposal: {key}")
        primary_by_key[key] = row
    reviewed_ids = set()
    path_to_2021 = {}
    for event in case_identity_events[case_identity_events.decision_type.eq("identity_link")
                                      & case_identity_events.event_action.eq("apply")
                                      & case_identity_events.relation_type.eq("same_place")].itertuples(index=False):
        endpoints = [event.from_observation_id, event.to_observation_id]
        for endpoint in endpoints:
            if endpoint not in obs_by_id.index:
                continue
            old = obs_by_id.loc[endpoint]
            if int(old.census_year) == 2010:
                reviewed_ids.add(endpoint)
                other = endpoints[1] if endpoint == endpoints[0] else endpoints[0]
                if other in obs_by_id.index and int(obs_by_id.loc[other].census_year) == 2021:
                    path_to_2021[endpoint] = event.decision_id
    if len(reviewed_ids) != 10 or set(path_to_2021) != reviewed_ids:
        raise ValueError(f"R4 expected ten already reviewed old-2010→2021 city paths; found {len(reviewed_ids)}")
    review_file_hashes = sorted(set(case_identity_events.loc[
        case_identity_events.decision_id.isin(path_to_2021.values()), "evidence_sha256"].dropna().astype(str)))
    dossier_sha = hashlib.sha256(json.dumps(review_file_hashes, separators=(",", ":")).encode()).hexdigest()
    events, bindings, derived_claims = [], [], []
    for old_id in sorted(reviewed_ids):
        old = obs_by_id.loc[old_id]
        key = (normalize(old.settlement_name), normalize(old.settlement_type))
        if key not in primary_by_key:
            raise ValueError(f"reviewed city has no unique primary Table 5 row: {key}")
        new = primary_by_key[key]
        if int(old.population) != int(new.population) or normalize(old.population_scope) != "settlement":
            raise ValueError(f"published Table 1.4/Table 5 population or settlement-only scope conflict for reviewed city: {old.settlement_name}")
        if int(new.men) + int(new.women) != int(new.population):
            raise ValueError(f"Table 5 sex subtotals do not reconcile for reviewed city: {old.settlement_name}")
        prior_edge = case_identity_events[case_identity_events.decision_id.eq(path_to_2021[old_id])].iloc[0]
        prior_evidence = json.loads(prior_edge.evidence_uri) if isinstance(prior_edge.evidence_uri, str) else {}
        prior_review_file = prior_evidence.get("review_file", prior_evidence.get("review_dossier"))
        prior_review_sha = prior_evidence.get("review_sha256", prior_evidence.get("review_sha256"))
        decision_id = stable_id("PUBLISHED-BINDING", f"{old_id}|{new.observation_id}|{new.source_population_reference}|{path_to_2021[old_id]}")
        event = {
            "decision_id": decision_id, "candidate_id": stable_id("CASE-BINDING", f"{old_id}|{new.observation_id}"),
            "event_order": 4, "event_action": "apply", "decision_type": "identity_link",
            "relation_type": "same_place", "observation_id": pd.NA,
            "from_observation_id": old.observation_id, "to_observation_id": new.observation_id,
            "place_id": pd.NA, "coordinate_claim_id": pd.NA, "decision_class": "rule",
            "decision_status": "case_specific_published_record_binding",
            "decision_rule": "rosstat_same_census_published_table_binding_v1",
            "evidence_uri": json.dumps({
                "old_published_record": {"source_record_id": old.source_record_id, "source_file": old.source_file,
                    "source_sha256": old.source_sha256, "locator": old.source_native_id,
                    "table": "2010 Rosstat Volume 1 Table 1.4", "population": int(old.population)},
                "new_published_record": {"source_record_id": new.source_record_id, "source_file": new.source_file,
                    "source_sha256": new.source_sha256, "locator": new.source_locator,
                    "table": "2010 Rosstat Volume 1 Table 5", "population": int(new.population),
                    "men": int(new.men), "women": int(new.women)},
                "same_publication_reference": "Both are settlement-level results of the 2010 census in Rosstat Volume 1; direct row label, settlement type and population agree.",
                "prior_review_path_decision_id": path_to_2021[old_id],
                "prior_case_review_file": prior_review_file, "prior_case_review_sha256": prior_review_sha,
                "case_review_evidence_bundle_sha256": dossier_sha,
                "selection_version": "karelia-primary-selection-r4",
            }, ensure_ascii=False),
            "evidence_sha256": dossier_sha, "evidence_source": "two direct same-census Rosstat published settlement rows + already reviewed identity path",
            "rationale": "Case-specific published-record binding; one canonical selected Table 5 observation replaces the Table 1.4 population record in the release. This does not duplicate the population or admit coordinates directly.",
            "reviewer": "documentary cross-table binding over independent case review", "reviewed_at": "2026-09-29",
            "supersedes_decision_id": pd.NA,
        }
        events.append(event)
        bindings.append({"binding_decision_id": decision_id, "binding_status": "applied_case_specific",
            "old_observation_id": old.observation_id, "old_source_record_id": old.source_record_id,
            "new_observation_id": new.observation_id, "new_source_record_id": new.source_record_id,
            "settlement_name": old.settlement_name, "settlement_type": old.settlement_type,
            "population": int(new.population), "old_source_table": "Rosstat Volume 1 Table 1.4",
            "new_source_table": "Rosstat Volume 1 Table 5", "new_source_locator": new.source_locator,
            "old_source_sha256": old.source_sha256, "new_source_sha256": new.source_sha256,
            "depends_on_reviewed_identity_decision_id": path_to_2021[old_id],
            "prior_case_review_file": prior_review_file, "prior_case_review_sha256": prior_review_sha,
            "population_entity_year_count": 1, "selection_version": "karelia-primary-selection-r4"})

        # Historical coordinates continue to depend on the reviewed new-year path,
        # and now also on this published-record binding to the selected observation.
        old_hist_events = case_identity_events
        old_coordinate_event = None
        for candidate in old_hist_events[old_hist_events.decision_type.eq("coordinate_admission")
                                         & old_hist_events.event_action.eq("apply")
                                         & old_hist_events.observation_id.eq(old.observation_id)].itertuples(index=False):
            if candidate.decision_class == "inferred_continuity":
                old_coordinate_event = candidate
                break
        if old_coordinate_event is None:
            raise ValueError(f"reviewed old 2010 historical coordinate event missing for {old.settlement_name}")
        parent_claim = claims[claims.coordinate_claim_id.eq(old_coordinate_event.coordinate_claim_id)]
        if len(parent_claim) != 1:
            raise ValueError(f"reviewed old 2010 coordinate claim missing for {old.settlement_name}")
        claim = parent_claim.iloc[0].to_dict()
        new_claim_id = stable_id("COORD-PUBLISHED-BINDING", f"{claim['coordinate_claim_id']}|{new.observation_id}")
        claim.update({"coordinate_claim_id": new_claim_id, "observation_id": new.observation_id,
            "source_record_id": new.source_record_id, "census_year": 2010,
            "claim_origin": "inferred_continuity_via_same_census_published_record_binding",
            "derived_from_coordinate_claim_id": claim.get("derived_from_coordinate_claim_id") or claim["coordinate_claim_id"],
            "admission_status": "unresolved", "admission_class": "inferred_continuity",
            "admission_reason": "Current point carried through reviewed 2010 same-place path and direct Table 1.4/Table 5 record binding; no direct historic coordinate.",
            "admission_rule": "rosstat_same_census_published_table_binding_v1",
            "temporal_applicability": "inferred_continuity; coordinate measured in source date unknown; 2010 link is not a dated 2010 coordinate"})
        derived_claims.append(claim)
        events.append({
            "decision_id": stable_id("COORD-PUBLISHED-BINDING", f"{new_claim_id}|{decision_id}|{dossier_sha}"),
            "candidate_id": event["candidate_id"], "event_order": 5, "event_action": "apply",
            "decision_type": "coordinate_admission", "relation_type": pd.NA,
            "observation_id": new.observation_id, "from_observation_id": new.observation_id,
            "to_observation_id": pd.NA, "place_id": new.provisional_place_id,
            "coordinate_claim_id": new_claim_id, "decision_class": "inferred_continuity",
            "decision_status": "case_specific_inferred_coordinate_binding",
            "decision_rule": "rosstat_same_census_published_table_binding_v1",
            "temporal_applicability": "inferred_continuity; coordinate measured in source date unknown; no direct 2010 coordinate source",
            "depends_on_identity_decision_ids": json.dumps([path_to_2021[old_id], decision_id]),
            "parent_coordinate_claim_id": claim["derived_from_coordinate_claim_id"],
            "evidence_uri": event["evidence_uri"], "evidence_sha256": dossier_sha,
            "evidence_source": "reviewed 2010→2021 place link + same-census published record binding + 2021 point evidence",
            "rationale": "Coordinate remains an explicit temporal continuity inference, not a direct 2010 coordinate admission.",
            "reviewer": "documentary cross-table binding over independent case review", "reviewed_at": "2026-09-29",
            "supersedes_decision_id": pd.NA,
        })
    if len(bindings) != 10:
        raise ValueError("R4 must bind exactly ten reviewed urban cases; refusing silent partial link")
    return pd.DataFrame(events), pd.DataFrame(bindings), pd.DataFrame(derived_claims)
def load_wikidata_evidence(observations: pd.DataFrame) -> pd.DataFrame:
    path = INPUTS_ROOT / "processed_inputs/karelia_master_2021_evidence.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"required hashed 2021 Wikidata evidence projection is absent: {artifact_path(path)}")
    m = pd.read_parquet(path)
    fields = ["source_record_id", "settlement_id", "source_dataset_url", "wikidata_id",
              "wikidata_match_method", "wikidata_match_accepted", "wikidata_candidate_name_agrees",
              "wikidata_label_ru", "wikipedia_url_ru", "wikidata_latitude", "wikidata_longitude",
              "wikidata_admin_label_ru", "coordinate_quality", "population_scope", "oktmo", "okato"]
    fields = [c for c in fields if c in m.columns]
    w = m[fields].copy()
    id_path = INPUTS_ROOT / "processed_inputs/karelia_2021_identifier_evidence.parquet"
    if id_path.exists():
        ids = pd.read_parquet(id_path)
        keep = [c for c in ["source_record_id", "source_dataset_url", "identifier_semantics"] if c in ids.columns]
        ids = ids[keep].drop_duplicates("source_record_id", keep=False)
        if "source_dataset_url" not in w.columns:
            w = w.merge(ids, on="source_record_id", how="left", validate="one_to_one")
    # The source identifier must point to one and only one 2021 row.
    w = w.drop_duplicates("source_record_id", keep=False)
    years = observations[["source_record_id", "census_year"]].copy()
    years = years[years.census_year.eq(2021)]
    return years.merge(w, on="source_record_id", how="left", validate="one_to_one")


def attach_source_hashes(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    if "source_sha256" not in out:
        out["source_sha256"] = pd.NA
    manifest_candidates = [ROOT / "research_audit/output/input_manifest.parquet",
                           CODE_ROOT / "research_rebuild/evidence/ingestion/source_manifest_karelia_r4_fresh.json"]
    source_map = {}
    input_manifest = next((p for p in manifest_candidates if p.is_file() and p.suffix == ".parquet"), None)
    if input_manifest:
        m = pd.read_parquet(input_manifest)
        if {"path", "sha256"}.issubset(m.columns):
            source_map.update(m.drop_duplicates("path", keep=False).set_index("path").sha256.astype(str).to_dict())
    method_manifest = manifest_candidates[-1]
    if method_manifest.is_file():
        for entry in json.loads(method_manifest.read_text(encoding="utf-8")):
            if entry.get("role") == "raw_primary_or_secondary_source":
                source_map[entry["path"]] = entry["sha256"]
    if "source_file" in out and source_map:
        out["source_sha256"] = out.source_sha256.where(out.source_sha256.notna(), out.source_file.map(source_map))
    return out


def write_table(frame: pd.DataFrame, name: str, csv: bool = False):
    frame.to_parquet(OUT / f"{name}.parquet", index=False)
    if csv:
        frame.to_csv(OUT / f"{name}.csv", index=False)


def make_review_batch(proposals: pd.DataFrame, observations: pd.DataFrame, n: int = 100) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare a deterministic blind batch and a separate prediction key."""
    if proposals.empty:
        return proposals.copy(), proposals.copy()
    source = observations.set_index("observation_id")
    eligible = proposals[proposals.event_action.eq("propose")].copy()
    # Stable SHA order is reproducible and independent of population/model score.
    eligible["_sample_key"] = eligible.observation_id.map(lambda x: hashlib.sha256(str(x).encode()).hexdigest())
    sample = eligible.sort_values("_sample_key").head(min(n, len(eligible))).copy()
    hidden = sample[["decision_id", "observation_id", "decision_status", "decision_class", "decision_rule"]].copy()
    sample = sample.merge(observations[["observation_id", "source_record_id", "census_year", "settlement_name",
        "settlement_type", "region_raw", "district_raw", "municipality_raw", "population", "latitude", "longitude",
        "coordinate_source", "coordinate_quality", "source_file", "source_sheet", "source_row", "source_sha256"]],
        on="observation_id", how="left", validate="one_to_one")
    # Keep the reviewer blind to the outcome/rule. Preserve citations and source
    # fields needed to inspect the item itself.
    wiki = load_wikidata_evidence(observations)
    evidence_cols = [c for c in ["source_record_id", "wikidata_id", "wikidata_label_ru", "wikipedia_url_ru",
        "wikidata_latitude", "wikidata_longitude", "wikidata_admin_label_ru", "wikidata_match_method",
        "source_dataset_url"] if c in wiki.columns]
    sample = sample.merge(wiki[evidence_cols].drop_duplicates("source_record_id", keep=False),
                          on="source_record_id", how="left", validate="many_to_one")
    sample["review_key"] = sample.decision_id.map(lambda x: stable_id("REVIEW", x))
    blind_cols = ["review_key", "observation_id", "source_record_id", "census_year", "settlement_name", "settlement_type",
        "region_raw", "district_raw", "municipality_raw", "population", "latitude", "longitude", "coordinate_source",
        "coordinate_quality", "source_file", "source_sheet", "source_row", "source_sha256", "wikidata_id",
        "wikidata_label_ru", "wikipedia_url_ru", "wikidata_latitude", "wikidata_longitude", "wikidata_admin_label_ru",
        "wikidata_match_method", "source_dataset_url"]
    return sample[[c for c in blind_cols if c in sample.columns]], hidden


def karelia_population_fingerprint(observations: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build three-date identity candidates corroborated by dated Wikidata P1082.

    This is intentionally a candidate family, never automatic identity
    acceptance. Its 2002 rows are the selected census snapshot, while raw
    alternative urban rows are accounted in a separate source-overlap table.
    """
    k = observations[observations.region_key.eq("карелия")].copy()
    k = k[k.census_year.isin([2002, 2010, 2021])]
    keys = ["region_key", "type_key", "name_key"]
    counts = k.groupby(keys + ["census_year"]).size().rename("n").reset_index()
    counts = counts[counts.n.eq(1)]
    complete_keys = counts.groupby(keys).census_year.nunique()
    complete_keys = complete_keys[complete_keys.eq(3)].reset_index()[keys]
    k = k.merge(complete_keys, on=keys, how="inner", validate="many_to_one")
    if k.empty:
        empty = pd.DataFrame()
        return empty, empty, empty
    a = load_wikidata_evidence(observations)
    a = a[a.census_year.eq(2021)][["source_record_id", "wikidata_id", "wikidata_match_method",
         "wikidata_match_accepted", "wikidata_candidate_name_agrees", "wikipedia_url_ru", "wikidata_latitude",
         "wikidata_longitude", "wikidata_admin_label_ru"]].copy()
    # Require the current census anchor to have a unique, exact identifier
    # resolution; historical identity still remains a proposal for review.
    a = a[a.wikidata_match_method.eq("exact_oktmo_okato_agree") & a.wikidata_match_accepted.eq(True)
          & a.wikidata_candidate_name_agrees.eq(True)]
    a = a.drop_duplicates("source_record_id", keep=False).drop_duplicates("wikidata_id", keep=False)
    latest = k[k.census_year.eq(2021)].merge(a, on="source_record_id", how="inner", validate="one_to_one")
    if latest.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    qids = set(latest.wikidata_id)
    population_claims_path = INPUTS_ROOT / "processed_inputs/karelia_wikidata_population_claims.parquet"
    if not population_claims_path.is_file():
        raise FileNotFoundError(f"required hashed Wikidata population claim evidence is absent: {artifact_path(population_claims_path)}")
    p = pd.read_parquet(population_claims_path)
    p = p[p.wikidata_id.isin(qids) & p.year.astype("string").isin(["2002", "2010", "2021"])].copy()
    p["year"] = pd.to_numeric(p.year, errors="coerce").astype("int16")
    p["population"] = pd.to_numeric(p.population, errors="coerce")
    pv = p.groupby(["wikidata_id", "year"]).population.agg(lambda s: sorted(set(s.dropna()))).reset_index()
    pv["unique_population"] = pv.population.map(lambda vals: vals[0] if len(vals) == 1 else None)
    pv["population_claims"] = pv.population.map(lambda vals: json.dumps(vals))
    pw = pv.pivot(index="wikidata_id", columns="year", values="unique_population").reset_index()
    pw = pw.rename(columns={y: f"wikidata_population_{y}" for y in [2002, 2010, 2021] if y in pw.columns})
    ps = p.groupby(["wikidata_id", "year"]).wikidata_statement_id.agg(lambda s: sorted(set(s.dropna().astype(str)))).reset_index()
    ps["statement_ids"] = ps.wikidata_statement_id.map(lambda vals: json.dumps(vals))
    psw = ps.pivot(index="wikidata_id", columns="year", values="statement_ids").reset_index()
    psw = psw.rename(columns={y: f"statement_ids_{y}" for y in [2002, 2010, 2021] if y in psw.columns})
    wide = k.pivot(index=keys, columns="census_year", values=["observation_id", "source_record_id", "population", "source_file", "source_sheet", "source_row", "latitude", "longitude", "coordinate_source", "coordinate_quality", "population_scope"])
    wide.columns = [f"{col}_{year}" for col, year in wide.columns]
    wide = wide.reset_index().merge(latest[keys + ["wikidata_id", "wikipedia_url_ru", "wikidata_latitude", "wikidata_longitude", "wikidata_admin_label_ru"]], on=keys, how="inner", validate="one_to_one")
    wide = wide.merge(pw, on="wikidata_id", how="left", validate="one_to_one").merge(psw, on="wikidata_id", how="left", validate="one_to_one")
    for year in [2002, 2010, 2021]:
        observed = pd.to_numeric(wide[f"population_{year}"], errors="coerce")
        wpop = pd.to_numeric(wide[f"wikidata_population_{year}"], errors="coerce") if f"wikidata_population_{year}" in wide else pd.Series(pd.NA, index=wide.index)
        wide[f"population_claim_matches_{year}"] = observed.eq(wpop) & wpop.notna()
    mask = wide[[f"population_claim_matches_{y}" for y in [2002, 2010, 2021]]].all(axis=1)
    candidates = wide[mask].copy()
    candidates["candidate_id"] = candidates.apply(lambda r: stable_id("KARELIA-IDENTITY", "|".join(str(r[f"observation_id_{y}"]) for y in [2002, 2010, 2021])), axis=1)
    candidates["candidate_status"] = "pending_blind_review"
    candidates["evidence_class"] = "rule"
    candidates["evidence_basis"] = "unique exact region/type/name + exact dated P1082 values for all 3 selected census observations + unique exact 2021 OKTMO/OKATO QID route"
    candidates["wikidata_url"] = candidates.wikidata_id.map(lambda q: f"https://www.wikidata.org/wiki/{q}")
    candidates["rosstat_2010_pdf"] = "https://rosstat.gov.ru/free_doc/new_site/perepis2010/croc/Documents/Vol11/pub-11-1-4.pdf"
    candidates["tochno_2021_dataset"] = "https://tochno.st/datasets/allsettlements"
    candidates["lingvarium_2002_catalog"] = "https://www.lingvarium.org/russia/Census2002.shtml"
    candidates["source_linkage_caveat"] = "Wikidata and census records can share a Rosstat upstream source; identity and continuity are still pending independent review."
    official_ref_path = ROOT / "research_audit/output/official_2010_table5_reference.parquet"
    if official_ref_path.exists():
        refs = pd.read_parquet(official_ref_path)
        refs = refs[refs.row_kind.eq("settlement")].copy()
        refs["name_key"] = refs.settlement_name.map(lambda x: " ".join(str(x).casefold().replace("ё", "е").split()))
        refs["type_key"] = refs.settlement_type.map(lambda x: " ".join(str(x).casefold().replace("ё", "е").split()))
        refs["region_key"] = refs.region_raw.map(lambda x: " ".join(str(x).casefold().replace("ё", "е").split()).removeprefix("республика "))
        refs = refs[["name_key", "type_key", "region_key", "reference_id", "pdf_page", "printed_page", "label_raw", "population"]].rename(columns={
            "reference_id": "rosstat2010_reference_id", "pdf_page": "rosstat2010_pdf_page", "printed_page": "rosstat2010_printed_page",
            "label_raw": "rosstat2010_label", "population": "rosstat2010_population"})
        # Keep only a unique primary-source row whose value matches the 2010
        # census observation; the reference is explicitly incomplete overall.
        refs = refs.drop_duplicates(["name_key", "type_key", "region_key"], keep=False)
        candidates = candidates.merge(refs, on=keys, how="left", validate="many_to_one")
        candidates["rosstat2010_population_matches"] = pd.to_numeric(candidates.population_2010, errors="coerce").eq(pd.to_numeric(candidates.rosstat2010_population, errors="coerce"))
    else:
        candidates["rosstat2010_reference_id"] = pd.NA
        candidates["rosstat2010_pdf_page"] = pd.NA
        candidates["rosstat2010_printed_page"] = pd.NA
        candidates["rosstat2010_label"] = pd.NA
        candidates["rosstat2010_population"] = pd.NA
        candidates["rosstat2010_population_matches"] = False
    candidates = candidates.sort_values(["population_2021", "candidate_id"], ascending=[False, True]).reset_index(drop=True)
    # Blind batch is deterministic, stratified by population quintile, and
    # contains source evidence without predicted status, rule, or rationale.
    candidates["review_hash"] = candidates.candidate_id.map(lambda x: hashlib.sha256(str(x).encode()).hexdigest())
    selected_parts=[]
    if len(candidates) <= 100:
        selected = candidates
    else:
        candidates["population_decile"] = pd.qcut(candidates.population_2021.rank(method="first"), 10, labels=False)
        selected = candidates.groupby("population_decile", group_keys=False).apply(
            lambda g: g.sort_values("review_hash").head(10)
        ).reset_index(drop=True)
    review = selected.copy()
    review["review_key"] = review.candidate_id.map(lambda x: stable_id("REVIEW", x))
    # Remove model-derived fields and keep citations/observed values visible.
    blind_columns = ["review_key", "name_key", "type_key", "region_key", "wikidata_id", "wikidata_url", "wikipedia_url_ru",
        "wikidata_latitude", "wikidata_longitude", "wikidata_admin_label_ru",
        "population_2002", "population_2010", "population_2021",
        "wikidata_population_2002", "wikidata_population_2010", "wikidata_population_2021", "statement_ids_2002", "statement_ids_2010", "statement_ids_2021",
        "source_record_id_2002", "source_record_id_2010", "source_record_id_2021",
        "source_file_2002", "source_file_2010", "source_file_2021", "source_sheet_2002", "source_sheet_2010", "source_sheet_2021",
        "source_row_2002", "source_row_2010", "source_row_2021", "lingvarium_2002_catalog", "rosstat_2010_pdf", "tochno_2021_dataset"]
    blind_columns += ["latitude_2021", "longitude_2021", "coordinate_source_2021", "coordinate_quality_2021", "population_scope_2021",
        "rosstat2010_reference_id", "rosstat2010_pdf_page", "rosstat2010_printed_page", "rosstat2010_label", "rosstat2010_population", "rosstat2010_population_matches"]
    blind = review[[c for c in blind_columns if c in review.columns]].copy()
    pred_key = review[["review_key", "candidate_id", "candidate_status", "evidence_class", "evidence_basis",
        "observation_id_2002", "observation_id_2010", "observation_id_2021", "source_linkage_caveat"]].copy()
    # The hidden key includes model status; the blind table does not.
    return candidates, blind, pred_key


def fingerprint_identity_proposals(candidates: pd.DataFrame) -> pd.DataFrame:
    """Represent each reviewed 3-date chain as two separate same-place edges."""
    rows = []
    for candidate in candidates.itertuples(index=False):
        evidence = {
            "wikidata": candidate.wikidata_url,
            "wikipedia": candidate.wikipedia_url_ru,
            "source_2002_catalog": candidate.lingvarium_2002_catalog,
            "source_2010_rosstat_pdf": candidate.rosstat_2010_pdf,
            "source_2021_dataset": candidate.tochno_2021_dataset,
            "rosstat_2010_reference": getattr(candidate, "rosstat2010_reference_id", None),
            "population_fingerprint_is_not_independent": True,
        }
        for left_year, right_year in ((2002, 2010), (2010, 2021)):
            decision_id = stable_id("IDPROPOSAL", f"{candidate.candidate_id}|{left_year}|{right_year}")
            rows.append({
                "decision_id": decision_id,
                "candidate_id": candidate.candidate_id,
                "event_order": 1,
                "event_action": "propose",
                "decision_type": "identity_link",
                "relation_type": "same_place",
                "observation_id": pd.NA,
                "from_observation_id": getattr(candidate, f"observation_id_{left_year}"),
                "to_observation_id": getattr(candidate, f"observation_id_{right_year}"),
                "place_id": pd.NA,
                "coordinate_claim_id": pd.NA,
                "decision_class": "rule",
                "decision_status": "pending_blind_validation",
                "decision_rule": "karelia_three_census_population_fingerprint_v1",
                "evidence_uri": json.dumps(evidence, ensure_ascii=False),
                "evidence_sha256": pd.NA,
                "evidence_source": json.dumps(["Tochno census dataset", "Lingvarium catalog", "Rosstat table 5", "Wikidata statements; upstream independence unverified"], ensure_ascii=False),
                "rationale": "Three-date same-place candidate for blind review. Wikidata population statements may derive from census sources and are not independent population validation. Continuity remains an inference; only a reviewer apply event creates a same_place edge.",
                "reviewer": "automated_rule",
                "reviewed_at": pd.NA,
                "supersedes_decision_id": pd.NA,
            })
    return pd.DataFrame(rows)


def frozen_review_artifact(batch: pd.DataFrame, key: pd.DataFrame, prefix: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reuse an existing blind batch byte-for-byte; never silently resample it."""
    batch_path = OUT_ROOT / f"{prefix}_blind_review_batch.parquet" if prefix else OUT_ROOT / "blind_review_batch.parquet"
    csv_path = OUT_ROOT / f"{prefix}_blind_review_batch.csv" if prefix else OUT_ROOT / "blind_review_batch.csv"
    key_path = OUT_ROOT / f"{prefix}_blind_prediction_key.parquet" if prefix else OUT_ROOT / "blind_review_prediction_key.parquet"
    if batch_path.exists() and key_path.exists():
        existing_batch, existing_key = pd.read_parquet(batch_path), pd.read_parquet(key_path)
        manifest_path = OUT_ROOT / f"{prefix}_blind_review_manifest.json" if prefix else OUT_ROOT / "blind_review_manifest.json"
        if not manifest_path.exists() and csv_path.exists():
            manifest = {
                "batch_file": batch_path.name, "batch_sha256": sha256(batch_path),
                "csv_file": csv_path.name, "csv_sha256": sha256(csv_path),
                "prediction_key_file": key_path.name, "prediction_key_sha256": sha256(key_path),
                "rule": "pre-existing batch frozen before review; exact selection recipe recorded in linkage methodology",
            }
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return existing_batch, existing_key
    batch.to_parquet(batch_path, index=False)
    batch.to_csv(csv_path, index=False)
    key.to_parquet(key_path, index=False)
    manifest_path = OUT_ROOT / f"{prefix}_blind_review_manifest.json" if prefix else OUT_ROOT / "blind_review_manifest.json"
    manifest = {
        "batch_file": batch_path.name, "batch_sha256": sha256(batch_path),
        "csv_file": csv_path.name, "csv_sha256": sha256(csv_path),
        "prediction_key_file": key_path.name, "prediction_key_sha256": sha256(key_path),
        "rule": "deterministic SHA-256 sampling from first preliminary build; frozen once generated",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return batch, key


def kostomuksha_case_events(observations: pd.DataFrame, claims: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load only the independently reviewed, case-scoped positive decision."""
    dossier_path = REVIEW_ROOT / "independent_review_kostomuksha.json"
    empty = pd.DataFrame()
    if not dossier_path.exists():
        return pd.DataFrame(), claims, empty
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    case = dossier["case"]
    if case.get("overall_review_result") != "accept" or case.get("wikidata_id") != "Q155379":
        raise ValueError("Kostomuksha dossier is not the expected reviewed positive case")
    if case.get("identity_of_named_NP_correct") is not True or case.get("point_belongs_to_named_NP") is not True:
        raise ValueError("Kostomuksha dossier does not affirm identity and point membership")
    expected = {int(item["year"]): item for item in dossier["year_observations"]}
    located = {}
    for year, item in expected.items():
        source_id = item["primary_source"].get("source_record_id")
        if source_id is None:
            match = re.search(r"source_record_id\s+(20\d{2}:[^\s;,]+)", item["primary_source"].get("locator", ""))
            source_id = match.group(1) if match else None
        row = observations[observations.census_year.eq(year) & observations.source_record_id.astype(str).eq(str(source_id))]
        if len(row) != 1:
            raise ValueError(f"reviewed source row does not resolve uniquely for {year}: {source_id}")
        source_row = row.iloc[0]
        if int(source_row.population) != int(item["population"]):
            raise ValueError(f"reviewed population scope/value does not match observation for {year}")
        located[year] = source_row
    links = [(2002, 2010), (2010, 2021)]
    evrows = []
    identity_event_ids = []
    source_urls = []
    for item in dossier["year_observations"]:
        source_urls.append(item["primary_source"]["url"])
        if item.get("conflicting_secondary_source"):
            source_urls.append(item["conflicting_secondary_source"]["local_path"])
    source_urls += [x["url"] for x in dossier.get("identity_and_history_evidence", [])]
    source_urls += [x["url"] for x in dossier.get("spatial_evidence", []) if x.get("url")]
    source_urls = sorted(set(source_urls))
    dossier_sha = sha256(dossier_path)
    for left_year, right_year in links:
        did = stable_id("REVIEW-CASE", f"kostomuksha-Q155379|same_place|{left_year}|{right_year}|{dossier_sha}")
        identity_event_ids.append(did)
        evrows.append({
            "decision_id": did, "candidate_id": stable_id("CASE", "kostomuksha-Q155379"),
            "event_order": 2, "event_action": "apply", "decision_type": "identity_link",
            "relation_type": "same_place", "observation_id": pd.NA,
            "from_observation_id": located[left_year].observation_id,
            "to_observation_id": located[right_year].observation_id,
            "place_id": pd.NA, "coordinate_claim_id": pd.NA,
            "decision_class": "rule", "decision_status": "case_review_accepted",
            "decision_rule": "independent_case_review_kostomuksha_v1",
            "evidence_uri": json.dumps({"review_dossier": artifact_path(dossier_path), "review_sha256": dossier_sha,
                "primary_source_locators": [expected[y]["primary_source"]["locator"] for y in [left_year, right_year]],
                "evidence_urls": source_urls}, ensure_ascii=False),
            "evidence_sha256": dossier_sha,
            "evidence_source": json.dumps(["primary census rows", "official municipal chronology", "spatial footprint check", "review dossier"], ensure_ascii=False),
            "rationale": "Independent case review accepts same physical city. Population fingerprint/Wikidata claims are not counted as independent census evidence; source scope excludes subordinate settlements.",
            "reviewer": dossier.get("reviewer_method", "independent_case_reviewer"),
            "reviewed_at": dossier.get("reviewed_at_utc"), "supersedes_decision_id": pd.NA,
        })
    point_record = next(item for item in dossier["year_observations"] if int(item["year"]) == 2021)
    coord = point_record["coordinate_claim"]
    target_2021 = located[2021]
    coordrow = claims[claims.observation_id.eq(target_2021.observation_id)]
    coordrow = coordrow[(coordrow.latitude.sub(coord["latitude"]).abs() <= 2e-6)
                        & (coordrow.longitude.sub(coord["longitude"]).abs() <= 2e-6)]
    if len(coordrow) != 1:
        raise ValueError("reviewed 2021 coordinate does not resolve to exactly one source claim")
    source_coord = coordrow.iloc[0]
    spatial_urls = [x["osm_feature"]["url"] for x in dossier.get("spatial_evidence", []) if "osm_feature" in x]
    spatial_urls += [x["url"] for x in dossier.get("spatial_evidence", []) if x.get("url")]
    reviewed_at = dossier.get("reviewed_at_utc")

    def coordinate_event(obs, claim_id, year_class, decision_id, parent=None):
        # A 2010 point inferred from 2021 needs only the 2010→2021 link;
        # reaching 2002 from 2021 additionally crosses 2002→2010.
        year = int(obs.census_year)
        required_identity = ([identity_event_ids[1]] if year == 2010 else identity_event_ids) if year_class == "inferred_continuity" else []
        return {
            "decision_id": decision_id, "candidate_id": stable_id("CASE", "kostomuksha-Q155379"),
            "event_order": 3, "event_action": "apply", "decision_type": "coordinate_admission",
            "relation_type": pd.NA, "observation_id": obs.observation_id,
            "from_observation_id": obs.observation_id, "to_observation_id": pd.NA,
            "place_id": obs.provisional_place_id, "coordinate_claim_id": claim_id,
            "decision_class": year_class, "decision_status": "case_review_accepted",
            "decision_rule": "independent_case_review_kostomuksha_v1",
            "temporal_applicability": ("current_place_representative_point; source measurement date unknown; contemporary footprint validation is dated 2022" if year_class == "rule" else "inferred continuity from reviewed same-place chain; no historical point or dated map found"),
            "depends_on_identity_decision_ids": json.dumps(required_identity),
            "parent_coordinate_claim_id": parent,
            "evidence_uri": json.dumps({"review_dossier": artifact_path(dossier_path), "review_sha256": dossier_sha,
                "coordinate_source_record_id": str(target_2021.source_record_id), "coordinate_source_urls": spatial_urls,
                "review_reason": case.get("coordinate_decision")}, ensure_ascii=False),
            "evidence_sha256": dossier_sha,
            "evidence_source": json.dumps([coord["source"], "OSM contemporary geometry validation", "independent case review"], ensure_ascii=False),
            "rationale": case.get("coordinate_decision", ""), "reviewer": dossier.get("reviewer_method", "independent_case_reviewer"),
            "reviewed_at": reviewed_at, "supersedes_decision_id": pd.NA,
        }

    coordinate_claim_id = source_coord.coordinate_claim_id
    point_event_id = stable_id("REVIEW-CASE", f"kostomuksha-Q155379|coordinate|2021|{dossier_sha}")
    evrows.append(coordinate_event(target_2021, coordinate_claim_id, "rule", point_event_id))
    derived = []
    for year in (2002, 2010):
        obs = located[year]
        claim_id = stable_id("COORD-CONTINUITY", f"{coordinate_claim_id}|{obs.observation_id}")
        new_claim = source_coord.to_dict()
        new_claim.update({
            "coordinate_claim_id": claim_id,
            "observation_id": obs.observation_id,
            "source_record_id": obs.source_record_id,
            "census_year": year,
            "source_year": 2021,
            "claim_origin": "inferred_continuity_from_2021_claim",
            "derived_from_coordinate_claim_id": coordinate_claim_id,
            "admission_status": "unresolved",
            "admission_class": "inferred_continuity",
            "admission_rule": "independent_case_review_kostomuksha_v1",
            "admission_reason": "no historical coordinate found; reviewer accepted cautious temporal continuity claim",
        })
        derived.append(new_claim)
        event_id = stable_id("REVIEW-CASE", f"kostomuksha-Q155379|coordinate|{year}|{dossier_sha}")
        evrows.append(coordinate_event(obs, claim_id, "inferred_continuity", event_id, coordinate_claim_id))
    if derived:
        claims = pd.concat([claims, pd.DataFrame(derived)], ignore_index=True, sort=False)
    dossier_row = {
        "case_id": "kostomuksha-Q155379", "review_file": artifact_path(dossier_path),
        "review_sha256": dossier_sha, "reviewed_at_utc": reviewed_at,
        "scope": case.get("scope"), "identity_result": case.get("identity_decision"),
        "coordinate_result": case.get("coordinate_decision"), "main_caveat": case.get("main_caveat"),
        "sources_and_spatial_evidence": json.dumps(source_urls, ensure_ascii=False),
        "scope_checked_values": json.dumps({str(y): expected[y]["population"] for y in expected}, ensure_ascii=False),
    }
    return pd.DataFrame(evrows), claims, pd.DataFrame([dossier_row])


def effective_after_dependency_cascade(events: pd.DataFrame) -> pd.DataFrame:
    effective = apply_decision_events(events)
    if effective.empty or "depends_on_identity_decision_ids" not in effective:
        return effective
    active_identity = set(effective.loc[effective.decision_type.eq("identity_link"), "decision_id"].astype(str))
    keep = []
    for value in effective.depends_on_identity_decision_ids.fillna("[]"):
        dependencies = json.loads(value) if isinstance(value, str) else []
        keep.append(set(dependencies).issubset(active_identity))
    return effective[pd.Series(keep, index=effective.index)].copy()


def reviewed_top6_case_events(observations: pd.DataFrame, claims: pd.DataFrame,
                              identity_proposals: pd.DataFrame, prediction_key: pd.DataFrame,
                              public_batch: pd.DataFrame | None = None
                              ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply only case verdicts returned by the independent reviewer."""
    path = REVIEW_ROOT / "karelia_identity_independent_review_top6.csv"
    if not path.exists():
        return pd.DataFrame(), claims, pd.DataFrame()
    reviews = pd.read_csv(path, encoding="utf-8-sig")
    review_hash = sha256(path)
    if reviews.review_key.duplicated().any():
        raise ValueError("independent Karelia review contains duplicate keys")
    if not reviews.review_result.eq("accept").all():
        raise ValueError("unexpected non-accept verdict requires explicit handling")
    if public_batch is not None:
        if public_batch.review_key.duplicated().any():
            raise ValueError("frozen public blind batch contains duplicate review keys")
        accepted = reviews.merge(public_batch, on="review_key", how="left", validate="one_to_one", indicator=True)
        if accepted._merge.ne("both").any():
            raise ValueError("review verdicts do not resolve against the frozen public blind batch")
        if not set([f"source_record_id_{year}" for year in (2002, 2010, 2021)]).issubset(accepted.columns):
            raise ValueError("frozen public blind batch lacks the three source-record bindings")
        indexed = observations.set_index("source_record_id", drop=False)
        for year in (2002, 2010, 2021):
            source_col = f"source_record_id_{year}"
            observation_ids, populations = [], []
            for source_id in accepted[source_col].astype(str):
                if source_id not in indexed.index:
                    raise ValueError(f"reviewed source row missing from source bundle: {source_id}")
                source_row = indexed.loc[source_id]
                if isinstance(source_row, pd.DataFrame) or int(source_row.census_year) != year:
                    raise ValueError(f"reviewed source row is not unique/year-bound: {source_id}")
                observation_ids.append(source_row.observation_id)
                populations.append(int(source_row.population))
            accepted[f"observation_id_{year}"] = observation_ids
            accepted[f"population_{year}"] = populations
        accepted["candidate_id"] = accepted.review_key
        id_events = []
        for record in accepted.itertuples(index=False):
            for left, right in ((2002, 2010), (2010, 2021)):
                id_events.append({
                    "decision_id": stable_id("REVIEW-CASE", f"{record.review_key}|same_place|{left}|{right}|{review_hash}"),
                    "candidate_id": record.candidate_id, "event_order": 2, "event_action": "apply",
                    "decision_type": "identity_link", "relation_type": "same_place", "observation_id": pd.NA,
                    "from_observation_id": getattr(record, f"observation_id_{left}"),
                    "to_observation_id": getattr(record, f"observation_id_{right}"), "place_id": pd.NA,
                    "coordinate_claim_id": pd.NA, "decision_class": "rule",
                    "decision_status": "case_review_accepted",
                    "decision_rule": "independent_blind_case_review_v1",
                    "evidence_uri": json.dumps({"review_file": artifact_path(path), "review_sha256": review_hash,
                        "review_key": record.review_key, "blind_batch_row": {
                            str(year): getattr(record, f"source_record_id_{year}") for year in (2002, 2010, 2021)},
                        "citation_locator": record.citation_locator}, ensure_ascii=False),
                    "evidence_sha256": review_hash,
                    "evidence_source": "independent per-case source and point review; frozen non-prediction batch binding",
                    "rationale": str(record.reason), "reviewer": "independent_blind_case_reviewer",
                    "reviewed_at": "2026-09-29", "supersedes_decision_id": pd.NA,
                })
        identity_events = pd.DataFrame(id_events)
    else:
        accepted = reviews.merge(prediction_key, on="review_key", how="left", validate="one_to_one", indicator=True)
        if accepted._merge.ne("both").any():
            raise ValueError("independent review keys do not match the frozen prediction key")
        accepted["candidate_id"] = accepted.candidate_id
        identity_results = reviews[["review_key", "review_result", "reason", "citation_locator"]].rename(
            columns={"citation_locator": "review_evidence_urls"})
        identity_events = reviewer_results_to_events(identity_proposals, identity_results, prediction_key,
            reviewer="independent_blind_case_reviewer", first_event_order=2)
    if not (accepted.identity_of_named_NP_correct.eq(True).all()
            and accepted.point_belongs_to_named_NP.eq(True).all()
            and accepted.admin_context_agrees.eq(True).all()):
        raise ValueError("review verdict conflicts with one or more identity/point/admin checks")
    located = observations.set_index("observation_id", drop=False)
    new_claims = []
    coordinate_events = []
    dossier_records = []
    for record in accepted.itertuples(index=False):
        evidence = str(record.reason)
        full_evidence = evidence + " " + str(record.citation_locator)
        # Verify the reviewer-checked population values against this release's
        # immutable rows before applying either identity or coordinate events.
        expected_pops = re.search(r"2002\s+(\d+).*?2010\s+(\d+).*?2021\s+(\d+)", evidence)
        if not expected_pops:
            raise ValueError(f"could not parse three checked census populations for {record.review_key}")
        obs_by_year = {}
        for year, expected_pop in zip((2002, 2010, 2021), map(int, expected_pops.groups())):
            obs = located.loc[getattr(record, f"observation_id_{year}")]
            if int(obs.population) != expected_pop:
                raise ValueError(f"reviewed {year} population does not match observation for {record.review_key}")
            obs_by_year[year] = obs
        coord_match = re.search(r"2021 coordinate \(([-\d.]+),\s*([-\d.]+);", evidence)
        if not coord_match:
            raise ValueError(f"reviewer evidence has no precise 2021 point for {record.review_key}")
        lat, lon = map(float, coord_match.groups())
        point_claims = claims[claims.observation_id.eq(obs_by_year[2021].observation_id)]
        point_claims = point_claims[(point_claims.latitude.sub(lat).abs() <= 2e-6)
                                    & (point_claims.longitude.sub(lon).abs() <= 2e-6)]
        if len(point_claims) != 1:
            raise ValueError(f"reviewed point does not match exactly one source claim for {record.review_key}")
        claim = point_claims.iloc[0]
        osm_url_match = re.search(r"https://api\.openstreetmap\.org/api/0\.6/(?:way|relation)/\d+/full", full_evidence)
        osm_sha_match = re.search(r"SHA256 ([a-f0-9]{64})", full_evidence[osm_url_match.end():], re.IGNORECASE) if osm_url_match else None
        qid_match = re.search(r"QID (Q\d+)", full_evidence)
        if not osm_url_match or not osm_sha_match:
            raise ValueError(f"reviewed point lacks OSM geometry URL or checksum for {record.review_key}")
        qid = qid_match.group(1) if qid_match else None
        identity_ids = identity_events.loc[identity_events.candidate_id.eq(record.candidate_id), "decision_id"].astype(str).tolist()
        coord_decision = stable_id("REVIEW-POINT", f"{record.review_key}|{claim.coordinate_claim_id}|{review_hash}")
        coordinate_events.append({
            "decision_id": coord_decision, "candidate_id": record.candidate_id,
            "event_order": 3, "event_action": "apply", "decision_type": "coordinate_admission",
            "relation_type": pd.NA, "observation_id": obs_by_year[2021].observation_id,
            "from_observation_id": obs_by_year[2021].observation_id, "to_observation_id": pd.NA,
            "place_id": obs_by_year[2021].provisional_place_id,
            "coordinate_claim_id": claim.coordinate_claim_id,
            "decision_class": "rule", "decision_status": "case_review_accepted",
            "decision_rule": "independent_osm_polygon_case_review_v1",
            "temporal_applicability": "current_place_representative_point; source measurement date unknown; OSM polygon retrieval dated 2026-09-29",
            "depends_on_identity_decision_ids": "[]", "parent_coordinate_claim_id": pd.NA,
            "evidence_uri": json.dumps({"review_file": artifact_path(path), "review_sha256": review_hash,
                "review_key": record.review_key, "citation_locator": record.citation_locator,
                "osm_geometry_url": osm_url_match.group(0), "osm_geometry_sha256": osm_sha_match.group(1),
                "wikidata_url": f"https://www.wikidata.org/wiki/{qid}" if qid else None}, ensure_ascii=False),
            "evidence_sha256": review_hash, "evidence_source": "independent reviewer local source check + OSM polygon containment",
            "rationale": evidence, "reviewer": "independent_blind_case_reviewer", "reviewed_at": "2026-09-29",
            "supersedes_decision_id": pd.NA,
        })
        for year in (2002, 2010):
            old = obs_by_year[year]
            derived_id = stable_id("COORD-CONTINUITY", f"{claim.coordinate_claim_id}|{old.observation_id}")
            derived = claim.to_dict()
            derived.update({"coordinate_claim_id": derived_id, "observation_id": old.observation_id,
                "source_record_id": old.source_record_id, "census_year": year, "source_year": 2021,
                "claim_origin": "inferred_continuity_from_2021_claim", "derived_from_coordinate_claim_id": claim.coordinate_claim_id,
                "admission_status": "unresolved", "admission_class": "inferred_continuity",
                "admission_rule": "independent_osm_polygon_case_review_v1",
                "admission_reason": "historical point not found; reviewed continuous place identity supports only inferred continuity"})
            new_claims.append(derived)
            coordinate_events.append({
                "decision_id": stable_id("REVIEW-POINT", f"{record.review_key}|{derived_id}|{review_hash}"),
                "candidate_id": record.candidate_id, "event_order": 3, "event_action": "apply",
                "decision_type": "coordinate_admission", "relation_type": pd.NA,
                "observation_id": old.observation_id, "from_observation_id": old.observation_id,
                "to_observation_id": pd.NA, "place_id": old.provisional_place_id,
                "coordinate_claim_id": derived_id, "decision_class": "inferred_continuity",
                "decision_status": "case_review_accepted", "decision_rule": "independent_osm_polygon_case_review_v1",
                "temporal_applicability": "inferred_continuity; no direct historical point or dated map found",
                "depends_on_identity_decision_ids": json.dumps([identity_ids[1]] if year == 2010 else identity_ids),
                "parent_coordinate_claim_id": claim.coordinate_claim_id,
                "evidence_uri": json.dumps({"review_file": artifact_path(path), "review_sha256": review_hash,
                    "review_key": record.review_key, "citation_locator": record.citation_locator,
                    "parent_coordinate_claim_id": claim.coordinate_claim_id, "osm_geometry_url": osm_url_match.group(0),
                    "osm_geometry_sha256": osm_sha_match.group(1)}, ensure_ascii=False),
                "evidence_sha256": review_hash, "evidence_source": "independent reviewer local source check + OSM polygon containment",
                "rationale": "Historical coordinate is an explicit continuity inference; the present-day polygon does not date the point.",
                "reviewer": "independent_blind_case_reviewer", "reviewed_at": "2026-09-29",
                "supersedes_decision_id": pd.NA,
            })
        dossier_records.append({"review_key": record.review_key, "candidate_id": record.candidate_id,
            "review_file": artifact_path(path), "review_sha256": review_hash,
            "review_result": record.review_result, "reason": evidence, "citation_locator": record.citation_locator,
            "wikidata_id": qid, "coordinate_latitude": lat, "coordinate_longitude": lon,
            "osm_geometry_url": osm_url_match.group(0), "osm_geometry_sha256": osm_sha_match.group(1),
            "identity_event_ids": json.dumps(identity_ids)})
    if new_claims:
        claims = pd.concat([claims, pd.DataFrame(new_claims)], ignore_index=True, sort=False)
    return pd.concat([identity_events, pd.DataFrame(coordinate_events)], ignore_index=True, sort=False), claims, pd.DataFrame(dossier_records)


def reviewed_major_city_events(observations: pd.DataFrame, claims: pd.DataFrame
                               ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Bind the out-of-sample major-city dossier to immutable observations."""
    path = REVIEW_ROOT / "independent_review_karelia_major_cities.json"
    if not path.exists():
        return pd.DataFrame(), claims, pd.DataFrame(), pd.DataFrame()
    dossier = json.loads(path.read_text(encoding="utf-8"))
    if dossier.get("case_result", "").lower().find("all three chains accepted") < 0:
        raise ValueError("major-city dossier lacks three explicit accepted verdicts")
    review_hash = sha256(path)
    indexed = observations.set_index("source_record_id", drop=False)
    claim_rows, events, dossiers, conflicts = [], [], [], []
    for case in dossier["cases"]:
        years = {int(year): data for year, data in case["year_observations"].items()}
        obs_by_year = {}
        for year in (2002, 2010, 2021):
            record = years[year]
            source_id = record["source_record_id"]
            if source_id not in indexed.index:
                raise ValueError(f"reviewed source row missing from immutable registry: {source_id}")
            obs = indexed.loc[source_id]
            if isinstance(obs, pd.DataFrame):
                raise ValueError(f"source record id is not unique: {source_id}")
            if int(obs.census_year) != year or int(obs.population) != int(record["population"]):
                raise ValueError(f"reviewed source row year/population mismatch: {source_id}")
            if normalize(obs.settlement_name) != normalize(case["name"]):
                raise ValueError(f"reviewed place name does not bind uniquely: {source_id}")
            obs_by_year[year] = obs
        link_ids=[]
        case_key = f"major-city-{case['wikidata_id']}"
        for left_year, right_year in ((2002, 2010), (2010, 2021)):
            did = stable_id("REVIEW-CASE", f"{case_key}|same_place|{left_year}|{right_year}|{review_hash}")
            link_ids.append(did)
            events.append({
                "decision_id": did, "candidate_id": stable_id("CASE", case_key), "event_order": 2,
                "event_action": "apply", "decision_type": "identity_link", "relation_type": "same_place",
                "observation_id": pd.NA, "from_observation_id": obs_by_year[left_year].observation_id,
                "to_observation_id": obs_by_year[right_year].observation_id,
                "place_id": pd.NA, "coordinate_claim_id": pd.NA, "decision_class": "rule",
                "decision_status": "independent_case_review_accepted",
                "decision_rule": "independent_major_city_followup_v1",
                "evidence_uri": json.dumps({"review_file": artifact_path(path), "review_sha256": review_hash,
                    "qid": case["wikidata_id"], "year_source_record_ids": {str(y): years[y]["source_record_id"] for y in (left_year, right_year)},
                    "osm_url": case["osm"]["url"], "osm_sha256": case["osm"]["sha256"]}, ensure_ascii=False),
                "evidence_sha256": review_hash, "evidence_source": "three official census rows + contemporary OSM geometry + independent case review",
                "rationale": case["identity_evidence"], "reviewer": "independent_case_reviewer_followup",
                "reviewed_at": dossier.get("reviewed_at_utc"), "supersedes_decision_id": pd.NA,
            })
        point = years[2021]
        point_claims = claims[claims.observation_id.eq(obs_by_year[2021].observation_id)]
        point_claims = point_claims[(point_claims.latitude.sub(float(point["latitude"])).abs() <= 2e-6)
                                    & (point_claims.longitude.sub(float(point["longitude"])).abs() <= 2e-6)]
        if len(point_claims) != 1:
            raise ValueError(f"reviewed point does not bind to one source coordinate claim: {case['name']}")
        point_claim = point_claims.iloc[0]
        point_event_id = stable_id("REVIEW-POINT", f"{case_key}|2021|{review_hash}")
        for year, cls in ((2021, "rule"), (2002, "inferred_continuity"), (2010, "inferred_continuity")):
            obs = obs_by_year[year]
            if year == 2021:
                claim_id = point_claim.coordinate_claim_id
                parent_claim_id = pd.NA
            else:
                claim_id = stable_id("COORD-CONTINUITY", f"{point_claim.coordinate_claim_id}|{obs.observation_id}")
                parent_claim_id = point_claim.coordinate_claim_id
                derived = point_claim.to_dict()
                derived.update({"coordinate_claim_id": claim_id, "observation_id": obs.observation_id,
                    "source_record_id": obs.source_record_id, "census_year": year, "source_year": 2021,
                    "claim_origin": "inferred_continuity_from_2021_claim", "derived_from_coordinate_claim_id": point_claim.coordinate_claim_id,
                    "admission_status": "unresolved", "admission_class": cls,
                    "admission_rule": "independent_major_city_followup_v1",
                    "admission_reason": "No direct historic point was found; current point reused only as inferred continuity"})
                claim_rows.append(derived)
            events.append({
                "decision_id": point_event_id if year == 2021 else stable_id("REVIEW-POINT", f"{case_key}|{year}|{review_hash}"),
                "candidate_id": stable_id("CASE", case_key), "event_order": 3, "event_action": "apply",
                "decision_type": "coordinate_admission", "relation_type": pd.NA,
                "observation_id": obs.observation_id, "from_observation_id": obs.observation_id,
                "to_observation_id": pd.NA, "place_id": obs.provisional_place_id,
                "coordinate_claim_id": claim_id, "decision_class": cls,
                "decision_status": "independent_case_review_accepted",
                "decision_rule": "independent_osm_polygon_case_review_v1",
                "temporal_applicability": ("current-place representative point; source measurement date not asserted; OSM geometry retrieved 2026-09-29" if year == 2021 else "inferred_continuity; no dated historic point/map found"),
                "depends_on_identity_decision_ids": json.dumps([] if year == 2021 else ([link_ids[1]] if year == 2010 else link_ids)),
                "parent_coordinate_claim_id": parent_claim_id,
                "evidence_uri": json.dumps({"review_file": artifact_path(path), "review_sha256": review_hash,
                    "qid": case["wikidata_id"], "osm_url": case["osm"]["url"], "osm_sha256": case["osm"]["sha256"],
                    "source_record_id_2021": obs_by_year[2021].source_record_id}, ensure_ascii=False),
                "evidence_sha256": review_hash, "evidence_source": "source point + contemporary OSM town polygon containment + independent review",
                "rationale": case["identity_evidence"], "reviewer": "independent_case_reviewer_followup",
                "reviewed_at": dossier.get("reviewed_at_utc"), "supersedes_decision_id": pd.NA,
            })
        conflict = case.get("population_conflict_2010")
        if conflict:
            conflicts.append({"case_id": case_key, "place_name": case["name"], "year": 2010,
                "selected_primary_population": conflict["official_rosstat"],
                "secondary_population": conflict["lingvarium_secondary"], "difference_secondary_minus_primary": -int(conflict["difference"]),
                "secondary_source_record_id": conflict["secondary_source_record_id"], "secondary_source_path": conflict["local_file"],
                "secondary_locator": conflict["locator"], "selection_basis": "Directly checked official Rosstat city row; secondary compilation retained as a separate conflict, not merged/averaged.",
                "review_file": artifact_path(path), "review_sha256": review_hash})
        dossiers.append({"case_id": case_key, "place_name": case["name"], "wikidata_id": case["wikidata_id"],
            "review_file": artifact_path(path), "review_sha256": review_hash,
            "reviewed_at": dossier.get("reviewed_at_utc"), "sample_design": dossier.get("sample_design"),
            "identity_evidence": case["identity_evidence"], "osm_url": case["osm"]["url"], "osm_sha256": case["osm"]["sha256"],
            "accepted_event_ids": json.dumps(link_ids), "populations": json.dumps({str(y): years[y]["population"] for y in years})})
    if claim_rows:
        claims = pd.concat([claims, pd.DataFrame(claim_rows)], ignore_index=True, sort=False)
    return pd.DataFrame(events), claims, pd.DataFrame(dossiers), pd.DataFrame(conflicts)


def karelia_2002_overlap_claims() -> pd.DataFrame:
    """Explain source rows omitted from the selected 2002 Karelia snapshot."""
    raw_path = ROOT / "research_audit/evidence/replayed_observations.parquet"
    snap_path = ROOT / "research_audit/output/audited_census_snapshots.parquet"
    raw = pd.read_parquet(raw_path)
    snap = pd.read_parquet(snap_path)
    k = raw[raw.census_year.eq(2002)
            & raw.region_raw.astype("string").str.contains("Карелия", case=False, na=False)
            & raw.settlement_type.astype("string").str.contains("город|пгт", case=False, na=False)].copy()
    selected_ids = set(snap.source_record_id.astype(str))
    k = k[~k.source_record_id.astype(str).isin(selected_ids)].copy()
    selected = snap[snap.census_year.eq(2002)
            & snap.region_raw.astype("string").str.contains("Карелия", case=False, na=False)
            & snap.settlement_type.astype("string").str.contains("город|пгт", case=False, na=False)].copy()
    k["name_key"] = k.settlement_name.map(lambda x: " ".join(str(x).casefold().replace("ё", "е").split()))
    selected["name_key"] = selected.settlement_name.map(lambda x: " ".join(str(x).casefold().replace("ё", "е").split()))
    k["type_key"] = k.settlement_type.map(lambda x: " ".join(str(x).casefold().replace("ё", "е").split()))
    selected["type_key"] = selected.settlement_type.map(lambda x: " ".join(str(x).casefold().replace("ё", "е").split()))
    selected = selected[["source_record_id", "source_file", "source_row", "settlement_name", "settlement_type", "population", "name_key", "type_key"]].rename(columns={
        "source_record_id": "selected_source_record_id", "source_file": "selected_source_file", "source_row": "selected_source_row",
        "settlement_name": "selected_name", "settlement_type": "selected_type", "population": "selected_population"})
    out = k.merge(selected, on=["name_key", "type_key"], how="left", validate="many_to_one")
    out["population_equal"] = pd.to_numeric(out.population, errors="coerce").eq(pd.to_numeric(out.selected_population, errors="coerce"))
    exact = out.selected_source_record_id.notna() & out.population_equal
    aggregate = out.settlement_name.astype("string").str.contains("подчин|подч", case=False, na=False)
    out["disposition"] = np.select([exact, aggregate], ["excluded_confirmed_alternative_row", "source_overlap_under_review"], default="source_overlap_under_review")
    out["disposition_reason"] = np.select([exact, aggregate], [
        "Alternate 02C row duplicates the selected official Tom 1 settlement row by exact name, type, and population; retained in raw observations only.",
        "02C label explicitly includes subordinate settlements; no same-label selected row, so possible aggregate scope remains unresolved."
    ], default="No exact selected name/type/population counterpart; exclusion remains under review.")
    out["source_02c_catalog_url"] = "https://www.lingvarium.org/russia/Census2002.shtml"
    out["source_official_tom1_url"] = "https://www.perepis2002.ru/ct/doc/1_TOM_01_04.xls"
    out["selected_snapshot_source"] = "research_audit/output/audited_census_snapshots.parquet"
    out["source_evidence_status"] = "row-level overlap arithmetic checked; underlying source publication comparison recorded; source value correctness is not independently certified by this check"
    columns = ["source_record_id", "source_file", "source_sheet", "source_row", "settlement_name", "settlement_type", "population",
        "selected_source_record_id", "selected_source_file", "selected_source_row", "selected_name", "selected_type", "selected_population",
        "population_equal", "disposition", "disposition_reason", "source_02c_catalog_url", "source_official_tom1_url", "selected_snapshot_source", "source_evidence_status"]
    out = out.reindex(columns=columns)
    return out.sort_values(["disposition", "settlement_name"], kind="stable").reset_index(drop=True)


def build(identity_review_results: Path | None = None, reviewer: str | None = None, scope: str = "karelia",
          release_name: str = "karelia_pilot_release_r2", validate_only: bool = False,
          source_selection_version: str = "legacy-current"):
    global OUT
    if scope not in {"karelia", "mixed", "national"}:
        raise ValueError("scope must be karelia, mixed, or national")
    if source_selection_version not in {"legacy-current", "primary2010"}:
        raise ValueError("source_selection_version must be legacy-current or primary2010")
    if scope != "karelia" and source_selection_version != "legacy-current":
        raise ValueError("primary2010 selection is currently scoped to Karelia")
    final_out = OUT_ROOT / release_name
    if scope == "karelia":
        if final_out.exists() and not validate_only:
            raise FileExistsError(f"immutable release already exists: {final_out}; choose a new release name")
        OUT = Path(tempfile.mkdtemp(prefix=f".{release_name}.staging-", dir=OUT_ROOT))
    else:
        OUT = OUT_ROOT
    OUT.mkdir(parents=True, exist_ok=True)
    source, input_status = load_observations(scope)
    source = attach_source_hashes(source)
    observations = prepare_observations(source)
    release_manifest = None
    case_observations = observations.copy()
    source_selection_assertions = pd.DataFrame()
    published_record_bindings = pd.DataFrame()
    selection_manifest = None
    if scope == "karelia":
        observations = observations[observations.region_key.eq("карелия")].copy()
        if observations.empty:
            raise ValueError("Karelia-only pilot input is empty")
        registry_source, selected_for_release = load_karelia_observation_registry()
        if source_selection_version == "primary2010":
            original_source, source_selection_status = load_observations("karelia")
            original_source = attach_source_hashes(original_source)
            case_observations = prepare_observations(original_source)
            registry_source, selected_for_release = load_karelia_observation_registry()
            selected_source, registry_source, selected_for_release, source_selection_assertions, selection_manifest = primary_2010_selection_inputs(
                original_source, registry_source, selected_for_release, release_name)
            input_status = {**input_status, **source_selection_status,
                "mode": "karelia_source_selection_primary2010_v2",
                "source_status": "2010 primary value layer independently extracted/row-ledger-bound; 2002/2021 selected dispositions carried forward; 2010 identity bindings remain case-specific; DOCX transport requires independent verification"}
            observations = prepare_observations(selected_source)
        registry = prepare_observations(registry_source)
        selected_for_release["release_id"] = release_name
    else:
        registry = observations.copy()
        selected_for_release = pd.DataFrame()
    candidates = make_identity_candidates(observations)
    claims = coordinate_claims(observations)
    wikidata = load_wikidata_evidence(observations)
    proposals = rule_coordinate_decisions(observations, claims, wikidata)
    karelia_fingerprints, karelia_identity_review, karelia_identity_key = karelia_population_fingerprint(
        case_observations if source_selection_version == "primary2010" else observations)
    identity_proposals = fingerprint_identity_proposals(karelia_fingerprints)
    overlap_claims = karelia_2002_overlap_claims()

    # No identity matching is promoted automatically. Each source row has an
    # internal provisional place ID; accepted relations require human/primary
    # documentary evidence in a later ledger event.
    place_entities = registry[["provisional_place_id", "observation_id", "source_record_id", "census_year",
                                  "settlement_name", "settlement_type", "region_raw", "district_raw"]].copy()
    place_entities = place_entities.rename(columns={"provisional_place_id": "place_id"})
    place_entities["identity_status"] = "unresolved_single_observation"
    place_entities["identity_rule_version"] = "place-id-v1"

    # R4 case decisions bind through the frozen public review batch. Do not
    # regenerate or require a hidden prediction key when replaying accepted cases.
    if source_selection_version == "primary2010":
        public_batch_path = REVIEW_ROOT / "karelia_identity_blind_review_batch.csv"
        if not public_batch_path.is_file():
            raise FileNotFoundError("R4 requires the frozen public blind batch; no hidden key is read or regenerated")
        review_batch = pd.read_csv(public_batch_path)
        if review_batch.review_key.duplicated().any():
            raise ValueError("frozen public blind batch keys are not unique")
        hidden_key = pd.DataFrame()
        karelia_identity_review = pd.DataFrame()
        karelia_identity_key = pd.DataFrame()
    else:
        review_batch, hidden_key = frozen_review_artifact(*make_review_batch(proposals, observations), "")
        karelia_identity_review, karelia_identity_key = frozen_review_artifact(
            karelia_identity_review, karelia_identity_key, "karelia_identity")

    all_proposals = pd.concat([proposals, identity_proposals], ignore_index=True, sort=False)
    reviewer_events = pd.DataFrame(columns=all_proposals.columns)
    if identity_review_results is not None:
        if reviewer is None:
            raise ValueError("reviewer identity is required with --identity-review-results")
        reviewer_results = pd.read_csv(identity_review_results)
        reviewer_events = reviewer_results_to_events(
            identity_proposals, reviewer_results, karelia_identity_key,
            reviewer=reviewer, first_event_order=2)
    reviewed_karelia_events, claims, reviewed_karelia_dossiers = reviewed_top6_case_events(
        case_observations if source_selection_version == "primary2010" else observations,
        claims, identity_proposals, karelia_identity_key,
        public_batch=review_batch if source_selection_version == "primary2010" else None)
    case_source = case_observations if source_selection_version == "primary2010" else observations
    kostomuksha_events, claims, kostomuksha_dossier = kostomuksha_case_events(case_source, claims)
    major_events, claims, major_dossiers, major_conflicts = reviewed_major_city_events(case_source, claims)
    case_review_events = pd.concat([reviewed_karelia_events, kostomuksha_events, major_events], ignore_index=True, sort=False)
    if source_selection_version == "primary2010":
        binding_events, published_record_bindings, binding_claims = primary_2010_published_record_bindings(
            observations, case_source, case_review_events, claims,
            REVIEW_ROOT / "independent_review_karelia_major_cities.json", release_name)
        claims = pd.concat([claims, binding_claims], ignore_index=True, sort=False)
        case_review_events = pd.concat([case_review_events, binding_events], ignore_index=True, sort=False)
    reviewer_events = pd.concat([reviewer_events, case_review_events], ignore_index=True, sort=False)
    ledger_events = pd.concat([all_proposals, reviewer_events], ignore_index=True, sort=False)
    effective = effective_after_dependency_cascade(ledger_events)
    active = release_coordinate_decisions(effective, set(observations.observation_id))
    effective_identity = effective[effective.decision_type.eq("identity_link")].copy() if not effective.empty else effective
    admitted_ids = set(active.coordinate_claim_id.dropna()) if not active.empty else set()
    claims["proposed_decision_id"] = claims.coordinate_claim_id.map(
        dict(zip(proposals.coordinate_claim_id, proposals.decision_id)) if not proposals.empty else {}
    )
    admitted_by_id = active.drop_duplicates("coordinate_claim_id").set_index("coordinate_claim_id") if not active.empty else pd.DataFrame()
    claims["admission_status"] = np.where(claims.coordinate_claim_id.isin(admitted_ids), "accepted", "unresolved")
    if not active.empty:
        claims["admission_class"] = claims.coordinate_claim_id.map(admitted_by_id.decision_class).fillna("unresolved")
        claims["admission_reason"] = claims.coordinate_claim_id.map(admitted_by_id.rationale).fillna("candidate or absent point evidence")
        claims["temporal_applicability"] = claims.coordinate_claim_id.map(admitted_by_id.temporal_applicability) if "temporal_applicability" in admitted_by_id else pd.NA
    else:
        claims["admission_class"] = "unresolved"
        claims["admission_reason"] = "candidate or absent point evidence"
    # Coordinates are observation-bound; same_place identity never copies a
    # coordinate from another date or source row.
    previous_components_path = OUT / "place_components.parquet"
    previous_components = pd.read_parquet(previous_components_path) if previous_components_path.exists() else pd.DataFrame()
    release_id = release_name
    components, component_membership = identity_components(place_entities, effective_identity, release_id)
    component_history = component_lineage(previous_components, components)

    relations_path = ROOT / "research_audit/output/historical_relations.parquet"
    if relations_path.exists():
        events = pd.read_parquet(relations_path)
        if "evidence_status" not in events:
            events["evidence_status"] = "legacy_claim_pending_independent_review"
        events["relationship_record_id"] = [stable_id("EVENT", f"{i}|{r}") for i, r in enumerate(events.to_dict("records"))]
    else:
        events = pd.DataFrame(columns=["relationship_record_id", "event_type", "effective_date", "evidence_status"])

    pilot = observations.copy() if scope == "karelia" else observations[observations.region_raw.astype("string").str.contains("Карелия|Карельская", case=False, na=False)].copy()
    pilot_metrics = summarize(pilot, claims, proposals, active, label="Karelia pilot")
    national_metrics = summarize(observations, claims, proposals, active, label="national") if scope != "karelia" else []
    metrics = pd.DataFrame(national_metrics + pilot_metrics)
    write_table(observations, "linkage_observations")
    write_table(place_entities, "place_entities")
    write_table(candidates, "identity_candidates")
    write_table(claims, "coordinate_claims_linkage")
    write_table(all_proposals, "decision_events_proposed")
    write_table(reviewer_events, "decision_events_reviewer")
    write_table(ledger_events, "decision_events_ledger")
    write_table(active, "effective_coordinate_decisions")
    write_table(effective_identity, "effective_identity_decisions")
    write_table(components, "place_components")
    write_table(component_membership, "place_component_membership")
    write_table(component_history, "place_component_lineage")
    write_table(events, "historical_event_claims")
    write_table(metrics, "linkage_coverage", True)
    write_table(pilot, "karelia_observations")
    write_table(karelia_fingerprints, "karelia_identity_fingerprint_candidates", True)
    write_table(overlap_claims, "karelia_2002_source_overlap_claims", True)
    write_table(reviewed_karelia_dossiers, "karelia_independent_review_dossiers")
    write_table(kostomuksha_dossier, "kostomuksha_independent_review_dossier")
    write_table(major_dossiers, "karelia_major_city_independent_review_dossiers")
    write_table(major_conflicts, "karelia_major_city_population_conflicts", True)
    population_decisions = build_karelia_population_source_decisions()
    if not population_decisions.empty:
        write_table(population_decisions, "karelia_population_source_decisions", True)
    runtime = {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__, "duckdb": duckdb.__version__}
    summary = {
        "linkage_rule_version": "identity-candidate-v1",
        "coordinate_rule_version": "oktmo_okato_wikidata_coordinate_corroboration_500m_v1",
        "input": input_status,
        "runtime": runtime,
        "observations": int(len(observations)),
        "candidate_identity_edges": int(len(candidates)),
        "candidate_ambiguous_member_rows": int(candidates.candidate_status.eq("conflict").sum()) if not candidates.empty else 0,
        "coordinate_claims": int(len(claims)),
        "coordinate_rule_proposals_pending_blind_review": int(len(proposals)),
        "effective_admitted_coordinates": int(len(active)),
        "effective_admitted_coordinate_classes": active.decision_class.value_counts(dropna=False).to_dict() if not active.empty else {},
        "reviewer_decision_events": int(len(reviewer_events)),
        "effective_same_place_edges": int(len(effective_identity)),
        "derived_identity_components": int(len(components)),
        "blind_review_batch_size": int(len(review_batch)) if scope != "karelia" else 0,
        "karelia_three_year_population_fingerprint_candidates": int(len(karelia_fingerprints)),
        "karelia_identity_review_batch_size": int(len(karelia_identity_review)),
        "karelia_2002_omitted_urban_alternatives": int(len(overlap_claims)),
        "identity_acceptances": int(len(effective_identity)),
        "independent_case_reviews": int(len(reviewed_karelia_dossiers) + len(kostomuksha_dossier) + len(major_dossiers)),
        "independent_rule_validation_sample_size": int(len(review_batch)) if scope != "karelia" else 0,
        "rule_family_validated": False,
        "blind_review_artifacts_frozen": True,
        "interpretation": "Case-specific accepted decisions are limited to independently reviewed Karelia cases and do not validate nationwide automated rules. National coordinate proposals remain pending review.",
        "scope": scope,
        "source_selection_version": source_selection_version,
        "pilot_source_status": ("R4 selects 800 source-backed 2010 primary observations and reconciles to the published 643,548 control; the separate 2002 +3 remains unassigned and DOCX transport verification remains pending; case decisions do not validate nationwide rules."
                                if source_selection_version == "primary2010" else
                                "R3 legacy selection retains an unresolved 2010 regional residual of -4,784 (urban -1,786 / rural -2,998); not population-production complete."),
    }
    (OUT / "linkage_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if scope == "karelia":
        inv_path = INGESTION_ROOT / "source_inventory_karelia.parquet"
        disp_path = INGESTION_ROOT / "source_dispositions_karelia.parquet"
        if inv_path.is_file() and disp_path.is_file():
            write_table(pd.read_parquet(disp_path), "source_dispositions_karelia")
            write_table(pd.read_parquet(inv_path), "source_inventory_karelia")
        write_table(registry, "linkage_observation_registry")
        write_table(selected_for_release, "selected_observations_for_release", True)
        if source_selection_version == "primary2010":
            write_table(source_selection_assertions, "source_selection_assertions", True)
            write_table(published_record_bindings, "published_record_bindings", True)
        control_path = INGESTION_ROOT / "population_controls_karelia.json"
        if control_path.exists():
            (OUT / "population_controls_karelia.json").write_bytes(control_path.read_bytes())
        release_manifest = {
            "release_id": release_name, "scope": "Karelia only", "source_mode": input_status["mode"],
            "source_observations_sha256": input_status.get("pilot_observations_sha256"),
            "source_dispositions_sha256": input_status.get("pilot_dispositions_sha256"),
            "source_selection_version": source_selection_version,
            "source_selection_manifest": selection_manifest,
            "portable_input_verification": INPUT_VERIFICATION,
            "frozen_public_blind_batch_sha256": sha256(REVIEW_ROOT / "karelia_identity_blind_review_batch.csv"),
            "independent_top6_review_sha256": sha256(REVIEW_ROOT / "karelia_identity_independent_review_top6.csv"),
            "kostomuksha_case_review_sha256": sha256(REVIEW_ROOT / "independent_review_kostomuksha.json"),
            "major_city_review_sha256": sha256(REVIEW_ROOT / "independent_review_karelia_major_cities.json"),
            "reviewed_cases": int(len(reviewed_karelia_dossiers) + len(kostomuksha_dossier) + len(major_dossiers)),
            "production_status": ("preliminary Karelia selected-source release; 2010 primary total reconciled; 2002 +3 unassigned; rural source transport requires independent verification; coordinate review remains ten cases only"
                                  if source_selection_version == "primary2010" else
                                  "preliminary scoped case review; not national-rule validation; 2010 population control residual unresolved"),
        }
        if not (inv_path.is_file() and disp_path.is_file()):
            release_manifest["parser_disposition_status"] = "baseline selected snapshot used for unchanged years; no new parser disposition ledger was supplied in portable inputs"
    # Build and query the staging database before the directory becomes a
    # release. The committed database is rebound to the final immutable path.
    # Views keep one canonical copy of Parquet evidence and avoid duplicating
    # large tables into the review database.
    def make_database(directory: Path):
        con = duckdb.connect(str(directory / "linkage_review.duckdb"))
        for path in sorted(directory.glob("*.parquet")):
            existing = con.execute("SELECT table_type FROM information_schema.tables WHERE table_schema='main' AND table_name=?", [path.stem]).fetchone()
            if existing:
                relation_type = "VIEW" if existing[0] == "VIEW" else "TABLE"
                con.execute(f'DROP {relation_type} "{path.stem}"')
            parquet_path = path.as_posix().replace("'", "''")
            con.execute(f'CREATE VIEW "{path.stem}" AS SELECT * FROM read_parquet(\'{parquet_path}\')')
        existing = con.execute("SELECT table_type FROM information_schema.tables WHERE table_schema='main' AND table_name='admitted_coordinate_observations'").fetchone()
        if existing:
            relation_type = "VIEW" if existing[0] == "VIEW" else "TABLE"
            con.execute(f'DROP {relation_type} admitted_coordinate_observations')
        con.execute("CREATE VIEW admitted_coordinate_observations AS SELECT * FROM effective_coordinate_decisions WHERE event_action='apply'")
        result = con.execute("SELECT count(*) FROM admitted_coordinate_observations").fetchone()[0]
        if (directory / "selected_observations_for_release.parquet").exists():
            leaked = con.execute("SELECT count(*) FROM admitted_coordinate_observations d ANTI JOIN selected_observations_for_release s USING(observation_id)").fetchone()[0]
            if leaked:
                con.close()
                raise ValueError(f"release database has {leaked} admitted coordinate rows outside selected source observations")
            joined = con.execute("SELECT count(*) FROM admitted_coordinate_observations d JOIN selected_observations_for_release s USING(observation_id)").fetchone()[0]
            if joined != result:
                con.close()
                raise ValueError("release admitted-coordinate view does not bind one-to-one to selected observations")
        views = con.execute("SELECT count(*) FROM information_schema.views WHERE table_schema='main'").fetchone()[0]
        con.close()
        return int(result), int(views)

    stage_admitted, stage_views = make_database(OUT)
    if scope == "karelia" and (stage_admitted != len(active) or stage_views < 10):
        raise ValueError("staging database validation failed")
    if scope == "karelia":
        staging_dir = OUT
        if validate_only:
            if not final_out.exists():
                raise FileNotFoundError(f"reference release for deterministic validation is missing: {final_out}")
            staged = {p.name: sha256(p) for pattern in ("*.parquet", "*.csv", "*.json") for p in staging_dir.glob(pattern)}
            reference = {p.name: sha256(p) for pattern in ("*.parquet", "*.csv", "*.json") for p in final_out.glob(pattern)
                         if p.name != "release_manifest.json"}
            if staged != reference:
                differing = sorted(set(staged) | set(reference))
                differing = [name for name in differing if staged.get(name) != reference.get(name)]
                raise ValueError(f"staged Parquet outputs are not byte-reproducible: {differing}")
            shutil.rmtree(staging_dir)
            OUT = final_out
            print(json.dumps({"staging_validation": "passed", "reference_release": release_name,
                "artifacts_compared": len(staged), "duckdb_views": stage_views,
                "admitted_coordinate_rows": stage_admitted}, ensure_ascii=False))
        else:
            OUT = final_out
            os.replace(staging_dir, final_out)
            final_admitted, final_views = make_database(OUT)
            if final_admitted != len(active) or final_views != stage_views:
                raise ValueError("committed database validation failed")
            release_manifest["database_validation"] = {"views": final_views, "admitted_coordinate_rows": final_admitted}
            release_manifest["output_artifact_sha256"] = {
                path.name: sha256(path) for path in sorted(OUT.iterdir())
                if path.is_file() and path.name != "release_manifest.json"
            }
            (OUT / "release_manifest.json").write_text(json.dumps(release_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def summarize(observations: pd.DataFrame, claims: pd.DataFrame, proposals: pd.DataFrame,
              effective_decisions: pd.DataFrame, label: str) -> list[dict]:
    rows=[]
    obs_ids=set(observations.observation_id)
    local_claims=claims[claims.observation_id.isin(obs_ids)]
    local_props=proposals[proposals.observation_id.isin(obs_ids)] if not proposals.empty else proposals
    for year, group in observations.groupby("census_year", dropna=False):
        ids=set(group.observation_id)
        cc=local_claims[local_claims.observation_id.isin(ids)]
        pp=local_props[local_props.observation_id.isin(ids)] if not local_props.empty else local_props
        accepted = effective_decisions[effective_decisions.observation_id.isin(ids)] if not effective_decisions.empty else effective_decisions
        admitted_obs = set(accepted.observation_id.dropna()) if not accepted.empty else set()
        pending_props = pp[~pp.observation_id.isin(admitted_obs)] if not pp.empty else pp
        admitted_pop = int(group[group.observation_id.isin(admitted_obs)].population.fillna(0).sum())
        pop=int(group.population.fillna(0).sum())
        is_national = label == "national"
        official_total = (OFFICIAL_TOTALS.get(int(year)) if is_national
                          else KARELIA_OFFICIAL_TOTALS.get(int(year)) if label == "Karelia pilot" else None)
        control_locator = ("Rosstat national control" if is_national else
                           KARELIA_CONTROL_LOCATORS.get(int(year)) if label == "Karelia pilot" else None)
        rows.append({"scope": label, "census_year": int(year), "rows": len(group), "population": pop,
            "official_total": official_total, "difference_vs_official": pop-official_total if official_total is not None else None,
            "rows_with_any_coordinate_claim": int(cc.observation_id.nunique()), "population_with_any_coordinate_claim": int(group[group.observation_id.isin(cc.observation_id)].population.fillna(0).sum()),
            "rows_with_rule_proposal_pending_review": int(pending_props.observation_id.nunique()), "population_with_rule_proposal_pending_review": int(group[group.observation_id.isin(pending_props.observation_id)].population.fillna(0).sum()),
            "rows_admitted_after_independent_review": len(admitted_obs), "population_admitted_after_independent_review": admitted_pop,
            "admitted_population_share_of_selected_snapshot_percent": (100*admitted_pop/pop if pop else None),
            "admitted_population_coverage_of_official_total_percent": (100*admitted_pop/official_total if official_total else None),
            "admitted_rule_rows": int(accepted.decision_class.eq("rule").sum()) if not accepted.empty else 0,
            "admitted_inferred_continuity_rows": int(accepted.decision_class.eq("inferred_continuity").sum()) if not accepted.empty else 0,
            "snapshot_coverage_of_official_total_percent": 100*pop/official_total if official_total else None,
            "official_control_locator": control_locator})
    return rows


def build_karelia_population_source_decisions() -> pd.DataFrame:
    path = INPUTS_ROOT / "evidence/ingestion/karelia_2010_urban_population_comparison.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    frame["decision_status"] = "preliminary_primary_source_selected"
    frame["selected_source"] = "Rosstat 2010 Table 5 sex-sum settlement row"
    frame["selected_population"] = frame.official_population
    frame["secondary_source_population"] = frame.local_population
    frame["difference_secondary_minus_selected"] = frame.delta_local_minus_official
    frame["selection_reason"] = "Direct official Table 5 settlement row with male/female subtotals; secondary parser values retained as alternative claims. Not an identity or coordinate decision."
    frame["official_reference_url"] = "https://rosstat.gov.ru/free_doc/new_site/perepis2010/croc/Documents/Vol11/pub-11-1-4.pdf"
    frame["pilot_source_file"] = artifact_path(path)
    frame["pilot_source_sha256"] = sha256(path)
    return frame


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--inputs-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--identity-review-results", type=Path)
    parser.add_argument("--reviewer")
    parser.add_argument("--scope", choices=["karelia", "mixed", "national"], default="karelia")
    parser.add_argument("--release-name", default="karelia_pilot_release_r2")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--source-selection-version", choices=["legacy-current", "primary2010"], default="legacy-current")
    args = parser.parse_args()
    supplied_roots = (args.data_root, args.inputs_root, args.output_root)
    if any(supplied_roots) and not all(supplied_roots):
        parser.error("portable builds require all three roots: --data-root, --inputs-root, and --output-root")
    if args.data_root:
        ROOT = args.data_root.expanduser().resolve()
    if args.inputs_root:
        INPUTS_ROOT = args.inputs_root.expanduser().resolve()
    if args.output_root:
        OUT_ROOT = args.output_root.expanduser().resolve()
    INGESTION_ROOT = (OUT_ROOT / "ingestion" if (OUT_ROOT / "ingestion").exists() else
                      INPUTS_ROOT / "evidence/ingestion" if (INPUTS_ROOT / "evidence/ingestion").exists() else
                      REBUILD / "evidence/ingestion")
    REVIEW_ROOT = INPUTS_ROOT / "review_inputs" if (INPUTS_ROOT / "review_inputs").exists() else OUT_ROOT
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    if all(supplied_roots):
        INPUT_VERIFICATION = verify_portable_inputs()
    build(args.identity_review_results, args.reviewer, args.scope, args.release_name,
          args.validate_only, args.source_selection_version)
