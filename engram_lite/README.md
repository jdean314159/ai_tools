# engram_lite

`engram_lite` is the lightweight memory augmentation package in the `ai_tools` suite.

It is intended to be the easiest way to add inspectable memory behavior to an LLM workflow without adopting the full `engram` runtime.

## Start here if you are learning from this repo

This is the default memory package in the teaching path.

- teaching path stage: Stage 3 in [`../LEARNING_PATH.md`](../LEARNING_PATH.md)
- use this before considering full `engram`
- inspect its behavior in `llm_inspector` and `llm_inspector_ui`

## Current support status

This package is the **default** memory path and is **active and recommended**.

## Responsibilities

- recent/project memory storage
- retrieval of relevant prior context
- prompt assembly with memory augmentation
- evidence trace production
- conversion to shared interop objects for inspection

## Position in the stack

Typical composition:

```text
llm_engines + engram_lite + llm_inspector + llm_inspector_ui
```

It is also the default memory path for:

- `llm_inspector_ui`
- `language_tutor`
- the lightweight `agent_lib` path

## Interop and observability

`engram_lite` participates in the shared `llm_harness_core` vocabulary.

It can expose:

- shared memory records
- shared operation results for augmentation
- shared trace events for prompt-building stages
- capability descriptors for the workbench/inspector layers

This is important because the package is not meant to be a hidden prompt manipulator. It should make memory contributions visible.

## Boundary relative to `engram`

`engram_lite` is the small, adoption-friendly memory layer.
`engram` remains the richer and more experimental/full memory runtime.

Operationally:

- choose `engram_lite` for simpler memory augmentation and easier adoption
- choose `engram` for richer persistent/project memory workflows

## Current quality controls

`engram_lite` includes a deliberately small subset of the memory-quality controls from `engram`:

- lightweight user-preferred turn ingestion and importance scoring
- store-time near-duplicate blocking
- internal episodic retrieval with scoring
- retrieval-time diversity filtering
- prompt assembly that can use internal episodic hits even without an external retriever
- basic canonical correction/update handling for lightweight fact replacement

## Memory formation policy

`engram_lite` defaults to **user-preferred ingestion**:

- user turns may be auto-ingested when they look memory-worthy
- assistant turns are kept in recent working memory but are **not** auto-ingested into episodic memory by default
- assistant content may still be stored explicitly when it is tagged as a memory artifact such as `session_summary`, `decision`, or `preference`

## Lightweight update handling

`engram_lite` performs a small amount of **canonical update handling** for common user correction/update phrasings so retrieval is less likely to drag stale values back into the prompt.
