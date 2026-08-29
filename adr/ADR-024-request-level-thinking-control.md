# ADR-024 — Request-level thinking control

**Status:** Accepted  
**Date:** 2026-08-28

## Decision

`GenerationRequest` adds `thinking: bool | None = None`.

- `None` preserves the backend or server default.
- `True` asks a capable backend to enable the model's thinking mode.
- `False` asks a capable backend to suppress thinking.

The field is a preference because not every backend exposes request-level
control. A backend that cannot honor it may ignore it; it must not claim that
reasoning was enabled or disabled as an observed fact.

The vLLM adapter and the non-cloud OpenAI-compatible adapter map a non-null
value to `chat_template_kwargs.enable_thinking`. Cloud OpenAI requests do not
receive this provider-specific option. `ToolExecutor.run()` carries the same
preference through every model turn in a tool loop.

This ADR does not add reasoning text to `GenerationResponse`. Provider-separated
reasoning remains transient and is discarded by the vLLM adapter. It therefore
does not enter Engram, RAG indexes, run artifacts, or inspector output through
this change. Capturing reasoning later requires a separate response, privacy,
recording, and retention decision.

## Acceptance observations

- Default requests omit the provider override.
- `True` and `False` produce the corresponding vLLM request option.
- Tool-loop follow-up requests preserve the original preference.
- A live request against the configured Qwen vLLM server returns a final answer
  with thinking enabled while ordinary default requests remain non-thinking.
- A live local OpenAI-compatible request against `llama-server` honors the same
  override and returns only the final answer. The output budget includes both
  provider-separated reasoning and final-answer tokens; exhausting it during
  reasoning can yield an empty final `content` value.
