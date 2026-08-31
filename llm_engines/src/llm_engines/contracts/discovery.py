"""
contracts/discovery.py

Hardware detection and model registry contracts.
Canonical home for HardwareProfile, ModelRegistry, and related types.

These types are implemented in llm_engines/discovery.py.
Engram imports from there (not directly from contracts).

ADR: Covered under ADR-001 (Engine Capability Model)
Status: Pending ADR acceptance
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .engine import EngineCapabilities


# ---------------------------------------------------------------------------
# Hardware detection
# ---------------------------------------------------------------------------


class GPU(BaseModel):
    """Single GPU as detected by the hardware probe."""

    id: int
    name: str
    vram_mb: int
    free_vram_mb: int | None = None
    used_vram_mb: int | None = None
    utilization_pct: float | None = None
    source: str | None = None
    # list[int] rather than tuple[int, int]: tuples don't round-trip through
    # JSON without a custom serialiser, and Pydantic v2 will coerce anyway.
    compute_capability: list[int] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="[major, minor] CUDA compute capability, e.g. [8, 6]",
    )


class HardwareProfile(BaseModel):
    """Detected hardware capabilities of the current machine."""

    gpus: list[GPU] = Field(default_factory=list)
    vram_total_mb: int = 0  # Sum across all GPUs; 0 = CPU-only
    vram_free_mb: int = 0  # Sum across all GPUs; 0 = unknown/CPU-only
    cpu_cores: int = 1
    memory_total_mb: int = 0  # System RAM
    has_cuda: bool = False
    detection_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_cpu_only(self) -> bool:
        return not self.has_cuda or self.vram_total_mb == 0

    @property
    def primary_gpu(self) -> GPU | None:
        if not self.gpus:
            return None
        return max(self.gpus, key=lambda gpu: gpu.vram_mb)

    @property
    def primary_gpu_free_mb(self) -> int:
        gpu = self.primary_gpu
        if gpu is None:
            return 0
        return int(gpu.free_vram_mb or gpu.vram_mb)


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

TaskType = Literal["chat", "embeddings", "coding", "general"]


class ModelInfo(BaseModel):
    """Metadata for a single model known to the registry."""

    name: str
    backend: str
    size_gb: float
    min_vram_mb: int  # Minimum to load at all (may swap heavily)
    recommended_vram_mb: int  # Comfortable inference VRAM
    capabilities: EngineCapabilities = Field(default_factory=EngineCapabilities)
    quantization: str | None = None  # e.g. "Q4_K_M", "fp16", "int8"


class ModelRegistry:
    """
    Enumerate, inspect, and recommend models.

    Concrete implementation lives in llm_engines/discovery.py.
    VRAM requirements come from a bundled model_catalog.yaml — the Ollama
    /api/tags endpoint does not expose min/recommended VRAM.
    """

    def list_available_models(self, backend: str = "ollama") -> list[str]:
        """
        List models currently available on the given backend.

        Args:
            backend: "ollama" | "anthropic" | "openai" | "huggingface"

        Returns:
            Sorted list of model name strings.

        Example:
            >>> registry = ModelRegistry()
            >>> registry.list_available_models("ollama")
            ['nomic-embed-text', 'qwen2.5:14b', 'qwen2.5:35b', 'qwen2.5:8b']

        Raises:
            BackendUnavailableError: if backend is unreachable.
        """
        raise NotImplementedError

    def get_model_info(self, model: str, backend: str = "ollama") -> ModelInfo:
        """
        Return metadata for a model, merging live backend data with catalog.

        Raises:
            ModelNotFoundError: if model is not in catalog or backend.
        """
        raise NotImplementedError

    def recommend_model(
        self,
        task: TaskType,
        hardware: HardwareProfile,
        backend: str = "ollama",
        prefer_speed: bool = False,
    ) -> str:
        """
        Recommend the best available model for a task given hardware constraints.

        Selection priority:
            1. Model must fit in available VRAM (or CPU RAM if CPU-only).
            2. If prefer_speed=True, choose smallest fitting model.
            3. Otherwise, choose largest fitting model (quality priority).

        Returns:
            Model name string suitable for passing to an engine constructor.

        Raises:
            ModelNotFoundError: if no suitable model is available.
            BackendUnavailableError: if backend is unreachable.
        """
        raise NotImplementedError

    def download_model(self, model: str, backend: str = "ollama") -> bool:
        """
        Trigger download of a model if not already present.

        Returns:
            True if the model is ready after this call.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# detect_hardware() function signature
# ---------------------------------------------------------------------------


def detect_hardware() -> HardwareProfile:
    """
    Probe the current machine and return a HardwareProfile.

    Detects CUDA GPUs via pynvml (if available), falls back to
    torch.cuda if pynvml is absent, and falls back to CPU-only
    if neither is available.

    Example:
        >>> hw = detect_hardware()
        >>> print(f"VRAM: {hw.vram_total_mb} MB, CUDA: {hw.has_cuda}")
        VRAM: 24576 MB, CUDA: True

    Raises:
        Never raises. Always returns a valid HardwareProfile.
    """
    raise NotImplementedError
