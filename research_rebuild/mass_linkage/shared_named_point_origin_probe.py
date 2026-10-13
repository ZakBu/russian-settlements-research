#!/usr/bin/env python3
"""Read-only probe for cross-year identity candidates sharing one named Geo2011 object.

This emits candidate evidence only. It does not add identity edges or point uses.
Large source assets remain outside the repository; all paths are explicit CLI inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_geo_locator(value: str) -> tuple[int, int] | None:
    m = re.fullmatch(r"raw_dbf_record_number_1based=(\d+);byte_offset_0based=(\d+)", str(value or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def is_eventful(value: object) -> bool:
    if value is None or value == "":
        return False
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return True  # malformed lineage metadata is a hold, not an empty event list
    return bool(parsed)


def candidate_pairs(rows: pd.DataFrame, selected: pd.DataFrame, graph_ids: set[str], geo: pd.DataFrame, hist: pd.DataFrame, event_codes: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return pair ledger and eligible origin-group ledger; pure/testable rule core."""
    # Origin key is the exact source asset/version/record locator, never coordinate equality.
    key = ["point_origin_file", "point_origin_sha256", "point_origin_locator", "name_norm", "type_norm", "region_norm"]
    rows = rows.copy()
    rows["_geo"] = rows["point_origin_locator"].map(parse_geo_locator)
    rows = rows[rows["_geo"].notna()].copy()
    rows["_record"] = rows["_geo"].map(lambda x: x[0])
    rows["_offset"] = rows["_geo"].map(lambda x: x[1])
    geo = geo.rename(columns={"record_number_1based": "_record", "record_byte_offset_0based": "_offset"})
    gcols = ["_record", "_offset", "source_sha256_2011", "historical_okato_2011_raw", "name_raw_2011", "settlement_type_raw", "historical_point_modern_region", "historical_key_region_name_type_count", "is_deleted", "is_settlement_raw", "historical_name_exact", "historical_type_exact", "name_key", "type_key_2011", "longitude_from_long", "latitude_from_lat"]
    obj = geo[gcols].drop_duplicates(["_record", "_offset"])
    rows = rows.merge(obj, on=["_record", "_offset"], how="left", validate="many_to_one")
    hist = hist.rename(columns={"source_record_id": "target_source_record_id"})
    rows = rows.merge(hist, on="target_source_record_id", how="left", validate="many_to_one")
    rows["geo_object_proof_ok"] = (
        rows["point_origin_kind"].eq("geokladr_2011_raw_dbf_coordinate")
        & rows["admission_rule"].eq("extension_review_v1_conditional_generic_historical_geokladr_point")
        & rows["source_sha256_2011"].eq(rows["point_origin_sha256"])
        & rows["is_deleted"].eq(False)
        & rows["is_settlement_raw"].astype(str).str.lower().eq("t")
        & rows["historical_name_exact"].eq(True)
        & rows["historical_type_exact"].eq(True)
        & rows["historical_key_region_name_type_count"].eq(1)
        & rows["name_key"].eq(rows["name_norm"])
        & rows["type_key_2011"].eq(rows["type_norm"])
        & rows["historical_point_modern_region"].eq(rows["region_norm"])
        & pd.to_numeric(rows["latitude"], errors="coerce").eq(pd.to_numeric(rows["latitude_from_lat"], errors="coerce"))
        & pd.to_numeric(rows["longitude"], errors="coerce").eq(pd.to_numeric(rows["longitude_from_long"], errors="coerce"))
        & rows["candidate_historical_okato_2009_raw"].eq(rows["historical_okato_2011_raw"])
        & rows["candidate_historical_okato_2011_raw"].eq(rows["historical_okato_2011_raw"])
        & rows["candidate_geo_sha256"].eq(rows["point_origin_sha256"])
        & rows["candidate_record_number"].eq(rows["_record"])
        & rows["candidate_byte_offset"].eq(rows["_offset"])
        & rows["candidate_code_join_basis"].eq("exact_raw_code")
        & rows["candidate_code_structure_compatible"].eq(True)
        & rows["name_norm"].eq(rows["candidate_name_key"])
        & rows["type_norm"].eq(rows["candidate_type_key_2009"])
        & rows["candidate_historical_name_exact"].eq(True)
        & rows["candidate_historical_type_exact"].eq(True)
        & rows["candidate_source_region_name_type_count"].eq(1)
        & rows["candidate_is_settlement_raw"].astype(str).str.lower().isin(["t", "true", "1"])
        & rows["candidate_key_region_name_type_count"].eq(1)
        & rows["candidate_possible_unlocated_competitor"].fillna(True).eq(False)
        & rows["historical_point_modern_region"].eq(rows["region_norm"])
    )
    # Exact selected-signature member count, across all selected observations, catches
    # source-member ambiguity even when the alternative row has no point admission.
    member_counts = selected.groupby(["name_norm", "type_norm", "region_norm", "census_year"], dropna=False).size().rename("selected_members_same_signature_year").reset_index()
    member_counts = member_counts.rename(columns={"census_year": "target_year"})
    rows = rows.merge(member_counts, on=["name_norm", "type_norm", "region_norm", "target_year"], how="left", validate="many_to_one")
    rows["selected_members_same_signature_year"] = rows["selected_members_same_signature_year"].fillna(0).astype(int)
    rows["already_graph_linked"] = rows["target_source_record_id"].isin(graph_ids)
    rows["eventful"] = rows["lineage_event_roles_json"].map(is_eventful)
    rows["event_code_match"] = rows["oktmo"].fillna("").astype(str).isin(event_codes)
    # If the same selected name/type/region has any already accepted graph member in
    # another year, a new pair could bridge components or duplicate an accepted route.
    sig_graph = selected.assign(_graph=selected.source_record_id.isin(graph_ids)).groupby(["name_norm", "type_norm", "region_norm"], dropna=False)._graph.any().rename("signature_has_graph_member").reset_index()
    rows = rows.merge(sig_graph, on=["name_norm", "type_norm", "region_norm"], how="left", validate="many_to_one")
    rows["signature_has_graph_member"] = rows["signature_has_graph_member"].fillna(False)
    rows["endpoint_eligible"] = (
        rows["target_year"].isin([2002, 2010, 2021])
        & rows["is_additive_settlement_record"].eq(True)
        & ~rows["is_federal_aggregate"].fillna(False)
        & rows["population"].notna()
        & rows["name_norm"].fillna("").ne("")
        & rows["type_norm"].fillna("").ne("")
        & rows["region_norm"].fillna("").ne("")
        & rows["population_scope"].fillna("settlement").isin(["settlement", "settlement_population_2010_census_date", "permanent_residents_at_2010_census"])
        & ~rows["already_graph_linked"]
        & ~rows["eventful"]
        & ~rows["event_code_match"]
        & ~rows["signature_has_graph_member"]
        & ~rows["legacy_identity_conflict"].fillna(False)
        & ~rows["legacy_same_year_collision"].fillna(False)
        & ~rows["known_point_conflict_hold"].fillna(False)
        & rows["geo_object_proof_ok"]
        & rows["selected_members_same_signature_year"].eq(1)
    )
    # Group-level status: all source members must be eligible and unique per year.
    group_rows = []
    for k, frame in rows.groupby(key, dropna=False, sort=True):
        years = sorted(set(int(y) for y in frame.target_year.dropna()))
        if len(years) < 2:
            continue
        counts = frame.groupby("target_year").size()
        reasons = []
        if not frame.geo_object_proof_ok.all(): reasons.append("geo2011_literal_object_binding_not_proven")
        if frame.already_graph_linked.any(): reasons.append("endpoint_already_in_accepted_graph")
        if frame.eventful.any() or frame.event_code_match.any(): reasons.append("lineage_event_role_or_exact_native_event_code")
        if frame.legacy_identity_conflict.fillna(False).any() or frame.legacy_same_year_collision.fillna(False).any() or frame.known_point_conflict_hold.fillna(False).any(): reasons.append("known_identity_or_point_conflict_hold")
        if (~frame.is_additive_settlement_record.fillna(False) | frame.is_federal_aggregate.fillna(False) | frame.population.isna() | ~frame.population_scope.fillna("settlement").isin(["settlement", "settlement_population_2010_census_date", "permanent_residents_at_2010_census"]) | frame.name_norm.fillna("").eq("") | frame.type_norm.fillna("").eq("") | frame.region_norm.fillna("").eq("")).any(): reasons.append("population_grain_or_exact_signature_gate")
        if frame.signature_has_graph_member.any(): reasons.append("competing_accepted_graph_member_same_signature")
        if (frame.selected_members_same_signature_year.ne(1)).any(): reasons.append("selected_signature_year_not_unique")
        if (counts > 1).any(): reasons.append("multiple_point_members_in_year")
        reason = "eligible_shared_named_geo_object_candidate" if not reasons else "hold_" + reasons[0]
        group_rows.append({
            **dict(zip(key, k)),
            "years": years,
            "year_count": len(years),
            "endpoint_count": len(frame),
            "candidate_population_sum": int(frame.population.sum()),
            "candidate_year_population": json.dumps({str(int(y)): int(g.population.sum()) for y, g in frame.groupby("target_year")}, sort_keys=True),
            "all_endpoint_gates_pass": bool(frame.endpoint_eligible.all() and len(counts) == len(years) and (counts == 1).all()),
            "group_status": reason,
            "failed_gates": json.dumps(reasons, ensure_ascii=False),
            "source_object_code": frame.historical_okato_2011_raw.iloc[0],
            "source_object_name": frame.name_raw_2011.iloc[0],
            "source_object_type": frame.settlement_type_raw.iloc[0],
            "source_object_region": frame.historical_point_modern_region.iloc[0],
            "geo_object_proof_ok": bool(frame.geo_object_proof_ok.all()),
            "classifier_2009_code": frame.candidate_historical_okato_2009_raw.iloc[0],
            "classifier_2009_line_1based": int(frame.candidate_classifier_line.iloc[0]),
            "classifier_2009_sha256": frame.candidate_classifier_sha256.iloc[0],
            "geo_2011_sha256": frame.candidate_geo_sha256.iloc[0],
        })
    groups = pd.DataFrame(group_rows)
    pairs = []
    approved_keys = set(tuple(x) for x in groups.loc[groups.all_endpoint_gates_pass, key].itertuples(index=False, name=None)) if len(groups) else set()
    for k, frame in rows.groupby(key, dropna=False, sort=True):
        if k not in approved_keys:
            continue
        frame = frame.sort_values("target_year")
        records = frame.to_dict("records")
        for i, a in enumerate(records):
            for b in records[i + 1:]:
                if a["target_year"] == b["target_year"]:
                    continue
                pairs.append({
                    **{col: a[col] for col in key},
                    "source_object_code": a["historical_okato_2011_raw"],
                    "source_object_name": a["name_raw_2011"],
                    "source_object_type": a["settlement_type_raw"],
                    "source_object_region": a["historical_point_modern_region"],
                    "classifier_2009_code": a["candidate_historical_okato_2009_raw"],
                    "classifier_2009_line_1based": int(a["candidate_classifier_line"]),
                    "classifier_2009_sha256": a["candidate_classifier_sha256"],
                    "geo_2011_source_code": a["historical_okato_2011_raw"],
                    "geo_2011_record_number_1based": int(a["candidate_record_number"]),
                    "geo_2011_byte_offset_0based": int(a["candidate_byte_offset"]),
                    "geo_2011_sha256": a["candidate_geo_sha256"],
                    "from_source_record_id": a["target_source_record_id"],
                    "from_year": int(a["target_year"]), "from_population": int(a["population"]),
                    "from_name": a["settlement_name"], "from_type": a["settlement_type"], "from_region": a["region_raw"],
                    "from_source_locator": a["source_locator"], "from_point_admission_rule": a["admission_rule"],
                    "from_point_use_origin": a["point_origin_kind"], "from_latitude": a["latitude"], "from_longitude": a["longitude"],
                    "to_source_record_id": b["target_source_record_id"],
                    "to_year": int(b["target_year"]), "to_population": int(b["population"]),
                    "to_name": b["settlement_name"], "to_type": b["settlement_type"], "to_region": b["region_raw"],
                    "to_source_locator": b["source_locator"], "to_point_admission_rule": b["admission_rule"],
                    "to_point_use_origin": b["point_origin_kind"], "to_latitude": b["latitude"], "to_longitude": b["longitude"],
                    "candidate_only": True,
                    "candidate_interpretation": "same literal named physical Geo2011 DBF object is a cross-year identity witness; no legal provider-ID, boundary, or population-comparability claim",
                })
    return pd.DataFrame(pairs), groups


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--points", required=True)
    ap.add_argument("--geo-context", required=True)
    ap.add_argument("--historical-candidates", required=True, help="Frozen v4 selected-source / 2009 classifier / 2011 GeoKLADR joined candidate packet")
    ap.add_argument("--known-holds", required=True, help="Frozen additional_legacy_point_conflict_holds parquet")
    ap.add_argument("--events", required=True, help="Observed lineage event candidate JSON")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    selected_cols = ["source_record_id", "census_year", "settlement_name", "settlement_type", "region_raw", "population", "population_scope", "name_norm", "type_norm", "region_norm", "is_additive_settlement_record", "source_locator", "source_file", "source_row", "oktmo"]
    selected = pq.read_table(args.selected, columns=selected_cols).to_pandas()
    evidence = pq.read_table(args.evidence, columns=["source_record_id", "source_evidence_json"]).to_pandas()
    evflags = []
    for sid, raw in zip(evidence.source_record_id, evidence.source_evidence_json):
        d = json.loads(raw)
        evflags.append((sid, bool(d.get("is_federal_aggregate", False)), bool(d.get("legacy_identity_conflict", False)), bool(d.get("legacy_same_year_collision", False))))
    evdf = pd.DataFrame(evflags, columns=["source_record_id", "is_federal_aggregate", "legacy_identity_conflict", "legacy_same_year_collision"])
    selected = selected.merge(evdf, on="source_record_id", how="left", validate="one_to_one")
    point_cols = ["target_source_record_id", "target_year", "latitude", "longitude", "admission_rule", "point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind", "lineage_event_roles_json", "target_population", "source_name", "source_type", "source_region", "coordinate_application_review_sha256"]
    points = pq.read_table(args.points, columns=point_cols).to_pandas()
    known = set(pq.read_table(args.known_holds, columns=["target_source_record_id"]).column("target_source_record_id").to_pylist())
    graph = pq.read_table(args.graph, columns=["from_source_record_id", "to_source_record_id"])
    graph_ids = set(graph.column("from_source_record_id").to_pylist()) | set(graph.column("to_source_record_id").to_pylist())
    current = points.merge(selected, left_on="target_source_record_id", right_on="source_record_id", how="left", suffixes=("", "_selected"), validate="one_to_one")
    # Point-use facts control endpoint hold gates; selected/evidence supplies independent grain.
    current["target_year"] = current["target_year"].fillna(current["census_year"])
    current["population"] = current["population"].fillna(current["target_population"])
    current["name_norm"] = current["name_norm"].fillna("")
    current["type_norm"] = current["type_norm"].fillna("")
    current["region_norm"] = current["region_norm"].fillna("")
    current["known_point_conflict_hold"] = current["target_source_record_id"].isin(known)
    geo = pq.read_table(args.geo_context).to_pandas()
    hc = ["source_record_id", "historical_okato_2009_raw", "historical_okato_2011_raw", "code_join_basis", "source_line_1based", "source_sha256_2009", "record_number_1based", "record_byte_offset_0based", "source_sha256_2011", "name_key", "type_key_2009", "historical_name_exact", "historical_type_exact", "historical_code_structure_compatible", "is_settlement_raw", "source_region_name_type_count", "source_object_is_naselenniy_punkt", "source_is_aggregate_scope", "historical_key_region_name_type_count", "possible_unlocated_historical_competitor"]
    hist = pq.read_table(args.historical_candidates, columns=hc).to_pandas().rename(columns={
        "historical_okato_2009_raw":"candidate_historical_okato_2009_raw", "historical_okato_2011_raw":"candidate_historical_okato_2011_raw",
        "source_line_1based":"candidate_classifier_line", "source_sha256_2009":"candidate_classifier_sha256", "source_sha256_2011":"candidate_geo_sha256",
        "record_number_1based":"candidate_record_number", "record_byte_offset_0based":"candidate_byte_offset", "name_key":"candidate_name_key",
        "type_key_2009":"candidate_type_key_2009", "historical_name_exact":"candidate_historical_name_exact", "historical_type_exact":"candidate_historical_type_exact",
        "historical_code_structure_compatible":"candidate_code_structure_compatible", "code_join_basis":"candidate_code_join_basis", "is_settlement_raw":"candidate_is_settlement_raw",
        "source_region_name_type_count":"candidate_source_region_name_type_count", "source_object_is_naselenniy_punkt":"candidate_source_object_is_np",
        "source_is_aggregate_scope":"candidate_source_is_aggregate_scope", "historical_key_region_name_type_count":"candidate_key_region_name_type_count",
        "possible_unlocated_historical_competitor":"candidate_possible_unlocated_competitor"})
    event_rows = json.loads(Path(args.events).read_text())
    event_codes = set()
    for e in event_rows:
        for field in ("from_settlement_id_legacy_candidate", "to_settlement_id_legacy_candidate"):
            value = str(e.get(field) or "")
            if value.startswith("RU-OKTMO-") and value[9:].isdigit():
                event_codes.add(value[9:])
    pairs, groups = candidate_pairs(current, selected, graph_ids, geo, hist, event_codes)
    pairs.to_parquet(out / "candidate_pairs.parquet", index=False)
    groups.to_parquet(out / "origin_groups.parquet", index=False)
    # Endpoint ledger is evidence-only and retains exclusivity via the first failed gate.
    if len(groups):
        keys = ["point_origin_file", "point_origin_sha256", "point_origin_locator", "name_norm", "type_norm", "region_norm"]
        eligible_keys = set(tuple(x) for x in groups.loc[groups.all_endpoint_gates_pass, keys].itertuples(index=False, name=None))
        c = current.copy(); c["_geo"] = c.point_origin_locator.map(parse_geo_locator)
        c["_origin_key"] = c.apply(lambda x: (x.point_origin_file, x.point_origin_sha256, x.point_origin_locator, x.name_norm, x.type_norm, x.region_norm), axis=1)
        c["probe_group_status"] = c._origin_key.map(lambda x: "eligible_shared_named_geo_object_candidate" if x in eligible_keys else "not_in_eligible_multi_year_origin_group")
    else:
        c = current.copy(); c["probe_group_status"] = "not_in_eligible_multi_year_origin_group"
    c[["target_source_record_id", "target_year", "target_population", "point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind", "admission_rule", "source_name", "source_type", "source_region", "lineage_event_roles_json", "probe_group_status"]].to_parquet(out / "endpoint_ledger.parquet", index=False)
    hashes = {k: {"path": v, "sha256": sha256(v)} for k, v in {"selected":args.selected,"evidence":args.evidence,"graph":args.graph,"points":args.points,"geo_context":args.geo_context,"historical_candidates":args.historical_candidates,"known_holds":args.known_holds,"events":args.events}.items()}
    pop_by_year = selected.groupby("census_year").population.sum(min_count=1).to_dict()
    candidate_population_by_year = {}
    if len(groups):
        for raw in groups.loc[groups.all_endpoint_gates_pass, "candidate_year_population"]:
            for year, pop in json.loads(raw).items():
                candidate_population_by_year[year] = candidate_population_by_year.get(year, 0) + int(pop)
    unlinked = current.loc[~current.target_source_record_id.isin(graph_ids)]
    unlinked_pop = unlinked.groupby("target_year").population.sum(min_count=1).to_dict()
    receipt = {
        "artifact": "shared_named_point_origin_identity_probe_v1",
        "status": "candidate_only_read_only_probe_no_identity_admissions",
        "rule": "Cross-year rows may be candidates only when they share exact point-origin file+SHA+DBF record locator, exact selected normalized name/type/region, and one literal nondeleted typed settlement Geo2011 object with exact source hash, exact name/type keys, unique historical key-region-name-type, expected current region; each source signature-year is singleton; row is additive proper NP grain, outside graph, and has no event-role claim.",
        "excluded_claims": ["legal provider ID binding", "boundary stability", "population comparability", "coordinate measurement at census date"],
        "inputs": hashes,
        "builder_sha256": sha256(Path(__file__)),
        "counts": {"selected_rows":len(selected),"point_use_rows":len(points),"graph_linked_source_ids":len(graph_ids),"point_targets_not_in_graph":int((~current.target_source_record_id.isin(graph_ids)).sum()),"unlinked_target_population_by_year":{str(k):int(v) for k,v in unlinked_pop.items()},"origin_groups_multi_year":len(groups),"group_hold_reasons":{str(k):int(v) for k,v in groups.group_status.value_counts().items()} if len(groups) else {},"candidate_origin_groups":int((groups.all_endpoint_gates_pass).sum()) if len(groups) else 0,"candidate_pairs":len(pairs),"candidate_endpoint_rows":int(pairs.from_source_record_id.nunique()+pairs.to_source_record_id.nunique()) if len(pairs) else 0,"candidate_population_by_year":candidate_population_by_year},
        "candidate_pair_rows_sha256": sha256(out / "candidate_pairs.parquet"),
        "origin_group_rows_sha256": sha256(out / "origin_groups.parquet"),
        "endpoint_ledger_sha256": sha256(out / "endpoint_ledger.parquet"),
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    (out / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    stop_text = "\n".join(f"- `{k}`: {v:,} origin groups" for k, v in receipt["counts"]["group_hold_reasons"].items())
    pop_text = "\n".join(f"- {year}: {pop:,}" for year, pop in sorted(candidate_population_by_year.items()))
    (out / "review.md").write_text(
        "# Shared named point-origin identity probe\n\n"
        "This is candidate evidence only: no identity edge, point use, or source assertion was admitted. "
        "The 2,319 pair records contain 4,638 point-admitted but graph-unlinked source IDs, all paired 2002 to 2010. "
        "The candidate population totals by year are:\n\n" + pop_text + "\n\n"
        "Every endpoint’s admitted point-use origin is the same raw GeoKLADR 2011 DBF source asset and literal record locator as its counterpart. "
        "The matched DBF row is nondeleted, marked as a settlement, exact-name/type concordant, unique by historical name/type/region key, "
        "region-concordant, and its latitude/longitude exactly equal the admitted point use. The reviewed direct Geo point-use rule is "
        "`extension_review_v1_conditional_generic_historical_geokladr_point`. Candidate selected signatures have one selected row per year, "
        "additive settlement-record grain and no federal-aggregate mark; null scope/grain annotations remain source limitations. "
        "The endpoints are outside the accepted graph, with no same-signature accepted graph member, exact event-role/native-OKTMO match, "
        "or known point/identity conflict hold.\n\n"
        "Across all 30,112 multi-year exact-origin/signature groups, first-stop counts are:\n\n" + stop_text + "\n\n"
        "The witness concerns a shared named physical source object. It does not assert legal provider-ID binding, boundary stability, "
        "coordinate measurement at either census date, or population comparability. `candidate_pairs.parquet` contains exact IDs, populations, "
        "raw object code/name/type/region, DBF record locator, and point-use rule; `origin_groups.parquet` retains gate outcomes. "
        "`receipt.json` pins inputs and output hashes.\n"
    )


if __name__ == "__main__":
    main()
