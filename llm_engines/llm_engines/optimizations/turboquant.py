"""
llm_engines/optimizations/turboquant.py

TurboQuantEngine: HuggingFace model with TurboQuant KV cache compression.

TurboQuant compresses the KV cache from fp16 (16-bit) to 4-bit using a
rotation + Lloyd-Max codebook scheme. This frees ~4x VRAM from the KV cache
without meaningfully degrading output quality.

On an RTX 3090 (24GB) with Qwen2.5-32B-Instruct:
  Baseline KV cache at 16K context:  ~4GB
  TurboQuant KV cache at 16K context: ~1GB
  VRAM freed:                         ~3GB → room for a 1.5B draft model

Status: EXPERIMENTAL — turboquant package is Alpha (community implementation).
        Google's official code expected Q2 2026.
        Validate on your hardware before production use.

Requires: pip install llm-engines[huggingface,optimizations]
  (torch, transformers, accelerate, turboquant)

Reference:
  Zandieh et al., "TurboQuant: Online Vector Quantization with Near-optimal
  Distortion Rate", ICLR 2026, arXiv:2504.19874
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterator

from llm_engines.contracts import (
    ActiveInferenceOptimization,
    ChatMessage,
    EngineCapabilities,
    EngineConfigError,
    GenerationError,
    GenerationRequest,
    GenerationResponse,
    StreamingModel,
    UsageStats,
)

logger = logging.getLogger(__name__)


def _require(package: str, extra: str) -> Any:
    try:
        import importlib
        return importlib.import_module(package)
    except ImportError as e:
        raise ImportError(
            f"TurboQuantEngine requires '{package}'. "
            f"Install with: pip install llm-engines[{extra}]"
        ) from e


BACKEND = "turboquant"


class TurboQuantEngine:
    """
    HuggingFace causal LM with TurboQuant KV cache compression.

    Implements ChatModel and StreamingModel. Drop-in for any other engine.

    Args:
        model_name:     HuggingFace model ID, e.g. "Qwen/Qwen2.5-32B-Instruct".
        bits:           KV cache quantisation bits. 4 = ~4x compression (default).
                        3 = ~5x compression with slightly more quality loss.
                        2 = aggressive, noticeable degradation on long contexts.
        device:         "cuda", "cpu", or "auto" (default). "auto" uses all
                        available GPUs and offloads to CPU when needed.
        torch_dtype:    Weight dtype. "auto" uses the model's native dtype.
                        "float16" or "bfloat16" for explicit control.
        max_new_tokens: Default generation length.

    Usage:
        engine = TurboQuantEngine("Qwen/Qwen2.5-32B-Instruct", bits=4)
        response = engine.generate(request)
    """

    def __init__(
        self,
        model_name: str,
        bits: int = 4,
        device: str = "auto",
        torch_dtype: str = "auto",
        max_new_tokens: int = 512,
    ) -> None:
        if bits not in (2, 3, 4):
            raise EngineConfigError(f"TurboQuant bits must be 2, 3, or 4. Got: {bits}")

        self.model_name = model_name
        self.bits = bits
        self.device = device
        self._max_new_tokens = max_new_tokens

        # Lazy imports — avoid loading torch/transformers at module level
        torch = _require("torch", "huggingface")
        transformers = _require("transformers", "huggingface")
        turboquant = _require("turboquant", "optimizations")

        logger.info("Loading model %s (this may take a minute)...", model_name)

        dtype_map = {"auto": "auto", "float16": torch.float16, "bfloat16": torch.bfloat16}
        dt = dtype_map.get(torch_dtype, "auto")

        try:
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
            self._model = transformers.AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=dt,
                device_map=device,
            )
        except Exception as e:
            raise EngineConfigError(
                f"Failed to load model '{model_name}': {e}"
            ) from e

        # Apply TurboQuant KV cache compression
        # The turboquant package API: TurboQuantCache wraps past_key_values
        try:
            self._tq_cache_cls = turboquant.TurboQuantCache
            self._bits = bits
            logger.info(
                "TurboQuantCache applied: %d-bit KV compression (~%.1fx reduction)",
                bits, 16 / bits,
            )
        except AttributeError as e:
            raise EngineConfigError(
                f"turboquant package does not expose TurboQuantCache. "
                f"Check package version. Error: {e}"
            ) from e

        self._torch = torch
        self._transformers = transformers
        logger.info("TurboQuantEngine ready: %s", model_name)

    # ------------------------------------------------------------------
    # ChatModel Protocol
    # ------------------------------------------------------------------

    def get_capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            chat=True,
            streaming=True,
            async_streaming=False,
            tool_calling=False,
            embeddings=False,
            structured_output=False,
            batch_generation=False,
            vision=False,
            usage_reporting=True,
            logprobs=False,
            speculative_decoding=False,
            kv_cache_compression=True,
            kv_cache_compression_modes=["turboquant"],
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        input_ids, attention_mask = self._encode(request)
        input_len = input_ids.shape[-1]

        tq_cache = self._tq_cache_cls(bits=self._bits)

        t0 = time.perf_counter()
        try:
            with self._torch.no_grad():
                output = self._model.generate(
                    input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=request.max_tokens or self._max_new_tokens,
                    temperature=request.temperature if request.temperature > 0 else None,
                    do_sample=request.temperature > 0,
                    past_key_values=tq_cache,
                    use_cache=True,
                )
        except Exception as e:
            raise GenerationError(f"TurboQuantEngine generation failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        generated_ids = output[0][input_len:]
        content = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
        output_tokens = len(generated_ids)

        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop",
            usage=UsageStats(
                input_tokens=input_len,
                output_tokens=output_tokens,
                total_tokens=input_len + output_tokens,
                latency_ms=round(latency_ms, 3),
            ),
            model_name=self.model_name,
            backend=f"{BACKEND}_{self.bits}bit",
            active_optimizations=[
                ActiveInferenceOptimization(
                    kind="kv_cache_compression",
                    backend=BACKEND,
                    parameters={"mode": "turboquant", "bits": self.bits},
                )
            ],
        )

    # ------------------------------------------------------------------
    # StreamingModel Protocol
    # ------------------------------------------------------------------

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        """Stream tokens using HuggingFace TextIteratorStreamer."""
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        import threading
        transformers = self._transformers

        input_ids, attention_mask = self._encode(request)
        tq_cache = self._tq_cache_cls(bits=self._bits)

        streamer = transformers.TextIteratorStreamer(
            self._tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        gen_kwargs = dict(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=request.max_tokens or self._max_new_tokens,
            temperature=request.temperature if request.temperature > 0 else None,
            do_sample=request.temperature > 0,
            past_key_values=tq_cache,
            use_cache=True,
            streamer=streamer,
        )

        thread = threading.Thread(
            target=lambda: self._model.generate(**gen_kwargs), daemon=True
        )
        thread.start()

        try:
            for token in streamer:
                if token:
                    yield token
        except Exception as e:
            raise GenerationError(f"TurboQuantEngine streaming failed: {e}") from e
        finally:
            thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _encode(self, request: GenerationRequest):
        """Encode messages to input_ids using chat template."""
        # Build message list for apply_chat_template
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]

        try:
            text = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            # Fallback: concatenate manually if no chat template
            text = "\n".join(
                f"{m['role']}: {m['content']}" for m in messages
            ) + "\nassistant:"

        device = next(self._model.parameters()).device
        encoded = self._tokenizer(text, return_tensors="pt").to(device)
        return encoded["input_ids"], encoded.get("attention_mask")

    @property
    def vram_saved_estimate_mb(self) -> int:
        """
        Rough estimate of VRAM saved vs. fp16 KV cache at current context length.
        Useful for monitoring — not precise.
        """
        compression_ratio = 16 / self.bits
        # Very rough: assume KV cache is ~10% of model size per 1K context tokens
        model_params = sum(p.numel() for p in self._model.parameters())
        fp16_kv_per_1k = model_params * 2 / 100  # bytes, very rough
        saved = fp16_kv_per_1k * (1 - 1 / compression_ratio)
        return int(saved / (1024 * 1024))
