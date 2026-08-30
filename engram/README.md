# engram

## Tier: beta

## Scope

Lightweight project memory for LLM applications. Stores conversation turns,
retrieves relevant prior context, and assembles memory-augmented prompts.
Does not run inference — it enriches prompts that other packages execute.

Internal storage layers (JSONL, ChromaDB, semantic graph) are implementation
details. The primary public API is `ProjectMemory`.

## Quick start

```python
from engram import ProjectMemory

mem = ProjectMemory(base_dir="~/.myapp", project_id="demo")
mem.new_session("s1")
mem.add_turn("user", "My name is Jeff and I work on LLM security.")
result = mem.build_prompt("What do I work on?")
print(result["prompt"])
```

With llm_engines:

```python
from engram import ProjectMemory
from llm_engines import get_engine, GenerationRequest, ChatMessage

mem = ProjectMemory(base_dir="~/.myapp", project_id="demo")
engine = get_engine("ollama", "qwen3:8b")

user_msg = "What projects am I working on?"
mem.add_turn("user", user_msg, "s1")
prompt = mem.build_prompt(user_msg)["prompt"]

response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content=prompt)]
))
mem.add_turn("assistant", response.text, "s1")
```



`engram` is the memory augmentation package in the `ai_tools` suite - an
inspectable way to add memory behavior to an LLM workflow.

## Using this with the rest of the suite

- inspect its behavior in `llm_inspector` and `llm_inspector_ui`
- evaluate stage boundaries with `llm_harness_core`
- see [Temporal memory](docs/temporal_memory.md) for versioned facts
- see [Reliability testing](docs/reliability_testing.md) for deterministic attribution

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
llm_engines + engram + llm_inspector + llm_inspector_ui
```

It is also the default memory path for:

- `llm_inspector_ui`
- `language_tutor`
- the lightweight `agent_lib` path

## Interop and observability

`engram` participates in the shared `llm_harness_core` vocabulary.

It can expose:

- shared memory records
- shared operation results for augmentation
- shared trace events for prompt-building stages
- capability descriptors for the workbench/inspector layers

This is important because the package is not meant to be a hidden prompt manipulator. It should make memory contributions visible.

Prompt results now include `budget_diagnostics` and `retrieval_diagnostics`.
Evidence traces retain structured episode provenance, including `episode_id`
and `topic_key` when available. For deterministic staged evaluation,
`observation_from_engram(...)` converts retrieval and prompt results into
`llm_harness_core.MemoryCaseObservation`, allowing testers to attribute storage,
retrieval, composition, inference, and exact-scoring failures separately.

### Prompt result diagnostics

`build_prompt(..., return_trace=True)` returns the existing prompt fields plus:

- `included_items`: the actual ranked items admitted to each prompt section
- `budget_diagnostics`: candidate, included, and excluded item counts;
  total/reserved/available tokens; and `memory_starved`
- `retrieval_diagnostics`: vector use, relevance filtering, temporal filtering,
  historical mode, and unresolved active-topic conflict counts
- `trace`: final sections and included evidence with structured metadata

Under budget pressure, Engram packs ranked items individually. It no longer
needs an entire memory layer to fit before admitting any item from that layer.
`memory_tokens` remains the candidate-memory token estimate for compatibility; use
`included_items` and `budget_diagnostics` to inspect what actually entered the
prompt.

### Temporal memory

Versioned facts can be stored explicitly with `store_temporal_episode(...)`:

```python
old_id = mem.store_temporal_episode(
    "Atlas deploys in us-east-1.",
    topic_key="atlas::deployment_region",
    action="set",
)
new_id = mem.store_temporal_episode(
    "Atlas now deploys in eu-central-1.",
    topic_key="atlas::deployment_region",
    action="update",
)

current = mem.search_episodes("Atlas current deployment region")
history = mem.search_episodes(
    "Atlas deployment region",
    include_historical=True,
)
```

Supported actions are `set`, `update`, and `retract`. Current-state retrieval
suppresses superseded predecessors while retaining them in persistent storage.
Historical retrieval exposes both active and superseded versions. See
[Temporal memory](docs/temporal_memory.md) for metadata and query behavior.

Engram does not infer arbitrary semantic contradictions. Callers must supply a
stable `topic_key` and temporal action for deterministic resolution.

## Optional memory layers

Experimental memory implementations can implement `MemoryLayer` and register
explicitly with `ProjectMemory.register_layer()`. Extensions receive successful
turn and episode observations, may contribute advisory recall-score boosts and
prompt hints, and receive persistence and close hooks.

Core Engram behavior remains authoritative: extensions cannot add, remove, or
suppress recall candidates, and extension failures are logged without breaking
the default memory flow. No extension layers are registered by default.

### Isolated neural primitives

`engram.neural` contains the recovered RTRL/TITANS associative-memory core,
`NeuralMemory` wrapper, and surprise filter. These components are opt-in and
are not imported by base `engram`.

The default backend is NumPy. Install the `neural-accel` extra and explicitly
select an accelerated device to use the optional Torch backend.

`ProjectMemory` can register the neural adapter explicitly:

```python
from engram import ProjectMemory
from engram.neural import NeuralMemoryConfig

memory = ProjectMemory(
    base_dir="~/.myapp",
    project_id="demo",
    embedder=my_embedder,
    enable_neural=True,
    neural_config=NeuralMemoryConfig(),
)
```

Neural memory is parked, default-off, and output-isolated after corpus
evaluation. It can learn paired user-to-assistant embedding associations and
report surprise telemetry, but its output does not affect retrieval order,
episode importance, or prompts by default. Neural retrieval re-ranking is
disabled. Surprise-based importance adjustment and reconstructed episode-list
prompt hints remain available only as explicit research controls through
`NeuralMemoryConfig(importance_advisory_enabled=True)` and
`NeuralMemoryConfig(prompt_advisory_enabled=True)`.

This is an integration decision, not a conclusion that RTRL is a failed
learning algorithm. The core learns sequential and repetition-related signals;
the tested label-free outputs did not translate those signals into dependable
candidate utility. The completed runs exceeded the 50-step warmup threshold,
so cold start alone does not explain the null and negative results.

NEURAL-07 found that calibrated surprise thresholds reduced neural updates
without improving full-run quality, inspected hints missed the expected episode
on all 180 queries, and a feedback-free candidate-utility scorer did not improve
held-out ranking across three seeds. See
`docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md` for the complete
record and reactivation gate.
Perplexity/logprob-based surprise filtering remains separate and is not wired
into `ProjectMemory`.

One use case remains deliberately unmeasured: direct projected-space candidate
affinity learned across many genuine sessions in a stable project domain. A
future longitudinal evaluation must first show held-out separation between
useful, stale, and plausible-but-wrong candidates in shadow mode. It must then
show retrieval improvement across fixed seeds without direct/paraphrase
regression or unsafe semantic promotion. More sessions or a larger affinity
weight are hypotheses to test, not presumed remedies.

The synthesis path uses `value_dim=32`; a 64-dimensional experiment overflowed
at full evaluation volume. Any non-finite neural state disables neural updates
and hints rather than affecting core Engram behavior.

## Current quality controls

`engram` includes memory-quality controls for:

- lightweight user-preferred turn ingestion and importance scoring
- store-time near-duplicate blocking
- internal episodic retrieval with scoring
- retrieval-time diversity filtering
- prompt assembly that can use internal episodic hits even without an external retriever
- basic canonical correction/update handling for lightweight fact replacement
- opt-in retained temporal history with current/historical retrieval boundaries
- item-level prompt packing with starvation and exclusion diagnostics
- structured episode provenance in evidence traces

## Memory formation policy

`engram` defaults to **user-preferred ingestion**:

- user turns may be auto-ingested when they look memory-worthy
- assistant turns are kept in recent working memory but are **not** auto-ingested into episodic memory by default
- assistant content may still be stored explicitly when it is tagged as a memory artifact such as `session_summary`, `decision`, or `preference`

## Lightweight update handling

`engram` performs a small amount of **canonical update handling** for common user correction/update phrasings so retrieval is less likely to drag stale values back into the prompt.

Canonical update handling preserves its existing replacement semantics. Use
`store_temporal_episode(...)` when historical retention, explicit retraction,
or deterministic validity metadata is required.

## Known Limitations (v0.2)

### Decoy resistance via threshold filtering
`engram` achieves 80%+ decoy resistance through a cosine similarity
threshold (default 0.4) applied to ChromaDB results. This filters results
that are vectorially dissimilar to the query before they reach the prompt.

The limitation: the threshold is a blunt instrument. It filters by geometric
distance in embedding space, not semantic relevance. A genuinely relevant
result that happens to be phrased differently from the query may be filtered
out alongside actual decoys. Tuning the threshold is empirical — lower values
admit more results (including decoys), higher values are more restrictive.

The correct long-term fix is LLM-based extraction scoring, which evaluates
relevance semantically rather than geometrically. This is deferred.

### Explicit temporal updates versus semantic contradiction

The explicit temporal API prevents known superseded versions from entering
current-state prompts. Paired validation removed obsolete evidence from 3/3
current prompts while preserving historical recall and exact answers. A cold
reopen with real MiniLM embeddings and ChromaDB also passed 3/3 timelines.

This does not solve unlabelled semantic contradiction. Independently stored
claims without a shared `topic_key` and temporal action can still conflict.
`retrieval_diagnostics["unresolved_conflict_topic_count"]` reports multiple
active retrieved records for a known topic, but Engram does not invent a
resolution. LLM-based semantic extraction remains outside the default
lightweight path.

### No procedural memory
`engram` stores episodic and semantic memory but has no synthesis
layer. It cannot extract generalizable rules from past sessions ("when X,
do Y") or surface procedural patterns in prompts. There is currently no
`synthesize_now()` API or `## Procedural Rules` prompt block in this package.

### No memory audit
`engram` has no `audit_memory()` facility. Orphaned records,
contradicting facts, and stale data accumulate silently. An audit and
remediation API remains future work.

## Validation scope

The current temporal evidence is intentionally bounded:

- paired legacy/temporal live-model validation: five queries per arm
- obsolete evidence in current prompts: legacy 3/3, temporal 0/3
- exact answers: 5/5 in both arms
- aggregate temporal prompt-token reduction: 11.8%
- cold-reopen hybrid vector validation: 3/3 timelines

These results validate the implemented mechanisms, not general performance on
large natural histories, arbitrary contradictions, or other embedding models.
The retained reports live under `docs/projects/` in the ai_tools repository.
