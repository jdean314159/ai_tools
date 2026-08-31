# Spark Qwen3.8 Flash-Next tool decisions — 2026-08-31

## Scope

The unchanged version-2 `llm_engines.tool_decision_campaign` ran against the
Spark endpoint reported as `Qwen3.8-Flash-Next-UD-IQ4_XS`. Four fixed cases
measure required tool use, choosing between relevant and irrelevant tools,
avoiding unnecessary tool use, and constructing typed arguments. Each case ran
three times per condition at temperature zero. Tools were never executed.

Thinking off was the advancement condition. Because all 12 decisions passed,
the separately disclosed thinking-on condition ran with the same cases,
repetitions, and scorer. Artifacts omit prompts, responses, argument values,
endpoint locators, host paths, API keys, and exception messages.

## Outcome

Every case passed in both conditions:

| Case | Off passed | Off median | On passed | On median |
|---|---:|---:|---:|---:|
| Required single tool | 3/3 | 1,299.837 ms | 3/3 | 2,497.958 ms |
| Choose relevant tool | 3/3 | 1,748.598 ms | 3/3 | 3,110.744 ms |
| Avoid unnecessary tool | 3/3 | 297.462 ms | 3/3 | 1,708.129 ms |
| Typed arguments | 3/3 | 1,610.117 ms | 3/3 | 2,629.517 ms |

Thinking increased median latency in all four cases without producing an exact
outcome difference. The off condition was already at ceiling, so improvement
was not measurable; the campaign could only detect regression. Conditions ran
sequentially, off before on, without randomized order or independent server-load
instrumentation. Latency differences are descriptive, not causal.

This validates the four observable decisions on this endpoint. It does not
establish application tool reliability, recovery after tool results, hidden
reasoning quality, or general planning ability.

## Artifacts

| Condition | Record ID | SHA-256 |
|---|---|---|
| Thinking off | `td_a52d8596f5dc6f478514c58ff482d861` | `75e080cf4cddf5e49d74dd015db1642d3e58f4b0a16382e50421b4c06fd0e7ab` |
| Thinking on | `td_dd5e557b627899a046a62be8f13d8f3a` | `dcb1bd67e6fd5b32e3bc61690b23067af9f106859de32edcbdb185780200d3e9` |

Both files are under `docs/projects/llm_engines/runs/`.
