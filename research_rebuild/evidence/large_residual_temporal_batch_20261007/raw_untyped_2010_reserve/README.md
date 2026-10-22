# Raw untyped 2010 reserve — candidate-only pilot

`scan.py` pins working graph stage7 and scans all18 staged Lingva-style census2010 XLS workbooks. It starts from already accepted2002/2021 exact-name regional pairs without2010, with independently matching explicitcounty. It checks every selected2010 record by physical file/sheet/row and normalized name/region acrossalltypes, so another parser interpretation cannot silently become a new census observation. An exact-name homonym only blocks if its independently supported county is the same or unresolved.

`eligible_auxiliary_observation_candidates.csv` requires two distinct accepted2010 locality anchors on opposite sides, each within20 physicalrows, agreeing on county andregion. Raw population cells and all rawcells are preserved; missingvalues remainunknown. Raw administrative-total terms block eligibility. These are source-backed proposals requiring integration review; selected observations, identity ledgers and national denominators are unchanged.

`boundary_context_auxiliary_candidates.csv` keeps Верхние Ачалуки separate: printed2002 Malgobekcounty hierarchy, genuine untyped2010 row855 with7470, and two immediately following accepted Malgobek anchors. Its preceding2010 anchor belongs to Jeyrakh, so it fails the ordinary two-sided bracket. It must receive explicit boundary-context review.

The bounded missing-old-county probe checks up to100 pairs (49 available) for printed2002 hierarchy. Unique official2002 urban names may be scanned with2010 source context and currentcounty; that currentcounty is explicitly not asserted as a native2002 county.

Read `summary.json` for candidate counts and population potential. No population or identity admission is claimed. Protected secondary-source precision remains protected. Source hashes, original populations/qualities, exact row locators and accepted currentpoint origins accompany proposals.
