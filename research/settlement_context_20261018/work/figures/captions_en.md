# English figure captions

## 1. Panel and population at risk

The accepted stage71 balanced panel comprises 142,570 ordinary settlement records with unique identifiers. Positive population in 2010 defines the 121,324-record population at risk of a transition to a recorded zero by 2021. Development and held-out risk subsets contain 101,593 and 19,731 records, respectively. The split protects the final assessment of this run; it does not establish that the observations were historically unseen. The panel does not represent the complete Russian census settlement universe. Source: data_audit/evidence/data_contract.json and the split manifest.

## 2. Source quality and zero-population trajectories

The left panel groups the quality flags of selected 2010 values into protected secondary values and all other statuses. The right panel shows every 2002→2010→2021 zero/positive trajectory containing at least one zero. The all-positive trajectory is omitted from this panel only and remains in the accompanying CSV. Zero values are recorded numerical states, not verified physical disappearance or loss of functions. Source: data_audit/evidence/zero_three_way_patterns.csv and population_value_quality_2010.csv.

## 3. Geography of the spatial split

Actual representative 2010 coordinates are projected to EPSG:3576, a Lambert azimuthal equal-area projection centred on 90°E. Blue points belong to held-out blocks; grey points belong to development blocks. No administrative basemap is supplied. Blank space does not establish absence of settlements outside the accepted panel. The 500-km bar measures projection-coordinate distance and is not a uniform ground-distance scale. The accompanying CSV contains block point centroids in metres, not block boundaries. Source: geo/features.csv.gz and the split manifest.

## 4. Incremental predictive information

Positive values indicate a relative reduction in prediction loss. E1 uses the Brier score for a transition to zero; E2/E3 use MAE of symmetric population change. The intervals are paired percentile 95% block-bootstrap intervals conditional on fitted predictions, with 1,999 resamples and seed 20261018. Development results use spatial cross-validation with a 60-km buffer. Held-out results are plotted only when the locked evaluation is available. The 2% reference is an operational convention, not a universal usefulness threshold. Interval calibration for actual predictive effects is not established. Source: development/result.json for each direction and final/evaluation.json when available.

## 5. Locked sensitivity assessments

All configurations were fixed before the final reveal. Radius variants use 10/60-km neighbourhoods; nn adds a normalised-nearest-neighbour control; buffer100 uses a 100-km exclusion buffer; linear changes the learner family; raw_control adds earlier population mass; permuted rearranges the additional feature block within spatial blocks; original and drift evaluate the specified population-value and coordinate sensitivities. Every configuration reuses the same held-out outcome set. Intervals are descriptive and are not adjusted for multiple comparisons. The figure is a diagnostic record, not a menu for selecting a favourable model. Source: final/evaluation.json.

## 6. Similar neighbourhood mass, different concentration

An illustrative development pair, Otonkhoy and Zaglik in Irkutsk Region, was selected from predictor values without reading its 2021 outcomes. Own populations are 271/261, neighbourhood populations within 30 km are 27,467/27,470, and neighbour counts are 49/49. The largest-neighbour shares are approximately 0.542/0.188; effective neighbour numbers, defined as the inverse sum of squared mass shares, are 3.31/12.42. The pair demonstrates distinguishable concentration at similar mass. It does not estimate an intervention effect or establish national common support. Source: e2/illustrative_pairs_preoutcome.csv.

## 7. A denominator changes the interpretation of graph connectivity

Development-only geometric graphs use a 10-km radius and settlements with positive population in 2010. Nodes recorded as zero in 2021 are removed; returns from zero are not added. The fixed denominator retains the initial node count, whereas the active denominator counts remaining nodes. In these three regional examples, the active-denominator share of the largest component increases while its fixed-denominator share decreases. Regional and holdout boundaries truncate edges. Panel-specific vertical scales are explicitly used to show within-region changes. No conditional spatial null model was run. Source: e3/regional_curves.csv.

## 8. Interval coverage depends on assumed dependence length

A synthetic bootstrap diagnostic uses the actual geometry and record-count weights of 89 held-out blocks, representing 19,731 risk records. Each scenario generates 300 Gaussian synthetic loss-difference fields with a known zero expectation, and uses 499 block-bootstrap resamples. Vertical intervals are 95% Wilson Monte Carlo intervals for the coverage proportion; they are not uncertainty intervals for research effects. The 100/300-km dependence scales are specified by the generator and are not estimates of real residual dependence. This diagnostic does not calibrate the learner, model selection, actual predictive gain or p-values. Source: statistics/calibration/run_v1/results.json.
