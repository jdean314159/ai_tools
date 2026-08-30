# Engram trust-label prompt-budget pressure — 2026-08-30

## Question and frozen boundary

How much crowded-context capacity is lost to Engram's enabled trust boundary
when every retrieved record is legitimate and fully conforms to policy?

Profile `examples.engram_trust_prompt_pressure`, version 3 freezes nine pairs:
budgets of 180, 260, and 420 approximate word-count tokens crossed with 2, 5,
and 10 accepted memories. Each condition reserves 64 output tokens. Retrieval is
a fixed ranked list so the experiment isolates composition rather than search
quality. The single answer-bearing record ranks first; the remainder are benign,
conforming distractors of comparable length.

Each pair runs with policy off and policy on. Policy on adds the production
boundary instruction and visible `evidence_id`, trust, tenant, source, and writer
labels. The profile records candidate, included, and excluded memory counts,
prompt and memory token estimates, compression/starvation, exact value/citation,
and the primary failure stage. It retains no raw prompts, memories, outputs,
endpoint, or local model path.

## Predeclared gate

The gate requires the highest-ranked answer evidence to survive composition in
all 18 conditions and exact value plus evidence-ID output in both 420-token
reference conditions at every density. Lower-budget model accuracy remains
descriptive so composition pressure is not confused with inference failure.
The run uses thinking off, temperature zero, seed 89, exact scoring, and no
oracle or LLM judge.

This is a bounded synthetic characterization. Word-count estimates are not the
served model's tokenizer, fixed retrieval excludes ranking variance, and the
result cannot estimate production workload prevalence.

## Disclosed run history

Version 1 used the frozen cases and passed deterministic preflight, but all 18
inference attempts returned `BackendUnavailableError` because the Python process
did not have network access. Retrieval and composition completed, but no model
inference occurred, so the failed gate is infrastructure-invalid and not an
Engram or model result. The privacy-safe artifact is retained rather than
overwritten:

`docs/projects/runs/2026-08-30-spark-qwen-engram-trust-prompt-pressure-v1.json`

SHA-256: `2a6bac3dae16ba6b36cfd0889125c15c36e4a828406ace8849ad62cc83b4095e`

Version 2 changed only the profile version and execution environment. All 18
model calls completed. Values were correct in 18/18 conditions and policy-on
citations were correct in 9/9, but policy-off citations were correct in 0/9.
Inspection showed that the control record text omitted its `evidence_id`; only
the policy-on provenance label exposed it. The exact-citation comparison was
therefore invalid even though the capacity measurements remained usable. The
artifact is retained:

`docs/projects/runs/2026-08-30-spark-qwen-engram-trust-prompt-pressure-v2.json`

SHA-256: `112200a73480e4330667576aba5a172ead137bec0680945978c61c4a1ae913e8`

Version 3 adds the synthetic evidence ID to each record's text so both
conditions can cite it. Budgets, density, ranking, seed, scorer, privacy
contract, and gate remain unchanged. The suite digest changes because the
frozen input text changed.

## Version-3 outcome

The llama.cpp-hosted `Qwen3.8-27B-UD-Q4_K_M.gguf` run passed its frozen gate.
All 18 calls completed and reported seed acceptance. The relevant first-ranked
record reached the prompt and produced the exact value and evidence ID in every
condition, including all six 420-token reference conditions.

| Budget | Memories | Policy off included | Policy on included | Difference |
|---:|---:|---:|---:|---:|
| 180 | 2 | 2 | 1 | -1 |
| 180 | 5 | 3 | 1 | -2 |
| 180 | 10 | 3 | 1 | -2 |
| 260 | 2 | 2 | 2 | 0 |
| 260 | 5 | 5 | 2 | -3 |
| 260 | 10 | 6 | 2 | -4 |
| 420 | 2 | 2 | 2 | 0 |
| 420 | 5 | 5 | 5 | 0 |
| 420 | 10 | 10 | 6 | -4 |

The trust boundary caused no loss at the two-memory density once the budget
reached 260 tokens and no loss at five memories at 420 tokens. At ten memories,
policy on displaced four otherwise accepted records at both 260 and 420 tokens.
This establishes real capacity pressure in the tested word-count budgets while
also showing that ranked item packing preserved the first relevant record.

Artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-trust-prompt-pressure-v3.json`

SHA-256: `5b2bd4f97355044da97fc8d733fa713071cd43c74d80529c9c0ab74328381765`
