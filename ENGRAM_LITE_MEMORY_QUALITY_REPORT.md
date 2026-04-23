# engram_lite memory quality pass

This pass improves `engram_lite`'s memory behavior without turning it into full `engram`.

## Changes made

- Added lightweight memory-quality helpers in `engram_lite.memory.quality`:
  - ingestion/importance scoring
  - ephemeral filtering
  - text normalization
  - near-duplicate similarity scoring
  - ranked retrieval scoring
  - retrieval-time diversity filtering
- Updated `ProjectMemory` to use those controls:
  - optional auto-ingest of high-value turns from `add_turn(...)`
  - store-time filtering in `store_episode(...)`
  - store-time near-duplicate blocking
  - internal episodic retrieval scoring in `search_episodes(...)`
  - internal episodic retrieval is now merged into prompt-building, even when no external retriever is configured
  - quality stats exposed through `get_stats()`
- Updated the interop descriptor so `engram_lite` advertises lightweight ingestion and deduped retrieval.
- Updated docs:
  - `engram_lite/README.md`
  - `CURRENT_STATE.md`
  - `ROADMAP.md`

## Validation

- `python -m compileall -q engram_lite llm_inspector_ui language_tutor`
- `PYTHONPATH=engram_lite/src:llm_harness_core/src pytest -q engram_lite/tests` → 52 passed
- `PYTHONPATH=. pytest -q llm_inspector_ui/tests` → 23 passed
- `PYTHONPATH=. pytest -q language_tutor/tests` → 16 passed, 1 skipped

## What this does not do yet

- It does not import the full `engram` lifecycle stack.
- It does not add semantic memory or multi-tier archival to `engram_lite`.
- It does not prove answer-quality uplift yet.

## Recommended next step

Build the memory evaluation harness to compare:

1. older `engram_lite`
2. improved `engram_lite`
3. full `engram`

Metrics should include:
- noise storage rate
- duplicate/near-duplicate storage rate
- retrieval precision/recall
- retrieved-context redundancy
- final answer uplift with memory on vs off
