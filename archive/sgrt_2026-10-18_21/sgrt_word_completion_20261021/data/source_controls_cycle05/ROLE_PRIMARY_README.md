# Dated source classification, cycle05

Use `source_settlement_role_tristate_primary2021_cycle05.parquet` keyed by `id`.
`source2021_rural_role` and `source2021_urban_role` are nullable booleans;
`source2021_effective_settlement_type` and `source2021_role_evidence` describe admission.
Never implement rural as the negation of an absent urban flag. Historical-only rows have
no asserted 2021 role. A positive-population member with unknown role makes the exact
rural denominator incomplete: report its population as an uncertainty, not zero.

The original normative-only classification and receipt remain unchanged as version1.
Version2 independently reads actual official January2021 national CSV. 148043 records
match an exact native eleven-digit NP code and normalized name; 130981 records have
an explicit primary urban/rural type admitted. There are 62 actual official exceptions
to the normative suffix-range rule: primary names explicitly say рп, пгт or кп while
the suffix is101+. Actual primary row type outranks the generic normative code rule.
All62 original strong conflicts have exact code/name identities. Normalization only
casefolds, unifies ё/е and removes punctuation/spacing, with no fuzzy name matching.

Небель has a separate unique primary witness: raw native25614418001, primary25614418101,
same exact eight-digit municipality25614418 and exact name. The primary NP row is
п Небель with rural suffix101. This corrects a false city role for250 residents;
both codes remain inspectable, and neither the frozen axis nor raw source is changed.

Remaining strong conflict is д.Виноградова, one resident: raw11508000023,
January2021 official11608422114. January parent is Верхнетоемский муниципальный район;
October source parent is Верхнетоемский муниципальный округ with a different native code.
No unproved reform crosswalk or name-only identity was accepted; role remains unknown.
January2021 classifier precedes October census. Exact code/name concordance does not
prove absence of all intervening legal status changes. Unmatched dated code/name rows
remain in a separate alignment queue, not falsely declared missing census settlements.

Independent primary government law23.07.2019№518-ЗС PDFpage2 proves Балаклава and Кача
urban, two отделения Золотой Балки rural. All11 distinct source NP children sum exactly
the Balaklavsky municipality total48494; the municipal row itself stays nonadditive.
Ласпи is legally urban but absent from the census source; no population was invented.

Final roles:153374 rural,2371 urban,18117 unknown (mostly no2021 source). The only
positive observed additive2021 population with unknown role is one resident.
