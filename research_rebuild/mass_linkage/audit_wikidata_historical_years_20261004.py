"""Inventory dated secondary Wikidata values; sums are not population coverage."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import duckdb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--long", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect()
    con.execute("SET memory_limit='256MB'")
    con.read_parquet(str(args.long)).create_view("long_rows")
    con.execute("""
        CREATE TEMP TABLE claims AS
        SELECT coalesce(nullif(current_wikidata_qid,''), nullif(wikidata_id,''),
            nullif(source_wikidata_qid,''),
            nullif(regexp_extract(source_record_id,'^WIKIDATA:(Q[0-9]+):',1),'')) AS qid,
            observation_year::INTEGER AS year, population_value AS population,
            source_record_id, quantitative_year_eligible,
            coalesce(current_coordinate_carrier_latitude, latitude,
                     current_subject_context_latitude) AS current_context_latitude
        FROM long_rows WHERE record_type='wiki_literal_series'
            AND source_record_id LIKE 'WIKIDATA:%'
    """)
    total = con.execute("""SELECT count(*), count(DISTINCT qid), min(year), max(year),
        count(*) FILTER (WHERE year<2002), count(DISTINCT qid) FILTER (WHERE year<2002),
        count(*) FILTER (WHERE year<2002 AND quantitative_year_eligible IS TRUE),
        count(DISTINCT qid) FILTER (WHERE year<2002 AND quantitative_year_eligible IS TRUE)
        FROM claims""").fetchone()
    con.execute("""CREATE TEMP TABLE object_year AS
        SELECT qid, year, count(*) AS claims, count(DISTINCT population) AS variants,
            max(population) AS population,
            bool_or(current_context_latitude IS NOT NULL) AS current_context_point
        FROM claims WHERE quantitative_year_eligible IS TRUE
            AND population IS NOT NULL AND qid IS NOT NULL
        GROUP BY qid,year""")
    rows = con.execute("""SELECT year, count(*) AS object_years,
        count(*) FILTER (WHERE variants=1) AS single_value_object_years,
        sum(population) FILTER (WHERE variants=1)::BIGINT AS sum_secondary_values,
        count(*) FILTER (WHERE variants>1) AS conflicting_object_years,
        count(*) FILTER (WHERE variants=1 AND current_context_point) AS with_current_point_context
        FROM object_year GROUP BY year ORDER BY year""").fetchall()
    csv_path = args.output / "wikidata_by_year.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["year", "object_years", "single_value_object_years",
                         "sum_secondary_values", "conflicting_object_years",
                         "with_current_point_context"])
        writer.writerows(rows)
    receipt = {
        "status": "secondary_history_inventory_no_admissions_or_coverage_gain",
        "input": {"path": str(args.long), "sha256": hashlib.file_digest(args.long.open('rb'), 'sha256').hexdigest()},
        "counts": dict(zip(["claims", "qids", "first_year", "last_year", "claims_before_2002",
                             "qids_before_2002", "date_eligible_claims_before_2002",
                             "date_eligible_qids_before_2002"], total)),
        "limitations": [
            "Working-export inventory, not an exhaustive Wikidata query.",
            "Secondary values; dated-year eligibility does not admit historical identity or boundaries.",
            "Different values for the same QID/year are excluded from sums; repeated equal values count once.",
            "Different QIDs may describe overlapping objects or territories: sums are not national coverage.",
            "Current point context does not establish a historical coordinate or census boundary.",
            "Candidate current associations remain candidates; their inclusion here is inventory only.",
        ],
        "outputs": {csv_path.name: {"sha256": hashlib.file_digest(csv_path.open('rb'), 'sha256').hexdigest()}},
    }
    (args.output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(receipt["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
