# North handoff, first bounded triage

This packet is a source-year triage for the exact 18-row north handoff roster. `roster_dispositions_v1.csv` preserves all roster values and records candidate, hold, and unknown-year states. The field `accepted_identity_edge_delta` is false for every row: no new identity edges are admitted by this triage alone. In particular, it does not award a point or population gain.

Strong 3-census candidates to promote after exact row-level review: Voykova; Naiste; Lahkolampi; Pechenga railway object; Kabozha railway object; Novopisovo PGT; Komsomolsky Oktyabrsky; Starorussky Dubovitsy. These are grouped across six northern regions. Preserve all native values and quality tags; secondary population discrepancies are not substitutions.

Concrete holds: Krasny Oktyabr same-name/county ambiguity; Kryuki2 2002 component versus later administrative combination; Vladimirsky Lager historical composite municipal totals; Hiidenselga missing historical row binding; Chalna-1’s 2002 individual source scope. No value is set to zero. The distinct Pechenga PGT and Moshenskoy Kabozha village are explicit rivals and cannot be joined to the railway records.

`source_file_integrity_pins.csv` hashes the staged source files and authoritative roster/residual list. Those hashes establish byte identity only; they do not prove row interpretation. The use of the `selected_observations.parquet` and stage68 accepted point snapshot during triage was narrow-column and exact-UID only; no State.load or pipeline run was performed.


## v2 bounded positive batch

Eight identity trajectories have been promoted to `accepted_identity_edge_delta.csv`: 16 edges across Vladimir, Karelia, Murmansk, Novgorod, and Ivanovo (five of the six regions represented). All 18 target UIDs remain individually dispositioned in `roster_dispositions_v1.csv`; the eight chains account for 14 of the 18 roster UIDs only if supplemental below-threshold endpoints are included, while all remaining named targets are explicit holds. There are 6 old/current row point uses in `accepted_point_use_delta.csv`: only records lacking an accepted own point use the accepted 2021 carrier; existing accepted point rows were not duplicated. Point use is spatial-only and makes no census-day/boundary claim. Native populations and protected quality states stay unchanged.

The remaining source-specific questions are: (1) Krasny Oktyabr PGT: competing same-name PGT/county branches; (2) Kryuki2: composite 2002 source and later administrative combination; (3) Vladimirsky Lager: historical composite municipal publications; (4) Hiidenselga: exact 2002/2010 source-row and county route; (5) Chalna-1: 2002 individual statistical scope under Petrozavodsk-15. They are held as unknown, not zero.
