# Station source-name designators — candidate-only batch

Fixed working_state stage 8; no accepted statuses or frozen-source edits. Match names only after removal of complete standard station designators at the beginning or a parenthesized station suffix. Preserve ordinary name letters (including ё), numbers, punctuation and lexical abbreviations; no fuzzy matching. Printed type variants are flagged, without asserting a legal rename or transformation.

Require identical normalized source region and explicit printed county, per-year county/name uniqueness ignoring type and counting unresolved plausible source competitors, physical additive whole-locality rows, and an already accepted component point. Exclude railway-feature types, administrative rows and locality parts. Repeated-year components, known events, shared same-year point collisions, native-coordinate contradictions and accepted points separated by more than 5 km are held. Point uses explicitly infer continuity and do not bind historical provider IDs or harmonize populations or boundaries.

All candidate raw endpoints are inspected because this batch has fewer than 100 cases. The 2002 counties are verified in preceding printed county headers; 2021 counties are read directly from mun_upper, and object_level is Населенный пункт. No 2010 endpoint with absent source county was included. Only prefix variants yield new edges in this run; the suffix rule is implemented but contributes no new candidates. The source population limitation in 2010 is preserved.

Run build_batch.py, sample_raw.py, then verify_structure.py in that order. simulation_receipt.json pins input bytes and reports distinct simulated full-chain gains, not candidate population sums. Root owns independent review and application.
