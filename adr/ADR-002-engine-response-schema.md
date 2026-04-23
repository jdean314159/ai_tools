# ADR-002: Engine Response Schema

**Date:** 2026-04-13
**Status:** Accepted
**Deciders:** Jeff Dean

---

## Context

All previous engine implementations returned plain `str` from `generate()`:

```python
def generate(self, prompt: str) -> str:
    return response.json()["text"]
```

This discards information that callers need:

- **Tool calls**: If the model decided to call a tool, that information is lost.
  The caller has no way to detect it without parsing the string.
- **Finish reason**: Was generation cut off by `max_tokens`? Stopped naturally?
  Callers can't distinguish these cases without inspecting the raw response.
- **Token usage**: Cost tracking, context window management, and rate limit
  awareness all require token counts. These are thrown away.
- **Which model ran**: In adaptive/fallback scenarios, the caller doesn't know
  whether the main model or a fallback actually served the request.
- **Debugging payload**: The raw provider response is discarded, making
  post-hoc debugging impossible.

The informal `dict` return from `generate_with_tools()` had the same problems,
plus inconsistent key names across backends.

---

## Decision

**All engine `generate()` calls return `GenerationResponse`. Never plain `str`.**

### Schema (`contracts/engine.py`)

```python
class GenerationResponse(BaseModel):
    message: ChatMessage            # The generated message (role="assistant")
    finish_reason: FinishReason     # "stop" | "length" | "tool_call" | ...
    usage: UsageStats               # Token counts and latency
    model_name: str                 # Model that actually ran
    backend: str                    # Backend that served the request
    raw_provider_payload: dict | None  # Full provider response, for debugging
```

```python
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None
    tool_calls: list[ToolCall]      # Non-empty when finish_reason == "tool_call"
    tool_call_id: str | None        # For tool result messages
    name: str | None
```

```python
class UsageStats(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    latency_ms: float | None        # float for sub-millisecond local inference
```

```python
FinishReason = Literal[
    "stop", "length", "tool_call", "content_filter", "error", "unknown"
]
```

### Rules

1. **Never return plain `str`.** Backends that currently return strings must
   wrap output in `GenerationResponse` before returning to the caller.

2. **Never raise on missing optional fields.** `UsageStats` fields are all
   `Optional`; backends that don't report token counts leave them `None`.
   Callers that need token counts must check capabilities first.

3. **Always populate `model_name` and `backend`.** These are required fields.
   A backend that runs a fallback model must report the fallback's name, not
   the originally requested model.

4. **Preserve `raw_provider_payload` in debug mode.** The full JSON response
   from the provider should be stored here when `debug=True` is passed to the
   engine constructor. In production it may be `None` to avoid memory overhead.

5. **`finish_reason` must be one of the defined literals.** Backends that
   receive an unrecognized reason from their provider must map it to `"unknown"`,
   not pass through the raw string.

6. **Tool calls in `message.tool_calls` must be typed `ToolCall` objects.**
   Backends must parse the provider's raw tool call format into `ToolCall`
   (with `call_id`, `name`, `arguments`) before returning.

### Streaming

Streaming variants (`StreamingModel.stream()`, `AsyncStreamingModel.stream_async()`)
yield `str` tokens during generation, matching current consumer expectations.
When streaming completes, the caller is responsible for assembling the full
`GenerationResponse` if usage stats or finish reason are needed. Backends may
provide a `get_last_response() -> GenerationResponse` method as a convenience,
but this is not part of the Protocol contract in Phase 1.

---

## Consequences

### Positive

- Tool calls are never silently dropped; `finish_reason == "tool_call"` signals
  the caller to inspect `message.tool_calls`.
- Token accounting is always available (when supported) without parsing raw dicts.
- `model_name` + `backend` make fallback behavior observable.
- `raw_provider_payload` preserves full debuggability without permanent overhead.
- Pydantic validation catches malformed responses at the boundary, not deep in
  application logic.

### Negative / Trade-offs

- Callers must update from `result = engine.generate(...)` (str) to
  `result.message.content` for the text. This is a one-time migration.
- Slightly more memory per response. Negligible in practice.

### Migration pattern for existing code

```python
# Before
text = engine.generate("Hello")
print(text)

# After
response = engine.generate(GenerationRequest(
    messages=[ChatMessage(role="user", content="Hello")]
))
print(response.message.content)
if response.message.tool_calls:
    handle_tool_calls(response.message.tool_calls)
print(f"Tokens used: {response.usage.total_tokens}")
```

---

## Deferred

- **Structured output**: `GenerationRequest.json_schema` is defined but backends
  that support constrained generation (Ollama format mode, OpenAI response_format)
  will implement it in a later iteration. Not part of Phase 1 OllamaEngine.
- **Logprobs**: `EngineCapabilities.logprobs` is declared; no Phase 1 backend
  exposes them. Deferred to research / eval harness work.
- **Streaming `GenerationResponse` assembly**: The streaming `get_last_response()`
  convenience is deferred. Callers that need post-stream metadata should use
  non-streaming `generate()` or assemble manually.

---

## Alternatives Considered

### Return `dict[str, Any]`

Rejected. Dicts are not validated, not typed, and not self-documenting. Every
caller would need to guard against missing keys. Pydantic validation at the
boundary is strictly better.

### Return `(str, dict)` tuple

Rejected. Callers that only want text must unpack; callers that want metadata
need to know the tuple structure. `GenerationResponse` is cleaner and extensible.

### Keep streaming returning `GenerationResponse` with partial content

Considered. Returning `GenerationResponse` mid-stream (with `finish_reason="unknown"`
and partial content) is achievable but adds complexity for consumers. Deferred.
The simpler token-yielding stream is sufficient for Phase 1.

---

## Related

- ADR-001: Engine Capability Model (defines the Protocols that use this schema)
- `contracts/engine.py`: Implementation of this decision
- `contracts/tools.py`: `ToolCall` structure referenced by `ChatMessage.tool_calls`
