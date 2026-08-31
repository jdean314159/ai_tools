"""
llm_engines/optimizations/

Performance optimisation engines.

All engines here are EXPERIMENTAL — validate on your hardware before production use.

TurboQuantEngine:
    HuggingFace model with TurboQuant KV cache compression.
    ~4x VRAM reduction for the KV cache. Standalone, no speculative decoding.

ComboEngine:
    TurboQuant KV cache compression + token-level speculative decoding.
    The "metamodel": longer context + faster generation + larger model fits in VRAM.
    Requires: main model and draft model with matching tokenizer vocabulary.

Status of underlying packages (as of 2026-04):
    turboquant 0.2.0:   Alpha, community implementation, HuggingFace target.
                        Google official: expected Q2 2026.
    turboquant-vllm:    Alpha, Triton kernels, vLLM target.
    HF speculative:     Stable (transformers >= 4.38), via assistant_model param.

Alternative (more stable) path:
    vLLM + turboquant-vllm + --speculative-model flag at server startup.
    Use vLLMEngine — no code changes, transparent to callers.
"""

from llm_engines.optimizations.turboquant import TurboQuantEngine
from llm_engines.optimizations.combo import ComboEngine

__all__ = ["TurboQuantEngine", "ComboEngine"]
