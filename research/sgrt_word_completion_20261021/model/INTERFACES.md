# Model data contract

`model_inputs.json` is the exact reviewable binding of source fields. No substring-discovered source becomes a new validated feature. A missing source stays missing. New layers join on stable `id`, one row per ID; rows outside the axis may be explicitly supplied as external service providers.

The full-settlement axis may replace the default142570-point legacy axis. Required columns: `id,name,lat,lon`, with `type,region,population_2002,population_2010,population_2021` where known. Missing historical population is `NULL`, never0. `axis_kind` distinguishes ordinary settlements and external service sites/territories. Same-year additive population observations must have been deduplicated upstream.

`external_centers.parquet`: stable `id,name,lat,lon`, `axis_kind=external_service_provider`; population optional. Physical function fields may live directly on these rows or in an ID-keyed layer. Sites belonging to one settlement must not become repeated independent population observations. Provider sites are facilities, not new settled-population counts.

Transport edges: `origin_id,destination_id,travel_minutes,route_status`; `route_status` in `routed,reachable,ok` is usable. Additional `road_distance_km,graph_sha256,snap_distance_m,travel_time_model` should be retained. These are shortest-path modeled minutes, not traffic observations. Origin and destination IDs must refer to this exact node axis, including center-to-center routes. Duplicated edges with different minutes are errors unless an explicit mode/version column is selected upstream. Geodesic kilometers are never converted silently into minutes.

The preparation stage writes `nodes.parquet` and `candidate_centers.parquet`, allowing the transport worker to compute only needed destination IDs. `--stage prepare` cannot close the transport/assignment gate. Full run requires actual network travel data and writes a separate incomplete-coverage receipt when routes are missing.

Typology indicators from new layers should use explicit nullable boolean columns: `commuting_observed`, `recreation_dacha_evidence`, `ethnocultural_demographic_evidence`, `resource_shift_evidence`, `industrial_decline_evidence`, `agro_high_productivity_evidence`, `agro_decline_evidence`. Unknown and false differ. Metadata must identify source/date/unit. No ethnicity, employment or factual commuting is inferred from just a growth sign, population or name.

Primary 2021 configs: `model_inputs_2021.json` and `model_inputs_2021_inclusive.json`. First uses explicit locality linkage; second includes coordinate candidates. Both use own population2021 for mass, fixed-grid retrospective dynamics2010–2021, and dated2021 OSM sector snapshots. Outputs live in `model/output_2021_baseline/` and `model/output_2021_inclusive/`.

Systems additionally contain rural population-weighted context means/coverage and agro true fractions; municipal hectares are not summed. `word_type_hypotheses.parquet` contains complete strict truth matrices and an operational core matrix. `operational_type_candidates.parquet` is the subset with every operational core criterion TRUE and complete population pairs, always HYPOTHESIS. Causal conditions may remain unknown. `functional_leader_agreement.parquet` retains different sector leaders and their agreement with the integrated assignment; these are modeled relations, not observed flows.
