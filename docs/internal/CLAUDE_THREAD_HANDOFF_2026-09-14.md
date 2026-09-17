# Fresh Claude thread handoff — 2026-09-14

## Read order

1. `AGENTS.md`
2. `docs/design/VISION.md`
3. `docs/internal/STATUS.md`
4. `docs/internal/ROADMAP.md`
5. `docs/projects/llm_engines/SPARK-SPECULATIVE-DECODING-COMPARISON-2026-09-13.md`
6. `docs/internal/CLAUDE_VERIFICATION_HANDOFF_2026-09-01.md` only if the older
   independent-verification ledger is relevant to the requested work

## Repository checkpoint

Before this documentation update, `ai_tools` was clean at
`4a659cf1c57c98cef826be3cf45e2ca538a07723`. The speculative-decoding note,
status update, and handoff changes are new, uncommitted work. Recompute the
identity and inspect the working tree rather than assuming that state persists.

The sibling `llm-reliability-lab` was not clean when this handoff was prepared.
Its M0, curriculum, and RAG snapshot/spec work belongs to the owner and prior
threads. Do not discard or overwrite it. M3 is authorized only as a draft
implementation and remains held until the owner reviews and approves M0.

The RAG snapshot's manifest-digest discrepancy is closed in
`llm-reliability-lab/docs/planning/VERIFICATION-2026-09-11-rag-corpus-snapshot-1.md`.
The authoritative frozen digest begins `15b9989a`; the earlier chat-only
`cb817a3c` value has no retained artifact behind it and must not be cited. Its
exact cause remains unknown rather than inferred.

The previously missing benchmark proposal has since been restored as
`llm-reliability-lab/docs/planning/SPEC-M3-BENCH-01.md`. It remains proposed
and unauthorized, retains the M0 implementation hold, and is excluded from the
frozen corpus by the nine-entry allowlist. Do not infer implementation authority
from the file's presence.

## New result to carry forward

The Spark now has two target-specific DFlash configurations:

- Qwen3-Coder 30B-A3B with its BF16 DFlash drafter, provisional maximum 14;
- Qwen3.8-27B with its Q4_K_M DFlash 2 drafter, maximum 7.

For the one tested Qwen3.8 prompt, DFlash 2 reached a five-run fixed-length
median of 46.888 tokens/s versus 35.054 for MTP and 13.291 without speculation.
A natural-stop run produced identical 322-token decoded content in all three
conditions and measured 64.517, 47.754, and 13.462 tokens/s respectively.
Read the project note for evidence levels, limitations, and the comparison
contract; do not promote the natural-stop check into a general equivalence
claim.

## Operational policy

Use DFlash to shorten new generation-bound Spark experiments when it is held
fixed across every arm. Do not compare an accelerated arm with an
unaccelerated arm and attribute the difference solely to the experimental
intervention. Tokens, not seconds, govern claim-bearing generation budgets.
Record the decoder and draft configuration with the same care as model, seed,
prompt/template, and cache settings.

No code implementation or new model experiment is authorized merely by this
handoff. Existing curriculum and experiment gates remain in force.
