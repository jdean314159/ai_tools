# Spark Qwen characterization — 2026-08-29

## Scope

These artifacts record privacy-bounded synthetic probes against one
OpenAI-compatible llama.cpp endpoint serving a model reported as
`Qwen3.8-27B-UD-Q4_K_M.gguf`. The label does not establish weight, tokenizer,
template, quantization, or runtime identity.

The artifacts omit the endpoint locator, host paths, prompts, responses,
argument values, API keys, and exception messages. A repository scan found
none of the private address, home path, username, or fixed synthetic prompt and
argument strings in the committed JSON candidates.

## Artifacts

| Artifact | Record ID | File SHA-256 |
|---|---|---|
| Five-run characterization, thinking off | `mc_2e3e4e6dc05e8fd6b1d887163eaebcb7` | `c75cdade1a7ddac6e4e41f2fce299947a469672235255bacc435e956aaf8d591` |
| Three-run tool decisions, thinking off | `td_88d026e6ac1ad4bb8e5dc48999c00cf1` | `74d2c9695bc93b98129891bc224a15aff64328458dd65b3ce1ed2686445ceb73` |
| Three-run tool decisions, thinking on | `td_faafaf8594842271b4872be4cc4a14e2` | `422cc712db194094ef94c10711a80d374732a1849f00446d3bc49273d41ff8ed` |

The exact JSON files are under `docs/projects/llm_engines/runs/`.

## Observations

The characterization campaign passed chat, structured-output, tool-call, and
logprob probes in all five repetitions. The chat probe's observed latency was
441.937–616.256 ms, with a 477.304 ms median.

The tool campaign used four fixed cases repeated three times per condition.
Every case passed in both conditions. The thinking-off baseline was therefore
already at ceiling; the experiment could detect regression but not improvement.
Thinking increased the observed median latency in every case:

| Case | Thinking off | Thinking on |
|---|---:|---:|
| Required single tool | 1244.351 ms | 2134.990 ms |
| Choose relevant tool | 1613.301 ms | 4036.467 ms |
| Avoid unnecessary tool | 445.208 ms | 1657.456 ms |
| Typed arguments | 1535.272 ms | 2223.671 ms |

The two timing conditions ran sequentially against the same endpoint, off
first and on second. No concurrent campaign was intentionally running. Server
load was not independently instrumented, the order was not randomized, and
only three repetitions were collected. The values are descriptive, not a
causal estimate or confidence interval.

## Open control gap

`GenerationRequest` has no seed field. These campaigns use temperature zero
and fixed prompts but cannot separate sampler variation from runtime or
hardware variation. Adding a cross-backend seed contract remains a separate
compatibility decision; these artifacts make no deterministic-generation
claim.
