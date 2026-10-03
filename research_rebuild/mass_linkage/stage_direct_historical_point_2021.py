"""Stage 2021 representative-point continuity uses from accepted direct Geo2011 points.

This is an application projection only. It creates no identities or admissions and
does not assert census-date measurement, population-scope, boundary, or legal-ID
comparability. See the pinned reviewer decision in the stage receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from collections import defaultdict, deque
from pathlib import Path

import pandas as pd

ACCEPTED_EDGE_STATUSES = {
    "checked_rule_accepted", "checked_rule_accepted_redundant_graph_connectivity_effect",
    "accepted_rule_family_after_independent_sample_review", "case_specific_independent_review_accepted",
    "case_review_accepted", "independent_case_review_accepted", "accepted_case_specific",
}
DIRECT_ORIGIN = "geokladr_2011_raw_dbf_coordinate"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def txt(v) -> str:
    if v is None or pd.isna(v):
        return ""
    return str(v).strip()


def truth(v) -> bool:
    return v is True or (isinstance(v, (int, float)) and not pd.isna(v) and v == 1)


def load_evidence(path: Path, ids: set[str]) -> dict[str, dict]:
    d = pd.read_parquet(path, columns=["source_record_id", "census_year", "source_evidence_json"],
                        filters=[("source_record_id", "in", sorted(ids))])
    out = {}
    for r in d.itertuples(index=False):
        sid = txt(r.source_record_id)
        if sid in out:
            raise ValueError(f"duplicate source evidence: {sid}")
        out[sid] = json.loads(r.source_evidence_json)
    return out


def parse_ids(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text().splitlines() if x.strip() and not x.startswith("#")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delivery", type=Path, default=Path("/workspace/settlements-delivery/continuation-loop-20261003"))
    ap.add_argument("--work", type=Path, default=Path("/workspace/settlements-work/continuation_20261003"))
    ap.add_argument("--out", type=Path, default=Path("/workspace/settlements-work/continuation_20261003/direct_historical_point_2021_stage_v1"))
    a = ap.parse_args()
    started = time.perf_counter()
    E, W, O = a.delivery, a.work, a.out
    O.mkdir(parents=True, exist_ok=False)
    review_dir = W / "direct_historical_point_2021_rule_review_v2"
    review_json = review_dir / "review.json"
    ids_path = review_dir / "approved_rule_candidate_ids.txt"
    ledger_path = W / "direct_historical_point_to_2021_gain_probe_v1" / "candidate_gain_ledger.parquet"
    selected_path, graph_path = E / "selected_observations.parquet", E / "accepted_identity_edges.parquet"
    points_path, evidence_path = E / "accepted_point_uses.parquet", E / "source_evidence.parquet"
    review = json.loads(review_json.read_text())
    ids = parse_ids(ids_path)
    if sha(review_json) != "f0e4d89bee24f1ead2f1f62f4abb87644e459d9cca61caa84c0e9cd1c3938a77":
        raise ValueError("review JSON SHA differs from approved pin")
    if sha(ids_path) != "abdc7df6b7b595d246a68e199cc714c2a7c9dfed311773e944848714c0efe64b":
        raise ValueError("approved exact-ID manifest SHA differs from reviewed pin")
    if len(ids) != 4575 or len(set(ids)) != 4575:
        raise ValueError("approved exact-ID manifest count/uniqueness mismatch")

    ledger = pd.read_parquet(ledger_path)
    cand = ledger[ledger.target_2021_source_record_id.astype(str).isin(set(ids))].copy()
    if len(cand) != len(ids) or set(cand.target_2021_source_record_id.astype(str)) != set(ids):
        raise ValueError("approved IDs do not exactly match gain-probe ledger rows")
    if not cand.diagnostic_status.eq("candidate_only_no_hard_hold").all():
        raise ValueError("approved candidate contains a diagnostic hard hold")
    if cand.target_or_origin_blocked.fillna(True).any() or cand.exact_native_event_roles_json.fillna("[]").astype(str).ne("[]").any():
        raise ValueError("approved candidate ledger includes a blocked/event target")
    if cand.point_staged.fillna(True).any() or cand.admission_allowed.fillna(True).any():
        raise ValueError("candidate diagnostic unexpectedly indicates staging/admission")

    targets = set(ids)
    old_ids = {x for s in cand.historical_direct_geo_source_record_ids_json for x in json.loads(s)}
    needed = targets | old_ids
    sel = pd.read_parquet(selected_path, columns=["source_record_id", "census_year", "settlement_name", "settlement_type", "region_raw", "region_norm", "population", "source_file", "source_sheet", "source_row", "source_sha256", "source_locator", "source_name_raw", "source_native_id", "population_scope", "population_value_quality", "is_additive_settlement_record", "entity_grain_status", "oktmo", "okato"])
    sel = sel[sel.source_record_id.astype(str).isin(needed)].copy()
    if sel.source_record_id.astype(str).duplicated().any():
        raise ValueError("selected endpoint IDs are not unique")
    selected = {txt(r.source_record_id): r._asdict() for r in sel.itertuples(index=False)}
    if set(selected) != needed:
        raise ValueError(f"selected endpoints missing: {len(needed-set(selected))}")
    evidence = load_evidence(evidence_path, needed)
    if set(evidence) != needed:
        raise ValueError(f"source evidence endpoints missing: {len(needed-set(evidence))}")

    # Restrict accepted points to candidate old endpoint IDs. Every carrier must be
    # a previously accepted direct raw Geo2011 named physical point use.
    point_cols = ["target_source_record_id", "target_year", "latitude", "longitude", "coordinate_quality", "coordinate_source", "coordinate_source_record_id", "coordinate_provider", "coordinate_provider_id", "source_name", "source_type", "source_region", "source_file", "source_row", "source_sha256", "source_locator", "coordinate_provenance", "admission_rule", "provider_binding_status", "provider_fias_binding_status", "coordinate_admission_status", "coordinate_measurement_date_unknown", "boundary_comparability_asserted", "coordinate_provider_family", "source_oktmo_raw", "source_okato_raw", "provider_query_receipt_missing", "coordinate_uncertainty_flags_json", "coordinate_application_family", "review_id", "application_inference_kind", "direct_historical_coordinate_measurement", "population_scope_comparability_asserted", "coordinate_source_sha256", "coordinate_source_locator", "coordinate_source_file", "coordinate_source_origin", "coordinate_source_date", "coordinate_source_latitude_raw", "coordinate_source_longitude_raw", "inference_modern_point_use_target_source_record_id", "inference_identity_path_decision_ids_json", "inference_identity_path_from_source_record_id", "inference_identity_path_to_source_record_id", "inference_identity_path_edge_count", "point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind", "point_claim_artifact_file", "point_claim_artifact_sha256", "coordinate_admission_status", "admission_allowed", "coordinate_admitted", "point_admitted", "identity_edge_admitted", "historical_propagation_allowed", "lineage_event_roles_json"]
    points = pd.read_parquet(points_path, columns=list(dict.fromkeys(point_cols)))
    points = points[points.target_source_record_id.astype(str).isin(old_ids)].copy()
    if points.target_source_record_id.astype(str).duplicated().any():
        raise ValueError("historical candidate endpoint has multiple accepted point rows")
    pby = {txt(r.target_source_record_id): r._asdict() for r in points.itertuples(index=False)}
    if set(pby) != old_ids:
        raise ValueError(f"historical accepted point endpoint missing: {len(old_ids-set(pby))}")
    for sid, p in pby.items():
        if txt(p.get("point_origin_kind")) != DIRECT_ORIGIN:
            raise ValueError(f"non-direct point origin at approved historical endpoint {sid}")
        if txt(p.get("coordinate_admission_status")) not in {"reviewed_extension_rule_accepted", "accepted_rule_family_after_independent_sample_review", "checked_rule_accepted"}:
            raise ValueError(f"historical point not accepted at {sid}")
        # The carrier is already admitted; its accepted admission flag should stay
        # true. The staged *target* below is independently marked false/pending.
        if p.get("admission_allowed") is False:
            raise ValueError(f"historical carrier unexpectedly not admitted: {sid}")
        if txt(p.get("admission_rule")).startswith("R_") or txt(p.get("application_inference_kind")) not in {"dated_historical_source_point_candidate", ""}:
            raise ValueError(f"inferred/modern point use cannot carry direct rule at {sid}")
        if not txt(p.get("point_origin_file")) or not txt(p.get("point_origin_sha256")) or not txt(p.get("point_origin_locator")):
            raise ValueError(f"point origin incomplete at {sid}")
        for key in ("inference_identity_path_decision_ids_json", "inference_identity_path_from_source_record_id", "inference_identity_path_to_source_record_id", "inference_modern_point_use_target_source_record_id"):
            if txt(p.get(key)) not in {"", "[]", "null"}:
                raise ValueError(f"historical endpoint itself is inferred at {sid}: {key}")
        if txt(p.get("lineage_event_roles_json")) not in {"", "[]", "null"}:
            raise ValueError(f"historical point endpoint has event role at {sid}")

    # Hash each canonical raw origin file once; this is a source-integrity pin, not
    # a re-parse of all DBF records.
    origin_by_file = {}
    for p in pby.values():
        origin = Path(txt(p["point_origin_file"]))
        expected = txt(p["point_origin_sha256"])
        if str(origin) not in origin_by_file:
            origin_by_file[str(origin)] = {"sha256": sha(origin), "bytes": origin.stat().st_size}
        if origin_by_file[str(origin)]["sha256"] != expected:
            raise ValueError(f"canonical point origin file hash mismatch: {origin}")

    # Read graph once, retain only accepted same_place edges, create deterministic
    # adjacency for exact endpoint-to-target path receipts.
    graph_cols = ["decision_id", "relation", "from_source_record_id", "to_source_record_id", "decision_status"]
    graph = pd.read_parquet(graph_path, columns=graph_cols)
    graph = graph[graph.relation.eq("same_place") & graph.decision_status.isin(ACCEPTED_EDGE_STATUSES)].copy()
    adj = defaultdict(list)
    edge_by_pair = {}
    for r in graph.itertuples(index=False):
        u, v, did = txt(r.from_source_record_id), txt(r.to_source_record_id), txt(r.decision_id)
        if not u or not v or not did or u == v:
            continue
        adj[u].append((v, did)); adj[v].append((u, did))
        edge_by_pair[(u, v, did)] = r
    for u in adj:
        adj[u].sort(key=lambda x: (x[0], x[1]))

    # Existing target point claims (including quarantines) are not overwritten.
    # The final output is the frozen accepted-state table and all approved targets
    # must currently have no point.
    final_cols = ["record_type", "observation_year", "source_record_id", "latitude", "longitude", "entity_id", "entity_category", "legacy_is_federal_aggregate", "entity_grain_status"]
    final = pd.read_parquet(E / "settlements_long.parquet", columns=final_cols)
    final = final[(final.record_type.eq("census")) & final.source_record_id.astype(str).isin(needed)].copy()
    if final.source_record_id.astype(str).duplicated().any():
        raise ValueError("final export contains duplicate endpoint source IDs")
    fby = {txt(r.source_record_id): r._asdict() for r in final.itertuples(index=False)}
    if set(fby) != needed:
        raise ValueError("final export missing target or historical endpoint")
    base_point_targets = set(pd.read_parquet(points_path, columns=["target_source_record_id"]).target_source_record_id.astype(str))
    if targets & base_point_targets:
        raise ValueError("approved target overlaps accepted base point uses")

    rows = []
    selected_sources = []
    path_cache = {}
    for c in cand.itertuples(index=False):
        tid = txt(c.target_2021_source_record_id)
        tsel, te = selected[tid], evidence[tid]
        tfinal = fby[tid]
        if int(tsel["census_year"]) != 2021 or int(tfinal["observation_year"]) != 2021 or txt(tfinal["entity_category"]) != "settlement":
            raise ValueError(f"target is not a 2021 physical settlement: {tid}")
        if not pd.isna(tfinal["latitude"]) or not pd.isna(tfinal["longitude"]):
            raise ValueError(f"target already has accepted coordinates: {tid}")
        if txt(te.get("source_record_id")) not in {"", tid} or te.get("is_federal_aggregate") is True or te.get("is_additive_settlement_record") is not True:
            raise ValueError(f"target source evidence contradicts candidate grain: {tid}")
        if txt(te.get("settlement_type")) != txt(tsel["settlement_type"]) or txt(te.get("settlement_name")) != txt(tsel["settlement_name"]):
            raise ValueError(f"selected/evidence target name/type mismatch: {tid}")
        if txt(te.get("region_norm")) and txt(te.get("region_norm")) != txt(tsel.get("region_norm")):
            raise ValueError(f"selected/evidence target region mismatch: {tid}")
        old_candidates = [txt(x) for x in json.loads(c.historical_direct_geo_source_record_ids_json)]
        if not old_candidates or not set(old_candidates).issubset(old_ids):
            raise ValueError(f"ledger endpoint list inconsistent at {tid}")
        # Rule review guarantees identical exact direct source origin and coordinate
        # when two historical census endpoints exist; select most recent year.
        old_candidates.sort(key=lambda sid: int(selected[sid]["census_year"]))
        source_id = old_candidates[-1]
        source = selected[source_id]
        p = pby[source_id]
        sfinal = fby[source_id]
        if int(source["census_year"]) not in (2002, 2010) or int(sfinal["observation_year"]) != int(source["census_year"]):
            raise ValueError(f"historical endpoint year mismatch: {source_id}")
        if txt(source["settlement_type"]) != txt(tsel["settlement_type"]) or txt(source["settlement_name"]) == "":
            raise ValueError(f"historical source type/name invalid at {source_id}")
        if txt(source["settlement_name"]) != txt(p.get("source_name")) or txt(source["settlement_type"]) != txt(p.get("source_type")):
            raise ValueError(f"accepted carrier source name/type does not match its selected endpoint: {source_id}")
        if not (math.isfinite(float(p["latitude"])) and math.isfinite(float(p["longitude"]))):
            raise ValueError(f"invalid accepted historical point at {source_id}")
        if (float(sfinal["latitude"]) != float(p["latitude"]) or float(sfinal["longitude"]) != float(p["longitude"])):
            raise ValueError(f"final output historical coordinates differ from accepted carrier: {source_id}")
        pair_key = (tid, source_id)
        if pair_key not in path_cache:
            q = deque([tid]); prev = {tid: None}
            while q and source_id not in prev:
                u = q.popleft()
                for v, did in adj.get(u, []):
                    if v not in prev:
                        prev[v] = (u, did); q.append(v)
            if source_id not in prev:
                raise ValueError(f"no accepted same_place path from target to historical carrier: {tid} -> {source_id}")
            dids, chain = [], [source_id]
            cur = source_id
            while cur != tid:
                parent, did = prev[cur]
                dids.append(did); chain.append(parent); cur = parent
            # Walking prev from source endpoint back toward target already emits
            # the path in source-to-target order, matching the field labels below.
            path_ids, chain = dids, chain
            if not chain or chain[0] != source_id or chain[-1] != tid or len(path_ids) != len(chain) - 1:
                raise ValueError(f"path orientation/length invariant failed: {source_id} -> {tid}")
            path_cache[pair_key] = (path_ids, chain)
        path_ids, chain = path_cache[pair_key]
        source_ev = te
        out = dict(p)
        out.update({
            "target_source_record_id": tid,
            "target_year": 2021,
            "source_name": txt(te.get("settlement_name") or tsel["settlement_name"]),
            "target_source_name_raw": txt(te.get("source_name_raw") or tsel["source_name_raw"]),
            "source_type": txt(te.get("settlement_type") or tsel["settlement_type"]),
            "source_region": txt(te.get("region_norm") or tsel.get("region_norm") or tsel["region_raw"]),
            "source_file": txt(te.get("source_file") or tsel["source_file"]),
            "source_row": te.get("source_row", tsel["source_row"]),
            "source_sha256": txt(te.get("source_sha256") or tsel["source_sha256"]),
            "source_locator": txt(te.get("source_locator") or tsel["source_locator"]),
            "source_okato_raw": txt(te.get("okato") or tsel["okato"]),
            "source_oktmo_raw": txt(te.get("oktmo") or tsel["oktmo"]),
            "coordinate_admission_status": "staged_candidate_pending_root_review",
            "admission_allowed": False,
            "coordinate_admitted": False,
            "point_admitted": False,
            "identity_edge_admitted": False,
            "historical_propagation_allowed": False,
            "coordinate_provenance": "Accepted direct GeoKLADR 2011 named physical-settlement point reused as a 2021 representative-point continuity inference through the exact accepted same_place component; 2011 source update only, no 2021 measurement or boundary/population comparison asserted.",
            "coordinate_measurement_date_unknown": True,
            "coordinate_source_date": "2011 source update",
            "boundary_comparability_asserted": False,
            "population_scope_comparability_asserted": False,
            "direct_historical_coordinate_measurement": False,
            "application_inference_kind": "forward_continuity_from_accepted_2011_representative_point",
            "inference_modern_point_use_target_source_record_id": None,
            "inference_identity_path_decision_ids_json": json.dumps(path_ids, ensure_ascii=False),
            "inference_identity_path_from_source_record_id": source_id,
            "inference_identity_path_to_source_record_id": tid,
            "inference_identity_path_edge_count": len(path_ids),
            "coordinate_application_family": "S_direct_historical_geo2011_to_2021_same_place_continuity",
            "review_id": "direct_historical_point_2021_rule_review_v2_pending_application_review",
            "provider_binding_status": "not_asserted_by_continuity_inference",
            "provider_fias_binding_status": "not_asserted_by_continuity_inference",
            "coordinate_source": "GeoKLADR 2011 named physical-point source; reused by accepted same_place continuity inference",
            "coordinate_source_record_id": txt(p.get("coordinate_source_record_id")),
            "coordinate_source_file": txt(p.get("coordinate_source_file")),
            "coordinate_source_sha256": txt(p.get("coordinate_source_sha256")),
            "coordinate_source_locator": txt(p.get("coordinate_source_locator")),
            "coordinate_source_latitude_raw": txt(p.get("coordinate_source_latitude_raw")),
            "coordinate_source_longitude_raw": txt(p.get("coordinate_source_longitude_raw")),
            "source_point_use_target_source_record_id": source_id,
            "source_point_use_target_year": int(source["census_year"]),
            "source_point_use_admission_rule": txt(p.get("admission_rule")),
            "source_point_use_status": txt(p.get("coordinate_admission_status")),
            "inference_path_source_to_target_decision_ids_json": json.dumps(path_ids, ensure_ascii=False),
            "inference_path_source_to_target_source_record_ids_json": json.dumps(chain, ensure_ascii=False),
            "target_source_evidence_json": json.dumps(source_ev, ensure_ascii=False, sort_keys=True),
            "target_population": int(te.get("population")) if te.get("population") is not None else None,
            "target_population_scope": txt(te.get("population_scope")),
            "target_population_value_quality": txt(te.get("population_value_quality")),
            "native_id_binding_asserted": False,
            "fias_identifier_binding_claimed": False,
            "historical_measurement_claimed": False,
            "population_scope_comparability_asserted": False,
            "modern_geonames_concordance_status": txt(c.geonames_concordance_status),
            "modern_geonames_geonameid_diagnostic": txt(c.geonames_geonameid_diagnostic),
            "modern_geonames_distance_km_diagnostic_only": c.geonames_min_distance_km_diagnostic_only,
            "modern_geonames_is_independent_measurement": False,
            "target_source_record_json": json.dumps({k: (None if pd.isna(v) else v) for k, v in tsel.items()}, ensure_ascii=False, sort_keys=True, default=str),
        })
        rows.append(out)
        selected_sources.append({"target_source_record_id": tid, "source_point_use_target_source_record_id": source_id,
                                 "source_year": int(source["census_year"]), "path_edge_count": len(path_ids),
                                 "path_decision_ids_json": json.dumps(path_ids, ensure_ascii=False),
                                 "path_source_record_ids_json": json.dumps(chain, ensure_ascii=False),
                                 "point_origin_file": txt(p["point_origin_file"]), "point_origin_sha256": txt(p["point_origin_sha256"]),
                                 "point_origin_locator": txt(p["point_origin_locator"]), "point_origin_kind": txt(p["point_origin_kind"]),
                                 "latitude": float(p["latitude"]), "longitude": float(p["longitude"]),
                                 "population_2021": int(c.population_2021) if not pd.isna(c.population_2021) else None})
    staged = pd.DataFrame(rows)
    if len(staged) != 4575 or staged.target_source_record_id.astype(str).duplicated().any() or set(staged.target_source_record_id.astype(str)) != targets:
        raise ValueError("staged table does not equal exact approved candidate IDs")
    if staged[["admission_allowed", "coordinate_admitted", "point_admitted", "identity_edge_admitted", "historical_propagation_allowed"]].fillna(True).any().any() or staged.coordinate_admission_status.ne("staged_candidate_pending_root_review").any():
        raise ValueError("staged application flags are invalid")
    if staged[["native_id_binding_asserted", "fias_identifier_binding_claimed", "historical_measurement_claimed", "boundary_comparability_asserted", "population_scope_comparability_asserted"]].fillna(True).any().any():
        raise ValueError("forbidden identity/measurement/comparability assertion in staged rows")
    staged_path = O / "staged_point_uses.parquet"
    staged.to_parquet(staged_path, index=False)
    pd.DataFrame(selected_sources).to_parquet(O / "source_path_ledger.parquet", index=False)
    pd.DataFrame(columns=["target_source_record_id", "hold_reason"]).to_parquet(O / "held_candidates.parquet", index=False)
    (O / "approved_target_source_record_ids.txt").write_text("\n".join(sorted(targets)) + "\n")
    inputs = [review_json, ids_path, ledger_path, E / "settlements_long.manifest.json", selected_path, graph_path, points_path, evidence_path,
              E / "accepted_publication_bindings.parquet", Path("/workspace/settlements-work/sources/historical_identifiers/observed_v1/lineage_event_candidates.json")]
    outputs = [staged_path, O / "source_path_ledger.parquet", O / "held_candidates.parquet", O / "approved_target_source_record_ids.txt"]
    receipt = {
        "artifact": "direct_historical_point_2021_stage_v1", "status": "application_stage_only_pending_separate_independent_review",
        "rule_review_sha256": sha(review_json), "approved_id_manifest_sha256": sha(ids_path),
        "approved_target_count": len(targets), "staged_count": len(staged), "held_count": 0,
        "staged_population_2021": int(cand.population_2021.sum(min_count=1)),
        "staged_source_year_counts": pd.Series([x["source_year"] for x in selected_sources]).value_counts().sort_index().to_dict(),
        "method": "Exact reviewer-approved 4,575 targets only. Copy the accepted direct GeoKLADR2011 representative point from its most recent accepted historical same_place endpoint; no averaging. Deterministic shortest accepted same_place path IDs retained.",
        "assertions": {"admission_allowed": False, "identity_edges_created": False, "native_or_fias_identifier_binding": False,
                       "census_date_measurement": False, "population_scope_comparability": False, "boundary_comparability": False,
                       "point_origin_is_2011_source_update": True, "measurement_date_unknown": True,
                       "geonames_used_as_independent_measurement": False, "source_grain_or_identity_reassessed": False},
        "origin_files_hashed_once": origin_by_file,
        "origin_file_hash_call_count": len(origin_by_file),
        "path_summary": {"unique_path_edge_counts": {str(k): int(v) for k,v in pd.Series([x["path_edge_count"] for x in selected_sources]).value_counts().items()},
                         "all_paths_use_accepted_same_place_edges": True},
        "inputs": {str(p): {"sha256": sha(p), "bytes": p.stat().st_size} for p in inputs},
        "outputs": {p.name: {"path": str(p), "sha256": sha(p), "bytes": p.stat().st_size} for p in outputs},
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    (O / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2, default=str) + "\n")
    print(json.dumps({"status": receipt["status"], "staged_count": len(staged), "population": receipt["staged_population_2021"],
                      "output": str(O), "receipt_sha256": sha(O / "receipt.json"), "runtime_seconds": receipt["runtime_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
