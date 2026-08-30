# Engram temporal reliability and shared memory evaluation — 2026-08-30

## Outcome

Engram now supports explicit, deterministic temporal episode versioning without
an LLM dependency. `store_temporal_episode(...)` retains prior topic versions
and records action, status, validity, and supersession metadata. Current-state
search suppresses superseded predecessors; `include_historical=True` exposes
the retained history. This does not infer arbitrary semantic contradiction:
callers must provide a stable topic key and temporal action.

Prompt construction now packs ranked memory items individually under pressure
instead of admitting or dropping an entire memory layer. Results expose
candidate, included, and excluded counts plus an explicit `memory_starved`
signal. Evidence traces carry structured episode provenance, and search traces
report temporal filtering and unresolved same-topic active conflicts.

`llm_harness_core` now owns dependency-free staged memory-evaluation contracts.
They deterministically attribute storage, retrieval, composition, inference,
and exact-scoring failures, emit stable issue codes and privacy-minimized report
bodies, and refuse governed artifact overwrite. Engram's
`observation_from_engram(...)` adapter converts real search and prompt results
into that shared contract.

## Compatibility

- Existing `store_episode(...)` topic-replacement behavior is unchanged.
- Temporal retention is opt-in through `store_temporal_episode(...)`.
- Existing prompt result fields remain; diagnostics and `included_items` are
  additive.
- Existing `search_episodes(...)` callers retain current-state behavior; the
  historical flag is additive.
- No model, embedding, Torch, or network dependency was added.

## Verification

- Engram plus `llm_harness_core`: 246 passed, 7 skipped live embedding tests.
- Repository-wide: 1,235 passed, 292 skipped, 3 existing multiprocessing
  deprecation warnings.

The subsequent paired live validation found obsolete evidence in 3/3 legacy
current-state prompts and 0/3 temporal prompts. Temporal mode retained both
historical queries, preserved 5/5 exact answer scoring, and reduced aggregate
prompt tokens by 11.8%. See `docs/projects/ENGRAM-TEMPORAL-AB-2026-08-30.md`.

Cold-reopen validation with cached MiniLM embeddings and real ChromaDB then
passed current filtering, historical retrieval, prompt provenance, and
persisted metadata in 3/3 timelines. See
`docs/projects/ENGRAM-TEMPORAL-VECTOR-COLD-2026-08-30.md`.
