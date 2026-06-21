"""
llm_engines/backends/anthropic.py

AnthropicEngine: cloud inference via the Anthropic API.

Protocols implemented: ChatModel, ToolCallingModel, AsyncStreamingModel
Embeddings: not supported (Anthropic has no native embedding endpoint)
Sync streaming: not implemented (use stream_async for FastAPI/asyncio)

Requires: pip install llm-engines[anthropic]
API key: ANTHROPIC_API_KEY env var (or pass api_key= directly)

Privacy note: is_cloud = True — FailoverEngine will apply cloud_policy
(memory block sanitisation) before routing to this engine.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator

from llm_engines.contracts import (
    AsyncStreamingModel,
    BackendUnavailableError,
    ChatMessage,
    ChatModel,
    EngineCapabilities,
    EngineConfigError,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    RateLimitError,
    ContextLengthExceededError,
    ToolCall,
    ToolCallingModel,
    ToolSpec,
    UsageStats,
)

try:
    import anthropic as _anthropic
except ImportError as _e:
    raise ImportError(
        "AnthropicEngine requires the 'anthropic' package. "
        "Install with: pip install llm-engines[anthropic]"
    ) from _e

logger = logging.getLogger(__name__)

BACKEND = "anthropic"

# Map Anthropic stop_reason → canonical FinishReason
_FINISH_MAP: dict[str, str] = {
    "end_turn":     "stop",
    "max_tokens":   "length",
    "tool_use":     "tool_call",
    "stop_sequence":"stop",
}


def _map_finish(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    return _FINISH_MAP.get(raw, "unknown")


def _convert_messages(request: GenerationRequest) -> tuple[str | None, list[dict[str, Any]]]:
    """Split GenerationRequest into system prompt + messages list for Anthropic API."""
    system: str | None = None
    messages: list[dict[str, Any]] = []
    for msg in request.messages:
        if msg.role == "system":
            system = msg.content or ""
        elif msg.role == "tool":
            # Tool result message
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id or "",
                    "content": msg.content or "",
                }]
            })
        elif msg.role == "assistant" and msg.tool_calls:
            # Assistant message with tool calls
            content: list[dict[str, Any]] = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.call_id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            messages.append({"role": "assistant", "content": content})
        else:
            messages.append({"role": msg.role, "content": msg.content or ""})
    return system, messages


def _extract_tool_calls(response_content: list[Any]) -> list[ToolCall]:
    """Extract ToolCall objects from Anthropic response content blocks."""
    calls = []
    for block in response_content:
        if getattr(block, "type", None) == "tool_use":
            calls.append(ToolCall(
                call_id=block.id,
                name=block.name,
                arguments=block.input or {},
            ))
    return calls


def _extract_text(response_content: list[Any]) -> str:
    """Extract concatenated text from Anthropic response content blocks."""
    parts = []
    for block in response_content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


class AnthropicEngine:
    """
    LLM engine backed by the Anthropic API.

    Args:
        model:      Anthropic model identifier, e.g. "claude-sonnet-4-6".
        api_key:    API key. Defaults to ANTHROPIC_API_KEY env var.
        max_tokens: Default max tokens for generation (required by Anthropic API).
        timeout:    Request timeout in seconds.
        debug:      If True, preserve raw provider payload in responses.
    """

    # Signals to FailoverEngine that cloud data policy should be applied
    is_cloud: bool = True

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        max_tokens: int = 1024,
        timeout: float = 60.0,
        debug: bool = False,
    ) -> None:
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise EngineConfigError(
                "AnthropicEngine requires ANTHROPIC_API_KEY env var or api_key= argument."
            )

        self.model = model
        self.debug = debug
        self._default_max_tokens = max_tokens

        try:
            self._client = _anthropic.Anthropic(
                api_key=resolved_key,
                timeout=timeout,
            )
            self._async_client = _anthropic.AsyncAnthropic(
                api_key=resolved_key,
                timeout=timeout,
            )
        except Exception as e:
            raise EngineConfigError(f"Failed to create Anthropic client: {e}") from e

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=True,
            streaming=False,
            async_streaming=True,
            tool_calling=True,
            embeddings=False,
            structured_output=False,
            batch_generation=False,
            vision=True,         # Claude supports image input
            usage_reporting=True,
            logprobs=False,
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate via Anthropic Messages API (synchronous)."""
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        system, messages = _convert_messages(request)
        max_tokens = request.max_tokens or self._default_max_tokens

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": request.temperature,
        }
        if system:
            kwargs["system"] = system
        if request.stop:
            kwargs["stop_sequences"] = request.stop

        t0 = time.perf_counter()
        try:
            raw = self._client.messages.create(**kwargs)
        except _anthropic.RateLimitError as e:
            raise RateLimitError(f"Anthropic rate limit: {e}") from e
        except _anthropic.BadRequestError as e:
            msg = str(e).lower()
            if "too long" in msg or "context" in msg:
                raise ContextLengthExceededError(str(e)) from e
            raise GenerationError(f"Anthropic bad request: {e}") from e
        except _anthropic.APIConnectionError as e:
            raise BackendUnavailableError(f"Anthropic unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"Anthropic generation failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        return self._build_response(raw, latency_ms)

    def _build_response(self, raw: Any, latency_ms: float) -> GenerationResponse:
        text = _extract_text(raw.content)
        tool_calls = _extract_tool_calls(raw.content)
        finish_reason = _map_finish(getattr(raw, "stop_reason", None))

        usage_raw = getattr(raw, "usage", None)
        input_tokens = getattr(usage_raw, "input_tokens", None)
        output_tokens = getattr(usage_raw, "output_tokens", None)
        usage = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=(
                (input_tokens + output_tokens)
                if input_tokens is not None and output_tokens is not None
                else None
            ),
            latency_ms=round(latency_ms, 3),
        )

        debug_payload: dict[str, Any] | None = None
        if self.debug:
            debug_payload = {
                "id": getattr(raw, "id", None),
                "model": getattr(raw, "model", None),
                "stop_reason": getattr(raw, "stop_reason", None),
                "usage": {"input": input_tokens, "output": output_tokens},
            }

        return GenerationResponse(
            message=ChatMessage(
                role="assistant",
                content=text or None,
                tool_calls=tool_calls,
            ),
            finish_reason=finish_reason,  # type: ignore[arg-type]
            usage=usage,
            model_name=self.model,
            backend=BACKEND,
            raw_provider_payload=debug_payload,
        )

    # ------------------------------------------------------------------
    # ToolCallingModel Protocol
    # ------------------------------------------------------------------

    def generate_with_tools(
        self,
        request: GenerationRequest,
        available_tools: list[ToolSpec],
    ) -> GenerationResponse:
        """Generate with tool use via Anthropic Messages API."""
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        system, messages = _convert_messages(request)
        max_tokens = request.max_tokens or self._default_max_tokens

        # Convert ToolSpec objects to Anthropic tool format
        tools_payload = []
        for tool in available_tools:
            props = {}
            required = list(getattr(tool, "required_params", []))
            for name, param in (getattr(tool, "parameters", {}) or {}).items():
                props[name] = {
                    "type": getattr(param, "type", "string"),
                    "description": getattr(param, "description", ""),
                }
                if getattr(param, "enum", None):
                    props[name]["enum"] = param.enum
            tools_payload.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            })

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": request.temperature,
            "tools": tools_payload,
        }
        if system:
            kwargs["system"] = system

        t0 = time.perf_counter()
        try:
            raw = self._client.messages.create(**kwargs)
        except _anthropic.RateLimitError as e:
            raise RateLimitError(f"Anthropic rate limit: {e}") from e
        except _anthropic.APIConnectionError as e:
            raise BackendUnavailableError(f"Anthropic unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"Anthropic tool generation failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        return self._build_response(raw, latency_ms)

    # ------------------------------------------------------------------
    # AsyncStreamingModel Protocol
    # ------------------------------------------------------------------

    async def stream_async(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Stream tokens asynchronously via Anthropic streaming API."""
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        system, messages = _convert_messages(request)
        max_tokens = request.max_tokens or self._default_max_tokens

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": request.temperature,
        }
        if system:
            kwargs["system"] = system
        if request.stop:
            kwargs["stop_sequences"] = request.stop

        try:
            async with self._async_client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield text
        except _anthropic.RateLimitError as e:
            raise RateLimitError(f"Anthropic rate limit: {e}") from e
        except _anthropic.APIConnectionError as e:
            raise BackendUnavailableError(f"Anthropic unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"Anthropic streaming failed: {e}") from e
