# Source inventory and use conditions

Conditions below summarize the working project's source register and documentation as reviewed on 2026-09-29. They are provenance notes, not legal opinions. The private archive intentionally has no blanket license.

| Source family | Role in the project | Recorded terms/status | Release handling |
|---|---|---|---|
| Rosstat 2002, 2010 and 2021 census publications | Population observations and official controls | Official published tables; retain publication, table, page/row and source URL | Preserve within the private baseline; cite table-level provenance |
| Lingvarium 2002/2010/2021 regional workbooks | Settlement-level extracts and comparison data | Catalog/mirror; redistribution license is not stated in the reviewed source register | Private research baseline only pending terms review; do not publicly redistribute complete workbooks or derived full extracts |
| Tochno / «Если быть точным», 2021 settlements | Population, OKTMO and DaData-derived coordinates | Source register records CC BY 4.0 | Preserve attribution and source version; do not infer that this license covers other merged sources |
| Wikidata | Identifiers, claims and coordinate/population comparisons | CC0 | Preserve entity/property and statement provenance |
| Russian Wikipedia | Articles, regional modules and settlement lists | CC BY-SA per source register/site terms | Keep revision IDs/permanent links and required attribution; review share-alike implications before distributing extracted corpora |
| Historical OKATO / GeoKLADR and candidate coordinate sources | Identifier and coordinate evidence | Source-specific terms vary; source register includes GIS-Lab and a CC BY-NC-SA coordinate mirror | Preserve source-specific terms; no blanket permission inferred; keep as candidate evidence where not admitted |
| Rosstat municipal indicators / FIAS-GAR | Administrative context | Official publication/register; object levels and validity dates differ | Do not expand municipal values to settlements or treat address validity as a legal settlement event |

The existing project has no root `LICENSE` file. The owner made the repository public on 2026-10-02; older manifests retain their original visibility as historical metadata. Public visibility does not assign a common license to the combined data. Source-specific attribution and redistribution conditions remain applicable to any new artifact.

## Added context source on 2026-10-02

GeoBoundaries gbOpen ADM1 release `9469f09` for RUS and UKR supplies a modern
physical-region contradiction screen. The source identifies its geometries as
OpenStreetMap/Wambacher, boundary year represented 2017, under Open Data Commons
Open Database License 1.0. Metadata, exact URLs and SHA-256 receipts are in
`research_rebuild/evidence/discovery/modern_region_point_screen_20261002`.
The source and its derivative diagnostic layer retain these distinct conditions;
no common merged-data license is assigned. RUS uses the simplified geometry,
so border-near points remain uncertain. Crimea and Sevastopol are mapped to the
explicit UKR geometry codes for physical context, independently of the recorded
Russian census-2021 territorial scope. This source neither proves historical
settlement boundaries nor converts territorial totals into settlement points.
