# Krasnodar exact-name triad review (Graph20)

Read-only review of Джигинка, Юровка, Гай-Кодзор, and Сукко. Ленина and Цибанобалка are excluded. Inputs, exact source locators, row-level competitor list, edge/point dispositions, and SHA-256 pins are in `review.json` and the adjacent CSV files.

## Findings

- All four current 2021 IDs are present in the configured working residual (one each). None of the eight adjacent 2002→2010 or 2010→2021 endpoint pairs is already in the active Graph20 identity edge ledger.
- I recommend the four 2002→2010 links as identity-edge candidates. Name and settlement type match exactly; the 2002 records and 2010 sources are both in Anapa rayon; the 2009 OKATO classifier has a unique named/type-matched Anapa locality row for each. Three 2010 values are directly supported by official Rosstat Table 5 page 76 (printed page 75): Джигинка 4361, Юровка 3537, Сукко 3156. The earlier Krasnodar XLS values for those same 2010 rows differ (4363, 3538, 3159); Table 5 is the selected primary value in the source inventory. For Гай-Кодзор, the cited regional census XLS row has 2971 and is tagged confidentiality-perturbed; it supports row identity only, with the perturbation preserved.
- Hold the four 2010→2021 links pending independent 2021 locality point / identity corroboration. The current DaData/Tochno raw point row carries the same FIAS ID `eeb7a0a7-3bbf-4f00-8a03-a7eabc257bed`, helper OKATO/OKTMO values, and coordinate `44.8948984, 37.3162896` for each target. The exact coordinate is shared by 40 Krasnodar rows, including the Anapa city row, while each 2021 native `oktmo` is a distinct settlement code. That is evidence the coordinate and helper identifiers are city-level provider bindings, not the village points. The historical district changes from Anapa rayon to Anapa urban okrug. No boundary or population comparability is claimed.
- The existing Graph20 point ledger contains reviewed GeoKLADR 2011 points for Джигинка, Юровка, and Сукко on the 2002 and T5 2010 endpoints. Retain these as historical source-point uses only; their dates are 2011 source coordinates, not census-date observations. The classifier and GeoKLADR name/type/code record for Гай-Кодзор exists, but its DBF coordinates (`44.268617, 40.878162`, record 1660) are severely displaced from the Anapa locality corridor (~290.5 km from the shared current provider point); hold that point. Hold all four current DaData points. No new point use is admitted by this review.

These are review recommendations only. No canonical graph, point, or population files were modified. `edge_dispositions.csv` records each adjacent edge separately, including active graph count and reason. `point_dispositions.csv` separates old source points from the four current provider points and the rejected Гай-Кодзор historical coordinate.

## Files

- `review.json`: summary and source pins.
- `selected_triads.csv`: literal selected observation metadata for the requested endpoints.
- `same_name_competitors.csv`: all selected same-name Krasnodar rows, including same-year duplicates/homonyms (if any).
- `edge_dispositions.csv`: per-edge candidate/hold outcomes.
- `point_dispositions.csv`: per-point outcomes and origin locators.
- `residual_presence.csv`: exact current residual check.
