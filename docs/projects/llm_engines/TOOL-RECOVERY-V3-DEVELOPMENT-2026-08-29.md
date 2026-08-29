# Tool-recovery v3 development work order — 2026-08-29

## Purpose

Develop a harder recovery suite without selecting evaluation cases according
to whether thinking helps. This stage runs only thinking off and cannot support
an intervention claim.

## Frozen development families

Each family requires one valid initial lookup followed by one observable
recovery action:

1. `stale_success`: a nominally successful result is too old; call the refresh
   tool for that record.
2. `warning_invalidates`: a success result carries a warning that makes it
   unusable; call the validation tool.
3. `partial_batch`: two requested records are returned but only one fails;
   retry only the failed record.
4. `authority_conflict`: two fields disagree and the tool identifies the
   authoritative source class; call the authority lookup.
5. `permission_boundary`: the lookup is denied and alternatives are prohibited;
   call the human-review tool instead of claiming success.
6. `malformed_result`: the result cannot be parsed; retry once while requesting
   the strict result format.

Tool descriptions state their functions but prompts do not name the required
recovery action. The scorer uses typed tool names and exact typed arguments;
it does not score free prose.

## Frozen development execution

- Profile: `llm_engines.tool_recovery_development`, version 1
- Endpoint: the same OpenAI-compatible llama.cpp server on the DGX Spark
- Condition: thinking off only
- Requested seed: 11
- Repetitions: 3
- Temperature: 0
- Maximum model turns per case: 2
- Condition order: `v3_development_thinking_off_only`
- No intentional concurrent load
- Artifact destination:
  `docs/projects/llm_engines/runs/2026-08-29-spark-qwen-tool-recovery-v3-development-v1.json`

## Advancement rule

A family is eligible for evaluation only when its development pass rate is
strictly between zero and one. Every eligible family advances; none may be
removed based on expected or observed thinking-on behavior. At least three
families must be eligible. Otherwise development stops and a new work order is
required.

## Predeclared held-out transformation

For every eligible family, the evaluation variant keeps the tool schemas,
failure structure, budgets, and scorer, while replacing all development record
identifiers and field values with the next unused values from a committed
family-specific table. The transformation changes no recovery rule. Evaluation
variants are generated and committed before any evaluation or thinking-on run.

The later evaluation profile will be `llm_engines.tool_recovery_campaign`,
version 3, with a new suite digest. A separate work order must freeze its
repetitions, condition order, and minimum improvement threshold.

## Interpretation

Development outcomes measure case difficulty for this endpoint only. They are
not retained as evaluation evidence and cannot support a claim about thinking,
recovery quality in applications, or model internals.
