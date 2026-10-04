#!/usr/bin/env python3
"""Build a point-only quarantine for the two reviewed Taezhny DBF uses.

The accepted point ledger is immutable input. This emits a full two-row
supersession snapshot and a remaining ledger retaining its original schema.
It does not edit graph edges, census observations, or source files.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path("/workspace/settlements-work/continuation_20261004")
OUT = ROOT / "root/accepted_taezhny_point_quarantine"
POINTS = ROOT / "accepted_mass_eleventh_reviewed28_point2/accepted_point_uses.parquet"
GRAPH = ROOT / "accepted_mass_eleventh_reviewed28_point2/accepted_identity_edges.parquet"
EXPECTED_POINT_SHA = "90a7c08ec0877472e80a52d42be37e0e37c0064578236f0810e599cb2fbc1ad5"
DBF = Path("/workspace/settlements-raw/data/raw/historical_geography/geokladr_okato_2011/okato.dbf")
DBF_SHA = "d1c8b983f2489724a940bd2a64dedda73b602f6c491d5c09391deaf362fe2650"
EXPECTED_DBFS = {
    "2002:070_48ec6f4a77_Irkut_obl_new.xls:Sheet1:1623",
    "2010:008_342f3c208b_16._20Сиб_ФО_2010.xls:Sib:4924",
}
CURRENT_PRESERVE_IDS = {
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:25538",
    "2021:data_allsettlements_anon_156_v20251217.parquet:parquet:24744",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def take_rows(iterator, n: int, schema: pa.Schema, carry: list[pa.RecordBatch]) -> pa.Table:
    """Read exactly n ordered rows from an Arrow batch iterator."""
    pieces: list[pa.RecordBatch] = []
    left = n
    while left:
        if not carry:
            carry.append(next(iterator))
        batch = carry.pop()
        if batch.num_rows <= left:
            pieces.append(batch)
            left -= batch.num_rows
        else:
            pieces.append(batch.slice(0, left))
            carry.append(batch.slice(left))
            left = 0
    return pa.Table.from_batches(pieces, schema=schema)


def main() -> None:
    if not POINTS.is_file() or not GRAPH.is_file() or not DBF.is_file():
        raise FileNotFoundError("Required frozen point, graph, or raw DBF input is missing")
    if OUT.exists():
        existing_outputs = [p.name for p in OUT.iterdir() if p.name != Path(__file__).name]
        if existing_outputs:
            raise FileExistsError(f"Refusing to overwrite existing output files: {existing_outputs}")
    OUT.mkdir(parents=True, exist_ok=True)
    point_sha_before = sha256(POINTS)
    graph_sha_before = sha256(GRAPH)
    dbf_sha_before = sha256(DBF)
    if point_sha_before != EXPECTED_POINT_SHA:
        raise ValueError(f"Unexpected point ledger SHA: {point_sha_before}")
    if dbf_sha_before != DBF_SHA:
        raise ValueError(f"Unexpected DBF SHA: {dbf_sha_before}")

    point_pf = pq.ParquetFile(POINTS)
    graph_pf = pq.ParquetFile(GRAPH)
    schema = point_pf.schema_arrow
    key = "target_source_record_id"
    if key not in schema.names:
        raise ValueError("Frozen point ledger lacks target_source_record_id")
    targets = EXPECTED_DBFS
    remaining_path = OUT / "accepted_point_uses.parquet"
    superseded_path = OUT / "superseded_point_uses.parquet"
    writer = pq.ParquetWriter(remaining_path, schema, compression="zstd")
    excluded_rows: list[dict] = []
    preserved_ids: set[str] = set()
    total = excluded = 0
    for batch in point_pf.iter_batches(batch_size=8192):
        ids = batch.column(batch.schema.get_field_index(key)).to_pylist()
        mask = [x in targets for x in ids]
        total += len(ids)
        if any(mask):
            positions = [i for i, selected in enumerate(mask) if selected]
            for row in batch.take(pa.array(positions, type=pa.int64())).to_pylist():
                excluded_rows.append(row)
            excluded += len(positions)
        keep = [i for i, selected in enumerate(mask) if not selected]
        if keep:
            writer.write_batch(batch.take(pa.array(keep, type=pa.int64())))
        preserved_ids.update(x for x in ids if x in CURRENT_PRESERVE_IDS)
    writer.close()

    if total != 418256 or excluded != 2 or {r[key] for r in excluded_rows} != targets:
        raise AssertionError(f"Unexpected ledger counts/target set: total={total}, excluded={excluded}, ids={[r.get(key) for r in excluded_rows]}")
    if preserved_ids != CURRENT_PRESERVE_IDS:
        raise AssertionError(f"Current point records missing from retained ledger: {CURRENT_PRESERVE_IDS - preserved_ids}")
    for row in excluded_rows:
        if (row.get("point_origin_sha256") != DBF_SHA or
                row.get("point_origin_locator") != "raw_dbf_record_number_1based=38578;byte_offset_0based=15238620" or
                row.get("latitude") != 55.6534 or row.get("longitude") != 98.9961 or
                row.get("coordinate_source_record_id") != "GeoKLADR2011:OKATO:25255553005"):
            raise AssertionError(f"Quarantined row does not match the reviewed exact DBF witness: {row.get(key)}")

    pq.write_table(pa.Table.from_pylist(excluded_rows, schema=schema), superseded_path, compression="zstd")

    # Independently confirm there is no accepted identity edge incident to either old observation.
    graph_names = set(graph_pf.schema_arrow.names)
    endpoints = [c for c in ("from_source_record_id", "to_source_record_id") if c in graph_names]
    if endpoints != ["from_source_record_id", "to_source_record_id"]:
        raise ValueError(f"Unexpected graph endpoint schema: {endpoints}")
    incidents: list[dict] = []
    for batch in graph_pf.iter_batches(columns=endpoints, batch_size=32768):
        left = batch.column(0).to_pylist()
        right = batch.column(1).to_pylist()
        for a, b in zip(left, right):
            if a in targets or b in targets:
                incidents.append({"from_source_record_id": a, "to_source_record_id": b})
    if incidents:
        raise AssertionError(f"Unexpected graph edges incident to old point targets: {incidents[:3]}")

    decisions_path = OUT / "quarantine_decisions.csv"
    with decisions_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["target_source_record_id", "target_year", "decision", "reason", "point_origin_file", "point_origin_sha256", "point_origin_locator", "latitude", "longitude", "coordinate_source_record_id", "same_dbf_witness_as_other_quarantined_use", "identity_graph_incident_edges"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in sorted(excluded_rows, key=lambda r: r["target_year"]):
            w.writerow({
                "target_source_record_id": row[key],
                "target_year": row.get("target_year"),
                "decision": "point_use_quarantined_superseded",
                "reason": "Exact 2011 DBF record 38578 is a Shelekhovsky name/type/code row, but its point is 522.209 km from the current Shelekhovsky Taezhny source-row point and 0.065 km from a distinct Nizhneudinsky Taezhny tract; do not use this historical point for the Shelekhovsky observation.",
                "point_origin_file": row.get("point_origin_file"),
                "point_origin_sha256": row.get("point_origin_sha256"),
                "point_origin_locator": row.get("point_origin_locator"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "coordinate_source_record_id": row.get("coordinate_source_record_id"),
                "same_dbf_witness_as_other_quarantined_use": "true",
                "identity_graph_incident_edges": 0,
            })

    if sha256(POINTS) != point_sha_before or sha256(GRAPH) != graph_sha_before or sha256(DBF) != dbf_sha_before:
        raise AssertionError("An input changed during the run")
    remaining_pf = pq.ParquetFile(remaining_path)
    superseded_pf = pq.ParquetFile(superseded_path)
    if remaining_pf.metadata.num_rows != 418254 or superseded_pf.metadata.num_rows != 2:
        raise AssertionError("Output row count mismatch")
    if not remaining_pf.schema_arrow.equals(schema, check_metadata=True) or not superseded_pf.schema_arrow.equals(schema, check_metadata=True):
        raise AssertionError("Output schema/metadata differs from frozen baseline")

    # Verify every retained source row, in original order, against the written
    # output. This is streamed in bounded batches and checks every column.
    actual_iter = iter(remaining_pf.iter_batches(batch_size=8192))
    carry: list[pa.RecordBatch] = []
    compared_rows = 0
    for source_batch in point_pf.iter_batches(batch_size=8192):
        source_ids = source_batch.column(source_batch.schema.get_field_index(key)).to_pylist()
        keep = [i for i, value in enumerate(source_ids) if value not in targets]
        if not keep:
            continue
        expected = pa.Table.from_batches([source_batch.take(pa.array(keep, type=pa.int64()))], schema=schema)
        actual = take_rows(actual_iter, expected.num_rows, remaining_pf.schema_arrow, carry)
        if not expected.equals(actual, check_metadata=True):
            raise AssertionError(f"Retained row content/order mismatch near source row {compared_rows + 1}")
        compared_rows += expected.num_rows
    if compared_rows != 418254 or carry or next(actual_iter, None) is not None:
        raise AssertionError("Retained streaming row comparison did not consume exactly the output")
    expected_removed = pa.Table.from_pylist(excluded_rows, schema=schema)
    actual_removed = pq.read_table(superseded_path)
    if not expected_removed.equals(actual_removed, check_metadata=True):
        raise AssertionError("Superseded rows differ from the two exact frozen baseline rows")

    receipt = {
        "status": "point_only_quarantine_complete_no_identity_or_population_mutation",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "baseline_point_ledger": {"path": str(POINTS), "sha256": point_sha_before, "rows": total, "schema_fields": len(schema.names)},
        "identity_graph": {"path": str(GRAPH), "sha256": graph_sha_before, "rows": graph_pf.metadata.num_rows, "incident_edges_for_quarantined_ids": len(incidents)},
        "raw_dbf": {"path": str(DBF), "sha256": dbf_sha_before, "locator": "record_number_1based=38578;byte_offset_0based=15238620", "code": "25255553005", "raw_name": "п Таежный", "raw_type": "п", "lat": 55.6534, "lon": 98.9961},
        "decision_scope": {"quarantined_point_uses": sorted(targets), "identity_edges_removed": 0, "source_observations_or_population_changed": False, "current_point_targets_preserved": sorted(CURRENT_PRESERVE_IDS), "replacement_or_identity_claim_made": False},
        "outputs": {
            "accepted_point_uses.parquet": {"sha256": sha256(remaining_path), "rows": remaining_pf.metadata.num_rows, "schema_fields": len(remaining_pf.schema_arrow.names)},
            "superseded_point_uses.parquet": {"sha256": sha256(superseded_path), "rows": superseded_pf.metadata.num_rows, "schema_fields": len(superseded_pf.schema_arrow.names)},
            "quarantine_decisions.csv": {"sha256": sha256(decisions_path), "rows": 2},
        },
        "verification": {"exactly_two_expected_point_uses_removed": True, "retained_schema_and_metadata_equal_baseline": True, "all_418254_retained_rows_and_all_453_fields_stream_compared_in_order": True, "superseded_full_rows_equal_baseline": True, "graph_incident_check_passed": True, "inputs_rehashed_after_run": True},
    }
    script = Path(__file__)
    receipt["script"] = {"path": str(script), "sha256": sha256(script)}
    write_json(OUT / "receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
