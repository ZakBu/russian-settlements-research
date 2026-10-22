# Graph29 current point-route inventory (v2)

This is a fresh exact-ID intersection of current selected 2002/2010 rows, Graph29 accepted point uses, Graph28 accepted identity edges and current residual rows. It reintersects the frozen R5 point-route availability on current IDs; its provider is unknown where the source schema does not preserve it. Route availability and candidate coordinates are not admissions.

- Physical point residual: 17,411 rows / 4,018,209 residents (2002); 16,482 / 2,126,316 (2010), excluding three federal-city aggregate rows as documented in `REPORT.md`.
- Exact candidate ceiling only: 95 rows / 91,880 residents (2002); 50 / 13,448 (2010), before independent review. Nearly all are holds due to shared-point or code-width bridge ambiguity.
- Provider-unspecified legacy routes: 12,246 / 1,442,193 (2002); 13,581 / 1,593,126 (2010). These are the largest point-resolution queue, not an expected gain.
- Correct full-graph readback: 348,670 accepted same-place edges; 143,263 path-valid components. Within the current point residual, 714 rows / 199,645 people in 2002 and 896 / 178,139 in 2010 already have a valid multi-year component and need only a point for the broad available-year joint metric.

## Superseded v1 graph result

The first read-only report used `decision_status LIKE 'accepted%'`, which selected just 1,114 of the 348,670 accepted edges. Its graph/component and residual intersection numbers are withdrawn. The route-status stratification was unchanged and its CSV has the same SHA-256 in v1 and v2. `REPORT.md` and `receipt.json` record the corrected allowlists, exact source hashes and component checks. No edges or points were admitted by this audit.

Replay with `point_route_inventory_graph29_v2.py` in the original working environment. Large data inputs are referenced by absolute working-volume paths and pinned by SHA-256 in the receipt.
