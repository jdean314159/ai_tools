"""
llm_engines/backends/ollama.py

OllamaEngine: local inference via Ollama native HTTP API.

Protocols implemented: ChatModel, EmbeddingModel, StreamingModel, LogprobModel
Tool calling: deferred to Phase 2.

Design decisions:
  - Uses /api/chat (not /v1/chat/completions): the OpenAI-compat endpoint
    ignores the 'think' flag needed to suppress CoT on Qwen3 and similar
    reasoning models.
  - All HTTP uses raw urllib — no ollama package required. This matches
    Engram's approach and removes a dependency.
  - Logprobs use /v1/chat/completions (OpenAI-compat) because /api/chat
    does not expose logprobs in the same format. Requires Ollama >= 0.12.11.
  - num_gpu: pass None for Ollama default (all GPU), 0 for CPU-only,
    N for N-layer split offload. Critical for 32B+ models on 24GB VRAM.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Iterator
from urllib.parse import urlparse

from llm_engines.contracts import (
    BackendUnavailableError,
    ChatMessage,
    ContextLengthExceededError,
    EmbeddingRequest,
    EmbeddingResponse,
    EngineCapabilities,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    LogprobResult,
    ModelNotFoundError,
    TokenLogprob,
    UsageStats,
)
from llm_engines.discovery import (
    check_ollama_logprobs_support,
    check_ollama_running,
    ensure_ollama_model,
    list_ollama_models,
)
from llm_engines.utils.json_schema import inline_local_json_schema_refs

BACKEND = "ollama"

_FINISH_MAP: dict[str, str] = {
    "stop": "stop",
    "length": "length",
    "": "unknown",
}


def _map_finish(raw: str | None) -> str:
    if raw is None:
        return "unknown"
    return _FINISH_MAP.get(raw.lower(), "unknown")


def _normalize_host_url(host: str) -> str:
    """Accept root URL or OpenAI-compat /v1 URL; always return API root."""
    cleaned = (host or "").strip().rstrip("/")
    if not cleaned:
        return "http://localhost:11434"
    parsed = urlparse(cleaned)
    if not parsed.scheme or not parsed.netloc:
        return cleaned
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    return f"{parsed.scheme}://{parsed.netloc}{path}"


class OllamaEngine:
    """
    LLM engine backed by a local Ollama instance.

    Args:
        model:       Ollama model tag, e.g. "qwen3:27b"
        host:        Ollama server URL. Default: http://localhost:11434
        keep_alive:  Seconds to keep model loaded after last request.
                     0 = unload immediately (saves VRAM for multi-model setups).
                     -1 = keep forever.
        think:       If False, passes think=false to suppress chain-of-thought
                     on Qwen3 and other reasoning models. Default: False.
        num_gpu:     None = Ollama default (all GPU layers).
                     0 = CPU-only (no VRAM used, slower).
                     N = N layers on GPU, remainder on CPU (split offload).
                     Use for 32B+ models that exceed VRAM. e.g. num_gpu=40
                     offloads ~40 layers to RTX 3090 (24GB), rest to CPU.
        auto_pull:   If True, pull the model if not present at startup.
        debug:       If True, raw provider payloads are preserved in responses.
        options:     Additional Ollama generation options (num_ctx, seed, etc.)
    """

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        keep_alive: int = 300,
        think: bool = False,
        num_gpu: int | None = None,
        auto_pull: bool = False,
        debug: bool = False,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.host = _normalize_host_url(host)
        self.keep_alive = keep_alive
        self.think = think
        self.num_gpu = num_gpu
        self.debug = debug
        self.options = options or {}

        if not check_ollama_running(self.host):
            raise BackendUnavailableError(
                f"Ollama not reachable at {self.host}. "
                "Is 'ollama serve' running?"
            )

        if auto_pull:
            ensure_ollama_model(model, self.host)
        else:
            self._verify_model()

        self._supports_logprobs = check_ollama_logprobs_support(host)
        if not self._supports_logprobs:
            import logging
            logging.getLogger(__name__).warning(
                "Ollama < 0.12.11: logprobs unavailable. "
                "Surprise filter will run in conservative mode."
            )

    def _verify_model(self) -> None:
        """Check model exists. Exact match first, then tag-less prefix as fallback."""
        available = [m.name for m in list_ollama_models(self.host)]
        # Exact match
        if self.model in available:
            return
        # Prefix fallback only when no tag was specified (e.g. "qwen3" → "qwen3:latest").
        # If the caller specified a tag (e.g. "qwen3:27b"), that exact model is required —
        # do NOT silently substitute a different tag like "qwen3:8b".
        if ":" not in self.model:
            base = self.model
            prefix_matches = [m for m in available if m.startswith(base + ":")]
            if len(prefix_matches) == 1:
                return
        raise ModelNotFoundError(
            f"Model '{self.model}' not found in Ollama. "
            f"Available: {available}. "
            f"Pull with: ollama pull {self.model}"
        )

    def _base_payload(
        self,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        json_schema: dict[str, Any] | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                **self.options,
            },
        }
        if self.num_gpu is not None:
            payload["options"]["num_gpu"] = self.num_gpu
        if json_schema is not None:
            payload["format"] = inline_local_json_schema_refs(json_schema)
        return payload

    def _post_json(self, endpoint: str, payload: dict, timeout: int = 300) -> dict:
        """POST JSON to Ollama native API endpoint. Returns parsed response dict."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}{endpoint}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            self._handle_http_error(e.code, body)
            raise AssertionError("_handle_http_error must always raise")  # unreachable
        except urllib.error.URLError as e:
            raise BackendUnavailableError(f"Ollama unreachable: {e.reason}") from e

    def _handle_http_error(self, code: int, body: str) -> None:
        msg = body.lower()
        if "not found" in msg or "no such" in msg:
            raise ModelNotFoundError(f"Model '{self.model}' not found: {body}")
        if "context" in msg and "length" in msg:
            raise ContextLengthExceededError(body)
        raise GenerationError(f"Ollama HTTP {code}: {body}")

    def _format_messages(self, request: GenerationRequest) -> list[dict]:
        return [{"role": m.role, "content": m.content or ""} for m in request.messages]

    def _debug_payload(self, raw: dict) -> dict[str, Any] | None:
        if not self.debug:
            return None
        return raw  # raw is already a dict from _post_json

    def _extract_usage(self, raw: dict, latency_ms: float) -> UsageStats:
        input_tokens = raw.get("prompt_eval_count")
        output_tokens = raw.get("eval_count")
        usage = UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(latency_ms, 3),
        )
        if usage.input_tokens is not None and usage.output_tokens is not None:
            usage.total_tokens = usage.input_tokens + usage.output_tokens
        return usage

    def _extract_content(self, raw: dict) -> str:
        msg = raw.get("message") or {}
        return msg.get("content") or msg.get("thinking") or ""

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=True,
            streaming=True,
            async_streaming=False,
            tool_calling=False,
            embeddings=True,
            structured_output=True,
            batch_generation=False,
            vision=False,
            usage_reporting=True,
            logprobs=self._supports_logprobs,
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Generate via /api/chat. Native endpoint honours think=false."""
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        payload = self._base_payload(
            self._format_messages(request),
            request.max_tokens,
            request.temperature,
            request.json_schema,
        )
        if request.stop:
            payload["options"]["stop"] = request.stop

        t0 = time.perf_counter()
        result = self._post_json("/api/chat", payload)
        latency_ms = (time.perf_counter() - t0) * 1000
        content = self._extract_content(result)
        finish_reason = _map_finish(result.get("done_reason"))

        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason=finish_reason,  # type: ignore[arg-type]
            usage=self._extract_usage(result, latency_ms),
            model_name=self.model,
            backend=BACKEND,
            raw_provider_payload=self._debug_payload(result),
        )

    # ------------------------------------------------------------------
    # EmbeddingModel Protocol
    # ------------------------------------------------------------------

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings via /api/embed."""
        embed_model = request.model or self.model
        payload = {"model": embed_model, "input": request.texts}
        result = self._post_json("/api/embed", payload, timeout=120)
        vectors = result.get("embeddings", [])
        dims = len(vectors[0]) if vectors else 0
        return EmbeddingResponse(
            vectors=vectors,
            dimensions=dims,
            model_name=embed_model,
            backend=BACKEND,
        )

    # ------------------------------------------------------------------
    # StreamingModel Protocol
    # ------------------------------------------------------------------

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        """Stream tokens via /api/chat with stream=True."""
        if not request.messages:
            return

        payload = self._base_payload(
            self._format_messages(request),
            request.max_tokens,
            request.temperature,
        )
        payload["stream"] = True
        if request.stop:
            payload["options"]["stop"] = request.stop

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = (chunk.get("message") or {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break
        except urllib.error.URLError as e:
            raise BackendUnavailableError(f"Ollama streaming failed: {e.reason}") from e

    # ------------------------------------------------------------------
    # LogprobModel Protocol
    # ------------------------------------------------------------------

    def generate_with_logprobs(
        self,
        request: GenerationRequest,
        top_logprobs: int = 0,
    ) -> LogprobResult:
        """
        Generate with token logprobs via /v1/chat/completions.

        Requires Ollama >= 0.12.11. Used by Engram's RTRL surprise filter.
        Raises GenerationError if this Ollama instance does not support logprobs.
        """
        if not self._supports_logprobs:
            raise GenerationError(
                "Logprobs require Ollama >= 0.12.11. "
                "Upgrade with: ollama update"
            )
        try:
            from openai import OpenAI
        except ImportError as e:
            raise GenerationError(
                "generate_with_logprobs requires the openai package. "
                "Install with: pip install openai"
            ) from e

        client = OpenAI(base_url=f"{self.host}/v1", api_key="ollama")
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        actual_top = max(1, top_logprobs)

        extra_body: dict[str, Any] = {"think": self.think}
        if self.num_gpu is not None:
            extra_body["options"] = {"num_gpu": self.num_gpu}

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            logprobs=True,
            top_logprobs=actual_top,
            extra_body=extra_body,
        )
        choice = response.choices[0]
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
