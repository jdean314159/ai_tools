# Temporal memory

Engram supports deterministic versioned memory when the application knows that
several episodes describe successive states of the same topic. This capability
is explicit and local: it does not call an LLM to infer contradictions.

## Store versions

```python
from engram import ProjectMemory

memory = ProjectMemory(base_dir="./state", project_id="operations")

initial_id = memory.store_temporal_episode(
    "The review is scheduled for Tuesday at 13:00 UTC.",
    topic_key="architecture_review::schedule",
    action="set",
    metadata={"source": "approved_minutes"},
    importance=1.0,
)

replacement_id = memory.store_temporal_episode(
    "The review is now scheduled for Wednesday at 14:00 UTC.",
    topic_key="architecture_review::schedule",
    action="update",
    metadata={"source": "approved_minutes"},
    importance=1.0,
)
```

`topic_key` is application-defined and must remain stable across versions.
`action` accepts:

- `set`: establish a value
- `update`: supersede the active version and establish a replacement
- `retract`: supersede the active version without claiming another value

The returned value is the normal Engram episode ID.

## Metadata

Temporal episodes retain ordinary metadata and add:

- `topic_key`
- `temporal_action`
- `temporal_status`: `active` or `superseded`
- `valid_from`
- `supersedes`: predecessor episode IDs

Superseded predecessors receive:

- `valid_until`
- `superseded_by`
- `temporal_status="superseded"`

`effective_at` can be supplied as a Unix timestamp. If omitted, Engram uses the
episode creation time.

## Current and historical retrieval

```python
current = memory.search_episodes("When is the review?")
history = memory.search_episodes(
    "Review schedule history",
    include_historical=True,
)
```

Current retrieval removes records explicitly marked `superseded`. Retractions
remain active evidence because they establish that no current value exists.
Engram does not generate the word `UNKNOWN`; the consuming application or model
decides how to represent a retracted value.

`build_prompt(...)` automatically requests historical episodes for queries
containing common historical language such as “before,” “previously,” “used
to,” or “after session.” For critical applications, call
`search_episodes(..., include_historical=True)` explicitly and inspect the
trace rather than relying solely on phrase detection.

## Persistence and vectors

JSONL remains authoritative. When ChromaDB returns an older indexed copy of an
episode's metadata, Engram reconciles the result with the current JSONL record
before temporal filtering. This preserves correct current/historical behavior
after close and cold reopen without rewriting the original vector.

## Compatibility

`store_episode(...)` is unchanged. Its existing canonical `topic_key`
replacement behavior still removes the previous episode. Temporal retention is
opt-in through `store_temporal_episode(...)`.

Do not use temporal memory as a security boundary. Applications should still
validate writers, source authority, tenant access, and untrusted content.

## Limitations

- Engram cannot infer that differently worded records concern the same topic.
- A wrong or overly broad `topic_key` can suppress valid current evidence.
- Multiple active records can remain when callers omit temporal actions.
- Temporal metadata expresses application assertions; it does not verify truth.
- Large histories and concurrent multi-writer update semantics require separate
  application-level validation.
