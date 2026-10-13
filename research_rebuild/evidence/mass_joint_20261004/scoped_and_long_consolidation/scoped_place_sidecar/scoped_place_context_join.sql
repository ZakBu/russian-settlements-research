-- Bounded append contract for the 8 accepted old-row scoped point/status cases.
-- Run against the 865395-row long input named in application_receipt.json.
-- This only appends scoped_* columns; it does not replace canonical NP3 columns.
SELECT l.*,
       o.scoped_place_latitude,
       o.scoped_place_longitude,
       o.scoped_coordinate_status,
       o.scoped_temporal_path_status,
       o.scoped_population_national_union_reason,
       o.ordinary_NP_full3_unchanged,
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
FROM long_table l
LEFT JOIN accepted_old_scoped_place_context o
USING (source_record_id, observation_year);
-- Guard before materializing: overlay has 8 unique key pairs; each matches exactly
-- one existing census row; population_value and all canonical coordinate/admission
-- fields are selected directly from l. No observation rows are added.
