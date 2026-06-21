# llm_engines

## Tier: stable

## Scope

One interface over multiple LLM backends (Ollama, Anthropic, OpenAI, vLLM,
llama.cpp). Does not handle memory, retrieval, or agent orchestration.

## Quick start

```python
from llm_engines import get_engine, ChatMessage, GenerationRequest

engine = get_engine("ollama", "qwen3:8b")
response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content="What is RAG?")]
))
print(response.text)
```

With tool calling:

```python
from llm_engines import get_engine, ToolExecutor, tool

@tool
def add(a: int, b: int) -> int:
    return a + b

engine = get_engine("ollama", "qwen3:8b")
executor = ToolExecutor(tools=[add])
```

With a config-file profile (failover across backends):

```python
from llm_engines import EngineFactory
engine = EngineFactory.from_profile("default_local")
```

`llm_engines` is the backend and model abstraction layer for the `ai_tools` suite.

It provides a stable way to call LLM backends without forcing the rest of the stack to understand backend-specific quirks.

## Using this with the rest of the suite

- pair it first with `llm_inspector` or `llm_inspector_ui`
- then add `engram` or `rag_lib`

## Current support status

This is a **core** package and is treated as **active and stable**.

## Responsibilities

- engine/backend abstraction
- capability discovery
- normalized generation responses
- backend diagnostics and readiness checks
- failover/fallback support where configured
- interop conversion into shared `llm_harness_core` objects

## Position in the stack

`llm_engines` sits near the bottom of the suite:

- `llm_inspector_ui` uses it for engine/model selection and execution
- `language_tutor` uses it for model access
- `agent_lib` uses it for agent-facing generation
- `llm_inspector` and the UI inspect metadata produced by it

## Architectural notes

Important settled decisions are recorded in:

- `../adr/ADR-001-engine-capability-model.md`
- `../adr/ADR-002-engine-response-schema.md`

Those ADRs mean callers should assume:

- engine capabilities are explicit, not universal
- engine responses are structured, not plain strings only

## Interop

`llm_engines` participates in the shared harness vocabulary through `llm_harness_core`.

Notable interop responsibilities include:

- describing engines with shared capability descriptors
- converting messages/tool calls to shared objects
- converting generation results to shared operation results

## Prefix caching and cost optimisation

Multi-turn sessions and agent loops repeat a large common prefix on every
call — system prompt, tool spec, background context. Backends that support
prefix caching serve those tokens from their KV cache rather than recomputing
attention, cutting both latency and (on cloud APIs) cost.

### Enabling prefix caching

Pass `session_id` on every request in the same session:

```python
from llm_engines import get_engine, ChatMessage, GenerationRequest

engine = get_engine("ollama", "qwen3:8b")

for user_msg in conversation:
    response = engine.generate(GenerationRequest(
        messages=[system_msg, *history, user_msg],
        session_id="my-project-session-001",   # same string every turn
    ))
    print(response.text)
    print(f"Cache hit ratio: {response.cache_stats.hit_ratio:.0%}")
```

Backends that support prefix caching (vLLM, llama.cpp with `cache_prompt=True`)
use `session_id` to group requests and cache the shared prefix. Backends that
do not support it ignore the field. A `hit_ratio` of 0.0 means the backend
did not report cache data, not that there were no cache hits.

### Reading cache statistics

```python
stats = response.cache_stats
print(stats.hit_ratio)               # e.g. 0.73
print(stats.prompt_cache_hit_tokens) # tokens served from cache
print(stats.prompt_cache_miss_tokens)# tokens that required computation
```

Watch for `hit_ratio` dropping over the course of a long session — it usually
means growing Engram context or varying RAG chunks have pushed the stable
prefix out of the cache boundary. Tighten the memory token budget or fix the
content ordering.

### Cost impact on cloud APIs

Cloud providers charge reduced rates for cached prompt tokens. The savings
are significant for multi-turn sessions and essential for recursive agent
patterns where the same prefix repeats across many sub-calls.

| Provider | Non-cached input | Cached input | Saving |
|---|---|---|---|
| Anthropic | full price | ~10 % of input price | ~90 % on cached tokens |
| OpenAI | full price | ~50 % of input price | ~50 % on cached tokens |
| Local (Ollama / vLLM) | full compute | near-zero (VRAM only) | latency reduction |

Example: an agent loop that makes 50 sub-calls each with a 1,500-token fixed
prefix. Without caching: 75,000 input tokens at full price. With caching:
1,500 full + 49 × 150 (10 % of 1,500) = 8,850 token-equivalents — 88 % cost
reduction on the prefix alone.

### Ordering rule

Stable content must appear **first** for the cache to hit. The recommended
order is:

```
[system prompt] → [stable background context / RAG] → [dynamic memory] → [dynamic RAG] → [user message]
```

Putting dynamic content (Engram turns, per-query RAG chunks) before stable
content means the prefix never matches and the cache never fires.

See `docs/design/INFERENCE_OPTIMIZATION.md` for the full design rationale,
the RLM pattern, and deferred infrastructure work.


## Intended use

Use `llm_engines` when you want a common engine layer underneath memory, retrieval, inspection, or agents.

Do not use it as a dumping ground for UI logic, retrieval logic, or memory policy.
