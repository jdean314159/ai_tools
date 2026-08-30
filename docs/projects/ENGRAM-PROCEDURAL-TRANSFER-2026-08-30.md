# Engram procedural experience-transfer experiment — 2026-08-30

## Purpose

Test whether Engram can retrieve a successful prior problem–action–outcome
episode and support applying it to a new analogous incident. This is an
experience-reuse test, not a claim that Engram autonomously induces or stores
general rules.

## Frozen design

- Profile `examples.engram_procedural_transfer`, version 1
- Five operational domains and one live transfer query per domain
- One relevant successful experience plus 36 unrelated incident records
- 440-token prompt budget with 96 tokens reserved for output
- Engram's normal text retrieval and prompt-building path
- Exact uppercase action code and exact supporting experience ID scoring
- Temperature 0, thinking off, seed 47
- No baseline answer, oracle context, oracle model, or LLM judge
- One run; changes or reruns require a new profile version

Missing supporting experience is a retrieval failure. Retrieved experience
followed by a wrong action is an answer-use/transfer failure. Success supports
bounded episodic experience reuse, but does not establish procedural rule
extraction, consolidation, or autonomous policy learning.

Planned artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-procedural-transfer-v1.json`

## Outcome

The sole version-1 run completed against `Qwen3.8-27B-UD-Q4_K_M.gguf`.

- Storage: 5/5
- Supporting experience retrieved: 5/5
- Exact supporting experience ID: 5/5
- Exact action-code match: 2/5
- End to end under the frozen exact scorer: 2/5

The three exact mismatches were `ROTATE_ARCHIVED_LOGS` versus
`ROTATE_ARCHIVED_LOGS_BEFORE_RETRY`, `SYNC_CLOCK` versus
`SYNC_SYSTEM_CLOCK_BEFORE_RETRY`, and `HALVE_BATCH_SIZE_AND_RESUME` versus
`HALVE_BATCH_AND_RESUME_CHECKPOINT`. Each response cited the correct experience
ID, and each observed action is consistent with part or all of its source
experience. Because the source memories described actions in prose but did not
define the expected synthetic action-code vocabulary, this is a label-generation
failure under the pre-registered scorer, not evidence of an Engram storage or
retrieval failure. The frozen score is retained unchanged; no post-hoc semantic
rescore is claimed.

The result supports bounded retrieval and reuse of prior experiences. It does
not validate autonomous general-rule extraction or provide a justification for
extending Engram based on this suite alone. A future distinct profile should
score pre-registered atomic action components rather than require an undefined
canonical label.

Artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-procedural-transfer-v1.json`

File SHA-256:
`5bacd6a04b5ab252cdb7b584ae237066f8140a87b1eb4a038309771df8a7f146`
