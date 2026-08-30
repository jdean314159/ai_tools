# Tool-recovery v4 development work order — 2026-08-30

## Purpose

Replace v3's invalid difficulty signal with a thinking-off development stage
that measures outcomes across distinct, predeclared variants. This is case
development, not evaluation, and cannot support a thinking-effect claim.

## Frozen families and variants

The six v3 recovery families remain unchanged: stale success, invalidating
warning, partial batch, authority conflict, permission boundary, and malformed
result. Each family has five committed variants in
`llm_engines.tool_recovery_probe._v4_development_cases`.

Variants change synthetic identifiers and the observable facts that make the
result unusable or identify the required recovery. They retain the family's
tool schema, two-turn budget, typed expected action, and exact typed-argument
scorer. Development prompts do not name the required recovery tool.

The suite therefore contains 30 distinct cases. One pass over those cases is
the difficulty sample. Repeating an identical variant is not evidence of
difficulty headroom.

## Frozen execution

- Profile: `llm_engines.tool_recovery_development`, version 2
- Endpoint class: the same OpenAI-compatible llama.cpp server on the DGX Spark
- Condition: thinking off only
- Requested seed: 17
- Repetitions per variant: 1
- Temperature: 0
- Maximum model turns per case: 2
- Condition order: `v4_distinct_variants_thinking_off_only`
- No intentional concurrent load
- Planned artifact destination:
  `docs/projects/llm_engines/runs/2026-08-30-spark-qwen-tool-recovery-v4-development-v1.json`

Seed acceptance is recorded but does not establish determinism. Endpoint URL,
server paths, raw prompts, raw responses, injected results, secrets, and
exception messages remain absent from the artifact.

## Advancement rule

A family is evaluation-eligible only when it passes at least one and fewer
than five of its distinct variants. At least three of the six families must be
eligible. Every eligible family advances; none may be selected or removed
according to anticipated thinking-on behavior.

If fewer than three families qualify, development stops. Changing wording,
difficulty, cases, or the eligibility rule requires another profile version
and work order. The v4 suite is not tuned in place after its first live run.

## Evaluation boundary

No thinking-on run is authorized by this work order. If the advancement gate
passes, held-out evaluation variants must be generated from a separately
committed table before either evaluation condition runs. A later evaluation
work order must freeze condition order, repetitions, minimum effect, and the
fabricated-success non-regression rule.

Repeatability, if measured later, uses a separate profile and summary. It must
not be combined with cross-variant pass rates or used to qualify families.

## Local acceptance before live execution

- All 30 case IDs are unique and every family contains five variants.
- A perfect fake engine yields zero eligible families.
- A fake engine passing four variants per family yields six eligible families.
- The artifact records family aggregates and omits raw case content.
- Frozen v1, v2, and v3 artifact byte digests remain covered by tests.

## Outcome: advancement stopped

The thinking-off development run completed all 30 distinct variants against
the same llama.cpp endpoint. It passed 28/30 cases and recorded no fabricated-
success failures. Five families passed 5/5. `stale_success` passed 3/5; its
first and fifth variants answered directly after the injected stale result
instead of calling `refresh_record`.

Only `stale_success` was evaluation-eligible. The work order required at least
three eligible families, so advancement stopped. No evaluation suite was
generated and no thinking-on run was performed. The aggregate 28/30 result is
not a reason to override the family-specific gate.

Artifact:
`runs/2026-08-30-spark-qwen-tool-recovery-v4-development-v1.json`

File SHA-256:
`a304925a3db422887af26b9a1afb9ae97a45d4203e51a69319afbfc5d6dd23d8`

The endpoint accepted the requested seed on every call. This records adapter
and provider acceptance only and does not establish deterministic generation.
The next recovery-development design, if pursued, requires a new profile
version and work order; v4 must not be tuned in place.
