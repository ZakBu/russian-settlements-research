import duckdb, hashlib, json, pathlib, datetime
from collections import defaultdict

ROOT = pathlib.Path('/workspace')
claim_p = ROOT/'settlements-work/continuation_20261004/R4/fetched_full_entity_secondary_history_20261004/fetched_p1082_claim_inventory.parquet'
bind_p = ROOT/'settlements-work/continuation_20261004/independent_history_review/review_eligible_current_QID_binding_candidates.csv'
bind_receipt = ROOT/'settlements-work/continuation_20261004/independent_history_review/receipt.json'
point_p = ROOT/'settlements-delivery/scoped-long-consolidated-20261004/accepted_point_uses.parquet'
point_receipt = ROOT/'settlements-delivery/scoped-long-consolidated-20261004/settlements_long.receipt.json'
frozen_overlay_p = ROOT/'settlements-work/continuation_20261004/root/R4/history_application_with_reviewed_supplement/reviewed_secondary_history_observations.parquet'
cand_p = ROOT/'settlements-work/continuation_20261004/R4/fetched_full_entity_secondary_history_20261004/new_claim_current_qid_binding_candidates.parquet'
claim_receipt = ROOT/'settlements-work/continuation_20261004/R4/fetched_full_entity_secondary_history_20261004/receipt.json'

out_csv=pathlib.Path('/tmp/wikidata_annual_secondary_current_points_20261005.csv')
out_receipt=pathlib.Path('/tmp/wikidata_annual_secondary_current_points_20261005_receipt.json')

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

c=duckdb.connect()
# Preserve one row per novel raw P1082 statement. Link selected current QID binding only via exact QID + selected source_record_id in the independently reviewed candidate register.
query=f"""
WITH binding AS (
  SELECT * FROM read_csv_auto('{bind_p.as_posix()}')
), candidate AS (
  SELECT * FROM read_parquet('{cand_p.as_posix()}')
), point AS (
  SELECT * FROM read_parquet('{point_p.as_posix()}')
  WHERE target_year='2021.0' OR target_year='2021'
), novel AS (
  SELECT *, try_cast(observed_year AS INTEGER) AS year,
         try_cast(population_value_numeric AS DOUBLE) AS population_value
  FROM read_parquet('{claim_p.as_posix()}')
  WHERE claim_snapshot_status='new_subject_GUID_candidate_not_in_frozen_history_overlay'
    AND date_status='actual_year_precision_only'
    AND date_precision='9'
    AND try_cast(observed_year AS INTEGER) NOT IN (2002,2010,2021)
), overlay AS (
  SELECT current_wikidata_qid AS wikidata_qid, try_cast(observation_year AS INTEGER) AS year,
         count(*) AS overlay_claim_count,
         count(DISTINCT try_cast(population_value AS DOUBLE)) AS overlay_distinct_values,
         min(try_cast(population_value AS DOUBLE)) AS overlay_min_value,
         max(try_cast(population_value AS DOUBLE)) AS overlay_max_value
  FROM read_parquet('{frozen_overlay_p.as_posix()}')
  WHERE record_type='secondary_population_observation'
  GROUP BY 1,2
), conflicts AS (
  SELECT wikidata_qid, year,
         count(DISTINCT population_value) AS distinct_values,
         count(*) AS claim_count
  FROM novel GROUP BY 1,2
)
SELECT
  n.wikidata_qid,
  n.p1082_statement_guid_raw AS statement_guid,
  n.year AS p585_year,
  n.date_value_literal,
  n.date_precision,
  n.date_status,
  n.population_value,
  n.population_value_raw AS population_value_raw,
  n.population_quantity_unit_raw,
  n.quantity_status,
  n.rank_raw,
  n.p585_qualifiers_json,
  n.raw_statement_json,
  n.claim_snapshot_status,
  n.current_binding_status AS binding_status_snapshot_at_claim_packet_build_not_final_review,
  n.current_source_record_id_candidate AS source_record_id,
  b.settlement_name AS current_selected_name,
  b.settlement_type AS current_selected_type,
  b.region_raw AS current_selected_region,
  b.source_oktmo_exact_digits AS current_selected_native_oktmo,
  b.exact_source_oktmo_p764 AS accepted_binding_exact_p764,
  b.current_source_name_exact AS accepted_binding_name_match,
  b.current_source_type_exact AS accepted_binding_type_match,
  b.current_source_region_exact AS accepted_binding_region_match,
  b.no_contradictory_admin_region AS accepted_binding_no_admin_region_contradiction,
  b.physical_p31_lineage AS accepted_binding_physical_p31_lineage,
  b.selected_OKTMO_matches_exact_WIDE_code AS selected_native_code_matches_WIDE,
  b.source_code_unique_qid AS source_code_unique_qid,
  b.qid_unique_current_source_code AS qid_unique_current_source_code,
  b.native_competition_clear AS native_competition_clear,
  'present_in_independently_reviewed_current_QID_binding_register' AS current_binding_review_status,
  p.latitude AS current_representative_latitude,
  p.longitude AS current_representative_longitude,
  p.target_year AS point_target_year,
  p.coordinate_source AS current_point_source,
  p.coordinate_source_record_id,
  p.coordinate_provider,
  p.coordinate_quality,
  p.coordinate_admission_status,
  (coalesce(p.admission_allowed, false) OR p.coordinate_admission_status IN ('reviewed_extension_rule_accepted','reviewed_rule_accepted')) AS current_point_admission_allowed,
  p.coordinate_measurement_date_unknown AS current_point_measurement_date_unknown,
  p.direct_historical_coordinate_measurement,
  p.coordinate_source_date,
  p.coordinate_source_file,
  p.coordinate_source_sha256,
  p.coordinate_source_locator,
  p.point_origin_file,
  p.point_origin_sha256,
  p.point_origin_locator,
  p.point_origin_kind,
  p.review_id AS point_review_id,
  p.coordinate_application_review_sha256 AS point_review_sha256,
  coalesce(p.boundary_comparability_asserted, false) AS point_boundary_comparability_asserted,
  cf.claim_count AS claims_for_qid_year,
  coalesce(o.overlay_claim_count,0) AS frozen_overlay_claims_for_qid_year,
  coalesce(o.overlay_distinct_values,0) AS frozen_overlay_distinct_values_for_qid_year,
  (coalesce(o.overlay_claim_count,0)>0 AND (coalesce(o.overlay_distinct_values,0)>1 OR o.overlay_min_value <> try_cast(n.population_value_numeric AS DOUBLE) OR o.overlay_max_value <> try_cast(n.population_value_numeric AS DOUBLE))) AS conflict_vs_frozen_overlay,
  cf.distinct_values AS distinct_values_for_qid_year,
  (cf.distinct_values > 1) AS qid_year_value_conflict,
  json_array_length(json_extract(n.raw_statement_json, '$.references')) AS references_count,
  'secondary_Wikidata_assertion' AS display_value_role,
  false AS primary_census_evidence,
  false AS historical_coordinate,
  'current representative point only; not a historical measurement or coordinate' AS coordinate_interpretation,
  n.entity_batch_file_verified_path,
  n.entity_batch_sha256,
  n.entity_batch_hash_verified,
  n.entity_retrieved_at_utc,
  n.raw_entity_lastrevid,
  n.raw_entity_modified
FROM novel n
JOIN binding b ON b.wikidata_qid=n.wikidata_qid
  AND b.source_record_id=n.current_source_record_id_candidate
JOIN candidate c ON c.wikidata_qid=n.wikidata_qid
  AND c.source_record_id=n.current_source_record_id_candidate
JOIN conflicts cf ON cf.wikidata_qid=n.wikidata_qid AND cf.year=n.year
LEFT JOIN point p ON p.target_source_record_id=b.source_record_id
LEFT JOIN overlay o ON o.wikidata_qid=n.wikidata_qid AND o.year=n.year
ORDER BY n.year, n.wikidata_qid, n.p1082_statement_guid_raw
"""
df=c.execute(query).df()
# Check the intended complete 17-QID/49-claim link and point one-to-one cardinality.
assert len(df)==49, f'expected 49 rows, got {len(df)}'
assert df.wikidata_qid.nunique()==17, f'expected 17 qids, got {df.wikidata_qid.nunique()}'
assert df.source_record_id.nunique()==17, f'expected 17 selected current records, got {df.source_record_id.nunique()}'
assert df.current_representative_latitude.notna().all() and df.current_representative_longitude.notna().all(), 'missing current representative point'
assert df.current_point_admission_allowed.fillna(False).all(), 'point row not admitted'
assert df.accepted_binding_exact_p764.fillna(False).all() and df.accepted_binding_physical_p31_lineage.fillna(False).all() and df.accepted_binding_name_match.fillna(False).all() and df.accepted_binding_type_match.fillna(False).all() and df.accepted_binding_region_match.fillna(False).all() and df.selected_native_code_matches_WIDE.fillna(False).all() and df.source_code_unique_qid.fillna(False).all() and df.qid_unique_current_source_code.fillna(False).all() and df.native_competition_clear.fillna(False).all() and df.accepted_binding_no_admin_region_contradiction.fillna(False).all(), 'reviewed binding gate failed'
assert df.groupby('wikidata_qid').apply(lambda x: len(x[['current_representative_latitude','current_representative_longitude']].drop_duplicates())==1).all(), 'multiple current points per QID'
assert not df.qid_year_value_conflict.any(), 'qid/year conflict found'
assert not df.conflict_vs_frozen_overlay.any(), 'new claim overlaps/conflicts with frozen overlay'
assert df[['wikidata_qid','p585_year']].drop_duplicates().shape[0] == 49, 'duplicate qid/year claims detected'
# Embed references count as explicit field while raw_statement_json retains full refs and source statement.
df.to_csv(out_csv,index=False)

annual=[]
for year,g in df.groupby('p585_year',sort=True):
    annual.append({
      'year':int(year), 'claims':int(len(g)), 'unique_qids':int(g.wikidata_qid.nunique()),
      'unique_qid_years':int(g[['wikidata_qid','p585_year']].drop_duplicates().shape[0]),
      'secondary_population_sum_once_per_qid_year':int(g[['wikidata_qid','p585_year','population_value']].drop_duplicates()['population_value'].sum()),
      'conflict_qid_years':int(g[['wikidata_qid','p585_year','distinct_values_for_qid_year']].drop_duplicates()['distinct_values_for_qid_year'].gt(1).sum()),
      'claims_with_references':int(g.references_count.fillna(0).gt(0).sum()),
      'qids_with_current_representative_point':int(g.loc[g.current_point_admission_allowed.fillna(False),'wikidata_qid'].nunique())
    })

point_counts=df.groupby('wikidata_qid').agg(point_uses=('current_point_admission_allowed','count'), distinct_coords=('current_representative_latitude', lambda s: len(set(zip(s,df.loc[s.index,'current_representative_longitude'])))), point_sources=('current_point_source',lambda s: sorted(set(s.dropna())))).reset_index()
inputs=[claim_p,bind_p,bind_receipt,point_p,point_receipt,cand_p,claim_receipt,frozen_overlay_p]
receipt={
 'status':'read_only_secondary_Wikidata_annual_claims_joined_to_accepted_current_bindings_and_current_representative_points',
 'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'output_csv':str(out_csv),
 'output_csv_sha256':sha(out_csv),
 'scope':{
   'selection':'novel P1082 statement GUIDs vs frozen overlay; year-precision P585 only; excludes 2002/2010/2021; exact QID + source_record_id joined to independently reviewed current 2021 QID binding register and accepted 2021 point use.',
   'display_role':'secondary Wikidata population assertions with current representative coordinates. Coordinates are current-representative only; they are not historical coordinates, not transferred to the P585 year, and not primary census evidence.',
   'current_binding_review':'17 QID/source rows are present in the independently reviewed eligible-current-QID register; this supports current-source association only.',
   'identity_and_scope':'no historical identity, historical population scope, historical boundary comparability, or primary census value is asserted.',
   'claim_provenance':'CSV retains raw statement JSON including references, statement GUID, P585 qualifiers, rank, entity batch file/hash, retrieval metadata.'
 },
 'counts':{
   'claims':int(len(df)), 'unique_qids':int(df.wikidata_qid.nunique()), 'unique_current_selected_rows':int(df.source_record_id.nunique()),
   'unique_qid_years':int(df[['wikidata_qid','p585_year']].drop_duplicates().shape[0]),
   'claims_with_current_accepted_point':int(df.current_point_admission_allowed.fillna(False).sum()),
   'qids_with_current_accepted_point':int(df.loc[df.current_point_admission_allowed.fillna(False),'wikidata_qid'].nunique()),
   'qids_without_point':int(df.loc[df.current_representative_latitude.isna(),'wikidata_qid'].nunique()),
   'unique_point_pairs':int(len(set(zip(df.current_representative_latitude,df.current_representative_longitude)))),
   'qids_with_multiple_selected_point_coordinate_pairs':int(point_counts.distinct_coords.gt(1).sum()),
   'claims_with_references':int(df.references_count.fillna(0).gt(0).sum()),
   'claims_without_references':int(df.references_count.fillna(0).eq(0).sum()),
   'conflicting_qid_years':int(df[['wikidata_qid','p585_year','distinct_values_for_qid_year']].drop_duplicates()['distinct_values_for_qid_year'].gt(1).sum()),
   'claims_overlapping_frozen_overlay_qid_year':int(df.frozen_overlay_claims_for_qid_year.gt(0).sum()),
   'claims_conflicting_with_frozen_overlay':int(df.conflict_vs_frozen_overlay.sum()),
   'secondary_population_sum_once_per_qid_year':int(df[['wikidata_qid','p585_year','population_value']].drop_duplicates()['population_value'].sum()),
   'primary_census_evidence_admitted':False,'historical_coordinates_asserted':False
 },
 'annual_summary':annual,
 'point_source_counts':{str(k):int(v) for k,v in df.groupby('current_point_source').size().to_dict().items()},
 'point_admission_counts':{str(k):int(v) for k,v in df.groupby('coordinate_admission_status').size().to_dict().items()},
 'input_sha256':{str(p):sha(p) for p in inputs},
 'accepted_current_point_row_provenance':{
   'coordinate_source_sha256_values':sorted(df.coordinate_source_sha256.dropna().astype(str).unique().tolist()),
   'point_origin_sha256_values':sorted(df.point_origin_sha256.dropna().astype(str).unique().tolist()),
   'point_review_sha256_values':sorted(df.point_review_sha256.dropna().astype(str).unique().tolist()),
   'entity_batch_source_hashes':sorted(df.entity_batch_sha256.dropna().astype(str).unique().tolist()),
   'entity_batch_hash_verified_values':sorted(df.entity_batch_hash_verified.astype(str).unique().tolist())
 },
 'risks_and_limits':[
  'P1082 values are secondary assertions attached to the current QID, with source-specific historical scope not adjudicated here.',
  'P585 has year-only precision; display as year labels and do not synthesize a census date.',
  'Current accepted point is a representative location for the selected current place. Its use alongside historical claims is visual context only, never a historical coordinate or a same-place trajectory assertion.',
  'Boundary, population grain and historical entity continuity require separate evidence.'
 ]
}
out_receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'csv':str(out_csv),'receipt':str(out_receipt),'counts':receipt['counts'],'annual_summary':annual,'point_sources':receipt['point_source_counts'],'sha_csv':receipt['output_csv_sha256']},ensure_ascii=False,indent=2))
