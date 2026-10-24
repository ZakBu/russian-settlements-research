#!/usr/bin/env python3
"""National municipal agricultural context and separate organisation headcounts.

Municipal totals are not settlement outputs, workers of a legal entity are not
jobs at its registered address, and neither layer is an institution mass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

try:
    from .match import build_reference, normalize_name, normalize_region
except ImportError:
    from match import build_reference, normalize_name, normalize_region

AGRICULTURE_SHA = "e6ca2906f49fd0fe561ae98f535206990cebc2675884571bced546c3374c198d"
FNS_SHA = "a4a2972b5d424d49424723cb77837f4605f390ee6edef42f382a0b9504f3f85a"
METRICS = [
    ("sown_area_ha", "Y48007018", "kultur", "Вся посевная площадь", "Гектар", False),
    ("grain_sown_ha", "Y48007018", "kultur", "Зерновые и зернобобовые культуры — всего", "Гектар", False),
    ("feed_sown_ha", "Y48007018", "kultur", "Кормовые культуры — всего", "Гектар", False),
    ("technical_sown_ha", "Y48007018", "kultur", "Технические культуры — всего", "Гектар", False),
    ("cattle_heads", "Y48007020", "skot", "Крупный рогатый скот", "Голова", False),
    ("grain_yield_centner_per_harvested_ha", "Y48007025", "kultur", "Зерновые и зернобобовые культуры — всего", "Центнер с гектара убранной площади", False),
    ("output_nominal_thousand_rub", "Y48007010", None, None, "Тысяча рублей", True),
    ("crop_output_nominal_thousand_rub", "Y48007011", None, None, "Тысяча рублей", True),
    ("livestock_output_nominal_thousand_rub", "Y48007012", None, None, "Тысяча рублей", True),
]
RAW_COLUMNS = ["oktmo", "municipality", "region_name", "mun_district", "mun_level", "year", "kategor", "kultur", "skot",
               "indicator_code", "indicator_name", "indicator_unit", "indicator_value", "oktmo_stable", "oktmo_history", "oktmo_year_from", "oktmo_year_to"]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save(frame, path):
    temporary = path.with_name(path.name + ".part")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def extract_agriculture(path, out):
    """Filter the exact source rows, then quarantine duplicate semantic keys."""
    primary_full = sha(path) == AGRICULTURE_SHA
    collected = []
    scanned = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=150000):
        if "metric" in batch.schema.names:
            frame = batch.to_pandas()
            collected.append(frame)
            scanned += len(batch)
            continue
        codes = batch.column("indicator_code")
        mask = pc.equal(codes, "__no_indicator__")
        for _, code, dimension, label, _, _ in METRICS:
            selected = pc.equal(codes, code)
            if dimension:
                selected = pc.and_(selected, pc.equal(batch.column(dimension), label))
            mask = pc.or_(mask, selected)
        positions = np.flatnonzero(mask.to_numpy(zero_copy_only=False)) + scanned + 1
        frame = batch.filter(mask).select(RAW_COLUMNS).to_pandas()
        frame["source_row_1based"] = positions
        scanned += len(batch)
        if len(frame):
            collected.append(frame)
    if not collected:
        raise ValueError("Agricultural source has no selected observations")
    raw = pd.concat(collected, ignore_index=True)
    if "metric" in raw:
        # Rebuild derived validity states from original cells, not old flags.
        raw = raw[[*RAW_COLUMNS, "source_row_1based", "metric", "nominal_current_prices"]].copy()
    if "metric" not in raw:
        raw["metric"] = pd.NA
        raw["nominal_current_prices"] = False
        for metric, code, dimension, label, unit, nominal in METRICS:
            selected = raw.indicator_code.eq(code)
            if dimension:
                selected &= raw[dimension].eq(label)
            if not raw.loc[selected, "indicator_unit"].eq(unit).all():
                raise ValueError(f"Unit conflict for {metric}")
            raw.loc[selected, "metric"] = metric
            raw.loc[selected, "nominal_current_prices"] = nominal
    raw["municipality_code"] = raw.oktmo.astype("string")
    raw["category_literal"] = raw.kategor
    raw["value_status"] = "observed"
    raw.loc[raw.indicator_value.isna(), "value_status"] = "source_missing"
    raw.loc[raw.indicator_value.eq(999999999), "value_status"] = "suspect_source_code_excluded_pending_dictionary"
    raw.loc[raw.indicator_value.lt(0), "value_status"] = "negative_source_value_held"
    raw["value"] = raw.indicator_value.where(raw.value_status.eq("observed"))
    start = pd.to_numeric(raw.oktmo_year_from, errors="coerce")
    end = pd.to_numeric(raw.oktmo_year_to, errors="coerce")
    raw["source_interval_status"] = "not_declared"
    declared = start.notna() | end.notna()
    within = start.fillna(-9999).le(raw.year) & end.fillna(9999).ge(raw.year)
    raw.loc[declared & within, "source_interval_status"] = "within_declared_interval"
    raw.loc[declared & ~within, "source_interval_status"] = "outside_declared_interval_held"
    raw.loc[declared & ~within, "value"] = np.nan
    raw.loc[declared & ~within, "value_status"] = "outside_declared_code_interval"
    keys = ["municipality_code", "year", "metric", "category_literal"]
    duplicated = raw.duplicated(keys, keep=False)
    save(raw.loc[duplicated].copy(), out / "agriculture_duplicate_keys_held.parquet")
    raw["duplicate_semantic_key"] = duplicated
    raw.loc[duplicated, "value"] = np.nan
    raw.loc[duplicated, "value_status"] = "duplicate_source_key_held"
    save(raw, out / "agriculture_selected_source_rows.parquet")
    valid = raw[~duplicated].copy()
    snapshots = []
    for year in [2010, 2021]:
        z = valid[valid.year.eq(year)].copy()
        z["reference_role"] = str(year)
        snapshots.append(z)
    # The last observed number is dated explicitly; it need not be 2024.
    grouped = ["municipality_code", "metric", "category_literal"]
    observed = valid[valid.value.notna()].sort_values("year").drop_duplicates(grouped, keep="last").copy()
    observed["reference_role"] = "latest_observed"
    snapshots.append(observed)
    snapshot = pd.concat(snapshots, ignore_index=True)
    snapshot["source_id"] = "BDMO_SECTION7_20250918"
    snapshot["agriculture_context_not_own_NP"] = True
    snapshot["agriculture_context_not_mass"] = True
    snapshot["historical_boundary_equivalence_proven"] = False
    save(snapshot, out / "municipal_agriculture_snapshots.parquet")
    return snapshot, {"original_full_parquet_verified": primary_full, "source_rows_scanned": scanned,
                      "selected_source_rows": len(raw), "duplicate_source_rows_held": int(duplicated.sum()),
                      "snapshot_observations": len(snapshot), "native_codes_with_selected_data": int(raw.municipality_code.nunique()),
                      "snapshot_native_codes": int(snapshot.municipality_code.nunique())}


def attach_parent_context(reference, parent_path, snapshot, out):
    bridge = pd.read_parquet(parent_path)
    required = {"native_np_oktmo11", "native_source_parent_oktmo8", "region", "object_name", "parent_relation_rule"}
    if not required.issubset(bridge):
        raise ValueError("Expected explicit typed 2021 census-parent bridge, not guessed code truncation")
    bridge["region_norm"] = bridge.region.map(normalize_region)
    bridge["source_name_norm"] = bridge.object_name.map(normalize_name)
    bridge = bridge.rename(columns={"native_np_oktmo11": "oktmo", "native_source_parent_oktmo8": "agri_municipality_code",
                                    "id": "legacy_parent_axis_id"})
    current = reference[reference.has_2021_record][["root", "source_record_id", "region_norm", "name_norm", "oktmo"]]
    candidates = current.merge(bridge[["legacy_parent_axis_id", "region_norm", "source_name_norm", "oktmo", "agri_municipality_code", "parent_relation_rule"]],
                               on=["region_norm", "oktmo"], how="inner", validate="many_to_many")
    candidates["exact_normalized_name_agreement"] = candidates.name_norm.eq(candidates.source_name_norm)
    save(candidates, out / "primary_parent_identity_candidates.parquet")
    name_conflicts = candidates[~candidates.exact_normalized_name_agreement].root.nunique()
    candidates = candidates[candidates.exact_normalized_name_agreement].copy()
    count = candidates.groupby("root").size()
    unique_roots = count[count.eq(1)].index
    accepted = candidates[candidates.root.isin(unique_roots)]
    base = reference[["root", "source_record_id", "name", "region", "district", "oktmo", "population_role", "ordinary_spatial_2021"]].copy()
    node = base.merge(accepted[["root", "legacy_parent_axis_id", "agri_municipality_code", "parent_relation_rule"]], on="root", how="left", validate="one_to_one")
    node["agri_parent_match_status"] = np.where(node.agri_municipality_code.notna(), "matched_explicit2021_code_region_name", "unknown_no_qualified_primary_parent")
    node.loc[node.root.isin(count[count.gt(1)].index), "agri_parent_match_status"] = "ambiguous_primary_parent_held"
    node["agriculture_context_not_own_NP"] = True
    node["do_not_sum_repeated_municipal_context"] = True
    node["agriculture_context_not_mass"] = True
    node["historical_boundary_equivalence_proven"] = False
    all_categories = snapshot[snapshot.category_literal.eq("Хозяйства всех категорий")]
    for metric, *_ in METRICS:
        for role in ["2010", "2021", "latest_observed"]:
            z = all_categories[all_categories.metric.eq(metric) & all_categories.reference_role.eq(role)]
            if z.municipality_code.duplicated().any():
                raise ValueError("Nonunique agricultural source context")
            values = z.set_index("municipality_code")
            node[f"agri_{metric}_{role}_municipal_context"] = node.agri_municipality_code.map(values.value)
            if role == "latest_observed":
                node[f"agri_{metric}_latest_source_year"] = node.agri_municipality_code.map(values.year).astype("Int64")
    save(node, out / "settlement_agriculture_context.parquet")
    spatial = node[node.ordinary_spatial_2021]
    stats = {"census_chain_rows": len(node), "ordinary_spatial2021_rows": len(spatial),
             "ordinary_spatial2021_with_explicit_parent": int(spatial.agri_municipality_code.notna().sum()),
             "ordinary_spatial2021_parent_unknown": int(spatial.agri_municipality_code.isna().sum()),
             "census2021_code_region_candidates_with_name_conflict": int(name_conflicts)}
    for metric in ["sown_area_ha", "grain_sown_ha", "cattle_heads", "grain_yield_centner_per_harvested_ha"]:
        stats[f"ordinary_spatial2021_with_{metric}_context_2021"] = int(spatial[f"agri_{metric}_2021_municipal_context"].notna().sum())
    stats["ordinary_spatial2021_with_grain_yield_context_2010"] = int(spatial.agri_grain_yield_centner_per_harvested_ha_2010_municipal_context.notna().sum())
    return node, stats


def extract_fns(path, out):
    if sha(path) != FNS_SHA:
        raise ValueError("FNS archive differs from dated checked source")
    destination = out / "organisation_headcount_2025.parquet"
    temporary = destination.with_name(destination.name + ".part")
    buffer, seen = [], set()
    writer = None
    observations, zeros, members = 0, 0, 0
    def flush():
        nonlocal writer
        if not buffer:
            return
        table = pa.Table.from_pylist(buffer)
        if writer is None:
            writer = pq.ParquetWriter(temporary, table.schema, compression="zstd",
                                      use_dictionary=["reference_date", "publication_date", "source_member", "source_id", "reference_year"])
        writer.write_table(table)
        buffer.clear()
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if not info.filename.endswith(".xml"):
                continue
            members += 1
            root = ET.fromstring(archive.read(info))
            for document in root.findall("Документ"):
                organisation, count = document.find("СведНП"), document.find("СведССЧР")
                if organisation is None or count is None:
                    raise ValueError("FNS source document missing mandatory fields")
                inn, value = organisation.attrib.get("ИННЮЛ"), count.attrib.get("КолРаб", "")
                if not inn or not re_full_inn(inn) or not value.isdigit() or inn in seen:
                    raise ValueError("Invalid or duplicate organisation headcount record")
                if document.attrib["ДатаСост"] != "31.12.2025":
                    raise ValueError("FNS source mixes reference years")
                seen.add(inn)
                number = int(value)
                observations += 1
                zeros += number == 0
                buffer.append({"inn": inn, "organisation_name": organisation.attrib["НаимОрг"],
                               "annual_average_employees": number, "reference_year": 2025,
                               "reference_date": document.attrib["ДатаСост"], "publication_date": document.attrib["ДатаДок"],
                               "source_member": info.filename, "source_id": "FNS_SSHR_20260925",
                               "headcount_is_settlement_jobs": False, "actual_worksite_geography_available": False})
                if len(buffer) >= 100000:
                    flush()
    flush()
    if writer:
        writer.close()
        temporary.replace(destination)
    return {"source_id": "FNS_SSHR_20260925", "whole_archive_scanned": True, "xml_members": members,
            "unique_organisations": observations, "organisations_with_zero_reported_employees": zeros,
            "reference_year": 2025, "settlement_jobs_inferred": False,
            "parquet_bytes": destination.stat().st_size, "parquet_sha256": sha(destination)}


def re_full_inn(value):
    return len(value) == 10 and value.isdigit()


def reuse_fns_parquet(path, out):
    """Validate a packaged full organisation snapshot; do not claim XML reread."""
    required = {"inn", "organisation_name", "annual_average_employees", "reference_year", "reference_date", "publication_date",
                "source_member", "source_id", "headcount_is_settlement_jobs", "actual_worksite_geography_available"}
    source = pq.ParquetFile(path)
    if not required.issubset(source.schema_arrow.names):
        raise ValueError("Incomplete packaged FNS snapshot schema")
    rows, zeros, seen = 0, 0, set()
    columns = ["inn", "annual_average_employees", "reference_year", "source_id", "headcount_is_settlement_jobs", "actual_worksite_geography_available"]
    for batch in source.iter_batches(batch_size=100000, columns=columns):
        frame = batch.to_pandas()
        if not frame.reference_year.eq(2025).all() or not frame.source_id.eq("FNS_SSHR_20260925").all():
            raise ValueError("Packaged FNS snapshot has another source or year")
        if frame.headcount_is_settlement_jobs.any() or frame.actual_worksite_geography_available.any():
            raise ValueError("Packaged FNS snapshot misstates geographical grain")
        counts = pd.to_numeric(frame.annual_average_employees, errors="coerce")
        if counts.isna().any() or counts.lt(0).any() or not counts.eq(np.floor(counts)).all():
            raise ValueError("Invalid packaged employee count")
        for inn in frame.inn:
            if not isinstance(inn, str) or not re_full_inn(inn) or inn in seen:
                raise ValueError("Invalid or repeated INN in packaged FNS snapshot")
            seen.add(inn)
        rows += len(frame)
        zeros += int(counts.eq(0).sum())
    if rows != 2049517 or zeros != 393210:
        raise ValueError("Packaged FNS snapshot does not reconcile with checked national source")
    destination = out / "organisation_headcount_2025.parquet"
    if path.resolve() != destination.resolve():
        temporary = destination.with_name(destination.name + ".part")
        shutil.copyfile(path, temporary)
        temporary.replace(destination)
    return {"source_id": "FNS_SSHR_20260925", "whole_archive_scanned": False,
            "packaged_parquet_rows_validated": rows, "unique_organisations": rows,
            "organisations_with_zero_reported_employees": zeros, "reference_year": 2025,
            "upstream_archive_sha256": FNS_SHA, "settlement_jobs_inferred": False,
            "parquet_bytes": destination.stat().st_size, "parquet_sha256": sha(destination)}


def attach_partial_workforce(path, reference, out):
    frame = pd.read_parquet(path)
    # Raw exporter values must not become measurements before workbook checks.
    if "column_semantics_verified" not in frame:
        raise ValueError("Workforce input lacks primary-column verification status")
    if "source_record_id" not in frame:
        raise ValueError("Workforce input lacks census identity")
    frame["total_settlement_jobs"] = np.nan
    frame["source_is_complete_local_employment"] = False
    save(frame, out / "partial_workforce_source_rows.parquet")
    verified = frame[frame.column_semantics_verified.fillna(False)].copy()
    required = {"value", "value_status", "observation_year", "source_id", "match_status"}
    if not required.issubset(verified):
        raise ValueError("Verified workforce observations lack source value/year/status")
    qualified = verified[verified.source_record_id.notna() & verified.match_status.eq("matched")].copy()
    qualified = qualified[qualified.source_record_id.isin(reference.source_record_id.dropna())]
    qualified = qualified[pd.to_numeric(qualified.observation_year, errors="coerce").eq(2025)]
    # Recheck grain independently; old saved match statuses are not authority.
    held_grain = pd.Series(False, index=qualified.index)
    if "source_row_grain" in qualified:
        held_grain |= qualified.source_row_grain.isin(["city_aggregate", "municipal_aggregate", "regional_aggregate", "aggregate_not_settlement"])
    if "source_oktmo" in qualified:
        codes = qualified.source_oktmo.astype("string")
        held_grain |= codes.str.fullmatch(r"\d{8}", na=False)
        held_grain |= codes.str.fullmatch(r"\d{11}", na=False) & codes.str.endswith("000", na=False) & ~codes.isin(set(reference.oktmo.dropna()))
    stale_aggregate_matches = int(held_grain.sum())
    qualified = qualified[~held_grain].copy()
    numeric = qualified[qualified.value_status.eq("observed") & pd.to_numeric(qualified.value, errors="coerce").notna()].copy()
    numeric["value"] = pd.to_numeric(numeric.value)
    if numeric.value.lt(0).any():
        raise ValueError("Negative verified workforce count")
    counts = numeric.groupby("source_record_id").value.nunique()
    conflicts = set(counts[counts.gt(1)].index)
    save(qualified[qualified.source_record_id.isin(conflicts)], out / "partial_workforce_conflicts_held.parquet")
    accepted = numeric[~numeric.source_record_id.isin(conflicts)].drop_duplicates("source_record_id")
    accepted = accepted.set_index("source_record_id")
    result = reference[["root", "source_record_id", "ordinary_spatial_2021"]].copy()
    result["partial_organisation_workforce_2025"] = result.source_record_id.map(accepted.value)
    result["partial_workforce_status"] = "unknown_no_verified_geographic_observation"
    result.loc[result.source_record_id.isin(set(qualified.source_record_id)), "partial_workforce_status"] = "verified_source_non_numeric"
    suppressed = set(qualified.loc[qualified.value_status.eq("suppressed"), "source_record_id"])
    result.loc[result.source_record_id.isin(suppressed), "partial_workforce_status"] = "source_suppressed"
    result.loc[result.partial_organisation_workforce_2025.notna(), "partial_workforce_status"] = "observed_partial_organisation_workforce"
    result.loc[result.source_record_id.isin(conflicts), "partial_workforce_status"] = "conflicting_values_held"
    result["reference_year"] = 2025
    row_counts = qualified.groupby("source_record_id").size()
    source_ids = qualified.groupby("source_record_id").source_id.first()
    result["partial_workforce_source_row_count"] = result.source_record_id.map(row_counts).fillna(0).astype(int)
    result["partial_workforce_source_id"] = result.source_record_id.map(source_ids)
    result["partial_workforce_observation_year"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    result.loc[result.partial_workforce_source_row_count.gt(0), "partial_workforce_observation_year"] = 2025
    result["total_settlement_jobs"] = np.nan
    result["excludes_small_business"] = True
    result["excludes_external_parttimers"] = True
    result["measures_resident_workers"] = False
    result["can_be_used_as_resident_employment_rate"] = False
    save(result, out / "settlement_partial_workforce.parquet")
    agriculture_path = out / "settlement_agriculture_context.parquet"
    if agriculture_path.exists():
        combined = pd.read_parquet(agriculture_path).merge(result.drop(columns=["source_record_id", "ordinary_spatial_2021"]), on="root", how="left", validate="one_to_one")
        save(combined, out / "settlement_context.parquet")
    return {"source_rows": len(frame), "primary_column_verified_rows": len(verified),
            "matched_verified_rows": int(verified.source_record_id.notna().sum()),
            "qualified_matched_numeric_rows": len(numeric), "unique_settlements_observed": len(accepted),
            "stale_aggregate_matches_independently_held": stale_aggregate_matches,
            "spatial_settlements_observed": int(result.loc[result.ordinary_spatial_2021, "partial_organisation_workforce_2025"].notna().sum()),
            "conflicting_settlement_values_held": len(conflicts), "total_jobs_inferred": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--agriculture", type=Path, required=True)
    parser.add_argument("--parent-bridge", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    fns = parser.add_mutually_exclusive_group()
    fns.add_argument("--fns-zip", type=Path)
    fns.add_argument("--fns-parquet", type=Path)
    parser.add_argument("--workforce", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reference = build_reference(args.population)
    save(reference, args.output / "census_reference.parquet")
    snapshots, agriculture_audit = extract_agriculture(args.agriculture, args.output)
    _, attachment_audit = attach_parent_context(reference, args.parent_bridge, snapshots, args.output)
    result = {"status": "national_context_not_settlement_jobs_or_own_agricultural_output",
              "agriculture": agriculture_audit, "attachment": attachment_audit,
              "derived_census_code_normalization": {"raw_population_base_modified": False,
                                                    "10digit_source_codes_leading_zero_restored": int(reference.oktmo_leading_zero_restored.sum())}}
    inputs = [args.population, args.agriculture, args.parent_bridge]
    if args.fns_zip:
        result["organisation_headcounts"] = extract_fns(args.fns_zip, args.output)
        inputs.append(args.fns_zip)
    if args.fns_parquet:
        result["organisation_headcounts"] = reuse_fns_parquet(args.fns_parquet, args.output)
        inputs.append(args.fns_parquet)
    if args.workforce:
        result["partial_workforce"] = attach_partial_workforce(args.workforce, reference, args.output)
        inputs.append(args.workforce)
    result["inputs"] = [{"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)} for p in inputs]
    (args.output / "context_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
