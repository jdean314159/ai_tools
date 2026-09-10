# Ornith oracle-localization pre-generation correction — 2026-09-10

No Ornith generation had started when Codex audited the v1 span manifest.
The audit found three load-bearing defects:

1. `defect_private_address` was a historical false fail. Target `23c1549`
   predates the Spark configuration entry and private address.
2. The validated Engram persistent-path permission defect was absent.
3. `defect_path_escape` began at line 318, after the unsafe `project_id` join at
   lines 311–315, so its displayed text could not support the oracle.

Manifest v2 corrects those issues before the first model request. Its five
defect spans correspond to the five valid external-grader behaviors documented
in `TARGET-ACQUISITION-2026-09-08.md`. The five matched negatives are the same
behaviors at corrected references `49026ea` and `8e2e9e5`, which pass those
graders. This is a pre-generation protocol repair, not an outcome-driven
change; commit `6eff393` permanently retains v1 for audit.

The experiment remains exploratory and consolidated: Codex designed the
implementation details, operates the run, scores and adjudicates it, and makes
no independent-verification claim.
