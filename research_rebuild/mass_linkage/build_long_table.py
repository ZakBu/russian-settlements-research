#!/usr/bin/env python3
"""Build a reproducible, source-preserving long table from accepted inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pyarrow.parquet as pq


DEFAULTS = {
    "census": "/workspace/settlements-data/research_rebuild/evidence/releases/national_source_selection_r2_regional_2010_20260930/selected_observations.parquet",
    "identity": "/workspace/settlements-work/identity/accepted_ordinary_v4/accepted_identity_edges.parquet",
    "coordinates": "/workspace/settlements-work/coordinates/accepted_modern_v1/accepted_point_uses.parquet",
    "annual": "/workspace/settlements-work/sources/annual-yearbook-accepted/annual_observations_accepted.parquet",
    "wiki": "/workspace/settlements-work/sources/annual_associations_accepted_v1/annual_named_history_associations.parquet",
    "source_evidence": "/workspace/settlements-work/candidates/optimized_run/source_evidence.parquet",
    "source_manifest": "/workspace/settlements-baseline/output/input_manifest.parquet",
}

ACCEPTED_EDGE_STATUSES = {
    "checked_rule_accepted", "checked_rule_accepted_redundant_graph_connectivity_effect",
    "accepted_rule_family_after_independent_sample_review", "case_specific_independent_review_accepted",
    "case_review_accepted", "independent_case_review_accepted", "accepted_case_specific",
}
ACCEPTED_PROJECTION_STATUSES = {"active_endpoints_selected", "active_after_reviewed_publication_binding_migration"}
ACCEPTED_COORDINATE_STATUSES = {"reviewed_rule_accepted", "frozen_r5b_reviewed_baseline_preserved"}


class UnionFind:
    def __init__(self, values: Iterable[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            nxt = self.parent[value]
            self.parent[value] = root
            value = nxt
        return root

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            # The representative itself is not exposed, but a stable union is useful
            # for repeatable diagnostics and debugging.
            low, high = sorted((a, b))
            self.parent[high] = low


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _none(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value


def _row_dict(row: pd.Series) -> dict[str, Any]:
    return {key: _none(value) for key, value in row.items()}


def _build_entity_map(census: pd.DataFrame, edges: pd.DataFrame, aggregate_ids: set[str] | None = None) -> tuple[dict[str, str], set[str], dict[str, set[int]]]:
    ids = census.source_record_id.astype(str).tolist()
    if len(ids) != len(set(ids)):
        raise ValueError("selected census has duplicate source_record_id values")
    present = set(ids)
    uf = UnionFind(ids)
    unknown_statuses = set(edges.decision_status.dropna().astype(str)) - ACCEPTED_EDGE_STATUSES
    unknown_projections = set(edges.selection_projection_status.dropna().astype(str)) - ACCEPTED_PROJECTION_STATUSES
    if edges.decision_status.isna().any() or unknown_statuses:
        raise ValueError(f"identity input has unrecognized/missing decision_status: {sorted(unknown_statuses)}")
    if edges.selection_projection_status.isna().any() or unknown_projections:
        raise ValueError(f"identity input has unrecognized/missing selection_projection_status: {sorted(unknown_projections)}")
    if not edges.relation.eq("same_place").all():
        raise ValueError("identity input contains a non-same_place edge")
    missing = (set(edges.from_source_record_id.astype(str)) | set(edges.to_source_record_id.astype(str))) - present
    if missing:
        raise ValueError(f"identity input contains {len(missing)} endpoint(s) absent from selected census")
    accepted = edges
    years = dict(zip(census.source_record_id.astype(str), census.census_year.astype(int)))
    same_year = [e for e in accepted.itertuples(index=False) if years[str(e.from_source_record_id)] == years[str(e.to_source_record_id)]]
    if same_year:
        raise ValueError(f"identity input has {len(same_year)} same-year edge(s)")
    year_mismatches = [e for e in accepted.itertuples(index=False)
                       if str(years[str(e.from_source_record_id)]) != str(e.from_year)
                       or str(years[str(e.to_source_record_id)]) != str(e.to_year)]
    if year_mismatches:
        raise ValueError(f"identity input has {len(year_mismatches)} endpoint-year mismatch(es)")
    for edge in accepted.itertuples(index=False):
        uf.union(str(edge.from_source_record_id), str(edge.to_source_record_id))
    components: dict[str, list[str]] = {}
    for source_id in ids:
        components.setdefault(uf.find(source_id), []).append(source_id)
    entity_map: dict[str, str] = {}
    entity_years: dict[str, set[int]] = {}
    aggregate_ids = aggregate_ids or set()
    for members in components.values():
        component_years = [years[source_id] for source_id in members]
        if len(component_years) != len(set(component_years)):
            raise ValueError(f"accepted identity component contains repeated census year: {members[:5]}")
        anchor = min(members, key=lambda source_id: ({2021: 0, 2010: 1, 2002: 2}.get(years[source_id], 3), source_id))
        prefix = "statisticalaggregate" if aggregate_ids.intersection(members) else "settlement"
        entity_id = f"{prefix}:{anchor}"
        entity_years[entity_id] = set(component_years)
        for source_id in members:
            entity_map[source_id] = entity_id
    linked = set()
    for edge in accepted.itertuples(index=False):
        linked.add(str(edge.from_source_record_id))
        linked.add(str(edge.to_source_record_id))
    return entity_map, linked, entity_years


def _coordinate_scientific_quality(point: dict[str, Any]) -> str:
    rule = str(point.get("admission_rule") or "")
    reviewed_prefixes = ("independent_", "reviewed_", "national_top14_review")
    if point.get("coordinate_admission_status") == "frozen_r5b_reviewed_baseline_preserved" or rule.startswith(reviewed_prefixes):
        return "individually_reviewed"
    return "automatically_accepted_checked_rule"


def _accepted_coordinate_map(coordinates: pd.DataFrame) -> dict[str, dict[str, Any]]:
    # The input itself is the accepted-use ledger. Preserve its admission and raw
    # provider quality strings instead of interpreting numeric-looking scores.
    unknown = set(coordinates.coordinate_admission_status.dropna().astype(str)) - ACCEPTED_COORDINATE_STATUSES
    if coordinates.coordinate_admission_status.isna().any() or unknown:
        raise ValueError(f"coordinate input has unrecognized/missing admission status: {sorted(unknown)}")
    coord = coordinates[coordinates.coordinate_admission_status.isin(ACCEPTED_COORDINATE_STATUSES)]
    coord = coord.sort_values(["target_year", "target_source_record_id", "coordinate_admission_status"], kind="stable")
    return {str(row.target_source_record_id): _row_dict(pd.Series(row._asdict())) for row in coord.itertuples(index=False)}


def _coordinate_columns(point: dict[str, Any], temporal_basis: str) -> dict[str, Any]:
    return {
        "latitude": point.get("latitude"), "longitude": point.get("longitude"),
        "coordinate_quality": _coordinate_scientific_quality(point),
        "coordinate_provider_quality_raw": point.get("coordinate_quality"),
        "coordinate_admission_status": point.get("coordinate_admission_status"),
        "coordinate_temporal_basis": temporal_basis,
        "coordinate_measurement_date_unknown": point.get("coordinate_measurement_date_unknown"),
        "boundary_comparability_asserted": point.get("boundary_comparability_asserted"),
        "coordinate_source": point.get("coordinate_source"),
        "coordinate_source_record_id": point.get("coordinate_source_record_id"),
        "coordinate_provider": point.get("coordinate_provider"),
        "coordinate_provider_id": point.get("coordinate_provider_id"),
        "coordinate_admission_rule": point.get("admission_rule"),
        "coordinate_provenance": point.get("coordinate_provenance"),
        "point_source_file": point.get("source_file"), "point_source_sha256": point.get("source_sha256"),
        "point_source_locator": point.get("source_locator"),
        "provider_binding_status": point.get("provider_binding_status"),
        "provider_fias_binding_status": point.get("provider_fias_binding_status"),
    }


def _aggregate_ids_from_evidence(census_ids: set[str], evidence_path: str | Path | None) -> set[str]:
    if evidence_path is None:
        return set()
    evidence_file = pq.ParquetFile(evidence_path)
    seen: set[str] = set()
    aggregate_ids: set[str] = set()
    for batch in evidence_file.iter_batches(columns=["source_record_id", "source_evidence_json"], batch_size=65536):
        for source_id, payload in zip(batch.column(0).to_pylist(), batch.column(1).to_pylist()):
            key = str(source_id)
            if key in seen:
                raise ValueError("source_evidence has duplicate source_record_id values")
            seen.add(key)
            if json.loads(payload).get("is_federal_aggregate"):
                aggregate_ids.add(key)
    if seen != census_ids:
        raise ValueError("source_evidence must have an exact source_record_id set match to selected census")
    return aggregate_ids


def _bind_source_hashes(census: pd.DataFrame, manifest_path: str | Path | None) -> pd.DataFrame:
    result = census.copy()
    result['source_sha256_original_selected'] = result.source_sha256
    result['source_hash_binding'] = 'selected_source_projection'
    if manifest_path is None:
        return result
    manifest = pd.read_parquet(manifest_path, columns=['path', 'sha256'])
    if manifest.groupby('path').sha256.nunique().gt(1).any():
        raise ValueError('Input manifest has conflicting exact-path hashes')
    lookup = manifest.drop_duplicates('path').set_index('path').sha256
    mapped = result.source_file.map(lookup).fillna(result.source_path.map(lookup))
    mismatch = result.source_sha256.notna() & mapped.notna() & result.source_sha256.ne(mapped)
    if mismatch.any():
        raise ValueError('Selected hash disagrees with exact source manifest path')
    inferred = result.source_sha256.isna() & mapped.notna()
    result.loc[inferred, 'source_sha256'] = mapped[inferred]
    result.loc[inferred, 'source_hash_binding'] = 'exact_path_in_frozen_input_manifest'
    if result.source_sha256.isna().any():
        raise ValueError('Unresolved census source hash')
    return result


def build_long_table(
    census_path: str | Path,
    identity_path: str | Path,
    coordinates_path: str | Path,
    annual_path: str | Path,
    output_path: str | Path,
    wiki_path: str | Path | None = None,
    source_evidence_path: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    census = pd.read_parquet(census_path)
    census = _bind_source_hashes(census, source_manifest_path)
    edges = pd.read_parquet(identity_path)
    coordinates = pd.read_parquet(coordinates_path)
    annual = pd.read_parquet(annual_path)
    wiki = pd.read_parquet(wiki_path) if wiki_path else pd.DataFrame()
    census_ids = set(census.source_record_id.astype(str))
    aggregate_ids = set(census.loc[census.population_scope.eq("federal_city_region"), "source_record_id"].astype(str))
    aggregate_ids.update(_aggregate_ids_from_evidence(census_ids, source_evidence_path))
    entity_map, linked_ids, entity_years = _build_entity_map(census, edges, aggregate_ids)
    entity_category_by_id = {source_id: "statistical_aggregate" if entity_id.startswith("statisticalaggregate:") else "settlement"
                             for source_id, entity_id in entity_map.items()}
    coord_by_id = _accepted_coordinate_map(coordinates)
    oktmo_by_entity: dict[str, str | None] = {}
    current_region_by_entity: dict[str, str] = {}
    for row in census.itertuples(index=False):
        if int(row.census_year) == 2021:
            oktmo_by_entity[entity_map[str(row.source_record_id)]] = _none(row.oktmo)
            current_region_by_entity[entity_map[str(row.source_record_id)]] = str(_none(row.region_raw) or "").casefold()

    records: list[dict[str, Any]] = []
    for row in census.itertuples(index=False):
        source_id = str(row.source_record_id)
        entity_id = entity_map[source_id]
        yr = int(row.census_year)
        linked = source_id in linked_ids
        entity_category = entity_category_by_id[source_id]
        years_present = entity_years[entity_id]
        current_region = current_region_by_entity.get(entity_id, "")
        outside_scope = any(token in current_region for token in ("крым", "севастопол"))
        year_status = {}
        for census_year in (2002, 2010, 2021):
            if census_year in years_present:
                year_status[f"census_{census_year}_status"] = "observed"
            elif outside_scope and census_year in (2002, 2010):
                year_status[f"census_{census_year}_status"] = "outside_russian_census_scope"
            else:
                year_status[f"census_{census_year}_status"] = "unknown_no_record"
        d = {
            "observation_id": f"census:{source_id}", "record_type": "census", "entity_id": entity_id,
            "associated_census_entity_id": None, "association_status": "accepted_same_place_component" if linked else "unknown_no_link",
            "spatial_identity_status": "accepted_same_place_component" if linked else "unknown_no_link",
            "observation_year": yr, "reference_date": None, "source_record_id": source_id,
            "source_publication_row_id": None, "source_name_raw": _none(row.source_name_raw),
            "settlement_name": _none(row.settlement_name), "settlement_type": _none(row.settlement_type),
            "region_raw": _none(row.region_raw), "district_raw": _none(row.district_raw),
            "municipality_raw": _none(row.municipality_raw), "population_value": _none(row.population),
            "population_raw": _none(row.source_population_raw),
            "population_value_quality": _none(row.population_value_quality),
            "population_scope": _none(row.population_scope), "source_path": _none(row.source_path) or _none(row.source_file),
            "source_sheet": _none(row.source_sheet), "source_row": _none(row.source_row), "source_native_id": _none(row.source_native_id),
            "entity_grain_status": _none(row.entity_grain_status), "source_population_quality": _none(row.population_value_quality),
            "legacy_is_federal_aggregate": source_id in aggregate_ids if source_evidence_path else None,
            "source_sha256": _none(row.source_sha256), "source_locator": _none(row.source_locator),
            "source_sha256_original_selected": _none(row.source_sha256_original_selected),
            "source_hash_binding": _none(row.source_hash_binding),
            "oktmo_current_observed_2021": oktmo_by_entity.get(entity_id),
            "oktmo_observed_at_year": _none(row.oktmo) if yr == 2021 else None,
            "oktmo_identifier_observation_year": 2021 if yr == 2021 and _none(row.oktmo) is not None else None,
            "oktmo_native_raw": _none(row.oktmo) if yr == 2021 else None,
            "coordinate_candidate_latitude": _none(row.latitude), "coordinate_candidate_longitude": _none(row.longitude),
            "latitude": None, "longitude": None, "coordinate_quality": None,
            "coordinate_admission_status": None, "coordinate_temporal_basis": None,
            "coordinate_measurement_date_unknown": None, "boundary_comparability_asserted": None,
            "coordinate_provider_quality_raw": None, "coordinate_source": None, "coordinate_source_record_id": None,
            "coordinate_provider": None, "coordinate_provider_id": None, "coordinate_admission_rule": None,
            "coordinate_provenance": None, "point_source_file": None, "point_source_sha256": None, "point_source_locator": None,
            "provider_binding_status": None, "provider_fias_binding_status": None,
            "entity_category": entity_category, "identity_quality": "accepted_same_place_component" if linked else "unknown_no_link",
            "census_full_chain": {2002, 2010, 2021}.issubset(years_present), **year_status,
        }
        c = coord_by_id.get(source_id)
        if c and entity_category == "settlement":
            d.update(_coordinate_columns(c, "accepted_point_target_year"))
        records.append(d)

    for row in annual.itertuples(index=False):
        target = str(row.target_2021_source_record_id)
        aggregate = str(row.target_population_scope) == "federal_city_region"
        target_is_aggregate = entity_category_by_id.get(target) == "statistical_aggregate"
        aggregate = aggregate or target_is_aggregate
        entity_id = f"statisticalaggregate:annual:{target}" if aggregate else entity_map.get(target)
        d = {
            "observation_id": f"annual:{row.source_record_id}", "record_type": "annual_official", "entity_id": entity_id,
            "associated_census_entity_id": entity_map.get(target),
            "association_status": "separate_statistical_aggregate" if aggregate else "accepted_target_2021_same_place",
            "spatial_identity_status": "statistical_aggregate" if aggregate else "accepted_target_2021_same_place",
            "observation_year": int(row.observation_year), "reference_date": _none(row.reference_date),
            "source_record_id": str(row.source_record_id), "source_publication_row_id": _none(row.source_publication_row_id),
            "source_name_raw": _none(row.settlement_name_raw), "settlement_name": _none(row.settlement_name),
            "settlement_type": None, "region_raw": _none(row.region_qualifier_raw), "district_raw": None, "municipality_raw": None,
            "population_value": _none(row.population_reported_scaled_persons), "population_raw": _none(row.population_raw),
            "population_value_quality": _none(row.population_value_quality), "population_scope": _none(row.target_population_scope),
            "population_reported_thousand": _none(row.population_reported_thousand),
            "population_unit_multiplier": _none(row.population_unit_multiplier),
            "population_rounding_convention": _none(row.rounding_convention),
            "source_path": _none(row.source_path), "source_sha256": _none(row.source_sha256),
            "source_locator": json.dumps({"page": row.source_pdf_page, "line": row.source_line, "table": row.source_table}, ensure_ascii=False, sort_keys=True),
            "oktmo_current_observed_2021": oktmo_by_entity.get(entity_map.get(target, "")), "oktmo_observed_at_year": None,
            "oktmo_identifier_observation_year": None,
            "oktmo_native_raw": None, "coordinate_candidate_latitude": None, "coordinate_candidate_longitude": None,
            "latitude": None, "longitude": None, "coordinate_quality": None, "coordinate_admission_status": None,
            "coordinate_temporal_basis": None, "coordinate_measurement_date_unknown": None, "boundary_comparability_asserted": None,
            "coordinate_provider_quality_raw": None, "coordinate_source": None, "coordinate_source_record_id": None,
            "coordinate_provider": None, "coordinate_provider_id": None, "coordinate_admission_rule": None,
            "coordinate_provenance": None, "point_source_file": None, "point_source_sha256": None, "point_source_locator": None,
            "provider_binding_status": None, "provider_fias_binding_status": None,
            "entity_category": "statistical_aggregate" if aggregate else "settlement",
            "identity_quality": "accepted_target_2021_same_place" if not aggregate else "statistical_aggregate_not_settlement",
        }
        point = coord_by_id.get(target)
        if point and not aggregate:
            d.update(_coordinate_columns(point, "modern_rep_point_spatial_continuity_inference_dateunknown"))
            d["coordinate_measurement_date_unknown"] = True
            d["boundary_comparability_asserted"] = False
        records.append(d)

    if wiki_path:
        for row in wiki.itertuples(index=False):
            # A current article/module association is carried as a separate link.
            # It never makes an historical assertion inherit census identity or coordinates.
            entity_id = f"wiki-series:{row.candidate_id}"
            records.append({
                "observation_id": f"wiki:{row.source_record_id}",
                "record_type": "wiki_literal_series", "entity_id": entity_id,
                "associated_census_entity_id": None, "association_status": "current_named_article_association_only",
                "spatial_identity_status": "unknown_historical_physical_continuity",
                "observation_year": int(row.observation_year), "reference_date": _none(row.source_date_note_raw),
                "source_record_id": str(row.source_record_id),
                "source_publication_row_id": None, "source_name_raw": _none(row.entry_title_comment_raw),
                "settlement_name": _none(row.current_source_name), "settlement_type": _none(row.current_source_type),
                "region_raw": _none(row.current_source_region), "district_raw": None, "municipality_raw": None,
                "population_value": _none(row.population_value), "population_raw": _none(row.population_value_raw),
                "population_value_quality": _none(row.exact_population_status), "population_scope": _none(row.population_scope),
                "population_admission_status": _none(row.population_admission_status),
                "source_path": f"data/raw/wikipedia_statistical/{row.module_code}.lua.gz", "source_sha256": _none(row.module_sha256),
                "source_locator": json.dumps({"source_locator": row.source_locator, "source_key_raw": row.source_key_raw,
                                              "source_text_raw": row.source_text_raw, "module_locator": row.module_locator}, ensure_ascii=False, sort_keys=True),
                "oktmo_current_observed_2021": None, "oktmo_observed_at_year": None, "oktmo_identifier_observation_year": None,
                "oktmo_native_raw": None, "wiki_current_source_oktmo_literal": _none(row.current_source_oktmo_exact_digits),
                "coordinate_candidate_latitude": None, "coordinate_candidate_longitude": None,
                "latitude": None, "longitude": None, "coordinate_quality": None, "coordinate_admission_status": None,
                "coordinate_temporal_basis": None, "coordinate_measurement_date_unknown": None, "boundary_comparability_asserted": None,
                "coordinate_provider_quality_raw": None, "coordinate_source": None, "coordinate_source_record_id": None,
                "coordinate_provider": None, "coordinate_provider_id": None, "coordinate_admission_rule": None,
                "coordinate_provenance": None, "point_source_file": None, "point_source_sha256": None, "point_source_locator": None,
                "provider_binding_status": None, "provider_fias_binding_status": None,
                "entity_category": "wiki_named_series_association", "identity_quality": "unverified_named_series_association",
                "source_association_status": _none(row.source_association_status),
                "historical_physical_identity_status": _none(row.historical_physical_identity_status),
            })

    table = pd.DataFrame.from_records(records)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    parquet_path = output if output.suffix == ".parquet" else output.with_suffix(".parquet")
    csv_path = parquet_path.with_suffix(".csv.gz")
    manifest_path = parquet_path.with_suffix(".manifest.json")
    existing = [str(path) for path in (parquet_path, csv_path, manifest_path) if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite existing output(s): {existing}")
    table.to_parquet(parquet_path, index=False)
    table.to_csv(csv_path, index=False, compression={"method": "gzip", "mtime": 0})
    summary = {
        "row_count": len(table), "record_type_counts": dict(Counter(table.record_type)),
        "entity_category_counts": dict(Counter(table.entity_category)),
        "association_status_counts": dict(Counter(table.association_status)),
        "coordinate_admission_status_counts": dict(Counter(table.coordinate_admission_status.dropna())),
        "census_record_count": len(census), "census_linked_record_count": len(linked_ids),
        "census_singleton_unknown_no_link_count": len(census) - len(linked_ids),
        "coordinate_count": int(table.latitude.notna().sum()),
        "coordinate_count_by_record_type": {str(k): int(v) for k, v in table.loc[table.latitude.notna()].groupby("record_type").size().items()},
        "wiki_rows_have_coordinates": int(table.loc[table.record_type.eq("wiki_literal_series"), "latitude"].notna().sum()),
        "duplicate_observation_id_count": int(table.observation_id.duplicated().sum()),
    }
    inputs = {"census": Path(census_path), "identity": Path(identity_path), "coordinates": Path(coordinates_path), "annual": Path(annual_path)}
    if wiki_path:
        inputs["wiki"] = Path(wiki_path)
    if source_evidence_path:
        inputs["source_evidence"] = Path(source_evidence_path)
    if source_manifest_path:
        inputs["source_manifest"] = Path(source_manifest_path)
    manifest = {"builder": "build_long_table.py", "inputs": {k: {"path": str(v), "sha256": _sha256(v)} for k, v in inputs.items()},
                "outputs": {"parquet": {"path": str(parquet_path), "sha256": _sha256(parquet_path)},
                            "csv_gzip": {"path": str(csv_path), "sha256": _sha256(csv_path)}}, "summary": summary}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return table, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in DEFAULTS.items():
        parser.add_argument(f"--{name}", default=default, help=f"{name} input path")
    parser.add_argument("--no-wiki", action="store_true", help="omit optional staged named-history associations")
    parser.add_argument("--no-source-evidence", action="store_true", help="omit optional exact-ID source evidence")
    parser.add_argument("--output", default="/workspace/settlements-work/table_builder_probe/settlements_long.parquet")
    args = parser.parse_args()
    _, manifest = build_long_table(args.census, args.identity, args.coordinates, args.annual, args.output,
                                   None if args.no_wiki else args.wiki,
                                   None if args.no_source_evidence else args.source_evidence,
                                   args.source_manifest)
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
