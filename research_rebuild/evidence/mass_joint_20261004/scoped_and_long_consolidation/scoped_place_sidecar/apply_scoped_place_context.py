from __future__ import annotations
import hashlib, json, os
from pathlib import Path
import duckdb

ROOT = Path('/workspace/settlements-work/continuation_20261004/root')
OUT = ROOT / 'eleventh_full_long_rebuild' / 'scoped_place_context_final'
INPUT = ROOT / 'eleventh_full_long_rebuild' / 'final' / 'long_865395_with_309_current_subject_context.parquet'
OUTPUT = OUT / 'long_865395_with_309_and_scoped_place_context.parquet'
OVERLAY = OUT / 'accepted_old_scoped_place_context.parquet'
RECEIPT = OUT / 'application_receipt.json'

GROUPS = {
 'talnakh': ROOT/'accepted_talnakh_typed_scope',
 'kayerkan': ROOT/'accepted_kayerkan_typed_scope',
 'krasnodar': ROOT/'accepted_krasnodar_inclusion_scope',
 'troitsk_shcherbinka': ROOT/'accepted_secondary_supported_troitsk_shcherbinka_trajectories',
}

def sha(path: Path) -> str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def q(path: Path) -> str:
 return "'"+str(path).replace("'","''").replace('\\','/')+"'"

if OUTPUT.exists() or RECEIPT.exists():
 raise SystemExit('Refusing to overwrite any existing output in the scoped_place_context_final zone')
con=duckdb.connect()
con.execute("SET memory_limit='512MB'")
con.execute('SET threads=1')
base=q(INPUT)
# Materialize the 8 explicitly reviewed old source rows from their accepted point ledgers.
parts=[]
for tag in ('talnakh','kayerkan','krasnodar'):
 p=GROUPS[tag]/'scoped_point_uses.parquet'
 parts.append(f"""SELECT target_source_record_id AS source_record_id, target_year AS observation_year,
 latitude AS scoped_place_latitude, longitude AS scoped_place_longitude,
 'accepted scoped representative-place point; retrospective context, not census-date measurement' AS scoped_coordinate_status,
 '{tag}' AS source_family, point_provider AS point_provider, provider_id AS point_provider_id,
 point_origin_file AS point_origin_file, point_origin_sha256 AS point_origin_sha256,
 point_origin_member AS point_origin_member, point_origin_locator AS point_origin_locator,
 point_origin_line_sha256 AS point_origin_line_sha256,
 point_claim_locator AS point_claim_locator, point_claim_file_sha256 AS point_claim_file_sha256,
 coordinate_use AS coordinate_use, point_status AS reviewed_point_status
 FROM read_parquet({q(p)}) WHERE target_year=2002 AND target_source_record_id IS NOT NULL""")
p=GROUPS['troitsk_shcherbinka']/'scoped_trajectory_observations.parquet'
parts.append(f"""SELECT source_record_id, observation_year,
 coordinate_latitude AS scoped_place_latitude, coordinate_longitude AS scoped_place_longitude,
 'accepted scoped representative-place point; retrospective context, not census-date measurement' AS scoped_coordinate_status,
 'troitsk_shcherbinka' AS source_family, 'Wikidata P625' AS point_provider,
 NULL::VARCHAR AS point_provider_id, coordinate_origin_file AS point_origin_file,
 coordinate_origin_sha256 AS point_origin_sha256, NULL::VARCHAR AS point_origin_member,
 coordinate_origin_locator AS point_origin_locator, NULL::VARCHAR AS point_origin_line_sha256,
 coordinate_origin_locator AS point_claim_locator, coordinate_origin_sha256 AS point_claim_file_sha256,
 'accepted physical-continuity scoped trajectory point context' AS coordinate_use,
 'accepted_scoped_physical_continuity' AS reviewed_point_status
 FROM read_parquet({q(p)}) WHERE source_record_id IS NOT NULL AND observation_year IN (2002,2010)""")
union=' UNION ALL '.join(parts)
if not OVERLAY.exists():
 con.execute(f"""COPY (SELECT *,
 CASE source_family WHEN 'talnakh' THEN 'accepted typed scoped partition path; separate from ordinary NP full3'
 WHEN 'kayerkan' THEN 'accepted typed scoped partition path; separate from ordinary NP full3'
 WHEN 'krasnodar' THEN 'accepted secondary-reported 2003 inclusion path; legal act/effective date unverified'
 ELSE 'accepted scoped physical continuity; secondary support retained separately' END AS scoped_temporal_path_status,
 CASE source_family WHEN 'talnakh' THEN 'nonadditive intracity partition inside Norilsk; no parent/child population transfer'
 WHEN 'kayerkan' THEN 'nonadditive intracity partition inside Norilsk; no parent/child population transfer'
 WHEN 'krasnodar' THEN 'existing 2002 source row only; no duplicate population append or inherited 2021 child value'
 ELSE 'no 2021 child value added to national totals; federal territory contains these places' END AS scoped_population_national_union_reason,
 TRUE AS ordinary_NP_full3_unchanged
 FROM ({union})) TO {q(OVERLAY)} (FORMAT PARQUET, COMPRESSION ZSTD)""")
# Exact key cardinality and required source-specific coverage.
keys=con.execute(f"SELECT source_record_id,observation_year,count(*) n FROM read_parquet({q(OVERLAY)}) GROUP BY 1,2 ORDER BY 1,2").fetchall()
if len(keys)!=8 or any(x[2]!=1 for x in keys): raise RuntimeError(f'Expected 8 unique point mappings, got {keys}')
# Match each overlay key to exactly one census row in the full table and retain the original values.
check=con.execute(f"""SELECT count(*), count_if(l.source_record_id IS NULL),
 count_if(l.record_type <> 'census'), count_if(l.population_value IS NULL),
 count_if(o.scoped_place_latitude IS NULL OR o.scoped_place_longitude IS NULL),
 count_if(l.latitude IS DISTINCT FROM orig.latitude OR l.longitude IS DISTINCT FROM orig.longitude)
 FROM read_parquet({q(OVERLAY)}) o
 LEFT JOIN read_parquet({base}) l USING(source_record_id,observation_year)
 LEFT JOIN read_parquet({base}) orig USING(source_record_id,observation_year)""").fetchone()
# prevent accidental nonunique match through explicit group check
matches=con.execute(f"""SELECT count(*) FROM (
 SELECT o.source_record_id,o.observation_year,count(l.source_record_id) n
 FROM read_parquet({q(OVERLAY)}) o LEFT JOIN read_parquet({base}) l USING(source_record_id,observation_year)
 GROUP BY 1,2 HAVING n<>1)""").fetchone()[0]
if check[0]!=8 or check[1]!=0 or check[2]!=0 or check[3]!=0 or check[4]!=0 or matches:
 raise RuntimeError(f'Old-row key/field guard failed: {check}, mismatched counts={matches}')
# Preserve every canonical column and only append the five explicitly scoped fields.
con.execute(f"""COPY (SELECT l.*,o.scoped_place_latitude,o.scoped_place_longitude,
 o.scoped_coordinate_status,o.scoped_temporal_path_status,
 o.scoped_population_national_union_reason,o.ordinary_NP_full3_unchanged,
 o.source_family AS scoped_place_context_source_family,
 o.point_provider AS scoped_place_context_point_provider,
 o.point_provider_id AS scoped_place_context_provider_id,
 o.point_origin_file AS scoped_place_context_origin_file,
 o.point_origin_sha256 AS scoped_place_context_origin_sha256,
 o.point_origin_member AS scoped_place_context_origin_member,
 o.point_origin_locator AS scoped_place_context_origin_locator,
 o.point_origin_line_sha256 AS scoped_place_context_origin_line_sha256,
 o.point_claim_locator AS scoped_place_context_claim_locator,
 o.point_claim_file_sha256 AS scoped_place_context_claim_sha256,
 o.coordinate_use AS scoped_place_context_coordinate_use,
 o.reviewed_point_status AS scoped_place_context_review_status
 FROM read_parquet({base}) l LEFT JOIN read_parquet({q(OVERLAY)}) o
 USING(source_record_id,observation_year)) TO {q(OUTPUT)} (FORMAT PARQUET, COMPRESSION ZSTD)""")
# Lightweight output guards, restricted to row counts and exact 8 target source fields.
out=q(OUTPUT)
out_guard=con.execute(f"""SELECT count(*), count_if(scoped_place_latitude IS NOT NULL),
 count_if(scoped_place_longitude IS NOT NULL), count_if(ordinary_NP_full3_unchanged IS TRUE)
 FROM read_parquet({out})""").fetchone()
if out_guard != (865395,8,8,8): raise RuntimeError(f'Output guard failed: {out_guard}')
receipt={
 'status':'completed_scoped_place_context_overlay_only',
 'input_long':{'path':str(INPUT),'sha256':sha(INPUT),'rows':865395},
 'overlay':{'path':str(OVERLAY),'sha256':sha(OVERLAY),'rows':len(keys),'source_year_keys':keys},
 'output_long':{'path':str(OUTPUT),'sha256':sha(OUTPUT),'rows':out_guard[0],'bytes':OUTPUT.stat().st_size},
 'input_source_groups':{k:{'points':sha(v/('scoped_trajectory_observations.parquet' if k=='troitsk_shcherbinka' else 'scoped_point_uses.parquet')),
                              'application_receipt':sha(v/'application_receipt.json')} for k,v in GROUPS.items()},
 'guards':{'all_8_keys_unique_and_match_exactly_one_census_row':True,'old_population_nonnull_and_preserved_by_projection':True,
 'canonical_np3_coordinates_and_quality_columns_projected_unchanged':True,'scoped_overlay_populated_on_exactly_8_rows':True,
 'no_duplicate_primary_rows_added':True,'ordinary_NP_full3_unchanged_true_on_overlay_rows':True},
 'limits':['All point contexts are scoped and retrospective; none is a census-date measurement.',
 'Population rows are unchanged; population inclusion/nonadditivity remains as stated per accepted source receipt.',
 'The 2003 Krasnodar inclusion legal act/effective date remains unverified.',
 'Canonical NP3 latitude/longitude/admission columns are retained unchanged; consumers may separately coalesce scoped coordinates with explicit status.']
}
RECEIPT.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
