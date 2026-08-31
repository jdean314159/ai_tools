# Spark Qwen3.8 Flash-Next characterization — 2026-08-30

## Scope

This is a new-model baseline using the unchanged version-2
`llm_engines.model_characterization_campaign` previously run against the
27B model. The Spark endpoint reported the served label
`Qwen3.8-Flash-Next-UD-IQ4_XS`. That label is endpoint metadata, not independent
proof of weights, template, tokenizer, or quantization identity.

The campaign ran five repetitions with thinking off and temperature zero. Each
repetition exercised exact chat, strict structured output, one typed tool call,
and token log probabilities. No prompts, responses, endpoint locator, host
paths, API keys, or exception messages are retained.

## Outcome

All four probes passed in all five repetitions:

| Probe | Passed | Stability |
|---|---:|---|
| Exact chat | 5/5 | Stable |
| Structured output | 5/5 | Stable |
| Tool call | 5/5 | Stable |
| Token log probabilities | 5/5 | Stable |

Exact-chat latency ranged from 337.2 to 434.179 ms, with a 361.603 ms median.
The earlier 27B campaign reported 441.937–616.256 ms and a 477.304 ms median.
This is a descriptive comparison across sequential campaigns on different
dates; server load was not independently instrumented, order was not
randomized, and the difference is not a causal performance estimate.

The result validates these four observable endpoint capabilities on fixed
synthetic probes. It does not establish general task quality, tool-selection
quality with competing tools, thinking-on behavior, or long-context behavior.

## Artifact

`docs/projects/llm_engines/runs/2026-08-30-spark-qwen38-flash-next-characterization-v2.json`

- Record ID: `mc_9215fdc63311eb2eb7d5202f07f1b760`
- SHA-256: `8f25d1143cfd6aa115f3a557033ae7957bacf81610792df1a36b2b3a2bb58c11`
