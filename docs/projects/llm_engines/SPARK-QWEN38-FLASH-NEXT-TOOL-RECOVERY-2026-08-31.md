# Spark Qwen3.8 Flash-Next tool-recovery baseline — 2026-08-31

## Scope

The valid frozen version-2 `llm_engines.tool_recovery_campaign` baseline ran
against the Spark endpoint reported as `Qwen3.8-Flash-Next-UD-IQ4_XS`. The
profile covers an explicit transient error, a contradictory successful result,
an unavailable tool with a named alternative, and an incomplete result that
requires targeted follow-up.

Each case ran three times with thinking off, temperature zero, requested seed
7, and at most two model turns. Tools were not executed; fixed synthetic tool
results were injected. The scorer requires the exact recovery action and rejects
fabricated success.

The predeclared headroom rule is unchanged: a zero or 12/12 ceiling result stops
the experiment. Only a primary pass rate strictly between zero and one could
permit design of a later matched comparison; it would not itself authorize a
thinking-on run.

## Outcome

The baseline reached ceiling:

| Failure family | Passed |
|---|---:|
| Explicit error | 3/3 |
| Contradiction | 3/3 |
| Unavailable tool | 3/3 |
| Incomplete result | 3/3 |

Primary recovery was 12/12, fabricated success was 0/12, and all 24 model turns
reported seed status `accepted`. Seed acceptance is not a deterministic-output
claim.

Per the frozen rule, the campaign stops. No thinking-on comparison was run, and
the stopped version-4 development suite was not reopened or tuned. This result
validates recovery only on four small synthetic families; it does not establish
application reliability or recovery from arbitrary tool failures.

## Artifact

`docs/projects/llm_engines/runs/2026-08-31-spark-qwen38-flash-next-tool-recovery-baseline-v2.json`

- Record ID: `tr_d11e1519f732d06534efd9dd0f152212`
- SHA-256: `1530cc7579d7b13e9059690178036594b497da9a333fd0dd5a4cf9c3a046c6a5`

The artifact omits prompts, responses, injected result values, reasoning,
endpoint locators, host paths, API keys, and exception messages.
