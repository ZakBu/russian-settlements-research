# Secondary annual Wikidata values with current representative point context

This separate 49-row display export joins each new, year-precision P1082 claim (1859–2025, excluding census years) to its independently reviewed current QID↔selected 2021 row binding and the accepted current representative point for that row. The CSV retains each raw statement, GUID, P585, rank, references, source entity batch hash, selected-row binding checks and point provenance.

It contains 49 claims for 17 QIDs and 49 distinct QID/year pairs. 48 claims have references; one has none. There are no conflicting QID/year values and no overlap with the frozen annual overlay. The 45,346 sum is only a sum of these distinct QID/year assertions, not a national total. Every claim is secondary Wikidata population data.

Coordinates in this file are **current representative point context** only. They are not measurements in the P585 year, are not transferred as historical coordinates, do not establish historical continuity or boundary comparability, and do not count toward census-year coordinate or linkage coverage. Display year-only dates at year precision. Do not turn claims into exact census observations.

The output reuses already accepted current point uses and does not add or alter a point, identity edge, population value, or census record. The receipt gives exact inputs and SHA-256 values. `build_current_point_context.py` is the read-only join used in the working environment; compare its input hashes with the receipt before reuse.
