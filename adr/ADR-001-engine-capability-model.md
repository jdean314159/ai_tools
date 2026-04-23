# ADR-001: Engine Capability Model

**Date:** 2026-04-13
**Status:** Accepted
**Deciders:** Jeff Dean

---

## Context

The original `LLMEngine` ABC defined a single class that all backends implemented,
regardless of what they actually supported. The interface included `generate_with_tools()`
and `get_capabilities() -> dict[str, bool]` on every engine, meaning backends that
don't support tool calling still had to implement a stub.

This created several problems:

1. No static type-checking of capability mismatches (callers couldn't know at compile
   time whether a given engine supported embeddings or tool calling).
2. "Universal engine" assumption encouraged callers to pass any engine anywhere,
   producing runtime failures when an unsupported capability was exercised.
3. `get_capabilities()` returning `dict[str, bool]` was stringly typed and not
   self-documenting.
4. Streaming was bolted on informally; no distinction between sync and async streaming.
5. No defined exception types — each backend raised different errors for the same
   failure conditions.

---

## Decision

**Split the monolithic `LLMEngine` ABC into composable `Protocol` classes.**

Each Protocol represents one capability. Backends declare which Protocols they
implement. The type checker (mypy / pyright) enforces that only conformant engines
are passed to functions requiring a given capability.

### Protocols defined in `contracts/engine.py`

| Protocol | Methods | Notes |
|----------|---------|-------|
| `ChatModel` | `get_capabilities()`, `generate()` | Required by all backends |
| `ToolCallingModel` | `generate_with_tools()` | Ollama, Anthropic, OpenAI only |
| `EmbeddingModel` | `embed()` | Ollama, OpenAI, vLLM, llama.cpp |
| `StreamingModel` | `stream()` | Synchronous; Ollama, llama.cpp |
| `AsyncStreamingModel` | `stream_async()` | Async; Anthropic, OpenAI, vLLM |
| `BatchChatModel` | `generate_batch()` | vLLM only in Phase 1 |

### Capability declarations per backend

| Backend | ChatModel | ToolCalling | Embedding | Streaming | AsyncStreaming | Batch |
|---------|-----------|-------------|-----------|-----------|---------------|-------|
| OllamaEngine | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| AnthropicEngine | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| OpenAIEngine | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| vLLMEngine | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| LlamaCppEngine | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| MockEngine | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |

### Capability model

`EngineCapabilities` (a Pydantic `BaseModel`) is returned by `ChatModel.get_capabilities()`.
It is the runtime-checkable complement to Protocol composition; callers that receive an
engine as `ChatModel` (and therefore can't statically inspect which other Protocols it
implements) can call `get_capabilities()` to determine what is available.

### Exception hierarchy

Defined in `contracts/engine.py` to ensure uniform error handling across backends:

```
LLMEngineError
├── BackendUnavailableError
├── ModelNotFoundError
├── ContextLengthExceededError
├── RateLimitError
├── GenerationError
└── EngineConfigError
```

All backend implementations must raise only these types (or subclasses thereof).
They must never let raw `requests.HTTPError`, `httpx.ConnectError`, or similar
library-specific exceptions propagate to the caller.

---

## Consequences

### Positive

- Type checker catches capability mismatches at development time, not runtime.
- Backends implement only what they actually support — no dead stubs.
- `EngineCapabilities` provides runtime introspection without dict lookups.
- Exception hierarchy allows `except BackendUnavailableError` across all backends.
- `AsyncStreamingModel` as a separate Protocol correctly routes FastAPI usage.

### Negative / Trade-offs

- More types to import. Mitigated by `contracts/__init__.py` re-exporting everything.
- Functions that accept multiple capability combinations must use `Union` types or
  overloads, which is slightly more verbose than accepting `LLMEngine` everywhere.
- Backends are declared as implementing multiple Protocols; the concrete classes in
  `llm_engines/backends/` must be verified against all declared Protocols (covered
  by conformance tests — see ADR-002).

### Deferred

- `ToolCallingModel` is declared but not implemented in any backend until Phase 2.
  The OllamaEngine Week 3-4 implementation covers `ChatModel` and `EmbeddingModel` only.
- `BatchChatModel` deferred to when vLLM backend is implemented.
- `LlamaCppEngine` tool calling: llama.cpp supports it via GGUF function call grammars,
  but this is deferred; the capability table will be updated when implemented.

---

## Alternatives Considered

### Keep the monolithic ABC

Rejected. The original `generate_with_tools()` on every engine requires every backend
to implement a method it may not support. Runtime `NotImplementedError` is worse than
a compile-time type error.

### Use abstract base classes with mixin inheritance

Rejected. Python's multiple inheritance MRO with ABCs is fragile when mixing capabilities
across many backend classes. `Protocol` structural subtyping achieves the same result
without the inheritance complexity and works correctly with `isinstance()` via
`@runtime_checkable`.

### Single Protocol with optional method returning None

Rejected. Returning `None` for unsupported capabilities makes callers responsible for
None-checking every call. The Protocol composition approach makes unsupported
capabilities unrepresentable in the type system.

---

## Related

- ADR-002: Engine Response Schema (defines `GenerationResponse` used by `ChatModel.generate()`)
- `contracts/engine.py`: Implementation of this decision
- `contracts/tools.py`: `ToolSpec` used by `ToolCallingModel`
