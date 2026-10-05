# Graph29: two historical point uses for Ожерелье

Graph29 applies one independently reviewed GeoKLADR 2011 representative point to the exact selected 2002 and 2010 census rows for Ожерелье. It adds two point uses and no identity edges. The exact 2009 OKATO `46220504` → 2011 GeoKLADR `46220504000` bridge is unique in its source records; the named city record is DBF row 72,730 (byte offset 28,728,660), coordinate 54.803036, 38.273946.

The two selected populations remain 11,113 (2002) and 10,469 (2010); they are not changed by this point application. A previously accepted direct 2002–2010 same-place edge already connects the rows. No 2021/Kashira edge, population comparability, boundary comparability, or census-date coordinate measurement is asserted. The 2011 edition/update field is not a coordinate measurement date.

The raw source replay and independent review are encoded in `application_receipt.json` and the pinned application script. The full accepted point ledger remains in the working data volume; its new SHA-256 is recorded in the receipt. The two point targets were absent from the prior ledger, and no competing point or same-year collision was found.

## Coverage readback

Direct selected-additive coordinate coverage rises by 11,113 people in 2002 and 10,469 in 2010. The separate frozen-residual measure “accepted point + a same-place component containing at least two actually observed census years” does not change: the Graph29 residual qualifying rows are byte-identical to Graph28 (`02e56bc738e9fb2fa88bd8149235144eb10bf32b2845107baa5053fffd7d6509`). This should be reported as no marginal change on that specific residual axis, not as no coordinate gain.

The revised metric receipt is `coverage_graph29_corrected.json`. It retains the same residual population totals as Graph28: 97.698317% / 98.159192% / 99.158829% of official controls for 2002 / 2010 / 2021, with 1,889,611 / 1,201,149 / 0 people to reach 99%. This is not the strict full 2002→2010→2021 chain, which remains 86.165442% / 85.659797% / 83.503575%.

## Reproduction

Run `research_rebuild/mass_linkage/apply_graph29_ozherele_historical_points_20261005.py` against the pinned selected layer, Graph28 ledgers and raw sources. Then run `research_rebuild/mass_linkage/measure_actual_observed_year_path_coverage_v2_20261005.py` with `config_graph29.json` and the frozen Graph24 residual to reproduce the broad residual-axis receipt. The minimal config pins hashes for the exact selected, identity, point, residual and scope-baseline inputs. National working Parquet inputs are not copied into Git.
