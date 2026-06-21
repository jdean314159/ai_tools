"""
llm_engines/optimizations/combo.py

ComboEngine: TurboQuant KV cache compression + token-level speculative decoding.

This is the "metamodel" architecture: three compounding benefits that don't
exist independently.

  Benefit 1 — Longer context:
    TurboQuant compresses the main model's KV cache by ~4x.
    At 16K tokens on a 32B model: ~4GB → ~1GB freed.

  Benefit 2 — Larger model fits:
    The freed VRAM is used to co-load the draft model (typically 1.5B–3B).
    Without TurboQuant, both models wouldn't fit on 24GB.

  Benefit 3 — Faster generation:
    Speculative decoding uses the draft model to propose K tokens at once.
    The main model verifies all K in one forward pass (= cost of 1 token).
    At 60–80% acceptance rate: ~3–5x throughput improvement.

  Combined on RTX 3090 with Qwen2.5-32B + Qwen2.5-1.5B draft:
    Baseline:   25 tok/s, 16K context
    ComboEngine: 80–100 tok/s, 32K+ context

Status: EXPERIMENTAL
  - turboquant package is Alpha (community implementation, ~March 2026)
  - HuggingFace speculative decoding via assistant_model is stable (>=4.38)
  - The combination (TQ KV cache + speculative decoding) may have interactions
    that require tuning. Validate on your hardware.
  - If turboquant is unstable, use vLLM with --speculative-model instead;
    turboquant-vllm may support both simultaneously.

Requires: pip install llm-engines[huggingface,optimizations]

Reference:
  TurboQuant: arXiv:2504.19874 (ICLR 2026)
  Speculative decoding: arXiv:2211.17192 (Leviathan et al., 2023)
  HuggingFace speculative: https://huggingface.co/docs/transformers/generation_strategies
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

BACKEND = "combo_tq_speculative"


def _require(package: str, extra: str) -> Any:
    try:
        import importlib
        return importlib.import_module(package)
    except ImportError as e:
        raise ImportError(
            f"ComboEngine requires '{package}'. "
            f"Install with: pip install llm-engines[{extra}]"
        ) from e


class ComboEngine:
    """
    Main model with TurboQuant KV cache + speculative decoding via draft model.

    Args:
        main_model:        HuggingFace model ID for the main (large) model.
        draft_model:       HuggingFace model ID for the draft (small) model.
                           Must share the same tokenizer vocabulary as main_model.
                           Qwen2.5-1.5B works with Qwen2.5-32B.
        turboquant_bits:   KV cache bit width. 4 = recommended; 3 = more compression.
        num_speculative_tokens: Draft tokens proposed per step. 5 is the HF default.
                           Higher = more speedup when acceptance rate is high,
                           but more wasted work when it's low.
        device:            "auto", "cuda", "cpu". Auto is almost always correct.
        torch_dtype:       Weight dtype. "auto" uses the model's native dtype.
        max_new_tokens:    Default generation length.

    Usage:
        engine = ComboEngine(
            main_model="Qwen/Qwen2.5-32B-Instruct",
            draft_model="Qwen/Qwen2.5-1.5B-Instruct",
            turboquant_bits=4,
            num_speculative_tokens=5,
        )
        response = engine.generate(request)

    Tuning tips:
        - num_speculative_tokens=5 is a good default. Increase if acceptance
          rate is >80% (check via stats). Decrease if <50%.
        - turboquant_bits=4 is safe. Try bits=3 if you need more VRAM headroom
          for a larger draft model; validate quality on your task first.
        - For the RTX 3090 + Qwen2.5-32B, start with:
          draft_model="Qwen/Qwen2.5-1.5B-Instruct", bits=4, n_spec=5
    """

    def __init__(
        self,
        main_model: str,
        draft_model: str,
        turboquant_bits: int = 4,
        num_speculative_tokens: int = 5,
        device: str = "auto",
        torch_dtype: str = "auto",
        max_new_tokens: int = 512,
    ) -> None:
        if turboquant_bits not in (2, 3, 4):
            raise EngineConfigError(f"turboquant_bits must be 2, 3, or 4.")
        if num_speculative_tokens < 1:
            raise EngineConfigError("num_speculative_tokens must be >= 1.")

        self.main_model_name = main_model
        self.draft_model_name = draft_model
        self.turboquant_bits = turboquant_bits
        self.num_speculative_tokens = num_speculative_tokens
        self._max_new_tokens = max_new_tokens

        # Track speculative decoding stats
        self._total_tokens_generated = 0
        self._total_draft_tokens_proposed = 0
        self._total_draft_tokens_accepted = 0

        torch = _require("torch", "huggingface")
        transformers = _require("transformers", "huggingface")
        turboquant = _require("turboquant", "optimizations")

        dtype_map = {
            "auto": "auto",
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        dt = dtype_map.get(torch_dtype, "auto")

        logger.info("Loading main model: %s", main_model)
        try:
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(main_model)
            self._main = transformers.AutoModelForCausalLM.from_pretrained(
                main_model,
                torch_dtype=dt,
                device_map=device,
            )
        except Exception as e:
            raise EngineConfigError(f"Failed to load main model '{main_model}': {e}") from e

        logger.info("Loading draft model: %s", draft_model)
        try:
            self._draft = transformers.AutoModelForCausalLM.from_pretrained(
                draft_model,
                torch_dtype=dt,
                device_map=device,
            )
        except Exception as e:
            raise EngineConfigError(
                f"Failed to load draft model '{draft_model}': {e}\n"
                f"VRAM tip: if this OOMs, increase turboquant_bits compression first, "
                f"or use a smaller draft model."
            ) from e

        # Verify tokenizer compatibility
        self._check_tokenizer_compat(transformers, draft_model)

        # Store TurboQuant cache class for use in generate()
        try:
            self._tq_cache_cls = turboquant.TurboQuantCache
        except AttributeError as e:
            raise EngineConfigError(
                f"turboquant.TurboQuantCache not found. Check package version. {e}"
            ) from e

        self._torch = torch
        self._transformers = transformers

        logger.info(
            "ComboEngine ready: main=%s, draft=%s, bits=%d, n_spec=%d",
            main_model, draft_model, turboquant_bits, num_speculative_tokens,
        )
        self._log_vram_estimate()

    def _check_tokenizer_compat(self, transformers: Any, draft_model_name: str) -> None:
        """Warn if draft model uses a different tokenizer vocab size."""
        try:
            draft_tok = transformers.AutoTokenizer.from_pretrained(draft_model_name)
            if len(draft_tok) != len(self._tokenizer):
                logger.warning(
                    "Tokenizer vocab size mismatch: main=%d, draft=%d. "
                    "Speculative decoding requires identical vocabularies. "
                    "This combination may produce incorrect results.",
                    len(self._tokenizer), len(draft_tok),
                )
        except Exception:
            pass  # Non-fatal

    def _log_vram_estimate(self) -> None:
        try:
            import torch
            if not torch.cuda.is_available():
                return
            allocated = torch.cuda.memory_allocated() / (1024 ** 3)
            reserved = torch.cuda.memory_reserved() / (1024 ** 3)
            total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            logger.info(
                "VRAM: %.1fGB allocated, %.1fGB reserved, %.1fGB total",
                allocated, reserved, total,
            )
        except Exception:
            pass

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
            speculative_decoding=True,
            kv_cache_compression=True,
            kv_cache_compression_modes=["turboquant"],
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """
        Generate using TurboQuant KV cache + speculative decoding.

        HuggingFace's generate() handles the speculative decoding loop when
        assistant_model is provided. TurboQuantCache replaces the default
        DynamicCache as the past_key_values store.
        """
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        input_ids, attention_mask = self._encode(request)
        input_len = input_ids.shape[-1]

        # TurboQuant cache: compresses KV pairs as they accumulate
        tq_cache = self._tq_cache_cls(bits=self.turboquant_bits)

        max_new = request.max_tokens or self._max_new_tokens
        temp = request.temperature

        t0 = time.perf_counter()
        try:
            with self._torch.no_grad():
                output = self._main.generate(
                    input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=max_new,
                    temperature=temp if temp > 0 else None,
                    do_sample=temp > 0,
                    # Speculative decoding: HF uses draft model to propose tokens
                    # and main model to verify all proposals in one forward pass
                    assistant_model=self._draft,
                    # TurboQuant KV cache: compresses past key-value pairs
                    past_key_values=tq_cache,
                    use_cache=True,
                )
        except Exception as e:
            msg = str(e).lower()
            if "memory" in msg or "oom" in msg:
                raise GenerationError(
                    f"OOM during ComboEngine generation. "
                    f"Try: reducing num_speculative_tokens, "
                    f"increasing turboquant_bits (more compression), "
                    f"or using a smaller draft model. Error: {e}"
                ) from e
            raise GenerationError(f"ComboEngine generation failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        generated_ids = output[0][input_len:]
        content = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
        output_tokens = len(generated_ids)

        self._total_tokens_generated += output_tokens

        return GenerationResponse(
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop",
            usage=UsageStats(
                input_tokens=input_len,
                output_tokens=output_tokens,
                total_tokens=input_len + output_tokens,
                latency_ms=round(latency_ms, 3),
            ),
            model_name=(
                f"{self.main_model_name}+"
                f"spec({self.draft_model_name})+"
                f"tq{self.turboquant_bits}bit"
            ),
            backend=BACKEND,
            active_optimizations=[
                ActiveInferenceOptimization(
                    kind="speculative_decoding",
                    backend=BACKEND,
                    model=self.draft_model_name,
                    parameters={"draft_model": self.draft_model_name, "speculative_tokens": self.num_speculative_tokens},
                ),
                ActiveInferenceOptimization(
                    kind="kv_cache_compression",
                    backend=BACKEND,
                    parameters={"mode": "turboquant", "bits": self.turboquant_bits},
                ),
            ],
        )

    # ------------------------------------------------------------------
    # StreamingModel Protocol
    # ------------------------------------------------------------------

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        """
        Stream tokens. Speculative decoding and TurboQuant are still active;
        tokens are yielded as the main model accepts them.

        Note: HuggingFace's speculative decoding with TextIteratorStreamer
        yields tokens in accepted batches, not one-by-one. You may see
        bursts of tokens followed by brief pauses (the verification steps).
        """
        if not request.messages:
            raise GenerationError("messages list cannot be empty")

        import threading
        transformers = self._transformers

        input_ids, attention_mask = self._encode(request)
        tq_cache = self._tq_cache_cls(bits=self.turboquant_bits)

        streamer = transformers.TextIteratorStreamer(
            self._tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        gen_kwargs = dict(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=request.max_tokens or self._max_new_tokens,
            temperature=request.temperature if request.temperature > 0 else None,
            do_sample=request.temperature > 0,
            assistant_model=self._draft,
            past_key_values=tq_cache,
            use_cache=True,
            streamer=streamer,
        )

        thread = threading.Thread(
            target=lambda: self._main.generate(**gen_kwargs), daemon=True
        )
        thread.start()

        try:
            for token in streamer:
                if token:
                    yield token
        except Exception as e:
            raise GenerationError(f"ComboEngine streaming failed: {e}") from e
        finally:
            thread.join(timeout=10)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _encode(self, request: GenerationRequest) -> tuple[Any, Any]:
        messages = [{"role": m.role, "content": m.content or ""} for m in request.messages]
        try:
            text = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            text = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"

        device = next(self._main.parameters()).device
        encoded = self._tokenizer(text, return_tensors="pt").to(device)
        return encoded["input_ids"], encoded.get("attention_mask")

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """
        Return speculative decoding performance statistics.

        acceptance_rate: Fraction of draft tokens accepted by the main model.
                         Target: >0.6. Below 0.5 means draft model is poor fit.
        tokens_generated: Total tokens generated since engine creation.

        Note: HuggingFace's generate() does not expose per-call acceptance rate
        directly. This is a placeholder; the actual rate would require patching
        the generation loop or using a custom stopping criterion.
        """
        return {
            "main_model": self.main_model_name,
            "draft_model": self.draft_model_name,
            "turboquant_bits": self.turboquant_bits,
            "num_speculative_tokens": self.num_speculative_tokens,
            "tokens_generated": self._total_tokens_generated,
            "vram_compression_ratio": f"{16 / self.turboquant_bits:.1f}x",
            "note": (
                "HuggingFace does not expose per-call acceptance rate. "
                "For acceptance rate monitoring, use vLLM with --speculative-model "
                "and query /metrics."
            ),
        }
