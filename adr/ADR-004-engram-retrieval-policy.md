# ADR-004: Engram Retrieval Policy

**Date:** 2026-04-13
**Status:** Accepted
**Deciders:** Jeff Dean

---

## Context

Engram's five-layer memory architecture stores information in multiple places
simultaneously: episodic (ChromaDB vectors), semantic (Kuzu graph), working
(SQLite), and cold (SQLite FTS5). When a query arrives, multiple layers may
return results, and those results may contradict each other.

The contradiction problem is concrete. Consider:

```
Episode 1 (stored 2026-01-01): "Alice likes Python"
Episode 2 (stored 2026-03-15): "Alice hates Python"
Query: "Does Alice like Python?"
```

Without a defined retrieval policy:
- Episodic returns both episodes (cosine similarity matches both)
- Caller gets contradictory context, which degrades LLM responses
- No defined authority for which fact is "current"

A second problem: deleted episodic entries can reappear via high cosine
similarity to similar-but-not-identical content. ChromaDB does not have a
concept of "soft delete with suppression."

Both problems were identified and partially fixed in Engram v0.1.19 but not
formally documented as architectural decisions.

---

## Decision

### 1. Semantic layer is the authority for current facts

The semantic graph (Kuzu) holds the current state of knowledge. When a query
can be answered by the semantic layer, that answer takes precedence over
episodic results.

Rationale: The semantic layer is updated by a contradiction-resolution process
that explicitly removes superseded relationships. Episodic memory preserves
history; semantic memory reflects current truth.

### 2. Superseded episodic episodes are suppressed in retrieval

When the semantic layer contains a fact that contradicts an episodic episode,
that episode is tagged `superseded=True` at consolidation time. Retrieval
filters suppress superseded episodes by default.

This is the `suppress_superseded_episodic` flag in `RetrievalPolicy`.

The suppression is applied **post-search** (after cosine retrieval) because
ChromaDB does not support pre-filtering on arbitrary metadata fields without
collection restructuring.

### 3. Tombstones prevent deleted content from resurfacing

Deleted episodic entries are added to a tombstone list (stored in SQLite).
Post-search filtering removes any result whose ID appears in the tombstone list.
Tombstones are retained for 90 days, then vacuumed, on the assumption that
embedding drift over 90 days is sufficient to prevent resurfacing.

### 4. RetrievalPolicy is the single control surface

All retrieval behavior is controlled through `RetrievalPolicy`. Callers do not
manipulate layer internals directly.

```python
class RetrievalPolicy(BaseModel):
    # Layer selection
    include_working: bool = True
    include_episodic: bool = True
    include_semantic: bool = True
    include_cold: bool = False       # Cold storage is opt-in (slow)

    # Episodic filtering
    suppress_superseded_episodic: bool = True   # Default: suppress contradictions
    max_episodic_results: int = 5
    episodic_after: datetime | None = None      # Temporal lower bound
    episodic_before: datetime | None = None     # Temporal upper bound

    # Semantic filtering
    max_semantic_hops: int = 2       # Graph traversal depth
    semantic_min_confidence: float = 0.0

    # Result ranking
    prefer_semantic: bool = True     # Semantic results ranked above episodic
    max_total_results: int = 10
```

### 5. Neural output does not influence retrieval by default

This section is superseded by ADR-016 / NEURAL-07. The optional RTRL layer can
produce prediction-error telemetry, but it does not filter or re-rank retrieval,
trigger consolidation, change episode importance, or emit prompt guidance by
default. Prompt and importance outputs survive only as explicit experimental
opt-ins. See
`docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md` for the evidence and
reactivation gate.

---

## Consequences

### Positive

- Contradictions are resolved deterministically: semantic wins, old episodic is
  suppressed.
- Deleted content does not reappear through embedding similarity.
- `RetrievalPolicy` is self-documenting and testable in isolation.
- Cold storage is opt-in, keeping default retrieval fast.

### Negative / Trade-offs

- Post-search tombstone filtering adds a small overhead proportional to the
  tombstone list size. Acceptable at current scale (<10K tombstones).
- Superseded tagging happens at consolidation time, not at store time. There is
  a window between Episode 2 being stored and consolidation running where both
  episodes are returned unsuppressed. Acceptable for current batch consolidation
  mode; will require re-evaluation if streaming consolidation (v0.3.0) changes
  the timing.
- The 90-day tombstone vacuum is a heuristic. If two nearly-identical pieces of
  content are stored 91 days apart, the deleted first one could theoretically
  resurface. This risk is accepted.

---

## Deferred

- **Retrieval from cold storage by default**: Cold storage retrieval is
  intentionally opt-in. A future policy could auto-promote to cold retrieval
  when episodic + semantic results are below a confidence threshold.
- **Cross-project retrieval**: `RetrievalPolicy` is per-project. Shared memory
  across projects is an architectural question deferred to v0.4.0 (distributed
  memory).
- **Streaming consolidation timing**: The supersession window issue will need
  a revised policy when `consolidation_mode="streaming"` is implemented.

---

## Related

- `contracts/memory.py` (Phase 2): Will formalize `RetrievalPolicy` as a
  contract. Currently lives in `engram/retrieval.py`.
- ADR-001: Engine capability model (retrieval uses `EmbeddingModel` protocol
  for the semantic search step)
- Engram v0.1.19 bug fixes: episodic contradiction bleed, None importance in
  ForgettingPolicy, cosine-similarity tombstoning
