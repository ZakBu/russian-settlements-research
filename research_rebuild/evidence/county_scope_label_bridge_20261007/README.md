# Literal county scope captions (candidate only)

Local v2 wrapper removes a trailing population-subtotal caption and the exact municipal-formation qualifier. Legacy county normalization and accepted inputs remain unchanged. Only newly equivalent county keys may produce candidates. See affected rows, graph-union simulation, source samples and held groups.

Stage 14 baseline reproduced exactly. The wrapper affects 228 Table 5 observations in 2010, totaling 1,623,392 people; 227 already have strict full-three-year identity and accepted points. The sole residual row is Кущевская (28,362), whose source scope/path requires separate treatment; a county-caption cleanup adds no actual missing observation. Municipal-formation cleanup affects 696 observations in 2021 (2,773,477 people). Its 69 residual rows total 10,517 people, and their geographic county spellings do not become cross-year equivalents through the literal cleanup.

No new candidate edges or points pass, and simulated gains are zero in every year. The only multi-component matched group is Копьево, which contains genuine same-year locality alternatives and remains held. The remaining 688 matched-caption groups have no cross-year equivalent county key. No PDF parsing or downloads were needed because no candidates survived. Existing legacy normalization, accepted inputs, source populations and source county fields remain unchanged.

The wrapper does not transform geographic adjective endings, infer county renames, strip middle scope captions followed by a locality, or collapse source parts. Exact literal cleanup is therefore not a remaining mass reserve.
