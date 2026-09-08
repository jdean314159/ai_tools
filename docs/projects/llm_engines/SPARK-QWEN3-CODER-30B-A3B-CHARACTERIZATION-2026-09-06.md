# Spark Qwen3-Coder 30B-A3B characterization — 2026-09-06

## Scope

This campaign characterized the llama.cpp endpoint label
`Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf` with thinking disabled and
temperature zero. The label is endpoint metadata and a model-file basename; it
is not independent proof of the weights, tokenizer, chat template, or complete
server configuration. The model digest and llama.cpp build commit were not
captured.

The user-reported launch configuration enabled Q4_0 key/value caches, flash
attention, Jinja templates, and draft MTP with a maximum of three draft tokens.
The endpoint reported a 262,144-token context and 30,532,122,624 parameters.
Those endpoint observations were not added to the privacy-bounded artifacts.

## Disclosed invalid preflight

The first four-probe smoke run returned `BackendUnavailableError` for all four
probes because the client process was still inside a local network sandbox. It
did not test the model and is infrastructure-invalid. It is retained rather
than discarded:

- Record ID: `mc_3ae5bf158dc8e16059b481f24ab9e48c`
- Artifact: [invalid smoke run](runs/2026-09-06-spark-qwen3-coder-30b-a3b-characterization-smoke-invalid-v2.json)
- SHA-256: `f5de82788fe54803ebc4899923b2cc2e254d0f81fbd90e4040bcf3f3cb878349`

The unchanged retry outside that network sandbox passed 4/4 probes:

- Record ID: `mc_0753a57bae09b514fd00a6139f360d17`
- Artifact: [valid smoke run](runs/2026-09-06-spark-qwen3-coder-30b-a3b-characterization-smoke-v2.json)
- SHA-256: `2d623f958a08aff270785ce1a43d457f2594e292880dc65e480475c0c157601e`

## Outcomes

The five-run characterization campaign passed all four probes in every
repetition: exact chat, strict structured output, one typed tool call, and token
log probabilities all scored 5/5. Exact-chat latency ranged from 63.101 to
202.891 ms, with a 66.624 ms median.

The single-turn tool-decision campaign passed 12/12 observations. Required
tool use, relevant-tool choice, unnecessary-tool avoidance, and typed argument
construction each passed 3/3.

The multi-turn recovery baseline passed 6/12 with no fabricated-success flags:

| Failure family | Passed |
|---|---:|
| Explicit error | 3/3 |
| Incomplete result | 3/3 |
| Contradictory result | 0/3 |
| Unavailable primary tool | 0/3 |

In the contradiction case the model answered directly instead of calling the
required status tool. In the unavailable-tool case it emitted the primary and
backup calls together instead of following the required primary-then-backup
sequence.

Together with the separately recorded repository assessment, the observed
scores form an ordinal pattern, not a statistical learning curve:

| Task boundary | Score |
|---|---:|
| Basic endpoint capabilities | 20/20 |
| Single-turn tool decisions | 12/12 |
| Multi-turn recovery | 6/12 |
| Repository known-defect recall | 0/3 |

Task definitions, repetition counts, opportunity for external grading, and
required autonomy differ across rows. The table therefore supports a bounded
observation that performance declined as these particular tasks required more
multi-step judgment; it does not isolate the cause or estimate general model
quality.

## Valid artifacts

- Characterization campaign: record `mc_a087741b5a063b717d74ff184ce16fa4`,
  [artifact](runs/2026-09-06-spark-qwen3-coder-30b-a3b-characterization-v2.json),
  SHA-256 `9e2b4f3f7a372cdac3f383626ccba5e4728031acf13ca1c326da4ea251272e93`.
- Tool decisions: record `td_3b715ffc2d06b01d1f2badff08227a4e`,
  [artifact](runs/2026-09-06-spark-qwen3-coder-30b-a3b-tool-decisions-v2.json),
  SHA-256 `79c442ed69a0c267335049e78d0cff4d1c3b85a9c059f6603cd104d93e1929a5`.
- Tool recovery: record `tr_4efc62102d0b67cada54c1b59f1a0ee0`,
  [artifact](runs/2026-09-06-spark-qwen3-coder-30b-a3b-tool-recovery-baseline-v2.json),
  suite digest
  `sha256:dda3e79e229e340928f5fc70571f04c8cc009a410d1106f06874b1a6a4634279`,
  artifact SHA-256
  `f6f13418b369d4037b6f9c54868416799bfc52202b9cb6005959ce498bf7fa59`.

These campaigns use fixed synthetic cases. They do not establish coding
correctness, long-context use, autonomous repository coverage, or comparative
superiority over another model.
