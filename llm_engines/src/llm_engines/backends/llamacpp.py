"""
llm_engines/backends/llamacpp.py

LlamaCppEngine: direct llama.cpp inference via llama-cpp-python.

Protocols: ChatModel, EmbeddingModel, StreamingModel
is_cloud = False

Why use this instead of OllamaEngine?
  - Direct access to logprobs without version restrictions
  - Fine-grained split-offload control (n_gpu_layers per request)
  - No Ollama server process required
  - Slightly lower latency (no HTTP round-trip)

When to prefer OllamaEngine:
  - You want model management (pull, list, switch)
  - You need the Ollama API's keep_alive behaviour
  - You don't need raw logprob access

Requires: pip install llm-engines[llama_cpp]
  (CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python for GPU support)

Typical split-offload for Qwen2.5-32B Q4_K_M on RTX 3090 (24GB):
    engine = LlamaCppEngine(
        model_path="/models/qwen2.5-32b-instruct-q4_k_m.gguf",
        n_gpu_layers=40,   # offload 40 layers to GPU, rest to CPU
        n_ctx=8192,
    )
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Iterator, cast

from llm_engines.contracts import (
    ChatMessage,
    EngineCapabilities,
    EngineConfigError,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    LogprobResult,
    TokenLogprob,
    UsageStats,
)
from llm_engines.utils.json_schema import inline_local_json_schema_refs

try:
    from llama_cpp import (
        GGML_TYPE_F16,
        GGML_TYPE_Q8_0,
        GGML_TYPE_Q4_0,
        Llama,
    )
except ImportError as _e:
    raise ImportError(
        "LlamaCppEngine requires llama-cpp-python. "
        "Install with: CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python"
    ) from _e

logger = logging.getLogger(__name__)

BACKEND = "llamacpp"

_KV_CACHE_TYPES = {
    "f16": GGML_TYPE_F16,
    "q8_0": GGML_TYPE_Q8_0,
    "q4_0": GGML_TYPE_Q4_0,
}


def _strip_think_blocks(text: str) -> str:
    stripped = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL | re.IGNORECASE)
    open_match = re.search(r"<think>", stripped, flags=re.IGNORECASE)
    if open_match and not re.search(r"</think>", stripped, flags=re.IGNORECASE):
        stripped = stripped[: open_match.start()]
    return stripped.strip()


def _resolve_kv_cache_type(name: str, *, field: str) -> int:
    try:
        return cast(int, _KV_CACHE_TYPES[name.lower()])
    except KeyError as e:
        supported = ", ".join(sorted(_KV_CACHE_TYPES))
        raise EngineConfigError(
            f"Unsupported {field}={name!r}; expected one of: {supported}"
        ) from e


def _validate_batch_settings(n_batch: int | None, n_ubatch: int | None) -> None:
    if n_batch is not None and n_batch < 1:
        raise EngineConfigError(f"n_batch must be >= 1 when set; got {n_batch}")
    if n_ubatch is not None and n_ubatch < 1:
        raise EngineConfigError(f"n_ubatch must be >= 1 when set; got {n_ubatch}")
    if n_batch is not None and n_ubatch is not None and n_ubatch > n_batch:
        raise EngineConfigError(
            f"n_ubatch must be <= n_batch when both are set; "
            f"got n_ubatch={n_ubatch}, n_batch={n_batch}"
        )


class LlamaCppEngine:
    """
    LLM engine backed by llama-cpp-python.

    Args:
        model_path:     Path to a GGUF model file.
        n_gpu_layers:   Number of layers to offload to GPU.
                        -1 = all layers (full GPU), 0 = CPU only.
                        For split-offload on RTX 3090 with 32B Q4_K_M: ~40.
        n_ctx:          Context window size in tokens. Default 4096.
        n_threads:      CPU threads for inference. Default None (auto).
        n_batch:        Logical batch size for prompt processing. Default None
                        uses llama-cpp-python's default.
        n_ubatch:       Physical micro-batch size. Must be <= n_batch when
                        both are set. Default None uses binding defaults.
        cache_type_k:   KV-cache K tensor type: "f16", "q8_0", or "q4_0".
        cache_type_v:   KV-cache V tensor type: "f16", "q8_0", or "q4_0".
        flash_attn:     Enable llama.cpp flash attention. Required by
                        llama.cpp for quantized V cache types such as q8_0.
                        Default False.
        verbose:        Enable llama.cpp verbose logging. Default False.
        embedding:      Enable embedding mode. Cannot be used with chat.
                        Create a separate instance for embeddings.
    """

    is_cloud: bool = False

    def __init__(
        self,
        model_path: str,
        n_gpu_layers: int = 0,
        n_ctx: int = 4096,
        n_threads: int | None = None,
        n_batch: int | None = None,
        n_ubatch: int | None = None,
        cache_type_k: str = "f16",
        cache_type_v: str = "f16",
        flash_attn: bool = False,
        think: bool = True,
        verbose: bool = False,
        embedding: bool = False,
    ) -> None:
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self._think = think
        self._embedding_mode = embedding
        _validate_batch_settings(n_batch, n_ubatch)

        # full-precision cache types don't need FA; everything else does
        if (
            cache_type_k not in {"f16", "f32", "bf16"} or cache_type_v not in {"f16", "f32", "bf16"}
        ) and not flash_attn:
            logger.warning(
                "Enabling flash_attn: quantized KV cache (k=%s, v=%s) requires it.",
                cache_type_k,
                cache_type_v,
            )
            flash_attn = True

        kwargs: dict[str, Any] = {
            "model_path": model_path,
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": n_ctx,
            "verbose": verbose,
            "embedding": embedding,
            "type_k": _resolve_kv_cache_type(cache_type_k, field="cache_type_k"),
            "type_v": _resolve_kv_cache_type(cache_type_v, field="cache_type_v"),
        }
        if n_threads is not None:
            kwargs["n_threads"] = n_threads
        if n_batch is not None:
            kwargs["n_batch"] = n_batch
        if n_ubatch is not None:
            kwargs["n_ubatch"] = n_ubatch
        if flash_attn:
            kwargs["flash_attn"] = True

        batch_detail = (
            f", n_batch={n_batch}, n_ubatch={n_ubatch}"
            if n_batch is not None or n_ubatch is not None
            else ""
        )
        flash_attn_detail = ", flash_attn=True" if flash_attn else ""
        logger.info(
            "Loading model %s (n_gpu_layers=%d, n_ctx=%d%s%s)",
            model_path,
            n_gpu_layers,
            n_ctx,
            batch_detail,
            flash_attn_detail,
        )
        try:
            self._llm = Llama(**kwargs)
        except Exception as e:
            raise EngineConfigError(f"Failed to load model '{model_path}': {e}") from e

        logger.info("LlamaCppEngine ready: %s", model_path)

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=not self._embedding_mode,
            streaming=not self._embedding_mode,
            async_streaming=False,
            tool_calling=False,
            embeddings=self._embedding_mode,
            structured_output=True,
            batch_generation=False,
            vision=False,
            usage_reporting=True,
            logprobs=True,
        )

    def count_tokens(self, text: str) -> int:
        return len(self._llm.tokenize(text.encode("utf-8")))

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")
        if self._embedding_mode:
            raise GenerationError(
                "This LlamaCppEngine instance is in embedding mode. "
                "Create a separate instance with embedding=False for chat."
            )

        messages = self._messages_for_request(request)
        completion_kwargs: dict[str, Any] = {
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stop": request.stop or [],
            "stream": False,
        }
        if request.seed is not None:
            completion_kwargs["seed"] = request.seed
        if request.json_schema is not None:
            completion_kwargs["response_format"] = {
                "type": "json_object",
                "schema": inline_local_json_schema_refs(request.json_schema),
            }

        t0 = time.perf_counter()
        try:
            raw = self._llm.create_chat_completion(**completion_kwargs)
        except Exception as e:
            raise GenerationError(f"LlamaCppEngine generation failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        choice = raw["choices"][0]
        content = choice["message"]["content"] or ""
        if not self._think:
            content = _strip_think_blocks(content)
        finish_reason = choice.get("finish_reason", "stop") or "stop"

        usage = raw.get("usage", {})
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")

        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason=finish_reason,  # type: ignore[arg-type]
            usage=UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=(
                    (input_tokens + output_tokens)
                    if input_tokens is not None and output_tokens is not None
                    else None
                ),
                latency_ms=round(latency_ms, 3),
            ),
            model_name=self.model_path,
            backend=BACKEND,
            seed_status="accepted" if request.seed is not None else "not_requested",
        )

    # ------------------------------------------------------------------
    # StreamingModel Protocol
    # ------------------------------------------------------------------

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages = self._messages_for_request(request)

        try:
            kwargs: dict[str, Any] = {
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stop": request.stop or [],
                "stream": True,
            }
            if request.seed is not None:
                kwargs["seed"] = request.seed
            for chunk in self._llm.create_chat_completion(**kwargs):
                delta = chunk["choices"][0].get("delta", {})
                token = delta.get("content")
                if token:
                    yield token
        except Exception as e:
            raise GenerationError(f"LlamaCppEngine streaming failed: {e}") from e

    # ------------------------------------------------------------------
    # LogprobModel Protocol
    # ------------------------------------------------------------------

    def generate_with_logprobs(
        self,
        request: GenerationRequest,
        top_logprobs: int = 0,
    ) -> LogprobResult:
        """Generate with per-token logprobs. Used by Engram's RTRL surprise filter."""
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages = self._messages_for_request(request)

        try:
            kwargs = {
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "logprobs": True,
                "top_logprobs": max(1, top_logprobs),
                "stream": False,
            }
            if request.seed is not None:
                kwargs["seed"] = request.seed
            raw = self._llm.create_chat_completion(**kwargs)
        except Exception as e:
            raise GenerationError(f"LlamaCppEngine logprob generation failed: {e}") from e

        choice = raw["choices"][0]
        text = choice["message"]["content"] or ""
        if not self._think:
            text = _strip_think_blocks(text)
        token_logprobs: list[TokenLogprob] = []

        logprob_info = choice.get("logprobs") or {}
        for token, lp in zip(
            logprob_info.get("tokens", []),
            logprob_info.get("token_logprobs", []),
        ):
            if lp is not None:
                token_logprobs.append(TokenLogprob(token=token, logprob=lp))

        return LogprobResult(text=text, token_logprobs=token_logprobs)

    def _messages_for_request(self, request: GenerationRequest) -> list[dict[str, str]]:
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        if self._think:
            return messages

        target_index = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                target_index = i
                break
        if target_index is None:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]["role"] == "system":
                    target_index = i
                    break
        if target_index is None:
            target_index = len(messages) - 1

        # Qwen3 supports this soft switch to suppress reasoning at generation time.
        messages[target_index]["content"] = f"{messages[target_index]['content']} /no_think"
        return messages

    # ------------------------------------------------------------------
    # EmbeddingModel Protocol
    # ------------------------------------------------------------------

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """
        Generate embeddings. Requires embedding=True at construction.

        Note: llama-cpp-python requires a separate Llama instance for embeddings
        vs. chat. Create two instances if you need both:
            chat_engine  = LlamaCppEngine(path, n_gpu_layers=40)
            embed_engine = LlamaCppEngine(path, n_gpu_layers=40, embedding=True)
        """
        if not self._embedding_mode:
            raise GenerationError(
                "This LlamaCppEngine instance is in chat mode. "
                "Create a separate instance with embedding=True for embeddings."
            )

        try:
            vectors = [self._llm.embed(text) for text in request.texts]
        except Exception as e:
            raise GenerationError(f"LlamaCppEngine embed failed: {e}") from e

        dims = len(vectors[0]) if vectors else 0
        return EmbeddingResponse(
            vectors=vectors,
            dimensions=dims,
            model_name=self.model_path,
            backend=BACKEND,
        )
