"""
llm_engines/backends/openai.py

OpenAIEngine: cloud inference via the OpenAI API (or any OpenAI-compatible endpoint).

Protocols: ChatModel, ToolCallingModel, EmbeddingModel, AsyncStreamingModel
is_cloud = True when using api.openai.com; False for local OpenAI-compat servers.

Requires: pip install llm-engines[openai]
API key: OPENAI_API_KEY env var (or api_key= argument).

Note: vLLMEngine (vllm.py) is a separate backend specialised for local vLLM servers.
This engine is for the OpenAI cloud API and third-party OpenAI-compatible APIs
(Together AI, Groq, etc.) where you have an API key.
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
    ContextLengthExceededError,
    EmbeddingModel,
    EmbeddingRequest,
    EmbeddingResponse,
    EngineCapabilities,
    EngineConfigError,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    RateLimitError,
    ToolCall,
    ToolCallingModel,
    ToolSpec,
    UsageStats,
)

try:
    import openai as _openai
except ImportError as _e:
    raise ImportError(
        "OpenAIEngine requires the 'openai' package. "
        "Install with: pip install llm-engines[openai]"
    ) from _e

logger = logging.getLogger(__name__)

BACKEND = "openai"

_FINISH_MAP = {
    "stop":          "stop",
    "length":        "length",
    "tool_calls":    "tool_call",
    "content_filter":"content_filter",
}


def _map_finish(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    return _FINISH_MAP.get(raw, "unknown")


def _to_openai_messages(request: GenerationRequest) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    for m in request.messages:
        if m.role == "tool":
            msgs.append({
                "role": "tool",
                "tool_call_id": m.tool_call_id or "",
                "content": m.content or "",
            })
        elif m.role == "assistant" and m.tool_calls:
            tool_calls_payload = [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": str(tc.arguments)},
                }
                for tc in m.tool_calls
            ]
            msgs.append({
                "role": "assistant",
                "content": m.content,
                "tool_calls": tool_calls_payload,
            })
        else:
            msgs.append({"role": m.role, "content": m.content or ""})
    return msgs


def _extract_tool_calls(choice: Any) -> list[ToolCall]:
    raw = getattr(choice.message, "tool_calls", None) or []
    calls = []
    for tc in raw:
        import json
        try:
            args = json.loads(tc.function.arguments)
        except Exception:
            args = {"raw": tc.function.arguments}
        calls.append(ToolCall(
            call_id=tc.id,
            name=tc.function.name,
            arguments=args,
        ))
    return calls


class OpenAIEngine:
    """
    LLM engine backed by the OpenAI API or any OpenAI-compatible endpoint.

    Args:
        model:     Model name, e.g. "gpt-4o-mini", "gpt-4o".
        api_key:   API key. Defaults to OPENAI_API_KEY env var.
        base_url:  Override API endpoint for OpenAI-compatible services
                   (e.g. "https://api.groq.com/openai/v1").
                   Set is_cloud=False for local OpenAI-compat servers.
        is_cloud:  True for cloud APIs (triggers cloud policy in FailoverEngine).
                   Set to False when using a local OpenAI-compat server.
        timeout:   Request timeout in seconds.
        debug:     Preserve raw provider payload in responses.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        is_cloud: bool = True,
        timeout: float = 60.0,
        debug: bool = False,
    ) -> None:
        if not isinstance(is_cloud, bool):
            raise TypeError(f"is_cloud={is_cloud!r} type={type(is_cloud).__name__}")
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if is_cloud and not resolved_key:
            raise EngineConfigError(
                "OpenAIEngine requires OPENAI_API_KEY env var or api_key= argument."
            )
        if not resolved_key:
            # Local OpenAI-compatible servers (llama-server, vLLM, etc.) don't need a real key
            resolved_key = "dummy"

        self.model = model
        self.is_cloud = is_cloud
        self.debug = debug

        client_kwargs: dict[str, Any] = {
            "api_key": resolved_key,
            "timeout": timeout,
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        try:
            self._client = _openai.OpenAI(**client_kwargs)
            self._async_client = _openai.AsyncOpenAI(**client_kwargs)
        except Exception as e:
            raise EngineConfigError(f"Failed to create OpenAI client: {e}") from e

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=True,
            streaming=False,
            async_streaming=True,
            tool_calling=True,
            embeddings=True,
            structured_output=True,   # via response_format={"type": "json_object"}
            batch_generation=False,
            vision=True,
            usage_reporting=True,
            logprobs=True,
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages = _to_openai_messages(request)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop:
            kwargs["stop"] = request.stop

        t0 = time.perf_counter()
        try:
            raw = self._client.chat.completions.create(**kwargs)
        except _openai.RateLimitError as e:
            raise RateLimitError(f"OpenAI rate limit: {e}") from e
        except _openai.APIConnectionError as e:
            raise BackendUnavailableError(f"OpenAI unreachable: {e}") from e
        except _openai.BadRequestError as e:
            msg = str(e).lower()
            if "context" in msg or "too long" in msg:
                raise ContextLengthExceededError(str(e)) from e
            raise GenerationError(f"OpenAI bad request: {e}") from e
        except Exception as e:
            raise GenerationError(f"OpenAI generation failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        return self._build_response(raw, latency_ms)

    def _build_response(self, raw: Any, latency_ms: float) -> GenerationResponse:
        choice = raw.choices[0]
        content = choice.message.content
        tool_calls = _extract_tool_calls(choice)
        finish_reason = _map_finish(choice.finish_reason)

        u = getattr(raw, "usage", None)
        usage = UsageStats(
            input_tokens=getattr(u, "prompt_tokens", None),
            output_tokens=getattr(u, "completion_tokens", None),
            total_tokens=getattr(u, "total_tokens", None),
            latency_ms=round(latency_ms, 3),
        )

        return GenerationResponse(
            message=ChatMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
            ),
            finish_reason=finish_reason,  # type: ignore[arg-type]
            usage=usage,
            model_name=getattr(raw, "model", self.model),
            backend=BACKEND,
            raw_provider_payload=(
                {"id": raw.id, "model": raw.model} if self.debug else None
            ),
        )

    # ------------------------------------------------------------------
    # ToolCallingModel Protocol
    # ------------------------------------------------------------------

    def generate_with_tools(
        self,
        request: GenerationRequest,
        available_tools: list[ToolSpec],
    ) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages: Any = _to_openai_messages(request)
        tools_payload: Any = [t.to_openai_schema() for t in available_tools]

        t0 = time.perf_counter()
        try:
            raw = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                tools=tools_payload,
                tool_choice="auto",
            )
        except _openai.RateLimitError as e:
            raise RateLimitError(f"OpenAI rate limit: {e}") from e
        except _openai.APIConnectionError as e:
            raise BackendUnavailableError(f"OpenAI unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"OpenAI tool generation failed: {e}") from e

        return self._build_response(raw, (time.perf_counter() - t0) * 1000)

    # ------------------------------------------------------------------
    # EmbeddingModel Protocol
    # ------------------------------------------------------------------

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        embed_model = request.model or "text-embedding-3-small"
        try:
            raw = self._client.embeddings.create(
                model=embed_model,
                input=request.texts,
            )
        except _openai.RateLimitError as e:
            raise RateLimitError(f"OpenAI rate limit: {e}") from e
        except _openai.APIConnectionError as e:
            raise BackendUnavailableError(f"OpenAI unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"OpenAI embed failed: {e}") from e

        vectors = [item.embedding for item in raw.data]
        dims = len(vectors[0]) if vectors else 0
        return EmbeddingResponse(
            vectors=vectors,
            dimensions=dims,
            model_name=embed_model,
            backend=BACKEND,
        )

    # ------------------------------------------------------------------
    # AsyncStreamingModel Protocol
    # ------------------------------------------------------------------

    async def stream_async(self, request: GenerationRequest) -> AsyncIterator[str]:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages: Any = _to_openai_messages(request)
        try:
            stream: Any = await self._async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except _openai.RateLimitError as e:
            raise RateLimitError(f"OpenAI rate limit: {e}") from e
        except _openai.APIConnectionError as e:
            raise BackendUnavailableError(f"OpenAI unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"OpenAI streaming failed: {e}") from e
