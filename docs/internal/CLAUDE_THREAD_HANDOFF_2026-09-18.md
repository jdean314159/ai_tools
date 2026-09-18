# Fresh Claude thread handoff — 2026-09-18

## Read order

1. `AGENTS.md`
2. `docs/design/VISION.md`
3. `docs/internal/STATUS.md`
4. `docs/internal/ROADMAP.md`
5. `rag_lib/README.md`
6. In the sibling `llm-reliability-lab`:
   `docs/planning/THREAD-HANDOVER-2026-09-18-m3-snapshot-binding.md`

## Repository checkpoints

- `ai_tools` implementation checkpoint:
  `ada73c1b3ba22376815d98d97908b78a76e52916`
- sibling reliability-lab implementation checkpoint:
  `5d6640041601ac40c78451c579cacd10dd3b7a9b`
- `origin/main` was `4a659cf1c57c98cef826be3cf45e2ca538a07723`
  before this handoff was committed. The local branch therefore also contains
  the earlier unpushed provenance/RAG-control commit `5ba81d2`.

Recompute identities and inspect the working tree rather than assuming these
remain current. The commit containing this handoff necessarily post-dates the
implementation checkpoint above.

## Completed bounded work

The owner authorized the storage support required by M3's snapshot-binding
contract. `rag_lib` now provides:

- `ChromaStorage.collection_state_inventory()`, a fail-closed complete scan of
  receipt metadata plus a specified digest of every stored dense vector;
- `HybridRetriever.lexical_state_inventory()`, an ordered, text-free digest
  inventory of the active BM25 source corpus; and
- protocol and regression-test coverage for both surfaces.

The dense digest uses finite IEEE-754 binary32, big-endian, with a domain
separator and dimension prefix. The fixed vector `[0.1, -0.0, 1.5]` yields
`sha256:987d0db0aa8fdffb48cc9e71ba51ec2f914516dd696ce21a9fee086e5a5bc308`.
This is an implementation-author test vector pending independent reproduction.

No private corpus was ingested. No retrieval, model call, or benchmark run was
performed.

## Verification reported by the implementation author

- `rag_lib`: 148 passed;
- cross-package integration: 48 passed, 1 optional skip;
- Ruff checks and `git diff --check`: passed.

These results establish local regression behavior, not independent closure.

## Remaining boundaries

1. **Independent verification is owed.** Read the implementation and construct
   separate adversarial cases rather than trusting the reported counts.
2. **Embedding serving identity remains unobserved.** Stored vector bytes are
   bound, but a configured model digest does not establish which model served
   the original embedding call.
3. **The public pipeline surface is incomplete for a real runner.** The
   documented public API is `RAGPipeline`, but it does not compose the dense and
   lexical inventories. A caller would currently reach through private `_store`
   and `_retriever` attributes. Before a real M3 run, design a small public
   observation method and a fabricated cross-repository reopen/mutation test.
   This handoff does not authorize or choose that public contract.
4. **Collection identity is snapshot-scoped.** The logical collection name plus
   complete state digest is sufficient for equality in this benchmark, but is
   not a global Chroma/storage-instance lineage identity.

The reliability lab's broader M3 implementation remains held pending owner
review and approval of M0. Do not infer authority for real ingestion or a model
run from these maintainer-side support changes.
