# Full graph readback of the frozen 129-pair historical OKATO cohort

This follow-up supersedes the earlier projected-residual estimate in `historical_code_bridge_graph24_overlap_20261005.md` for the question “how many new identity edges are available?”. It is an overlap audit, not a newly accepted bridge batch. The candidate-only table has 129 exact-name/type/region/code candidate pairs and SHA-256 `a5e3476269a5077dab7d43c715989d4ea4a440faf0171a3e3bb781d5d3dba8d8`. Its two-year gross selected population sum is 1,965,919 (2002) plus 2,005,127 (2010), or 3,971,046 person-observations across two years. This is not additive coverage and must not be presented as a prospective gain.

Recomputing connected components over **all** selected source IDs and all accepted Graph28 edges shows 129/129 candidate pairs are already in the same accepted temporal component, often through a 2021 endpoint. Therefore this cohort contributes zero new identity edges. Both historical endpoint rows already have accepted points for 128/129 pairs. Ожерелье is the sole point gap; Graph29 applies one reviewed point to its 2002 and 2010 endpoints. The four pairs initially flagged as disconnected by an endpoint-only component check (Белоозёрский, Пеледуй, Витим, Беринговский) are in fact connected through intermediate selected IDs. The endpoint-only check was incorrect.

Independent pair review additionally noted 3.4003 km and 3.2117 km differences between accepted coordinates and the historical GeoKLADR point for Витим and Беринговский. Those point differences remain a coordinate-quality issue; they do not undo the already accepted identity links and are not grounds to replace those points in this audit.

Eight candidate rows were held in the original candidate screen for shared-point ambiguity (Лондоко, Истра, Софрино, Быково, Руза, Жилёво, Михнево, Шумерля). The 129-row CSV is retained beside this note as a candidate inventory only. No rule expansion is authorized by this readback.

The full-graph component and accepted-point intersection can be replayed with `research_rebuild/mass_linkage/readback_historical_code_bridge_129_full_graph_20261005.py`. Its checked receipt is `historical_code_bridge_129_full_graph_readback_20261005.json`; candidate, Graph28 edge-ledger and Graph28 point-ledger SHA-256 values are pinned there. It adds zero edges.

## Self-critique

The first quick component check incorrectly restricted its graph to source IDs present in the candidate table and suggested four remaining disconnected pairs. An independent full-graph readback found the omitted intermediate 2021 nodes and disproved that conclusion. The earlier “125/129 already connected” statement was withdrawn. All subsequent component claims use the full selected-ID graph. The reported 3,971,046 is gross person-years across both census endpoints, not population coverage or a gain.
