# NAV-STRUCT-00 structured navigation validation

**Date:** 2026-07-23  
**Status:** Experimental structured-navigation track; live completeness gate failed.

## Scope

NAV-STRUCT-00 is separate from autonomous NAV-TEST-00. It measures a planner
operating under a harness-seeded information-goal protocol. Results must not be
reported as autonomous navigation.

The harness seeds three requirements copied from the user-visible task:

1. persistent Chroma client and collection initialization;
2. every direct Chroma collection mutation;
3. direct `RAGPipeline` call sites invoking those mutations.

No answer-key paths, symbols, or line regions are supplied to the planner.

## Contract

Every structured planner action returns the complete goal ledger:

- stable `goal_id` and immutable requirement;
- `open`, `resolved`, or `abandoned` status;
- resolution summary;
- observed evidence references.

Tool actions also identify the open goals they serve. The harness rejects:

- disappearing, appearing, or duplicate goals;
- changed requirements;
- reopening resolved or abandoned goals;
- resolutions without summaries and observed evidence;
- tool actions that do not serve an open goal;
- finalization while any required goal remains open.

The mode is opt-in through `--structured-navigation` and requires
`--action-guard-mode off`. Autonomous NAV defaults are unchanged.

## Deterministic gate

Tests cover premature finalization, disappearing goals, unobserved resolution
evidence, valid completion, end-to-end runtime metadata, and isolation from the
action-loop guard. The combined package/contract gate passed (`135 passed`).

## Live seed2 control

Pinned candidate `95c6ab1`, Qwen3.6-27B-Q4_K_M, seed 2, temperature 0.6:

- completed at 76,179 cumulative tokens;
- 13 tool calls / 14 steps;
- 9/12 evidence regions surfaced;
- 7/12 structured claims validated;
- three unsupported claims;
- no malformed or unobserved-evidence claims;
- read-only verification passed.

The ledger prevented the prior structured-claims control from finalizing after
only `chroma.py`, but the planner marked all three broad goals resolved too
early. It missed:

- `RAGPipeline.delete_collection`;
- pipeline construction of `ChromaStorage`;
- the direct `_embed_and_store → self._store.add` call.

It also renamed the observed `ChromaStorage.add` operation as
`ChromaStorage.store_chunks` and reported indirect `_embed_and_store` helper
invocations as direct storage-mutation call sites.

This is a control-loop improvement despite the failed completeness gate. Unlike
the budget-exhausting NAV failures, the structured run terminated with an
answer, and unlike the earlier structured-claims control it could not finalize
after inspecting only `chroma.py`. The deterministic ledger contract held:
there were no malformed goal transitions, disappearing goals, unobserved goal
evidence, or premature-finalization violations.

The result is also a regression against the autonomous seed2 control, which
completed with 12/12 evidence recall at 53,494 tokens. Structured seed2 used
76,179 tokens (42.4% more) while surfacing only 9/12 regions. The ledger's
control benefit therefore carries a measured exploration and token cost on the
one trajectory where autonomous navigation succeeded.

After this run, claim validation gained an optional source-backed syntactic
check: cited Python lines must be enclosed by the claimed function or class.
This rejects an invented enclosing symbol such as
`ChromaStorage.store_chunks`. It intentionally does not validate semantic
relations such as whether a call is direct or indirect; that requires an
AST/call-graph relation scorer rather than identifier grounding.

## Conclusion

Externalizing required goals improves control flow but does not make the
planner's sufficiency judgment trustworthy. Observed evidence proves that a
resolution is grounded; it does not prove that an existentially broad
requirement such as “every mutation” is complete.

The next design decision is not another prompt or loop signal. It is whether
the structured task manifest should provide deterministic, testable acceptance
criteria or finer-grained required subgoals. Doing so would make the harness
more capable of proving completeness, but would move it further from autonomous
navigation and closer to a task-specific execution protocol.

No additional prompt tuning, budget fallback, action-loop enforcement, or 8B
portability run is justified until that evaluation target is explicitly chosen.

The exhaustive-enumeration result remains a negative result under
NAV-STRUCT-00. A separate `NAV-VERIFIABLE-00` track may evaluate the ledger on
locally decidable goals, but must preserve an autonomous baseline on the exact
same tasks and must not redefine NAV-TEST-00.
