# Turgoyak: wrong legacy baseline edge erratum

This narrow supplement preserves the frozen V7 candidate packet. It identifies the exact baseline edge responsible for the repeated-year collision.

`legacy-temporal-2002-bc0c503bddac92de6f` linked the 2002 22-person `посёлок Тургояк` at `2002:061_e177b0a77d_Chel_abinskaja1.xls:Sheet1:145` directly to the 2021 2,766-person current posyolok. The source workbook places row 145 under the `Сыростанский сельсовет` caption (row 140), among rural council settlements. This is distinct from the 2002 official Tom 1 urban PGT row `2002:1_TOM_01_04.xls:0:8028` (2,292).

The bad edge is recorded in the legacy staged ledger row 5366 (file SHA in receipt); exact rows from staged, status, independent-review, and root application ledgers are copied into `bad_baseline_edge_exact_rows.csv`. Batch 7 confirms that the tiny old row is the 2002 collision blocking the frozen V7 proper-PGT edge.

Recommended correction: withdraw only the wrong 22→2021 edge; retain the 22-person source observation separately; preserve the 2010/2021 large locality; then consider the already-frozen V7 2002 PGT→2010 candidate. This does not create a net 2,292 gain unless the separate 22 source observation is handled in the same application. Station rows (2010=11; 2021=7) are separate objects. No coordinate changes.

All source and ledger pins are in `receipt.json`.
