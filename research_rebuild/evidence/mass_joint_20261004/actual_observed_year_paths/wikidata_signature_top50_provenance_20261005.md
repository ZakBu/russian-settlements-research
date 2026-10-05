# Wikidata 923-pair layer: provenance check for the 50 largest candidates

This read-only check evaluates whether the largest entries in the existing 923-pair signature layer can be promoted from candidates using Wikidata `P1082` references alone. It adds no identity edges, coordinates, or population values.

## Result

The 50 largest QID pairs by historical population represent 234,524 selected people in 2002 and 238,119 in 2010. None of their 100 Wikidata population claims contains a page, table-row, line, or historical district locator. The claims therefore do not independently identify the selected source row, even where a census publication is named.

For 2002, 35 claims (168,734 people) cite the general 2002 census bulletin Q126687602 without a page or row. Two claims (16,221 people) cite Q69499838 and a URL titled as a Bashkortostan 2019 estimate despite being attached to 2002 values. Thirteen claims (49,569 people) cite catalog items whose bibliography metadata was not cached. For 2010, four claims (18,061 people) cite cached census volumes Q126959207 or Q127414173, but still without a page or row; 42 claims (193,973 people) refer to catalog items with unavailable cached metadata; three (17,358 people) cite URLs without row locators; and one claim (8,691 people) has no reference.

Only three selected 2010 values among the top 50 pair IDs also have a direct reviewed Table 5 row: Q282116, Q2017643, and Q3881411, totaling 17,629 people. Their QID claims remain bibliographic rather than row-specific, and each has a separate identity or legacy-conflict hold. Four IDs with cached census-publication metadata—Q282116, Q4081691, Q4230261, and Q4333196—are the best queue for a targeted page/context lookup, not automatic admissions. For Q4333196, the cited 2002 bulletin's published scope starts with villages of 3,000 people plus district centres; the selected 2,576-person Октябрьское row is not marked as a district centre.

## Decision and limitations

No narrower automatic-admission rule is supported by citation provenance in this largest-candidate sample. Exact or near-exact population signatures, matching typed names and regions, and a current QID/code anchor remain useful candidate evidence, but the sampled references cannot establish that the historical claims describe the exact selected row. Keep the 923 pairs in candidate status and prioritize page-level source recovery for the largest cases. This is a targeted top-50 provenance audit, not a probability sample and not an accuracy estimate for all 923 pairs.

The check was performed by an independent read-only reviewer against cached QID claims, cached reference metadata, selected source-row dispositions, and direct Table 5 review records. No primary files were downloaded and no canonical ledger changed.
