"""
llm_engines/backends/vllm.py

vLLMEngine: high-performance local inference via vLLM's OpenAI-compatible API.

Protocols: ChatModel, ToolCallingModel, AsyncStreamingModel, BatchChatModel, LogprobModel
is_cloud = False (local server, no sanitisation applied by FailoverEngine)

Requires: a running vLLM server — NOT the vllm Python package directly.
vLLM is invoked as a server process; this engine talks to it over HTTP
using the openai package as the client.

Typical startup:
    vllm serve Qwen/Qwen2.5-32B-Instruct-AWQ \
        --port 8000 \
        --gpu-memory-utilization 0.92 \
        --max-model-len 8192

Requires: pip install llm-engines[openai]  (uses openai client against vLLM)

Key differences from OpenAIEngine:
  - No API key required (passes "dummy")
  - Logprobs available via the OpenAI-compat /v1/chat/completions endpoint
  - Model name is resolved at startup against /v1/models (vLLM reports its
    own model ID which may differ from what you specify in YAML)
  - Batch generation supported via multiple parallel async calls
  - is_cloud = False → FailoverEngine does not strip memory context
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from llm_engines.contracts import (
    AsyncStreamingModel,
    BackendUnavailableError,
    BatchChatModel,
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
    LogprobModel,
    LogprobResult,
    TokenLogprob,
    ToolCall,
    ToolSpec,
    UsageStats,
)

try:
    import openai as _openai
except ImportError as _e:
    raise ImportError(
        "vLLMEngine uses the 'openai' package to communicate with vLLM's HTTP API. "
        "Install with: pip install llm-engines[openai]"
    ) from _e

logger = logging.getLogger(__name__)

BACKEND = "vllm"

_FINISH_MAP = {
    "stop":       "stop",
    "length":     "length",
    "tool_calls": "tool_call",
}


def _map_finish(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    return _FINISH_MAP.get(raw, "unknown")


def _to_openai_messages(request: GenerationRequest) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role == "tool":
            messages.append({
                "role": "tool",
                "tool_call_id": message.tool_call_id or "",
                "content": message.content or "",
            })
        elif message.role == "assistant" and message.tool_calls:
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in message.tool_calls
                ],
            })
        else:
            messages.append({"role": message.role, "content": message.content or ""})
    return messages


def _extract_tool_calls(choice: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for raw_call in getattr(choice.message, "tool_calls", None) or []:
        try:
            arguments = json.loads(raw_call.function.arguments)
        except (TypeError, ValueError):
            arguments = {"raw": raw_call.function.arguments}
        calls.append(ToolCall(
            call_id=raw_call.id,
            name=raw_call.function.name,
            arguments=arguments,
        ))
    return calls


def _apply_thinking_preference(
    kwargs: dict[str, Any], request: GenerationRequest
) -> None:
    if request.thinking is not None:
        kwargs["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": request.thinking}
        }


def _apply_seed_preference(kwargs: dict[str, Any], request: GenerationRequest) -> None:
    if request.seed is not None:
        kwargs["seed"] = request.seed


class vLLMEngine:
    """
    LLM engine backed by a local vLLM HTTP server.

    Args:
        model:          Model name to request. vLLM may return a different
                        resolved name — check model_name in responses.
        base_url:       vLLM server URL, e.g. "http://localhost:8000/v1".
        max_context:    Maximum context length. vLLM enforces its own limit;
                        this is used for client-side truncation decisions.
        timeout:        Request timeout in seconds.
        debug:          Preserve raw provider payload in responses.
    """

    is_cloud: bool = False

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:8000/v1",
        max_context: int = 8192,
        timeout: float = 120.0,
        debug: bool = False,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_context = max_context
        self.debug = debug

        try:
            self._client = _openai.OpenAI(
                api_key="dummy",
                base_url=self.base_url,
                timeout=timeout,
            )
            self._async_client = _openai.AsyncOpenAI(
                api_key="dummy",
                base_url=self.base_url,
                timeout=timeout,
            )
        except Exception as e:
            raise EngineConfigError(f"Failed to create vLLM client: {e}") from e

        self._resolved_model = self._resolve_model()

    def _resolve_model(self) -> str:
        """
        Query /v1/models and resolve the best match for self.model.

        vLLM exposes the model under its HuggingFace ID, which may differ
        from a short alias. Returns the resolved ID, or self.model if
        the server is unreachable (allowing deferred connection).
        """
        try:
            models = self._client.models.list()
            ids = [m.id for m in models.data]
            if not ids:
                return self.model
            # Exact match
            if self.model in ids:
                return self.model
            # Suffix match: "Qwen2.5-32B-Instruct-AWQ" matches "Qwen/Qwen2.5-32B-Instruct-AWQ"
            for model_id in ids:
                if model_id.endswith(self.model) or self.model in model_id:
                    logger.info("vLLM model resolved: '%s' → '%s'", self.model, model_id)
                    return model_id
            # Fallback: use first available
            logger.warning(
                "vLLM: requested model '%s' not found. Using '%s'. Available: %s",
                self.model, ids[0], ids,
            )
            return ids[0]
        except Exception as e:
            logger.warning("vLLM model discovery failed (%s) — using '%s'", e, self.model)
            return self.model

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=True,
            streaming=False,
            async_streaming=True,
            tool_calling=True,
            embeddings=False,      # vLLM can serve embedding models separately
            structured_output=False,
            batch_generation=True,
            vision=False,
            usage_reporting=True,
            logprobs=True,
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages: Any = _to_openai_messages(request)
        kwargs: dict[str, Any] = {
            "model": self._resolved_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.stop:
            kwargs["stop"] = request.stop
        _apply_thinking_preference(kwargs, request)
        _apply_seed_preference(kwargs, request)

        t0 = time.perf_counter()
        try:
            raw = self._client.chat.completions.create(**kwargs)
        except _openai.APIConnectionError as e:
            raise BackendUnavailableError(
                f"vLLM not reachable at {self.base_url}. Is vLLM running?"
            ) from e
        except _openai.BadRequestError as e:
            msg = str(e).lower()
            if "max_model_len" in msg or "too long" in msg or "context" in msg:
                raise ContextLengthExceededError(str(e)) from e
            raise GenerationError(f"vLLM bad request: {e}") from e
        except Exception as e:
            raise GenerationError(f"vLLM generation failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        return self._build_response(raw, latency_ms, request=request)

    def _build_response(
        self, raw: Any, latency_ms: float, *, request: GenerationRequest
    ) -> GenerationResponse:
        choice = raw.choices[0]
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
                content=choice.message.content,
                tool_calls=_extract_tool_calls(choice),
            ),
            finish_reason=_map_finish(choice.finish_reason),  # type: ignore[arg-type]
            usage=usage,
            model_name=getattr(raw, "model", self._resolved_model),
            backend=BACKEND,
            raw_provider_payload=(
                {"id": raw.id, "model": raw.model} if self.debug else None
            ),
            seed_status="accepted" if request.seed is not None else "not_requested",
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

        kwargs: dict[str, Any] = {
            "model": self._resolved_model,
            "messages": _to_openai_messages(request),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "tools": [tool.to_openai_schema() for tool in available_tools],
            "tool_choice": "auto",
        }
        if request.stop:
            kwargs["stop"] = request.stop
        _apply_thinking_preference(kwargs, request)
        _apply_seed_preference(kwargs, request)

        started = time.perf_counter()
        try:
            raw = self._client.chat.completions.create(**kwargs)
        except _openai.APIConnectionError as exc:
            raise BackendUnavailableError(
                f"vLLM not reachable at {self.base_url}. Is vLLM running?"
            ) from exc
        except _openai.BadRequestError as exc:
            message = str(exc).lower()
            if "max_model_len" in message or "too long" in message or "context" in message:
                raise ContextLengthExceededError(str(exc)) from exc
            raise GenerationError(f"vLLM tool request rejected: {exc}") from exc
        except Exception as exc:
            raise GenerationError(f"vLLM tool generation failed: {exc}") from exc

        return self._build_response(
            raw, (time.perf_counter() - started) * 1000, request=request
        )

    # ------------------------------------------------------------------
    # LogprobModel Protocol
    # ------------------------------------------------------------------

    def generate_with_logprobs(
        self,
        request: GenerationRequest,
        top_logprobs: int = 0,
    ) -> LogprobResult:
        """Generate with token logprobs. Used by Engram's RTRL surprise filter."""
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages: Any = _to_openai_messages(request)
        actual_top = max(1, top_logprobs)

        kwargs: dict[str, Any] = {
            "model": self._resolved_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "logprobs": True,
            "top_logprobs": actual_top,
        }
        _apply_thinking_preference(kwargs, request)
        _apply_seed_preference(kwargs, request)

        try:
            raw = self._client.chat.completions.create(**kwargs)
        except _openai.APIConnectionError as e:
            raise BackendUnavailableError(f"vLLM unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"vLLM logprob generation failed: {e}") from e

        choice = raw.choices[0]
        text = choice.message.content or ""
        token_logprobs: list[TokenLogprob] = []

        if choice.logprobs and choice.logprobs.content:
            for tlp in choice.logprobs.content:
                token_logprobs.append(TokenLogprob(
                    token=tlp.token,
                    logprob=tlp.logprob,
                    bytes=getattr(tlp, "bytes", None),
                ))

        return LogprobResult(text=text, token_logprobs=token_logprobs)

    # ------------------------------------------------------------------
    # AsyncStreamingModel Protocol
    # ------------------------------------------------------------------

    async def stream_async(self, request: GenerationRequest) -> AsyncIterator[str]:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages: Any = _to_openai_messages(request)
        kwargs: dict[str, Any] = {
            "model": self._resolved_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }
        _apply_thinking_preference(kwargs, request)
        _apply_seed_preference(kwargs, request)
        try:
            stream: Any = await self._async_client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
        except _openai.APIConnectionError as e:
            raise BackendUnavailableError(f"vLLM unreachable: {e}") from e
        except Exception as e:
            raise GenerationError(f"vLLM streaming failed: {e}") from e

    # ------------------------------------------------------------------
    # BatchChatModel Protocol
    # ------------------------------------------------------------------

    def generate_batch(
        self,
        requests: list[GenerationRequest],
    ) -> list[GenerationResponse]:
        """
        Process multiple requests in parallel via asyncio.

        vLLM handles concurrent requests efficiently through continuous batching.
        This method fans out all requests simultaneously rather than serially.
        """
        async def _run_all() -> list[GenerationResponse]:
            tasks = [self._generate_async(req) for req in requests]
            return await asyncio.gather(*tasks)

        async def _ensure_loop() -> list[GenerationResponse]:
            return await _run_all()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in an async context — use nest_asyncio or thread pool
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _run_all())
                    return future.result()
            return loop.run_until_complete(_run_all())
        except Exception:
            return asyncio.run(_run_all())

    async def _generate_async(self, request: GenerationRequest) -> GenerationResponse:
        messages: Any = _to_openai_messages(request)
        kwargs: dict[str, Any] = {
            "model": self._resolved_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        _apply_thinking_preference(kwargs, request)
        _apply_seed_preference(kwargs, request)
        t0 = time.perf_counter()
        try:
            raw = await self._async_client.chat.completions.create(**kwargs)
        except Exception as e:
            raise GenerationError(f"vLLM async generation failed: {e}") from e
        return self._build_response(
            raw, (time.perf_counter() - t0) * 1000, request=request
        )
