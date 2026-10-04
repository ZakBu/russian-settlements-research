#!/usr/bin/env python3
"""Build final-config census long rows plus a remapped, separate secondary-history overlay.

No secondary Wikidata observation is admitted as census identity, coordinate, or
population. The overlay's current-place and current-coordinate context is refreshed
from the final selected 2021 census row and canonical accepted point ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import duckdb
import pyarrow.parquet as pq
import gc

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "research_rebuild" / "mass_linkage"))
from build_long_table import build_long_table  # noqa: E402

DEFAULT_CONFIG = REPO / "config/mass_joint_20261004.json"
BASE = Path("/workspace/settlements-work/continuation_20261004")
DEFAULT_HISTORY = BASE / "root/R4/history_application/reviewed_secondary_history_observations.parquet"
DEFAULT_HISTORY_RECEIPT = BASE / "root/R4/history_application/receipt.json"
DEFAULT_FEDERAL_RECEIPT = BASE / "federal_application/receipt.json"
DEFAULT_OUTPUT = BASE / "R4/final_long_preparation/current_long_with_secondary_overlay"
EXPECTED_HISTORY_ROWS = 362_606

HISTORY_CONTEXT_REMAP = {
    "current_place_observation_id": "observation_id",
    "current_place_label": "settlement_name",
    "current_place_type": "settlement_type",
    "current_place_region": "region_raw",
    "current_2021_population": "population_value",
    "current_2021_population_raw": "population_raw",
    "current_2021_source_native_id": "source_native_id",
    "oktmo_current_observed_2021": "oktmo_native_raw",
    "current_population_source_sha256": "source_sha256",
    "current_population_source_path": "source_path",
    "current_population_source_locator": "source_locator",
    "current_population_scope": "population_scope",
    "current_spatial_identity_status": "spatial_identity_status",
    "current_coordinate_carrier_latitude": "latitude",
    "current_coordinate_carrier_longitude": "longitude",
    "current_coordinate_admission_status": "coordinate_admission_status",
    "current_coordinate_quality": "coordinate_quality",
    "current_coordinate_source": "coordinate_source",
    "current_coordinate_provider": "coordinate_provider",
    "current_coordinate_source_record_id": "coordinate_source_record_id",
    "current_coordinate_provenance": "coordinate_provenance",
    "current_coordinate_source_file": "point_source_file",
    "current_coordinate_source_sha256": "point_source_sha256",
    "current_coordinate_source_locator": "point_source_locator",
    "current_coordinate_admission_rule": "coordinate_admission_rule",
    "current_coordinate_temporal_basis": "coordinate_temporal_basis",
}


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_hash(path: str | Path, expected: str, label: str) -> str:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch: expected {expected}, got {actual}: {path}")
    return actual


def _same_values(left: pd.Series, right: pd.Series, label: str) -> None:
    a = left.reset_index(drop=True)
    b = right.reset_index(drop=True)
    if len(a) != len(b):
        raise ValueError(f"census preservation length mismatch for {label}")
    if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
        equal = a.fillna(float("nan")).equals(b.fillna(float("nan")))
    else:
        def canonical(s: pd.Series) -> list[Any]:
            return [None if pd.isna(v) else str(v) for v in s]
        equal = canonical(a) == canonical(b)
    if not equal:
        raise ValueError(f"census source value changed in long projection: {label}")


def assert_census_values_preserved(selected: pd.DataFrame, core: pd.DataFrame) -> None:
    """Prove exact source-row population/native-ID preservation after core build."""
    census = core[core.record_type.eq("census")].copy()
    selected = selected.copy()
    selected["source_record_id"] = selected.source_record_id.astype(str)
    census["source_record_id"] = census.source_record_id.astype(str)
    if len(census) != len(selected) or census.source_record_id.duplicated().any():
        raise ValueError("core census row count/identity differs from selected source observations")
    order = selected.source_record_id.tolist()
    census = census.set_index("source_record_id").loc[order].reset_index()
    _same_values(selected.population, census.population_value, "population_value")
    _same_values(selected.source_population_raw, census.population_raw, "population_raw")
    _same_values(selected.source_raw_line, census.population_source_raw_line, "population_source_raw_line")
    _same_values(selected.source_native_id, census.source_native_id, "source_native_id")
    expected_oktmo = selected.oktmo.where(selected.census_year.astype(int).eq(2021), None)
    _same_values(expected_oktmo, census.oktmo_native_raw, "oktmo_native_raw")


def remap_secondary_history(history: pd.DataFrame, final_census_long: pd.DataFrame,
                            expected_rows: int = EXPECTED_HISTORY_ROWS) -> pd.DataFrame:
    """Refresh current-place context while preserving each secondary observation."""
    if len(history) != expected_rows:
        raise ValueError(f"secondary history row count changed: expected {expected_rows}, got {len(history)}")
    if (~history.record_type.isin({"wiki_literal_series", "wiki_literal_series_candidate_current_binding_review"})).any():
        raise ValueError("secondary-history input has unexpected record_type")
    if history.wikidata_statement_id.isna().any():
        raise ValueError("secondary-history rows must retain their statement GUID")
    if history.latitude.notna().any() or history.longitude.notna().any():
        raise ValueError("secondary history contains asserted historical coordinates; refusing to blend")
    if history.historical_identity_admitted.fillna(True).astype(bool).any():
        raise ValueError("secondary history asserts historical identity; expected candidate association only")
    if history.historical_coordinate_asserted.fillna(True).astype(bool).any():
        raise ValueError("secondary history asserts a historical coordinate; expected null historical coordinates")
    if history.observation_id.duplicated().any():
        raise ValueError("secondary history has duplicate observation_id values")

    current = final_census_long[
        final_census_long.record_type.eq("census") & final_census_long.observation_year.eq(2021)
    ].copy()
    current["source_record_id"] = current.source_record_id.astype(str)
    if current.source_record_id.duplicated().any():
        raise ValueError("final current census mapping has duplicate 2021 source IDs")
    current = current.set_index("source_record_id", drop=False)
    ids = history.current_source_record_id.astype(str)
    missing = sorted(set(ids) - set(current.index.astype(str)))
    if missing:
        raise ValueError(f"{len(missing)} secondary rows lack a final selected 2021 source row; sample={missing[:3]}")

    out = history.copy()
    out["source_record_type_before_display_projection"] = history.record_type
    out["record_type"] = "wiki_literal_series"
    # Keep the former context visible for audit; do not change the history-series
    # entity_id/source_record_id namespace or any historical observation fields.
    out["current_place_entity_id_before_final_remap"] = out.current_place_entity_id
    out["associated_census_entity_id_before_final_remap"] = out.associated_census_entity_id
    out["current_coordinate_carrier_latitude_before_final_remap"] = out.current_coordinate_carrier_latitude
    out["current_coordinate_carrier_longitude_before_final_remap"] = out.current_coordinate_carrier_longitude
    out["current_2021_population_before_final_remap"] = out.current_2021_population
    out["oktmo_current_observed_2021_before_final_remap"] = out.oktmo_current_observed_2021

    remap = dict(HISTORY_CONTEXT_REMAP)
    remap.update({
        "current_place_entity_id": "entity_id",
        "associated_census_entity_id": "entity_id",
        "final_current_oktmo_native_raw_2021": "oktmo_native_raw",
        "current_coordinate_provider_quality_raw": "coordinate_provider_quality_raw",
        "current_coordinate_measurement_date_unknown": "coordinate_measurement_date_unknown",
        "current_coordinate_boundary_comparability_asserted": "boundary_comparability_asserted",
        "current_coordinate_population_scope_comparability_asserted": "population_scope_comparability_asserted",
        "current_coordinate_uncertainty_flags_json": "coordinate_uncertainty_flags_json",
    })
    # Column maps avoid materializing 150k wide dictionaries and millions of
    # scalar mutations. Mapping preserves the observation index and nulls.
    for target_col, source_col in remap.items():
        out[target_col] = ids.map(current[source_col]) if source_col in current else None
    out["current_place_mapping_basis"] = "final_selected_2021_source_record_id_to_core_census_entity"
    out["historical_identity_admitted"] = False
    out["historical_coordinate_asserted"] = False
    out["secondary_statement_guid_duplicate"] = out.wikidata_statement_id.duplicated(keep=False)
    if out.latitude.notna().any() or out.longitude.notna().any():
        raise AssertionError("historical coordinates must remain null")
    if len(out) != len(history):
        raise AssertionError("secondary rows were dropped or duplicated")
    for col in ("observation_id", "source_record_id", "wikidata_statement_id", "population_value",
                "population_raw", "population_value_raw_for_secondary_display", "source_native_id"):
        if col in history.columns:
            _same_values(history[col], out[col], f"secondary.{col}")
    return out


FROZEN_SUPPLEMENT_PINS = {
    "annual_official_observations.parquet": "3f2b0878e547c192470875e6d57355c00738a24da39d6d8206e7e4d7089bf94a",
    "wiki_literal_associations.parquet": "04672327ef9717dfdc8aa628f921b5589c6813b11d410b28717a223fccbbbece",
    "input_manifest.parquet": "15c03537ad7050138ebda5a198198784d41c776c12cbe6222a0fb76194124a97",
}


def frozen_supplement_paths(selected: Path) -> dict[str, Path]:
    """Require the published annual/wiki inputs rather than silently dropping them."""
    paths = {name: selected.with_name(name) for name in FROZEN_SUPPLEMENT_PINS}
    for name, path in paths.items():
        verify_hash(path, FROZEN_SUPPLEMENT_PINS[name], name)
    return paths


def assert_supplements_preserved(core: pd.DataFrame) -> None:
    counts = core.record_type.value_counts().to_dict()
    expected = {"census": 465800, "annual_official": 516, "wiki_literal_series": 34004}
    if counts != expected:
        raise ValueError(f"published observation layers were lost or duplicated: {counts}, expected {expected}")


ANALYSIS_COLUMNS = ["observation_id", "record_type", "entity_id", "associated_census_entity_id",
             "current_place_entity_id", "current_source_record_id", "source_record_id",
             "observation_year", "reference_date", "reference_date_basis", "settlement_name",
             "settlement_type", "region_raw", "district_raw", "population_value", "population_raw",
             "population_value_quality", "population_scope", "association_status", "identity_quality",
             "census_full_chain", "census_2002_status", "census_2010_status", "census_2021_status",
             "latitude", "longitude", "coordinate_quality", "coordinate_admission_status",
             "coordinate_temporal_basis", "boundary_comparability_asserted",
             "current_coordinate_carrier_latitude", "current_coordinate_carrier_longitude",
             "current_coordinate_admission_status", "historical_identity_admitted",
             "historical_coordinate_asserted", "oktmo_native_raw", "oktmo_observed_at_year",
             "oktmo_current_observed_2021", "source_native_id", "source_path", "source_sha256",
             "source_locator", "point_source_file", "point_source_sha256", "point_source_locator",
             "wikidata_statement_id", "secondary_statement_guid_duplicate"]

def build_analysis_view(combined: pd.DataFrame, federal_points: pd.DataFrame,
                        federal_chains: pd.DataFrame) -> pd.DataFrame:
    """Compact display: keep admitted points, reference context and territories explicit."""
    names = ANALYSIS_COLUMNS
    out = combined[[col for col in names if col in combined]].copy()
    out["display_latitude"] = out.latitude
    out["display_longitude"] = out.longitude
    out["display_point_role"] = None
    admitted = out.latitude.notna() & out.longitude.notna()
    out.loc[admitted, "display_point_role"] = "admitted_NP_point_use"
    secondary = (out.record_type.eq("wiki_literal_series") & ~admitted &
                 out.current_coordinate_carrier_latitude.notna() &
                 out.current_coordinate_carrier_longitude.notna())
    out.loc[secondary, "display_latitude"] = out.loc[secondary, "current_coordinate_carrier_latitude"]
    out.loc[secondary, "display_longitude"] = out.loc[secondary, "current_coordinate_carrier_longitude"]
    out.loc[secondary, "display_point_role"] = "secondary_subject_current_reference_context; historical_point_not_admitted"
    fed = federal_points.set_index("source_record_id")
    if fed.index.duplicated().any():
        raise ValueError("federal reference points have duplicate source IDs")
    territory = out.record_type.eq("census") & out.source_record_id.isin(fed.index)
    out.loc[territory, "display_latitude"] = out.loc[territory, "source_record_id"].map(fed.latitude)
    out.loc[territory, "display_longitude"] = out.loc[territory, "source_record_id"].map(fed.longitude)
    out.loc[territory, "display_point_role"] = "reviewed_federal_territory_reference; NP_coverage_separate"
    city_ids = {}
    for row in federal_chains.itertuples(index=False):
        for source_id in json.loads(row.source_record_ids_json):
            if source_id in city_ids:
                raise ValueError("federal typed-continuity source ID belongs to two cities")
            city_ids[source_id] = row.chain_id
    out["federal_typed_continuity_id"] = out.source_record_id.map(city_ids)
    out["display_series_id"] = out.entity_id
    secondary_context = out.current_place_entity_id.notna() & out.record_type.eq("wiki_literal_series")
    out.loc[secondary_context, "display_series_id"] = out.loc[secondary_context, "current_place_entity_id"]
    typed = out.federal_typed_continuity_id.notna()
    out.loc[typed, "display_series_id"] = out.loc[typed, "federal_typed_continuity_id"]
    out["display_series_basis"] = "accepted_census_identity_or_primary_annual_target"
    out.loc[out.record_type.eq("wiki_literal_series"), "display_series_basis"] = "secondary_source_association; historical_identity_quality_separate"
    out.loc[typed, "display_series_basis"] = "typed_city_continuity; observation_scope_changes_preserved"
    return out


def _copy_federal_overlay(config: dict[str, Any], output_dir: Path, receipt_path: Path) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    points = Path(config["federal_points"])
    chains = Path(config["federal_city_continuity"])
    federal_points_hash = receipt["outputs"]["accepted_territory_reference_points.parquet"]
    federal_chains_hash = receipt["outputs"]["accepted_typed_city_continuity.parquet"]
    verify_hash(points, federal_points_hash, "federal territory points")
    verify_hash(chains, federal_chains_hash, "federal city continuity")
    point_df = pd.read_parquet(points)
    chain_df = pd.read_parquet(chains)
    if len(point_df) != 6 or not point_df.admission_status.eq("reviewed_territory_reference_accepted").all():
        raise ValueError("federal territorial point overlay status/count mismatch")
    if len(chain_df) != 3 or chain_df.atomic_same_place_edge.fillna(True).astype(bool).any():
        raise ValueError("federal typed continuity must remain separate and non-atomic")
    p_out = output_dir / "federal_territory_reference_points.parquet"
    c_out = output_dir / "federal_typed_city_continuity.parquet"
    point_df.to_parquet(p_out, index=False)
    chain_df.to_parquet(c_out, index=False)
    return {"receipt": str(receipt_path), "receipt_sha256": sha256(receipt_path),
            "point_rows": len(point_df), "typed_continuity_rows": len(chain_df),
            "points_output_sha256": sha256(p_out), "continuity_output_sha256": sha256(c_out),
            "separate_from_census_and_secondary_long_table": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--secondary-history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--secondary-receipt", type=Path, default=DEFAULT_HISTORY_RECEIPT)
    parser.add_argument("--federal-receipt", type=Path, default=DEFAULT_FEDERAL_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-history-rows", type=int, default=EXPECTED_HISTORY_ROWS)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=False)
    cfg_bytes = args.config.read_bytes()
    config = json.loads(cfg_bytes)
    selected = Path(config["working_population_layer"])
    identity = Path(config["working_identity_graph"])
    points = Path(config["working_point_uses"])
    evidence = selected.with_name("source_evidence.parquet")
    if config.get("working_identity_graph_sha256"):
        verify_hash(identity, config["working_identity_graph_sha256"], "configured final identity graph")
    if config.get("working_point_uses_sha256"):
        verify_hash(points, config["working_point_uses_sha256"], "configured final point ledger")
    history_receipt = json.loads(args.secondary_receipt.read_text(encoding="utf-8"))
    expected_history_hash = history_receipt["outputs"]["reviewed_secondary_history_observations.parquet"]["sha256"]
    history_hash = verify_hash(args.secondary_history, expected_history_hash, "reviewed secondary-history input")
    history_rows = history_receipt["observations"]["observations"]
    if int(history_rows) != args.expected_history_rows:
        raise ValueError(f"history receipt row count mismatch: {history_rows}")
    federal_points = Path(config["federal_points"])
    federal_chains = Path(config["federal_city_continuity"])
    for p in (selected, identity, points, evidence, federal_points, federal_chains):
        if not p.exists():
            raise FileNotFoundError(p)

    supplements = frozen_supplement_paths(selected)
    annual_path = supplements["annual_official_observations.parquet"]
    wiki_path = supplements["wiki_literal_associations.parquet"]
    source_manifest_path = supplements["input_manifest.parquet"]
    census_core_path = args.output / "source_preserving_core.parquet"
    core, builder_manifest = build_long_table(
        census_path=selected, identity_path=identity, coordinates_path=points,
        annual_path=annual_path, output_path=census_core_path,
        wiki_path=wiki_path, source_evidence_path=evidence, source_manifest_path=source_manifest_path,
    )
    assert_supplements_preserved(core)
    selected_df = pd.read_parquet(selected)
    assert_census_values_preserved(selected_df, core)
    del selected_df
    history = pd.read_parquet(args.secondary_history)
    secondary = remap_secondary_history(history, core, expected_rows=args.expected_history_rows)
    secondary_path = args.output / "secondary_history_overlay.parquet"
    secondary.to_parquet(secondary_path, index=False)
    # This is a display layer only. No secondary year-level or national population
    # totals are generated, and duplicate statement GUIDs are retained and flagged.
    history_entity_ids_preserved = bool(secondary.entity_id.equals(history.entity_id))
    guid_duplicate = secondary.secondary_statement_guid_duplicate
    core_summary = {"module": "build_long_table.py", "manifest": builder_manifest,
                    "census_rows": int(core.record_type.eq("census").sum()),
                    "census_values_preserved": True, "published_supplement_layers_preserved": True,
                    "record_type_counts": core.record_type.value_counts().to_dict()}
    secondary_summary = {
        "rows": len(secondary), "unique_observation_ids": int(secondary.observation_id.nunique()),
        "unique_current_source_rows": int(secondary.current_source_record_id.nunique()),
        "history_series_entity_ids_preserved": history_entity_ids_preserved,
        "historical_latitude_longitude_null": bool(secondary.latitude.isna().all() and secondary.longitude.isna().all()),
        "historical_identity_admitted_false": bool((secondary.historical_identity_admitted == False).all()),
        "duplicate_statement_guid_rows_retained_and_flagged": int(guid_duplicate.sum()),
        "source_observation_population_values_modified": False,
        "current_place_mapping": "final current_source_record_id -> 2021 census entity_id",
        "coordinate_context": "from final core census row populated by canonical accepted point ledger; no historical coordinate copied",
    }
    # Release wide frames before streaming the union. Source observations retain
    # all columns; only the compact analysis projection is materialized later.
    del core, history, secondary, guid_duplicate
    gc.collect()
    combined_path = args.output / "settlements_long_with_secondary_history.parquet"
    con = duckdb.connect(config={"threads": 1, "memory_limit": "3GB"})
    con.read_parquet([str(census_core_path), str(secondary_path)], union_by_name=True).create_view("long_union")
    con.execute("COPY long_union TO ? (FORMAT PARQUET, COMPRESSION ZSTD)", [str(combined_path)])
    expected_combined = 500_320 + args.expected_history_rows
    actual_combined = con.execute("SELECT count(*) FROM read_parquet(?)", [str(combined_path)]).fetchone()[0]
    if actual_combined != expected_combined:
        raise AssertionError(f"streamed observation union has {actual_combined} rows, expected {expected_combined}")
    con.close()
    federal_summary = _copy_federal_overlay(config, args.output, args.federal_receipt)
    available = set(pq.read_schema(combined_path).names)
    compact = pd.read_parquet(combined_path, columns=[col for col in ANALYSIS_COLUMNS if col in available])
    analysis = build_analysis_view(compact, pd.read_parquet(federal_points), pd.read_parquet(federal_chains))
    del compact
    analysis_path = args.output / "settlements_analysis_view.csv.gz"
    analysis.to_csv(analysis_path, index=False, compression={"method": "gzip", "mtime": 0})

    receipt = {
        "status": "staged_final_config_long_plus_separate_secondary_history_overlay",
        "census_identity_or_population_admissions": 0,
        "historical_secondary_identity_or_coordinate_admissions": 0,
        "analysis_display_point_roles": analysis.display_point_role.value_counts().to_dict(),
        "analysis_display_coordinates_do_not_override_scientific_coordinate_status": True,
        "secondary_population_year_or_national_sums_emitted": False,
        "config": {"path": str(args.config), "sha256": hashlib.sha256(cfg_bytes).hexdigest()},
        "pinned_inputs": {
            "selected_observations": {"path": str(selected), "sha256": sha256(selected)},
            "source_evidence": {"path": str(evidence), "sha256": sha256(evidence)},
            "published_supplement_layers": {name: {"path": str(path), "sha256": sha256(path)} for name, path in supplements.items()},
            "final_identity_graph": {"path": str(identity), "sha256": sha256(identity)},
            "final_point_uses": {"path": str(points), "sha256": sha256(points)},
            "secondary_history": {"path": str(args.secondary_history), "sha256": history_hash, "rows": args.expected_history_rows},
            "secondary_history_receipt": {"path": str(args.secondary_receipt), "sha256": sha256(args.secondary_receipt)},
        },
        "core_builder": core_summary,
        "secondary_overlay": secondary_summary,
        "federal_overlay": federal_summary,
        "outputs": {},
        "limitations": [
            "Secondary P1082 rows remain source-scoped secondary observations; this overlay does not assert census identity, exact census date, or population-boundary comparability.",
            "No secondary population sums, year totals, or national totals are computed; duplicate statement GUID rows are retained and flagged.",
            "Federal territory reference points and typed-city continuity stay in separate files and are not inserted as atomic census same_place edges.",
        ],
    }
    for p in (census_core_path, secondary_path, combined_path, analysis_path,
              args.output / "federal_territory_reference_points.parquet",
              args.output / "federal_typed_city_continuity.parquet"):
        receipt["outputs"][p.name] = {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}
    (args.output / "run_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "census_rows": receipt["core_builder"]["census_rows"],
                      "secondary_rows": secondary_summary["rows"], "federal_point_rows": federal_summary["point_rows"],
                      "federal_continuity_rows": federal_summary["typed_continuity_rows"]}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
