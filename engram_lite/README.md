# engram_lite

`engram_lite` is the lightweight memory augmentation facade in the `ai_tools` suite.
It provides a simplified interface over `engram` with a smaller public surface focused on the most common memory augmentation needs.

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

## Known Limitations (v0.2)

### Decoy resistance via threshold filtering
`engram_lite` achieves 80%+ decoy resistance through a cosine similarity
threshold (default 0.4) applied to ChromaDB results. This filters results
that are vectorially dissimilar to the query before they reach the prompt.

The limitation: the threshold is a blunt instrument. It filters by geometric
distance in embedding space, not semantic relevance. A genuinely relevant
result that happens to be phrased differently from the query may be filtered
out alongside actual decoys. Tuning the threshold is empirical — lower values
admit more results (including decoys), higher values are more restrictive.

The correct long-term fix is LLM-based extraction scoring, which evaluates
relevance semantically rather than geometrically. This is deferred.

### Contradiction bleed under stress (~18%)
When contradictory facts are stored (one claim overriding another),
`engram_lite` may surface both the original and the override in the same
prompt under stress conditions — particularly when distractor volume is
high. The contradiction rate under stress is approximately 18% with the
current pattern-based extraction (`pattern_only=True`).

The root cause is that `engram_lite` detects contradictions via regex
pattern matching on known update phrases ("actually", "correction:", etc.).
It does not understand semantic contradiction — two facts can conflict
without either using correction language.

The correct fix is LLM-based extraction to identify contradictions
semantically. This requires `pattern_only=False` and a running LLM, which
is outside engram_lite's lightweight design constraints.

### No procedural memory
`engram_lite` stores episodic and semantic memory but has no synthesis
layer. It cannot extract generalizable rules from past sessions ("when X,
do Y") or surface procedural patterns in prompts. This capability exists
in full `engram` via `synthesize_now()` and the `## Procedural Rules`
prompt block.

### No memory audit
`engram_lite` has no `audit_memory()` facility. Orphaned records,
contradicting facts, and stale data accumulate silently. Full `engram`
provides `pm.audit_memory()` with six diagnostic checks and a remediation
API.
