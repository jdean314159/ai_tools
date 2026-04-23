from __future__ import annotations

from llm_engines.contracts import (
    EngineFitRequest,
    GPU,
    HardwareProfile,
    InferenceOptimizationRequest,
)
from llm_engines.resources import (
    estimate_engine_fit,
    probe_system_resources,
    recommend_engine_launch,
    recommend_role_placement,
)


class StubRegistry:
    def __init__(self, mapping: dict[tuple[str, str], object]) -> None:
        self.mapping = mapping

    def get_model_info(self, model: str, backend: str = "ollama"):
        key = (backend, model)
        if key not in self.mapping:
            from llm_engines.contracts import ModelNotFoundError

            raise ModelNotFoundError(model)
        return self.mapping[key]


class StubModelInfo:
    def __init__(self, recommended_vram_mb: int, min_vram_mb: int | None = None) -> None:
        self.recommended_vram_mb = recommended_vram_mb
        self.min_vram_mb = recommended_vram_mb if min_vram_mb is None else min_vram_mb


def _sample_hw() -> HardwareProfile:
    return HardwareProfile(
        gpus=[
            GPU(
                id=0,
                name="RTX 3090",
                vram_mb=24576,
                free_vram_mb=22000,
                used_vram_mb=2576,
                utilization_pct=12.0,
                source="nvidia-smi",
                compute_capability=[8, 6],
            )
        ],
        vram_total_mb=24576,
        vram_free_mb=22000,
        cpu_cores=32,
        memory_total_mb=131072,
        has_cuda=True,
        detection_sources=["nvidia-smi"],
        warnings=[],
    )


def test_probe_system_resources_returns_hardware_profile() -> None:
    hw = probe_system_resources()
    assert isinstance(hw, HardwareProfile)
    assert hw.primary_gpu_free_mb >= 0


def test_estimate_engine_fit_accounts_for_speculation_and_kv_compression() -> None:
    registry = StubRegistry(
        {
            ("vllm", "qwen2.5:14b"): StubModelInfo(recommended_vram_mb=14000),
            ("ollama", "qwen2.5:3b"): StubModelInfo(recommended_vram_mb=3000, min_vram_mb=1800),
        }
    )
    req = EngineFitRequest(
        backend="vllm",
        model="qwen2.5:14b",
        engine_role="worker",
        gpu_memory_utilization=0.90,
        context_length=4096,
        max_num_seqs=8,
        max_num_batched_tokens=8192,
        optimizations=InferenceOptimizationRequest(
            speculative_decoding=True,
            draft_model="qwen2.5:3b",
            kv_cache_compression="turboquant",
            kv_cache_bits=4,
        ),
    )

    estimate = estimate_engine_fit(req, hardware=_sample_hw(), registry=registry)

    assert estimate.backend == "vllm"
    assert estimate.engine_role == "worker"
    assert estimate.estimated_weights_mb == 14000
    assert estimate.estimated_draft_mb >= 1800
    assert estimate.estimated_kv_cache_mb > 0
    assert estimate.usable_vram_mb == int(22000 * 0.90)
    assert estimate.confidence in {"medium", "high"}
    assert any("KV-cache" in note or "Draft model" in note for note in estimate.notes)


def test_recommend_engine_launch_returns_profiles_in_order() -> None:
    registry = StubRegistry({("vllm", "qwen2.5:14b"): StubModelInfo(recommended_vram_mb=14000)})
    req = EngineFitRequest(
        backend="vllm",
        model="qwen2.5:14b",
        max_num_seqs=8,
        max_num_batched_tokens=8192,
        optimizations=InferenceOptimizationRequest(
            speculative_decoding=True,
            draft_model="qwen2.5:3b",
        ),
    )

    recs = recommend_engine_launch(req, hardware=_sample_hw(), registry=registry)

    assert [rec.profile for rec in recs] == ["safe", "balanced", "aggressive"]
    safe = recs[0]
    assert safe.parameters["gpu_memory_utilization"] <= 0.80
    assert safe.parameters["optimizations"]["kv_cache_compression"] == "turboquant"
    assert safe.parameters["optimizations"]["speculative_decoding"] is False


def test_recommend_role_placement_handles_remote_mentor_and_local_worker() -> None:
    registry = StubRegistry({("vllm", "qwen2.5:14b"): StubModelInfo(recommended_vram_mb=12000)})
    plan = recommend_role_placement(
        [
            EngineFitRequest(backend="openai", model="gpt-5", engine_role="mentor"),
            EngineFitRequest(
                backend="vllm",
                model="qwen2.5:14b",
                engine_role="worker",
                max_num_seqs=4,
                max_num_batched_tokens=4096,
            ),
        ],
        hardware=_sample_hw(),
        registry=registry,
    )

    assert plan.fits is True
    mentor = next(rec for rec in plan.recommendations if rec.engine_role == "mentor")
    worker = next(rec for rec in plan.recommendations if rec.engine_role == "worker")
    assert mentor.profile == "remote"
    assert mentor.assigned_gpu_id is None
    assert worker.assigned_gpu_id == 0


def test_recommend_role_placement_marks_no_fit_when_budgets_are_exceeded() -> None:
    registry = StubRegistry({("vllm", "qwen2.5:32b"): StubModelInfo(recommended_vram_mb=20000)})
    hw = _sample_hw()
    plan = recommend_role_placement(
        [
            EngineFitRequest(backend="vllm", model="qwen2.5:32b", engine_role="worker_a"),
            EngineFitRequest(backend="vllm", model="qwen2.5:32b", engine_role="worker_b"),
        ],
        hardware=hw,
        registry=registry,
    )

    assert plan.fits is False
    assert any("does not fit" in note for note in plan.notes)
