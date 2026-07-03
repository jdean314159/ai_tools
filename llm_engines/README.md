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

## Prefix-cache contract (backend integration deferred)

`GenerationRequest.session_id` and `GenerationResponse.cache_stats` reserve a
backend-neutral contract for future prefix-cache integration:

```python
from llm_engines import get_engine, ChatMessage, GenerationRequest

engine = get_engine("ollama", "qwen3:8b")

response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content="Hello")],
    session_id="my-project-session-001",
))
print(response.cache_stats.hit_ratio)
```

The fields are implemented, but no current backend consumes `session_id` or
populates `cache_stats`; zero values therefore mean "not reported." Treat this
surface as forward-compatible scaffolding, not as an operational caching
feature.

See `../docs/design/INFERENCE_OPTIMIZATION.md` for the deferred backend work
and design rationale.


## Intended use

Use `llm_engines` when you want a common engine layer underneath memory, retrieval, inspection, or agents.

Do not use it as a dumping ground for UI logic, retrieval logic, or memory policy.
