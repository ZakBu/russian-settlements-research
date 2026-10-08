# Accepted historical native own-point promotion

This bounded packet applies only independently identified own locality points to
actual selected native settlement IDs that lacked an admitted point in State47.
The frozen lifecycle sources and formation candidates are unchanged.

Actual State47 application admitted 41 points: 36 native 2002 observations
(population 245367) and five native 2010 observations (population 45821).
Eight existing admitted points were retained; alternatives are recorded without
overriding them or manufacturing point conflicts. Two own PGT native 2002–2010
same-place edges join Киевский and Кокошкино. No municipal 2021 observations are
joined to these individual settlements.

All 465800 selected source observations remain unchanged. Finite native
three-census histories with every component member pointed remain 138838, with
population totals 126710197 / 123868655 / 124470630 in 2002 / 2010 / 2021.
The point improvements do not imply a gain in that three-census denominator.
The per-year coordinate totals in the receipt include all native source rows;
their populations are source-year coordinate coverage, not longitudinal credit.

Historical use of later physical points is an explicit continuity inference,
not a measured census-day coordinate or boundary comparability assertion.
No child 2021 count is created, no municipal P625 is projected to an NP, and
source counts and population-quality classes are preserved.

`build.py` consumes State47 once and imports the guarded finite helper. It checks
the frozen sources and actual Geo2011 DBF record bytes, types, codes and point
coordinates. `verify.py` independently verifies every input/output pin and
reopens all 49 candidate native population rows (46 XLS rows, two official PDF
rows, and the previously verified exact Murmansk primary-parser ledger row).
The original Murmansk DOC remains unavailable; its retained source condition
does not become a fresh DOC retrieval or an improved population-quality claim.

Reproduce with `python build.py` followed by `python verify.py` from this folder.
Root integration of the accepted CSV deltas into the loader is separate.
