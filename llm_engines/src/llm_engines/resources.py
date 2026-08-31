"""Resource probing and launch-advisory helpers for local engine runtimes.

The intent is to give applications a reusable way to answer questions like:
- What GPU resources are available right now?
- Will this model + backend configuration fit locally?
- Which launch parameters are the safest/balanced/most aggressive?
- Can multiple engine roles fit on this machine at the same time?

The estimates in this module are intentionally heuristic. They should provide a
useful, explainable preflight rather than pretend to know the exact runtime
footprint for every backend and model family.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from llm_engines.contracts import (
    EngineFitEstimate,
    EngineFitRequest,
    EngineLaunchRecommendation,
    HardwareProfile,
    InferenceOptimizationRequest,
    ModelNotFoundError,
    RolePlacementPlan,
)
from llm_engines.discovery import ModelRegistry, detect_hardware


_REMOTE_BACKENDS = {"anthropic", "openai", "gemini", "google", "chatgpt", "claude"}
_LOCAL_BACKENDS = {"vllm", "ollama", "llamacpp", "llama.cpp"}


Confidence = Literal["low", "medium", "high"]
LaunchProfile = Literal["safe", "balanced", "aggressive", "remote"]


@dataclass(frozen=True)
class _ModelSizing:
    weights_mb: int
    confidence: Confidence
    notes: list[str]


def probe_system_resources() -> HardwareProfile:
    """Return the current hardware profile.

    This is a thin named wrapper over :func:`detect_hardware` so callers can
    depend on a resource-oriented API without importing discovery internals.
    """

    return detect_hardware()


def estimate_engine_fit(
    request: EngineFitRequest,
    *,
    hardware: HardwareProfile | None = None,
    registry: ModelRegistry | None = None,
    gpu_id: int | None = None,
) -> EngineFitEstimate:
    hardware = hardware or probe_system_resources()
    registry = registry or ModelRegistry()
    backend = request.backend.lower().strip()

    if backend in _REMOTE_BACKENDS:
        remote_note = (
            "Remote/API backend selected; local GPU fit is not required for the main model."
        )
        return EngineFitEstimate(
            backend=request.backend,
            model=request.model,
            engine_role=request.engine_role,
            gpu_id=None,
            free_vram_mb=hardware.primary_gpu_free_mb,
            usable_vram_mb=hardware.primary_gpu_free_mb,
            estimated_total_mb=0,
            estimated_headroom_mb=hardware.primary_gpu_free_mb,
            fits=True,
            confidence="high",
            assumptions={"backend_mode": "remote"},
            notes=[remote_note],
        )

    note: str | None
    if backend not in _LOCAL_BACKENDS:
        note = f"Unknown backend '{request.backend}'. Using generic local fit heuristics."
    else:
        note = None

    gpu = _select_gpu(hardware, gpu_id=gpu_id)
    free_vram_mb = int(
        (gpu.free_vram_mb if gpu and gpu.free_vram_mb is not None else (gpu.vram_mb if gpu else 0))
        or 0
    )
    total_vram_mb = int((gpu.vram_mb if gpu else hardware.vram_total_mb) or 0)
    usable_vram_mb = (
        int(free_vram_mb * float(request.gpu_memory_utilization or 0.90))
        if free_vram_mb
        else int(total_vram_mb * float(request.gpu_memory_utilization or 0.90))
    )

    sizing = _resolve_model_sizing(request, registry)
    draft_mb, draft_notes = _estimate_draft_model_mb(request.optimizations, registry)
    kv_mb, kv_assumptions, kv_notes = _estimate_kv_cache_mb(request, usable_vram_mb)

    total_estimated_mb = sizing.weights_mb + draft_mb + kv_mb
    headroom_mb = usable_vram_mb - total_estimated_mb
    fits = total_estimated_mb <= usable_vram_mb and headroom_mb >= 512

    notes: list[str] = []
    notes.extend(sizing.notes)
    notes.extend(draft_notes)
    notes.extend(kv_notes)
    if note:
        notes.append(note)
    if gpu is None:
        notes.append("No CUDA GPU detected; local backends may need CPU/offload modes.")
    if hardware.warnings:
        notes.extend(hardware.warnings)

    confidence = _merge_confidence(
        sizing.confidence, "high" if gpu and gpu.free_vram_mb is not None else "medium"
    )
    if draft_mb and request.optimizations and request.optimizations.draft_model:
        confidence = _merge_confidence(confidence, "medium")

    return EngineFitEstimate(
        backend=request.backend,
        model=request.model,
        engine_role=request.engine_role,
        gpu_id=(gpu.id if gpu else None),
        free_vram_mb=free_vram_mb,
        usable_vram_mb=usable_vram_mb,
        estimated_weights_mb=sizing.weights_mb,
        estimated_draft_mb=draft_mb,
        estimated_kv_cache_mb=kv_mb,
        estimated_total_mb=total_estimated_mb,
        estimated_headroom_mb=headroom_mb,
        fits=fits,
        confidence=confidence,
        assumptions={
            "gpu_memory_utilization": request.gpu_memory_utilization,
            "context_length": request.context_length,
            "max_num_seqs": request.max_num_seqs,
            "max_num_batched_tokens": request.max_num_batched_tokens,
            **kv_assumptions,
        },
        notes=notes,
    )


def recommend_engine_launch(
    request: EngineFitRequest,
    *,
    hardware: HardwareProfile | None = None,
    registry: ModelRegistry | None = None,
) -> list[EngineLaunchRecommendation]:
    hardware = hardware or probe_system_resources()
    registry = registry or ModelRegistry()
    backend = request.backend.lower().strip()

    if backend in _REMOTE_BACKENDS:
        remote_estimate = estimate_engine_fit(request, hardware=hardware, registry=registry)
        return [
            EngineLaunchRecommendation(
                profile="remote",
                backend=request.backend,
                model=request.model,
                engine_role=request.engine_role,
                parameters={},
                estimate=remote_estimate,
                rationale=[
                    "Use the remote provider as configured; local GPU placement is not required.",
                ],
            )
        ]

    profiles = [
        _profile_request(request, profile="safe"),
        _profile_request(request, profile="balanced"),
        _profile_request(request, profile="aggressive"),
    ]
    recommendations: list[EngineLaunchRecommendation] = []
    for profile_name, profiled_request, rationale in profiles:
        estimate = estimate_engine_fit(profiled_request, hardware=hardware, registry=registry)
        params: dict[str, Any] = {
            "gpu_memory_utilization": profiled_request.gpu_memory_utilization,
            "max_num_seqs": profiled_request.max_num_seqs,
            "max_num_batched_tokens": profiled_request.max_num_batched_tokens,
            "context_length": profiled_request.context_length,
        }
        if profiled_request.optimizations is not None:
            params["optimizations"] = profiled_request.optimizations.model_dump(exclude_none=True)
        recommendations.append(
            EngineLaunchRecommendation(
                profile=profile_name,
                backend=request.backend,
                model=request.model,
                engine_role=request.engine_role,
                assigned_gpu_id=estimate.gpu_id,
                parameters=params,
                estimate=estimate,
                rationale=rationale + _fit_rationale(estimate),
            )
        )
    return recommendations


def recommend_role_placement(
    requests: Iterable[EngineFitRequest],
    *,
    hardware: HardwareProfile | None = None,
    registry: ModelRegistry | None = None,
) -> RolePlacementPlan:
    hardware = hardware or probe_system_resources()
    registry = registry or ModelRegistry()

    gpu_budgets: dict[int, int] = {
        gpu.id: int(gpu.free_vram_mb if gpu.free_vram_mb is not None else gpu.vram_mb)
        for gpu in hardware.gpus
    }
    recommendations: list[EngineLaunchRecommendation] = []
    notes: list[str] = []
    fits = True

    for request in requests:
        backend = request.backend.lower().strip()
        recs = recommend_engine_launch(request, hardware=hardware, registry=registry)
        chosen = next(
            (rec for rec in recs if rec.profile in {"safe", "remote"} and rec.estimate.fits),
            recs[0],
        )
        if backend in _REMOTE_BACKENDS:
            recommendations.append(chosen)
            continue

        assigned_gpu = _assign_gpu(chosen, gpu_budgets)
        if assigned_gpu is None:
            fits = False
            notes.append(
                f"Role '{request.engine_role or request.model}' does not fit within current free GPU budgets."
            )
            recommendations.append(chosen)
            continue

        gpu_budgets[assigned_gpu] -= max(chosen.estimate.estimated_total_mb, 0)
        recommendations.append(chosen.model_copy(update={"assigned_gpu_id": assigned_gpu}))

    if not hardware.gpus:
        notes.append(
            "No local CUDA GPUs detected. Role placement can only advise remote/API roles."
        )
        fits = fits and all(rec.profile == "remote" for rec in recommendations)

    return RolePlacementPlan(fits=fits, recommendations=recommendations, notes=notes)


def _select_gpu(hardware: HardwareProfile, *, gpu_id: int | None = None) -> Any | None:
    if not hardware.gpus:
        return None
    if gpu_id is not None:
        for gpu in hardware.gpus:
            if gpu.id == gpu_id:
                return gpu
    return max(
        hardware.gpus,
        key=lambda gpu: int(gpu.free_vram_mb if gpu.free_vram_mb is not None else gpu.vram_mb),
    )


def _resolve_model_sizing(request: EngineFitRequest, registry: ModelRegistry) -> _ModelSizing:
    if request.requested_vram_mb is not None:
        return _ModelSizing(
            weights_mb=int(request.requested_vram_mb),
            confidence="medium",
            notes=[
                "Using caller-supplied requested_vram_mb because the model size was not resolved from the catalog."
            ],
        )

    try:
        info = registry.get_model_info(request.model, backend=request.backend)
        baseline_mb = info.recommended_vram_mb or info.min_vram_mb
        notes = [
            f"Estimated weights from model catalog: {baseline_mb} MB recommended VRAM.",
        ]
        return _ModelSizing(weights_mb=int(baseline_mb), confidence="high", notes=notes)
    except ModelNotFoundError:
        fallback = 8192
        return _ModelSizing(
            weights_mb=fallback,
            confidence="low",
            notes=[
                "Model not found in the catalog; using a conservative 8 GB baseline. Set requested_vram_mb to override.",
            ],
        )


def _estimate_draft_model_mb(
    optimizations: InferenceOptimizationRequest | None,
    registry: ModelRegistry,
) -> tuple[int, list[str]]:
    if optimizations is None or not optimizations.speculative_decoding:
        return 0, []
    draft_model = (optimizations.draft_model or "").strip()
    if not draft_model:
        return 1024, [
            "Speculative decoding enabled without a known draft model; reserving 1 GB for the draft path."
        ]
    try:
        info = registry.get_model_info(draft_model, backend="ollama")
        return int(info.min_vram_mb or info.recommended_vram_mb), [
            f"Draft model '{draft_model}' contributes additional VRAM pressure."
        ]
    except ModelNotFoundError:
        return 1024, [
            f"Draft model '{draft_model}' is not in the catalog; reserving 1 GB heuristically."
        ]


def _estimate_kv_cache_mb(
    request: EngineFitRequest,
    usable_vram_mb: int,
) -> tuple[int, dict[str, int | float | str], list[str]]:
    tokens = max(request.context_length * request.max_num_seqs, request.max_num_batched_tokens)
    base_kv_mb = max(512, int(tokens * 0.08))
    assumptions: dict[str, int | float | str] = {
        "kv_cache_token_factor_mb_per_token": 0.08,
        "kv_cache_tokens_basis": tokens,
    }
    notes = [
        "KV-cache estimate is heuristic and should be validated after launch with actual runtime measurements.",
    ]
    effective_kv_mb = base_kv_mb

    optimizations = request.optimizations
    if optimizations and optimizations.kv_cache_compression:
        mode = optimizations.kv_cache_compression
        bits = int(optimizations.kv_cache_bits or 4)
        factor = 0.35 if mode == "turboquant" and bits <= 4 else 0.50
        effective_kv_mb = max(256, int(base_kv_mb * factor))
        assumptions["kv_cache_compression_mode"] = mode
        assumptions["kv_cache_compression_bits"] = bits
        assumptions["kv_cache_compression_factor"] = factor
        notes.append(f"Applying heuristic KV-cache reduction for {mode} compression ({bits}-bit).")

    if usable_vram_mb and effective_kv_mb > int(usable_vram_mb * 0.40):
        notes.append(
            "Estimated KV-cache budget is consuming more than 40% of usable VRAM; consider lowering concurrency."
        )
    return effective_kv_mb, assumptions, notes


def _profile_request(
    request: EngineFitRequest,
    *,
    profile: LaunchProfile,
) -> tuple[LaunchProfile, EngineFitRequest, list[str]]:
    base_opts = (
        request.optimizations.model_copy(deep=True) if request.optimizations is not None else None
    )
    rationale: list[str] = []
    if profile == "safe":
        if base_opts is not None and base_opts.speculative_decoding:
            base_opts.speculative_decoding = False
            base_opts.draft_model = None
            rationale.append(
                "Safe profile disables speculative decoding to preserve VRAM headroom."
            )
        if base_opts is None:
            base_opts = InferenceOptimizationRequest(
                kv_cache_compression="turboquant", kv_cache_bits=4
            )
            rationale.append(
                "Safe profile enables 4-bit KV-cache compression to maximize fit margin."
            )
        elif not base_opts.kv_cache_compression:
            base_opts.kv_cache_compression = "turboquant"
            base_opts.kv_cache_bits = base_opts.kv_cache_bits or 4
            rationale.append("Safe profile adds KV-cache compression to maximize fit margin.")
        return (
            profile,
            request.model_copy(
                update={
                    "gpu_memory_utilization": min(float(request.gpu_memory_utilization), 0.80),
                    "max_num_seqs": max(1, request.max_num_seqs // 2),
                    "max_num_batched_tokens": max(1024, request.max_num_batched_tokens // 2),
                    "optimizations": base_opts,
                }
            ),
            rationale,
        )
    if profile == "balanced":
        return (
            profile,
            request.model_copy(
                update={
                    "gpu_memory_utilization": min(float(request.gpu_memory_utilization), 0.88),
                    "optimizations": base_opts,
                }
            ),
            [
                "Balanced profile keeps requested concurrency while capping GPU utilization at a moderate level."
            ],
        )
    return (
        profile,
        request.model_copy(
            update={
                "gpu_memory_utilization": max(float(request.gpu_memory_utilization), 0.94),
                "max_num_seqs": max(request.max_num_seqs, int(request.max_num_seqs * 1.5)),
                "max_num_batched_tokens": max(
                    request.max_num_batched_tokens, int(request.max_num_batched_tokens * 1.5)
                ),
                "optimizations": base_opts,
            }
        ),
        ["Aggressive profile trades launch headroom for higher utilization and concurrency."],
    )


def _fit_rationale(estimate: EngineFitEstimate) -> list[str]:
    if estimate.fits:
        return [
            f"Estimated total footprint {estimate.estimated_total_mb} MB fits within usable VRAM {estimate.usable_vram_mb} MB.",
            f"Estimated headroom after launch: {estimate.estimated_headroom_mb} MB.",
        ]
    return [
        f"Estimated total footprint {estimate.estimated_total_mb} MB exceeds usable VRAM {estimate.usable_vram_mb} MB or leaves insufficient headroom.",
        "Reduce concurrency, lower GPU utilization, enable KV-cache compression, or choose a smaller model/draft model.",
    ]


def _assign_gpu(
    recommendation: EngineLaunchRecommendation, gpu_budgets: dict[int, int]
) -> int | None:
    if not gpu_budgets:
        return None
    needed = max(recommendation.estimate.estimated_total_mb, 0)
    candidates = sorted(gpu_budgets.items(), key=lambda item: item[1], reverse=True)
    for gpu_id, budget in candidates:
        if budget >= needed:
            return gpu_id
    return None


def _merge_confidence(left: Confidence, right: Confidence) -> Confidence:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order.get(left, 0) <= order.get(right, 0) else right
