# Inference Optimization Design Notes

**Status:** Design guidance and extension-point inventory. The `llm_engines`
API additions (§2) are implemented. Everything else is deferred pending a
concrete triggering task.
**Date:** 2026-05-27
**Source:** Article assessment thread (RLM/MIT paper arXiv:2512.24601) plus a
summary of recent KV-cache advances (Tutti, ThunderAgent, Irminsul, TurboQuant).
**Purpose:** Capture the architectural direction so context-management work
is placed correctly in the package structure and not re-derived from scratch.

---

## 0. Thesis: context as a managed resource

The dominant shift in inference optimization is that the context window is
increasingly treated as a *managed resource* rather than a passive buffer.
Two complementary strategies capture most of the current work:

- **Minimize what enters the context** — the RLM pattern (§1) and RAG both
  keep large data external and let the model explore selectively.
- **Optimize what is in the context** — KV-cache reuse, compression, and
  SSD-backed tiers reduce the cost of attention over the tokens that do enter.

Both strategies matter for local-first inference and agent workflows, where
VRAM is fixed, context rot is the reliability enemy, and cloud escalation is
a cost failure mode. They are not competing; they compose.

## 1. RLM pattern — deferred, home in `rag_lib`

**What it is:** Recursive Language Models (Zhang, Kraska, Khattab — MIT CSAIL,
arXiv:2512.24601, December 2025). Instead of loading large context into LLM
attention, the model receives the data as an external Python variable and
writes code to inspect, chunk, and recursively call sub-instances over
specific segments. Each LLM call sees only 200–1k tokens regardless of total
data size.

**Verified benchmarks:** 26% median win over compaction, 130% over CodeAct
with sub-calls, 13% over Claude Code across four long-context tasks at
comparable cost. Median token reduction varies by task type.

**Critical constraint:** current implementations operate at depth=1 — recursive
sub-calls do not themselves recurse. Deeper recursion stacks are experimental.

**Security surface:** model-written code executes against real data. Requires
the same sandbox baseline as ADR-011 (container isolation, network default-deny)
before pointing at non-trivial data.

**Complexity classes the paper identifies:**

- *Constant complexity* (needle-in-haystack): standard search; RLM adds little.
- *Linear complexity* (examine every item): e.g. categorize 10k tickets.
  RLM: model loops with tiny per-item calls. Directly applicable to agent
  tool-result processing.
- *Quadratic complexity* (pairwise reasoning): e.g. attack chain correlation
  in network logs. GPT-5 baseline achieves ~0% without RLM. This is the use
  case where RLM is essential, not just helpful.

**Where it lives in ai_tools:** `rag_lib`. RAG and RLM are both "keep data
external, retrieve selectively" patterns. RLM replaces the retrieval step with
model-driven exploration. A `rag_lib.rlm` module or `RecursiveExplorer` class
is the correct home — not a new package, not `agent_lib`.

**Triggering task:** build `rag_lib.rlm` when a concrete consumer task (e.g.
pointing `agent_coordination_teaching` at a real codebase analysis task)
produces a clear failure from direct context loading. That failure provides
the acceptance test. Do not build speculatively.

**What the implementation needs (when triggered):**
- A sandbox runner (model writes code → we exec in confined environment).
  Reuse the ADR-011 container baseline, not a Python `exec()` in-process.
- A recursive call coordinator with a depth cap (default 1).
- A context-variable registry (keeps large data out of the LLM prompt).
- Integration with `llm_engines.get_engine` for sub-calls (already exists).

## 2. KV-cache layer — partially implemented

### 2a. Per-response cache statistics — **implemented**

`llm_engines.CacheStats` has been added to `GenerationResponse`:

```python
from llm_engines import CacheStats, GenerationRequest, get_engine

engine = get_engine("ollama", "qwen3:8b")
response = engine.generate(GenerationRequest(
    messages=[...],
    session_id="my-agent-session",   # prefix-cache hint
))
print(response.cache_stats.hit_ratio)      # 0.0 if backend doesn't report
print(response.cache_stats.prompt_cache_hit_tokens)
```

`CacheStats` fields:
- `prompt_cache_hit_tokens` — tokens served from KV cache
- `prompt_cache_miss_tokens` — tokens requiring fresh computation
- `hit_ratio` (property) — fraction served from cache; 0.0 means "unknown"
- `cache_key` — key used for this entry (backend-reported, may be None)
- `total_cached_tokens` (property) — sum of hit + miss

Backends populate `cache_stats` when they expose cache information. Ollama
exposes partial stats. vLLM exposes full prefix-cache statistics. Backends
that do not report cache data leave `cache_stats` as zero-value (`hit_ratio`
== 0.0, which means *unknown*, not *no hits*).

### 2b. Session-based prefix-cache hint — **implemented**

`GenerationRequest.session_id: str | None` has been added. Backends that
support prefix caching (vLLM, llama.cpp with `cache_prompt=True`) use it to
group requests sharing a common prefix (system prompt, tool spec, long
task preamble) and serve those tokens from cache rather than recomputing
attention.

Usage:

```python
# All turns in a session share the system-prompt + context prefix
request = GenerationRequest(
    messages=[system_msg, *history, user_msg],
    session_id="tutor-session-abc123",
)
```

Ignored by backends that do not support prefix caching.

### 2c. Cache observability in `llm_inspector` — deferred

`llm_inspector.TraceEvent` and `RunMetrics` are the natural home for cache
hit rate, prefix reuse, and token reuse efficiency metrics across a run.
A `CacheTrace` alongside the existing `RunMetrics` should be added when a
real agent workflow produces enough requests to make cache analysis meaningful.
Do not add before there is something to measure.

## 3. Deferred: heavier KV-cache infrastructure

These require vLLM integration at a depth not yet present, or hardware not
universally available. Design intent captured here; implementations deferred.

**Tutti (SSD-backed KV restoration):** Integrates with vLLM, uses GPU-centric
NVMe I/O for KV cache restoration. Reports ~78% lower time-to-first-token
and ~2× throughput under load. Relevant when the agent workload has long-lived
sessions with large shared prefixes that exceed VRAM. Belongs in the vLLM
backend layer of `llm_engines`, not in the application layer.

**ThunderAgent / Irminsul (agent-aware cache scheduling):** Target repeated
prompt prefixes, shifted conversational context, and inter-agent KV reuse.
ThunderAgent reports 1.5–3.6× throughput gains with major cache-hit
improvements. These operate at the inference server scheduler level — they
require a vLLM (or equivalent) deployment, not just a Python client. Relevant
when the future agent orchestration repo (see AGENT_BUILD_NOTES §8) is
running multiple concurrent agents against the same model.

**Persistent KV snapshots:** Cache a model's KV state for a long shared prefix
(e.g. the entire project context) to disk so it survives between sessions.
Requires backend support not widely available yet. Extension point: a
`session_snapshot_path` field on `GenerationRequest` could hint a backend to
restore from or save to a path. Do not add until at least one backend supports it.

### 3a. Memory-hierarchy tiering (RAM / NVMe) — deferred, backend concern

The KV cache is a memory hierarchy: VRAM (hot, ~1 TB/s, small) → system RAM
(warm, ~16–32 GB/s over PCIe, large) → NVMe (cold, ~3–7 GB/s, persistent,
unlimited). Cached prefixes that exceed VRAM can live in the lower tiers and
be paged up on a hit instead of being evicted and recomputed.

**The governing question is restore-vs-recompute.** Restoring a prefix's KV
tensors from a lower tier is bandwidth-bound; recomputing it is a compute-bound
prefill pass. Tiering wins when restore is faster than recompute, which is
exactly the local-first regime: a consumer GPU (slower prefill), a large prefix
(many tokens), and a prefix reused many times (amortizes the one-time store).
On a frontier datacenter GPU with a small prefix, recompute can be faster and
tiering loses — so this is *more* attractive on the project's hardware
(RTX 3090), not less.

**Tier guidance for the project's hardware (3090 / 128 GB RAM / NVMe):**

- **RAM is the immediate lever and is underused.** 128 GB holds dozens of
  multi-GB prefixes resident — directly the multi-agent case (§6). Mature in
  vLLM today via `swap_space` (CPU/RAM KV offload); partial in llama.cpp.
  Enabling RAM-backed offload converts "out of VRAM → evict + recompute" into
  "out of VRAM → RAM restore."
- **NVMe is the persistence tier.** Snapshot a stable prefix's KV state to disk
  so a cold start skips the prefill entirely. Tutti's GPU-centric I/O
  (GPUDirect Storage, NVMe→VRAM direct, no CPU double-copy) is what produces
  the ~78% TTFT numbers.

**`CacheStats` extension when this lands:** report *which tier* served a hit —
VRAM hit (fast) / RAM-restored (medium) / NVMe-restored (slow) / miss
(recompute). Those have very different latency profiles; knowing the tier turns
`CacheStats` from "did we hit?" into "what did the hit cost?"

**Engram as a KV-snapshot tier (speculative):** Engram already has a multi-tier
storage model, and the stable project-context prefix it assembles every session
is a natural snapshot candidate. Engram could eventually manage a *precomputed
KV snapshot* for its stable prefix rather than returning text that gets
re-prefilled each session — blurring "memory" into "pre-attended state." Do not
build until a backend exposes snapshot save/restore and the §6 contention need
is real.

**Caveats that bite if ignored:**

- **Model-and-quantization-specific.** A KV snapshot for Qwen 32B Q4 is useless
  for any other model or quant. Persistent snapshots are fragile across the
  frequent model upgrades this project does (Gemma 4, Qwen 3.5, …) — every model
  bump invalidates the snapshot cache.
- **Byte-identical prefix required.** Any system-prompt or pinned-background
  change invalidates all stored snapshots. The §2 ordering discipline becomes
  even more load-bearing.
- **GPUDirect Storage needs hardware/driver support.** Without it, NVMe→RAM→VRAM
  is a double copy and most of the benefit evaporates. Verify the NVMe + driver
  stack supports GDS before counting on Tutti-class numbers.
- **Position-dependence.** KV cache is reusable only at the same position, which
  is why *prefix* caching works and arbitrary mid-context caching does not. This
  bounds tiering to prefix reuse.

## 4. Ecosystem placement (Ollama vs vLLM)

The ecosystem has settled into complementary roles that ai_tools should reflect:

- **Ollama:** simplicity, local dev, coding tool integration, single-user
  workloads. `get_engine("ollama", ...)` is the right default.
- **vLLM:** throughput, batching, KV-aware serving, multi-user/agent
  workloads. `get_engine("vllm", ...)` is the right choice for the future
  agent orchestration repo running concurrent workers.

Neither is universally better; `llm_engines`' backend abstraction is the right
seam. Do not let application code hardcode either.

## 5. Instrumentation target list

When building the future agent orchestration repo (AGENT_BUILD_NOTES §8),
instrument these from the first session that runs real workloads:

- Cache hit rate per session (from `response.cache_stats.hit_ratio`)
- Prefix token reuse across agents sharing the same system prompt
- Context overlap between consecutive agent turns (Engram dedup can measure this)
- Token reuse efficiency (hit tokens / total prompt tokens across a run)

These metrics are what ThunderAgent and Irminsul target at the scheduler level.
Having them from the application layer allows informed decisions about whether
a vLLM deployment with agent-aware scheduling is worth the operational cost.

## 6. Multi-agent implications

In a multi-agent / ASC-type system, these primitives stop being conveniences
and start shaping the architecture. The findings below come from design
analysis, not yet from a running system; they are extension points for the
future agent orchestration repo (AGENT_BUILD_NOTES §8), not build mandates.

**`session_id` is necessary but not sufficient.** It groups requests within one
thread, but a multi-agent system has a different cache shape: N workers each
with their own thread yet sharing a large common prefix (system prompt, tool
spec, task context). Tagging each worker with a distinct `session_id` caches
that identical prefix N times. The eventual need is a *layered* cache identity —
a shared-prefix key for the common base plus a per-agent suffix. vLLM does this
automatically via block hashing; the `llm_engines` abstraction does not yet
expose the concept. **Trigger:** the future repo running concurrent workers
that share a system prompt. Until then, document only.

**KV-cache contention is a hard concurrency limit on local multi-agent.** On a
single GPU the cache is finite and shared; agent A filling it evicts agent B's
prefix, so B pays full recompute (the "memory imbalance across agents"
ThunderAgent names). The future repo needs a concurrency limiter informed by
*cache capacity*, not just worker count. `CacheStats.hit_ratio` dropping across
agents simultaneously is the diagnostic signature of thrashing. **Memory-tier
offload (§3a) directly mitigates this** — paging B's prefix to RAM instead of
evicting it converts a hard wall into a graceful gradient, raising the ceiling
on concurrent local agents.

**`CacheStats` becomes a fleet-level signal — expands `llm_inspector`.** Across
agents, aggregated `CacheStats` answers scheduling/debugging questions a single
run cannot: which agents thrash, whether the shared prefix is actually reused,
whether A's session evicted B's prefix at turn 5 or B's own context grew. The
deferred `CacheTrace` (§2c) becomes a cross-agent telemetry aggregator in this
context.

**The cost circuit-breaker gains a dollars dimension.** A cloud mentor's prefix
(escalation-context format, task spec) is stable across escalations, so a
re-escalation is cheaper than a first one. The AGENT_BUILD_NOTES §4 circuit
breaker can therefore move from "max N mentor calls" to "max $X of mentor
spend," computed from `CacheStats` hit ratios — the right unit once cache
economics are in play.

**Engram shared-vs-per-agent memory becomes a cost decision, not only a
correctness one.** A shared read-only `ProjectMemory` across agents is a
cacheable shared prefix (cheap, consistent); per-agent mutable memory gives
isolation but creates N separate prefixes (more misses). The future repo must
choose deliberately, now with a cost axis layered on the correctness axis.

**RLM amplifies both savings and contention.** Within one agent, RLM sub-calls
share a prefix and cache well (the large savings). N agents each running M-sub-
call RLM loops is N×M calls competing for finite local cache. RLM is where
prefix amortization pays off most *and* where contention is worst — the same
mechanism from opposite ends. The orchestration repo must budget cache capacity
for it rather than treating RLM as a free optimization.

**Through-line:** these primitives turn previously-qualitative multi-agent
decisions (how many agents, shared vs separate memory, when to escalate) into
quantitative, measurable ones — the difference between guessing at concurrency
limits and measuring them.

---

## Reference

Paper: Zhang, Kraska, Khattab — "Recursive Language Models," arXiv:2512.24601,
MIT CSAIL, December 2025 (revised through May 2026).

Related docs: `docs/design/AGENT_BUILD_NOTES.md` (worker/mentor pattern,
context-rot reduction via Engram, future agent repo), `adr/ADR-011` (isolation
baseline required for RLM sandbox execution), `docs/design/VISION.md`
(harness engineering principles).
