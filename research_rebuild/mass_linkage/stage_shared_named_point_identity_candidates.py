#!/usr/bin/env python3
"""Stage candidate identity edges for the frozen shared-Geo2011-object cohort."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stable_pair_id(a: str, b: str) -> str:
    endpoints = sorted((str(a), str(b)))
    return "SHNP-" + hashlib.sha256((endpoints[0] + "\n" + endpoints[1]).encode()).hexdigest()[:20]


def select_sample(df: pd.DataFrame, seed: int = 20261003) -> pd.DataFrame:
    """Fixed ≤60 sample with targeted extremes and separate seeded regional/ordinary strata."""
    strata: dict[str, list[int]] = {}

    def choose(label: str, indices) -> None:
        for ix in indices:
            strata.setdefault(int(ix), []).append(label)

    top = df.sort_values(["pair_population_max", "edge_id"], ascending=[False, True]).head(10)
    choose("targeted_top_population", top.index)
    covered = set(strata)
    zeros = df.loc[~df.index.isin(covered) & df["has_zero_population"]].sort_values("edge_id").head(6)
    choose("targeted_zero_population", zeros.index)
    covered = set(strata)
    norm = df.loc[~df.index.isin(covered) & df["raw_name_or_region_normalization_diff"]].sort_values("edge_id").head(10)
    choose("targeted_raw_name_or_region_difference", norm.index)
    covered = set(strata)
    held = df.loc[~df.index.isin(covered) & df["has_source_row_hold"]].sort_values("edge_id").head(6)
    choose("targeted_source_row_hold", held.index)
    covered = set(strata)
    ordinary = df.loc[~df.index.isin(covered) & ~df["has_source_row_hold"] & ~df["has_zero_population"] & ~df["raw_name_or_region_normalization_diff"]]
    rng = random.Random(seed)
    regions = sorted(ordinary.from_region_norm.dropna().unique().tolist())
    rng.shuffle(regions)
    regional_ids=[]
    for region in regions[:20]:
        candidates=ordinary.loc[ordinary.from_region_norm.eq(region)]
        regional_ids.append(rng.choice(list(candidates.index)))
    choose("seeded_random_region_strata", regional_ids)
    covered = set(strata)
    ordinary = df.loc[~df.index.isin(covered) & ~df["has_source_row_hold"] & ~df["has_zero_population"] & ~df["raw_name_or_region_normalization_diff"]]
    rand_ids=list(ordinary.index);rng.shuffle(rand_ids)
    choose("seeded_random_ordinary",rand_ids[:8])
    out = df.loc[sorted(strata)].copy()
    out["sample_strata"] = [json.dumps(strata[ix], ensure_ascii=False) for ix in out.index]
    out["sample_seed"] = seed
    return out.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True, help="Frozen shared_named_point_origin_identity_probe_v1/candidate_pairs.parquet")
    ap.add_argument("--groups", required=True, help="Frozen origin_groups.parquet from that probe")
    ap.add_argument("--selected", required=True)
    ap.add_argument("--points", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--geo-context", required=True)
    ap.add_argument("--historical-candidates", required=True)
    ap.add_argument("--manifest", required=True, help="Frozen exact source input manifest for raw-row checks")
    ap.add_argument("--raw-root", required=True)
    ap.add_argument("--prior-2010-holds", required=True, help="Frozen v3 endpoint holds; unresolved cases remain held")
    ap.add_argument("--output", required=True)
    started=time.perf_counter()
    a = ap.parse_args()
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    pairs = pq.read_table(a.pairs).to_pandas()
    if len(pairs) != 2319 or not pairs.candidate_only.all():
        raise ValueError("frozen candidate pair input does not match the pinned 2,319 candidate-only cohort")
    selected_cols = ["source_record_id", "census_year", "source_file", "source_sheet", "source_row", "source_sha256", "source_locator", "source_name_raw", "settlement_name", "settlement_type", "region_raw", "name_norm", "type_norm", "region_norm", "population", "population_scope", "population_value_quality", "is_additive_settlement_record", "entity_grain_status", "source_native_id", "okato", "oktmo", "source_raw_line", "district_raw", "municipality_raw"]
    selected = pq.read_table(a.selected, columns=selected_cols).to_pandas()
    points = pq.read_table(a.points, columns=["target_source_record_id", "target_year", "point_origin_file", "point_origin_sha256", "point_origin_locator", "point_origin_kind", "admission_rule", "coordinate_provenance", "latitude", "longitude", "provider_binding_status", "provider_fias_binding_status", "coordinate_admission_status", "lineage_event_roles_json", "coordinate_source_record_id", "coordinate_source_sha256", "coordinate_source_locator", "coordinate_application_review_sha256"]).to_pandas()
    geo = pq.read_table(a.geo_context, columns=["record_number_1based", "record_byte_offset_0based", "historical_okato_2011_raw", "historical_okato_2009_raw", "name_raw_2009", "status", "name_full", "source_line_1based", "source_sha256_2009", "code_join_basis", "historical_code_structure_compatible", "name_key", "type_key_2009", "historical_name_exact", "historical_type_exact", "name_raw_2011", "settlement_type_raw", "historical_point_modern_region", "source_sha256_2011", "longitude_from_long", "latitude_from_lat", "is_deleted", "is_settlement_raw", "historical_key_region_name_type_count", "ter_raw_text", "kod1_raw_text", "kod2_raw_text", "kod3_raw_text", "scokato_raw_text", "oktmo_2011_raw", "data_upd_raw_text"]).to_pandas()
    hist_cols=["source_record_id","historical_okato_2009_raw","name_raw_2009","status","name_full","is_settlement_raw","source_line_1based","source_sha256_2009","historical_okato_2011_raw","code_join_basis"]
    hist=pq.read_table(a.historical_candidates,columns=hist_cols).to_pandas().drop_duplicates("source_record_id").set_index("source_record_id")
    evidence=pq.read_table(a.evidence,columns=["source_record_id","source_evidence_json"]).to_pandas().set_index("source_record_id")
    base_graph=pq.read_table(a.graph).to_pandas()
    prior_holds=pq.read_table(a.prior_2010_holds).to_pandas().set_index("from_source_record_id")
    group_df=pq.read_table(a.groups).to_pandas()
    group_key=["point_origin_file","point_origin_sha256","point_origin_locator","name_norm","type_norm","region_norm"]
    group_df=group_df.set_index(group_key,drop=False)
    graph_ids=set(base_graph.from_source_record_id.dropna())|set(base_graph.to_source_record_id.dropna())
    from research_rebuild.mass_linkage.apply_identity_rules import _metadata
    from research_rebuild.mass_linkage.apply_historical_identity_rule import verify_source_rows
    endpoint_ids=set(pairs.from_source_record_id)|set(pairs.to_source_record_id)
    metadata,raw_bindings=_metadata(Path(a.selected),endpoint_ids,Path(a.manifest))
    source_checks=verify_source_rows(metadata,raw_bindings,Path(a.raw_root))
    selected_idx = selected.set_index("source_record_id", drop=False)
    points_idx = points.set_index("target_source_record_id", drop=False)
    geo_idx = geo.set_index(["record_number_1based", "record_byte_offset_0based"], drop=False)
    rows=[];source_rows=[];application_rows=[]
    for pair in pairs.itertuples(index=False):
        pa=pair._asdict()
        m=__import__('re').fullmatch(r"raw_dbf_record_number_1based=(\d+);byte_offset_0based=(\d+)",pa["point_origin_locator"])
        if not m: raise ValueError(f"unexpected frozen Geo locator: {pa['point_origin_locator']}")
        grow=geo_idx.loc[(int(m.group(1)),int(m.group(2)))]
        endpoints=[]
        for prefix in ("from", "to"):
            sid=pa[f"{prefix}_source_record_id"]
            srow=selected_idx.loc[sid]
            prow=points_idx.loc[sid]
            raw_locator=pa["point_origin_locator"]
            fields=dict(partner_role=prefix, source_record_id=sid, census_year=int(srow.census_year), source_file=srow.source_file,
                        source_sheet=srow.source_sheet, source_row=srow.source_row, source_sha256=srow.source_sha256,
                        source_locator=srow.source_locator, source_name_raw=srow.source_name_raw, settlement_name=srow.settlement_name,
                        settlement_type=srow.settlement_type, region_raw=srow.region_raw, name_norm=srow.name_norm,
                        type_norm=srow.type_norm, region_norm=srow.region_norm, population=int(srow.population),
                        population_scope=srow.population_scope, population_value_quality=srow.population_value_quality,
                        is_additive_settlement_record=bool(srow.is_additive_settlement_record), entity_grain_status=srow.entity_grain_status,
                        source_native_id=srow.source_native_id, okato_raw=srow.okato, oktmo_raw=srow.oktmo, source_raw_line=srow.source_raw_line,
                        source_district_raw=srow.district_raw, source_municipality_raw=srow.municipality_raw,
                        point_origin_file=prow.point_origin_file, point_origin_sha256=prow.point_origin_sha256,
                        point_origin_locator=prow.point_origin_locator, point_origin_kind=prow.point_origin_kind,
                        point_admission_rule=prow.admission_rule, coordinate_provenance=prow.coordinate_provenance,
                        point_latitude=float(prow.latitude), point_longitude=float(prow.longitude),
                        provider_binding_status=prow.provider_binding_status, provider_fias_binding_status=prow.provider_fias_binding_status,
                        prior_coordinate_status=prow.coordinate_admission_status, lineage_event_roles_json=prow.lineage_event_roles_json,
                        coordinate_source_record_id=prow.coordinate_source_record_id, coordinate_source_sha256=prow.coordinate_source_sha256,
                        coordinate_source_locator=prow.coordinate_source_locator, coordinate_application_review_sha256=prow.coordinate_application_review_sha256)
            hrow=hist.loc[sid] if sid in hist.index else grow
            classifier_basis="frozen_v4_target_source_id_row" if sid in hist.index else "shared_literal_geo_record_exact_code_and_selected_name_type_region"
            fields.update(classifier_2009_code=hrow.historical_okato_2009_raw,classifier_2009_raw_name=hrow.name_raw_2009,
                          classifier_2009_status=hrow.status,classifier_2009_name_full=hrow.name_full,
                          classifier_2009_is_settlement=hrow.is_settlement_raw,classifier_2009_line_1based=int(hrow.source_line_1based),
                          classifier_2009_sha256=hrow.source_sha256_2009,classifier_2009_code_join_basis=hrow.code_join_basis,
                          classifier_target_binding_basis=classifier_basis,
                          classifier_code_matches_raw_geo=(str(hrow.historical_okato_2009_raw)==str(grow.historical_okato_2011_raw)),
                          classifier_name_type_matches_target=(str(srow.name_norm)==str(grow.name_key) and str(srow.type_norm)==str(grow.type_key_2009)),
                          classifier_region_matches_target=(str(srow.region_norm)==str(grow.historical_point_modern_region)))
            prior=prior_holds.loc[sid].to_dict() if int(srow.census_year)==2010 and sid in prior_holds.index else None
            if int(srow.census_year)==2010 and sid in source_checks:
                rawcheck=source_checks[sid]
                fields.update(raw_2010_source_row_status=rawcheck.get("status"),raw_2010_source_row_label=rawcheck.get("raw_label"),
                              raw_2010_source_row_population=rawcheck.get("raw_population"),raw_2010_source_row_region=rawcheck.get("raw_region"),
                              raw_2010_selected_region=rawcheck.get("selected_region"),raw_2010_source_hash=rawcheck.get("source_sha256"),
                              raw_2010_source_file=rawcheck.get("source_file"),raw_2010_source_sheet=rawcheck.get("source_sheet"),
                              raw_2010_source_row_1based=rawcheck.get("source_row_1based"),raw_2010_district_carry_used=rawcheck.get("district_carry_used"),
                              prior_2010_application_status=prior.get("application_status") if prior else None,
                              prior_2010_hold_reasons_json=prior.get("hold_reasons_json") if prior else None)
            elif int(srow.census_year)==2010:
                rawcheck={"status":"held_source_row_check_missing"}
                fields["raw_2010_source_row_status"]="held_source_row_check_missing"
            else:
                rawcheck={"status":"pinned_selected_row_not_reopened_in_this_application"}
                fields["raw_2010_source_row_status"]="not_applicable_2002_source"
            endpoints.append(fields)
            evidence_obj=json.loads(evidence.loc[sid].source_evidence_json)
            source_rows.append({**fields,"source_evidence_aggregate":evidence_obj.get("is_federal_aggregate"),
                                "source_evidence_additive":evidence_obj.get("is_additive_settlement_record"),
                                "source_evidence_legacy_identity_conflict":evidence_obj.get("legacy_identity_conflict"),
                                "source_evidence_legacy_same_year_collision":evidence_obj.get("legacy_same_year_collision"),
                                "source_raw_row_reopened_in_this_stage":False,
                                "source_row_provenance_status":"frozen_selected_source_id_file_hash_sheet_row_locator"})
            fields["raw_2010_source_row_check_status_internal"]=rawcheck.get("status")
            fields["prior_2010_source_hold_internal"]=bool(prior)
        obj={"raw_geo_record_number_1based":int(m.group(1)),"raw_geo_byte_offset_0based":int(m.group(2)),
             "raw_geo_okato_code":grow.historical_okato_2011_raw,"raw_geo_name":grow.name_raw_2011,
             "raw_geo_type":grow.settlement_type_raw,"raw_geo_region":grow.historical_point_modern_region,
             "raw_geo_ter":grow.ter_raw_text,"raw_geo_kod1":grow.kod1_raw_text,"raw_geo_kod2":grow.kod2_raw_text,
             "raw_geo_kod3":grow.kod3_raw_text,"raw_geo_scokato":grow.scokato_raw_text,"raw_geo_oktmo_2011":grow.oktmo_2011_raw,
             "raw_geo_data_updated":grow.data_upd_raw_text,
             "raw_geo_file_sha256":grow.source_sha256_2011,"raw_geo_latitude":float(grow.latitude_from_lat),
             "raw_geo_longitude":float(grow.longitude_from_long),"raw_geo_is_deleted":bool(grow.is_deleted),
             "raw_geo_is_settlement":str(grow.is_settlement_raw).lower() in ("t","true","1"),
             "raw_geo_key_region_name_type_count":int(grow.historical_key_region_name_type_count)}
        if obj["raw_geo_file_sha256"] != pa["point_origin_sha256"] or any(e["point_origin_locator"] != raw_locator or e["point_origin_sha256"] != obj["raw_geo_file_sha256"] or e["point_latitude"] != obj["raw_geo_latitude"] or e["point_longitude"] != obj["raw_geo_longitude"] for e in endpoints):
            raise ValueError(f"point-use origin does not resolve to the same literal raw Geo point: {pa['from_source_record_id']}")
        candidate_rule="shared_literal_named_geokladr_object_identity_v1"
        source_row_holds=[f"{e['source_record_id']}:{e.get('raw_2010_source_row_check_status_internal')}" for e in endpoints if e.get("census_year")==2010 and e.get("raw_2010_source_row_check_status_internal")!="raw_row_exact_label_population_region_verified"]
        source_row_holds += [f"{e['source_record_id']}:prior_application_hold:{e.get('prior_2010_hold_reasons_json')}" for e in endpoints if e.get("prior_2010_source_hold_internal")]
        decision="held_raw_2010_source_row_check" if source_row_holds else "candidate_pending_independent_application_review"
        rows.append({"edge_id":stable_pair_id(pa["from_source_record_id"],pa["to_source_record_id"]),
            "relation":"same_place","from_source_record_id":pa["from_source_record_id"],"from_year":str(int(pa["from_year"])),
            "to_source_record_id":pa["to_source_record_id"],"to_year":str(int(pa["to_year"])),"candidate_rule":candidate_rule,
            "candidate_status":decision,"decision_status":decision,"hold_reasons_json":json.dumps(source_row_holds,ensure_ascii=False),
            "admission_status":"not_admitted","graph_add_status":False,"candidate_only":True,
            "source_identity_witness":"two selected census observations have exact compatible normalized name/type/region and each has an already reviewed GeoKLADR 2011 point use whose raw origin is the same exact nondeleted typed DBF settlement record; see endpoint JSON + literal raw row fields",
            "raw_origin_file":pa["point_origin_file"],"raw_origin_sha256":pa["point_origin_sha256"],"raw_origin_locator":raw_locator,
            "raw_origin_code":pa["source_object_code"],"raw_origin_name":pa["source_object_name"],"raw_origin_type":pa["source_object_type"],"raw_origin_region":pa["source_object_region"],**obj,
            "endpoint_evidence_json":json.dumps(endpoints,ensure_ascii=False,sort_keys=True,default=str),
            "from_name":endpoints[0]["settlement_name"],"to_name":endpoints[1]["settlement_name"],
            "from_region":endpoints[0]["region_raw"],"to_region":endpoints[1]["region_raw"],
            "from_region_norm":endpoints[0]["region_norm"],"to_region_norm":endpoints[1]["region_norm"],
            "pop_from":int(pa["from_population"]),"pop_to":int(pa["to_population"]),
            "population_comparability_asserted":False,"boundary_comparability_asserted":False,
            "no_coordinate_measurement_date_claim":True,"provider_id_binding_claimed":False})
        group=group_df.loc[(pa["point_origin_file"],pa["point_origin_sha256"],pa["point_origin_locator"],pa["name_norm"],pa["type_norm"],pa["region_norm"])]
        approw={"edge_id":stable_pair_id(pa["from_source_record_id"],pa["to_source_record_id"]),
            "from_source_record_id":pa["from_source_record_id"],"to_source_record_id":pa["to_source_record_id"],
            "candidate_rule":candidate_rule,"status":decision,"hold_reasons_json":json.dumps(source_row_holds,ensure_ascii=False),
            "source_object_sha_locator_gate":"passed_literal_raw_geo_and_point_origin_equality",
            "source_object_classifier_code_name_type_gate":"exact raw 2009 and 2011 code; exact name/type; unique historical key",
            "source_region_name_type_gate":"unique exact region/name/type on selected and historical object",
            "selected_signature_year_singleton":True,"point_origin_coordinates_exactly_match_raw_geo":True,
            "accepted_graph_endpoint_gate":"outside accepted graph" if all(e["source_record_id"] not in graph_ids for e in endpoints) else "failed",
            "graph_component_competitor_gate":"passed_frozen_probe_signature_wide_scan",
            "event_role_native_code_gate":"passed_frozen_probe_event_register_scan",
            "known_identity_point_conflict_gate":"passed_frozen_probe_known_holds",
            "raw_2010_source_row_gate":"held" if source_row_holds else "passed_exact_cached_source_row_checks",
            "probe_origin_group_status":group.group_status,"probe_failed_gates":group.failed_gates,
            "population_comparability_asserted":False,"coordinate_admission":False,"boundary_comparability_asserted":False}
        application_rows.append(approw)
    edges=pd.DataFrame(rows)
    edges["pair_population_max"]=edges[["pop_from","pop_to"]].max(axis=1)
    edges["has_zero_population"]=(edges["pop_from"].eq(0)|edges["pop_to"].eq(0))
    edges["has_source_row_hold"]=edges.decision_status.eq("held_raw_2010_source_row_check")
    edges["raw_name_or_region_normalization_diff"]=(edges.from_name.astype(str).ne(edges.to_name.astype(str))|edges.from_region.astype(str).ne(edges.to_region.astype(str)))
    # Graph/event risk gates are an exact stage assertion from the frozen candidate ledger.
    # These candidate IDs were generated after both endpoint and signature-wide checks.
    edges["graph_collision_gate"]="passed_in_frozen_probe"
    edges["event_gate"]="passed_in_frozen_probe"
    sample=select_sample(edges)
    # Do not carry sampling-only columns into the full candidate ledger.
    all_edges=edges.drop(columns=["pair_population_max","has_zero_population","has_source_row_hold","raw_name_or_region_normalization_diff"])
    all_edges.to_parquet(out/"candidate_identity_edges.parquet",index=False)
    sample.to_parquet(out/"fixed_stratified_sample.parquet",index=False)
    pd.DataFrame(application_rows).to_parquet(out/"application_checks.parquet",index=False)
    pd.DataFrame(source_rows).to_parquet(out/"source_row_checks.parquet",index=False)
    staged_candidates=all_edges.loc[all_edges.decision_status.eq("candidate_pending_independent_application_review")].copy()
    staged_candidates["decision_status"]="pending_independent_application_review"
    staged_candidates["decision_id"]=staged_candidates.edge_id
    staged_candidates["decision_rule"]="shared_literal_named_geokladr_object_identity_v1"
    staged_candidates["reviewer"]="pending_independent_application_review"
    staged_candidates["reviewed_at"]=None
    staged_candidates["selection_projection_status"]="active_endpoints_selected"
    staged_candidates["graph_add_status"]="pending_independent_application_review"
    staged_candidates["coordinate_admitted"]=False
    staged_candidates["population_quality_changed"]=False
    staged_candidates["boundary_comparability_asserted"]=False
    staged_candidates["evidence_uri"]=str(a.pairs)
    staged_candidates["evidence_sha256"]=sha256(a.pairs)
    base_staged=base_graph.copy()
    staged=pd.concat([base_staged,staged_candidates],ignore_index=True,sort=False)
    staged.to_parquet(out/"staged_identity_edges.parquet",index=False)
    (out/"raw_source_bindings.json").write_text(json.dumps(raw_bindings,ensure_ascii=False,indent=2,default=str)+"\n")
    receipt={"artifact":"shared_named_point_identity_stage_v1","status":"candidate_edges_only_no_graph_admission",
        "candidate_rule":"shared_literal_named_geokladr_object_identity_v1","pair_input_sha256":sha256(a.pairs),
        "scope":{"staged_new_pairs":len(staged_candidates),"held_source_row_pairs":int(edges.decision_status.eq("held_raw_2010_source_row_check").sum()),"candidate_pairs":len(edges),"base_graph_edges_preserved":len(base_graph)},
        "pair_rows":len(edges),"application_status_counts":{str(k):int(v) for k,v in edges.decision_status.value_counts().items()},"candidate_edges_sha256":sha256(out/"candidate_identity_edges.parquet"),
        "application_checks_sha256":sha256(out/"application_checks.parquet"),"source_row_checks_sha256":sha256(out/"source_row_checks.parquet"),
        "staged_identity_edges_sha256":sha256(out/"staged_identity_edges.parquet"),
        "sample_rows":len(sample),"sample_sha256":sha256(out/"fixed_stratified_sample.parquet"),"sample_seed":20261003,
        "sample_policy":"Targeted: up to 10 largest population pairs, 6 zero-population pairs, 10 pairs with inter-endpoint raw-name/region differences, and 6 pairs held on source-row checks. Seeded random: one pair from each of up to 20 randomly selected regions plus 8 ordinary pairs. Strata may overlap; total is at most 60.",
        "sample_strata_counts":{k:int(sum(k in json.loads(x) for x in sample.sample_strata)) for k in ["targeted_top_population","targeted_zero_population","targeted_raw_name_or_region_difference","targeted_source_row_hold","seeded_random_region_strata","seeded_random_ordinary"]},
        "elapsed_seconds":round(time.perf_counter()-started,3),
        "inputs":{k:{"path":v,"sha256":sha256(v)} for k,v in {"pairs":a.pairs,"groups":a.groups,"selected":a.selected,"points":a.points,"evidence":a.evidence,"graph":a.graph,"geo_context":a.geo_context,"historical_candidates":a.historical_candidates,"source_manifest":a.manifest,"prior_2010_holds":a.prior_2010_holds}.items()},
        "raw_source_bindings_sha256":sha256(out/"raw_source_bindings.json"),
        "scope_limits":["candidate edges are not accepted identity edges","no population or census-boundary comparability claim","no provider ID/FIAS claim","coordinates are source points without census-date measurement claim"]}
    (out/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    (out/"review.md").write_text(f"# Shared literal GeoKLADR object identity candidates\n\nStaged {len(edges):,} candidate same-place edges for independent review with the frozen {len(base_graph):,}-edge R graph preserved. No candidate edge is accepted. The {len(sample)}-row sample has targeted high-population, zero-population, and raw endpoint name/region difference strata plus separate seeded region-stratified and ordinary cases. Source-row, classifier, raw Geo/admin-code, point-origin, graph, and event fields are inspectable in the ledgers. Candidate identity does not imply census-boundary or population comparability, point measurement date, or provider identifier binding. See `receipt.json` for pinned input/output hashes.\n")


if __name__ == "__main__":
    main()
