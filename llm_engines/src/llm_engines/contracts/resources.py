"""Resource probing and engine-fit advisory contracts.

These contracts are owned by ``llm_engines`` because they describe how local
engine runtimes fit onto available hardware. Higher-level packages should
consume these models rather than invent their own launch heuristics.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .engine import InferenceOptimizationRequest


class EngineFitRequest(BaseModel):
    """Request for a backend-specific fit estimate.

    ``requested_vram_mb`` can be used when the model is not in the catalog yet,
    for example for a freshly downloaded HuggingFace repo.
    """

    backend: str
    model: str
    engine_role: str | None = None
    requested_vram_mb: int | None = None
    gpu_memory_utilization: float = Field(default=0.90, ge=0.10, le=1.0)
    context_length: int = Field(default=4096, ge=1)
    max_num_seqs: int = Field(default=8, ge=1)
    max_num_batched_tokens: int = Field(default=8192, ge=1)
    optimizations: InferenceOptimizationRequest | None = None
    prefer_speed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineFitEstimate(BaseModel):
    """Heuristic estimate for whether an engine configuration fits locally."""

    backend: str
    model: str
    engine_role: str | None = None
    gpu_id: int | None = None
    free_vram_mb: int = 0
    usable_vram_mb: int = 0
    estimated_weights_mb: int = 0
    estimated_draft_mb: int = 0
    estimated_kv_cache_mb: int = 0
    estimated_total_mb: int = 0
    estimated_headroom_mb: int = 0
    fits: bool = False
    confidence: Literal["low", "medium", "high"] = "medium"
    assumptions: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class EngineLaunchRecommendation(BaseModel):
    """Suggested launch profile and parameters for a single engine."""

    profile: Literal["safe", "balanced", "aggressive", "remote"]
    backend: str
    model: str
    engine_role: str | None = None
    assigned_gpu_id: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    estimate: EngineFitEstimate
    rationale: list[str] = Field(default_factory=list)


class RolePlacementPlan(BaseModel):
    """Placement plan for one or more engine roles."""

    fits: bool = False
    recommendations: list[EngineLaunchRecommendation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
