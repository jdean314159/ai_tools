# Spark Ornith 1.5 35B characterization — 2026-09-07

## Scope

This campaign characterized the llama.cpp endpoint label
`Ornith-1.5-35B-Q4_K_M.gguf` with thinking disabled and temperature zero. The
label and endpoint metadata are not independent proof of the weights,
tokenizer, or chat template, and the remote model digest was unavailable.

The endpoint reported llama.cpp build `b10679-50f068fff`, 35,505,251,456
parameters, Q4_K_M weights, four slots, and a 262,144-token context. The
user-reported launch configuration used Q4_0 key/value caches, flash attention,
Jinja templates, and the MTP flags accepted by the server. However, `/props`
reported only the default `speculative.types` value `none`, while the
post-campaign `/slots` response reported `speculative: true` and effective
`speculative.types` of `none,draft-mtp` for all four slots. Slot-level evidence
therefore confirms that draft MTP was active. The engine capability probe's
`speculative_decoding: false` describes the OpenAI adapter's declared control
surface, not the server's independently configured behavior.

## Outcomes

The initial one-run smoke test passed exact chat, strict structured output, one
typed tool call, and token log probabilities. The unchanged five-run
characterization then passed all four probes in every repetition, for 20/20
observations. Exact-chat latency ranged from 200.518 to 315.349 ms, with a
218.516 ms median.

The unchanged single-turn tool-decision campaign passed 12/12 observations:
required tool use, relevant-tool choice, unnecessary-tool avoidance, and typed
argument construction each passed 3/3.

The unchanged multi-turn recovery baseline passed 12/12, with no
fabricated-success flags:

| Failure family | Passed |
|---|---:|
| Explicit error | 3/3 |
| Incomplete result | 3/3 |
| Contradictory result | 3/3 |
| Unavailable primary tool | 3/3 |

On these exact frozen suites, Ornith passed 44/44 observations while the prior
Qwen3-Coder 30B-A3B campaign passed 38/44: both passed basic characterization
and single-turn decisions, while recovery was Ornith 12/12 versus Qwen3-Coder
6/12. This is a sequential endpoint comparison with different model files and
does not isolate architecture, quantization, server-state, or latency effects.
It establishes neither general coding quality nor repository-assessment
ability.

## Durable artifacts

- Smoke: record `mc_89253775d9499e1a1b62296b5b648643`,
  [artifact](runs/2026-09-07-spark-ornith-1.5-35b-characterization-smoke-v2.json),
  SHA-256 `75678e35af4276f73405e81eab619d25437d87c85ce3612d0b5901907ef3e2aa`.
- Characterization: record `mc_c4a70f2cdb44ea90e07fe95244c7095b`,
  [artifact](runs/2026-09-07-spark-ornith-1.5-35b-characterization-v2.json),
  SHA-256 `9c6be2d0bbd2e35e3672ea31770b931591227979189d159634ac29f2e41707cb`.
- Tool decisions: record `td_69b4a7179a94bba135c47d0eb5335b9b`,
  [artifact](runs/2026-09-07-spark-ornith-1.5-35b-tool-decisions-v2.json),
  SHA-256 `73906e1d9235864a48067d70bc062bb80aecb96115c76caf0b77fe6262c5bd28`.
- Tool recovery: record `tr_41983f803fdae35a9e212c58920d543d`,
  [artifact](runs/2026-09-07-spark-ornith-1.5-35b-tool-recovery-baseline-v2.json),
  suite digest
  `sha256:dda3e79e229e340928f5fc70571f04c8cc009a410d1106f06874b1a6a4634279`,
  artifact SHA-256
  `1a31925997c15b622959d648bd51ac3a3a2771976a832c813d66af32757528ff`.

The artifacts are privacy-bounded: they omit raw prompts, responses, argument
values, endpoint URLs, host paths, secrets, and exception messages.
