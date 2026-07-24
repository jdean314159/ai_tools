# NAV-VERIFIABLE-00 deterministic foundation validation

**Date:** 2026-07-23  
**Status:** First live paired campaign complete; frozen verdict inconclusive.

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

The `agent_lib` package gate passed with `150 passed`. Dedicated tests cover all
four task shapes, exact relation scoring, indirect-as-direct rejection,
unobserved evidence, source hash drift, aliases, same-named methods, nested
functions, dynamic calls, relation-claim shape, and paired configuration drift.

The repository-root pytest command remains unavailable because the root
`conftest.py` imports a missing `examples._repo_bootstrap` module before test
collection. This is pre-existing and outside the NAV change; the supported
package-scoped gate was used.

## Remaining validation boundary

The campaign establishes a directional termination and relation-correctness
signal, but it does not meet the frozen support rule and does not validate exact
correctness on exploratory tasks. No adoption conclusion follows.

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

## Campaign policy gate

Campaign schema v1 is frozen before production task construction. It requires
at least four local, four intermediate, and six exploratory tasks. Exploratory
tasks must span three source-hash-derived snapshots, no task shape may exceed
half the tier, and both decoy-heavy and graph/multi-file subsets require at
least three tasks.

The paired summarizer reports every metric per tier, makes exploratory results
primary, retains all individual token and tool-step deltas, and permits only an
equal-tier macro-average as the secondary overall result. When supplied the
campaign manifest, it rejects any missing, additional, duplicated, or re-tiered
pair.

This policy was fixed before the complete paired campaign and was applied
without changing thresholds after outcomes.

## Arm, decision, and selection freeze

The comparison now holds the final-answer instrument constant. Both arms must
emit the same typed relation claims and use the same canonicalizer and AST
scorer. The baseline is explicitly named `no_ledger`; only the comparison arm
maintains per-step goal state. Free-form extraction and asymmetric scoring are
rejected.

The exploratory-tier adoption, rejection, and inconclusive boundaries are
encoded in the deterministic campaign decision function. Cost is represented
both by total exploratory tokens and median overhead where both arms complete.
If both shared-schema arms terminate on all six exploratory tasks, the function
returns `inconclusive_schema_ceiling` unless correctness or cost independently
triggers rejection. Zero gain with available no-ledger failures remains a
rejection.

Candidate selection is also mechanical: enumerate all v1-oracle-resolvable
task shapes, deduplicate normalized expected relations, hash the complete pool,
and select by frozen coverage priorities plus a public salted hash order. An
undersupplied stratum requires a new pinned snapshot and complete pool
regeneration, not a hand-picked replacement.

Selection schema v2 superseded v1 before any production model outcome because
v1 could omit a task shape despite the parent spec requiring all four. The v2
coverage priority requires definition, direct-callers, call-path, and
mutation-target representation and uses a new public ordering salt. No
candidate was substituted after selection.

## Production candidate and admission result

Three independently source-hashed, oracle-compatible evaluation snapshots were
added under `agent_lib/eval_snapshots/`. Full schema-v2 enumeration produced
204 candidates. Deterministic selection and admission produced exactly 14
tasks: four local, four intermediate, and six exploratory, with all four task
shapes represented and exploratory tasks spanning all three snapshots.

Frozen identifiers:

- candidate pool:
  `480f48928bc067926d44cf31b3e79571dd0af2912aaafbb7aec976c429399f4e`;
- candidate selection:
  `a7cd9f555843fe127e47229bcdd67b988e15a34467a20cf5b8533a7553121b39`;
- campaign admission:
  `00dfcc508ddf18b330a2f9c9e9f32ffe92ae570e08f52f1bc165442cd30f8cb6`.

The complete pool, selected tasks, per-snapshot task sets and admissions, and
portable run plan are tracked in
`agent_lib/eval_manifests/nav_verifiable_campaign_v1/`. These are pre-model
artifacts; they contain no observed planner outcome.

## Paired executable gate

`agent_lib/examples/nav_verifiable_campaign.py` loads only the frozen run plan,
validates every source hash, alternates no-ledger/ledger order, and holds task,
model, seed, decoding, budget, final relation schema, and scorer constant. The
ledger arm is seeded from the selected task's user-visible goal requirements;
the no-ledger arm receives no goal state. Each arm record is written before the
campaign summary, so an interrupted campaign retains completed evidence.

The planner extension is opt-in. Existing NAV defaults retain the original
navigation claims, system prompt, and NAV-TEST-00 goals. The `agent_lib` package
gate passes with the relation-schema and task-specific-goal path enabled.

An initial one-pair runner smoke exposed two missing runtime-contract details:
the relation array permitted zero items, and definition-field empty-value
semantics were not stated. That smoke is excluded from the campaign. The
runner then symmetrically required observed evidence and at least one relation
in both arms, and stated the already-oracle-defined empty-field semantics. The
same selected task was rerun under the corrected contract and the remaining
campaign resumed from that record. This is a real protocol-adoption correction
after observing one selected task, so the campaign is not a pristine
first-contact dataset even though no scorer, task, tier, or decision threshold
changed.

## First live paired campaign

All 14 pairs completed under Qwen3.6-27B-Q4_K_M, seed 0, temperature 0, the
40,000-token context window, 120,000 cumulative-token limit, and alternating
arm order. The frozen decision function returned `inconclusive`.

Primary exploratory-tier results:

- termination: no-ledger 0/6, ledger 3/6; paired net +3;
- relation correctness: no-ledger 0/6, ledger 2/6; paired net +2;
- exact correctness: 0/6 in both arms; paired net 0;
- total tokens: no-ledger 124,583, ledger 99,313 (ratio 0.797);
- evidence-complete ledger answers: 2/6;
- evidence-precise ledger answers: 0/6.

The two relation-correct ledger answers failed exactness through over-citation.
A third ledger answer terminated with an unsupported relation. The other three
exploratory pairs failed to terminate in both arms.

The result did not satisfy `support_broader_shadow` because the frozen rule
requires a median ledger overhead among exploratory pairs where both arms
complete; there were no such pairs, so that metric was `null`. The result was
not rejected because termination and relation nets were positive, exact net
was nonnegative, and ledger aggregate tokens were lower. The rule therefore
correctly preserved the outcome as `inconclusive`; it must not be reinterpreted
post hoc as support.

External result directory:
`/home/cybernaif/repos/repo_agent_eval/repo_agent/nav-verifiable-campaign-v1-smoke-contract-20260723`.

Result hashes:

- `pairs.json`:
  `92920f0696f061f651265534adf2950a12e2feb47942c8854307ae5e33469283`;
- `summary.json`:
  `ce066fdc71348a21009638c0e64dfabc5eb8b984fe3c2ea87ef2b4edeb72d7c5`;
- `decision.json`:
  `63524de4e6e7ad9fadd4b1eb8fc41cec2d0511d57d0adb4065613779cbb8929b`.
