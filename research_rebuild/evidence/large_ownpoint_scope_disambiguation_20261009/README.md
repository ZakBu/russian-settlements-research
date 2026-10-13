# Scope-only overlay for the 223-row ownpoint roster

This packet classifies literal source parts, administrative aggregates, and federal-territory totals in the frozen 223-UID roster for the ownpoint workstream. It performs no point finding, identity review, population edit, allocation, deletion, or denominator change.

## Results

- `scope_overlay.csv` contains 38 exact source UIDs: 32 literal part rows, one municipal-council aggregate, one partial rural component of a pgt, and four federal-territory totals. Raw source populations are retained unchanged. These source units are not treated as separate whole-NP ownpoint targets.
- The 32 literal part records total 127,915 as printed: 25 rows / 110,899 in 2002 and seven rows / 17,016 in 2010. This is a raw published-part total, not a new population credit, a whole-settlement estimate, or an allocation to a receiver.
- All 32 part UIDs appear in the Stage68 applied component snapshot and have `has_own_point=False` in that frozen snapshot. Thirty-one also appear in the Stage68 primary source UID roster; that records source membership and does not make a literal part a whole-NP spatial target. The remaining row is `Троицкое (часть 2)` (1,196), which has an explicit Stage70 coarse typed association to the current Троицкое carrier. The Stage70 row expressly says exact historic part coordinate is `UNKNOWN`, and it asserts neither ordinary identity nor population equivalence; no count or quality was changed.
- For the other 31 literal parts, the overlay retains their source UIDs as part-level observations and does not invent an exact point or receiver. Where no exact UID-scoped Stage70 carrier row appears in the final batch manifest, it is left blank in the overlay.
- The extra scope rows retain one Khakassia municipal-council aggregate (1,042), one Omsk rural part of pgt Павлоградка (1,124), and four federal-territory totals. The cited Stage70 source-scope overlay classifies the first two as nonordinary source units, with `raw_population_modified=False`; the four federal totals are excluded by their territory-total source grain.
- `whole_NP_not_scope_exempt_root_point_route.csv` records Tambov `село Ярославка` 2010 (1,022) as a whole named settlement, not a scope exemption. The existing Stage70 typed scope manifest associates it with the 2021 joint physical-NP carrier under `volga_yaroslavka_first_second_joint`, with historic part coordinate `UNKNOWN`. Root owns the separate point review, so this row is kept out of the scope-exclusion overlay.

## Reproduction and limits

Run `build_scope_overlay.py` to regenerate the CSV overlays from the pinned 223-row roster, scope inventory, Stage68 component/credited UID ledgers, and Stage70 scope manifest. `raw_source_file_pins.json` gives SHA-256 for each underlying publication file represented in the overlay; `receipt.json` pins all intermediate ledgers and output hashes.

This classifies source grain for completion accounting only. It does not claim that every numbered part has a known whole-settlement receiver. It does not resolve exact historic part coordinates, compare census boundaries, or use aggregates/parts as separate ownpoint claims.
