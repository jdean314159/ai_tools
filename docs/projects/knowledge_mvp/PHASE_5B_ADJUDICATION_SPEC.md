# Knowledge Curation MVP: Neural-Memory Adjudication Probe

**Status:** Revised before first schema-valid probe
**Date:** 2026-06-13
**Scope:** Phase 5B only

## Decision Question

Can the knowledge workflow represent an early optimistic conversational claim,
later contrary evaluation evidence, and an accepted architectural resolution as
one inspectable claim history rather than unrelated agreeable cards?

## Focal Claims

The probe uses one historical implementation hypothesis plus four extracted
candidates:

1. `hypothesis-neural-affinity-improves-retrieval`
   - adding neural affinity to Engram retrieval improves memory recall;
2. `candidate-e5b8ff4a96914696`
   - system-level surprise weighting can replicate functional benefits of
     architectural long-term-memory modules;
3. `candidate-1daddd4ca13cf45a`
   - TITANS uses an MLP long-term-memory module and surprise-based updates;
4. `candidate-fa30e8c2f2f35393`
   - surprise filtering can reduce storage by 70-90%;
5. `candidate-738380e8de4da93d`
   - durable synthesis nodes can compound value across sessions.

The claims are intentionally not treated identically. A description of the
published TITANS mechanism is not refuted merely because the ai_tools adapter
failed. Numeric benefit claims require their own evidence. The repository's
negative result applies specifically to the integrated RTRL/TITANS retrieval
and prompt-synthesis roles.

## Evidence Hierarchy

From weakest to strongest:

1. `conversation_assessment`
2. `source_summary`
3. `implementation_spec`
4. `local_evaluation`
5. `accepted_adr`

Higher authority does not make a claim universally true. It controls current
ai_tools guidance only within the evidence's stated scope.

## Required Relations

The adjudicator must represent:

- early conversational support for neural/surprise memory;
- the local evaluation's challenge to retrieval benefit;
- ADR-016's supersession of default-on or active-development guidance;
- the distinction between architecture description and measured product value;
- dependent broad-benefit claims as needing review rather than silently
  inheriting approval.

## Status Vocabulary

- `supported`: current evidence supports the claim in its stated scope;
- `qualified`: a narrower version remains supportable;
- `contested`: material evidence conflicts and no controlling resolution exists;
- `resolved_against`: controlling evidence rejects the claim for the stated
  ai_tools scope;
- `unresolved`: evidence is insufficient;
- `historical`: retained to explain prior reasoning, not current guidance.

Evidence relations use `supports`, `challenges`, `qualifies`, `supersedes`, or
`unresolved`. The last value records that cited evidence does not adjudicate a
claim in its stated scope; it is not a substitute for a claim status.

## Predeclared Gate

The probe passes only if:

1. the ai_tools neural-affinity retrieval hypothesis is `resolved_against`;
2. the broad replication claim is narrowed to `qualified`, not treated as
   universally disproven by the adapter evaluation;
3. the TITANS mechanism description is not marked `resolved_against`;
4. the unsupported `70-90%` storage-reduction claim is `unresolved` or
   `contested`;
5. the synthesis-node claim is flagged for review rather than automatically
   approved or rejected;
6. local evaluation and ADR evidence outrank conversational assessments;
7. the optimistic claims remain visible in history;
8. the rendered current guidance says re-ranking is disabled, the layer is
   parked/default-off, and reactivation requires a new need and gate;
9. no numeric confidence score is introduced.

## Revision Note

The first model call did not validate against the output schema, so it did not
produce a probe verdict. Its malformed response nevertheless exposed an
overbroad expected status: local adapter failure cannot refute every possible
system-level approximation of architectural memory. The gate was narrowed
before the first schema-valid run by adding the explicit ai_tools retrieval
hypothesis above.

Failure means the proposed knowledge capability remains an index and should not
proceed to a general adjudication subsystem.

## Probe Result

The final `qwen3.6:27b` run was schema-valid but failed the substantive gate
with six errors:

- it correctly marked the narrow ai_tools retrieval hypothesis
  `resolved_against`;
- it marked the broad system-memory and TITANS descriptions `historical`
  instead of producing reviewable, qualified current statements;
- it marked the unsupported `70-90%` storage-reduction claim `qualified`
  instead of `unresolved`;
- it left the unresolved synthesis-node claim with `review_required=false`;
- its current guidance omitted the explicit facts that re-ranking is disabled.

This is a useful negative result. The local model can organize the evidence and
apply the repository decision to the directly tested hypothesis, but it cannot
yet be trusted to preserve uncertainty and human-review requirements across
adjacent claims without deterministic policy checks. Phase 5B therefore does
not justify building a general wiki adjudication subsystem.
