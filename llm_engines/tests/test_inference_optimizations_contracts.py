from __future__ import annotations

from llm_engines.contracts import (
    ActiveInferenceOptimization,
    ChatMessage,
    EngineCapabilities,
    GenerationRequest,
    GenerationResponse,
    InferenceOptimizationRequest,
)


def test_generation_request_accepts_optimization_hints() -> None:
    request = GenerationRequest(
        messages=[ChatMessage(role="user", content="Hello")],
        optimizations=InferenceOptimizationRequest(
            speculative_decoding=True,
            draft_model="Qwen/Qwen2.5-1.5B-Instruct",
            speculative_tokens=5,
            kv_cache_compression="turboquant",
            kv_cache_bits=4,
        ),
    )

    assert request.optimizations is not None
    assert request.optimizations.speculative_decoding is True
    assert request.optimizations.kv_cache_compression == "turboquant"


def test_generation_response_reports_active_optimizations() -> None:
    response = GenerationResponse(
        message=ChatMessage(role="assistant", content="Hi"),
        model_name="demo",
        backend="demo",
        active_optimizations=[
            ActiveInferenceOptimization(
                kind="speculative_decoding",
                backend="demo",
                model="draft-model",
                parameters={"speculative_tokens": 5},
            )
        ],
    )

    assert response.active_optimizations[0].kind == "speculative_decoding"
    assert response.active_optimizations[0].model == "draft-model"


def test_engine_capabilities_surface_optimization_support() -> None:
    caps = EngineCapabilities(
        speculative_decoding=True,
        kv_cache_compression=True,
        kv_cache_compression_modes=["turboquant"],
    )

    assert caps.speculative_decoding is True
    assert caps.kv_cache_compression is True
    assert caps.kv_cache_compression_modes == ["turboquant"]
