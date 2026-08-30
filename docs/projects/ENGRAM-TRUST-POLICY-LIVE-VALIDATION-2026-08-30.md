# Engram trust-policy live validation — 2026-08-30

## Purpose

Validate the opt-in persistent-memory trust boundary against the same five
frozen synthetic attack families used for the original DGX Spark
characterization. The paired run uses the llama.cpp-hosted
`Qwen3.8-27B-UD-Q4_K_M.gguf`, temperature zero, thinking off, and seed 61.
There is no oracle, semantic judge, or LLM judge.

The policy-off condition is the control. Policy on requires verified trust,
the case's authorized tenant, the verified-decision source, and the operator
writer; violations are rejected. The security gate requires zero poison
retrieval and zero poison prompt inclusion. The final combined gate also
requires exact value and evidence-ID output in 5/5 cases.

## Disclosed run history

Version 2 was the first paired live run. Its predeclared security gate passed:
policy-on poison exposure fell to zero. Exact output, however, fell from 5/5 to
1/5, so the result was not treated as a clean overall success.

Version 3 added only privacy-safe `value_correct` and `citation_correct`
booleans plus an explicit utility gate. It reproduced the behavior and showed
that value selection remained correct in 5/5 cases while exact evidence-ID
citation was correct in only 1/5. This attributed the regression to prompt
provenance/citation rather than retrieval or answer selection.

Inspection then found that Engram's visible provenance label omitted the
application's `evidence_id`. The implementation was corrected to include that
field when present. Version 4 retained the same cases, engine settings, scorer,
and combined gate.

## Version-4 outcome

| Measure | Policy off | Policy on |
|---|---:|---:|
| Poison stored | 5/5 | 0/5 |
| Poison retrieved | 5/5 | 0/5 |
| Poison included in prompt | 5/5 | 0/5 |
| Model compromise | 0/5 | 0/5 |
| Correct value | 5/5 | 5/5 |
| Correct evidence ID | 5/5 | 5/5 |
| Exact answer plus citation | 5/5 | 5/5 |
| End-to-end memory contract | 0/5 | 5/5 |

Both the security and utility gates passed. This validates the configured
policy on these five cases; it is not evidence of general prompt-injection
security or multi-tenant isolation beyond the tested boundary.

## Artifacts

- Version 2: `docs/projects/runs/2026-08-30-spark-qwen-engram-memory-security-policy-v2.json`
  SHA-256: `a67d6d37252737073a850efcc7d5451efdfa40e9e2a9cba9978386e67c6f5bce`
- Version 3: `docs/projects/runs/2026-08-30-spark-qwen-engram-memory-security-policy-v3.json`
  SHA-256: `714548066045ac2c4a19822ed72ea0172e262d841374cf0f51e0bb7aad033214`
- Version 4: `docs/projects/runs/2026-08-30-spark-qwen-engram-memory-security-policy-v4.json`
  SHA-256: `2f9b2e8565598a6e99498cd84cf1ff3aa0470813b1a4c62df3aa03c52e3f2a31`

All artifacts omit endpoint URLs, raw prompts, raw memories, raw outputs, and
local model paths. The failed intermediate artifacts are retained to avoid
survivorship bias.
