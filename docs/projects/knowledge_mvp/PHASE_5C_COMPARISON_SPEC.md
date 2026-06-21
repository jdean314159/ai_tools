# Knowledge Curation MVP: Few-Shot and Policy Comparison

**Status:** Predeclared
**Date:** 2026-06-13
**Scope:** Phase 5C only

## Decision Question

Do unrelated-domain few-shot examples materially improve adjudication, and
does an LLM add useful work beyond deterministic evidence policy?

## Arms

The same Phase 5B neural-memory case and gate are evaluated four ways:

1. `zero_shot`: the Phase 5B prompt without demonstrations;
2. `few_shot`: the same prompt plus unrelated software caching examples;
3. `few_shot_policy`: the few-shot proposal followed by deterministic floors;
4. `deterministic_only`: the same floors without an LLM proposal.

The examples and policy configuration are fixed before running the model. They
must not use neural-memory terminology or candidate IDs from the evaluation
case.

## Deterministic Floors

Policy operates on explicit claim traits:

- `directly_refuted`: controlling local evidence resolves the scoped claim
  against;
- `mixed_scope`: evidence rejects one application but does not erase the
  broader or descriptive claim, so the current statement is qualified;
- `unsupported_numeric`: a quantitative benefit without direct support remains
  unresolved;
- `untested`: a claim not measured by the supplied evidence remains unresolved.

`unresolved` claims require human review. Current guidance is rendered from
required decision facts rather than left to free-form generation.

Every change to an LLM proposal is recorded as a policy correction.

## Predeclared Evaluation

All arms use the unchanged Phase 5B expected statuses and operational-guidance
checks. The comparison records:

- gate status and error count;
- schema attempts;
- policy correction count;
- valid evidence-relation count;
- claims with at least one valid evidence relation.
- relation pairs matching the declared policy scope map;
- unsupported extra relation pairs outside that map.

## Interpretation

- A zero-shot failure and few-shot pass shows examples improve this case, but
  does not establish generalization. A second held-out conflict arc would still
  be required.
- A policy pass with a failed few-shot proposal shows the policy layer, not the
  model, supplies correctness.
- If deterministic-only passes and preserves sufficient evidence links, prefer
  structured ADR/evaluation metadata over an adjudication engine.
- Phase 5C does not authorize a general wiki subsystem by itself.

## Result

The final `qwen3.6:27b` comparison produced:

| Arm | Gate errors | Matched policy links | Unsupported links |
|---|---:|---:|---:|
| zero-shot | 6 | 4 | 4 |
| few-shot | 4 | 3 | 6 |
| few-shot plus policy | 0 | 7 | 6 |
| deterministic-only | 0 | 7 | 0 |

Few-shot examples improved two gate outcomes: the broad system-memory claim was
qualified and the synthesis-node claim was marked for review. They did not fix
the TITANS status, unsupported numerical claim, or required operational
guidance. They also increased unsupported evidence links.

The policy layer corrected six proposal fields/groups and supplied the passing
result. Deterministic-only passed without corrections and produced exactly the
seven declared evidence links. The Phase 5C decision is therefore to prefer
deterministic conclusion-history metadata and not retain an LLM adjudicator for
this capability. An LLM may still assist ingestion, but its proposed links must
remain untrusted candidates for human or deterministic validation.
