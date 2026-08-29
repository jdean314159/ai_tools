# ADR-025 — Validated streamed tool-call events

**Status:** Accepted  
**Date:** 2026-08-29

## Decision

Tool-call streaming uses a separate `AsyncToolStreamingModel` protocol:

```python
stream_with_tools_async(request, available_tools)
```

It does not change the existing text-only `stream_async()` interface. The new
method yields a closed set of typed events:

- `TextDeltaEvent` for immediately usable text fragments;
- `ToolCallEvent` for one complete `ToolCall`; and
- `StreamFinishedEvent` for the terminal provider finish reason.

Provider tool-name and argument fragments are not public events. The adapter
buffers them by provider call index. It emits a `ToolCallEvent` only after the
call ID and function name are present and the accumulated arguments parse as a
JSON object. Missing identity, truncated JSON, non-object JSON, or malformed
JSON raises `GenerationError`. No repair is attempted.

This boundary prevents a partial streamed argument such as `"{"` from being
executed or written into conversation history. It also preserves compatibility
for callers that need only text streaming.

The protocol streams one model response; it does not execute tools or continue
the multi-turn loop. `ToolExecutor` remains the synchronous complete-response
loop. A future streaming executor must consume only complete `ToolCallEvent`
values and requires a separate lifecycle and error-handling decision.

`EngineCapabilities.streaming_tool_calls` distinguishes this interface from
ordinary async text streaming. The OpenAI-compatible backend is the first
implementation.

## Acceptance observations

- Text fragments are emitted as ordered `TextDeltaEvent` values.
- Fragmented tool arguments produce no public event before complete JSON exists.
- A complete call is emitted once, followed by one terminal finish event.
- Truncated JSON raises `GenerationError` and emits no `ToolCallEvent`.
- Existing `stream_async()` behavior remains unchanged.
- A live Qwen llama.cpp stream preserved apostrophes, Unicode, arrays, and a
  nested object exactly in one complete tool-call event.
