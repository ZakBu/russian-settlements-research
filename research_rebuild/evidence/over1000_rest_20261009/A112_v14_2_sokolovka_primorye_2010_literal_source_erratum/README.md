# Sokolovka V14.2: literal 2010 source row and imported district-field erratum

The frozen V14 hold labeled the only selected 2010 row as Khasansky. Reopening the pinned raw XLS shows that source record `...:ДВ:512` is literal raw worksheet row 512 in the Primorsky region: `с. Соколовка`, population 1,058. The worksheet's `район` field is blank on row 512. The raw source sequence is Chuguevka (row 511), Sokolovka (512), Tsvetkovka (513), Shumnoe (514).

Independent 2002 primary rows 874–876 bind Chuguevka, Sokolovka and Tsvetkovka to Chuguevsky district / Chuguevskaya administration. In 2021, their named current counterparts (including the target) are in the Chuguevsky municipal district. This is a source-order and cross-census administration bridge; equality of 1,058 is incidental evidence only. The selected ledger's `district_raw=Хасанский` is a contradictory imported field, not literal raw XLS content. Preserve that discrepancy as parser provenance and use the literal source row context for review.

Both 2002→2010 and 2010→2021 are proposed as `same_place` candidates with raw-source pins in `sokolovka_2010_scope_candidate_edges.csv`. The current own point remains with the 2021 target; this packet does not supply a historic coordinate or make a boundary comparability claim. Prior V14 files remain unchanged.
