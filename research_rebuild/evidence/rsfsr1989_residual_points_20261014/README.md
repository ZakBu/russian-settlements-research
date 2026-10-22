# Primary 1989 residual identity and ownpoint batch

Final handoff: `combined_reviewed_primary_delta.parquet` (23 rows, 157,266 primary persons). These are **not 157,266 additional covered persons**: 22 target roots already occur in selected 1989 or its overlapping alternatives. Only Ташла (5,585 persons) is a previously unrepresented target root. Root integration must apply source preference/deduplication and keep alternatives rather than sum them.

Residual is an exact primary source_record_id anti-join against selected source IDs and overlapping alternative IDs, saved at `/workspace/shared/rsfsr1989_residual_points/residual.parquet`. It has 192 rows /745,837 persons. Primary values, locators and hashes are preserved.

Seven urban former-name transitions have explicit published name/status evidence in `published_alias_evidence.json` and `review.json`. Sixteen rural identities use the primary source's explicit rural district-center class (table title), the current page's explicit administrative-center statement and district-qualified core root. Proximity proposes the root; the published district-center identity is required separately. Near conflicting roots remain held. Rural excerpts and blocked routes are in `rural_review.json`.

Coordinates are independent **own locality infobox coordinates**, not inherited parent centers. Cached HTML origins live in the shared directory; URL, hash and locator are retained in every delta row. Reusing a modern locality point for1989 is explicitly continuity inference; boundaries remain unknown. No provider identifier binding is asserted.

Darovskoye, Ob'yachevo and Beltyrsky spelling cases remain held because the fetched page does not explicitly document the source spelling; Kumylzhensky requires explicit name evidence. Mamontovo is held and Pyt-Yakh city point was not substituted.

`solntsevo1979_separate_candidate.parquet` preserves the primary1979 count61,153 and published1984 absorption evidence. The downloaded modern Solntsevo district point is held as a different object level pending a historical-city ownpoint route.

Scripts: `build.py` stages published urban aliases; `review.py` admits the seven explicit transitions; `rural.py` produces the rural reviewed batch. Combined output is the concatenation of both, annotated by root representation against frozen selected+alternatives. `receipt.json` pins frozen input bytes and final output hash. No frozen primary, core, integration, or Git files were changed.
