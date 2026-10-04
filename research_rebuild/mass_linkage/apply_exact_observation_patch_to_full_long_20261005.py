#!/usr/bin/env python3
"""Rebuild a full long view from a tiny census-row patch, preserving all other IDs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd

from research_rebuild.mass_linkage.build_long_table import build_long_table


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selected", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--points", required=True)
    ap.add_argument("--annual", required=True)
    ap.add_argument("--base-long", required=True)
    ap.add_argument("--source-ids", required=True, help="JSON list of exact source_record_id values")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--expected-rows", type=int, required=True)
    ap.add_argument("--expected-census-rows", type=int, required=True)
    ap.add_argument("--expected-census-population", type=int, required=True)
    args = ap.parse_args()

    out = Path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory must be empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    ids = json.loads(args.source_ids)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("patch source IDs must be a nonempty unique list")
    selected = pd.read_parquet(args.selected)
    subset = selected[selected.source_record_id.astype(str).isin(ids)].copy()
    if set(subset.source_record_id.astype(str)) != set(ids):
        raise ValueError("requested patch IDs do not exactly exist in selected population layer")
    if subset.source_record_id.astype(str).duplicated().any():
        raise ValueError("selected source IDs are not unique")
    subset_path = out / "patch_selected.parquet"
    subset.to_parquet(subset_path, index=False)

    # Keep only edges and accepted point uses that touch this tiny identity set.
    con = duckdb.connect(config={"threads": "1", "memory_limit": "2GB", "preserve_insertion_order": "false"})
    graph_path = Path(args.graph)
    points_path = Path(args.points)
    ids_sql = ",".join("'" + sid.replace("'", "''") + "'" for sid in ids)
    patch_graph = out / "patch_edges.parquet"
    con.execute(f"""COPY (
      SELECT * FROM read_parquet('{graph_path}')
      WHERE from_source_record_id IN ({ids_sql}) OR to_source_record_id IN ({ids_sql})
    ) TO '{patch_graph}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    patch_points = out / "patch_points.parquet"
    con.execute(f"""COPY (
      SELECT * FROM read_parquet('{points_path}') WHERE target_source_record_id IN ({ids_sql})
    ) TO '{patch_points}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    patch_edge_ids = con.execute(f"""SELECT DISTINCT id FROM (
      SELECT from_source_record_id AS id FROM read_parquet('{patch_graph}')
      UNION ALL SELECT to_source_record_id AS id FROM read_parquet('{patch_graph}')
    )""").fetchdf().id.astype(str).tolist()
    if not set(ids).issubset(set(patch_edge_ids)):
        raise ValueError("a requested patch record has no accepted identity path")

    annual = pd.read_parquet(args.annual)
    annual.iloc[:0].to_parquet(out / "empty_annual.parquet", index=False)
    patch_path = out / "rebuilt_patch.parquet"
    patch_table, patch_manifest = build_long_table(
        census_path=subset_path, identity_path=patch_graph, coordinates_path=patch_points,
        annual_path=out / "empty_annual.parquet", output_path=patch_path,
        wiki_path=None, source_evidence_path=None, source_manifest_path=None,
    )
    patch_table = patch_table[patch_table.record_type.eq("census")].copy()
    expected_obs = {f"census:{sid}" for sid in ids}
    if set(patch_table.observation_id.astype(str)) != expected_obs:
        raise ValueError("rebuilt census patch IDs do not exactly match request")
    patch_table.to_parquet(out / "exact_census_patch.parquet", index=False)
    patch_path = out / "exact_census_patch.parquet"

    base = Path(args.base_long)
    final = out / "settlements_long_refreshed.parquet"
    con.execute(f"CREATE VIEW base AS SELECT * FROM read_parquet('{base}')")
    con.execute(f"CREATE VIEW patch AS SELECT * FROM read_parquet('{patch_path}')")
    base_rows = con.execute("SELECT count(*) FROM base").fetchone()[0]
    base_obs_ids = con.execute("SELECT count(DISTINCT observation_id) FROM base").fetchone()[0]
    if base_rows != args.expected_rows or base_obs_ids != base_rows:
        raise ValueError("base full-long rows/observation IDs fail expected uniqueness guard")
    absent = con.execute("""SELECT count(*) FROM patch p LEFT JOIN base b USING(observation_id)
      WHERE b.observation_id IS NULL""").fetchone()[0]
    if absent:
        raise ValueError(f"{absent} patch observation IDs are absent from base long")
    patch_n = con.execute("SELECT count(*) FROM patch").fetchone()[0]
    if patch_n != len(expected_obs):
        raise ValueError("unexpected number of exact patch rows")
    con.execute(f"""COPY (
      SELECT * FROM patch
      UNION ALL BY NAME
      SELECT b.* FROM base b WHERE NOT EXISTS
        (SELECT 1 FROM patch p WHERE p.observation_id=b.observation_id)
    ) TO '{final}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    final_rows = con.execute(f"SELECT count(*) FROM read_parquet('{final}')").fetchone()[0]
    census = con.execute(f"""SELECT count(*), round(sum(population_value))
      FROM read_parquet('{final}') WHERE record_type='census'""").fetchone()
    if final_rows != args.expected_rows or census != (args.expected_census_rows, args.expected_census_population):
        raise ValueError(f"full-long population guard failed: rows={final_rows}, census={census}")
    patch_json = con.execute(f"""SELECT observation_id,entity_id,latitude,longitude,
       census_full_chain,census_2002_status,census_2010_status,census_2021_status
       FROM read_parquet('{final}') WHERE observation_id IN ({','.join("'census:"+sid.replace("'","''")+"'" for sid in ids)})
       ORDER BY observation_year""").fetchdf().to_dict("records")
    receipt = {
        "status": "full_long_exact_census_observation_patch_passed",
        "base_long": {"path": str(base), "sha256": sha(base), "rows": base_rows},
        "selected": {"path": args.selected, "sha256": sha(Path(args.selected))},
        "graph": {"path": str(graph_path), "sha256": sha(graph_path)},
        "point_uses": {"path": str(points_path), "sha256": sha(points_path)},
        "exact_source_ids": ids,
        "exact_observation_ids_replaced": patch_n,
        "base_only_rows_preserved": base_rows - patch_n,
        "final_rows": final_rows,
        "census_rows": census[0],
        "selected_census_population_sum": census[1],
        "population_values_modified": False,
        "readback": patch_json,
        "final": {"path": str(final), "sha256": sha(final), "bytes": final.stat().st_size},
        "patch_builder_summary": patch_manifest.get("summary"),
    }
    (out / "refresh_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
