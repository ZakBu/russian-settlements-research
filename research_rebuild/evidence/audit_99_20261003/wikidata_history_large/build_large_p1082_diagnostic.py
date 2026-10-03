#!/usr/bin/env python3
"""Candidate-only P1082 history inventory for large 2021 physical settlements.

All population claims come from the cached full Wikidata entity JSON. Flat
Wikidata TSV/module artifacts are counted for coverage comparison only.
No historical identity edges or population admissions are created.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

F = Path("/workspace/settlements-delivery/continuation-consolidated-20261003")
W = Path("/workspace/settlements-work/wikidata/wide_v5")
RAW = Path("/workspace/settlements-raw/data/raw")
ENTITIES = RAW / "wikidata_entities_full"
OUT = Path(__file__).resolve().parent
MIN_POP = 2000


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def quantity_parts(claim: dict) -> tuple[str | None, str | None, str | None]:
    snak = claim.get("mainsnak") or {}
    data = snak.get("datavalue") or {}
    value = data.get("value") or {}
    if not isinstance(value, dict):
        return (str(value), None, data.get("type"))
    return (value.get("amount"), value.get("unit"), data.get("type"))


def time_rows(qualifiers: dict) -> list[dict]:
    out = []
    for q in qualifiers.get("P585", []) or []:
        dv = (q.get("datavalue") or {}).get("value")
        if isinstance(dv, dict):
            raw_time = dv.get("time")
            match = re.match(r"^[+-](\d+)", str(raw_time or ""))
            out.append({
                "snaktype": q.get("snaktype"), "property": q.get("property"),
                "time_literal": raw_time, "timezone": dv.get("timezone"),
                "before": dv.get("before"), "after": dv.get("after"),
                "precision": dv.get("precision"), "calendarmodel": dv.get("calendarmodel"),
                "literal_year_prefix_only_not_census_assignment": match.group(1) if match else None,
            })
        else:
            out.append({"snaktype": q.get("snaktype"), "property": q.get("property"), "raw_snak": q})
    return out


def graph_components(edges: pd.DataFrame) -> dict[str, set[str]]:
    accepted_statuses = {
        "checked_rule_accepted", "checked_rule_accepted_redundant_graph_connectivity_effect",
        "accepted_rule_family_after_independent_sample_review", "case_specific_independent_review_accepted",
        "case_review_accepted", "independent_case_review_accepted", "accepted_case_specific",
    }
    if edges.decision_status.isna().any() or not edges.decision_status.isin(accepted_statuses).all():
        raise ValueError("frozen graph contains a noncanonical or unaccepted decision_status")
    keep = edges.decision_status.isin(accepted_statuses)
    e = edges.loc[keep, ["from_source_record_id", "to_source_record_id"]].dropna()
    parent: dict[str, str] = {}
    size: dict[str, int] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        size.setdefault(x, 1)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if size[ra] < size[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        size[ra] += size[rb]

    for a, b in e.itertuples(index=False, name=None):
        union(str(a), str(b))
    comps: dict[str, set[str]] = defaultdict(set)
    for node in list(parent):
        comps[find(node)].add(node)
    return comps


def main() -> None:
    selected = pd.read_parquet(F / "selected_observations.parquet")
    selected = selected.loc[
        selected.census_year.eq(2021)
        & selected.is_additive_settlement_record.fillna(False)
        & selected.population_scope.eq("settlement")
        & pd.to_numeric(selected.population, errors="coerce").ge(MIN_POP)
    ].copy()
    physical = pd.read_parquet(W / "provider_code_candidate_screen.parquet", columns=["source_record_id", "source_is_physical_np"])
    selected = selected.merge(physical, on="source_record_id", how="left", validate="one_to_one")
    selected = selected.loc[selected.source_is_physical_np.fillna(False).astype(bool)].copy()
    selected["source_record_id"] = selected.source_record_id.astype(str)
    selected["population"] = pd.to_numeric(selected.population, errors="coerce")
    selected_by_id = selected.set_index("source_record_id").to_dict("index")

    wide = pd.read_parquet(W / "wide_point_bindings.parquet")
    wide = wide.loc[wide.source_record_id.astype(str).isin(set(selected.source_record_id))].copy()
    wide["source_record_id"] = wide.source_record_id.astype(str)
    wide = wide.loc[wide.wikidata_truthy_exact_p764_match.fillna(False).astype(bool)].copy()
    wide["wikidata_qid"] = wide.wikidata_qid.astype(str)
    qids_by_target = wide.groupby("source_record_id").wikidata_qid.apply(lambda x: sorted(set(x))).to_dict()
    qid_to_targets: dict[str, list[str]] = defaultdict(list)
    for sid, qids in qids_by_target.items():
        for qid in qids:
            qid_to_targets[qid].append(sid)

    edge_path = F / "accepted_identity_edges.parquet"
    edges = pd.read_parquet(edge_path)
    components = graph_components(edges)
    component_by_node = {node: nodes for nodes in components.values() for node in nodes}
    selected_ids = set(selected.source_record_id)
    historical_ids = {str(sid) for sid in selected_ids}
    # Historical graph endpoints are kept only as existing accepted component context.
    for nodes in components.values():
        historical_ids.update(n for n in nodes if n not in selected_ids)
    graph_old_by_target: dict[str, list[str]] = {}
    historical_source = pd.read_parquet(F / "selected_observations.parquet", columns=["source_record_id", "census_year"])
    hist_year = dict(zip(historical_source.source_record_id.astype(str), historical_source.census_year.astype(str)))
    for sid in selected_ids:
        nodes = component_by_node.get(sid, {sid})
        olds = sorted(n for n in nodes if n != sid and n in hist_year and hist_year[n] != "2021")
        graph_old_by_target[sid] = olds

    qid_set = set(qid_to_targets)
    entity_files = sorted(p for p in ENTITIES.glob("*.json.gz") if not p.name.startswith("._"))
    raw_file_hashes = {p.name: sha(p) for p in entity_files}
    entity_by_qid: dict[str, tuple[dict, str, str]] = {}
    raw_entity_qids: set[str] = set()
    raw_entity_p1082_qids: set[str] = set()
    for path in entity_files:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            batch = json.load(stream)
        payload = batch.get("payload") or {}
        entities = payload.get("entities") or {}
        for qid, entity in entities.items():
            raw_entity_qids.add(qid)
            if any(c.get("rank", "normal") != "deprecated" for c in (entity.get("claims") or {}).get("P1082", []) or []):
                raw_entity_p1082_qids.add(qid)
            if qid in qid_set:
                entity_by_qid[qid] = (entity, path.name, batch.get("retrieved_at_utc"))

    rows: list[dict] = []
    qid_summary: dict[str, dict] = {}
    deprecated_count = 0
    for qid, target_ids in sorted(qid_to_targets.items()):
        found = entity_by_qid.get(qid)
        if found is None:
            qid_summary[qid] = {"raw_entity_present": False, "nondeprecated_p1082_count": 0, "deprecated_p1082_count": 0}
            continue
        entity, batch_name, retrieved = found
        batch_path = ENTITIES / batch_name
        payload_hash = raw_file_hashes[batch_name]
        claims = (entity.get("claims") or {}).get("P1082", []) or []
        active = [c for c in claims if c.get("rank", "normal") != "deprecated"]
        deprecated = len(claims) - len(active)
        deprecated_count += deprecated
        label_ru = ((entity.get("labels") or {}).get("ru") or {}).get("value")
        desc_ru = ((entity.get("descriptions") or {}).get("ru") or {}).get("value")
        qid_summary[qid] = {
            "raw_entity_present": True, "nondeprecated_p1082_count": len(active),
            "deprecated_p1082_count": deprecated,
        }
        for target_id in target_ids:
            target = selected_by_id[target_id]
            old_ids = graph_old_by_target.get(target_id, [])
            old_years = sorted({hist_year.get(x, "") for x in old_ids if hist_year.get(x, "")})
            for index, claim in enumerate(claims):
                rank = claim.get("rank", "normal")
                if rank == "deprecated":
                    continue
                amount, unit, value_type = quantity_parts(claim)
                qualifiers = claim.get("qualifiers") or {}
                p585 = time_rows(qualifiers)
                refs = claim.get("references") or []
                reference_urls = []
                for ref in refs:
                    for url_snak in ((ref.get("snaks") or {}).get("P854") or []):
                        value = (url_snak.get("datavalue") or {}).get("value")
                        if isinstance(value, str):
                            reference_urls.append(value)
                statement_id = claim.get("id")
                locator = f"{batch_name}#payload.entities.{qid}.claims.P1082[{index}]#{statement_id or 'missing-statement-id'}"
                rows.append({
                    "source_record_id_2021": target_id, "source_population_2021": target.get("population"),
                    "source_name_2021": target.get("settlement_name"), "source_type_2021": target.get("settlement_type"),
                    "source_region_2021": target.get("region_raw"), "source_file_2021": target.get("source_file"),
                    "source_row_2021": target.get("source_row"), "source_sha256_2021": target.get("source_sha256"),
                    "population_scope_2021": target.get("population_scope"), "wikidata_qid": qid,
                    "wikidata_ru_label": label_ru, "wikidata_ru_description": desc_ru,
                    "wide_qid_binding_rows_for_target": len(qids_by_target.get(target_id, [])),
                    "existing_accepted_graph_old_record_ids_json": json.dumps(old_ids, ensure_ascii=False),
                    "existing_accepted_graph_old_years_json": json.dumps(old_years, ensure_ascii=False),
                    "entity_lastrevid": entity.get("lastrevid"), "entity_modified_utc": entity.get("modified"),
                    "entity_retrieved_at_utc": retrieved, "entity_batch_file": batch_name,
                    "entity_batch_sha256": payload_hash, "raw_record_locator": locator,
                    "raw_claim_index_in_entity": index, "statement_id": statement_id,
                    "rank": rank, "mainsnak_snaktype": (claim.get("mainsnak") or {}).get("snaktype"),
                    "mainsnak_property": (claim.get("mainsnak") or {}).get("property"),
                    "population_amount_literal": amount, "population_unit_literal": unit,
                    "population_datavalue_type": value_type,
                    "p585_literals_json": json.dumps(p585, ensure_ascii=False, sort_keys=True),
                    "p585_literal_year_prefixes_json": json.dumps(sorted({x["literal_year_prefix_only_not_census_assignment"] for x in p585 if x.get("literal_year_prefix_only_not_census_assignment")}), ensure_ascii=False),
                    "qualifiers_order_json": json.dumps(claim.get("qualifiers-order") or [], ensure_ascii=False),
                    "all_qualifiers_raw_json": json.dumps(qualifiers, ensure_ascii=False, sort_keys=True),
                    "references_count": len(refs), "references_with_p854_url_count": len(reference_urls),
                    "reference_p854_urls_json": json.dumps(reference_urls, ensure_ascii=False),
                    "all_references_raw_json": json.dumps(refs, ensure_ascii=False, sort_keys=True),
                    "raw_statement_json": json.dumps(claim, ensure_ascii=False, sort_keys=True),
                    "year_assignment_status": "literal_P585_only_not_assigned_to_census_year",
                    "population_admission": False, "historical_identity_admission": False,
                })

    long = pd.DataFrame(rows)
    if long.empty:
        long = pd.DataFrame(columns=["source_record_id_2021", "wikidata_qid", "statement_id", "population_amount_literal", "rank", "raw_record_locator"])
    long.to_parquet(OUT / "candidate_long.parquet", index=False)

    target_ids_exact = set(qids_by_target)
    exact_qids = set(qid_to_targets)
    large_population = int(selected.population.sum())
    qid_targets = selected.loc[selected.source_record_id.isin(target_ids_exact)]
    full_entity_qids = {q for q, val in qid_summary.items() if val["raw_entity_present"]}
    p1082_qids = {q for q, val in qid_summary.items() if val["nondeprecated_p1082_count"]}
    rows_with_qid = int(len(qid_targets))
    rows_with_p1082 = int(qid_targets.source_record_id.isin(set(s for q in p1082_qids for s in qid_to_targets[q])).sum())
    # Full-entity statement inventory counts distinct statements once per QID, not per target row.
    statements_by_qid = long.drop_duplicates(["wikidata_qid", "statement_id"])
    year_counter = Counter()
    precision_counter = Counter()
    for record in statements_by_qid.itertuples(index=False):
        times = json.loads(record.p585_literals_json or "[]")
        if not times:
            year_counter["<no_P585>"] += 1
        for item in times:
            year_counter[str(item.get("literal_year_prefix_only_not_census_assignment") or "<unparsed_P585>")] += 1
            precision_counter[str(item.get("precision"))] += 1

    # Coverage comparison only: these are flattened/secondary representations in the same
    # Wikimedia/Wikipedia family, not additional, independent population claims.
    population_tsv = RAW / "wikimedia/wikidata_oktmo_population.tsv"
    tsv = pd.read_csv(population_tsv, sep="\t", dtype=str)
    qcol = "?item"
    tsv["qid"] = tsv[qcol].str.extract(r"/(Q\d+)>?$")
    tsv_matching = tsv.loc[tsv.qid.isin(exact_qids)].copy()
    tsv_qids = set(tsv_matching.qid.dropna())
    tsv_statement_count = int(tsv_matching["?statement"].nunique())
    tsv_matching["raw_tsv_line_number"] = tsv_matching.index + 2
    def literal_variants(values) -> str:
        return json.dumps(sorted({str(v) for v in values if pd.notna(v)}), ensure_ascii=False)
    tsv_line_map = tsv_matching.groupby(["qid", "?statement"], as_index=False).agg(
        raw_duplicate_row_count=("raw_tsv_line_number", "size"),
        raw_matching_line_numbers_json=("raw_tsv_line_number", lambda vals: json.dumps(sorted(map(int, vals)))),
        date_literal_variants_json=("?date", literal_variants),
        population_literal_variants_json=("?population", literal_variants),
        oktmo_literal_variants_json=("?oktmo", literal_variants),
        rank_uri_variants_json=("?rank", literal_variants),
    )
    tsv_long = tsv_matching.drop_duplicates(["qid", "?statement"]).copy()
    tsv_long = tsv_long.merge(tsv_line_map, on=["qid", "?statement"], validate="one_to_one")
    tsv_long = tsv_long.rename(columns={
        "?item": "wikidata_item_uri", "?oktmo": "oktmo_literal_raw",
        "?statement": "statement_uri", "?population": "population_literal_flat_tsv",
        "?date": "date_literal_flat_tsv", "?rank": "rank_uri_flat_tsv",
    })
    tsv_long["date_literal_variant_count"] = tsv_long.date_literal_variants_json.map(lambda x: len(json.loads(x)))
    tsv_long["date_literal_ambiguous"] = tsv_long.date_literal_variant_count.gt(1)
    # Suppress the arbitrarily retained first scalar when duplicate source rows disagree.
    tsv_long.loc[tsv_long.date_literal_ambiguous, "date_literal_flat_tsv"] = None
    tsv_long["target_source_record_ids_2021_json"] = tsv_long.qid.map(
        lambda q: json.dumps(sorted(qid_to_targets.get(q, [])), ensure_ascii=False))
    tsv_long["statement_id"] = tsv_long.statement_uri.astype(str).str.extract(r"/statement/([^>]+)")[0].str.replace("-", "$", n=1)
    admissible_rank_uris = {
        "<http://wikiba.se/ontology#NormalRank>",
        "<http://wikiba.se/ontology#PreferredRank>",
    }
    deprecated_rank_uri = "<http://wikiba.se/ontology#DeprecatedRank>"
    tsv_long["rank_is_deprecated"] = tsv_long.rank_uri_flat_tsv.eq(deprecated_rank_uri)
    tsv_long["rank_admissible_for_candidate_history"] = tsv_long.rank_uri_flat_tsv.isin(admissible_rank_uris)
    tsv_long["raw_source_file"] = str(population_tsv)
    tsv_long["raw_source_sha256"] = sha(population_tsv)
    tsv_long["raw_source_line_number"] = tsv_long.raw_tsv_line_number
    tsv_long["evidence_tier"] = "flat_TSV_candidate_no_full_qualifiers_or_references"
    tsv_long["population_admission"] = False
    tsv_long["historical_identity_admission"] = False
    tsv_long.to_parquet(OUT / "candidate_tsv_long.parquet", index=False)
    full_statement_ids = set(long.statement_id.dropna().astype(str))
    tsv_full_entity_overlap = int(tsv_long.statement_id.isin(full_statement_ids).sum())
    tsv_year_counter = Counter()
    for variants_json in tsv_long.date_literal_variants_json:
        for literal in json.loads(variants_json):
            match = re.match(r"^([+-]?\d{4})", literal)
            tsv_year_counter[match.group(1) if match else "<unparsed>"] += 1
    tsv_rank_counter = Counter(tsv_long.rank_uri_flat_tsv.fillna("<missing>").astype(str))
    tsv_deprecated_count = int(tsv_long.rank_is_deprecated.sum())
    tsv_history_admissible_count = int(tsv_long.rank_admissible_for_candidate_history.sum())
    module_file = RAW / "wikipedia_statistical/module_qid_population.jsonl.gz"
    module_qids = set()
    module_rows = 0
    with gzip.open(module_file, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            qid = re.search(r"(Q\d+)$", str(record.get("item", "")))
            if qid and qid.group(1) in exact_qids:
                module_qids.add(qid.group(1)); module_rows += 1
    literal_associations = pd.read_parquet(F / "wiki_literal_associations.parquet")
    literal_qids = set(literal_associations.wikidata_qid.dropna().astype(str)) & exact_qids
    literal_rows = int(literal_associations.wikidata_qid.astype("string").isin(exact_qids).sum())

    graph_old_targets = {sid for sid, ids in graph_old_by_target.items() if ids}
    graph_old_large_exact = qid_targets.loc[qid_targets.source_record_id.isin(target_ids_exact) & qid_targets.source_record_id.isin(graph_old_targets)]
    graph_year_counts = Counter()
    for sid in graph_old_targets & target_ids_exact:
        for oldid in graph_old_by_target.get(sid, []):
            year = hist_year.get(oldid)
            if year:
                graph_year_counts[year] += 1

    summary = {
        "status": "candidate_only_cached_population_series_diagnostic_no_population_or_identity_admissions",
        "scope": {"year": 2021, "source_population_scope": "settlement", "physical_source_flag": "source_is_physical_np=True", "minimum_population_inclusive": MIN_POP},
        "current_large_universe": {"rows": int(len(selected)), "population": large_population},
        "exact_wide_p764_qid_coverage": {
            "target_rows_with_at_least_one_exact_qid": rows_with_qid,
            "population_of_covered_rows": int(qid_targets.population.sum()),
            "covered_population_share": float(qid_targets.population.sum() / large_population) if large_population else None,
            "distinct_exact_qids": int(len(exact_qids)),
            "targets_with_multiple_exact_qids": int((wide.groupby("source_record_id").wikidata_qid.nunique() > 1).sum()),
        },
        "cached_full_entity_and_p1082_coverage": {
            "exact_qids_with_full_entity_record": int(len(full_entity_qids)),
            "exact_qids_missing_full_entity_record": int(len(exact_qids - full_entity_qids)),
            "exact_qids_with_nondeprecated_P1082": int(len(p1082_qids)),
            "large_target_rows_with_nondeprecated_P1082": rows_with_p1082,
            "large_target_population_with_nondeprecated_P1082": int(qid_targets.loc[qid_targets.source_record_id.isin(set(s for q in p1082_qids for s in qid_to_targets[q])), "population"].sum()),
            "distinct_nondeprecated_P1082_statements": int(len(statements_by_qid)),
            "deprecated_P1082_statements_skipped": int(deprecated_count),
            "population_statements_by_literal_P585_year_prefix": dict(sorted(year_counter.items())),
            "P585_precision_value_counts": dict(sorted(precision_counter.items())),
            "statements_with_any_reference": int(statements_by_qid.references_count.gt(0).sum()) if len(statements_by_qid) else 0,
            "statements_with_P854_reference_url": int(statements_by_qid.references_with_p854_url_count.gt(0).sum()) if len(statements_by_qid) else 0,
            "statement_rank_counts": dict(Counter(statements_by_qid["rank"].fillna("<missing>").astype(str))),
        },
        "existing_accepted_graph_context": {
            "accepted_component_filter": "accepted_identity_edges filtered by canonical decision_status allowlist from mass_linkage/coverage.py; optional candidate_only/admission flags are ignored; no new edges added",
            "large_exact_qid_rows_with_existing_old_year_component": int(len(graph_old_large_exact)),
            "population_of_large_exact_qid_rows_with_existing_old_year_component": int(graph_old_large_exact.population.sum()),
            "linked_old_endpoint_counts_by_year": dict(sorted(graph_year_counts.items())),
            "role": "existing same-place identity context only; P1082 P585 values are not assigned to census years and graph links do not assert population comparability",
        },
        "same_family_coverage_checks_not_added_as_facts": {
            "wikidata_population_tsv_qids_covered": int(len(tsv_qids)),
            "wikidata_population_tsv_distinct_statement_ids": tsv_statement_count,
            "wikidata_population_tsv_candidate_rows_after_qid_statement_dedup": int(len(tsv_long)),
            "wikidata_population_tsv_raw_matching_rows_before_dedup": int(len(tsv_matching)),
            "wikidata_population_tsv_statement_ids_overlapping_full_entity_P1082": tsv_full_entity_overlap,
            "wikidata_population_tsv_statements_with_date_literal_ambiguity": int(tsv_long.date_literal_ambiguous.sum()),
            "wikidata_population_tsv_statements_with_population_literal_variants": int(tsv_long.population_literal_variants_json.map(lambda x: len(json.loads(x)) > 1).sum()),
            "wikidata_population_tsv_statements_with_oktmo_literal_variants": int(tsv_long.oktmo_literal_variants_json.map(lambda x: len(json.loads(x)) > 1).sum()),
            "wikidata_population_tsv_statements_with_rank_uri_variants": int(tsv_long.rank_uri_variants_json.map(lambda x: len(json.loads(x)) > 1).sum()),
            "wikidata_population_tsv_statements_by_rank": dict(sorted(tsv_rank_counter.items())),
            "wikidata_population_tsv_raw_inventory_statements": int(len(tsv_long)),
            "wikidata_population_tsv_deprecated_rank_statements_retained_but_excluded_from_candidate_history": tsv_deprecated_count,
            "wikidata_population_tsv_nondeprecated_candidate_history_statements": tsv_history_admissible_count,
            "wikidata_population_tsv_literal_date_year_prefix_counts_not_census_assignments": dict(sorted(tsv_year_counter.items())),
            "wikidata_population_tsv_rank_uri_counts": dict(sorted(tsv_rank_counter.items())),
            "wikipedia_statistical_module_qids_covered": int(len(module_qids)),
            "wikipedia_statistical_module_matching_rows": module_rows,
            "existing_wiki_literal_associations_qids_covered": int(len(literal_qids)),
            "existing_wiki_literal_associations_matching_rows": literal_rows,
            "interpretation": "TSV rows are retained in candidate_tsv_long.parquet as lower-detail raw population observations; full entity statements preserve qualifiers/references. TSV/module/literal data belong to the same Wikimedia/Wikipedia family, are deduplicated by statement ID where possible, and are never counted as independent corroboration",
        },
        "input_sha256": {
            str(path): sha(path) for path in [
                F / "selected_observations.parquet", F / "accepted_identity_edges.parquet",
                F / "wiki_literal_associations.parquet", W / "wide_point_bindings.parquet",
                W / "provider_code_candidate_screen.parquet", W / "manifest.json",
                population_tsv, module_file,
            ]
        },
        "raw_full_entity_batch_files": raw_file_hashes,
        "raw_full_entity_cache": {
            "batch_file_count": len(entity_files), "unique_entity_qids_in_all_batches": len(raw_entity_qids),
            "unique_entity_qids_with_nondeprecated_P1082": len(raw_entity_p1082_qids),
            "overlapping_exact_qids": int(len(full_entity_qids)),
        },
        "output": {
            "candidate_long.parquet": {"rows": int(len(long)), "sha256": sha(OUT / "candidate_long.parquet"), "columns": list(long.columns)},
            "candidate_tsv_long.parquet": {"rows": int(len(tsv_long)), "sha256": sha(OUT / "candidate_tsv_long.parquet"), "columns": list(tsv_long.columns)},
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "report.md").write_text(make_report(summary), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in {"input_sha256", "raw_full_entity_batch_files", "output"}}, ensure_ascii=False, indent=2))


def make_report(s: dict) -> str:
    u = s["current_large_universe"]
    c = s["exact_wide_p764_qid_coverage"]
    p = s["cached_full_entity_and_p1082_coverage"]
    g = s["existing_accepted_graph_context"]
    x = s["same_family_coverage_checks_not_added_as_facts"]
    return f'''# Large-settlement Wikidata P1082 history inventory\n\n**Status:** candidate-only source inventory. No population value, historical identity edge, or coordinate was admitted. Current scope is 2021 physical settlement observations with population >= {MIN_POP:,}.\n\n## Coverage\n\n- Current large physical universe: {u['rows']:,} rows, population {u['population']:,}.\n- Exact WIDE-v5 truthy P764-linked QID: {c['target_rows_with_at_least_one_exact_qid']:,} rows, population {c['population_of_covered_rows']:,} ({100*c['covered_population_share']:.1f}% of this large universe), {c['distinct_exact_qids']:,} QIDs. These remain exact-code candidates.\n- Cached full entity records: {p['exact_qids_with_full_entity_record']:,} of {c['distinct_exact_qids']:,} exact QIDs are present in {s['raw_full_entity_cache']['batch_file_count']} cached batches ({s['raw_full_entity_cache']['unique_entity_qids_in_all_batches']:,} unique entity QIDs across the cache). These matching full entities contain nondeprecated P1082 for {p['exact_qids_with_nondeprecated_P1082']:,} current rows (population {p['large_target_population_with_nondeprecated_P1082']:,}), with {p['distinct_nondeprecated_P1082_statements']:,} distinct statements. Cache absence for another exact QID means only that its full entity is not in this cache.\n- The flat TSV raw inventory contains {x['wikidata_population_tsv_raw_inventory_statements']:,} distinct QID-statement observations for {x['wikidata_population_tsv_qids_covered']:,} of the large exact QIDs ({x['wikidata_population_tsv_raw_matching_rows_before_dedup']:,} raw matching rows before deduplication); {x['wikidata_population_tsv_nondeprecated_candidate_history_statements']:,} are nondeprecated and eligible for candidate history, while {x['wikidata_population_tsv_deprecated_rank_statements_retained_but_excluded_from_candidate_history']:,} deprecated-rank statements remain preserved in the raw inventory but are explicitly excluded from candidate history. Rank counts are {json.dumps(x['wikidata_population_tsv_statements_by_rank'], ensure_ascii=False)}. {x['wikidata_population_tsv_statement_ids_overlapping_full_entity_P1082']:,} statement IDs overlap the full-entity inventory after GUID normalization. See `candidate_tsv_long.parquet` for literal amount/date/rank/OKTMO and source-line provenance.\n- Existing accepted identity graph components connect {g['large_exact_qid_rows_with_existing_old_year_component']:,} exact-QID current targets (population {g['population_of_large_exact_qid_rows_with_existing_old_year_component']:,}) to historical endpoint rows; endpoint years are {json.dumps(g['linked_old_endpoint_counts_by_year'], ensure_ascii=False)}. This is existing identity context only.\n\n## What is preserved\n\n`candidate_long.parquet` has one row per 2021 source-QID-P1082 statement found in cached full entities. It preserves literal amount and unit, rank, statement ID, raw P585 time/precision/calendar/before/after, every qualifier (including P518 and P459 where present), all references, full raw statement JSON, QID/entity revision and modified time, full-entity retrieval time, raw batch SHA-256, and locator. Deprecated P1082 claims are excluded; they are counted in `summary.json`. P585 year prefixes are indexed for coverage summaries but remain literal qualifiers; a year-only `2002` does not establish a 2002 census observation.\n\n`candidate_tsv_long.parquet` retains the full raw TSV inventory deduplicated by QID + statement ID, including literal amount/rank/OKTMO, every distinct raw date literal, all duplicate source line numbers and the source hash. It marks normal/preferred ranks as admissible for candidate history and deprecated ranks as ineligible; all 17 deprecated statements remain preserved but must not enter the usable history series. Four statement IDs have conflicting date literals across repeated raw rows; for those rows the scalar date field is suppressed and all alternatives remain in `date_literal_variants_json`. The flat TSV omits date precision, full qualifiers and references, so its dates do not settle population scope/grain or census-year interpretation alone. Shared statement GUIDs are deduplicated across tiers for overlap counts and are never independent corroboration.\n\n## Evidence limits and next step\n\nThe full-entity JSON preserves the richest cached statement form. TSV, module rows ({x['wikipedia_statistical_module_qids_covered']:,} matching QIDs), and existing literal associations ({x['existing_wiki_literal_associations_qids_covered']:,}) belong to one Wikimedia/Wikipedia lineage and are not independent corroboration. The TSV/module flattening does not retain the full qualifiers and references present in the raw entity.\n\nTreat this as a bounded large-population historical-series pilot. Review dated statements' scope, P518 qualifiers, references and object grain against source records before creating any census-year population assertion. Do not infer a census match from P585 year alone, use city/municipality population as settlement population, or create new graph links. Existing accepted graph components remain unchanged. The historical component uses the canonical `decision_status` allowlist from `research_rebuild/mass_linkage/coverage.py`; optional flags do not define acceptance. Existing small-settlement exceptions remain untouched.\n\nReproduce with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/settlements-venv/bin/python {OUT}/build_large_p1082_diagnostic.py`. Full source, batch, and output hashes are in `summary.json`.\n'''


if __name__ == "__main__":
    main()
