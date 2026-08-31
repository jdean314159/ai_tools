# Spark Qwen3.8 Flash-Next context retention — 2026-08-31

## Frozen boundary

Profile `llm_engines.context_retention_campaign`, version 1, tests start/end
retention and server-reported prompt usage with 1,024, 8,192, and 32,768
synthetic filler words. Each case requests strict JSON at temperature zero,
thinking off, seed 101, and a 64-token output budget.

The gate requires no request errors, exact recovery of both boundary values,
positive input-token reporting, and strictly increasing input-token counts.
Raw prompts, outputs, boundary values, endpoint locators, and host paths are not
retained.

This is deliberately below the endpoint's advertised 262,144-token context. It
characterizes safe-range retention and adapter/server usage agreement; it does
not establish the maximum accepted context, tokenizer identity, or behavior at
the truncation boundary.

## Outcome

The sole version-1 run passed every gate:

| Filler words | Reported input tokens | Exact boundaries | Latency |
|---:|---:|---:|---:|
| 1,024 | 1,070 | Yes | 2,655.584 ms |
| 8,192 | 8,238 | Yes | 10,826.523 ms |
| 32,768 | 32,814 | Yes | 38,015.953 ms |

All responses stopped normally, used 24 output tokens, and reported seed status
`accepted`. Input-token counts were positive and strictly increasing. Both
boundary values were returned exactly in every case, providing no evidence of
unexpected truncation within this tested range.

The timing increase is descriptive prompt-processing behavior for repeated
synthetic filler. It is not a general throughput benchmark. In particular, the
run does not test maximum-context rejection, server-side automatic truncation,
attention quality throughout the middle of a long prompt, or the advertised
262,144-token boundary.

Artifact:
`docs/projects/llm_engines/runs/2026-08-31-spark-qwen38-flash-next-context-retention-v1.json`

- Record ID: `cr_008282914fcede529889de69657f4e19`
- SHA-256: `adfaab32d1b04de829212bf3831bf69ecf35d84eca0f387f566082f5d59575eb`
