# Khorlovo three-date identity and boundary-population review

## Disposition

Recommend same_place identity links for both adjacent transitions:

- 2002 → 2010: 2002:1_TOM_01_04.xls:0:1080 → 2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:8353.
- 2010 → 2021: 2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:8353 → 2021:data_allsettlements_anon_156_v20251217.parquet:parquet:65692.

These identities are supported by exact typed name and region, unique within-year source tuples, the unique 2009 typed OKATO row 46206567 (SQL line 95491), exact 2011 GeoKLADR code 46206567000 (record 71249), and consistent points. The current 2021 record is the uniquely matching Moscow-oblast pgt Horlovo, with native OKATO 46410566000, OKTMO 46710000066 and FIAS ID e74a5d47-dbbd-4d8c-81d2-7f0f16d7dfc0. There are no Graph24 accepted identity edges among these endpoints today.

Carry the 2004 inclusion and 2019 restoration of Fosforitny as explicit historical event context. The local lineage-event note says Fosforitny was included in Horlovo in 2004, restored as a separate urban settlement in 2019, and that its 2010 population belonged to Horlovo's boundary. The event source asserts years, while valid_from/valid_to are null and the note says exact legal timing was not independently verified.

## What the population rows represent

- 2002 source row: 3,884 for pgt Horlovo, explicitly under Воскресенский район. The neighboring row is separate pgt Фосфоритный, 4,193. Both values are direct published census rows.
- Selected 2010 secondary row: 7,850 for pgt Хорлово рп on Data Sheet row 8353. It is tagged confidentiality_perturbed_within_ten / exact scope unverified. The raw selected XLS reproduces 7,850, but the official Rosstat Tom 1 Table 5 row separately publishes 7,875 (men 3,512 + women 4,363), under the Воскресенский район hierarchy. The 25-person gap means 7,850 should not be presented as the exact official census total; the selected value was not changed. The official row contains no separate 2010 Fosforitny entry, consistent with the boundary event note.
- 2021: direct selected records are Horlovo 3,714 and Fosforitny 3,883, both pgt records under Городской округ Воскресенск.

For a boundary-context comparison, the separate 2002 and 2021 source rows sum to 8,077 and 7,597, respectively, around the 2010 official-primary Horlovo boundary total of 7,875. These totals support the event interpretation but do not replace per-settlement rows or assert exact polygon equivalence. Do not treat the individual Horlovo values (3,884 → 7,850/7,875 → 3,714) as a like-for-like population trend.

## Point evidence

Graph24 already has point uses but no identity links for the three target IDs. Its 2002 and 2010 historical points are the same 2011 GeoKLADR record (55.330969, 38.807070); the 2021 accepted point is the Tochno/DaData own-locality point (55.3255923, 38.8153121). Their separation is about 0.79 km. Additional locality-level points are close: Wikidata Q4499948 0.17 km, RCSI 0.42 km, GeoNames PPL 0.80 km from the accepted 2021 point.

Nearby/other feature rows were distinguished: Wikidata Q4145612 is a municipality point; GeoNames Stantsiya Khorlovo is a railway station 1.67 km away; GeoNames also has a Tver rural homonym 318.86 km away. The point source inventory and coordinate distances are in point_sources.csv. No point source conflicts with the Horlovo locality coordinates.

## Source limits

The event note gives year-level history, not a verified legal effective date or polygon. The 2010 secondary 7,850 value remains protected/uncertain despite the exact primary Table 5 value being available separately. This review proposes identity edges only; it makes no canonical edge, point, or population changes.

## Artifacts

- population_identity_rows.csv: source rows, administrative context, and population qualification.
- point_sources.csv: available point records, feature interpretation, and distances.
- decision.json: candidate same-place edges and boundary-matched population context.
- receipt.json: input and output SHA-256 pins and row locators.
