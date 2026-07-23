# NAV-VERIFIABLE-00 deterministic foundation validation

**Date:** 2026-07-23  
**Status:** Contract gate passed; no live model result.

## Implemented boundary

The deterministic layer now provides:

- source-hash-pinned, versioned task fixtures;
- exact task contracts for definition lookup, direct callers, one unique call
  path, and a call expression at a named site;
- relation-aware structured claims for definitions, caller→callee edges,
  ordered paths, and mutation targets;
- a conservative Python AST oracle;
- observed-evidence-aware exact scoring;
- paired-run manifest validation that permits only one autonomous and one
  structured run with identical shared configuration.

The oracle does not infer runtime dispatch. It resolves module-local calls,
`self`/`cls` method calls, and explicit class-qualified calls. Aliases and
dynamically constructed calls fail closed. Same-named symbols require
qualification, nested-function calls are attributed to the nested function,
and indirect helper calls cannot satisfy a direct-edge claim.

## Deterministic result

The `agent_lib` package gate passed with `136 passed`. Dedicated tests cover all
four task shapes, exact relation scoring, indirect-as-direct rejection,
unobserved evidence, source hash drift, aliases, same-named methods, nested
functions, dynamic calls, relation-claim shape, and paired configuration drift.

The repository-root pytest command remains unavailable because the root
`conftest.py` imports a missing `examples._repo_bootstrap` module before test
collection. This is pre-existing and outside the NAV change; the supported
package-scoped gate was used.

## Not yet validated

This checkpoint does not show that a model can emit the relation schema, that
task-specific ledger goals work, or that the ledger improves any paired task.
The production task set and paired executable do not exist. No live run was
performed.

The next gate is model-facing adoption plus deterministic end-to-end tests:
seed each task's user-visible goals, require `relation_claims` only for this
track, preserve the autonomous mode on the same question, and score both run
records with the external AST oracle. Live runs remain premature until that
contract passes.

## Formatter-only live gate

A reproducible probe now supplies the complete pinned `sample.py` source to
Qwen3.6-27B-Q4_K_M and requests three constrained outputs without navigation
tools: one direct edge, one ordered path, and one named-site target.

The first protocol returned JSON matching the server grammar but failed the
claim contract in all three cases. The model treated `path` as a human-readable
call-chain field, used inconsistent relation kinds, and omitted canonical
qualification. Because the schema provided types without field semantics, this
was an underspecified representation rather than a model-capability result.

One correction added field descriptions and explicit kind rules. The corrected
temperature-zero gate produced:

- 3/3 structurally valid `relation_claims`;
- correct requested relation kinds in 3/3;
- correct direct edge, ordered path shape, and evidence locations in 3/3;
- 0/3 exact scorer passes.

The remaining failures expose a second contract boundary. The oracle exports
module-prefixed symbols such as `sample.Pipeline._prepare`, while the task and
model use `Pipeline._prepare`. For named-site targets, the oracle records the
callable expression `self.store.add`, while the model returned the complete
call expression `self.store.add(value)`. Both model forms are supported by the
visible source and task wording.

Therefore formatter feasibility passed while the external canonicalization
contract remained unresolved at that checkpoint. No further prompt or live
iteration was performed; the deterministic scoring correction and offline
replay below resolved the representation question.

Artifacts:

- initial protocol:
  `/home/cybernaif/repos/repo_agent_eval/repo_agent/nav-verifiable-schema-probe-20260723.json`;
- corrected protocol:
  `/home/cybernaif/repos/repo_agent_eval/repo_agent/nav-verifiable-schema-probe-corrected-20260723.json`.

## Frozen canonicalization and offline replay

Canonicalization v1 was fixed before production task selection and is applied
to both oracle relations and model claims. It removes only the source-derived
module prefix, preserves structural qualification, and reduces AST call
expressions to their callable while retaining raw claims for audit. Fixture
admission rejects any symbol collision introduced by normalization. The full
rules are in `NAV-RELATION-CANONICALIZATION-V1.md`.

The scorer also now records the exact syntax-line set required by each
relation. A path requires every component edge line, not overlap with the
minimum-to-maximum enclosing span. Extra lines are reported as evidence
imprecision and fail exact correctness.

Replaying the saved corrected responses without another model call produced:

- direct caller: exact pass after two-sided symbol normalization;
- mutation target: exact pass after deterministic call-expression reduction;
- call path: relation and required lines present, but exact failure because the
  cited range 7–14 includes six non-edge lines around required lines 8 and 11.

The frozen scorer therefore returns 2/3 exact passes, not the earlier 0/3 and
not an overstated 3/3. Formatter feasibility remains established; minimal
evidence precision remains unproven under live navigation.

Replay artifact:
`/home/cybernaif/repos/repo_agent_eval/repo_agent/nav-verifiable-schema-probe-canonical-v1-replay-20260723.json`.

## Metric decomposition and admission gate

Exact scoring is now factored into relation correctness, evidence completeness,
and evidence precision. Unsupported relations, missing required evidence, and
extra evidence are separate defect classes. `exact_correct` remains the strict
conjunction, so the bar did not weaken.

Replaying the same saved responses under the decomposed scorer yields:

| Task | Relation | Evidence complete | Evidence precise | Exact |
|---|---:|---:|---:|---:|
| Direct caller | pass | pass | pass | pass |
| Call path | pass | pass | fail | fail |
| Mutation target | pass | pass | pass | pass |

The shared JSON schema now states the minimal-line requirement explicitly. The
path over-citation remains known model behavior because the corrected live
prompt already contained the same requirement.

Task-admission schema v1 is also frozen before production fixture
construction. It records source hashes, oracle resolvability, canonical
uniqueness, exact expected relations, and four structural difficulty features:
hop count, answer-file count, candidate-file count, and decoy count. Tier
classification uses only these source-derived values. Autonomous run cost may
identify a calibration miss but cannot reclassify or remove a task.

Decomposed replay artifact:
`/home/cybernaif/repos/repo_agent_eval/repo_agent/nav-verifiable-schema-probe-decomposed-v1-replay-20260723.json`.
