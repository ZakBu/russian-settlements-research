# Three Moscow Oblast urban-merger series — completeness assessment

## Decision

No complete merger-group series is emitted. All three groups remain candidate-only and on hold because the available materials do not establish the full physical urban constituent roster for the 2002/2010 counts and tie that roster to the final 2021 city extent. The package does not sum component populations, use a municipal-total value, impute population, assert unchanged borders, or add point coordinates.

`candidate_census_observations.csv` lists the exact selected census rows and raw locators that motivate each review. These are component observations only; row presence does not prove membership in a future city. `group_completeness_decisions.csv` records the group-specific hold. No “group total” field is produced.

## Group decisions

| Group | Candidate 2002 urban rows | Candidate 2010 urban rows | Direct 2021 city row | Status |
|---|---|---|---|---|
| Balashikha / Zheleznodorozhny | Balashikha, Zheleznodorozhny, plus Nikolsko-Arkhangelsky and Saltykovka as possible earlier constituents | Balashikha, Zheleznodorozhny | Balashikha | Hold: the two extra 2002 urban-type rows do not appear separately in the 2010 candidate roster, and no verified legal record maps their scope into Balashikha. |
| Podolsk / Klimovsk / Lvovskiy | Podolsk, Klimovsk, Lvovskiy | Podolsk, Klimovsk, Lvovskiy | Podolsk | Hold: Lvovskiy remains a separate 2010 pgt row; the actual 103/2015 law text and boundary schedule are not in the source packet, so its inclusion in the 2021 physical city row is unproven. |
| Korolev / Yubileiny | Korolev, Yubileiny | Korolev, Yubileiny | Korolev | Hold: the two-row census roster is plausible, but the accepted event references mark the legal acts independently unverified; the full law and boundary attachment were not recovered. |

The selected 2021 city rows are direct city observations, not municipal totals: Balashikha 520,962; Podolsk 314,934; Korolev 228,095. Their presence does not establish a legally complete historical constituent list. The 2021 “Железнодорожный” row with type `посёлок` and its 2002/2010 namesake are separate homonym controls, not the former city.

## Source review

The accepted event package records the three successor relationships and law numbers, but its own guardrails say `legal_acts_independently_verified=false`, `population_boundary_comparability=unknown`, and no child count or parent transfer. The older Zheleznodorozhny review reaches the same scope limit: the cached third-party mirror of 209/2014-ОЗ concerns administrative-territorial units and does not prove settlement-level population inclusion.

I checked the cached legal material first, then fetched only the three official Duma URLs already cited by the accepted event manifest. Their bytes did not contain the corresponding statutes: the 209/2014 URL returned the Duma 2014 annual activity overview; the 103/2015 URL returned the Duma 2015 annual activity overview; the 53/54 URL returned a 12-page Duma meeting/municipal material PDF. The first two summarize the laws but contain no complete settlement roster or physical-city boundary schedule; the third likewise does not provide a complete law/annex. Their paths and SHA-256 values are in `legal_source_inventory.json`; the PDFs are retained under `legal_sources/` as retrieval evidence, not cited as the acts themselves.

Official 2002 and 2010 census sources establish the candidate row values and locators. The source rows are in `candidate_census_observations.csv`, with local source-file hashes. They do not on their own establish legal membership in the successor city's physical boundary. The previous accepted event package remains a historic-place context display; this assessment does not alter it.

## Reproducibility and limits

Run `PYTHONDONTWRITEBYTECODE=1 python research_rebuild/evidence/complete_urban_merger_series_20261007/build_candidate_assessment.py` from the repository root. `source_manifest.json` pins selected data, accepted event inputs, local census files, downloaded Duma PDF bytes, and output hashes.

A complete series can be reconsidered after receiving the authentic acts and applicable maps or official urban-settlement inclusion tables for each event, plus a dated crosswalk proving which historical physical urban constituents correspond to each 2021 physical city row. Until then, summing only the named successor/predecessor rows would be a partial group estimate, so none is published here.
