# Agent methods used in the 2026-10-02 run

Installed skill versions, source repositories and content hashes are recorded in
`config/research_skills_20261002.json`. Skills were read before application.

- `find-skills`: discover and inspect relevant local skills; unsuccessful searches
  are recorded and do not imply an installation.
- `context-optimization` and `context-compression`: short scoped handoffs,
  persistent intent/decision/artifact anchors, compact machine-readable receipts,
  filtered tool output and source references instead of repeatedly copying data.
- `multi-agent-patterns`: one supervising integrator, bounded competent workers,
  separate file ownership and a separate verifier for concrete proposed rules.
- `harness-engineering`: fixed objective and admission gates; diagnose, propose,
  verify, measure, record, and select the next action from the residual. Failed
  experiments are recorded. Gates are not weakened to improve the percentage.
- `scientific-critical-thinking`: distinguish observations, interpretations,
  candidates and admissions; check source grain, denominators, independent
  evidence and counterexamples; scale conclusions to the validation performed.
- `geopandas`: preserve coordinate reference systems and identifier cardinality;
  handle negative Chukotka longitudes and geodesic distances explicitly. It does
  not make geocoding quality scores evidence of correct object identity.

Deterministic columnar processing handles large datasets; agents examine rules,
source semantics and exceptions. There is no language-model call per settlement.
Current workers use `gpt-6-luna` for bounded tasks; the root agent resolves ambiguity
and integrates accepted outputs. Actual token usage and inference cost are not
exposed by this runtime, so no measured token-savings claim is made.

The first optimized candidate run took 95.66 seconds, with sampled peak RSS
3,085,772 KiB. It generated candidates, not admissions. This timing does not
predict the time needed to resolve source or historical uncertainty.

Software-method reference for Scientific Agent Skills:
Kassis, T., Agarwal, V., He, Y., Patel, D., and Brueckner, A. M. (2026).
*Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*.
[arXiv:2609.00065](https://doi.org/10.48550/arXiv.2609.00065).
This is a software-workflow reference, not demographic evidence.
