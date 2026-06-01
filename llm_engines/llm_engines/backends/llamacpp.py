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
import time
from typing import Any, Iterator

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
    from llama_cpp import Llama  # type: ignore
except ImportError as _e:
    raise ImportError(
        "LlamaCppEngine requires llama-cpp-python. "
        "Install with: CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python"
    ) from _e

logger = logging.getLogger(__name__)

BACKEND = "llamacpp"


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
        verbose: bool = False,
        embedding: bool = False,
    ) -> None:
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self._embedding_mode = embedding

        kwargs: dict[str, Any] = {
            "model_path": model_path,
            "n_gpu_layers": n_gpu_layers,
            "n_ctx": n_ctx,
            "verbose": verbose,
            "embedding": embedding,
        }
        if n_threads is not None:
            kwargs["n_threads"] = n_threads

        logger.info(
            "Loading model %s (n_gpu_layers=%d, n_ctx=%d)",
            model_path, n_gpu_layers, n_ctx,
        )
        try:
            self._llm = Llama(**kwargs)
        except Exception as e:
            raise EngineConfigError(
                f"Failed to load model '{model_path}': {e}"
            ) from e

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

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")
        if self._embedding_mode:
            raise GenerationError(
                "This LlamaCppEngine instance is in embedding mode. "
                "Create a separate instance with embedding=False for chat."
            )

        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        completion_kwargs: dict[str, Any] = {
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stop": request.stop or [],
            "stream": False,
        }
        if request.json_schema is not None:
            completion_kwargs["response_format"] = {
                "type": "json_schema",
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
        )

    # ------------------------------------------------------------------
    # StreamingModel Protocol
    # ------------------------------------------------------------------

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]

        try:
            for chunk in self._llm.create_chat_completion(
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stop=request.stop or [],
                stream=True,
            ):
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

        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]

        try:
            raw = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                logprobs=True,
                top_logprobs=max(1, top_logprobs),
                stream=False,
            )
        except Exception as e:
            raise GenerationError(f"LlamaCppEngine logprob generation failed: {e}") from e

        choice = raw["choices"][0]
        text = choice["message"]["content"] or ""
        token_logprobs: list[TokenLogprob] = []

        logprob_info = choice.get("logprobs") or {}
        for token, lp in zip(
            logprob_info.get("tokens", []),
            logprob_info.get("token_logprobs", []),
        ):
            if lp is not None:
                token_logprobs.append(TokenLogprob(token=token, logprob=lp))

        return LogprobResult(text=text, token_logprobs=token_logprobs)

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
