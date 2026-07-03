# engram

## Tier: beta

## Scope

Lightweight project memory for LLM applications. Stores conversation turns,
retrieves relevant prior context, and assembles memory-augmented prompts.
Does not run inference — it enriches prompts that other packages execute.

Internal storage layers (SQLite, ChromaDB, semantic graph) are implementation
details. The public API is `ProjectMemory`.

## Quick start

```python
from engram import ProjectMemory

mem = ProjectMemory(base_dir="~/.myapp", project_id="demo")
mem.new_session("s1")
mem.add_turn("user", "My name is Jeff and I work on LLM security.")
result = mem.build_prompt("What do I work on?", session_id="s1")
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
prompt = mem.build_prompt(user_msg, session_id="s1")["prompt"]

response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content=prompt)]
))
mem.add_turn("assistant", response.text, "s1")
```



`engram` is the memory augmentation package in the `ai_tools` suite - an
inspectable way to add memory behavior to an LLM workflow.

## Using this with the rest of the suite

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

NEURAL-07 found that calibrated surprise thresholds reduced neural updates
without improving full-run quality, inspected hints missed the expected episode
on all 180 queries, and a feedback-free candidate-utility scorer did not improve
held-out ranking across three seeds. See
`docs/projects/engram/NEURAL-07-RTRL-OUTPUT-EVALUATION.md` for the complete
record and reactivation gate.
Perplexity/logprob-based surprise filtering remains separate and is not wired
into `ProjectMemory`.

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

## Memory formation policy

`engram` defaults to **user-preferred ingestion**:

- user turns may be auto-ingested when they look memory-worthy
- assistant turns are kept in recent working memory but are **not** auto-ingested into episodic memory by default
- assistant content may still be stored explicitly when it is tagged as a memory artifact such as `session_summary`, `decision`, or `preference`

## Lightweight update handling

`engram` performs a small amount of **canonical update handling** for common user correction/update phrasings so retrieval is less likely to drag stale values back into the prompt.

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

### Contradiction bleed under stress (~18%)
When contradictory facts are stored (one claim overriding another),
`engram` may surface both the original and the override in the same
prompt under stress conditions — particularly when distractor volume is
high. The contradiction rate under stress is approximately 18% with the
current pattern-based extraction (`pattern_only=True`).

The root cause is that `engram` detects contradictions via regex
pattern matching on known update phrases ("actually", "correction:", etc.).
It does not understand semantic contradiction — two facts can conflict
without either using correction language.

The correct fix is LLM-based extraction to identify contradictions
semantically. This requires `pattern_only=False` and a running LLM, which
is outside engram's lightweight design constraints.

### No procedural memory
`engram` stores episodic and semantic memory but has no synthesis
layer. It cannot extract generalizable rules from past sessions ("when X,
do Y") or surface procedural patterns in prompts. There is currently no
`synthesize_now()` API or `## Procedural Rules` prompt block in this package.

### No memory audit
`engram` has no `audit_memory()` facility. Orphaned records,
contradicting facts, and stale data accumulate silently. An audit and
remediation API remains future work.
