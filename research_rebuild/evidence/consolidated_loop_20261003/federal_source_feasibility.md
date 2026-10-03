# Federal-city atomic scope feasibility

Status: bounded source-only review; no population selection, geometry admission, identity change, or Git change. The complete city/year matrix is in `city_year_inventory.csv`.

## Finding

The present 2021 subject aggregates cannot yet be replaced by a core-only physical-settlement population for Moscow, Saint Petersburg, or Sevastopol. The official Table 5 does support 32 additive named urban-settlement observations: 29 Saint Petersburg places (822,633) and three Sevastopol places (56,010). Kronstadt’s 44,399 line remains held because it combines a district and city. Moscow’s 293 locality values (644,544) are secondary and not individually verified. These rows can be retained at their published grain while the federal-city totals and municipal/district/rural rows remain nonpoint aggregate controls.

The clearest source-native core count is historical Moscow 2002: Table 4 row 2155 `г. Москва` = 10,126,424 is indented beneath row 2154, `г. Москва и подчиненные его администрации населенные пункты - городское население` = 10,382,754. That parent/child hierarchy makes the 2002 row a distinct physical-city count candidate. It does not settle 2010 or 2021 scope or cross-year comparability.

Table 1.4 publishes 2010 Moscow (11,503,501) and Saint Petersburg (4,879,566), each equal to its federal-subject total, but does not say these values exclude other settlements inside subject territory. The 2002 Saint Petersburg value (4,661,219) also equals the subject control. Keep these as city-labeled values with unresolved city-versus-subject scope. Sevastopol has no Russian 2002/2010 census observation because it is outside the Russian census territorial scope in those years; do not encode zero or a failed match.

## What the 2021 hierarchies show

Moscow’s 13,010,112 root is arithmetically decomposed into 12,365,568 across 125 municipal units and 644,544 in 293 secondary locality values. That closure mixes administrative rows and secondary figures, and does not define the pre-2012 physical core boundary. Saint Petersburg’s 5,601,911 root closes with 29 approved named NP rows (822,633), the held Kronstadt composite (44,399), and 81 municipal units (4,734,879); those 81 units are not proved coextensive with a single physical place. Sevastopol’s 547,820 root closes as 56,010 in three named urban places, 449,467 in three urban-only municipal-district rows, and 42,343 rural aggregate. The 449,467 is only a candidate subtotal until primary boundary evidence establishes the district/core relationship.

The 2021 Table 5 title reports urban places and rural settlements from 3,000 people. The presence of that threshold and aggregate municipal rows means source table closure alone cannot establish an exhaustive child-level physical-NP partition.

## Minimal path to a complete replacement

Keep each federal subject total as a nonadditive control. Add direct, approved named physical-NP counts only at their published grain. Keep municipal, district, rural, unreported, and unresolved territory as population-bearing aggregate holds without coordinates. Do not assign a residual or use a municipal centre point.

To add the missing physical core, Moscow needs a Rosstat census-date count or lower-level census counts with an authoritative boundary crosswalk that distinguishes the pre-2012 core from annexed territory. Saint Petersburg needs a dated official city/satellite register or map (including Kronstadt) and a direct core count or census-unit crosswalk. Sevastopol needs a primary boundary/map proving whether the three urban-only districts are a disjoint, exhaustive core partition excluding Balaklava, Inkerman, and Kacha, or a direct physical-core census tabulation. No such exact census-date boundary/crosswalk locator was found in the existing cached source inventories. The 2025 yearbook root request was reported as HTTP 503; no retry was made.

The task-provided theoretical point ceilings remain 86.982221% for 2021 and 96.780981% for 2002. Current sources do not support lifting the aggregate-scope blocker to reach 99.9% without guessing.

## Hash-pinned evidence

See `inventory.json` for the source hashes, exact locators, and per-year entries. Key pins: official 2021 Table 5 SHA `0b232b3d2ab5daa231568acc719ac6fda4fb0979a01a0da6bacc69be6f252474`; the 32-row grain review SHA `fcaa8194eb41d2d2a65d1d14b672f8f0f9480d2395633d52e739a3a0d488f012`; 2002 Table 4 SHA `745a24599719c877a8ddf015aadf22d3cb859444819a32f8197ae525d91483f3`; 2010 Tom 11 PDF SHA `db2528e6db3c6089351bd09d253c9dfa607e2f2dff6cc45d1174fb21fa96d500`. The 2010 official HTTPS URL returned 503 on the existing bounded TLS check; cached bytes were used without retry.
