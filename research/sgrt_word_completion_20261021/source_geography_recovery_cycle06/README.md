# Native2021 settlement coordinate source recovery: proposal only

This namespace investigates all 1,767 remaining ordinary-native2021 geography gaps: 1,614 missing coordinates and 153 existing sourcepoints rejected by the unchanged 10km road snap rule. The accepted settlement axis, routing graph/matrices and model outputs are unchanged. The final source-only proposal is `finite_source_candidate_proposal_receipt.json`:479 NP (319 A1,154 A2,6 B2),353 positive-population NP and10,593 people. The complete final gap ledger is `all1767_finite_recovery_unknown_ledger.parquet`;1,135 missing-coordinate NP/18,415 people and153 existing over10km cases remain explicit. Earlier intermediate receipts are preserved for audit and are superseded by this finite proposal.

`all1767_native2021_geography_gaps_source_frame.parquet` fixes the target universe and the actual native11 census code, published parent8, raw typed name, region and source rows. Published source parentage is taken from the accepted exact-source2021 bridge, not inferred from a modern municipal code or a nearby settlement.

## Actual historical source acquisition

`national_osm2021_stream_acquisition_receipt.json` and `boundary_dependency_stream_receipt.json` each verify every byte of the original national PBF against 2,969,339,717 bytes and SHA256 `1b7c5e9f160afa4cd5889ea1d2ecbebb6dfaaa7f67a1e53efe92c21779d920fe`. Both were streamed through libosmium; the full PBF was neither stored on disk nor loaded into RAM. Its header is 2021-01-01T21:42:03Z. That is the source snapshot date; neither object modification timestamps nor snapshot dates establish when a coordinate was measured.

The first extraction preserves all 459,207 settlement-place, administrative-boundary and native-code source objects selected by the declared inventory predicate, including complete original tags, versions, timestamps, way refs and relation membership. A completed third exact national stream found642 additional user-code-only objects, none bearing any of the1,767 target native codes. Its21 actual B source-node readbacks all have exact matching version/tags/coordinates, visible=True and deleted=False. The full-stream complement audit includes `oktmo:user`/`okato:user` objects without place/admin tags to test the all-source-code uniqueness condition. User-supplied `oktmo:user` is not an official identity authority.

The second extraction preserves actual original nodes and all way/relation dependencies needed for 155 node+boundary candidates. Four API way histories were acquired solely to find dependencies and were then checked exactly against the original national snapshot. All 155 original source boundaries cover their sole same-identity observed settlement node. The node is the only coordinate witness; no polygon centroid or synthetic settlement coordinate is created.

## Independent dated official identity

The actual primary classifier CSV published 18 January2021 supplies exact native11 names and dated native8 parent headers. Both section1 municipal units and section2 population-unit headers are preserved, together with the immediate lower-parent header, full original NP row and any explanatory former-settlement context. These are compared with the actual October2021 census parent bridge. A stable parent code is identity evidence; it does not prove unchanged polygons or a surveyed sourcepoint.

`dated_primary_and_geometry_validated_A_candidates_v2.parquet` retains all485 coded node candidate decisions. Version1 incorrectly limited parent headers to classifier section2; version2 additionally reads the actual section1 municipal-rayon records. This is a parser correction, not a change to raw source identity. Currentname/code/explicit legal subtype, lifecycle and stated position uncertainty remain explicit review gates. Missing OSM parent tags are not invented. Observed regional point-cloud envelopes are only plausibility checks, not administrative boundary tests.

B_v2 is a separate predeclared exact typed-name/parent source candidate class. It requires literal source parent/region equality to the actual published October2021 parent/region, an exact dated January parent code, a unique exact typed name in the complete census universe and a unique same-legal-type sourcepoint across the entire source inventory. An unknown source legal subtype remains a competing assertion. Generic `place=village` is not used as legal subtype. No administrative aliases or district-to-urban-okrug transformations are inferred.

## Additional primary published coordinate witnesses

The archived official GKGN catalog contains88 published regional settlement-register links, enumerated in `official_national_GKGN_NP_catalog_inventory.json`. Actual primary PDFs were acquired from official-site archived URLs for Moscow (registry15.12.2022) and Perm (28.03.2023), with full byte hashes. Their dates are later source dates, not2021 measurements. The9,586 parsed complete single-line register records retain literal coordinates, administrative attachment, registry IDs, PDF page and exact original text. Multiline records are not silently reconstructed.

The409 target-to-register assertions concern111 target NP and remain **C_review**, because name/type similarity alone does not establish the exact dated native identity or parent bridge. No closest registry coordinate is selected and no points are averaged. Of particular concern, two same-name Centralny settlements in Chusovoy have competing geocoder, OSM and GKGN assertions; retain all witnesses and the primary classifier's Nikiforovskoye/Skalninskoye explanations for independent review.

## Limits and handoff

The proposal ledger retains all1,767 targets, both recovered-source candidates and unresolved gaps. Passing a finite candidate screen is not axis adoption. All coordinate measurement dates and calibrated accuracy remain unknown. Existing153 over10km rejections are unchanged. Any later adopted coordinate family must receive independent source readback, re-snap actual geometry and recompute its affected routing rows; this namespace changes none of those results.
