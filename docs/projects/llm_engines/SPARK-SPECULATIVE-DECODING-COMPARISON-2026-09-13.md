# Spark speculative-decoding comparison — 2026-09-13

## Scope and evidence boundary

This note records two user-run llama.cpp experiments on the Spark: a DFlash
draft-length sweep for Qwen3-Coder and a same-target baseline/MTP/DFlash 2
comparison for Qwen3.8-27B. The retained numbers below were transcribed from
response summaries and GGUF metadata excerpts supplied in the working
conversation. The raw response files remain under the Spark's temporary
storage and are not committed here. The llama.cpp commit and local model-file
digests were not captured, so these results are descriptive and are not a
reproducible benchmark packet.

No endpoint locator, private host path, prompt response, or model-generated
prose is retained in this document. Model locators are sanitized filenames.

## Common request and server controls

The reported tests used one llama.cpp server slot, full GPU offload, a 32,768
token context, Q4_0 K/V caches, flash attention, Jinja chat templating,
temperature zero, seed 42, prompt caching disabled, and thinking disabled. The
prompt requested a typed Python merge function with three assertions.

The Qwen3.8 fixed-length protocol ran one warm-up followed by five measured
requests per condition. Each request forced 512 completion tokens with
`ignore_eos: true`. The natural-stop check used the same request with
`ignore_eos: false`; one run was retained per condition.

## Qwen3-Coder DFlash draft-length sweep

Target:
`Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf`.

Drafter:
`Qwen3-Coder-30B-A3B-DFlash-bf16.gguf`.

The baseline and DFlash maximum-three conditions are five-run medians. The
maximum-eight, -twelve, -fourteen, and -fifteen rows are single responses. Only
throughput was retained for maximum ten. The rows therefore locate a useful
region for this prompt; they do not establish a general or statistically
resolved optimum.

| Condition | Generation tokens/s | Generation ms | Draft acceptance | Evidence |
|---|---:|---:|---:|---|
| No speculation | 83.437 | 6,124.346 | — | five-run median |
| DFlash, maximum 3 | 113.808 | 4,490.029 | 1,800/2,235 = 80.54% | five-run median and aggregate |
| DFlash, maximum 8 | 160.418 | 3,185.421 | 441/554 = 79.60% | one run |
| DFlash, maximum 10 | 170.3 | not retained | not retained | one reported value |
| DFlash, maximum 12 | 184.128 | 2,775.248 | 457/645 = 70.85% | one run |
| DFlash, maximum 14 | **189.608** | **2,695.039** | 459/723 = 63.49% | one run |
| DFlash, maximum 15 | 182.615 | 2,798.241 | 458/774 = 59.17% | one run |

Maximum fourteen was selected as the provisional operational setting for this
target. It was 2.27 times the five-run baseline throughput in the observed
single response. This setting remains workload-specific and should be
revisited if representative prompts show a different optimum.

The sweep treated 15 as the effective ceiling for this drafter's 16-position
block. The supporting local metadata excerpt was not retained in this
checkout, so that ceiling should be rechecked when the model and build digests
are captured. An early baseline-versus-DFlash content-hash comparison used
responses with different lengths and finish reasons; it was not a controlled
identity test and supplies no equivalence finding.

## Qwen3.8 same-target comparison

Target: `Qwen3.8-27B-UD-Q4_K_M.gguf`.

The target's user-reported GGUF metadata was:

```text
general.architecture = qwen35
qwen35.block_count = 65
qwen35.nextn_predict_layers = 1
```

The MTP condition used the target's embedded NextN layer with
`--spec-type draft-mtp --spec-draft-n-max 7`.

DFlash 2 drafter: `Qwen3.8-27B-DFlash2-Q4_K_M.gguf`.

The drafter's user-reported metadata was:

```text
general.architecture = dflash
dflash.block_size = 8
dflash.selector_rank = 256
dflash.selector_top_k = 16
```

The DFlash 2 condition used `--spec-type draft-dflash` and a maximum of seven
draft tokens. Seven is the effective ceiling for this drafter: its eight-token
block contains one anchor and seven draft positions.

### Fixed-length throughput

| Condition | Median tokens/s | Median generation ms | Aggregate draft acceptance | Speedup over baseline |
|---|---:|---:|---:|---:|
| No speculation | 13.291 | 38,446.252 | — | 1.00x |
| MTP, maximum 7 | 35.054 | 14,577.577 | 2,065/3,405 = 60.65% | 2.64x |
| DFlash 2, maximum 7 | **46.888** | **10,898.229** | 2,075/3,335 = 62.22% | **3.53x** |

DFlash 2 produced 33.8% greater median throughput than MTP and reduced median
generation time by 25.2% relative to MTP. Relative to no speculation, DFlash
2 produced 252.8% greater throughput and reduced median generation time by
71.7%.

Within each condition, all five decoded-content SHA-256 values matched. MTP
and DFlash 2 shared one content digest; the baseline digest differed. A text
diff located the difference only in the final explanatory paragraph. The
function and assertions matched, and both responses were truncated mid-sentence
after `ignore_eos: true` forced generation beyond the natural stop. These are
digests of decoded response content, not token-ID sequences.

### Natural-stop check

| Condition | Completion tokens | Finish reason | Generation tokens/s |
|---|---:|---|---:|
| No speculation | 322 | `stop` | 13.462 |
| MTP, maximum 7 | 322 | `stop` | 47.754 |
| DFlash 2, maximum 7 | 322 | `stop` | **64.517** |

All three decoded responses had SHA-256
`96b5a8a8f720b48787758f353d3792e027640db1e926ea7fb07fc312bea1f8e7`.
Thus the three conditions produced byte-identical decoded content, the same
length, and the same finish reason for this natural-stop request. DFlash 2 was
4.79 times the baseline throughput and 35.1% faster than MTP in the retained
single response.

The natural-stop result does not establish general exact-token or
distributional equivalence. It shows content identity for one prompt. The
fixed-length difference is not contradictory: that protocol forced another
190 tokens beyond the point at which every natural-stop condition terminated.

## Operational decision and comparison contract

DFlash is the provisional Spark accelerator for future generation-bound
experiments:

- Qwen3-Coder uses DFlash with `--spec-draft-n-max 14` as a workload-derived
  provisional default.
- Qwen3.8-27B uses DFlash 2 with `--spec-draft-n-max 7`, the drafter's maximum.
- MTP remains a strong Qwen3.8 fallback that needs no external drafter.

The accelerator is a fixed condition within a campaign, not a knob changed
between intervention arms. A run record must identify at least the target and
draft model digests, llama.cpp commit, speculative type, maximum draft length,
prompt and template identity, sampling parameters and seed, context and cache
configuration, drafted and accepted counts, termination reason, token counts,
throughput, and wall time. Tokens, not elapsed seconds, govern any experimental
generation budget; wall-clock time remains an operational measurement.

Cross-decoder comparisons require a separate paired check. New campaigns that
hold DFlash fixed across every arm do not depend on identity with a
no-speculation run. Occasional natural-stop task-correctness canaries remain
appropriate. Distributional equivalence is assumed neither from the
algorithm nor from this bounded test and need not be studied unless a later
claim depends on it.

## Remaining reproducibility gaps

Before promoting these observations into a canonical benchmark artifact:

1. record the exact llama.cpp commit and build fingerprint;
2. record target and drafter file digests;
3. retain the request bodies, per-run summaries, client wall times, and server
   metrics under sanitized locators;
4. rerun natural-stop cases across representative experimental prompts; and
5. distinguish decoded-content equality from token-ID equality in every
   reported claim.
