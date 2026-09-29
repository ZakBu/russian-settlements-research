# Methodology and release policy

## Research unit

The target is a physical inhabited locality and a representative point for that locality. Census observations, administrative names/codes, identity decisions, historical events and coordinate claims are separate facts with their own source and date. An administrative code or coordinate inherited from a later successor does not by itself establish historical identity or location.

## Evidence handling

- Preserve each census source row, reported population and source locator unchanged.
- Treat the existing crosswalk as a candidate-generating result. Record accepted, rejected, unresolved and conflicting decisions with evidence and rule version; corrections supersede prior decisions without erasing them.
- Record name, type, administrative affiliation and identifiers as dated claims. A rename or type change may describe continuity; merger, split and incorporation are explicit events that can connect multiple places.
- Store coordinate candidates with source, object level, time applicability and review status. Admit a point to a census observation only when its settlement-level provenance and the observation-to-place link are supported.
- Do not convert text similarity, provider agreement, a modern code, an administrative centroid or a matching population total into proof by itself.

## Coverage measures

For each census year, report both the fraction of additive settlement rows and the fraction of their population with an admitted representative point tied to that specific observation. Report territorial aggregates and unallocated controls separately. Report longitudinal identity/panel coverage as a distinct measure; an observation can have a valid annual point while its relationship to another census year remains unresolved.

## Independent quality control

Each automated admission rule must identify the evidence class it accepts and preserve the evidence used for each decision. Validate the implementation against independent primary-source checks, a stratified sample of accepted rows, all high-population conflicts, and targeted cases covering duplicate names, administrative changes, type changes, inclusion, merger and split. Report errors by evidence class and retain rejected and unresolved cases. Sampling tests implementation quality; it does not substitute for direct evidence required by an individual admission rule.

## Reproducibility

Every baseline asset has a SHA-256 digest. A scientific release must bind its input manifest, code revision, rule versions and output checks to the exact source snapshot. Do not overwrite baseline assets when correcting a parser or decision.
