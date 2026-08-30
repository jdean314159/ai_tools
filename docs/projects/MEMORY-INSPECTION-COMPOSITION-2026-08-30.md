# Memory/inspection composition experiment — 2026-08-30

## Purpose

Test whether the remote llama.cpp model safely changes an answer when synthetic
project memory is added through Engram, while Inspector records which memory
entered the prompt. This is a bounded composition test, not a general memory-
quality or model-quality claim.

## Frozen cases

Five synthetic cases use unrelated projects and value types:

| Case | Fact | Current value | Superseded distractor |
|---|---|---|---|
| `atlas_region` | deployment region | `eu-central-1` | `us-west-2` |
| `beacon_retention` | retention period | `45 days` | `90 days` |
| `cedar_escalation` | escalation team | `ORANGE` | `BLUE` |
| `delta_window` | maintenance time | `03:30 UTC` | `01:00 UTC` |
| `ember_format` | export format | `PARQUET` | `CSV` |

Each memory condition contains one explicitly current fact and one explicitly
superseded fact. Synthetic memory IDs are included in their text so Inspector
can prove which items entered the prompt without retaining raw memory text.

## Conditions and order

- Profile: `examples.memory_inspection_composition`, version 1
- Endpoint: the OpenAI-compatible llama.cpp server on the DGX Spark
- Model: the currently served Qwen GGUF label, reduced to its basename in the artifact
- Order: all baseline cases, then all memory cases
- Thinking: off
- Temperature: 0
- Requested seed: 23
- One observation per distinct case and condition
- No intentional concurrent load

The baseline receives the question and an instruction to return `UNKNOWN` and
`NONE` when supplied context does not establish the answer. The memory
condition receives Engram's assembled prompt for the same question. Both must
return the same strict JSON schema: `value` and `memory_id` strings.

## Scoring

- Baseline-safe: exact normalized `UNKNOWN` value and `NONE` memory ID.
- Memory-correct: exact current value and relevant memory ID.
- Trace-grounded: Inspector reports the relevant memory ID in included evidence
  and the final prompt section contains that ID.
- Distractor-used: the answer equals the superseded value or cites its memory ID.
- Paired success: baseline-safe, memory-correct, trace-grounded, and not
  distractor-used.

The primary outcome is paired-success count out of five. Latency, token use,
selected-memory counts, and whether the distractor entered the prompt are
descriptive. No minimum effect or thinking comparison is authorized.

## Privacy and artifact

The artifact retains case IDs, condition, normalized scored values, expected
synthetic IDs, selected synthetic IDs, booleans, token counts, latency, seed
status, model basename, suite digest, and aggregate counts. It omits endpoint
URL, host paths, raw prompts, raw responses, raw memory text, secrets, and
exception messages.

Planned artifact:
`docs/projects/runs/2026-08-30-spark-qwen-memory-inspection-v1.json`

## Version-1 execution failure

Version 1 produced no retained result. Its first invocation was interrupted by
the user before completion and left no process or artifact. The unchanged
restart completed inference but failed before persistence because the planned
artifact's parent directory did not exist. No summary was printed because
artifact writing preceded summary output. These attempts cannot support an
outcome claim and v1 must not be run again.

Version 2 changes no case, prompt, scorer, model condition, or order. It creates
and validates the artifact destination before constructing the engine or making
an inference request, records `prior_unretained_attempts: 2`, and writes to:
`docs/projects/runs/2026-08-30-spark-qwen-memory-inspection-v2.json`.

## Stop rule

Run this profile once. Record the result without editing cases or scorer. Any
rerun, changed case, additional condition, or claimed comparison requires a new
work order and profile version. Version 2 is the sole authorized retry after
the disclosed version-1 execution failure.

## Version-2 outcome

The retained version-2 run completed all five baseline cases followed by all
five memory cases. Baseline-safe, memory-correct, trace-grounded, and paired
success were each 5/5. Inspector showed that both the relevant memory and its
superseded distractor entered every memory prompt. The model returned the
current value and relevant memory ID in all five cases and used no distractor.
All ten calls reported seed acceptance.

This supports only the frozen composition proposition: on these five synthetic
cases, Engram supplied inspectable context and the served endpoint selected the
explicitly current fact over an explicit superseded distractor. It does not
establish general memory quality, conflict resolution, or deterministic model
behavior. The two prior unretained attempts remain an execution limitation.

Artifact:
`runs/2026-08-30-spark-qwen-memory-inspection-v2.json`

File SHA-256:
`1fc7e20b98875e3e7128337dea6b78e9d387a556d0541a80bbb9248e2384055c`
